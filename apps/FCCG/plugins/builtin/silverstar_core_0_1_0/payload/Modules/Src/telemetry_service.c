#include "telemetry_service.h"

#include "system_user_config.h"

#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "air_protocol.h"
#include "estimator_task.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "silverstar_assert.h"
#include "platform_memory.h"
#include "system_alignment.h"
#include "system_calibration.h"
#include "system_gnss_if.h"
#include "system_imu_if.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_inertial.h"
#include "system_lifecycle.h"
#include "system_navigation_health.h"
#include "system_sensor_status.h"
#include "system_startup.h"
#include "system_time.h"
#include "system_telemetry_transport_if.h"

#define TELEMETRY_STATUS_QUEUE_DEPTH SYSTEM_TELEMETRY_STATUS_QUEUE_DEPTH
#define TELEMETRY_ACK_QUEUE_DEPTH SYSTEM_TELEMETRY_ACK_QUEUE_DEPTH
#define TELEMETRY_ACK_CACHE_DEPTH SYSTEM_TELEMETRY_ACK_CACHE_DEPTH
#define TELEMETRY_STATUS_REPEAT_COUNT SYSTEM_TELEMETRY_STATUS_REPEAT_COUNT
#define TELEMETRY_START_RESPONSE_MAX_PER_CYCLE \
    SYSTEM_LIFECYCLE_QUEUE_DEPTH
#define TELEMETRY_RX_MAX_FRAMES_PER_CYCLE 8U

_Static_assert(SYSTEM_TELEMETRY_COMMAND_POLICY ==
                   AIR_COMMAND_POLICY_PREFLIGHT_ONLY ||
               SYSTEM_TELEMETRY_COMMAND_POLICY ==
                   AIR_COMMAND_POLICY_MISSION_ALLOWED,
               "invalid telemetry command policy");
_Static_assert(SYSTEM_CALIBRATION_CAPABILITY_NONE ==
                   AIR_CALIBRATION_MODE_MASK_NONE &&
               SYSTEM_CALIBRATION_CAPABILITY_ONE_FACE ==
                   AIR_CALIBRATION_MODE_MASK_ONE_FACE &&
               SYSTEM_CALIBRATION_CAPABILITY_SIX_FACE ==
                   AIR_CALIBRATION_MODE_MASK_SIX_FACE,
               "Calibration capability bit mismatch");
_Static_assert((uint8_t)SYSTEM_STATE_FAULT ==
                   (uint8_t)AIR_LIFECYCLE_FAULT,
               "lifecycle enum does not fit AIR profile");
_Static_assert((uint8_t)SYSTEM_CALIBRATION_STATE_FAILED ==
                   (uint8_t)AIR_CALIBRATION_STATE_FAILED,
               "Calibration state enum does not fit AIR profile");
_Static_assert((uint8_t)SYSTEM_ALIGNMENT_STATE_STALE ==
                   (uint8_t)AIR_ALIGNMENT_STATE_STALE,
               "Alignment state enum does not fit AIR profile");
_Static_assert((uint8_t)SYSTEM_CALIBRATION_WAIT_NONE ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_NONE &&
               (uint8_t)SYSTEM_CALIBRATION_WAIT_NO_STREAM ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_NO_STREAM &&
               (uint8_t)SYSTEM_CALIBRATION_WAIT_GYRO_MOVING ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_GYRO_MOVING &&
               (uint8_t)SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_ACCEL_MAGNITUDE &&
               (uint8_t)SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_GRAVITY_DIRECTION &&
               (uint8_t)SYSTEM_CALIBRATION_WAIT_VARIANCE ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_VARIANCE &&
               (uint8_t)SYSTEM_CALIBRATION_WAIT_SAMPLE_GAP ==
                   (uint8_t)AIR_CALIBRATION_DIAGNOSTIC_SAMPLE_GAP,
               "Calibration diagnostic enum does not fit AIR profile");
_Static_assert((uint8_t)SYSTEM_CALIBRATION_FACE_X_POSITIVE ==
                   (uint8_t)AIR_CALIBRATION_FACE_X_POSITIVE &&
               (uint8_t)SYSTEM_CALIBRATION_FACE_Z_NEGATIVE ==
                   (uint8_t)AIR_CALIBRATION_FACE_Z_NEGATIVE &&
               (uint8_t)SYSTEM_CALIBRATION_FACE_NONE ==
                   (uint8_t)AIR_CALIBRATION_FACE_NOT_SELECTED,
               "Calibration face enum does not fit AIR profile");
_Static_assert(SYSTEM_SENSOR_STATUS_REGISTERED ==
                   AIR_SENSOR_STATUS_REGISTERED &&
               SYSTEM_SENSOR_STATUS_REQUIRED_FOR_START ==
                   AIR_SENSOR_STATUS_REQUIRED_FOR_START,
               "Sensor status flags do not fit AIR M0");
_Static_assert((uint8_t)SYSTEM_SENSOR_DETAIL_NONE ==
                   (uint8_t)AIR_SENSOR_DETAIL_NONE &&
               (uint8_t)SYSTEM_SENSOR_DETAIL_OTHER ==
                   (uint8_t)AIR_SENSOR_DETAIL_OTHER,
               "Sensor detail codes do not fit AIR M0");

typedef struct
{
    uint8_t status_id;
    uint8_t arg0;
    uint8_t arg1;
    uint8_t repeats_remaining;
    uint32_t event_time_ms;
    uint64_t next_send_us;
} TelemetryStatusEvent;

typedef struct
{
    uint8_t frame[AIR_ACK_LEN];
} TelemetryAckItem;

typedef struct
{
    uint8_t frame[AIR_ACK_LEN];
    AirCmdPayload command;
    uint64_t recorded_us;
    uint8_t valid;
} TelemetryAckCacheEntry;

static TelemetryStatusEvent s_status_queue[TELEMETRY_STATUS_QUEUE_DEPTH];
static uint8_t s_status_head;
static uint8_t s_status_tail;
static TelemetryAckItem s_ack_queue[TELEMETRY_ACK_QUEUE_DEPTH];
static uint8_t s_ack_head;
static uint8_t s_ack_tail;
static TelemetryAckCacheEntry s_ack_cache[TELEMETRY_ACK_CACHE_DEPTH];
static uint8_t s_ack_cache_next;
static uint8_t s_tx_sequence;
static uint8_t s_start_request_pending;
static uint8_t s_start_cmd_sequence;
static AirCmdPayload s_start_command;
static uint8_t s_capability_ack_known;
static uint8_t s_capability_ack_sequence;
static uint64_t s_capability_ack_us;
static uint8_t s_locked;
static uint8_t s_gnss_state_known;
static uint8_t s_gnss_position_usable;
static uint8_t s_selftest_event_sent;
static uint8_t s_alignment_status_known;
static uint8_t s_alignment_state;
static uint32_t s_sensor_snapshot_sequence;
static uint8_t s_sensor_snapshot_active;
static uint8_t s_sensor_snapshot_index;
static uint8_t s_sensor_snapshot_total;
static uint8_t s_sensor_snapshot_id;
static uint8_t s_sensor_snapshot_terminal_pending;
static uint8_t s_sensor_snapshot_terminal_state;
static uint8_t s_preflight_attitude_source_known;
static SystemAlignmentPreflightAttitudeSource
    s_preflight_attitude_source;
static uint32_t s_preflight_attitude_alignment_sequence;
static uint8_t s_calibration_status_known;
static uint8_t s_calibration_state;
static uint8_t s_calibration_mode;
static uint32_t s_calibration_face_event_sequence;
static uint32_t s_calibration_diagnostic_sequence;
static uint32_t s_deploy_event_sequence;
static uint32_t s_landing_event_sequence;
#define TELEMETRY_CAPABILITY_WINDOW_DEPTH 4U
#define TELEMETRY_CAPABILITY_WINDOW_MS 4000U
typedef struct
{
    uint64_t sent_us;
    uint8_t sequence;
} TelemetryCapabilityAdvertisement;
typedef struct
{
    TelemetryCapabilityAdvertisement advertised[TELEMETRY_CAPABILITY_WINDOW_DEPTH];
    uint64_t pending_since_us;
    uint64_t ack_advertised_us;
    uint32_t pending_id;
    uint8_t pending_sequence;
    uint8_t count;
    uint8_t next;
    uint8_t latest_sequence;
} TelemetryCapabilityTransaction;
/* CPU-only timestamps/sequence/token metadata. No radio payload or DMA pointer
 * is stored here; SendControl writes its token synchronously, before return.
 * The target supplies placement/alignment/zeroing; other targets use normal BSS. */
