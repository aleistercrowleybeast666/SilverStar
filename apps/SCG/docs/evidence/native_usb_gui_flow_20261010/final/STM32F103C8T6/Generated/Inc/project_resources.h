#ifndef __PROJECT_RESOURCES_H
#define __PROJECT_RESOURCES_H
#include "platform_spi.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "system_device_types.h"
#define PROJECT_SX1281_INSTANCE_COUNT 1U
#define PROJECT_SX1281_INSTANCE_COUNT_MAX 4U
typedef struct {
    PlatformSpiId spi; PlatformGpioId nss,reset,busy,dio1;
    PlatformTimeId time; PlatformGpioId rx_en,tx_en;
} ProjectSx1281Resources;
SystemDeviceResult ProjectSx1281Resources_Get(uint8_t instance,ProjectSx1281Resources *resources);
#endif /* __PROJECT_RESOURCES_H */
