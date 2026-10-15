#include <string.h>
#include "navigation_kf_replay.h"
#include "test_common.h"

static NavigationCurrentContext s_current;
static NavigationKfContext s_state;
static NavigationKfContext s_expected;

static void Test_Initialize(void)
{
    const float delta[3] = {0.001f, -0.002f, 0.003f};
    NavigationKf_Init(&s_state);
    NavigationKf_Reset(&s_state);
    s_expected = s_state;
    TEST_CHECK(NavigationCurrent_Reset(&s_current, &s_state,
        1000000ULL, 7U, 11U) == NAV_CURRENT_OK);
    for (uint32_t step = 1U; step <= 100U; step++)
    {
        TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state,
            1000000ULL + (uint64_t)step * 10000ULL,
            delta, 0.01f) == NAV_CURRENT_OK);
        TEST_CHECK(NavigationKf_Predict(&s_expected, delta, 0.01f) != 0U);
        TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    }
}

static NavigationReplayEvent Test_Event(uint32_t sequence)
{
    NavigationReplayEvent event;
    memset(&event, 0, sizeof(event));
    event.kind = NAV_REPLAY_BAROMETER;
    event.source = 1U;
    event.epoch = 7U;
    event.calibration_generation = 11U;
    event.sequence = sequence;
    event.measurement_timestamp_us = 1700000ULL;
    event.receive_timestamp_us = 1900000ULL;
    event.altitude = 0.25f;
    event.altitude_variance = 4.0f;
    return event;
}

static void Test_LateAppliedOnceAtPresent(void)
{
    NavigationReplayOutcome outcome;
    NavigationReplayEvent event = Test_Event(1U);
    const float delta[3] = {0.0f, 0.0f, 0.0f};
    Test_Initialize();
    TEST_CHECK(NavigationKf_UpdateBaroAltitude(&s_expected,
        event.altitude, event.altitude_variance) == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
        &event, &outcome) == NAV_CURRENT_OK);
    TEST_CHECK(outcome.barometer == NAV_KF_UPDATE_ACCEPTED);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
        &event, &outcome) == NAV_CURRENT_DUPLICATE);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state,
        2010000ULL, delta, 0.01f) == NAV_CURRENT_OK);
    TEST_CHECK(NavigationKf_Predict(&s_expected, delta, 0.01f) != 0U);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
}

static void Test_AgeBoundaries(void)
{
    const uint64_t ages[3] = {499999ULL, 500000ULL, 500001ULL};
    for (uint8_t receive_case = 0U; receive_case < 2U; receive_case++)
    {
        for (uint8_t index = 0U; index < 3U; index++)
        {
            NavigationReplayEvent event = Test_Event(1U);
            NavigationReplayOutcome outcome;
            Test_Initialize();
            event.measurement_timestamp_us = 2000000ULL - ages[index];
            event.receive_timestamp_us = receive_case ? event.measurement_timestamp_us : 2000000ULL;
            NavigationCurrentResult result = NavigationCurrent_Insert(
                &s_current, &s_state, &event, &outcome);
            TEST_CHECK(result == ((index < 2U) ? NAV_CURRENT_OK : NAV_CURRENT_STALE));
            if (index == 2U)
            { TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0); }
        }
    }
}

static void Test_RejectedTimeAndIdentity(void)
{
    for (uint8_t item = 0U; item < 5U; item++)
    {
        NavigationReplayEvent event = Test_Event(1U);
        NavigationReplayOutcome outcome;
        Test_Initialize();
        if (item == 0U) { event.receive_timestamp_us = 2000001ULL; }
        if (item == 1U) { event.measurement_timestamp_us = 1900001ULL; }
        if (item == 2U) { event.measurement_timestamp_us = 0U; }
        if (item == 3U) { event.epoch = 8U; }
        if (item == 4U) { event.altitude = NAN; }
        TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
            &event, &outcome) != NAV_CURRENT_OK);
        TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    }
}

