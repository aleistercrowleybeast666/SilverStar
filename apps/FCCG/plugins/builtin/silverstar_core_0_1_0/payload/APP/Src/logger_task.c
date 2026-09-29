#include "app_tasks.h"

#include <stddef.h>
#include <string.h>

#include "FreeRTOS.h"
#include "task.h"
#include "logger_bus.h"
#include "logger_task.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "silverstar_assert.h"
#include "system_calibration.h"
#include "system_log_sink_if.h"
#include "system_mission_snapshot_if.h"
#include "system_profile.h"
#include "system_startup.h"
#include "system_time.h"
#include "system_user_config.h"
#include "system_version.h"

#define LOGGER_MAX_TEXT_LENGTH 128U
#define LOGGER_CRITICAL_FLUSH_MAX_US 20000ULL
#define LOGGER_STREAMING_WRITE_QUANTUM_BYTES 512U

typedef struct
{
    uint32_t record_sequence;
    uint32_t aggregate_length;
    uint32_t observed_drop_count;
    uint64_t critical_deadline_us;
    uint64_t last_iteration_us;
    uint8_t critical_pending;
    uint64_t last_flush_us;
    uint64_t next_retry_us;
    uint8_t session_active;
    uint8_t session_finalized;
    uint8_t header_written;
    uint8_t startup_report_written;
    uint8_t decoder_profile_queued;
    uint8_t bootstrap_config_queued;
    uint16_t sink_offset_mod_quantum;
    SystemMissionSnapshotStatus snapshot;
} LoggerRuntime;

