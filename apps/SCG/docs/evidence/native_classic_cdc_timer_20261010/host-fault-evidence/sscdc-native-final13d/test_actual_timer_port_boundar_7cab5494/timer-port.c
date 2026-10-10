#include "main.h"
#include "native_clock.h"
#include "platform_critical.h"
#include <assert.h>
#include <string.h>
#include "native_clock.h"
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
    TIM1->PSC=83U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->PSC=167U;
    TIM1->ARR=1000U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->ARR=999U;
    TIM1->DIER=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);TIM1->DIER=1U;
    enabled=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_InvalidConfiguration);enabled=1U;
    TIM1->CNT=0U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot);
    TIM1->CNT=1000U;assert(NativeClockPort_SnapshotGet(&sample)==NativeClockResult_UnstableSnapshot);
    return 0;
}
