#include "navigation_eskf_reacquisition.h"
#include "system_fusion_timing.h"
#include <stddef.h>
#include <string.h>

/* EstimatorTask-owned CPU data. No DMA, heap, callbacks or replayed receipt FSM.
 * Unused modes and disabled-feature storage remain independently collectable. */
static NavigationEskfRecoveryReceiveState s_receive;
static NavigationEskfRecoveryQualifier s_qualifier;
static NavigationEskfRecoveryReplayState s_current_policy;
static NavigationEskfRecoveryTransaction s_current_transaction;
static NavigationEskfReplayRecovery s_replay_recovery;
static NavigationEskfHorizonRecovery s_horizon_recovery;
static NavigationEskfReacquisitionReceipt s_receipt;
static uint8_t s_configured;
static uint8_t s_epoch_started;
static uint8_t s_faulted;
static uint8_t s_limited;
static const NavigationEskfRecoveryEvidence s_no_evidence;

void NavigationEskfReacquisition_Reset(void)
{
    if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0) { return; }
    s_configured = 0U; s_epoch_started = 0U; s_faulted = 0U; s_limited = 0U;
    s_receive.initialized = 0U; s_qualifier.initialized = 0U;
    s_current_policy.initialized = 0U; s_receipt.valid = 0U;
    s_replay_recovery.initialized = 0U; s_horizon_recovery.initialized = 0U;
}

uint8_t NavigationEskfReacquisition_FaultedGet(void)
{ return (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED != 0) ? s_faulted : 0U; }

void NavigationEskfReacquisition_FaultMark(void)
{ if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED != 0) { s_faulted = 1U; } }

static NavigationEskfReacquisitionResult Reacquisition_Fault(void)
{ s_faulted = 1U; s_receipt.valid = 0U; return NAV_ESKF_REACQUISITION_BAD_STATE; }

static NavigationEskfReacquisitionResult Reacquisition_ReceiveResult(NavigationEskfRecoveryResult result)
{
    if (result == NAV_ESKF_RECOVERY_COMPLETE) { return NAV_ESKF_REACQUISITION_COMPLETE; }
    if ((result == NAV_ESKF_RECOVERY_DUPLICATE) || (result == NAV_ESKF_RECOVERY_DISCONTINUITY) ||
        (result == NAV_ESKF_RECOVERY_INELIGIBLE)) { return NAV_ESKF_REACQUISITION_SKIPPED; }
    if (result == NAV_ESKF_RECOVERY_EXHAUSTED)
    { s_limited = 1U; return NAV_ESKF_REACQUISITION_LIMITED; }
    return Reacquisition_Fault();
}

NavigationEskfReacquisitionResult NavigationEskfReacquisition_Initialize(void)
{
    if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0) { return NAV_ESKF_REACQUISITION_DISABLED; }
    if (s_configured || s_epoch_started || s_faulted) { return Reacquisition_Fault(); }
    if (NavigationEskfRecoveryConfiguration_Validate() != NAV_ESKF_RECOVERY_CONFIGURATION_COMPLETE)
    { return Reacquisition_Fault(); }
    s_configured = 1U;
    return NAV_ESKF_REACQUISITION_COMPLETE;
}

NavigationEskfReacquisitionResult NavigationEskfReacquisition_EpochStart(
    const NavigationEskfState *state, uint32_t calibration, uint64_t epoch_us)
{
    if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0) { return NAV_ESKF_REACQUISITION_DISABLED; }
    if (state == NULL) { return NAV_ESKF_REACQUISITION_INVALID_ARGUMENT; }
    if (!s_configured || s_epoch_started || s_faulted || (state->initialized != 1U) ||
        (state->timestamp_us != epoch_us)) { return Reacquisition_Fault(); }
    const NavigationEskfRecoveryConfiguration *config = NavigationEskfRecoveryConfiguration_Get();
    if ((NavigationEskfRecovery_Reset(&s_receive, &s_current_policy, &config->policy,
            state->generation, calibration, epoch_us) != NAV_ESKF_RECOVERY_COMPLETE) ||
        (NavigationEskfRecoveryQualifier_Reset(&s_qualifier) != NAV_ESKF_QUALIFIER_COMPLETE))
    { return Reacquisition_Fault(); }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_LEGACY_REPLAY)
    {
        if (NavigationEskfReplayRecovery_Reset(&s_replay_recovery, state,
            &s_current_policy, &config->policy) != NAV_ESKF_REPLAY_OK) { return Reacquisition_Fault(); }
    }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    {
        if (NavigationEskfHorizonRecovery_Reset(&s_horizon_recovery, state,
            &s_current_policy, &config->policy) != NAV_ESKF_HORIZON_OK) { return Reacquisition_Fault(); }
    }
    s_receipt.valid = 0U; s_epoch_started = 1U;
    return NAV_ESKF_REACQUISITION_COMPLETE;
}

