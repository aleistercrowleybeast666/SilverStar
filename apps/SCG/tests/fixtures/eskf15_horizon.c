/* Host-only accessors. Production uses the actual owning horizon/kernel. */
#include "navigation_eskf_horizon.h"
#include <math.h>
#include <string.h>

static NavigationEskfHorizon s_horizon;
static NavigationEskfWorkspace s_workspace;
static NavigationEskfState s_output;
static NavigationEskfConfig s_config;

int Test_Reset(uint64_t start, uint64_t lag);
int Test_Body(uint64_t start, uint64_t end, float dt, const float raw[12],
    uint32_t source, uint32_t generation, uint32_t flags);
int Test_Insert(uint64_t source_us, uint64_t receive_us, uint32_t sequence,
    uint32_t source, uint32_t generation, uint32_t group, uint32_t valid,
    uint32_t operation, const float values[7]);
int Test_Advance(void);
int Test_Pop(uint32_t result[5], float values[8]);
void Test_Snapshot(float primary[241], float output[241], uint64_t times[4], uint32_t counts[9]);
void Test_Corrupt(uint32_t kind);
uint32_t Test_ContextSize(void);
uint32_t Test_Result(uint32_t index);
void Test_AccelerationGet(float value[3]);

int Test_Reset(uint64_t start, uint64_t lag)
{
    float nominal[16] = {0.0f};
    memset(&s_horizon, 0, sizeof(s_horizon));
    memset(&s_config, 0, sizeof(s_config));
    memset(&s_output, 0, sizeof(s_output));
    s_config.gravity_mps2 = 9.78f; s_config.gyro_noise_density = 0.003f;
    s_config.accel_noise_density = 0.08f; s_config.gyro_bias_rw = 0.0001f;
    s_config.accel_bias_rw = 0.001f; s_config.nis_soft[0] = 6.635f;
    s_config.nis_soft[1] = 9.21f; s_config.nis_hard[0] = 10.828f;
    s_config.nis_hard[1] = 13.816f; s_config.maximum_r_scale = 4.0f;
    nominal[6] = 1.0f;
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++)
    {
        for (uint32_t j = 0U; j < NAV_ESKF_DIM; j++)
        { s_workspace.candidate_p[i][j] = (i == j) ? 1.0f : 0.0f; }
    }
    if (NavigationEskf_Initialize(&s_output, &s_workspace, nominal,
        (const float (*)[NAV_ESKF_DIM])s_workspace.candidate_p, start, 0U, 1U) != NAV_ESKF_OK)
    { return -1; }
    return (int)NavigationEskfHorizon_Reset(&s_horizon, &s_output, &s_workspace, &s_config, lag);
}

int Test_Body(uint64_t start, uint64_t end, float dt, const float raw[12],
    uint32_t source, uint32_t generation, uint32_t flags)
{
    NavigationEskfBodyInput input;
    memset(&input, 0, sizeof(input));
    input.start_us = start; input.end_us = end; input.dt_s = dt;
    input.source = source; input.generation = generation; input.quality_flags = flags;
    memcpy(input.gyro_radps, raw, 6U * sizeof(float));
    memcpy(input.accel_mps2, raw + 6, 6U * sizeof(float));
    return (int)NavigationEskfHorizon_BodyReceive(&s_horizon, &input);
}

int Test_Insert(uint64_t source_us, uint64_t receive_us, uint32_t sequence,
    uint32_t source, uint32_t generation, uint32_t group, uint32_t valid,
    uint32_t operation, const float values[7])
{
    NavigationEskfHorizonEvent input;
    memset(&input, 0, sizeof(input));
    input.event.measurement_us = source_us; input.event.receive_us = receive_us;
    input.event.sequence = sequence; input.event.source = source; input.event.generation = generation;
    input.event.measurement.group = (uint8_t)group; input.event.measurement.physically_valid = (uint8_t)valid;
    memcpy(input.event.measurement.observation, values, 2U * sizeof(float));
    memcpy(input.event.measurement.variance, values + 2, 2U * sizeof(float));
    memcpy(input.event.measurement.lever_arm_b_m, values + 4, 3U * sizeof(float));
    input.sample_us = source_us; input.operation_sequence = operation;
    input.quality_scale = 1.0f; input.consistency_scale = 1.0f;
    memcpy(input.base_variance, values + 2, 2U * sizeof(float));
    return (int)NavigationEskfHorizon_Insert(&s_horizon, &input);
}

