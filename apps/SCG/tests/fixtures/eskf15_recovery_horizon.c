/* Actual horizon implementation, CPU-only late-output fault interception.
 * The interception is confined to this Host fixture and never target firmware. */
#include "navigation_eskf_horizon_recovery.h"
#include <string.h>

int Test_RecoveryHorizon(uint32_t scenario);
int Test_Prepare(NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    NavigationEskfConfig *filter, NavigationEskfRecoveryConfig *config,
    NavigationEskfRecoveryReceiveState *receive, NavigationEskfRecoveryReplayState *policy,
    const float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM]);
NavigationEskfResult Test_HorizonPredict(NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input);

static NavigationEskfHorizon s_test_horizon;
static NavigationEskfHorizonRecovery s_test_recovery;
static NavigationEskfState s_test_output;
static NavigationEskfState s_test_reference;
static NavigationEskfState s_test_reference_primary;
static NavigationEskfState s_test_original_output;
static NavigationEskfState s_test_original_primary;
static NavigationEskfWorkspace s_test_workspace;
static NavigationEskfRecoveryConfig s_test_config;
static NavigationEskfConfig s_test_filter;
static NavigationEskfRecoveryReceiveState s_test_receive;
static NavigationEskfRecoveryReplayState s_test_policy;
static NavigationEskfRecoveryReplayState s_test_original_policy;
static NavigationEskfRecoveryTransaction s_test_transaction;
static uint8_t s_test_fail_output;
static uint8_t s_test_intercepted;

NavigationEskfResult Test_HorizonPredict(NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input)
{
    if (s_test_fail_output && (s_test_recovery.candidate.attempts != 0U) &&
        (state == &s_test_horizon.output_candidate))
    { s_test_intercepted = 1U; return NAV_ESKF_NUMERIC_ERROR; }
    return NavigationEskf_Predict(state, workspace, config, input);
}

#define NavigationEskf_Predict Test_HorizonPredict
#include HORIZON_SOURCE
#undef NavigationEskf_Predict

#define CHECK(predicate) do { if (!(predicate)) { return __LINE__; } } while (0)

static void HorizonTest_Event(uint32_t ordinal, NavigationEskfHorizonEvent *event,
    NavigationEskfRecoveryEvidence *evidence)
{
    memset(event, 0, sizeof(*event)); memset(evidence, 0, sizeof(*evidence));
    event->event.measurement_us = (ordinal == 1U) ? 1300000ULL :
        ((ordinal == 2U) ? 1100000ULL : ((ordinal == 3U) ? 1200000ULL : 1350000ULL));
    event->event.receive_us = 1400000ULL; event->event.sequence = ordinal;
    event->event.source = 0U; event->event.generation = 7U;
    event->event.measurement.group = 0U; event->event.measurement.physically_valid = 1U;
    event->event.measurement.observation[0] = 1000.0f;
    event->event.measurement.observation[1] = -1000.0f;
    event->event.measurement.variance[0] = 1.0f; event->event.measurement.variance[1] = 1.0f;
    event->base_variance[0] = 1.0f; event->base_variance[1] = 1.0f;
    event->quality_scale = 1.0f; event->consistency_scale = 1.0f;
    event->operation_sequence = ordinal;
    evidence->ordinal = ordinal; evidence->chain = 1U; evidence->qualified = 1U;
    for (uint8_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++) { evidence->loss_tokens[i] = 1U; }
}

static int HorizonTest_Reset(void)
{
    float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM] = {{0}};
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++) { covariance[i][i] = 0.05f; }
    s_test_fail_output = 0U; s_test_intercepted = 0U;
    CHECK(Test_Prepare(&s_test_output, &s_test_workspace, &s_test_filter, &s_test_config,
        &s_test_receive, &s_test_policy, (const float (*)[NAV_ESKF_DIM])covariance) == NAV_ESKF_RECOVERY_COMPLETE);
    s_test_reference = s_test_output;
    CHECK(NavigationEskfHorizon_Reset(&s_test_horizon, &s_test_output, &s_test_workspace,
        &s_test_filter, 50000ULL) == NAV_ESKF_HORIZON_OK);
    CHECK(NavigationEskfHorizonRecovery_Reset(&s_test_recovery, &s_test_output,
        &s_test_policy, &s_test_config) == NAV_ESKF_HORIZON_OK);
    return 0;
}

