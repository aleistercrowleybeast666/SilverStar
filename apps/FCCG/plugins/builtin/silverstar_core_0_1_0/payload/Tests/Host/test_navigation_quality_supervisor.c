#include <stdint.h>
#include <string.h>
#include "navigation_quality.h"
#include "system_navigation_health.h"
#include "test_common.h"

static const NavigationWindowConfig s_config = {
    10000000ULL, 5000000ULL, 6000000ULL, 120000U, 10.0f, 4.0f
};

static NavigationWindowSample Test_SampleMake(uint32_t index, float mismatch)
{
    NavigationWindowSample sample = {0};
    float time = (float)index * 0.04f;
    sample.epoch_us = 1000000ULL + (uint64_t)index * 40000ULL;
    sample.sequence = index + 1U; sample.source = 2U; sample.generation = 7U;
    /* Large continuous acceleration is not itself an integrity fault. */
    sample.position_en[0] = 2.5f * time * time + mismatch * time;
    sample.velocity_en[0] = 5.0f * time;
    sample.position_en[1] = -3.0f * time;
    sample.velocity_en[1] = -3.0f;
    sample.position_valid = 1U; sample.velocity_valid = 1U;
    return sample;
}

static void Test_WindowHealthyAndBounded(void)
{
    NavigationWindowContext context, prior;
    NavigationWindowSample sample;
    uint32_t index;
    TEST_CHECK(NavigationWindow_Reset(&context) == NAV_QUALITY_OK);
    for (index = 0U; index <= 625U; index++)
    {
        sample = Test_SampleMake(index, 0.0f);
        if ((index > 50U) && (index < 70U)) { sample.position_valid = 0U; }
        TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_OK);
        if (index < 250U) { TEST_CHECK(context.evidence_valid == 0U); }
    }
    TEST_CHECK(context.completed_count == 4U);
    TEST_CHECK_NEAR(context.closure_norm_m, 0.0f, 0.005f);
    TEST_CHECK(context.completed_covered_us == 10000000U);
    TEST_CHECK(context.completed_velocity_epochs == 250U);
    TEST_CHECK(context.completed_window_index == 1U);
    TEST_CHECK_NEAR(NavigationWindow_VarianceScale(&context, &s_config, sample.epoch_us), 1.0f, 0.0f);
    prior = context;
    TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_DUPLICATE);
    TEST_CHECK(memcmp(&prior, &context, sizeof(context)) == 0);
    sample.sequence++; sample.epoch_us -= 1000U;
    TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_DUPLICATE);
    TEST_CHECK(memcmp(&prior, &context, sizeof(context)) == 0);
    sample = Test_SampleMake(629U, 0.0f);
    TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_DISCONTINUITY);
    TEST_CHECK(context.evidence_valid == 0U);
    for (index = 630U; index < 879U; index++)
    {
        sample = Test_SampleMake(index, 0.0f);
        TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_OK);
        TEST_CHECK(context.evidence_valid == 0U);
    }
    sample = Test_SampleMake(879U, 0.0f);
    TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_OK);
    TEST_CHECK(context.evidence_valid != 0U);
}

static void Test_WindowExpiryAndEndpoint(void)
{
    NavigationWindowContext context;
    NavigationWindowSample sample;
    uint32_t index;
    TEST_CHECK(NavigationWindow_Reset(&context) == NAV_QUALITY_OK);
    for (index = 0U; index <= 375U; index++)
    {
        sample = Test_SampleMake(index, 2.0f);
        if (index == 375U) { sample.position_valid = 0U; }
        TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_OK);
    }
    TEST_CHECK(context.completed_count == 1U);
    TEST_CHECK(context.unavailable_count == 1U);
    TEST_CHECK(context.completed_us == 11000000ULL);
    TEST_CHECK(context.completed_start_us == 1000000ULL);
    TEST_CHECK_NEAR(context.closure_norm_m, 20.0f, 0.005f);
    TEST_CHECK_NEAR(NavigationWindow_VarianceScale(&context, &s_config, 17000000ULL), 4.0f, 0.005f);
    TEST_CHECK_NEAR(NavigationWindow_VarianceScale(&context, &s_config, 17000001ULL), 1.0f, 0.0f);
    sample = Test_SampleMake(376U, 2.0f); sample.source++;
    TEST_CHECK(NavigationWindow_Receive(&context, &s_config, &sample) == NAV_QUALITY_DISCONTINUITY);
    TEST_CHECK(context.evidence_valid == 0U);
}

