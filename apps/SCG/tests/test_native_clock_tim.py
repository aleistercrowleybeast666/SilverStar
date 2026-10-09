"""Actual native timer bodies and counter port with bounded Host fault cases."""
from pathlib import Path
from types import SimpleNamespace
import os,shutil,subprocess,json
import pytest
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender
from silverstar_fccg.generator.native_clock_tim import NativeClockTimSourceContract_Inspect, NativeClockTimDerivatives_Render, NativeClockTimPort_Render
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.hardware.native_classic_cdc import NativeClassicCdc_Inspect
from test_native_classic_cdc import native
from test_native_derivatives import _Replay


@pytest.fixture
def timer_native(tmp_path):
    root,args=native.__wrapped__(SimpleNamespace(param='f407-usb'),tmp_path)
    proof,inventory,files=NativeClassicCdc_Inspect(root,**args)
    return proof,inventory,files


def test_actual_timer_source_and_replay_contract(timer_native,tmp_path):
    proof,_inventory,files=timer_native
    contract=NativeClockTimSourceContract_Inspect(files,proof['build']['sources'],hclk_hz=168000000)
    assert contract['counter_hz']==1000000 and contract['period_counts']==1000
    rendered,_replacements,manifest=NativeClockTimDerivatives_Render(files)
    for entry in manifest['entries']:
        original=files[entry['original'].removeprefix('HardwareGenerated/NativeClassicCdc/')]
        _Replay(tmp_path,entry['original'],original,rendered[entry['derived']],rendered[entry['patch']])


@pytest.mark.parametrize('mutation',['timebase','irq','callback','tick','inventory','another-owner','shared-owner','clock-header'])
def test_unreviewed_timer_owner_is_rejected(timer_native,mutation):
    proof,_inventory,files=timer_native
    if mutation in ('timebase','irq'):
        path='Core/Src/stm32f4xx_hal_timebase_tim.c' if mutation=='timebase' else 'Core/Src/stm32f4xx_it.c'
        files[path]+=b'\n/* unreviewed */\n'
    elif mutation=='callback':
        files['Core/Src/main.c']=files['Core/Src/main.c'].replace(b'    HAL_IncTick();',b'    HAL_IncTick(); HAL_IncTick();')
    elif mutation=='tick':
        path=next(p for p in files if p.endswith('/stm32f4xx_hal.c'))
        files[path]=files[path].replace(b'  return uwTick;',b'  return uwTick + 1U;')
    elif mutation=='inventory':
        path=next(p for p in files if p.endswith('.ioc') and '/' not in p)
        files[path]=files[path].replace(b'NVIC.TimeBaseIP=TIM1',b'NVIC.TimeBaseIP=TIM2')
    elif mutation=='another-owner':
        path='Core/Src/gpio.c';files[path]+=b'\nvoid Extra_Configure(void) { htim1.Init.Period = 5U; }\n'
    elif mutation=='shared-owner':
        path='Core/Src/gpio.c';files[path]+=b'\nvoid Extra_Configure(void) { htim10.Instance = TIM10; }\n'
    else:
        path='Drivers/CMSIS/Device/ST/STM32F4xx/Include/stm32f407xx.h'
        files[path]+=b'\n#define RCC_DCKCFGR_TIMPRE 1U\n'
    with pytest.raises(ValueError):
        NativeClockTimSourceContract_Inspect(files,proof['build']['sources'],hclk_hz=168000000)


