#include <stdint.h>
#include <string.h>

#include "system_alignment.h"
#include "system_calibration.h"
#include "system_health.h"
#include "system_lifecycle.h"
#include "system_output_if.h"
#include "test_common.h"

static uint8_t s_ready;
static uint64_t s_now_us;
static uint64_t s_mission_start_us;
static uint64_t s_mission_stop_us;
static uint8_t s_mission_started;
static uint8_t s_profile_frozen;
static uint8_t s_log_frozen;
static uint8_t s_navigation_frozen;
static uint8_t s_estimator_frozen;
static uint32_t s_safe_count;
static uint32_t s_prepare_count;
static uint32_t s_origin_count;
static uint32_t s_navigation_count;
static uint32_t s_queue_count;
static uint32_t s_abort_count;
static uint8_t s_fail_stage;
static SystemDeviceResult s_prepare_result;
static SystemHealthAttitudeStatus s_attitude_status;
static uint8_t s_calibration_ready;
static uint8_t s_storage_ready;
static SystemAlignmentStatus s_alignment_status;

uint8_t SystemCalibration_IsReady(void) { return s_calibration_ready; }
uint8_t SystemAlignment_IsReady(void) { return s_alignment_status.ready; }

uint8_t SystemHealth_IsReady(void) { return s_ready; }
void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot)
{
    if (snapshot != NULL)
    {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->ready = s_ready;
        snapshot->attitude_status = s_attitude_status;
    }
}
uint64_t SystemTime_GetMonotonicUs(void) { return ++s_now_us; }
uint8_t SystemTime_IsMissionStarted(void) { return s_mission_started; }
void SystemTime_MissionStart(uint64_t timestamp_us)
{
    if (s_mission_started == 0U)
    {
        s_mission_started = 1U;
        s_mission_start_us = timestamp_us;
    }
}
void SystemTime_MissionStop(uint64_t timestamp_us)
{
    s_mission_stop_us = timestamp_us;
}
void SystemTime_MissionReset(void)
{
    s_mission_started = 0U;
    s_mission_start_us = 0U;
    s_mission_stop_us = 0U;
}

void SystemProfile_Freeze(void) { s_profile_frozen = 1U; }
void SystemProfile_UnfreezeForRollback(void) { s_profile_frozen = 0U; }
void SystemLogPolicy_Freeze(void) { s_log_frozen = 1U; }
void SystemLogPolicy_UnfreezeForRollback(void) { s_log_frozen = 0U; }
void SystemNavigationProfile_Freeze(void) { s_navigation_frozen = 1U; }
void SystemNavigationProfile_UnfreezeForRollback(void) { s_navigation_frozen = 0U; }
void SystemEstimatorProfile_Freeze(void) { s_estimator_frozen = 1U; }
void SystemEstimatorProfile_UnfreezeForRollback(void) { s_estimator_frozen = 0U; }

SystemDeviceResult SystemOutput_SafeSet(void)
{
    s_safe_count++;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Hook_Prepare(void)
{
    s_prepare_count++;
    return (s_fail_stage == 1U) ? s_prepare_result : SYSTEM_DEVICE_OK;
}
static SystemDeviceResult Hook_Origins(void)
{
    s_origin_count++;
    return (s_fail_stage == 2U) ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK;
}
static SystemDeviceResult Hook_Navigation(void)
{
    s_navigation_count++;
    return (s_fail_stage == 3U) ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK;
}
static SystemDeviceResult Hook_Queues(void)
{
    s_queue_count++;
    return (s_fail_stage == 4U) ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK;
}
static void Hook_Abort(void) { s_abort_count++; }

SystemDeviceResult SystemLifecycleBackend_PrepareStart(void)
{ return Hook_Prepare(); }
SystemDeviceResult SystemLifecycleBackend_FreezeOrigins(void)
{ return Hook_Origins(); }
SystemDeviceResult SystemLifecycleBackend_InitializeNavigation(void)
{ return Hook_Navigation(); }
SystemDeviceResult SystemLifecycleBackend_ResetFlightQueues(void)
{ return Hook_Queues(); }
uint8_t SystemLifecycleBackend_StorageReadyGet(void)
{ return s_storage_ready; }
void SystemLifecycleBackend_AbortStart(void) { Hook_Abort(); }

static void Test_StateReset(void)
{
    s_ready = 1U;
    s_now_us = 1000U;
    SystemTime_MissionReset();
    s_profile_frozen = 0U;
    s_log_frozen = 0U;
    s_navigation_frozen = 0U;
    s_estimator_frozen = 0U;
    s_prepare_count = 0U;
    s_origin_count = 0U;
    s_navigation_count = 0U;
    s_queue_count = 0U;
    s_abort_count = 0U;
    s_fail_stage = 0U;
    s_prepare_result = SYSTEM_DEVICE_IO_ERROR;
    s_attitude_status = SYSTEM_HEALTH_ATTITUDE_READY;
    s_calibration_ready = 1U;
    s_storage_ready = 1U;
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    SystemLifecycle_Init();
    TEST_CHECK(SystemLifecycle_EnterSelfTest() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterPreflight() == SYSTEM_DEVICE_OK);
}

static void Test_StartTransaction(void)
{
    Test_StateReset();
    s_ready = 0U;
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_NOT_READY);
    s_ready = 1U;
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_OK);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(s_prepare_count == 1U && s_origin_count == 1U &&
               s_navigation_count == 1U && s_queue_count == 1U);
    TEST_CHECK(s_profile_frozen != 0U && s_navigation_frozen != 0U && s_estimator_frozen != 0U);
    TEST_CHECK(s_log_frozen == (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U ? 1U : 0U));
    TEST_CHECK(s_mission_started != 0U && s_mission_start_us != 0U);
    TEST_CHECK(SystemLifecycle_IsConfigurationLocked() != 0U);
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_LOCKED);
    TEST_CHECK(s_prepare_count == 1U);
}

