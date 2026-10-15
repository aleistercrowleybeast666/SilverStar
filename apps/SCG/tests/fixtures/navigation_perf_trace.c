/* Host-only bitwise differential, including full dense P and diagnostics. */
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "navigation_eskf.h"
#include "navigation_kf.h"
#include "ins_mechanization.h"
#include "baseline_api.h"

void NavPerf_EskfReset(NavigationEskfWorkspace *work);
void Baseline_NavPerf_EskfReset(NavigationEskfWorkspace *work);

static const NavigationEskfConfig s_config = {
    .gravity_mps2 = 9.80665f, .gyro_noise_density = 0.002f,
    .accel_noise_density = 0.02f, .gyro_bias_rw = 0.0001f,
    .accel_bias_rw = 0.001f, .nis_soft = {6.0f, 9.0f},
    .nis_hard = {20.0f, 25.0f}, .maximum_r_scale = 4.0f
};
static NavigationEskfState s_state[2];
static NavigationEskfWorkspace s_work[2];
static uint32_t s_seed = 0x513a71U;
static uint32_t s_comparisons;

static float Test_Random(void)
{
    s_seed = 1664525U * s_seed + 1013904223U;
    return (float)(s_seed >> 8) * (1.0f / 16777216.0f) - 0.5f;
}

static void Test_Equal(const void *a, const void *b, size_t size)
{
    if (memcmp(a, b, size) != 0)
    {
        const unsigned char *lhs = a, *rhs = b;
        for (size_t i = 0; i < size; ++i)
        {
            if (lhs[i] != rhs[i])
            {
                fprintf(stderr, "comparison=%lu byte=%lu before=%02x after=%02x\n",
                    (unsigned long)s_comparisons, (unsigned long)i, lhs[i], rhs[i]);
                break;
            }
        }
        assert(memcmp(a, b, size) == 0);
    }
    ++s_comparisons;
}

static void Test_Spd(float out[15][15], float scale)
{
    float l[15][15] = {{0}};
    for (uint32_t i = 0; i < 15; ++i)
    {
        for (uint32_t j = 0; j <= i; ++j)
        { l[i][j] = (i == j ? 1.0f + (float)i * 0.03f : Test_Random() * 0.2f) * scale; }
    }
    for (uint32_t i = 0; i < 15; ++i)
    {
        for (uint32_t j = 0; j <= i; ++j)
        {
            float sum = 0;
            for (uint32_t k = 0; k < 15; ++k) { sum += l[i][k] * l[j][k]; }
            out[i][j] = sum; out[j][i] = sum;
        }
    }
}

static void Test_Init(void)
{
    float p[15][15];
    float x[16] = {0};
    x[6] = 1.0f;
    Test_Spd(p, 1.0f);
    memset(s_state, 0, sizeof(s_state));
    memset(s_work, 0, sizeof(s_work));
    assert(Baseline_NavigationEskf_Initialize(&s_state[0], &s_work[0], x,
        (const float (*)[15])p, 1000000ULL, 1U, 7U) == NAV_ESKF_OK);
    assert(NavigationEskf_Initialize(&s_state[1], &s_work[1], x,
        (const float (*)[15])p, 1000000ULL, 1U, 7U) == NAV_ESKF_OK);
    Test_Equal(&s_state[0], &s_state[1], sizeof(s_state[0]));
}

static NavigationEskfBodyInput Test_Input(uint32_t step)
{
    NavigationEskfBodyInput b = {0};
    b.dt_s = 0.005f;
    b.start_us = s_state[0].timestamp_us; b.end_us = b.start_us + 5000ULL;
    b.source = s_state[0].source; b.generation = s_state[0].generation;
    b.quality_flags = step % 71 == 0 ? 1U : 0U;
    for (uint32_t half = 0; half < 2; ++half)
    {
        for (uint32_t axis = 0; axis < 3; ++axis)
        {
            b.gyro_radps[half][axis] = Test_Random() * 0.03f;
            b.accel_mps2[half][axis] = Test_Random() * 0.06f +
                (axis == 2 ? 9.80665f : 0.0f);
        }
    }
    return b;
}

