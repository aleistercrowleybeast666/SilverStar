/* Separate RF56 qualification probe. The original 200Hz-barometer stress and
 * its expectations remain unchanged. Sensors, attitude/origin preparation,
 * time, scheduling and SD medium are Host models. Actual Flight START record
 * capture/retry, SF6 backend logging, LoggerBus/Task and FatFs execute below.
 * Includes expose static Flight owner operations only in this Host TU.
 * setjmp/longjmp terminate Host task loops; this is never MCU recovery. */
#define SystemTime_GetMonotonicUs Rf_LegacyMonotonicUs
#define ProjectDeviceInstance_DescriptorGet Rf_LegacyDescriptorGet
#include "test_logger_storage.c"
#undef ProjectDeviceInstance_DescriptorGet
#undef SystemTime_GetMonotonicUs

uint64_t SystemTime_GetMonotonicUs(void);
#include "../../../APP/Src/flight_task.c"
#include "system_navigation_backend.h"
#include "system_estimator_profile.h"
#include "system_gnss_quality.h"
#include "common_spsc_queue.h"
#include "platform_time.h"

#define RF_FRAME_COUNT 6000U
#define RF_START_FRAME 1200U
#define RF_START_STALL_MS 80U
#define RF_REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "RF_FAIL line=%d condition=%s\n", __LINE__, #condition); \
    exit(11); } } while (0)

static EstimatorOutputSnapshot s_rf_output;
static uint32_t s_rf_drops[64];
static uint32_t s_rf_records[64];
static uint32_t s_rf_start_records;
static uint32_t s_rf_start_streams;
static uint32_t s_rf_start_syncs;
static uint32_t s_rf_last_synced_generation;
static uint32_t s_rf_ack_count;
static uint32_t s_rf_predicts;
static uint32_t s_rf_baro_samples;
static uint32_t s_rf_gnss_samples;
static uint32_t s_rf_imu_samples;
static uint64_t s_rf_first_flight_us;
static uint64_t s_rf_last_flight_us;
static uint8_t s_rf_started;
static uint8_t s_rf_stall_done;
static uint8_t s_rf_sync_fault;
static uint8_t s_rf_fault_observed;
static uint8_t s_rf_last_sync_ok;
static uint32_t s_rf_delay_ms = RF_START_STALL_MS;

static void Rf_Produce(void);

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance,
    SystemDeviceDescriptor *descriptor)
{
    return SystemDescriptor_DeviceFind(device_class, instance, descriptor);
}

uint8_t Ins_GetAlignmentSnapshot(InsAlignmentSnapshot *snapshot)
{
    if (snapshot == NULL) { return 0U; }
    memset(snapshot, 0, sizeof(*snapshot));
    snapshot->algorithm = SYSTEM_ALIGNMENT_ALGORITHM;
    snapshot->valid = 1U; snapshot->q_nb[0] = 1.0f;
    snapshot->sample_count = 1000U;
    snapshot->acceleration_mean_b_mps2[2] = SYSTEM_INS_GRAVITY_MPS2;
    return 1U;
}

uint8_t Estimator_GetInitialStateSnapshot(EstimatorInitialStateSnapshot *snapshot)
{
    const SystemEstimatorProfile *profile = SystemEstimatorProfile_Get();
    if (snapshot == NULL || profile == NULL) { return 0U; }
    memset(snapshot, 0, sizeof(*snapshot));
    snapshot->valid = 1U;
    snapshot->gnss_origin_valid = 1U; snapshot->barometer_origin_valid = 1U;
    snapshot->gnss_sample_count = 100U; snapshot->barometer_sample_count = 100U;
    snapshot->velocity_valid_mask = 7U;
    snapshot->barometer_origin_std_m = profile->barometer_altitude_std_m;
    memcpy(snapshot->p0_diagonal, profile->p0_diagonal, sizeof(profile->p0_diagonal));
    for (unsigned axis = 0U; axis < 3U; axis++)
    { snapshot->initial_velocity_std_mps[axis] = sqrtf(profile->p0_diagonal[axis + 3U]); }
    return 1U;
}

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_gnss[0];
    return SYSTEM_DEVICE_OK;
}

PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }
uint64_t __wrap_SystemTime_GetMonotonicUs(void) { return Rf_LegacyMonotonicUs(); }

CommonSpscQueueResult __real_CommonSpscQueue_Push(CommonSpscQueue *, const void *);
CommonSpscQueueResult __wrap_CommonSpscQueue_Push(CommonSpscQueue *queue, const void *data)
{
    CommonSpscQueueResult result = __real_CommonSpscQueue_Push(queue, data);
    if (result == COMMON_SPSC_QUEUE_RESULT_FULL && queue != NULL && data != NULL &&
        queue->item_size == SYSTEM_LOG_RECORD_SLOT_SIZE)
    {
        FlightLogRecordType type;
        memcpy(&type, (const uint8_t *)data + offsetof(FlightLogRecord, record_type), sizeof(type));
        RF_REQUIRE((unsigned)type < 64U);
        s_rf_drops[type]++;
        uint64_t timestamp;
        memcpy(&timestamp, (const uint8_t *)data + offsetof(FlightLogRecord, timestamp_us), sizeof(timestamp));
        printf("RF_DROP type=%u sample_us=%llu frame=%lu queued=%u\n", (unsigned)type,
            (unsigned long long)timestamp, (unsigned long)(s_produced - 1U), CommonSpscQueue_Count(queue));
    }
    return result;
}

FlightLogSerializeResult __real_FlightLog_RecordSerialize(const FlightLogRecord *,
    uint32_t, uint8_t *, uint16_t, uint16_t *);
FlightLogSerializeResult __wrap_FlightLog_RecordSerialize(const FlightLogRecord *record,
    uint32_t sequence, uint8_t *buffer, uint16_t capacity, uint16_t *length)
{
    FlightLogSerializeResult result = __real_FlightLog_RecordSerialize(record, sequence, buffer, capacity, length);
    if (result != FLIGHT_LOG_SERIALIZE_RESULT_OK) { return result; }
    RF_REQUIRE((unsigned)record->record_type < 64U);
    s_rf_records[record->record_type]++;
    if (s_start_log.pending != 0U && s_start_log.generation != 0U &&
        (record->record_type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG ||
         record->record_type == FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR ||
         record->record_type == FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR ||
         record->record_type == FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR ||
         record->record_type == FLIGHT_LOG_RECORD_MISSION_CONFIG ||
         record->record_type == FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY ||
         record->record_type == FLIGHT_LOG_RECORD_INITIAL_STATE ||
         (record->record_type == FLIGHT_LOG_RECORD_EVENT &&
          record->payload.event.event_id == FLIGHT_LOG_EVENT_MISSION_START)))
    {
        s_rf_start_records++;
        if (record->record_type == FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR) { s_rf_start_streams++; }
    }
    return result;
}

FRESULT __real_f_sync(FIL *);
FRESULT __wrap_f_sync(FIL *file)
{
    uint32_t generation = LoggerBus_StartBarrierGet();
    if (generation != 0U && s_rf_stall_done == 0U)
    {
        RF_REQUIRE(s_start_log.pending == 1U && s_start_log.generation == generation);
        RF_REQUIRE(LoggerBus_StartAcknowledgedGet() != generation);
        s_rf_stall_done = 1U;
        s_ticks += s_rf_delay_ms;
        Rf_Produce();
        if (s_rf_sync_fault != 0U) { s_start_failure = 1U; }
        printf("RF_START_SYNC_BEGIN generation=%lu pending=%u records=%lu streams=%lu delay_ms=%u ack=%lu\n",
            (unsigned long)generation, s_start_log.pending, (unsigned long)s_rf_start_records,
            (unsigned long)s_rf_start_streams, (unsigned)s_rf_delay_ms,
            (unsigned long)LoggerBus_StartAcknowledgedGet());
    }
    FRESULT result = __real_f_sync(file);
    if (generation != 0U)
    {
        s_rf_start_syncs++;
        s_rf_last_synced_generation = generation;
        s_rf_last_sync_ok = (uint8_t)(result == FR_OK);
        printf("RF_START_SYNC_END generation=%lu sync=%lu result=%u ack=%lu\n",
            (unsigned long)generation, (unsigned long)s_rf_start_syncs, result,
            (unsigned long)LoggerBus_StartAcknowledgedGet());
    }
    return result;
}

