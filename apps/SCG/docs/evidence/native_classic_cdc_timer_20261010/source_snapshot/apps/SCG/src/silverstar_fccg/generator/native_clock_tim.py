"""Private actual TIM1 timebase profile; originals remain immutable.

This is a native source/counter contract, not an MCU-family backend selector.
Hardware IRQ latency and the complete timer/library call graph remain unproven.
"""
import hashlib
import difflib
import re
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet, NativeC_VisibleGet
from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX


_TIMEBASE = 'Core/Src/stm32f4xx_hal_timebase_tim.c'
_IRQ = 'Core/Src/stm32f4xx_it.c'
_CLOCK_HEADER = 'Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f407xx.h'
_CLOCK_HEADER_SHA256 = 'bd21220ea8b6858c2d727cca1d2a5f1077f8a81717acdac583a1e9165d858160'
_PROFILES = {_TIMEBASE:'bfc01b357084f00c3799755d1c3d9ce7536a4072f31f6136fc3bdd431c1880aa',
    _IRQ:'5f7ec81a56f6765c682581b90da27fea1b07002fad09b174592263ae7377965e'}


def NativeClockTimSourceContract_Inspect(files, sources, *, hclk_hz):
    # F407's timer multiplier has no selectable TIMPRE mode. Bind that fact to
    # its actual reviewed device header, rather than adding a preprocessing
    # exception or assuming that every F4 has the same kernel clock contract.
    if hashlib.sha256(files.get(_CLOCK_HEADER,b'')).hexdigest()!=_CLOCK_HEADER_SHA256:
        raise ValueError('Native TIM1 kernel clock header requires review')
    for path,digest in _PROFILES.items():
        if path not in sources or hashlib.sha256(files.get(path,b'')).hexdigest()!=digest:
            raise ValueError('Native TIM1 source profile requires review: '+path)
    iocs=[p for p in files if p.endswith('.ioc') and '/' not in p]
    if len(iocs)!=1:raise ValueError('Native TIM1 requires one native clock inventory')
    fields=dict(line.split('=',1) for line in files[iocs[0]].decode('utf-8-sig').splitlines() if '=' in line)
    if fields.get('NVIC.TimeBaseIP')!='TIM1' or fields.get('RCC.HCLKFreq_Value')!=str(hclk_hz):
        raise ValueError('Native TIM1 clock inventory does not match its actual owner')
    # The recognized strong callback is in the native main, not the vendor's
    # weak default. No callback registry, alternate increment or timer owner.
    callbacks=[]; ticks=[]
    for path in sources:
        text=files[path].decode('utf-8-sig')
        for name,owners in [('HAL_TIM_PeriodElapsedCallback',callbacks),('HAL_GetTick',ticks)]:
            try:a,o,b=NativeC_FunctionSpanGet(text,name)
            except ValueError:continue
            if '__weak' not in NativeC_VisibleGet(text[a:o]):owners.append((path,text[o+1:b-1]))
        if path!=_TIMEBASE and re.search(r'\bhtim1\s*\.\s*(?:Instance|Init)\b',NativeC_VisibleGet(text)):
            raise ValueError('Native TIM1 has an additional configuration owner')
        if path.startswith('Core/') and re.search(r'\bTIM10\b',NativeC_VisibleGet(text)):
            raise ValueError('Native TIM1 shared vector has an unreviewed TIM10 owner')
    if len(callbacks)!=1 or re.sub(r'\s+','',NativeC_VisibleGet(callbacks[0][1]))!='if(htim->Instance==TIM1){HAL_IncTick();}':
        raise ValueError('Native TIM1 period callback/increment owner is unreviewed')
    # HAL_GetTick is weak but deliberately retained; no strong replacement.
    hal_paths=[p for p in sources if p.endswith('/stm32f4xx_hal.c')]
    if len(hal_paths)!=1 or ticks:raise ValueError('Native HAL tick has an unreviewed override')
    hal=files[hal_paths[0]].decode('utf-8-sig')
    for name,expected in [('HAL_GetTick','returnuwTick;'),('HAL_IncTick','uwTick+=(uint32_t)uwTickFreq;')]:
        _a,o,b=NativeC_FunctionSpanGet(hal,name)
        actual=re.sub(r'\s+','',NativeC_VisibleGet(hal[o+1:b-1]))
        alternatives={expected,'uwTick+=uwTickFreq;'} if name=='HAL_IncTick' else {expected}
        if actual not in alternatives:
            raise ValueError('Native TIM1 HAL tick contract changed: '+name)
    if not re.search(r'HAL_TickFreqTypeDef\s+uwTickFreq\s*=\s*HAL_TICK_FREQ_DEFAULT\s*;',NativeC_VisibleGet(hal)):
        raise ValueError('Native TIM1 tick frequency is not the reviewed default')
    return {'port':'tim1','hclk_hz':hclk_hz,'timebase_owner':_TIMEBASE,'irq_owner':_IRQ,
        'clock_header':_CLOCK_HEADER,'clock_header_sha256':_CLOCK_HEADER_SHA256,
        'callback_owner':callbacks[0][0],'tick_owner':hal_paths[0],'counter_hz':1000000,
        'period_counts':1000,'runtime_policy':'Actual APB2/TIM1 1MHz/1000-count port; pending update rejected, no SysTick substitution',
        'limits':'NOT PROVEN: timer IRQ latency, waveform timing, call graph/stack and hardware'}