static NavigationEskfMeasurement Test_Measurement(uint32_t group)
{
    NavigationEskfMeasurement m = {0};
    m.group = (uint8_t)group; m.physically_valid = 1;
    m.variance[0] = 0.2f; m.variance[1] = 0.3f;
    m.lever_arm_b_m[0] = 0.1f; m.lever_arm_b_m[1] = -0.08f;
    m.lever_arm_b_m[2] = 0.03f;
    m.angular_rate_b_radps[0] = 0.03f; m.angular_rate_b_radps[1] = -0.02f;
    if (group == 0)
    { m.observation[0] = s_state[0].position[0]; m.observation[1] = s_state[0].position[1]; }
    else if (group == 1 || group == 4) { m.observation[0] = s_state[0].position[2]; }
    else if (group == 2)
    { m.observation[0] = s_state[0].velocity[0]; m.observation[1] = s_state[0].velocity[1]; }
    else { m.observation[0] = s_state[0].velocity[2]; }
    m.observation[0] += Test_Random() * 0.05f;
    m.observation[1] += Test_Random() * 0.05f;
    return m;
}

static void Test_Long(void)
{
    Test_Init();
    for (uint32_t step = 1; step <= 100000; ++step)
    {
        NavigationEskfBodyInput input = Test_Input(step);
        NavigationEskfResult a = Baseline_NavigationEskf_Predict(&s_state[0], &s_work[0], &s_config, &input);
        NavigationEskfResult b = NavigationEskf_Predict(&s_state[1], &s_work[1], &s_config, &input);
        assert(a == NAV_ESKF_OK && b == a);
        Test_Equal(&s_state[0], &s_state[1], sizeof(s_state[0]));
        if (step % 20 == 0)
        {
            for (uint32_t group = 0; group < 5; ++group)
            {
                NavigationEskfOutcome out[2] = {{0}};
                NavigationEskfMeasurement m = Test_Measurement(group);
                a = Baseline_NavigationEskf_Update(&s_state[0], &s_work[0], &s_config, &m, &out[0]);
                b = NavigationEskf_Update(&s_state[1], &s_work[1], &s_config, &m, &out[1]);
                assert((a == NAV_ESKF_OK || a == NAV_ESKF_SOFT_WEIGHTED) && b == a);
                Test_Equal(&out[0], &out[1], sizeof(out[0]));
                Test_Equal(&s_state[0], &s_state[1], sizeof(s_state[0]));
            }
        }
    }
}

static void Test_Dense(void)
{
    for (uint32_t trial = 0; trial < 4000; ++trial)
    {
        Test_Spd(s_work[0].candidate_p, powf(10.0f, (float)(trial % 13) - 6.0f));
        memset(s_work[0].correction, 0, sizeof(s_work[0].correction));
        for (uint32_t i = 6; i < 9; ++i)
        { s_work[0].correction[i] = Test_Random() * (trial % 2 ? 0.001f : 0.25f); }
        s_work[1] = s_work[0];
        Baseline_NavPerf_EskfReset(&s_work[0]); NavPerf_EskfReset(&s_work[1]);
        Test_Equal(s_work[0].candidate_p, s_work[1].candidate_p, sizeof(s_work[0].candidate_p));
    }
    for (uint32_t trial = 0; trial < 128; ++trial)
    {
        for (uint32_t i = 0; i < 15; ++i)
        {
            for (uint32_t j = 0; j < 15; ++j)
            {
                float v = trial % 4 == 0 ? 0.0f : trial % 4 == 1 ? -0.0f :
                    trial % 4 == 2 ? 0x1p-145f : -0x1p-145f;
                s_work[0].candidate_p[i][j] = i == j ? 1.0f : v;
            }
        }
        memset(s_work[0].correction, 0, sizeof(s_work[0].correction));
        s_work[0].correction[6] = trial < 64 ? -0.0f : 0.1f;
        s_work[1] = s_work[0];
        Baseline_NavPerf_EskfReset(&s_work[0]); NavPerf_EskfReset(&s_work[1]);
        Test_Equal(s_work[0].candidate_p, s_work[1].candidate_p, sizeof(s_work[0].candidate_p));
    }
}

