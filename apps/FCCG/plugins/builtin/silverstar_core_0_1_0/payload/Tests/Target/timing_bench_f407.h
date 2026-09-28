#ifndef __TIMING_BENCH_F407_H
#define __TIMING_BENCH_F407_H

#include "timing_bench.h"
#include "system_task_stack.h"
#include "logger_bus.h"
#include "logger_task.h"
#include "imu_sample_bus.h"
#include "estimator_bus.h"

#define TIMING_BENCH_VALID_TASK_STACK 1U
#define TIMING_BENCH_VALID_LOGGER_QUEUE 2U
#define TIMING_BENCH_VALID_LOGGER_TASK 4U
#define TIMING_BENCH_VALID_ALL 7U

typedef struct
{
    uint64_t capture_begin_us;
    uint64_t capture_end_us;
    TimingBenchStats interval[TIMING_BENCH_COUNT];
    SystemTaskStackSnapshot task_stack;
    LoggerBusDiagnostics logger_queue;
    LoggerTaskDiagnostics logger_task;
    ImuSampleBusStats imu_queue;
    EstimatorBusStats estimator_queue;
    uint32_t clock_hz;
    uint32_t valid_mask;
} TimingBenchReport;

typedef void (*TimingBenchWork)(void *argument);

/* Sole normal-task initialization, once after scheduler/time initialization.
 * Never resets a running DWT counter; shared debugger/trace ownership remains external. */
TimingBenchResult TimingBenchF407_Initialize(void);
TimingBenchResult TimingBenchF407_Begin(TimingBenchInterval interval, TimingBenchTicket *ticket);
TimingBenchResult TimingBenchF407_End(const TimingBenchTicket *ticket);
/* Always executes valid work exactly once, even if timing admission fails. */
TimingBenchResult TimingBenchF407_Measure(TimingBenchInterval interval,
    TimingBenchWork work, void *argument);
/* Normal task only; HWM scans run with interrupts enabled, outside timed sections. */
TimingBenchResult TimingBenchF407_ReportGet(TimingBenchReport *report);

#endif /* __TIMING_BENCH_F407_H */
