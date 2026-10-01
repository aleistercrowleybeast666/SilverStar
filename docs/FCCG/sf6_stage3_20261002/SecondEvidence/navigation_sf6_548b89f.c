#include "navigation_sf6.h"
#include "silverstar_assert.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

/* Estimator task owns this context. External bad observations return errors;
 * corrupt ring ownership/capacity enters the existing assertion fail-stop. */
static void NavigationSf6_ContextValidate(const NavigationSf6Context *context)
{
    uint8_t axis;
    SILVERSTAR_ASSERT(context->initialized <= 1U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(context->first < NAV_SF6_HISTORY_CAPACITY &&
        context->count <= NAV_SF6_HISTORY_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT(!context->initialized || context->count != 0U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (context->initialized)
    {
        uint16_t latest = (uint16_t)((context->first + context->count - 1U) % NAV_SF6_HISTORY_CAPACITY);
        for (axis = 0U; axis < 6U; axis++)
        {
            SILVERSTAR_ASSERT(isfinite(context->history[latest].state[axis]),
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
            SILVERSTAR_ASSERT(isfinite(context->gain[axis]) && context->gain[axis] >= 0.0f && context->gain[axis] <= 1.0f,
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
        }
    }
}

static uint16_t NavigationSf6_Index(const NavigationSf6Context *context, uint16_t offset)
{
    SILVERSTAR_ASSERT(offset < context->count,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    return (uint16_t)((context->first + offset) % NAV_SF6_HISTORY_CAPACITY);
}

void NavigationSf6_Reset(NavigationSf6Context *context)
{
    if (context != NULL) { memset(context, 0, sizeof(*context)); }
}

NavigationSf6Result NavigationSf6_Initialize(NavigationSf6Context *context,
    const float gain[6], const float velocity[3], uint64_t timestamp_us)
{
    uint8_t axis;
    if ((context == NULL) || (gain == NULL) || (velocity == NULL))
    { return NAV_SF6_INVALID_ARGUMENT; }
    for (axis = 0U; axis < 6U; axis++)
    {
        if (!isfinite(gain[axis]) || gain[axis] < 0.0f || gain[axis] > 1.0f)
        { return NAV_SF6_INVALID_ARGUMENT; }
    }
    for (axis = 0U; axis < 3U; axis++)
    { if (!isfinite(velocity[axis])) { return NAV_SF6_INVALID_ARGUMENT; } }
    NavigationSf6_Reset(context);
    memcpy(context->gain, gain, sizeof(context->gain));
    memcpy(context->history[0].state, velocity, 3U * sizeof(float));
    context->history[0].timestamp_us = timestamp_us;
    context->count = 1U; context->initialized = 1U;
    NavigationSf6_ContextValidate(context);
    return NAV_SF6_OK;
}

NavigationSf6Result NavigationSf6_SnapshotGet(const NavigationSf6Context *context,
    NavigationSf6Sample *snapshot)
{
    if ((context == NULL) || (snapshot == NULL)) { return NAV_SF6_INVALID_ARGUMENT; }
    NavigationSf6_ContextValidate(context);
    if (!context->initialized) { return NAV_SF6_NOT_READY; }
    *snapshot = context->history[NavigationSf6_Index(context, (uint16_t)(context->count - 1U))];
    return NAV_SF6_OK;
}

static void NavigationSf6_Append(NavigationSf6Context *context,
    const NavigationSf6Sample *next)
{
    uint16_t index;
    NavigationSf6_ContextValidate(context);
    SILVERSTAR_ASSERT(next->timestamp_us >
        context->history[NavigationSf6_Index(context, (uint16_t)(context->count - 1U))].timestamp_us,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    if (context->count == NAV_SF6_HISTORY_CAPACITY)
    {
        context->first = (uint16_t)((context->first + 1U) % NAV_SF6_HISTORY_CAPACITY);
        context->count--;
    }
    index = (uint16_t)((context->first + context->count) % NAV_SF6_HISTORY_CAPACITY);
    context->history[index] = *next; context->count++;
    /* At most the ring's fixed capacity can be removed. Keep the current state. */
    for (index = 0U; index < NAV_SF6_HISTORY_CAPACITY; index++)
    {
        if (context->count <= 1U || next->timestamp_us -
            context->history[context->first].timestamp_us <= NAV_SF6_HISTORY_US) { break; }
        context->first = (uint16_t)((context->first + 1U) % NAV_SF6_HISTORY_CAPACITY);
        context->count--;
    }
}

NavigationSf6Result NavigationSf6_Predict(NavigationSf6Context *context,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s)
{
    NavigationSf6Sample next;
    uint8_t axis;
    uint64_t duration;
    if ((context == NULL) || (delta_velocity == NULL) || !isfinite(dt_s) ||
        dt_s <= 0.0f || dt_s > NAV_SF6_MAX_DT_S)
    { return NAV_SF6_INVALID_ARGUMENT; }
    if (NavigationSf6_SnapshotGet(context, &next) != NAV_SF6_OK)
    { return NAV_SF6_NOT_READY; }
    duration = (uint64_t)llroundf(dt_s * 1000000.0f);
    if (timestamp_us <= next.timestamp_us || duration == 0U ||
        timestamp_us - next.timestamp_us != duration) { return NAV_SF6_STALE; }
    for (axis = 0U; axis < 3U; axis++)
    {
        if (!isfinite(delta_velocity[axis])) { return NAV_SF6_INVALID_ARGUMENT; }
        next.state[3U + axis] += (next.state[axis] + 0.5f * delta_velocity[axis]) * dt_s;
        next.state[axis] += delta_velocity[axis];
        if (!isfinite(next.state[axis]) || !isfinite(next.state[3U + axis]))
        { return NAV_SF6_NUMERIC_ERROR; }
    }
    next.timestamp_us = timestamp_us;
    NavigationSf6_Append(context, &next);
    return NAV_SF6_OK;
}

static uint16_t NavigationSf6_BoundaryFind(const NavigationSf6Context *context,
    uint64_t measurement_us)
{
    uint16_t offset, boundary = 0U;
    NavigationSf6_ContextValidate(context);
    for (offset = 0U; offset < context->count; offset++)
    {
        if (context->history[NavigationSf6_Index(context, offset)].timestamp_us > measurement_us)
        { break; }
        boundary = offset;
    }
    return boundary;
}

static NavigationSf6Result NavigationSf6_MeasurementValidate(
    const NavigationSf6Context *context, const NavigationSf6Measurement *measurement)
{
    uint8_t group = measurement->group;
    uint64_t present = context->history[NavigationSf6_Index(context, (uint16_t)(context->count - 1U))].timestamp_us;
    if (group >= NAV_SF6_GROUP_COUNT || measurement->receive_us > present ||
        measurement->measurement_us > measurement->receive_us ||
        !isfinite(measurement->observation[0]) ||
        ((group == 0U || group == 2U) && !isfinite(measurement->observation[1])))
    { return NAV_SF6_INVALID_ARGUMENT; }
    if (measurement->measurement_us < context->history[context->first].timestamp_us)
    { return NAV_SF6_STALE; }
    if (context->seen[group] &&
        (measurement->measurement_us <= context->last_measurement_us[group] ||
         measurement->receive_us <= context->last_receive_us[group] ||
         (uint32_t)(measurement->sequence - context->last_sequence[group]) == 0U ||
         (uint32_t)(measurement->sequence - context->last_sequence[group]) >= 0x80000000UL))
    { return NAV_SF6_DUPLICATE; }
    return NAV_SF6_OK;
}

static uint8_t NavigationSf6_CorrectionBuild(const NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement, uint16_t boundary, float correction[6])
{
    const NavigationSf6Sample *sample = &context->history[NavigationSf6_Index(context, boundary)];
    uint8_t axis, first = (measurement->group < 2U) ? 3U : 0U;
    uint8_t count = (measurement->group == 0U || measurement->group == 2U) ? 2U : 1U;
    if (measurement->group == 1U || measurement->group == 3U) { first += 2U; }
    if (measurement->group == 4U) { first = 5U; }
    memset(correction, 0, 6U * sizeof(float));
    SILVERSTAR_ASSERT(first + count <= 6U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (axis = 0U; axis < count; axis++)
    {
        correction[first + axis] = context->gain[first + axis] == 0.0f ? 0.0f : context->gain[first + axis] *
            (measurement->observation[axis] - sample->state[first + axis]);
        if (!isfinite(correction[first + axis])) { return 0U; }
    }
    return 1U;
}

static NavigationSf6Sample NavigationSf6_Corrected(const NavigationSf6Sample *sample,
    uint64_t boundary_us, const float correction[6])
{
    NavigationSf6Sample next = *sample;
    float dt_s = (float)(sample->timestamp_us - boundary_us) * 1.0e-6f;
    uint8_t axis;
    SILVERSTAR_ASSERT(sample->timestamp_us >= boundary_us,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    for (axis = 0U; axis < 3U; axis++)
    {
        next.state[axis] += correction[axis];
        next.state[3U + axis] += correction[3U + axis] + correction[axis] * dt_s;
    }
    return next;
}

NavigationSf6Result NavigationSf6_Update(NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement, uint64_t *boundary_us)
{
    float correction[6];
    uint16_t boundary, offset;
    uint64_t boundary_time;
    NavigationSf6Result result;
    if (context == NULL || measurement == NULL || boundary_us == NULL)
    { return NAV_SF6_INVALID_ARGUMENT; }
    NavigationSf6_ContextValidate(context);
    if (!context->initialized) { return NAV_SF6_NOT_READY; }
    result = NavigationSf6_MeasurementValidate(context, measurement);
    if (result != NAV_SF6_OK) { return result; }
    boundary = NavigationSf6_BoundaryFind(context, measurement->measurement_us);
    boundary_time = context->history[NavigationSf6_Index(context, boundary)].timestamp_us;
    if (!NavigationSf6_CorrectionBuild(context, measurement, boundary, correction))
    { return NAV_SF6_NUMERIC_ERROR; }
    /* Validate the complete affine correction before publishing any state. */
    for (offset = boundary; offset < context->count; offset++)
    {
        uint8_t axis;
        NavigationSf6Sample next = NavigationSf6_Corrected(
            &context->history[NavigationSf6_Index(context, offset)], boundary_time, correction);
        for (axis = 0U; axis < 6U; axis++)
        { if (!isfinite(next.state[axis])) { return NAV_SF6_NUMERIC_ERROR; } }
    }
    for (offset = boundary; offset < context->count; offset++)
    {
        uint16_t index = NavigationSf6_Index(context, offset);
        context->history[index] = NavigationSf6_Corrected(&context->history[index], boundary_time, correction);
    }
    context->seen[measurement->group] = 1U;
    context->last_measurement_us[measurement->group] = measurement->measurement_us;
    context->last_receive_us[measurement->group] = measurement->receive_us;
    context->last_sequence[measurement->group] = measurement->sequence;
    *boundary_us = boundary_time;
    return NAV_SF6_OK;
}
