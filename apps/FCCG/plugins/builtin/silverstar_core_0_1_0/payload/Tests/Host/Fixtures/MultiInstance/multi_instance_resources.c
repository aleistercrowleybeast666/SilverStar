#include "project_resources.h"

#include <stddef.h>

static const ProjectNeoM9nResources s_gnss_resources[] =
{
    {PLATFORM_UART_1, PLATFORM_GPIO_0, PLATFORM_GPIO_1, PLATFORM_TIME_1},
    {PLATFORM_UART_2, PLATFORM_GPIO_2, PLATFORM_GPIO_3, PLATFORM_TIME_1}
};

static const ProjectJy901bResources s_imu_resources[] =
{
    {PLATFORM_UART_1, PLATFORM_TIME_1},
    {PLATFORM_UART_2, PLATFORM_TIME_1}
};

static const ProjectSx1281Resources s_telemetry_resources[] =
{
    {PLATFORM_SPI_1, PLATFORM_GPIO_4, PLATFORM_GPIO_5,
     PLATFORM_GPIO_6, PLATFORM_GPIO_7, PLATFORM_TIME_1},
    {(PlatformSpiId)1U, PLATFORM_GPIO_8, (PlatformGpioId)9U,
     (PlatformGpioId)10U, (PlatformGpioId)11U, PLATFORM_TIME_1}
};

SystemDeviceResult ProjectNeoM9nResources_Get(
    uint8_t source_instance, ProjectNeoM9nResources *resources)
{
    if (resources == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (source_instance >= PROJECT_NEO_M9N_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *resources = s_gnss_resources[source_instance];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectJy901bResources_Get(
    uint8_t source_instance, ProjectJy901bResources *resources)
{
    if (resources == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (source_instance >= PROJECT_JY901B_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *resources = s_imu_resources[source_instance];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectSx1281Resources_Get(
    uint8_t source_instance, ProjectSx1281Resources *resources)
{
    if (resources == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (source_instance >= PROJECT_SX1281_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *resources = s_telemetry_resources[source_instance];
    return SYSTEM_DEVICE_OK;
}
