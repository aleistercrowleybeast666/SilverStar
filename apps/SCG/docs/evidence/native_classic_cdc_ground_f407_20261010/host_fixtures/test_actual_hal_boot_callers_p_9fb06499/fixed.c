#include <stdint.h>
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
HAL_StatusTypeDef HAL_Init(void)
{
  /* Configure Flash prefetch, Instruction cache, Data cache */ 
#if (INSTRUCTION_CACHE_ENABLE != 0U)
  __HAL_FLASH_INSTRUCTION_CACHE_ENABLE();
#endif /* INSTRUCTION_CACHE_ENABLE */

#if (DATA_CACHE_ENABLE != 0U)
  __HAL_FLASH_DATA_CACHE_ENABLE();
#endif /* DATA_CACHE_ENABLE */

#if (PREFETCH_ENABLE != 0U)
  __HAL_FLASH_PREFETCH_BUFFER_ENABLE();
#endif /* PREFETCH_ENABLE */

  /* Set Interrupt Group Priority */
  HAL_NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);

  /* Use systick as time base source and configure 1ms tick (default clock after Reset is HSI) */
  if (HAL_InitTick(TICK_INT_PRIORITY) != HAL_OK) { return HAL_ERROR; }

  /* Init the low level hardware */
  HAL_MspInit();

  /* Return function status */
  return HAL_OK;
}
HAL_StatusTypeDef HAL_RCC_ClockConfig(const RCC_ClkInitTypeDef  *RCC_ClkInitStruct, uint32_t FLatency)
{
  uint32_t tickstart;

  /* Check Null pointer */
  if (RCC_ClkInitStruct == NULL)
  {
    return HAL_ERROR;
  }

  /* Check the parameters */
  assert_param(IS_RCC_CLOCKTYPE(RCC_ClkInitStruct->ClockType));
  assert_param(IS_FLASH_LATENCY(FLatency));

  /* To correctly read data from FLASH memory, the number of wait states (LATENCY)
    must be correctly programmed according to the frequency of the CPU clock
    (HCLK) and the supply voltage of the device. */

  /* Increasing the number of wait states because of higher CPU frequency */
  if (FLatency > __HAL_FLASH_GET_LATENCY())
  {
    /* Program the new number of wait states to the LATENCY bits in the FLASH_ACR register */
    __HAL_FLASH_SET_LATENCY(FLatency);

    /* Check that the new number of wait states is taken into account to access the Flash
    memory by reading the FLASH_ACR register */
    if (__HAL_FLASH_GET_LATENCY() != FLatency)
    {
      return HAL_ERROR;
    }
  }

  /*-------------------------- HCLK Configuration --------------------------*/
  if (((RCC_ClkInitStruct->ClockType) & RCC_CLOCKTYPE_HCLK) == RCC_CLOCKTYPE_HCLK)
  {
    /* Set the highest APBx dividers in order to ensure that we do not go through
       a non-spec phase whatever we decrease or increase HCLK. */
    if (((RCC_ClkInitStruct->ClockType) & RCC_CLOCKTYPE_PCLK1) == RCC_CLOCKTYPE_PCLK1)
    {
      MODIFY_REG(RCC->CFGR, RCC_CFGR_PPRE1, RCC_HCLK_DIV16);
    }

    if (((RCC_ClkInitStruct->ClockType) & RCC_CLOCKTYPE_PCLK2) == RCC_CLOCKTYPE_PCLK2)
    {
      MODIFY_REG(RCC->CFGR, RCC_CFGR_PPRE2, (RCC_HCLK_DIV16 << 3));
    }

    assert_param(IS_RCC_HCLK(RCC_ClkInitStruct->AHBCLKDivider));
    MODIFY_REG(RCC->CFGR, RCC_CFGR_HPRE, RCC_ClkInitStruct->AHBCLKDivider);
  }

  /*------------------------- SYSCLK Configuration ---------------------------*/
  if (((RCC_ClkInitStruct->ClockType) & RCC_CLOCKTYPE_SYSCLK) == RCC_CLOCKTYPE_SYSCLK)
  {
    assert_param(IS_RCC_SYSCLKSOURCE(RCC_ClkInitStruct->SYSCLKSource));

    /* HSE is selected as System Clock Source */
    if (RCC_ClkInitStruct->SYSCLKSource == RCC_SYSCLKSOURCE_HSE)
    {
      /* Check the HSE ready flag */
      if (__HAL_RCC_GET_FLAG(RCC_FLAG_HSERDY) == RESET)
      {
        return HAL_ERROR;
      }
    }
    /* PLL is selected as System Clock Source */
    else if ((RCC_ClkInitStruct->SYSCLKSource == RCC_SYSCLKSOURCE_PLLCLK)   ||
             (RCC_ClkInitStruct->SYSCLKSource == RCC_SYSCLKSOURCE_PLLRCLK))
    {
      /* Check the PLL ready flag */
      if (__HAL_RCC_GET_FLAG(RCC_FLAG_PLLRDY) == RESET)
      {
        return HAL_ERROR;
      }
    }
    /* HSI is selected as System Clock Source */
    else
    {
      /* Check the HSI ready flag */
      if (__HAL_RCC_GET_FLAG(RCC_FLAG_HSIRDY) == RESET)
      {
        return HAL_ERROR;
      }
    }

    __HAL_RCC_SYSCLK_CONFIG(RCC_ClkInitStruct->SYSCLKSource);

    /* Get Start Tick */
    tickstart = HAL_GetTick();

    while (__HAL_RCC_GET_SYSCLK_SOURCE() != (RCC_ClkInitStruct->SYSCLKSource << RCC_CFGR_SWS_Pos))
    {
      if ((HAL_GetTick() - tickstart) > CLOCKSWITCH_TIMEOUT_VALUE)
      {
        return HAL_TIMEOUT;
      }
    }
  }

  /* Decreasing the number of wait states because of lower CPU frequency */
  if (FLatency < __HAL_FLASH_GET_LATENCY())
  {
    /* Program the new number of wait states to the LATENCY bits in the FLASH_ACR register */
    __HAL_FLASH_SET_LATENCY(FLatency);

    /* Check that the new number of wait states is taken into account to access the Flash
    memory by reading the FLASH_ACR register */
    if (__HAL_FLASH_GET_LATENCY() != FLatency)
    {
      return HAL_ERROR;
    }
  }

  /*-------------------------- PCLK1 Configuration ---------------------------*/
  if (((RCC_ClkInitStruct->ClockType) & RCC_CLOCKTYPE_PCLK1) == RCC_CLOCKTYPE_PCLK1)
  {
    assert_param(IS_RCC_PCLK(RCC_ClkInitStruct->APB1CLKDivider));
    MODIFY_REG(RCC->CFGR, RCC_CFGR_PPRE1, RCC_ClkInitStruct->APB1CLKDivider);
  }

  /*-------------------------- PCLK2 Configuration ---------------------------*/
  if (((RCC_ClkInitStruct->ClockType) & RCC_CLOCKTYPE_PCLK2) == RCC_CLOCKTYPE_PCLK2)
  {
    assert_param(IS_RCC_PCLK(RCC_ClkInitStruct->APB2CLKDivider));
    MODIFY_REG(RCC->CFGR, RCC_CFGR_PPRE2, ((RCC_ClkInitStruct->APB2CLKDivider) << 3U));
  }

  /* Update the SystemCoreClock global variable */
  SystemCoreClock = HAL_RCC_GetSysClockFreq() >> AHBPrescTable[(RCC->CFGR & RCC_CFGR_HPRE) >> RCC_CFGR_HPRE_Pos];

  /* Configure the source of time base considering new system clocks settings */
  if (HAL_InitTick(uwTickPrio) != HAL_OK) { return HAL_ERROR; }

  return HAL_OK;
}
int main(int argc,char **argv)
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
