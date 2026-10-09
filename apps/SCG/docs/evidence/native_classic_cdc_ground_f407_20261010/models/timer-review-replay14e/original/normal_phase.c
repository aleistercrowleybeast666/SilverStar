#include "main.h"
#include "native_clock.h"
#include "platform_time.h"
#include "platform_critical.h"
#include <assert.h>
#include <stdio.h>
TimerRegisters timer_registers={.CR1=1U,.ARR=999U,.PSC=167U,.DIER=1U,.CNT=123U};
TIM_HandleTypeDef htim1={.Instance=TIM1,.State=HAL_TIM_STATE_BUSY};
uint32_t SystemCoreClock=168000000U,uwTickPrio;
static uint32_t tick=9U,mask,sub_us;
uint32_t HAL_RCC_GetPCLK2Freq(void) { return 84000000U; }
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *config,uint32_t *latency) { config->APB2CLKDivider=RCC_HCLK_DIV2;*latency=0U; }
uint32_t HAL_RCC_GetHCLKFreq(void) { return SystemCoreClock; }
uint32_t HAL_GetTickFreq(void) { return 1U; }
uint32_t HAL_GetTick(void) { return tick; }
uint32_t __get_IPSR(void) { return 0U; }
uint32_t __get_PRIMASK(void) { return mask; }
uint32_t NVIC_GetEnableIRQ(int irq) { assert(irq==25);return 1U; }
PlatformCriticalState PlatformCritical_Enter(void) { uint32_t saved=mask;mask=1U;return saved; }
/* A running 1MHz counter: each ordinary snapshot consumes 0.2us.
   This is a valid timing model, not a measured STM32 latency claim. */
void PlatformCritical_Exit(PlatformCriticalState saved) { mask=saved;sub_us++;if(sub_us==5U){sub_us=0U;TIM1->CNT++;if(TIM1->CNT==1000U){TIM1->CNT=0U;tick++;}} }
int main(void) {
 uint64_t now=0U;
 assert(PlatformTime_Init()==PLATFORM_OK);
 assert(NativeClock_Read(&now)==NativeClockResult_Ok);
 /* Ordinary update completed and IRQ retired; CNT=0 for first microsecond. */
 tick++;TIM1->CNT=0U;TIM1->SR=0U;sub_us=0U;
 NativeClockResult first=NativeClock_Read(&now);
 TIM1->CNT=10U;
 NativeClockResult later=NativeClock_Read(&now);
 printf("running timer, UIF=0, first=%u later=%u status=%u retries_us=0.6\n",(unsigned)first,(unsigned)later,(unsigned)NativeClock_StatusGet());
 assert(first==NativeClockResult_UnstableSnapshot);
 assert(later==NativeClockResult_UnstableSnapshot);
 return 0;
}
