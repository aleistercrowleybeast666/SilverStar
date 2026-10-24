#ifndef __USART_H
#define __USART_H

#include <stdint.h>

/* Host-only state for the generated maintenance configuration guard.
 * These identifiers are not MCU addresses or a replacement HAL ABI. */
#define USART1 1U
#define USART2 2U
#define USART3 3U
#define UART4 4U
#define UART5 5U
#define USART6 6U
#define UART_WORDLENGTH_8B 8U
#define UART_PARITY_NONE 0U
#define UART_STOPBITS_1 1U
#define UART_MODE_TX_RX 3U
#define UART_HWCONTROL_NONE 0U

typedef struct
{
    uint32_t BaudRate, WordLength, Parity, StopBits, Mode, HwFlowCtl;
} HostUartConfiguration;

typedef struct
{
    uint32_t Instance;
    HostUartConfiguration Init;
} HostUartHandle;

extern HostUartHandle huart1, huart2, huart3, huart4, huart5, huart6;

#endif /* __USART_H */