static void Test_SupervisorCausalRecovery(void)
{
    SystemNavigationFusionEvidence evidence = {0};
    SystemNavigationGroupHealth state;
    uint8_t group;
    SystemNavigationHealth_Reset(1000000ULL);
    evidence.receive_us = 1100000ULL; evidence.measurement_us = 850000ULL;
    evidence.evaluation_us = 1200000ULL; evidence.sequence = 1U;
    evidence.variance_scale = 1.0f; evidence.nis = 0.5f;
    evidence.physically_valid = 1U; evidence.attempted = 1U; evidence.effective_update = 1U;
    for (group = 0U; group < 5U; group++)
    { TEST_CHECK(SystemNavigationHealth_Observe(group, &evidence) == SYSTEM_DEVICE_OK); }
    TEST_CHECK(SystemNavigationHealth_ChangesGet(1200000ULL) == 31U);
    TEST_CHECK(SystemNavigationHealth_ChangesGet(1200000ULL) == 0U);
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_BAD_STATE);
    /* Distinct physical sources may share the same receive tick and sequence. */
    evidence.source = 1U;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 1200000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.source == 1U);
    TEST_CHECK(state.last_receive_us == 1100000ULL);
    evidence.receive_us++;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_BAD_STATE);
    evidence.sequence++; evidence.receive_us = 3150000ULL;
    evidence.measurement_us = 3000000ULL; evidence.evaluation_us = 3200000ULL;
    evidence.effective_update = 0U; evidence.nis = 1000.0f;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 3200000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.state == SYSTEM_NAVIGATION_DEAD_RECKONING);
    TEST_CHECK(state.last_successful_fusion_us == 1200000ULL);
    TEST_CHECK(state.last_physically_valid_us == 3150000ULL);
    TEST_CHECK(SystemNavigationHealth_OverallGet(11200000ULL, 15U, 0U) == SYSTEM_NAVIGATION_HEALTH_INVALID);
    evidence.sequence++; evidence.receive_us = 11200000ULL;
    evidence.measurement_us = 11000000ULL; evidence.evaluation_us = 11250000ULL;
    evidence.effective_update = 1U; evidence.nis = 0.5f;
    for (group = 0U; group < 5U; group++)
    { TEST_CHECK(SystemNavigationHealth_Observe(group, &evidence) == SYSTEM_DEVICE_OK); }
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 11250000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.recovery_count == 1U);
    TEST_CHECK(state.last_recovery_us == 11250000ULL);
    TEST_CHECK(state.last_successful_fusion_us == 11250000ULL);
    TEST_CHECK(SystemNavigationHealth_OverallGet(11250000ULL, 15U, 0U) == SYSTEM_NAVIGATION_HEALTH_HEALTHY);
    SystemNavigationHealth_ImuQualityRecord(4U);
    TEST_CHECK(SystemNavigationHealth_OverallGet(11250000ULL, 15U, 0U) == SYSTEM_NAVIGATION_HEALTH_DEGRADED);
    SystemNavigationHealth_ImuQualityRecord(2U);
    SystemNavigationHealth_ImuQualityRecord(0U);
    TEST_CHECK(SystemNavigationHealth_OverallGet(11250000ULL, 15U, 0U) == SYSTEM_NAVIGATION_HEALTH_INVALID);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 11250000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.state == SYSTEM_NAVIGATION_INVALID);
    TEST_CHECK(state.reason == 0x82U);
    SystemNavigationHealth_Reset(12000000ULL);
    TEST_CHECK(SystemNavigationHealth_OverallGet(12000000ULL, 15U, 0U) == SYSTEM_NAVIGATION_HEALTH_WARMUP);
    evidence.physically_valid = 0U;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_INVALID_ARGUMENT);
}

