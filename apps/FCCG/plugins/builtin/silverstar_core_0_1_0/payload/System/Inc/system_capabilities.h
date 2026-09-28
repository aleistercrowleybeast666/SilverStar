#ifndef __SYSTEM_CAPABILITIES_H
#define __SYSTEM_CAPABILITIES_H

#include <stdint.h>

#include "system_device_types.h"

#define SYSTEM_CAPABILITY_IMU                 (1UL << 0)
#define SYSTEM_CAPABILITY_GNSS                (1UL << 1)
#define SYSTEM_CAPABILITY_MAGNETOMETER        (1UL << 2)
#define SYSTEM_CAPABILITY_BAROMETER           (1UL << 3)
#define SYSTEM_CAPABILITY_HARDWARE_QUATERNION (1UL << 4)
#define SYSTEM_CAPABILITY_TELEMETRY           (1UL << 5)
#define SYSTEM_CAPABILITY_CONSOLE             (1UL << 6)
#define SYSTEM_CAPABILITY_POWER               (1UL << 7)
#define SYSTEM_CAPABILITY_STORAGE             (1UL << 8)
#define SYSTEM_CAPABILITY_OUTPUT              (1UL << 9)

typedef struct
{
    uint32_t compiled_mask;
    uint32_t enabled_mask;
    uint32_t present_mask;
    uint32_t healthy_mask;
} SystemCapabilities;

SystemDeviceResult SystemCapabilities_Refresh(void);
void SystemCapabilities_Get(SystemCapabilities *capabilities);
uint8_t SystemCapabilities_RequiredAvailable(uint32_t required_mask);

#endif /* __SYSTEM_CAPABILITIES_H */
