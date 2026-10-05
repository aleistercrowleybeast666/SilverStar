#include <float.h>
#include <stdint.h>
#include <string.h>
#include "navigation_kf_replay.h"
#include "system_gnss_quality.h"
#include "test_common.h"

static NavigationReplayContext s_history;
static NavigationReplayStorage s_storage;
static uint32_t s_random = 20261005U;

static uint32_t Test_RandomNext(void)
{
    s_random = s_random * 1664525U + 1013904223U;
    return s_random;
}

static void Test_Initialize(NavigationKfContext *state)
{
    float p[36] = {0.0f};
    const float sigma[3] = {1.0f, 1.7f, 2.4f};
    for (uint8_t i = 0U; i < 6U; i++)
    {
        for (uint8_t j = 0U; j < 6U; j++)
        { p[i * 6U + j] = ((i == j) ? 0.1f : 0.0f) + 0.001f * (float)(i + 1U) * (float)(j + 1U); }
    }
    NavigationKf_Init(state);
    TEST_CHECK(NavigationKf_ResetWithCovariance(state, p) != 0U);
    NavigationKf_SetProcessAccelStd(state, sigma);
    for (uint8_t i = 0U; i < 6U; i++) { state->state[i] = 0.1f * (float)i; }
}

static void Test_Compare(const NavigationKfContext *a, const NavigationKfContext *b)
{
    /* 128 random partitions: float32 additions change evaluation order.
     * At this fixture scale 2e-6 is <20 ULP, far below the old Qvv difference. */
    for (uint8_t i = 0U; i < 6U; i++)
    {
        TEST_CHECK_NEAR(a->state[i], b->state[i], 2.0e-6f);
        for (uint8_t j = 0U; j < 6U; j++)
        { TEST_CHECK_NEAR(a->covariance[i][j], b->covariance[i][j], 2.0e-6f); }
    }
}

static void Test_RandomPartitions(void)
{
    const float acceleration[3] = {0.2f, -0.3f, 0.4f};
    for (uint32_t sample = 0U; sample < 128U; sample++)
    {
        NavigationKfContext full, split;
        float delta[3];
        uint32_t remaining = 20000U;
        Test_Initialize(&full); split = full;
        for (uint8_t i = 0U; i < 3U; i++) { delta[i] = acceleration[i] * 0.02f; }
        TEST_CHECK(NavigationKf_Predict(&full, delta, 0.02f) != 0U);
        for (uint8_t part = 0U; part < 7U; part++)
        {
            uint32_t us = (part == 6U) ? remaining : 1U + Test_RandomNext() % (remaining / 2U);
            float h = 0.02f * (float)us / 20000.0f;
            for (uint8_t i = 0U; i < 3U; i++) { delta[i] = acceleration[i] * h; }
            TEST_CHECK(NavigationKf_PredictInterval(&split, delta, h, 0.02f) == NAV_KF_PREDICT_OK);
            remaining -= us;
        }
        TEST_CHECK(remaining == 0U);
        Test_Compare(&full, &split);
    }
}

static void Test_RejectedEventNeutral(void)
{
    NavigationKfContext state, before;
    NavigationReplayEvent event = {0};
    NavigationReplayOutcome outcome;
    const float delta[3] = {0.1f, -0.05f, 0.0f};
    Test_Initialize(&state);
    NavigationReplay_Reset(&s_history, &s_storage, &state, 1000000ULL, 7U);
    TEST_CHECK(NavigationReplay_Predict(&s_history, &state, 1020000ULL, delta, 0.02f) == NAV_REPLAY_OK);
    before = state;
    event.measurement_timestamp_us = 1007000ULL;
    event.receive_timestamp_us = 1020000ULL;
    event.epoch = 7U; event.sequence = 1U; event.source = 1U;
    event.kind = NAV_REPLAY_VELOCITY; event.valid_group_mask = 4U;
    event.velocity[0] = 1000.0f; event.velocity[1] = -1000.0f;
    event.velocity_variance[0] = 0.01f; event.velocity_variance[1] = 0.01f;
    TEST_CHECK(NavigationReplay_Insert(&s_history, &state, &event, &outcome) == NAV_REPLAY_OK);
    TEST_CHECK(outcome.velocity_groups.horizontal_result == NAV_KF_UPDATE_REJECTED_NIS);
    Test_Compare(&state, &before);
    event.sequence = 2U; event.source = 2U; /* Same timestamp, distinct event. */
    TEST_CHECK(NavigationReplay_Insert(&s_history, &state, &event, &outcome) == NAV_REPLAY_OK);
    TEST_CHECK(outcome.velocity_groups.horizontal_result == NAV_KF_UPDATE_REJECTED_NIS);
    Test_Compare(&state, &before);
}

