Current SF6 replay owner at 7ee9cbc12aeb9dc6ab03d156d2bec781d356f128.

## Algorithm/Estimator/SF6/Inc/navigation_sf6.h

```c
#ifndef __NAVIGATION_SF6_H
#define __NAVIGATION_SF6_H

#include <stdint.h>

#define NAV_SF6_HISTORY_CAPACITY 256U
#define NAV_SF6_EVENT_CAPACITY 256U
#define NAV_SF6_HISTORY_US 600000ULL
#define NAV_SF6_MAX_DT_S 0.02f
#define NAV_SF6_GROUP_COUNT 5U

typedef enum
{
    NAV_SF6_OK = 0,
    NAV_SF6_INVALID_ARGUMENT,
    NAV_SF6_NOT_READY,
    NAV_SF6_STALE,
    NAV_SF6_DUPLICATE,
    NAV_SF6_NUMERIC_ERROR,
    NAV_SF6_FULL
} NavigationSf6Result;

/* State order and gain order are vE, vN, vU, pE, pN, pU. No covariance. */
typedef struct
{
    uint64_t timestamp_us;
    float state[6];
    float delta_velocity[3]; /* Increment leading to this boundary. */
    float dt_s; /* Preserve the admitted integration interval during replay. */
} NavigationSf6Sample;

typedef struct
{
    uint64_t measurement_us;
    float observation[2];
    uint8_t group;
} NavigationSf6Event;

typedef struct
{
    NavigationSf6Sample history[NAV_SF6_HISTORY_CAPACITY];
    NavigationSf6Event events[NAV_SF6_EVENT_CAPACITY];
    float base_state[6]; /* Before observations at the oldest boundary. */
    float gain[6];
    uint64_t last_measurement_us[NAV_SF6_GROUP_COUNT];
    uint64_t last_receive_us[NAV_SF6_GROUP_COUNT];
    uint32_t last_sequence[NAV_SF6_GROUP_COUNT];
    uint16_t first;
    uint16_t count;
    uint16_t event_count;
    uint8_t seen[NAV_SF6_GROUP_COUNT];
    uint8_t initialized;
} NavigationSf6Context;

typedef struct
{
    uint64_t measurement_us;
    uint64_t receive_us;
    uint32_t sequence;
    uint8_t group; /* position EN/U, velocity EN/U, barometer U. */
    float observation[2];
} NavigationSf6Measurement;

void NavigationSf6_Reset(NavigationSf6Context *context);
NavigationSf6Result NavigationSf6_Initialize(NavigationSf6Context *context,
    const float gain[6], const float velocity[3], uint64_t timestamp_us);
NavigationSf6Result NavigationSf6_Predict(NavigationSf6Context *context,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s);
NavigationSf6Result NavigationSf6_Update(NavigationSf6Context *context,
    const NavigationSf6Measurement *measurement, uint64_t *boundary_us);
NavigationSf6Result NavigationSf6_SnapshotGet(const NavigationSf6Context *context,
    NavigationSf6Sample *snapshot);

#endif /* __NAVIGATION_SF6_H */

```

## Algorithm/Estimator/SF6/Src/navigation_sf6.c

```c
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

```

## Algorithm/Estimator/SF6/Src/navigation_sf6_backend.c

