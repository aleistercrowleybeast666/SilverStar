#include <math.h>
#include <stdint.h>
#include <string.h>

#include "system_flight_recovery.h"
#include "flight_landing.h"
#include "system_lifecycle.h"
#include "system_mission_action_if.h"
#include "system_user_config.h"
#include "test_common.h"

#define TEST_DEG_TO_RAD 0.01745329251994329577f
#define TEST_INITIAL_AXIS_TILT_DEG 20.0f

static SystemLifecycleState s_lifecycle_state;
static SystemDeviceResult s_recovery_transition_result;
static SystemDeviceResult s_landed_transition_result;
static uint32_t s_enter_recovery_count;
static uint32_t s_enter_landed_count;

static SystemDeviceResult s_action_init_result;
static SystemDeviceResult s_action_results[2];
static uint32_t s_action_init_count;
static uint32_t s_action_counts[2];

static SystemDeviceResult MockAction_Init(void)
{
    s_action_init_count++;
    return s_action_init_result;
}

static SystemDeviceResult MockAction_Execute(SystemMissionAction action)
{
    if ((action < SYSTEM_MISSION_ACTION_START) ||
        (action > SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    s_action_counts[action]++;
    return s_action_results[action];
}

const char *SystemMissionAction_NameGet(void) { return "Mock Mission Action"; }
SystemDeviceResult SystemMissionAction_Init(void)
{ return MockAction_Init(); }
SystemDeviceResult SystemMissionAction_Execute(SystemMissionAction action)
{ return MockAction_Execute(action); }

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return s_lifecycle_state;
}

SystemDeviceResult SystemLifecycle_EnterRecovery(void)
{
    s_enter_recovery_count++;
    if (s_recovery_transition_result == SYSTEM_DEVICE_OK)
    {
        s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    }
    return s_recovery_transition_result;
}

SystemDeviceResult SystemLifecycle_EnterLanded(void)
{
    s_enter_landed_count++;
    if (s_landed_transition_result == SYSTEM_DEVICE_OK)
    {
        s_lifecycle_state = SYSTEM_STATE_LANDED;
    }
    return s_landed_transition_result;
}

static void Test_ActionCountersReset(void)
{
    s_action_init_result = SYSTEM_DEVICE_OK;
    s_action_results[SYSTEM_MISSION_ACTION_START] = SYSTEM_DEVICE_OK;
    s_action_results[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] =
        SYSTEM_DEVICE_OK;
    s_action_init_count = 0U;
    (void)memset(s_action_counts, 0, sizeof(s_action_counts));
    s_recovery_transition_result = SYSTEM_DEVICE_OK;
    s_landed_transition_result = SYSTEM_DEVICE_OK;
    s_enter_recovery_count = 0U;
    s_enter_landed_count = 0U;
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
}

static void Test_InputInit(SystemFlightRecoveryInput *input)
{
    float half_angle_rad = TEST_INITIAL_AXIS_TILT_DEG *
        0.5f * TEST_DEG_TO_RAD;

    (void)memset(input, 0, sizeof(*input));
    input->now_us = 1000000ULL;
    input->mission_time_ms = 1234U;
    input->estimator_timestamp_us = input->now_us;
    input->estimator_sequence = 1U;
    input->ins_timestamp_us = input->now_us;
    input->ins_sequence = 1U;
    input->inertial_timestamp_us = input->now_us;
    input->inertial_sequence = 1U;
    input->barometer_timestamp_us = input->now_us;
    input->barometer_sequence = 1U;
    input->q_nb[0] = cosf(half_angle_rad);
    input->q_nb[1] = sinf(half_angle_rad);
    (void)memcpy(input->initial_q_nb, input->q_nb,
                 sizeof(input->initial_q_nb));
    input->corrected_accel_b_mps2[2] = SYSTEM_LOCAL_GRAVITY_MPS2;
    input->attitude_valid = 1U;
    input->velocity_valid = 1U;
    input->initial_attitude_valid = 1U;
    input->linear_accel_valid = 1U;
    input->corrected_accel_valid = 1U;
    input->corrected_gyro_valid = 1U;
    input->barometer_altitude_m = 100.0f;
    input->barometer_healthy = 1U;
    input->barometer_valid = 1U;
}

static void Test_InputTimeSet(SystemFlightRecoveryInput *input,
                              uint64_t now_us)
{
    input->now_us = now_us;
    input->estimator_timestamp_us = now_us;
    input->estimator_sequence++;
    input->ins_timestamp_us = now_us;
    input->ins_sequence++;
    input->inertial_timestamp_us = now_us;
    input->inertial_sequence++;
    input->barometer_timestamp_us = now_us;
    input->barometer_sequence++;
}

#if defined(TEST_EXPECT_TILT) || defined(TEST_EXPECT_NONE) || \
    defined(TEST_EXPECT_OR) || defined(TEST_EXPECT_ALL) || \
    defined(TEST_EXPECT_PAIR)
static void Test_TiltDeviationSet(SystemFlightRecoveryInput *input,
                                  float deviation_deg)
{
    float half_angle_rad = (TEST_INITIAL_AXIS_TILT_DEG + deviation_deg) *
        0.5f * TEST_DEG_TO_RAD;

    input->q_nb[0] = cosf(half_angle_rad);
    input->q_nb[1] = sinf(half_angle_rad);
    input->q_nb[2] = 0.0f;
    input->q_nb[3] = 0.0f;
}
#endif

static void Test_ManagerReset(void)
{
    Test_ActionCountersReset();
    TEST_CHECK(SystemFlightRecovery_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_init_count == 1U);
}

static void Test_StartActionOneShot(void)
{
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;

    Test_ManagerReset();
    Test_InputInit(&input);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_START] == 0U);

    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_START] == 1U);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_START] == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mission_start_action_done != 0U);
    TEST_CHECK(status.mission_start_action_result == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.action_event_sequence == 1U);

    Test_ManagerReset();
    Test_InputInit(&input);
    s_action_results[SYSTEM_MISSION_ACTION_START] = SYSTEM_DEVICE_IO_ERROR;
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_START] == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mission_start_action_result == SYSTEM_DEVICE_IO_ERROR);
}

