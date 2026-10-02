
#ifndef __MAIN_H
#define __MAIN_H
#include <stdint.h>
typedef struct { unsigned value; } DMA_HandleTypeDef;
typedef struct { DMA_HandleTypeDef *hdmarx; DMA_HandleTypeDef *hdmatx; } UART_HandleTypeDef;
typedef enum { HAL_OK = 0, HAL_ERROR = 1, HAL_BUSY = 2 } HAL_StatusTypeDef;
#define DMA_IT_HT 1U
#define __HAL_DMA_DISABLE_IT(handle, flag) ((void)(handle), (void)(flag))
HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle_DMA(UART_HandleTypeDef *, uint8_t *, uint16_t);
HAL_StatusTypeDef HAL_UART_Transmit_DMA(UART_HandleTypeDef *, uint8_t *, uint16_t);
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *);
#endif