def NativeClockTimDerivatives_Render(files):
    for path,digest in _PROFILES.items():
        if hashlib.sha256(files.get(path,b'')).hexdigest()!=digest:
            raise ValueError('Native TIM1 derivative source changed: '+path)
    source=files[_TIMEBASE].decode('utf-8-sig').replace('\r\n','\n')
    a,o,b=NativeC_FunctionSpanGet(source,'HAL_InitTick')
    function=source[a:b]
    opening=o-a+1
    function=function[:opening]+'''
  if (TickPriority >= (1UL << __NVIC_PRIO_BITS)) { return HAL_ERROR; }
'''+function[opening:]
    old='uwTimclock = 2*HAL_RCC_GetPCLK2Freq();'
    if function.count(old)!=1:raise ValueError('Native TIM1 APB2 clock expression changed')
    function=function.replace(old,'''uwTimclock = HAL_RCC_GetPCLK2Freq();
  if ((uwTimclock == 0U) || (uwTimclock > 100000000U)) { return HAL_ERROR; }
  if (clkconfig.APB2CLKDivider != RCC_HCLK_DIV1) { uwTimclock *= 2U; }
  if ((uwTimclock < 1000000U) || ((uwTimclock % 1000000U) != 0U)) { return HAL_ERROR; }''',1)
    enable='HAL_NVIC_EnableIRQ(TIM1_UP_TIM10_IRQn);'
    if function.count(enable)!=1 or function.count('uwTickPrio = TickPriority;')!=1:
        raise ValueError('Native TIM1 IRQ initialization boundary changed')
    function=function.replace(enable,'',1).replace('uwTickPrio = TickPriority;',
        'uwTickPrio = TickPriority;\n        '+enable,1)
    source=source[:a]+function+source[b:]
    irq=files[_IRQ].decode('utf-8-sig')
    a,o,b=NativeC_FunctionSpanGet(irq,'TIM1_UP_TIM10_IRQHandler')
    if NativeC_VisibleGet(irq[o+1:b-1]).strip():
        raise ValueError('Native TIM1 refuses an existing/custom shared IRQ owner')
    irq=irq[:o+1]+'\n  HAL_TIM_IRQHandler(&htim1);\n'+irq[o+1:]
    include='#include "stm32f4xx_it.h"'
    if irq.count(include)!=1:raise ValueError('Native TIM1 IRQ include owner changed')
    irq=irq.replace(include,include+'\nextern TIM_HandleTypeDef htim1;',1)
    rendered={};replacements={};entries=[]
    for path,derived in [(_TIMEBASE,source.encode()),(_IRQ,irq.encode())]:
        original=files[path];target='HardwareGenerated/ReviewedNativeTime/'+path
        patch=target+'.patch';rendered[target]=derived
        rendered[patch]=''.join(difflib.unified_diff(original.decode().splitlines(keepends=True),
            derived.decode().splitlines(keepends=True),fromfile=NATIVE_PREFIX+path,tofile=NATIVE_PREFIX+path)).encode()
        replacements[NATIVE_PREFIX+path]=target
        entries.append({'original':NATIVE_PREFIX+path,'original_sha256':hashlib.sha256(original).hexdigest(),
            'derived':target,'derived_sha256':hashlib.sha256(derived).hexdigest(),
            'patch':patch,'patch_sha256':hashlib.sha256(rendered[patch]).hexdigest()})
    return rendered,replacements,{'entries':entries,'scope':'Private TIM1 timebase and initially empty shared IRQ; no other shared owner admitted'}


