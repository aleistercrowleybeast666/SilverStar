#include "project_resources.h"
#include <stddef.h>
SystemDeviceResult ProjectSx1281Resources_Get(uint8_t instance,ProjectSx1281Resources *resources)
{
    if (resources == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance >= PROJECT_SX1281_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    *resources = (ProjectSx1281Resources){PLATFORM_SPI_1,PLATFORM_GPIO_0,PLATFORM_GPIO_1,
        PLATFORM_GPIO_2,PLATFORM_GPIO_3,PLATFORM_TIME_1,
        (PlatformGpioId)PLATFORM_GPIO_COUNT,(PlatformGpioId)PLATFORM_GPIO_COUNT};
    return SYSTEM_DEVICE_OK;
}
