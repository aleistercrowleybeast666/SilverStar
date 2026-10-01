#include "navigation_sf6.h"
#include "silverstar_assert.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

/* EstimatorTask owns the context. Replay keeps every admitted observation,
 * including gain-zero observations, in stable measurement-time order. */
typedef struct
{
    float state[6];
    uint16_t event;
    uint8_t candidate_applied;
} NavigationSf6ReplayCursor;

static void NavigationSf6_ContextValidate(const NavigationSf6Context *context)
{
    SILVERSTAR_ASSERT(context->initialized <= 1U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(context->first < NAV_SF6_HISTORY_CAPACITY &&
        context->count <= NAV_SF6_HISTORY_CAPACITY && context->event_count <= NAV_SF6_EVENT_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT(!context->initialized || context->count != 0U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (context->initialized)
    {
        uint16_t latest = (uint16_t)((context->first + context->count - 1U) % NAV_SF6_HISTORY_CAPACITY);
        for (uint8_t axis = 0U; axis < 6U; axis++)
        {
            SILVERSTAR_ASSERT(isfinite(context->history[latest].state[axis]) && isfinite(context->base_state[axis]),
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
    memcpy(context->history[0].state, velocity, 3U * sizeof(float));
    memcpy(context->base_state, context->history[0].state, sizeof(context->base_state));
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

static void NavigationSf6_OldestDrop(NavigationSf6Context *context)
{
    uint16_t next, removed = 0U;
    float base[6];
    NavigationSf6Result result;
    SILVERSTAR_ASSERT(context->count > 1U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    next = NavigationSf6_Index(context, 1U);
    SILVERSTAR_ASSERT(context->history[next].timestamp_us > context->history[context->first].timestamp_us,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    memcpy(base, context->history[context->first].state, sizeof(base));
    result = NavigationSf6_StateAdvance(base, context->history[next].delta_velocity,
        context->history[next].dt_s);
    SILVERSTAR_ASSERT(result == NAV_SF6_OK,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
    memcpy(context->base_state, base, sizeof(base));
    context->first = next; context->count--;
    for (uint16_t index = 0U; index < NAV_SF6_EVENT_CAPACITY; index++)
    {
        if (index >= context->event_count || context->events[index].measurement_us >= context->history[next].timestamp_us)
        { break; }
        removed++;
    }
    if (removed != 0U)
    {
        context->event_count = (uint16_t)(context->event_count - removed);
        memmove(context->events, &context->events[removed], (size_t)context->event_count * sizeof(context->events[0]));
    }
}

static void NavigationSf6_Append(NavigationSf6Context *context, const NavigationSf6Sample *next)
{
    uint16_t index;
    NavigationSf6_ContextValidate(context);
    SILVERSTAR_ASSERT(next->timestamp_us > context->history[NavigationSf6_Index(context, (uint16_t)(context->count - 1U))].timestamp_us,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    if (context->count == NAV_SF6_HISTORY_CAPACITY) { NavigationSf6_OldestDrop(context); }
    index = (uint16_t)((context->first + context->count) % NAV_SF6_HISTORY_CAPACITY);
    context->history[index] = *next; context->count++;
    for (index = 0U; index < NAV_SF6_HISTORY_CAPACITY; index++)
    {
        if (context->count <= 1U || next->timestamp_us - context->history[context->first].timestamp_us <= NAV_SF6_HISTORY_US)
        { break; }
        NavigationSf6_OldestDrop(context);
    }
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
    next.dt_s = dt_s;
    next.timestamp_us = timestamp_us;
    NavigationSf6_Append(context, &next);
    return NAV_SF6_OK;
}

static uint16_t NavigationSf6_BoundaryFind(const NavigationSf6Context *context, uint64_t measurement_us)
{
    uint16_t boundary = 0U;
    for (uint16_t offset = 0U; offset < context->count; offset++)
    {
        uint64_t timestamp = context->history[NavigationSf6_Index(context, offset)].timestamp_us;
        if (offset != 0U)
        {
            SILVERSTAR_ASSERT(timestamp > context->history[NavigationSf6_Index(context, (uint16_t)(offset - 1U))].timestamp_us,
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
        }
        if (timestamp > measurement_us) { break; }
        boundary = offset;
    }
    return boundary;
}

static NavigationSf6Result NavigationSf6_MeasurementValidate(const NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement)
{
    uint8_t group = measurement->group;
    uint64_t present = context->history[NavigationSf6_Index(context, (uint16_t)(context->count - 1U))].timestamp_us;
    if (group >= NAV_SF6_GROUP_COUNT || measurement->receive_us > present ||
        measurement->measurement_us > measurement->receive_us || !isfinite(measurement->observation[0]) ||
        ((group == 0U || group == 2U) && !isfinite(measurement->observation[1]))) { return NAV_SF6_INVALID_ARGUMENT; }
    if (measurement->measurement_us < context->history[context->first].timestamp_us) { return NAV_SF6_STALE; }
    if (context->seen[group] && (measurement->measurement_us <= context->last_measurement_us[group] ||
        measurement->receive_us <= context->last_receive_us[group] ||
        (uint32_t)(measurement->sequence - context->last_sequence[group]) == 0U ||
        (uint32_t)(measurement->sequence - context->last_sequence[group]) >= 0x80000000UL)) { return NAV_SF6_DUPLICATE; }
    if (context->event_count == NAV_SF6_EVENT_CAPACITY) { return NAV_SF6_FULL; }
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

static NavigationSf6Result NavigationSf6_ReplayEvents(const NavigationSf6Context *context,
    const NavigationSf6Measurement *candidate, uint64_t next_us, uint8_t last, NavigationSf6ReplayCursor *cursor)
{
    for (uint16_t processed = 0U; processed <= NAV_SF6_EVENT_CAPACITY; processed++)
    {
        uint8_t existing = (uint8_t)(cursor->event < context->event_count && (last || context->events[cursor->event].measurement_us < next_us));
        uint8_t pending = (uint8_t)(!cursor->candidate_applied && (last || candidate->measurement_us < next_us));
        NavigationSf6Result result;
        if (!existing && !pending) { break; }
        if (existing && (!pending || context->events[cursor->event].measurement_us < candidate->measurement_us ||
            (context->events[cursor->event].measurement_us == candidate->measurement_us && context->events[cursor->event].group <= candidate->group)))
        {
            const NavigationSf6Event *event = &context->events[cursor->event];
            SILVERSTAR_ASSERT(event->measurement_us >= context->history[context->first].timestamp_us &&
                event->measurement_us <= context->history[NavigationSf6_Index(context, (uint16_t)(context->count - 1U))].timestamp_us,
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
            SILVERSTAR_ASSERT(cursor->event == 0U || event->measurement_us > context->events[cursor->event - 1U].measurement_us ||
                (event->measurement_us == context->events[cursor->event - 1U].measurement_us && event->group >= context->events[cursor->event - 1U].group),
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
            result = NavigationSf6_StateObserve(cursor->state, context->gain, event->group, event->observation);
            cursor->event++;
        }
        else
        {
            result = NavigationSf6_StateObserve(cursor->state, context->gain, candidate->group, candidate->observation);
            cursor->candidate_applied = 1U;
        }
        if (result != NAV_SF6_OK) { return result; }
    }
    return NAV_SF6_OK;
}

static NavigationSf6Result NavigationSf6_ReplayRun(NavigationSf6Context *context,
    const NavigationSf6Measurement *candidate, uint8_t publish)
{
    NavigationSf6ReplayCursor cursor = {0};
    memcpy(cursor.state, context->base_state, sizeof(cursor.state));
    for (uint16_t offset = 0U; offset < context->count; offset++)
    {
        uint16_t index = NavigationSf6_Index(context, offset);
        uint64_t next_us = UINT64_MAX;
        NavigationSf6Result result;
        for (uint8_t axis = 0U; axis < 6U; axis++)
        {
            SILVERSTAR_ASSERT(isfinite(context->history[index].state[axis]),
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
        }
        if (offset != 0U)
        {
            uint64_t previous_us = context->history[NavigationSf6_Index(context, (uint16_t)(offset - 1U))].timestamp_us;
            SILVERSTAR_ASSERT(context->history[index].timestamp_us > previous_us,
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
            SILVERSTAR_ASSERT(isfinite(context->history[index].dt_s) && context->history[index].dt_s > 0.0f &&
                context->history[index].dt_s <= NAV_SF6_MAX_DT_S,
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
            SILVERSTAR_ASSERT(context->history[index].timestamp_us - previous_us ==
                (uint64_t)llroundf(context->history[index].dt_s * 1000000.0f),
                SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
            for (uint8_t axis = 0U; axis < 3U; axis++)
            {
                SILVERSTAR_ASSERT(isfinite(context->history[index].delta_velocity[axis]),
                    SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
            }
            result = NavigationSf6_StateAdvance(cursor.state, context->history[index].delta_velocity,
                context->history[index].dt_s);
            if (result != NAV_SF6_OK) { return result; }
        }
        if (offset + 1U < context->count) { next_us = context->history[NavigationSf6_Index(context, (uint16_t)(offset + 1U))].timestamp_us; }
        result = NavigationSf6_ReplayEvents(context, candidate, next_us, (uint8_t)(offset + 1U == context->count), &cursor);
        if (result != NAV_SF6_OK) { return result; }
        if (publish) { memcpy(context->history[index].state, cursor.state, sizeof(cursor.state)); }
    }
    SILVERSTAR_ASSERT(cursor.candidate_applied && cursor.event == context->event_count,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    return NAV_SF6_OK;
}

static void NavigationSf6_EventInsert(NavigationSf6Context *context, const NavigationSf6Measurement *measurement)
{
    uint16_t insertion = context->event_count;
    SILVERSTAR_ASSERT(context->event_count < NAV_SF6_EVENT_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (uint16_t moved = 0U; moved < context->event_count; moved++)
    {
        if (insertion == 0U || context->events[insertion - 1U].measurement_us < measurement->measurement_us ||
            (context->events[insertion - 1U].measurement_us == measurement->measurement_us && context->events[insertion - 1U].group <= measurement->group)) { break; }
        context->events[insertion] = context->events[insertion - 1U]; insertion--;
    }
    context->events[insertion].measurement_us = measurement->measurement_us;
    memcpy(context->events[insertion].observation, measurement->observation, sizeof(measurement->observation));
    context->events[insertion].group = measurement->group; context->event_count++;
}

NavigationSf6Result NavigationSf6_Update(NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement, uint64_t *boundary_us)
{
    NavigationSf6Result result;
    uint16_t boundary;
    if (context == NULL || measurement == NULL || boundary_us == NULL) { return NAV_SF6_INVALID_ARGUMENT; }
    NavigationSf6_ContextValidate(context);
    if (!context->initialized) { return NAV_SF6_NOT_READY; }
    result = NavigationSf6_MeasurementValidate(context, measurement);
    if (result != NAV_SF6_OK) { return result; }
    boundary = NavigationSf6_BoundaryFind(context, measurement->measurement_us);
    result = NavigationSf6_ReplayRun(context, measurement, 0U);
    if (result != NAV_SF6_OK) { return result; }
    /* Single owner, identical validated inputs: commit cannot newly overflow. */
    result = NavigationSf6_ReplayRun(context, measurement, 1U);
    SILVERSTAR_ASSERT(result == NAV_SF6_OK,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    NavigationSf6_EventInsert(context, measurement);
    context->seen[measurement->group] = 1U;
    context->last_measurement_us[measurement->group] = measurement->measurement_us;
    context->last_receive_us[measurement->group] = measurement->receive_us;
    context->last_sequence[measurement->group] = measurement->sequence;
    *boundary_us = context->history[NavigationSf6_Index(context, boundary)].timestamp_us;
    return NAV_SF6_OK;
}
