#ifndef __PLATFORM_UART_H
#define __PLATFORM_UART_H

#include <stdint.h>

#include "platform_types.h"

typedef enum
{
    PLATFORM_UART_1 = 0,
    PLATFORM_UART_2,
    PLATFORM_UART_3,
    PLATFORM_UART_COUNT = 6
} PlatformUartId;

typedef enum
{
    PLATFORM_UART_TX_NORMAL = 0,
    PLATFORM_UART_TX_PRIORITY
} PlatformUartTxPriority;

typedef struct
{
    uint32_t rx_bytes;
    uint32_t tx_bytes;
    uint32_t rx_event_count;
    uint32_t rx_idle_event_count;
    uint32_t rx_transfer_complete_count;
    uint32_t rx_discarded_bytes;
    uint32_t tx_discarded_bytes;
    uint32_t uart_overrun_error_count;
    uint32_t uart_framing_error_count;
    uint32_t uart_noise_error_count;
    uint32_t uart_parity_error_count;
    uint32_t dma_error_count;
    uint32_t rx_restart_count;
    uint32_t rx_restart_failure_count;
    uint32_t rx_discontinuity_count;
    uint32_t transport_error_count;
    uint8_t rx_active;
    uint8_t tx_active;
} PlatformUartDiagnostics;

PlatformResult PlatformUart_Init(PlatformUartId id);
PlatformResult PlatformUart_Write(PlatformUartId id,
                                  const uint8_t *data,
                                  uint16_t length,
                                  uint32_t timeout_ms);
PlatformResult PlatformUart_WriteAsync(PlatformUartId id,
                                       const uint8_t *data,
                                       uint16_t length,
                                       PlatformUartTxPriority priority,
                                       uint16_t *accepted_length);
PlatformResult PlatformUart_Read(PlatformUartId id,
                                 uint8_t *data,
                                 uint16_t capacity,
                                 uint16_t *read_length);
PlatformResult PlatformUart_RxFlush(PlatformUartId id);
PlatformResult PlatformUart_RxStop(PlatformUartId id);
PlatformResult PlatformUart_RxRestart(PlatformUartId id);
PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baudrate);
PlatformResult PlatformUart_BaudGet(PlatformUartId id, uint32_t *baudrate);
PlatformResult PlatformUart_RxCountGet(PlatformUartId id, uint16_t *count);
PlatformResult PlatformUart_TxCountGet(PlatformUartId id,
                                       PlatformUartTxPriority priority,
                                       uint16_t *count);
PlatformResult PlatformUart_DiagnosticsGet(
    PlatformUartId id,
    PlatformUartDiagnostics *diagnostics);
void PlatformUart_Process(PlatformUartId id);

#endif /* __PLATFORM_UART_H */
