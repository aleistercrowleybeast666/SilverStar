#include "timing_bench.h"

#include <stddef.h>
#include <string.h>

static TimingBenchResult TimingBench_Reject(TimingBenchSlot *slot, TimingBenchResult result)
{
    if (slot->stats.rejected != UINT32_MAX) {
        slot->stats.rejected++;
    } else {
        slot->stats.saturated = 1U;
    }
    return result;
}

TimingBenchResult TimingBench_ContextValidate(uint32_t exception, TimingBenchInterval interval)
{
    if ((uint32_t)interval >= (uint32_t)TIMING_BENCH_COUNT) {
        return TIMING_BENCH_BAD_PARAM;
    }
    if ((exception > 0U) && (exception < 16U)) {
        return TIMING_BENCH_BAD_OWNER;
    }
    if (((exception != 0U) ? 1U : 0U) != ((interval == TIMING_BENCH_ISR) ? 1U : 0U)) {
        return TIMING_BENCH_BAD_OWNER;
    }
    return TIMING_BENCH_OK;
}

TimingBenchResult TimingBench_Initialize(TimingBenchContext *context, uint32_t clock_hz)
{
    if ((context == NULL) || (clock_hz < 1000000U) ||
        (clock_hz > TIMING_BENCH_MAX_CLOCK_HZ)) {
        return TIMING_BENCH_BAD_PARAM;
    }
    if (context->clock_hz != 0U) {
        return TIMING_BENCH_BUSY;
    }
    (void)memset(context, 0, sizeof(*context));
    context->clock_hz = clock_hz;
    return TIMING_BENCH_OK;
}

TimingBenchResult TimingBench_Begin(TimingBenchContext *context, TimingBenchInterval interval,
    uint32_t owner, const TimingBenchStamp *stamp, TimingBenchTicket *ticket)
{
    TimingBenchSlot *slot;
    if ((context == NULL) || (stamp == NULL) || (ticket == NULL) ||
        ((uint32_t)interval >= (uint32_t)TIMING_BENCH_COUNT) || (owner == 0U)) {
        return TIMING_BENCH_BAD_PARAM;
    }
    if (context->clock_hz == 0U) {
        return TIMING_BENCH_NOT_READY;
    }
    slot = &context->slot[interval];
    if (slot->active != 0U) {
        return TimingBench_Reject(slot, TIMING_BENCH_BUSY);
    }
    if (stamp->clock_hz != context->clock_hz) {
        return TimingBench_Reject(slot, TIMING_BENCH_CLOCK_INVALID);
    }
    if (context->next_serial == UINT32_MAX) {
        slot->stats.saturated = 1U;
        return TimingBench_Reject(slot, TIMING_BENCH_SATURATED);
    }
    context->next_serial++;
    slot->serial = context->next_serial;
    slot->owner = owner;
    slot->begin = *stamp;
    slot->active = 1U;
    ticket->serial = slot->serial;
    ticket->owner = owner;
    ticket->interval = interval;
    return TIMING_BENCH_OK;
}

static TimingBenchResult TimingBench_DurationGet(const TimingBenchContext *context,
    const TimingBenchSlot *slot, const TimingBenchStamp *stamp, uint32_t *cycles)
{
    uint64_t elapsed_us;
    uint64_t expected;
    uint64_t tolerance;
    uint64_t difference;
    if ((stamp->clock_hz != context->clock_hz) ||
        (stamp->monotonic_us < slot->begin.monotonic_us)) {
        return TIMING_BENCH_CLOCK_INVALID;
    }
    elapsed_us = stamp->monotonic_us - slot->begin.monotonic_us;
    if (elapsed_us > TIMING_BENCH_MAX_SPAN_US) {
        return TIMING_BENCH_CLOCK_INVALID;
    }
    /* 5 seconds * 180 MHz < 2^32: modulo subtraction cannot conceal two wraps. */
    *cycles = stamp->cycles - slot->begin.cycles;
    expected = (elapsed_us * context->clock_hz) / 1000000U;
    tolerance = ((uint64_t)TIMING_BENCH_CLOCK_TOLERANCE_US * context->clock_hz) / 1000000U;
    difference = (*cycles > expected) ? (*cycles - expected) : (expected - *cycles);
    if ((*cycles == 0U) || (difference > tolerance)) {
        return TIMING_BENCH_CLOCK_INVALID;
    }
    return TIMING_BENCH_OK;
}

TimingBenchResult TimingBench_End(TimingBenchContext *context, uint32_t owner,
    const TimingBenchStamp *stamp, const TimingBenchTicket *ticket)
{
    TimingBenchSlot *slot;
    TimingBenchResult result;
    uint32_t cycles = 0U;
    if ((context == NULL) || (stamp == NULL) || (ticket == NULL) || (owner == 0U) ||
        ((uint32_t)ticket->interval >= (uint32_t)TIMING_BENCH_COUNT)) {
        return TIMING_BENCH_BAD_PARAM;
    }
    slot = &context->slot[ticket->interval];
    if ((slot->active == 0U) || (ticket->serial != slot->serial)) {
        return TimingBench_Reject(slot, TIMING_BENCH_STALE_TICKET);
    }
    if ((owner != slot->owner) || (ticket->owner != owner)) {
        return TimingBench_Reject(slot, TIMING_BENCH_BAD_OWNER);
    }
    slot->active = 0U;
    result = TimingBench_DurationGet(context, slot, stamp, &cycles);
    if (result != TIMING_BENCH_OK) {
        return TimingBench_Reject(slot, result);
    }
    if ((slot->stats.completed == UINT32_MAX) ||
        (slot->stats.total_cycles > UINT64_MAX - cycles)) {
        slot->stats.saturated = 1U;
        return TimingBench_Reject(slot, TIMING_BENCH_SATURATED);
    }
    if ((slot->stats.completed == 0U) || (cycles < slot->stats.minimum_cycles)) {
        slot->stats.minimum_cycles = cycles;
    }
    if (cycles > slot->stats.maximum_cycles) {
        slot->stats.maximum_cycles = cycles;
    }
    slot->stats.last_cycles = cycles;
    slot->stats.total_cycles += cycles;
    slot->stats.completed++;
    return TIMING_BENCH_OK;
}
