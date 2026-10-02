#include "platform_uart.h"
#include "project_resources.h"

#include <stddef.h>
#include <string.h>

#include "common_ringbuf.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "platform_stm32f4_resources.h"
#include "silverstar_assert.h"
#include "stm32f4xx_hal.h"

/* STM32 HAL transmit APIs predate const-correct buffer declarations. */
static uint8_t *PlatformUart_HalTransmitBufferGet(const uint8_t *data)
{
    return (uint8_t *)(uintptr_t)data;
}

#define PLATFORM_UART_TX_DMA_MAX_CHUNK  128U

typedef struct
{
    UART_HandleTypeDef *handle;
    uint8_t *rx_dma_buffer;
    uint16_t rx_dma_size;
    uint8_t *rx_ring_memory;
    uint16_t rx_ring_size;
    uint8_t *tx_ring_memory;
    uint16_t tx_ring_size;
    uint8_t *tx_priority_memory;
    uint16_t tx_priority_size;
    ringbuf_t rx_ring;
    ringbuf_t tx_ring;
    ringbuf_t tx_priority_ring;
    volatile uint16_t rx_dma_last_position;
    volatile uint16_t tx_dma_length;
    volatile uint8_t tx_dma_priority;
    volatile uint8_t rx_active;
    volatile uint8_t tx_active;
    uint8_t initialized;
    PlatformUartDiagnostics diagnostics;
} PlatformUartContext;

