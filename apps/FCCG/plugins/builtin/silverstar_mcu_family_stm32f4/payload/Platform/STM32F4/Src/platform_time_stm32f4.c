#include "platform_time.h"

#include "platform_critical.h"
#include "platform_stm32f4_resources.h"
#include "silverstar_assert.h"
#include "stm32f4xx_hal.h"

static PlatformStm32f4TimeResource s_timebase;
static uint8_t s_initialized;
static uint32_t s_last_tick_ms;
static uint64_t s_tick_epoch_ms;
static uint64_t s_last_monotonic_us;

PlatformResult PlatformTime_Init(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();

    s_initialized = 0U;
    s_last_tick_ms = 0U;
    s_tick_epoch_ms = 0ULL;
    s_last_monotonic_us = 0ULL;
    if (PlatformStm32f4Resource_TimeGet(PLATFORM_TIME_1, &s_timebase) == 0U)
    {
        PlatformCritical_Exit(state);
        return PLATFORM_INVALID_ARGUMENT;
    }
    if ((s_timebase.handle == NULL) ||
        (s_timebase.counter_frequency_hz != 1000000U) ||
        (s_timebase.period_counts != 1000U) ||
        (s_timebase.tick_frequency_hz != 1000U))
    {
        PlatformCritical_Exit(state);
        return PLATFORM_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT(s_timebase.handle != NULL,
                      SILVERSTAR_ASSERT_MODULE_PLATFORM,
                      SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(
        (s_timebase.counter_frequency_hz == 1000000U) &&
            (s_timebase.period_counts == 1000U) &&
            (s_timebase.tick_frequency_hz == 1000U),
        SILVERSTAR_ASSERT_MODULE_PLATFORM,
        SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

uint32_t PlatformTime_Ms(void)
{
    return HAL_GetTick();
}

uint64_t PlatformTime_Us(void)
{
    PlatformCriticalState state;
    TIM_HandleTypeDef *timebase;
    uint32_t tick_ms;
    uint32_t counter;
    uint32_t counter_us = 0U;
    uint8_t update_pending = 0U;
    uint64_t timestamp_us;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_PLATFORM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    state = PlatformCritical_Enter();
    timebase = (TIM_HandleTypeDef *)s_timebase.handle;
    tick_ms = HAL_GetTick();
    if ((timebase != NULL) && (timebase->Instance != NULL))
    {
        counter = __HAL_TIM_GET_COUNTER(timebase);
        counter_us = (uint32_t)(((uint64_t)counter * 1000000ULL) /
                                s_timebase.counter_frequency_hz);
        if (__HAL_TIM_GET_FLAG(timebase, TIM_FLAG_UPDATE) != RESET)
        {
            update_pending = 1U;
            counter = __HAL_TIM_GET_COUNTER(timebase);
            counter_us = (uint32_t)(((uint64_t)counter * 1000000ULL) /
                                    s_timebase.counter_frequency_hz);
        }
    }
    if (update_pending != 0U)
    {
        tick_ms++;
    }
    if (s_initialized == 0U)
    {
        s_initialized = 1U;
        s_last_tick_ms = tick_ms;
    }
    else if (tick_ms < s_last_tick_ms)
    {
        s_tick_epoch_ms += (1ULL << 32);
    }
    s_last_tick_ms = tick_ms;
    timestamp_us = ((s_tick_epoch_ms + tick_ms) * 1000ULL) + counter_us;
    if (timestamp_us < s_last_monotonic_us)
    {
        timestamp_us = s_last_monotonic_us;
    }
    SILVERSTAR_ASSERT(timestamp_us >= s_last_monotonic_us,
                      SILVERSTAR_ASSERT_MODULE_PLATFORM,
                      SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    s_last_monotonic_us = timestamp_us;
    PlatformCritical_Exit(state);
    return timestamp_us;
}

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    HAL_Delay(delay_ms);
}
