"""Bounded STM32 HAL UART DMA byte stream for Ground GSP."""

from __future__ import annotations

import re


def PcUartDma_Render(handle: str) -> str:
    if re.fullmatch(r"huart[0-9]+", handle) is None:
        raise ValueError("Ground UART DMA requires a CubeMX UART handle")
    return _SOURCE.replace("__PC_UART_HANDLE__", handle)


_SOURCE = r'''#include "pc_byte_stream.h"

#include "gsp_min_protocol.h"
#include "main.h"

#define PC_UART_DMA_RX_CHUNK 128U
#define PC_UART_RX_CAPACITY 512U

extern UART_HandleTypeDef __PC_UART_HANDLE__;

static uint8_t s_dma_rx[PC_UART_DMA_RX_CHUNK];
static uint8_t s_rx_buffer[PC_UART_RX_CAPACITY];
static uint8_t s_tx_buffer[GSP_MIN_MAX_FRAME_LEN];
static volatile uint16_t s_rx_head;
static volatile uint16_t s_rx_tail;
static volatile uint32_t s_rx_overflow_count;
static volatile uint8_t s_rx_armed;
static volatile uint8_t s_tx_busy;

static PcByteStreamInitResult PcByteStream_DmaReceiveStart(void)
{
    HAL_StatusTypeDef result;

    s_rx_armed = 1U;
    result = HAL_UARTEx_ReceiveToIdle_DMA(
        &__PC_UART_HANDLE__, s_dma_rx, PC_UART_DMA_RX_CHUNK);
    if (result != HAL_OK)
    {
        s_rx_armed = 0U;
        return PC_BYTE_STREAM_INIT_HARDWARE_ERROR;
    }
    /* Only IDLE and full-buffer events own a chunk; half-transfer is disabled. */
    __HAL_DMA_DISABLE_IT(__PC_UART_HANDLE__.hdmarx, DMA_IT_HT);
    return PC_BYTE_STREAM_INIT_OK;
}

PcByteStreamInitResult PcByteStream_Init(void)
{
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_rx_overflow_count = 0U;
    s_rx_armed = 0U;
    s_tx_busy = 0U;
    if (__PC_UART_HANDLE__.hdmarx == NULL || __PC_UART_HANDLE__.hdmatx == NULL)
    {
        return PC_BYTE_STREAM_INIT_HARDWARE_ERROR;
    }
    return PcByteStream_DmaReceiveStart();
}

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *uart, uint16_t length)
{
    uint16_t index;

    if (uart != &__PC_UART_HANDLE__) { return; }
    s_rx_armed = 0U;
    if (length > PC_UART_DMA_RX_CHUNK)
    {
        length = PC_UART_DMA_RX_CHUNK;
    }
    for (index = 0U; index < length; index++)
    {
        uint16_t next = (uint16_t)((s_rx_head + 1U) % PC_UART_RX_CAPACITY);
        if (next == s_rx_tail)
        {
            if (s_rx_overflow_count < UINT32_MAX) { s_rx_overflow_count++; }
        }
        else
        {
            s_rx_buffer[s_rx_head] = s_dma_rx[index];
            s_rx_head = next;
        }
    }
    (void)PcByteStream_DmaReceiveStart();
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart == &__PC_UART_HANDLE__) { s_tx_busy = 0U; }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart == &__PC_UART_HANDLE__)
    {
        s_rx_armed = 0U;
        s_tx_busy = 0U;
    }
}

uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity)
{
    uint16_t count = 0U;

    if (buffer == NULL) { return 0U; }
    if (s_rx_armed == 0U)
    {
        (void)HAL_UART_AbortReceive(&__PC_UART_HANDLE__);
        (void)PcByteStream_DmaReceiveStart();
    }
    while ((count < capacity) && (s_rx_tail != s_rx_head))
    {
        buffer[count++] = s_rx_buffer[s_rx_tail];
        s_rx_tail = (uint16_t)((s_rx_tail + 1U) % PC_UART_RX_CAPACITY);
    }
    return count;
}

uint16_t PcByteStream_Write(const uint8_t *data, uint16_t length)
{
    uint16_t index;

    if (data == NULL || length == 0U || length > sizeof(s_tx_buffer)
        || s_tx_busy != 0U)
    {
        return 0U;
    }
    for (index = 0U; index < length; index++) { s_tx_buffer[index] = data[index]; }
    s_tx_busy = 1U;
    if (HAL_UART_Transmit_DMA(&__PC_UART_HANDLE__, s_tx_buffer, length) != HAL_OK)
    {
        s_tx_busy = 0U;
        return 0U;
    }
    return length;
}

void PcByteStream_OnUsbReceive(const uint8_t *data, uint16_t length)
{
    (void)data;
    (void)length;
}

uint32_t PcByteStream_OverflowCount_Get(void)
{
    return s_rx_overflow_count;
}
'''
