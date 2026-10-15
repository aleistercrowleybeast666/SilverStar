/* Host-only API boundary fixture. No recovery policy or target integration. */
#include "navigation_eskf.h"

#include <stdint.h>
#include <string.h>

#define TEST_SENTINEL UINT64_C(0x73534b65726e656c)

typedef struct
{
    uint64_t before;
    NavigationEskfState value;
    uint64_t after;
} TestGuardedState;

typedef struct
{
    uint64_t before;
    NavigationEskfWorkspace value;
    uint64_t after;
} TestGuardedWorkspace;

static TestGuardedState s_state[2];
static TestGuardedWorkspace s_work[2];
static NavigationEskfState s_saved[2];
#if defined(TEST_COVARIANCE_SCALE_API)
static NavigationEskfWorkspace s_saved_work;
#endif

static void Test_StatePrepare(uint32_t slot, const float *covariance)
{
    NavigationEskfState *state = &s_state[slot].value;
    memset(&s_state[slot], 0, sizeof(s_state[slot]));
    memset(&s_work[slot], 0x5a, sizeof(s_work[slot]));
    s_state[slot].before = TEST_SENTINEL; s_state[slot].after = TEST_SENTINEL;
    s_work[slot].before = TEST_SENTINEL; s_work[slot].after = TEST_SENTINEL;
    state->position[0] = 7.0f; state->position[1] = -3.0f; state->position[2] = 2.0f;
    state->velocity[0] = 0.3f; state->velocity[1] = -0.1f;
    state->quaternion[0] = 1.0f;
    state->gyro_bias[1] = 0.001f; state->accel_bias[2] = -0.01f;
    memcpy(state->covariance, covariance, sizeof(state->covariance));
    state->timestamp_us = UINT64_C(1234567890123);
    state->source = 13U; state->generation = 29U; state->initialized = 1U;
}

/* Existing Update only: baseline trace is a limitation/input for later policy,
 * not evidence that a missing new API is an existing defect. No outage model. */
int Test_NisTrace(const float *covariance, float *nis, int *results, int *unchanged)
{
    const NavigationEskfConfig config = {
        .gravity_mps2 = 9.80665f, .gyro_noise_density = 0.002f,
        .accel_noise_density = 0.02f, .gyro_bias_rw = 0.0001f,
        .accel_bias_rw = 0.001f, .nis_soft = {6.0f, 9.0f},
        .nis_hard = {20.0f, 25.0f}, .maximum_r_scale = 4.0f
    };
    NavigationEskfMeasurement measurement = {0};
    NavigationEskfOutcome outcome = {0};
    Test_StatePrepare(0U, covariance);
    memcpy(&s_saved[0], &s_state[0].value, sizeof(s_saved[0]));
    measurement.group = 0U; measurement.physically_valid = 1U;
    measurement.variance[0] = 1.0f; measurement.variance[1] = 1.0f;
    for (uint32_t i = 0U; i < 8U; i++)
    {
        measurement.observation[0] = 1000.0f + (float)i;
        measurement.observation[1] = -1000.0f - (float)i;
        results[i] = (int)NavigationEskf_Update(&s_state[0].value, &s_work[0].value,
            &config, &measurement, &outcome);
        nis[i] = outcome.nis;
        unchanged[i] = memcmp(&s_saved[0], &s_state[0].value, sizeof(s_saved[0])) == 0;
    }
    return (int)NAV_ESKF_REJECTED_NIS;
}

#if defined(TEST_COVARIANCE_SCALE_API)
/* Keep the fixture independent of the public enum's numeric assignments. */
int Test_ScaleResult(uint32_t index)
{
    const NavigationEskfCovarianceScaleResult values[5] = {
        NAV_ESKF_COVARIANCE_SCALE_APPLIED, NAV_ESKF_COVARIANCE_SCALE_NO_CHANGE,
        NAV_ESKF_COVARIANCE_SCALE_AT_CAP, NAV_ESKF_COVARIANCE_SCALE_INVALID_ARGUMENT,
        NAV_ESKF_COVARIANCE_SCALE_NUMERIC_ERROR
    };
    return index < 5U ? (int)values[index] : -1;
}

