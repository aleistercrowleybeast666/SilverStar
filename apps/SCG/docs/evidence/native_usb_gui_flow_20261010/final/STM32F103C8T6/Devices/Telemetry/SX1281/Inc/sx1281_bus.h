#ifndef __SX1281_BUS_H
#define __SX1281_BUS_H

#include <stdint.h>

#include "platform_gpio.h"
#include "platform_types.h"

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
    uint32_t first_failure_at_ms;
    uint32_t first_failure_elapsed_ms;
    PlatformResult first_failure_platform_result;
    Sx1281BusResult first_failure_result;
    uint16_t first_failure_length;
    uint8_t first_failure_opcode;
    uint8_t first_failure_valid;
    uint8_t first_failure_opcode_valid;
    uint8_t first_failure_platform_result_valid;
    uint8_t first_failure_driver_valid;
    uint32_t first_failure_driver_status;
    uint32_t first_failure_driver_error_code;
    uint32_t first_failure_driver_state;
    uint32_t first_failure_spi_sr;
    uint32_t first_failure_driver_elapsed_ms;
    uint16_t first_failure_tx_remaining;
    uint16_t first_failure_rx_remaining;
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
