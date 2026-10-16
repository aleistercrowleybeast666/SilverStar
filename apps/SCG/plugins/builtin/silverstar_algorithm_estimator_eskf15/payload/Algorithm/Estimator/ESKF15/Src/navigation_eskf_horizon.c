#include "navigation_eskf_horizon.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

static uint8_t Horizon_RangesOverlap(const void *a, size_t a_size,
    const void *b, size_t b_size)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return (uint8_t)((x <= y) ? (y - x < a_size) : (x - y < b_size));
}

static NavigationEskfHorizonResult Horizon_Fault(NavigationEskfHorizon *horizon,
    NavigationEskfHorizonResult result)
{
    horizon->faulted = 1U;
    return result;
}

static uint8_t Horizon_NominalValid(const NavigationEskfState *state)
{
    float quaternion_norm2 = 0.0f, gyro_bias_norm2 = 0.0f, accel_bias_norm2 = 0.0f;
    if (state->initialized != 1U) { return 0U; }
    for (uint32_t axis = 0U; axis < 4U; axis++)
    {
        if (!isfinite(state->quaternion[axis])) { return 0U; }
        quaternion_norm2 += state->quaternion[axis] * state->quaternion[axis];
    }
    for (uint32_t axis = 0U; axis < 3U; axis++)
    {
        if (!isfinite(state->position[axis]) || !isfinite(state->velocity[axis]) ||
            !isfinite(state->gyro_bias[axis]) || !isfinite(state->accel_bias[axis])) { return 0U; }
        gyro_bias_norm2 += state->gyro_bias[axis] * state->gyro_bias[axis];
        accel_bias_norm2 += state->accel_bias[axis] * state->accel_bias[axis];
    }
    return (uint8_t)(isfinite(quaternion_norm2) && isfinite(gyro_bias_norm2) && isfinite(accel_bias_norm2) &&
        (fabsf(quaternion_norm2 - 1.0f) <= 0.002001f) &&
        (gyro_bias_norm2 <= NAV_ESKF_MAX_GYRO_BIAS_RADPS * NAV_ESKF_MAX_GYRO_BIAS_RADPS) &&
        (accel_bias_norm2 <= NAV_ESKF_MAX_ACCEL_BIAS_MPS2 * NAV_ESKF_MAX_ACCEL_BIAS_MPS2));
}

static NavigationEskfHorizonResult Horizon_Ready(NavigationEskfHorizon *horizon)
{
    if (horizon == NULL) { return NAV_ESKF_HORIZON_INVALID; }
    if (horizon->initialized != 1U) { return NAV_ESKF_HORIZON_NOT_READY; }
    if (horizon->faulted == 1U) { return NAV_ESKF_HORIZON_NOT_READY; }
    if ((horizon->faulted > 1U) || (horizon->body_head >= NAV_ESKF_HORIZON_BODY_CAPACITY) ||
        (horizon->body_count > NAV_ESKF_HORIZON_BODY_CAPACITY) ||
        (horizon->event_count > NAV_ESKF_HORIZON_EVENT_CAPACITY) ||
        (horizon->completion_count > horizon->event_count) ||
        (horizon->completion_read > horizon->completion_count) ||
        (horizon->primary.timestamp_us < horizon->initial_us) ||
        (horizon->primary.timestamp_us > horizon->present_us) ||
        (horizon->body_start_us > horizon->primary.timestamp_us) ||
        (Horizon_NominalValid(&horizon->primary) == 0U) ||
        (Horizon_NominalValid(&horizon->output_candidate) == 0U) ||
        (horizon->output_candidate.timestamp_us < horizon->primary.timestamp_us) ||
        (horizon->output_candidate.timestamp_us > horizon->present_us) ||
        (horizon->horizon_us < 10000ULL) || (horizon->horizon_us > 550000ULL))
    { return Horizon_Fault(horizon, NAV_ESKF_HORIZON_NUMERIC_ERROR); }
    return (horizon->faulted != 0U) ? NAV_ESKF_HORIZON_NOT_READY : NAV_ESKF_HORIZON_OK;
}

