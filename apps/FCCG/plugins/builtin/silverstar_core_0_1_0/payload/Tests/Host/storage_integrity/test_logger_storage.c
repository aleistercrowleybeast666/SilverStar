/* Real LoggerBus -> LoggerTask -> LogSink -> Storage -> FatFs -> diskio.
 * Only time, RTOS scheduling and the SD card are Host models. */
#define main Fixture_DiskMain
#define vTaskDelay Fixture_BaseDelay
#define xQueueReceive Fixture_BaseReceive
#define xTaskGetTickCount Fixture_BaseTickCount
#include "test_storage_integrity.c"
#undef main
#undef vTaskDelay
#undef xQueueReceive
#undef xTaskGetTickCount
#include <setjmp.h>
#include "app_tasks.h"
#include "logger_bus.h"
#include "logger_task.h"
#include "platform_critical.h"
#include "system_log_policy.h"
#include "system_storage_if.h"
#include "persistent_storage.h"
#include "system_calibration.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_mission_snapshot_if.h"
#include "system_mag_calibration.h"
#include "system_mag_calibration_storage_if.h"
#include "system_source_selector.h"
#include "system_startup.h"
#include "system_user_config.h"

FATFS SDFatFS;
char SDPath[4];
static jmp_buf s_exit;
static uint8_t s_running;
static uint8_t s_in_producer;
static uint8_t s_overflow_test;
static uint8_t s_startup_overflow_test;
static uint8_t s_startup_burst_test;
static uint8_t s_open_stall_done;
static uint8_t s_sparse_test;
static uint32_t s_preflight_frames;
static uint32_t s_frame_limit = TEST_RECORD_COUNT;
static uint64_t s_landing_us;
static uint32_t s_producer_failures;
static uint32_t s_device_steps;
static uint32_t s_flight_steps;
static uint32_t s_first_delay_ticks;
static uint32_t s_recovery_drops;
static uint32_t s_last_drop_frame;
static uint32_t s_observed_drops;
static uint16_t s_peak_frame_normal;
static uint16_t s_peak_frame_estimator;
static uint8_t s_burst_done;
static uint8_t s_final_armed;
static uint32_t s_produced;
static uint64_t s_next_production_us;
static uint64_t s_clock_us;
static uint64_t s_start_us;
static uint64_t s_production_begin_us;
static uint64_t s_production_end_us;
static uint32_t s_start_accepted;
static uint32_t s_last_jitter_transaction;
static uint32_t s_jitter_count;
static SystemStartupReport s_startup;


PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint64_t PlatformTime_Us(void) { return s_clock_us + (uint64_t)s_ticks * 1000ULL; }
uint64_t SystemTime_GetMonotonicUs(void) { s_clock_us += 20ULL; return PlatformTime_Us(); }
const SystemStartupReport *SystemStartup_GetReport(void) { return &s_startup; }

