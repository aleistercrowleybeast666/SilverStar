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
/* Enqueue one command frame completely or return BUSY without enqueueing bytes. */
PlatformResult PlatformUart_WriteFrameAsync(PlatformUartId id,
                                            const uint8_t *data,
                                            uint16_t length,
                                            PlatformUartTxPriority priority);
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

#ifndef PLATFORM_UART_FIRST_READ_TRACE_ENABLE
#define PLATFORM_UART_FIRST_READ_TRACE_ENABLE 0U
#endif

#if (PLATFORM_UART_FIRST_READ_TRACE_ENABLE != 0U)
#define PLATFORM_UART_FIRST_READ_TRACE_EVENTS 80U
typedef enum
{
    PlatformUartFirstReadTrace_Begin = 1,
    PlatformUartFirstReadTrace_Flush,
    PlatformUartFirstReadTrace_Enqueue,
    PlatformUartFirstReadTrace_TxStart,
    PlatformUartFirstReadTrace_TxEnd,
    PlatformUartFirstReadTrace_RxCandidate,
    PlatformUartFirstReadTrace_Discard,
    PlatformUartFirstReadTrace_Reset,
    PlatformUartFirstReadTrace_StartResult,
    PlatformUartFirstReadTrace_PollResult
} PlatformUartFirstReadTraceKind;
typedef struct
{
    uint32_t offset_ms;
    uint32_t detail;
    uint8_t kind;
    uint8_t checksum_valid;
    uint8_t bytes[11];
} PlatformUartFirstReadTraceEvent;
typedef struct
{
    PlatformUartFirstReadTraceEvent events[PLATFORM_UART_FIRST_READ_TRACE_EVENTS];
    uint32_t started_ms;
    uint32_t finished_offset_ms;
    uint32_t dropped_events;
    uint32_t poll_count;
    uint32_t observed_rx_bytes;
    uint16_t event_count;
    uint8_t window[11];
    uint8_t window_position;
    uint8_t window_count;
    uint8_t uart;
    uint8_t reg;
    uint8_t armed;
    uint8_t frozen;
    uint8_t last_phase;
    uint8_t last_result;
} PlatformUartFirstReadTrace;
/* First attempt only; stored for debugger inspection, no output traffic. */
void PlatformUart_FirstReadTraceBegin(PlatformUartId id, uint8_t reg);
void PlatformUart_FirstReadTraceResult(PlatformUartId id,
    uint8_t phase, uint8_t result, uint8_t finished);
#endif

#endif /* __PLATFORM_UART_H */
