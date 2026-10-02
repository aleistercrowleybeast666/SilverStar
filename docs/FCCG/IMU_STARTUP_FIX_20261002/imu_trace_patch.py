from pathlib import Path
import sys,subprocess,shutil
sys.dont_write_bytecode=True
repo=Path(r'D:\python_software\SilverStar\.work\ImuStartupHotfix_20261002')
builtin=repo/'apps/FCCG/plugins/builtin'
driver=builtin/'silverstar_device_imu_jy901b/payload/Devices/IMU/JY901B/Src/jy901b_device.c'
platform=builtin/'silverstar_mcu_family_stm32f4/payload/Platform/STM32F4/Src/platform_uart_stm32f4.c'
header=builtin/'silverstar_platform_api/payload/Platform/Inc/platform_uart.h'
checker=builtin/'silverstar_core_0_1_0/payload/Tools/check_power_of_ten.ps1'
review=repo/'.work/imu_trace_review'
if review.exists():raise FileExistsError(review)
review.mkdir(parents=True)
files=[driver,platform,header,checker]
for p in files:shutil.copy2(p,review/('original_'+p.name))
def insert_once(text,key,replacement):
    assert text.count(key)==1,(key,text.count(key))
    return text.replace(key,replacement)
guard='#if (PLATFORM_UART_FIRST_READ_TRACE_ENABLE != 0U)\n'
h=header.read_text(encoding='utf8')
h=insert_once(h,'#endif /* __PLATFORM_UART_H */',Path(__file__).with_name('imu_trace_header.txt').read_text(encoding='utf8')+'#endif /* __PLATFORM_UART_H */')
header.write_text(h,encoding='utf8',newline='\n')
p=platform.read_text(encoding='utf8')
p=insert_once(p,'#include "platform_memory.h"','#include "platform_memory.h"\n#include "platform_time.h"')
p=insert_once(p,'static PlatformResult PlatformUart_ResultMap(',Path(__file__).with_name('imu_trace_body.txt').read_text(encoding='utf8')+'static PlatformResult PlatformUart_ResultMap(')
p=insert_once(p,'    context->rx_dma_last_position = 0U;\n    context->rx_active = 0U;',guard+'''    if (PlatformUart_FirstReadTraceMatches(context) != 0U)
    {
        PlatformUart_FirstReadTraceRecord(PlatformUartFirstReadTrace_Reset,
            context->diagnostics.rx_discontinuity_count + 1U, NULL, 0U);
        s_first_read_trace.window_count = 0U;
        s_first_read_trace.window_position = 0U;
    }
#endif
    context->rx_dma_last_position = 0U;
    context->rx_active = 0U;''')
p=insert_once(p,'    written = RingBuf_Push(&context->rx_ring, data, length);',guard+'''    PlatformUart_FirstReadTraceObserve(context, data, length);
#endif
    written = RingBuf_Push(&context->rx_ring, data, length);''')
p=insert_once(p,'    if (written != length)\n    {\n        context->diagnostics.rx_discarded_bytes',guard+'''    if ((written != length) && (PlatformUart_FirstReadTraceMatches(context) != 0U))
    {
        PlatformUart_FirstReadTraceRecord(PlatformUartFirstReadTrace_Discard,
            length - written + RingBuf_GetUsed(&context->rx_ring), NULL, 0U);
    }
#endif
    if (written != length)
    {
        context->diagnostics.rx_discarded_bytes''')
p=insert_once(p,'        context->tx_dma_length = length;',guard+'''        if (PlatformUart_FirstReadTraceMatches(context) != 0U)
        {
            PlatformUart_FirstReadTraceRecord(PlatformUartFirstReadTrace_TxStart,
                length, tx_data, (uint8_t)((length < 11U) ? length : 11U));
        }
#endif
        context->tx_dma_length = length;''')
p=insert_once(p,'    (void)RingBuf_Push(ring, data, length);',guard+'''    if (PlatformUart_FirstReadTraceMatches(context) != 0U)
    {
        PlatformUart_FirstReadTraceRecord(PlatformUartFirstReadTrace_Enqueue,
            length, data, (uint8_t)((length < 11U) ? length : 11U));
    }
#endif
    (void)RingBuf_Push(ring, data, length);''')
key='''    state = PlatformCritical_Enter();
    context->diagnostics.rx_discarded_bytes +=
        RingBuf_GetUsed(&context->rx_ring);
    RingBuf_Reset(&context->rx_ring);'''