static void Test_Faults(void)
{
    for (uint32_t fault = 0; fault < 24; ++fault)
    {
        Test_Init();
        NavigationEskfBodyInput input = Test_Input(1);
        NavigationEskfConfig config = s_config;
        if (fault == 0) { input.start_us++; }
        if (fault == 1) { input.dt_s = 0; }
        if (fault == 2) { input.gyro_radps[0][1] = NAN; }
        if (fault == 3) { input.accel_mps2[1][2] = INFINITY; }
        if (fault == 4) { input.quality_flags = 0x02U; }
        if (fault == 5) { config.nis_disabled_mask = 4U; }
        if (fault == 6) { config.accel_noise_density = FLT_MAX; }
        if (fault == 7) { config.gyro_noise_density = FLT_MAX; }
        if (fault >= 8)
        {
            uint32_t row = (fault - 8) % 15;
            s_state[0].covariance[row][row] = fault % 3 == 0 ? NAN : fault % 3 == 1 ? INFINITY : -1.0f;
        }
        s_state[1] = s_state[0];
        NavigationEskfState saved = s_state[0];
        NavigationEskfResult a = Baseline_NavigationEskf_Predict(&s_state[0], &s_work[0], &config, &input);
        NavigationEskfResult b = NavigationEskf_Predict(&s_state[1], &s_work[1], &config, &input);
        assert(a == b && a != NAV_ESKF_OK);
        Test_Equal(&saved, &s_state[0], sizeof(saved)); Test_Equal(&saved, &s_state[1], sizeof(saved));
    }
    for (uint32_t fault = 0; fault < 30; ++fault)
    {
        Test_Init();
        NavigationEskfMeasurement m = Test_Measurement(fault % 5);
        NavigationEskfOutcome outcome[2] = {{0}};
        if (fault < 5) { m.observation[0] = NAN; }
        else if (fault < 10) { m.variance[0] = -1.0f; }
        else if (fault < 15) { m.observation[0] = 1.0e9f; }
        else
        {
            uint32_t i = fault - 15;
            s_state[0].covariance[i][i] = fault % 2 ? NAN : INFINITY;
        }
        s_state[1] = s_state[0];
        NavigationEskfState saved = s_state[0];
        NavigationEskfResult a = Baseline_NavigationEskf_Update(&s_state[0], &s_work[0], &s_config, &m, &outcome[0]);
        NavigationEskfResult b = NavigationEskf_Update(&s_state[1], &s_work[1], &s_config, &m, &outcome[1]);
        assert(a == b && a != NAV_ESKF_OK && a != NAV_ESKF_SOFT_WEIGHTED);
        Test_Equal(&saved, &s_state[0], sizeof(saved)); Test_Equal(&saved, &s_state[1], sizeof(saved));
        Test_Equal(&outcome[0], &outcome[1], sizeof(outcome[0]));
    }
    /* Private reset kernels: every nonfinite entry still reaches final validation.
     * Compare classification for NaNs, whose payload/sign are not a contract. */
    for (uint32_t trial = 0; trial < 675; ++trial)
    {
        Test_Spd(s_work[0].candidate_p, 1.0f);
        s_work[0].candidate_p[trial % 15][(trial / 15) % 15] =
            trial < 225 ? NAN : trial < 450 ? INFINITY : FLT_MAX;
        memset(s_work[0].correction, 0, sizeof(s_work[0].correction));
        s_work[0].correction[6] = 0.2f;
        s_work[1] = s_work[0];
        Baseline_NavPerf_EskfReset(&s_work[0]); NavPerf_EskfReset(&s_work[1]);
        for (uint32_t i = 0; i < 15; ++i)
        {
            for (uint32_t j = 0; j < 15; ++j)
            {
                float a = s_work[0].candidate_p[i][j], b = s_work[1].candidate_p[i][j];
                assert((isnan(a) && isnan(b)) || (a == b && signbit(a) == signbit(b)));
            }
        }
    }
}

