"""Ordinary native HAL boot return propagation; no USB/control execution."""
from pathlib import Path
import os,subprocess,shutil,json,hashlib
import pytest
from silverstar_fccg.generator.native_clock_tim import NativeClockTimCallerDerivatives_Render
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet


@pytest.mark.parametrize('scenario',['normal','init-failure','clock-failure'])
def test_actual_hal_boot_callers_propagate_timer_return(tmp_path,scenario):
    gcc=shutil.which('gcc');origin=os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT')
    if not gcc or not origin:pytest.skip('Actual native input or Host GCC unavailable')
    native=Path(origin)/'cube-f407-usb'
    paths=['Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c',
        'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c']
    files={p:(native/p).read_bytes() for p in paths}
    rendered,replacements,_manifest=NativeClockTimCallerDerivatives_Render(files)
    header=r"""#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#define INSTRUCTION_CACHE_ENABLE 0U
#define DATA_CACHE_ENABLE 0U
#define PREFETCH_ENABLE 0U
#define NVIC_PRIORITYGROUP_4 4U
#define TICK_INT_PRIORITY 15U
#define RCC_CLOCKTYPE_HCLK 1U
#define RCC_CLOCKTYPE_PCLK1 2U
#define RCC_CLOCKTYPE_PCLK2 4U
#define RCC_CLOCKTYPE_SYSCLK 8U
#define RCC_CFGR_PPRE1 0x1C00U
#define RCC_CFGR_PPRE2 0xE000U
#define RCC_CFGR_HPRE 0xF0U
#define RCC_CFGR_HPRE_Pos 4U
#define RCC_CFGR_SWS_Pos 2U
#define RCC_HCLK_DIV16 0x1C00U
#define RCC_SYSCLKSOURCE_HSE 1U
#define RCC_SYSCLKSOURCE_PLLCLK 2U
#define RCC_SYSCLKSOURCE_PLLRCLK 3U
#define RCC_FLAG_HSERDY 1U
#define RCC_FLAG_PLLRDY 2U
#define RCC_FLAG_HSIRDY 3U
#define RESET 0U
#define CLOCKSWITCH_TIMEOUT_VALUE 5U
#define IS_RCC_CLOCKTYPE(v) ((v)<=15U)
#define IS_FLASH_LATENCY(v) ((v)<=7U)
#define IS_RCC_HCLK(v) ((v)<=0xF0U)
#define IS_RCC_SYSCLKSOURCE(v) ((v)<=3U)
#define IS_RCC_PCLK(v) ((v)<=RCC_HCLK_DIV16)
#define assert_param(v) assert(v)
#define MODIFY_REG(reg,clear,value) ((reg)=((reg)&~(clear))|(value))
typedef enum { HAL_OK,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT } HAL_StatusTypeDef;
typedef struct { uint32_t ClockType,SYSCLKSource,AHBCLKDivider,APB1CLKDivider,APB2CLKDivider; } RCC_ClkInitTypeDef;
static struct { uint32_t CFGR; } rcc;
#define RCC (&rcc)
static uint32_t latency,sys_source,SystemCoreClock=16000000U,uwTickPrio=15U,tick_calls,msp_calls;
static const uint32_t AHBPrescTable[16]={0U};
static HAL_StatusTypeDef tick_result=HAL_OK;
#define __HAL_FLASH_GET_LATENCY() latency
#define __HAL_FLASH_SET_LATENCY(v) (latency=(v))
#define __HAL_RCC_GET_FLAG(v) ((v)!=0U ? 1U : 0U)
#define __HAL_RCC_SYSCLK_CONFIG(v) (sys_source=((v)<<RCC_CFGR_SWS_Pos))
#define __HAL_RCC_GET_SYSCLK_SOURCE() sys_source
static void HAL_NVIC_SetPriorityGrouping(uint32_t group) { assert(group==4U); }
static void HAL_MspInit(void) { msp_calls++; }
static uint32_t HAL_GetTick(void) { return 0U; }
static uint32_t HAL_RCC_GetSysClockFreq(void) { return 168000000U; }
static HAL_StatusTypeDef HAL_InitTick(uint32_t priority) { assert(priority==15U);tick_calls++;return tick_result; }
HAL_StatusTypeDef HAL_Init(void);
HAL_StatusTypeDef HAL_RCC_ClockConfig(const RCC_ClkInitTypeDef *,uint32_t);
"""
    harness=r"""int main(int argc,char **argv)
{
  assert(argc==2);RCC_ClkInitTypeDef clock={.ClockType=15U,.SYSCLKSource=RCC_SYSCLKSOURCE_PLLCLK};
  if (strcmp(argv[1],"init-failure")==0) { tick_result=HAL_ERROR; }
  assert(HAL_Init()==tick_result);
  assert(msp_calls==(tick_result==HAL_OK ? 1U : 0U));
  if (strcmp(argv[1],"clock-failure")==0) { tick_result=HAL_ERROR; }
  assert(HAL_RCC_ClockConfig(&clock,5U)==tick_result);
  assert(tick_calls==2U && SystemCoreClock==168000000U);
  return 0;
}
"""
    for label in ('original','fixed'):
        functions=[]
        for path,name in zip(paths,('HAL_Init','HAL_RCC_ClockConfig')):
            data=files[path] if label=='original' else rendered[replacements['HardwareGenerated/NativeClassicCdc/'+path]]
            text=data.decode();a,_o,b=NativeC_FunctionSpanGet(text,name);functions.append(text[a:b])
        source=tmp_path/(label+'.c');source.write_text(header+'\n'.join(functions)+'\n'+harness)
        exe=tmp_path/(label+'.exe')
        command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion','-Wundef','-fanalyzer',str(source),'-o',str(exe)]
        compiled=subprocess.run(command,capture_output=True,text=True,timeout=60)
        assert compiled.returncode==0,compiled.stdout+compiled.stderr
        run=subprocess.run([str(exe),scenario],capture_output=True,text=True,timeout=15)
        (tmp_path/(label+'-evidence.json')).write_text(json.dumps({'compile':command,'compile_exit':compiled.returncode,'compile_stdout':compiled.stdout,'compile_stderr':compiled.stderr,
            'run':[str(exe),scenario],'run_exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr,
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()},indent=2))
        assert (run.returncode==0)==(label=='fixed' or scenario=='normal'),run.stdout+run.stderr