#if !defined(TEST_EXPECT_NONE) && !defined(TEST_EXPECT_DELAY) && \
    !defined(TEST_EXPECT_ALL) && !defined(TEST_EXPECT_PAIR)
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS > 0U)
static void Test_DeployConditionMakeNonqualifying(
    SystemFlightRecoveryInput *input)
{
#if defined(TEST_EXPECT_TILT)
    input->attitude_valid = 1U;
    Test_TiltDeviationSet(input, 0.0f);
#elif defined(TEST_EXPECT_OR)
    input->attitude_valid = 1U;
    input->velocity_valid = 1U;
    Test_TiltDeviationSet(input, 0.0f);
    input->velocity_enu_mps[2] =
        SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS + 0.01f;
#elif defined(TEST_EXPECT_APOGEE)
    input->velocity_valid = 1U;
    input->velocity_enu_mps[2] =
        SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS + 0.01f;
#endif
}

static void Test_DeployConditionInvalidate(SystemFlightRecoveryInput *input)
{
#if defined(TEST_EXPECT_TILT)
    input->attitude_valid = 0U;
#elif defined(TEST_EXPECT_OR)
    input->attitude_valid = 0U;
    input->velocity_valid = 0U;
    input->velocity_enu_mps[2] = NAN;
#elif defined(TEST_EXPECT_APOGEE)
    input->velocity_enu_mps[2] = NAN;
#endif
}
#endif

static void Test_DeployConditionRestore(SystemFlightRecoveryInput *input)
{
#if defined(TEST_EXPECT_TILT)
    input->attitude_valid = 1U;
    Test_TiltDeviationSet(input, 45.0f);
#elif defined(TEST_EXPECT_OR)
    input->attitude_valid = 1U;
    input->velocity_valid = 1U;
    Test_TiltDeviationSet(input, 0.0f);
    input->velocity_enu_mps[2] = -3.0f;
#elif defined(TEST_EXPECT_APOGEE)
    input->velocity_valid = 1U;
    input->velocity_enu_mps[2] = -3.0f;
#endif
}
#endif