def test_timer_probe_has_one_heap_owner_and_explicit_configuration(timer_native):
    from silverstar_fccg.generator.native_clock_probe import NativeTimerProbe_FilesRender, NativeTimerProbe_MakeRender
    proof,_inventory,files=timer_native
    scg=Path(__file__).resolve().parents[1]
    rendered,graph,contract=NativeTimerProbe_FilesRender(files,proof,hclk_hz=168000000,scg_root=scg)
    assert len(graph['sources'])==len(set(graph['sources']))
    objects=[str(Path(p).with_suffix('.o')) for p in graph['sources']+graph['asm_sources']]
    assert len(objects)==len(set(objects))
    assert graph['sources'].count('Generated/Src/native_no_heap.c')==1
    assert not any(p.endswith('/sysmem.c') for p in graph['sources'])
    assert graph['include_dirs'][0]==contract['usb_config']['derived'].rsplit('/',1)[0]
    for original,derived in contract['source_replacements'].items():
        assert original not in graph['sources'] and graph['sources'].count(derived)==1
    make=NativeTimerProbe_MakeRender(graph,'arm-none-eabi-')
    assert '-Wl,-u,_sbrk' in make and 'Tools/check_native_probe.py artifact' in make
    assert rendered['Generated/Src/native_clock_port.c']==NativeClockTimPort_Render()


_HEADER='''#ifndef TEST_NATIVE_MAIN_H
#define TEST_NATIVE_MAIN_H
#include <stdint.h>
#define __NVIC_PRIO_BITS 4U
#define USE_HAL_TIM_REGISTER_CALLBACKS 0U
#define RCC_HCLK_DIV1 0U
#define RCC_HCLK_DIV2 4U
#define TIM_COUNTERMODE_UP 0U
#define TIM_AUTORELOAD_PRELOAD_DISABLE 0U
#define TIM_CR1_CEN 1U
#define TIM_CR1_UDIS 2U
#define TIM_CR1_URS 4U
#define TIM_CR1_DIR 16U
#define TIM_CR1_CMS 96U
#define TIM_CR1_ARPE 128U
#define TIM_CR1_CKD 768U
#define TIM_DIER_UIE 1U
#define TIM_SR_UIF 1U
#define TIM_IT_UPDATE 1U
#define TIM1_UP_TIM10_IRQn 25
#define HAL_TICK_FREQ_1KHZ 1U
#define HAL_TIM_STATE_BUSY 2U
typedef enum { HAL_OK, HAL_ERROR } HAL_StatusTypeDef;
typedef struct { uint32_t CR1,SMCR,RCR,ARR,PSC,DIER,SR,CNT; } TimerRegisters;
extern TimerRegisters timer_registers;
#define TIM1 (&timer_registers)
typedef struct { uint32_t Period,Prescaler,ClockDivision,CounterMode,AutoReloadPreload; } TimerInit;
typedef struct { TimerRegisters *Instance; TimerInit Init; uint32_t State; } TIM_HandleTypeDef;
extern TIM_HandleTypeDef htim1;
typedef struct { uint32_t APB2CLKDivider; } RCC_ClkInitTypeDef;
extern uint32_t SystemCoreClock,uwTickPrio;
uint32_t HAL_RCC_GetPCLK2Freq(void);
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *config,uint32_t *latency);
uint32_t HAL_RCC_GetHCLKFreq(void);
uint32_t HAL_GetTickFreq(void);
uint32_t HAL_GetTick(void);
uint32_t __get_IPSR(void);
uint32_t __get_PRIMASK(void);
uint32_t NVIC_GetEnableIRQ(int irq);
void HAL_NVIC_EnableIRQ(int irq);
void HAL_NVIC_SetPriority(int irq,uint32_t priority,uint32_t sub);
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *handle);
HAL_StatusTypeDef HAL_TIM_Base_Start_IT(TIM_HandleTypeDef *handle);
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *handle);
HAL_StatusTypeDef HAL_InitTick(uint32_t priority);
void TIM1_UP_TIM10_IRQHandler(void);
#define __HAL_RCC_TIM1_CLK_ENABLE() ((void)0)
#endif
'''


