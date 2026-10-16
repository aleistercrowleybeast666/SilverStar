#include "navigation_eskf_recovery.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct
{
    const void *address;
    size_t size;
    uint8_t writable;
} RecoveryRegion;

/* Typed-object extent checks use integer differences, never pointer+size or
 * relational comparison of pointers to different C objects. Read-only may alias. */
static uint8_t Recovery_RegionsDisjoint(const RecoveryRegion *region, uint32_t count)
{
    if ((region == NULL) || (count > 8U)) { return 0U; }
    for (uint32_t i = 0U; i < count; i++)
    {
        if (region[i].address == NULL) { return 0U; }
        for (uint32_t j = 0U; j < i; j++)
        {
            uintptr_t a = (uintptr_t)region[i].address, b = (uintptr_t)region[j].address;
            uint8_t overlap = (uint8_t)((a <= b) ?
                (b - a < region[i].size) : (a - b < region[j].size));
            if (overlap && (region[i].writable || region[j].writable)) { return 0U; }
        }
    }
    return 1U;
}

NavigationEskfRecoveryResult NavigationEskfRecovery_ConfigValidate(
    const NavigationEskfRecoveryConfig *config)
{
    if ((config == NULL) || (config->identity == 0U) ||
        (config->maximum_interval_us == 0U) ||
        (config->loss_gap_us <= config->maximum_interval_us) ||
        (config->stable_span_us == 0U) || (config->cooldown_us == 0U) ||
        (config->stable_count < 2U) || (config->reject_count == 0U) ||
        (config->confirmation_count == 0U) || (config->maximum_attempts == 0U))
    { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    for (uint32_t i = 0U; i < NAV_ESKF_DIM; i++)
    {
        if (!isfinite(config->scale[i]) || (config->scale[i] <= 1.0f) ||
            (config->scale[i] > 2.0f) || (config->scale[i] != config->scale[0]) ||
            !isfinite(config->variance_cap[i]) || (config->variance_cap[i] <= 0.0f))
        { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    }
    return NAV_ESKF_RECOVERY_COMPLETE;
}

static uint8_t Recovery_ReceiveValid(const NavigationEskfRecoveryReceiveState *receive)
{
    if ((receive == NULL) || (receive->initialized != 1U) ||
        (receive->selected_valid > 1U) || (receive->exhausted > 1U) ||
        (receive->selected_source >= NAV_ESKF_RECOVERY_SOURCES) ||
        (receive->horizon_us < receive->epoch_start_us)) { return 0U; }
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    {
        const NavigationEskfRecoveryQualification *group = &receive->group[i];
        if ((receive->source[i].valid > 1U) || (group->in_outage > 1U) || (group->chain == 0U) ||
            (group->last_physical_us > receive->horizon_us) ||
            (group->last_qualified_us > receive->horizon_us) ||
            (group->stable_start_us > group->last_qualified_us) ||
            (group->in_outage && ((group->loss_token == 0U) || (group->last_physical_us == 0U))) ||
            ((group->stable_count != 0U) && (group->stable_start_us == 0U)) ||
            ((group->stable_count == 0U) && (group->last_qualified_us != 0U)) ||
            (receive->source[i].valid && (receive->source[i].receive_us == 0U))) { return 0U; }
    }
    return 1U;
}

static uint8_t Recovery_CountsValid(const NavigationEskfRecoveryReceiveState *receive,
    const NavigationEskfRecoveryConfig *config)
{
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    { if (receive->group[i].stable_count > config->stable_count) { return 0U; } }
    return 1U;
}

NavigationEskfRecoveryResult NavigationEskfRecovery_Reset(
    NavigationEskfRecoveryReceiveState *receive, NavigationEskfRecoveryReplayState *policy,
    const NavigationEskfRecoveryConfig *config, uint32_t mission, uint32_t calibration,
    uint64_t epoch_start_us)
{
    const RecoveryRegion regions[3] = {{receive, sizeof(*receive), 1U},
        {policy, sizeof(*policy), 1U}, {config, sizeof(*config), 0U}};
    if (!Recovery_RegionsDisjoint(regions, 3U) ||
        (NavigationEskfRecovery_ConfigValidate(config) != NAV_ESKF_RECOVERY_COMPLETE))
    { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    memset(receive, 0, sizeof(*receive)); memset(policy, 0, sizeof(*policy));
    receive->mission = mission; receive->calibration = calibration;
    receive->configuration = config->identity; receive->initialized = 1U;
    receive->epoch_start_us = epoch_start_us; receive->horizon_us = epoch_start_us;
    policy->mission = mission; policy->calibration = calibration;
    policy->configuration = config->identity; policy->initialized = 1U;
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++) { receive->group[i].chain = 1U; }
    return NAV_ESKF_RECOVERY_COMPLETE;
}

static void Recovery_ChainBreak(NavigationEskfRecoveryReceiveState *receive, uint32_t group)
{
    NavigationEskfRecoveryQualification *item = &receive->group[group];
    item->stable_count = 0U; item->stable_start_us = 0U; item->last_qualified_us = 0U;
    if (item->chain == UINT32_MAX) { receive->exhausted = 1U; }
    else { item->chain++; }
}

NavigationEskfRecoveryResult NavigationEskfRecovery_SourceSelect(
    NavigationEskfRecoveryReceiveState *receive, uint32_t source)
{
    if (!Recovery_ReceiveValid(receive) || (source >= NAV_ESKF_RECOVERY_SOURCES))
    { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    if (receive->exhausted) { return NAV_ESKF_RECOVERY_EXHAUSTED; }
    if (!receive->selected_valid || (receive->selected_source != source))
    {
        for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++) { Recovery_ChainBreak(receive, i); }
        receive->selected_source = (uint8_t)source; receive->selected_valid = 1U;
        receive->native_us = 0U;
    }
    return receive->exhausted ? NAV_ESKF_RECOVERY_EXHAUSTED : NAV_ESKF_RECOVERY_COMPLETE;
}

NavigationEskfRecoveryResult NavigationEskfRecovery_SourceUnavailable(
    NavigationEskfRecoveryReceiveState *receive)
{
    if (!Recovery_ReceiveValid(receive)) { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    if (receive->exhausted) { return NAV_ESKF_RECOVERY_EXHAUSTED; }
    if (receive->selected_valid)
    {
        for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++) { Recovery_ChainBreak(receive, i); }
        receive->selected_valid = 0U; receive->native_us = 0U;
    }
    return receive->exhausted ? NAV_ESKF_RECOVERY_EXHAUSTED : NAV_ESKF_RECOVERY_COMPLETE;
}

NavigationEskfRecoveryResult NavigationEskfRecovery_Tick(
    NavigationEskfRecoveryReceiveState *receive, const NavigationEskfRecoveryConfig *config,
    uint64_t present_us)
{
    const RecoveryRegion regions[2] = {{receive, sizeof(*receive), 1U}, {config, sizeof(*config), 0U}};
    if (!Recovery_RegionsDisjoint(regions, 2U) || !Recovery_ReceiveValid(receive) ||
        (NavigationEskfRecovery_ConfigValidate(config) != NAV_ESKF_RECOVERY_COMPLETE) ||
        (receive->configuration != config->identity) || !Recovery_CountsValid(receive, config))
    { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    if (receive->exhausted) { return NAV_ESKF_RECOVERY_EXHAUSTED; }
    if (present_us < receive->horizon_us) { return NAV_ESKF_RECOVERY_DISCONTINUITY; }
    receive->horizon_us = present_us;
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    {
        NavigationEskfRecoveryQualification *group = &receive->group[i];
        if ((group->last_physical_us != 0U) && !group->in_outage &&
            (present_us >= group->last_physical_us) &&
            (present_us - group->last_physical_us >= config->loss_gap_us))
        {
            if (group->loss_token == UINT32_MAX) { receive->exhausted = 1U; }
            else { group->loss_token++; }
            group->in_outage = 1U; Recovery_ChainBreak(receive, i);
        }
    }
    return receive->exhausted ? NAV_ESKF_RECOVERY_EXHAUSTED : NAV_ESKF_RECOVERY_COMPLETE;
}

static NavigationEskfRecoveryResult Recovery_ReceiptCheck(
    const NavigationEskfRecoveryReceiveState *receive, const NavigationEskfRecoveryPacket *packet)
{
    const NavigationEskfRecoveryReceipt *slot;
    uint32_t delta;
    if ((packet->source >= NAV_ESKF_RECOVERY_SOURCES) || (packet->mission != receive->mission) ||
        (packet->calibration != receive->calibration) || (packet->receive_us == 0U) ||
        (packet->receive_us < receive->epoch_start_us)) { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    if (receive->exhausted || (receive->ordinal == UINT32_MAX)) { return NAV_ESKF_RECOVERY_EXHAUSTED; }
    slot = &receive->source[packet->source];
    if (!slot->valid) { return NAV_ESKF_RECOVERY_COMPLETE; }
    delta = packet->sequence - slot->sequence;
    if (delta == 0U) { return NAV_ESKF_RECOVERY_DUPLICATE; }
    if ((delta >= UINT32_C(0x80000000)) || (packet->receive_us <= slot->receive_us))
    { return NAV_ESKF_RECOVERY_DISCONTINUITY; }
    return NAV_ESKF_RECOVERY_COMPLETE;
}

static void Recovery_QualifyGroup(NavigationEskfRecoveryReceiveState *receive,
    const NavigationEskfRecoveryConfig *config, const NavigationEskfRecoveryPacket *packet,
    uint32_t index, uint8_t time_valid)
{
    NavigationEskfRecoveryQualification *group = &receive->group[index];
    const uint8_t bit = (uint8_t)(1U << index);
    if ((packet->physical_mask <= 15U) && ((packet->physical_mask & bit) != 0U))
    { group->last_physical_us = packet->receive_us; group->in_outage = 0U; }
    if (!time_valid || ((packet->physical_mask & packet->coherent_mask & bit) == 0U))
    { Recovery_ChainBreak(receive, index); return; }
    if ((group->last_qualified_us != 0U) &&
        (packet->receive_us - group->last_qualified_us > config->maximum_interval_us))
    { Recovery_ChainBreak(receive, index); }
    if (group->stable_count == 0U) { group->stable_start_us = packet->receive_us; }
    if (group->stable_count < config->stable_count) { group->stable_count++; }
    group->last_qualified_us = packet->receive_us;
}

static void Recovery_EvidenceWrite(const NavigationEskfRecoveryReceiveState *receive,
    const NavigationEskfRecoveryConfig *config, uint64_t receive_us,
    NavigationEskfRecoveryEvidence evidence[NAV_ESKF_RECOVERY_GROUPS])
{
    memset(evidence, 0, NAV_ESKF_RECOVERY_GROUPS * sizeof(*evidence));
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    {
        const NavigationEskfRecoveryQualification *group = &receive->group[i];
        evidence[i].ordinal = receive->ordinal; evidence[i].chain = group->chain;
        for (uint32_t j = 0U; j < NAV_ESKF_RECOVERY_GROUPS; j++)
        { evidence[i].loss_tokens[j] = receive->group[j].loss_token; }
        evidence[i].qualified = (uint8_t)(!receive->exhausted && (group->loss_token != 0U) &&
            (group->stable_count >= config->stable_count) && (receive_us >= group->stable_start_us) &&
            (receive_us - group->stable_start_us >= config->stable_span_us));
    }
}

NavigationEskfRecoveryResult NavigationEskfRecovery_Receive(
    NavigationEskfRecoveryReceiveState *receive, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryPacket *packet,
    NavigationEskfRecoveryEvidence evidence[NAV_ESKF_RECOVERY_GROUPS])
{
    NavigationEskfRecoveryResult result;
    uint8_t time_valid;
    const RecoveryRegion regions[4] = {{receive, sizeof(*receive), 1U}, {config, sizeof(*config), 0U},
        {packet, sizeof(*packet), 0U}, {evidence, NAV_ESKF_RECOVERY_GROUPS * sizeof(*evidence), 1U}};
    if (!Recovery_RegionsDisjoint(regions, 4U) || !Recovery_ReceiveValid(receive) ||
        (NavigationEskfRecovery_ConfigValidate(config) != NAV_ESKF_RECOVERY_COMPLETE) ||
        (receive->configuration != config->identity) || !Recovery_CountsValid(receive, config))
    { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    result = Recovery_ReceiptCheck(receive, packet);
    if (result != NAV_ESKF_RECOVERY_COMPLETE) { return result; }
    receive->source[packet->source].sequence = packet->sequence;
    receive->source[packet->source].receive_us = packet->receive_us;
    receive->source[packet->source].valid = 1U; receive->ordinal++;
    result = NavigationEskfRecovery_SourceSelect(receive, packet->source);
    if (result != NAV_ESKF_RECOVERY_COMPLETE) { return result; }
    if (packet->receive_us < receive->horizon_us)
    {
        for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++) { Recovery_ChainBreak(receive, i); }
        Recovery_EvidenceWrite(receive, config, packet->receive_us, evidence);
        return NAV_ESKF_RECOVERY_INELIGIBLE;
    }
    result = NavigationEskfRecovery_Tick(receive, config, packet->receive_us);
    if (result != NAV_ESKF_RECOVERY_COMPLETE) { return result; }
    time_valid = (uint8_t)((packet->time_proven == 1U) && (packet->native_us != 0U) &&
        (packet->native_us > receive->native_us) &&
        (packet->physical_mask <= 15U) && (packet->coherent_mask <= 15U));
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    { Recovery_QualifyGroup(receive, config, packet, i, time_valid); }
    receive->native_us = time_valid ? packet->native_us : 0U;
    Recovery_EvidenceWrite(receive, config, packet->receive_us, evidence);
    return receive->exhausted ? NAV_ESKF_RECOVERY_EXHAUSTED : NAV_ESKF_RECOVERY_COMPLETE;
}

static uint8_t Recovery_PolicyValid(const NavigationEskfRecoveryReplayState *policy,
    const NavigationEskfRecoveryConfig *config)
{
    if ((policy->initialized != 1U) || (policy->configuration != config->identity) ||
        (policy->active_mask > 15U) || (policy->limited > 1U) || (policy->pending_valid > 1U) ||
        (policy->attempts > config->maximum_attempts) ||
        (policy->pending_group >= NAV_ESKF_RECOVERY_GROUPS) ||
        (policy->pending_source >= NAV_ESKF_RECOVERY_SOURCES)) { return 0U; }
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    {
        if ((policy->group[i].rejects > config->reject_count) ||
            (policy->group[i].confirmations > config->confirmation_count) ||
            ((policy->group[i].rejects != 0U) && (policy->group[i].confirmations != 0U)) ||
            (((policy->active_mask & (1U << i)) != 0U) && (policy->group[i].loss_token == 0U))) { return 0U; }
    }
    if (policy->pending_valid && ((policy->pending_ordinal == 0U) ||
        ((policy->active_mask & (1U << policy->pending_group)) == 0U) ||
        (policy->pending_ordinal > policy->group[policy->pending_group].ordinal) ||
        (policy->pending_loss != policy->group[policy->pending_group].loss_token) ||
        (policy->pending_chain != policy->group[policy->pending_group].chain))) { return 0U; }
    return 1U;
}

NavigationEskfRecoveryResult NavigationEskfRecovery_PolicyValidate(
    const NavigationEskfRecoveryReplayState *policy, const NavigationEskfRecoveryConfig *config)
{
    if ((policy == NULL) ||
        (NavigationEskfRecovery_ConfigValidate(config) != NAV_ESKF_RECOVERY_COMPLETE) ||
        !Recovery_PolicyValid(policy, config)) { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    return NAV_ESKF_RECOVERY_COMPLETE;
}

static uint8_t Recovery_EvidenceMerge(NavigationEskfRecoveryReplayState *policy,
    const NavigationEskfRecoveryEvent *event)
{
    uint32_t index = event->measurement.group;
    NavigationEskfRecoveryGroup *group = &policy->group[index];
    if ((event->evidence.ordinal == 0U) || (event->evidence.ordinal <= group->ordinal)) { return 0U; }
    group->ordinal = event->evidence.ordinal;
    for (uint32_t i = 0U; i < NAV_ESKF_RECOVERY_GROUPS; i++)
    {
        if (event->evidence.loss_tokens[i] > policy->group[i].loss_token)
        {
            policy->group[i].loss_token = event->evidence.loss_tokens[i];
            policy->group[i].rejects = 0U; policy->group[i].confirmations = 0U;
            policy->active_mask |= (uint8_t)(1U << i);
            if (policy->pending_group == i) { policy->pending_valid = 0U; }
        }
    }
    if (event->evidence.chain != group->chain)
    {
        group->chain = event->evidence.chain; group->rejects = 0U; group->confirmations = 0U;
        if (policy->pending_group == index) { policy->pending_valid = 0U; }
    }
    if (!event->evidence.qualified || (event->evidence.loss_tokens[index] != group->loss_token) ||
        ((policy->active_mask & (1U << index)) == 0U))
    {
        group->rejects = 0U; group->confirmations = 0U;
        if (policy->pending_group == index) { policy->pending_valid = 0U; }
        return 0U;
    }
    return 1U;
}

static uint8_t Recovery_ScaleDue(const NavigationEskfRecoveryReplayState *policy,
    const NavigationEskfRecoveryConfig *config, const NavigationEskfRecoveryEvent *event)
{
    return (uint8_t)(policy->pending_valid && !policy->limited &&
        (policy->pending_group == event->measurement.group) && (policy->pending_source == event->source) &&
        (policy->pending_chain == event->evidence.chain) &&
        (policy->pending_loss == event->evidence.loss_tokens[event->measurement.group]) &&
        (event->evidence.ordinal > policy->pending_ordinal) &&
        (event->evidence.ordinal > policy->last_scale_ordinal) &&
        ((policy->last_scale_receive_us == 0U) ||
         ((event->receive_us >= policy->last_scale_receive_us) &&
          (event->receive_us - policy->last_scale_receive_us >= config->cooldown_us))));
}

static NavigationEskfRecoveryResult Recovery_ScaleTry(NavigationEskfRecoveryTransaction *transaction,
    NavigationEskfWorkspace *workspace, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryEvent *event, NavigationEskfRecoveryOutput *output)
{
    NavigationEskfRecoveryReplayState *policy = &transaction->policy;
    NavigationEskfCovarianceScaleResult result;
    if (policy->attempts >= config->maximum_attempts)
    { policy->limited = 1U; output->action = NAV_ESKF_RECOVERY_ACTION_LIMITED; return NAV_ESKF_RECOVERY_COMPLETE; }
    result = NavigationEskf_CovarianceScale(&transaction->state, workspace, config->scale, config->variance_cap);
    if (result == NAV_ESKF_COVARIANCE_SCALE_NUMERIC_ERROR) { return NAV_ESKF_RECOVERY_NUMERIC_ERROR; }
    if (result == NAV_ESKF_COVARIANCE_SCALE_INVALID_ARGUMENT) { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    policy->attempts++; policy->pending_valid = 0U;
    if (result != NAV_ESKF_COVARIANCE_SCALE_APPLIED)
    { policy->limited = 1U; output->action = NAV_ESKF_RECOVERY_ACTION_LIMITED; }
    else
    {
        policy->last_scale_receive_us = event->receive_us;
        policy->last_scale_ordinal = event->evidence.ordinal;
        policy->limited = (uint8_t)(policy->attempts >= config->maximum_attempts);
        output->action = NAV_ESKF_RECOVERY_ACTION_SCALED;
    }
    return NAV_ESKF_RECOVERY_COMPLETE;
}

static void Recovery_OutcomeApply(NavigationEskfRecoveryReplayState *policy,
    const NavigationEskfRecoveryConfig *config, const NavigationEskfRecoveryEvent *event,
    NavigationEskfRecoveryOutput *output)
{
    const uint32_t index = event->measurement.group;
    NavigationEskfRecoveryGroup *group = &policy->group[index];
    if (((output->filter.result == NAV_ESKF_OK) || (output->filter.result == NAV_ESKF_SOFT_WEIGHTED)) &&
        isfinite(output->filter.gain_norm) && (output->filter.gain_norm > 0.0f))
    {
        group->rejects = 0U;
        if (group->confirmations < config->confirmation_count) { group->confirmations++; }
        if (group->confirmations >= config->confirmation_count)
        {
            policy->active_mask &= (uint8_t)~(1U << index);
            if (policy->pending_group == index) { policy->pending_valid = 0U; }
            if (policy->active_mask == 0U) { policy->attempts = 0U; policy->limited = 0U; }
        }
    }
    else if (output->filter.result == NAV_ESKF_REJECTED_NIS)
    {
        group->confirmations = 0U;
        if (group->rejects < config->reject_count) { group->rejects++; }
        if ((group->rejects >= config->reject_count) && !policy->limited && !policy->pending_valid)
        {
            policy->pending_valid = 1U; policy->pending_group = (uint8_t)index;
            policy->pending_source = (uint8_t)event->source; policy->pending_chain = event->evidence.chain;
            policy->pending_loss = event->evidence.loss_tokens[index]; policy->pending_ordinal = event->evidence.ordinal;
            if (output->action == NAV_ESKF_RECOVERY_ACTION_NONE) { output->action = NAV_ESKF_RECOVERY_ACTION_PENDING; }
        }
    }
    else { group->rejects = 0U; group->confirmations = 0U; }
}

/* Screen only the existing public measurement contract before optional scaling.
 * Invalid data still goes through the single original Update, preserving its
 * outcome and error precedence even if a simultaneous covariance fault exists. */
static uint8_t Recovery_MeasurementAllowsScale(const NavigationEskfMeasurement *measurement)
{
    uint32_t dimension = ((measurement->group == 0U) || (measurement->group == 2U)) ? 2U : 1U;
    if (measurement->physically_valid == 0U) { return 0U; }
    for (uint32_t i = 0U; i < NAV_ESKF_AXES; i++)
    {
        if (!isfinite(measurement->lever_arm_b_m[i]) || !isfinite(measurement->angular_rate_b_radps[i]))
        { return 0U; }
    }
    for (uint32_t i = 0U; i < dimension; i++)
    {
        if (!isfinite(measurement->observation[i]) || !isfinite(measurement->variance[i]) ||
            (measurement->variance[i] <= 0.0f)) { return 0U; }
    }
    return 1U;
}

static NavigationEskfRecoveryResult Recovery_TransactionRun(NavigationEskfRecoveryTransaction *transaction,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *filter_config,
    const NavigationEskfRecoveryConfig *config, const NavigationEskfRecoveryEvent *event,
    NavigationEskfRecoveryOutput *output, uint8_t revision)
{
    NavigationEskfRecoveryResult result;
    NavigationEskfResult update;
    uint8_t eligible = Recovery_EvidenceMerge(&transaction->policy, event);
    if (eligible && Recovery_MeasurementAllowsScale(&event->measurement) &&
        Recovery_ScaleDue(&transaction->policy, config, event))
    {
        result = Recovery_ScaleTry(transaction, workspace, config, event, output);
        if (result != NAV_ESKF_RECOVERY_COMPLETE) { return result; }
    }
    update = (revision == 2U) ?
        NavigationEskf_UpdateRevision2(&transaction->state, workspace, filter_config, &event->measurement, &output->filter) :
        NavigationEskf_Update(&transaction->state, workspace, filter_config, &event->measurement, &output->filter);
    if (update == NAV_ESKF_NUMERIC_ERROR) { return NAV_ESKF_RECOVERY_NUMERIC_ERROR; }
    if (update == NAV_ESKF_MODEL_MISMATCH) { return NAV_ESKF_RECOVERY_MODEL_MISMATCH; }
    if (update == NAV_ESKF_INVALID_INPUT) { return NAV_ESKF_RECOVERY_MEASUREMENT_INVALID; }
    if (eligible) { Recovery_OutcomeApply(&transaction->policy, config, event, output); }
    return NAV_ESKF_RECOVERY_COMPLETE;
}

static NavigationEskfRecoveryResult Recovery_UpdateCandidate(
    NavigationEskfState *state, NavigationEskfRecoveryReplayState *policy,
    NavigationEskfWorkspace *workspace, NavigationEskfRecoveryTransaction *transaction,
    const NavigationEskfConfig *filter_config, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryEvent *event, NavigationEskfRecoveryOutput *output,
    uint8_t revision)
{
    NavigationEskfRecoveryResult result;
    const RecoveryRegion regions[8] = {{state, sizeof(*state), 1U}, {policy, sizeof(*policy), 1U},
        {workspace, sizeof(*workspace), 1U}, {transaction, sizeof(*transaction), 1U},
        {filter_config, sizeof(*filter_config), 0U}, {config, sizeof(*config), 0U},
        {event, sizeof(*event), 0U}, {output, sizeof(*output), 1U}};
    if (!Recovery_RegionsDisjoint(regions, 8U)) { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    memset(output, 0, sizeof(*output)); output->filter.result = NAV_ESKF_INVALID_INPUT;
    if ((NavigationEskfRecovery_ConfigValidate(config) != NAV_ESKF_RECOVERY_COMPLETE) ||
        (NavigationEskf_ConfigValidate(filter_config) != NAV_ESKF_OK) ||
        !Recovery_PolicyValid(policy, config) || (state->initialized != 1U) ||
        (event->source >= NAV_ESKF_RECOVERY_SOURCES) || (event->measurement.group >= NAV_ESKF_RECOVERY_GROUPS) ||
        (event->evidence.qualified > 1U) ||
        ((event->evidence.ordinal != 0U) && (event->evidence.chain == 0U)) ||
        ((event->evidence.ordinal == 0U) && event->evidence.qualified) ||
        (event->mission != policy->mission) || (event->calibration != policy->calibration) ||
        (state->generation != policy->mission) || (event->receive_us == 0U))
    { return NAV_ESKF_RECOVERY_INVALID_ARGUMENT; }
    memcpy(&transaction->state, state, sizeof(*state)); memcpy(&transaction->policy, policy, sizeof(*policy));
    result = Recovery_TransactionRun(transaction, workspace, filter_config, config, event, output, revision);
    if (result == NAV_ESKF_RECOVERY_COMPLETE)
    { memcpy(state, &transaction->state, sizeof(*state)); memcpy(policy, &transaction->policy, sizeof(*policy)); }
    else { output->action = NAV_ESKF_RECOVERY_ACTION_NONE; }
    return result;
}

NavigationEskfRecoveryResult NavigationEskfRecovery_UpdateCandidate(
    NavigationEskfState *state, NavigationEskfRecoveryReplayState *policy,
    NavigationEskfWorkspace *workspace, NavigationEskfRecoveryTransaction *transaction,
    const NavigationEskfConfig *filter_config, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryEvent *event, NavigationEskfRecoveryOutput *output)
{
    return Recovery_UpdateCandidate(state, policy, workspace, transaction,
        filter_config, config, event, output, 1U);
}

NavigationEskfRecoveryResult NavigationEskfRecovery_UpdateCandidateRevision2(
    NavigationEskfState *state, NavigationEskfRecoveryReplayState *policy,
    NavigationEskfWorkspace *workspace, NavigationEskfRecoveryTransaction *transaction,
    const NavigationEskfConfig *filter_config, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryEvent *event, NavigationEskfRecoveryOutput *output)
{
    return Recovery_UpdateCandidate(state, policy, workspace, transaction,
        filter_config, config, event, output, 2U);
}
