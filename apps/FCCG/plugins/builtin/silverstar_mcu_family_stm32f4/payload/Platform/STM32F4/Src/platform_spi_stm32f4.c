#include "platform_spi.h"

#include "platform_stm32f4_resources.h"
#include "stm32f4xx_hal.h"

static SPI_HandleTypeDef *PlatformSpi_HandleGet(PlatformSpiId id)
{
    return (SPI_HandleTypeDef *)PlatformStm32f4Resource_SpiHandleGet(id);
}

/* STM32 HAL transmit APIs predate const-correct buffer declarations. */
static uint8_t *PlatformSpi_HalTransmitBufferGet(const uint8_t *data)
{
    return (uint8_t *)(uintptr_t)data;
}

static PlatformResult PlatformSpi_ResultMap(HAL_StatusTypeDef result)
{
    if (result == HAL_OK) { return PLATFORM_OK; }
    if (result == HAL_TIMEOUT) { return PLATFORM_TIMEOUT; }
    if (result == HAL_BUSY) { return PLATFORM_BUSY; }
    return PLATFORM_IO_ERROR;
}

PlatformResult PlatformSpi_Write(PlatformSpiId id,
                                 const uint8_t *data,
                                 uint16_t length,
                                 uint32_t timeout_ms)
{
    SPI_HandleTypeDef *handle = PlatformSpi_HandleGet(id);

    if ((handle == NULL) || (data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformSpi_ResultMap(
        HAL_SPI_Transmit(handle, PlatformSpi_HalTransmitBufferGet(data),
                         length, timeout_ms));
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id,
                                    const uint8_t *tx_data,
                                    uint8_t *rx_data,
                                    uint16_t length,
                                    uint32_t timeout_ms)
{
    SPI_HandleTypeDef *handle = PlatformSpi_HandleGet(id);

    if ((handle == NULL) || (tx_data == NULL) || (rx_data == NULL) ||
        (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    return PlatformSpi_ResultMap(HAL_SPI_TransmitReceive(
        handle, PlatformSpi_HalTransmitBufferGet(tx_data), rx_data,
        length, timeout_ms));
}
