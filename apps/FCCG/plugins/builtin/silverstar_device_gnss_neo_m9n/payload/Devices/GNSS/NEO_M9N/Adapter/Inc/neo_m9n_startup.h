#ifndef __NEO_M9N_STARTUP_H
#define __NEO_M9N_STARTUP_H

#include <stdint.h>

#include "system_device_startup.h"
#include "system_gnss_if.h"

typedef enum
{
    NeoM9nStartupResult_Ok = 0,
    NeoM9nStartupResult_InvalidArgument,
    NeoM9nStartupResult_ControllerError
} NeoM9nStartupResult;

NeoM9nStartupResult NeoM9nStartup_Init(
    uint8_t instance, const SystemGnssConfig *target);
void NeoM9nStartup_Tick(uint8_t instance, uint32_t now_ms);
SystemDeviceStartupState NeoM9nStartup_StateGet(uint8_t instance);
SystemDeviceStartupFailure NeoM9nStartup_FailureGet(uint8_t instance);

#endif /* __NEO_M9N_STARTUP_H */