p=insert_once(p,key,'''    state = PlatformCritical_Enter();
'''+guard+'''    if (PlatformUart_FirstReadTraceMatches(context) != 0U)
    {
        PlatformUart_FirstReadTraceRecord(PlatformUartFirstReadTrace_Flush,
            RingBuf_GetUsed(&context->rx_ring), NULL, 0U);
        s_first_read_trace.window_count = 0U;
        s_first_read_trace.window_position = 0U;
    }
#endif
    context->diagnostics.rx_discarded_bytes +=
        RingBuf_GetUsed(&context->rx_ring);
    RingBuf_Reset(&context->rx_ring);''')
p=insert_once(p,'    context->diagnostics.tx_bytes += context->tx_dma_length;',guard+'''    if (PlatformUart_FirstReadTraceMatches(context) != 0U)
    {
        PlatformUart_FirstReadTraceRecord(PlatformUartFirstReadTrace_TxEnd,
            context->tx_dma_length, NULL, 0U);
    }
#endif
    context->diagnostics.tx_bytes += context->tx_dma_length;''')
platform.write_text(p,encoding='utf8',newline='\n')
d=driver.read_text(encoding='utf8').replace('Both frame kinds share the CRC.','Both frame kinds share the checksum.')
d=insert_once(d,'    if (PlatformUart_RxFlush(Jy901bResource_UartGet(instance)) != PLATFORM_OK)\n    { return Jy901bRegisterReadStartResult_IoError; }',guard+'''    PlatformUart_FirstReadTraceBegin(Jy901bResource_UartGet(instance), reg);
#endif
    if (PlatformUart_RxFlush(Jy901bResource_UartGet(instance)) != PLATFORM_OK)
    {
'''+guard+'''        PlatformUart_FirstReadTraceResult(Jy901bResource_UartGet(instance),
            1U, Jy901bRegisterReadStartResult_IoError, 1U);
#endif
        return Jy901bRegisterReadStartResult_IoError;
    }''')
d=insert_once(d,'        if (send_result == PLATFORM_BUSY)\n        { return Jy901bRegisterReadStartResult_Busy; }\n        if (send_result != PLATFORM_OK)\n        { return Jy901bRegisterReadStartResult_IoError; }','''        if (send_result != PLATFORM_OK)
        {
'''+guard+'''            PlatformUart_FirstReadTraceResult(Jy901bResource_UartGet(instance),
                1U, (send_result == PLATFORM_BUSY) ?
                Jy901bRegisterReadStartResult_Busy : Jy901bRegisterReadStartResult_IoError,
                (uint8_t)(send_result != PLATFORM_BUSY));
#endif
            return (send_result == PLATFORM_BUSY) ?
                Jy901bRegisterReadStartResult_Busy : Jy901bRegisterReadStartResult_IoError;
        }''')
d=insert_once(d,'    context->register_read_active = 1U;\n    return Jy901bRegisterReadStartResult_Ok;', '''    context->register_read_active = 1U;
'''+guard+'''    PlatformUart_FirstReadTraceResult(Jy901bResource_UartGet(instance),
        1U, Jy901bRegisterReadStartResult_Ok, 0U);
#endif
    return Jy901bRegisterReadStartResult_Ok;''')
d=insert_once(d,'    if (result != Jy901bRegisterReadPollResult_Pending)\n    { context->register_read_active = 0U; }\n    return result;',guard+'''    PlatformUart_FirstReadTraceResult(Jy901bResource_UartGet(instance),
        2U, (uint8_t)result, (uint8_t)(result != Jy901bRegisterReadPollResult_Pending));
#endif
    if (result != Jy901bRegisterReadPollResult_Pending)
    { context->register_read_active = 0U; }
    return result;''')
driver.write_text(d,encoding='utf8',newline='\n')
c=checker.read_text(encoding='utf8')
c=insert_once(c,"            ($Line -match '^\\s*#\\s*(?:else|endif)\\b'))",'''            (($normalized -in @('Platform/STM32F4/Src/platform_uart_stm32f4.c',
                                'Devices/IMU/JY901B/Src/jy901b_device.c')) -and
             ($Line -match '^\\s*#\\s*if\\s+\\(PLATFORM_UART_FIRST_READ_TRACE_ENABLE\\s*!=\\s*0U\\)\\s*$')) -or
            ($Line -match '^\\s*#\\s*(?:else|endif)\\b'))''')
checker.write_text(c,encoding='utf8',newline='\n')
git=['git','-c','safe.directory='+str(repo).replace('\\','/'),'-C',str(repo)]
for path in files:
    before=review/('original_'+path.name)
    result=subprocess.run(['git','diff','--no-index','--',str(before),str(path)],capture_output=True)
    assert result.returncode in (0,1)
    (review/(path.name+'.diff')).write_bytes(result.stdout)
print(str(review),flush=True)