NavigationEskfReacquisitionResult NavigationEskfReacquisition_SourceSelect(uint8_t source, uint8_t available)
{
    if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0) { return NAV_ESKF_REACQUISITION_DISABLED; }
    if ((available > 1U) || (available && (source >= NAV_ESKF_RECOVERY_SOURCES)))
    { return NAV_ESKF_REACQUISITION_INVALID_ARGUMENT; }
    if (!s_epoch_started || s_faulted) { return Reacquisition_Fault(); }
    if (s_limited) { return NAV_ESKF_REACQUISITION_LIMITED; }
    if (!available)
    {
        if (s_receive.selected_valid &&
            (NavigationEskfRecoveryQualifier_Reset(&s_qualifier) != NAV_ESKF_QUALIFIER_COMPLETE))
        { return Reacquisition_Fault(); }
        s_receipt.valid = 0U;
        return Reacquisition_ReceiveResult(NavigationEskfRecovery_SourceUnavailable(&s_receive));
    }
    if (!s_receive.selected_valid || (s_receive.selected_source != source)) { s_receipt.valid = 0U; }
    return Reacquisition_ReceiveResult(NavigationEskfRecovery_SourceSelect(&s_receive, source));
}

static void Reacquisition_ReceiptBegin(const SystemGnssReceiptSnapshot *receipt, uint64_t present_us)
{
    /* Fixed owned output; memset's return is its destination, not a failure. */
    (void)memset(&s_receipt, 0, sizeof(s_receipt));
    s_receipt.receive_us = receipt->sample.receive_timestamp_us; s_receipt.evaluation_us = present_us;
    s_receipt.source = receipt->source; s_receipt.sequence = receipt->sample.sequence;
    s_receipt.mission = s_receive.mission; s_receipt.calibration = s_receive.calibration;
    s_receipt.configuration = s_receive.configuration; s_receipt.ordinal = s_receive.ordinal;
}

NavigationEskfReacquisitionResult NavigationEskfReacquisition_Receive(
    const SystemGnssReceiptSnapshot *receipt, const float position_enu_m[3], uint64_t present_us)
{
    if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0) { return NAV_ESKF_REACQUISITION_DISABLED; }
    if ((receipt == NULL) || (position_enu_m == NULL)) { return NAV_ESKF_REACQUISITION_INVALID_ARGUMENT; }
    if (!s_epoch_started || s_faulted) { return Reacquisition_Fault(); }
    if (NavigationEskfRecoveryConfiguration_Validate() != NAV_ESKF_RECOVERY_CONFIGURATION_COMPLETE)
    { return Reacquisition_Fault(); }
    const NavigationEskfRecoveryConfiguration *config = NavigationEskfRecoveryConfiguration_Get();
    Reacquisition_ReceiptBegin(receipt, present_us);
    if (s_limited)
    { s_receipt.receive_result = NAV_ESKF_RECOVERY_EXHAUSTED; s_receipt.valid = 1U; return NAV_ESKF_REACQUISITION_LIMITED; }
    s_receipt.qualifier_result = NavigationEskfRecoveryQualifier_Receive(&s_qualifier, &config->qualifier,
        receipt, position_enu_m, present_us, &s_receipt.qualification);
    if ((s_receipt.qualifier_result == NAV_ESKF_QUALIFIER_INVALID_ARGUMENT) ||
        (s_receipt.qualifier_result == NAV_ESKF_QUALIFIER_BAD_STATE)) { return Reacquisition_Fault(); }
    if ((receipt->source >= NAV_ESKF_RECOVERY_SOURCES) || (receipt->sample.receive_timestamp_us > present_us) ||
        (receipt->sample.receive_timestamp_us < s_receive.epoch_start_us) ||
        (present_us - receipt->sample.receive_timestamp_us > 500000ULL))
    { s_receipt.receive_result = NAV_ESKF_RECOVERY_INELIGIBLE; s_receipt.valid = 1U; return NAV_ESKF_REACQUISITION_SKIPPED; }
    NavigationEskfRecoveryPacket packet = {0};
    packet.receive_us = receipt->sample.receive_timestamp_us; packet.sequence = receipt->sample.sequence;
    packet.source = receipt->source; packet.mission = s_receive.mission; packet.calibration = s_receive.calibration;
    packet.native_us = s_receipt.qualification.native_us; packet.time_proven = s_receipt.qualification.time_proven;
    packet.physical_mask = s_receipt.qualification.physical_mask; packet.coherent_mask = s_receipt.qualification.coherent_mask;
    s_receipt.receive_result = NavigationEskfRecovery_Receive(&s_receive, &config->policy, &packet, s_receipt.evidence);
    NavigationEskfReacquisitionResult result = Reacquisition_ReceiveResult(s_receipt.receive_result);
    s_receipt.ordinal = s_receive.ordinal;
    if (result != NAV_ESKF_REACQUISITION_BAD_STATE) { s_receipt.valid = 1U; }
    return result;
}