static void Test_Ins(void)
{
    InsMechanizationContext c[2];
    InsState state[2];
    float q[4] = {1, 0, 0, 0};
    Baseline_InsMechanization_Init(&c[0], 9.80665f); InsMechanization_Init(&c[1], 9.80665f);
    assert(Baseline_InsMechanization_ResetNavigationWithAttitude(&c[0], q));
    assert(InsMechanization_ResetNavigationWithAttitude(&c[1], q));
    for (uint32_t step = 0; step < 100000; ++step)
    {
        InsAlgorithmSample sample = {0};
        sample.timestamp_us = 1000000ULL + (uint64_t)step * 5000ULL;
        sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
        for (uint32_t axis = 0; axis < 3; ++axis)
        {
            sample.gyro_b_radps[axis] = Test_Random() * 0.1f;
            sample.accel_b_mps2[axis] = Test_Random() * 0.3f + (axis == 2 ? 9.80665f : 0);
        }
        if (step % 997 == 996) { sample.accel_b_mps2[0] = NAN; }
        if (step % 991 == 990) { sample.gyro_b_radps[0] = FLT_MAX; sample.gyro_b_radps[1] = FLT_MAX; }
        uint8_t a = Baseline_InsMechanization_Update(&c[0], &sample, &state[0]);
        uint8_t b = InsMechanization_Update(&c[1], &sample, &state[1]);
        assert(a == b);
        Test_Equal(&c[0], &c[1], sizeof(c[0])); Test_Equal(&state[0], &state[1], sizeof(state[0]));
    }
}

static void Test_Kf(void)
{
    NavigationKfContext c[2];
    float dense[15][15];
    float p[6][6];
    Test_Spd(dense, 1.0f);
    for (uint32_t i = 0; i < 6; ++i)
    { for (uint32_t j = 0; j < 6; ++j) { p[i][j] = dense[i][j]; } }
    Baseline_NavigationKf_Init(&c[0]); NavigationKf_Init(&c[1]);
    assert(Baseline_NavigationKf_ResetWithCovariance(&c[0], &p[0][0]));
    assert(NavigationKf_ResetWithCovariance(&c[1], &p[0][0]));
    for (uint32_t step = 0; step < 100000; ++step)
    {
        float dv[3], position[3], velocity[3], variance[3] = {0.3f, 0.4f, 0.7f};
        for (uint32_t i = 0; i < 3; ++i) { dv[i] = Test_Random() * 0.001f; }
        assert(Baseline_NavigationKf_Predict(&c[0], dv, 0.005f) ==
            NavigationKf_Predict(&c[1], dv, 0.005f));
        for (uint32_t i = 0; i < 3; ++i)
        { position[i] = c[0].state[i] + Test_Random() * 0.1f; velocity[i] = c[0].state[3+i] + Test_Random() * 0.01f; }
        if (step % 20 == 0)
        {
            assert(Baseline_NavigationKf_UpdateGnssPosition(&c[0], position, variance) ==
                NavigationKf_UpdateGnssPosition(&c[1], position, variance));
            assert(Baseline_NavigationKf_UpdateGnssVelocity3D(&c[0], velocity, variance) ==
                NavigationKf_UpdateGnssVelocity3D(&c[1], velocity, variance));
            assert(Baseline_NavigationKf_UpdateBaroAltitude(&c[0], position[2], variance[2]) ==
                NavigationKf_UpdateBaroAltitude(&c[1], position[2], variance[2]));
        }
        Test_Equal(&c[0], &c[1], sizeof(c[0]));
    }
}