static TelemetryCapabilityTransaction s_capability_tx PLATFORM_CPU_FAST_BSS;
static uint8_t s_capability_sent;
static uint8_t s_capability_send_pending;
static uint8_t s_command_policy;
static uint8_t s_preflight_status_send_pending;
static uint8_t s_preflight_status_known;
static TelemetryCapabilityState s_capability_state;
static TelemetryServiceDiagnostics s_diagnostics;
static AirPreflightStatusPayload s_preflight_status_observed;
static uint64_t s_next_capability_us;
static uint64_t s_next_preflight_status_us;
static uint64_t s_next_preflight_state_us;
static uint64_t s_next_stream_us;

static uint8_t TelemetryService_QueueNext(uint8_t index)
{
    index++;
    return (index >= TELEMETRY_STATUS_QUEUE_DEPTH) ? 0U : index;
}

static uint8_t TelemetryService_AckQueueNext(uint8_t index)
{
    index++;
    return (index >= TELEMETRY_ACK_QUEUE_DEPTH) ? 0U : index;
}

static uint8_t TelemetryService_AckQueueHasSpace(void)
{
    return (uint8_t)(TelemetryService_AckQueueNext(s_ack_head) !=
                     s_ack_tail);
}

static uint8_t TelemetryService_AckCacheNext(uint8_t index)
{
    index++;
    return (index >= TELEMETRY_ACK_CACHE_DEPTH) ? 0U : index;
}

static uint8_t TelemetryService_IsPreflightState(void)
{
    SystemLifecycleState state = SystemLifecycle_GetState();

    return (uint8_t)(((state == SYSTEM_STATE_PREFLIGHT) ||
                      (state == SYSTEM_STATE_READY)) &&
                     (s_capability_state !=
                      TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT));
}

static uint8_t TelemetryService_CommandRxAllowed(void)
{
    SystemLifecycleState state = SystemLifecycle_GetState();

    if (TelemetryService_IsPreflightState() != 0U) { return 1U; }
    return (uint8_t)(
        (s_command_policy == AIR_COMMAND_POLICY_MISSION_ALLOWED) &&
        ((state == SYSTEM_STATE_FLIGHT) ||
         (state == SYSTEM_STATE_RECOVERY)));
}

static uint32_t TelemetryService_AirTimeMs(void)
{
    uint64_t time_us = (SystemTime_IsMissionStarted() != 0U) ?
        SystemTime_GetMissionUs() : SystemTime_GetMonotonicUs();

    return (uint32_t)(time_us / 1000ULL);
}

static int16_t TelemetryService_QuaternionToQ15(float value)
{
    if (value >= 1.0f) { return INT16_MAX; }
    if (value <= -1.0f) { return INT16_MIN; }
    return (int16_t)(value * 32768.0f);
}

static uint8_t TelemetryService_AckFrameQueue(const uint8_t *frame)
{
    uint8_t next_head;

    if (frame == NULL)
    {
        s_diagnostics.ack_queue_failure_count++;
        return 0U;
    }
    next_head = TelemetryService_AckQueueNext(s_ack_head);
    if (next_head == s_ack_tail)
    {
        s_diagnostics.ack_queue_failure_count++;
        return 0U;
    }
    (void)memcpy(s_ack_queue[s_ack_head].frame, frame, AIR_ACK_LEN);
    s_ack_head = next_head;
    return 1U;
}