static int HorizonTest_Build(void)
{
    for (uint32_t step = 1U; step <= 40U; step++)
    {
        NavigationEskfBodyInput input = {0};
        input.start_us = 1000000ULL + (uint64_t)(step - 1U) * 10000ULL;
        input.end_us = input.start_us + 10000ULL;
        input.dt_s = 0.01f; input.source = 13U; input.generation = 7U;
        input.accel_mps2[0][2] = s_test_filter.gravity_mps2;
        input.accel_mps2[1][2] = s_test_filter.gravity_mps2;
        CHECK(NavigationEskfHorizon_BodyReceive(&s_test_horizon, &input) == NAV_ESKF_HORIZON_OK);
        CHECK(NavigationEskf_Predict(&s_test_reference, &s_test_workspace, &s_test_filter, &input) == NAV_ESKF_OK);
        if ((step == 10U) || (step == 20U) || (step == 30U) || (step == 35U))
        {
            NavigationEskfHorizonEvent event;
            NavigationEskfRecoveryEvidence evidence;
            NavigationEskfRecoveryEvent received = {0};
            NavigationEskfRecoveryOutput output;
            uint32_t ordinal = (step == 10U) ? 2U :
                ((step == 20U) ? 3U : ((step == 30U) ? 1U : 4U));
            HorizonTest_Event(ordinal, &event, &evidence);
            received.receive_us = event.event.receive_us; received.source = event.event.source;
            received.sequence = event.event.sequence; received.mission = 7U; received.calibration = 11U;
            received.measurement = event.event.measurement; received.evidence = evidence;
            CHECK(NavigationEskfRecovery_UpdateCandidateRevision2(&s_test_reference, &s_test_policy,
                &s_test_workspace, &s_test_transaction, &s_test_filter, &s_test_config,
                &received, &output) == NAV_ESKF_RECOVERY_COMPLETE);
        }
        if (step == 35U) { s_test_reference_primary = s_test_reference; }
    }
    /* Receive sequences stay monotonic; varying delay reorders source epochs. */
    for (uint32_t ordinal = 1U; ordinal <= 4U; ordinal++)
    {
        NavigationEskfHorizonEvent event;
        NavigationEskfRecoveryEvidence evidence;
        HorizonTest_Event(ordinal, &event, &evidence);
        CHECK(NavigationEskfHorizonRecovery_Insert(&s_test_horizon, &event,
            &s_test_recovery, &evidence) == NAV_ESKF_HORIZON_QUEUED);
    }
    return 0;
}

int Test_RecoveryHorizon(uint32_t scenario)
{
    int result = HorizonTest_Reset(); if (result != 0) { return result; }
    result = HorizonTest_Build(); if (result != 0) { return result; }
    s_test_original_output = s_test_output; s_test_original_primary = s_test_horizon.primary;
    s_test_original_policy = s_test_recovery.primary;
    if (scenario == 1U) { s_test_fail_output = 1U; }
    if (scenario == 2U) { s_test_recovery.primary.configuration++; }
    NavigationEskfHorizonResult advanced = NavigationEskfHorizonRecovery_Advance(&s_test_horizon,
        &s_test_output, &s_test_workspace, &s_test_filter, &s_test_recovery);
    if (scenario != 0U)
    {
        CHECK(advanced == ((scenario == 1U) ? NAV_ESKF_HORIZON_NUMERIC_ERROR : NAV_ESKF_HORIZON_INVALID));
        CHECK(memcmp(&s_test_output, &s_test_original_output, sizeof(s_test_output)) == 0);
        CHECK(memcmp(&s_test_horizon.primary, &s_test_original_primary, sizeof(s_test_output)) == 0);
        if (scenario == 1U)
        {
            CHECK(s_test_intercepted == 1U && s_test_recovery.candidate.attempts == 1U);
            CHECK(s_test_horizon.faulted == 1U && s_test_horizon.completion_count == 0U);
            CHECK(memcmp(&s_test_recovery.primary, &s_test_original_policy, sizeof(s_test_policy)) == 0);
        }
        return 0;
    }
    CHECK(advanced == NAV_ESKF_HORIZON_OK);
    CHECK(memcmp(&s_test_output, &s_test_reference, sizeof(s_test_output)) == 0);
    CHECK(memcmp(&s_test_horizon.primary, &s_test_reference_primary, sizeof(s_test_output)) == 0);
    CHECK(memcmp(&s_test_recovery.primary, &s_test_policy, sizeof(s_test_policy)) == 0);
    CHECK(s_test_recovery.primary.attempts == 1U && s_test_horizon.completion_count == 4U);
    const uint32_t order[4] = {2U, 3U, 1U, 4U};
    for (uint32_t index = 0U; index < 4U; index++)
    {
        NavigationEskfHorizonEvent event;
        NavigationEskfRecoveryAction action;
        CHECK(NavigationEskfHorizonRecovery_CompletionPop(&s_test_horizon, &event,
            &s_test_recovery, &action) == NAV_ESKF_HORIZON_OK);
        CHECK(event.event.sequence == order[index]);
        CHECK(action == ((index == 3U) ? NAV_ESKF_RECOVERY_ACTION_SCALED :
            ((index == 1U) ? NAV_ESKF_RECOVERY_ACTION_PENDING : NAV_ESKF_RECOVERY_ACTION_NONE)));
    }
    CHECK(s_test_horizon.event_count == 0U && s_test_horizon.completion_count == 0U);
    CHECK(memcmp(&s_test_recovery.primary, &s_test_policy, sizeof(s_test_policy)) == 0);
    return 0;
}
