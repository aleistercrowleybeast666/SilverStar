#include "timing_bench_example.h"

#include <stddef.h>

static void TimingBenchExample_InsRead(void *argument)
{
    TimingBenchExample *example = (TimingBenchExample *)argument;
    example->ins_available = Ins_GetLatestSnapshot(&example->ins);
}

static void TimingBenchExample_EstimatorRead(void *argument)
{
    TimingBenchExample *example = (TimingBenchExample *)argument;
    example->estimator_available = Estimator_GetLatestSnapshot(&example->estimator);
}

TimingBenchResult TimingBenchExample_Collect(TimingBenchExample *example)
{
    if (example == NULL) {
        return TIMING_BENCH_BAD_PARAM;
    }
    example->ins_timing = TimingBenchF407_Measure(TIMING_BENCH_INS,
        TimingBenchExample_InsRead, example);
    example->estimator_timing = TimingBenchF407_Measure(TIMING_BENCH_ESTIMATOR,
        TimingBenchExample_EstimatorRead, example);
    return TimingBenchF407_ReportGet(&example->report);
}