static void Test_AutomaticDeployment(void)
{
    SystemFlightRecoveryInput input;
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS * 1000ULL;

#if defined(TEST_EXPECT_DELAY) || defined(TEST_EXPECT_ALL) || \
    defined(TEST_EXPECT_PAIR)
    (void)confirm_us;
#endif
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;

#if defined(TEST_EXPECT_NONE)
    input.velocity_enu_mps[2] = -100.0f;
    Test_TiltDeviationSet(&input, 90.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    TEST_CHECK(s_enter_recovery_count == 0U);
#elif defined(TEST_EXPECT_DELAY)
    SystemFlightRecoveryStatus status;

    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    input.now_us = 800000000ULL;
    input.mission_time_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS + 1U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);

    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    input.now_us = 900000000ULL;
    input.mission_time_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS - 1U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    input.mission_time_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_matched_mask == SYSTEM_DEPLOY_TRIGGER_DELAY);
    TEST_CHECK_NEAR(status.deploy_trigger_value,
                    (float)SYSTEM_FLIGHT_DEPLOY_DELAY_MS, 0.1f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#elif defined(TEST_EXPECT_ALL)
    SystemFlightRecoveryStatus status;

    Test_TiltDeviationSet(&input,
        SYSTEM_FLIGHT_TILT_THRESHOLD_DEG + 5.0f);
    input.velocity_enu_mps[2] = -3.0f;
    input.mission_time_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_matched_mask ==
        (SYSTEM_DEPLOY_TRIGGER_TILT |
         SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ |
         SYSTEM_DEPLOY_TRIGGER_DELAY));
    TEST_CHECK(status.deploy_event_sequence == 1U);
#elif defined(TEST_EXPECT_PAIR)
    SystemFlightRecoveryStatus status;

    Test_TiltDeviationSet(&input,
        SYSTEM_FLIGHT_TILT_THRESHOLD_DEG + 5.0f);
    input.velocity_enu_mps[2] = -3.0f;
    input.mission_time_ms = SYSTEM_FLIGHT_DEPLOY_DELAY_MS;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(s_enter_recovery_count == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_matched_mask == TEST_EXPECTED_DEPLOY_MASK);
    TEST_CHECK(status.deploy_event_sequence == 1U);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_matched_mask == TEST_EXPECTED_DEPLOY_MASK);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#else
    SystemFlightRecoveryStatus status;

#if defined(TEST_EXPECT_TILT)
    Test_TiltDeviationSet(&input,
        SYSTEM_FLIGHT_TILT_THRESHOLD_DEG * 0.5f);
#elif defined(TEST_EXPECT_OR)
    Test_TiltDeviationSet(&input, 0.0f);
    input.velocity_enu_mps[2] =
        SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS + 0.01f;
#else
    input.velocity_enu_mps[2] =
        SYSTEM_FLIGHT_APOGEE_VZ_THRESHOLD_MPS + 0.01f;
#endif
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);

    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_DeployConditionRestore(&input);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U)
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#else
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    /* Re-reading one snapshot cannot finish confirmation via wall clock. */
    input.now_us += confirm_us + 1ULL;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    input.estimator_timestamp_us += confirm_us - 1ULL;
    input.estimator_sequence++;
    input.now_us++;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    input.estimator_timestamp_us += 2ULL;
    input.estimator_sequence++;
    input.now_us++;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#endif
    TEST_CHECK(s_enter_recovery_count == 1U);
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_RECOVERY);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_triggered != 0U);
    TEST_CHECK(status.deploy_completed != 0U);
    TEST_CHECK(status.deploy_event_sequence == 1U);
    TEST_CHECK(status.deploy_event_mission_time_ms == input.mission_time_ms);
#if defined(TEST_EXPECT_TILT)
    TEST_CHECK(status.deploy_matched_mask == SYSTEM_DEPLOY_TRIGGER_TILT);
    TEST_CHECK_NEAR(status.deploy_trigger_value, 45.0f, 0.05f);
#else
    TEST_CHECK(status.deploy_matched_mask == SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ);
    TEST_CHECK_NEAR(status.deploy_trigger_value, -3.0f, 0.001f);
#endif
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
#if defined(TEST_EXPECT_TILT)
    Test_TiltDeviationSet(&input, 0.0f);
