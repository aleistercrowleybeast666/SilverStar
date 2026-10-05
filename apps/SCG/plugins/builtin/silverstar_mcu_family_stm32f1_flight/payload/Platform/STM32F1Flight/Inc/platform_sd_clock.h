#ifndef __PLATFORM_SD_CLOCK_H
#define __PLATFORM_SD_CLOCK_H

#include <stdint.h>

typedef enum
{
    PlatformSdClockResult_Ok = 0U,
    PlatformSdClockResult_InvalidArgument,
    PlatformSdClockResult_UnsupportedClock
} PlatformSdClockResult;

PlatformSdClockResult PlatformSdClock_InitializationDividerResolve(
    uint32_t nominal_sdioclk_hz, uint32_t *divider);
PlatformSdClockResult PlatformSdClock_TransferValidate(
    uint32_t nominal_sdioclk_hz, uint32_t divider, uint32_t bypass_enabled);

#endif /* __PLATFORM_SD_CLOCK_H */
