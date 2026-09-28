#include "system_flight_recovery.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "flight_deployment.h"
#include "flight_landing.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_lifecycle.h"
#include "system_mission_action_if.h"
#include "system_user_config.h"

_Static_assert((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK &
                ~SYSTEM_DEPLOY_TRIGGER_MASK_ALL) == 0U,
               "invalid SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK");
_Static_assert((SYSTEM_FLIGHT_TILT_REFERENCE ==
                SYSTEM_TILT_REFERENCE_INITIAL_AXIS) ||
               (SYSTEM_FLIGHT_TILT_REFERENCE ==
                SYSTEM_TILT_REFERENCE_NAV_UP),
               "invalid SYSTEM_FLIGHT_TILT_REFERENCE");
_Static_assert((SYSTEM_FLIGHT_LANDING_MODE ==
                SYSTEM_LANDING_MODE_STILLNESS) ||
               (SYSTEM_FLIGHT_LANDING_MODE ==
                SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS) ||
               (SYSTEM_FLIGHT_LANDING_MODE ==
                SYSTEM_LANDING_MODE_BARO_IMU_WINDOW),
               "invalid SYSTEM_FLIGHT_LANDING_MODE");
_Static_assert((SYSTEM_FLIGHT_ROCKET_LONGITUDINAL_AXIS >=
                SYSTEM_BODY_AXIS_X_POSITIVE) &&
               (SYSTEM_FLIGHT_ROCKET_LONGITUDINAL_AXIS <=
                SYSTEM_BODY_AXIS_Z_NEGATIVE),
               "invalid SYSTEM_FLIGHT_ROCKET_LONGITUDINAL_AXIS");

static SystemFlightRecoveryStatus s_status;
static uint64_t s_deploy_confirm_start_sample_us;
static SystemDeployTriggerMask s_deploy_confirm_mask;
static uint64_t s_last_deploy_estimator_timestamp_us;
static uint32_t s_last_deploy_estimator_sequence;
static uint8_t s_last_deploy_estimator_valid;
static uint64_t s_recovery_enter_timestamp_us;
static uint64_t s_landing_confirm_start_sample_us;
static uint64_t s_last_landing_inertial_timestamp_us;
static uint32_t s_last_landing_inertial_sequence;
static uint8_t s_last_landing_inertial_valid;
static uint64_t s_last_landing_ins_timestamp_us;
static uint32_t s_last_landing_ins_sequence;
static uint8_t s_last_landing_ins_valid;
static FlightDeploymentContext s_deployment_context;
static FlightLandingContext s_landing_context;
static FlightLandingTimeWindow s_landing_imu_window;
static uint64_t s_landing_baro_covered_us;
static FlightLandingBarometerRegression s_baro_trigger_window;
static FlightLandingBarometerRegression s_baro_candidate_window;
static uint64_t s_landing_candidate_start_us;
static uint64_t s_landing_candidate_first_imu_us;
static uint64_t s_landing_candidate_last_imu_us;
static uint64_t s_last_landing_baro_timestamp_us;
static uint32_t s_last_landing_baro_sequence;
static uint8_t s_last_landing_baro_valid;
static uint32_t s_landing_candidate_imu_count;
static float s_landing_candidate_max_gyro_norm;
static float s_landing_candidate_max_accel_norm;
static float s_landing_candidate_max_gravity_error;

static const FlightDeploymentConfig s_deployment_config =
{
    .trigger_mask = SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK,
    .rocket_longitudinal_axis =
        (SystemBodyAxis)SYSTEM_FLIGHT_ROCKET_LONGITUDINAL_AXIS,
    .tilt_reference = (SystemTiltReference)SYSTEM_FLIGHT_TILT_REFERENCE,
    .tilt_threshold_deg = SYSTEM_FLIGHT_TILT_THRESHOLD_DEG,
    .apogee_vertical_velocity_threshold_mps =
        SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS,
    .delay_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS
};

static const FlightLandingConfig s_landing_config =
{
    .sample_max_age_ms = SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS,
    .local_gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2,
    .impact_threshold_mps2 = SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2,
    .still_gyro_threshold_radps =
        SYSTEM_FLIGHT_LANDING_STILL_GYRO_THRESHOLD_RADPS,
    .still_accel_tolerance_mps2 =
        SYSTEM_FLIGHT_LANDING_STILL_ACCEL_TOLERANCE_MPS2,
    .barometer_confirm_rate_mps =
        SYSTEM_FLIGHT_LANDING_BARO_CONFIRM_RATE_MPS,
    .barometer_max_span_m = SYSTEM_FLIGHT_LANDING_BARO_MAX_SPAN_M
};

static uint32_t SystemFlightRecovery_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemFlightRecovery_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static void SystemFlightRecovery_StatusCommit(
    SystemFlightRecoveryStatus *status)
{
    uint32_t primask;

    if (status == NULL) { return; }
    status->sequence++;
    primask = SystemFlightRecovery_IrqLock();
    s_status = *status;
    SystemFlightRecovery_IrqUnlock(primask);
}

static uint8_t SystemFlightRecovery_ConfigIsValid(void)
{
    return (uint8_t)(
        isfinite(SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_RATE_MPS) &&
        (SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_RATE_MPS > 0.0f) &&
        (s_deployment_context.initialized != 0U) &&
        (s_landing_context.initialized != 0U));
}

static uint8_t SystemFlightRecovery_SampleIsFresh(uint64_t now_us,
                                                   uint64_t timestamp_us)
{
    return (uint8_t)(FlightLanding_SampleFreshEvaluate(
        &s_landing_context, now_us, timestamp_us) ==
        FLIGHT_LANDING_CONDITION_MET);
}

static void SystemFlightRecovery_BaroRegressionReset(
    FlightLandingBarometerRegression *regression)
{
    FlightLanding_BarometerRegressionReset(regression);
}

static uint8_t SystemFlightRecovery_BaroRegressionAdd(
    FlightLandingBarometerRegression *regression,
    uint64_t timestamp_us,
    float altitude_m)
{
    return (uint8_t)(FlightLanding_BarometerRegressionAdd(
        regression, timestamp_us, altitude_m) == FLIGHT_LANDING_RESULT_OK);
}

static uint8_t SystemFlightRecovery_BaroRegressionGet(
    const FlightLandingBarometerRegression *regression,
    float *slope_mps,
    float *span_m)
{
    return (uint8_t)(FlightLanding_BarometerRegressionGet(
        regression, slope_mps, span_m) == FLIGHT_LANDING_RESULT_OK);
}

