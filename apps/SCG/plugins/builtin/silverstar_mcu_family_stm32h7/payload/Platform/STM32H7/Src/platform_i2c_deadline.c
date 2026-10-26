#include "platform_i2c_deadline.h"

#include <stddef.h>

#include "silverstar_assert.h"
#include "stm32h7xx_hal.h"

/* Cortex-M3 CYCCNT advances with the core clock even in the vendor's brief
 * IRQ-masked last-three-byte receive sequence. TIM6/HAL tick alone cannot
 * measure that sequence. Do not reset a shared cycle counter or enable output
 * tracing; set only the counter's trace gate and CYCCNT enable bit.
 * Cut polling at 90% nominal cycles to allow a slower HSI and cleanup. This
 * arithmetic is not a RET6 wall-time/WCET measurement. IRQ/preemption and
 * cleanup bounds remain hardware/manual acceptance requirements. */
PlatformI2cDeadlineResult PlatformI2cDeadline_Start(
    PlatformI2cDeadline *deadline, uint32_t timeout_ms)
{
    uint32_t clock_hz;
    uint32_t before;

    if ((deadline == NULL) || (timeout_ms == 0U) || (timeout_ms > 1000U))
    { return PlatformI2cDeadlineResult_InvalidArgument; }
    SILVERSTAR_ASSERT(deadline->active == 0U,
        SILVERSTAR_ASSERT_MODULE_PLATFORM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    deadline->active = 0U;
    clock_hz = HAL_RCC_GetHCLKFreq();
    if ((clock_hz < 1000000U) || (clock_hz > 72000000U))
    { return PlatformI2cDeadlineResult_Unavailable; }
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    before = DWT->CYCCNT;
    __DSB();
    __NOP();
    __NOP();
    if (((DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) == 0U) ||
        (DWT->CYCCNT == before))
    { return PlatformI2cDeadlineResult_Unavailable; }
    deadline->budget_cycles = (uint32_t)(
        ((uint64_t)clock_hz * timeout_ms * 9U) / 10000U);
    deadline->start_cycles = before;
    deadline->active = 1U;
    return PlatformI2cDeadlineResult_Ok;
}

uint8_t PlatformI2cDeadline_Expired(const PlatformI2cDeadline *deadline)
{
    if (deadline == NULL) { return 1U; }
    SILVERSTAR_ASSERT((deadline->active == 1U) && (deadline->budget_cycles > 0U),
        SILVERSTAR_ASSERT_MODULE_PLATFORM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (
        ((CoreDebug->DEMCR & CoreDebug_DEMCR_TRCENA_Msk) == 0U) ||
        ((DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) == 0U))
    { return 1U; }
    return ((uint32_t)(DWT->CYCCNT - deadline->start_cycles) >=
            deadline->budget_cycles) ? 1U : 0U;
}
