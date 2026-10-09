#include "main.h"
#include "native_clock.h"
#include "platform_critical.h"
#include <assert.h>
#include <string.h>
void NativeRuntime_TransportFaultRecord(void);
void HAL_NVIC_DisableIRQ(int irq);
void NVIC_ClearPendingIRQ(int irq);
HAL_StatusTypeDef HAL_InitTick(uint32_t TickPriority)
{
  /* Only the two stock boot clock phases may configure this timer. Once the
   * time owner initializes, reconfiguration is a latched internal fault. */
  if ((__get_IPSR() != 0U) || (__get_PRIMASK() != 0U) ||
      (NativeClock_StatusGet() != NativeClockResult_NotInitialized))
  { NativeRuntime_TransportFaultRecord(); return HAL_ERROR; }

  if (TickPriority >= (1UL << __NVIC_PRIO_BITS)) { return HAL_ERROR; }

  RCC_ClkInitTypeDef    clkconfig;
  uint32_t              uwTimclock = 0U;

  uint32_t              uwPrescalerValue = 0U;
  uint32_t              pFLatency;

  HAL_StatusTypeDef     status;

  /* Enable TIM1 clock */
  __HAL_RCC_TIM1_CLK_ENABLE();

  /* Get clock configuration */
  HAL_RCC_GetClockConfig(&clkconfig, &pFLatency);

  /* Compute TIM1 clock */
      if ((clkconfig.APB2CLKDivider != RCC_HCLK_DIV1) &&
      (clkconfig.APB2CLKDivider != RCC_HCLK_DIV2)) { return HAL_ERROR; }
  uwTimclock = HAL_RCC_GetPCLK2Freq();
  if ((uwTimclock == 0U) || (uwTimclock > 100000000U)) { return HAL_ERROR; }
  if (clkconfig.APB2CLKDivider != RCC_HCLK_DIV1) { uwTimclock *= 2U; }
  if ((uwTimclock < 1000000U) || ((uwTimclock % 1000000U) != 0U)) { return HAL_ERROR; }

  /* Compute the prescaler value to have TIM1 counter clock equal to 1MHz */
  uwPrescalerValue = (uint32_t) ((uwTimclock / 1000000U) - 1U);

  /* Quiesce the sole shared-vector owner before replacing its boot setup. */
  HAL_NVIC_DisableIRQ(TIM1_UP_TIM10_IRQn);
  TIM1->DIER = 0U;
  TIM1->CR1 = 0U;
  TIM1->SR = 0U;
  NVIC_ClearPendingIRQ(TIM1_UP_TIM10_IRQn);
  /* Initialize TIM1 */
  htim1.Instance = TIM1;

  /* Initialize TIMx peripheral as follow:
   * Period = [(TIM1CLK/1000) - 1]. to have a (1/1000) s time base.
   * Prescaler = (uwTimclock/1000000 - 1) to have a 1MHz counter clock.
   * ClockDivision = 0
   * Counter direction = Up
   */
  htim1.Init.Period = (1000000U / 1000U) - 1U;
  htim1.Init.Prescaler = uwPrescalerValue;
  htim1.Init.ClockDivision = 0;
  htim1.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim1.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;

  status = HAL_TIM_Base_Init(&htim1);
  if (status == HAL_OK)
  {
    TIM1->SR = 0U;
    NVIC_ClearPendingIRQ(TIM1_UP_TIM10_IRQn);
    /* Start the TIM time Base generation in interrupt mode */
    status = HAL_TIM_Base_Start_IT(&htim1);
    if (status == HAL_OK)
    {
    /* Enable the TIM1 global Interrupt */
        
      /* Configure the SysTick IRQ priority */
      if (TickPriority < (1UL << __NVIC_PRIO_BITS))
      {
        /* Configure the TIM IRQ priority */
        HAL_NVIC_SetPriority(TIM1_UP_TIM10_IRQn, TickPriority, 0U);
        uwTickPrio = TickPriority;
        HAL_NVIC_EnableIRQ(TIM1_UP_TIM10_IRQn);
      }
      else
      {
        status = HAL_ERROR;
      }
    }
  }

 /* Return function status */
  return status;
}
TimerRegisters timer_registers;
TIM_HandleTypeDef htim1;
uint32_t SystemCoreClock=168000000U,uwTickPrio;
static uint32_t pclk=84000000U,divider=RCC_HCLK_DIV2,enabled,priority_set,irq_calls;
static HAL_StatusTypeDef base_result=HAL_OK,start_result=HAL_OK;
static NativeClockResult clock_result=NativeClockResult_NotInitialized;
static uint32_t mask,ipsr,faults;
NativeClockResult NativeClock_StatusGet(void) { return clock_result; }
uint32_t __get_IPSR(void) { return ipsr; }
uint32_t __get_PRIMASK(void) { return mask; }
void NativeRuntime_TransportFaultRecord(void) { faults++; }
void HAL_NVIC_DisableIRQ(int irq) { assert(irq==25);enabled=0U; }
void NVIC_ClearPendingIRQ(int irq) { assert(irq==25); }

uint32_t HAL_RCC_GetPCLK2Freq(void) { return pclk; }
void HAL_RCC_GetClockConfig(RCC_ClkInitTypeDef *config,uint32_t *latency) { config->APB2CLKDivider=divider;*latency=0U; }
HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef *handle) { assert(handle==&htim1 && enabled==0U && TIM1->DIER==0U && TIM1->CR1==0U && TIM1->SR==0U);TIM1->SR=1U;return base_result; }
HAL_StatusTypeDef HAL_TIM_Base_Start_IT(TIM_HandleTypeDef *handle) { assert(handle==&htim1 && enabled==0U && TIM1->SR==0U);return start_result; }
void HAL_NVIC_EnableIRQ(int irq) { assert(irq==25);enabled++; }
void HAL_NVIC_SetPriority(int irq,uint32_t priority,uint32_t sub) { assert(irq==25 && priority<16U && sub==0U);priority_set++; }
void HAL_TIM_IRQHandler(TIM_HandleTypeDef *handle) { assert(handle==&htim1);irq_calls++; }
int main(int argc,char **argv)
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
}