#elif defined(TEST_EXPECT_OR)
    Test_TiltDeviationSet(&input, 0.0f);
    input.velocity_enu_mps[2] = 10.0f;
#else
    input.velocity_enu_mps[2] = 10.0f;
#endif
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_DeployConditionRestore(&input);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(s_enter_recovery_count == 1U);
#endif
}

static void Test_DeploySampleValidityAndReset(void)
{
#if !defined(TEST_EXPECT_NONE) && !defined(TEST_EXPECT_DELAY) && \
    !defined(TEST_EXPECT_ALL) && !defined(TEST_EXPECT_PAIR)
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS * 1000ULL;

    Test_ManagerReset();
    Test_InputInit(&input);
#if defined(TEST_EXPECT_TILT)
    (void)memset(input.q_nb, 0, sizeof(input.q_nb));
#elif defined(TEST_EXPECT_OR)
    (void)memset(input.q_nb, 0, sizeof(input.q_nb));
    input.velocity_valid = 0U;
    input.velocity_enu_mps[2] = NAN;
#else
    input.velocity_enu_mps[2] = NAN;
#endif
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_triggered == 0U);

#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS > 0U)
    Test_ManagerReset();
    Test_InputInit(&input);
    Test_DeployConditionRestore(&input);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_DeployConditionInvalidate(&input);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_confirming != 0U);
    TEST_CHECK(status.deploy_triggered == 0U);

    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_DeployConditionMakeNonqualifying(&input);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_confirming == 0U);
    TEST_CHECK(status.deploy_triggered == 0U);

    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_DeployConditionRestore(&input);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    input.now_us += confirm_us + 1000000ULL;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_confirming != 0U);
    TEST_CHECK(status.deploy_triggered == 0U);
#endif
#endif
}

static void Test_DeployHasNoAbsoluteAgeVeto(void)
{
#if !defined(TEST_EXPECT_NONE) && !defined(TEST_EXPECT_DELAY) && \
    !defined(TEST_EXPECT_ALL) && !defined(TEST_EXPECT_PAIR)
    SystemFlightRecoveryInput input;

    Test_ManagerReset();
    Test_InputInit(&input);
    Test_DeployConditionRestore(&input);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    input.now_us += 10000000ULL;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U)
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#else
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    input.estimator_timestamp_us +=
        ((uint64_t)SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS * 1000ULL) + 1ULL;
    input.estimator_sequence++;
    input.now_us++;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#endif
#endif
}

static void Test_PreflightSnapshotIsNotNewAfterTransition(void)
{
#if !defined(TEST_EXPECT_NONE) && !defined(TEST_EXPECT_DELAY) && \
    !defined(TEST_EXPECT_ALL) && !defined(TEST_EXPECT_PAIR)
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;

    Test_ManagerReset();
    Test_InputInit(&input);
    Test_DeployConditionRestore(&input);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U)
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
#else
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
    TEST_CHECK(status.deploy_confirming != 0U);
#endif
#endif
}

static void Test_DeployActionAndTransitionFailuresAreOneShot(void)
{
#if !defined(TEST_EXPECT_NONE) && !defined(TEST_EXPECT_DELAY) && \
    !defined(TEST_EXPECT_ALL) && !defined(TEST_EXPECT_PAIR)
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS > 0U)
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS * 1000ULL;
#endif

    Test_ManagerReset();
    Test_InputInit(&input);
    Test_DeployConditionRestore(&input);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    s_action_results[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] =
        SYSTEM_DEVICE_IO_ERROR;
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U)
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_IO_ERROR);
#else
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_IO_ERROR);
#endif
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(s_enter_recovery_count == 0U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_triggered != 0U);
    TEST_CHECK(status.deploy_completed == 0U);
    TEST_CHECK(status.deploy_event_sequence == 0U);

    Test_ManagerReset();
    Test_InputInit(&input);
    Test_DeployConditionRestore(&input);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    s_recovery_transition_result = SYSTEM_DEVICE_BAD_STATE;
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U)
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_BAD_STATE);
#else
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_BAD_STATE);
#endif
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(s_enter_recovery_count == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_completed != 0U);
    TEST_CHECK(status.deploy_event_sequence == 1U);