/* Exact wire fields, not struct padding, identify an idempotent retry. */
static uint8_t TelemetryService_CommandEqual(const AirCmdPayload *left,
                                              const AirCmdPayload *right)
{
    SILVERSTAR_ASSERT_OBJECT(left, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    SILVERSTAR_ASSERT_OBJECT(right, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    return (uint8_t)((left->seq == right->seq) &&
        (left->cmd_id == right->cmd_id) && (left->token == right->token) &&
        (left->param0 == right->param0) && (left->param1 == right->param1));
}

static uint8_t TelemetryService_CachedAckQueue(const AirCmdPayload *command)
{
    uint8_t index;
    uint64_t now_us = SystemTime_GetMonotonicUs();

    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    for (index = 0U; index < TELEMETRY_ACK_CACHE_DEPTH; index++)
    {
        TelemetryAckCacheEntry *entry = &s_ack_cache[index];
        /* GSHC's existing four attempts span 3.2 seconds. Bound reuse even if
         * the 8-bit sequence wraps without a new Capability handshake. */
        if ((entry->valid != 0U) &&
            ((now_us - entry->recorded_us) >= 4000000ULL))
        { entry->valid = 0U; }
        if ((entry->valid != 0U) &&
            (TelemetryService_CommandEqual(&entry->command, command) != 0U))
        {
            /* A full ACK queue drops this retry, not the idempotence record.
             * Re-executing the command here would duplicate its side effects. */
            if (TelemetryService_AckFrameQueue(entry->frame) == 0U) { return 1U; }
            return 1U;
        }
    }
    return 0U;
}

static uint8_t TelemetryService_StatusQueueAt(uint8_t status_id,
                                              uint8_t arg0,
                                              uint8_t arg1,
                                              uint8_t repeat_count,
                                              uint32_t event_time_ms)
{
    uint8_t next_head = TelemetryService_QueueNext(s_status_head);

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (repeat_count == 0U) { return 0U; }
    if (next_head == s_status_tail)
    {
        s_diagnostics.status_event_drop_count++;
        return 0U;
    }
    s_status_queue[s_status_head].status_id = status_id;
    s_status_queue[s_status_head].arg0 = arg0;
    s_status_queue[s_status_head].arg1 = arg1;
    s_status_queue[s_status_head].repeats_remaining = repeat_count;
    s_status_queue[s_status_head].event_time_ms = event_time_ms;
    s_status_queue[s_status_head].next_send_us =
        SystemTime_GetMonotonicUs();
    s_status_head = next_head;
    return 1U;
}

static uint8_t TelemetryService_StatusQueue(uint8_t status_id,
                                            uint8_t arg0,
                                            uint8_t arg1,
                                            uint8_t repeat_count)
{
    return TelemetryService_StatusQueueAt(status_id, arg0, arg1,
                                           repeat_count,
                                           TelemetryService_AirTimeMs());
}

static uint8_t TelemetryService_AckRawQueue(uint8_t command_sequence,
                                            uint8_t command_id,
                                            AirAckResult result,
                                            const AirCmdPayload *command)
{
    uint8_t frame[AIR_ACK_LEN];
    uint8_t length = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (Air_AckBuild(s_tx_sequence++, command_sequence, command_id,
                     (uint8_t)result, TelemetryService_AirTimeMs(),
                     frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        s_diagnostics.ack_queue_failure_count++;
        return 0U;
    }
    if (command != NULL)
    {
        SILVERSTAR_ASSERT(s_ack_cache_next < TELEMETRY_ACK_CACHE_DEPTH,
            SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        (void)memcpy(s_ack_cache[s_ack_cache_next].frame, frame, AIR_ACK_LEN);
        s_ack_cache[s_ack_cache_next].command = *command;
        s_ack_cache[s_ack_cache_next].recorded_us = SystemTime_GetMonotonicUs();
        s_ack_cache[s_ack_cache_next].valid = 1U;
        s_ack_cache_next = TelemetryService_AckCacheNext(s_ack_cache_next);
    }
    return TelemetryService_AckFrameQueue(frame);
}

static uint8_t TelemetryService_AckQueue(const AirCmdPayload *command,
                                         AirAckResult result)
{
    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload, SILVERSTAR_ASSERT_MODULE_MODULES);
    return TelemetryService_AckRawQueue(command->seq, command->cmd_id, result, command);
}

static AirAckResult TelemetryService_DeviceResultMap(
    SystemDeviceResult result)
{
    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    switch (result)
    {
        case SYSTEM_DEVICE_OK: return AIR_ACK_RESULT_OK;
        case SYSTEM_DEVICE_BUSY: return AIR_ACK_RESULT_BUSY;
        case SYSTEM_DEVICE_INVALID_ARGUMENT:
        case SYSTEM_DEVICE_VERIFY_FAILED:
            return AIR_ACK_RESULT_BAD_PARAM;
        case SYSTEM_DEVICE_BAD_STATE: return AIR_ACK_RESULT_BAD_STATE;
        case SYSTEM_DEVICE_ALREADY_MATCHED:
        case SYSTEM_DEVICE_NOT_READY:
        case SYSTEM_DEVICE_NOT_PRESENT:
        case SYSTEM_DEVICE_OFFLINE:
        case SYSTEM_DEVICE_UNSUPPORTED:
        case SYSTEM_DEVICE_TIMEOUT:
        case SYSTEM_DEVICE_IO_ERROR:
        case SYSTEM_DEVICE_VALUE_ADJUSTED:
        case SYSTEM_DEVICE_INTERNAL_ERROR:
        case SYSTEM_DEVICE_CONFIG_NO_ACTION:
        case SYSTEM_DEVICE_CONFIG_DELEGATED:
        case SYSTEM_DEVICE_NOT_EXECUTED:
        default: return AIR_ACK_RESULT_REJECTED;
    }
}

static AirAckResult TelemetryService_StartResultMap(
    SystemLifecycleStartResult result,
    SystemLifecycleStartReason reason)
{
    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (result == SYSTEM_LIFECYCLE_START_OK)
    {
        return AIR_ACK_RESULT_OK;
    }
    if (result == SYSTEM_LIFECYCLE_START_BUSY)
    {
        return AIR_ACK_RESULT_BUSY;
    }
    switch (reason)
    {
        case SYSTEM_START_REASON_NONE:
            return AIR_ACK_RESULT_REJECTED;
        case SYSTEM_START_REASON_CALIBRATION_REQUIRED:
            return AIR_ACK_RESULT_CALIBRATION_REQUIRED;
        case SYSTEM_START_REASON_ALIGNMENT_REQUIRED:
            return AIR_ACK_RESULT_ALIGNMENT_REQUIRED;
        case SYSTEM_START_REASON_ATTITUDE_NOT_READY:
            return AIR_ACK_RESULT_ATTITUDE_NOT_READY;
        case SYSTEM_START_REASON_ATTITUDE_INVALID:
            return AIR_ACK_RESULT_ATTITUDE_INVALID;
        case SYSTEM_START_REASON_ATTITUDE_STALE:
            return AIR_ACK_RESULT_ATTITUDE_STALE;
        case SYSTEM_START_REASON_SYSTEM_NOT_READY:
            return AIR_ACK_RESULT_SYSTEM_NOT_READY;
        case SYSTEM_START_REASON_STORAGE_NOT_READY:
            return AIR_ACK_RESULT_SYSTEM_NOT_READY;
        case SYSTEM_START_REASON_ORIGIN_FAILED:
            return AIR_ACK_RESULT_ORIGIN_FAILED;
        case SYSTEM_START_REASON_NAVIGATION_FAILED:
            return AIR_ACK_RESULT_NAVIGATION_FAILED;
        case SYSTEM_START_REASON_QUEUE_FAILED:
            return AIR_ACK_RESULT_QUEUE_FAILED;
        case SYSTEM_START_REASON_HOOKS_UNAVAILABLE:
            return AIR_ACK_RESULT_HOOKS_UNAVAILABLE;
        case SYSTEM_START_REASON_PREPARE_FAILED:
            return AIR_ACK_RESULT_PREPARE_FAILED;
        case SYSTEM_START_REASON_REQUEST_PENDING:
            return AIR_ACK_RESULT_BUSY;
        case SYSTEM_START_REASON_LOCKED:
            return AIR_ACK_RESULT_BAD_STATE;
        default:
            return (result == SYSTEM_LIFECYCLE_START_LOCKED) ?
                AIR_ACK_RESULT_BAD_STATE : AIR_ACK_RESULT_REJECTED;
    }
}

static AirAckResult TelemetryService_StartResponseMap(
    const SystemLifecycleStartResponse *response)
{
    if (response == NULL) { return AIR_ACK_RESULT_REJECTED; }
    return TelemetryService_StartResultMap(response->result,
                                            response->reason);
}

static AirAckResult TelemetryService_AirStartBlockReasonGet(void)
{
    SystemLifecycleStartReason reason = SYSTEM_START_REASON_NONE;
    SystemLifecycleStartResult result;

    if (s_capability_state != TELEMETRY_CAPABILITY_ACKED)
    {
        return AIR_ACK_RESULT_CAPABILITY_REQUIRED;
    }
    if (s_locked != 0U)
    {
        return AIR_ACK_RESULT_LOCKED_REQUIRED;
    }
    if (s_start_request_pending != 0U)
    {
        return AIR_ACK_RESULT_BUSY;
    }
    result = SystemLifecycle_StartReadinessGet(&reason);
    return TelemetryService_StartResultMap(result, reason);
}

static void TelemetryService_PreflightDisable(void)
{
    s_capability_state = TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT;
    s_capability_send_pending = 0U;
    s_next_capability_us = 0ULL;
    s_preflight_status_send_pending = 0U;
    s_preflight_status_known = 0U;
    s_next_preflight_status_us = 0ULL;
    s_next_preflight_state_us = 0ULL;
    s_sensor_snapshot_active = 0U;
    s_sensor_snapshot_terminal_pending = 0U;
}

static void TelemetryService_StartResponseProcess(void)
{
    SystemLifecycleStartResponse response;
    uint8_t response_index;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((s_start_request_pending != 0U) &&
        (TelemetryService_AckQueueHasSpace() == 0U))
    {
        return;
    }
    for (response_index = 0U;
         response_index < TELEMETRY_START_RESPONSE_MAX_PER_CYCLE;
         response_index++)
    {
        AirAckResult ack_result;

        if (SystemLifecycle_TryGetStartResponse(&response) == 0U)
        {
            break;
        }

        if ((response.source != SYSTEM_START_SOURCE_AIR) ||
            (s_start_request_pending == 0U) ||
            (response.request_id != s_start_cmd_sequence))
        {
            continue;
        }
        ack_result = TelemetryService_StartResponseMap(&response);
        if (TelemetryService_AckQueue(&s_start_command, ack_result) == 0U)
        {
            return;
        }
        s_start_request_pending = 0U;
        if (response.result == SYSTEM_LIFECYCLE_START_OK)
        {
            TelemetryService_PreflightDisable();
        }
        if (response.result == SYSTEM_LIFECYCLE_START_OK)
        {
            (void)TelemetryService_StatusQueue(AIR_STATUS_MISSION_START,
                0U, 0U, TELEMETRY_STATUS_REPEAT_COUNT);
        }
        return;
    }
    if (response_index == TELEMETRY_START_RESPONSE_MAX_PER_CYCLE)
    {
        s_diagnostics.start_response_limit_count++;
    }
}

static uint8_t TelemetryService_CapabilityAdvertised(uint8_t sequence,
    uint64_t *sent_us)
{
    uint8_t index;
    uint8_t found = 0U;
    uint64_t best_age = (uint64_t)TELEMETRY_CAPABILITY_WINDOW_MS * 1000ULL;
    uint64_t now_us = SystemTime_GetMonotonicUs();
    SILVERSTAR_ASSERT(s_capability_tx.count <= TELEMETRY_CAPABILITY_WINDOW_DEPTH,
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (index = 0U; index < TELEMETRY_CAPABILITY_WINDOW_DEPTH; index++)
    {
        uint64_t age = now_us - s_capability_tx.advertised[index].sent_us;
        if ((index < s_capability_tx.count) &&
            (s_capability_tx.advertised[index].sequence == sequence) && (age < best_age))
        { *sent_us = s_capability_tx.advertised[index].sent_us; best_age = age; found = 1U; }
    }
    return found;
}

static void TelemetryService_CapabilityTxPoll(void)
{
    uint32_t age_ms = 0U;
    SystemDeviceResult result;
    uint64_t now_us;
    if (s_capability_tx.pending_id == 0U) { return; }
    now_us = SystemTime_GetMonotonicUs();
    /* Use the 64-bit service clock for lifetime, including a whole 32-bit ms wrap.
     * The transport receipt age still has its independent wrap-safe clock. */
    if ((now_us - s_capability_tx.pending_since_us) >=
        ((uint64_t)TELEMETRY_CAPABILITY_WINDOW_MS * 1000ULL))
    {
        s_capability_tx.pending_id = 0U;
        s_capability_send_pending = 1U;
        s_next_capability_us = now_us + SYSTEM_TELEMETRY_CAPABILITY_PERIOD_US;
        return;
    }
    result = SystemTelemetry_TxResultGet(s_capability_tx.pending_id, &age_ms);
    if (result == SYSTEM_DEVICE_BUSY) { return; }
    if ((result == SYSTEM_DEVICE_OK) && (age_ms < TELEMETRY_CAPABILITY_WINDOW_MS))
    {
        SILVERSTAR_ASSERT(s_capability_tx.next < TELEMETRY_CAPABILITY_WINDOW_DEPTH,
            SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        SILVERSTAR_ASSERT(s_capability_tx.count <= TELEMETRY_CAPABILITY_WINDOW_DEPTH,
            SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        s_capability_tx.advertised[s_capability_tx.next].sequence = s_capability_tx.pending_sequence;
        s_capability_tx.advertised[s_capability_tx.next].sent_us = now_us - (uint64_t)age_ms * 1000ULL;
        s_capability_tx.next = (uint8_t)((s_capability_tx.next + 1U) % TELEMETRY_CAPABILITY_WINDOW_DEPTH);
        if (s_capability_tx.count < TELEMETRY_CAPABILITY_WINDOW_DEPTH) { s_capability_tx.count++; }
        s_capability_tx.latest_sequence = s_capability_tx.pending_sequence;
        s_capability_sent = 1U;
        s_diagnostics.capability_tx_count++;
    }
    else
    { s_capability_send_pending = 1U; s_next_capability_us = now_us + SYSTEM_TELEMETRY_CAPABILITY_PERIOD_US; }
    s_capability_tx.pending_id = 0U;
}

static void TelemetryService_CapabilityCommand(
    const AirCmdPayload *command)
{
    uint64_t advertised_us = 0U;
    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((TelemetryService_IsPreflightState() == 0U) ||
        (s_capability_sent == 0U) ||
        (command->param1 != AIR_PROFILE_ID_CURRENT) ||
        (TelemetryService_CapabilityAdvertised(command->param0, &advertised_us) == 0U))
    {
        (void)TelemetryService_AckQueue(command,
            (TelemetryService_IsPreflightState() != 0U) ?
                AIR_ACK_RESULT_BAD_PARAM : AIR_ACK_RESULT_BAD_STATE);
        return;
    }
    if ((s_capability_ack_known == 0U) ||
        (advertised_us > s_capability_tx.ack_advertised_us) ||
        ((SystemTime_GetMonotonicUs() - s_capability_ack_us) >= 4000000ULL))
    {
        /* A newly validated handshake invalidates prior-session business ACKs.
         * A delayed reply within the sent window cannot invalidate newer ACKs. */
        (void)memset(s_ack_cache, 0, sizeof(s_ack_cache));
        s_capability_ack_sequence = command->param0;
        s_capability_tx.ack_advertised_us = advertised_us;
        s_capability_ack_us = SystemTime_GetMonotonicUs();
        s_capability_ack_known = 1U;
    }
    s_capability_state = TELEMETRY_CAPABILITY_ACKED;
    s_capability_send_pending = 0U;
    /* Keep the existing deadline: reconnects still need periodic Capability. */
    s_preflight_status_send_pending = 1U;
    s_next_preflight_status_us = 0ULL;
    (void)TelemetryService_AckQueue(command,
                              AIR_ACK_RESULT_OK);
}

static void TelemetryService_CalibrationCommand(
    const AirCmdPayload *command)
{
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    switch (command->cmd_id)
    {
        case AIR_CMD_CAL_START:
            result = SystemCalibration_Start(
                (SystemCalibrationMode)command->param0);
            break;
        case AIR_CMD_CAL_FACE:
            result = SystemCalibration_FaceCollect(
                (SystemCalibrationFace)command->param0);
            break;
        case AIR_CMD_CAL_STOP:
            result = SystemCalibration_Stop();
            break;
        case AIR_CMD_CAL_RESET:
            result = SystemCalibration_Reset();
            break;
        default:
            result = SYSTEM_DEVICE_INVALID_ARGUMENT;
            break;
    }
    (void)TelemetryService_AckQueue(command,
                              TelemetryService_DeviceResultMap(result));
}

static void TelemetryService_AlignmentCommand(
    const AirCmdPayload *command)
{
    SystemDeviceResult result;
    AirAckResult ack_result;

    switch (command->cmd_id)
    {
        case AIR_CMD_ALIGN_START: result = SystemAlignment_Start(); break;
        case AIR_CMD_ALIGN_STOP: result = SystemAlignment_Stop(); break;
        case AIR_CMD_ALIGN_RESET: result = SystemAlignment_Reset(); break;
        default: result = SYSTEM_DEVICE_INVALID_ARGUMENT; break;
    }
    ack_result = ((command->cmd_id == AIR_CMD_ALIGN_START) &&
                  (result == SYSTEM_DEVICE_NOT_READY)) ?
        ((SystemCalibration_IsReady() == 0U) ?
            AIR_ACK_RESULT_CALIBRATION_REQUIRED : AIR_ACK_RESULT_SYSTEM_NOT_READY) :
        TelemetryService_DeviceResultMap(result);
    (void)TelemetryService_AckQueue(command,
                                    ack_result);
}

static void TelemetryService_StartCommand(const AirCmdPayload *command)
{
    SystemLifecycleStartRequest request;
    SystemDeviceResult result;
    AirAckResult block_reason;

    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    block_reason = TelemetryService_AirStartBlockReasonGet();
    if (block_reason != AIR_ACK_RESULT_OK)
    {
        (void)TelemetryService_AckQueue(command,
            block_reason);
        return;
    }
    request.source = SYSTEM_START_SOURCE_AIR;
    request.request_id = command->seq;
    result = SystemLifecycle_SubmitStart(&request);
    if (result != SYSTEM_DEVICE_OK)
    {
        (void)TelemetryService_AckQueue(command,
            (result == SYSTEM_DEVICE_BUSY) ? AIR_ACK_RESULT_BUSY :
                                             AIR_ACK_RESULT_REJECTED);
        return;
    }
    s_start_request_pending = 1U;
    s_start_cmd_sequence = command->seq;
    s_start_command = *command;
}

static void TelemetryService_LockCommand(const AirCmdPayload *command,
                                         uint8_t lock_requested)
{
    uint8_t status_id;

    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (s_locked == lock_requested)
    {
        (void)TelemetryService_AckQueue(command,
            (lock_requested != 0U) ? AIR_ACK_RESULT_ALREADY_LOCKED :
                                     AIR_ACK_RESULT_ALREADY_UNLOCKED);
        return;
    }
    s_locked = lock_requested;
    status_id = (lock_requested != 0U) ? AIR_STATUS_LOCKED :
                                         AIR_STATUS_UNLOCKED;
    (void)TelemetryService_AckQueue(command,
        AIR_ACK_RESULT_OK);
    (void)TelemetryService_StatusQueue(status_id, 0U, 0U,
        TELEMETRY_STATUS_REPEAT_COUNT);
}

static uint8_t TelemetryService_CommandIsPendingStart(
    const AirCmdPayload *command)
{
    return (uint8_t)((s_start_request_pending != 0U) &&
        (TelemetryService_CommandEqual(command, &s_start_command) != 0U));
}

static void TelemetryService_MissionCommand(const AirCmdPayload *command)
{
    switch (command->cmd_id)
    {
        case AIR_CMD_START_MISSION: TelemetryService_StartCommand(command); break;
        case AIR_CMD_LOCK: TelemetryService_LockCommand(command, 1U); break;
        case AIR_CMD_UNLOCK: TelemetryService_LockCommand(command, 0U); break;
        default:
            (void)TelemetryService_AckQueue(command,
                AIR_ACK_RESULT_BAD_CMD);
            break;
    }
}

static void TelemetryService_CommandDispatch(const AirCmdPayload *command)
{
    if (command == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(command, AirCmdPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (command->cmd_id == AIR_CMD_CAPABILITY_ACK)
    {
        TelemetryService_CapabilityCommand(command);
        return;
    }
    if (TelemetryService_CachedAckQueue(command) != 0U)
    {
        return;
    }
    if (TelemetryService_CommandIsPendingStart(command) != 0U)
    {
        return;
    }
    if (command->cmd_id == AIR_CMD_PING)
    {
        (void)TelemetryService_AckQueue(command,
            AIR_ACK_RESULT_OK);
        return;
    }
    if ((TelemetryService_IsPreflightState() != 0U) &&
        (s_capability_state != TELEMETRY_CAPABILITY_ACKED))
    {
        (void)TelemetryService_AckQueue(command,
                                  AIR_ACK_RESULT_CAPABILITY_REQUIRED);
        return;
    }

    if ((command->cmd_id >= AIR_CMD_CAL_START) &&
        (command->cmd_id <= AIR_CMD_CAL_RESET))
    {
        TelemetryService_CalibrationCommand(command);
        return;
    }
    if ((command->cmd_id >= AIR_CMD_ALIGN_START) &&
        (command->cmd_id <= AIR_CMD_ALIGN_RESET))
    {
        TelemetryService_AlignmentCommand(command);
        return;
    }

    TelemetryService_MissionCommand(command);
}

static void TelemetryService_ReceiveProcess(void)
{
    uint8_t frame[AIR_MAX_FRAME_LEN];
    uint16_t length;
    SystemDeviceResult result;
    uint8_t frame_index;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    for (frame_index = 0U;
         frame_index < TELEMETRY_RX_MAX_FRAMES_PER_CYCLE;
         frame_index++)
    {
        AirCmdPayload command;
        AirParseResult parse_result;

        length = 0U;
        result = SystemTelemetry_Receive(frame, sizeof(frame), &length);
        if (result != SYSTEM_DEVICE_OK) { return; }
        if (TelemetryService_CommandRxAllowed() == 0U)
        {
            continue;
        }
        parse_result = Air_CmdParse(frame, (uint8_t)length, &command);
        if (parse_result == AIR_PARSE_OK)
        {
            TelemetryService_CommandDispatch(&command);
        }
        else if ((length >= 3U) && (frame[0] == AIR_TYPE_CMD))
        {
            AirAckResult ack_result = AIR_ACK_RESULT_BAD_CMD;

            if (parse_result == AIR_PARSE_BAD_LEN)
            {
                ack_result = AIR_ACK_RESULT_BAD_LEN;
            }
            else if (parse_result == AIR_PARSE_BAD_TOKEN)
            {
                ack_result = AIR_ACK_RESULT_BAD_TOKEN;
            }
            else if (parse_result == AIR_PARSE_BAD_FIELD)
            {
                ack_result = AIR_ACK_RESULT_BAD_PARAM;
            }
            (void)TelemetryService_AckRawQueue(frame[1], frame[2], ack_result, NULL);
        }
    }
    s_diagnostics.receive_limit_count++;
}

static void TelemetryService_GnssStateProcess(void)
{
    SystemGnssSample sample;
    uint8_t usable = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((SystemGnss_LatestSampleGet(&sample) == SYSTEM_DEVICE_OK) &&
        (sample.online != 0U) && (sample.position_usable != 0U))
    {
        usable = 1U;
    }
    if (s_gnss_state_known == 0U)
    {
        s_gnss_state_known = 1U;
        s_gnss_position_usable = 0U;
        if (usable == 0U) { return; }
    }
    if ((usable != s_gnss_position_usable) &&
        (TelemetryService_StatusQueue(AIR_STATUS_GNSS_POSITION,
            usable, 0U, 1U) != 0U))
    {
        s_gnss_position_usable = usable;
    }
}

static void TelemetryService_SelfTestStateProcess(void)
{
    const SystemStartupReport *report;

    if (s_selftest_event_sent != 0U) { return; }
    report = SystemStartup_GetReport();
    if ((report == NULL) || (report->completed == 0U)) { return; }
    if (TelemetryService_StatusQueue(AIR_STATUS_SELFTEST_COMPLETE,
            report->mission_capable, 0U, 1U) != 0U)
    {
        s_selftest_event_sent = 1U;
    }
}

static uint8_t TelemetryService_AlignmentStateMap(
    SystemAlignmentState state)
{
    switch (state)
    {
        case SYSTEM_ALIGNMENT_STATE_IDLE: return AIR_ALIGNMENT_STATE_IDLE;
        case SYSTEM_ALIGNMENT_STATE_COLLECTING:
            return AIR_ALIGNMENT_STATE_COLLECTING;
        case SYSTEM_ALIGNMENT_STATE_CHECKING:
            return AIR_ALIGNMENT_STATE_CHECKING;
        case SYSTEM_ALIGNMENT_STATE_READY: return AIR_ALIGNMENT_STATE_READY;
        case SYSTEM_ALIGNMENT_STATE_FAILED: return AIR_ALIGNMENT_STATE_FAILED;
        case SYSTEM_ALIGNMENT_STATE_STALE: return AIR_ALIGNMENT_STATE_STALE;
        default: return AIR_ALIGNMENT_STATE_FAILED;
    }
}

static void TelemetryService_AttitudeSourceTrack(
    const SystemAlignmentSummary *summary)
{
    if ((s_preflight_attitude_source_known != 0U) &&
        (summary->preflight_attitude_source == s_preflight_attitude_source) &&
        ((summary->preflight_attitude_source !=
          SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT) ||
         (summary->start_sequence ==
          s_preflight_attitude_alignment_sequence)))
    {
        return;
    }
    s_preflight_attitude_source = summary->preflight_attitude_source;
    s_preflight_attitude_alignment_sequence = summary->start_sequence;
    s_preflight_attitude_source_known = 1U;
    s_next_preflight_state_us = 0ULL;
}

static uint8_t TelemetryService_AlignmentSnapshotSchedule(uint8_t state)
{
    SystemSensorStatusSnapshotInfo snapshot;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((SystemSensorStatus_SnapshotInfoGet(&snapshot) != SYSTEM_DEVICE_OK) ||
        (snapshot.sequence == s_sensor_snapshot_sequence) ||
        (snapshot.alignment_state != state))
    {
        if ((SystemSensorStatus_SnapshotCapture(state) != SYSTEM_DEVICE_OK) ||
            (SystemSensorStatus_SnapshotInfoGet(&snapshot) !=
             SYSTEM_DEVICE_OK))
        {
            return 0U;
        }
    }
    s_sensor_snapshot_sequence = snapshot.sequence;
    s_sensor_snapshot_id = snapshot.snapshot_id;
    s_sensor_snapshot_total = snapshot.total;
    s_sensor_snapshot_index = 0U;
    s_sensor_snapshot_active = 1U;
    s_sensor_snapshot_terminal_pending = 0U;
    s_sensor_snapshot_terminal_state = state;
    return 1U;
}

static void TelemetryService_AlignmentStateProcess(void)
{
    SystemAlignmentSummary summary;
    uint8_t state;
    uint8_t state_changed;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (SystemAlignment_SummaryGet(&summary) != SYSTEM_DEVICE_OK) { return; }
    state = TelemetryService_AlignmentStateMap(summary.state);
    state_changed = (uint8_t)((s_alignment_status_known == 0U) ||
                              (state != s_alignment_state));
    TelemetryService_AttitudeSourceTrack(&summary);
    if (state_changed == 0U)
    {
        return;
    }
    if ((state == AIR_ALIGNMENT_STATE_READY) ||
        (state == AIR_ALIGNMENT_STATE_FAILED))
    {
        if (TelemetryService_AlignmentSnapshotSchedule(state) == 0U) { return; }
    }
    else if (state == AIR_ALIGNMENT_STATE_STALE)
    {
        if (TelemetryService_StatusQueue(AIR_STATUS_ALIGNMENT,
                state, 0xFFU, 1U) == 0U)
        {
            return;
        }
    }
    s_alignment_state = state;
    s_alignment_status_known = 1U;
}

static uint8_t TelemetryService_CalibrationStateMap(
    SystemCalibrationState state)
{
    switch (state)
    {
        case SYSTEM_CALIBRATION_STATE_IDLE: return AIR_CALIBRATION_STATE_IDLE;
        case SYSTEM_CALIBRATION_STATE_WAIT_FACE:
            return AIR_CALIBRATION_STATE_WAIT_FACE;
        case SYSTEM_CALIBRATION_STATE_COLLECTING:
            return AIR_CALIBRATION_STATE_COLLECTING;
        case SYSTEM_CALIBRATION_STATE_CHECKING:
            return AIR_CALIBRATION_STATE_CHECKING;
        case SYSTEM_CALIBRATION_STATE_READY:
            return AIR_CALIBRATION_STATE_READY;
        case SYSTEM_CALIBRATION_STATE_FAILED:
        default: return AIR_CALIBRATION_STATE_FAILED;
    }
}

static void TelemetryService_CalibrationStateProcess(void)
{
    SystemCalibrationStatus status;
    uint8_t state;
    uint8_t mode;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (SystemCalibration_StatusGet(&status) != SYSTEM_DEVICE_OK) { return; }
    state = TelemetryService_CalibrationStateMap(status.state);
    mode = (uint8_t)status.mode;
    if ((s_calibration_status_known == 0U) ||
        (state != s_calibration_state) ||
        (mode != s_calibration_mode))
    {
        if (TelemetryService_StatusQueue(AIR_STATUS_CALIBRATION,
                state, mode, 1U) != 0U)
        {
            s_calibration_state = state;
            s_calibration_mode = mode;
            s_calibration_status_known = 1U;
        }
    }
    if (status.face_event_sequence != s_calibration_face_event_sequence)
    {
        uint8_t result =
            (status.last_face_result ==
             SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE) ?
                AIR_CALIBRATION_FACE_PASSED :
                AIR_CALIBRATION_FACE_FAILED;

        if ((status.last_face <= SYSTEM_CALIBRATION_FACE_Z_NEGATIVE) &&
            (TelemetryService_StatusQueue(AIR_STATUS_CALIBRATION_FACE,
                (uint8_t)status.last_face, result, 1U) != 0U))
        {
            s_calibration_face_event_sequence =
                status.face_event_sequence;
        }
    }
    if (status.diagnostic_sequence != s_calibration_diagnostic_sequence)
    {
        uint8_t face = (status.diagnostic_face <=
            SYSTEM_CALIBRATION_FACE_Z_NEGATIVE) ?
                (uint8_t)status.diagnostic_face :
                AIR_CALIBRATION_FACE_NOT_SELECTED;

        if (TelemetryService_StatusQueue(
                AIR_STATUS_CALIBRATION_DIAGNOSTIC,
                face, (uint8_t)status.diagnostic_reason, 1U) != 0U)
        {
            s_calibration_diagnostic_sequence =
                status.diagnostic_sequence;
        }
    }
}

static void TelemetryService_FlightRecoveryStateProcess(void)
{
    SystemFlightRecoveryStatus status;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (SystemFlightRecovery_StatusGet(&status) != SYSTEM_DEVICE_OK)
    {
        return;
    }
    if (status.deploy_event_sequence != s_deploy_event_sequence)
    {
        if (TelemetryService_StatusQueueAt(
                AIR_STATUS_PARACHUTE_DEPLOY, 0U, 0U,
                TELEMETRY_STATUS_REPEAT_COUNT,
                status.deploy_event_mission_time_ms) == 0U)
        {
            return;
        }
        s_deploy_event_sequence = status.deploy_event_sequence;
    }
    if (status.landing_event_sequence != s_landing_event_sequence)
    {
        if (TelemetryService_StatusQueueAt(
                AIR_STATUS_LANDING, 0U, 0U,
                TELEMETRY_STATUS_REPEAT_COUNT,
                status.landing_event_mission_time_ms) == 0U)
        {
            return;
        }
        s_landing_event_sequence = status.landing_event_sequence;
    }
}

static uint8_t TelemetryService_PreflightStatusPayloadGet(
    AirPreflightStatusPayload *payload)
{
    const SystemStartupReport *startup;
    SystemCalibrationStatus calibration;
    SystemAlignmentSummary alignment;
    SystemHealthSnapshot health;

    if ((payload == NULL) ||
        (s_capability_state != TELEMETRY_CAPABILITY_ACKED) ||
        (TelemetryService_IsPreflightState() == 0U) ||
        (SystemCalibration_StatusGet(&calibration) != SYSTEM_DEVICE_OK) ||
        (SystemAlignment_SummaryGet(&alignment) != SYSTEM_DEVICE_OK))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(payload, AirPreflightStatusPayload,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    (void)memset(payload, 0, sizeof(*payload));
    (void)memset(&health, 0, sizeof(health));
    SystemHealth_GetSnapshot(&health);
    startup = SystemStartup_GetReport();
    payload->lifecycle_state = (uint8_t)SystemLifecycle_GetState();
    payload->calibration_state =
        TelemetryService_CalibrationStateMap(calibration.state);
    payload->calibration_mode = (uint8_t)calibration.mode;
    payload->completed_face_mask = calibration.completed_face_mask;
    payload->current_face = (uint8_t)calibration.current_face;
    payload->alignment_state =
        TelemetryService_AlignmentStateMap(alignment.state);
    if (health.ready != 0U)
    {
        payload->flags |= AIR_PREFLIGHT_FLAG_SYSTEM_READY;
    }
    if (s_locked == 0U)
    {
        payload->flags |= AIR_PREFLIGHT_FLAG_START_UNLOCKED;
    }
    if ((startup != NULL) && (startup->completed != 0U) &&
        (startup->mission_capable != 0U))
    {
        payload->flags |= AIR_PREFLIGHT_FLAG_SELFTEST_PASSED;
    }
    if (s_gnss_position_usable != 0U)
    {
        payload->flags |= AIR_PREFLIGHT_FLAG_GNSS_USABLE;
    }
    payload->flags |= AIR_PREFLIGHT_FLAG_CAPABILITY_ACKED;
    if (calibration.ready != 0U)
    {
        payload->flags |= AIR_PREFLIGHT_FLAG_CALIBRATION_READY;
    }
    if (alignment.ready != 0U)
    {
        payload->flags |= AIR_PREFLIGHT_FLAG_ALIGNMENT_READY;
    }
    payload->start_block_reason =
        (uint8_t)TelemetryService_AirStartBlockReasonGet();
    return 1U;
}

static void TelemetryService_PreflightStatusStateProcess(void)
{
    AirPreflightStatusPayload payload;

    if (TelemetryService_PreflightStatusPayloadGet(&payload) == 0U)
    {
        return;
    }
    if ((s_preflight_status_known == 0U) ||
        (memcmp(&payload, &s_preflight_status_observed,
                sizeof(payload)) != 0))
    {
        s_preflight_status_observed = payload;
        s_preflight_status_known = 1U;
        s_preflight_status_send_pending = 1U;
    }
}

static uint8_t TelemetryService_AckSend(void)
{
    if (s_ack_tail == s_ack_head) { return 0U; }
    if (SystemTelemetry_SendControl(s_ack_queue[s_ack_tail].frame,
                             AIR_ACK_LEN, NULL) != SYSTEM_DEVICE_OK)
    {
        return 1U;
    }
    s_ack_tail = TelemetryService_AckQueueNext(s_ack_tail);
    return 1U;
}

static uint8_t TelemetryService_StatusSend(void)
{
    TelemetryStatusEvent event;
    uint8_t frame[AIR_STATUS_LEN];
    uint8_t length = 0U;
    uint8_t pending_count;
    uint8_t scan_count;
    uint64_t now_us;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    pending_count = (s_status_head >= s_status_tail) ?
        (uint8_t)(s_status_head - s_status_tail) :
        (uint8_t)(TELEMETRY_STATUS_QUEUE_DEPTH - s_status_tail +
                  s_status_head);
    now_us = SystemTime_GetMonotonicUs();
    for (scan_count = 0U;
         (scan_count < TELEMETRY_STATUS_QUEUE_DEPTH) &&
         (pending_count != 0U);
         scan_count++)
    {
        event = s_status_queue[s_status_tail];
        if (now_us < event.next_send_us)
        {
            s_status_tail = TelemetryService_QueueNext(s_status_tail);
            s_status_queue[s_status_head] = event;
            s_status_head = TelemetryService_QueueNext(s_status_head);
            pending_count--;
            continue;
        }
        if (Air_StatusBuild(s_tx_sequence++, event.status_id,
                            event.event_time_ms,
                            event.arg0, event.arg1,
                            frame, sizeof(frame), &length) != AIR_BUILD_OK)
        {
            s_status_tail = TelemetryService_QueueNext(s_status_tail);
            return 0U;
        }
        if (SystemTelemetry_SendControl(frame, length, NULL) != SYSTEM_DEVICE_OK) { return 1U; }
        s_status_tail = TelemetryService_QueueNext(s_status_tail);
        event.repeats_remaining--;
        if (event.repeats_remaining != 0U)
        {
            event.next_send_us = now_us +
                SYSTEM_TELEMETRY_STATUS_REPEAT_PERIOD_US;
            s_status_queue[s_status_head] = event;
            s_status_head = TelemetryService_QueueNext(s_status_head);
        }
        return 1U;
    }
    return 0U;
}

static uint8_t TelemetryService_SensorSnapshotSend(void)
{
    SystemSensorStatus sensor;
    AirSensorStatusPayload payload;
    uint8_t frame[AIR_SENSOR_STATUS_LEN];
    uint8_t length = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((s_sensor_snapshot_active == 0U) ||
        (s_capability_state != TELEMETRY_CAPABILITY_ACKED) ||
        (TelemetryService_IsPreflightState() == 0U))
    {
        return 0U;
    }
    if (s_sensor_snapshot_index >= s_sensor_snapshot_total)
    {
        s_sensor_snapshot_active = 0U;
        s_sensor_snapshot_terminal_pending = 1U;
        return 0U;
    }
    if (SystemSensorStatus_SnapshotGet(
            s_sensor_snapshot_index, &sensor) != SYSTEM_DEVICE_OK)
    {
        s_sensor_snapshot_active = 0U;
        s_sensor_snapshot_terminal_pending = 1U;
        return 0U;
    }
    payload.snapshot_id = s_sensor_snapshot_id;
    payload.sensor_id = sensor.sensor_id;
    payload.instance_id = sensor.instance_id;
    payload.status_flags = sensor.status_flags;
    payload.detail_code = sensor.detail_code;
    payload.index = s_sensor_snapshot_index;
    payload.total = s_sensor_snapshot_total;
    if (Air_SensorStatusBuild(s_tx_sequence, &payload,
            frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        return 0U;
    }
    if (SystemTelemetry_SendControl(frame, length, NULL) != SYSTEM_DEVICE_OK) { return 1U; }
    s_tx_sequence++;
    s_sensor_snapshot_index++;
    if (s_sensor_snapshot_index >= s_sensor_snapshot_total)
    {
        s_sensor_snapshot_active = 0U;
        s_sensor_snapshot_terminal_pending = 1U;
    }
    return 1U;
}

static uint8_t TelemetryService_SensorSnapshotTerminalSend(void)
{
    uint8_t frame[AIR_STATUS_LEN];
    uint8_t length = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((s_sensor_snapshot_terminal_pending == 0U) ||
        (s_capability_state != TELEMETRY_CAPABILITY_ACKED) ||
        (TelemetryService_IsPreflightState() == 0U))
    {
        return 0U;
    }
    if (Air_StatusBuild(s_tx_sequence,
            AIR_STATUS_ALIGNMENT, TelemetryService_AirTimeMs(),
            s_sensor_snapshot_terminal_state, s_sensor_snapshot_id,
            frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        return 0U;
    }
    if (SystemTelemetry_SendControl(frame, length, NULL) != SYSTEM_DEVICE_OK) { return 1U; }
    s_tx_sequence++;
    s_sensor_snapshot_terminal_pending = 0U;
    return 1U;
}

static uint8_t TelemetryService_CapabilitySend(void)
{
    AirCapabilityPayload capability;
    uint8_t frame[AIR_CAPABILITY_LEN];
    uint8_t length = 0U;
    uint8_t sequence;
    uint64_t now_us;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((TelemetryService_IsPreflightState() == 0U) ||
        (s_capability_state == TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT))
    {
        return 0U;
    }
    if (s_capability_tx.pending_id != 0U) { return 0U; }
    now_us = SystemTime_GetMonotonicUs();
    if ((s_capability_send_pending == 0U) &&
        (s_next_capability_us != 0ULL) &&
        (now_us < s_next_capability_us))
    {
        return 0U;
    }
    capability.air_profile_id = AIR_PROFILE_ID_CURRENT;
    capability.command_policy = s_command_policy;
    capability.calibration_mode_mask =
        SystemCalibration_CapabilityMaskGet();
    capability.sensor_summary_flags =
        SystemSensorStatus_SummaryFlagsGet();
    capability.accel_full_scale_g = AIR_ACCEL_FULL_SCALE_G;
    capability.gyro_full_scale_dps = AIR_GYRO_FULL_SCALE_DPS;
    sequence = s_tx_sequence;
    for (uint8_t attempt = 0U; attempt < TELEMETRY_CAPABILITY_WINDOW_DEPTH; attempt++)
    {
        uint64_t advertised_us;
        if (TelemetryService_CapabilityAdvertised(sequence, &advertised_us) == 0U) { break; }
        sequence++;
    }
    if (Air_CapabilityBuild(sequence, &capability,
            frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        return 0U;
    }
    if (SystemTelemetry_SendControl(frame, length, &s_capability_tx.pending_id) != SYSTEM_DEVICE_OK) { return 1U; }
    s_tx_sequence = (uint8_t)(sequence + 1U);
    s_capability_tx.pending_sequence = sequence;
    s_capability_tx.pending_since_us = now_us;
    s_capability_send_pending = 0U;
    s_next_capability_us = now_us +
        SYSTEM_TELEMETRY_CAPABILITY_PERIOD_US;
    return 1U;
}

static uint8_t TelemetryService_PreflightStatusSend(void)
{
    AirPreflightStatusPayload payload;
    uint8_t frame[AIR_PREFLIGHT_STATUS_LEN];
    uint8_t length = 0U;
    uint64_t now_us;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((s_capability_state != TELEMETRY_CAPABILITY_ACKED) ||
        (TelemetryService_IsPreflightState() == 0U))
    {
        return 0U;
    }
    now_us = SystemTime_GetMonotonicUs();
    if ((s_preflight_status_send_pending == 0U) &&
        (s_next_preflight_status_us != 0ULL) &&
        (now_us < s_next_preflight_status_us))
    {
        return 0U;
    }
    if (TelemetryService_PreflightStatusPayloadGet(&payload) == 0U)
    {
        return 0U;
    }
    if (Air_PreflightStatusBuild(s_tx_sequence, &payload,
            frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        return 0U;
    }
    if (SystemTelemetry_SendControl(frame, length, NULL) != SYSTEM_DEVICE_OK) { return 1U; }
    s_tx_sequence++;
    s_preflight_status_observed = payload;
    s_preflight_status_known = 1U;
    s_preflight_status_send_pending = 0U;
    s_next_preflight_status_us = now_us +
        SYSTEM_TELEMETRY_PREFLIGHT_STATUS_PERIOD_US;
    return 1U;
}

static uint8_t TelemetryService_ImuQuantizedGet(
    AirCompactV0ImuQuantized *quantized)
{
    SystemCalibrationImuCorrection correction;
    SystemInertialSample sample;
    float corrected_accel_b_mps2[3];
    float corrected_gyro_b_radps[3];
    uint8_t index;

    if ((quantized == NULL) ||
        (SystemInertial_LatestGet(&sample) != SYSTEM_DEVICE_OK) ||
        ((sample.valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL |
                               SYSTEM_INERTIAL_VALID_GYRO)) !=
         (SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO)))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(quantized, AirCompactV0ImuQuantized,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK)
    {
        (void)memset(&correction, 0, sizeof(correction));
        correction.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
        for (index = 0U; index < 3U; index++)
        {
            correction.accel_scale[index] = 1.0f;
            correction.gyro_scale[index] = 1.0f;
        }
    }
    if ((SystemCalibration_ImuCorrectionApply(
            sample.accel_b_mps2, sample.gyro_b_radps,
            &correction, corrected_accel_b_mps2,
            corrected_gyro_b_radps) != SYSTEM_DEVICE_OK) ||
        (Air_CompactV0ImuQuantize(corrected_accel_b_mps2,
            corrected_gyro_b_radps, quantized) != AIR_BUILD_OK))
    {
        return 0U;
    }
    s_diagnostics.quantization_saturation_count +=
        quantized->saturation_count;
    return 1U;
}

static uint8_t TelemetryService_PreflightStateSend(void)
{
    float quaternion_wxyz[4];
    SystemAlignmentPreflightAttitudeSource attitude_source;
    AirCompactV0ImuQuantized quantized;
    AirPreflightStatePayload payload;
    uint8_t frame[AIR_PREFLIGHT_STATE_LEN];
    uint8_t length = 0U;
    uint8_t index;
    uint64_t now_us;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((SYSTEM_TELEMETRY_PREFLIGHT_STATE_ENABLE == 0U) ||
        (TelemetryService_IsPreflightState() == 0U))
    {
        return 0U;
    }
    now_us = SystemTime_GetMonotonicUs();
    if ((s_next_preflight_state_us != 0ULL) &&
        (now_us < s_next_preflight_state_us))
    {
        return 0U;
    }
    if ((SystemAlignment_PreflightQuaternionGet(
            quaternion_wxyz, &attitude_source) != SYSTEM_DEVICE_OK) ||
        (TelemetryService_ImuQuantizedGet(&quantized) == 0U))
    {
        return 0U;
    }
    (void)attitude_source;
    (void)memset(&payload, 0, sizeof(payload));
    payload.time_ms = TelemetryService_AirTimeMs();
    for (index = 0U; index < 3U; index++)
    {
        payload.accel_i16[index] = quantized.accel_i16[index];
        payload.gyro_i16[index] = quantized.gyro_i16[index];
    }
    for (index = 0U; index < 4U; index++)
    {
        payload.quaternion_q15[index] =
            TelemetryService_QuaternionToQ15(
                quaternion_wxyz[index]);
    }
    if (Air_PreflightStateBuild(s_tx_sequence++, &payload,
            frame, sizeof(frame), &length) != AIR_BUILD_OK)
    {
        return 0U;
    }
    if (SystemTelemetry_Send(frame, length) != SYSTEM_DEVICE_OK) { return 1U; }
    s_next_preflight_state_us = now_us +
        SYSTEM_TELEMETRY_PREFLIGHT_STATE_PERIOD_US;
    return 1U;
}

static void TelemetryService_StreamSend(void)
{
    EstimatorOutputSnapshot estimator;
    AirCompactV0ImuQuantized quantized;
    AirFlightStatePayload payload;
    uint8_t frame[AIR_FLIGHT_STATE_LEN];
    uint8_t length = 0U;
    uint8_t index;
    uint64_t now_us;
    SystemLifecycleState state = SystemLifecycle_GetState();

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    if ((state != SYSTEM_STATE_FLIGHT) &&
        (state != SYSTEM_STATE_RECOVERY))
    {
        return;
    }
    now_us = SystemTime_GetMonotonicUs();
    if (now_us < s_next_stream_us) { return; }
    if ((TelemetryService_ImuQuantizedGet(&quantized) == 0U) ||
        (Estimator_GetLatestSnapshot(&estimator) == 0U))
    {
        return;
    }
    (void)memset(&payload, 0, sizeof(payload));
    payload.time_ms = TelemetryService_AirTimeMs();
    for (index = 0U; index < 3U; index++)
    {
        payload.accel_i16[index] = quantized.accel_i16[index];
        payload.gyro_i16[index] = quantized.gyro_i16[index];
        payload.velocity_enu_mps[index] = estimator.velocity_enu_mps[index];
        payload.position_enu_m[index] = estimator.position_enu_m[index];
    }
    for (index = 0U; index < 4U; index++)
    {
        payload.quaternion_q15[index] =
            TelemetryService_QuaternionToQ15(estimator.q_nb[index]);
    }
    if ((Air_FlightStateBuild(s_tx_sequence++, &payload,
            frame, sizeof(frame), &length) == AIR_BUILD_OK) &&
        (SystemTelemetry_Send(frame, length) == SYSTEM_DEVICE_OK))
    {
        s_next_stream_us = now_us + SYSTEM_TELEMETRY_STREAM_PERIOD_US;
    }
}

SystemDeviceResult TelemetryService_Init(void)
{
    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    (void)memset(s_status_queue, 0, sizeof(s_status_queue));
    (void)memset(s_ack_queue, 0, sizeof(s_ack_queue));
    (void)memset(s_ack_cache, 0, sizeof(s_ack_cache));
    (void)memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    (void)memset(&s_preflight_status_observed, 0,
                 sizeof(s_preflight_status_observed));
    s_status_head = 0U;
    s_status_tail = 0U;
    s_ack_head = 0U;
    s_ack_tail = 0U;
    s_ack_cache_next = 0U;
    s_capability_ack_known = 0U;
    s_capability_ack_sequence = 0U;
    s_capability_ack_us = 0ULL;
    (void)memset(&s_start_command, 0, sizeof(s_start_command));
    s_tx_sequence = 0U;
    s_start_request_pending = 0U;
    s_start_cmd_sequence = 0U;
    s_locked = 1U;
    s_gnss_state_known = 0U;
    s_gnss_position_usable = 0U;
    s_selftest_event_sent = 0U;
    s_alignment_status_known = 0U;
    s_alignment_state = AIR_ALIGNMENT_STATE_IDLE;
    s_sensor_snapshot_sequence = 0U;
    s_sensor_snapshot_active = 0U;
    s_sensor_snapshot_index = 0U;
    s_sensor_snapshot_total = 0U;
    s_sensor_snapshot_id = 0U;
    s_sensor_snapshot_terminal_pending = 0U;
    s_sensor_snapshot_terminal_state = AIR_ALIGNMENT_STATE_IDLE;
    s_preflight_attitude_source_known = 0U;
    s_preflight_attitude_source =
        SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE;
    s_preflight_attitude_alignment_sequence = 0U;
    s_calibration_status_known = 0U;
    s_calibration_state = AIR_CALIBRATION_STATE_IDLE;
    s_calibration_mode = AIR_CALIBRATION_MODE_NOT_SELECTED;
    s_calibration_face_event_sequence = 0U;
    s_calibration_diagnostic_sequence = 0U;
    s_deploy_event_sequence = 0U;
    s_landing_event_sequence = 0U;
    (void)memset(&s_capability_tx, 0, sizeof(s_capability_tx));
    s_capability_sent = 0U;
    s_capability_send_pending = 1U;
    s_command_policy = SYSTEM_TELEMETRY_COMMAND_POLICY;
    s_preflight_status_send_pending = 0U;
    s_preflight_status_known = 0U;
    s_capability_state = TELEMETRY_CAPABILITY_NOT_ACKED;
    s_next_capability_us = 0ULL;
    s_next_preflight_status_us = 0ULL;
    s_next_preflight_state_us = 0ULL;
    s_next_stream_us = 0ULL;
    return SYSTEM_DEVICE_OK;
}

void TelemetryService_Process(void)
{
    SystemLifecycleState lifecycle_state;

    SILVERSTAR_ASSERT_OBJECT(&s_diagnostics, TelemetryServiceDiagnostics,
        SILVERSTAR_ASSERT_MODULE_MODULES);
    SystemTelemetry_Process();
    TelemetryService_CapabilityTxPoll();
    TelemetryService_StartResponseProcess();
    TelemetryService_ReceiveProcess();

    lifecycle_state = SystemLifecycle_GetState();
    if (((lifecycle_state == SYSTEM_STATE_FLIGHT) ||
         (lifecycle_state == SYSTEM_STATE_RECOVERY) ||
         (lifecycle_state == SYSTEM_STATE_LANDED) ||
         (lifecycle_state == SYSTEM_STATE_POSTFLIGHT)) &&
        (s_capability_state !=
         TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT))
    {
        TelemetryService_PreflightDisable();
    }

    if (TelemetryService_IsPreflightState() != 0U)
    {
        TelemetryService_SelfTestStateProcess();
        TelemetryService_CalibrationStateProcess();
        TelemetryService_AlignmentStateProcess();
    }
    TelemetryService_GnssStateProcess();
    TelemetryService_PreflightStatusStateProcess();
    TelemetryService_FlightRecoveryStateProcess();
    if (TelemetryService_AckSend() != 0U) { return; }
    if (TelemetryService_SensorSnapshotSend() != 0U) { return; }
    if (TelemetryService_SensorSnapshotTerminalSend() != 0U) { return; }
    if (TelemetryService_StatusSend() != 0U) { return; }
    if ((s_capability_state == TELEMETRY_CAPABILITY_NOT_ACKED) &&
        (TelemetryService_CapabilitySend() != 0U)) { return; }
    if (TelemetryService_PreflightStatusSend() != 0U) { return; }
    if (TelemetryService_CapabilitySend() != 0U) { return; }
    if (TelemetryService_PreflightStateSend() != 0U) { return; }
    TelemetryService_StreamSend();
}

void TelemetryService_DiagnosticsGet(TelemetryServiceDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return; }
    *diagnostics = s_diagnostics;
    diagnostics->capability_state = s_capability_state;
    diagnostics->capability_acked = (uint8_t)(
        s_capability_state == TELEMETRY_CAPABILITY_ACKED);
}
