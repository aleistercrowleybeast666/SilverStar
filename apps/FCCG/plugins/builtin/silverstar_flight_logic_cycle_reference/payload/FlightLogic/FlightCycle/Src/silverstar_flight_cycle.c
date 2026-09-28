#include "system_lifecycle.h"
#include "system_lifecycle_backend.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_alignment.h"
#include "system_calibration.h"
#include "system_estimator_profile.h"
#include "system_health.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "system_log_policy.h"
#endif
#include "system_navigation_profile.h"
#include "system_output_if.h"
#include "system_profile.h"
#include "system_time.h"

static volatile SystemLifecycleState s_lifecycle_state;
static volatile uint32_t s_fault_reason_mask;
static SystemLifecycleStartRequest s_request_queue[SYSTEM_LIFECYCLE_QUEUE_DEPTH];
static SystemLifecycleStartResponse s_response_queue[SYSTEM_LIFECYCLE_QUEUE_DEPTH];
static volatile uint8_t s_request_head;
static volatile uint8_t s_request_tail;
static volatile uint8_t s_response_head;
static volatile uint8_t s_response_tail;
static volatile uint8_t s_start_request_pending;
static volatile uint8_t s_start_transaction_active;
static SystemLifecycleStartDiagnostic s_start_diagnostics[3];
static uint32_t s_start_diagnostic_sequence;

static uint32_t SystemLifecycle_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemLifecycle_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static uint8_t SystemLifecycle_QueueNext(uint8_t index)
{
    index++;
    return (index >= SYSTEM_LIFECYCLE_QUEUE_DEPTH) ? 0U : index;
}

static void SystemLifecycle_StartRollback(void)
{
    SystemLifecycleBackend_AbortStart();
    SystemTime_MissionReset();
    SystemEstimatorProfile_UnfreezeForRollback();
    SystemNavigationProfile_UnfreezeForRollback();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemLogPolicy_UnfreezeForRollback();
#endif
    SystemProfile_UnfreezeForRollback();
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
}

