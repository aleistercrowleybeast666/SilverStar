
#include <assert.h>
#include <stdint.h>
#include <string.h>

#include "main.h"
#include "pc_byte_stream.h"

static DMA_HandleTypeDef s_rx_dma;
static DMA_HandleTypeDef s_tx_dma;
UART_HandleTypeDef huart1 = {&s_rx_dma, &s_tx_dma};
static uint8_t *s_dma_destination;
static uint16_t s_dma_capacity;
static uint8_t *s_tx_source;
static HAL_StatusTypeDef s_tx_status = HAL_OK;

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *, uint16_t);
void HAL_UART_TxCpltCallback(UART_HandleTypeDef *);

HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle_DMA(
    UART_HandleTypeDef *uart, uint8_t *destination, uint16_t capacity)
{
    assert(uart == &huart1);
    s_dma_destination = destination;
    s_dma_capacity = capacity;
    return HAL_OK;
}

HAL_StatusTypeDef HAL_UART_Transmit_DMA(
    UART_HandleTypeDef *uart, uint8_t *source, uint16_t length)
{
    assert(uart == &huart1 && length != 0U);
    s_tx_source = source;
    return s_tx_status;
}

HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *uart)
{
    assert(uart == &huart1);
    return HAL_OK;
}

int main(void)
{
    uint8_t bytes[128];
    uint8_t output[64];
    uint8_t tx[4] = {1U, 2U, 3U, 4U};
    uint16_t batch;
    uint16_t index;

    assert(PcByteStream_Init() == PC_BYTE_STREAM_INIT_OK);
    assert(s_dma_capacity == 128U);
    for (index = 0U; index < 5U; index++) { bytes[index] = (uint8_t)(index + 1U); }
    memcpy(s_dma_destination, bytes, 5U);
    HAL_UARTEx_RxEventCallback(&huart1, 5U);
    assert(PcByteStream_Read(output, sizeof(output)) == 5U);
    assert(memcmp(output, bytes, 5U) == 0);
    assert(PcByteStream_Write(tx, sizeof(tx)) == PC_BYTE_STREAM_WRITE_OK);
    assert(s_tx_source != tx && memcmp(s_tx_source, tx, sizeof(tx)) == 0);
    assert(PcByteStream_Write(tx, sizeof(tx)) == PC_BYTE_STREAM_WRITE_BUSY);
    HAL_UART_TxCpltCallback(&huart1);
    s_tx_status = HAL_BUSY;
    assert(PcByteStream_Write(tx, sizeof(tx)) == PC_BYTE_STREAM_WRITE_BUSY);
    s_tx_status = HAL_ERROR;
    assert(PcByteStream_Write(tx, sizeof(tx)) == PC_BYTE_STREAM_WRITE_ERROR);
    s_tx_status = HAL_OK;
    assert(PcByteStream_Write(tx, sizeof(tx)) == PC_BYTE_STREAM_WRITE_OK);
    for (batch = 0U; batch < 5U; batch++)
    {
        memset(s_dma_destination, (int)batch, s_dma_capacity);
        HAL_UARTEx_RxEventCallback(&huart1, s_dma_capacity);
    }
    assert(PcByteStream_OverflowCount_Get() == 129U);
    assert(PcByteStream_Read(output, sizeof(output)) == sizeof(output));
    return 0;
}
