#include "system_mission_action_if.h"

#include "system_output_if.h"
#include "mission_action_output_config.h"
#include "silverstar_assert.h"

static uint8_t s_initialized;

static SystemDeviceResult SilverStarMissionActionService_Init(void)
{
    if (s_initialized != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    s_initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarMissionActionService_Execute(
    SystemMissionAction action)
{
    SystemDeviceResult arm_result;
    SystemDeviceResult activate_result;
    uint32_t pulse_ms;
    uint8_t channel;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    switch (action)
    {
        case SYSTEM_MISSION_ACTION_START:
            channel = MISSION_ACTION_START_OUTPUT_CHANNEL;
            pulse_ms = MISSION_ACTION_START_PULSE_MS;
            break;
        case SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY:
            channel = MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL;
            pulse_ms = MISSION_ACTION_DEPLOY_PULSE_MS;
            break;
        default:
            return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT(
        (channel == MISSION_ACTION_START_OUTPUT_CHANNEL) ||
            (channel == MISSION_ACTION_DEPLOY_OUTPUT_CHANNEL),
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(pulse_ms > 0U, SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);

    arm_result = SystemOutput_Arm(channel);
    if ((arm_result != SYSTEM_DEVICE_OK) &&
        (arm_result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        return arm_result;
    }
    activate_result = SystemOutput_Activate(channel, pulse_ms);
    if (activate_result != SYSTEM_DEVICE_OK)
    {
        (void)SystemOutput_Deactivate(channel);
    }
    return activate_result;
}

const char *SystemMissionAction_NameGet(void) { return "Output Mission Action"; }
SystemDeviceResult SystemMissionAction_Init(void)
{ return SilverStarMissionActionService_Init(); }
SystemDeviceResult SystemMissionAction_Execute(SystemMissionAction action)
{ return SilverStarMissionActionService_Execute(action); }