static uint8_t SystemFlightRecovery_EstimatorSampleIsNew(
    const SystemFlightRecoveryInput *input)
{
    if ((input == NULL) || (input->estimator_timestamp_us == 0ULL) ||
        (input->estimator_timestamp_us > input->now_us))
    {
        return 0U;
    }
    if ((s_last_deploy_estimator_valid != 0U) &&
        (input->estimator_sequence == s_last_deploy_estimator_sequence) &&
        (input->estimator_timestamp_us ==
         s_last_deploy_estimator_timestamp_us))
    {
        return 0U;
    }
    s_last_deploy_estimator_sequence = input->estimator_sequence;
    s_last_deploy_estimator_timestamp_us = input->estimator_timestamp_us;
    s_last_deploy_estimator_valid = 1U;
    return 1U;
}

static uint8_t SystemFlightRecovery_InertialSampleIsNew(
    const SystemFlightRecoveryInput *input)
{
    if ((input == NULL) || (input->inertial_timestamp_us == 0ULL) ||
        (input->inertial_timestamp_us > input->now_us))
    {
        return 0U;
    }
    if ((s_last_landing_inertial_valid != 0U) &&
        (input->inertial_sequence == s_last_landing_inertial_sequence) &&
        (input->inertial_timestamp_us ==
         s_last_landing_inertial_timestamp_us))
    {
        return 0U;
    }
    s_last_landing_inertial_sequence = input->inertial_sequence;
    s_last_landing_inertial_timestamp_us = input->inertial_timestamp_us;
    s_last_landing_inertial_valid = 1U;
    return 1U;
}

static uint8_t SystemFlightRecovery_InsSampleIsNew(
    const SystemFlightRecoveryInput *input)
{
    if ((input == NULL) || (input->ins_timestamp_us == 0ULL) ||
        (input->ins_timestamp_us > input->now_us))
    {
        return 0U;
    }
    if ((s_last_landing_ins_valid != 0U) &&
        (input->ins_sequence == s_last_landing_ins_sequence) &&
        (input->ins_timestamp_us == s_last_landing_ins_timestamp_us))
    {
        return 0U;
    }
    s_last_landing_ins_sequence = input->ins_sequence;
    s_last_landing_ins_timestamp_us = input->ins_timestamp_us;
    s_last_landing_ins_valid = 1U;
    return 1U;
}

static uint8_t SystemFlightRecovery_BarometerSampleIsNew(
    const SystemFlightRecoveryInput *input)
{
    if ((input == NULL) || (input->barometer_timestamp_us == 0ULL) ||
        (input->barometer_timestamp_us > input->now_us))
    {
        return 0U;
    }
    if ((s_last_landing_baro_valid != 0U) &&
        (input->barometer_sequence == s_last_landing_baro_sequence) &&
        (input->barometer_timestamp_us ==
         s_last_landing_baro_timestamp_us))
    {
        return 0U;
    }
    s_last_landing_baro_sequence = input->barometer_sequence;
    s_last_landing_baro_timestamp_us = input->barometer_timestamp_us;
    s_last_landing_baro_valid = 1U;
    return 1U;
}

static void SystemFlightRecovery_InitialAxisCapture(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemLifecycleState lifecycle_state)
{
    if ((status == NULL) || (input == NULL) ||
        (lifecycle_state != SYSTEM_STATE_FLIGHT) ||
        (status->initial_rocket_axis_valid != 0U) ||
        (input->initial_attitude_valid == 0U))
    {
        return;
    }
    status->initial_rocket_axis_valid = (uint8_t)(
        FlightDeployment_RocketAxisGet(
            &s_deployment_context,
            input->initial_q_nb,
            status->initial_rocket_axis_n) == FLIGHT_DEPLOYMENT_AXIS_OK);
}

static void SystemFlightRecovery_ActionRecord(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemMissionAction action,
    SystemDeviceResult result)
{
    status->action_event_sequence++;
    status->last_action = action;
    status->last_action_result = result;
    status->last_action_timestamp_us = input->now_us;
    status->last_action_mission_time_ms = input->mission_time_ms;
}

static SystemDeviceResult SystemFlightRecovery_ActionExecute(
    SystemMissionAction action)
{
    return SystemMissionAction_Execute(action);
}

static void SystemFlightRecovery_StartActionProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemLifecycleState lifecycle_state)
{
    SystemDeviceResult result;

    if ((lifecycle_state != SYSTEM_STATE_FLIGHT) ||
        (status->mission_start_action_done != 0U))
    {
        return;
    }
    status->mission_start_action_done = 1U;
    SystemFlightRecovery_StatusCommit(status);
    result = SystemFlightRecovery_ActionExecute(SYSTEM_MISSION_ACTION_START);
    status->mission_start_action_result = result;
    SystemFlightRecovery_ActionRecord(status, input,
                                      SYSTEM_MISSION_ACTION_START, result);
    SystemFlightRecovery_StatusCommit(status);
}

