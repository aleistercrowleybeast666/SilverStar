#ifndef __JY901B_STARTUP_H
#define __JY901B_STARTUP_H

#include <stdint.h>

#include "jy901b_device.h"
#include "system_device_startup.h"

typedef enum
{
    Jy901bStartupResult_Ok = 0,
    Jy901bStartupResult_InvalidArgument,
    Jy901bStartupResult_ControllerError
} Jy901bStartupResult;

Jy901bStartupResult Jy901bStartup_Init(
    uint8_t instance, IMUOutputRate output_rate, IMUAlgorithm algorithm);
void Jy901bStartup_Tick(uint8_t instance, uint32_t now_ms);
SystemDeviceStartupState Jy901bStartup_StateGet(uint8_t instance);
SystemDeviceStartupFailure Jy901bStartup_FailureGet(uint8_t instance);

#endif /* __JY901B_STARTUP_H */
