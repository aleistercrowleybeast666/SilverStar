#include "native_clock.h"
#include "platform_time.h"
#include "silverstar_assert.h"
#include <stddef.h>

static NativeClockResult s_clock_result = NativeClockResult_NotInitialized;
static uint32_t s_last_tick;
static uint64_t s_total_ms;
static uint64_t s_last_us;

NativeClockResult NativeClock_StatusGet(void) { return s_clock_result; }

void NativeClock_FaultRecord(NativeClockResult reason)
{
    if ((reason != NativeClockResult_Ok) &&
        (s_clock_result == NativeClockResult_Ok)) { s_clock_result = reason; }
}

static NativeClockResult NativeClock_Update(const NativeClockSnapshot *sample)
{
    uint32_t delta = sample->tick_ms - s_last_tick;
    uint64_t next;
    SILVERSTAR_ASSERT(s_last_us / 1000ULL == s_total_ms,
        SILVERSTAR_ASSERT_MODULE_GENERATED, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_total_ms <= (UINT64_MAX / 1000ULL - 10000ULL),
        SILVERSTAR_ASSERT_MODULE_GENERATED, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if ((delta > 10000U) || (sample->elapsed_cycles >= NATIVE_CLOCK_HCLK_HZ / 1000U))
    { return NativeClockResult_Discontinuous; }
    next = (s_total_ms + delta) * 1000ULL +
        sample->elapsed_cycles / NATIVE_CLOCK_CYCLES_PER_US;
    if (next < s_last_us) { return NativeClockResult_Discontinuous; }
    s_total_ms += delta;
    s_last_tick = sample->tick_ms;
    s_last_us = next;
    return NativeClockResult_Ok;
}

NativeClockResult NativeClock_Read(uint64_t *now_us)
{
    NativeClockSnapshot sample;
    NativeClockResult result;
    if (now_us == NULL) { return NativeClockResult_InvalidArgument; }
    if (s_clock_result != NativeClockResult_Ok) { return s_clock_result; }
    result = NativeClockPort_SnapshotGet(&sample);
    if (result == NativeClockResult_Ok) { result = NativeClock_Update(&sample); }
    if (result != NativeClockResult_Ok)
    { NativeClock_FaultRecord(result); return result; }
    *now_us = s_last_us;
    return NativeClockResult_Ok;
}

NativeClockResult NativeClock_DelayUs(uint32_t delay_us)
{
    uint64_t start;
    uint64_t now;
    uint32_t poll;
    NativeClockResult result;
    if (delay_us > NATIVE_CLOCK_DELAY_LIMIT_US)
    { return NativeClockResult_InvalidArgument; }
    result = NativeClock_Read(&start);
    if (result != NativeClockResult_Ok) { return result; }
    for (poll = 0U; poll < NATIVE_CLOCK_POLL_LIMIT; poll++)
    {
        result = NativeClock_Read(&now);
        if (result != NativeClockResult_Ok) { return result; }
        if (now - start >= delay_us) { return NativeClockResult_Ok; }
    }
    NativeClock_FaultRecord(NativeClockResult_Stopped);
    return NativeClockResult_Stopped;
}

PlatformResult PlatformTime_Init(void)
{
    NativeClockSnapshot sample;
    NativeClockResult result;
    if (s_clock_result == NativeClockResult_Ok) { return PLATFORM_ALREADY_INITIALIZED; }
    if (s_clock_result != NativeClockResult_NotInitialized) { return PLATFORM_NOT_READY; }
    result = NativeClockPort_SnapshotGet(&sample);
    if (result != NativeClockResult_Ok) { s_clock_result = result; return PLATFORM_NOT_READY; }
    if (sample.elapsed_cycles >= NATIVE_CLOCK_HCLK_HZ / 1000U)
    { s_clock_result = NativeClockResult_InvalidConfiguration; return PLATFORM_NOT_READY; }
    s_last_tick = sample.tick_ms;
    s_total_ms = sample.tick_ms;
    s_last_us = s_total_ms * 1000ULL + sample.elapsed_cycles / NATIVE_CLOCK_CYCLES_PER_US;
    s_clock_result = NativeClockResult_Ok;
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok) { return PLATFORM_NOT_READY; }
    return PLATFORM_OK;
}

uint64_t PlatformTime_Us(void)
{
    uint64_t now = s_last_us;
    NativeClockResult result = NativeClock_Read(&now);
    if (result != NativeClockResult_Ok) { NativeClock_FaultRecord(result); }
    return now;
}

uint32_t PlatformTime_Ms(void) { return (uint32_t)(PlatformTime_Us() / 1000ULL); }

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    NativeClockResult result;
    if (delay_ms > NATIVE_CLOCK_DELAY_LIMIT_US / 1000U)
    { NativeClock_FaultRecord(NativeClockResult_InvalidArgument); return; }
    result = NativeClock_DelayUs(delay_ms * 1000U);
    if (result != NativeClockResult_Ok) { NativeClock_FaultRecord(result); }
}