static FlightDeploymentConditionResult
SystemFlightRecovery_DeployConditionGet(
    const SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemDeployTriggerMask *matched_mask,
    float *tilt_angle_deg,
    float *vertical_velocity_mps)
{
    FlightDeploymentEvaluation evaluation;
    FlightDeploymentInput deployment_input;
    FlightDeploymentConditionResult result;

    if ((status == NULL) || (input == NULL) || (matched_mask == NULL) ||
        (tilt_angle_deg == NULL) || (vertical_velocity_mps == NULL))
    {
        return FLIGHT_DEPLOYMENT_CONDITION_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    (void)memset(&evaluation, 0, sizeof(evaluation));
    (void)memset(&deployment_input, 0, sizeof(deployment_input));
    deployment_input.mission_time_ms = input->mission_time_ms;
    (void)memcpy(deployment_input.q_nb, input->q_nb,
                 sizeof(deployment_input.q_nb));
    (void)memcpy(deployment_input.velocity_enu_mps,
                 input->velocity_enu_mps,
                 sizeof(deployment_input.velocity_enu_mps));
    (void)memcpy(deployment_input.initial_rocket_axis_n,
                 status->initial_rocket_axis_n,
                 sizeof(deployment_input.initial_rocket_axis_n));
    deployment_input.attitude_valid = input->attitude_valid;
    deployment_input.velocity_valid = input->velocity_valid;
    deployment_input.initial_rocket_axis_valid =
        status->initial_rocket_axis_valid;
    result = FlightDeployment_ConditionEvaluate(
        &s_deployment_context, &deployment_input, &evaluation);
    *matched_mask = evaluation.matched_mask;
    *tilt_angle_deg = evaluation.tilt_angle_deg;
    *vertical_velocity_mps = evaluation.vertical_velocity_mps;
    return result;
}

static void SystemFlightRecovery_DeployTrackingReset(
    SystemFlightRecoveryStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    status->deploy_confirming = 0U;
    s_deploy_confirm_start_sample_us = 0ULL;
    s_deploy_confirm_mask = SYSTEM_DEPLOY_TRIGGER_NONE;
}

static FlightDeploymentConditionResult
SystemFlightRecovery_DeployConditionResolve(
    const SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemDeployTriggerMask *matched_mask,
    float *tilt_angle_deg,
    float *vertical_velocity_mps,
    uint8_t *condition_evaluated)
{
    FlightDeploymentConditionResult result;
    uint8_t sensor_sample_new;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(condition_evaluated, uint8_t,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    *condition_evaluated = 1U;
    sensor_sample_new = SystemFlightRecovery_EstimatorSampleIsNew(input);
    if ((sensor_sample_new == 0U) &&
        ((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK &
          SYSTEM_DEPLOY_TRIGGER_DELAY) == 0U))
    {
        *condition_evaluated = 0U;
        return FLIGHT_DEPLOYMENT_CONDITION_NOT_MET;
    }
    result = SystemFlightRecovery_DeployConditionGet(
        status, input, matched_mask, tilt_angle_deg,
        vertical_velocity_mps);
    if (sensor_sample_new == 0U)
    {
        *matched_mask &= SYSTEM_DEPLOY_TRIGGER_DELAY;
        result = (*matched_mask != SYSTEM_DEPLOY_TRIGGER_NONE) ?
            FLIGHT_DEPLOYMENT_CONDITION_MET :
            FLIGHT_DEPLOYMENT_CONDITION_NOT_MET;
    }
    return result;
}

static uint8_t SystemFlightRecovery_DeployConfirmationReady(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    FlightDeploymentConditionResult condition_result,
    SystemDeployTriggerMask *matched_mask)
{
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS * 1000ULL;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (condition_result == FLIGHT_DEPLOYMENT_CONDITION_INVALID)
    {
        return 0U;
    }
    if (condition_result == FLIGHT_DEPLOYMENT_CONDITION_NOT_MET)
    {
        SystemFlightRecovery_DeployTrackingReset(status);
        return 0U;
    }
    if (((*matched_mask & SYSTEM_DEPLOY_TRIGGER_DELAY) != 0U) ||
        (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U))
    {
        status->deploy_confirming = 0U;
        return 1U;
    }
    if ((status->deploy_confirming == 0U) ||
        ((s_deploy_confirm_mask & *matched_mask) == 0U))
    {
        status->deploy_confirming = 1U;
        s_deploy_confirm_start_sample_us = input->estimator_timestamp_us;
        s_deploy_confirm_mask = *matched_mask;
        return 0U;
    }
    if ((input->estimator_timestamp_us <
         s_deploy_confirm_start_sample_us) ||
        ((input->estimator_timestamp_us -
          s_deploy_confirm_start_sample_us) < confirm_us))
    {
        if (input->estimator_timestamp_us < s_deploy_confirm_start_sample_us)
        {
            s_deploy_confirm_start_sample_us = input->estimator_timestamp_us;
        }
        return 0U;
    }
    *matched_mask &= s_deploy_confirm_mask;
    return 1U;
}

static void SystemFlightRecovery_DeployStatusRecord(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemDeployTriggerMask matched_mask,
    float tilt_angle_deg,
    float vertical_velocity_mps)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    status->deploy_confirming = 0U;
    status->deploy_triggered = 1U;
    status->deploy_matched_mask = matched_mask;
    status->deploy_tilt_angle_deg = tilt_angle_deg;
    status->deploy_vertical_velocity_mps = vertical_velocity_mps;
    status->deploy_delay_ms = input->mission_time_ms;
    if ((matched_mask & SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ) != 0U)
    {
        status->deploy_trigger_value = vertical_velocity_mps;
    }
    else if ((matched_mask & SYSTEM_DEPLOY_TRIGGER_TILT) != 0U)
    {
        status->deploy_trigger_value = tilt_angle_deg;
    }
    else
    {
        status->deploy_trigger_value = (float)input->mission_time_ms;
    }
    status->deploy_event_timestamp_us = input->now_us;
    status->deploy_event_mission_time_ms = input->mission_time_ms;
}

static SystemDeviceResult SystemFlightRecovery_DeployActionProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    SystemDeviceResult action_result;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SystemFlightRecovery_StatusCommit(status);
    action_result = SystemFlightRecovery_ActionExecute(
        SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY);
    status->deploy_action_result = action_result;
    SystemFlightRecovery_ActionRecord(
        status, input, SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY,
        action_result);
    if (action_result != SYSTEM_DEVICE_OK)
    {
        SystemFlightRecovery_StatusCommit(status);
        return action_result;
    }
    status->deploy_completed = 1U;
    status->deploy_event_sequence++;
    status->recovery_transition_result = SystemLifecycle_EnterRecovery();
    SystemFlightRecovery_StatusCommit(status);
    return status->recovery_transition_result;
}

static SystemDeviceResult SystemFlightRecovery_DeployProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemLifecycleState lifecycle_state)
{
    FlightDeploymentConditionResult condition_result;
    SystemDeployTriggerMask matched_mask = SYSTEM_DEPLOY_TRIGGER_NONE;
    float tilt_angle_deg = 0.0f;
    float vertical_velocity_mps = 0.0f;
    uint8_t condition_evaluated;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (lifecycle_state != SYSTEM_STATE_FLIGHT)
    {
        (void)SystemFlightRecovery_EstimatorSampleIsNew(input);
        SystemFlightRecovery_DeployTrackingReset(status);
        return SYSTEM_DEVICE_OK;
    }
    if ((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK == SYSTEM_DEPLOY_TRIGGER_NONE) ||
        (status->deploy_triggered != 0U))
    {
        SystemFlightRecovery_DeployTrackingReset(status);
        return SYSTEM_DEVICE_OK;
    }
    condition_result = SystemFlightRecovery_DeployConditionResolve(
        status, input, &matched_mask, &tilt_angle_deg,
        &vertical_velocity_mps, &condition_evaluated);
    if (condition_evaluated == 0U)
    {
        return SYSTEM_DEVICE_OK;
    }
    if (SystemFlightRecovery_DeployConfirmationReady(
            status, input, condition_result, &matched_mask) == 0U)
    {
        return SYSTEM_DEVICE_OK;
    }
    SystemFlightRecovery_DeployStatusRecord(
        status, input, matched_mask, tilt_angle_deg, vertical_velocity_mps);
    return SystemFlightRecovery_DeployActionProcess(status, input);
}

static uint8_t SystemFlightRecovery_PostImpactStillnessGet(
    const SystemFlightRecoveryInput *input,
    float *accel_norm)
{
    if ((input == NULL) || (accel_norm == NULL)) { return 0U; }
    return (uint8_t)(FlightLanding_PostImpactStillnessEvaluate(
        &s_landing_context,
        input->now_us,
        input->inertial_timestamp_us,
        input->corrected_accel_valid,
        input->corrected_gyro_valid,
        input->corrected_accel_b_mps2,
        input->corrected_gyro_b_radps,
        accel_norm) == FLIGHT_LANDING_CONDITION_MET);
}

