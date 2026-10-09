"""Explicit C071 PC UART alternative, sharing the owned CDC session/ring core.

No DMA, polling transfer, runtime transport switch or simultaneous CDC is used.
The resulting C file is first-party and must be strictly compiled and analyzed.
"""
import re


def C071PcUartIt_Render(usb_source: str) -> str:
    source = usb_source
    for header in ('usbd_conf.h', 'usb_device.h', 'usbd_cdc_if.h'):
        source = source.replace('#include "'+header+'"\n', '')
    source = source.replace('PC_USB_RX_CAPACITY', 'PC_UART_RX_CAPACITY')
    source = source.replace('extern USBD_HandleTypeDef hUsbDeviceFS;', '''extern UART_HandleTypeDef huart2;
static uint8_t s_rx_byte;
static volatile uint8_t s_rx_armed;
static volatile uint8_t s_tx_busy;
static PcByteStreamInitResult PcUart_Recover(void);''')
    init = '''PcByteStreamInitResult PcByteStream_Init(void)
{
    return PcUart_Recover();
}'''
    source, count = re.subn(r'PcByteStreamInitResult PcByteStream_Init\(void\)\n\{.*?\n\}', init, source, flags=re.S)
    if count != 1: raise ValueError('unreviewed byte stream initialization')
    source = source.replace('    saved_mask = __get_PRIMASK();\n    __disable_irq();\n    *session = s_session;', '''    if (s_rx_armed == 0U) { (void)PcUart_Recover(); }
    saved_mask = __get_PRIMASK();
    __disable_irq();
    *session = s_session;''')
    # A failed recovery is an ordinary unavailable stream; stale data is reset.
    source = source.replace('    if (s_rx_armed == 0U) { (void)PcUart_Recover(); }', '''    if ((s_rx_armed == 0U) && (PcUart_Recover() != PC_BYTE_STREAM_INIT_OK))
    { *session = PcByteStream_Session_Get(); return 0U; }''')
    begin = source.index('    if ((hUsbDeviceFS.dev_state')
    end = source.index('    for (index = 0U; (index < length)', begin)
    source = source[:begin]+'''    if ((s_rx_armed == 0U) || (s_tx_busy != 0U))
    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_WRITE_BUSY; }
'''+source[end:]
    source = source.replace('    uint8_t result;\n', '    HAL_StatusTypeDef result;\n').replace('    USBD_CDC_HandleTypeDef *cdc;\n','')
    begin = source.index('    /* Own the bytes until the stack retires TxState')
    end = source.index('\n}', begin)
    source = source[:begin]+'''    /* Own fixed TX bytes until completion; IT submission does not poll. */
    s_tx_busy = 1U;
    result = HAL_UART_Transmit_IT(&huart2, s_tx_buffer, length);
    if (result != HAL_OK) { s_tx_busy = 0U; }
    if ((result != HAL_OK) && (result != HAL_BUSY)) { PcByteStream_OnUsbReset(); }
    __set_PRIMASK(saved_mask);
    if (result == HAL_BUSY) { return PC_BYTE_STREAM_WRITE_BUSY; }
    return (result == HAL_OK) ? PC_BYTE_STREAM_WRITE_OK : PC_BYTE_STREAM_WRITE_ERROR;
'''+source[end:]
    source += '''
/* Main-context recovery aborts the old TX/RX before releasing fixed storage.
 * IRQ callbacks only invalidate the session and request this bounded recovery.
 * HAL_UART_Abort on this no-DMA profile has no polling or retry loop. */
static PcByteStreamInitResult PcUart_Recover(void)
{
    uint32_t saved_mask = __get_PRIMASK();
    HAL_StatusTypeDef result;
    __disable_irq();
    s_rx_armed = 0U;
    PcByteStream_OnUsbReset();
    if ((huart2.hdmarx != NULL) || (huart2.hdmatx != NULL))
    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_INIT_HARDWARE_ERROR; }
    result = HAL_UART_Abort(&huart2);
    if (result != HAL_OK)
    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_INIT_HARDWARE_ERROR; }
    s_tx_busy = 0U;
    if (s_session_exhausted != 0U)
    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_INIT_HARDWARE_ERROR; }
    s_rx_armed = 1U;
    result = HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1U);
    if (result != HAL_OK) { s_rx_armed = 0U; }
    __set_PRIMASK(saved_mask);
    return (result == HAL_OK) ? PC_BYTE_STREAM_INIT_OK : PC_BYTE_STREAM_INIT_HARDWARE_ERROR;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
    uint8_t full;
    if ((uart != &huart2) || (s_rx_armed == 0U)) { return; }
    full = ((uint16_t)((s_rx_head + 1U) % PC_UART_RX_CAPACITY) == s_rx_tail) ? 1U : 0U;
    PcByteStream_OnUsbReceive(&s_rx_byte, 1U);
    if (full != 0U) { PcByteStream_OnUsbReset(); }
    if (HAL_UART_Receive_IT(&huart2, &s_rx_byte, 1U) != HAL_OK)
    { s_rx_armed = 0U; PcByteStream_OnUsbReset(); }
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart == &huart2) { s_tx_busy = 0U; }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart != &huart2) { return; }
    s_rx_armed = 0U;
    PcByteStream_OnUsbReset();
}
'''
    if any(token in source for token in ('CDC_Transmit_FS','USBD_', 'HAL_UARTEx_ReceiveToIdle_DMA','while (')):
        raise ValueError('unexpected dependency or polling in UART alternative')
    return source
