#ifndef __TIMING_BENCH_H
#define __TIMING_BENCH_H

#include <stdint.h>

#define TIMING_BENCH_MAX_SPAN_US 5000000U
#define TIMING_BENCH_CLOCK_TOLERANCE_US 10U
#define TIMING_BENCH_MAX_CLOCK_HZ 180000000U

typedef enum
{
    TIMING_BENCH_INS = 0U,
    TIMING_BENCH_ESTIMATOR,
    TIMING_BENCH_LOGGER,
    TIMING_BENCH_ISR,
    TIMING_BENCH_COUNT
} TimingBenchInterval;

typedef enum
{
    TIMING_BENCH_OK = 0U,
    TIMING_BENCH_BAD_PARAM,
    TIMING_BENCH_NOT_READY,
    TIMING_BENCH_BUSY,
    TIMING_BENCH_BAD_OWNER,
    TIMING_BENCH_STALE_TICKET,
    TIMING_BENCH_CLOCK_INVALID,
    TIMING_BENCH_SATURATED,
    TIMING_BENCH_PARTIAL
} TimingBenchResult;

typedef struct
{
    uint64_t monotonic_us;
    uint32_t cycles;
    uint32_t clock_hz;
} TimingBenchStamp;

typedef struct
{
    uint64_t total_cycles;
    uint32_t completed;
    uint32_t rejected;
    uint32_t minimum_cycles;
    uint32_t maximum_cycles;
    uint32_t last_cycles;
    uint8_t saturated;
} TimingBenchStats;

typedef struct
{
    uint32_t serial;
    uint32_t owner;
    TimingBenchInterval interval;
} TimingBenchTicket;

typedef struct
{
    TimingBenchStamp begin;
    TimingBenchStats stats;
    uint32_t serial;
    uint32_t owner;
    uint8_t active;
} TimingBenchSlot;

/* Zero-initialized, caller-owned context; initialize once per session.
 * Reinitialization is rejected, so a ticket from an old session cannot alias.
 * No heap, no hidden global state in the portable core.
 * Its owner must serialize every access; the F407 adapter uses PRIMASK. */
typedef struct
{
    TimingBenchSlot slot[TIMING_BENCH_COUNT];
    uint32_t next_serial;
    uint32_t clock_hz;
} TimingBenchContext;

TimingBenchResult TimingBench_Initialize(TimingBenchContext *context, uint32_t clock_hz);
/* Only normal tasks and maskable peripheral IRQs are valid bench owners. */
TimingBenchResult TimingBench_ContextValidate(uint32_t exception, TimingBenchInterval interval);
TimingBenchResult TimingBench_Begin(TimingBenchContext *context, TimingBenchInterval interval,
    uint32_t owner, const TimingBenchStamp *stamp, TimingBenchTicket *ticket);
TimingBenchResult TimingBench_End(TimingBenchContext *context, uint32_t owner,
    const TimingBenchStamp *stamp, const TimingBenchTicket *ticket);

#endif /* __TIMING_BENCH_H */