static void SystemFlightRecovery_LandingDiagnosticCapture(
    SystemFlightRecoveryStatus *status, uint8_t transition,
    SystemLandingResetReason reason)
{
    SystemLandingDiagnostic *diagnostic = &status->landing_diagnostic;
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus, SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT(transition <= 3U,
        SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    uint64_t elapsed_us = (status->last_process_timestamp_us > s_landing_candidate_start_us) ?
        status->last_process_timestamp_us - s_landing_candidate_start_us : 0ULL;
    diagnostic->evaluation_timestamp_us = status->last_process_timestamp_us;
    diagnostic->candidate_start_timestamp_us = s_landing_candidate_start_us;
    diagnostic->sequence++;
    diagnostic->transition = transition;
    diagnostic->reset_reason = reason;
    diagnostic->candidate_elapsed_us = (elapsed_us > UINT32_MAX) ? UINT32_MAX : (uint32_t)elapsed_us;
    diagnostic->valid_coverage = (elapsed_us != 0ULL) ?
        (float)s_landing_imu_window.valid_us / (float)elapsed_us : 0.0f;
    diagnostic->still_ratio = (s_landing_imu_window.valid_us != 0ULL) ?
        (float)s_landing_imu_window.still_us / (float)s_landing_imu_window.valid_us : 0.0f;
    diagnostic->maximum_bad_duration_us = (s_landing_imu_window.maximum_bad_us > UINT32_MAX) ?
        UINT32_MAX : (uint32_t)s_landing_imu_window.maximum_bad_us;
    diagnostic->baro_slope_mps = 0.0f;
    diagnostic->baro_span_m = 0.0f;
    (void)SystemFlightRecovery_BaroRegressionGet(&s_baro_candidate_window,
        &diagnostic->baro_slope_mps, &diagnostic->baro_span_m);
    diagnostic->baro_coverage = (elapsed_us != 0ULL) ?
        (float)s_landing_baro_covered_us / (float)elapsed_us : 0.0f;
}

static SystemDeviceResult SystemFlightRecovery_LandingComplete(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    SystemFlightRecovery_LandingDiagnosticCapture(status, 3U, SYSTEM_LANDING_RESET_NONE);
    status->landing_confirming = 0U;
    status->landing_detected = 1U;
    status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_LANDED;
    status->landing_event_timestamp_us = input->now_us;
    status->landing_event_mission_time_ms = input->mission_time_ms;
    status->landing_event_sequence++;
    SystemFlightRecovery_StatusCommit(status);
    status->landing_transition_result = SystemLifecycle_EnterLanded();
    SystemFlightRecovery_StatusCommit(status);
    return status->landing_transition_result;
}

static SystemDeviceResult SystemFlightRecovery_StillnessLandingProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_CONFIRM_MS * 1000ULL;
    uint8_t condition_met;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if ((SystemFlightRecovery_InertialSampleIsNew(input) == 0U) ||
        (SystemFlightRecovery_InsSampleIsNew(input) == 0U))
    {
        return SYSTEM_DEVICE_OK;
    }
    condition_met = (uint8_t)(FlightLanding_StillnessEvaluate(
        &s_landing_context,
        input->now_us,
        input->inertial_timestamp_us,
        input->ins_timestamp_us,
        input->corrected_gyro_valid,
        input->linear_accel_valid,
        input->corrected_gyro_b_radps,
        input->linear_accel_n_mps2) == FLIGHT_LANDING_CONDITION_MET);
    if (condition_met == 0U)
    {
        status->landing_confirming = 0U;
        status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED;
        s_landing_confirm_start_sample_us = 0ULL;
        return SYSTEM_DEVICE_OK;
    }
    status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM;
    if (status->landing_confirming == 0U)
    {
        status->landing_confirming = 1U;
        s_landing_confirm_start_sample_us = input->inertial_timestamp_us;
        return SYSTEM_DEVICE_OK;
    }
    if ((input->inertial_timestamp_us <
         s_landing_confirm_start_sample_us) ||
        ((input->inertial_timestamp_us -
          s_landing_confirm_start_sample_us) < confirm_us))
    {
        return SYSTEM_DEVICE_OK;
    }
    return SystemFlightRecovery_LandingComplete(status, input);
}

static SystemDeviceResult SystemFlightRecovery_ImpactCaptureProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    float accel_norm)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (accel_norm <= s_landing_context.config.impact_threshold_mps2)
    {
        return SYSTEM_DEVICE_OK;
    }
    status->landing_state =
        SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED;
    status->impact_armed = 0U;
    status->impact_metric_mps2 = accel_norm;
    status->impact_peak_mps2 = accel_norm;
    status->impact_event_timestamp_us = input->inertial_timestamp_us;
    status->impact_event_mission_time_ms = input->mission_time_ms;
    status->impact_event_sequence++;
    status->landing_confirming = 0U;
    s_landing_confirm_start_sample_us = 0ULL;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SystemFlightRecovery_PostImpactProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    float accel_norm,
    uint64_t confirm_us)
{
    uint8_t still;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (accel_norm > status->impact_peak_mps2)
    {
        status->impact_peak_mps2 = accel_norm;
    }
    still = SystemFlightRecovery_PostImpactStillnessGet(input, &accel_norm);
    if (status->landing_state ==
        SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED)
    {
        if (still == 0U)
        {
            return SYSTEM_DEVICE_OK;
        }
        status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM;
        status->landing_confirming = 1U;
        s_landing_confirm_start_sample_us = input->inertial_timestamp_us;
        return SYSTEM_DEVICE_OK;
    }
    if (status->landing_state ==
        SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM)
    {
        if (still == 0U)
        {
            status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED;
            status->impact_armed = 1U;
            status->landing_confirming = 0U;
            s_landing_confirm_start_sample_us = 0ULL;
            return SYSTEM_DEVICE_OK;
        }
        if ((input->inertial_timestamp_us >=
             s_landing_confirm_start_sample_us) &&
            ((input->inertial_timestamp_us -
              s_landing_confirm_start_sample_us) >= confirm_us))
        {
            return SystemFlightRecovery_LandingComplete(status, input);
        }
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SystemFlightRecovery_ImpactLandingProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_CONFIRM_MS * 1000ULL;
    float accel_norm;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (SystemFlightRecovery_InertialSampleIsNew(input) == 0U)
    {
        return SYSTEM_DEVICE_OK;
    }
    if (FlightLanding_ImpactMetricGet(
            &s_landing_context,
            input->now_us,
            input->inertial_timestamp_us,
            input->corrected_accel_valid,
            input->corrected_accel_b_mps2,
            &accel_norm) != FLIGHT_LANDING_RESULT_OK)
    {
        return SYSTEM_DEVICE_OK;
    }
    if (status->landing_state == SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED)
    {
        return SystemFlightRecovery_ImpactCaptureProcess(
            status, input, accel_norm);
    }
    return SystemFlightRecovery_PostImpactProcess(
        status, input, accel_norm, confirm_us);
}

static uint8_t SystemFlightRecovery_BarometerSampleValid(
    const SystemFlightRecoveryInput *input)
{
    if (input == NULL) { return 0U; }
    return (uint8_t)(FlightLanding_BarometerSampleEvaluate(
        &s_landing_context,
        input->now_us,
        input->barometer_timestamp_us,
        input->barometer_healthy,
        input->barometer_valid,
        input->barometer_altitude_m) == FLIGHT_LANDING_CONDITION_MET);
}

static void SystemFlightRecovery_BaroMonitorReset(
    SystemFlightRecoveryStatus *status, SystemLandingResetReason reason)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (status->landing_candidate_active != 0U)
    { SystemFlightRecovery_LandingDiagnosticCapture(status, 2U, reason); }
    SystemFlightRecovery_BaroRegressionReset(&s_baro_trigger_window);
    SystemFlightRecovery_BaroRegressionReset(&s_baro_candidate_window);
    s_landing_candidate_start_us = 0ULL;
    s_landing_candidate_first_imu_us = 0ULL;
    s_landing_candidate_last_imu_us = 0ULL;
    s_landing_candidate_imu_count = 0U;
    s_landing_candidate_max_gyro_norm = 0.0f;
    s_landing_candidate_max_accel_norm = 0.0f;
    s_landing_candidate_max_gravity_error = 0.0f;
    status->landing_candidate_active = 0U;
    status->landing_confirming = 0U;
    status->landing_candidate_elapsed_ms = 0U;
    status->landing_candidate_baro_count = 0U;
    status->landing_candidate_imu_count = 0U;
    status->landing_candidate_baro_slope_mps = 0.0f;
    status->landing_candidate_baro_span_m = 0.0f;
    status->landing_candidate_gyro_norm_radps = 0.0f;
    status->landing_candidate_accel_norm_mps2 = 0.0f;
    status->landing_candidate_gravity_error_mps2 = 0.0f;
    status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_BARO_MONITOR;
}

