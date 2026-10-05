#include <stdint.h>

#include "mission_action_output_config.h"
#include "system_mission_action_if.h"
#include "system_output_if.h"
#include "test_common.h"

static SystemDeviceResult s_arm_result;
static SystemDeviceResult s_activate_result;
static uint32_t s_arm_count;
static uint32_t s_activate_count;
static uint32_t s_deactivate_count;
static uint8_t s_last_arm_channel;
static uint8_t s_last_activate_channel;
static uint8_t s_last_deactivate_channel;
static uint32_t s_last_duration_ms;

SystemDeviceResult SystemOutput_Arm(uint8_t channel)
{
    s_arm_count++;
    s_last_arm_channel = channel;
    return s_arm_result;
}

SystemDeviceResult SystemOutput_Activate(uint8_t channel,
                                         uint32_t duration_ms)
{
    s_activate_count++;
    s_last_activate_channel = channel;
    s_last_duration_ms = duration_ms;
    return s_activate_result;
}

SystemDeviceResult SystemOutput_Deactivate(uint8_t channel)
{
    s_deactivate_count++;
    s_last_deactivate_channel = channel;
    return SYSTEM_DEVICE_OK;
}

static void Test_ActionMapsToOutput(void)
{
    s_arm_result = SYSTEM_DEVICE_OK;
    s_activate_result = SYSTEM_DEVICE_OK;
    TEST_CHECK(SystemMissionAction_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemMissionAction_Init() == SYSTEM_DEVICE_ALREADY_MATCHED);
    TEST_CHECK(SystemMissionAction_Execute(SYSTEM_MISSION_ACTION_START) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(s_arm_count == 1U && s_activate_count == 1U);
    TEST_CHECK(s_last_arm_channel == MISSION_ACTION_START_OUTPUT_CHANNEL);
    TEST_CHECK(s_last_activate_channel == MISSION_ACTION_START_OUTPUT_CHANNEL);
    TEST_CHECK(s_last_duration_ms == MISSION_ACTION_START_PULSE_MS);

    TEST_CHECK(SystemMissionAction_Execute(
        SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_last_arm_channel == MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL);
    TEST_CHECK(s_last_activate_channel == MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL);
    TEST_CHECK(s_last_duration_ms == MISSION_ACTION_DEPLOY_PULSE_MS);
}

static void Test_ActivationFailureReturnsSafe(void)
{
    s_activate_result = SYSTEM_DEVICE_IO_ERROR;
    TEST_CHECK(SystemMissionAction_Execute(
        SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY) == SYSTEM_DEVICE_IO_ERROR);
    TEST_CHECK(s_deactivate_count == 1U);
    TEST_CHECK(s_last_deactivate_channel ==
               MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL);
    TEST_CHECK(SystemMissionAction_Execute((SystemMissionAction)99) ==
               SYSTEM_DEVICE_INVALID_ARGUMENT);
}

int main(void)
{
    Test_ActionMapsToOutput();
    Test_ActivationFailureReturnsSafe();
    return Test_Finish("board_mission_action_service");
}
