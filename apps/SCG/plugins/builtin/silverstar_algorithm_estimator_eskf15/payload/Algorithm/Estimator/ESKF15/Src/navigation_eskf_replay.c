#include "navigation_eskf_replay_recovery.h"
#include "silverstar_assert.h"

#include <stddef.h>
#include <string.h>

typedef struct
{
    const void *address;
    size_t size;
    uint8_t writable;
} ReplayRegion;

static uint8_t Replay_RegionsValid(const ReplayRegion *region, uint8_t count)
{
    if ((region == NULL) || (count > 10U)) { return 0U; }
    for (uint8_t i = 0U; i < count; i++)
    {
        if (region[i].address == NULL) { return 0U; }
        for (uint8_t j = 0U; j < i; j++)
        {
            uintptr_t a = (uintptr_t)region[i].address, b = (uintptr_t)region[j].address;
            uint8_t overlap = (uint8_t)((a <= b) ?
                (b - a < region[i].size) : (a - b < region[j].size));
            if (overlap && (region[i].writable || region[j].writable)) { return 0U; }
        }
    }
    return 1U;
}

static uint8_t Replay_RecoveryReady(const NavigationEskfReplayRecovery *recovery,
    const NavigationEskfState *state)
{
    if (recovery == NULL) { return 1U; }
    return (uint8_t)((state != NULL) && (recovery->initialized == 1U) &&
        (recovery->anchor.mission == state->generation) &&
        (recovery->current.mission == state->generation) &&
        (recovery->anchor.calibration == recovery->current.calibration) &&
        (NavigationEskfRecovery_PolicyValidate(&recovery->anchor, &recovery->config) == NAV_ESKF_RECOVERY_COMPLETE) &&
        (NavigationEskfRecovery_PolicyValidate(&recovery->current, &recovery->config) == NAV_ESKF_RECOVERY_COMPLETE));
}

