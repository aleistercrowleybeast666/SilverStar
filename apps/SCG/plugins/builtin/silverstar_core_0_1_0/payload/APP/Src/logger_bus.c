#include "logger_bus.h"

#include <stddef.h>
#include <string.h>

#include "common_spsc_queue.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "project_log_decoder_profile.h"
#include "silverstar_assert.h"
#include "system_descriptor_if.h"
#include "system_estimator_profile.h"
#include "system_log_policy.h"
#include "system_navigation_profile.h"
#include "system_profile.h"
#include "system_user_config.h"
#include "system_version.h"

#define LOGGER_RECORD_QUEUE_DEPTH \
    SYSTEM_LOG_RECORD_QUEUE_DEPTH
#define LOGGER_ESTIMATOR_RECORD_QUEUE_DEPTH \
    SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH

_Static_assert(FLIGHT_LOG_MAX_PAYLOAD_SIZE >=
               FLIGHT_LOG_INITIAL_STATE_PAYLOAD_SIZE,
               "SSLOG payload capacity is too small");
_Static_assert(FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR <= 0xFFU,
               "SSLOG0 record type must fit in one byte");
static CommonSpscQueue s_logger_queue;
static uint8_t s_logger_storage[LOGGER_RECORD_QUEUE_DEPTH][SYSTEM_LOG_RECORD_SLOT_SIZE];
static CommonSpscQueue s_estimator_logger_queue;
static uint8_t s_estimator_logger_storage[LOGGER_ESTIMATOR_RECORD_QUEUE_DEPTH]
    [SYSTEM_LOG_ESTIMATOR_SLOT_SIZE];
static LoggerBusDiagnostics s_diagnostics;
static uint8_t s_initialized;
static uint8_t s_next_estimator_queue;
static uint8_t s_queue_drain_run;
static uint8_t s_accepting_records;
static uint8_t s_boot_disabled;
static LoggerBusFinalizationState s_finalization_state;
static uint64_t s_finalization_deadline_us;

/* Request payload is written by the claimant, immutable after publication.
 * Descriptor tables are generated const data. Only LoggerTask advances cursor.
 * Locks protect phase/publication, never construction of the record batch. */
typedef enum
{
    LOGGER_REQUEST_IDLE = 0U, LOGGER_REQUEST_BUILDING,
    LOGGER_REQUEST_READY, LOGGER_REQUEST_BARRIER, LOGGER_REQUEST_FAULT
} LoggerRequestPhase;
typedef struct
{
    FlightLogSystemConfigRecord config;
    SystemLogStreamConfig streams[SSLOG_RECORD_COUNT];
    LoggerBusStartRecords start;
    uint64_t timestamp_us;
    uint32_t generation;
    uint16_t cursor;
    uint16_t count;
    uint8_t is_start;
    LoggerRequestPhase phase;
    uint8_t io_fault;
    uint32_t next_generation;
    uint32_t acknowledged_generation;
} LoggerSnapshotRequest;
/* CPU-only owned copies: never passed to HAL, FatFs, a DMA engine or sink.
 * Target owns placement; targets without CCM retain ordinary static BSS. */
static PLATFORM_CPU_FAST_BSS LoggerSnapshotRequest s_request;

_Static_assert(SYSTEM_LOG_RECORD_SLOT_SIZE >= offsetof(FlightLogRecord, payload) &&
    SYSTEM_LOG_RECORD_SLOT_SIZE <= sizeof(FlightLogRecord), "Invalid normal slot size");
_Static_assert(SYSTEM_LOG_ESTIMATOR_SLOT_SIZE >= offsetof(FlightLogRecord, payload) &&
    SYSTEM_LOG_ESTIMATOR_SLOT_SIZE <= sizeof(FlightLogRecord), "Invalid estimator slot size");

/* Called with IRQ ownership held, before either queue's copy. A corrupted
 * stride/capacity must fail-stop before accessing storage or the output. */
