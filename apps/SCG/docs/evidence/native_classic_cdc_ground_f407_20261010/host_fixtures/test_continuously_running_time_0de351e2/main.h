#ifndef TEST_NATIVE_MAIN_H
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