#endif
}

static void Test_TiltInitialAxisReference(void)
{
#if defined(TEST_EXPECT_TILT)
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;

    Test_ManagerReset();
    Test_InputInit(&input);
    Test_TiltDeviationSet(&input, 0.0f);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.initial_rocket_axis_valid != 0U);
    TEST_CHECK(status.initial_rocket_axis_n[2] < 0.99f);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);

    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_TiltDeviationSet(&input, SYSTEM_FLIGHT_TILT_THRESHOLD_DEG + 5.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
#if (SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS > 0U)
    Test_InputTimeSet(&input, input.now_us +
        ((uint64_t)SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS * 1000ULL) + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
#endif
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_matched_mask == SYSTEM_DEPLOY_TRIGGER_TILT);
    TEST_CHECK_NEAR(status.deploy_trigger_value,
                    SYSTEM_FLIGHT_TILT_THRESHOLD_DEG + 5.0f, 0.05f);
#endif
}

#if defined(TEST_EXPECT_OR)
static void Test_OrTriggerCase(float vertical_velocity_mps,
                               float tilt_deviation_deg,
                               SystemDeployTriggerMask expected_mask)
{
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;

    Test_ManagerReset();
    Test_InputInit(&input);
    input.velocity_enu_mps[2] = vertical_velocity_mps;
    Test_TiltDeviationSet(&input, tilt_deviation_deg);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
    TEST_CHECK(s_enter_recovery_count == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.deploy_matched_mask == expected_mask);
    TEST_CHECK(status.deploy_event_sequence == 1U);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
}
#endif

static void Test_OrDeploymentTriggers(void)
{
#if defined(TEST_EXPECT_OR)
    TEST_CHECK(SYSTEM_FLIGHT_DEPLOY_CONFIRM_MS == 0U);
    Test_OrTriggerCase(-3.0f, 0.0f,
                       SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ);
    Test_OrTriggerCase(1.0f, SYSTEM_FLIGHT_TILT_THRESHOLD_DEG + 5.0f,
                       SYSTEM_DEPLOY_TRIGGER_TILT);
    Test_OrTriggerCase(-3.0f, SYSTEM_FLIGHT_TILT_THRESHOLD_DEG + 5.0f,
                       SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ |
                       SYSTEM_DEPLOY_TRIGGER_TILT);
#endif
}

#if defined(TEST_EXPECT_IMPACT)
static void Test_ImpactAccelerationSet(SystemFlightRecoveryInput *input,
                                       float acceleration_norm_mps2)
{
    input->corrected_accel_b_mps2[0] = acceleration_norm_mps2;
    input->corrected_accel_b_mps2[1] = 0.0f;
    input->corrected_accel_b_mps2[2] = 0.0f;
    input->corrected_accel_valid = 1U;
}
#endif

#if defined(TEST_EXPECT_BARO)
static void Test_BaroSampleAdvance(SystemFlightRecoveryInput *input,
                                   uint64_t delta_us,
                                   float altitude_m)
{
    uint64_t remaining = delta_us;
    uint32_t step;
    for (step = 0U; (step < 1000U) && (remaining > 10000ULL); step++)
    {
        Test_InputTimeSet(input, input->now_us + 10000ULL);
        input->barometer_altitude_m = altitude_m;
        TEST_CHECK(SystemFlightRecovery_Process(input) == SYSTEM_DEVICE_OK);
        remaining -= 10000ULL;
    }
    Test_InputTimeSet(input, input->now_us + remaining);
    input->barometer_altitude_m = altitude_m;
}