/* Sensor queues have 191 usable bytes, covering the 136-byte M9N command.
 * Generated sizes preserve console capacity and avoid reserving inactive slots. */
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart1_rx_dma[PROJECT_PLATFORM_UART_1_RX_DMA_SIZE];
static uint8_t s_uart1_rx_ring[PROJECT_PLATFORM_UART_1_RX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart1_tx_ring[PROJECT_PLATFORM_UART_1_TX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart1_tx_priority_ring[PROJECT_PLATFORM_UART_1_TX_PRIORITY_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart2_rx_dma[PROJECT_PLATFORM_UART_2_RX_DMA_SIZE];
static uint8_t s_uart2_rx_ring[PROJECT_PLATFORM_UART_2_RX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart2_tx_ring[PROJECT_PLATFORM_UART_2_TX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart2_tx_priority_ring[PROJECT_PLATFORM_UART_2_TX_PRIORITY_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart3_rx_dma[PROJECT_PLATFORM_UART_3_RX_DMA_SIZE];
static uint8_t s_uart3_rx_ring[PROJECT_PLATFORM_UART_3_RX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart3_tx_ring[PROJECT_PLATFORM_UART_3_TX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart3_tx_priority_ring[PROJECT_PLATFORM_UART_3_TX_PRIORITY_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart4_rx_dma[PROJECT_PLATFORM_UART_4_RX_DMA_SIZE];
static uint8_t s_uart4_rx_ring[PROJECT_PLATFORM_UART_4_RX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart4_tx_ring[PROJECT_PLATFORM_UART_4_TX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart4_tx_priority_ring[PROJECT_PLATFORM_UART_4_TX_PRIORITY_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart5_rx_dma[PROJECT_PLATFORM_UART_5_RX_DMA_SIZE];
static uint8_t s_uart5_rx_ring[PROJECT_PLATFORM_UART_5_RX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart5_tx_ring[PROJECT_PLATFORM_UART_5_TX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart5_tx_priority_ring[PROJECT_PLATFORM_UART_5_TX_PRIORITY_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart6_rx_dma[PROJECT_PLATFORM_UART_6_RX_DMA_SIZE];
static uint8_t s_uart6_rx_ring[PROJECT_PLATFORM_UART_6_RX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart6_tx_ring[PROJECT_PLATFORM_UART_6_TX_RING_SIZE];
static PLATFORM_DMA_ACCESSIBLE uint8_t s_uart6_tx_priority_ring[PROJECT_PLATFORM_UART_6_TX_PRIORITY_SIZE];

static PlatformUartContext s_uart[PLATFORM_UART_COUNT] =
{
    {
        .rx_dma_buffer = s_uart1_rx_dma,
        .rx_dma_size = sizeof(s_uart1_rx_dma),
        .rx_ring_memory = s_uart1_rx_ring,
        .rx_ring_size = sizeof(s_uart1_rx_ring),
        .tx_ring_memory = s_uart1_tx_ring,
        .tx_ring_size = sizeof(s_uart1_tx_ring),
        .tx_priority_memory = s_uart1_tx_priority_ring,
        .tx_priority_size = sizeof(s_uart1_tx_priority_ring)
    },
    {
        .rx_dma_buffer = s_uart2_rx_dma,
        .rx_dma_size = sizeof(s_uart2_rx_dma),
        .rx_ring_memory = s_uart2_rx_ring,
        .rx_ring_size = sizeof(s_uart2_rx_ring),
        .tx_ring_memory = s_uart2_tx_ring,
        .tx_ring_size = sizeof(s_uart2_tx_ring),
        .tx_priority_memory = s_uart2_tx_priority_ring,
        .tx_priority_size = sizeof(s_uart2_tx_priority_ring)
    },
    {
        .rx_dma_buffer = s_uart3_rx_dma,
        .rx_dma_size = sizeof(s_uart3_rx_dma),
        .rx_ring_memory = s_uart3_rx_ring,
        .rx_ring_size = sizeof(s_uart3_rx_ring),
        .tx_ring_memory = s_uart3_tx_ring,
        .tx_ring_size = sizeof(s_uart3_tx_ring),
        .tx_priority_memory = s_uart3_tx_priority_ring,
        .tx_priority_size = sizeof(s_uart3_tx_priority_ring)
    },
    {
        .rx_dma_buffer = s_uart4_rx_dma,
        .rx_dma_size = sizeof(s_uart4_rx_dma),
        .rx_ring_memory = s_uart4_rx_ring,
        .rx_ring_size = sizeof(s_uart4_rx_ring),
        .tx_ring_memory = s_uart4_tx_ring,
        .tx_ring_size = sizeof(s_uart4_tx_ring),
        .tx_priority_memory = s_uart4_tx_priority_ring,
        .tx_priority_size = sizeof(s_uart4_tx_priority_ring)
    },
    {
        .rx_dma_buffer = s_uart5_rx_dma,
        .rx_dma_size = sizeof(s_uart5_rx_dma),
        .rx_ring_memory = s_uart5_rx_ring,
        .rx_ring_size = sizeof(s_uart5_rx_ring),
        .tx_ring_memory = s_uart5_tx_ring,
        .tx_ring_size = sizeof(s_uart5_tx_ring),
        .tx_priority_memory = s_uart5_tx_priority_ring,
        .tx_priority_size = sizeof(s_uart5_tx_priority_ring)
    },
    {
        .rx_dma_buffer = s_uart6_rx_dma,
        .rx_dma_size = sizeof(s_uart6_rx_dma),
        .rx_ring_memory = s_uart6_rx_ring,
        .rx_ring_size = sizeof(s_uart6_rx_ring),
        .tx_ring_memory = s_uart6_tx_ring,
        .tx_ring_size = sizeof(s_uart6_tx_ring),
        .tx_priority_memory = s_uart6_tx_priority_ring,
        .tx_priority_size = sizeof(s_uart6_tx_priority_ring)
    }
};

static PlatformUartContext *PlatformUart_ContextGet(PlatformUartId id)
{
    PlatformUartContext *context;

    if ((uint32_t)id >= (uint32_t)PLATFORM_UART_COUNT) { return NULL; }
    context = &s_uart[id];
    if (context->handle == NULL)
    {
        context->handle = (UART_HandleTypeDef *)
            PlatformStm32f4Resource_UartHandleGet(id);
    }
    return (context->handle != NULL) ? context : NULL;
}

static PlatformUartContext *PlatformUart_ContextFind(
    UART_HandleTypeDef *handle)
{
    uint8_t index;

    for (index = 0U; index < (uint8_t)PLATFORM_UART_COUNT; index++)
    {
        if (s_uart[index].handle == handle) { return &s_uart[index]; }
    }
    return NULL;
}

static PlatformResult PlatformUart_ResultMap(HAL_StatusTypeDef result)
{
    if (result == HAL_OK) { return PLATFORM_OK; }
    if (result == HAL_TIMEOUT) { return PLATFORM_TIMEOUT; }
    if (result == HAL_BUSY) { return PLATFORM_BUSY; }
    return PLATFORM_IO_ERROR;
}

static void PlatformUart_DiscontinuityRecord(PlatformUartContext *context)
{
    context->diagnostics.rx_discarded_bytes +=
        RingBuf_GetUsed(&context->rx_ring);
    RingBuf_Reset(&context->rx_ring);
    context->rx_dma_last_position = 0U;
    context->rx_active = 0U;
    context->diagnostics.rx_active = 0U;
    context->diagnostics.rx_discontinuity_count++;
}

static PlatformResult PlatformUart_RxStart(PlatformUartContext *context)
{
    HAL_StatusTypeDef result;

    SILVERSTAR_ASSERT(context != NULL,
                      SILVERSTAR_ASSERT_MODULE_PLATFORM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(
        PlatformMemory_IsDmaAccessible(context->rx_dma_buffer,
                                       context->rx_dma_size) != 0U,
        SILVERSTAR_ASSERT_MODULE_PLATFORM,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    result = HAL_UARTEx_ReceiveToIdle_DMA(context->handle,
                                         context->rx_dma_buffer,
                                         context->rx_dma_size);
    if (result != HAL_OK)
    {
        context->rx_active = 0U;
        context->diagnostics.rx_active = 0U;
        return PlatformUart_ResultMap(result);
    }
    if (context->handle->hdmarx != NULL)
    {
        __HAL_DMA_DISABLE_IT(context->handle->hdmarx, DMA_IT_HT);
    }
    context->rx_dma_last_position = 0U;
    context->rx_active = 1U;
    context->diagnostics.rx_active = 1U;
    return PLATFORM_OK;
}

static void PlatformUart_RxPush(PlatformUartContext *context,
                                const uint8_t *data,
                                uint16_t length)
{
    uint16_t written;

    if (length == 0U) { return; }
    written = RingBuf_Push(&context->rx_ring, data, length);
    context->diagnostics.rx_bytes += length;
    context->diagnostics.rx_discarded_bytes +=
        (uint32_t)(length - written);
    if (written != length)
    {
        context->diagnostics.rx_discarded_bytes +=
            RingBuf_GetUsed(&context->rx_ring);
        RingBuf_Reset(&context->rx_ring);
        context->diagnostics.rx_discontinuity_count++;
    }
}

static ringbuf_t *PlatformUart_TxRingGet(PlatformUartContext *context,
                                        PlatformUartTxPriority priority)
{
    /* HAL_UART_Transmit_DMA dereferences hdmatx; missing CubeMX TX DMA is
     * an unsupported backend, never an accepted command or a null access. */
    if (context->handle->hdmatx == NULL) { return NULL; }
    if (priority == PLATFORM_UART_TX_PRIORITY)
    {
        return (context->tx_priority_size >= 2U) ?
            &context->tx_priority_ring : NULL;
    }
    return (context->tx_ring_size >= 2U) ? &context->tx_ring : NULL;
}

static void PlatformUart_TxTryStart(PlatformUartContext *context)
{
    PlatformCriticalState state;
    ringbuf_t *ring;
    uint8_t *tx_data;
    uint16_t length;
    uint8_t priority = 1U;

    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    state = PlatformCritical_Enter();
    if ((context->initialized == 0U) || (context->tx_active != 0U))
    {
        PlatformCritical_Exit(state);
        return;
    }
    ring = PlatformUart_TxRingGet(context, PLATFORM_UART_TX_PRIORITY);
    if ((ring == NULL) || (RingBuf_GetUsed(ring) == 0U))
    {
        priority = 0U;
        ring = PlatformUart_TxRingGet(context, PLATFORM_UART_TX_NORMAL);
    }
    if ((ring == NULL) || (RingBuf_GetUsed(ring) == 0U))
    {
        PlatformCritical_Exit(state);
        return;
    }
    length = RingBuf_GetLinearReadLen(ring);
    if (length > PLATFORM_UART_TX_DMA_MAX_CHUNK)
    {
        length = PLATFORM_UART_TX_DMA_MAX_CHUNK;
    }
    tx_data = RingBuf_GetLinearReadPtr(ring);
    SILVERSTAR_ASSERT(
        PlatformMemory_IsDmaAccessible(tx_data, length) != 0U,
        SILVERSTAR_ASSERT_MODULE_PLATFORM,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if (HAL_UART_Transmit_DMA(context->handle,
                             tx_data,
                             length) == HAL_OK)
    {
        context->tx_dma_length = length;
        context->tx_dma_priority = priority;
        context->tx_active = 1U;
        context->diagnostics.tx_active = 1U;
    }
    else
    {
        context->diagnostics.transport_error_count++;
    }
    PlatformCritical_Exit(state);
}

PlatformResult PlatformUart_Init(PlatformUartId id)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;
    PlatformResult result;

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    state = PlatformCritical_Enter();
    if (context->initialized == 0U)
    {
        RingBuf_Init(&context->rx_ring, context->rx_ring_memory,
                     context->rx_ring_size);
        if (context->tx_ring_size >= 2U)
        {
            RingBuf_Init(&context->tx_ring, context->tx_ring_memory,
                         context->tx_ring_size);
        }
        if (context->tx_priority_size >= 2U)
        {
            RingBuf_Init(&context->tx_priority_ring,
                         context->tx_priority_memory,
                         context->tx_priority_size);
        }
        (void)memset(&context->diagnostics, 0,
                     sizeof(context->diagnostics));
        context->initialized = 1U;
    }
    else
    {
        PlatformUart_DiscontinuityRecord(context);
        context->diagnostics.rx_restart_count++;
    }
    PlatformCritical_Exit(state);
    result = PlatformUart_RxStart(context);
    if (result != PLATFORM_OK)
    {
        state = PlatformCritical_Enter();
        context->diagnostics.rx_restart_failure_count++;
        PlatformCritical_Exit(state);
    }
    return result;
}

PlatformResult PlatformUart_Write(PlatformUartId id,
                                  const uint8_t *data,
                                  uint16_t length,
                                  uint32_t timeout_ms)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;
    HAL_StatusTypeDef result;

    if ((context == NULL) || (data == NULL) || (length == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    result = HAL_UART_Transmit(context->handle,
                               PlatformUart_HalTransmitBufferGet(data),
                               length, timeout_ms);
    state = PlatformCritical_Enter();
    if (result == HAL_OK) { context->diagnostics.tx_bytes += length; }
    else { context->diagnostics.transport_error_count++; }
    PlatformCritical_Exit(state);
    return PlatformUart_ResultMap(result);
}

PlatformResult PlatformUart_WriteAsync(PlatformUartId id,
                                       const uint8_t *data,
                                       uint16_t length,
                                       PlatformUartTxPriority priority,
                                       uint16_t *accepted_length)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;
    ringbuf_t *ring;
    uint16_t written;

    if ((context == NULL) || (data == NULL) || (length == 0U) ||
        (accepted_length == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    if ((priority != PLATFORM_UART_TX_NORMAL) &&
        (priority != PLATFORM_UART_TX_PRIORITY))
    { return PLATFORM_INVALID_ARGUMENT; }
    if (context->initialized == 0U) { return PLATFORM_NOT_READY; }
    ring = PlatformUart_TxRingGet(context, priority);
    if (ring == NULL) { return PLATFORM_UNSUPPORTED; }
    state = PlatformCritical_Enter();
    written = RingBuf_Push(ring, data, length);
    context->diagnostics.tx_discarded_bytes +=
        (uint32_t)(length - written);
    PlatformCritical_Exit(state);
    *accepted_length = written;
    PlatformUart_TxTryStart(context);
    return (written == length) ? PLATFORM_OK : PLATFORM_BUSY;
}

PlatformResult PlatformUart_WriteFrameAsync(PlatformUartId id,
                                            const uint8_t *data,
                                            uint16_t length,
                                            PlatformUartTxPriority priority)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;
    ringbuf_t *ring;

    if ((context == NULL) || (data == NULL) || (length == 0U))
    { return PLATFORM_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                            SILVERSTAR_ASSERT_MODULE_PLATFORM);
    if ((priority != PLATFORM_UART_TX_NORMAL) &&
        (priority != PLATFORM_UART_TX_PRIORITY))
    { return PLATFORM_INVALID_ARGUMENT; }
    if (context->initialized == 0U) { return PLATFORM_NOT_READY; }
    ring = PlatformUart_TxRingGet(context, priority);
    if (ring == NULL) { return PLATFORM_UNSUPPORTED; }
    SILVERSTAR_ASSERT_OBJECT(ring, ringbuf_t,
                            SILVERSTAR_ASSERT_MODULE_PLATFORM);
    state = PlatformCritical_Enter();
    if (RingBuf_GetFree(ring) < length)
    {
        PlatformCritical_Exit(state);
        return PLATFORM_BUSY;
    }
    (void)RingBuf_Push(ring, data, length);
    PlatformCritical_Exit(state);
    PlatformUart_TxTryStart(context);
    return PLATFORM_OK;
}

PlatformResult PlatformUart_Read(PlatformUartId id,
                                 uint8_t *data,
                                 uint16_t capacity,
                                 uint16_t *read_length)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;

    if ((context == NULL) || (data == NULL) || (capacity == 0U) ||
        (read_length == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    state = PlatformCritical_Enter();
    *read_length = RingBuf_Pop(&context->rx_ring, data, capacity);
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxFlush(PlatformUartId id)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    state = PlatformCritical_Enter();
    context->diagnostics.rx_discarded_bytes +=
        RingBuf_GetUsed(&context->rx_ring);
    RingBuf_Reset(&context->rx_ring);
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxStop(PlatformUartId id)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;
    HAL_StatusTypeDef result;

    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    result = HAL_UART_AbortReceive(context->handle);
    state = PlatformCritical_Enter();
    context->rx_active = 0U;
    context->diagnostics.rx_active = 0U;
    PlatformCritical_Exit(state);
    return PlatformUart_ResultMap(result);
}

static PlatformResult PlatformUart_ReceiveRestart(PlatformUartContext *context)
{
    PlatformCriticalState state;
    PlatformResult result;

    result = PlatformUart_ResultMap(HAL_UART_AbortReceive(context->handle));
    state = PlatformCritical_Enter();
    PlatformUart_DiscontinuityRecord(context);
    context->diagnostics.rx_restart_count++;
    PlatformCritical_Exit(state);
    /* Never start another DMA transfer after an unconfirmed receive stop. */
    if (result == PLATFORM_OK) { result = PlatformUart_RxStart(context); }
    if (result != PLATFORM_OK)
    {
        state = PlatformCritical_Enter();
        context->diagnostics.rx_restart_failure_count++;
        PlatformCritical_Exit(state);
    }
    return result;
}

PlatformResult PlatformUart_RxRestart(PlatformUartId id)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    if (context == NULL) { return PLATFORM_INVALID_ARGUMENT; }
    return PlatformUart_ReceiveRestart(context);
}

static void PlatformUart_TransportErrorRecord(PlatformUartContext *context)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    context->diagnostics.transport_error_count++;
    PlatformCritical_Exit(state);
}

static PlatformResult PlatformUart_BaudRestore(
    PlatformUartContext *context, PlatformUartId id, uint32_t baudrate)
{
    /* Receive is already inactive. Recovery is bounded, and a failed HAL
     * lifecycle step must not be followed by a DMA start. */
    if (HAL_UART_DeInit(context->handle) != HAL_OK)
    {
        PlatformUart_TransportErrorRecord(context);
        return PLATFORM_IO_ERROR;
    }
    context->handle->Init.BaudRate = baudrate;
    if (HAL_UART_Init(context->handle) != HAL_OK)
    {
        PlatformUart_TransportErrorRecord(context);
        return PLATFORM_IO_ERROR;
    }
    return PlatformUart_RxRestart(id);
}

PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baudrate)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    uint32_t previous_baudrate;
    PlatformResult result;
    PlatformResult restored;

    if ((context == NULL) || (baudrate == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    previous_baudrate = context->handle->Init.BaudRate;
    result = PlatformUart_RxStop(id);
    if (result != PLATFORM_OK)
    {
        restored = PlatformUart_RxRestart(id);
        return (restored == PLATFORM_OK) ? result : restored;
    }
    if (HAL_UART_DeInit(context->handle) != HAL_OK)
    {
        PlatformUart_TransportErrorRecord(context);
        restored = PlatformUart_BaudRestore(context, id, previous_baudrate);
        return (restored == PLATFORM_OK) ? PLATFORM_IO_ERROR : restored;
    }
    context->handle->Init.BaudRate = baudrate;
    if (HAL_UART_Init(context->handle) != HAL_OK)
    {
        PlatformUart_TransportErrorRecord(context);
        restored = PlatformUart_BaudRestore(context, id, previous_baudrate);
        return (restored == PLATFORM_OK) ? PLATFORM_IO_ERROR : restored;
    }
    __HAL_UART_CLEAR_OREFLAG(context->handle);
    __HAL_UART_FLUSH_DRREGISTER(context->handle);
    return PlatformUart_RxRestart(id);
}

PlatformResult PlatformUart_BaudGet(PlatformUartId id, uint32_t *baudrate)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);

    if ((context == NULL) || (baudrate == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *baudrate = context->handle->Init.BaudRate;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_RxCountGet(PlatformUartId id, uint16_t *count)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;

    if ((context == NULL) || (count == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    state = PlatformCritical_Enter();
    *count = RingBuf_GetUsed(&context->rx_ring);
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

PlatformResult PlatformUart_TxCountGet(PlatformUartId id,
                                       PlatformUartTxPriority priority,
                                       uint16_t *count)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;
    ringbuf_t *ring;

    if ((context == NULL) || (count == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    ring = PlatformUart_TxRingGet(context, priority);
    if (ring == NULL) { return PLATFORM_UNSUPPORTED; }
    state = PlatformCritical_Enter();
    *count = RingBuf_GetUsed(ring);
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

PlatformResult PlatformUart_DiagnosticsGet(
    PlatformUartId id,
    PlatformUartDiagnostics *diagnostics)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);
    PlatformCriticalState state;

    if ((context == NULL) || (diagnostics == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    state = PlatformCritical_Enter();
    *diagnostics = context->diagnostics;
    diagnostics->rx_active = context->rx_active;
    diagnostics->tx_active = context->tx_active;
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

void PlatformUart_Process(PlatformUartId id)
{
    PlatformUartContext *context = PlatformUart_ContextGet(id);

    if (context != NULL) { PlatformUart_TxTryStart(context); }
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *handle)
{
    PlatformUartContext *context = PlatformUart_ContextFind(handle);
    PlatformCriticalState state;
    ringbuf_t *ring;

    if ((context == NULL) || (context->tx_active == 0U)) { return; }
    state = PlatformCritical_Enter();
    ring = PlatformUart_TxRingGet(
        context,
        (context->tx_dma_priority != 0U) ?
            PLATFORM_UART_TX_PRIORITY : PLATFORM_UART_TX_NORMAL);
    if (ring != NULL) { RingBuf_Skip(ring, context->tx_dma_length); }
    context->diagnostics.tx_bytes += context->tx_dma_length;
    context->tx_dma_length = 0U;
    context->tx_active = 0U;
    context->diagnostics.tx_active = 0U;
    PlatformCritical_Exit(state);
    PlatformUart_TxTryStart(context);
}

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *handle, uint16_t size)
{
    PlatformUartContext *context = PlatformUart_ContextFind(handle);
    PlatformCriticalState state;
    HAL_UART_RxEventTypeTypeDef event_type;
    uint16_t last_position;

    if ((context == NULL) || (context->rx_active == 0U) ||
        (size > context->rx_dma_size))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    event_type = HAL_UARTEx_GetRxEventType(handle);
    state = PlatformCritical_Enter();
    context->diagnostics.rx_event_count++;
    if (event_type == HAL_UART_RXEVENT_IDLE)
    {
        context->diagnostics.rx_idle_event_count++;
    }
    else if (event_type == HAL_UART_RXEVENT_TC)
    {
        context->diagnostics.rx_transfer_complete_count++;
    }
    last_position = context->rx_dma_last_position;
    if (size > last_position)
    {
        PlatformUart_RxPush(context,
                            &context->rx_dma_buffer[last_position],
                            (uint16_t)(size - last_position));
    }
    else if (size < last_position)
    {
        PlatformUart_RxPush(context,
                            &context->rx_dma_buffer[last_position],
                            (uint16_t)(context->rx_dma_size - last_position));
        PlatformUart_RxPush(context, context->rx_dma_buffer, size);
    }
    else if ((event_type == HAL_UART_RXEVENT_TC) &&
             (size == context->rx_dma_size))
    {
        PlatformUart_RxPush(context, context->rx_dma_buffer,
                            context->rx_dma_size);
    }
    else
    {
        /* A repeated IDLE position carries no new bytes. */
    }
    context->rx_dma_last_position = size;
    PlatformCritical_Exit(state);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *handle)
{
    PlatformUartContext *context = PlatformUart_ContextFind(handle);
    PlatformCriticalState state;
    PlatformResult result;

    if (context == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(context, PlatformUartContext,
                             SILVERSTAR_ASSERT_MODULE_PLATFORM);
    state = PlatformCritical_Enter();
    if ((handle->ErrorCode & HAL_UART_ERROR_ORE) != 0U)
    { context->diagnostics.uart_overrun_error_count++; }
    if ((handle->ErrorCode & HAL_UART_ERROR_FE) != 0U)
    { context->diagnostics.uart_framing_error_count++; }
    if ((handle->ErrorCode & HAL_UART_ERROR_NE) != 0U)
    { context->diagnostics.uart_noise_error_count++; }
    if ((handle->ErrorCode & HAL_UART_ERROR_PE) != 0U)
    { context->diagnostics.uart_parity_error_count++; }
    if ((handle->ErrorCode & HAL_UART_ERROR_DMA) != 0U)
    { context->diagnostics.dma_error_count++; }
    PlatformCritical_Exit(state);
    result = PlatformUart_ReceiveRestart(context);
    if (result != PLATFORM_OK)
    {
        /* ReceiveRestart records the failure and keeps rx_active clear. */
        return;
    }
}