static LoggerRuntime s_logger;
static LoggerTaskDiagnostics s_diagnostics;
static uint8_t s_record_buffer[FLIGHT_LOG_MAX_RECORD_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t
    s_aggregate_buffer[SYSTEM_LOG_AGGREGATION_BUFFER_SIZE];

static void LoggerTask_HeaderInfoBuild(FlightLogFileHeaderInfo *info)
{
    static const uint8_t telemetry_tag[8] =
        SILVERSTAR_LOG_TELEMETRY_COMPATIBILITY_TAG;
    static const uint8_t build_tag[] = SILVERSTAR_LOG_BUILD_TAG;

    _Static_assert(sizeof(telemetry_tag) == 8U,
                   "Telemetry compatibility tag must contain eight bytes");
    _Static_assert(sizeof(build_tag) == 9U,
                   "SSLOG build tag must contain eight bytes");

    SILVERSTAR_ASSERT_OBJECT(info, FlightLogFileHeaderInfo,
                             SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(info, 0, sizeof(*info));
    info->profile_id = SYSTEM_LOG_PROFILE_ID;
    info->nominal_imu_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ;
    info->nominal_ins_rate_hz = (uint16_t)(SYSTEM_IMU_OUTPUT_RATE_HZ /
        SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT);
    info->coordinate_frame = 1U;
    info->position_axis_order[0] = 3U;
    info->position_axis_order[1] = 1U;
    info->position_axis_order[2] = 2U;
    info->quaternion_order = 1U;
    info->quaternion_semantics = 1U;
    info->local_gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2;
    (void)memcpy(info->air_compatibility_tag, telemetry_tag,
                 sizeof(info->air_compatibility_tag));
    (void)memcpy(info->build_tag, build_tag, sizeof(info->build_tag));
    info->mechanization_subsample_count =
        SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT;
    info->firmware_version[0] = SILVERSTAR_VERSION_MAJOR;
    info->firmware_version[1] = SILVERSTAR_VERSION_MINOR;
    info->firmware_version[2] = SILVERSTAR_VERSION_PATCH;
    info->firmware_version[3] = SILVERSTAR_VERSION_BUILD;
}

static uint8_t LoggerTask_SinkWrite(const uint8_t *data, uint32_t length)
{
    uint32_t written = 0U;
    uint64_t begin_us;
    uint64_t elapsed;
    SystemDeviceResult result;
    PlatformCriticalState state;

    if ((s_logger.session_active == 0U) ||
        (data == NULL) || (length == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT(length <= sizeof(s_aggregate_buffer),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(s_diagnostics.io_fault == 0U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    begin_us = SystemTime_GetMonotonicUs();
    result = SystemLogSink_Write(data, length, &written);
    elapsed = SystemTime_GetMonotonicUs() - begin_us;
    state = PlatformCritical_Enter();
    s_diagnostics.write_count++;
    s_diagnostics.total_write_us += elapsed;
    if (elapsed > s_diagnostics.max_write_us) { s_diagnostics.max_write_us = elapsed; }
    PlatformCritical_Exit(state);
    if ((result != SYSTEM_DEVICE_OK) || (written != length))
    {
        /* A partial/uncertain write cannot be replayed or appended to safely. */
        s_diagnostics.io_fault = 1U;
        s_diagnostics.append_failure_count++;
        return 0U;
    }
    s_logger.sink_offset_mod_quantum = (uint16_t)(
        ((uint32_t)s_logger.sink_offset_mod_quantum + length) %
        LOGGER_STREAMING_WRITE_QUANTUM_BYTES);
    return 1U;
}

static uint8_t LoggerTask_AggregateWrite(void)
{
    if (s_logger.aggregate_length == 0U) { return 1U; }
    if (LoggerTask_SinkWrite(s_aggregate_buffer,
                             s_logger.aggregate_length) == 0U)
    {
        return 0U;
    }
    s_logger.aggregate_length = 0U;
    return 1U;
}

static uint8_t LoggerTask_StreamingWrite(void)
{
    uint32_t tail = ((uint32_t)s_logger.sink_offset_mod_quantum +
        s_logger.aggregate_length) % LOGGER_STREAMING_WRITE_QUANTUM_BYTES;
    uint32_t prefix;
    if (tail >= s_logger.aggregate_length) { return LoggerTask_AggregateWrite(); }
    prefix = s_logger.aggregate_length - tail;
    SILVERSTAR_ASSERT(prefix <= sizeof(s_aggregate_buffer),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    /* This is only a batching optimization. Arbitrary byte lengths remain
     * legal; critical, periodic and final flushes still write the entire tail.
     * No record padding or DMA-buffer reuse occurs before successful return. */
    if (LoggerTask_SinkWrite(s_aggregate_buffer, prefix) == 0U) { return 0U; }
    s_logger.aggregate_length = tail;
    (void)memmove(s_aggregate_buffer, &s_aggregate_buffer[prefix], tail);
    return 1U;
}

static uint8_t LoggerTask_SinkFlush(void)
{
    if (SystemLogSink_Flush() != SYSTEM_DEVICE_OK)
    {
        s_diagnostics.io_fault = 1U;
        s_diagnostics.flush_failure_count++;
        return 0U;
    }
    return 1U;
}

static uint8_t LoggerTask_Flush(void)
{
    if ((LoggerTask_AggregateWrite() == 0U) ||
        (LoggerTask_SinkFlush() == 0U)) { return 0U; }
    s_logger.last_flush_us = SystemTime_GetMonotonicUs();
    s_logger.critical_pending = 0U;
    return 1U;
}

static uint8_t LoggerTask_SinkEnd(void)
{
    if (SystemLogSink_SessionEnd() != SYSTEM_DEVICE_OK)
    {
        s_diagnostics.close_failure_count++;
        return 0U;
    }
    return 1U;
}

static void LoggerTask_Close(void)
{
    if (s_logger.session_active != 0U)
    {
        /* The sink owns write/close error counters; close remains best effort. */
        /* Pending aggregate is never replayed by an error close. */
        (void)LoggerTask_SinkEnd();
    }
    s_diagnostics.discarded_bytes += s_logger.aggregate_length;
    s_logger.session_active = 0U;
    s_logger.aggregate_length = 0U;
}

static uint8_t LoggerTask_DecoderProfileQueue(uint64_t timestamp_us)
{
    if (s_logger.decoder_profile_queued != 0U) { return 1U; }
    if (LoggerBus_DecoderProfileDescriptorPush(timestamp_us) !=
        LOGGER_BUS_RESULT_OK)
    {
        return 0U;
    }
    s_logger.decoder_profile_queued = 1U;
    return 1U;
}

static uint8_t LoggerTask_SessionOpen(void)
{
    FlightLogFileHeaderInfo header_info;
    SystemLogSessionInfo info;
    SystemDeviceResult result;
    uint16_t header_size = 0U;

    SILVERSTAR_ASSERT(s_logger.session_active <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_logger.header_written <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_diagnostics.io_fault != 0U) { return 0U; }
    result = SystemLogSink_Init();
    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        return 0U;
    }
    (void)memset(&info, 0, sizeof(info));
    info.profile_id = SystemProfile_Get()->profile_id;
    info.version_major = SILVERSTAR_VERSION_MAJOR;
    info.version_minor = SILVERSTAR_VERSION_MINOR;
    info.version_patch = SILVERSTAR_VERSION_PATCH;
    result = SystemLogSink_SessionBegin(&info);
    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        return 0U;
    }
    s_logger.session_active = 1U;
    s_diagnostics.session_count++;
    s_logger.last_flush_us = SystemTime_GetMonotonicUs();
    if (s_logger.header_written == 0U)
    {
        LoggerTask_HeaderInfoBuild(&header_info);
        if ((FlightLog_FileHeaderSerialize(&header_info, s_record_buffer,
                                           sizeof(s_record_buffer),
                                           &header_size) !=
             FLIGHT_LOG_SERIALIZE_RESULT_OK) ||
            (LoggerTask_SinkWrite(s_record_buffer, header_size) == 0U) ||
            (LoggerTask_SinkFlush() == 0U))
        {
            s_diagnostics.io_fault = 1U;
            LoggerTask_Close();
            return 0U;
        }
        s_logger.header_written = 1U;
        s_logger.record_sequence = 0U;
        s_logger.last_flush_us = SystemTime_GetMonotonicUs();
    }
    /* A full startup queue must not prevent the only consumer from opening.
     * Retry the Required descriptor after freeing a slot in the main loop. */
    (void)LoggerTask_DecoderProfileQueue(s_logger.last_flush_us);
    return 1U;
}

static uint8_t LoggerTask_DescriptorRecordIsCritical(uint8_t record_type)
{
    return (uint8_t)((record_type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG) ||
        (record_type == FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR) ||
        (record_type == FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR) ||
        (record_type == FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR) ||
        (record_type == FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR) ||
        (record_type == FLIGHT_LOG_RECORD_INITIAL_STATE) ||
        (record_type == FLIGHT_LOG_RECORD_MISSION_CONFIG) ||
        (record_type == FLIGHT_LOG_RECORD_CALIBRATION_RESULT) ||
        (record_type == FLIGHT_LOG_RECORD_ALIGNMENT_RESULT));
}

static uint8_t LoggerTask_EventRecordIsCritical(
    const FlightLogRecord *record)
{
    return (uint8_t)((record->record_type == FLIGHT_LOG_RECORD_EVENT) &&
        ((record->payload.event.event_id == FLIGHT_LOG_EVENT_MISSION_START) ||
         (record->payload.event.event_id == FLIGHT_LOG_EVENT_SELF_TEST_COMPLETE) ||
         (record->payload.event.event_id == FLIGHT_LOG_EVENT_LANDING) ||
         (record->payload.event.event_id == FLIGHT_LOG_EVENT_SYSTEM_FAULT)));
}

static uint8_t LoggerTask_RecordIsCritical(const FlightLogRecord *record)
{
    if (record == NULL) { return 0U; }
    if (LoggerTask_DescriptorRecordIsCritical(record->record_type) != 0U)
    { return 1U; }
    return LoggerTask_EventRecordIsCritical(record);
}

static uint8_t LoggerTask_Finalize(void)
{
    SILVERSTAR_ASSERT(s_logger.session_active <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_logger.session_finalized <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_logger.session_active == 0U) ||
        (LoggerTask_AggregateWrite() == 0U) ||
        (LoggerTask_SinkFlush() == 0U) ||
        (LoggerTask_SinkEnd() == 0U))
    {
        s_diagnostics.io_fault = 1U;
        LoggerTask_Close();
        return 0U;
    }
    s_logger.last_flush_us = SystemTime_GetMonotonicUs();
    if (SystemMissionSnapshot_FinalStatusWrite(
            s_logger.last_flush_us, s_diagnostics.io_fault) !=
        SystemMissionSnapshotResult_Ok)
    { s_diagnostics.final_status_write_failed = 1U; }
    s_logger.session_active = 0U;
    s_logger.session_finalized = 1U;
    s_logger.aggregate_length = 0U;
    LoggerBus_FinalizationComplete();
    return 1U;
}

static uint8_t LoggerTask_RecordAppend(const FlightLogRecord *record)
{
    uint16_t serialized_size = 0U;
    uint32_t drops = LoggerBus_OverflowCountGet();

    if (record == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    /* Both queues are merged fairly, so a push-time sequence would reorder.
     * Advance the writer sequence by each newly observed explicit drop. */
    s_logger.record_sequence += drops - s_logger.observed_drop_count;
    s_logger.observed_drop_count = drops;
    if (FlightLog_RecordSerialize(record, s_logger.record_sequence,
                                  s_record_buffer,
                                  sizeof(s_record_buffer),
                                  &serialized_size) !=
        FLIGHT_LOG_SERIALIZE_RESULT_OK)
    {
        s_diagnostics.serialize_failure_count++;
        s_diagnostics.io_fault = 1U;
        return 0U;
    }
    if ((s_logger.aggregate_length + serialized_size) >
        sizeof(s_aggregate_buffer))
    {
        if (LoggerTask_StreamingWrite() == 0U) { return 0U; }
    }
    (void)memcpy(&s_aggregate_buffer[s_logger.aggregate_length],
                 s_record_buffer, serialized_size);
    s_logger.aggregate_length += serialized_size;
    s_logger.record_sequence++;
    s_diagnostics.serialized_count++;
    if ((LoggerTask_RecordIsCritical(record) != 0U) &&
        (s_logger.critical_pending == 0U))
    {
        s_logger.critical_pending = 1U;
        s_logger.critical_deadline_us = SystemTime_GetMonotonicUs() +
            LOGGER_CRITICAL_FLUSH_MAX_US;
    }
    /* Coalesce a descriptor/START burst into one sync. Never extend the first
     * critical record's deadline; an empty queue still flushes immediately. */
    if ((s_logger.critical_pending != 0U) &&
        ((LoggerBus_Count() == 0U) ||
         (SystemTime_GetMonotonicUs() >= s_logger.critical_deadline_us)))
    { return LoggerTask_Flush(); }
    return 1U;
}

static uint32_t LoggerTask_StringHash(const char *text)
{
    uint32_t hash = 2166136261UL;
    uint32_t index;

    if (text == NULL) { return 0U; }
    for (index = 0U; index < LOGGER_MAX_TEXT_LENGTH; index++)
    {
        if (text[index] == '\0')
        {
            return hash;
        }
        hash ^= (uint8_t)text[index];
        hash *= 16777619UL;
    }
    SILVERSTAR_ASSERT(index < LOGGER_MAX_TEXT_LENGTH,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    return 0U;
}

static uint8_t LoggerTask_StartupEventAppend(uint64_t timestamp_us,
                                             FlightLogEventId event_id,
                                             uint32_t arg0,
                                             uint32_t arg1)
{
    FlightLogRecord record;

    (void)memset(&record, 0, sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_EVENT;
    record.timestamp_us = timestamp_us;
    record.payload.event.event_id = event_id;
    record.payload.event.arg0 = arg0;
    record.payload.event.arg1 = arg1;
    return LoggerTask_RecordAppend(&record);
}

static uint8_t LoggerTask_StartupDeviceAppend(
    uint64_t timestamp_us,
    const SystemStartupDeviceReport *device)
{
    uint32_t identity;
    uint32_t results;

    SILVERSTAR_ASSERT_OBJECT(device, SystemStartupDeviceReport,
                             SILVERSTAR_ASSERT_MODULE_APP);
    identity = (uint32_t)device->device_id |
        ((uint32_t)device->required << 8U) |
        ((uint32_t)device->safety_critical << 9U) |
        ((uint32_t)device->present << 10U) |
        ((device->capability_mask & 0xFFFFUL) << 16U);
    results = ((uint32_t)device->init_result) |
        ((uint32_t)device->start_result << 4U) |
        ((uint32_t)device->config_result << 8U) |
        ((uint32_t)device->persist_result << 12U) |
        ((uint32_t)device->verify_result << 16U) |
        ((uint32_t)device->communication_result << 20U);
    if ((LoggerTask_StartupEventAppend(timestamp_us,
            FLIGHT_LOG_EVENT_STARTUP_DEVICE_RESULT,
            identity, results) == 0U) ||
        (LoggerTask_StartupEventAppend(timestamp_us,
            FLIGHT_LOG_EVENT_STARTUP_CONFIG_MASKS,
            device->requested_mask, device->applied_mask) == 0U) ||
        (LoggerTask_StartupEventAppend(timestamp_us,
            FLIGHT_LOG_EVENT_STARTUP_CONFIG_FAILURES,
            device->delegated_mask, device->failed_mask) == 0U) ||
        (LoggerTask_StartupEventAppend(timestamp_us,
            FLIGHT_LOG_EVENT_STARTUP_DEVICE_DETAIL,
            device->detail_code, device->retry_count) == 0U) ||
        (LoggerTask_StartupEventAppend(timestamp_us,
            FLIGHT_LOG_EVENT_STARTUP_DEVICE_NAMES,
            LoggerTask_StringHash(device->device_name),
            LoggerTask_StringHash(device->model_name)) == 0U))
    { return 0U; }
    return 1U;
}

static uint8_t LoggerTask_StartupGnssAppend(
    uint64_t timestamp_us,
    const SystemGnssConfigTransactionReport *gnss)
{
    uint32_t results;

    SILVERSTAR_ASSERT_OBJECT(gnss, SystemGnssConfigTransactionReport,
                             SILVERSTAR_ASSERT_MODULE_APP);
    results = ((uint32_t)gnss->uart_baudrate_result) |
        ((uint32_t)gnss->uart_settle_result << 4U) |
        ((uint32_t)gnss->protocol_result << 8U) |
        ((uint32_t)gnss->nav_pvt_result << 12U) |
        ((uint32_t)gnss->rate_result << 16U) |
        ((uint32_t)gnss->dynamic_model_result << 20U) |
        ((uint32_t)gnss->signals_result << 24U) |
        ((uint32_t)gnss->pvt_recovery_result << 28U);
    if (LoggerTask_StartupEventAppend(
            timestamp_us,
            FLIGHT_LOG_EVENT_GNSS_CONFIG_TRANSACTION,
            results,
            ((uint32_t)gnss->failed_stage << 16U) |
            ((uint32_t)gnss->ack_result << 8U) |
            (uint32_t)gnss->write_layers) == 0U)
    {
        return 0U;
    }
    return 1U;
}

static uint8_t LoggerTask_StartupReportWrite(void)
{
    const SystemStartupReport *report = SystemStartup_GetReport();
    uint8_t index;

    if ((report == NULL) || (report->completed == 0U)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(report, SystemStartupReport,
                             SILVERSTAR_ASSERT_MODULE_APP);
    if (LoggerTask_StartupEventAppend(report->timestamp_us,
            FLIGHT_LOG_EVENT_SELF_TEST_COMPLETE, report->passed,
            ((report->required_failure_mask & 0xFFFFUL) << 16U) |
             (report->warning_mask & 0xFFFFUL)) == 0U)
    { return 0U; }
    for (index = 0U; index < report->device_count; index++)
    {
        if (LoggerTask_StartupDeviceAppend(
                report->timestamp_us, &report->devices[index]) == 0U)
        { return 0U; }
    }
    return LoggerTask_StartupGnssAppend(
        report->timestamp_us, &report->gnss_config);
}

static void LoggerTask_SessionOpenTry(uint64_t now_us)
{
    SILVERSTAR_ASSERT(s_logger.session_active == 0U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_logger.startup_report_written <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_diagnostics.io_fault != 0U) || (now_us < s_logger.next_retry_us)) { return; }
    s_diagnostics.open_attempt_count++;
    if (LoggerTask_SessionOpen() == 0U)
    {
        s_diagnostics.open_failure_count++;
        s_logger.next_retry_us = now_us + SYSTEM_LOG_RETRY_PERIOD_US;
    }
}

static uint8_t LoggerTask_SnapshotMaintain(void)
{
    SystemMissionSnapshotResult result;
    PlatformCriticalState state;
    SILVERSTAR_ASSERT(s_logger.session_active <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_diagnostics.snapshot_ready <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_logger.session_active == 0U) { return 0U; }
    if ((s_diagnostics.snapshot_ready != 0U) &&
        (s_logger.snapshot.calibration_generation ==
         SystemCalibration_GenerationGet()))
    { return 1U; }
    state = PlatformCritical_Enter();
    s_diagnostics.snapshot_ready = 0U;
    PlatformCritical_Exit(state);
    result = SystemMissionSnapshot_Create(&s_logger.snapshot);
    if (result == SystemMissionSnapshotResult_NotReady) { return 0U; }
    if (result != SystemMissionSnapshotResult_Ok)
    {
        s_diagnostics.io_fault = 1U;
        LoggerTask_Close();
        return 0U;
    }
    state = PlatformCritical_Enter();
    s_diagnostics.snapshot_mission_id = s_logger.snapshot.mission_id;
    s_diagnostics.snapshot_commit_generation =
        s_logger.snapshot.commit_generation;
    s_diagnostics.snapshot_sequence = s_logger.snapshot.snapshot_sequence;
    s_diagnostics.snapshot_base_instance =
        s_logger.snapshot.snapshot_base_instance;
    s_diagnostics.snapshot_calibration_generation =
        s_logger.snapshot.calibration_generation;
    s_diagnostics.snapshot_ready = 1U;
    PlatformCritical_Exit(state);
    return 1U;
}

static void LoggerTask_BootstrapProcess(uint64_t now_us)
{
    const SystemStartupReport *report = SystemStartup_GetReport();
    PlatformCriticalState state;
    if ((s_logger.session_active == 0U) ||
        (LoggerBus_StartupStateGet() == LOGGER_STREAMING_READY) ||
        (LoggerBus_Count() != 0U)) { return; }
    SILVERSTAR_ASSERT(s_logger.header_written != 0U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_diagnostics.io_fault == 0U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (LoggerTask_DecoderProfileQueue(now_us) == 0U) { return; }
    if (LoggerBus_Count() != 0U) { return; }
    if (s_logger.bootstrap_config_queued == 0U)
    {
        if (LoggerBus_SystemConfigPush(now_us) == LOGGER_BUS_RESULT_OK)
        { s_logger.bootstrap_config_queued = 1U; }
        return;
    }
    /* Startup may still be collecting. Keep this session and drain critical
     * records; an incomplete report is not a storage failure or reopen reason. */
    if ((report == NULL) || (report->completed == 0U)) { return; }
    if (s_logger.startup_report_written == 0U)
    {
        if (LoggerTask_StartupReportWrite() == 0U)
        { LoggerTask_Close(); return; }
        s_logger.startup_report_written = 1U;
    }
    if (LoggerTask_Flush() == 0U) { LoggerTask_Close(); return; }
    if (LoggerTask_SnapshotMaintain() == 0U) { return; }
    /* Producers can run during sync. Admission opens only if their critical
     * records have also drained; no producer waits for this transition. */
    if (LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK)
    {
        state = PlatformCritical_Enter();
        s_diagnostics.streaming_ready_us = SystemTime_GetMonotonicUs();
        PlatformCritical_Exit(state);
    }
}

static uint8_t LoggerTask_DrainFinalizeTry(
    uint64_t now_us,
    LoggerBusFinalizationState finalization_state)
{
    if ((s_logger.session_active == 0U) ||
        (finalization_state != LOGGER_BUS_FINALIZATION_DRAINING) ||
        (LoggerBus_Count() != 0U))
    { return 0U; }
    if ((now_us >= s_logger.next_retry_us) &&
        (LoggerTask_Finalize() == 0U))
    {
        s_logger.next_retry_us = now_us + SYSTEM_LOG_RETRY_PERIOD_US;
    }
    return 1U;
}

static void LoggerTask_IterationRecord(uint64_t now_us)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    uint64_t elapsed = now_us - s_logger.last_iteration_us;
    if ((s_logger.last_iteration_us != 0ULL) &&
        (elapsed > s_diagnostics.max_iteration_us))
    { s_diagnostics.max_iteration_us = elapsed; }
    s_logger.last_iteration_us = now_us;
    s_diagnostics.iteration_count++;
    PlatformCritical_Exit(state);
}

static void LoggerTask_PeriodicFlushTry(uint64_t now_us)
{
    if ((s_logger.session_active != 0U) &&
        (((now_us - s_logger.last_flush_us) >= SYSTEM_LOG_SYNC_PERIOD_US) ||
         ((s_logger.critical_pending != 0U) &&
          (now_us >= s_logger.critical_deadline_us))))
    {
        if (LoggerTask_Flush() == 0U)
        {
            LoggerTask_Close();
            s_logger.next_retry_us = now_us + SYSTEM_LOG_RETRY_PERIOD_US;
        }
    }
}

void AppTask_Logger(void *argument)
{
    FlightLogRecord record;
    LoggerBusFinalizationState finalization_state;
    uint64_t now_us;

    (void)argument;
    (void)memset(&s_logger, 0, sizeof(s_logger));
    (void)memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    SILVERSTAR_ASSERT(s_logger.session_active == 0U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_logger.session_finalized == 0U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (;;)
    {
        now_us = SystemTime_GetMonotonicUs();
        LoggerTask_IterationRecord(now_us);
        finalization_state = LoggerBus_FinalizationProcess(now_us);
        if ((s_logger.session_finalized != 0U) ||
            (finalization_state == LOGGER_BUS_FINALIZATION_FINALIZED))
        {
            vTaskDelay(pdMS_TO_TICKS(10U));
            continue;
        }
        if (s_logger.session_active == 0U)
        {
            LoggerTask_SessionOpenTry(now_us);
            if (s_logger.session_active == 0U)
            { vTaskDelay(pdMS_TO_TICKS(10U)); continue; }
        }

        if (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
        {
            s_diagnostics.drain_count++;
            (void)LoggerTask_DecoderProfileQueue(now_us);
            if (LoggerTask_RecordAppend(&record) == 0U)
            {
                LoggerTask_Close();
                s_logger.next_retry_us = now_us + SYSTEM_LOG_RETRY_PERIOD_US;
            }
        }
        else
        {
            vTaskDelay(pdMS_TO_TICKS(2U));
        }

        now_us = SystemTime_GetMonotonicUs();
        finalization_state = LoggerBus_FinalizationProcess(now_us);
        if (LoggerTask_DrainFinalizeTry(now_us, finalization_state) != 0U)
        {
            vTaskDelay(pdMS_TO_TICKS(2U));
            continue;
        }
        LoggerTask_PeriodicFlushTry(now_us);
        if (LoggerBus_StartupStateGet() == LOGGER_STREAMING_READY)
        { (void)LoggerTask_SnapshotMaintain(); }
        LoggerTask_BootstrapProcess(now_us);
    }
}

SystemDeviceResult LoggerTask_DiagnosticsGet(LoggerTaskDiagnostics *diagnostics)
{
    PlatformCriticalState state;
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    state = PlatformCritical_Enter();
    *diagnostics = s_diagnostics;
    PlatformCritical_Exit(state);
    return SYSTEM_DEVICE_OK;
}
