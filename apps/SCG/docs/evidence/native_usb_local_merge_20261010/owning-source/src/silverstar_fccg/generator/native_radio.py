"""Private native radio derivative for the single bare-metal owner contract."""
import hashlib
import re
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet


def NativeRadioHal_Derive(original: bytes, *, context_header="native_clock.h", context_expression="NativeClock_ContextAllowedGet()") -> bytes:
    if hashlib.sha256(original).hexdigest() != 'b8caf4dd85dd3307897fa8f923adcaf7153b0d4c91a787eb58537d0b34eb783d':
        raise ValueError('Native radio HAL payload profile changed; review its ownership contract')
    source = original.decode('utf-8-sig')
    source = source.replace('#include "platform_time.h"',
        '#include "platform_time.h"\n#include "'+context_header+'"',1)
    start,_opening,end=NativeC_FunctionSpanGet(source,'SX1280HalWakeup')
    function=source[start:end]
    enter='    PlatformCriticalState critical_state = PlatformCritical_Enter();'
    exit='    PlatformCritical_Exit(critical_state);'
    if function.count(enter)!=1 or function.count(exit)!=1:
        raise ValueError('Native radio Wakeup critical owner changed')
    function=function.replace(enter,'''    /* Native bare-metal main is the sole radio/SPI owner; DIO ISR only
     * records a flag. Keep tick/USB IRQs live through SPI and Busy waits. */
    SILVERSTAR_ASSERT(NativeClock_ContextAllowedGet() != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);''',1)
    function=function.replace(exit,'',1)
    function=function.replace('NativeClock_ContextAllowedGet()',context_expression)
    return (source[:start]+function+source[end:]).encode('utf-8')


def NativeRadioDevice_Derive(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != '56ee9b35e54535249816363d0328120a6018f157ce51f8bad93185ebea78428c':
        raise ValueError('Native radio device payload changed; review timestamp/IRQ ownership')
    source=original.decode('utf-8-sig')
    contracts=(('Lora_RadioFault',1,0),('Lora_TxResultGet',1,0),('Lora_DiagnosticsRefresh',2,0),
        ('Lora_TxReceiptRecord',1,0),('Lora_ForceRxContinuousDirect',1,1),
        ('Lora_ControlResultGet',1,0),('Lora_ControlProcess',1,0))
    for name,expected_times,lock_index in contracts:
        start,_opening,end=NativeC_FunctionSpanGet(source,name)
        function=source[start:end].replace('\r\n','\n')
        times=list(re.finditer(r'\bPlatformTime_Ms\(\)',function))
        locks=list(re.finditer(r'(?m)^    (?:uint32_t )?primask = Lora_IrqLock\(\);',function))
        expected_locks=2 if name in {'Lora_ForceRxContinuousDirect','Lora_ControlProcess'} else 1
        if len(times)!=expected_times or len(locks)!=expected_locks or times[-1].start()<locks[lock_index].start():
            raise ValueError('Native radio timestamp/lock boundary changed: '+name)
        # ISR only latches DIO; the sole main owner samples time immediately
        # before its state lock. The earlier diagnostic refresh probe stays live.
        time=times[-1]
        function=function[:time.start()]+'native_now_ms'+function[time.end():]
        lock=locks[lock_index]
        function=(function[:lock.start()]+'    uint32_t native_now_ms = PlatformTime_Ms();\n'+
            function[lock.start():])
        if name == 'Lora_ControlProcess':
            # Construct one coherent result locally for both timeout and normal
            # completion. The timeout publishes the complete value under the
            # same lock, instead of duplicating field-by-field publication.
            initial = '''    result.transaction_id = s_control_transaction.transaction_id;
    result.raw_irq_before = 0U;
'''
            timeout = '''        s_control_transaction.result.transaction_id =
            s_control_transaction.transaction_id;
        s_control_transaction.result.result = LORA_DIAG_RESULT_TIMEOUT;
        s_control_transaction.result.raw_irq_before = 0U;'''
            if function.count(initial) != 1 or function.count(timeout) != 1:
                raise ValueError('Native control result publication profile changed')
            function = function.replace(initial, '', 1)
            function = function.replace('    if ((native_now_ms - ', initial+'    if ((native_now_ms - ', 1)
            function = function.replace(timeout, '''        result.result = LORA_DIAG_RESULT_TIMEOUT;
        s_control_transaction.result = result;''', 1)
        source=source[:start]+function+source[end:]
    return source.encode('utf-8')