static void Test_OverallQualityAggregation(void)
{
    SystemNavigationFusionEvidence evidence = {0};
    SystemNavigationGroupHealth state;
    uint8_t group;
    const uint8_t all_groups = (uint8_t)((1U << SYSTEM_NAVIGATION_GROUP_COUNT) - 1U);
    SystemNavigationHealth_Reset(1000000ULL);
    evidence.receive_us = 1100000ULL; evidence.measurement_us = 1050000ULL;
    evidence.evaluation_us = 1200000ULL; evidence.sequence = 1U;
    evidence.variance_scale = 1.0f; evidence.nis = 0.5f;
    evidence.physically_valid = 1U; evidence.attempted = 1U; evidence.effective_update = 1U;
    for (group = 0U; group < SYSTEM_NAVIGATION_GROUP_COUNT; group++)
    { TEST_CHECK(SystemNavigationHealth_Observe(group, &evidence) == SYSTEM_DEVICE_OK); }
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_HEALTHY);
    evidence.sequence++; evidence.receive_us++;
    evidence.soft_weighted = 1U;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_DEGRADED);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, (uint8_t)(all_groups & 0x1EU), 0U) == SYSTEM_NAVIGATION_HEALTH_HEALTHY);
    evidence.sequence++; evidence.receive_us++;
    evidence.soft_weighted = 0U; evidence.variance_scale = 3.0f;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 1200000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.state == SYSTEM_NAVIGATION_ACCEPTED);
    TEST_CHECK(state.quality == 2U);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_DEGRADED);
    evidence.sequence++; evidence.receive_us++;
    evidence.variance_scale = 1.0f;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_HEALTHY);
    evidence.sequence++; evidence.receive_us++;
    evidence.physically_valid = 0U; evidence.attempted = 0U; evidence.effective_update = 0U;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_DEGRADED);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 1200000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.last_successful_fusion_us == 1200000ULL);
    TEST_CHECK(SystemNavigationHealth_OverallGet(3200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_DEAD_RECKONING);
    TEST_CHECK(SystemNavigationHealth_OverallGet(11200000ULL, all_groups, 0U) == SYSTEM_NAVIGATION_HEALTH_INVALID);
}

static void Test_ModelMismatchLatch(void)
{
    SystemNavigationFusionEvidence evidence = {0};
    SystemNavigationGroupHealth state;
    SystemNavigationHealth_Reset(1000000ULL);
    evidence.receive_us = 1100000ULL; evidence.measurement_us = 1050000ULL;
    evidence.evaluation_us = 1200000ULL; evidence.sequence = 1U;
    evidence.variance_scale = 1.0f; evidence.nis = 0.5f;
    evidence.physically_valid = 1U; evidence.attempted = 1U;
    evidence.reason = SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, 1U, 0U) == SYSTEM_NAVIGATION_HEALTH_INVALID);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 1200000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.reason == SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH);
    TEST_CHECK(state.last_successful_fusion_us == 0U);
    evidence.sequence++; evidence.receive_us++; evidence.effective_update = 1U;
    evidence.reason = 0U;
    TEST_CHECK(SystemNavigationHealth_Observe(0U, &evidence) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U, 1200000ULL, &state) == SYSTEM_DEVICE_OK);
    TEST_CHECK(state.last_successful_fusion_us == 1200000ULL);
    TEST_CHECK(state.state == SYSTEM_NAVIGATION_INVALID);
    TEST_CHECK(state.reason == SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1200000ULL, 1U, 0U) == SYSTEM_NAVIGATION_HEALTH_INVALID);
    SystemNavigationHealth_Reset(1300000ULL);
    TEST_CHECK(SystemNavigationHealth_OverallGet(1300000ULL, 1U, 0U) == SYSTEM_NAVIGATION_HEALTH_WARMUP);
}

int main(void)
{
    NavigationWindowConfig invalid = s_config;
    TEST_CHECK(NavigationWindow_ConfigValidate(&s_config) == NAV_QUALITY_OK);
    invalid.maximum_variance_scale = 4.01f;
    TEST_CHECK(NavigationWindow_ConfigValidate(&invalid) == NAV_QUALITY_INVALID);
    TEST_CHECK(NavigationWindow_ConfigValidate(NULL) == NAV_QUALITY_INVALID);
    TEST_CHECK_NEAR(NavigationQuality_SatelliteVarianceScale(6U, 1U), 1.0f, 0.0f);
    TEST_CHECK_NEAR(NavigationQuality_SatelliteVarianceScale(5U, 1U), 1.5f, 0.0f);
    TEST_CHECK_NEAR(NavigationQuality_SatelliteVarianceScale(4U, 1U), 3.0f, 0.0f);
    TEST_CHECK_NEAR(NavigationQuality_SatelliteVarianceScale(0U, 1U), 4.0f, 0.0f);
    TEST_CHECK_NEAR(NavigationQuality_SatelliteVarianceScale(0U, 0U), 1.0f, 0.0f);
    Test_WindowHealthyAndBounded(); Test_WindowExpiryAndEndpoint(); Test_SupervisorCausalRecovery();
    Test_ModelMismatchLatch();
    Test_OverallQualityAggregation();
    (void)printf("window_context_bytes=%zu; two windows; no sample history\n", sizeof(NavigationWindowContext));
    return Test_Finish("navigation_quality_supervisor");
}
