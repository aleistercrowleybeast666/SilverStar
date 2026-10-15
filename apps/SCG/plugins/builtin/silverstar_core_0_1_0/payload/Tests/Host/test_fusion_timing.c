/* Reuse the existing device fixture; exercise the actual logical producer. */
#ifdef FUSION_TIMING_COLD_TEST
#define main ColdExisting_Main
#include "test_barometer_cold.c"
#undef main
#endif
#include <string.h>
#include "system_fusion_timing.h"
#include "test_common.h"

static void Test_CurrentTimeBoundaries(void)
{
    const uint64_t ages[] = {499999ULL, 500000ULL, 500001ULL};
    for (uint8_t index = 0U; index < 3U; index++)
    {
        SystemFusionExecutionResult expected = (index < 2U) ?
            SYSTEM_FUSION_EXEC_COMPLETE : SYSTEM_FUSION_EXEC_STALE;
        TEST_CHECK(SystemFusionTiming_CurrentValidate(2000000ULL - ages[index],
            2000000ULL, 2000000ULL, 1000000ULL) == expected);
        TEST_CHECK(SystemFusionTiming_CurrentValidate(2000000ULL - ages[index],
            2000000ULL - ages[index], 2000000ULL, 1000000ULL) == expected);
    }
    TEST_CHECK(SystemFusionTiming_CurrentValidate(0U, 2000000U, 2000000U, 0U) == SYSTEM_FUSION_EXEC_INVALID);
    TEST_CHECK(SystemFusionTiming_CurrentValidate(2000000U, 2000001U, 2000000U, 0U) == SYSTEM_FUSION_EXEC_INVALID);
    TEST_CHECK(SystemFusionTiming_CurrentValidate(2000001U, 2000000U, 2000000U, 0U) == SYSTEM_FUSION_EXEC_INVALID);
    TEST_CHECK(SystemFusionTiming_CurrentValidate(1000000U, 2000000U, 2000000U, 1000001U) == SYSTEM_FUSION_EXEC_EPOCH_MISMATCH);
}

static void Test_SerialWatermark(void)
{
    SystemFusionReceipt sources[SYSTEM_FUSION_SOURCE_COUNT] = {0};
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], UINT32_MAX, 1U) == SYSTEM_FUSION_EXEC_COMPLETE);
    SystemFusionTiming_ReceiptCommit(&sources[0], UINT32_MAX, 1U);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0U, 1U) == SYSTEM_FUSION_EXEC_COMPLETE);
    SystemFusionTiming_ReceiptCommit(&sources[0], 0U, 1U);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0U, 2U) == SYSTEM_FUSION_EXEC_COMPLETE);
    SystemFusionTiming_ReceiptCommit(&sources[0], 0U, 2U);
    SystemFusionTiming_ReceiptCommit(&sources[1], 0U, 1U);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0U, 1U) == SYSTEM_FUSION_EXEC_DUPLICATE);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0x7FFFFFFFUL, 1U) == SYSTEM_FUSION_EXEC_COMPLETE);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0x80000000UL, 1U) == SYSTEM_FUSION_EXEC_DISCONTINUITY);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0x80000001UL, 1U) == SYSTEM_FUSION_EXEC_DISCONTINUITY);
    memset(sources, 0, sizeof(sources));
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&sources[0], 0U, 1U) == SYSTEM_FUSION_EXEC_COMPLETE);
}

#ifdef FUSION_TIMING_COLD_TEST
static void Test_ColdLogicalSequence(void)
{
    SystemBarometerSample delivered;
    SystemFusionReceipt receipt = {0};
    TestReset(0U);
    s_sample[0].sequence = 900U;
    TEST_CHECK(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemBarometerCold_SampleGet(&delivered) == SYSTEM_DEVICE_OK);
    TEST_CHECK(delivered.sequence == 1U && delivered.sequence != s_sample[0].sequence);
    SystemFusionTiming_ReceiptCommit(&receipt, delivered.sequence, 1U);
    TEST_CHECK(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemBarometerCold_SampleGet(&delivered) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&receipt, delivered.sequence, 1U) == SYSTEM_FUSION_EXEC_DUPLICATE);
    /* An unchanged native sequence with a newly received sample is a new
     * logical producer packet; never substitute the native sequence. */
    s_sample[0].receive_timestamp_us = ++s_now;
    s_sample[0].sample_timestamp_us = s_now;
    TEST_CHECK(SystemBarometerCold_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemBarometerCold_SampleGet(&delivered) == SYSTEM_DEVICE_OK);
    TEST_CHECK(delivered.sequence == 2U && s_sample[0].sequence == 900U);
    TEST_CHECK(SystemFusionTiming_ReceiptCheck(&receipt, delivered.sequence, 1U) == SYSTEM_FUSION_EXEC_COMPLETE);
    TEST_CHECK(SystemBarometerCold_Stop() == SYSTEM_DEVICE_OK);
}
#endif

int main(void)
{
    Test_CurrentTimeBoundaries();
    Test_SerialWatermark();
#ifdef FUSION_TIMING_COLD_TEST
    TEST_CHECK(ColdExisting_Main() == 0);
    Test_ColdLogicalSequence();
#endif
    return Test_Finish("fusion_timing");
}
