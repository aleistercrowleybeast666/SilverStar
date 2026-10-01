/* Host-only differential evidence. No fixture code enters target firmware. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#if defined(_WIN32)
#include <windows.h>
#endif
#include "navigation_eskf_replay.h"

static const NavigationEskfConfig s_config = {
    9.80665f, 0.002f, 0.02f, 0.0001f, 0.001f,
    {6.0f, 9.0f}, {20.0f, 25.0f}, 4.0f
};
static NavigationEskfState s_state[2], s_reference[2];
static NavigationEskfWorkspace s_work[2], s_reference_work[2];
static NavigationEskfReplay s_history[2], s_reference_history[2];
static NavigationEskfHistoryInput s_body[2][NAV_ESKF_HISTORY_CAPACITY];
static NavigationEskfHistoryInput s_reference_body[2][NAV_ESKF_HISTORY_CAPACITY];

static void Test_FloatEmit(float value)
{
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    printf(",%08lx", (unsigned long)bits);
}

static void Test_StateEmit(const NavigationEskfState *state)
{
    uint32_t i, j;
    printf("STATE,%llu,%lu,%lu,%u", (unsigned long long)state->timestamp_us,
        (unsigned long)state->source, (unsigned long)state->generation, state->initialized);
    for (i = 0U; i < 3U; i++) { Test_FloatEmit(state->position[i]); }
    for (i = 0U; i < 3U; i++) { Test_FloatEmit(state->velocity[i]); }
    for (i = 0U; i < 4U; i++) { Test_FloatEmit(state->quaternion[i]); }
    for (i = 0U; i < 3U; i++) { Test_FloatEmit(state->gyro_bias[i]); }
    for (i = 0U; i < 3U; i++) { Test_FloatEmit(state->accel_bias[i]); }
    for (i = 0U; i < NAV_ESKF_DIM; i++)
    { for (j = 0U; j < NAV_ESKF_DIM; j++) { Test_FloatEmit(state->covariance[i][j]); } }
    putchar('\n');
}

static void Test_OutcomeEmit(const NavigationEskfOutcome *outcome)
{
    printf("OUTCOME,%u,%u", outcome->dimension, (unsigned)outcome->result);
    Test_FloatEmit(outcome->nis); Test_FloatEmit(outcome->r_scale);
    Test_FloatEmit(outcome->innovation[0]); Test_FloatEmit(outcome->innovation[1]);
    Test_FloatEmit(outcome->effective_variance[0]); Test_FloatEmit(outcome->effective_variance[1]);
    Test_FloatEmit(outcome->gain_norm); putchar('\n');
}

static void Test_Initialize(NavigationEskfState *state, NavigationEskfWorkspace *work,
    NavigationEskfReplay *history, NavigationEskfHistoryInput *body, uint32_t instance)
{
    float nominal[16] = {0.0f};
    nominal[6] = 1.0f;
    memset(work->f, 0, sizeof(work->f));
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++) { work->f[i][i] = 1.0f + 0.1f * (float)i; }
    assert(NavigationEskf_Initialize(state, work, nominal,
        (const float (*)[NAV_ESKF_DIM])work->f, 1000000ULL, instance + 1U, 7U) == NAV_ESKF_OK);
    assert(NavigationEskfReplay_Reset(history, state, body) == NAV_ESKF_REPLAY_OK);
}

static void Test_Rotation(float t, uint8_t rotating, float rotation[3][3])
{
    float axis[3] = {0.25f, -0.1f, 0.3f};
    float norm = sqrtf(0.1625f);
    float half = rotating ? 0.5f * norm * t : 0.0f;
    float factor = sinf(half) / norm;
    float w = cosf(half), x = factor * axis[0], y = factor * axis[1], z = factor * axis[2];
    rotation[0][0] = 1.0f - 2.0f * (y*y + z*z);
    rotation[0][1] = 2.0f * (x*y - w*z); rotation[0][2] = 2.0f * (x*z + w*y);
    rotation[1][0] = 2.0f * (x*y + w*z); rotation[1][1] = 1.0f - 2.0f * (x*x + z*z);
    rotation[1][2] = 2.0f * (y*z - w*x); rotation[2][0] = 2.0f * (x*z - w*y);
    rotation[2][1] = 2.0f * (y*z + w*x); rotation[2][2] = 1.0f - 2.0f * (x*x + y*y);
}

static NavigationEskfBodyInput Test_Input(const NavigationEskfState *state,
    uint32_t step, uint8_t rotating, uint8_t moving)
{
    NavigationEskfBodyInput input = {0};
    float force[3] = {moving ? 0.1f : 0.0f, moving ? 0.02f : 0.0f, 9.80665f};
    input.dt_s = 0.005f; input.start_us = state->timestamp_us;
    input.end_us = input.start_us + 5000ULL;
    input.source = state->source; input.generation = state->generation;
    for (uint32_t half = 0U; half < 2U; half++)
    {
        float rotation[3][3];
        float t = ((float)(step - 1U) + 0.25f + 0.5f * (float)half) * input.dt_s;
        Test_Rotation(t, rotating, rotation);
        input.gyro_radps[half][0] = rotating ? 0.25f : 0.0f;
        input.gyro_radps[half][1] = rotating ? -0.1f : 0.0f;
        input.gyro_radps[half][2] = rotating ? 0.3f : 0.0f;
        for (uint32_t axis = 0U; axis < 3U; axis++)
        { for (uint32_t i = 0U; i < 3U; i++) { input.accel_mps2[half][axis] += rotation[i][axis] * force[i]; } }
    }
    return input;
}

static void Test_Event(NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *work, uint32_t step, uint8_t group, uint8_t moving, uint8_t emit)
{
    NavigationEskfReplayEvent event = {0};
    NavigationEskfOutcome outcome = {0};
    NavigationEskfReplayResult result;
    float t;
    event.measurement_us = state->timestamp_us - 20000ULL;
    event.receive_us = state->timestamp_us;
    event.sequence = step * 8U + group;
    event.source = state->source; event.generation = state->generation;
    event.measurement.group = group; event.measurement.physically_valid = 1U;
    event.measurement.variance[0] = 0.5f; event.measurement.variance[1] = 0.5f;
    t = (float)(event.measurement_us - 1000000ULL) * 1.0e-6f;
    if (group == 0U)
    { event.measurement.observation[0] = moving ? 0.05f*t*t : 0.0f;
      event.measurement.observation[1] = moving ? 0.01f*t*t : 0.0f; }
    if (group == 2U)
    { event.measurement.observation[0] = moving ? 0.1f*t : 0.0f;
      event.measurement.observation[1] = moving ? 0.02f*t : 0.0f; }
    result = NavigationEskfReplay_Insert(history, state, work, &s_config, &event, &outcome);
    assert(result == NAV_ESKF_REPLAY_OK);
    assert(outcome.result == NAV_ESKF_OK || outcome.result == NAV_ESKF_SOFT_WEIGHTED);
    if (emit) { printf("EVENT,%lu,%u,%u\n", (unsigned long)step, group, result); Test_OutcomeEmit(&outcome); }
}

static void Test_Simulate(NavigationEskfState *state, NavigationEskfWorkspace *work,
    NavigationEskfReplay *history, uint8_t rotating, uint8_t moving, uint8_t outage, uint8_t emit)
{
    for (uint32_t step = 1U; step <= 240U; step++)
    {
        NavigationEskfBodyInput input = Test_Input(state, step, rotating, moving);
        assert(NavigationEskfReplay_Predict(history, state, work, &s_config, &input) == NAV_ESKF_REPLAY_OK);
        if ((step % 20U == 0U) && !(outage && step >= 80U && step <= 160U))
        { Test_Event(history, state, work, step, (uint8_t)((step / 20U - 1U) % 4U), moving, emit); }
        if (step % 15U == 0U) { Test_Event(history, state, work, step, 4U, moving, emit); }
        if (emit)
        {
            printf("STEP,%lu,%u,%u,%lu,%lu,%lu\n", (unsigned long)step, history->body_count,
                history->event_count, (unsigned long)history->replay_count,
                (unsigned long)history->last_steps, (unsigned long)history->maximum_steps);
            Test_StateEmit(state); Test_StateEmit(&history->anchor); Test_StateEmit(&history->working);
        }
    }
}

static void Test_Aliases(void)
{
    float nominal[16] = {0.0f};
    float expected[NAV_ESKF_DIM][NAV_ESKF_DIM] = {{0.0f}};
    nominal[6] = 1.0f;
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++) { expected[i][i] = 1.0f + 0.1f * (float)i; }
    for (uint32_t which = 0U; which < 4U; which++)
    {
        const float (*covariance)[NAV_ESKF_DIM];
        if (which == 0U) { memcpy(s_work[0].f, expected, sizeof(expected)); covariance = (const float (*)[NAV_ESKF_DIM])s_work[0].f; }
        else if (which == 1U) { memcpy(s_work[0].candidate_p, expected, sizeof(expected)); covariance = (const float (*)[NAV_ESKF_DIM])s_work[0].candidate_p; }
        else if (which == 2U) { memcpy(s_work[0].transition, expected, sizeof(expected)); covariance = (const float (*)[NAV_ESKF_DIM])s_work[0].transition; }
        else { memcpy(s_state[0].covariance, expected, sizeof(expected)); covariance = (const float (*)[NAV_ESKF_DIM])s_state[0].covariance; }
        memcpy(s_work[0].candidate_x, nominal, sizeof(nominal));
        assert(NavigationEskf_Initialize(&s_state[0], &s_work[0], s_work[0].candidate_x,
            covariance, 1000000ULL, 1U, 7U) == NAV_ESKF_OK);
        assert(memcmp(s_state[0].covariance, expected, sizeof(expected)) == 0);
        assert(s_state[0].quaternion[0] == 1.0f);
        printf("ALIAS,%lu\n", (unsigned long)which); Test_StateEmit(&s_state[0]);
    }
}

static void Test_Faults(void)
{
    NavigationEskfState saved;
    NavigationEskfOutcome outcome;
    NavigationEskfMeasurement measurement = {0};
    Test_Initialize(&s_state[0], &s_work[0], &s_history[0], s_body[0], 0U);
    for (uint32_t fault = 0U; fault < 10U; fault++)
    {
        NavigationEskfBodyInput input = Test_Input(&s_state[0], 1U, 0U, 0U);
        if (fault == 0U) { input.start_us++; }
        if (fault == 1U) { input.end_us = input.start_us; }
        if (fault == 2U) { input.dt_s = 0.0f; }
        if (fault == 3U) { input.dt_s = 0.03f; }
        if (fault == 4U) { input.source++; }
        if (fault == 5U) { input.generation++; }
        if (fault == 6U) { input.gyro_radps[0][0] = NAN; }
        if (fault == 7U) { input.quality_flags = 0x02U; }
        if (fault == 8U) { s_state[0].covariance[0][0] = -1.0f; }
        if (fault == 9U) { s_state[0].covariance[0][0] = NAN; }
        saved = s_state[0];
        NavigationEskfResult result = NavigationEskf_Predict(&s_state[0], &s_work[0], &s_config, &input);
        assert(result == (fault >= 8U ? NAV_ESKF_NUMERIC_ERROR : NAV_ESKF_INVALID_INPUT));
        assert(memcmp(&saved, &s_state[0], sizeof(saved)) == 0);
        printf("FAULT,%lu,%u\n", (unsigned long)fault, result); Test_StateEmit(&s_state[0]);
        Test_Initialize(&s_state[0], &s_work[0], &s_history[0], s_body[0], 0U);
    }
    for (uint32_t fault = 0U; fault < 5U; fault++)
    {
        memset(&measurement, 0, sizeof(measurement));
        measurement.group = 1U; measurement.physically_valid = 1U;
        measurement.variance[0] = 0.5f;
        if (fault == 0U) { measurement.physically_valid = 0U; }
        if (fault == 1U) { measurement.group = 5U; }
        if (fault == 2U) { measurement.variance[0] = NAN; }
        if (fault == 3U) { measurement.observation[0] = 10000.0f; }
        if (fault == 4U) { measurement.observation[0] = 4.0f; }
        saved = s_state[0];
        NavigationEskfResult result = NavigationEskf_Update(&s_state[0], &s_work[0], &s_config, &measurement, &outcome);
        assert(result == (fault < 3U ? NAV_ESKF_INVALID_INPUT : fault == 3U ? NAV_ESKF_REJECTED_NIS : NAV_ESKF_SOFT_WEIGHTED));
        if (fault < 4U) { assert(memcmp(&saved, &s_state[0], sizeof(saved)) == 0); }
        printf("MEASUREMENT_FAULT,%lu,%u\n", (unsigned long)fault, result);
        Test_OutcomeEmit(&outcome); Test_StateEmit(&s_state[0]);
    }
    saved = s_state[0]; s_history[0].body_count = NAV_ESKF_HISTORY_CAPACITY + 1U;
    NavigationEskfBodyInput input = Test_Input(&s_state[0], 1U, 0U, 0U);
    assert(NavigationEskfReplay_Predict(&s_history[0], &s_state[0], &s_work[0], &s_config, &input) == NAV_ESKF_REPLAY_INVALID);
    assert(memcmp(&saved, &s_state[0], sizeof(saved)) == 0);
    s_history[0].body_count = 0U;
    s_state[0].timestamp_us = UINT64_MAX - 4999ULL;
    input = Test_Input(&s_state[0], 1U, 0U, 0U); input.end_us = UINT64_MAX; input.dt_s = 0.004999f;
    assert(NavigationEskf_Predict(&s_state[0], &s_work[0], &s_config, &input) == NAV_ESKF_OK);
    saved = s_state[0]; input.start_us = UINT64_MAX; input.end_us = 0U;
    assert(NavigationEskf_Predict(&s_state[0], &s_work[0], &s_config, &input) == NAV_ESKF_INVALID_INPUT);
    assert(memcmp(&saved, &s_state[0], sizeof(saved)) == 0);
    Test_StateEmit(&s_state[0]);
}

#if defined(_WIN32)
static DWORD WINAPI Test_Worker(void *argument)
{
    uint32_t instance = *(const uint32_t *)argument;
    Test_Simulate(&s_state[instance], &s_work[instance], &s_history[instance], 1U, 1U, 1U, 0U);
    return 0U;
}
static void Test_Concurrent(void)
{
    HANDLE threads[2]; uint32_t ids[2] = {0U, 1U};
    for (uint32_t i = 0U; i < 2U; i++)
    {
        Test_Initialize(&s_state[i], &s_work[i], &s_history[i], s_body[i], i);
        Test_Initialize(&s_reference[i], &s_reference_work[i], &s_reference_history[i], s_reference_body[i], i);
        threads[i] = CreateThread(NULL, 0U, Test_Worker, &ids[i], 0U, NULL);
        assert(threads[i] != NULL);
    }
    for (uint32_t i = 0U; i < 2U; i++)
    {
        assert(WaitForSingleObject(threads[i], 30000U) == WAIT_OBJECT_0);
        assert(CloseHandle(threads[i]) != 0);
        Test_Simulate(&s_reference[i], &s_reference_work[i], &s_reference_history[i], 1U, 1U, 1U, 0U);
        assert(memcmp(&s_state[i], &s_reference[i], sizeof(s_state[i])) == 0);
        Test_StateEmit(&s_state[i]);
    }
}
#endif

int main(int argc, char **argv)
{
    clock_t start = clock();
    assert(argc == 2);
    if (strcmp(argv[1], "size") == 0) { printf("%lu\n", (unsigned long)sizeof(NavigationEskfWorkspace)); return 0; }
    if (strcmp(argv[1], "aliases") == 0) { Test_Aliases(); return 0; }
    if (strcmp(argv[1], "faults") == 0) { Test_Faults(); return 0; }
#if defined(_WIN32)
    if (strcmp(argv[1], "concurrent") == 0) { Test_Concurrent(); return 0; }
#endif
    Test_Initialize(&s_state[0], &s_work[0], &s_history[0], s_body[0], 0U);
    uint8_t rotating = (uint8_t)(strcmp(argv[1], "stationary") != 0);
    uint8_t moving = (uint8_t)(strcmp(argv[1], "motion") == 0 || strcmp(argv[1], "outage") == 0 || strcmp(argv[1], "benchmark") == 0);
    Test_Simulate(&s_state[0], &s_work[0], &s_history[0], rotating, moving,
        (uint8_t)(strcmp(argv[1], "outage") == 0 || strcmp(argv[1], "benchmark") == 0),
        (uint8_t)(strcmp(argv[1], "benchmark") != 0));
    if (strcmp(argv[1], "benchmark") == 0)
    { Test_StateEmit(&s_state[0]); fprintf(stderr, "BENCH_CPU_SECONDS=%.6f\n", (double)(clock() - start) / CLOCKS_PER_SEC); }
    return 0;
}