static NavigationEskfResult Replay_EventApply(NavigationEskfReplay *history,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    uint16_t index, NavigationEskfOutcome *outcome,
    NavigationEskfReplayRecovery *recovery, NavigationEskfRecoveryAction *action)
{
    const NavigationEskfReplayEvent *event = &history->event[index];
    NavigationEskfRecoveryEvent received = {0};
    NavigationEskfRecoveryOutput output;
    NavigationEskfRecoveryResult result;
    *action = NAV_ESKF_RECOVERY_ACTION_NONE;
    if ((recovery == NULL) || (event->measurement.group >= NAV_ESKF_RECOVERY_GROUPS))
    { return NavigationEskf_Update(&history->working, workspace, config, &event->measurement, outcome); }
    received.receive_us = event->receive_us; received.sequence = event->sequence;
    received.source = event->source; received.mission = event->generation;
    received.calibration = recovery->anchor.calibration;
    received.measurement = event->measurement; received.evidence = recovery->evidence[index];
    result = NavigationEskfRecovery_UpdateCandidate(&history->working, &recovery->working,
        workspace, &recovery->transaction, config, &recovery->config, &received, &output);
    *outcome = output.filter; *action = output.action;
    if ((result == NAV_ESKF_RECOVERY_COMPLETE) || (result == NAV_ESKF_RECOVERY_MODEL_MISMATCH) ||
        (result == NAV_ESKF_RECOVERY_MEASUREMENT_INVALID)) { return output.filter.result; }
    return NAV_ESKF_NUMERIC_ERROR;
}

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
    NavigationEskfOutcome *target_outcome, NavigationEskfReplayRecovery *recovery,
    NavigationEskfRecoveryAction *target_action)
{
    SILVERSTAR_ASSERT_OBJECT(history, NavigationEskfReplay, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(workspace, NavigationEskfWorkspace, SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    uint16_t body_index, event_index = 0U;
    uint32_t steps = 0U;
    history->working = history->anchor;
    if (recovery != NULL) { recovery->working = recovery->anchor; }
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
            NavigationEskfRecoveryAction action;
            const NavigationEskfReplayEvent *event;
            if ((event_index >= history->event_count) ||
                (history->event[event_index].measurement_us > body.end_us)) { break; }
            event = &history->event[event_index];
            if (Replay_PropagatePart(&history->working, workspace, config,
                    &body, event->measurement_us) != NAV_ESKF_REPLAY_OK)
            { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
            result = Replay_EventApply(history, workspace, config, event_index, &outcome, recovery, &action);
            if (result == NAV_ESKF_NUMERIC_ERROR) { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
            if ((target != NULL) && (event->sequence == target->sequence) &&
                (event->source == target->source) &&
                (event->measurement.group == target->measurement.group))
            { *target_outcome = outcome; if (target_action != NULL) { *target_action = action; } }
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

static void Replay_PrefixCommit(NavigationEskfReplay *history, uint16_t body_count,
    NavigationEskfReplayRecovery *recovery)
{
    uint16_t consumed = 0U;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationEskfReplay, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT((body_count > 0U) && (body_count <= history->body_count),
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    history->anchor = history->working;
    if (recovery != NULL) { recovery->anchor = recovery->working; }
    for (uint16_t index = 0U; index < history->event_count; index++)
    { if (history->event[index].measurement_us <= history->anchor.timestamp_us) { consumed++; } }
    for (uint16_t index = consumed; index < history->event_count; index++)
    {
        history->event[index - consumed] = history->event[index];
        if (recovery != NULL) { recovery->evidence[index - consumed] = recovery->evidence[index]; }
    }
    history->event_count = (uint16_t)(history->event_count - consumed);
    for (uint16_t index = body_count; index < history->body_count; index++)
    { history->body[index - body_count] = history->body[index]; }
    history->body_count = (uint16_t)(history->body_count - body_count);
}

static NavigationEskfReplayResult Replay_Predict(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input, NavigationEskfReplayRecovery *recovery)
{
    uint16_t trim_count = 0U;
    if ((history == NULL) || (history->body == NULL) || (state == NULL) || (workspace == NULL) || (input == NULL) ||
        (history->body_count > NAV_ESKF_HISTORY_CAPACITY) ||
        (history->event_count > NAV_ESKF_EVENT_CAPACITY) || !Replay_RecoveryReady(recovery, state))
    { return NAV_ESKF_REPLAY_INVALID; }
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
        NavigationEskfReplayResult planned = Replay_Run(history, workspace, config, trim_count, NULL, NULL, recovery, NULL);
        if (planned != NAV_ESKF_REPLAY_OK) { return planned; }
    }
    if (NavigationEskf_Predict(state, workspace, config, input) != NAV_ESKF_OK)
    { return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
    if (trim_count != 0U) { Replay_PrefixCommit(history, trim_count, recovery); }
    history->body[history->body_count].end_us = input->end_us;
    history->body[history->body_count].dt_s = input->dt_s;
    history->body[history->body_count].quality_flags = input->quality_flags;
    memcpy(history->body[history->body_count].gyro_radps, input->gyro_radps, sizeof(input->gyro_radps));
    memcpy(history->body[history->body_count].accel_mps2, input->accel_mps2, sizeof(input->accel_mps2));
    history->body_count++;
    return NAV_ESKF_REPLAY_OK;
}

static NavigationEskfReplayResult Replay_Insert(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfReplayEvent *event, NavigationEskfOutcome *outcome,
    NavigationEskfReplayRecovery *recovery, const NavigationEskfRecoveryEvidence *evidence,
    NavigationEskfRecoveryAction *action)
{
    uint16_t at;
    NavigationEskfReplayResult result;
    if ((history == NULL) || (history->body == NULL) || (state == NULL) || (workspace == NULL) || (event == NULL) || (outcome == NULL) ||
        (event->generation != state->generation) || (event->measurement.group >= 5U) ||
        (event->receive_us > state->timestamp_us) || (event->measurement_us > event->receive_us) ||
        (history->body_count > NAV_ESKF_HISTORY_CAPACITY) || (history->event_count > NAV_ESKF_EVENT_CAPACITY) ||
        !Replay_RecoveryReady(recovery, state))
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
        history->event[at] = history->event[at - 1U];
        if (recovery != NULL) { recovery->evidence[at] = recovery->evidence[at - 1U]; }
        at--;
    }
    history->event[at] = *event; history->event_count++;
    if (recovery != NULL) { recovery->evidence[at] = *evidence; }
    result = Replay_Run(history, workspace, config, history->body_count, event, outcome, recovery, action);
    if (result == NAV_ESKF_REPLAY_OK)
    {
        *state = history->working; history->replay_count++;
        if (recovery != NULL) { recovery->current = recovery->working; }
    }
    else
    {
        for (uint16_t index = at + 1U; index < history->event_count; index++)
        {
            history->event[index - 1U] = history->event[index];
            if (recovery != NULL) { recovery->evidence[index - 1U] = recovery->evidence[index]; }
        }
        history->event_count--;
    }
    return result;
}

NavigationEskfReplayResult NavigationEskfReplay_Predict(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input)
{ return Replay_Predict(history, state, workspace, config, input, NULL); }

NavigationEskfReplayResult NavigationEskfReplay_Insert(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfReplayEvent *event, NavigationEskfOutcome *outcome)
{ return Replay_Insert(history, state, workspace, config, event, outcome, NULL, NULL, NULL); }

NavigationEskfReplayResult NavigationEskfReplayRecovery_Reset(
    NavigationEskfReplayRecovery *recovery, const NavigationEskfState *state,
    const NavigationEskfRecoveryReplayState *policy, const NavigationEskfRecoveryConfig *config)
{
    const ReplayRegion region[4] = {{recovery, sizeof(*recovery), 1U},
        {state, sizeof(*state), 0U}, {policy, sizeof(*policy), 0U}, {config, sizeof(*config), 0U}};
    if (!Replay_RegionsValid(region, 4U)) { return NAV_ESKF_REPLAY_INVALID; }
    if ((recovery == NULL) || (state == NULL) || (policy == NULL) ||
        (policy->mission != state->generation) || (state->initialized != 1U) ||
        (NavigationEskfRecovery_PolicyValidate(policy, config) != NAV_ESKF_RECOVERY_COMPLETE))
    { return NAV_ESKF_REPLAY_INVALID; }
    memset(recovery, 0, sizeof(*recovery)); recovery->config = *config;
    recovery->anchor = *policy; recovery->current = *policy; recovery->working = *policy;
    recovery->initialized = 1U;
    return NAV_ESKF_REPLAY_OK;
}

NavigationEskfReplayResult NavigationEskfReplayRecovery_Predict(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input, NavigationEskfReplayRecovery *recovery)
{
    if (history == NULL) { return NAV_ESKF_REPLAY_INVALID; }
    const ReplayRegion region[7] = {{recovery, sizeof(*recovery), 1U},
        {history, sizeof(*history), 1U}, {state, sizeof(*state), 1U},
        {workspace, sizeof(*workspace), 1U}, {config, sizeof(*config), 0U},
        {input, sizeof(*input), 0U},
        {history->body, NAV_ESKF_HISTORY_CAPACITY * sizeof(*history->body), 1U}};
    if (!Replay_RegionsValid(region, 7U)) { return NAV_ESKF_REPLAY_INVALID; }
    return Replay_Predict(history, state, workspace, config, input, recovery);
}

NavigationEskfReplayResult NavigationEskfReplayRecovery_Insert(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfReplayEvent *event, NavigationEskfOutcome *outcome,
    NavigationEskfReplayRecovery *recovery, const NavigationEskfRecoveryEvidence *evidence,
    NavigationEskfRecoveryAction *action)
{
    if (history == NULL) { return NAV_ESKF_REPLAY_INVALID; }
    const ReplayRegion region[10] = {{recovery, sizeof(*recovery), 1U},
        {history, sizeof(*history), 1U}, {state, sizeof(*state), 1U},
        {workspace, sizeof(*workspace), 1U}, {config, sizeof(*config), 0U},
        {event, sizeof(*event), 0U}, {outcome, sizeof(*outcome), 1U},
        {evidence, sizeof(*evidence), 0U}, {action, sizeof(*action), 1U},
        {history->body, NAV_ESKF_HISTORY_CAPACITY * sizeof(*history->body), 1U}};
    if (!Replay_RegionsValid(region, 10U)) { return NAV_ESKF_REPLAY_INVALID; }
    *action = NAV_ESKF_RECOVERY_ACTION_NONE;
    return Replay_Insert(history, state, workspace, config, event, outcome, recovery, evidence, action);
}
