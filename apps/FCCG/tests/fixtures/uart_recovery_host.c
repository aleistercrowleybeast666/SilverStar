#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "platform_critical.h"
#include "platform_stm32f4_resources.h"

static UART_HandleTypeDef s_handle;
static uint32_t s_abort_calls, s_deinit_calls, s_init_calls, s_receive_calls;
static uint32_t s_abort_fail_at, s_deinit_fail_at, s_init_fail_at, s_receive_fail_at;
static uint8_t s_fail_all_deinit;
static uint8_t s_fail_all_init;
static uint32_t s_critical_depth;

void *PlatformStm32f4Resource_UartHandleGet(PlatformUartId id)
{ return (id == PLATFORM_UART_1) ? &s_handle : NULL; }
PlatformCriticalState PlatformCritical_Enter(void)
{ return s_critical_depth++; }
void PlatformCritical_Exit(PlatformCriticalState previous)
{ assert(s_critical_depth == previous + 1U); s_critical_depth = previous; }
uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length)
{ return (uint8_t)((data != NULL) && (length != 0U)); }
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *handle)
{ assert(handle == &s_handle); s_abort_calls++; return (s_abort_calls == s_abort_fail_at) ? HAL_ERROR : HAL_OK; }
HAL_StatusTypeDef HAL_UART_DeInit(UART_HandleTypeDef *handle)
{ assert(handle == &s_handle); s_deinit_calls++; return ((s_deinit_calls == s_deinit_fail_at) || s_fail_all_deinit) ? HAL_ERROR : HAL_OK; }
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *handle)
{ assert(handle == &s_handle); s_init_calls++; return ((s_init_calls == s_init_fail_at) || s_fail_all_init) ? HAL_ERROR : HAL_OK; }
HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle_DMA(UART_HandleTypeDef *handle, uint8_t *data, uint16_t length)
{ assert(handle == &s_handle && data != NULL && length != 0U); s_receive_calls++; return (s_receive_calls == s_receive_fail_at) ? HAL_ERROR : HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit_DMA(UART_HandleTypeDef *handle, uint8_t *data, uint16_t length)
{ assert(handle == &s_handle && data != NULL && length != 0U); return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *handle, uint8_t *data, uint16_t length, uint32_t timeout)
{ (void)timeout; return HAL_UART_Transmit_DMA(handle, data, length); }
HAL_UART_RxEventTypeTypeDef HAL_UARTEx_GetRxEventType(UART_HandleTypeDef *handle)
{ assert(handle == &s_handle); return HAL_UART_RXEVENT_IDLE; }

#include "platform_uart_stm32f4.c"

int main(int argc, char **argv)
{
    PlatformUartDiagnostics diagnostics;
    PlatformResult result;
    uint8_t recovery = 0U;
    uint8_t active = 1U;
    assert(argc == 2);
    s_handle.Init.BaudRate = 9600U;
    assert(PlatformUart_Init(PLATFORM_UART_1) == PLATFORM_OK);
    s_receive_calls = 0U;
    if (strcmp(argv[1], "abort_fail") == 0) { s_abort_fail_at = 1U; }
    if (strcmp(argv[1], "deinit_fail") == 0) { s_deinit_fail_at = 1U; }
    if (strncmp(argv[1], "init_fail", 9U) == 0) { s_init_fail_at = 1U; recovery = 1U; }
    if (strcmp(argv[1], "init_fail_deinit_fail") == 0) { s_deinit_fail_at = 2U; active = 0U; }
    if (strcmp(argv[1], "init_fail_restore_fail") == 0) { s_fail_all_init = 1U; active = 0U; }
    if (strcmp(argv[1], "init_fail_receive_fail") == 0) { s_receive_fail_at = 1U; active = 0U; }
    if (strcmp(argv[1], "restart_abort_fail") == 0) { s_abort_fail_at = 1U; active = 0U; }
    if (strcmp(argv[1], "second_abort_fail") == 0) { s_abort_fail_at = 2U; active = 0U; }
    if (strcmp(argv[1], "all_deinit_fail") == 0) { s_fail_all_deinit = 1U; active = 0U; }
    if (strcmp(argv[1], "receive_fail") == 0) { s_receive_fail_at = 1U; active = 0U; }
    if (strcmp(argv[1], "callback_abort_fail") == 0)
    {
        s_abort_fail_at = 1U;
        HAL_UART_ErrorCallback(&s_handle);
        assert(PlatformUart_DiagnosticsGet(PLATFORM_UART_1, &diagnostics) == PLATFORM_OK);
        assert(diagnostics.rx_active == 0U && diagnostics.rx_restart_failure_count == 1U);
        assert(s_receive_calls == 0U);
        return 0;
    }
    result = (strcmp(argv[1], "restart_abort_fail") == 0) ?
        PlatformUart_RxRestart(PLATFORM_UART_1) : PlatformUart_BaudSet(PLATFORM_UART_1, 115200U);
    assert(result == ((strcmp(argv[1], "normal") == 0) ? PLATFORM_OK : PLATFORM_IO_ERROR));
    assert(PlatformUart_DiagnosticsGet(PLATFORM_UART_1, &diagnostics) == PLATFORM_OK);
    assert(diagnostics.rx_active == active);
    if (s_abort_fail_at == 1U) { assert(s_receive_calls <= 1U); }
    if (active == 0U) { assert(s_receive_calls <= 1U); }
    if (recovery != 0U && active != 0U) { assert(s_handle.Init.BaudRate == 9600U); }
    if (strcmp(argv[1], "abort_fail") == 0) { assert(s_deinit_calls == 0U && s_init_calls == 0U); }
    if (strcmp(argv[1], "init_fail_deinit_fail") == 0) { assert(s_init_calls == 1U); }
    if (strcmp(argv[1], "all_deinit_fail") == 0) { assert(s_init_calls == 0U); }
    if (strcmp(argv[1], "restart_abort_fail") == 0 || strcmp(argv[1], "second_abort_fail") == 0)
    { assert(s_receive_calls == 0U && diagnostics.rx_restart_failure_count == 1U); }
    assert(s_critical_depth == 0U);
    return 0;
}