static void SystemFlightRecovery_BaroCandidateStart(
    SystemFlightRecoveryStatus *status,
    uint64_t timestamp_us)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SystemFlightRecovery_BaroRegressionReset(&s_baro_candidate_window);
    s_landing_candidate_start_us = timestamp_us;
    FlightLanding_TimeWindowReset(&s_landing_imu_window, timestamp_us);
    s_landing_baro_covered_us = 0U;
    s_landing_candidate_first_imu_us = 0ULL;
    s_landing_candidate_last_imu_us = 0ULL;
    s_landing_candidate_imu_count = 0U;
    s_landing_candidate_max_gyro_norm = 0.0f;
    s_landing_candidate_max_accel_norm = 0.0f;
    s_landing_candidate_max_gravity_error = 0.0f;
    status->landing_candidate_active = 1U;
    status->landing_confirming = 1U;
    status->landing_candidate_elapsed_ms = 0U;
    status->landing_candidate_baro_count = 0U;
    status->landing_candidate_imu_count = 0U;
    status->landing_state =
        SYSTEM_FLIGHT_LANDING_STATE_BARO_IMU_CANDIDATE;
    SystemFlightRecovery_LandingDiagnosticCapture(status, 1U, SYSTEM_LANDING_RESET_NONE);
}

static uint8_t SystemFlightRecovery_BaroCandidateImuAdd(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    FlightLandingImuMetrics metrics;
    uint8_t valid;
    uint8_t still;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    valid = (uint8_t)(FlightLanding_ImuMetricsGet(
            &s_landing_context,
            input->now_us,
            input->inertial_timestamp_us,
            s_landing_candidate_start_us,
            input->corrected_accel_valid,
            input->corrected_gyro_valid,
            input->corrected_accel_b_mps2,
            input->corrected_gyro_b_radps,
            &metrics) == FLIGHT_LANDING_RESULT_OK);
    still = (uint8_t)((valid != 0U) &&
        (metrics.gyro_norm_radps < s_landing_context.config.still_gyro_threshold_radps) &&
        (metrics.gravity_error_mps2 < s_landing_context.config.still_accel_tolerance_mps2));
    if (FlightLanding_TimeWindowAdd(&s_landing_imu_window,
            input->inertial_timestamp_us, valid, still) != FLIGHT_LANDING_RESULT_OK)
    { return 0U; }
    if (s_landing_imu_window.maximum_bad_us > FLIGHT_LANDING_MAXIMUM_BAD_US) { return 0U; }
    if (valid == 0U) { return 1U; }
    if (s_landing_candidate_imu_count == 0U)
    {
        s_landing_candidate_first_imu_us = input->inertial_timestamp_us;
    }
    s_landing_candidate_last_imu_us = input->inertial_timestamp_us;
    s_landing_candidate_imu_count++;
    if (metrics.gyro_norm_radps > s_landing_candidate_max_gyro_norm)
    {
        s_landing_candidate_max_gyro_norm = metrics.gyro_norm_radps;
    }
    if (metrics.accel_norm_mps2 > s_landing_candidate_max_accel_norm)
    {
        s_landing_candidate_max_accel_norm = metrics.accel_norm_mps2;
    }
    if (metrics.gravity_error_mps2 > s_landing_candidate_max_gravity_error)
    {
        s_landing_candidate_max_gravity_error = metrics.gravity_error_mps2;
    }
    status->landing_candidate_imu_count = s_landing_candidate_imu_count;
    status->landing_candidate_gyro_norm_radps =
        s_landing_candidate_max_gyro_norm;
    status->landing_candidate_accel_norm_mps2 =
        s_landing_candidate_max_accel_norm;
    status->landing_candidate_gravity_error_mps2 =
        s_landing_candidate_max_gravity_error;
    return 1U;
}

static void SystemFlightRecovery_BarometerStatusUpdate(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    status->barometer_valid =
        SystemFlightRecovery_BarometerSampleValid(input);
    status->barometer_age_ms =
        ((input->barometer_timestamp_us != 0ULL) &&
         (input->now_us >= input->barometer_timestamp_us)) ?
        (uint32_t)((input->now_us - input->barometer_timestamp_us) /
                   1000ULL) : UINT32_MAX;
}

