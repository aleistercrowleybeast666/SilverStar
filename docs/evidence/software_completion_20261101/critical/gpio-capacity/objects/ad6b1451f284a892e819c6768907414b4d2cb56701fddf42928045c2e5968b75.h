#ifndef __PLATFORM_SPI_H
#define __PLATFORM_SPI_H

#include <stdint.h>

#include "platform_types.h"

typedef enum
{
    PLATFORM_SPI_1 = 0,
    PLATFORM_SPI_COUNT = 3
} PlatformSpiId;

/* Filled by an observed call before that call returns to its owner. The
 * numeric HAL values are diagnostic only and retain the MCU HAL ABI. */
typedef struct
{
    uint32_t driver_status;
    uint32_t driver_error_code;
    uint32_t driver_state;
    uint32_t spi_sr;
    uint32_t driver_elapsed_ms;
    uint16_t tx_remaining;
    uint16_t rx_remaining;
    uint8_t valid;
} PlatformSpiDriverObservation;

PlatformResult PlatformSpi_WriteObserved(PlatformSpiId id,
    const uint8_t *data, uint16_t length, uint32_t timeout_ms,
    PlatformSpiDriverObservation *observation);
PlatformResult PlatformSpi_TransferObserved(PlatformSpiId id,
    const uint8_t *tx_data, uint8_t *rx_data, uint16_t length,
    uint32_t timeout_ms, PlatformSpiDriverObservation *observation);

PlatformResult PlatformSpi_Write(PlatformSpiId id,
                                 const uint8_t *data,
                                 uint16_t length,
                                 uint32_t timeout_ms);
PlatformResult PlatformSpi_Transfer(PlatformSpiId id,
                                    const uint8_t *tx_data,
                                    uint8_t *rx_data,
                                    uint16_t length,
                                    uint32_t timeout_ms);

#endif /* __PLATFORM_SPI_H */