int Test_Advance(void)
{
    return (int)NavigationEskfHorizon_Advance(&s_horizon, &s_output, &s_workspace, &s_config);
}

int Test_Pop(uint32_t result[5], float values[8])
{
    NavigationEskfHorizonEvent event;
    NavigationEskfHorizonResult status = NavigationEskfHorizon_CompletionPop(&s_horizon, &event);
    if (status != NAV_ESKF_HORIZON_OK) { return (int)status; }
    result[0] = event.operation_sequence; result[1] = event.event.sequence;
    result[2] = event.event.measurement.group; result[3] = event.event.source;
    result[4] = (uint32_t)event.outcome.result;
    values[0] = event.outcome.nis; values[1] = event.outcome.r_scale;
    memcpy(values + 2, event.outcome.innovation, 2U * sizeof(float));
    memcpy(values + 4, event.outcome.effective_variance, 2U * sizeof(float));
    values[6] = event.outcome.gain_norm; values[7] = (float)event.outcome.dimension;
    return (int)status;
}

static void Test_StateCopy(const NavigationEskfState *state, float values[241])
{
    memcpy(values, state->position, 3U * sizeof(float));
    memcpy(values + 3, state->velocity, 3U * sizeof(float));
    memcpy(values + 6, state->quaternion, 4U * sizeof(float));
    memcpy(values + 10, state->gyro_bias, 3U * sizeof(float));
    memcpy(values + 13, state->accel_bias, 3U * sizeof(float));
    memcpy(values + 16, state->covariance, 225U * sizeof(float));
}

void Test_Snapshot(float primary[241], float output[241], uint64_t times[4], uint32_t counts[9])
{
    Test_StateCopy(&s_horizon.primary, primary); Test_StateCopy(&s_output, output);
    times[0] = s_horizon.primary.timestamp_us; times[1] = s_output.timestamp_us;
    times[2] = s_horizon.present_us; times[3] = s_horizon.body_start_us;
    counts[0] = s_horizon.body_count; counts[1] = s_horizon.event_count;
    counts[2] = s_horizon.completion_count; counts[3] = s_horizon.faulted;
    counts[4] = s_horizon.warmup; counts[5] = s_horizon.last_work;
    counts[6] = s_horizon.maximum_work; counts[7] = s_horizon.late_count;
    counts[8] = s_horizon.capacity_count;
}

void Test_Corrupt(uint32_t kind)
{
    if (kind == 1U) { s_horizon.primary.covariance[0][0] = -1.0f; }
    if (kind == 2U) { s_horizon.body[s_horizon.body_head].accel_mps2[1][0] = NAN; }
    if (kind == 3U) { s_horizon.body_count = NAV_ESKF_HORIZON_BODY_CAPACITY + 1U; }
    if (kind == 4U) { s_horizon.event_count = NAV_ESKF_HORIZON_EVENT_CAPACITY + 1U; }
    if (kind == 5U) { s_horizon.completion_read = NAV_ESKF_HORIZON_EVENT_CAPACITY; }
    if (kind == 6U) { s_config.accel_noise_density *= 2.0f; }
    if (kind == 7U) { s_output.position[0] = 12345.0f; s_output.covariance[0][0] = -1.0f; }
    if (kind == 8U) { s_horizon.primary.gyro_bias[0] = 2.0f; }
}

uint32_t Test_ContextSize(void) { return (uint32_t)sizeof(s_horizon); }

void Test_AccelerationGet(float value[3])
{
    memcpy(value, s_horizon.output_acceleration, 3U * sizeof(float));
}

uint32_t Test_Result(uint32_t index)
{
    const uint32_t values[] = {NAV_ESKF_HORIZON_OK, NAV_ESKF_HORIZON_QUEUED,
        NAV_ESKF_HORIZON_WARMUP, NAV_ESKF_HORIZON_INVALID, NAV_ESKF_HORIZON_STALE,
        NAV_ESKF_HORIZON_LATE, NAV_ESKF_HORIZON_CAPACITY, NAV_ESKF_HORIZON_DUPLICATE,
        NAV_ESKF_HORIZON_EPOCH_MISMATCH, NAV_ESKF_HORIZON_DISCONTINUITY,
        NAV_ESKF_HORIZON_NUMERIC_ERROR, NAV_ESKF_HORIZON_MODEL_MISMATCH,
        NAV_ESKF_HORIZON_NOT_READY, NAV_ESKF_HORIZON_BUSY, NAV_ESKF_HORIZON_EMPTY};
    return (index < 15U) ? values[index] : UINT32_MAX;
}