static SystemDeviceResult SystemFlightRecovery_BaroTriggerProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    uint8_t baro_new,
    uint64_t trigger_window_us)
{
    float slope_mps;
    float span_m;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_BARO_MONITOR;
    if (baro_new == 0U) { return SYSTEM_DEVICE_OK; }
    if (status->barometer_valid == 0U)
    {
        SystemFlightRecovery_BaroRegressionReset(&s_baro_trigger_window);
        return SYSTEM_DEVICE_OK;
    }
    if (SystemFlightRecovery_BaroRegressionAdd(
            &s_baro_trigger_window, input->barometer_timestamp_us,
            input->barometer_altitude_m) == 0U)
    {
        SystemFlightRecovery_BaroRegressionReset(&s_baro_trigger_window);
        return SYSTEM_DEVICE_OK;
    }
    if ((s_baro_trigger_window.last_timestamp_us -
         s_baro_trigger_window.first_timestamp_us) < trigger_window_us)
    {
        return SYSTEM_DEVICE_OK;
    }
    if ((s_baro_trigger_window.count <
         SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_MIN_SAMPLES) ||
        (SystemFlightRecovery_BaroRegressionGet(
            &s_baro_trigger_window, &slope_mps, &span_m) == 0U))
    {
        SystemFlightRecovery_BaroRegressionReset(&s_baro_trigger_window);
        return SYSTEM_DEVICE_OK;
    }
    status->barometer_trigger_rate_mps = slope_mps;
    SystemFlightRecovery_BaroRegressionReset(&s_baro_trigger_window);
    if (fabsf(slope_mps) < SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_RATE_MPS)
    {
        SystemFlightRecovery_BaroCandidateStart(
            status, input->barometer_timestamp_us);
    }
    return SYSTEM_DEVICE_OK;
}

static uint8_t SystemFlightRecovery_BaroCandidateSamplesProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    uint8_t baro_new,
    uint8_t inertial_new)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (((status->barometer_valid == 0U) &&
         (SystemFlightRecovery_SampleIsFresh(input->now_us,
             (s_baro_candidate_window.count != 0U) ?
             s_baro_candidate_window.last_timestamp_us : s_landing_candidate_start_us) == 0U)) ||
        (SystemFlightRecovery_SampleIsFresh(
            input->now_us, (input->inertial_timestamp_us != 0U) ?
                input->inertial_timestamp_us : s_landing_imu_window.last_us) == 0U))
    {
        SystemFlightRecovery_BaroMonitorReset(status,
            (status->barometer_valid == 0U) ? SYSTEM_LANDING_RESET_BARO_STALE :
                SYSTEM_LANDING_RESET_IMU_INVALID);
        return 0U;
    }
    if ((baro_new != 0U) && (status->barometer_valid != 0U))
    {
        uint64_t previous_us = (s_baro_candidate_window.count != 0U) ?
            s_baro_candidate_window.last_timestamp_us : s_landing_candidate_start_us;
        if ((input->barometer_timestamp_us > previous_us) &&
            (input->barometer_timestamp_us - previous_us <=
             ((uint64_t)SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS * 1000ULL)))
        { s_landing_baro_covered_us += input->barometer_timestamp_us - previous_us; }
        if ((input->barometer_timestamp_us <=
             s_landing_candidate_start_us) ||
            (SystemFlightRecovery_BaroRegressionAdd(
                &s_baro_candidate_window,
                input->barometer_timestamp_us,
                input->barometer_altitude_m) == 0U))
        {
            SystemFlightRecovery_BaroMonitorReset(status, SYSTEM_LANDING_RESET_TIMESTAMP_DISCONTINUITY);
            return 0U;
        }
        status->landing_candidate_baro_count =
            s_baro_candidate_window.count;
    }
    if ((inertial_new != 0U) &&
        (SystemFlightRecovery_BaroCandidateImuAdd(status, input) == 0U))
    {
        SystemFlightRecovery_BaroMonitorReset(status,
            (s_landing_imu_window.maximum_bad_us > FLIGHT_LANDING_MAXIMUM_BAD_US) ?
                SYSTEM_LANDING_RESET_IMU_CONTINUOUS_MOTION : SYSTEM_LANDING_RESET_TIMESTAMP_DISCONTINUITY);
        return 0U;
    }
    return (uint8_t)((status->barometer_valid != 0U) &&
                     (s_baro_candidate_window.count != 0U) &&
                     (s_landing_candidate_imu_count != 0U));
}

static uint8_t SystemFlightRecovery_BaroCandidateTimingCheck(
    SystemFlightRecoveryStatus *status,
    uint64_t candidate_duration_us,
    uint64_t minimum_coverage_us,
    float *slope_mps,
    float *span_m)
{
    uint64_t synchronized_end_us;
    uint64_t baro_coverage_us;
    uint64_t imu_coverage_us;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(slope_mps, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(span_m, float,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    synchronized_end_us =
        (s_baro_candidate_window.last_timestamp_us <
         s_landing_candidate_last_imu_us) ?
        s_baro_candidate_window.last_timestamp_us :
        s_landing_candidate_last_imu_us;
    if (synchronized_end_us <= s_landing_candidate_start_us) { return 0U; }
    status->landing_candidate_elapsed_ms = (uint32_t)(
        (synchronized_end_us - s_landing_candidate_start_us) / 1000ULL);
    if ((synchronized_end_us - s_landing_candidate_start_us) <
        candidate_duration_us)
    {
        return 0U;
    }
    baro_coverage_us = s_landing_baro_covered_us;
    imu_coverage_us = s_landing_imu_window.valid_us;
    if ((s_baro_candidate_window.count <
         SYSTEM_FLIGHT_LANDING_BARO_MIN_SAMPLES) ||
        (FlightLanding_TimeWindowEvaluate(&s_landing_imu_window,
             candidate_duration_us) != FLIGHT_LANDING_CONDITION_MET) ||
        (baro_coverage_us < minimum_coverage_us) ||
        (imu_coverage_us < minimum_coverage_us) ||
        (SystemFlightRecovery_BaroRegressionGet(
            &s_baro_candidate_window, slope_mps, span_m) == 0U))
    {
        SystemFlightRecovery_BaroMonitorReset(status,
            (baro_coverage_us < minimum_coverage_us) ? SYSTEM_LANDING_RESET_BARO_COVERAGE :
                SYSTEM_LANDING_RESET_IMU_COVERAGE);
        return 0U;
    }
    return 1U;
}

static SystemDeviceResult SystemFlightRecovery_BaroImuLandingProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    const uint64_t trigger_window_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_BARO_TRIGGER_WINDOW_MS * 1000ULL;
    const uint64_t candidate_duration_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_CANDIDATE_DURATION_MS * 1000ULL;
    const uint64_t minimum_coverage_us =
        (candidate_duration_us *
         SYSTEM_FLIGHT_LANDING_MIN_COVERAGE_PERCENT) / 100ULL;
    float slope_mps;
    float span_m;
    uint8_t baro_new = SystemFlightRecovery_BarometerSampleIsNew(input);
    uint8_t inertial_new = SystemFlightRecovery_InertialSampleIsNew(input);

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SystemFlightRecovery_BarometerStatusUpdate(status, input);
    if (status->landing_candidate_active == 0U)
    {
        return SystemFlightRecovery_BaroTriggerProcess(
            status, input, baro_new, trigger_window_us);
    }
    if (SystemFlightRecovery_BaroCandidateSamplesProcess(
            status, input, baro_new, inertial_new) == 0U)
    { return SYSTEM_DEVICE_OK; }
    if ((input->now_us < s_landing_imu_window.last_good_us) ||
        (input->now_us - s_landing_imu_window.last_good_us > FLIGHT_LANDING_COVERAGE_GAP_US))
    { return SYSTEM_DEVICE_OK; }
    if (SystemFlightRecovery_BaroCandidateTimingCheck(
            status, candidate_duration_us, minimum_coverage_us,
            &slope_mps, &span_m) == 0U)
    { return SYSTEM_DEVICE_OK; }
    status->landing_candidate_baro_slope_mps = slope_mps;
    status->landing_candidate_baro_span_m = span_m;
    if (FlightLanding_BarometerCandidateEvaluate(
            &s_landing_context,
            slope_mps,
            span_m,
            0.0f, 0.0f) !=
        FLIGHT_LANDING_CONDITION_MET)
    {
        SystemFlightRecovery_BaroMonitorReset(status,
            (span_m > s_landing_context.config.barometer_max_span_m) ? SYSTEM_LANDING_RESET_BARO_SPAN :
                SYSTEM_LANDING_RESET_BARO_SLOPE);
        return SYSTEM_DEVICE_OK;
    }
    return SystemFlightRecovery_LandingComplete(status, input);
}

static void SystemFlightRecovery_LandingTrackingReset(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    (void)SystemFlightRecovery_InertialSampleIsNew(input);
    (void)SystemFlightRecovery_InsSampleIsNew(input);
    (void)SystemFlightRecovery_BarometerSampleIsNew(input);
    s_recovery_enter_timestamp_us = 0ULL;
    s_landing_confirm_start_sample_us = 0ULL;
    SystemFlightRecovery_BaroMonitorReset(status, SYSTEM_LANDING_RESET_NONE);
    status->landing_confirming = 0U;
    status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_WAIT_RECOVERY;
}

static SystemDeviceResult SystemFlightRecovery_ImpactModeProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    uint64_t inhibit_us)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (s_recovery_enter_timestamp_us == 0ULL)
    {
        s_recovery_enter_timestamp_us = input->now_us;
        status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT;
    }
    if ((input->now_us < s_recovery_enter_timestamp_us) ||
        ((input->now_us - s_recovery_enter_timestamp_us) < inhibit_us))
    {
        (void)SystemFlightRecovery_InertialSampleIsNew(input);
        (void)SystemFlightRecovery_InsSampleIsNew(input);
        status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT;
        return SYSTEM_DEVICE_OK;
    }
    if (status->landing_state == SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT)
    {
        status->landing_state = SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED;
        status->impact_armed = 1U;
    }
    return SystemFlightRecovery_ImpactLandingProcess(status, input);
}

