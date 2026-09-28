#include "system_indicator_if.h"

#include "project_resources.h"
#include "platform_gpio.h"

static SystemDeviceResult SilverStarIndicatorService_Set(uint8_t channel,
                                            uint8_t logical_on)
{
    switch (channel)
    {
        case 0U:
            return (PlatformGpio_Write(PROJECT_RESOURCE_SYSTEM_INDICATOR,
                                       (uint8_t)((logical_on != 0U) ?
                                           0U : 1U)) ==
                    PLATFORM_OK) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
        case 1U:
        case 2U:
        default:
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

SystemDeviceResult SystemIndicatorDevice_Set(uint8_t channel,
                                             uint8_t logical_on)
{
    return SilverStarIndicatorService_Set(channel, logical_on);
}