/* flags: NULL state/work/scale/cap = bits 0..3; initialized=0/2 = bits 4/5;
 * scale/cap overlapping work/state = bits 6..9; scale/cap same array = bit 10.
 * Invariants: whole state, non-P state, non-scratch workspace, input arrays,
 * allocation guards, independent second pair. F/candidate_p remain scratch. */
int Test_ScaleRun(const float *covariance, const float *scale, const float *cap,
    uint32_t flags, float *output, int *invariants)
{
    float scales[NAV_ESKF_DIM], caps[NAV_ESKF_DIM];
    float saved_scale[NAV_ESKF_DIM], saved_cap[NAV_ESKF_DIM];
    const float *input_scale = scales, *input_cap = caps;
    NavigationEskfState non_p;
    NavigationEskfCovarianceScaleResult result;
    Test_StatePrepare(0U, covariance); Test_StatePrepare(1U, covariance);
    if ((flags & 16U) != 0U) { s_state[0].value.initialized = 0U; }
    if ((flags & 32U) != 0U) { s_state[0].value.initialized = 2U; }
    memcpy(scales, scale, sizeof(scales)); memcpy(caps, cap, sizeof(caps));
    if ((flags & 64U) != 0U)
    { memcpy(s_work[0].value.f[0], scales, sizeof(scales)); input_scale = s_work[0].value.f[0]; }
    if ((flags & 128U) != 0U)
    { memcpy(s_work[0].value.f[0], caps, sizeof(caps)); input_cap = s_work[0].value.f[0]; }
    if ((flags & 256U) != 0U)
    { memcpy(s_state[0].value.covariance[0], scales, sizeof(scales)); input_scale = s_state[0].value.covariance[0]; }
    if ((flags & 512U) != 0U)
    { memcpy(s_state[0].value.covariance[0], caps, sizeof(caps)); input_cap = s_state[0].value.covariance[0]; }
    if ((flags & 1024U) != 0U) { input_cap = input_scale; }
    memcpy(saved_scale, input_scale, sizeof(saved_scale)); memcpy(saved_cap, input_cap, sizeof(saved_cap));
    memcpy(&s_saved[0], &s_state[0].value, sizeof(s_saved[0]));
    memcpy(&s_saved[1], &s_state[1].value, sizeof(s_saved[1]));
    memcpy(&s_saved_work, &s_work[0].value, sizeof(s_saved_work));
    result = NavigationEskf_CovarianceScale(
        (flags & 1U) != 0U ? NULL : &s_state[0].value,
        (flags & 2U) != 0U ? NULL : &s_work[0].value,
        (flags & 4U) != 0U ? NULL : input_scale, (flags & 8U) != 0U ? NULL : input_cap);
    memcpy(output, s_state[0].value.covariance, sizeof(s_state[0].value.covariance));
    invariants[0] = memcmp(&s_saved[0], &s_state[0].value, sizeof(s_saved[0])) == 0;
    memcpy(&non_p, &s_state[0].value, sizeof(non_p));
    memcpy(non_p.covariance, s_saved[0].covariance, sizeof(non_p.covariance));
    invariants[1] = memcmp(&s_saved[0], &non_p, sizeof(non_p)) == 0;
    memcpy(s_saved_work.f, s_work[0].value.f, sizeof(s_saved_work.f));
    memcpy(s_saved_work.candidate_p, s_work[0].value.candidate_p, sizeof(s_saved_work.candidate_p));
    invariants[2] = memcmp(&s_saved_work, &s_work[0].value, sizeof(s_saved_work)) == 0;
    invariants[3] = memcmp(saved_scale, input_scale, sizeof(saved_scale)) == 0 &&
        memcmp(saved_cap, input_cap, sizeof(saved_cap)) == 0;
    invariants[4] = s_state[0].before == TEST_SENTINEL && s_state[0].after == TEST_SENTINEL &&
        s_work[0].before == TEST_SENTINEL && s_work[0].after == TEST_SENTINEL;
    invariants[5] = memcmp(&s_saved[1], &s_state[1].value, sizeof(s_saved[1])) == 0;
    /* Compare the second workspace to its original fill without treating any
     * field as persistent algorithm state. */
    const unsigned char *other_work = (const unsigned char *)&s_work[1].value;
    for (uint32_t i = 0U; i < sizeof(s_work[1].value); i++)
    { if (other_work[i] != 0x5aU) { invariants[5] = 0; } }
    return (int)result;
}
#endif