static SystemDeviceResult SystemFlightRecovery_LandingProcess(
    SystemFlightRecoveryStatus *status,
    const SystemFlightRecoveryInput *input,
    SystemLifecycleState lifecycle_state)
{
    const uint64_t inhibit_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_IMPACT_INHIBIT_MS * 1000ULL;

    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if ((SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE == 0U) ||
        (status->landing_detected != 0U))
    {
        status->landing_state = (status->landing_detected != 0U) ?
            SYSTEM_FLIGHT_LANDING_STATE_LANDED :
            SYSTEM_FLIGHT_LANDING_STATE_DISABLED;
        return SYSTEM_DEVICE_OK;
    }
    if (lifecycle_state != SYSTEM_STATE_RECOVERY)
    {
        SystemFlightRecovery_LandingTrackingReset(status, input);
        return SYSTEM_DEVICE_OK;
    }
    if (SYSTEM_FLIGHT_LANDING_MODE ==
        SYSTEM_LANDING_MODE_BARO_IMU_WINDOW)
    {
        if (s_recovery_enter_timestamp_us == 0ULL)
        {
            s_recovery_enter_timestamp_us = input->now_us;
            SystemFlightRecovery_BaroMonitorReset(status, SYSTEM_LANDING_RESET_NONE);
        }
        return SystemFlightRecovery_BaroImuLandingProcess(status, input);
    }
    if (SYSTEM_FLIGHT_LANDING_MODE == SYSTEM_LANDING_MODE_STILLNESS)
    {
        /* Preserve the original bench/HIL mode: it does not require an
           impact transaction or the impact-only opening-shock inhibit. */
        status->landing_state =
            SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED;
        return SystemFlightRecovery_StillnessLandingProcess(status, input);
    }
    return SystemFlightRecovery_ImpactModeProcess(status, input, inhibit_us);
}

static void SystemFlightRecovery_StatusDefaultsSet(
    SystemFlightRecoveryStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    (void)memset(status, 0, sizeof(*status));
    status->deploy_trigger_mask = SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK;
    status->rocket_longitudinal_axis =
        (SystemBodyAxis)SYSTEM_FLIGHT_ROCKET_LONGITUDINAL_AXIS;
    status->tilt_reference =
        (SystemTiltReference)SYSTEM_FLIGHT_TILT_REFERENCE;
    status->landing_enabled = SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE;
    status->landing_mode = (SystemLandingMode)SYSTEM_FLIGHT_LANDING_MODE;
    status->impact_capable = SYSTEM_IMU_CAP_LANDING_IMPACT_DETECTION;
    status->impact_threshold_mps2 =
        SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2;
    status->landing_state = (SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE != 0U) ?
        SYSTEM_FLIGHT_LANDING_STATE_WAIT_RECOVERY :
        SYSTEM_FLIGHT_LANDING_STATE_DISABLED;
    status->mission_start_action_result = SYSTEM_DEVICE_NOT_EXECUTED;
    status->deploy_action_result = SYSTEM_DEVICE_NOT_EXECUTED;
    status->recovery_transition_result = SYSTEM_DEVICE_NOT_EXECUTED;
    status->landing_transition_result = SYSTEM_DEVICE_NOT_EXECUTED;
    status->last_action_result = SYSTEM_DEVICE_NOT_EXECUTED;
}

static void SystemFlightRecovery_DeployTrackingInit(void)
{
    s_deploy_confirm_start_sample_us = 0ULL;
    s_deploy_confirm_mask = SYSTEM_DEPLOY_TRIGGER_NONE;
    s_last_deploy_estimator_timestamp_us = 0ULL;
    s_last_deploy_estimator_sequence = 0U;
    s_last_deploy_estimator_valid = 0U;
}

static void SystemFlightRecovery_LandingTrackingInit(void)
{
    s_recovery_enter_timestamp_us = 0ULL;
    s_landing_confirm_start_sample_us = 0ULL;
    s_last_landing_inertial_timestamp_us = 0ULL;
    s_last_landing_inertial_sequence = 0U;
    s_last_landing_inertial_valid = 0U;
    s_last_landing_ins_timestamp_us = 0ULL;
    s_last_landing_ins_sequence = 0U;
    s_last_landing_ins_valid = 0U;
    s_last_landing_baro_timestamp_us = 0ULL;
    s_last_landing_baro_sequence = 0U;
    s_last_landing_baro_valid = 0U;
}

