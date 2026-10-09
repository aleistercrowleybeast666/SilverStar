from pathlib import Path
import shutil,subprocess,json,hashlib
import pytest
from silverstar_fccg.generator.native_clock import NativeClock_FilesRender
from silverstar_fccg.generator.native_clock_tim import NativeClockTimPort_Render
from test_native_clock_tim import _HEADER


@pytest.mark.parametrize('scenario',['zero-phase','rollover','tick-wrap','stopped','pending'])
def test_continuously_running_timer_zero_phase_and_rollover(tmp_path,scenario):
    gcc=shutil.which('gcc')
    if not gcc:pytest.skip('Host GCC unavailable')
    scg=Path(__file__).resolve().parents[1]
    api=scg/'plugins/builtin/silverstar_platform_api/payload/Platform/Inc'
    (tmp_path/'main.h').write_text(_HEADER)
    (tmp_path/'silverstar_assert.h').write_text('#include <assert.h>\n#define SILVERSTAR_ASSERT(p,m,r) assert(p)\n')
    rendered=NativeClock_FilesRender(hclk_hz=168000000)
    (tmp_path/'native_clock.h').write_bytes(rendered['Generated/Inc/native_clock.h'])
    (tmp_path/'clock.c').write_bytes(rendered['Generated/Src/native_clock.c'])
    harness='''#include "main.h"
#include "native_clock.h"
#include "platform_time.h"
#include "platform_critical.h"
#include <assert.h>
#include <string.h>
TimerRegisters timer_registers={.CR1=1U,.ARR=999U,.PSC=167U,.DIER=1U,.CNT=123U};
TIM_HandleTypeDef htim1={.Instance=TIM1,.State=HAL_TIM_STATE_BUSY};
uint32_t SystemCoreClock=168000000U,uwTickPrio;
static uint32_t tick=9U,mask,sub_us,running=1U;
uint32_t HAL_RCC_GetPCLK2Freq(void) { return 84000000U; }
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *c,uint32_t *l) { c->APB2CLKDivider=RCC_HCLK_DIV2;*l=0U; }
uint32_t HAL_RCC_GetHCLKFreq(void) { return SystemCoreClock; }
uint32_t HAL_GetTickFreq(void) { return 1U; }
uint32_t HAL_GetTick(void) { return tick; }
uint32_t __get_IPSR(void) { return 0U; }
uint32_t __get_PRIMASK(void) { return mask; }
uint32_t NVIC_GetEnableIRQ(int irq) { assert(irq==25);return 1U; }
PlatformCriticalState PlatformCritical_Enter(void) { uint32_t saved=mask;mask=1U;return saved; }
/* Each snapshot consumes 0.2 us in this ordinary timing model, never a claim
 * about real STM32 execution time. IRQ has retired at every modeled update. */
void PlatformCritical_Exit(PlatformCriticalState saved)
{ mask=saved;if (running!=0U) { sub_us++;if(sub_us==5U) { sub_us=0U;TIM1->CNT++;if(TIM1->CNT==1000U) { TIM1->CNT=0U;tick++; } } } }
int main(int argc,char **argv)
{
  assert(argc==2);uint64_t now=0U,last;
  if (strcmp(argv[1],"tick-wrap")==0) { tick=UINT32_MAX-1U; }
  assert(PlatformTime_Init()==PLATFORM_OK);
  assert(NativeClock_Read(&now)==NativeClockResult_Ok);last=now;
  tick++;TIM1->CNT=0U;TIM1->SR=0U;sub_us=0U;
  assert(NativeClock_Read(&now)==NativeClockResult_Ok && now>=last);
  if (strcmp(argv[1],"stopped")==0) { running=0U;assert(NativeClock_DelayUs(1U)==NativeClockResult_Stopped);return 0; }
  if (strcmp(argv[1],"pending")==0) { TIM1->SR=1U;assert(NativeClock_Read(&now)==NativeClockResult_UnstableSnapshot);return 0; }
  for (unsigned i=0U;i<7000U;i++) { last=now;assert(NativeClock_Read(&now)==NativeClockResult_Ok && now>=last); }
  assert(NativeClock_StatusGet()==NativeClockResult_Ok);
  assert(NativeClock_DelayUs(1U)==NativeClockResult_Ok);
  return 0;
}'''
    (tmp_path/'phase.c').write_text(harness)
    old=scg/'docs/evidence/native_classic_cdc_timer_20261010/final/Generated/Src/native_clock_port.c'
    for label,port in [('original',old.read_bytes()),('fixed',NativeClockTimPort_Render())]:
        source=tmp_path/(label+'.c');source.write_bytes(port);exe=tmp_path/(label+'.exe')
        command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion','-Wundef','-fanalyzer',
            '-I'+str(tmp_path),'-I'+str(api),str(tmp_path/'clock.c'),str(source),str(tmp_path/'phase.c'),'-o',str(exe)]
        compile_result=subprocess.run(command,capture_output=True,text=True,timeout=60)
        assert compile_result.returncode==0,compile_result.stdout+compile_result.stderr
        result=subprocess.run([str(exe),scenario],capture_output=True,text=True,timeout=20)
        (tmp_path/(label+'-evidence.json')).write_text(json.dumps({'source_sha256':hashlib.sha256(port).hexdigest(),
            'compile_command':command,'compile_exit':compile_result.returncode,'compile_stdout':compile_result.stdout,'compile_stderr':compile_result.stderr,
            'run_command':[str(exe),scenario],'run_exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()},indent=2))
        assert (result.returncode==0)==(label=='fixed'),result.stdout+result.stderr