NavigationEskfReacquisitionResult NavigationEskfReacquisition_Tick(uint64_t present_us)
{
    if (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED == 0) { return NAV_ESKF_REACQUISITION_DISABLED; }
    if (!s_epoch_started || s_faulted) { return Reacquisition_Fault(); }
    if (s_limited) { return NAV_ESKF_REACQUISITION_LIMITED; }
    return Reacquisition_ReceiveResult(NavigationEskfRecovery_Tick(&s_receive,
        &NavigationEskfRecoveryConfiguration_Get()->policy, present_us));
}

const NavigationEskfReacquisitionReceipt *NavigationEskfReacquisition_ReceiptGet(void)
{ return (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED && s_epoch_started) ? &s_receipt : NULL; }

const NavigationEskfRecoveryReceiveState *NavigationEskfReacquisition_ReceiveStateGet(void)
{ return (SYSTEM_ESKF_GNSS_RECOVERY_ENABLED && s_epoch_started) ? &s_receive : NULL; }

const NavigationEskfRecoveryReplayState *NavigationEskfReacquisition_PolicyGet(void)
{
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED || !s_epoch_started) { return NULL; }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_LEGACY_REPLAY) { return &s_replay_recovery.current; }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) { return &s_horizon_recovery.primary; }
    return &s_current_policy;
}

static uint8_t Reacquisition_ConfigEqual(const NavigationEskfRecoveryConfig *left,
    const NavigationEskfRecoveryConfig *right)
{
    if ((left->identity != right->identity) || (left->loss_gap_us != right->loss_gap_us) ||
        (left->stable_span_us != right->stable_span_us) || (left->maximum_interval_us != right->maximum_interval_us) ||
        (left->cooldown_us != right->cooldown_us) || (left->stable_count != right->stable_count) ||
        (left->reject_count != right->reject_count) || (left->confirmation_count != right->confirmation_count) ||
        (left->maximum_attempts != right->maximum_attempts)) { return 0U; }
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++)
    { if ((left->scale[i] != right->scale[i]) || (left->variance_cap[i] != right->variance_cap[i])) { return 0U; } }
    return 1U;
}

static uint8_t Reacquisition_StateReady(const NavigationEskfState *state)
{
    const NavigationEskfRecoveryReplayState *policy = NavigationEskfReacquisition_PolicyGet();
    const NavigationEskfRecoveryConfig *config = &NavigationEskfRecoveryConfiguration_Get()->policy;
    if ((state == NULL) || (policy == NULL) || s_faulted || !s_configured ||
        (state->generation != s_receive.mission) ||
        (NavigationEskfRecovery_PolicyValidate(policy, config) != NAV_ESKF_RECOVERY_COMPLETE)) { return 0U; }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_LEGACY_REPLAY)
    { return Reacquisition_ConfigEqual(&s_replay_recovery.config, config); }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { return Reacquisition_ConfigEqual(&s_horizon_recovery.config, config); }
    return 1U;
}

static const NavigationEskfRecoveryEvidence *Reacquisition_EvidenceGet(const NavigationEskfReplayEvent *event)
{
    if (s_limited || !s_receipt.valid || (event->measurement.group >= NAV_ESKF_RECOVERY_GROUPS) ||
        (event->source != s_receipt.source) || (event->sequence != s_receipt.sequence) ||
        (event->receive_us != s_receipt.receive_us) || (event->generation != s_receipt.mission))
    { return &s_no_evidence; }
    return &s_receipt.evidence[event->measurement.group];
}

NavigationEskfReplayResult NavigationEskfReacquisition_ReplayPredict(
    NavigationEskfReplay *history, NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfBodyInput *input)
{
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED) { return NavigationEskfReplay_Predict(history, state, workspace, config, input); }
    if (!Reacquisition_StateReady(state)) { s_faulted = 1U; return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
    NavigationEskfReplayResult result = NavigationEskfReplayRecovery_Predict(history, state, workspace, config, input, &s_replay_recovery);
    if (result != NAV_ESKF_REPLAY_OK) { s_faulted = 1U; }
    return result;
}

