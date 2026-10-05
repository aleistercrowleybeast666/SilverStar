#ifndef __PLATFORM_SPI_H
#define __PLATFORM_SPI_H

#include <stdint.h>

#include "platform_types.h"

typedef enum
{
    PLATFORM_SPI_1 = 0,
    PLATFORM_SPI_COUNT = 3
} PlatformSpiId;

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
