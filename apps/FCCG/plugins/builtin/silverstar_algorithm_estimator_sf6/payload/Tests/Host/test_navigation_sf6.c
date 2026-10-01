#include <float.h>
#include <string.h>
#include "navigation_sf6.h"
#include "test_common.h"

static NavigationSf6Context s_context;
static NavigationSf6Sample s_snapshot;
static const float s_zero[3] = {0.0f, 0.0f, 0.0f};

static void Test_GainEndpoints(void)
{
    uint8_t active, axis, endpoint;
    uint64_t boundary;
    for (endpoint = 0U; endpoint <= 1U; endpoint++)
    {
        for (active = 0U; active < 6U; active++)
        {
            float gain[6] = {0.0f};
            NavigationSf6Measurement measurement = {0};
            gain[active] = (float)endpoint;
            TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
            measurement.receive_us = 1000000ULL; measurement.measurement_us = 1000000ULL;
            measurement.sequence = 9U;
            measurement.group = active < 3U ? (active == 2U ? 3U : 2U) : (active == 5U ? 1U : 0U);
            measurement.observation[0] = 10.0f; measurement.observation[1] = 20.0f;
            TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
            TEST_CHECK(boundary == 1000000ULL);
            TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
            for (axis = 0U; axis < 6U; axis++)
            { TEST_CHECK_NEAR(s_snapshot.state[axis], axis == active ?
                (float)endpoint * (active == 1U || active == 4U ? 20.0f : 10.0f) : 0.0f, 1.0e-6f); }
        }
    }
}

static void Test_DelayAndIndependentGroups(void)
{
    const float gain[6] = {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 0.5f};
    const float dv[3] = {0.1f, 0.0f, 0.0f};
    NavigationSf6Measurement measurement = {0};
    uint64_t boundary;
    unsigned int step;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
    for (step = 1U; step <= 20U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context, 1000000ULL + step * 10000ULL, dv, 0.01f) == NAV_SF6_OK); }
    measurement.receive_us = 1200000ULL; measurement.measurement_us = 1105000ULL;
    measurement.sequence = UINT32_MAX; measurement.group = 2U;
    measurement.observation[0] = 5.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(boundary == 1100000ULL);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[0], 6.0f, 1.0e-5f);
    TEST_CHECK_NEAR(s_snapshot.state[3], 0.6f, 1.0e-5f);
    /* Same packet has an independent position observation, not a duplicate. */
    measurement.group = 0U; measurement.observation[0] = 10.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_DUPLICATE);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[3], 10.55f, 1.0e-5f);
    /* Barometer shares pU gain; it never creates a hidden vU correction. */
    measurement.group = 4U; measurement.measurement_us = 1200000ULL;
    measurement.observation[0] = 8.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[5], 4.0f, 1.0e-6f);
    TEST_CHECK_NEAR(s_snapshot.state[2], 0.0f, 1.0e-6f);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 1210000ULL, s_zero, 0.01f) == NAV_SF6_OK);
    measurement.receive_us = 1210000ULL; measurement.measurement_us = 1210000ULL;
    measurement.sequence = 0U;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    measurement.sequence = UINT32_MAX; measurement.receive_us++;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) != NAV_SF6_OK);
}

static void Test_BoundsAndOutage(void)
{
    float gain[6] = {0.2f, 0.2f, 0.2f, 0.2f, 0.2f, 0.2f};
    NavigationSf6Measurement measurement = {0};
    NavigationSf6Sample before;
    uint64_t boundary = UINT64_MAX;
    unsigned int step;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
    for (step = 1U; step <= 1000U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context, 1000000ULL + step * 1000ULL, s_zero, 0.001f) == NAV_SF6_OK); }
    TEST_CHECK(s_context.count == NAV_SF6_HISTORY_CAPACITY);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &before) == NAV_SF6_OK);
    measurement.receive_us = 2000000ULL; measurement.measurement_us = 1000000ULL;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_STALE);
    measurement.measurement_us = 2000000ULL; measurement.observation[0] = NAN;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_INVALID_ARGUMENT);
    measurement.observation[0] = INFINITY;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_INVALID_ARGUMENT);
    TEST_CHECK(boundary == UINT64_MAX);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 2001000ULL, s_zero, NAN) == NAV_SF6_INVALID_ARGUMENT);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 2001000ULL, s_zero, 0.1f) == NAV_SF6_INVALID_ARGUMENT);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 2000000ULL, s_zero, 0.001f) == NAV_SF6_STALE);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK(memcmp(&before, &s_snapshot, sizeof(before)) == 0);
    gain[5] = -0.01f;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 0U) == NAV_SF6_INVALID_ARGUMENT);
    gain[5] = 1.01f;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 0U) == NAV_SF6_INVALID_ARGUMENT);
    gain[5] = NAN;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 0U) == NAV_SF6_INVALID_ARGUMENT);
    NavigationSf6_Reset(&s_context);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_NOT_READY);
}

int main(void)
{
    Test_GainEndpoints(); Test_DelayAndIndependentGroups(); Test_BoundsAndOutage();
    return Test_Finish("navigation_sf6");
}