static void Test_BaroCandidateStart(SystemFlightRecoveryInput *input,
                                    float altitude_m)
{
    SystemFlightRecoveryStatus status;

    Test_BaroSampleAdvance(input, 50000ULL, altitude_m);
    TEST_CHECK(SystemFlightRecovery_Process(input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(input, 50000ULL, altitude_m);
    TEST_CHECK(SystemFlightRecovery_Process(input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(input, 50000ULL, altitude_m);
    TEST_CHECK(SystemFlightRecovery_Process(input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active != 0U);
    TEST_CHECK(status.landing_state ==
               SYSTEM_FLIGHT_LANDING_STATE_BARO_IMU_CANDIDATE);
}
#endif

static void Test_LandingDetection(void)
{
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;
    const uint64_t confirm_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_CONFIRM_MS * 1000ULL;

#if defined(TEST_EXPECT_BARO)
    (void)confirm_us;
#endif

#if defined(TEST_EXPECT_STILLNESS)
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);

#if (SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE != 0U)
    Test_InputTimeSet(&input, input.now_us - 2ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 0U);
    Test_InputTimeSet(&input, input.now_us + 2ULL);
    input.linear_accel_n_mps2[0] =
        SYSTEM_FLIGHT_LANDING_ACCEL_THRESHOLD_MPS2 * 2.0f;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_confirming == 0U);
    input.linear_accel_n_mps2[0] = 0.0f;
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    input.corrected_gyro_b_radps[0] =
        SYSTEM_FLIGHT_LANDING_GYRO_THRESHOLD_RADPS * 2.0f;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_confirming == 0U);
    input.corrected_gyro_b_radps[0] = 0.0f;
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    input.linear_accel_valid = 0U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_confirming == 0U);
    input.linear_accel_valid = 1U;
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    input.now_us += confirm_us + 1ULL;
    input.ins_timestamp_us = input.now_us -
        ((uint64_t)SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS * 1000ULL) -
        1ULL;
    input.ins_sequence++;
    input.inertial_timestamp_us = input.now_us;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_confirming == 0U);
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    input.mission_time_ms = 4321U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 1U);
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_LANDED);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_detected != 0U);
    TEST_CHECK(status.landing_event_sequence == 1U);
    TEST_CHECK(status.landing_event_mission_time_ms == 4321U);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 1U);
#else
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 0U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_detected == 0U);
#endif
#elif defined(TEST_EXPECT_IMPACT)
    const uint64_t inhibit_us =
        (uint64_t)SYSTEM_FLIGHT_LANDING_IMPACT_INHIBIT_MS * 1000ULL;

    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    Test_ImpactAccelerationSet(&input,
        SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2 * 2.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_state ==
               SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT);
    TEST_CHECK(status.impact_event_sequence == 0U);

    Test_InputTimeSet(&input, input.now_us + inhibit_us - 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.impact_event_sequence == 0U);

    Test_InputTimeSet(&input, input.now_us + 2ULL);
    input.mission_time_ms = 5000U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.impact_event_sequence == 1U);
    TEST_CHECK(status.landing_state ==
               SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED);
    TEST_CHECK(status.landing_detected == 0U);
    TEST_CHECK_NEAR(status.impact_metric_mps2,
        SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2 * 2.0f, 0.001f);

    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_ImpactAccelerationSet(&input, SYSTEM_LOCAL_GRAVITY_MPS2);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_state ==
               SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM);

    /* Wall time and a new-but-stale sample must not complete confirmation. */
    input.now_us += confirm_us +
        ((uint64_t)SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS * 1000ULL) + 1ULL;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    input.inertial_sequence++;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 0U);

    Test_InputTimeSet(&input, input.now_us + 1ULL);
    input.mission_time_ms = 6000U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_detected != 0U);
    TEST_CHECK(status.landing_event_sequence == 1U);
    TEST_CHECK(status.landing_event_mission_time_ms == 6000U);
    TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);

    /* A bounce cancels the candidate; a new impact is required. */
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + inhibit_us + 1ULL);
    Test_ImpactAccelerationSet(&input,
        SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2 * 2.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_ImpactAccelerationSet(&input, SYSTEM_LOCAL_GRAVITY_MPS2);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + (confirm_us / 2ULL) + 1ULL);
    input.corrected_gyro_b_radps[0] =
        SYSTEM_FLIGHT_LANDING_STILL_GYRO_THRESHOLD_RADPS * 2.0f;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_state ==
               SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED);
    TEST_CHECK(status.landing_detected == 0U);

    input.corrected_gyro_b_radps[0] = 0.0f;
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 0U);
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_ImpactAccelerationSet(&input,
        SYSTEM_FLIGHT_LANDING_IMPACT_THRESHOLD_MPS2 * 2.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + 1ULL);
    Test_ImpactAccelerationSet(&input, SYSTEM_LOCAL_GRAVITY_MPS2);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us + confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.impact_event_sequence == 2U);
    TEST_CHECK(status.landing_event_sequence == 1U);
