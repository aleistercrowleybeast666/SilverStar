"""Run the shared pressure scenarios against the actual C071 UART adapter.

HAL callbacks are mocks. Connect models explicit reinitialization; UART does
not detect a physical cable disconnection. No target source is rewritten.
"""
from pathlib import Path
import argparse
import subprocess
import sys

UART = r'''
#include "main.h"
UART_HandleTypeDef huart2;
uint32_t test_mask;
static uint8_t *rx_byte;
void before_mask(void) { }
void after_restore(void) { }
HAL_StatusTypeDef HAL_UART_Abort(UART_HandleTypeDef *uart)
{ assert(uart == &huart2 && test_mask == 1U); rx_byte = NULL; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Receive_IT(UART_HandleTypeDef *uart, uint8_t *data, uint16_t length)
{ assert(uart == &huart2 && data != NULL && length == 1U); rx_byte = data; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit_IT(UART_HandleTypeDef *uart, uint8_t *data, uint16_t length)
{
    assert(uart == &huart2 && test_mask == 1U); write_calls++;
    if (!connected) { return HAL_BUSY; }
    if (fail_write) { return HAL_ERROR; }
    TxAccept(data, length); return HAL_OK;
}
static void Feed(const uint8_t *data, uint16_t length)
{
    for (uint16_t i = 0U; i < length; i++)
    { assert(rx_byte != NULL); *rx_byte = data[i]; HAL_UART_RxCpltCallback(&huart2); }
}
static void Connect(uint8_t value)
{
    connected = value; pending = 0U;
    cancelled_acknowledgements = forwarded - acknowledgements;
    assert(PcByteStream_Init() == PC_BYTE_STREAM_INIT_OK);
}
'''

def Run(root, host_cc):
    from c071_uart_host import HEADER
    root = Path(root)
    build = root / 'build/c071-uart-backpressure'
    build.mkdir(parents=True, exist_ok=True)
    (build / 'main.h').write_text(HEADER, encoding='utf-8')
    body = (root / 'Tests/Host/ground_backpressure.c').read_text(encoding='utf-8')
    start = body.index('#if defined(GROUND_TEST_USB)')
    end = body.index('#endif', start) + len('#endif')
    body = body[:start] + UART + body[end:]
    body = body.replace('#if defined(GROUND_TEST_USB)\n    usb_class.TxState = 0U;\n#endif',
                        '    HAL_UART_TxCpltCallback(&huart2);')
    body = body.replace('#if !defined(GROUND_TEST_USB)\n        assert(read_bytes == 64U && (unsigned)(rx_head - rx_tail) == 64U);\n#endif', '')
    harness = build / 'backpressure.c'
    harness.write_text(body, encoding='utf-8')
    includes = (build, root/'Ground/Core/Inc', root/'Ground/Protocol/Inc', root/'Common/Inc')
    sources = ('Generated/Src/pc_byte_stream.c', 'Common/Src/silverstar_assert.c',
               'Ground/Core/Src/ground_bridge.c', 'Ground/Protocol/Src/gsp_min_protocol.c',
               'Ground/Protocol/Src/protocol_crc16.c')
    exe = build / 'backpressure.exe'
    command = [host_cc, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wconversion',
               '-Wsign-conversion', '-Wshadow', '-Wvla', *['-I'+str(p) for p in includes],
               *[str(root/p) for p in sources], str(harness), '-o', str(exe)]
    print('COMMAND', command, flush=True)
    subprocess.run(command, check=True)
    for scenario in ('idle', 'burst', 'radio', 'slow', 'mixed', 'sessions', 'queued-reset', 'budget', 'error', 'error-reset'):
        subprocess.run([str(exe), scenario], check=True)
    print('PASS C071 actual UART bridge pressure; mock HAL timing, no physical disconnect proof', flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', type=Path)
    parser.add_argument('--host-cc', default='gcc')
    parser.add_argument('--helper-directory', type=Path)
    args = parser.parse_args()
    if args.helper_directory:
        sys.path.insert(0, str(args.helper_directory))
    Run(args.target, args.host_cc)
