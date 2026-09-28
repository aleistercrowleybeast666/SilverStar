#include "test_common.h"
#include "timing_bench.h"

#include <string.h>

static TimingBenchStamp Test_Stamp(uint32_t cycles, uint64_t us)
{
    TimingBenchStamp stamp = {us, cycles, 168000000U};
    return stamp;
}

static void Test_Ownership(void)
{
    TimingBenchContext context = {0};
    TimingBenchTicket ins = {0}, isr = {0}, forged = {0};
    TimingBenchStamp start = Test_Stamp(100U, 100U);
    TimingBenchStamp end = Test_Stamp(16900U, 200U);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 1U, &start, &ins) == TIMING_BENCH_NOT_READY);
    TEST_CHECK(TimingBench_Initialize(&context, 168000000U) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_Initialize(&context, 168000000U) == TIMING_BENCH_BUSY);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 1U, &start, &ins) == TIMING_BENCH_OK);
    forged = ins;
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 1U, &start, &forged) == TIMING_BENCH_BUSY);
    TEST_CHECK(memcmp(&forged, &ins, sizeof(ins)) == 0);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 2U, &start, &forged) == TIMING_BENCH_BUSY);
    TEST_CHECK(TimingBench_End(&context, 2U, &end, &ins) == TIMING_BENCH_BAD_OWNER);
    TEST_CHECK(context.slot[TIMING_BENCH_INS].active == 1U);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ISR, 16U, &start, &isr) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_End(&context, 16U, &end, &isr) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ins) == TIMING_BENCH_OK);
    TEST_CHECK(context.slot[TIMING_BENCH_INS].stats.last_cycles == 16800U);
    TEST_CHECK(context.slot[TIMING_BENCH_ISR].stats.last_cycles == 16800U);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ins) == TIMING_BENCH_STALE_TICKET);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 1U, &start, &forged) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ins) == TIMING_BENCH_STALE_TICKET);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &forged) == TIMING_BENCH_OK);
}

static void Test_WrapAndClock(void)
{
    TimingBenchContext context = {0};
    TimingBenchTicket ticket = {0};
    TimingBenchStamp start = Test_Stamp(UINT32_MAX - 99U, 1000000U);
    TimingBenchStamp end = Test_Stamp(1580U, 1000010U);
    TEST_CHECK(TimingBench_Initialize(&context, 168000000U) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ESTIMATOR, 1U, &start, &ticket) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_OK);
    TEST_CHECK(context.slot[TIMING_BENCH_ESTIMATOR].stats.last_cycles == 1680U);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ESTIMATOR, 1U, &start, &ticket) == TIMING_BENCH_OK);
    end.monotonic_us = start.monotonic_us + 30000000U;
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_CLOCK_INVALID);
    TEST_CHECK(context.slot[TIMING_BENCH_ESTIMATOR].stats.completed == 1U);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ESTIMATOR, 1U, &start, &ticket) == TIMING_BENCH_OK);
    end = start;
    end.monotonic_us += 100U;
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_CLOCK_INVALID);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ESTIMATOR, 1U, &start, &ticket) == TIMING_BENCH_OK);
    end = Test_Stamp(1580U, start.monotonic_us - 1U);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_CLOCK_INVALID);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ESTIMATOR, 1U, &start, &ticket) == TIMING_BENCH_OK);
    end = Test_Stamp(1580U, start.monotonic_us + 10U);
    end.clock_hz = 84000000U;
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_CLOCK_INVALID);
    start.clock_hz = 0U;
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_ESTIMATOR, 1U, &start, &ticket) == TIMING_BENCH_CLOCK_INVALID);
    TEST_CHECK(context.slot[TIMING_BENCH_ESTIMATOR].stats.rejected == 5U);
}