static SystemLifecycleStartReason SystemLifecycle_AttitudeReasonMap(
    SystemHealthAttitudeStatus status)
{
    SystemLifecycleStartReason reason;

    SILVERSTAR_ASSERT(status <= SYSTEM_HEALTH_ATTITUDE_STALE,
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (status)
    {
        case SYSTEM_HEALTH_ATTITUDE_UNKNOWN:
        case SYSTEM_HEALTH_ATTITUDE_READY:
            reason = SYSTEM_START_REASON_SYSTEM_NOT_READY;
            break;
        case SYSTEM_HEALTH_ATTITUDE_CALIBRATION_NOT_READY:
            reason = SYSTEM_START_REASON_CALIBRATION_REQUIRED;
            break;
        case SYSTEM_HEALTH_ATTITUDE_SOURCE_UNAVAILABLE:
        case SYSTEM_HEALTH_ATTITUDE_NO_SAMPLE:
            reason = SYSTEM_START_REASON_ATTITUDE_NOT_READY;
            break;
        case SYSTEM_HEALTH_ATTITUDE_INVALID:
            reason = SYSTEM_START_REASON_ATTITUDE_INVALID;
            break;
        case SYSTEM_HEALTH_ATTITUDE_STALE:
            reason = SYSTEM_START_REASON_ATTITUDE_STALE;
            break;
        default:
            reason = SYSTEM_START_REASON_SYSTEM_NOT_READY;
            break;
    }
    SILVERSTAR_ASSERT(
        (reason == SYSTEM_START_REASON_CALIBRATION_REQUIRED) ||
        ((reason >= SYSTEM_START_REASON_ATTITUDE_NOT_READY) &&
         (reason <= SYSTEM_START_REASON_SYSTEM_NOT_READY)),
        SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
        SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return reason;
}

static SystemLifecycleStartReason SystemLifecycle_AttitudeReasonGet(void)
{
    SystemHealthSnapshot health;

    SystemHealth_GetSnapshot(&health);
    return SystemLifecycle_AttitudeReasonMap(health.attitude_status);
}

static SystemLifecycleStartResult SystemLifecycle_StartPreconditionsGet(
    SystemLifecycleStartReason *reason)
{
    SILVERSTAR_ASSERT(s_lifecycle_state <= SYSTEM_STATE_FAULT,
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((s_start_request_pending <= 1U) &&
                      (s_start_transaction_active <= 1U),
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (reason != NULL) { *reason = SYSTEM_START_REASON_NONE; }
    if ((s_lifecycle_state == SYSTEM_STATE_FLIGHT) ||
        (s_lifecycle_state == SYSTEM_STATE_RECOVERY) ||
        (s_lifecycle_state == SYSTEM_STATE_LANDED) ||
        (s_lifecycle_state == SYSTEM_STATE_POSTFLIGHT) ||
        (s_lifecycle_state == SYSTEM_STATE_FAULT))
    {
        if (reason != NULL) { *reason = SYSTEM_START_REASON_LOCKED; }
        return SYSTEM_LIFECYCLE_START_LOCKED;
    }
    if (SystemCalibration_IsReady() == 0U)
    {
        if (reason != NULL)
        {
            *reason = SYSTEM_START_REASON_CALIBRATION_REQUIRED;
        }
        return SYSTEM_LIFECYCLE_START_NOT_READY;
    }
    if (SystemAlignment_IsReady() == 0U)
    {
        if (reason != NULL)
        {
            *reason = SYSTEM_START_REASON_ALIGNMENT_REQUIRED;
        }
        return SYSTEM_LIFECYCLE_START_NOT_READY;
    }
    if ((s_lifecycle_state != SYSTEM_STATE_READY) ||
        (SystemHealth_IsReady() == 0U))
    {
        if (reason != NULL)
        {
            *reason = SystemLifecycle_AttitudeReasonGet();
        }
        return SYSTEM_LIFECYCLE_START_NOT_READY;
    }
    return SYSTEM_LIFECYCLE_START_OK;
}

static void SystemLifecycle_DiagnosticStore(
    const SystemLifecycleStartResponse *response)
{
    SystemLifecycleStartDiagnostic *diagnostic;

    if ((response == NULL) || (response->source > SYSTEM_START_SOURCE_LOCAL))
    {
        return;
    }
    diagnostic = &s_start_diagnostics[(uint8_t)response->source];
    diagnostic->response = *response;
    diagnostic->sequence = ++s_start_diagnostic_sequence;
    diagnostic->valid = 1U;
}

void SystemLifecycle_Init(void)
{
    s_lifecycle_state = SYSTEM_STATE_BOOT;
    s_fault_reason_mask = 0U;
    s_request_head = 0U;
    s_request_tail = 0U;
    s_response_head = 0U;
    s_response_tail = 0U;
    s_start_request_pending = 0U;
    s_start_transaction_active = 0U;
    s_start_diagnostic_sequence = 0U;
    (void)memset(s_start_diagnostics, 0, sizeof(s_start_diagnostics));
}

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return s_lifecycle_state;
}

SystemDeviceResult SystemLifecycle_EnterSelfTest(void)
{
    if (s_lifecycle_state != SYSTEM_STATE_BOOT)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_lifecycle_state = SYSTEM_STATE_SELF_TEST;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemLifecycle_EnterPreflight(void)
{
    if ((s_lifecycle_state != SYSTEM_STATE_SELF_TEST) &&
        (s_lifecycle_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemLifecycle_EnterReady(void)
{
    if ((s_lifecycle_state == SYSTEM_STATE_FLIGHT) ||
        (s_lifecycle_state == SYSTEM_STATE_RECOVERY) ||
        (s_lifecycle_state == SYSTEM_STATE_FAULT))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (SystemHealth_IsReady() == 0U)
    {
        s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
        return SYSTEM_DEVICE_NOT_READY;
    }
    s_lifecycle_state = SYSTEM_STATE_READY;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemLifecycle_EnterRecovery(void)
{
    if (s_lifecycle_state != SYSTEM_STATE_FLIGHT)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemLifecycle_EnterLanded(void)
{
    if ((s_lifecycle_state != SYSTEM_STATE_FLIGHT) &&
        (s_lifecycle_state != SYSTEM_STATE_RECOVERY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_lifecycle_state = SYSTEM_STATE_LANDED;
    SystemTime_MissionStop(SystemTime_GetMonotonicUs());
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemLifecycle_EnterPostflight(void)
{
    if (s_lifecycle_state != SYSTEM_STATE_LANDED)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_lifecycle_state = SYSTEM_STATE_POSTFLIGHT;
    return SYSTEM_DEVICE_OK;
}

void SystemLifecycle_EnterFault(uint32_t reason_mask)
{
    s_fault_reason_mask |= reason_mask;
    s_lifecycle_state = SYSTEM_STATE_FAULT;
    (void)SystemOutput_SafeSet();
    if (SystemTime_IsMissionStarted() != 0U)
    {
        SystemTime_MissionStop(SystemTime_GetMonotonicUs());
    }
}

uint32_t SystemLifecycle_GetFaultReason(void)
{
    return s_fault_reason_mask;
}

SystemLifecycleStartResult SystemLifecycle_StartReadinessGet(
    SystemLifecycleStartReason *reason)
{
    uint8_t busy;
    uint32_t primask = SystemLifecycle_IrqLock();

    busy = (uint8_t)((s_start_request_pending != 0U) ||
                     (s_start_transaction_active != 0U));
    SystemLifecycle_IrqUnlock(primask);
    if (busy != 0U)
    {
        if (reason != NULL) { *reason = SYSTEM_START_REASON_REQUEST_PENDING; }
        return SYSTEM_LIFECYCLE_START_BUSY;
    }
    return SystemLifecycle_StartPreconditionsGet(reason);
}

static void SystemLifecycle_MissionProfilesFreeze(void)
{
    SystemProfile_Freeze();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemLogPolicy_Freeze();
#endif
    SystemNavigationProfile_Freeze();
    SystemEstimatorProfile_Freeze();
    SystemTime_MissionStart(SystemTime_GetMonotonicUs());
}

static SystemLifecycleStartResult SystemLifecycle_StartExecute(
    SystemLifecycleStartReason *reason)
{
    SystemDeviceResult prepare_result;
    SystemLifecycleStartResult readiness_result;

    SILVERSTAR_ASSERT(s_lifecycle_state <= SYSTEM_STATE_FAULT,
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(s_start_transaction_active <= 1U,
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    readiness_result = SystemLifecycle_StartPreconditionsGet(reason);
    if (readiness_result != SYSTEM_LIFECYCLE_START_OK)
    {
        return readiness_result;
    }
    prepare_result = SystemLifecycleBackend_PrepareStart();
    if (prepare_result != SYSTEM_DEVICE_OK)
    {
        if (prepare_result == SYSTEM_DEVICE_NOT_READY)
        {
            if (reason != NULL)
            {
                *reason = SystemLifecycle_AttitudeReasonGet();
            }
            return SYSTEM_LIFECYCLE_START_NOT_READY;
        }
        if (reason != NULL) { *reason = SYSTEM_START_REASON_PREPARE_FAILED; }
        return SYSTEM_LIFECYCLE_START_PREPARE_FAILED;
    }
    if (SystemLifecycleBackend_FreezeOrigins() != SYSTEM_DEVICE_OK)
    {
        SystemLifecycleBackend_AbortStart();
        if (reason != NULL) { *reason = SYSTEM_START_REASON_ORIGIN_FAILED; }
        return SYSTEM_LIFECYCLE_START_ORIGIN_FAILED;
    }

    SystemLifecycle_MissionProfilesFreeze();

    if (SystemLifecycleBackend_InitializeNavigation() != SYSTEM_DEVICE_OK)
    {
        SystemLifecycle_StartRollback();
        if (reason != NULL)
        {
            *reason = SYSTEM_START_REASON_NAVIGATION_FAILED;
        }
        return SYSTEM_LIFECYCLE_START_NAVIGATION_FAILED;
    }
    if (SystemLifecycleBackend_ResetFlightQueues() != SYSTEM_DEVICE_OK)
    {
        SystemLifecycle_StartRollback();
        if (reason != NULL) { *reason = SYSTEM_START_REASON_QUEUE_FAILED; }
        return SYSTEM_LIFECYCLE_START_QUEUE_FAILED;
    }
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    return SYSTEM_LIFECYCLE_START_OK;
}

SystemLifecycleStartResult SystemLifecycle_StartTransaction(void)
{
    SystemLifecycleStartResponse response;
    uint32_t primask = SystemLifecycle_IrqLock();

    SILVERSTAR_ASSERT(s_start_request_pending <= 1U,
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_start_transaction_active <= 1U,
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((s_start_request_pending != 0U) ||
        (s_start_transaction_active != 0U))
    {
        SystemLifecycle_IrqUnlock(primask);
        return SYSTEM_LIFECYCLE_START_BUSY;
    }
    s_start_transaction_active = 1U;
    SystemLifecycle_IrqUnlock(primask);

    response.source = SYSTEM_START_SOURCE_LOCAL;
    response.request_id = 0U;
    response.timestamp_us = SystemTime_GetMonotonicUs();
    response.result = SystemLifecycle_StartExecute(&response.reason);

    primask = SystemLifecycle_IrqLock();
    SystemLifecycle_DiagnosticStore(&response);
    s_start_transaction_active = 0U;
    SystemLifecycle_IrqUnlock(primask);
    return response.result;
}

SystemDeviceResult SystemLifecycle_SubmitStart(
    const SystemLifecycleStartRequest *request)
{
    SystemLifecycleStartResponse response;
    uint8_t next_head;
    uint32_t primask;

    if ((request == NULL) || (request->source > SYSTEM_START_SOURCE_LOCAL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(request, SystemLifecycleStartRequest,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    response.source = request->source;
    response.request_id = request->request_id;
    response.timestamp_us = SystemTime_GetMonotonicUs();
    response.result = SYSTEM_LIFECYCLE_START_BUSY;
    response.reason = SYSTEM_START_REASON_REQUEST_PENDING;
    primask = SystemLifecycle_IrqLock();
    if ((s_start_request_pending != 0U) ||
        (s_start_transaction_active != 0U))
    {
        SystemLifecycle_DiagnosticStore(&response);
        SystemLifecycle_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    next_head = SystemLifecycle_QueueNext(s_request_head);
    if (next_head == s_request_tail)
    {
        SystemLifecycle_DiagnosticStore(&response);
        SystemLifecycle_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    s_request_queue[s_request_head] = *request;
    s_request_head = next_head;
    s_start_request_pending = 1U;
    SystemLifecycle_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemLifecycle_TryGetStartResponse(
    SystemLifecycleStartResponse *response)
{
    if ((response == NULL) || (s_response_tail == s_response_head))
    {
        return 0U;
    }
    *response = s_response_queue[s_response_tail];
    s_response_tail = SystemLifecycle_QueueNext(s_response_tail);
    return 1U;
}

uint8_t SystemLifecycle_GetLastStartDiagnostic(
    SystemStartSource source,
    SystemLifecycleStartDiagnostic *diagnostic)
{
    uint32_t primask;

    if ((diagnostic == NULL) || (source > SYSTEM_START_SOURCE_LOCAL))
    {
        return 0U;
    }
    primask = SystemLifecycle_IrqLock();
    *diagnostic = s_start_diagnostics[(uint8_t)source];
    SystemLifecycle_IrqUnlock(primask);
    return diagnostic->valid;
}

void SystemLifecycle_Process(void)
{
    SystemLifecycleStartRequest request;
    SystemLifecycleStartResponse response;
    uint8_t next_head;
    uint32_t primask;

    primask = SystemLifecycle_IrqLock();
    SILVERSTAR_ASSERT((s_request_head < SYSTEM_LIFECYCLE_QUEUE_DEPTH) &&
                      (s_request_tail < SYSTEM_LIFECYCLE_QUEUE_DEPTH),
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_response_head < SYSTEM_LIFECYCLE_QUEUE_DEPTH) &&
                      (s_response_tail < SYSTEM_LIFECYCLE_QUEUE_DEPTH),
                      SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
                      SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (s_request_tail == s_request_head)
    {
        SystemLifecycle_IrqUnlock(primask);
        return;
    }
    request = s_request_queue[s_request_tail];
    s_request_tail = SystemLifecycle_QueueNext(s_request_tail);
    s_start_transaction_active = 1U;
    SystemLifecycle_IrqUnlock(primask);

    response.source = request.source;
    response.request_id = request.request_id;
    response.timestamp_us = SystemTime_GetMonotonicUs();
    response.result = SystemLifecycle_StartExecute(&response.reason);

    primask = SystemLifecycle_IrqLock();
    SystemLifecycle_DiagnosticStore(&response);
    next_head = SystemLifecycle_QueueNext(s_response_head);
    if (next_head != s_response_tail)
    {
        s_response_queue[s_response_head] = response;
        s_response_head = next_head;
    }
    s_start_transaction_active = 0U;
    s_start_request_pending = 0U;
    SystemLifecycle_IrqUnlock(primask);
}

const char *SystemLifecycle_StartResultText(SystemLifecycleStartResult result)
{
    switch (result)
    {
        case SYSTEM_LIFECYCLE_START_OK: return "OK";
        case SYSTEM_LIFECYCLE_START_BUSY: return "BUSY";
        case SYSTEM_LIFECYCLE_START_NOT_READY: return "NOT_READY";
        case SYSTEM_LIFECYCLE_START_LOCKED: return "LOCKED";
        case SYSTEM_LIFECYCLE_START_PREPARE_FAILED: return "PREPARE_FAILED";
        case SYSTEM_LIFECYCLE_START_ORIGIN_FAILED: return "ORIGIN_FAILED";
        case SYSTEM_LIFECYCLE_START_NAVIGATION_FAILED:
            return "NAVIGATION_FAILED";
        case SYSTEM_LIFECYCLE_START_QUEUE_FAILED: return "QUEUE_FAILED";
        case SYSTEM_LIFECYCLE_START_INTERNAL_ERROR:
        default: return "INTERNAL_ERROR";
    }
}

static const char *SystemLifecycle_StartReadinessReasonText(
    SystemLifecycleStartReason reason)
{
    switch ((uint32_t)reason)
    {
        case SYSTEM_START_REASON_NONE: return "NONE";
        case SYSTEM_START_REASON_REQUEST_PENDING: return "REQUEST_PENDING";
        case SYSTEM_START_REASON_CALIBRATION_REQUIRED:
            return "CALIBRATION_REQUIRED";
        case SYSTEM_START_REASON_ALIGNMENT_REQUIRED:
            return "ALIGNMENT_REQUIRED";
        case SYSTEM_START_REASON_ATTITUDE_NOT_READY:
            return "ATTITUDE_NOT_READY";
        case SYSTEM_START_REASON_ATTITUDE_INVALID: return "ATTITUDE_INVALID";
        case SYSTEM_START_REASON_ATTITUDE_STALE: return "ATTITUDE_STALE";
        case SYSTEM_START_REASON_SYSTEM_NOT_READY: return "SYSTEM_NOT_READY";
        default: return NULL;
    }
}

static const char *SystemLifecycle_StartExecutionReasonText(
    SystemLifecycleStartReason reason)
{
    switch ((uint32_t)reason)
    {
        case SYSTEM_START_REASON_LOCKED: return "LOCKED";
        case SYSTEM_START_REASON_HOOKS_UNAVAILABLE:
            return "HOOKS_UNAVAILABLE";
        case SYSTEM_START_REASON_PREPARE_FAILED: return "PREPARE_FAILED";
        case SYSTEM_START_REASON_ORIGIN_FAILED: return "ORIGIN_FAILED";
        case SYSTEM_START_REASON_NAVIGATION_FAILED:
            return "NAVIGATION_FAILED";
        case SYSTEM_START_REASON_QUEUE_FAILED: return "QUEUE_FAILED";
        default: return "UNKNOWN";
    }
}

const char *SystemLifecycle_StartReasonText(SystemLifecycleStartReason reason)
{
    const char *text = SystemLifecycle_StartReadinessReasonText(reason);

    if (text != NULL)
    {
        return text;
    }
    return SystemLifecycle_StartExecutionReasonText(reason);
}

uint8_t SystemLifecycle_IsConfigurationLocked(void)
{
    return (uint8_t)((s_lifecycle_state == SYSTEM_STATE_FLIGHT) ||
                     (s_lifecycle_state == SYSTEM_STATE_RECOVERY));
}