#elif defined(TEST_EXPECT_BARO)
    Test_ManagerReset();
    Test_InputInit(&input);
    input.velocity_enu_mps[2] = 123.0f;
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;

    /* A clearly descending direct-Baro window must not open a candidate,
       regardless of the unrelated navigation velocity value above. */
    input.barometer_altitude_m = 100.0f;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(&input, 50000ULL, 99.9f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(&input, 50000ULL, 99.8f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active == 0U);
    TEST_CHECK(status.barometer_trigger_rate_mps < -1.0f);

    Test_BaroCandidateStart(&input, 99.8f);
    Test_BaroSampleAdvance(&input, 10000ULL, 99.8f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(&input, 100000ULL, 99.8f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(&input, 100000ULL, 99.8f);
    input.mission_time_ms = 7000U;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_enter_landed_count == 1U);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_detected != 0U);
    TEST_CHECK(status.landing_candidate_baro_count >= 3U);
    TEST_CHECK(status.landing_candidate_imu_count >= 3U);
    TEST_CHECK_NEAR(status.landing_candidate_baro_slope_mps, 0.0f, 0.01f);
    TEST_CHECK(status.landing_diagnostic.transition == 3U);
    TEST_CHECK(status.landing_diagnostic.reset_reason == SYSTEM_LANDING_RESET_NONE);
    TEST_CHECK(status.landing_diagnostic.sequence == 2U);
    TEST_CHECK(status.landing_diagnostic.valid_coverage >= 0.9f);
    TEST_CHECK(status.landing_diagnostic.still_ratio >= 0.95f);
    TEST_CHECK(status.landing_diagnostic.baro_coverage >= 0.9f);

    /* Motion cancels a candidate instead of falling back to another mode. */
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroCandidateStart(&input, 100.0f);
    Test_BaroSampleAdvance(&input, 10000ULL, 100.0f);
    input.corrected_gyro_b_radps[0] =
        SYSTEM_FLIGHT_LANDING_STILL_GYRO_THRESHOLD_RADPS * 2.0f;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active != 0U);
    Test_BaroSampleAdvance(&input, 210000ULL, 100.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active == 0U);
    TEST_CHECK(s_enter_landed_count == 0U);

    /* Excess specific-force error is an independent IMU rejection. */
    TEST_CHECK(status.landing_diagnostic.transition == 2U);
    TEST_CHECK(status.landing_diagnostic.reset_reason == SYSTEM_LANDING_RESET_IMU_CONTINUOUS_MOTION);
    TEST_CHECK(status.landing_diagnostic.maximum_bad_duration_us > 200000U);
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroCandidateStart(&input, 100.0f);
    Test_BaroSampleAdvance(&input, 10000ULL, 100.0f);
    input.corrected_accel_b_mps2[2] =
        SYSTEM_LOCAL_GRAVITY_MPS2 +
        (SYSTEM_FLIGHT_LANDING_STILL_ACCEL_TOLERANCE_MPS2 * 2.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active != 0U);
    Test_BaroSampleAdvance(&input, 210000ULL, 100.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active == 0U);
    TEST_CHECK(s_enter_landed_count == 0U);

    /* Stable IMU cannot override a changing direct-Baro candidate. */
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroCandidateStart(&input, 100.0f);
    Test_BaroSampleAdvance(&input, 10000ULL, 100.0f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(&input, 100000ULL, 100.7f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroSampleAdvance(&input, 100000ULL, 101.4f);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active == 0U);
    TEST_CHECK(s_enter_landed_count == 0U);

    /* Fresh Baro with a stale IMU also cancels the synchronized window. */
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroCandidateStart(&input, 100.0f);
    input.now_us +=
        ((uint64_t)SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS * 1000ULL) +
        1ULL;
    input.barometer_timestamp_us = input.now_us;
    input.barometer_sequence++;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.landing_candidate_active == 0U);
    TEST_CHECK(s_enter_landed_count == 0U);

    /* A stale/unhealthy Baro cannot land and cannot silently use KF/INS. */
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_BaroCandidateStart(&input, 100.0f);
    input.now_us +=
        ((uint64_t)SYSTEM_FLIGHT_LANDING_SAMPLE_MAX_AGE_MS * 1000ULL) +
        1ULL;
    input.inertial_timestamp_us = input.now_us;
    input.inertial_sequence++;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.barometer_valid == 0U);
    TEST_CHECK(status.landing_candidate_active == 0U);
    TEST_CHECK(s_enter_landed_count == 0U);
