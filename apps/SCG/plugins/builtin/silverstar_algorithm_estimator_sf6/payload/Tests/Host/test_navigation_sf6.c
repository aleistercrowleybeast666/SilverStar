#include <float.h>
#include <string.h>
#include "navigation_sf6.h"
#include "test_common.h"

static NavigationSf6Context s_context;
static NavigationSf6Sample s_snapshot;
static const float s_zero[3] = {0.0f, 0.0f, 0.0f};
static const float s_gain[6] = {0.2f, 0.2f, 0.2f, 0.2f, 0.2f, 0.2f};

static void Test_GroupIsolation(void)
{
    const uint8_t first[5] = {3U,5U,0U,2U,5U};
    for (uint8_t group = 0U; group < 5U; group++)
    {
        uint64_t boundary = 0U;
        NavigationSf6Measurement m = {1000000ULL,1000000ULL,1U,group,{10.0f,20.0f}};
        TEST_CHECK(NavigationSf6_Initialize(&s_context,s_gain,s_zero,1000000ULL) == NAV_SF6_OK);
        TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK);
        TEST_CHECK(boundary == 1000000ULL);
        TEST_CHECK(NavigationSf6_SnapshotGet(&s_context,&s_snapshot) == NAV_SF6_OK);
        for (uint8_t axis = 0U; axis < 6U; axis++)
        {
            float expected = axis == first[group] ? 2.0f :
                ((group == 0U || group == 2U) && axis == first[group]+1U ? 4.0f : 0.0f);
            TEST_CHECK_NEAR(s_snapshot.state[axis],expected,1.0e-6f);
        }
    }
}

static void Test_ArrivalOrderAndPrediction(void)
{
    const float gains[6] = {1.0f,1.0f,1.0f,1.0f,1.0f,0.5f}, dv[3] = {0.1f,0.0f,0.0f};
    NavigationSf6Measurement m = {1105000ULL,1200000ULL,UINT32_MAX,2U,{5.0f,0.0f}};
    uint64_t boundary = 0U;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,gains,s_zero,1000000ULL) == NAV_SF6_OK);
    for (uint32_t step = 1U; step <= 20U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context,1000000ULL+step*10000ULL,dv,0.01f) == NAV_SF6_OK); }
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK);
    TEST_CHECK(boundary == 1200000ULL);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context,&s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[0],5.0f,1.0e-5f);
    TEST_CHECK_NEAR(s_snapshot.state[3],0.2f,1.0e-5f);
    m.group = 4U; m.measurement_us = 1200000ULL; m.observation[0] = 8.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK);
    m.group = 1U; m.measurement_us = 1100000ULL; m.observation[0] = 10.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_SnapshotGet(&s_context,&s_snapshot) == NAV_SF6_OK);
    TEST_CHECK_NEAR(s_snapshot.state[5],7.0f,1.0e-6f); /* arrival order: baro->4, GNSS->7 */
    TEST_CHECK(s_snapshot.state[2] == 0.0f); /* altitude cannot secretly change velocity */
    TEST_CHECK(NavigationSf6_Predict(&s_context,1210000ULL,s_zero,0.01f) == NAV_SF6_OK);
    m.group = 2U; m.sequence = 0U; m.measurement_us = 1210000ULL; m.receive_us = 1210000ULL;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK); /* sequence wraps */
}

static void Test_RejectionAtomicity(void)
{
    NavigationSf6Measurement m = {1000000ULL,1000000ULL,9U,2U,{2.0f,3.0f}};
    uint64_t boundary = UINT64_MAX;
    NavigationSf6Context before;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,s_gain,s_zero,1000000ULL) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK);
    before = s_context; boundary = UINT64_MAX;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_DUPLICATE);
    m.sequence = 8U; m.measurement_us++; m.receive_us++;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_INVALID_ARGUMENT); /* future */
    TEST_CHECK(NavigationSf6_Predict(&s_context,1001000ULL,s_zero,0.001f) == NAV_SF6_OK);
    before = s_context;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_DUPLICATE); /* reordered seq */
    m.sequence = 10U; m.measurement_us = 999999ULL; m.receive_us = 1001000ULL;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_STALE); /* pre-init */
    m.measurement_us = 1001001ULL;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_INVALID_ARGUMENT);
    m.measurement_us = 1001000ULL; m.observation[0] = NAN;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_INVALID_ARGUMENT);
    m.observation[0] = 2.0f; m.observation[1] = INFINITY;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_INVALID_ARGUMENT);
    m.group = 5U; m.observation[1] = 0.0f;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_INVALID_ARGUMENT);
    TEST_CHECK(memcmp(&before,&s_context,sizeof(before)) == 0 && boundary == UINT64_MAX);
    for (uint32_t step = 1U; step <= 26U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context,1001000ULL+step*20000ULL,s_zero,0.02f) == NAV_SF6_OK); }
    m.group = 4U; m.measurement_us = 1001000ULL; m.receive_us = 1521000ULL;
    before = s_context;
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_STALE);
    TEST_CHECK(memcmp(&before,&s_context,sizeof(before)) == 0);
}

