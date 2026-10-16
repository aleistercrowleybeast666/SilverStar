/* CPU-only replay transaction checks; explicit synthetic policy, no flight tuning. */
#include "navigation_eskf_replay_recovery.h"
#include <math.h>
#include <string.h>

int Test_RecoveryReplay(uint32_t scenario);
int Test_Prepare(NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    NavigationEskfConfig *filter, NavigationEskfRecoveryConfig *config,
    NavigationEskfRecoveryReceiveState *receive, NavigationEskfRecoveryReplayState *policy,
    const float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM]);

#define CHECK(predicate) do { if (!(predicate)) { return __LINE__; } } while (0)

static NavigationEskfReplay s_history[2];
static NavigationEskfHistoryInput s_body[2][NAV_ESKF_HISTORY_CAPACITY];
static NavigationEskfState s_state[2];
static NavigationEskfWorkspace s_workspace;
static NavigationEskfReplayRecovery s_recovery[2];
static NavigationEskfRecoveryReceiveState s_receive;
static NavigationEskfRecoveryReplayState s_policy;
static NavigationEskfRecoveryConfig s_config;
static NavigationEskfConfig s_filter;
static NavigationEskfState s_saved_state;
static NavigationEskfRecoveryReplayState s_saved_policy;

static int ReplayTest_Reset(void)
{
    float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM] = {{0}};
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++) { covariance[i][i] = 0.05f; }
    CHECK(Test_Prepare(&s_state[0], &s_workspace, &s_filter, &s_config, &s_receive,
        &s_policy, (const float (*)[NAV_ESKF_DIM])covariance) == NAV_ESKF_RECOVERY_COMPLETE);
    s_state[1] = s_state[0];
    for (uint8_t i = 0U; i < 2U; i++)
    {
        CHECK(NavigationEskfReplay_Reset(&s_history[i], &s_state[i], s_body[i]) == NAV_ESKF_REPLAY_OK);
        CHECK(NavigationEskfReplayRecovery_Reset(&s_recovery[i], &s_state[i], &s_policy, &s_config) == NAV_ESKF_REPLAY_OK);
    }
    return 0;
}

static int ReplayTest_Bodies(uint32_t steps)
{
    for (uint32_t step = 0U; step < steps; step++)
    {
        NavigationEskfBodyInput input = {0};
        input.start_us = s_state[0].timestamp_us; input.end_us = input.start_us + 10000U;
        input.dt_s = 0.01f; input.source = 13U; input.generation = 7U;
        input.accel_mps2[0][2] = s_filter.gravity_mps2;
        input.accel_mps2[1][2] = s_filter.gravity_mps2;
        for (uint8_t track = 0U; track < 2U; track++)
        {
            CHECK(NavigationEskfReplayRecovery_Predict(&s_history[track], &s_state[track],
                &s_workspace, &s_filter, &input, &s_recovery[track]) == NAV_ESKF_REPLAY_OK);
        }
    }
    return 0;
}

static void ReplayTest_Event(uint32_t ordinal, NavigationEskfReplayEvent *event,
    NavigationEskfRecoveryEvidence *evidence)
{
    memset(event, 0, sizeof(*event)); memset(evidence, 0, sizeof(*evidence));
    event->measurement_us = 1000000ULL + (uint64_t)ordinal * 100000ULL;
    event->receive_us = 1400000ULL; event->sequence = ordinal; event->source = 0U;
    event->generation = 7U; event->measurement.group = 0U;
    event->measurement.physically_valid = 1U;
    event->measurement.observation[0] = 1000.0f; event->measurement.observation[1] = -1000.0f;
    event->measurement.variance[0] = 1.0f; event->measurement.variance[1] = 1.0f;
    evidence->ordinal = ordinal; evidence->chain = 1U; evidence->qualified = 1U;
    for (uint8_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++) { evidence->loss_tokens[i] = 1U; }
}

