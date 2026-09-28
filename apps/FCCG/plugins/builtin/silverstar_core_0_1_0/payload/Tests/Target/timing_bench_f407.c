#include "timing_bench_f407.h"

#include <stddef.h>
#include <string.h>
#include "stm32f4xx.h"
#include "FreeRTOS.h"
#include "task.h"
#include "system_time.h"

static TimingBenchContext s_timing;
static uint8_t s_initialized;

static uint32_t TimingBenchF407_OwnerGet(void)
{
    uint32_t exception = __get_IPSR();
    /* A static task's kernel-owned name address is a stable identity token.
     * Do not dereference its string; no extra FreeRTOS task-handle API is enabled. */
    return (exception != 0U) ? exception : (uint32_t)(uintptr_t)pcTaskGetName(NULL);
}

static TimingBenchStamp TimingBenchF407_StampGet(void)
{
    TimingBenchStamp stamp;
    stamp.monotonic_us = SystemTime_GetMonotonicUsFromIsr();
    stamp.cycles = DWT->CYCCNT;
    stamp.clock_hz = ((DWT->CTRL & DWT_CTRL_CYCCNTENA_Msk) != 0U) ? SystemCoreClock : 0U;
    return stamp;
}

TimingBenchResult TimingBenchF407_Initialize(void)
{
    TimingBenchResult result;
    uint32_t primask;
    if ((__get_IPSR() != 0U) || (__get_PRIMASK() != 0U) ||
        (xTaskGetSchedulerState() != taskSCHEDULER_RUNNING)) {
        return TIMING_BENCH_BAD_OWNER;
    }
    primask = __get_PRIMASK();
    __disable_irq();
    if (s_initialized != 0U) {
        __set_PRIMASK(primask);
        return TIMING_BENCH_BUSY;
    }
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    if ((DWT->CTRL & DWT_CTRL_NOCYCCNT_Msk) != 0U) {
        __set_PRIMASK(primask);
        return TIMING_BENCH_NOT_READY;
    }
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    __DSB();
    __ISB();
    result = TimingBench_Initialize(&s_timing, SystemCoreClock);
    if (result == TIMING_BENCH_OK) {
        s_initialized = 1U;
    }
    __set_PRIMASK(primask);
    return result;
}

TimingBenchResult TimingBenchF407_Begin(TimingBenchInterval interval, TimingBenchTicket *ticket)
{
    TimingBenchResult result;
    TimingBenchStamp stamp;
    uint32_t primask;
    if (s_initialized == 0U) {
        return TIMING_BENCH_NOT_READY;
    }
    result = TimingBench_ContextValidate(__get_IPSR(), interval);
    if (result != TIMING_BENCH_OK) {
        return result;
    }
    primask = __get_PRIMASK();
    __disable_irq();
    stamp = TimingBenchF407_StampGet();
    result = TimingBench_Begin(&s_timing, interval, TimingBenchF407_OwnerGet(), &stamp, ticket);
    __set_PRIMASK(primask);
    return result;
}

TimingBenchResult TimingBenchF407_End(const TimingBenchTicket *ticket)
{
    TimingBenchResult result;
    TimingBenchStamp stamp;
    uint32_t primask;
    if (s_initialized == 0U) {
        return TIMING_BENCH_NOT_READY;
    }
    if (ticket == NULL) {
        return TIMING_BENCH_BAD_PARAM;
    }
    result = TimingBench_ContextValidate(__get_IPSR(), ticket->interval);
    if (result != TIMING_BENCH_OK) {
        return result;
    }
    primask = __get_PRIMASK();
    __disable_irq();
    stamp = TimingBenchF407_StampGet();
    result = TimingBench_End(&s_timing, TimingBenchF407_OwnerGet(), &stamp, ticket);
    __set_PRIMASK(primask);
    return result;
}

TimingBenchResult TimingBenchF407_Measure(TimingBenchInterval interval,
    TimingBenchWork work, void *argument)
{
    TimingBenchTicket ticket = {0};
    TimingBenchResult result;
    if (work == NULL) {
        return TIMING_BENCH_BAD_PARAM;
    }
    result = TimingBenchF407_Begin(interval, &ticket);
    work(argument);
    return (result == TIMING_BENCH_OK) ? TimingBenchF407_End(&ticket) : result;
}

TimingBenchResult TimingBenchF407_ReportGet(TimingBenchReport *report)
{
    uint32_t primask;
    uint32_t index;
    if ((report == NULL) || (__get_IPSR() != 0U) || (__get_PRIMASK() != 0U)) {
        return TIMING_BENCH_BAD_PARAM;
    }
    if (s_initialized == 0U) {
        return TIMING_BENCH_NOT_READY;
    }
    (void)memset(report, 0, sizeof(*report));
    report->capture_begin_us = SystemTime_GetMonotonicUs();
    primask = __get_PRIMASK();
    __disable_irq();
    report->clock_hz = s_timing.clock_hz;
    for (index = 0U; index < (uint32_t)TIMING_BENCH_COUNT; index++) {
        report->interval[index] = s_timing.slot[index].stats;
    }
    __set_PRIMASK(primask);
    if (SystemTaskStack_SnapshotGet(&report->task_stack) == SYSTEM_DEVICE_OK) {
        report->valid_mask |= TIMING_BENCH_VALID_TASK_STACK;
    }
    if (LoggerBus_DiagnosticsGet(&report->logger_queue) == LOGGER_BUS_RESULT_OK) {
        report->valid_mask |= TIMING_BENCH_VALID_LOGGER_QUEUE;
    }
    if (LoggerTask_DiagnosticsGet(&report->logger_task) == SYSTEM_DEVICE_OK) {
        report->valid_mask |= TIMING_BENCH_VALID_LOGGER_TASK;
    }
    ImuSampleBus_StatsGet(&report->imu_queue);
    EstimatorBus_StatsGet(&report->estimator_queue);
    report->capture_end_us = SystemTime_GetMonotonicUs();
    return (report->valid_mask == TIMING_BENCH_VALID_ALL) ? TIMING_BENCH_OK : TIMING_BENCH_PARTIAL;
}
