#ifndef __CONSOLE_UART_DEVICE_H
#define __CONSOLE_UART_DEVICE_H

#include <stdint.h>

#include "platform_uart.h"

typedef enum
{
    CONSOLE_UART_INIT_OK = 0,
    CONSOLE_UART_INIT_IO_ERROR
} ConsoleUartInitResult;

ConsoleUartInitResult ConsoleUart_Init(void);
void ConsoleUart_Process(void);
uint16_t ConsoleUart_Write(const uint8_t *data, uint16_t length);
uint16_t ConsoleUart_WritePriority(const uint8_t *data, uint16_t length);
uint16_t ConsoleUart_Read(uint8_t *data, uint16_t capacity);
uint16_t ConsoleUart_RxCountGet(void);
uint16_t ConsoleUart_TxCountGet(PlatformUartTxPriority priority);
void ConsoleUart_DiagnosticsGet(PlatformUartDiagnostics *diagnostics);

#endif /* __CONSOLE_UART_DEVICE_H */
