#ifndef __STM32F4XX_HAL_H
#define __STM32F4XX_HAL_H
#include <stdint.h>
typedef enum { HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { HAL_UART_RXEVENT_IDLE, HAL_UART_RXEVENT_TC } HAL_UART_RxEventTypeTypeDef;
typedef struct { uint32_t unused; } DMA_HandleTypeDef;
/* Host declaration only. Generated resource validation reads the full 8N1
 * contract; these fields are not an emulation of a UART peripheral. */
typedef struct {
    uint32_t BaudRate, WordLength, StopBits, Parity, Mode, HwFlowCtl;
} UART_InitTypeDef;
typedef struct { UART_InitTypeDef Init; DMA_HandleTypeDef *hdmarx; DMA_HandleTypeDef *hdmatx;
    uint32_t ErrorCode; void *Instance; } UART_HandleTypeDef;
#define USART3 ((void *)(uintptr_t)0x40004800U)
#define UART_WORDLENGTH_8B 0U
#define UART_PARITY_NONE 0U
#define UART_STOPBITS_1 0U
#define UART_MODE_TX_RX 12U
#define UART_HWCONTROL_NONE 0U
#define DMA_IT_HT 1U
#define HAL_UART_ERROR_ORE 1U
#define HAL_UART_ERROR_FE 2U
#define HAL_UART_ERROR_NE 4U
#define HAL_UART_ERROR_PE 8U
#define HAL_UART_ERROR_DMA 16U
#define __HAL_DMA_DISABLE_IT(h, f) ((void)(h), (void)(f))
#define __HAL_UART_CLEAR_OREFLAG(h) ((void)(h))
#define __HAL_UART_FLUSH_DRREGISTER(h) ((void)(h))
HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle_DMA(UART_HandleTypeDef *, uint8_t *, uint16_t);
HAL_StatusTypeDef HAL_UART_Transmit_DMA(UART_HandleTypeDef *, uint8_t *, uint16_t);
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *, uint8_t *, uint16_t, uint32_t);
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *);
HAL_StatusTypeDef HAL_UART_DeInit(UART_HandleTypeDef *);
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *);
HAL_UART_RxEventTypeTypeDef HAL_UARTEx_GetRxEventType(UART_HandleTypeDef *);
#endif
