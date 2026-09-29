#include "platform_uart.h"

#include <stddef.h>
#include <string.h>

#include "platform_stm32f1_resources.h"
#include "stm32f1xx_hal.h"

#define PLATFORM_UART_POLL_BATCH_MAX 64U

static PlatformUartDiagnostics s_uart_diagnostics[PLATFORM_UART_COUNT];

static UART_HandleTypeDef *PlatformUart_HandleGet(PlatformUartId id)
{
    return (UART_HandleTypeDef *)PlatformStm32f1Resource_UartHandleGet(id);
}

static PlatformResult PlatformUart_ResultMap(HAL_StatusTypeDef result)
{
    if (result == HAL_OK) { return PLATFORM_OK; }
    if (result == HAL_BUSY) { return PLATFORM_BUSY; }
    if (result == HAL_TIMEOUT) { return PLATFORM_TIMEOUT; }
    return PLATFORM_IO_ERROR;
}

PlatformResult PlatformUart_Init(PlatformUartId id)
{
    return (PlatformUart_HandleGet(id) != NULL) ?
        PLATFORM_OK : PLATFORM_INVALID_ARGUMENT;
}

PlatformResult PlatformUart_Write(
    PlatformUartId id, const uint8_t *data, uint16_t length,
    uint32_t timeout_ms)
{
    UART_HandleTypeDef *handle = PlatformUart_HandleGet(id);
    HAL_StatusTypeDef result;

    if ((handle == NULL) || (data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    result = HAL_UART_Transmit(
        handle, (uint8_t *)(uintptr_t)data, length, timeout_ms);
    if (result == HAL_OK)
    {
        s_uart_diagnostics[id].tx_bytes += length;
    }
    else
    {
        s_uart_diagnostics[id].transport_error_count++;
    }
    return PlatformUart_ResultMap(result);
}

PlatformResult PlatformUart_WriteAsync(
    PlatformUartId id, const uint8_t *data, uint16_t length,
    PlatformUartTxPriority priority, uint16_t *accepted_length)
{
    (void)id;
    (void)data;
    (void)length;
    (void)priority;
    if (accepted_length != NULL) { *accepted_length = 0U; }
    return PLATFORM_UNSUPPORTED;
}

PlatformResult PlatformUart_WriteFrameAsync(
    PlatformUartId id, const uint8_t *data, uint16_t length,
    PlatformUartTxPriority priority)
{
    (void)id;
    (void)data;
    (void)length;
    (void)priority;
    return PLATFORM_UNSUPPORTED;
}

PlatformResult PlatformUart_Read(
    PlatformUartId id, uint8_t *data, uint16_t capacity,
    uint16_t *read_length)
{
    UART_HandleTypeDef *handle = PlatformUart_HandleGet(id);
    uint16_t limit;
    uint16_t count;

    if ((handle == NULL) || (data == NULL) || (read_length == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *read_length = 0U;
    limit = (capacity < PLATFORM_UART_POLL_BATCH_MAX) ?
        capacity : PLATFORM_UART_POLL_BATCH_MAX;
    for (count = 0U; count < limit; count++)
    {
        if (HAL_UART_Receive(handle, &data[count], 1U, 0U) != HAL_OK)
        {
            break;
        }
    }
    *read_length = count;
    s_uart_diagnostics[id].rx_bytes += count;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxFlush(PlatformUartId id)
{
    return (PlatformUart_HandleGet(id) != NULL) ?
        PLATFORM_OK : PLATFORM_INVALID_ARGUMENT;
}

PlatformResult PlatformUart_RxStop(PlatformUartId id)
{
    (void)id;
    return PLATFORM_UNSUPPORTED;
}

PlatformResult PlatformUart_RxRestart(PlatformUartId id)
{
    (void)id;
    return PLATFORM_UNSUPPORTED;
}

PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baudrate)
{
    UART_HandleTypeDef *handle = PlatformUart_HandleGet(id);
    if ((handle == NULL) || (baudrate == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    handle->Init.BaudRate = baudrate;
    return PlatformUart_ResultMap(HAL_UART_Init(handle));
}

PlatformResult PlatformUart_BaudGet(PlatformUartId id, uint32_t *baudrate)
{
    UART_HandleTypeDef *handle = PlatformUart_HandleGet(id);
    if ((handle == NULL) || (baudrate == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *baudrate = handle->Init.BaudRate;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxCountGet(PlatformUartId id, uint16_t *count)
{
    if ((PlatformUart_HandleGet(id) == NULL) || (count == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *count = 0U;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_TxCountGet(
    PlatformUartId id, PlatformUartTxPriority priority, uint16_t *count)
{
    (void)priority;
    return PlatformUart_RxCountGet(id, count);
}

PlatformResult PlatformUart_DiagnosticsGet(
    PlatformUartId id, PlatformUartDiagnostics *diagnostics)
{
    if ((PlatformUart_HandleGet(id) == NULL) || (diagnostics == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    memcpy(diagnostics, &s_uart_diagnostics[id], sizeof(*diagnostics));
    return PLATFORM_OK;
}

void PlatformUart_Process(PlatformUartId id)
{
    (void)id;
}