uint8_t SystemCalibration_IsReady(void) { return 1U; }
uint32_t SystemCalibration_GenerationGet(void) { return 1U; }
SystemDeviceResult SystemFlightRecovery_StatusGet(
    SystemFlightRecoveryStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    status->landing_detected = s_final_armed;
    status->deploy_triggered = s_final_armed;
    status->deploy_completed = s_final_armed;
    return SYSTEM_DEVICE_OK;
}
void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot)
{
    if (snapshot == NULL) { return; }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->ready = 1U;
}
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{
    if (instance == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *instance = 0U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{
    if (instance == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *instance = 0U;
    return SYSTEM_DEVICE_OK;
}

TickType_t xTaskGetTickCount(void)
{
    /* The multi-stream model uses a wall clock: reading SysTick does not cost
     * a millisecond. The legacy slow-card model retains its original clock. */
    return (s_startup_burst_test || s_sparse_test) ? (TickType_t)(PlatformTime_Us() / 1000ULL) : Fixture_BaseTickCount();
}

static void Fixture_ResultCheckAt(LoggerBusResult result, const char *file, unsigned line)
{
    if (result != LOGGER_BUS_RESULT_OK)
    {
        s_producer_failures++;
        if (s_producer_failures < 24U)
        {
            LoggerBusDiagnostics diagnostics;
            (void)LoggerBus_DiagnosticsGet(&diagnostics);
            fprintf(stderr, "PUSH_FAILURE file=%s line=%u result=%u frame=%lu normal=%u estimator=%u time=%llu\n",
                file, line, result, (unsigned long)s_produced, diagnostics.normal_count,
                diagnostics.estimator_count, (unsigned long long)PlatformTime_Us());
        }
        if (s_sparse_test && s_producer_failures < 8U)
        { fprintf(stderr, "SPARSE_PUSH result=%u frame=%lu time=%llu\n", result,
            (unsigned long)s_produced, (unsigned long long)PlatformTime_Us()); }
    }
}

#define Fixture_ResultCheck(result) Fixture_ResultCheckAt((result), __FILE__, __LINE__)

#include "test_sparse_preflight.h"
#if SYSTEM_BUILD_ESKF15_ENABLED
#include "test_eskf_storage.h"
#endif

static void Fixture_DefaultFrame(uint32_t frame, uint64_t now)
{
    FlightLogRecord r = {0};
    s_device_steps++;
    s_flight_steps++;
    if (frame % 4U == 0U) { Fixture_ResultCheck(LoggerBus_PowerPush(now, &r.payload.power)); }
    if (frame == 1U) { Fixture_ResultCheck(LoggerBus_CalibrationResultPush(now, &r.payload.calibration_result)); }
    if (frame == 1000U) { Fixture_ResultCheck(LoggerBus_AlignmentResultPush(now, &r.payload.alignment_result)); }
    if (frame == 1200U)
    {
        Fixture_ResultCheck(LoggerBus_MissionConfigPush(now));
        Fixture_ResultCheck(LoggerBus_SystemConfigPush(now));
        Fixture_ResultCheck(LoggerBus_InitialStatePush(now, &r.payload.initial_state));
        Fixture_ResultCheck(LoggerBus_EventPush(now, FLIGHT_LOG_EVENT_MISSION_START, 0U, 0U));
    }
    if (frame < 1200U) { return; }
    Fixture_ResultCheck(LoggerBus_BaroNativePush(now, frame, &r.payload.baro_native));
    if (frame % 8U == 0U) { Fixture_ResultCheck(LoggerBus_GnssNativePush(now, frame, &r.payload.gnss_native)); }
    Fixture_ResultCheck(LoggerBus_ImuCorrectedPush(now, frame, &r.payload.imu_corrected));
#if SYSTEM_BUILD_ESKF15_ENABLED
    Fixture_EskfFrame(frame, now);
#else
    if (frame % 2U == 0U)
    {
        Fixture_ResultCheck(LoggerBus_InertialIncrementPush(now, frame, &r.payload.inertial_increment));
        Fixture_ResultCheck(LoggerBus_EstimatorStepPush(now, &r.payload.estimator_step));
        Fixture_ResultCheck(LoggerBus_EstimatorPush(now, frame, &r.payload.estimator));
        Fixture_ResultCheck(LoggerBus_Kf6DiagnosticPush(now, frame, &r.payload.kf6_diagnostic));
        Fixture_ResultCheck(LoggerBus_Kf6FullPPush(now, &r.payload.kf6_full_p));
        Fixture_ResultCheck(LoggerBus_BaroMeasurementPush(now, frame, &r.payload.baro_measurement));
    }
    if (frame % 8U == 0U)
    {
        Fixture_ResultCheck(LoggerBus_GnssMeasurementPush(now, frame, &r.payload.gnss_measurement));
        Fixture_ResultCheck(LoggerBus_GnssRecoveryPush(now, &r.payload.gnss_recovery));
    }
#endif
    if (frame % 40U == 0U) { Fixture_ResultCheck(LoggerBus_TelemetryDiagnosticPush(now, &r.payload.telemetry_diagnostic)); }
    if (frame % 200U == 0U)
    {
        r.payload.stats.logger_queue_overflow_count = LoggerBus_OverflowCountGet();
        Fixture_ResultCheck(LoggerBus_StatsPush(now, &r.payload.stats));
        Fixture_ResultCheck(LoggerBus_HealthPush(now, &r.payload.health));
    }
}

static LoggerBusResult Fixture_RecordPush(uint32_t index, uint64_t now)
{
    FlightLogRecord record;
    memset(&record, 0, sizeof(record));
    /* Every required record appears before START; native sensor mix follows.
     * Caller RAM is overwritten on return to verify queue copy ownership. */
    if (index == 5U) { return LoggerBus_AlignmentResultPush(now, &record.payload.alignment_result); }
    if (index == 6U) { return LoggerBus_CalibrationResultPush(now, &record.payload.calibration_result); }
    if (index == 7U || index == 1000U) { return LoggerBus_MissionConfigPush(now); }
    if (index == 8U) { return LoggerBus_InitialStatePush(now, &record.payload.initial_state); }
    if (index == 1001U)
    { return LoggerBus_EventPush(now, FLIGHT_LOG_EVENT_MISSION_START, 0U, 0U); }
    if ((index % 1000U) == 9U)
    {
        record.payload.stats.logger_queue_overflow_count = LoggerBus_OverflowCountGet();
        return LoggerBus_StatsPush(now, &record.payload.stats);
    }
    if (index > 11U && index % 31U == 0U)
    { return LoggerBus_EstimatorPush(now, index, &record.payload.estimator); }
    switch (index % 5U)
    {
        case 0U: return LoggerBus_ImuCorrectedPush(now, index, &record.payload.imu_corrected);
        case 1U: return LoggerBus_ImuCorrectedPush(now, index, &record.payload.imu_corrected);
        case 2U: return LoggerBus_GnssNativePush(now, index, &record.payload.gnss_native);
        case 3U: return LoggerBus_BaroNativePush(now, index, &record.payload.baro_native);
        default: return LoggerBus_MagNativePush(now, index, &record.payload.mag_native);
    }
}

static void Fixture_Produce(void)
{
    uint64_t now;
    if (!s_running || s_in_producer) { return; }
    s_in_producer = 1U;
    now = PlatformTime_Us();
    while (s_produced < s_frame_limit && now >= s_next_production_us)
    {
        LoggerBusResult result;
        LoggerBusDiagnostics before_frame;
        LoggerBusDiagnostics after_frame;
        (void)LoggerBus_DiagnosticsGet(&before_frame);
        if (s_produced == 1500U) { s_recovery_drops = LoggerBus_OverflowCountGet(); }
        if (s_produced == 0U) { s_production_begin_us = now; }
        if (s_produced == (s_sparse_test ? s_preflight_frames : (s_startup_burst_test ? 1200U : 1000U)))
        {
            LoggerBusDiagnostics diagnostics;
            s_start_us = now;
            (void)LoggerBus_DiagnosticsGet(&diagnostics);
            s_start_accepted = diagnostics.accepted_count;
        }
        if (s_sparse_test)
        {
            Fixture_SparseFrame(s_produced++, s_next_production_us);
            result = LOGGER_BUS_RESULT_OK;
        }
        else if (s_startup_burst_test)
        {
            Fixture_DefaultFrame(s_produced++, s_next_production_us);
            result = LOGGER_BUS_RESULT_OK;
        }
        else { result = Fixture_RecordPush(s_produced++, s_next_production_us); }
        if (result != LOGGER_BUS_RESULT_OK && result != LOGGER_BUS_RESULT_FULL) { abort(); }
        s_next_production_us += s_sparse_test ? 10000ULL : (s_startup_burst_test ? 5000ULL : (s_produced < 1000U ? 10000ULL : 2000ULL));
        s_production_end_us = now;
        (void)LoggerBus_DiagnosticsGet(&after_frame);
        if (s_startup_burst_test && s_produced > 1201U)
        {
            uint16_t normal_added = (uint16_t)(after_frame.normal_count - before_frame.normal_count);
            uint16_t estimator_added = (uint16_t)(after_frame.estimator_count - before_frame.estimator_count);
            if (normal_added > s_peak_frame_normal) { s_peak_frame_normal = normal_added; }
            if (estimator_added > s_peak_frame_estimator) { s_peak_frame_estimator = estimator_added; }
        }
        if (LoggerBus_OverflowCountGet() != s_observed_drops)
        {
            s_observed_drops = LoggerBus_OverflowCountGet();
            s_last_drop_frame = s_produced;
        }
    }
    if (s_startup_burst_test && s_produced >= 100U) { s_startup.completed = 1U; }
    if (s_overflow_test && !s_burst_done && s_produced > (s_startup_burst_test ? 1201U : 1001U))
    {
        /* Deliberate finite overload, separate from normal rate/SD latency. */
        for (unsigned index = 0U; index < 500U; index++)
        { (void)LoggerBus_EventPush(now, FLIGHT_LOG_EVENT_SAMPLE_GAP, index, 0U); }
        for (unsigned index = 0U; index < 100U; index++)
        {
            FlightLogEstimatorRecord estimator = {0};
            (void)LoggerBus_EstimatorPush(now, index, &estimator);
        }
        s_burst_done = 1U;
    }
    if (s_produced == s_frame_limit && LoggerBus_Count() == 0U && !s_final_armed)
    {
        FlightLogStatsRecord stats = {0};
        stats.logger_queue_overflow_count = LoggerBus_OverflowCountGet();
        if (LoggerBus_StatsPush(now, &stats) != LOGGER_BUS_RESULT_OK) { abort(); }
        /* Time already exceeds the normal landing grace deadline. */
        if (LoggerBus_FinalizationArm(1ULL) != LOGGER_BUS_RESULT_OK) { abort(); }
        s_final_armed = 1U;
    }
    s_in_producer = 0U;
}

void vTaskDelay(TickType_t ticks)
{
    if (s_running && s_first_delay_ticks == 0U) { s_first_delay_ticks = ticks; }
    Fixture_BaseDelay(ticks);
    Fixture_Produce();
    if (s_running && LoggerBus_FinalizationStateGet() == LOGGER_BUS_FINALIZATION_FINALIZED)
    { longjmp(s_exit, 1); }
    if (s_running && PlatformTime_Us() > 300000000ULL)
    {
        fprintf(stderr, "Logger exceeded the simulated completion deadline\n");
        s_failures++;
        longjmp(s_exit, 2);
    }
}

BaseType_t xQueueReceive(QueueHandle_t queue, void *data, TickType_t ticks)
{
    if (s_running && s_startup_burst_test && !s_open_stall_done && ticks != 0U)
    {
        /* A 300 ms session-open stall while 200 Hz multi-sensor producers run. */
        s_ticks += 300U;
        s_open_stall_done = 1U;
        Fixture_Produce();
    }
    if (s_running && s_startup_burst_test && s_dma_pending && s_dma_write &&
        ticks != 0U && s_produced > 1200U && s_dma_transactions % 128U == 0U &&
        s_dma_transactions != s_last_jitter_transaction)
    {
        /* Genuine in-flight DMA: producers continue during a bounded 20--100 ms stall. */
        s_last_jitter_transaction = s_dma_transactions;
        s_ticks += 20U * (1U + s_jitter_count % 5U);
        s_jitter_count++;
        Fixture_Produce();
    }
    BaseType_t result = Fixture_BaseReceive(queue, data, ticks);
    Fixture_Produce();
    return result;
}

static int Test_Writer(const char *output)
{
    LoggerBusDiagnostics bus;
    LoggerTaskDiagnostics task;
    SystemStorageHealth storage;
    SystemLogStreamConfig power_config;
    SystemLogStreamConfig imu_config;
    FILE *exported;
    FILINFO info = {0};
    uint8_t buffer[513];
    UINT read;
    CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    for (uint16_t index = 0U; !s_startup_burst_test && index < SystemLogPolicy_StreamCountGet(); index++)
    {
        SystemLogStreamConfig config;
        CHECK(SystemLogPolicy_StreamByIndexGet(index, &config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U;
        config.decimation = 1U;
        CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    }
    if (s_startup_burst_test && s_overflow_test)
    {
        SystemLogStreamConfig stats_config;
        /* Overload audit needs a durable counter for dropped queue records. */
        CHECK(SystemLogPolicy_StreamGet(
            FLIGHT_LOG_RECORD_STATS, &stats_config) == SYSTEM_DEVICE_OK);
        stats_config.enabled = 1U;
        stats_config.decimation = 1U;
        CHECK(SystemLogPolicy_StreamConfigure(&stats_config) == SYSTEM_DEVICE_OK);
    }
    s_startup.completed = (uint8_t)!s_startup_burst_test;
    s_startup.passed = 1U;
    s_startup.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    for (unsigned index = 0U; index < s_startup.device_count; index++)
    {
        s_startup.devices[index].device_name = "Fixture device";
        s_startup.devices[index].model_name = "SS0.5";
    }
    CHECK(LoggerBus_EventPush(PlatformTime_Us(), FLIGHT_LOG_EVENT_BOOT, 0U, 0U) == LOGGER_BUS_RESULT_OK);
    if (s_startup_overflow_test)
    {
        for (unsigned index = 0U; index < 200U; index++)
        { (void)LoggerBus_EventPush(PlatformTime_Us(), FLIGHT_LOG_EVENT_BOOT, index, 0U); }
    }
    s_next_production_us = PlatformTime_Us() + 10000ULL;
    s_running = 1U;
    if (setjmp(s_exit) == 0) { AppTask_Logger(NULL); }
    s_running = 0U;
    CHECK(s_failures == 0U);
    if (s_sparse_test)
    {
        CHECK(s_produced == s_frame_limit && s_calibration_steps == s_frame_limit);
        CHECK(s_producer_failures == 0U);
        CHECK(PlatformTime_Us() >= s_landing_us + (uint64_t)SYSTEM_LOG_POST_LANDING_GRACE_MS * 1000ULL);
        CHECK(LoggerBus_FinalizationStateGet() == LOGGER_BUS_FINALIZATION_FINALIZED);
        printf("SPARSE_PREFLIGHT pre_s=%lu samples=%lu start_us=%llu landing_us=%llu final_us=%llu native=%u corrected=%u\n",
            (unsigned long)(s_preflight_frames / 100U), (unsigned long)s_calibration_steps,
            (unsigned long long)s_start_us, (unsigned long long)s_landing_us,
            (unsigned long long)PlatformTime_Us(), SYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE,
            SYSTEM_LOG_PREFLIGHT_CORRECTED_IMU_ENABLE);
    }
    CHECK(LoggerBus_DiagnosticsGet(&bus) == LOGGER_BUS_RESULT_OK);
    printf("LOGGER_QUEUE_OBSERVED normal=%u/%u estimator=%u/%u drops=%lu producer_failures=%lu jitter_count=%lu\n",
        bus.normal_high_water, SYSTEM_LOG_RECORD_QUEUE_DEPTH,
        bus.estimator_high_water, SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH,
        (unsigned long)bus.overflow_count, (unsigned long)s_producer_failures,
        (unsigned long)s_jitter_count);
    printf("LOGGER_SAME_EPOCH_PEAK normal=%u estimator=%u period_us=5000\n",
        s_peak_frame_normal, s_peak_frame_estimator);
    CHECK(LoggerTask_DiagnosticsGet(&task) == SYSTEM_DEVICE_OK && task.io_fault == 0U);
    CHECK(SystemStorage_HealthGet(&storage) == SYSTEM_DEVICE_OK && storage.error_count == 0U);
    CHECK(bus.normal_count == 0U && bus.estimator_count == 0U);
    CHECK(bus.accepted_count == bus.dequeued_count);
    CHECK(bus.startup_state == LOGGER_STREAMING_READY && task.streaming_ready_us != 0ULL);
    CHECK(SystemLogPolicy_StreamGet(
        FLIGHT_LOG_RECORD_POWER, &power_config) == SYSTEM_DEVICE_OK);
    CHECK(s_sparse_test || (power_config.enabled == 0U) ||
          (bus.bootstrap_suppressed_count > 0U));
    CHECK(task.session_count == 1U && task.open_attempt_count == 1U);
    CHECK(task.append_failure_count == 0U && task.flush_failure_count == 0U);
    CHECK(task.serialize_failure_count == 0U && task.discarded_bytes == 0U);
    CHECK(task.drain_count == bus.dequeued_count && task.iteration_count >= task.drain_count);
    if (s_startup_burst_test)
    {
        CHECK(SystemLogPolicy_StreamGet(
            FLIGHT_LOG_RECORD_IMU_CORRECTED, &imu_config) == SYSTEM_DEVICE_OK);
        CHECK((imu_config.enabled == 0U) || (s_jitter_count >= 5U));
        CHECK(s_overflow_test || s_producer_failures == 0U);
        CHECK(s_device_steps == TEST_RECORD_COUNT && s_flight_steps == TEST_RECORD_COUNT);
        CHECK(s_first_delay_ticks != 10U);
    }
    CHECK(s_overflow_test ? bus.overflow_count > 0U : bus.overflow_count == 0U);
    printf("LOGGER_OVERLOAD_RECOVERY sampled_frame=1500 sampled_drops=%lu final_drops=%lu last_drop_frame=%lu\n",
        (unsigned long)s_recovery_drops, (unsigned long)bus.overflow_count,
        (unsigned long)s_last_drop_frame);
    CHECK(bus.overflow_count == s_recovery_drops);
    CHECK(f_mount(NULL, "0:", 0U) == FR_OK);
    CHECK(f_mount(&s_fs, "0:", 1U) == FR_OK);
    CHECK(f_stat("0:/missions/000001/manifest", &info) == FR_OK);
    CHECK(f_open(&s_file, "0:/missions/000001/flight.sslog", FA_READ) == FR_OK);
    CHECK(f_size(&s_file) == storage.bytes_written);
    exported = fopen(output, "wb");
    CHECK(exported != NULL);
    do
    {
        CHECK(f_read(&s_file, buffer + 1U, 512U, &read) == FR_OK);
        CHECK(fwrite(buffer + 1U, 1U, read, exported) == read);
    } while (read != 0U);
    CHECK(fclose(exported) == 0 && f_close(&s_file) == FR_OK);
    printf("LOGGER_STORAGE accepted=%lu drops=%lu hwm=%u/%u max_write_us=%llu max_sync_us=%llu max_iteration_us=%llu\n",
        (unsigned long)bus.accepted_count, (unsigned long)bus.overflow_count,
        bus.normal_high_water, bus.estimator_high_water,
        (unsigned long long)storage.max_write_latency_us,
        (unsigned long long)storage.max_sync_latency_us,
        (unsigned long long)task.max_iteration_us);
    printf("LOGGER_RATE pre_steps=%u pre_us=%llu post_steps=%u post_us=%llu pre_accepted=%lu\n",
        s_startup_burst_test ? 1200U : 1000U,
        (unsigned long long)(s_start_us - s_production_begin_us),
        s_startup_burst_test ? 38800U : 39000U,
        (unsigned long long)(s_production_end_us - s_start_us), (unsigned long)s_start_accepted);
    printf("LOGGER_BOOTSTRAP suppressed=%lu ready_us=%llu first_delay_ticks=%lu slot_bytes=%u depth=%u/%u\n",
        (unsigned long)bus.bootstrap_suppressed_count, (unsigned long long)task.streaming_ready_us,
        (unsigned long)s_first_delay_ticks, (unsigned)sizeof(FlightLogRecord),
        SYSTEM_LOG_RECORD_QUEUE_DEPTH, SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH);
    printf("LOGGER_JITTER count=%lu range_ms=20-100\n", (unsigned long)s_jitter_count);
#if SYSTEM_BUILD_ESKF15_ENABLED
    if (s_startup_burst_test)
    {
        CHECK(s_eskf_body_attempts == (TEST_RECORD_COUNT - 1200U) / 2U);
        CHECK(s_eskf_measurement_attempts == s_eskf_body_attempts * 2U);
        CHECK(s_eskf_covariance_attempts == s_eskf_body_attempts + 1U);
        printf("ESKF_STORAGE_LOAD body_hz=100 gnss_hz=25 groups=4 baro_hz=100 body=%lu meas=%lu covariance_attempts=%lu\n",
            (unsigned long)s_eskf_body_attempts, (unsigned long)s_eskf_measurement_attempts,
            (unsigned long)s_eskf_covariance_attempts);
    }
#endif
    printf("LOGGER_CAUSALITY capacity_reject=%lu state_reject=%lu append_fail=%lu flush_fail=%lu discard_bytes=%lu opens=%lu/%lu write_avg_us=%llu steps=%lu/%lu\n",
        (unsigned long)bus.capacity_reject_count, (unsigned long)bus.state_reject_count,
        (unsigned long)task.append_failure_count, (unsigned long)task.flush_failure_count,
        (unsigned long)task.discarded_bytes, (unsigned long)task.session_count,
        (unsigned long)task.open_attempt_count, (unsigned long long)(task.total_write_us / task.write_count),
        (unsigned long)s_device_steps, (unsigned long)s_flight_steps);
    return 1;
}

static int Test_MagCalibrationPersistent(void)
{
    static const char valid_hex[] =
        "01010B00000000004041000000C1000040400000803F000000000000000000000000"
        "0000803F0000000000000000000000000000803F00004842CDCC4C3ECDCC4C3F"
        "9A99993F4B4B4B4B4B4B4B4B58024754EB56";
    static const char wrong_device_hex[] =
        "01012A00000000004041000000C1000040400000803F000000000000000000000000"
        "0000803F0000000000000000000000000000803F00004842CDCC4C3ECDCC4C3F"
        "9A99993F4B4B4B4B4B4B4B4B580211E8A9C5";
    uint8_t readback[SYSTEM_MAG_CAL_PACKET_BYTES];
    uint16_t length = 0U;
    uint32_t generation = 0U;
    SystemMagCalibrationStatus status;
    s_mag_calibration_test_enabled = 1U;
    SystemMagCalibration_Init();
    SystemMagCalibrationStorage_Service();
    SystemMagCalibrationStorage_Service();
    CHECK(SystemMagCalibrationStorage_LoadCompleteGet() == 1U);
    CHECK(SystemMagCalibration_StatusGet(0U, &status) ==
        SystemMagCalibrationResult_Ok &&
        status.load_error == SystemMagCalibrationResult_InvalidObject);
    CHECK(SystemMagCalibration_PacketApply(0U, wrong_device_hex) ==
        SystemMagCalibrationResult_WrongDevice);
    CHECK(SystemMagCalibration_PacketApply(0U, valid_hex) ==
        SystemMagCalibrationResult_Ok);
    CHECK(SystemMagCalibration_SaveRequest(0U) ==
        SystemMagCalibrationResult_Ok);
    CHECK(SystemMagCalibration_ReadyForMissionGet() == 0U);
    SystemMagCalibrationStorage_Service();
    CHECK(SystemMagCalibration_StatusGet(0U, &status) ==
        SystemMagCalibrationResult_Ok);
    CHECK(status.active == 1U && status.saved == 1U &&
        status.physical_device_id == 11U && status.generation == 3U &&
        status.load_error == SystemMagCalibrationResult_Ok);
    CHECK(SystemMagCalibration_ReadyForMissionGet() == 1U);
    CHECK(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        readback, sizeof(readback), &length, &generation) ==
        PERSISTENT_STORAGE_OK);
    CHECK(length == sizeof(readback) && generation == status.generation);
    SystemMagCalibration_Init();
    CHECK(SystemMagCalibration_PacketApply(0U, wrong_device_hex) ==
        SystemMagCalibrationResult_WrongDevice);
    CHECK(SystemMagCalibration_StoredLoad(0U, readback, generation) ==
        SystemMagCalibrationResult_Ok);
    CHECK(SystemMagCalibration_StatusGet(0U, &status) ==
        SystemMagCalibrationResult_Ok && status.saved == 1U);
    return 1;
}

static int Test_PersistentObjects(void)
{
    static const uint8_t calibration_a[] = {1U, 2U, 3U};
    static const uint8_t calibration_b[] = {4U, 5U, 6U, 7U};
    static const uint8_t snapshot[] = {9U, 8U, 7U};
    static const uint8_t torn[] = {0U, 0U, 0U};
    uint8_t readback[8];
    uint8_t manifest[20];
    UINT manifest_read = 0U;
    uint16_t length = 0U;
    uint32_t generation = 0U;
    uint32_t mission_id = 0U;
    FILINFO info = {0};
    SystemMissionSnapshotStatus snapshot_status;
    uint8_t section;
    uint8_t snapshot_readback[PERSISTENT_STORAGE_OBJECT_MAX_BYTES];
    CHECK(SystemStorage_Init() == SYSTEM_DEVICE_OK);
    CHECK(SystemStorage_Mount() == SYSTEM_DEVICE_OK);
    CHECK(SystemStorage_MissionDirectoryReserve(1U) == SYSTEM_DEVICE_OK);
    CHECK(SystemStorage_MissionIdGet(&mission_id) == SYSTEM_DEVICE_NOT_READY);
    CHECK(SystemStorage_MissionManifestCreate(0x12345678UL, 0U, 1U, 0U) ==
        SYSTEM_DEVICE_OK);
    CHECK(SystemStorage_MissionIdGet(&mission_id) == SYSTEM_DEVICE_OK);
    CHECK(mission_id == 1U);
    CHECK(f_open(&s_file, "0:/missions/000001/manifest", FA_READ) == FR_OK);
    CHECK(f_read(&s_file, manifest, sizeof(manifest), &manifest_read) == FR_OK);
    CHECK(f_close(&s_file) == FR_OK);
    CHECK(manifest_read == sizeof(manifest));
    CHECK(memcmp(manifest, "SSMF", 4U) == 0);
    CHECK(manifest[4] == 1U && manifest[5] == 0U &&
        manifest[6] == 1U && manifest[7] == 0U);
    CHECK(manifest[8] == 1U && manifest[12] == 0x78U &&
        manifest[13] == 0x56U && manifest[14] == 0x34U &&
        manifest[15] == 0x12U);
    CHECK(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        calibration_a, sizeof(calibration_a), &generation) ==
        PERSISTENT_STORAGE_OK);
    CHECK(generation == 1U);
    CHECK(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        calibration_b, sizeof(calibration_b), &generation) ==
        PERSISTENT_STORAGE_OK);
    CHECK(generation == 2U);
    CHECK(f_stat("0:/system/calibration/mag00.1", &info) == FR_OK);
    CHECK(SystemStorage_ObjectSlotWrite(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U, 0U,
        torn, sizeof(torn)) == SYSTEM_DEVICE_OK);
    CHECK(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        readback, sizeof(readback), &length, &generation) ==
        PERSISTENT_STORAGE_OK);
    CHECK(generation == 2U && length == sizeof(calibration_b));
    CHECK(memcmp(readback, calibration_b, length) == 0);
    CHECK(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT, 0U,
        snapshot, sizeof(snapshot), &generation) == PERSISTENT_STORAGE_OK);
    CHECK(f_stat("0:/missions/000001/snap00.0", &info) == FR_OK);
    CHECK(SystemMissionSnapshot_Create(&snapshot_status) ==
        SystemMissionSnapshotResult_Ok);
    CHECK(snapshot_status.mission_id == mission_id);
    CHECK(snapshot_status.commit_generation == 2U);
    CHECK(snapshot_status.snapshot_sequence == 1U);
    CHECK(snapshot_status.snapshot_base_instance == 0U);
    CHECK(snapshot_status.calibration_generation == 1U);
    CHECK(snapshot_status.mag_calibration_generation == 2U);
    for (section = 0U; section <= 6U; section++)
    {
        CHECK(PersistentStorage_ObjectRead(
            PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT, section,
            snapshot_readback, sizeof(snapshot_readback), &length,
            &generation) == PERSISTENT_STORAGE_OK);
        CHECK(length >= 8U);
        CHECK(memcmp(snapshot_readback, "SSMS", 4U) == 0);
        CHECK(snapshot_readback[4] == 2U);
        CHECK(snapshot_readback[5] == section);
        if (section == 0U)
        {
            /* Header fields after the fixed AIR PHY profile. */
            CHECK(length > 83U);
            CHECK(snapshot_readback[82] ==
                SYSTEM_ALIGNMENT_CONSTRAINT_COUNT);
            CHECK(snapshot_readback[83] ==
                SYSTEM_ALIGNMENT_EXTERNAL_YAW_AUTHORITATIVE);
        }
    }
    CHECK(SystemMissionSnapshot_Create(&snapshot_status) ==
        SystemMissionSnapshotResult_Ok);
    CHECK(snapshot_status.snapshot_sequence == 2U);
    CHECK(snapshot_status.snapshot_base_instance == 8U);
    for (section = 0U; section <= 6U; section++)
    {
        CHECK(PersistentStorage_ObjectRead(
            PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT,
            (uint8_t)(8U + section), snapshot_readback,
            sizeof(snapshot_readback), &length, &generation) ==
            PERSISTENT_STORAGE_OK);
        CHECK(snapshot_readback[5] == section);
    }
    CHECK(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT, 0U,
        snapshot_readback, sizeof(snapshot_readback), &length,
        &generation) == PERSISTENT_STORAGE_OK);
    CHECK(generation == 2U && snapshot_readback[5] == 0U);
    s_final_armed = 1U;
    CHECK(SystemMissionSnapshot_FinalStatusWrite(123456ULL, 0U) ==
        SystemMissionSnapshotResult_Ok);
    CHECK(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT, 7U,
        snapshot_readback, sizeof(snapshot_readback), &length,
        &generation) == PERSISTENT_STORAGE_OK);
    CHECK(length >= 40U && snapshot_readback[5] == 7U);
    CHECK(snapshot_readback[22] == 1U);
    CHECK(snapshot_readback[23] == 1U);
    CHECK(snapshot_readback[24] == 1U);
    CHECK(snapshot_readback[25] == 0U);
    CHECK(Test_MagCalibrationPersistent());
    printf("PERSISTENT_OBJECTS generation=%lu fallback=1 lfn=1\n",
        (unsigned long)generation);
    return 1;
}

