#include <string.h>
#include "navigation_kf_replay.h"
#include "platform_time.h"
#include "platform_critical.h"
#include "test_common.h"

PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }
uint64_t PlatformTime_Us(void) { return 0ULL; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }

static NavigationReplayContext s_history;
static NavigationReplayStorage s_storage;
static NavigationKfContext s_state;
static NavigationKfContext s_before;

int main(void)
{
    const float delta[3] = {0.0f, 0.0f, 0.0f};
    NavigationReplayEvent event;
    NavigationReplayOutcome outcome;
    NavigationKf_Init(&s_state);
    NavigationKf_Reset(&s_state);
    NavigationReplay_Reset(&s_history, &s_storage, &s_state, 1000000ULL, 7U);
    TEST_CHECK(NavigationReplay_Predict(&s_history, &s_state, 1005000ULL, delta, 0.005f) == NAV_REPLAY_OK);
    s_before = s_state;
    (void)memset(&event, 0, sizeof(event));
    event.kind = NAV_REPLAY_BAROMETER;
    event.epoch = 7U;
    event.measurement_timestamp_us = 1001000ULL;
    event.receive_timestamp_us = 1005000ULL;
    event.altitude = 1.0f;
    event.altitude_variance = 6.25f;
    TEST_CHECK(NavigationReplay_Insert(&s_history, &s_state, &event, &outcome) == NAV_REPLAY_WORK_LIMIT);
    TEST_CHECK(memcmp(&s_state, &s_before, sizeof(s_state)) == 0);
    TEST_CHECK(s_history.faulted == 1U);
    TEST_CHECK(s_history.diagnostics.replay_count == 1U);
    TEST_CHECK(s_history.diagnostics.last_steps == 2U);
    TEST_CHECK(s_history.diagnostics.last_result == NAV_REPLAY_WORK_LIMIT);
    TEST_CHECK(outcome.barometer == NAV_KF_UPDATE_REJECTED_INVALID);
    TEST_CHECK(NavigationReplay_Predict(&s_history, &s_state, 1010000ULL, delta, 0.005f) == NAV_REPLAY_INVALID);
    TEST_CHECK(memcmp(&s_state, &s_before, sizeof(s_state)) == 0);
    return Test_Finish("replay_work_limit");
}