static void Test_Benchmark(void)
{
    float p[15][15];
    volatile float checksum = 0;
    double elapsed[2];
    Test_Spd(p, 1.0f);
    for (uint32_t version = 0; version < 2; ++version)
    {
        memset(&s_work[version], 0, sizeof(s_work[version]));
        s_work[version].correction[6] = 0.05f;
        s_work[version].correction[7] = -0.1f;
        clock_t start = clock();
        for (uint32_t step = 0; step < 100000; ++step)
        {
            memcpy(s_work[version].candidate_p, p, sizeof(p));
            if (version == 0) { Baseline_NavPerf_EskfReset(&s_work[version]); }
            else { NavPerf_EskfReset(&s_work[version]); }
            checksum += s_work[version].candidate_p[7][6];
        }
        elapsed[version] = (double)(clock() - start) / CLOCKS_PER_SEC;
    }
    printf("Host reset kernel seconds baseline=%.6f current=%.6f checksum=%.9g\n",
        elapsed[0], elapsed[1], (double)checksum);
    for (uint32_t trial = 0; trial < 5; ++trial)
    {
        for (uint32_t order = 0; order < 2; ++order)
        {
            uint32_t version = (order + trial) % 2;
            s_seed = 0x513a71U + trial;
            Test_Init();
            NavigationEskfState saved = s_state[version];
            NavigationEskfMeasurement m = Test_Measurement(0);
            NavigationEskfOutcome outcome;
            clock_t start = clock();
            for (uint32_t step = 0; step < 10000; ++step)
            {
                s_state[version] = saved;
                NavigationEskfResult result = version == 0 ?
                    Baseline_NavigationEskf_Update(&s_state[version], &s_work[version], &s_config, &m, &outcome) :
                    NavigationEskf_Update(&s_state[version], &s_work[version], &s_config, &m, &outcome);
                assert(result == NAV_ESKF_OK);
                checksum += s_state[version].covariance[0][0];
            }
            elapsed[version] = (double)(clock() - start) / CLOCKS_PER_SEC;
        }
        printf("Host full ESKF update sample=%lu baseline=%.6f current=%.6f\n",
            (unsigned long)trial, elapsed[0], elapsed[1]);
    }
    for (uint32_t trial = 0; trial < 5; ++trial)
    {
        for (uint32_t order = 0; order < 2; ++order)
        {
            uint32_t version = (order + trial) % 2;
            InsMechanizationContext context;
            InsState state;
            InsAlgorithmSample sample = {0};
            float q[4] = {1, 0, 0, 0};
            if (version == 0)
            {
                Baseline_InsMechanization_Init(&context, 9.80665f);
                assert(Baseline_InsMechanization_ResetNavigationWithAttitude(&context, q));
            }
            else
            {
                InsMechanization_Init(&context, 9.80665f);
                assert(InsMechanization_ResetNavigationWithAttitude(&context, q));
            }
            sample.accel_b_mps2[2] = 9.80665f;
            sample.gyro_b_radps[0] = 0.003f; sample.gyro_b_radps[1] = -0.002f;
            sample.valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
            clock_t start = clock();
            for (uint32_t step = 0; step < 1000000; ++step)
            {
                sample.timestamp_us = 1000000ULL + (uint64_t)step * 5000ULL;
                uint8_t result = version == 0 ?
                    Baseline_InsMechanization_Update(&context, &sample, &state) :
                    InsMechanization_Update(&context, &sample, &state);
                if (result) { checksum += state.delta_theta_b_coning_corrected[0]; }
            }
            elapsed[version] = (double)(clock() - start) / CLOCKS_PER_SEC;
        }
        printf("Host full INS update sample=%lu baseline=%.6f current=%.6f\n",
            (unsigned long)trial, elapsed[0], elapsed[1]);
    }
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    if (strcmp(argv[1], "dense") == 0) { Test_Dense(); }
    else if (strcmp(argv[1], "long") == 0) { Test_Long(); }
    else if (strcmp(argv[1], "faults") == 0) { Test_Faults(); }
    else if (strcmp(argv[1], "ins") == 0) { Test_Ins(); }
    else if (strcmp(argv[1], "kf") == 0) { Test_Kf(); }
    else if (strcmp(argv[1], "benchmark") == 0) { Test_Benchmark(); }
    else { assert(0); }
    printf("PASS %s comparisons=%lu\n", argv[1], (unsigned long)s_comparisons);
    return 0;
}
