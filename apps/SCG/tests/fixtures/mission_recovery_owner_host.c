/* Reuse the existing owner mocks, while retaining its legacy main as a distinct
 * test entry. This executable proves phase-owned action policy, not hardware. */
#define main MissionLegacy_ReferenceMain
#include "test_flight_recovery.c"
#undef main
#include "project_mission_process.h"

int main(void)
{
    SystemFlightRecoveryInput input;
    SystemFlightRecoveryStatus status;
    Test_ManagerReset();
    Test_InputInit(&input);
    TEST_CHECK(SystemFlightRecovery_StageRecoveryRequest(UINT32_MAX) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    if (PROJECT_MISSION_RECOVERY_STAGE_HASH == 0U)
    {
        input.velocity_enu_mps[2] = -100.0f;
        for (uint32_t i = 0U; i < 1000U; i++)
        {
            Test_InputTimeSet(&input, input.now_us + 10000000ULL);
            input.mission_time_ms += 10000U;
            TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
        }
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_START] == 0U);
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
        TEST_CHECK(s_enter_landed_count == 0U && s_enter_recovery_count == 0U);
        TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_FLIGHT);
        TEST_CHECK(Test_RecoveryStatusGet(&status) == SYSTEM_DEVICE_OK);
        TEST_CHECK(status.deploy_triggered == 0U && status.landing_detected == 0U);
    }
    else
    {
        input.velocity_enu_mps[2] = 100.0f;
        TEST_CHECK(SystemFlightRecovery_StageRecoveryRequest(PROJECT_MISSION_RECOVERY_STAGE_HASH) == SYSTEM_DEVICE_OK);
        TEST_CHECK(SystemFlightRecovery_StageRecoveryRequest(PROJECT_MISSION_RECOVERY_STAGE_HASH) == SYSTEM_DEVICE_ALREADY_MATCHED);
        TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
        Test_InputTimeSet(&input, input.now_us + 100000ULL);
        input.velocity_enu_mps[2] = -100.0f;
        TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_START] == 0U);
        TEST_CHECK(s_enter_recovery_count == 1U);
        Test_ManagerReset(); Test_InputInit(&input); s_lifecycle_state = SYSTEM_STATE_FLIGHT;
        input.velocity_enu_mps[2] = -100.0f;
        s_action_results[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] = SYSTEM_DEVICE_IO_ERROR;
        TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 0U);
        TEST_CHECK(SystemFlightRecovery_StageRecoveryRequest(PROJECT_MISSION_RECOVERY_STAGE_HASH) == SYSTEM_DEVICE_OK);
        TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_IO_ERROR);
        TEST_CHECK(SystemFlightRecovery_Process(&input) == SYSTEM_DEVICE_OK);
        TEST_CHECK(s_action_counts[SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY] == 1U);
        TEST_CHECK(s_enter_recovery_count == 0U);
    }
    return Test_Finish("mission_recovery_owner");
}