static void SystemFlightRecovery_BaroTrackingInit(void)
{
    SystemFlightRecovery_BaroRegressionReset(&s_baro_trigger_window);
    SystemFlightRecovery_BaroRegressionReset(&s_baro_candidate_window);
    s_landing_candidate_start_us = 0ULL;
    s_landing_candidate_first_imu_us = 0ULL;
    s_landing_candidate_last_imu_us = 0ULL;
    s_landing_candidate_imu_count = 0U;
    s_landing_candidate_max_gyro_norm = 0.0f;
    s_landing_candidate_max_accel_norm = 0.0f;
    s_landing_candidate_max_gravity_error = 0.0f;
}

SystemDeviceResult SystemFlightRecovery_Init(void)
{
    SystemFlightRecoveryStatus status;
    SystemDeviceResult init_result;

    SILVERSTAR_ASSERT(
        SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK <= SYSTEM_DEPLOY_TRIGGER_MASK_ALL,
        SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(
        SYSTEM_FLIGHT_LANDING_MODE <= SYSTEM_LANDING_MODE_BARO_IMU_WINDOW,
        SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SystemFlightRecovery_StatusDefaultsSet(&status);
    SystemFlightRecovery_DeployTrackingInit();
    SystemFlightRecovery_LandingTrackingInit();
    SystemFlightRecovery_BaroTrackingInit();
    if ((FlightDeployment_ContextInit(
             &s_deployment_context, &s_deployment_config) !=
         FLIGHT_DEPLOYMENT_INIT_OK) ||
        (FlightLanding_ContextInit(
             &s_landing_context, &s_landing_config) !=
         FLIGHT_LANDING_INIT_OK))
    {
        SystemFlightRecovery_StatusCommit(&status);
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (SystemFlightRecovery_ConfigIsValid() == 0U)
    {
        SystemFlightRecovery_StatusCommit(&status);
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    init_result = SystemMissionAction_Init();
    if ((init_result != SYSTEM_DEVICE_OK) &&
        (init_result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        SystemFlightRecovery_StatusCommit(&status);
        return init_result;
    }
    status.initialized = 1U;
    SystemFlightRecovery_StatusCommit(&status);
    return init_result;
}

SystemDeviceResult SystemFlightRecovery_Process(
    const SystemFlightRecoveryInput *input)
{
    SystemFlightRecoveryStatus status;
    SystemLifecycleState lifecycle_state;
    SystemDeviceResult result;

    if (input == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
                             SILVERSTAR_ASSERT_MODULE_FLIGHT_LOGIC);
    if (SystemFlightRecovery_StatusGet(&status) != SYSTEM_DEVICE_OK)
    {
        return SYSTEM_DEVICE_INTERNAL_ERROR;
    }
    if (status.initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    lifecycle_state = SystemLifecycle_GetState();
    status.last_process_timestamp_us = input->now_us;
    SystemFlightRecovery_InitialAxisCapture(&status, input, lifecycle_state);
    SystemFlightRecovery_StartActionProcess(&status, input, lifecycle_state);
    result = SystemFlightRecovery_DeployProcess(&status, input,
                                                 lifecycle_state);
    if ((lifecycle_state == SYSTEM_STATE_FLIGHT) &&
        (status.deploy_triggered != 0U))
    {
        SystemFlightRecovery_StatusCommit(&status);
        return result;
    }
    result = SystemFlightRecovery_LandingProcess(&status, input,
                                                  lifecycle_state);
    SystemFlightRecovery_StatusCommit(&status);
    return result;
}

SystemDeviceResult SystemFlightRecovery_StatusGet(
    SystemFlightRecoveryStatus *status)
{
    uint32_t primask;

    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SystemFlightRecovery_IrqLock();
    *status = s_status;
    SystemFlightRecovery_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

const char *SystemFlightRecovery_DeployTriggerMaskText(
    SystemDeployTriggerMask mask)
{
    switch (mask)
    {
        case SYSTEM_DEPLOY_TRIGGER_NONE: return "NONE";
        case SYSTEM_DEPLOY_TRIGGER_TILT: return "TILT";
        case SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ: return "APOGEE_VZ";
        case SYSTEM_DEPLOY_TRIGGER_DELAY: return "DELAY";
        default: return "MULTIPLE";
    }
}

const char *SystemFlightRecovery_TiltReferenceText(SystemTiltReference mode)
{
    switch (mode)
    {
        case SYSTEM_TILT_REFERENCE_INITIAL_AXIS: return "INITIAL_AXIS";
        case SYSTEM_TILT_REFERENCE_NAV_UP: return "NAV_UP";
        default: return "UNKNOWN";
    }
}

const char *SystemFlightRecovery_LandingModeText(SystemLandingMode mode)
{
    switch (mode)
    {
        case SYSTEM_LANDING_MODE_STILLNESS: return "STILLNESS";
        case SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS:
            return "IMPACT_THEN_STILLNESS";
        case SYSTEM_LANDING_MODE_BARO_IMU_WINDOW:
            return "BARO_IMU_WINDOW";
        default: return "UNKNOWN";
    }
}

static const char *SystemFlightRecovery_LandingStateEarlyText(
    uint32_t state)
{
    switch (state)
    {
        case SYSTEM_FLIGHT_LANDING_STATE_DISABLED: return "DISABLED";
        case SYSTEM_FLIGHT_LANDING_STATE_WAIT_RECOVERY:
            return "WAIT_RECOVERY";
        case SYSTEM_FLIGHT_LANDING_STATE_BARO_MONITOR:
            return "BARO_MONITOR";
        case SYSTEM_FLIGHT_LANDING_STATE_BARO_IMU_CANDIDATE:
            return "BARO_IMU_CANDIDATE";
        case SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT:
            return "IMPACT_INHIBIT";
        default: return NULL;
    }
}

static const char *SystemFlightRecovery_LandingStateLateText(
    uint32_t state)
{
    switch (state)
    {
        case SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED:
            return "IMPACT_ARMED";
        case SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED:
            return "GROUND_IMPACT_CAPTURED";
        case SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM:
            return "POST_IMPACT_CONFIRM";
        case SYSTEM_FLIGHT_LANDING_STATE_LANDED: return "LANDED";
        default: return "UNKNOWN";
    }
}

const char *SystemFlightRecovery_LandingStateText(
    SystemFlightLandingState state)
{
    const char *text = SystemFlightRecovery_LandingStateEarlyText(
        (uint32_t)state);

    return (text != NULL) ? text :
        SystemFlightRecovery_LandingStateLateText((uint32_t)state);
}

const char *SystemFlightRecovery_ActionText(SystemMissionAction action)
{
    switch (action)
    {
        case SYSTEM_MISSION_ACTION_START: return "MISSION_START";
        case SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY:
            return "PARACHUTE_DEPLOY";
        default: return "UNKNOWN";
    }
}