static void Test_NumericAndGainEndpoints(void)
{
    float gains[6] = {1.0f,1.0f,1.0f,1.0f,1.0f,1.0f}, velocity[3] = {FLT_MAX,0.0f,0.0f};
    const float dv[3] = {FLT_MAX,0.0f,0.0f};
    NavigationSf6Measurement m = {1000000ULL,1000000ULL,1U,2U,{-FLT_MAX,0.0f}};
    uint64_t boundary = UINT64_MAX;
    NavigationSf6Context before;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,gains,velocity,1000000ULL) == NAV_SF6_OK);
    before = s_context;
    TEST_CHECK(NavigationSf6_Predict(&s_context,1001000ULL,dv,0.001f) == NAV_SF6_NUMERIC_ERROR);
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_NUMERIC_ERROR);
    TEST_CHECK(memcmp(&before,&s_context,sizeof(before)) == 0 && boundary == UINT64_MAX);
    gains[0] = 0.0f;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,gains,velocity,1000000ULL) == NAV_SF6_OK);
    TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK);
    TEST_CHECK(s_context.latest.state[0] == FLT_MAX && s_context.seen[2] == 1U);
    gains[0] = 1.01f;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,gains,s_zero,0U) == NAV_SF6_INVALID_ARGUMENT);
    gains[0] = NAN;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,gains,s_zero,0U) == NAV_SF6_INVALID_ARGUMENT);
}

static void Test_ConvergenceDropoutRecovery(void)
{
    const float velocity[3] = {5.0f,-4.0f,3.0f};
    NavigationSf6Measurement m = {0};
    uint64_t boundary = 0U;
    TEST_CHECK(NavigationSf6_Initialize(&s_context,s_gain,velocity,1000000ULL) == NAV_SF6_OK);
    /* Independent stationary oracle: each admitted axis error decays by 0.8. */
    for (uint32_t step = 1U; step <= 100U; step++)
    {
        m.measurement_us = 1000000ULL+step*10000ULL; m.receive_us = m.measurement_us; m.sequence = step;
        TEST_CHECK(NavigationSf6_Predict(&s_context,m.receive_us,s_zero,0.01f) == NAV_SF6_OK);
        for (uint8_t group = 0U; group < 5U; group++)
        { m.group = group; TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK); }
    }
    for (uint8_t axis = 0U; axis < 6U; axis++) { TEST_CHECK(fabsf(s_context.latest.state[axis]) < 1.0e-6f); }
    /* Constant finite bias over a finite dropout is bounded in this test; then
     * valid stationary measurements restore convergence. No universal claim. */
    const float bias[3] = {0.01f,0.0f,0.0f};
    for (uint32_t step = 1U; step <= 200U; step++)
    { TEST_CHECK(NavigationSf6_Predict(&s_context,2000000ULL+step*10000ULL,bias,0.01f) == NAV_SF6_OK); }
    TEST_CHECK_NEAR(s_context.latest.state[0],2.0f,1.0e-5f);
    for (uint32_t step = 1U; step <= 100U; step++)
    {
        m.measurement_us = 4000000ULL+step*10000ULL; m.receive_us = m.measurement_us; m.sequence = 100U+step;
        TEST_CHECK(NavigationSf6_Predict(&s_context,m.receive_us,s_zero,0.01f) == NAV_SF6_OK);
        for (uint8_t group = 0U; group < 5U; group++)
        { m.group = group; TEST_CHECK(NavigationSf6_Update(&s_context,&m,&boundary) == NAV_SF6_OK); }
    }
    for (uint8_t axis = 0U; axis < 6U; axis++) { TEST_CHECK(fabsf(s_context.latest.state[axis]) < 1.0e-6f); }
    printf("current_state_revision=2 context_bytes=%u finite_stationary_and_dropout_recovery=PASS\n",(unsigned int)sizeof(s_context));
}

int main(int argc, char **argv)
{
    if (argc == 2)
    {
        if (NavigationSf6_Initialize(&s_context,s_gain,s_zero,1000000ULL) != NAV_SF6_OK) { return 2; }
        if (strcmp(argv[1],"capacity") == 0) { s_context.seen[0] = 2U; }
        else if (strcmp(argv[1],"state") == 0) { s_context.latest.state[0] = NAN; }
        else if (strcmp(argv[1],"gain") == 0) { s_context.gain[0] = 1.01f; }
        else if (strcmp(argv[1],"history") == 0) { s_context.epoch_us++; }
        else { return 2; }
        (void)NavigationSf6_SnapshotGet(&s_context,&s_snapshot);
        return 3;
    }
    Test_GroupIsolation(); Test_ArrivalOrderAndPrediction(); Test_RejectionAtomicity();
    Test_NumericAndGainEndpoints(); Test_ConvergenceDropoutRecovery();
    return Test_Finish("navigation_sf6_current_state");
}
