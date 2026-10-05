#include "platform_spi.h"

#include "platform_stm32f1flight_resources.h"
#include "stm32f1xx_hal.h"

static SPI_HandleTypeDef *PlatformSpi_HandleGet(PlatformSpiId id)
{
    return (SPI_HandleTypeDef *)PlatformStm32f1flightResource_SpiHandleGet(id);
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

PlatformResult PlatformSpi_WriteObserved(PlatformSpiId id,
    const uint8_t *data, uint16_t length, uint32_t timeout_ms,
    PlatformSpiDriverObservation *observation)
{
    SPI_HandleTypeDef *handle = PlatformSpi_HandleGet(id);
    HAL_StatusTypeDef hal_result;
    uint32_t started_ms;

    if (observation != NULL) { observation->valid = 0U; }
    if ((handle == NULL) || (data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    started_ms = HAL_GetTick();
    hal_result = HAL_SPI_Transmit(handle, PlatformSpi_HalTransmitBufferGet(data),
        length, timeout_ms);
    uint32_t elapsed_ms = HAL_GetTick() - started_ms;
    if (observation != NULL)
    {
        observation->driver_status = (uint32_t)hal_result;
        observation->driver_error_code = handle->ErrorCode;
        observation->driver_state = (uint32_t)handle->State;
        observation->spi_sr = handle->Instance->SR;
        observation->driver_elapsed_ms = elapsed_ms;
        observation->tx_remaining = handle->TxXferCount;
        observation->rx_remaining = handle->RxXferCount;
        observation->valid = 1U;
    }
    return PlatformSpi_ResultMap(hal_result);
}

PlatformResult PlatformSpi_Write(PlatformSpiId id,
    const uint8_t *data, uint16_t length, uint32_t timeout_ms)
{
    return PlatformSpi_WriteObserved(id, data, length, timeout_ms, NULL);
}

PlatformResult PlatformSpi_TransferObserved(PlatformSpiId id,
    const uint8_t *tx_data, uint8_t *rx_data, uint16_t length,
    uint32_t timeout_ms, PlatformSpiDriverObservation *observation)
{
    SPI_HandleTypeDef *handle = PlatformSpi_HandleGet(id);
    HAL_StatusTypeDef hal_result;
    uint32_t started_ms;

    if (observation != NULL) { observation->valid = 0U; }
    if ((handle == NULL) || (tx_data == NULL) || (rx_data == NULL) ||
        (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    started_ms = HAL_GetTick();
    hal_result = HAL_SPI_TransmitReceive(
        handle, PlatformSpi_HalTransmitBufferGet(tx_data), rx_data,
        length, timeout_ms);
    uint32_t elapsed_ms = HAL_GetTick() - started_ms;
    if (observation != NULL)
    {
        observation->driver_status = (uint32_t)hal_result;
        observation->driver_error_code = handle->ErrorCode;
        observation->driver_state = (uint32_t)handle->State;
        observation->spi_sr = handle->Instance->SR;
        observation->driver_elapsed_ms = elapsed_ms;
        observation->tx_remaining = handle->TxXferCount;
        observation->rx_remaining = handle->RxXferCount;
        observation->valid = 1U;
    }
    return PlatformSpi_ResultMap(hal_result);
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id,
    const uint8_t *tx_data, uint8_t *rx_data, uint16_t length,
    uint32_t timeout_ms)
{
    return PlatformSpi_TransferObserved(id, tx_data, rx_data,
        length, timeout_ms, NULL);
}