#else
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    Test_InputTimeSet(&input, input.now_us +
        ((uint64_t)SYSTEM_FLIGHT_LANDING_IMPACT_INHIBIT_MS * 1000ULL) +
        confirm_us + 1ULL);
    TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFlightRecovery_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.impact_event_sequence == 0U);
    TEST_CHECK(status.landing_detected == 0U);
#endif
}

static void Test_InvalidArguments(void)
{
    TEST_CHECK(SystemFlightRecovery_Process(NULL) ==
               SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemFlightRecovery_StatusGet(NULL) ==
               SYSTEM_DEVICE_INVALID_ARGUMENT);
}

static void Test_LandingMixedSourceRates(void)
{
#if defined(TEST_EXPECT_BARO)
    SystemFlightRecoveryInput input;
    uint64_t barometer_time;
    uint32_t barometer_sequence;
    unsigned int index;
    Test_ManagerReset();
    Test_InputInit(&input);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    input.barometer_altitude_m = 100.0f;
    barometer_time = input.barometer_timestamp_us;
    barometer_sequence = input.barometer_sequence;
    /* IMU 200 Hz and barometer 20 Hz have distinct sequence/timestamp clocks. */
    for (index = 0U; index < 400U; index++)
    {
        Test_InputTimeSet(&input, input.now_us + 5000ULL);
        if ((index % 10U) == 0U)
        {
            barometer_time = input.now_us;
            barometer_sequence++;
        }
        input.barometer_timestamp_us = barometer_time;
        input.barometer_sequence = barometer_sequence;
        TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
    }
    TEST_CHECK(s_enter_landed_count == 1U);
#endif
}

static void Test_LandingTimeCoverage(void)
{
    const uint32_t periods[3] = {10000U, 5000U, 2500U};
    unsigned int rate;
    unsigned int scenario;
    for (rate = 0U; rate < 3U; rate++)
    {
        for (scenario = 0U; scenario < 5U; scenario++)
        {
            FlightLandingTimeWindow window;
            uint64_t time;
            FlightLanding_TimeWindowReset(&window, 1000000ULL);
            for (time = 1000000ULL + periods[rate]; time <= 4000000ULL; time += periods[rate])
            {
                uint8_t valid = (uint8_t)!((scenario == 2U) && (time >= 2000000ULL) && (time < 2040000ULL));
                uint8_t still = (uint8_t)!(((scenario == 1U) && (time == 2000000ULL)) ||
                    ((scenario == 3U) && (time >= 2000000ULL) && (time < 2220000ULL)) || (scenario == 4U));
                TEST_CHECK(FlightLanding_TimeWindowAdd(&window, time, valid, still) == FLIGHT_LANDING_RESULT_OK);
            }
            TEST_CHECK(FlightLanding_TimeWindowEvaluate(&window, 3000000ULL) ==
                ((scenario < 3U) ? FLIGHT_LANDING_CONDITION_MET : FLIGHT_LANDING_CONDITION_NOT_MET));
        }
    }
}

int main(void)
{
    Test_LandingTimeCoverage();
    Test_LandingMixedSourceRates();
    Test_StartActionOneShot();
    Test_AutomaticDeployment();
    Test_DeploySampleValidityAndReset();
    Test_DeployHasNoAbsoluteAgeVeto();
    Test_PreflightSnapshotIsNotNewAfterTransition();
    Test_DeployActionAndTransitionFailuresAreOneShot();
    Test_TiltInitialAxisReference();
    Test_OrDeploymentTriggers();
    Test_LandingDetection();
    Test_InvalidArguments();
    return Test_Finish("flight_recovery");
}
