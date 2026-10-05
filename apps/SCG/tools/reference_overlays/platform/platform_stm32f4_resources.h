#ifndef __PLATFORM_STM32F4_RESOURCES_H
#define __PLATFORM_STM32F4_RESOURCES_H

#include <stdint.h>

#include "platform_adc.h"
#include "platform_can.h"
#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_pwm.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "platform_uart.h"

typedef struct
{
    void *port;
    uint16_t pin;
    uint8_t irq_enabled;
} PlatformStm32f4GpioResource;

typedef struct
{
    void *handle;
    uint32_t channel;
    uint32_t frequency_hz;
    uint16_t resolution_bits;
    PlatformPwmMode mode;
    uint8_t active_high;
} PlatformStm32f4PwmResource;

typedef struct
{
    void *handle;
    uint32_t counter_frequency_hz;
    uint32_t period_counts;
    uint32_t tick_frequency_hz;
} PlatformStm32f4TimeResource;

void *PlatformStm32f4Resource_UartHandleGet(PlatformUartId id);
void *PlatformStm32f4Resource_SpiHandleGet(PlatformSpiId id);
void *PlatformStm32f4Resource_AdcHandleGet(PlatformAdcId id);
uint8_t PlatformStm32f4Resource_GpioGet(
    PlatformGpioId id,
    PlatformStm32f4GpioResource *resource);
void *PlatformStm32f4Resource_I2cHandleGet(PlatformI2cId id);
void *PlatformStm32f4Resource_CanHandleGet(PlatformCanId id);
uint8_t PlatformStm32f4Resource_PwmGet(
    PlatformPwmId id,
    PlatformStm32f4PwmResource *resource);
uint8_t PlatformStm32f4Resource_TimeGet(
    PlatformTimeId id,
    PlatformStm32f4TimeResource *resource);

#endif /* __PLATFORM_STM32F4_RESOURCES_H */
