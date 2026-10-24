#include "console_uart_device.h"

#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "platform_critical.h"

static uint32_t s_rejected_frame_bytes;

static void ConsoleUart_FrameRejectionRecord(uint16_t length)
{
    PlatformCriticalState state = PlatformCritical_Enter();

    if (s_rejected_frame_bytes > (UINT32_MAX - (uint32_t)length))
    {
        s_rejected_frame_bytes = UINT32_MAX;
    }
    else
    {
        s_rejected_frame_bytes += (uint32_t)length;
    }
    PlatformCritical_Exit(state);
}

ConsoleUartInitResult ConsoleUart_Init(void)
{
    if (ProjectMaintenanceUart_Validate() != ProjectMaintenanceUartResult_Ok)
    { return CONSOLE_UART_INIT_IO_ERROR; }
    return (PlatformUart_Init(PROJECT_RESOURCE_CONSOLE_UART) == PLATFORM_OK) ?
        CONSOLE_UART_INIT_OK : CONSOLE_UART_INIT_IO_ERROR;
}

void ConsoleUart_Process(void)
{
    PlatformUart_Process(PROJECT_RESOURCE_CONSOLE_UART);
}

static uint16_t ConsoleUart_WriteWithPriority(
    const uint8_t *data,
    uint16_t length,
    PlatformUartTxPriority priority)
{
    PlatformResult result = PlatformUart_WriteFrameAsync(
        PROJECT_RESOURCE_CONSOLE_UART, data, length, priority);

    if (result != PLATFORM_OK)
    {
        if (result == PLATFORM_BUSY) { ConsoleUart_FrameRejectionRecord(length); }
        return 0U;
    }
    return length;
}

uint16_t ConsoleUart_Write(const uint8_t *data, uint16_t length)
{
    return ConsoleUart_WriteWithPriority(data, length,
                                         PLATFORM_UART_TX_NORMAL);
}

uint16_t ConsoleUart_WritePriority(const uint8_t *data, uint16_t length)
{
    return ConsoleUart_WriteWithPriority(data, length,
                                         PLATFORM_UART_TX_PRIORITY);
}

uint16_t ConsoleUart_Read(uint8_t *data, uint16_t capacity)
{
    uint16_t read_length = 0U;

    if (PlatformUart_Read(PROJECT_RESOURCE_CONSOLE_UART, data, capacity,
                          &read_length) != PLATFORM_OK)
    {
        return 0U;
    }
    return read_length;
}

uint16_t ConsoleUart_RxCountGet(void)
{
    uint16_t count = 0U;

    (void)PlatformUart_RxCountGet(PROJECT_RESOURCE_CONSOLE_UART, &count);
    return count;
}

uint16_t ConsoleUart_TxCountGet(PlatformUartTxPriority priority)
{
    uint16_t count = 0U;

    (void)PlatformUart_TxCountGet(PROJECT_RESOURCE_CONSOLE_UART, priority, &count);
    return count;
}

void ConsoleUart_DiagnosticsGet(PlatformUartDiagnostics *diagnostics)
{
    PlatformCriticalState state;
    uint32_t rejected;

    if (diagnostics == NULL) { return; }
    if (PlatformUart_DiagnosticsGet(PROJECT_RESOURCE_CONSOLE_UART, diagnostics) !=
        PLATFORM_OK)
    {
        (void)memset(diagnostics, 0, sizeof(*diagnostics));
    }
    state = PlatformCritical_Enter();
    rejected = s_rejected_frame_bytes;
    PlatformCritical_Exit(state);
    diagnostics->tx_discarded_bytes =
        (diagnostics->tx_discarded_bytes > (UINT32_MAX - rejected)) ?
        UINT32_MAX : diagnostics->tx_discarded_bytes + rejected;
}