int main(int argc, char **argv)
{
    if (argc != 2 && argc != 3 && argc != 4) { return 2; }
    if (argc == 4 && strcmp(argv[2], "sparse") == 0)
    {
        s_sparse_test = 1U;
        s_preflight_frames = (uint32_t)strtoul(argv[3], NULL, 10) * 100U;
        s_frame_limit = s_preflight_frames + 2100U;
        if (ImuSampleBus_Init() != IMU_SAMPLE_BUS_RESULT_OK) { return 6; }
    }
    if (argc == 3)
    {
        s_startup_burst_test = (uint8_t)((strcmp(argv[2], "startup-burst") == 0) ||
            (strcmp(argv[2], "startup-burst-overload") == 0));
        s_overflow_test = (uint8_t)(strcmp(argv[2], "startup-burst") != 0);
        s_startup_overflow_test = (uint8_t)(strcmp(argv[2], "startup-overflow") == 0);
    }
    if (FATFS_LinkDriver(&SD_Driver, SDPath) != 0U) { return 3; }
    if (f_mkfs(SDPath, FM_FAT | FM_SFD, 512U, s_work, sizeof(s_work)) != FR_OK) { return 4; }
    if (f_mount(&s_fs, SDPath, 1U) != FR_OK) { return 5; }
    if (argc == 3 && strcmp(argv[2], "persistent-objects") == 0)
    { return Test_PersistentObjects() ? 0 : 1; }
    return Test_Writer(argv[1]) ? 0 : 1;
}