LoggerBusResult __real_LoggerBus_StartDurable(uint32_t);
LoggerBusResult __wrap_LoggerBus_StartDurable(uint32_t generation)
{
    RF_REQUIRE(s_rf_last_sync_ok == 1U && s_rf_last_synced_generation == generation);
    RF_REQUIRE(s_rf_start_records == 58U && s_rf_start_streams == 40U);
    RF_REQUIRE(s_start_log.pending == 1U && LoggerBus_StartAcknowledgedGet() != generation);
    LoggerBusResult result = __real_LoggerBus_StartDurable(generation);
    RF_REQUIRE(result == LOGGER_BUS_RESULT_OK);
    s_rf_ack_count++;
    printf("RF_START_DURABLE generation=%lu preceding_sync=%lu records=%lu streams=%lu ack=%lu\n",
        (unsigned long)generation, (unsigned long)s_rf_start_syncs,
        (unsigned long)s_rf_start_records, (unsigned long)s_rf_start_streams,
        (unsigned long)LoggerBus_StartAcknowledgedGet());
    return result;
}

static void Rf_SourceUpdate(uint32_t frame, uint64_t now)
{
    if (frame % 8U == 0U)
    {
        SystemGnssSample *sample = &s_gnss[0];
        sample->sequence = frame / 8U + 1U;
        sample->sample_timestamp_us = now; sample->receive_timestamp_us = now;
        sample->supported_fields = 0x3FFU; sample->valid_fields = 0x3FFU;
        sample->online = 1U; sample->fix_type = 3U; sample->fix_ok = 1U;
        sample->satellite_count = 12U; sample->measurement_timestamp_trusted = 1U;
        sample->horizontal_accuracy_m = 0.1f; sample->vertical_accuracy_m = 0.1f;
        sample->speed_accuracy_mps = 0.1f;
        RF_REQUIRE(SystemGnssQuality_Evaluate(sample, now) == SYSTEM_DEVICE_OK);
        RF_REQUIRE(sample->valid_group_mask == 15U && sample->position_usable == 1U);
        if (frame >= RF_START_FRAME) { s_rf_gnss_samples++; }
    }
    if (frame % 10U == 0U)
    {
        SystemBarometerSample *sample = &s_barometer[0];
        sample->sequence = frame / 10U + 1U;
        sample->sample_timestamp_us = now; sample->receive_timestamp_us = now;
        sample->pressure_pa = 101325.0f;
        sample->supported_fields = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
        sample->valid_fields = SYSTEM_BARO_VALID_PRESSURE | SYSTEM_BARO_VALID_ALTITUDE;
        sample->measurement_timestamp_trusted = 1U;
    }
}

static void Rf_MissionBegin(uint64_t now)
{
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    LoggerTaskDiagnostics diagnostics;
    RF_REQUIRE(LoggerTask_DiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK && diagnostics.snapshot_ready == 1U);
    RF_REQUIRE(SystemNavigationBackend_Initialize(q, &s_gnss[0], 0.0f, 1U, 1U, 1U) == SYSTEM_DEVICE_OK);
    s_lifecycle = SYSTEM_STATE_FLIGHT;
    s_rf_started = 1U; s_rf_first_flight_us = now;
    FlightTask_WriteStartRecords();
    FlightTask_StartRecordsProcess();
    RF_REQUIRE(s_start_log.pending == 1U && s_start_log.captured == 1U && s_start_log.generation != 0U);
    RF_REQUIRE(s_start_log.records.initial.origin_valid_flags == 3U);
}

