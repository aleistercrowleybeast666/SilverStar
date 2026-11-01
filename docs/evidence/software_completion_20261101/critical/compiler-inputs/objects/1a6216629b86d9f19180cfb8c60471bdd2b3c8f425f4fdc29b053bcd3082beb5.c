#include "system_mission_process.h"
#include "project_mission_process.h"
#include "project_flight_config.h"
#include "system_inertial.h"
#include "system_calibration.h"
#include "system_time.h"
#include "system_lifecycle.h"
#include "system_flight_recovery.h"
#include "estimator_task.h"
#include "ins_task.h"
#include <math.h>
#include <string.h>
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
static uint32_t s_log_sequence;
#endif
static uint32_t s_action_sequence;

static void SystemMissionProcess_AccelerationRead(SystemMissionProcessInput *input)
{
    SystemInertialSample sample;
    SystemCalibrationImuCorrection correction;
    float accel[3];
    float gyro[3];
    if ((SystemInertial_LatestGet(&sample) != SYSTEM_DEVICE_OK) ||
        ((sample.valid_mask & SYSTEM_INERTIAL_VALID_ACCEL) == 0U) ||
        (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK) ||
        (correction.ready == 0U) ||
        (SystemCalibration_ImuCorrectionApply(sample.accel_b_mps2, sample.gyro_b_radps,
            &correction, accel, gyro) != SYSTEM_DEVICE_OK)) { return; }
    input->acceleration_g = sqrtf(accel[0] * accel[0] + accel[1] * accel[1] + accel[2] * accel[2]) / 9.80665f;
    input->acceleration_timestamp_us = sample.sample_timestamp_us;
    input->acceleration_sequence = sample.sequence;
    input->acceleration_source = SystemInertialSample_SourceGet(&sample);
    input->acceleration_epoch = SystemInertialSample_EpochGet(&sample);
    input->valid_mask |= SYSTEM_MISSION_PROCESS_VALID_ACCEL;
}

static void SystemMissionProcess_NavigationRead(SystemMissionProcessInput *input)
{
    EstimatorOutputSnapshot snapshot;
    if ((Estimator_GetLatestSnapshot(&snapshot) == 0U) ||
        (snapshot.initialized == 0U) || (snapshot.mission_running == 0U) ||
        (snapshot.health_flags != ESTIMATOR_HEALTH_NONE)) { return; }
    input->altitude_agl_m = snapshot.position_enu_m[2];
    input->vertical_velocity_mps = snapshot.velocity_enu_mps[2];
    input->navigation_timestamp_us = snapshot.timestamp_us;
    input->navigation_sequence = snapshot.update_sequence;
    input->valid_mask |= SYSTEM_MISSION_PROCESS_VALID_NAV;
    if ((snapshot.timestamp_us != 0U) && (snapshot.timestamp_us <= input->now_us) &&
        (input->now_us - snapshot.timestamp_us <= 100000ULL))
    { input->ready_function_mask |= 8U; input->ready_timestamp_us[1] = snapshot.timestamp_us; }
}

static void SystemMissionProcess_InsRead(SystemMissionProcessInput *input)
{
    InsOutputSnapshot snapshot;
    if ((Ins_GetLatestSnapshot(&snapshot) == 0U) || (snapshot.ins_valid == 0U) ||
        (snapshot.mission_running == 0U) || (snapshot.alignment_valid == 0U) ||
        (snapshot.health_flags != 0U) || (snapshot.timestamp_us == 0U) ||
        (snapshot.timestamp_us > input->now_us) ||
        (input->now_us - snapshot.timestamp_us > 100000ULL)) { return; }
    input->ready_function_mask |= 4U;
    input->ready_timestamp_us[0] = snapshot.timestamp_us;
}

static void SystemMissionProcess_EventsRead(SystemMissionProcessInput *input)
{
    SystemFlightRecoveryStatus status;
    SystemLifecycleState state = SystemLifecycle_GetState();
    input->mission_started = SystemTime_IsMissionStarted();
    if ((state >= SYSTEM_STATE_READY) && (state < SYSTEM_STATE_FAULT)) { input->events |= 1UL; }
    if (input->mission_started != 0U) { input->events |= 2UL; }
    if (SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK)
    {
        if ((status.deploy_triggered != 0U) &&
            ((status.deploy_matched_mask & SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ) != 0U))
        { input->events |= (1UL << 4); }
        if (status.deploy_completed != 0U) { input->events |= (1UL << 5); }
        if (status.landing_detected != 0U) { input->events |= (1UL << 6); }
    }
    if (state == SYSTEM_STATE_POSTFLIGHT) { input->events |= (1UL << 7); }
    input->terminated = (uint8_t)((state == SYSTEM_STATE_POSTFLIGHT) || (state == SYSTEM_STATE_FAULT));
}

static void SystemMissionProcess_ActionsProcess(void)
{
    SystemMissionProcessEvent event;
    uint8_t count;
    for (count = 0U; count < 2U; count++)
    {
        if (SystemMissionProcess_EventGet(s_action_sequence, &event) != SystemMissionProcessResult_Entered) { break; }
        if ((event.event_code == SYSTEM_MISSION_PROCESS_EVENT_ENTER) &&
            (event.stage_id_hash == PROJECT_MISSION_RECOVERY_STAGE_HASH))
        {
            SystemDeviceResult result = SystemFlightRecovery_StageRecoveryRequest(event.stage_id_hash);
            if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_ALREADY_MATCHED))
            { SystemLifecycle_EnterFault(0x4D504143UL); return; }
        }
        s_action_sequence = event.sequence;
    }
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void SystemMissionProcess_LogProcess(void)
{
    SystemMissionProcessEvent event;
    uint8_t count;
    for (count = 0U; count < 2U; count++)
    {
        if (SystemMissionProcess_EventGet(s_log_sequence, &event) != SystemMissionProcessResult_Entered) { break; }
        FlightLogEventId code = (event.event_code == SYSTEM_MISSION_PROCESS_EVENT_ENTER) ?
            FLIGHT_LOG_EVENT_STAGE_ENTER : FLIGHT_LOG_EVENT_STAGE_EXIT;
        if (LoggerBus_EventPush(event.timestamp_us, code, event.stage_id_hash, event.sequence) != LOGGER_BUS_RESULT_OK) { break; }
        s_log_sequence = event.sequence;
    }
}
#endif

void SystemMissionProcess_RuntimeProcess(void)
{
    SystemMissionProcessInput input;
    SystemMissionProcessResult result;
    (void)memset(&input, 0, sizeof(input));
    input.now_us = SystemTime_GetMonotonicUs();
    SystemMissionProcess_EventsRead(&input);
    SystemMissionProcess_AccelerationRead(&input);
    SystemMissionProcess_NavigationRead(&input);
    if ((PROJECT_MISSION_FUNCTION_DEPENDENCIES & 4U) != 0U)
    { SystemMissionProcess_InsRead(&input); }
    result = SystemMissionProcess_Step(&input);
    if (result == SystemMissionProcessResult_Invalid)
    { SystemLifecycle_EnterFault(0x4D505243UL); return; }
    SystemMissionProcess_ActionsProcess();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemMissionProcess_LogProcess();
#endif
}
