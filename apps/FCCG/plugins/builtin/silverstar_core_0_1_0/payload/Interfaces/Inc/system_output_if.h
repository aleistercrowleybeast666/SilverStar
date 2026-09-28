#ifndef __SYSTEM_OUTPUT_IF_H
#define __SYSTEM_OUTPUT_IF_H

#include "system_device_types.h"

typedef enum
{
    SYSTEM_OUTPUT_SAFE = 0,
    SYSTEM_OUTPUT_ARMED,
    SYSTEM_OUTPUT_ACTIVE,
    SYSTEM_OUTPUT_FAULT
} SystemOutputState;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    uint32_t requested_duration_ms;
    uint32_t remaining_duration_ms;
    SystemOutputState state;
    uint8_t channel;
    uint8_t commanded_active;
    uint8_t physical_active;
    uint8_t fault;
} SystemOutputStatus;

const char *SystemOutput_NameGet(void);
SystemDeviceResult SystemOutput_Init(void);
SystemDeviceResult SystemOutput_SafeSet(void);
SystemDeviceResult SystemOutput_Arm(uint8_t channel);
SystemDeviceResult SystemOutput_Activate(uint8_t channel,
                                         uint32_t duration_ms);
SystemDeviceResult SystemOutput_Deactivate(uint8_t channel);
SystemDeviceResult SystemOutput_StatusGet(uint8_t channel,
                                          SystemOutputStatus *status);
void SystemOutput_Process(void);

#endif /* __SYSTEM_OUTPUT_IF_H */
