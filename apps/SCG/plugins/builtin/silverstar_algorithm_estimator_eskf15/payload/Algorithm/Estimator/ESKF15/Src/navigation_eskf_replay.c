#include "navigation_eskf_replay.h"
#include "silverstar_assert.h"

#include <stddef.h>
#include <string.h>

NavigationEskfReplayResult NavigationEskfReplay_Reset(
    NavigationEskfReplay *history, const NavigationEskfState *state,
    NavigationEskfHistoryInput body_storage[NAV_ESKF_HISTORY_CAPACITY])
{
    if ((history == NULL) || (state == NULL) || (body_storage == NULL) || (state->initialized == 0U))
    { return NAV_ESKF_REPLAY_INVALID; }
    memset(history, 0, sizeof(*history));
    history->body = body_storage;
    history->anchor = *state;
    history->working = *state;
    return NAV_ESKF_REPLAY_OK;
}

static uint8_t Replay_EventBefore(const NavigationEskfReplayEvent *left,
    const NavigationEskfReplayEvent *right)
{
    if (left->measurement_us != right->measurement_us)
    { return (uint8_t)(left->measurement_us < right->measurement_us); }
    if (left->measurement.group != right->measurement.group)
    { return (uint8_t)(left->measurement.group < right->measurement.group); }
    if (left->source != right->source) { return (uint8_t)(left->source < right->source); }
    return (uint8_t)(left->sequence < right->sequence);
}