static void Rf_Predict(uint32_t frame, uint64_t now)
{
    SystemInertialIncrement increment = {0};
    FlightLogInertialIncrementRecord record = {0};
    increment.sequence = frame / 2U; increment.timestamp_us = now; increment.dt_s = 0.01f;
    increment.delta_velocity_b_sculling_corrected[2] = SYSTEM_INS_GRAVITY_MPS2 * increment.dt_s;
    record.sequence = increment.sequence; record.dt_s = increment.dt_s;
    record.interval_start_timestamp_us = now - 10000ULL; record.interval_end_timestamp_us = now;
    memcpy(record.delta_velocity_b_sculling_corrected, increment.delta_velocity_b_sculling_corrected,
        sizeof(record.delta_velocity_b_sculling_corrected));
    (void)LoggerBus_InertialIncrementPush(now, 3U, &record);
    RF_REQUIRE(SystemNavigationBackend_Predict(&increment, &s_rf_output) == SYSTEM_DEVICE_OK);
    s_rf_predicts++;
}

static void Rf_Frame(uint32_t frame, uint64_t now)
{
    InsImuSample consumed;
    Rf_SourceUpdate(frame, now);
    if (frame == RF_START_FRAME) { Rf_MissionBegin(now); }
    if (s_rf_started != 0U)
    {
        FlightTask_StartRecordsProcess();
        s_rf_last_flight_us = now; s_rf_imu_samples++;
        DeviceNativeLog_Process();
        if (frame % 10U == 0U)
        {
            EstimatorPressureSnapshot pressure = {0};
            pressure.sequence = s_barometer[0].sequence;
            pressure.timestamp_us = now; pressure.receive_timestamp_us = now;
            pressure.pressure_pa = 101325.0f; pressure.valid = 1U; pressure.healthy = 1U;
            pressure.measurement_timestamp_trusted = 1U;
            pressure.supported_fields = s_barometer[0].supported_fields;
            pressure.valid_fields = s_barometer[0].valid_fields;
            RF_REQUIRE(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
            s_rf_baro_samples++;
        }
    }
    s_source_sample.sequence = frame + 1U;
    s_source_sample.sample_timestamp_us = now; s_source_sample.receive_timestamp_us = now;
    s_source_sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    s_source_sample.accel_b_mps2[2] = SYSTEM_INS_GRAVITY_MPS2;
    s_source_sample_pending = 1U;
    ImuSampleBus_Process();
    RF_REQUIRE(ImuSampleBus_Pop(&consumed) == IMU_SAMPLE_BUS_RESULT_OK && consumed.sequence == frame + 1U);
    if (s_rf_started == 0U) { return; }
    if (frame % 2U != 0U) { Rf_Predict(frame, now); }
    if (frame % 200U == 0U)
    {
        FlightLogStatsRecord stats = {0}; FlightLogHealthRecord health = {0};
        stats.logger_queue_overflow_count = LoggerBus_OverflowCountGet();
        stats.health_flags = s_rf_output.health_flags;
        (void)LoggerBus_StatsPush(now, &stats); (void)LoggerBus_HealthPush(now, &health);
    }
}

static void Rf_Produce(void)
{
    if (s_running == 0U || s_in_producer != 0U) { return; }
    s_in_producer = 1U;
    /* Fixed6000 frame limit bounds every catch-up, including the80ms pulse. */
    while (s_produced < RF_FRAME_COUNT && PlatformTime_Us() >= s_next_production_us)
    { Rf_Frame(s_produced++, s_next_production_us); s_next_production_us += 5000ULL; }
    if (s_produced == RF_FRAME_COUNT && LoggerBus_Count() == 0U && s_final_armed == 0U)
    {
        FlightLogStatsRecord stats = {0};
        stats.logger_queue_overflow_count = LoggerBus_OverflowCountGet();
        (void)LoggerBus_StatsPush(PlatformTime_Us(), &stats);
        RF_REQUIRE(LoggerBus_FinalizationArm(1ULL) == LOGGER_BUS_RESULT_OK);
        s_final_armed = 1U;
    }
    s_in_producer = 0U;
}

void __wrap_vTaskDelay(TickType_t ticks)
{
    Fixture_BaseDelay(ticks); Rf_Produce();
    LoggerTaskDiagnostics diagnostics;
    RF_REQUIRE(LoggerTask_DiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK);
    if (s_rf_sync_fault != 0U && diagnostics.io_fault != 0U)
    {
        RF_REQUIRE(LoggerBus_StartAcknowledgedGet() == 0U && s_rf_ack_count == 0U);
        FlightTask_StartRecordsProcess();
        RF_REQUIRE(s_start_log.pending == 1U && s_start_log.captured == 1U);
        s_rf_fault_observed = 1U; longjmp(s_exit, 2);
    }
    if (LoggerBus_FinalizationStateGet() == LOGGER_BUS_FINALIZATION_FINALIZED) { longjmp(s_exit, 1); }
    RF_REQUIRE(PlatformTime_Us() < 40000000ULL);
}

BaseType_t __wrap_xQueueReceive(QueueHandle_t queue, void *data, TickType_t ticks)
{
    BaseType_t result = Fixture_BaseReceive(queue, data, ticks);
    Rf_Produce();
    return result;
}

static void Rf_Export(const char *output)
{
    FILE *file; UINT read; uint8_t buffer[513];
    RF_REQUIRE(f_mount(NULL, "0:", 0U) == FR_OK && f_mount(&s_fs, "0:", 1U) == FR_OK);
    RF_REQUIRE(f_open(&s_file, "0:/missions/000001/flight.sslog", FA_READ) == FR_OK);
    file = fopen(output, "wb"); RF_REQUIRE(file != NULL);
    do
    {
        RF_REQUIRE(f_read(&s_file, buffer + 1U, 512U, &read) == FR_OK);
        RF_REQUIRE(fwrite(buffer + 1U, 1U, read, file) == read);
    } while (read != 0U);
    RF_REQUIRE(fclose(file) == 0 && f_close(&s_file) == FR_OK);
}

/* Host CRT enters this independent probe through --wrap=main. The included
 * original stress main and its expectations are neither changed nor executed. */
int __wrap_main(int argc, char **argv)
{
    if (argc != 3) { return 2; }
    s_rf_sync_fault = (uint8_t)(strcmp(argv[2], "start-sync-error") == 0);
    RF_REQUIRE(s_rf_sync_fault != 0U || strcmp(argv[2], "actual-rates") == 0 ||
        strcmp(argv[2], "actual-rates-baseline") == 0);
    if (strcmp(argv[2], "actual-rates-baseline") == 0) { s_rf_delay_ms = 0U; }
    s_startup_burst_test = 1U; /* Wall-clock tick reads, without original jitter. */
    RF_REQUIRE(SYSTEM_LOG_RECORD_QUEUE_DEPTH == 56U && SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH == 16U);
    RF_REQUIRE(FATFS_LinkDriver(&SD_Driver, SDPath) == 0U);
    RF_REQUIRE(f_mount(&s_fs, SDPath, 0U) == FR_OK && f_mkfs(SDPath, 1U, 1024U) == FR_OK);
    RF_REQUIRE(f_mount(&s_fs, SDPath, 1U) == FR_OK);
    RF_REQUIRE(LoggerBus_Init() == LOGGER_BUS_RESULT_OK && ImuSampleBus_Init() == IMU_SAMPLE_BUS_RESULT_OK);
    RF_REQUIRE(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    s_startup.completed = 1U; s_startup.passed = 1U; s_startup.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    for (unsigned index = 0U; index < s_startup.device_count; index++)
    { s_startup.devices[index].device_name = "Host source"; s_startup.devices[index].model_name = "Logical fixture"; }
    RF_REQUIRE(LoggerBus_EventPush(0U, FLIGHT_LOG_EVENT_BOOT, 0U, 0U) == LOGGER_BUS_RESULT_OK);
    s_next_production_us = PlatformTime_Us() + 10000ULL; s_running = 1U;
    if (setjmp(s_exit) == 0) { AppTask_Logger(NULL); }
    s_running = 0U;
    if (s_rf_sync_fault != 0U)
    {
        RF_REQUIRE(s_rf_fault_observed == 1U && s_rf_stall_done == 1U && s_rf_last_sync_ok == 0U);
        printf("RF_EXPECTED_SYNC_FAULT ack=0 pending=1 captured=1 fault=1\n"); return 0;
    }
    FlightTask_StartRecordsProcess();
    LoggerBusDiagnostics bus; LoggerTaskDiagnostics task; SystemStorageHealth storage;
    RF_REQUIRE(LoggerBus_DiagnosticsGet(&bus) == LOGGER_BUS_RESULT_OK);
    RF_REQUIRE(LoggerTask_DiagnosticsGet(&task) == SYSTEM_DEVICE_OK && task.io_fault == 0U);
    RF_REQUIRE(SystemStorage_HealthGet(&storage) == SYSTEM_DEVICE_OK && storage.error_count == 0U);
    RF_REQUIRE(s_start_log.pending == 0U && s_rf_ack_count == 1U && s_rf_stall_done == 1U);
    RF_REQUIRE(bus.normal_count == 0U && bus.estimator_count == 0U && bus.accepted_count == bus.dequeued_count);
    RF_REQUIRE(LoggerBus_FinalizationStateGet() == LOGGER_BUS_FINALIZATION_FINALIZED);
    uint32_t drops = 0U;
    for (unsigned type = 0U; type < 64U; type++)
    { drops += s_rf_drops[type]; printf("RF_RECORD type=%u serialized=%lu full=%lu\n", type,
        (unsigned long)s_rf_records[type], (unsigned long)s_rf_drops[type]); }
    RF_REQUIRE(drops == bus.overflow_count);
    printf("RF_ACTUAL_RATE frames=%lu imu=%lu increments=%lu baro=%lu gnss=%lu flight_first_us=%llu flight_last_us=%llu\n",
        (unsigned long)s_produced, (unsigned long)s_rf_imu_samples, (unsigned long)s_rf_predicts,
        (unsigned long)s_rf_baro_samples, (unsigned long)s_rf_gnss_samples,
        (unsigned long long)s_rf_first_flight_us, (unsigned long long)s_rf_last_flight_us);
    printf("RF_FINAL normal_hwm=%u estimator_hwm=%u overflow=%lu accepted=%lu dequeued=%lu snapshot_records=%lu streams=%lu ack=%lu finalized=1 health_flags=%lu\n",
        bus.normal_high_water, bus.estimator_high_water, (unsigned long)bus.overflow_count,
        (unsigned long)bus.accepted_count, (unsigned long)bus.dequeued_count,
        (unsigned long)s_rf_start_records, (unsigned long)s_rf_start_streams,
        (unsigned long)s_rf_ack_count, (unsigned long)s_rf_output.health_flags);
    Rf_Export(argv[1]);
    if (drops != 0U) { fprintf(stderr, "RF_FAIL ordinary queue overflow=%lu; exported for exact audit\n", (unsigned long)drops); return 1; }
    return 0;
}