static void Test_Rollback(void)
{
    Test_StateReset();
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    s_fail_stage = 3U;
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_NAVIGATION_FAILED);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_PREFLIGHT);
    TEST_CHECK(s_abort_count == 1U);
    TEST_CHECK(s_mission_started == 0U);
    TEST_CHECK(s_profile_frozen == 0U && s_log_frozen == 0U &&
               s_navigation_frozen == 0U && s_estimator_frozen == 0U);
    TEST_CHECK(SystemLifecycle_IsConfigurationLocked() == 0U);

    Test_StateReset();
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    s_fail_stage = 2U;
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_ORIGIN_FAILED);
    TEST_CHECK(s_abort_count == 1U);
    TEST_CHECK(s_navigation_count == 0U);
    TEST_CHECK(s_mission_started == 0U);
}

static void Test_RequestQueueAndFault(void)
{
    SystemLifecycleStartRequest request;
    SystemLifecycleStartResponse response;

    Test_StateReset();
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    request.source = SYSTEM_START_SOURCE_AIR;
    request.request_id = 42U;
    TEST_CHECK(SystemLifecycle_SubmitStart(&request) == SYSTEM_DEVICE_OK);
    SystemLifecycle_Process();
    TEST_CHECK(SystemLifecycle_TryGetStartResponse(&response) != 0U);
    TEST_CHECK(response.request_id == 42U);
    TEST_CHECK(response.result == SYSTEM_LIFECYCLE_START_OK);
    TEST_CHECK(response.reason == SYSTEM_START_REASON_NONE);
    TEST_CHECK(s_prepare_count == 1U);
    SystemLifecycle_Process();
    TEST_CHECK(s_prepare_count == 1U);

    SystemLifecycle_EnterFault(0x10U);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FAULT);
    TEST_CHECK(SystemLifecycle_GetFaultReason() == 0x10U);
    TEST_CHECK(s_safe_count != 0U);
    TEST_CHECK(s_mission_stop_us != 0U);
}

static void Test_StartReasonsAndPending(void)
{
    SystemLifecycleStartDiagnostic diagnostic;
    SystemLifecycleStartRequest request;
    SystemLifecycleStartReason readiness_reason;

    Test_StateReset();
    s_ready = 0U;
    s_calibration_ready = 0U;
    s_attitude_status = SYSTEM_HEALTH_ATTITUDE_CALIBRATION_NOT_READY;
    TEST_CHECK(SystemLifecycle_StartReadinessGet(&readiness_reason) ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(readiness_reason ==
               SYSTEM_START_REASON_CALIBRATION_REQUIRED);
    TEST_CHECK(s_prepare_count == 0U);
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_LOCAL, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.reason ==
               SYSTEM_START_REASON_CALIBRATION_REQUIRED);

    Test_StateReset();
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_alignment_status.ready = 0U;
    TEST_CHECK(SystemLifecycle_StartReadinessGet(&readiness_reason) ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(readiness_reason == SYSTEM_START_REASON_ALIGNMENT_REQUIRED);
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_LOCAL, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.reason ==
               SYSTEM_START_REASON_ALIGNMENT_REQUIRED);

    Test_StateReset();
    s_storage_ready = 0U;
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartReadinessGet(&readiness_reason) ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(readiness_reason == SYSTEM_START_REASON_STORAGE_NOT_READY);
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(s_prepare_count == 0U && s_mission_started == 0U);
    s_storage_ready = 1U;
    TEST_CHECK(SystemLifecycle_StartReadinessGet(&readiness_reason) ==
               SYSTEM_LIFECYCLE_START_OK);

    Test_StateReset();
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_STALE;
    s_alignment_status.ready = 0U;
    s_alignment_status.ready_mask =
        SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
        SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN;
    TEST_CHECK(SystemLifecycle_StartReadinessGet(&readiness_reason) ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(readiness_reason == SYSTEM_START_REASON_ALIGNMENT_REQUIRED);
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_LOCAL, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.reason ==
               SYSTEM_START_REASON_ALIGNMENT_REQUIRED);

    Test_StateReset();
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    s_fail_stage = 1U;
    s_prepare_result = SYSTEM_DEVICE_NOT_READY;
    s_attitude_status = SYSTEM_HEALTH_ATTITUDE_STALE;
    TEST_CHECK(SystemLifecycle_StartTransaction() ==
               SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_LOCAL, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.reason ==
               SYSTEM_START_REASON_ATTITUDE_STALE);

    Test_StateReset();
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    request.source = SYSTEM_START_SOURCE_CONSOLE;
    request.request_id = 7U;
    TEST_CHECK(SystemLifecycle_SubmitStart(&request) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartReadinessGet(&readiness_reason) ==
               SYSTEM_LIFECYCLE_START_BUSY);
    TEST_CHECK(readiness_reason == SYSTEM_START_REASON_REQUEST_PENDING);
    request.request_id = 8U;
    TEST_CHECK(SystemLifecycle_SubmitStart(&request) == SYSTEM_DEVICE_BUSY);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_CONSOLE, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.result == SYSTEM_LIFECYCLE_START_BUSY);
    TEST_CHECK(diagnostic.response.reason ==
               SYSTEM_START_REASON_REQUEST_PENDING);
    SystemLifecycle_Process();
}

int main(void)
{
    Test_StartTransaction();
    Test_Rollback();
    Test_RequestQueueAndFault();
    Test_StartReasonsAndPending();
    return Test_Finish("lifecycle");
}