static void Test_SaturationAndParameters(void)
{
    TimingBenchContext context = {0};
    TimingBenchTicket ticket = {0};
    TimingBenchStamp start = Test_Stamp(100U, 100U), end = Test_Stamp(16900U, 200U);
    uint32_t exception;
    for (exception = 1U; exception < 16U; exception++) {
        TEST_CHECK(TimingBench_ContextValidate(exception, TIMING_BENCH_ISR) == TIMING_BENCH_BAD_OWNER);
        TEST_CHECK(TimingBench_ContextValidate(exception, TIMING_BENCH_INS) == TIMING_BENCH_BAD_OWNER);
    }
    TEST_CHECK(TimingBench_ContextValidate(0U, TIMING_BENCH_INS) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_ContextValidate(16U, TIMING_BENCH_ISR) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_ContextValidate(0U, TIMING_BENCH_ISR) == TIMING_BENCH_BAD_OWNER);
    TEST_CHECK(TimingBench_ContextValidate(16U, TIMING_BENCH_INS) == TIMING_BENCH_BAD_OWNER);
    TEST_CHECK(TimingBench_ContextValidate(0U, TIMING_BENCH_COUNT) == TIMING_BENCH_BAD_PARAM);
    TEST_CHECK(TimingBench_Initialize(NULL, 168000000U) == TIMING_BENCH_BAD_PARAM);
    TEST_CHECK(TimingBench_Initialize(&context, UINT32_MAX) == TIMING_BENCH_BAD_PARAM);
    TEST_CHECK(TimingBench_Initialize(&context, 168000000U) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_COUNT, 1U, &start, &ticket) == TIMING_BENCH_BAD_PARAM);
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 0U, &start, &ticket) == TIMING_BENCH_BAD_PARAM);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, NULL) == TIMING_BENCH_BAD_PARAM);
    context.next_serial = UINT32_MAX;
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_LOGGER, 1U, &start, &ticket) == TIMING_BENCH_SATURATED);
    TEST_CHECK(context.slot[TIMING_BENCH_LOGGER].stats.saturated == 1U);
    context.next_serial = 0U; /* Test-only counter fault injection. */
    context.slot[TIMING_BENCH_LOGGER].stats.total_cycles = UINT64_MAX - 2U;
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_LOGGER, 1U, &start, &ticket) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_SATURATED);
    TEST_CHECK(context.slot[TIMING_BENCH_LOGGER].stats.total_cycles == UINT64_MAX - 2U);
    context.slot[TIMING_BENCH_LOGGER].stats.total_cycles = 0U;
    context.slot[TIMING_BENCH_LOGGER].stats.completed = UINT32_MAX;
    TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_LOGGER, 1U, &start, &ticket) == TIMING_BENCH_OK);
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_SATURATED);
    TEST_CHECK(context.slot[TIMING_BENCH_LOGGER].stats.completed == UINT32_MAX);
    context.slot[TIMING_BENCH_LOGGER].stats.rejected = UINT32_MAX;
    TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_STALE_TICKET);
    TEST_CHECK(context.slot[TIMING_BENCH_LOGGER].stats.rejected == UINT32_MAX);
}

static void Test_RunningStatistics(void)
{
    TimingBenchContext context = {0};
    TimingBenchTicket ticket = {0};
    uint32_t index;
    TEST_CHECK(TimingBench_Initialize(&context, 168000000U) == TIMING_BENCH_OK);
    for (index = 1U; index <= 1000U; index++) {
        TimingBenchStamp start = Test_Stamp(UINT32_MAX - 84U, 1000U);
        TimingBenchStamp end = Test_Stamp(start.cycles + index * 168U, start.monotonic_us + index);
        TEST_CHECK(TimingBench_Begin(&context, TIMING_BENCH_INS, 1U, &start, &ticket) == TIMING_BENCH_OK);
        TEST_CHECK(TimingBench_End(&context, 1U, &end, &ticket) == TIMING_BENCH_OK);
    }
    TEST_CHECK(context.slot[TIMING_BENCH_INS].stats.completed == 1000U);
    TEST_CHECK(context.slot[TIMING_BENCH_INS].stats.minimum_cycles == 168U);
    TEST_CHECK(context.slot[TIMING_BENCH_INS].stats.maximum_cycles == 168000U);
    TEST_CHECK(context.slot[TIMING_BENCH_INS].stats.total_cycles == 84084000U);
}

int main(void)
{
    Test_Ownership();
    Test_WrapAndClock();
    Test_SaturationAndParameters();
    Test_RunningStatistics();
    return Test_Finish("timing_bench");
}
