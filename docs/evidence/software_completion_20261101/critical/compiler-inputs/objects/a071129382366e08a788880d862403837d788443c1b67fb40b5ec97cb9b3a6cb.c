/* Compile the owning runtime, inject provider failures, observe publication and
 * retry. No generated wrapper or replacement mission runtime is under test. */
#include "system_mission_process_runtime.c"
#include <assert.h>
#include <stdio.h>

static const char *s_mode;
static uint32_t s_fault;
static uint32_t s_event_reads;
static uint32_t s_actions;
static uint32_t s_log_attempts;
static uint32_t s_log_accepted;
static LoggerBusResult s_log_result = LOGGER_BUS_RESULT_OK;

uint64_t SystemTime_GetMonotonicUs(void) { return 123U; }
uint8_t SystemTime_IsMissionStarted(void) { return 1U; }
SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_READY; }
void SystemLifecycle_EnterFault(uint32_t reason)
{ assert(s_fault == 0U); s_fault = reason; }
SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{ (void)sample; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemCalibration_ImuCorrectionGet(SystemCalibrationImuCorrection *correction)
{ (void)correction; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemCalibration_ImuCorrectionApply(const float accel[3], const float gyro[3],
    const SystemCalibrationImuCorrection *correction, float corrected_accel[3], float corrected_gyro[3])
{
    (void)accel; (void)gyro; (void)correction; (void)corrected_accel; (void)corrected_gyro;
    return SYSTEM_DEVICE_NOT_READY;
}
uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{ (void)snapshot; return 0U; }
uint8_t Ins_GetLatestSnapshot(InsOutputSnapshot *snapshot)
{ (void)snapshot; return 0U; }
SystemDeviceResult SystemFlightRecovery_StatusGet(SystemFlightRecoveryStatus *status)
{ (void)status; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemFlightRecovery_StageRecoveryRequest(uint32_t identity)
{
    assert(identity == PROJECT_MISSION_RECOVERY_STAGE_HASH);
    s_actions++;
    return strcmp(s_mode, "action-error") == 0 ? SYSTEM_DEVICE_NOT_READY : SYSTEM_DEVICE_OK;
}
LoggerBusResult LoggerBus_EventPush(uint64_t timestamp, FlightLogEventId event,
    uint32_t arg0, uint32_t arg1)
{
    assert(timestamp == 123U && arg0 == PROJECT_MISSION_RECOVERY_STAGE_HASH);
    assert(arg1 == s_log_accepted + 1U);
    assert(event == (arg1 == 1U ? FLIGHT_LOG_EVENT_STAGE_ENTER : FLIGHT_LOG_EVENT_STAGE_EXIT));
    s_log_attempts++;
    if (s_log_result == LOGGER_BUS_RESULT_OK) { s_log_accepted++; }
    return s_log_result;
}
SystemMissionProcessResult SystemMissionProcess_Step(const SystemMissionProcessInput *input)
{
    assert(input->now_us == 123U);
    return strcmp(s_mode, "step-invalid") == 0 ?
        SystemMissionProcessResult_Invalid : SystemMissionProcessResult_Waiting;
}
SystemMissionProcessResult SystemMissionProcess_EventGet(uint32_t after,
    SystemMissionProcessEvent *event)
{
    s_event_reads++;
    if ((strcmp(s_mode, "events-invalid") == 0) ||
        ((strcmp(s_mode, "log-events-invalid") == 0) && (s_event_reads > 2U)))
    { return SystemMissionProcessResult_Invalid; }
    if ((strcmp(s_mode, "no-events") == 0) || (after >= 2U))
    { return SystemMissionProcessResult_Unavailable; }
    event->timestamp_us = 123U; event->sequence = after + 1U;
    event->stage_id_hash = PROJECT_MISSION_RECOVERY_STAGE_HASH;
    event->event_code = after == 0U ? SYSTEM_MISSION_PROCESS_EVENT_ENTER : SYSTEM_MISSION_PROCESS_EVENT_EXIT;
    return SystemMissionProcessResult_Entered;
}

int main(int argc, char **argv)
{
    assert(argc == 2); s_mode = argv[1];
    if (strcmp(s_mode, "log-full") == 0) { s_log_result = LOGGER_BUS_RESULT_FULL; }
    if (strcmp(s_mode, "log-busy") == 0) { s_log_result = LOGGER_BUS_RESULT_BUSY; }
    if (strcmp(s_mode, "log-not-ready") == 0) { s_log_result = LOGGER_BUS_RESULT_BAD_STATE; }
    if (strcmp(s_mode, "log-bad-param") == 0) { s_log_result = LOGGER_BUS_RESULT_BAD_PARAM; }
    SystemMissionProcess_RuntimeProcess();
    if (strcmp(s_mode, "events-invalid") == 0)
    { assert(s_fault == 0x4D504143UL && s_actions == 0U && s_log_attempts == 0U && s_action_sequence == 0U); }
    else if (strcmp(s_mode, "action-error") == 0)
    { assert(s_fault == 0x4D504143UL && s_actions == 1U && s_log_attempts == 0U && s_action_sequence == 0U); }
    else if (strcmp(s_mode, "log-events-invalid") == 0)
    { assert(s_fault == 0x4D504C47UL && s_log_attempts == 0U && s_log_sequence == 0U); }
    else if (strcmp(s_mode, "log-bad-param") == 0)
    { assert(s_fault == 0x4D504C47UL && s_log_attempts == 1U && s_log_sequence == 0U); }
    else if (strcmp(s_mode, "step-invalid") == 0)
    { assert(s_fault == 0x4D505243UL && s_event_reads == 0U); }
    else if (strcmp(s_mode, "no-events") == 0)
    { assert(s_fault == 0U && s_actions == 0U && s_log_attempts == 0U && s_event_reads == 2U); }
    else
    {
        assert(s_fault == 0U && s_actions == 1U && s_action_sequence == 2U);
        if (s_log_result != LOGGER_BUS_RESULT_OK)
        { assert(s_log_sequence == 0U && s_log_accepted == 0U && s_log_attempts == 1U); }
        else { assert(s_log_sequence == 2U && s_log_accepted == 2U); }
        s_log_result = LOGGER_BUS_RESULT_OK;
        SystemMissionProcess_RuntimeProcess();
        assert(s_fault == 0U && s_actions == 1U && s_log_sequence == 2U && s_log_accepted == 2U);
    }
    printf("runtime error propagation and bounded retry: %s PASS\n", s_mode);
    return 0;
}
