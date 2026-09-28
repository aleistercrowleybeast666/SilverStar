#ifndef __TIMING_BENCH_EXAMPLE_H
#define __TIMING_BENCH_EXAMPLE_H

#include "timing_bench_f407.h"
#include "ins_task.h"
#include "estimator_task.h"

typedef struct
{
    InsOutputSnapshot ins;
    EstimatorOutputSnapshot estimator;
    TimingBenchReport report;
    TimingBenchResult ins_timing;
    TimingBenchResult estimator_timing;
    uint8_t ins_available;
    uint8_t estimator_available;
} TimingBenchExample;

/* Executable integration example: measures only actual snapshot getters,
 * then collects actual task/queue HWM. It does NOT measure full task execution. */
TimingBenchResult TimingBenchExample_Collect(TimingBenchExample *example);

#endif /* __TIMING_BENCH_EXAMPLE_H */