NavigationEskfReplayResult NavigationEskfReacquisition_ReplayInsert(
    NavigationEskfReplay *history, NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfReplayEvent *event,
    NavigationEskfOutcome *outcome, NavigationEskfRecoveryAction *action)
{
    if ((event == NULL) || (action == NULL)) { return NAV_ESKF_REPLAY_INVALID; }
    *action = NAV_ESKF_RECOVERY_ACTION_NONE;
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED) { return NavigationEskfReplay_Insert(history, state, workspace, config, event, outcome); }
    if (!Reacquisition_StateReady(state)) { s_faulted = 1U; return NAV_ESKF_REPLAY_NUMERIC_ERROR; }
    NavigationEskfReplayResult result = NavigationEskfReplayRecovery_Insert(history, state, workspace,
        config, event, outcome, &s_replay_recovery, Reacquisition_EvidenceGet(event), action);
    if (result == NAV_ESKF_REPLAY_NUMERIC_ERROR) { s_faulted = 1U; }
    return result;
}

NavigationEskfResult NavigationEskfReacquisition_CurrentUpdate(
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfReplayEvent *event,
    NavigationEskfOutcome *outcome, NavigationEskfRecoveryAction *action)
{
    if ((event == NULL) || (outcome == NULL) || (action == NULL)) { return NAV_ESKF_INVALID_INPUT; }
    *action = NAV_ESKF_RECOVERY_ACTION_NONE;
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED || (event->measurement.group >= NAV_ESKF_RECOVERY_GROUPS))
    { return NavigationEskf_Update(state, workspace, config, &event->measurement, outcome); }
    if (!Reacquisition_StateReady(state)) { s_faulted = 1U; return NAV_ESKF_NUMERIC_ERROR; }
    NavigationEskfRecoveryEvent received = {0}; NavigationEskfRecoveryOutput output;
    received.receive_us = event->receive_us; received.source = event->source; received.sequence = event->sequence;
    received.mission = event->generation; received.calibration = s_receive.calibration;
    received.measurement = event->measurement; received.evidence = *Reacquisition_EvidenceGet(event);
    NavigationEskfRecoveryResult result = NavigationEskfRecovery_UpdateCandidate(state, &s_current_policy,
        workspace, &s_current_transaction, config, &NavigationEskfRecoveryConfiguration_Get()->policy, &received, &output);
    *outcome = output.filter; *action = output.action;
    if ((result == NAV_ESKF_RECOVERY_COMPLETE) || (result == NAV_ESKF_RECOVERY_MEASUREMENT_INVALID)) { return outcome->result; }
    s_faulted = 1U;
    return (result == NAV_ESKF_RECOVERY_MODEL_MISMATCH) ? NAV_ESKF_MODEL_MISMATCH : NAV_ESKF_NUMERIC_ERROR;
}

NavigationEskfHorizonResult NavigationEskfReacquisition_HorizonInsert(
    NavigationEskfHorizon *horizon, const NavigationEskfHorizonEvent *event)
{
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED) { return NavigationEskfHorizon_Insert(horizon, event); }
    if ((horizon == NULL) || (event == NULL)) { return NAV_ESKF_HORIZON_INVALID; }
    if (!Reacquisition_StateReady(&horizon->primary)) { s_faulted = 1U; return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    return NavigationEskfHorizonRecovery_Insert(horizon, event, &s_horizon_recovery, Reacquisition_EvidenceGet(&event->event));
}

NavigationEskfHorizonResult NavigationEskfReacquisition_HorizonAdvance(
    NavigationEskfHorizon *horizon, NavigationEskfState *output,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config)
{
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED) { return NavigationEskfHorizon_Advance(horizon, output, workspace, config); }
    if (horizon == NULL) { return NAV_ESKF_HORIZON_INVALID; }
    if (!Reacquisition_StateReady(&horizon->primary)) { s_faulted = 1U; return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    NavigationEskfHorizonResult result = NavigationEskfHorizonRecovery_Advance(horizon, output, workspace, config, &s_horizon_recovery);
    if ((result != NAV_ESKF_HORIZON_OK) && (result != NAV_ESKF_HORIZON_WARMUP)) { s_faulted = 1U; }
    return result;
}

NavigationEskfHorizonResult NavigationEskfReacquisition_HorizonPop(
    NavigationEskfHorizon *horizon, NavigationEskfHorizonEvent *event, NavigationEskfRecoveryAction *action)
{
    if (action == NULL) { return NAV_ESKF_HORIZON_INVALID; }
    *action = NAV_ESKF_RECOVERY_ACTION_NONE;
    if (!SYSTEM_ESKF_GNSS_RECOVERY_ENABLED) { return NavigationEskfHorizon_CompletionPop(horizon, event); }
    if (horizon == NULL) { return NAV_ESKF_HORIZON_INVALID; }
    if (!Reacquisition_StateReady(&horizon->primary)) { s_faulted = 1U; return NAV_ESKF_HORIZON_NUMERIC_ERROR; }
    return NavigationEskfHorizonRecovery_CompletionPop(horizon, event, &s_horizon_recovery, action);
}
