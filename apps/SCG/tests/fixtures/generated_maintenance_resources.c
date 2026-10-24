/* Host-only CubeMX handle, private to the generated resource translation unit.
 * No UART peripheral is emulated and no firmware-owned source is substituted. */
#include "stm32f4xx_hal.h"
static UART_HandleTypeDef huart3 = {
    .Init = {.BaudRate = 230400U, .WordLength = UART_WORDLENGTH_8B,
             .StopBits = UART_STOPBITS_1, .Parity = UART_PARITY_NONE,
             .Mode = UART_MODE_TX_RX, .HwFlowCtl = UART_HWCONTROL_NONE},
    .Instance = USART3
};
#include "project_resources.c"
