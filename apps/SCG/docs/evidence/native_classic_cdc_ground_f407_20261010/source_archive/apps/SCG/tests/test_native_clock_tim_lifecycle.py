from pathlib import Path
import subprocess,json
import pytest
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.generator.native_clock_tim import NativeClockTimDerivatives_Render
from test_native_clock_tim import timer_native,_Compile,_OWNER


@pytest.mark.parametrize('scenario',['second-boot','late','masked','irq'])
def test_actual_timer_second_boot_is_quiesced_and_late_reinit_is_rejected(timer_native,tmp_path,scenario):
    _proof,_inventory,files=timer_native
    rendered,_replacements,_manifest=NativeClockTimDerivatives_Render(files,runtime=True)
    old=Path(__file__).resolve().parents[1]/'docs/evidence/native_classic_cdc_timer_20261010/final/HardwareGenerated/ReviewedNativeTime/Core/Src/stm32f4xx_hal_timebase_tim.c'
    inputs=[('original',old.read_text()),('fixed',rendered['HardwareGenerated/ReviewedNativeTime/Core/Src/stm32f4xx_hal_timebase_tim.c'].decode())]
    base=_OWNER[:_OWNER.index('int main(')]
    base=base.replace('static HAL_StatusTypeDef base_result=HAL_OK,start_result=HAL_OK;',
        'static HAL_StatusTypeDef base_result=HAL_OK,start_result=HAL_OK;\n'
        'static NativeClockResult clock_result=NativeClockResult_NotInitialized;\n'
        'static uint32_t mask,ipsr,faults;\n'
        'NativeClockResult NativeClock_StatusGet(void) { return clock_result; }\n'
        'uint32_t __get_IPSR(void) { return ipsr; }\n'
        'uint32_t __get_PRIMASK(void) { return mask; }\n'
        'void NativeRuntime_TransportFaultRecord(void) { faults++; }\n'
        'void HAL_NVIC_DisableIRQ(int irq) { assert(irq==25);enabled=0U; }\n'
        'void NVIC_ClearPendingIRQ(int irq) { assert(irq==25); }\n')
    base=base.replace('assert(handle==&htim1);return base_result;',
        'assert(handle==&htim1 && enabled==0U && TIM1->DIER==0U && TIM1->CR1==0U && TIM1->SR==0U);TIM1->SR=1U;return base_result;')
    base=base.replace('assert(handle==&htim1);return start_result;',
        'assert(handle==&htim1 && enabled==0U && TIM1->SR==0U);return start_result;')
    harness=base+'''int main(int argc,char **argv)
{
  assert(argc==2);enabled=1U;TIM1->DIER=1U;TIM1->CR1=1U;TIM1->SR=1U;
  pclk=16000000U;divider=RCC_HCLK_DIV1;
  assert(HAL_InitTick(15U)==HAL_OK && htim1.Init.Prescaler==15U && enabled==1U);
  pclk=84000000U;divider=RCC_HCLK_DIV2;
  assert(HAL_InitTick(15U)==HAL_OK && htim1.Init.Prescaler==167U && enabled==1U);
  if(strcmp(argv[1],"second-boot")==0) { assert(faults==0U);return 0; }
  if(strcmp(argv[1],"late")==0) { clock_result=NativeClockResult_Ok; }
  if(strcmp(argv[1],"masked")==0) { mask=1U; }
  if(strcmp(argv[1],"irq")==0) { ipsr=25U; }
  TIM1->CR1=1U;TIM1->DIER=1U;TIM1->SR=1U;
  assert(HAL_InitTick(15U)==HAL_ERROR && faults==1U && enabled==1U);
  assert(TIM1->CR1==1U && TIM1->DIER==1U && TIM1->SR==1U && htim1.Init.Prescaler==167U);
  return 0;
}'''
    declarations='void NativeRuntime_TransportFaultRecord(void);\nvoid HAL_NVIC_DisableIRQ(int irq);\nvoid NVIC_ClearPendingIRQ(int irq);\n'
    for label,text in inputs:
        a,_o,b=NativeC_FunctionSpanGet(text,'HAL_InitTick')
        exe=_Compile(tmp_path,declarations+text[a:b],harness,label)
        result=subprocess.run([str(exe),scenario],capture_output=True,text=True,timeout=15)
        (tmp_path/(label+'-run.json')).write_text(json.dumps({'command':[str(exe),scenario],
            'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr},indent=2))
        assert (result.returncode==0)==(label=='fixed'),result.stdout+result.stderr