static uint8_t Horizon_ConfigEqual(const NavigationEskfConfig *a,
    const NavigationEskfConfig *b)
{
    return (uint8_t)((a->gravity_mps2 == b->gravity_mps2) &&
        (a->gyro_noise_density == b->gyro_noise_density) &&
        (a->accel_noise_density == b->accel_noise_density) &&
        (a->gyro_bias_rw == b->gyro_bias_rw) && (a->accel_bias_rw == b->accel_bias_rw) &&
        (a->nis_soft[0] == b->nis_soft[0]) && (a->nis_soft[1] == b->nis_soft[1]) &&
        (a->nis_hard[0] == b->nis_hard[0]) && (a->nis_hard[1] == b->nis_hard[1]) &&
        (a->maximum_r_scale == b->maximum_r_scale) &&
        (a->nis_disabled_mask == b->nis_disabled_mask));
}

NavigationEskfHorizonResult NavigationEskfHorizon_Reset(
    NavigationEskfHorizon *horizon, const NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    uint64_t horizon_us)
{
    float nominal[16];
    if ((horizon == NULL) || (state == NULL) || (workspace == NULL) || (config == NULL))
    { return NAV_ESKF_HORIZON_INVALID; }
    if (Horizon_RangesOverlap(horizon, sizeof(*horizon), state, sizeof(*state)) ||
        Horizon_RangesOverlap(horizon, sizeof(*horizon), workspace, sizeof(*workspace)) ||
        Horizon_RangesOverlap(horizon, sizeof(*horizon), config, sizeof(*config)) ||
        Horizon_RangesOverlap(workspace, sizeof(*workspace), state, sizeof(*state)) ||
        Horizon_RangesOverlap(workspace, sizeof(*workspace), config, sizeof(*config)))
    { return NAV_ESKF_HORIZON_INVALID; }
    horizon->faulted = 1U;
    if ((state->initialized != 1U) || (horizon_us < 10000ULL) || (horizon_us > 550000ULL) ||
        (NavigationEskf_ConfigValidate(config) != NAV_ESKF_OK))
    { return NAV_ESKF_HORIZON_INVALID; }
    memcpy(nominal, state->position, 3U * sizeof(float));
    memcpy(nominal + 3, state->velocity, 3U * sizeof(float));
    memcpy(nominal + 6, state->quaternion, 4U * sizeof(float));
    memcpy(nominal + 10, state->gyro_bias, 3U * sizeof(float));
    memcpy(nominal + 13, state->accel_bias, 3U * sizeof(float));
    if (NavigationEskf_Initialize(&horizon->candidate, workspace, nominal,
        (const float (*)[NAV_ESKF_DIM])state->covariance, state->timestamp_us,
        state->source, state->generation) != NAV_ESKF_OK)
    { return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    memset(horizon, 0, sizeof(*horizon));
    horizon->primary = *state; horizon->output_candidate = *state; horizon->config = *config;
    horizon->initial_us = state->timestamp_us; horizon->present_us = state->timestamp_us;
    horizon->body_start_us = state->timestamp_us; horizon->horizon_us = horizon_us;
    horizon->initialized = 1U; horizon->warmup = 1U;
    return NAV_ESKF_HORIZON_OK;
}

static uint8_t Horizon_BodyValid(const NavigationEskfBodyInput *input)
{
    if (!isfinite(input->dt_s) || (input->dt_s <= 0.0f) ||
        (input->dt_s > NAV_ESKF_MAX_DT_S) || (input->end_us <= input->start_us) ||
        ((input->quality_flags & 0x72U) != 0U) ||
        (fabsf((float)(input->end_us - input->start_us) * 1.0e-6f - input->dt_s) > 2.0e-6f))
    { return 0U; }
    for (uint32_t sample = 0U; sample < 2U; sample++)
    {
        for (uint32_t axis = 0U; axis < 3U; axis++)
        {
            if (!isfinite(input->gyro_radps[sample][axis]) ||
                !isfinite(input->accel_mps2[sample][axis])) { return 0U; }
        }
    }
    return 1U;
}

NavigationEskfHorizonResult NavigationEskfHorizon_BodyReceive(
    NavigationEskfHorizon *horizon, const NavigationEskfBodyInput *input)
{
    NavigationEskfHorizonResult ready = Horizon_Ready(horizon);
    uint16_t slot;
    if (ready != NAV_ESKF_HORIZON_OK) { return ready; }
    if ((input == NULL) || Horizon_RangesOverlap(horizon, sizeof(*horizon), input, sizeof(*input)))
    { return NAV_ESKF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_ESKF_HORIZON_BUSY; }
    if ((input->source != horizon->primary.source) || (input->generation != horizon->primary.generation))
    { return Horizon_Fault(horizon, NAV_ESKF_HORIZON_EPOCH_MISMATCH); }
    if ((input->start_us != horizon->present_us) || (Horizon_BodyValid(input) == 0U) ||
        (horizon->body_seen && ((input->quality_flags & 0x08U) != 0U)))
    { return Horizon_Fault(horizon, NAV_ESKF_HORIZON_DISCONTINUITY); }
    if (horizon->body_count == NAV_ESKF_HORIZON_BODY_CAPACITY)
    {
        if (horizon->capacity_count < UINT32_MAX) { horizon->capacity_count++; }
        return Horizon_Fault(horizon, NAV_ESKF_HORIZON_CAPACITY);
    }
    slot = (uint16_t)((horizon->body_head + horizon->body_count) % NAV_ESKF_HORIZON_BODY_CAPACITY);
    horizon->body[slot].end_us = input->end_us; horizon->body[slot].dt_s = input->dt_s;
    horizon->body[slot].quality_flags = input->quality_flags;
    memcpy(horizon->body[slot].gyro_radps, input->gyro_radps, sizeof(input->gyro_radps));
    memcpy(horizon->body[slot].accel_mps2, input->accel_mps2, sizeof(input->accel_mps2));
    horizon->body_count++; horizon->present_us = input->end_us; horizon->body_seen = 1U;
    return NAV_ESKF_HORIZON_OK;
}

static NavigationEskfHorizonResult Horizon_ReceiptCheck(
    const NavigationEskfHorizonReceipt *receipt, uint32_t sequence, uint8_t mask)
{
    if (receipt->groups == 0U) { return NAV_ESKF_HORIZON_OK; }
    if (sequence == receipt->sequence)
    { return ((receipt->groups & mask) != 0U) ? NAV_ESKF_HORIZON_DUPLICATE : NAV_ESKF_HORIZON_OK; }
    return ((uint32_t)(sequence - receipt->sequence) < 0x80000000UL) ?
        NAV_ESKF_HORIZON_OK : NAV_ESKF_HORIZON_DISCONTINUITY;
}

static NavigationEskfHorizonResult Horizon_EventValidate(const NavigationEskfHorizon *horizon,
    const NavigationEskfHorizonEvent *received)
{
    const NavigationEskfReplayEvent *event = &received->event;
    uint32_t dimension = (event->measurement.group & 1U) ? 1U : 2U;
    if ((event->measurement.group >= 5U) || (event->source >= NAV_ESKF_HORIZON_SOURCE_COUNT) ||
        ((event->measurement.group == 4U) && (event->source != 1U)) ||
        (event->measurement.physically_valid > 1U) || (event->measurement_us == 0U) ||
        !isfinite(received->quality_scale) || (received->quality_scale <= 0.0f) ||
        !isfinite(received->consistency_scale) || (received->consistency_scale <= 0.0f) ||
        (event->receive_us == 0U) || (event->measurement_us > event->receive_us) ||
        (event->receive_us > horizon->present_us)) { return NAV_ESKF_HORIZON_INVALID; }
    if ((event->generation != horizon->primary.generation) ||
        (event->measurement_us < horizon->initial_us) || (event->receive_us < horizon->initial_us))
    { return NAV_ESKF_HORIZON_EPOCH_MISMATCH; }
    if ((horizon->present_us - event->measurement_us > 600000ULL) ||
        (horizon->present_us - event->receive_us > 500000ULL)) { return NAV_ESKF_HORIZON_STALE; }
    if (event->measurement.group == 4U) { dimension = 1U; }
    for (uint32_t axis = 0U; axis < 2U; axis++)
    {
        if ((axis < dimension) && (!isfinite(event->measurement.observation[axis]) ||
            !isfinite(event->measurement.variance[axis]) || (event->measurement.variance[axis] <= 0.0f) ||
            !isfinite(received->base_variance[axis]) || (received->base_variance[axis] <= 0.0f)))
        { return NAV_ESKF_HORIZON_INVALID; }
    }
    for (uint32_t axis = 0U; axis < 3U; axis++)
    { if (!isfinite(event->measurement.lever_arm_b_m[axis])) { return NAV_ESKF_HORIZON_INVALID; } }
    return NAV_ESKF_HORIZON_OK;
}

static uint8_t Horizon_EventBefore(const NavigationEskfHorizonEvent *a,
    const NavigationEskfHorizonEvent *b)
{
    return (uint8_t)((a->event.measurement_us < b->event.measurement_us) ||
        ((a->event.measurement_us == b->event.measurement_us) &&
         (a->event.measurement.group < b->event.measurement.group)));
}

NavigationEskfHorizonResult NavigationEskfHorizon_Insert(
    NavigationEskfHorizon *horizon, const NavigationEskfHorizonEvent *received)
{
    NavigationEskfHorizonResult result = Horizon_Ready(horizon);
    NavigationEskfHorizonReceipt *receipt;
    uint8_t mask;
    uint16_t slot;
    if (result != NAV_ESKF_HORIZON_OK) { return result; }
    if ((received == NULL) || Horizon_RangesOverlap(horizon, sizeof(*horizon), received, sizeof(*received)))
    { return NAV_ESKF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_ESKF_HORIZON_BUSY; }
    if (horizon->body_seen == 0U) { return NAV_ESKF_HORIZON_NOT_READY; }
    result = Horizon_EventValidate(horizon, received);
    if (result != NAV_ESKF_HORIZON_OK) { return result; }
    receipt = (received->event.measurement.group == 4U) ? &horizon->barometer :
        &horizon->gnss[received->event.source];
    mask = (uint8_t)(1U << received->event.measurement.group);
    result = Horizon_ReceiptCheck(receipt, received->event.sequence, mask);
    if (result != NAV_ESKF_HORIZON_OK) { return result; }
    if (receipt->sequence != received->event.sequence) { receipt->groups = 0U; }
    receipt->sequence = received->event.sequence; receipt->groups |= mask;
    if (received->event.measurement.physically_valid != 1U) { return NAV_ESKF_HORIZON_INVALID; }
    if (received->event.measurement_us < horizon->primary.timestamp_us)
    {
        if (horizon->late_count < UINT32_MAX) { horizon->late_count++; }
        return NAV_ESKF_HORIZON_LATE;
    }
    if (horizon->event_count == NAV_ESKF_HORIZON_EVENT_CAPACITY)
    {
        if (horizon->capacity_count < UINT32_MAX) { horizon->capacity_count++; }
        return NAV_ESKF_HORIZON_CAPACITY;
    }
    slot = horizon->event_count;
    for (uint16_t limit = 0U; limit < NAV_ESKF_HORIZON_EVENT_CAPACITY; limit++)
    {
        if ((slot == 0U) || !Horizon_EventBefore(received, &horizon->event[slot - 1U])) { break; }
        horizon->event[slot] = horizon->event[slot - 1U]; slot--;
    }
    horizon->event[slot] = *received;
    memset(&horizon->event[slot].outcome, 0, sizeof(horizon->event[slot].outcome));
    horizon->event[slot].outcome.r_scale = 1.0f;
    horizon->event_count++;
    return NAV_ESKF_HORIZON_QUEUED;
}

static void Horizon_BodyGet(const NavigationEskfHorizon *horizon,
    uint16_t index, NavigationEskfBodyInput *body)
{
    uint16_t slot = (uint16_t)((horizon->body_head + index) % NAV_ESKF_HORIZON_BODY_CAPACITY);
    uint16_t previous = (uint16_t)((horizon->body_head + index + NAV_ESKF_HORIZON_BODY_CAPACITY - 1U) %
        NAV_ESKF_HORIZON_BODY_CAPACITY);
    body->start_us = (index == 0U) ? horizon->body_start_us : horizon->body[previous].end_us;
    body->end_us = horizon->body[slot].end_us; body->dt_s = horizon->body[slot].dt_s;
    body->source = horizon->primary.source; body->generation = horizon->primary.generation;
    body->quality_flags = horizon->body[slot].quality_flags;
    memcpy(body->gyro_radps, horizon->body[slot].gyro_radps, sizeof(body->gyro_radps));
    memcpy(body->accel_mps2, horizon->body[slot].accel_mps2, sizeof(body->accel_mps2));
}

static NavigationEskfHorizonResult Horizon_Predict(NavigationEskfHorizon *horizon,
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfBodyInput *body)
{
    if (horizon->last_work >= NAV_ESKF_HORIZON_MAX_WORK) { return NAV_ESKF_HORIZON_CAPACITY; }
    horizon->last_work++;
    return (NavigationEskf_Predict(state, workspace, &horizon->config, body) == NAV_ESKF_OK) ?
        NAV_ESKF_HORIZON_OK : NAV_ESKF_HORIZON_NUMERIC_ERROR;
}

static NavigationEskfHorizonResult Horizon_PartApply(NavigationEskfHorizon *horizon,
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfBodyInput *body, uint64_t end_us)
{
    NavigationEskfBodyInput part = *body;
    if (state->timestamp_us == end_us) { return NAV_ESKF_HORIZON_OK; }
    if (Horizon_BodyValid(body) == 0U) { return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    if ((state->timestamp_us < body->start_us) || (end_us > body->end_us) ||
        (end_us < state->timestamp_us)) { return NAV_ESKF_HORIZON_DISCONTINUITY; }
    if ((state->timestamp_us == body->start_us) && (end_us == body->end_us))
    { return Horizon_Predict(horizon, state, workspace, body); }
    for (uint32_t half = 0U; half < 2U; half++)
    {
        uint64_t boundary = (half == 0U) ? body->start_us + (body->end_us - body->start_us) / 2U : body->end_us;
        uint64_t target = (end_us < boundary) ? end_us : boundary;
        NavigationEskfHorizonResult result;
        if (target <= state->timestamp_us) { continue; }
        part.start_us = state->timestamp_us; part.end_us = target;
        part.dt_s = (float)(target - part.start_us) * 1.0e-6f;
        for (uint32_t sample = 0U; sample < 2U; sample++)
        {
            memcpy(part.gyro_radps[sample], body->gyro_radps[half], sizeof(part.gyro_radps[sample]));
            memcpy(part.accel_mps2[sample], body->accel_mps2[half], sizeof(part.accel_mps2[sample]));
        }
        result = Horizon_Predict(horizon, state, workspace, &part);
        if (result != NAV_ESKF_HORIZON_OK) { return result; }
    }
    return NAV_ESKF_HORIZON_OK;
}

static NavigationEskfHorizonResult Horizon_PropagateTo(NavigationEskfHorizon *horizon,
    NavigationEskfState *state, NavigationEskfWorkspace *workspace, uint64_t target)
{
    for (uint16_t index = 0U; index < NAV_ESKF_HORIZON_BODY_CAPACITY; index++)
    {
        NavigationEskfBodyInput body;
        NavigationEskfHorizonResult result;
        if ((index >= horizon->body_count) || (state->timestamp_us == target)) { break; }
        Horizon_BodyGet(horizon, index, &body);
        if (body.end_us <= state->timestamp_us) { continue; }
        result = Horizon_PartApply(horizon, state, workspace, &body,
            (target < body.end_us) ? target : body.end_us);
        if (result != NAV_ESKF_HORIZON_OK) { return result; }
    }
    return (state->timestamp_us == target) ? NAV_ESKF_HORIZON_OK : NAV_ESKF_HORIZON_DISCONTINUITY;
}

static NavigationEskfHorizonResult Horizon_AngularRateGet(const NavigationEskfHorizon *horizon,
    uint64_t source_us, float rate[3])
{
    if ((source_us == horizon->body_start_us) && horizon->endpoint_valid)
    { memcpy(rate, horizon->primary_endpoint_rate, 3U * sizeof(float)); return NAV_ESKF_HORIZON_OK; }
    for (uint16_t index = 0U; index < NAV_ESKF_HORIZON_BODY_CAPACITY; index++)
    {
        NavigationEskfBodyInput body;
        uint32_t half;
        if (index >= horizon->body_count) { break; }
        Horizon_BodyGet(horizon, index, &body);
        if ((source_us < body.start_us) || (source_us > body.end_us)) { continue; }
        half = (source_us <= body.start_us + (body.end_us - body.start_us) / 2U) ? 0U : 1U;
        memcpy(rate, body.gyro_radps[half], 3U * sizeof(float));
        return NAV_ESKF_HORIZON_OK;
    }
    return NAV_ESKF_HORIZON_DISCONTINUITY;
}

static NavigationEskfHorizonResult Horizon_MeasurementApply(NavigationEskfHorizon *horizon,
    NavigationEskfWorkspace *workspace, uint16_t index)
{
    NavigationEskfMeasurement measurement = horizon->event[index].event.measurement;
    NavigationEskfResult result;
    if (measurement.group == 4U)
    { memset(measurement.angular_rate_b_radps, 0, sizeof(measurement.angular_rate_b_radps)); }
    else if (Horizon_AngularRateGet(horizon, horizon->event[index].event.measurement_us,
        measurement.angular_rate_b_radps) != NAV_ESKF_HORIZON_OK)
    { return NAV_ESKF_HORIZON_DISCONTINUITY; }
    if (horizon->last_work >= NAV_ESKF_HORIZON_MAX_WORK) { return NAV_ESKF_HORIZON_CAPACITY; }
    horizon->last_work++;
    result = NavigationEskf_UpdateRevision2(&horizon->candidate, workspace, &horizon->config,
        &measurement, &horizon->event[index].outcome);
    if (result == NAV_ESKF_NUMERIC_ERROR) { return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    if (result == NAV_ESKF_MODEL_MISMATCH) { return NAV_ESKF_HORIZON_MODEL_MISMATCH; }
    if (result == NAV_ESKF_INVALID_INPUT) { return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    return NAV_ESKF_HORIZON_OK;
}

static NavigationEskfHorizonResult Horizon_PrimaryBuild(NavigationEskfHorizon *horizon,
    NavigationEskfWorkspace *workspace, uint64_t target, uint16_t *ready_count)
{
    horizon->candidate = horizon->primary; *ready_count = 0U;
    for (uint16_t index = 0U; index < NAV_ESKF_HORIZON_EVENT_CAPACITY; index++)
    {
        NavigationEskfHorizonResult result;
        if ((index >= horizon->event_count) || (horizon->event[index].event.measurement_us > target)) { break; }
        horizon->failure_operation = horizon->event[index].operation_sequence;
        horizon->failure_operation_valid = 1U;
        result = Horizon_PropagateTo(horizon, &horizon->candidate, workspace,
            horizon->event[index].event.measurement_us);
        if (result != NAV_ESKF_HORIZON_OK) { return result; }
        result = Horizon_MeasurementApply(horizon, workspace, index);
        if (result != NAV_ESKF_HORIZON_OK) { return result; }
        (*ready_count)++;
    }
    horizon->failure_operation_valid = 0U;
    return Horizon_PropagateTo(horizon, &horizon->candidate, workspace, target);
}

static void Horizon_BodyTrim(NavigationEskfHorizon *horizon)
{
    for (uint16_t limit = 0U; limit < NAV_ESKF_HORIZON_BODY_CAPACITY; limit++)
    {
        if ((horizon->body_count == 0U) ||
            (horizon->body[horizon->body_head].end_us > horizon->primary.timestamp_us)) { break; }
        horizon->body_start_us = horizon->body[horizon->body_head].end_us;
        memcpy(horizon->primary_endpoint_rate, horizon->body[horizon->body_head].gyro_radps[1],
            sizeof(horizon->primary_endpoint_rate));
        horizon->endpoint_valid = 1U;
        horizon->body_head = (uint16_t)((horizon->body_head + 1U) % NAV_ESKF_HORIZON_BODY_CAPACITY);
        horizon->body_count--;
    }
}

/* Preserve the existing backend's prediction-before-measurement acceleration
 * meaning. A delayed GNSS velocity correction is not an IMU acceleration.
 * This prior-output calculation never changes the primary or final predictor. */
static NavigationEskfHorizonResult Horizon_OutputAccelerationBuild(NavigationEskfHorizon *horizon,
    NavigationEskfWorkspace *workspace, float acceleration[3])
{
    uint64_t previous_us = horizon->output_candidate.timestamp_us;
    float previous_velocity[3], duration_s = 0.0f;
    NavigationEskfHorizonResult result;
    memcpy(previous_velocity, horizon->output_candidate.velocity, sizeof(previous_velocity));
    memcpy(acceleration, horizon->output_acceleration, 3U * sizeof(float));
    for (uint16_t index = 0U; index < NAV_ESKF_HORIZON_BODY_CAPACITY; index++)
    {
        NavigationEskfBodyInput body;
        if (index >= horizon->body_count) { break; }
        Horizon_BodyGet(horizon, index, &body);
        if (body.end_us <= previous_us) { continue; }
        if (body.start_us < previous_us) { return NAV_ESKF_HORIZON_DISCONTINUITY; }
        duration_s += body.dt_s;
    }
    if (previous_us != horizon->present_us)
    {
        if (!isfinite(duration_s) || (duration_s <= 0.0f)) { return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
        result = Horizon_PropagateTo(horizon, &horizon->output_candidate, workspace, horizon->present_us);
        if (result != NAV_ESKF_HORIZON_OK) { return result; }
        for (uint32_t axis = 0U; axis < 3U; axis++)
        { acceleration[axis] = (horizon->output_candidate.velocity[axis] - previous_velocity[axis]) / duration_s; }
    }
    for (uint32_t axis = 0U; axis < 3U; axis++)
    { if (!isfinite(acceleration[axis])) { return NAV_ESKF_HORIZON_NUMERIC_ERROR; } }
    return NAV_ESKF_HORIZON_OK;
}

NavigationEskfHorizonResult NavigationEskfHorizon_Advance(
    NavigationEskfHorizon *horizon, NavigationEskfState *output,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config)
{
    NavigationEskfHorizonResult result = Horizon_Ready(horizon);
    uint64_t target;
    uint16_t ready_count;
    float acceleration[3];
    if (result != NAV_ESKF_HORIZON_OK) { return result; }
    if ((output == NULL) || (workspace == NULL) || (config == NULL)) { return NAV_ESKF_HORIZON_INVALID; }
    if (Horizon_RangesOverlap(horizon, sizeof(*horizon), output, sizeof(*output)) ||
        Horizon_RangesOverlap(horizon, sizeof(*horizon), workspace, sizeof(*workspace)) ||
        Horizon_RangesOverlap(horizon, sizeof(*horizon), config, sizeof(*config)) ||
        Horizon_RangesOverlap(workspace, sizeof(*workspace), output, sizeof(*output)) ||
        Horizon_RangesOverlap(output, sizeof(*output), config, sizeof(*config)) ||
        Horizon_RangesOverlap(workspace, sizeof(*workspace), config, sizeof(*config)))
    { return NAV_ESKF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_ESKF_HORIZON_BUSY; }
    if (horizon->body_seen == 0U) { return NAV_ESKF_HORIZON_NOT_READY; }
    if ((NavigationEskf_ConfigValidate(config) != NAV_ESKF_OK) || !Horizon_ConfigEqual(config, &horizon->config))
    { return Horizon_Fault(horizon, NAV_ESKF_HORIZON_EPOCH_MISMATCH); }
    target = (horizon->present_us - horizon->initial_us < horizon->horizon_us) ?
        horizon->initial_us : horizon->present_us - horizon->horizon_us;
    horizon->last_work = 0U;
    horizon->failure_operation_valid = 0U;
    result = Horizon_OutputAccelerationBuild(horizon, workspace, acceleration);
    if (result != NAV_ESKF_HORIZON_OK) { return Horizon_Fault(horizon, result); }
    result = Horizon_PrimaryBuild(horizon, workspace, target, &ready_count);
    if (result != NAV_ESKF_HORIZON_OK) { return Horizon_Fault(horizon, result); }
    horizon->output_candidate = horizon->candidate;
    result = Horizon_PropagateTo(horizon, &horizon->output_candidate, workspace, horizon->present_us);
    if (result != NAV_ESKF_HORIZON_OK) { return Horizon_Fault(horizon, result); }
    horizon->primary = horizon->candidate; *output = horizon->output_candidate;
    memcpy(horizon->output_acceleration, acceleration, sizeof(acceleration));
    horizon->completion_count = ready_count; horizon->completion_read = 0U;
    horizon->warmup = (uint8_t)(horizon->present_us - horizon->initial_us < horizon->horizon_us);
    if (horizon->last_work > horizon->maximum_work) { horizon->maximum_work = horizon->last_work; }
    Horizon_BodyTrim(horizon);
    return horizon->warmup ? NAV_ESKF_HORIZON_WARMUP : NAV_ESKF_HORIZON_OK;
}

NavigationEskfHorizonResult NavigationEskfHorizon_CompletionPop(
    NavigationEskfHorizon *horizon, NavigationEskfHorizonEvent *event)
{
    NavigationEskfHorizonResult result = Horizon_Ready(horizon);
    uint16_t remaining;
    if (result != NAV_ESKF_HORIZON_OK) { return result; }
    if ((event == NULL) || Horizon_RangesOverlap(horizon, sizeof(*horizon), event, sizeof(*event)))
    { return NAV_ESKF_HORIZON_INVALID; }
    if (horizon->completion_count == 0U) { return NAV_ESKF_HORIZON_EMPTY; }
    *event = horizon->event[horizon->completion_read];
    horizon->completion_read++;
    if (horizon->completion_read != horizon->completion_count) { return NAV_ESKF_HORIZON_OK; }
    remaining = (uint16_t)(horizon->event_count - horizon->completion_count);
    for (uint16_t index = 0U; index < NAV_ESKF_HORIZON_EVENT_CAPACITY; index++)
    {
        if (index >= remaining) { break; }
        horizon->event[index] = horizon->event[index + horizon->completion_count];
    }
    horizon->event_count = remaining; horizon->completion_count = 0U; horizon->completion_read = 0U;
    return NAV_ESKF_HORIZON_OK;
}
