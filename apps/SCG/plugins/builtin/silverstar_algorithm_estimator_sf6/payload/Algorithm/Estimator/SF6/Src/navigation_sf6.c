#include "navigation_sf6.h"
#include "silverstar_assert.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

/* Single EstimatorTask owner. All fallible arithmetic is performed on a local
 * candidate before publishing either state or per-group admission metadata. */
static void NavigationSf6_ContextValidate(const NavigationSf6Context *context)
{
    SILVERSTAR_ASSERT(context->initialized <= 1U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (!context->initialized) { return; }
    SILVERSTAR_ASSERT(context->latest.timestamp_us >= context->epoch_us,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    for (uint8_t axis = 0U; axis < 6U; axis++)
    {
        SILVERSTAR_ASSERT(isfinite(context->latest.state[axis]),
            SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
        SILVERSTAR_ASSERT(isfinite(context->gain[axis]) && context->gain[axis] >= 0.0f && context->gain[axis] <= 1.0f,
            SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    }
    for (uint8_t group = 0U; group < NAV_SF6_GROUP_COUNT; group++)
    {
        SILVERSTAR_ASSERT(context->seen[group] <= 1U,
            SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
        SILVERSTAR_ASSERT(!context->seen[group] || (context->last_measurement_us[group] >= context->epoch_us &&
            context->last_measurement_us[group] <= context->last_receive_us[group] &&
            context->last_receive_us[group] <= context->latest.timestamp_us),
            SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    }
}

void NavigationSf6_Reset(NavigationSf6Context *context)
{
    if (context != NULL) { memset(context, 0, sizeof(*context)); }
}

NavigationSf6Result NavigationSf6_Initialize(NavigationSf6Context *context,
    const float gain[6], const float velocity[3], uint64_t timestamp_us)
{
    if ((context == NULL) || (gain == NULL) || (velocity == NULL))
    { return NAV_SF6_INVALID_ARGUMENT; }
    for (uint8_t axis = 0U; axis < 6U; axis++)
    {
        if (!isfinite(gain[axis]) || gain[axis] < 0.0f || gain[axis] > 1.0f)
        { return NAV_SF6_INVALID_ARGUMENT; }
    }
    for (uint8_t axis = 0U; axis < 3U; axis++)
    { if (!isfinite(velocity[axis])) { return NAV_SF6_INVALID_ARGUMENT; } }
    NavigationSf6_Reset(context);
    memcpy(context->gain, gain, sizeof(context->gain));
    memcpy(context->latest.state, velocity, 3U * sizeof(float));
    context->latest.timestamp_us = timestamp_us; context->epoch_us = timestamp_us;
    context->initialized = 1U;
    NavigationSf6_ContextValidate(context);
    return NAV_SF6_OK;
}

NavigationSf6Result NavigationSf6_SnapshotGet(const NavigationSf6Context *context,
    NavigationSf6Sample *snapshot)
{
    if ((context == NULL) || (snapshot == NULL)) { return NAV_SF6_INVALID_ARGUMENT; }
    NavigationSf6_ContextValidate(context);
    if (!context->initialized) { return NAV_SF6_NOT_READY; }
    *snapshot = context->latest;
    return NAV_SF6_OK;
}

static NavigationSf6Result NavigationSf6_StateAdvance(float state[6],
    const float delta_velocity[3], float dt_s)
{
    for (uint8_t axis = 0U; axis < 3U; axis++)
    {
        if (!isfinite(delta_velocity[axis])) { return NAV_SF6_INVALID_ARGUMENT; }
        state[3U + axis] += (state[axis] + 0.5f * delta_velocity[axis]) * dt_s;
        state[axis] += delta_velocity[axis];
        if (!isfinite(state[axis]) || !isfinite(state[3U + axis])) { return NAV_SF6_NUMERIC_ERROR; }
    }
    return NAV_SF6_OK;
}

NavigationSf6Result NavigationSf6_Predict(NavigationSf6Context *context,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s)
{
    NavigationSf6Sample next;
    NavigationSf6Result result;
    uint64_t duration;
    if ((context == NULL) || (delta_velocity == NULL) || !isfinite(dt_s) || dt_s <= 0.0f || dt_s > NAV_SF6_MAX_DT_S)
    { return NAV_SF6_INVALID_ARGUMENT; }
    if (NavigationSf6_SnapshotGet(context, &next) != NAV_SF6_OK) { return NAV_SF6_NOT_READY; }
    duration = (uint64_t)llroundf(dt_s * 1000000.0f);
    if (timestamp_us <= next.timestamp_us || duration == 0U || timestamp_us - next.timestamp_us != duration)
    { return NAV_SF6_STALE; }
    result = NavigationSf6_StateAdvance(next.state, delta_velocity, dt_s);
    if (result != NAV_SF6_OK) { return result; }
    memcpy(next.delta_velocity, delta_velocity, sizeof(next.delta_velocity));
    next.dt_s = dt_s; next.timestamp_us = timestamp_us;
    context->latest = next;
    return NAV_SF6_OK;
}

static NavigationSf6Result NavigationSf6_MeasurementValidate(const NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement)
{
    uint8_t group = measurement->group;
    uint64_t present = context->latest.timestamp_us;
    if (group >= NAV_SF6_GROUP_COUNT || measurement->receive_us > present ||
        measurement->measurement_us > measurement->receive_us || !isfinite(measurement->observation[0]) ||
        ((group == 0U || group == 2U) && !isfinite(measurement->observation[1]))) { return NAV_SF6_INVALID_ARGUMENT; }
    if (measurement->measurement_us < context->epoch_us ||
        present - measurement->measurement_us > NAV_SF6_MAX_MEASUREMENT_AGE_US) { return NAV_SF6_STALE; }
    if (context->seen[group] && (measurement->measurement_us <= context->last_measurement_us[group] ||
        measurement->receive_us <= context->last_receive_us[group] ||
        (uint32_t)(measurement->sequence - context->last_sequence[group]) == 0U ||
        (uint32_t)(measurement->sequence - context->last_sequence[group]) >= 0x80000000UL)) { return NAV_SF6_DUPLICATE; }
    return NAV_SF6_OK;
}

static NavigationSf6Result NavigationSf6_StateObserve(float state[6], const float gain[6],
    uint8_t group, const float observation[2])
{
    uint8_t first = group < 2U ? 3U : 0U;
    uint8_t count = group == 0U || group == 2U ? 2U : 1U;
    SILVERSTAR_ASSERT(group < NAV_SF6_GROUP_COUNT,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (group == 1U || group == 3U) { first += 2U; }
    if (group == 4U) { first = 5U; }
    for (uint8_t axis = 0U; axis < count; axis++)
    {
        SILVERSTAR_ASSERT(isfinite(state[first + axis]) && isfinite(observation[axis]),
            SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
        float correction = gain[first + axis] == 0.0f ? 0.0f : gain[first + axis] * (observation[axis] - state[first + axis]);
        if (!isfinite(correction)) { return NAV_SF6_NUMERIC_ERROR; }
        state[first + axis] += correction;
        if (!isfinite(state[first + axis])) { return NAV_SF6_NUMERIC_ERROR; }
    }
    return NAV_SF6_OK;
}

NavigationSf6Result NavigationSf6_Update(NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement, uint64_t *boundary_us)
{
    NavigationSf6Result result;
    NavigationSf6Sample next;
    if (context == NULL || measurement == NULL || boundary_us == NULL)
    { return NAV_SF6_INVALID_ARGUMENT; }
    if (NavigationSf6_SnapshotGet(context, &next) != NAV_SF6_OK) { return NAV_SF6_NOT_READY; }
    result = NavigationSf6_MeasurementValidate(context, measurement);
    if (result != NAV_SF6_OK) { return result; }
    result = NavigationSf6_StateObserve(next.state, context->gain, measurement->group, measurement->observation);
    if (result != NAV_SF6_OK) { return result; }
    context->latest = next;
    context->last_measurement_us[measurement->group] = measurement->measurement_us;
    context->last_receive_us[measurement->group] = measurement->receive_us;
    context->last_sequence[measurement->group] = measurement->sequence;
    context->seen[measurement->group] = 1U;
    *boundary_us = next.timestamp_us;
    return NAV_SF6_OK;
}