```c
#include "system_navigation_backend.h"
#include "navigation_sf6.h"
#include "attitude_frame.h"
#include "ins_mechanization.h"
#include "geodesy_local.h"
#include "estimator_bus.h"
#include "system_gnss_quality.h"
#include "system_barometer.h"
#include "system_estimator_profile.h"
#include "system_source_selector.h"
#include "system_navigation_health.h"
#include "system_time.h"
#include "system_user_config.h"
#include "silverstar_assert.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include <math.h>
#include <string.h>

/* One logical barometer is active. Conservatively cover both the integrated
 * IMU packet rate and the independent barometer configured output rate.
 * These are configuration bounds, not measured MCU timing guarantees. */
#define NAV_SF6_BARO_BOUND_HZ ((SYSTEM_IMU_OUTPUT_RATE_HZ > SYSTEM_BAROMETER_OUTPUT_RATE_HZ) ? SYSTEM_IMU_OUTPUT_RATE_HZ : SYSTEM_BAROMETER_OUTPUT_RATE_HZ)
_Static_assert(4ULL * ((NAV_SF6_HISTORY_US * SYSTEM_GNSS_NAVIGATION_RATE_HZ + 999999ULL) / 1000000ULL + 1ULL) +
    ((NAV_SF6_HISTORY_US * NAV_SF6_BARO_BOUND_HZ + 999999ULL) / 1000000ULL + 1ULL) <= NAV_SF6_EVENT_CAPACITY,
    "SF6 observation capacity cannot retain configured GNSS groups and barometer rate for 600ms");
_Static_assert((NAV_SF6_HISTORY_US * SYSTEM_IMU_OUTPUT_RATE_HZ + 999999ULL) / 1000000ULL + 1ULL <= NAV_SF6_HISTORY_CAPACITY,
    "SF6 prediction capacity cannot retain configured IMU rate for 600ms");

/* CPU-only, single EstimatorTask owner. No KF/ESKF workspace or callback table. */
static NavigationSf6Context s_context;
static GeoLocalFrame s_frame;
static float s_q_nb[4];
static float s_baro_origin;
static uint8_t s_baro_origin_valid;
static uint8_t s_active;
static uint8_t s_started;
static uint8_t s_gnss_source;
static uint8_t s_gnss_seen;
static uint8_t s_baro_seen;
static uint32_t s_gnss_sequence;
static uint32_t s_baro_sequence;
static const float s_gain[6] = {
    SYSTEM_SF6_GAIN_VE, SYSTEM_SF6_GAIN_VN, SYSTEM_SF6_GAIN_VU,
    SYSTEM_SF6_GAIN_PE, SYSTEM_SF6_GAIN_PN, SYSTEM_SF6_GAIN_PU
};

static void Backend_LifecycleValidate(void)
{
    SILVERSTAR_ASSERT(s_active <= 1U && s_started <= 1U && s_baro_origin_valid <= 1U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(!s_baro_origin_valid || isfinite(s_baro_origin),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
}

static void Backend_AttitudeValidate(void)
{
    float norm_squared = 0.0f;
    for (uint8_t axis = 0U; axis < 4U; axis++)
    {
        SILVERSTAR_ASSERT(isfinite(s_q_nb[axis]),
            SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
        norm_squared += s_q_nb[axis] * s_q_nb[axis];
    }
    /* Initialize and every admitted propagation normalize this stored rotation.
     * A 1e-3 squared-norm margin covers float rounding, not arbitrary rotations. */
    SILVERSTAR_ASSERT(norm_squared >= 0.999f && norm_squared <= 1.001f,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

void SystemNavigationBackend_Reset(void)
{
    NavigationSf6_Reset(&s_context);
    memset(&s_frame, 0, sizeof(s_frame));
    memset(s_q_nb, 0, sizeof(s_q_nb));
    s_active = 0U; s_started = 0U; s_gnss_seen = 0U; s_baro_seen = 0U;
    s_baro_origin_valid = 0U;
}

SystemDeviceResult SystemNavigationBackend_Initialize(const float q_nb[4],
    const SystemGnssSample *origin, float barometer_origin_m,
    uint8_t barometer_origin_valid, uint32_t generation, uint8_t activate)
{
    float velocity[3] = {0.0f};
    float quaternion[4];
    uint8_t axis;
    (void)generation; /* SF6 has no covariance generation or bias-state reset. */
    if (q_nb == NULL || origin == NULL || activate > 1U || barometer_origin_valid > 1U ||
        !isfinite(barometer_origin_m)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SystemNavigationBackend_Reset();
    memcpy(quaternion, q_nb, sizeof(quaternion));
    for (axis = 0U; axis < 4U; axis++)
    { if (!isfinite(quaternion[axis])) { return SYSTEM_DEVICE_INVALID_ARGUMENT; } }
    if (!Attitude_QuaternionNormalize(quaternion) || !origin->position_usable ||
        SystemSourceSelector_GnssActiveInstanceGet(&s_gnss_source) != SYSTEM_DEVICE_OK ||
        !GeoLocalFrame_Init(&s_frame, origin->latitude_e7, origin->longitude_e7,
            origin->ellipsoid_height_mm)) { return SYSTEM_DEVICE_NOT_READY; }
    for (axis = 0U; axis < 3U; axis++)
    {
        if ((origin->velocity_valid_mask & (1U << axis)) != 0U)
        { velocity[axis] = origin->velocity_enu_mps[axis]; }
    }
    if (NavigationSf6_Initialize(&s_context, s_gain, velocity, 0U) != NAV_SF6_OK)
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    memcpy(s_q_nb, quaternion, sizeof(s_q_nb));
    s_baro_origin = barometer_origin_m; s_baro_origin_valid = barometer_origin_valid; s_active = activate;
    SystemNavigationHealth_Reset(0U);
    return SYSTEM_DEVICE_OK;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void Backend_StateLog(EstimatorOutputSnapshot *output)
{
    FlightLogSf6StateRecord record = {0};
    record.snapshot_id = output->update_sequence;
    record.algorithm_id = 3U; record.algorithm_revision = 1U;
    record.health = (uint8_t)SystemNavigationHealth_OverallGet(output->timestamp_us, 0x0FU, 0U);
    memcpy(record.position_enu_m, output->position_enu_m, sizeof(record.position_enu_m));
    memcpy(record.velocity_enu_mps, output->velocity_enu_mps, sizeof(record.velocity_enu_mps));
    memcpy(record.q_nb, output->q_nb, sizeof(record.q_nb));
    memcpy(record.gain, s_gain, sizeof(record.gain));
    if (LoggerBus_Sf6StatePush(output->timestamp_us, &record) != LOGGER_BUS_RESULT_OK)
    { output->health_flags |= ESTIMATOR_HEALTH_LOG_EVENT_FAILED; }
}
#endif

static uint8_t Backend_EffectiveGain(uint8_t group)
{
    SILVERSTAR_ASSERT(group < NAV_SF6_GROUP_COUNT,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (group == 0U) { return (uint8_t)(s_gain[3] > 0.0f || s_gain[4] > 0.0f); }
    if (group == 1U || group == 4U) { return (uint8_t)(s_gain[5] > 0.0f); }
    if (group == 2U) { return (uint8_t)(s_gain[0] > 0.0f || s_gain[1] > 0.0f); }
    return (uint8_t)(s_gain[2] > 0.0f);
}

static void Backend_OutcomePublish(const NavigationSf6Measurement *measurement,
    uint8_t physical, NavigationSf6Result result, EstimatorOutputSnapshot *output)
{
    SystemNavigationFusionEvidence evidence = {0};
    uint8_t group = measurement->group;
    uint8_t accepted = (uint8_t)(result == NAV_SF6_OK);
    SystemEstimatorMeasurementResult outcome = accepted ?
        SYSTEM_ESTIMATOR_MEAS_ACCEPTED : SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    SILVERSTAR_ASSERT(group < NAV_SF6_GROUP_COUNT,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    evidence.receive_us = measurement->receive_us;
    evidence.measurement_us = measurement->measurement_us;
    evidence.evaluation_us = output->timestamp_us;
    evidence.sequence = measurement->sequence;
    /* The legacy pressure bus has no endpoint identity. UNKNOWN is explicit;
     * the Baro integration must carry the actual producing endpoint here. */
    evidence.source = group == 4U ? UINT8_MAX : s_gnss_source;
    evidence.physically_valid = physical; evidence.attempted = physical;
    evidence.effective_update = (uint8_t)(accepted && Backend_EffectiveGain(group));
    /* Health uses admission/age only. Statistics are unavailable on the wire. */
    evidence.nis = 0.0f; evidence.variance_scale = 1.0f;
    evidence.reason = (uint8_t)(accepted ? 0U : 16U + (uint32_t)result);
    if (SystemNavigationHealth_Observe(group, &evidence) != SYSTEM_DEVICE_OK)
    { output->health_flags |= ESTIMATOR_HEALTH_GNSS_MEASUREMENT_INVALID; }
    if (group < 2U)
    {
        output->measurement_attempt_mask |= ESTIMATOR_ATTEMPT_GNSS_POSITION;
        output->position_update_result = outcome;
        if (accepted) { output->gnss_position_update_count++; }
        else { output->position_reject_count++; }
    }
    else if (group < 4U)
    {
        output->measurement_attempt_mask |= ESTIMATOR_ATTEMPT_GNSS_VELOCITY;
        output->velocity_update_result = outcome;
        if (accepted) { output->gnss_velocity_update_count++; }
        else { output->velocity_reject_count++; }
    }
    else
    {
        output->measurement_attempt_mask |= ESTIMATOR_ATTEMPT_BAROMETER;
        output->baro_update_result = outcome;
        if (accepted) { output->baro_update_count++; }
        else { output->baro_reject_count++; }
    }
}

static void Backend_MeasurementApply(NavigationSf6Measurement *measurement,
    uint8_t physical, uint64_t sample_us, EstimatorOutputSnapshot *output)
{
    NavigationSf6Result result = NAV_SF6_INVALID_ARGUMENT;
    uint64_t boundary_us = 0U;
    SILVERSTAR_ASSERT(measurement->group < NAV_SF6_GROUP_COUNT,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (physical) { result = NavigationSf6_Update(&s_context, measurement, &boundary_us); }
    Backend_OutcomePublish(measurement, physical, result, output);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    FlightLogSf6MeasurementRecord record = {0};
    record.sample_timestamp_us = sample_us;
    record.receive_timestamp_us = measurement->receive_us;
    record.measurement_timestamp_us = measurement->measurement_us;
    record.evaluation_timestamp_us = output->timestamp_us;
    record.boundary_timestamp_us = boundary_us;
    record.sequence = measurement->sequence; record.group = measurement->group;
    record.physically_valid = physical; record.result = (uint8_t)result;
    record.effective_update = (uint8_t)(result == NAV_SF6_OK && Backend_EffectiveGain(measurement->group));
    memcpy(record.observation, measurement->observation, sizeof(record.observation));
    if (LoggerBus_Sf6MeasurementPush(output->timestamp_us, &record) != LOGGER_BUS_RESULT_OK)
    { output->health_flags |= ESTIMATOR_HEALTH_LOG_EVENT_FAILED; }
#else
    (void)sample_us; /* Retained only by the optional SSLOG adapter. */
#endif

}

static void Backend_GnssGroupApply(const SystemGnssSample *sample,
    const float position[3], uint8_t group, EstimatorOutputSnapshot *output)
{
    NavigationSf6Measurement measurement = {0};
    uint8_t axis, first = (group & 1U) ? 2U : 0U;
    uint8_t count = (group & 1U) ? 1U : 2U;
    uint8_t physical = (uint8_t)((sample->valid_group_mask & (1U << group)) != 0U);
    uint32_t delay = group < 2U ? SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS :
        SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS;
    SILVERSTAR_ASSERT(group < 4U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    measurement.group = group; measurement.receive_us = sample->receive_timestamp_us;
    measurement.sequence = sample->sequence;
    if (SystemTime_MeasurementTimestampResolve(sample->receive_timestamp_us,
        sample->sample_timestamp_us, sample->measurement_timestamp_trusted, delay,
        &measurement.measurement_us) != SYSTEM_MEASUREMENT_TIME_OK) { physical = 0U; }
    for (axis = 0U; axis < count; axis++)
    { measurement.observation[axis] = group < 2U ? position[first + axis] : sample->velocity_enu_mps[first + axis]; }
    Backend_MeasurementApply(&measurement, physical, sample->sample_timestamp_us, output);
}

static void Backend_GnssUpdate(EstimatorOutputSnapshot *output)
{
    SystemGnssSample sample;
    float position[3];
    uint8_t group, source;
    if (SystemSourceSelector_GnssActiveInstanceGet(&source) != SYSTEM_DEVICE_OK) { return; }
    if (source != s_gnss_source)
    {
        /* A different GNSS reference is not supported until mission reinit. */
        output->health_flags |= ESTIMATOR_HEALTH_GNSS_MEASUREMENT_INVALID;
        return;
    }
    if (SystemGnss_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK ||
        sample.receive_timestamp_us > output->timestamp_us ||
        (s_gnss_seen && sample.sequence == s_gnss_sequence)) { return; }
    s_gnss_seen = 1U; s_gnss_sequence = sample.sequence;
    if (SystemGnssQuality_Evaluate(&sample, output->timestamp_us) != SYSTEM_DEVICE_OK)
    { sample.valid_group_mask = 0U; }
    if (!GeoLocalFrame_ToEnu(&s_frame,
        sample.valid_group_mask & 1U ? sample.latitude_e7 : s_frame.origin_lat_e7,
        sample.valid_group_mask & 1U ? sample.longitude_e7 : s_frame.origin_lon_e7,
        sample.valid_group_mask & 2U ? sample.ellipsoid_height_mm : s_frame.origin_height_mm, position))
    { memset(position, 0, sizeof(position)); sample.valid_group_mask &= (uint8_t)~3U; }
    output->last_gnss_timestamp_us = sample.receive_timestamp_us;
    output->last_gnss_sequence = sample.sequence;
    memcpy(output->gnss_position_enu_m, position, sizeof(position));
    memcpy(output->gnss_velocity_enu_mps, sample.velocity_enu_mps, sizeof(sample.velocity_enu_mps));
    for (group = 0U; group < 4U; group++)
    { Backend_GnssGroupApply(&sample, position, group, output); }
}

static void Backend_BarometerUpdate(EstimatorOutputSnapshot *output)
{
    EstimatorPressureSnapshot pressure;
    SystemBarometerSample sample = {0};
    NavigationSf6Measurement measurement = {0};
    float altitude;
    uint8_t physical;
    if (!EstimatorBus_PressureGetLatest(&pressure) ||
        pressure.receive_timestamp_us > output->timestamp_us ||
        (s_baro_seen && pressure.sequence == s_baro_sequence)) { return; }
    s_baro_seen = 1U; s_baro_sequence = pressure.sequence;
    sample.pressure_pa = pressure.pressure_pa; sample.altitude_m = pressure.altitude_m;
    sample.supported_fields = pressure.supported_fields; sample.valid_fields = pressure.valid_fields;
    physical = (uint8_t)(s_baro_origin_valid && pressure.valid == 1U && pressure.healthy == 1U &&
        output->timestamp_us - pressure.receive_timestamp_us <= SYSTEM_ESTIMATOR_MEASUREMENT_MAX_AGE_US &&
        SystemBarometer_AltitudeResolve(&sample, &altitude) == SYSTEM_DEVICE_OK);
    measurement.group = 4U; measurement.sequence = pressure.sequence;
    measurement.receive_us = pressure.receive_timestamp_us;
    if (SystemTime_MeasurementTimestampResolve(pressure.receive_timestamp_us,
        pressure.timestamp_us, pressure.measurement_timestamp_trusted,
        SYSTEM_ESTIMATOR_BARO_MEASUREMENT_DELAY_MS, &measurement.measurement_us) != SYSTEM_MEASUREMENT_TIME_OK)
    { physical = 0U; }
    if (physical) { measurement.observation[0] = altitude - s_baro_origin; }
    output->last_baro_timestamp_us = pressure.receive_timestamp_us;
    output->last_baro_sequence = pressure.sequence;
    output->baro_relative_altitude_m = physical ? measurement.observation[0] : NAN;
    Backend_MeasurementApply(&measurement, physical, pressure.timestamp_us, output);
}

SystemDeviceResult SystemNavigationBackend_SnapshotGet(EstimatorOutputSnapshot *output)
{
    NavigationSf6Sample snapshot;
    uint8_t axis;
    if (output == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    Backend_LifecycleValidate();
    if (NavigationSf6_SnapshotGet(&s_context, &snapshot) != NAV_SF6_OK)
    { return SYSTEM_DEVICE_NOT_READY; }
    Backend_AttitudeValidate();
    output->timestamp_us = snapshot.timestamp_us;
    memcpy(output->velocity_enu_mps, snapshot.state, 3U * sizeof(float));
    memcpy(output->position_enu_m, &snapshot.state[3], 3U * sizeof(float));
    memcpy(output->q_nb, s_q_nb, sizeof(s_q_nb));
    output->initialized = 1U; output->mission_running = s_active;
    output->gnss_origin_valid = s_frame.valid; output->baro_origin_valid = s_baro_origin_valid;
    if (!s_baro_origin_valid) { output->health_flags |= ESTIMATOR_HEALTH_BARO_ORIGIN_UNAVAILABLE; }
    for (axis = 0U; axis < 6U; axis++)
    {
        uint8_t column;
        output->covariance_diagonal[axis] = NAN;
        for (column = 0U; column < 6U; column++) { output->covariance[axis][column] = NAN; }
    }
    for (axis = 0U; axis < 3U; axis++)
    {
        output->position_variance_r[axis] = NAN; output->velocity_variance_r[axis] = NAN;
        output->process_accel_std_mps2[axis] = NAN;
    }
    output->baro_variance_r = NAN;
    output->last_position_nis = NAN; output->last_velocity_nis = NAN; output->last_baro_nis = NAN;
    output->position_r_scale = NAN; output->velocity_r_scale = NAN; output->baro_r_scale = NAN;
    if (SystemNavigationHealth_DegradedGet(snapshot.timestamp_us))
    { output->health_flags |= ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    else { output->health_flags &= ~ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemNavigationBackend_Predict(
    const SystemInertialIncrement *input, EstimatorOutputSnapshot *output)
{
    float delta_velocity[3], quaternion[4];
    NavigationSf6Sample previous;
    uint64_t duration;
    uint8_t axis;
    if (input == NULL || output == NULL || !isfinite(input->dt_s) ||
        input->dt_s <= 0.0f || input->dt_s > NAV_SF6_MAX_DT_S)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    Backend_LifecycleValidate();
    if (!s_active || NavigationSf6_SnapshotGet(&s_context, &previous) != NAV_SF6_OK)
    { return SYSTEM_DEVICE_NOT_READY; }
    Backend_AttitudeValidate();
    duration = (uint64_t)llroundf(input->dt_s * 1000000.0f);
    if (duration == 0U || input->timestamp_us < duration) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (!Attitude_PropagateQuaternionBodyIncrement(s_q_nb, input->delta_theta_b_corrected, quaternion))
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    Ins_TransformDeltaVelocityToNavigation(s_q_nb, input->delta_velocity_b_sculling_corrected,
        input->dt_s, SYSTEM_INS_GRAVITY_MPS2, delta_velocity);
    for (axis = 0U; axis < 3U; axis++)
    { if (!isfinite(delta_velocity[axis])) { return SYSTEM_DEVICE_INVALID_ARGUMENT; } }
    if (!s_started)
    {
        if (NavigationSf6_Initialize(&s_context, s_gain, previous.state,
            input->timestamp_us - duration) != NAV_SF6_OK) { return SYSTEM_DEVICE_VERIFY_FAILED; }
        SystemNavigationHealth_EpochSet(input->timestamp_us - duration); s_started = 1U;
    }
    if (NavigationSf6_Predict(&s_context, input->timestamp_us, delta_velocity, input->dt_s) != NAV_SF6_OK)
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    memcpy(s_q_nb, quaternion, sizeof(s_q_nb));
    output->timestamp_us = input->timestamp_us; output->measurement_attempt_mask = 0U;
    for (axis = 0U; axis < 3U; axis++) { output->acceleration_enu_mps2[axis] = delta_velocity[axis] / input->dt_s; }
    Backend_GnssUpdate(output); Backend_BarometerUpdate(output);
    output->predict_count++; output->update_sequence++;
    if (SystemNavigationBackend_SnapshotGet(output) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_INTERNAL_ERROR; }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_StateLog(output);
#endif
    return SYSTEM_DEVICE_OK;
}

```

