#ifndef __PROJECT_RESOURCES_H
#define __PROJECT_RESOURCES_H

#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "system_device_types.h"

#define PROJECT_NEO_M9N_INSTANCE_COUNT     2U
#define PROJECT_NEO_M9N_INSTANCE_COUNT_MAX 4U

typedef struct
{
    PlatformUartId uart;
    PlatformGpioId reset;
    PlatformGpioId timepulse;
    PlatformTimeId time;
} ProjectNeoM9nResources;

SystemDeviceResult ProjectNeoM9nResources_Get(
    uint8_t source_instance, ProjectNeoM9nResources *resources);

#define PROJECT_JY901B_INSTANCE_COUNT     2U
#define PROJECT_JY901B_INSTANCE_COUNT_MAX 4U

typedef struct
{
    PlatformUartId uart;
    PlatformTimeId time;
} ProjectJy901bResources;

SystemDeviceResult ProjectJy901bResources_Get(
    uint8_t source_instance, ProjectJy901bResources *resources);

#define PROJECT_SX1281_INSTANCE_COUNT     2U
#define PROJECT_SX1281_INSTANCE_COUNT_MAX 4U

typedef struct
{
    PlatformSpiId spi;
    PlatformGpioId nss;
    PlatformGpioId reset;
    PlatformGpioId busy;
    PlatformGpioId dio1;
    PlatformTimeId time;
} ProjectSx1281Resources;

SystemDeviceResult ProjectSx1281Resources_Get(
    uint8_t source_instance, ProjectSx1281Resources *resources);

#endif /* __PROJECT_RESOURCES_H */
