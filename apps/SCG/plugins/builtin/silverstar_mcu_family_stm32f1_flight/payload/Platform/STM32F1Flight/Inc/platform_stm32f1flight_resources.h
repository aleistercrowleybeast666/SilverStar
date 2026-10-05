#ifndef __PLATFORM_STM32F1FLIGHT_RESOURCES_H
#define __PLATFORM_STM32F1FLIGHT_RESOURCES_H

#include <stdint.h>

#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "platform_uart.h"

typedef struct
{
    void *port;
    uint16_t pin;
    uint8_t irq_enabled;
} PlatformStm32f1flightGpioResource;

typedef struct
{
    void *handle;
    uint32_t counter_frequency_hz;
    uint32_t period_counts;
    uint32_t tick_frequency_hz;
} PlatformStm32f1flightTimeResource;

void *PlatformStm32f1flightResource_UartHandleGet(PlatformUartId id);
void *PlatformStm32f1flightResource_SpiHandleGet(PlatformSpiId id);
uint8_t PlatformStm32f1flightResource_GpioGet(
    PlatformGpioId id,
    PlatformStm32f1flightGpioResource *resource);
void *PlatformStm32f1flightResource_I2cHandleGet(PlatformI2cId id);
uint8_t PlatformStm32f1flightResource_TimeGet(
    PlatformTimeId id,
    PlatformStm32f1flightTimeResource *resource);

#endif /* __PLATFORM_STM32F1FLIGHT_RESOURCES_H */
