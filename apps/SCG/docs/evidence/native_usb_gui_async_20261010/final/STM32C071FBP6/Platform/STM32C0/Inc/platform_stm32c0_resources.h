#ifndef __PLATFORM_STM32C0_RESOURCES_H
#define __PLATFORM_STM32C0_RESOURCES_H

#include <stdint.h>

#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "platform_uart.h"

typedef struct
{
    void *port;
    uint16_t pin;
    uint8_t irq_enabled;
} PlatformStm32c0GpioResource;

typedef struct
{
    uint32_t tick_frequency_hz;
} PlatformStm32c0TimeResource;

void *PlatformStm32c0Resource_UartHandleGet(PlatformUartId id);
void *PlatformStm32c0Resource_SpiHandleGet(PlatformSpiId id);
uint8_t PlatformStm32c0Resource_GpioGet(
    PlatformGpioId id, PlatformStm32c0GpioResource *resource);
uint8_t PlatformStm32c0Resource_TimeGet(
    PlatformTimeId id, PlatformStm32c0TimeResource *resource);

#endif /* __PLATFORM_STM32C0_RESOURCES_H */
