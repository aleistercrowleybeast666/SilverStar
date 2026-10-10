#include "native_clock.h"
#include "platform_critical.h"
#include "main.h"

uint8_t NativeClock_ContextAllowedGet(void)
{
    return ((__get_IPSR() == 0U) && (__get_PRIMASK() == 0U)) ? 1U : 0U;
}
#include <stddef.h>

NativeClockResult NativeClockPort_SnapshotGet(NativeClockSnapshot *snapshot)
{
    uint32_t attempt;
    uint32_t control;
    uint32_t reload;
    if (snapshot == NULL) { return NativeClockResult_InvalidArgument; }
    if ((__get_IPSR() != 0U) || (__get_PRIMASK() != 0U))
    { return NativeClockResult_InvalidContext; }
    control = SysTick->CTRL;
    reload = SysTick->LOAD;
    if ((SystemCoreClock != NATIVE_CLOCK_HCLK_HZ) ||
        (HAL_RCC_GetHCLKFreq() != NATIVE_CLOCK_HCLK_HZ) ||
        (HAL_GetTickFreq() != HAL_TICK_FREQ_1KHZ) ||
        ((control & (SysTick_CTRL_ENABLE_Msk | SysTick_CTRL_TICKINT_Msk |
          SysTick_CTRL_CLKSOURCE_Msk)) != (SysTick_CTRL_ENABLE_Msk |
          SysTick_CTRL_TICKINT_Msk | SysTick_CTRL_CLKSOURCE_Msk)) ||
        (reload != (NATIVE_CLOCK_HCLK_HZ / 1000U - 1U)))
    { return NativeClockResult_InvalidConfiguration; }
    for (attempt = 0U; attempt < 3U; attempt++)
    {
        PlatformCriticalState saved = PlatformCritical_Enter();
        uint32_t pending_before = SCB->ICSR & SCB_ICSR_PENDSTSET_Msk;
        uint32_t tick = HAL_GetTick();
        uint32_t counter = SysTick->VAL;
        uint32_t pending_after = SCB->ICSR & SCB_ICSR_PENDSTSET_Msk;
        PlatformCritical_Exit(saved);
        /* VAL zero is the wrap/reload boundary; do not publish that sample.
         * The bounded critical section contains only the recognized HAL tick
         * read and register samples. Division happens after PRIMASK restore. */
        if ((pending_before == pending_after) && (counter != 0U) &&
            (counter <= reload))
        {
            snapshot->tick_ms = tick + ((pending_before != 0U) ? 1U : 0U);
            snapshot->elapsed_cycles = reload - counter;
            return NativeClockResult_Ok;
        }
    }
    return NativeClockResult_UnstableSnapshot;
}
