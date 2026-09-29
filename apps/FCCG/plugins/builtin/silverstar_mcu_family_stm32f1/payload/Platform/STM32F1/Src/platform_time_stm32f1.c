#include "platform_time.h"

#include "platform_critical.h"
#include "stm32f1xx_hal.h"

#define PLATFORM_TIME_US_PER_MS 1000ULL
#define PLATFORM_TIME_TICK_WRAP  (1ULL << 32)

static uint32_t s_last_tick_ms;
static uint64_t s_tick_epoch_ms;
static uint8_t s_tick_seen;

PlatformResult PlatformTime_Init(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    s_last_tick_ms = HAL_GetTick();
    s_tick_epoch_ms = 0ULL;
    s_tick_seen = 1U;
    PlatformCritical_Exit(state);
    return PLATFORM_OK;
}

uint32_t PlatformTime_Ms(void)
{
    return HAL_GetTick();
}

uint64_t PlatformTime_Us(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    uint32_t tick_ms = HAL_GetTick();
    uint64_t result;

    if (s_tick_seen == 0U)
    {
        s_tick_seen = 1U;
    }
    else if (tick_ms < s_last_tick_ms)
    {
        s_tick_epoch_ms += PLATFORM_TIME_TICK_WRAP;
    }
    s_last_tick_ms = tick_ms;
    /* F103 Ground exposes a monotonic millisecond clock with microsecond units. */
    result = (s_tick_epoch_ms + tick_ms) * PLATFORM_TIME_US_PER_MS;
    PlatformCritical_Exit(state);
    return result;
}

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    HAL_Delay(delay_ms);
}