static void Test_DomainAtomicity(void)
{
    const float invalid[] = {0.0f, -1.0f, NAN, INFINITY, 0.001f, 0.101f};
    const float delta[3] = {0.0f, 0.0f, 0.0f};
    NavigationKfContext state, before;
    Test_Initialize(&state); before = state;
    for (uint8_t i = 0U; i < sizeof(invalid) / sizeof(invalid[0]); i++)
    {
        TEST_CHECK(NavigationKf_PredictInterval(&state, delta, 0.01f, invalid[i]) == NAV_KF_PREDICT_INVALID);
        TEST_CHECK(memcmp(state.state, before.state, sizeof(state.state)) == 0);
        TEST_CHECK(memcmp(state.covariance, before.covariance, sizeof(state.covariance)) == 0);
        TEST_CHECK(state.predict_count == before.predict_count);
    }
    state.process_accel_std_mps2[0] = FLT_MAX;
    TEST_CHECK(NavigationKf_PredictInterval(&state, delta, 0.01f, 0.02f) == NAV_KF_PREDICT_INVALID);
    TEST_CHECK(memcmp(state.state, before.state, sizeof(state.state)) == 0);
    TEST_CHECK(memcmp(state.covariance, before.covariance, sizeof(state.covariance)) == 0);
}

static void Test_JointGaussianVector(void)
{
    NavigationKfContext state;
    const float delta[3] = {0.0f, 0.0f, 0.0f};
    const float observation[2] = {0.34f, 0.37f};
    const float variance[2] = {0.02f, 0.03f};
    Test_Initialize(&state);
    TEST_CHECK(NavigationKf_PredictInterval(&state, delta, 0.007f, 0.02f) == NAV_KF_PREDICT_OK);
    TEST_CHECK(NavigationKf_UpdateGnssVelocity2D(&state, observation, variance) == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(NavigationKf_PredictInterval(&state, delta, 0.013f, 0.02f) == NAV_KF_PREDICT_OK);
    (void)printf("JOINT");
    for (uint8_t i = 0U; i < 6U; i++) { (void)printf(" %.9g", (double)state.state[i]); }
    for (uint8_t i = 0U; i < 6U; i++)
    { for (uint8_t j = 0U; j < 6U; j++) { (void)printf(" %.9g", (double)state.covariance[i][j]); } }
    (void)printf("\n");
}

static void Test_BadEvidenceVisible(void)
{
    SystemGnssSample sample = {0};
    sample.receive_timestamp_us = 1000000ULL;
    sample.online = 1U; sample.fix_type = 3U; sample.fix_ok = 1U;
    sample.satellite_count = 12U; sample.supported_fields = 0x3ffU; sample.valid_fields = 0x3ffU;
    sample.horizontal_accuracy_m = 0.5f; sample.vertical_accuracy_m = 0.8f; sample.speed_accuracy_mps = 0.1f;
    for (uint8_t test = 0U; test < 2U; test++)
    {
        sample.velocity_enu_mps[0] = (test == 0U) ? 20.0f : 1000.0f;
        TEST_CHECK(SystemGnssQuality_Evaluate(&sample, 1000000ULL) == SYSTEM_DEVICE_OK);
        TEST_CHECK(sample.physical_valid_group_mask == 15U);
        TEST_CHECK(sample.quality_degraded_group_mask == 0U);
        /* Visible legacy limitation; not asserted to be a trustworthy fix. */
    }
    sample.fix_ok = 0U;
    TEST_CHECK(SystemGnssQuality_Evaluate(&sample, 1000000ULL) == SYSTEM_DEVICE_OK);
    TEST_CHECK(sample.physical_valid_group_mask == 0U);
}

int main(void)
{
    TEST_CHECK(NAV_KF_ALGORITHM_REVISION == 2U);
    Test_RandomPartitions(); Test_RejectedEventNeutral(); Test_DomainAtomicity();
    Test_JointGaussianVector(); Test_BadEvidenceVisible();
    return Test_Finish("kf6_process_model_revision2");
}
