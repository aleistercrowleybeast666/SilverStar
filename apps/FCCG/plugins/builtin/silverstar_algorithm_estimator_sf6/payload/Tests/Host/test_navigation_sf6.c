#include <float.h>
#include <string.h>
#include "navigation_sf6.h"
#include "test_common.h"

static NavigationSf6Context s_context;
static NavigationSf6Sample s_snapshot;
static NavigationSf6Context s_before_context;
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
    gain[5] = INFINITY;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 0U) == NAV_SF6_INVALID_ARGUMENT);
    NavigationSf6_Reset(&s_context);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_NOT_READY);
}

static void Test_NumericAtomicity(void)
{
    const float velocity[3] = {FLT_MAX, 0.0f, 0.0f};
    const float dv[3] = {FLT_MAX, 0.0f, 0.0f};
    float gain[6] = {1.0f, 1.0f, 1.0f, 1.0f, 1.0f, 1.0f};
    NavigationSf6Sample before;
    NavigationSf6Measurement measurement = {0};
    uint64_t boundary = UINT64_MAX;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, velocity, 1000000ULL) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &before) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 1001000ULL, dv, 0.001f) == NAV_SF6_NUMERIC_ERROR);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK(memcmp(&before, &s_snapshot, sizeof(before)) == 0);
    measurement.receive_us = 1000000ULL; measurement.measurement_us = 1000000ULL;
    measurement.group = 2U; measurement.observation[0] = -FLT_MAX;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_NUMERIC_ERROR);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK(memcmp(&before, &s_snapshot, sizeof(before)) == 0 && boundary == UINT64_MAX);
    TEST_CHECK(s_context.seen[2] == 0U);
    gain[0] = 0.0f;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, velocity, 1000000ULL) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK(s_snapshot.state[0] == FLT_MAX);
    /* A valid late observation can make a later saved prediction overflow.
     * Reject the complete replay without changing cached states or admission. */
    gain[0] = 1.0f;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 1001000ULL, dv, 0.001f) == NAV_SF6_OK);
    s_before_context = s_context;
    measurement.receive_us = 1001000ULL; measurement.observation[0] = FLT_MAX;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_NUMERIC_ERROR);
    TEST_CHECK(memcmp(&s_before_context, &s_context, sizeof(s_context)) == 0);
}

static void Test_CrossGroupTemporalOracle(void)
{
    const float gain[6] = {0.0f, 0.0f, 0.5f, 0.0f, 0.0f, 0.5f};
    uint8_t scenario;
    for (scenario = 0U; scenario < 2U; scenario++)
    {
        NavigationSf6Measurement baro = {1100000ULL, 1100000ULL, 1U, 4U, {8.0f, 0.0f}};
        NavigationSf6Measurement gnss = {1050000ULL, 1100000ULL, 1U, 1U, {10.0f, 0.0f}};
        NavigationSf6Sample before;
        uint64_t boundary = 0U;
        float expected;
        TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
        for (uint32_t step = 1U; step <= 10U; step++)
        { TEST_CHECK(NavigationSf6_Predict(&s_context, 1000000ULL + step * 10000ULL, s_zero, 0.01f) == NAV_SF6_OK); }
        /* Receive baro first at t=.100, then delayed GNSS from t=.050.
         * Independent chronological oracle: GNSS pU ->5, baro ->6.5;
         * GNSS vU ->5, propagate .050 s ->.25, baro ->4.125. */
        TEST_CHECK(NavigationSf6_Update(&s_context, &baro, &boundary) == NAV_SF6_OK);
        if (scenario != 0U) { gnss.group = 3U; }
        TEST_CHECK(NavigationSf6_Update(&s_context, &gnss, &boundary) == NAV_SF6_OK);
        TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
        expected = scenario == 0U ? 6.5f : 4.125f;
        printf("cross_group scenario=%u pU=%g chronological_oracle=%g error=%g\n",
            (unsigned int)scenario, (double)s_snapshot.state[5], (double)expected,
            (double)(s_snapshot.state[5] - expected));
        TEST_CHECK_NEAR(s_snapshot.state[5], expected, 1.0e-6f);
        TEST_CHECK_NEAR(s_snapshot.state[2], scenario == 0U ? 0.0f : 5.0f, 1.0e-6f);
        before = s_snapshot;
        TEST_CHECK(NavigationSf6_Update(&s_context, &gnss, &boundary) == NAV_SF6_DUPLICATE);
        TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
        TEST_CHECK(memcmp(&before, &s_snapshot, sizeof(before)) == 0);
    }
}