static void LoggerBus_QueueGeometryValidate(const CommonSpscQueue *queue)
{
    uint8_t estimator = (uint8_t)(queue == &s_estimator_logger_queue);
    SILVERSTAR_ASSERT((queue == &s_logger_queue) || estimator,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(queue->item_size == (estimator ? SYSTEM_LOG_ESTIMATOR_SLOT_SIZE :
        SYSTEM_LOG_RECORD_SLOT_SIZE) && queue->capacity == (estimator ?
        LOGGER_ESTIMATOR_RECORD_QUEUE_DEPTH : LOGGER_RECORD_QUEUE_DEPTH) &&
        queue->storage == (estimator ? &s_estimator_logger_storage[0][0] : &s_logger_storage[0][0]),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
}

static PlatformCriticalState LoggerBus_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void LoggerBus_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

static LoggerBusResult LoggerBus_PushStateGet(void)
{
    LoggerBusResult result;
    PlatformCriticalState state = LoggerBus_IrqLock();

    result = ((s_initialized != 0U) &&
              ((s_accepting_records != 0U) || (s_boot_disabled != 0U))) ?
        LOGGER_BUS_RESULT_OK : LOGGER_BUS_RESULT_BAD_STATE;
    if (result != LOGGER_BUS_RESULT_OK) { s_diagnostics.state_reject_count++; }
    LoggerBus_IrqUnlock(state);
    return result;
}

static LoggerBusResult LoggerBus_QueuePush(
    CommonSpscQueue *queue, const FlightLogRecord *record)
{
    CommonSpscQueueResult queue_result;
    PlatformCriticalState state;

    if ((queue == NULL) || (record == NULL))
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(queue, CommonSpscQueue,
                             SILVERSTAR_ASSERT_MODULE_APP);
    state = LoggerBus_IrqLock();
    if ((s_initialized == 0U) ||
        ((s_accepting_records == 0U) && (s_boot_disabled == 0U)))
    {
        s_diagnostics.state_reject_count++;
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_BAD_STATE;
    }
    if (s_boot_disabled != 0U)
    {
        s_diagnostics.disabled_suppressed_count++;
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_OK;
    }
    LoggerBus_QueueGeometryValidate(queue);
    /* Mandatory evidence cannot be admitted to a latched failed writer. */
    if ((record->record_type == FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE) &&
        (s_request.io_fault != 0U))
    {
        s_diagnostics.state_reject_count++;
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_BAD_STATE;
    }
    queue_result = CommonSpscQueue_Push(queue, record);
    if (queue_result == COMMON_SPSC_QUEUE_RESULT_OK)
    {
        uint16_t count = CommonSpscQueue_Count(queue);
        uint16_t *high_water = (queue == &s_logger_queue) ?
            &s_diagnostics.normal_high_water : &s_diagnostics.estimator_high_water;
        s_diagnostics.accepted_count++;
        if (count > *high_water) { *high_water = count; }
    }
    else { s_diagnostics.capacity_reject_count++; }
    LoggerBus_IrqUnlock(state);
    if (queue_result == COMMON_SPSC_QUEUE_RESULT_OK)
    {
        return LOGGER_BUS_RESULT_OK;
    }
    return (queue_result == COMMON_SPSC_QUEUE_RESULT_FULL) ?
        LOGGER_BUS_RESULT_FULL : LOGGER_BUS_RESULT_BAD_PARAM;
}

/* C object sizes include native padding; SSLOG wire sizes are unrelated.
 * Byte slots are copied by memcpy and are never dereferenced as typed objects. */
static size_t LoggerBus_PayloadSizeGet(FlightLogRecordType type)
{
    switch (type)
    {
        case FLIGHT_LOG_RECORD_EVENT: return sizeof(((FlightLogRecord *)0)->payload.event);
        case FLIGHT_LOG_RECORD_STATS: return sizeof(((FlightLogRecord *)0)->payload.stats);
        case FLIGHT_LOG_RECORD_ESTIMATOR: return sizeof(((FlightLogRecord *)0)->payload.estimator);
        case FLIGHT_LOG_RECORD_SYSTEM_CONFIG: return sizeof(((FlightLogRecord *)0)->payload.system_config);
        case FLIGHT_LOG_RECORD_PURE_INS: return sizeof(((FlightLogRecord *)0)->payload.pure_ins);
        case FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC: return sizeof(((FlightLogRecord *)0)->payload.kf6_diagnostic);
        case FLIGHT_LOG_RECORD_KF6_FULL_P: return sizeof(((FlightLogRecord *)0)->payload.kf6_full_p);
        case FLIGHT_LOG_RECORD_POWER: return sizeof(((FlightLogRecord *)0)->payload.power);
        case FLIGHT_LOG_RECORD_HEALTH: return sizeof(((FlightLogRecord *)0)->payload.health);
        case FLIGHT_LOG_RECORD_TELEMETRY_DIAG: return sizeof(((FlightLogRecord *)0)->payload.telemetry_diagnostic);
        case FLIGHT_LOG_RECORD_INITIAL_STATE: return sizeof(((FlightLogRecord *)0)->payload.initial_state);
        case FLIGHT_LOG_RECORD_GNSS_NATIVE: return sizeof(((FlightLogRecord *)0)->payload.gnss_native);
        case FLIGHT_LOG_RECORD_BARO_NATIVE: return sizeof(((FlightLogRecord *)0)->payload.baro_native);
        case FLIGHT_LOG_RECORD_MAG_NATIVE: return sizeof(((FlightLogRecord *)0)->payload.mag_native);
        case FLIGHT_LOG_RECORD_INERTIAL_INCREMENT: return sizeof(((FlightLogRecord *)0)->payload.inertial_increment);
        case FLIGHT_LOG_RECORD_GNSS_MEASUREMENT: return sizeof(((FlightLogRecord *)0)->payload.gnss_measurement);
        case FLIGHT_LOG_RECORD_BARO_MEASUREMENT: return sizeof(((FlightLogRecord *)0)->payload.baro_measurement);
        case FLIGHT_LOG_RECORD_IMU_CORRECTED: return sizeof(((FlightLogRecord *)0)->payload.imu_corrected);
        case FLIGHT_LOG_RECORD_CALIBRATION_RESULT: return sizeof(((FlightLogRecord *)0)->payload.calibration_result);
        case FLIGHT_LOG_RECORD_ALIGNMENT_RESULT: return sizeof(((FlightLogRecord *)0)->payload.alignment_result);
        case FLIGHT_LOG_RECORD_MISSION_CONFIG: return sizeof(((FlightLogRecord *)0)->payload.mission_config);
        case FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR: return sizeof(((FlightLogRecord *)0)->payload.device_descriptor);
        case FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR: return sizeof(((FlightLogRecord *)0)->payload.algorithm_descriptor);
        case FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR: return sizeof(((FlightLogRecord *)0)->payload.stream_descriptor);
        case FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR: return sizeof(((FlightLogRecord *)0)->payload.decoder_profile_descriptor);
        case FLIGHT_LOG_RECORD_ESTIMATOR_STEP: return sizeof(((FlightLogRecord *)0)->payload.estimator_step);
        case FLIGHT_LOG_RECORD_GNSS_RECOVERY: return sizeof(((FlightLogRecord *)0)->payload.gnss_recovery);
        case FLIGHT_LOG_RECORD_LANDING_DIAGNOSTIC: return sizeof(((FlightLogRecord *)0)->payload.landing_diagnostic);
        case FLIGHT_LOG_RECORD_ESKF15_STATE: return sizeof(((FlightLogRecord *)0)->payload.eskf15_state);
        case FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART: return sizeof(((FlightLogRecord *)0)->payload.eskf15_full_p_part);
        case FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE: return sizeof(((FlightLogRecord *)0)->payload.eskf15_initial_state);
        case FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART: return sizeof(((FlightLogRecord *)0)->payload.eskf15_initial_p_part);
        case FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT: return sizeof(((FlightLogRecord *)0)->payload.eskf15_measurement);
        case FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT: return sizeof(((FlightLogRecord *)0)->payload.eskf15_body_input);
        case FLIGHT_LOG_RECORD_NAV_QUALITY: return sizeof(((FlightLogRecord *)0)->payload.navigation_quality);
        case FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE: return sizeof(((FlightLogRecord *)0)->payload.alignment_evidence);
        case FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY: return sizeof(((FlightLogRecord *)0)->payload.mission_snapshot_identity);
        case FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY: return sizeof(((FlightLogRecord *)0)->payload.mag_calibration_identity);
        case FLIGHT_LOG_RECORD_SF6_STATE: return sizeof(((FlightLogRecord *)0)->payload.sf6_state);
        case FLIGHT_LOG_RECORD_SF6_MEASUREMENT: return sizeof(((FlightLogRecord *)0)->payload.sf6_measurement);
        default: return 0U;
    }
}

static uint8_t LoggerBus_EstimatorLaneGet(FlightLogRecordType type)
{
    return (uint8_t)(type == FLIGHT_LOG_RECORD_BARO_MEASUREMENT ||
        type == FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT ||
        type == FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART ||
        type == FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE ||
        type == FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT ||
        type == FLIGHT_LOG_RECORD_ESTIMATOR ||
        type == FLIGHT_LOG_RECORD_ESTIMATOR_STEP ||
        type == FLIGHT_LOG_RECORD_GNSS_MEASUREMENT ||
        type == FLIGHT_LOG_RECORD_GNSS_RECOVERY ||
        type == FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC ||
        type == FLIGHT_LOG_RECORD_KF6_FULL_P ||
        type == FLIGHT_LOG_RECORD_NAV_QUALITY ||
        type == FLIGHT_LOG_RECORD_SF6_MEASUREMENT ||
        type == FLIGHT_LOG_RECORD_SF6_STATE);
}

static LoggerBusResult LoggerBus_RecordPush(
    FlightLogRecordType type, uint64_t timestamp_us,
    uint32_t valid_flags, const void *payload,
    size_t payload_size, uint8_t estimator_queue)
{
    FlightLogRecord record;

    size_t expected = LoggerBus_PayloadSizeGet(type);
    size_t slot = (estimator_queue != 0U) ? SYSTEM_LOG_ESTIMATOR_SLOT_SIZE :
        SYSTEM_LOG_RECORD_SLOT_SIZE;
    if ((payload == NULL) || (expected == 0U) || (payload_size != expected) ||
        (estimator_queue != LoggerBus_EstimatorLaneGet(type)) ||
        (offsetof(FlightLogRecord, payload) + expected > slot) ||
        (payload_size > sizeof(record.payload)))
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    (void)memset(&record, 0, sizeof(record));
    record.record_type = type;
    record.timestamp_us = timestamp_us;
    record.valid_flags = valid_flags;
    /* In-memory queue copy only; SSLOG wire bytes use the generated codec. */
    (void)memcpy(&record.payload, payload, payload_size);
    return LoggerBus_QueuePush(
        (estimator_queue != 0U) ?
            &s_estimator_logger_queue : &s_logger_queue,
        &record);
}

static uint8_t LoggerBus_BootstrapAllows(FlightLogRecordType type)
{
    return (uint8_t)((type == FLIGHT_LOG_RECORD_EVENT) ||
        (type == FLIGHT_LOG_RECORD_STATS) ||
        (type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG) ||
        (type == FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR) ||
        (type == FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR) ||
        (type == FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR) ||
        (type == FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR) ||
        (type == FLIGHT_LOG_RECORD_CALIBRATION_RESULT) ||
        (type == FLIGHT_LOG_RECORD_ALIGNMENT_RESULT) ||
        (type == FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE) ||
        (type == FLIGHT_LOG_RECORD_MISSION_CONFIG) ||
        (type == FLIGHT_LOG_RECORD_INITIAL_STATE) ||
        (type == FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE) ||
        (type == FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART) ||
        (type == FLIGHT_LOG_RECORD_LANDING_DIAGNOSTIC));
}

static uint8_t LoggerBus_BootstrapSuppress(FlightLogRecordType type)
{
    uint8_t suppressed;
    PlatformCriticalState state = LoggerBus_IrqLock();
    suppressed = (uint8_t)((s_diagnostics.startup_state == LOGGER_BOOTSTRAP) &&
        (LoggerBus_BootstrapAllows(type) == 0U));
    if (suppressed != 0U) { s_diagnostics.bootstrap_suppressed_count++; }
    LoggerBus_IrqUnlock(state);
    return suppressed;
}

LoggerBusResult LoggerBus_StreamingReady(void)
{
    LoggerBusResult result = LOGGER_BUS_RESULT_BAD_STATE;
    PlatformCriticalState state = LoggerBus_IrqLock();
    if ((s_initialized != 0U) && (s_accepting_records != 0U) &&
        (s_boot_disabled == 0U))
    {
        result = LOGGER_BUS_RESULT_FULL;
        if ((CommonSpscQueue_Count(&s_logger_queue) == 0U) &&
            (CommonSpscQueue_Count(&s_estimator_logger_queue) == 0U) &&
            (s_request.phase == LOGGER_REQUEST_IDLE))
        {
            s_diagnostics.startup_state = LOGGER_STREAMING_READY;
            result = LOGGER_BUS_RESULT_OK;
        }
    }
    LoggerBus_IrqUnlock(state);
    return result;
}

LoggerBusStartupState LoggerBus_StartupStateGet(void)
{
    LoggerBusStartupState startup_state;
    PlatformCriticalState state = LoggerBus_IrqLock();
    startup_state = s_diagnostics.startup_state;
    LoggerBus_IrqUnlock(state);
    return startup_state;
}

LoggerBusResult LoggerBus_DisableForBootNoStorage(void)
{
    LoggerBusResult result = LOGGER_BUS_RESULT_BAD_STATE;
    PlatformCriticalState state = LoggerBus_IrqLock();
    SILVERSTAR_ASSERT((s_diagnostics.startup_state == LOGGER_BOOTSTRAP) ||
        (s_diagnostics.startup_state == LOGGER_STREAMING_READY) ||
        (s_diagnostics.startup_state == LOGGER_DISABLED_NO_STORAGE),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(s_boot_disabled <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_initialized != 0U) &&
        (s_diagnostics.startup_state != LOGGER_STREAMING_READY))
    {
        s_boot_disabled = 1U;
        s_diagnostics.disabled_discarded_count +=
            (uint32_t)CommonSpscQueue_Count(&s_logger_queue) +
            CommonSpscQueue_Count(&s_estimator_logger_queue);
        if (s_request.phase == LOGGER_REQUEST_READY)
        { s_diagnostics.disabled_discarded_count += s_request.count - s_request.cursor; }
        if (s_request.phase != LOGGER_REQUEST_BUILDING)
        { s_request.phase = LOGGER_REQUEST_IDLE; }
        CommonSpscQueue_Reset(&s_logger_queue);
        CommonSpscQueue_Reset(&s_estimator_logger_queue);
        s_diagnostics.startup_state = LOGGER_DISABLED_NO_STORAGE;
        result = LOGGER_BUS_RESULT_OK;
    }
    LoggerBus_IrqUnlock(state);
    return result;
}

static uint8_t LoggerBus_DisabledSuppress(void)
{
    uint8_t disabled;
    PlatformCriticalState state = LoggerBus_IrqLock();
    disabled = s_boot_disabled;
    if (disabled != 0U) { s_diagnostics.disabled_suppressed_count++; }
    LoggerBus_IrqUnlock(state);
    return disabled;
}

static LoggerBusResult LoggerBus_ConfiguredRecordPush(
    FlightLogRecordType type, uint64_t timestamp_us,
    uint32_t valid_flags, const void *payload,
    size_t payload_size, uint8_t estimator_queue)
{
    LoggerBusResult result;
    if (payload == NULL) { return LOGGER_BUS_RESULT_BAD_PARAM; }
    SILVERSTAR_ASSERT(payload_size > 0U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(estimator_queue <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (LoggerBus_PushStateGet() != LOGGER_BUS_RESULT_OK)
    {
        return LOGGER_BUS_RESULT_BAD_STATE;
    }
    if (LoggerBus_DisabledSuppress() != 0U) { return LOGGER_BUS_RESULT_OK; }
    if (SystemLogPolicy_ShouldEmitAt(type, timestamp_us) == 0U)
    {
        return LOGGER_BUS_RESULT_OK;
    }
    if (LoggerBus_BootstrapSuppress(type) != 0U) { return LOGGER_BUS_RESULT_OK; }
    result = LoggerBus_RecordPush(type, timestamp_us, valid_flags,
                                  payload, payload_size, estimator_queue);
    if (result == LOGGER_BUS_RESULT_OK)
    { SystemLogPolicy_EmissionTimeRecord(type, timestamp_us); }
    return result;
}

LoggerBusResult LoggerBus_Init(void)
{
    CommonSpscQueueResult normal_result;
    CommonSpscQueueResult estimator_result;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_accepting_records <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_initialized != 0U) { return LOGGER_BUS_RESULT_OK; }
    SystemLogPolicy_Init();
    (void)memset(s_logger_storage, 0, sizeof(s_logger_storage));
    (void)memset(s_estimator_logger_storage, 0,
                 sizeof(s_estimator_logger_storage));
    normal_result = CommonSpscQueue_Init(
        &s_logger_queue, s_logger_storage,
        LOGGER_RECORD_QUEUE_DEPTH, SYSTEM_LOG_RECORD_SLOT_SIZE);
    estimator_result = CommonSpscQueue_Init(
        &s_estimator_logger_queue, s_estimator_logger_storage,
        LOGGER_ESTIMATOR_RECORD_QUEUE_DEPTH, SYSTEM_LOG_ESTIMATOR_SLOT_SIZE);
    if ((normal_result != COMMON_SPSC_QUEUE_RESULT_OK) ||
        (estimator_result != COMMON_SPSC_QUEUE_RESULT_OK))
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    s_initialized = 1U;
    s_next_estimator_queue = 0U;
    s_queue_drain_run = 0U;
    s_accepting_records = 1U;
    s_finalization_state = LOGGER_BUS_FINALIZATION_IDLE;
    s_finalization_deadline_us = 0ULL;
    SystemLogPolicy_EmissionReset();
    return LOGGER_BUS_RESULT_OK;
}

void LoggerBus_Reset(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();

    if (s_initialized != 0U)
    {
        /* Reset is an initialization/test operation with producers quiescent. */
        SILVERSTAR_ASSERT(s_request.phase != LOGGER_REQUEST_BUILDING,
            SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
        s_request.phase = LOGGER_REQUEST_IDLE;
        s_request.generation = 0U;
        s_request.is_start = 0U;
        s_request.cursor = 0U;
        s_request.count = 0U;
        s_request.acknowledged_generation = 0U;
        s_request.io_fault = 0U;
        (void)memset(&s_diagnostics, 0, sizeof(s_diagnostics));
        s_diagnostics.startup_state = (s_boot_disabled != 0U) ?
            LOGGER_DISABLED_NO_STORAGE : LOGGER_BOOTSTRAP;
        CommonSpscQueue_Reset(&s_logger_queue);
        CommonSpscQueue_Reset(&s_estimator_logger_queue);
        s_next_estimator_queue = 0U;
        s_queue_drain_run = 0U;
        s_accepting_records = 1U;
        s_finalization_state = LOGGER_BUS_FINALIZATION_IDLE;
        s_finalization_deadline_us = 0ULL;
    }
    LoggerBus_IrqUnlock(state);
    SystemLogPolicy_EmissionReset();
}

LoggerBusResult LoggerBus_EventPush(
    uint64_t timestamp_us, FlightLogEventId event_id,
    uint32_t arg0, uint32_t arg1)
{
    FlightLogEventRecord record;

    if ((event_id < FLIGHT_LOG_EVENT_BOOT) ||
        (event_id >= FLIGHT_LOG_EVENT_ID_LIMIT))
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    (void)memset(&record, 0, sizeof(record));
    record.event_id = event_id;
    record.arg0 = arg0;
    record.arg1 = arg1;
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_EVENT, timestamp_us, 0U,
        &record, sizeof(record), 0U);
}

LoggerBusResult LoggerBus_StatsPush(
    uint64_t timestamp_us, const FlightLogStatsRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_STATS, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_EstimatorPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogEstimatorRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ESTIMATOR, timestamp_us, valid_flags,
        record, sizeof(*record), 1U);
}

static void LoggerBus_EstimatorConfigBuild(
    FlightLogSystemConfigRecord *record,
    const SystemEstimatorProfile *estimator_profile)
{
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogSystemConfigRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(estimator_profile, SystemEstimatorProfile,
                             SILVERSTAR_ASSERT_MODULE_APP);
    (void)memcpy(record->p0_diagonal, estimator_profile->p0_diagonal,
                 sizeof(record->p0_diagonal));
    (void)memcpy(record->process_accel_std_mps2,
                 estimator_profile->process_accel_std_mps2,
                 sizeof(record->process_accel_std_mps2));
    record->measurement_profile[0] = estimator_profile->gnss_accuracy_scale;
    record->measurement_profile[1] =
        estimator_profile->gnss_horizontal_position_std_floor_m;
    record->measurement_profile[2] =
        estimator_profile->gnss_vertical_position_std_floor_m;
    record->measurement_profile[3] =
        estimator_profile->gnss_velocity_std_floor_mps;
    record->measurement_profile[4] =
        estimator_profile->barometer_altitude_std_m;
    record->nis_profile[0] = estimator_profile->nis_1d_soft;
    record->nis_profile[1] = estimator_profile->nis_1d_hard;
    record->nis_profile[2] = estimator_profile->nis_2d_soft;
    record->nis_profile[3] = estimator_profile->nis_2d_hard;
    record->nis_profile[4] = estimator_profile->nis_3d_soft;
    record->nis_profile[5] = estimator_profile->nis_3d_hard;
    record->nis_profile[6] = estimator_profile->nis_max_r_scale;
}

static void LoggerBus_SystemConfigBuild(
    FlightLogSystemConfigRecord *record)
{
    const SystemEstimatorProfile *estimator_profile =
        SystemEstimatorProfile_Get();

    SILVERSTAR_ASSERT_OBJECT(record, FlightLogSystemConfigRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->version[0] = SILVERSTAR_VERSION_MAJOR;
    record->version[1] = SILVERSTAR_VERSION_MINOR;
    record->version[2] = SILVERSTAR_VERSION_PATCH;
    record->version[3] = SILVERSTAR_VERSION_BUILD;
    record->profile_id = SystemProfile_Get()->profile_id;
    record->device_config_digest = SystemDescriptor_ConfigDigestGet();
    record->configured_imu_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ;
    record->configured_gnss_rate_hz = SYSTEM_GNSS_NAVIGATION_RATE_HZ;
    record->configured_magnetometer_rate_hz =
        SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ;
    record->configured_barometer_rate_hz =
        SYSTEM_BAROMETER_OUTPUT_RATE_HZ;
    record->configured_hardware_quaternion_rate_hz =
        SYSTEM_HARDWARE_QUATERNION_OUTPUT_RATE_HZ;
    record->mechanization_subsample_count =
        SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT;
    record->expected_ins_rate_hz = (uint16_t)(SYSTEM_IMU_OUTPUT_RATE_HZ /
        SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT);
    record->mechanization_min_sample_rate_hz =
        SYSTEM_MECHANIZATION_SAMPLE_RATE_MIN_HZ;
    record->mechanization_max_sample_rate_hz =
        SYSTEM_MECHANIZATION_SAMPLE_RATE_MAX_HZ;
    record->log_profile_id = SYSTEM_LOG_PROFILE_ID;
    record->sync_period_us = (uint32_t)SYSTEM_LOG_SYNC_PERIOD_US;
    record->aggregation_buffer_size = SYSTEM_LOG_AGGREGATION_BUFFER_SIZE;
    record->normal_queue_depth = SYSTEM_LOG_RECORD_QUEUE_DEPTH;
    record->estimator_queue_depth = SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH;
    record->device_descriptor_count =
        SystemDescriptor_DeviceCountGet();
    record->algorithm_descriptor_count =
        SystemDescriptor_AlgorithmCountGet();
    record->log_stream_descriptor_count =
        SystemLogPolicy_StreamCountGet();
    LoggerBus_EstimatorConfigBuild(record, estimator_profile);
}

static LoggerBusResult LoggerBus_DeviceDescriptorBuild(
    uint16_t index, FlightLogDeviceDescriptorRecord *record)
{
    SystemDeviceDescriptor descriptor;
    if (SystemDescriptor_DeviceGet(index, &descriptor) != SYSTEM_DEVICE_OK)
    { return LOGGER_BUS_RESULT_BAD_STATE; }
    (void)memset(record, 0, sizeof(*record));
    record->descriptor_id = descriptor.descriptor_id;
    record->physical_device_id = descriptor.physical_device_id;
    record->device_class = (uint8_t)descriptor.device_class;
    record->instance_id = descriptor.instance_id;
    record->driver_id = descriptor.driver_id;
    record->flags = descriptor.flags;
    record->capability_mask = descriptor.capability_mask;
    record->configured_rate_hz = descriptor.configured_rate_hz;
    record->driver_name_hash = descriptor.driver_name_hash;
    record->model_name_hash = descriptor.model_name_hash;
    return LOGGER_BUS_RESULT_OK;
}

static LoggerBusResult LoggerBus_AlgorithmDescriptorBuild(
    uint16_t index, FlightLogAlgorithmDescriptorRecord *record)
{
    SystemAlgorithmDescriptor descriptor;
    if (SystemDescriptor_AlgorithmGet(index, &descriptor) != SYSTEM_DEVICE_OK)
    { return LOGGER_BUS_RESULT_BAD_STATE; }
    (void)memset(record, 0, sizeof(*record));
    record->descriptor_id = descriptor.descriptor_id;
    record->algorithm_class = (uint8_t)descriptor.algorithm_class;
    record->instance_id = descriptor.instance_id;
    record->algorithm_id = descriptor.algorithm_id;
    record->flags = descriptor.flags;
    record->config_digest = descriptor.config_digest;
    record->name_hash = descriptor.name_hash;
    return LOGGER_BUS_RESULT_OK;
}

static void LoggerBus_MissionConfigBuild(FlightLogMissionConfigRecord *record)
{
    (void)memset(record, 0, sizeof(*record));
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogMissionConfigRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    record->alignment_algorithm = (uint8_t)SYSTEM_ALIGNMENT_ALGORITHM;
    record->rocket_longitudinal_axis =
        (uint8_t)SYSTEM_FLIGHT_ROCKET_LONGITUDINAL_AXIS;
    record->deploy_trigger_mask =
        (uint8_t)SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK;
    record->tilt_reference = (uint8_t)SYSTEM_FLIGHT_TILT_REFERENCE;
    record->landing_enable = SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE;
    record->landing_mode = (uint8_t)SYSTEM_FLIGHT_LANDING_MODE;
    record->impact_capable = SYSTEM_IMU_CAP_LANDING_IMPACT_DETECTION;
    record->known_yaw_deg = SYSTEM_ALIGNMENT_KNOWN_YAW_DEG;
    record->magnetic_declination_deg =
        SYSTEM_ALIGNMENT_MAGNETIC_DECLINATION_DEG;
    record->tilt_threshold_deg = SYSTEM_FLIGHT_TILT_THRESHOLD_DEG;
    record->apogee_vz_threshold_mps =
        SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS;
    record->deploy_confirm_ms = SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS;
    record->deploy_delay_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS;
    record->baro_trigger_window_ms =
        SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_WINDOW_MS;
    record->baro_trigger_min_samples =
        SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_MIN_SAMPLES;
    record->baro_trigger_rate_mps =
        SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_RATE_MPS;
    record->candidate_duration_ms =
        SYSTEM_FLIGHT_LANDING_CANDIDATE_DURATION_MS;
    record->baro_confirm_rate_mps =
        SYSTEM_FLIGHT_LANDING_BARO_CONFIRM_RATE_MPS;
    record->baro_max_span_m = SYSTEM_FLIGHT_LANDING_BARO_MAX_SPAN_M;
    record->candidate_baro_min_samples =
        SYSTEM_FLIGHT_LANDING_BARO_MIN_SAMPLES;
    record->candidate_imu_min_samples =
        SYSTEM_FLIGHT_LANDING_IMU_MIN_SAMPLES;
    record->candidate_min_coverage_percent =
        SYSTEM_FLIGHT_LANDING_MIN_COVERAGE_PERCENT;
    record->impact_inhibit_ms =
        SYSTEM_FLIGHT_LANDING_IMPACT_INHIBIT_MS;
    record->impact_threshold_mps2 =
        SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2;
    record->still_gyro_threshold_radps =
        SYSTEM_FLIGHT_LANDING_STILL_GYRO_THRESHOLD_RADPS;
    record->still_accel_tolerance_mps2 =
        SYSTEM_FLIGHT_LANDING_STILL_ACCEL_TOLERANCE_MPS2;
    record->landing_confirm_ms = SYSTEM_FLIGHT_LANDING_CONFIRM_MS;
    record->landing_sample_max_age_ms =
        SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS;
}

static LoggerBusResult LoggerBus_RequestClaim(void)
{
    LoggerBusResult result = LOGGER_BUS_RESULT_OK;
    PlatformCriticalState state = LoggerBus_IrqLock();
    SILVERSTAR_ASSERT(s_request.phase <= LOGGER_REQUEST_FAULT,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if ((s_initialized == 0U) || (s_accepting_records == 0U) || (s_request.io_fault != 0U))
    { result = LOGGER_BUS_RESULT_BAD_STATE; }
    else if (s_request.phase != LOGGER_REQUEST_IDLE)
    { s_diagnostics.capacity_reject_count++; result = LOGGER_BUS_RESULT_BUSY; }
    else { s_request.phase = LOGGER_REQUEST_BUILDING; }
    /* A busy request is retryable admission, not lost wire records. */
    LoggerBus_IrqUnlock(state);
    return result;
}

static LoggerBusResult LoggerBus_RequestPublish(uint8_t is_start)
{
    LoggerBusResult result = LOGGER_BUS_RESULT_OK;
    PlatformCriticalState state = LoggerBus_IrqLock();
    SILVERSTAR_ASSERT(s_request.phase == LOGGER_REQUEST_BUILDING,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_accepting_records == 0U) || (s_boot_disabled != 0U) || (s_request.io_fault != 0U))
    { result = LOGGER_BUS_RESULT_BAD_STATE; }
    if (result == LOGGER_BUS_RESULT_OK)
    {
        s_request.is_start = is_start;
        s_request.cursor = 0U;
        s_request.count = (uint16_t)(1U + s_request.config.device_descriptor_count +
            s_request.config.algorithm_descriptor_count + SSLOG_RECORD_COUNT);
        if (is_start != 0U)
        { s_request.count = (uint16_t)(s_request.count + 4U + s_request.start.mag_count); }
        s_diagnostics.accepted_count += s_request.count;
        s_request.phase = LOGGER_REQUEST_READY;
    }
    else { s_request.phase = LOGGER_REQUEST_IDLE; }
    LoggerBus_IrqUnlock(state);
    return result;
}

static LoggerBusResult LoggerBus_RequestBuild(uint64_t timestamp_us)
{
    LoggerBus_SystemConfigBuild(&s_request.config);
    s_request.timestamp_us = timestamp_us;
    if ((s_request.config.device_descriptor_count > SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX) ||
        (s_request.config.algorithm_descriptor_count > SYSTEM_DESCRIPTOR_ALGORITHM_COUNT_MAX) ||
        (s_request.config.log_stream_descriptor_count != SSLOG_RECORD_COUNT) ||
        (SystemLogPolicy_SnapshotCopy(s_request.streams, SSLOG_RECORD_COUNT) != SYSTEM_DEVICE_OK))
    { return LOGGER_BUS_RESULT_BAD_STATE; }
    return LOGGER_BUS_RESULT_OK;
}

static void LoggerBus_RequestCancel(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();
    SILVERSTAR_ASSERT(s_request.phase == LOGGER_REQUEST_BUILDING,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    s_request.phase = LOGGER_REQUEST_IDLE;
    LoggerBus_IrqUnlock(state);
}

LoggerBusResult LoggerBus_SystemConfigPush(uint64_t timestamp_us)
{
    LoggerBusResult result;
    if (LoggerBus_PushStateGet() != LOGGER_BUS_RESULT_OK)
    { return LOGGER_BUS_RESULT_BAD_STATE; }
    if (LoggerBus_DisabledSuppress() != 0U) { return LOGGER_BUS_RESULT_OK; }
    /* Mandatory metadata is independent of periodic queue capacity/cadence. */
    result = LoggerBus_RequestClaim();
    if (result != LOGGER_BUS_RESULT_OK) { return result; }
    result = LoggerBus_RequestBuild(timestamp_us);
    if (result != LOGGER_BUS_RESULT_OK) { LoggerBus_RequestCancel(); return result; }
    return LoggerBus_RequestPublish(0U);
}

LoggerBusResult LoggerBus_StartRecordsPush(uint64_t timestamp_us,
    const LoggerBusStartRecords *records, uint32_t *generation)
{
    LoggerBusResult result;
    uint32_t assigned_generation;
    if ((records == NULL) || (generation == NULL))
    { return LOGGER_BUS_RESULT_BAD_PARAM; }
    if (LoggerBus_PushStateGet() != LOGGER_BUS_RESULT_OK)
    { return LOGGER_BUS_RESULT_BAD_STATE; }
    if (LoggerBus_DisabledSuppress() != 0U) { *generation = 0U; return LOGGER_BUS_RESULT_OK; }
    if (*generation != 0U)
    {
        PlatformCriticalState state = LoggerBus_IrqLock();
        uint8_t known = (uint8_t)((*generation == s_request.acknowledged_generation) ||
            ((s_request.is_start != 0U) && (*generation == s_request.generation) &&
             ((s_request.phase == LOGGER_REQUEST_READY) ||
              (s_request.phase == LOGGER_REQUEST_BARRIER) ||
              (s_request.phase == LOGGER_REQUEST_FAULT))));
        LoggerBus_IrqUnlock(state);
        return (known != 0U) ? LOGGER_BUS_RESULT_OK : LOGGER_BUS_RESULT_BAD_STATE;
    }
    if ((records->mag_count > PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX) ||
        (records->identity.ready != 1U) || (records->identity.mission_id == 0U) ||
        (records->identity.commit_generation == 0U))
    { return LOGGER_BUS_RESULT_BAD_PARAM; }
    result = LoggerBus_RequestClaim();
    if (result != LOGGER_BUS_RESULT_OK) { return result; }
    if (s_request.next_generation == UINT32_MAX)
    { LoggerBus_RequestCancel(); return LOGGER_BUS_RESULT_BAD_STATE; }
    s_request.start = *records;
    result = LoggerBus_RequestBuild(timestamp_us);
    if (result != LOGGER_BUS_RESULT_OK) { LoggerBus_RequestCancel(); return result; }
    assigned_generation = ++s_request.next_generation;
    s_request.generation = assigned_generation;
    result = LoggerBus_RequestPublish(1U);
    if (result == LOGGER_BUS_RESULT_OK) { *generation = assigned_generation; }
    return result;
}

static LoggerBusResult LoggerBus_StreamDescriptorBuild(
    uint16_t index, FlightLogStreamDescriptorRecord *record)
{
    const SystemLogStreamConfig *config;
    const SslogRecordMetadata *metadata;
    SILVERSTAR_ASSERT(index < SSLOG_RECORD_COUNT,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    config = &s_request.streams[index];
    metadata = SslogRecords_MetadataGet(config->record_type);
    SILVERSTAR_ASSERT((metadata != NULL) && (config->decimation > 0U) &&
        (config->enabled <= 1U) && (config->policy <= SSLOG_STREAM_POLICY_ONE_SHOT),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    record->record_type = (uint8_t)config->record_type;
    record->record_version = metadata->record_version;
    record->enabled = config->enabled;
    record->policy = (uint8_t)config->policy;
    record->decimation = config->decimation;
    record->period_us = config->period_us;
    return LOGGER_BUS_RESULT_OK;
}

static void LoggerBus_StartRecordBuild(uint16_t index, FlightLogRecord *record)
{
    SILVERSTAR_ASSERT(index < (uint16_t)(4U + s_request.start.mag_count),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (index == 0U)
    { record->record_type = FLIGHT_LOG_RECORD_MISSION_CONFIG;
      LoggerBus_MissionConfigBuild(&record->payload.mission_config); }
    else if (index == 1U)
    { record->record_type = FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY;
      record->payload.mission_snapshot_identity = s_request.start.identity; }
    else if (index < (uint16_t)(2U + s_request.start.mag_count))
    { record->record_type = FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY;
      record->payload.mag_calibration_identity = s_request.start.mag[index - 2U]; }
    else if (index == (uint16_t)(2U + s_request.start.mag_count))
    { record->record_type = FLIGHT_LOG_RECORD_INITIAL_STATE;
      record->payload.initial_state = s_request.start.initial; }
    else
    { record->record_type = FLIGHT_LOG_RECORD_EVENT;
      record->payload.event.event_id = FLIGHT_LOG_EVENT_MISSION_START; }
}

static LoggerBusResult LoggerBus_RequestRecordBuild(FlightLogRecord *record)
{
    uint16_t index = s_request.cursor;
    uint16_t devices = s_request.config.device_descriptor_count;
    uint16_t algorithms = s_request.config.algorithm_descriptor_count;
    SILVERSTAR_ASSERT((devices <= SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX) &&
        (algorithms <= SYSTEM_DESCRIPTOR_ALGORITHM_COUNT_MAX) &&
        (s_request.start.mag_count <= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX ||
         s_request.is_start == 0U),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT((s_request.is_start <= 1U) &&
        (s_request.count == (uint16_t)(1U + devices + algorithms + SSLOG_RECORD_COUNT +
            ((s_request.is_start != 0U) ? (4U + s_request.start.mag_count) : 0U))),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    (void)memset(record, 0, sizeof(*record));
    record->timestamp_us = s_request.timestamp_us;
    SILVERSTAR_ASSERT(index < s_request.count,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (index == 0U)
    { record->record_type = FLIGHT_LOG_RECORD_SYSTEM_CONFIG;
      record->payload.system_config = s_request.config; return LOGGER_BUS_RESULT_OK; }
    index--;
    if (index < devices)
    { record->record_type = FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR;
      return LoggerBus_DeviceDescriptorBuild(index, &record->payload.device_descriptor); }
    index = (uint16_t)(index - devices);
    if (index < algorithms)
    { record->record_type = FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR;
      return LoggerBus_AlgorithmDescriptorBuild(index, &record->payload.algorithm_descriptor); }
    index = (uint16_t)(index - algorithms);
    if (index < SSLOG_RECORD_COUNT)
    { record->record_type = FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR;
      return LoggerBus_StreamDescriptorBuild(index, &record->payload.stream_descriptor); }
    LoggerBus_StartRecordBuild((uint16_t)(index - SSLOG_RECORD_COUNT), record);
    return LOGGER_BUS_RESULT_OK;
}

static LoggerBusResult LoggerBus_RequestPop(FlightLogRecord *record)
{
    LoggerBusResult result;
    PlatformCriticalState state = LoggerBus_IrqLock();
    SILVERSTAR_ASSERT(s_request.phase <= LOGGER_REQUEST_FAULT,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    uint8_t ready = (uint8_t)(s_request.phase == LOGGER_REQUEST_READY);
    LoggerBus_IrqUnlock(state);
    if (ready == 0U) { return LOGGER_BUS_RESULT_EMPTY; }
    /* Only the logger consumer calls pop; immutable construction needs no lock. */
    result = LoggerBus_RequestRecordBuild(record);
    /* Generated immutable descriptor tables must satisfy their declared counts.
     * A violation is internal corruption, not ordinary external storage input. */
    SILVERSTAR_ASSERT(result == LOGGER_BUS_RESULT_OK,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    state = LoggerBus_IrqLock();
    if (result == LOGGER_BUS_RESULT_OK)
    {
        s_request.cursor++;
        s_diagnostics.dequeued_count++;
        if (s_request.cursor == s_request.count)
        { s_request.phase = (s_request.is_start != 0U) ?
            LOGGER_REQUEST_BARRIER : LOGGER_REQUEST_IDLE; }
    }
    else { s_request.phase = LOGGER_REQUEST_FAULT; }
    LoggerBus_IrqUnlock(state);
    return result;
}

uint32_t LoggerBus_StartBarrierGet(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();
    uint32_t generation = (s_request.phase == LOGGER_REQUEST_BARRIER) ? s_request.generation : 0U;
    LoggerBus_IrqUnlock(state);
    return generation;
}

LoggerBusResult LoggerBus_StartDurable(uint32_t generation)
{
    LoggerBusResult result = LOGGER_BUS_RESULT_BAD_STATE;
    PlatformCriticalState state = LoggerBus_IrqLock();
    if ((s_request.phase == LOGGER_REQUEST_BARRIER) &&
        (generation != 0U) && (generation == s_request.generation))
    { s_request.acknowledged_generation = generation; s_request.phase = LOGGER_REQUEST_IDLE;
      result = LOGGER_BUS_RESULT_OK; }
    LoggerBus_IrqUnlock(state);
    return result;
}

uint32_t LoggerBus_StartAcknowledgedGet(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();
    uint32_t generation = s_request.acknowledged_generation;
    LoggerBus_IrqUnlock(state);
    return generation;
}

void LoggerBus_StartFault(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();
    s_request.io_fault = 1U;
    if (((s_request.phase == LOGGER_REQUEST_READY) ||
         (s_request.phase == LOGGER_REQUEST_BARRIER)) && (s_request.is_start != 0U))
    { s_request.phase = LOGGER_REQUEST_FAULT; }
    LoggerBus_IrqUnlock(state);
}

LoggerBusResult LoggerBus_MissionConfigPush(uint64_t timestamp_us)
{
    FlightLogMissionConfigRecord record;
    LoggerBus_MissionConfigBuild(&record);
    return LoggerBus_ConfiguredRecordPush(FLIGHT_LOG_RECORD_MISSION_CONFIG,
        timestamp_us, 0U, &record, sizeof(record), 0U);
}

static void LoggerBus_DecoderProfileRecordBuild(
    const ProjectLogDecoderProfile *profile,
    FlightLogDecoderProfileDescriptorRecord *record)
{
    SILVERSTAR_ASSERT_OBJECT(profile, ProjectLogDecoderProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogDecoderProfileDescriptorRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->package_schema_major = profile->package_schema_major;
    record->package_schema_minor = profile->package_schema_minor;
    record->container_format_major = profile->container_format_major;
    record->container_format_minor = profile->container_format_minor;
    (void)memcpy(record->record_catalog_hash_128,
        profile->record_catalog_hash_128,
        sizeof(record->record_catalog_hash_128));
    (void)memcpy(record->project_semantics_hash_128,
        profile->project_semantics_hash_128,
        sizeof(record->project_semantics_hash_128));
    (void)memcpy(record->generation_profile_hash_128,
        profile->generation_profile_hash_128,
        sizeof(record->generation_profile_hash_128));
}

LoggerBusResult LoggerBus_DecoderProfileDescriptorPush(uint64_t timestamp_us)
{
    ProjectLogDecoderProfile profile;
    FlightLogDecoderProfileDescriptorRecord record;

    ProjectLogDecoderProfile_Get(&profile);
    LoggerBus_DecoderProfileRecordBuild(&profile, &record);
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR,
        timestamp_us, 0U, &record, sizeof(record), 0U);
}

LoggerBusResult LoggerBus_PureInsPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogPureInsRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_PURE_INS, timestamp_us, valid_flags,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_Kf6DiagnosticPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogKf6DiagnosticRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC, timestamp_us, valid_flags,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_NavigationQualityPush(
    uint64_t timestamp_us, const FlightLogNavigationQualityRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_NAV_QUALITY, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_Eskf15BodyInputPush(
    uint64_t timestamp_us, const FlightLogEskf15BodyInputRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_Sf6StatePush(
    uint64_t timestamp_us, const FlightLogSf6StateRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_SF6_STATE, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_Sf6MeasurementPush(
    uint64_t timestamp_us, const FlightLogSf6MeasurementRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_SF6_MEASUREMENT, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_Eskf15StatePush(
    uint64_t timestamp_us, const FlightLogEskf15StateRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ESKF15_STATE, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_Eskf15CovariancePush(
    uint64_t timestamp_us, const FlightLogEskf15CovariancePartRecord *identity,
    const float *covariance_row_major)
{
    FlightLogEskf15CovariancePartRecord part;
    FlightLogRecordType type;
    LoggerBusResult first_failure = LOGGER_BUS_RESULT_OK;
    uint16_t row = 0U;
    uint16_t column = 0U;
    uint8_t part_index;
    if ((identity == NULL) || (covariance_row_major == NULL) ||
        (identity->algorithm_id != 2U) || (identity->phase > 1U))
    { return LOGGER_BUS_RESULT_BAD_PARAM; }
    SILVERSTAR_ASSERT_OBJECT(identity, FlightLogEskf15CovariancePartRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(covariance_row_major, float, SILVERSTAR_ASSERT_MODULE_APP);
    type = (identity->phase == 0U) ? FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART :
        FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART;
    if (LoggerBus_PushStateGet() != LOGGER_BUS_RESULT_OK)
    { return LOGGER_BUS_RESULT_BAD_STATE; }
    if (LoggerBus_DisabledSuppress() != 0U) { return LOGGER_BUS_RESULT_OK; }
    /* Cadence belongs to a whole covariance snapshot. Evaluating it for each
     * fragment silently suppresses fragments 1..3 after fragment 0 succeeds. */
    if (SystemLogPolicy_ShouldEmitAt(type, timestamp_us) == 0U)
    { return LOGGER_BUS_RESULT_OK; }
    if (LoggerBus_BootstrapSuppress(type) != 0U)
    { return LOGGER_BUS_RESULT_OK; }
    part = *identity;
    part.part_count = 4U;
    part.count = 30U;
    for (part_index = 0U; part_index < 4U; ++part_index)
    {
        uint16_t index;
        LoggerBusResult result;
        part.part_index = part_index;
        part.offset = (uint16_t)((uint16_t)part_index * 30U);
        for (index = 0U; index < 30U; ++index)
        {
            SILVERSTAR_ASSERT((row < 15U) && (column < 15U) && (column >= row),
                SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
            part.values[index] = covariance_row_major[(size_t)row * 15U + column];
            column++;
            if (column == 15U) { row++; column = row; }
        }
        /* Never stop on the first full queue: every attempted fragment retains
         * normal sequence-gap, overflow and capacity-rejection accounting. */
        /* Initial snapshots retain replay-input ordering. Periodic covariance
         * is a diagnostic alongside the normal state summaries. */
        result = LoggerBus_RecordPush(type, timestamp_us, 0U, &part, sizeof(part),
            (uint8_t)(identity->phase == 0U));
        if ((result != LOGGER_BUS_RESULT_OK) && (first_failure == LOGGER_BUS_RESULT_OK))
        { first_failure = result; }
    }
    if (first_failure == LOGGER_BUS_RESULT_OK)
    { SystemLogPolicy_EmissionTimeRecord(type, timestamp_us); }
    return first_failure;
}

LoggerBusResult LoggerBus_Eskf15InitialStatePush(
    uint64_t timestamp_us, const FlightLogEskf15StateRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_Eskf15MeasurementPush(
    uint64_t timestamp_us, const FlightLogEskf15MeasurementRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_Kf6FullPPush(
    uint64_t timestamp_us, const FlightLogKf6FullPRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_KF6_FULL_P, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_PowerPush(
    uint64_t timestamp_us, const FlightLogPowerRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_POWER, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_HealthPush(
    uint64_t timestamp_us, const FlightLogHealthRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_HEALTH, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_TelemetryDiagnosticPush(
    uint64_t timestamp_us,
    const FlightLogTelemetryDiagnosticRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_TELEMETRY_DIAG, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_InitialStatePush(
    uint64_t timestamp_us, const FlightLogInitialStateRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_INITIAL_STATE, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_GnssNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogGnssNativeRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_GNSS_NATIVE, timestamp_us, valid_flags,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_BaroNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogBaroNativeRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_BARO_NATIVE, timestamp_us, valid_flags,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_MagNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogMagNativeRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_MAG_NATIVE, timestamp_us, valid_flags,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_InertialIncrementPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogInertialIncrementRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_INERTIAL_INCREMENT, timestamp_us, valid_flags,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_GnssMeasurementPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogGnssMeasurementRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_GNSS_MEASUREMENT, timestamp_us, valid_flags,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_BaroMeasurementPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogBaroMeasurementRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_BARO_MEASUREMENT, timestamp_us, valid_flags,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_ImuCorrectedPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogImuCorrectedRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_IMU_CORRECTED, timestamp_us, valid_flags,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_CalibrationResultPush(
    uint64_t timestamp_us,
    const FlightLogCalibrationResultRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_CALIBRATION_RESULT, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_AlignmentResultPush(
    uint64_t timestamp_us,
    const FlightLogAlignmentResultRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ALIGNMENT_RESULT, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_AlignmentEvidencePush(
    uint64_t timestamp_us,
    const FlightLogAlignmentEvidenceRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_MissionSnapshotIdentityPush(
    uint64_t timestamp_us,
    const FlightLogMissionSnapshotIdentityRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_MagCalibrationIdentityPush(
    uint64_t timestamp_us,
    const FlightLogMagCalibrationIdentityRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}

LoggerBusResult LoggerBus_FinalizationArm(uint64_t landing_timestamp_us)
{
    const uint64_t grace_us =
        (uint64_t)SYSTEM_LOG_POST_LANDING_GRACE_MS * 1000ULL;
    PlatformCriticalState state = LoggerBus_IrqLock();

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_finalization_state <=
                      LOGGER_BUS_FINALIZATION_FINALIZED,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (s_initialized == 0U)
    {
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_BAD_STATE;
    }
    if (s_finalization_state == LOGGER_BUS_FINALIZATION_IDLE)
    {
        s_finalization_deadline_us =
            (landing_timestamp_us > (UINT64_MAX - grace_us)) ? UINT64_MAX :
            (landing_timestamp_us + grace_us);
        s_finalization_state = LOGGER_BUS_FINALIZATION_ARMED;
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_OK;
    }
    if (s_finalization_state == LOGGER_BUS_FINALIZATION_ARMED)
    {
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_OK;
    }
    LoggerBus_IrqUnlock(state);
    return LOGGER_BUS_RESULT_BAD_STATE;
}

LoggerBusFinalizationState LoggerBus_FinalizationProcess(uint64_t now_us)
{
    LoggerBusFinalizationState finalization_state;
    PlatformCriticalState state = LoggerBus_IrqLock();

    if ((s_finalization_state == LOGGER_BUS_FINALIZATION_ARMED) &&
        (now_us >= s_finalization_deadline_us))
    {
        s_accepting_records = 0U;
        s_finalization_state = LOGGER_BUS_FINALIZATION_DRAINING;
    }
    finalization_state = s_finalization_state;
    LoggerBus_IrqUnlock(state);
    return finalization_state;
}

void LoggerBus_FinalizationComplete(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();

    if (s_finalization_state == LOGGER_BUS_FINALIZATION_DRAINING)
    {
        s_finalization_state = LOGGER_BUS_FINALIZATION_FINALIZED;
    }
    LoggerBus_IrqUnlock(state);
}

LoggerBusFinalizationState LoggerBus_FinalizationStateGet(void)
{
    LoggerBusFinalizationState finalization_state;
    PlatformCriticalState state = LoggerBus_IrqLock();

    finalization_state = s_finalization_state;
    LoggerBus_IrqUnlock(state);
    return finalization_state;
}

static LoggerBusResult LoggerBus_QueuePop(
    CommonSpscQueue *queue, FlightLogRecord *record)
{
    CommonSpscQueueResult result;
    PlatformCriticalState state;

    if ((queue == NULL) || (record == NULL))
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    state = LoggerBus_IrqLock();
    if (s_initialized == 0U)
    {
        LoggerBus_IrqUnlock(state);
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    LoggerBus_QueueGeometryValidate(queue);
    (void)memset(record, 0, sizeof(*record));
    result = CommonSpscQueue_Pop(queue, record);
    if (result == COMMON_SPSC_QUEUE_RESULT_OK)
    {
        size_t payload_size = LoggerBus_PayloadSizeGet(record->record_type);
        SILVERSTAR_ASSERT(payload_size != 0U &&
            (offsetof(FlightLogRecord, payload) + payload_size <= queue->item_size),
            SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
        SILVERSTAR_ASSERT(LoggerBus_EstimatorLaneGet(record->record_type) ==
            (uint8_t)(queue == &s_estimator_logger_queue),
            SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    }
    if (result == COMMON_SPSC_QUEUE_RESULT_OK) { s_diagnostics.dequeued_count++; }
    LoggerBus_IrqUnlock(state);
    if (result == COMMON_SPSC_QUEUE_RESULT_OK)
    {
        return LOGGER_BUS_RESULT_OK;
    }
    return (result == COMMON_SPSC_QUEUE_RESULT_EMPTY) ?
        LOGGER_BUS_RESULT_EMPTY : LOGGER_BUS_RESULT_BAD_PARAM;
}

LoggerBusResult LoggerBus_Pop(FlightLogRecord *record)
{
    LoggerBusResult result;
    if (record == NULL) { return LOGGER_BUS_RESULT_BAD_PARAM; }
    result = LoggerBus_RequestPop(record);
    if (result != LOGGER_BUS_RESULT_EMPTY) { return result; }
    return LoggerBus_QueuePop(&s_logger_queue, record);
}

LoggerBusResult LoggerBus_EstimatorPop(FlightLogRecord *record)
{
    return LoggerBus_QueuePop(&s_estimator_logger_queue, record);
}

static uint8_t LoggerBus_QueuePreferenceGet(void)
{
    PlatformCriticalState state = LoggerBus_IrqLock();
    uint32_t normal = CommonSpscQueue_Count(&s_logger_queue);
    uint32_t estimator = CommonSpscQueue_Count(&s_estimator_logger_queue);
    uint8_t preferred = s_next_estimator_queue;
    LoggerBus_IrqUnlock(state);
    if (normal == 0U) { return 1U; }
    if (estimator == 0U) { return 0U; }
    normal *= LOGGER_ESTIMATOR_RECORD_QUEUE_DEPTH;
    estimator *= LOGGER_RECORD_QUEUE_DEPTH;
    if (normal != estimator) { preferred = (uint8_t)(estimator > normal); }
    /* Normalize pressure by the existing queue capacities. A busy producer
     * can never deny the other nonempty queue more than three successful pops. */
    if ((s_queue_drain_run >= 3U) &&
        (preferred == (uint8_t)(s_next_estimator_queue == 0U)))
    { preferred = (uint8_t)(preferred == 0U); }
    return preferred;
}

LoggerBusResult LoggerBus_NextPop(FlightLogRecord *record)
{
    LoggerBusResult result;
    uint8_t preferred;
    if (record == NULL) { return LOGGER_BUS_RESULT_BAD_PARAM; }
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    result = LoggerBus_RequestPop(record);
    if (result != LOGGER_BUS_RESULT_EMPTY) { return result; }
    preferred = LoggerBus_QueuePreferenceGet();
    if (preferred != 0U)
    {
        result = LoggerBus_EstimatorPop(record);
        if (result == LOGGER_BUS_RESULT_EMPTY)
        {
            preferred = 0U;
            result = LoggerBus_Pop(record);
        }
    }
    else
    {
        result = LoggerBus_Pop(record);
        if (result == LOGGER_BUS_RESULT_EMPTY)
        {
            preferred = 1U;
            result = LoggerBus_EstimatorPop(record);
        }
    }
    if (result == LOGGER_BUS_RESULT_OK)
    {
        if ((preferred == (uint8_t)(s_next_estimator_queue == 0U)) &&
            (s_queue_drain_run < 3U)) { s_queue_drain_run++; }
        else { s_queue_drain_run = 1U; }
        s_next_estimator_queue = (uint8_t)(preferred == 0U);
    }
    return result;
}

uint16_t LoggerBus_Count(void)
{
    uint16_t count;
    PlatformCriticalState state = LoggerBus_IrqLock();

    count = (uint16_t)(CommonSpscQueue_Count(&s_logger_queue) +
                       CommonSpscQueue_Count(&s_estimator_logger_queue));
    if (s_request.phase == LOGGER_REQUEST_READY)
    { count = (uint16_t)(count + s_request.count - s_request.cursor); }
    else if (s_request.phase != LOGGER_REQUEST_IDLE) { count++; }
    LoggerBus_IrqUnlock(state);
    return count;
}

uint32_t LoggerBus_OverflowCountGet(void)
{
    uint32_t count;
    PlatformCriticalState state = LoggerBus_IrqLock();

    count = s_logger_queue.overflow_count +
            s_estimator_logger_queue.overflow_count;
    LoggerBus_IrqUnlock(state);
    return count;
}

LoggerBusResult LoggerBus_DiagnosticsGet(LoggerBusDiagnostics *diagnostics)
{
    PlatformCriticalState state;
    if (diagnostics == NULL) { return LOGGER_BUS_RESULT_BAD_PARAM; }
    state = LoggerBus_IrqLock();
    *diagnostics = s_diagnostics;
    diagnostics->normal_count = CommonSpscQueue_Count(&s_logger_queue);
    diagnostics->estimator_count = CommonSpscQueue_Count(&s_estimator_logger_queue);
    diagnostics->overflow_count = s_logger_queue.overflow_count +
        s_estimator_logger_queue.overflow_count;
    LoggerBus_IrqUnlock(state);
    return LOGGER_BUS_RESULT_OK;
}

LoggerBusResult LoggerBus_EstimatorStepPush(
    uint64_t timestamp_us, const FlightLogEstimatorStepRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_ESTIMATOR_STEP, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_NavigationSnapshotPush(uint64_t timestamp_us,
    const FlightLogEstimatorRecord *state, const FlightLogKf6FullPRecord *covariance)
{
    LoggerBusResult state_result = LOGGER_BUS_RESULT_OK;
    LoggerBusResult covariance_result = LOGGER_BUS_RESULT_OK;
    if ((state == NULL) || (covariance == NULL)) { return LOGGER_BUS_RESULT_BAD_PARAM; }
    if (LoggerBus_PushStateGet() != LOGGER_BUS_RESULT_OK) { return LOGGER_BUS_RESULT_BAD_STATE; }
    if (LoggerBus_DisabledSuppress() != 0U) { return LOGGER_BUS_RESULT_OK; }
    /* Critical snapshots bypass cadence/bootstrap suppression; queue failures
     * retain normal sequence gaps and overflow accounting. */
    if (SystemLogPolicy_IsEnabled(FLIGHT_LOG_RECORD_ESTIMATOR) != 0U)
    {
        state_result = LoggerBus_RecordPush(FLIGHT_LOG_RECORD_ESTIMATOR,
            timestamp_us, 0U, state, sizeof(*state), 1U);
    }
    if (SystemLogPolicy_IsEnabled(FLIGHT_LOG_RECORD_KF6_FULL_P) != 0U)
    {
        covariance_result = LoggerBus_RecordPush(FLIGHT_LOG_RECORD_KF6_FULL_P,
            timestamp_us, 0U, covariance, sizeof(*covariance), 1U);
    }
    return (state_result != LOGGER_BUS_RESULT_OK) ? state_result : covariance_result;
}

LoggerBusResult LoggerBus_GnssRecoveryPush(
    uint64_t timestamp_us, const FlightLogGnssRecoveryRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_GNSS_RECOVERY, timestamp_us, 0U,
        record, sizeof(*record), 1U);
}

LoggerBusResult LoggerBus_LandingDiagnosticPush(
    uint64_t timestamp_us, const FlightLogLandingDiagnosticRecord *record)
{
    return LoggerBus_ConfiguredRecordPush(
        FLIGHT_LOG_RECORD_LANDING_DIAGNOSTIC, timestamp_us, 0U,
        record, sizeof(*record), 0U);
}