static NavigationEskfReplayResult Replay_PropagatePart(NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *body, uint64_t end_us)
{
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(body, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    NavigationEskfBodyInput part = *body;
    if (state->timestamp_us == end_us) { return NAV_ESKF_REPLAY_OK; }
    if ((end_us < state->timestamp_us) || (end_us > body->end_us) ||
        (state->timestamp_us < body->start_us)) { return NAV_ESKF_REPLAY_INVALID; }
    if ((state->timestamp_us == body->start_us) && (end_us == body->end_us))
    {
        return (NavigationEskf_Predict(state, workspace, config, body) == NAV_ESKF_OK) ?
            NAV_ESKF_REPLAY_OK : NAV_ESKF_REPLAY_NUMERIC_ERROR;
    }
    /* A subinterval only sees its own half's body sample. In particular the
       first half cannot borrow the future second sample after a rewind. */
    for (uint32_t half = 0U; half < 2U; half++)
    {
        uint64_t boundary = (half == 0U) ?
            body->start_us + (body->end_us - body->start_us) / 2U : body->end_us;
        uint64_t target = (end_us < boundary) ? end_us : boundary;
        if (target <= state->timestamp_us) { continue; }
        part.start_us = state->timestamp_us;
        part.end_us = target;
        part.dt_s = (float)(target - part.start_us) * 1.0e-6f;
        for (uint32_t sample = 0U; sample < 2U; sample++)
        {
            memcpy(part.gyro_radps[sample], body->gyro_radps[half], sizeof(part.gyro_radps[sample]));
            memcpy(part.accel_mps2[sample], body->accel_mps2[half], sizeof(part.accel_mps2[sample]));
        }
        if (NavigationEskf_Predict(state, workspace, config, &part) != NAV_ESKF_OK)
        { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
    }
    return NAV_ESKF_REPLAY_OK;
}

static NavigationEskfReplayResult Replay_Run(NavigationEskfReplay *history,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    uint16_t body_count, const NavigationEskfReplayEvent *target,
    NavigationEskfOutcome *target_outcome)
{
    SILVERSTAR_ASSERT_OBJECT(history, NavigationEskfReplay, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(workspace, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint16_t body_index, event_index = 0U;
    uint32_t steps = 0U;
    history->working = history->anchor;
    for (body_index = 0U; body_index < body_count; body_index++)
    {
        NavigationEskfBodyInput body;
        const NavigationEskfHistoryInput *stored = &history->body[body_index];
        body.start_us = history->working.timestamp_us; body.end_us = stored->end_us;
        body.dt_s = stored->dt_s; body.quality_flags = stored->quality_flags;
        body.source = history->anchor.source; body.generation = history->anchor.generation;
        memcpy(body.gyro_radps, stored->gyro_radps, sizeof(body.gyro_radps));
        memcpy(body.accel_mps2, stored->accel_mps2, sizeof(body.accel_mps2));
        for (uint16_t limit = 0U; limit < NAV_ESKF_EVENT_CAPACITY; limit++)
        {
            NavigationEskfOutcome outcome;
            NavigationEskfResult result;
            const NavigationEskfReplayEvent *event;
            if ((event_index >= history->event_count) ||
                (history->event[event_index].measurement_us > body.end_us)) { break; }
            event = &history->event[event_index];
            if (Replay_PropagatePart(&history->working, workspace, config,
                    &body, event->measurement_us) != NAV_ESKF_REPLAY_OK)
            { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
            result = NavigationEskf_Update(&history->working, workspace, config,
                &event->measurement, &outcome);
            if (result == NAV_ESKF_NUMERIC_ERROR) { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
            if ((target != NULL) && (event->sequence == target->sequence) &&
                (event->source == target->source) &&
                (event->measurement.group == target->measurement.group)) { *target_outcome = outcome; }
            event_index++; steps += 2U;
        }
        if (Replay_PropagatePart(&history->working, workspace, config, &body, body.end_us) != NAV_ESKF_REPLAY_OK)
        { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
        steps++;
    }
    if (steps > NAV_ESKF_REPLAY_MAX_STEPS) { return NAV_ESKF_REPLAY_OVERFLOW; }
    history->last_steps = steps;
    if (steps > history->maximum_steps) { history->maximum_steps = steps; }
    return NAV_ESKF_REPLAY_OK;
}

static void Replay_PrefixCommit(NavigationEskfReplay *history, uint16_t body_count)
{
    uint16_t consumed = 0U;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationEskfReplay, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT((body_count > 0U) && (body_count <= history->body_count),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    history->anchor = history->working;
    for (uint16_t index = 0U; index < history->event_count; index++)
    { if (history->event[index].measurement_us <= history->anchor.timestamp_us) { consumed++; } }
    for (uint16_t index = consumed; index < history->event_count; index++)
    { history->event[index - consumed] = history->event[index]; }
    history->event_count = (uint16_t)(history->event_count - consumed);
    for (uint16_t index = body_count; index < history->body_count; index++)
    { history->body[index - body_count] = history->body[index]; }
    history->body_count = (uint16_t)(history->body_count - body_count);
}

NavigationEskfReplayResult NavigationEskfReplay_Predict(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input)
{
    uint16_t trim_count = 0U;
    if ((history == NULL) || (history->body == NULL) || (state == NULL) || (workspace == NULL) || (input == NULL) ||
        (history->body_count > NAV_ESKF_HISTORY_CAPACITY) ||
        (history->event_count > NAV_ESKF_EVENT_CAPACITY)) { return NAV_ESKF_REPLAY_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(history, NavigationEskfReplay, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if (((input->quality_flags & 0x08U) != 0U) && (history->body_count != 0U))
    { return NAV_ESKF_REPLAY_INVALID; }
    if ((input->start_us != state->timestamp_us) || (input->end_us <= input->start_us))
    { return NAV_ESKF_REPLAY_INVALID; }
    for (uint16_t index = 0U; index < history->body_count; index++)
    {
        if ((input->end_us < history->body[index].end_us) ||
            (input->end_us - history->body[index].end_us < NAV_ESKF_HISTORY_WINDOW_US)) { break; }
        trim_count++;
    }
    if ((uint16_t)(history->body_count - trim_count) >= NAV_ESKF_HISTORY_CAPACITY)
    { history->overflows++; return NAV_ESKF_REPLAY_OVERFLOW; }
    /* working and workspace are scratch, never authoritative history. Build
       the prospective anchor without removing anything; prediction itself
       commits live state only after all numerical/input checks succeed. */
    if (trim_count != 0U)
    {
        NavigationEskfReplayResult planned = Replay_Run(history, workspace, config, trim_count, NULL, NULL);
        if (planned != NAV_ESKF_REPLAY_OK) { return planned; }
    }
    if (NavigationEskf_Predict(state, workspace, config, input) != NAV_ESKF_OK)
    { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
    if (trim_count != 0U) { Replay_PrefixCommit(history, trim_count); }
    history->body[history->body_count].end_us = input->end_us;
    history->body[history->body_count].dt_s = input->dt_s;
    history->body[history->body_count].quality_flags = input->quality_flags;
    memcpy(history->body[history->body_count].gyro_radps, input->gyro_radps, sizeof(input->gyro_radps));
    memcpy(history->body[history->body_count].accel_mps2, input->accel_mps2, sizeof(input->accel_mps2));
    history->body_count++;
    return NAV_ESKF_REPLAY_OK;
}

NavigationEskfReplayResult NavigationEskfReplay_Insert(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfReplayEvent *event, NavigationEskfOutcome *outcome)
{
    uint16_t at;
    NavigationEskfReplayResult result;
    if ((history == NULL) || (history->body == NULL) || (state == NULL) || (workspace == NULL) || (event == NULL) || (outcome == NULL) ||
        (event->generation != state->generation) || (event->measurement.group >= 5U) ||
        (event->receive_us > state->timestamp_us) || (event->measurement_us > event->receive_us) ||
        (history->body_count > NAV_ESKF_HISTORY_CAPACITY) || (history->event_count > NAV_ESKF_EVENT_CAPACITY))
    { return NAV_ESKF_REPLAY_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(history, NavigationEskfReplay, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationEskfState, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if ((event->measurement_us <= history->anchor.timestamp_us) || (history->body_count == 0U))
    { history->history_misses++; return NAV_ESKF_REPLAY_HISTORY_MISS; }
    if (history->event_count >= NAV_ESKF_EVENT_CAPACITY)
    { history->overflows++; return NAV_ESKF_REPLAY_OVERFLOW; }
    for (at = 0U; at < history->event_count; at++)
    {
        if ((history->event[at].source == event->source) && (history->event[at].sequence == event->sequence) &&
            (history->event[at].measurement.group == event->measurement.group)) { return NAV_ESKF_REPLAY_DUPLICATE; }
    }
    at = history->event_count;
    for (uint16_t limit = 0U; limit < NAV_ESKF_EVENT_CAPACITY; limit++)
    {
        if ((at == 0U) || (Replay_EventBefore(event, &history->event[at - 1U]) == 0U)) { break; }
        history->event[at] = history->event[at - 1U]; at--;
    }
    history->event[at] = *event; history->event_count++;
    result = Replay_Run(history, workspace, config, history->body_count, event, outcome);
    if (result == NAV_ESKF_REPLAY_OK)
    { *state = history->working; history->replay_count++; }
    else
    {
        for (uint16_t index = at + 1U; index < history->event_count; index++)
        { history->event[index - 1U] = history->event[index]; }
        history->event_count--;
    }
    return result;
}