def NativeClockTimPort_Render():
    return '''#include "native_clock.h"
#include "platform_critical.h"
#include "main.h"
#include <stddef.h>
/* A real compiled callback ownership contract, not assertion density credit.
 * The selected F407 kernel-clock header is separately pinned and checked. */
_Static_assert(USE_HAL_TIM_REGISTER_CALLBACKS == 0U,
    "Native TIM1 port requires fixed HAL timer callbacks");
extern TIM_HandleTypeDef htim1;

uint8_t NativeClock_ContextAllowedGet(void)
{
    return ((__get_IPSR() == 0U) && (__get_PRIMASK() == 0U)) ? 1U : 0U;
}

static uint8_t NativeTimer_ConfigurationValidGet(void)
{
    RCC_ClkInitTypeDef config;
    uint32_t latency;
    uint32_t timer_hz = HAL_RCC_GetPCLK2Freq();
    HAL_RCC_GetClockConfig(&config, &latency);
    if (timer_hz > 100000000U) { return 0U; }
    if (config.APB2CLKDivider != RCC_HCLK_DIV1) { timer_hz *= 2U; }
    return ((SystemCoreClock == NATIVE_CLOCK_HCLK_HZ) &&
        (HAL_RCC_GetHCLKFreq() == NATIVE_CLOCK_HCLK_HZ) &&
        (HAL_GetTickFreq() == HAL_TICK_FREQ_1KHZ) && (timer_hz >= 1000000U) &&
        ((timer_hz % 1000000U) == 0U) && (htim1.Instance == TIM1) &&
        (htim1.State == HAL_TIM_STATE_BUSY) &&
        ((TIM1->CR1 & (TIM_CR1_CEN | TIM_CR1_UDIS | TIM_CR1_URS | TIM_CR1_DIR |
            TIM_CR1_CMS | TIM_CR1_CKD | TIM_CR1_ARPE)) == TIM_CR1_CEN) &&
        (TIM1->SMCR == 0U) && (TIM1->RCR == 0U) && (TIM1->ARR == 999U) &&
        (TIM1->PSC == (timer_hz / 1000000U - 1U)) &&
        ((TIM1->DIER & TIM_DIER_UIE) != 0U) &&
        (NVIC_GetEnableIRQ(TIM1_UP_TIM10_IRQn) != 0U)) ? 1U : 0U;
}

NativeClockResult NativeClockPort_SnapshotGet(NativeClockSnapshot *snapshot)
{
    uint32_t attempt;
    if (snapshot == NULL) { return NativeClockResult_InvalidArgument; }
    if (NativeClock_ContextAllowedGet() == 0U) { return NativeClockResult_InvalidContext; }
    if (NativeTimer_ConfigurationValidGet() == 0U) { return NativeClockResult_InvalidConfiguration; }
    for (attempt = 0U; attempt < 3U; attempt++)
    {
        PlatformCriticalState saved = PlatformCritical_Enter();
        uint32_t pending_before = TIM1->SR & TIM_SR_UIF;
        uint32_t tick = HAL_GetTick();
        uint32_t counter = TIM1->CNT;
        uint32_t pending_after = TIM1->SR & TIM_SR_UIF;
        PlatformCritical_Exit(saved);
        /* A pending update may hide missed IRQs. Never invent extra HAL ticks.
         * Restore PRIMASK so the actual IRQ can retire it before a retry. */
        if ((pending_before == 0U) && (pending_after == 0U) &&
            (counter != 0U) && (counter <= 999U))
        {
            snapshot->tick_ms = tick;
            /* Common fractional interval uses HCLK-cycle units; TIM1 itself
             * counts actual microseconds at its verified 1MHz kernel. */
            snapshot->elapsed_cycles = counter * NATIVE_CLOCK_CYCLES_PER_US;
            return NativeClockResult_Ok;
        }
    }
    return NativeClockResult_UnstableSnapshot;
}
'''.encode()
