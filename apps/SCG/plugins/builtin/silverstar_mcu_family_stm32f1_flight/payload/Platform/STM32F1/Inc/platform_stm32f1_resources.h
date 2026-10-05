#ifndef __PLATFORM_STM32F1_RESOURCES_H
#define __PLATFORM_STM32F1_RESOURCES_H

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
} PlatformStm32f1GpioResource;

typedef struct
{
    uint32_t tick_frequency_hz;
} PlatformStm32f1TimeResource;

void *PlatformStm32f1Resource_UartHandleGet(PlatformUartId id);
void *PlatformStm32f1Resource_SpiHandleGet(PlatformSpiId id);
uint8_t PlatformStm32f1Resource_GpioGet(
    PlatformGpioId id, PlatformStm32f1GpioResource *resource);
uint8_t PlatformStm32f1Resource_TimeGet(
    PlatformTimeId id, PlatformStm32f1TimeResource *resource);

#endif /* __PLATFORM_STM32F1_RESOURCES_H */
