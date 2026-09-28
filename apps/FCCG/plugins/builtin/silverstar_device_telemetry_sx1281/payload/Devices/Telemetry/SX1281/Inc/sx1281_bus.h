#ifndef __SX1281_BUS_H
#define __SX1281_BUS_H

#include <stdint.h>

#include "platform_gpio.h"

typedef enum
{
    SX1281_BUS_OK = 0,
    SX1281_BUS_SPI_ERROR,
    SX1281_BUS_SPI_TIMEOUT,
    SX1281_BUS_BUSY_TIMEOUT
} Sx1281BusResult;

typedef struct
{
    Sx1281BusResult last_result;
    uint32_t spi_error_count;
    uint32_t spi_timeout_count;
    uint32_t busy_timeout_count;
} Sx1281BusStatus;

void Sx1281Bus_Init(uint8_t instance);
void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status);
PlatformGpioId Sx1281Bus_NssGet(uint8_t instance);
PlatformGpioId Sx1281Bus_ResetGet(uint8_t instance);
PlatformGpioId Sx1281Bus_BusyGet(uint8_t instance);
PlatformGpioId Sx1281Bus_Dio1Get(uint8_t instance);
void GpioWrite(uint8_t instance, PlatformGpioId id, uint32_t value);
uint8_t GpioRead(uint8_t instance, PlatformGpioId id);
void SpiIn(uint8_t instance, const uint8_t *tx_buffer, uint16_t size);
void SpiInOut(uint8_t instance, const uint8_t *tx_buffer,
              uint8_t *rx_buffer, uint16_t size);
uint8_t GpioWaitLow(
    uint8_t instance, PlatformGpioId id, uint32_t timeout_ms);

#endif /* __SX1281_BUS_H */