static int ReplayTest_Reorder(void)
{
    const uint32_t order[2][3] = {{1U, 2U, 3U}, {3U, 1U, 2U}};
    NavigationEskfRecoveryReceiveState original_receive = s_receive;
    for (uint8_t track = 0U; track < 2U; track++)
    {
        for (uint8_t index = 0U; index < 3U; index++)
        {
            NavigationEskfReplayEvent event;
            NavigationEskfRecoveryEvidence evidence;
            NavigationEskfOutcome outcome;
            NavigationEskfRecoveryAction action;
            ReplayTest_Event(order[track][index], &event, &evidence);
            CHECK(NavigationEskfReplayRecovery_Insert(&s_history[track], &s_state[track], &s_workspace,
                &s_filter, &event, &outcome, &s_recovery[track], &evidence, &action) == NAV_ESKF_REPLAY_OK);
            CHECK(outcome.result == NAV_ESKF_REJECTED_NIS);
            if ((track == 0U) && (index == 2U)) { CHECK(action == NAV_ESKF_RECOVERY_ACTION_SCALED); }
        }
    }
    CHECK(memcmp(&s_state[0], &s_state[1], sizeof(s_state[0])) == 0);
    CHECK(memcmp(&s_recovery[0].current, &s_recovery[1].current, sizeof(s_policy)) == 0);
    CHECK(s_recovery[0].current.attempts == 1U && s_recovery[0].current.last_scale_ordinal == 3U);
    CHECK(memcmp(&s_receive, &original_receive, sizeof(s_receive)) == 0);
    return 0;
}

static int ReplayTest_Fault(uint32_t scenario)
{
    NavigationEskfReplayEvent event;
    NavigationEskfRecoveryEvidence evidence;
    NavigationEskfOutcome outcome;
    NavigationEskfRecoveryAction action;
    NavigationEskfReplayResult expected;
    ReplayTest_Event(4U, &event, &evidence);
    if (scenario == 1U)
    { event.source = NAV_ESKF_RECOVERY_SOURCES; expected = NAV_ESKF_REPLAY_NUMERIC_ERROR; }
    else if (scenario == 2U)
    { s_recovery[0].current.configuration++; expected = NAV_ESKF_REPLAY_INVALID; }
    else if (scenario == 3U)
    { event.sequence = 3U; expected = NAV_ESKF_REPLAY_DUPLICATE; }
    else
    { event.measurement_us = s_history[0].anchor.timestamp_us; expected = NAV_ESKF_REPLAY_HISTORY_MISS; }
    s_saved_state = s_state[0]; s_saved_policy = s_recovery[0].current;
    uint16_t event_count = s_history[0].event_count;
    NavigationEskfRecoveryReplayState original_anchor = s_recovery[0].anchor;
    CHECK(NavigationEskfReplayRecovery_Insert(&s_history[0], &s_state[0], &s_workspace,
        &s_filter, &event, &outcome, &s_recovery[0], &evidence, &action) == expected);
    CHECK(memcmp(&s_state[0], &s_saved_state, sizeof(s_saved_state)) == 0);
    CHECK(memcmp(&s_recovery[0].current, &s_saved_policy, sizeof(s_policy)) == 0);
    CHECK(memcmp(&s_recovery[0].anchor, &original_anchor, sizeof(s_policy)) == 0);
    CHECK(s_history[0].event_count == event_count);
    CHECK(action == NAV_ESKF_RECOVERY_ACTION_NONE);
    return 0;
}

int Test_RecoveryReplay(uint32_t scenario)
{
    int result = ReplayTest_Reset(); if (result != 0) { return result; }
    result = ReplayTest_Bodies(40U); if (result != 0) { return result; }
    result = ReplayTest_Reorder(); if (result != 0) { return result; }
    if (scenario != 0U) { return ReplayTest_Fault(scenario); }
    result = ReplayTest_Bodies(100U); if (result != 0) { return result; }
    CHECK(s_history[0].event_count == 0U && s_history[1].event_count == 0U);
    CHECK(memcmp(&s_recovery[0].anchor, &s_recovery[1].anchor, sizeof(s_policy)) == 0);
    CHECK(memcmp(&s_recovery[0].current, &s_recovery[0].anchor, sizeof(s_policy)) == 0);
    CHECK(memcmp(&s_state[0], &s_state[1], sizeof(s_state[0])) == 0);
    return 0;
}
