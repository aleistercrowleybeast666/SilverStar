#ifndef __HW_H__
#define __HW_H__

#include <stdint.h>
#include "project_resources.h"
#include "platform_gpio.h"
#include "sx1280.h"

#include "sx1281_bus.h"

#define RADIO_NSS   Sx1281Bus_NssGet(instance)
#define RADIO_BUSY  Sx1281Bus_BusyGet(instance)
#define RADIO_RESET Sx1281Bus_ResetGet(instance)
#define RADIO_DIO1  Sx1281Bus_Dio1Get(instance)

void GpioWrite(uint8_t instance, PlatformGpioId id, uint32_t value);
uint8_t GpioRead(uint8_t instance, PlatformGpioId id);
uint8_t GpioWaitLow(
    uint8_t instance, PlatformGpioId id, uint32_t timeout_ms);

void SpiIn(uint8_t instance, const uint8_t *tx_buffer, uint16_t size);
void SpiInOut(uint8_t instance, const uint8_t *tx_buffer,
              uint8_t *rx_buffer, uint16_t size);

#endif