static void Test_SequenceWrapAndSourceChange(void)
{
    NavigationReplayOutcome outcome;
    NavigationReplayEvent event = Test_Event(UINT32_MAX);
    Test_Initialize();
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
        &event, &outcome) == NAV_CURRENT_OK);
    event.sequence = 0U;
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
        &event, &outcome) == NAV_CURRENT_OK);
    s_expected = s_state;
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
        &event, &outcome) == NAV_CURRENT_DUPLICATE);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    event.source = 2U;
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state,
        &event, &outcome) == NAV_CURRENT_INVALID);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
}

static void Test_FailedPredictionUncommitted(void)
{
    const float invalid[3] = {INFINITY, 0.0f, 0.0f};
    const float zero[3] = {0.0f, 0.0f, 0.0f};
    Test_Initialize();
    TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state,
        2010000ULL, invalid, 0.01f) != NAV_CURRENT_OK);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    Test_Initialize();
    s_state.covariance[0][0] = NAN;
    s_expected = s_state;
    TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state,
        2010000ULL, zero, 0.01f) != NAV_CURRENT_OK);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
}

static void Test_GnssPacketWatermarks(void)
{
    NavigationReplayEvent event = Test_Event(UINT32_MAX);
    NavigationReplayOutcome outcome;
    NavigationKfGnssEpoch receive = {0};
    NavigationKfContext tracker;
    Test_Initialize();
    receive.timestamp_us = 1900000ULL;
    event.kind = NAV_REPLAY_POSITION; event.source = 0U;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_OK);
    tracker = s_current.receive_tracker;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_DUPLICATE);
    TEST_CHECK(memcmp(&tracker, &s_current.receive_tracker, sizeof(tracker)) == 0);
    event.source = 1U;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_OK);
    event.source = 0U;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_DUPLICATE);
    event.measurement_timestamp_us = 1499999ULL;
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state, &event, &outcome) == NAV_CURRENT_STALE);
    event.measurement_timestamp_us = 1800000ULL;
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state, &event, &outcome) == NAV_CURRENT_DUPLICATE);
    event.kind = NAV_REPLAY_VELOCITY;
    TEST_CHECK(NavigationCurrent_Insert(&s_current, &s_state, &event, &outcome) == NAV_CURRENT_OK);
    event.sequence = 0U;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_OK);
    event.sequence = 0x80000000UL;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_DISCONTINUITY);
    event.sequence = 0x7FFFFFFFUL;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_OK);
    event.source = UINT32_MAX;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_INVALID);
    event.source = 0U; event.calibration_generation++;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_EPOCH_MISMATCH);
    TEST_CHECK(NavigationCurrent_Reset(&s_current, &s_state, 2000000ULL, 8U, 12U) == NAV_CURRENT_OK);
    event.sequence = UINT32_MAX; receive.timestamp_us = 2000000ULL;
    TEST_CHECK(NavigationCurrent_ReceiveTrack(&s_current, &receive, &event) == NAV_CURRENT_OK);
}

static void Test_PredictionAdapterResults(void)
{
    const float zero[3] = {0.0f, 0.0f, 0.0f};
    Test_Initialize();
    TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state, 2010002ULL,
        zero, 0.01f) == NAV_CURRENT_DISCONTINUITY);
    TEST_CHECK(s_current.faulted == 1U);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
    TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state, 2010000ULL,
        zero, 0.01f) == NAV_CURRENT_NOT_READY);
    Test_Initialize();
    s_state.process_accel_std_mps2[0] += 1.0f;
    s_expected = s_state;
    TEST_CHECK(NavigationCurrent_Predict(&s_current, &s_state, 2010000ULL,
        zero, 0.01f) == NAV_CURRENT_EPOCH_MISMATCH);
    TEST_CHECK(s_current.faulted == 1U);
    TEST_CHECK(memcmp(&s_state, &s_expected, sizeof(s_state)) == 0);
}

int main(void)
{
    Test_LateAppliedOnceAtPresent();
    Test_AgeBoundaries();
    Test_RejectedTimeAndIdentity();
    Test_SequenceWrapAndSourceChange();
    Test_FailedPredictionUncommitted();
    Test_GnssPacketWatermarks();
    Test_PredictionAdapterResults();
    return Test_Finish("navigation_kf_current");
}