static void Test_FutureAndTimestampGroups(void)
{
    const float gain[6] = {0.5f, 0.5f, 0.5f, 0.5f, 0.5f, 0.5f};
    NavigationSf6Measurement measurement = {1100000ULL, 1100000ULL, 7U, 4U, {8.0f, 0.0f}};
    NavigationSf6Sample before;
    uint64_t boundary = UINT64_MAX;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
    for (uint32_t step = 1U; step <= 10U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context, 1000000ULL + step * 10000ULL, s_zero, 0.01f) == NAV_SF6_OK); }
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &before) == NAV_SF6_OK);
    measurement.receive_us++;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_INVALID_ARGUMENT);
    measurement.receive_us--; measurement.measurement_us++;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_INVALID_ARGUMENT);
    TEST_CHECK(boundary == UINT64_MAX && s_context.event_count == 0U);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK(memcmp(&before, &s_snapshot, sizeof(before)) == 0);
    measurement.measurement_us--;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    measurement.group = 1U; measurement.observation[0] = 10.0f;
    /* Fixed tie-break is ascending group, independent of receive order. */
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[5], 6.5f, 1.0e-6f);
    measurement.group = 0U; measurement.measurement_us = 1080000ULL; measurement.observation[0] = 4.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    measurement.group = 2U; measurement.measurement_us = 1060000ULL; measurement.observation[0] = 2.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[0], 1.0f, 1.0e-6f);
    /* At t=.080 pE=.020 before gain=.5 pos observation ->2.010;
     * propagate another .020 ->2.030. */
    TEST_CHECK_NEAR(s_snapshot.state[3], 2.03f, 1.0e-6f);
    measurement.sequence++; measurement.receive_us++; measurement.measurement_us = 1050000ULL;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) != NAV_SF6_OK);
}

static void Test_EventCapacityAndExpiryRecovery(void)
{
    const float gain[6] = {0.0f, 0.0f, 0.0f, 0.5f, 0.5f, 0.5f};
    NavigationSf6Measurement measurement = {0};
    uint64_t boundary = 0U;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Predict(&s_context, 1001000ULL, s_zero, 0.001f) == NAV_SF6_OK);
    for (uint32_t index = 1U; index <= NAV_SF6_EVENT_CAPACITY; index++)
    {
        measurement.measurement_us = 1000000ULL + index;
        measurement.receive_us = measurement.measurement_us; measurement.sequence = index;
        measurement.observation[0] = 2.0f;
        TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    }
    TEST_CHECK(s_context.event_count == NAV_SF6_EVENT_CAPACITY);
    measurement.sequence++; measurement.measurement_us++; measurement.receive_us++;
    boundary = UINT64_MAX;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_FULL);
    TEST_CHECK(boundary == UINT64_MAX && s_context.last_sequence[0] == NAV_SF6_EVENT_CAPACITY);
    for (uint32_t step = 1U; step <= 30U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context, 1001000ULL + step * 20000ULL, s_zero, 0.02f) == NAV_SF6_OK); }
    TEST_CHECK(s_context.event_count == 0U);
    measurement.measurement_us = 1601000ULL; measurement.receive_us = measurement.measurement_us;
    TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
    TEST_CHECK(s_context.event_count == 1U && boundary == 1601000ULL);
}