def _Compile(tmp_path,source,harness,label):
    gcc=shutil.which('gcc')
    if gcc is None:pytest.skip('Host GCC unavailable')
    scg=Path(__file__).resolve().parents[1]
    api=scg/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    (tmp_path/'main.h').write_text(_HEADER)
    for path,content in NativeClock_FilesRender(hclk_hz=168000000).items():
        dest=tmp_path/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
    path=tmp_path/(label+'.c');path.write_text('#include "main.h"\n#include "native_clock.h"\n#include "platform_critical.h"\n#include <assert.h>\n#include <string.h>\n'+source+harness)
    exe=tmp_path/(label+'.exe')
    command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion','-Wundef','-fanalyzer',
        '-I'+str(tmp_path),'-I'+str(api),'-I'+str(tmp_path/'Generated/Inc'),str(path),'-o',str(exe)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (tmp_path/(label+'-command.json')).write_text(json.dumps({'command':command,'exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr},indent=2))
    assert run.returncode==0,run.stdout+run.stderr
    return exe


_OWNER='''
TimerRegisters timer_registers;
TIM_HandleTypeDef htim1;
uint32_t SystemCoreClock=168000000U,uwTickPrio;
static uint32_t pclk=84000000U,divider=RCC_HCLK_DIV2,enabled,priority_set,irq_calls;
static HAL_StatusTypeDef base_result=HAL_OK,start_result=HAL_OK;
uint32_t HAL_RCC_GetPCLK2Freq(void) { return pclk; }
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *config,uint32_t *latency) { config->APB2CLKDivider=divider;*latency=0U; }
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *handle) { assert(handle==&htim1);return base_result; }
HAL_StatusTypeDef HAL_TIM_Base_Start_IT(TIM_HandleTypeDef *handle) { assert(handle==&htim1);return start_result; }
void HAL_NVIC_EnableIRQ(int irq) { assert(irq==25);enabled++; }
void HAL_NVIC_SetPriority(int irq,uint32_t priority,uint32_t sub) { assert(irq==25 && priority<16U && sub==0U);priority_set++; }
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *handle) { assert(handle==&htim1);irq_calls++; }
int main(int argc,char **argv)
{
    assert(argc==2);
    if (strcmp(argv[1],"div1")==0) { pclk=16000000U;divider=RCC_HCLK_DIV1; }
    if (strcmp(argv[1],"bad-divider")==0) { divider=8U; }
    if (strcmp(argv[1],"bad-clock")==0) { pclk=16500000U;divider=RCC_HCLK_DIV1; }
    if (strcmp(argv[1],"base-fail")==0) { base_result=HAL_ERROR; }
    if (strcmp(argv[1],"start-fail")==0) { start_result=HAL_ERROR; }
    uint32_t priority=strcmp(argv[1],"bad-priority")==0 ? 16U : 15U;
    HAL_StatusTypeDef result=HAL_InitTick(priority);
    if (priority==16U || divider==8U || pclk==16500000U || base_result!=HAL_OK || start_result!=HAL_OK)
    { assert(result==HAL_ERROR && enabled==0U && priority_set==0U);return 0; }
    assert(result==HAL_OK && enabled==1U && priority_set==1U && uwTickPrio==15U);
    assert(htim1.Init.Period==999U);
    assert(htim1.Init.Prescaler==((divider==RCC_HCLK_DIV1 ? pclk : 2U*pclk)/1000000U-1U));
    TIM1_UP_TIM10_IRQHandler();assert(irq_calls==1U);
    return 0;
}
'''


@pytest.mark.parametrize('scenario',['div1','div2','bad-clock','bad-divider','bad-priority','base-fail','start-fail'])
def test_actual_timer_init_irq_pre_failure_and_derivative(timer_native,tmp_path,scenario):
    _proof,_inventory,files=timer_native
    rendered,_replace,_manifest=NativeClockTimDerivatives_Render(files)
    for label,inputs in [('original',files),('derived',rendered)]:
        body=''
        for suffix,name in [('stm32f4xx_hal_timebase_tim.c','HAL_InitTick'),('stm32f4xx_it.c','TIM1_UP_TIM10_IRQHandler')]:
            text=next(value.decode('utf-8-sig') for path,value in inputs.items() if path.endswith('/'+suffix))
            a,_o,b=NativeC_FunctionSpanGet(text,name);body+=text[a:b]+'\n'
        exe=_Compile(tmp_path,body,_OWNER,label)
        run=subprocess.run([str(exe),scenario],capture_output=True,text=True,timeout=15)
        (tmp_path/(label+'-'+scenario+'.log')).write_text(run.stdout+run.stderr)
        # These are real failures of the original body, not a replaced safety
        # expectation. Failed HAL init/start already returned ordinary errors.
        expected=0 if label=='derived' or scenario in ('base-fail','start-fail') else 1
        assert (run.returncode==0)==(expected==0),run.stdout+run.stderr


def test_actual_timer_port_boundary_and_pending_irq_contract(tmp_path):
    harness='''
TimerRegisters timer_registers={.CR1=1U,.ARR=999U,.PSC=167U,.DIER=1U,.CNT=123U};
TIM_HandleTypeDef htim1={.Instance=TIM1,.State=HAL_TIM_STATE_BUSY};
uint32_t SystemCoreClock=168000000U,uwTickPrio;
static uint32_t pclk=84000000U,divider=RCC_HCLK_DIV2,enabled=1U,mask,ipsr,tick=9U,retire_pending;
uint32_t HAL_RCC_GetPCLK2Freq(void) { return pclk; }
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *config,uint32_t *latency) { config->APB2CLKDivider=divider;*latency=0U; }
uint32_t HAL_RCC_GetHCLKFreq(void) { return SystemCoreClock; }
uint32_t HAL_GetTickFreq(void) { return 1U; }
uint32_t HAL_GetTick(void) { return tick; }
uint32_t __get_IPSR(void) { return ipsr; }
uint32_t __get_PRIMASK(void) { return mask; }
uint32_t NVIC_GetEnableIRQ(int irq) { assert(irq==25);return enabled; }
PlatformCriticalState PlatformCritical_Enter(void) { uint32_t saved=mask;mask=1U;return saved; }
void PlatformCritical_Exit(PlatformCriticalState saved)
{ mask=saved;if (retire_pending!=0U && mask==0U && (TIM1->SR&1U)!=0U) { TIM1->SR=0U;tick++;TIM1->CNT=1U; } }
int main(void)
{
    NativeClockSnapshot sample={0xDEADU,0xBEEFU};
    assert(NativeClockPort_SnapshotGet(NULL)==NativeClockResult_InvalidArgument);
    assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok);
    assert(sample.tick_ms==9U && sample.elapsed_cycles==123U*168U && mask==0U);
    mask=1U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidContext && mask==1U);mask=0U;
    ipsr=3U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidContext);ipsr=0U;
    sample.tick_ms=0xDEADU;sample.elapsed_cycles=0xBEEFU;
    TIM1->SR=1U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot);
    assert(sample.tick_ms==0xDEADU && sample.elapsed_cycles==0xBEEFU && mask==0U);
    retire_pending=1U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok && sample.tick_ms==10U && sample.elapsed_cycles==168U);
    TIM1->CR1=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->CR1=1U;
    divider=8U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);divider=RCC_HCLK_DIV2;
    TIM1->PSC=83U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->PSC=167U;
    TIM1->ARR=1000U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->ARR=999U;
    TIM1->DIER=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->DIER=1U;
    enabled=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);enabled=1U;
    TIM1->CNT=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_Ok && sample.elapsed_cycles==0U);
    TIM1->CNT=1000U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot);
    return 0;
}
'''
    exe=_Compile(tmp_path,NativeClockTimPort_Render().decode(),harness,'timer-port')
    run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
    assert run.returncode==0,run.stdout+run.stderr
