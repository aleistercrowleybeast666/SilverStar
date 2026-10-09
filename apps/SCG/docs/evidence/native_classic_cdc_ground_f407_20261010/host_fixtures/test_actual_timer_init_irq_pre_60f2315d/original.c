#include "main.h"
#include "native_clock.h"
#include "platform_critical.h"
#include <assert.h>
#include <string.h>
HAL_StatusTypeDef HAL_InitTick(uint32_t TickPriority)
{
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
      uwTimclock = 2*HAL_RCC_GetPCLK2Freq();

  /* Compute the prescaler value to have TIM1 counter clock equal to 1MHz */
  uwPrescalerValue = (uint32_t) ((uwTimclock / 1000000U) - 1U);

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
    /* Start the TIM time Base generation in interrupt mode */
    status = HAL_TIM_Base_Start_IT(&htim1);
    if (status == HAL_OK)
    {
    /* Enable the TIM1 global Interrupt */
        HAL_NVIC_EnableIRQ(TIM1_UP_TIM10_IRQn);
      /* Configure the SysTick IRQ priority */
      if (TickPriority < (1UL << __NVIC_PRIO_BITS))
      {
        /* Configure the TIM IRQ priority */
        HAL_NVIC_SetPriority(TIM1_UP_TIM10_IRQn, TickPriority, 0U);
        uwTickPrio = TickPriority;
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
void TIM1_UP_TIM10_IRQHandler(void)
{
  /* USER CODE BEGIN TIM1_UP_TIM10_IRQn 0 */

  /* USER CODE END TIM1_UP_TIM10_IRQn 0 */
  /* USER CODE BEGIN TIM1_UP_TIM10_IRQn 1 */

  /* USER CODE END TIM1_UP_TIM10_IRQn 1 */
}

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