static void Test_LongWrapIndependentOracle(void)
{
    const float gain[6] = {0.0f, 0.0f, 0.25f, 0.0f, 0.0f, 0.5f};
    const float dv[3] = {0.0f, 0.0f, 0.001f};
    float velocity = 0.0f, position = 0.0f;
    NavigationSf6Measurement measurement = {0};
    uint64_t boundary = 0U;
    TEST_CHECK(NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) == NAV_SF6_OK);
    for (uint32_t step = 1U; step <= 2030U; step++)
    {
        position += (velocity + 0.0005f) * 0.001f; velocity += 0.001f;
        if (step <= 2000U && step % 100U == 0U) { position += 0.5f * ((float)step * 0.01f - position); }
        if (step <= 2000U && step % 50U == 0U) { velocity += 0.25f * (1.0f + (float)step * 0.002f - velocity); }
        if (step <= 2000U && step % 20U == 0U) { position += 0.5f * ((float)step * 0.01f + 0.5f - position); }
        TEST_CHECK(NavigationSf6_Predict(&s_context, 1000000ULL + step * 1000ULL, dv, 0.001f) == NAV_SF6_OK);
        measurement.receive_us = 1000000ULL + step * 1000ULL;
        if (step <= 2000U && step % 20U == 0U)
        {
            measurement.group = 4U; measurement.measurement_us = measurement.receive_us;
            measurement.sequence = step / 20U; measurement.observation[0] = (float)step * 0.01f + 0.5f;
            TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
        }
        if (step > 15U && step - 15U <= 2000U && (step - 15U) % 50U == 0U)
        {
            measurement.group = 3U; measurement.measurement_us = measurement.receive_us - 15000ULL;
            measurement.sequence = UINT32_MAX - 10U + (step - 15U) / 50U;
            measurement.observation[0] = 1.0f + (float)(step - 15U) * 0.002f;
            TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
        }
        if (step > 30U && step - 30U <= 2000U && (step - 30U) % 100U == 0U)
        {
            measurement.group = 1U; measurement.measurement_us = measurement.receive_us - 30000ULL;
            measurement.sequence = UINT32_MAX - 3U + (step - 30U) / 100U;
            measurement.observation[0] = (float)(step - 30U) * 0.01f;
            TEST_CHECK(NavigationSf6_Update(&s_context, &measurement, &boundary) == NAV_SF6_OK);
        }
    }
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context, &s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[2], velocity, 1.0e-5f);
    TEST_CHECK_NEAR(s_snapshot.state[5], position, 1.0e-4f);
    TEST_CHECK(s_context.count == NAV_SF6_HISTORY_CAPACITY && s_context.event_count < NAV_SF6_EVENT_CAPACITY);
    printf("long_wrap vU=%g pU=%g independent_oracle_vU=%g pU=%g context_bytes=%u\n",
        (double)s_snapshot.state[2], (double)s_snapshot.state[5], (double)velocity, (double)position,
        (unsigned int)sizeof(s_context));
}

int main(int argc, char **argv)
{
    if (argc == 2)
    {
        const float gain[6] = {0.2f, 0.2f, 0.2f, 0.2f, 0.2f, 0.2f};
        if (NavigationSf6_Initialize(&s_context, gain, s_zero, 1000000ULL) != NAV_SF6_OK) { return 2; }
        if (strcmp(argv[1], "capacity") == 0) { s_context.first = NAV_SF6_HISTORY_CAPACITY; }
        else if (strcmp(argv[1], "state") == 0) { s_context.history[0].state[0] = NAN; }
        else if (strcmp(argv[1], "gain") == 0) { s_context.gain[0] = 1.01f; }
        else if (strcmp(argv[1], "history") == 0)
        {
            NavigationSf6Measurement measurement = {0};
            uint64_t boundary;
            if (NavigationSf6_Predict(&s_context, 1001000ULL, s_zero, 0.001f) != NAV_SF6_OK) { return 2; }
            s_context.history[0].state[0] = NAN;
            measurement.group = 2U; measurement.measurement_us = 1000000ULL;
            measurement.receive_us = 1001000ULL;
            (void)NavigationSf6_Update(&s_context, &measurement, &boundary);
            return 3; /* Corrupt historical state must fail-stop too. */
        }
        else { return 2; }
        (void)NavigationSf6_SnapshotGet(&s_context, &s_snapshot);
        return 3; /* The actual assertion trap must terminate this Host process. */
    }
    Test_GainEndpoints(); Test_DelayAndIndependentGroups(); Test_BoundsAndOutage();
    Test_NumericAtomicity(); Test_CrossGroupTemporalOracle();
    Test_FutureAndTimestampGroups(); Test_EventCapacityAndExpiryRecovery(); Test_LongWrapIndependentOracle();
    return Test_Finish("navigation_sf6");
}
