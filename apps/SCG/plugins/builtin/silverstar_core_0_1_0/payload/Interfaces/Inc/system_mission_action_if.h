#ifndef __SYSTEM_MISSION_ACTION_IF_H
#define __SYSTEM_MISSION_ACTION_IF_H

#include "system_device_types.h"

typedef enum
{
    SYSTEM_MISSION_ACTION_START = 0,
    SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY
} SystemMissionAction;

const char *SystemMissionAction_NameGet(void);
SystemDeviceResult SystemMissionAction_Init(void);
SystemDeviceResult SystemMissionAction_Execute(SystemMissionAction action);

#endif /* __SYSTEM_MISSION_ACTION_IF_H */
