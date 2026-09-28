#include "navigation_integrity.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

_Static_assert(sizeof(NavigationIntegrityContext) <= 192U,
               "GNSS integrity must use constant bounded memory");

static uint8_t NavigationIntegrity_Positive(float value)
{
    return (uint8_t)(isfinite(value) && (value > 0.0f));
}

NavigationIntegrityProcessResult NavigationIntegrity_ConfigValidate(
    const NavigationIntegrityConfig *config)
{
    if (config == NULL) { return NAV_INTEGRITY_PROCESS_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(config, NavigationIntegrityConfig,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((config->enabled > 1U) ||
        (config->max_gap_us < 40000U) || (config->max_gap_us > 1200000U) ||
        (config->suspect_duration_us == 0U) ||
        (config->reject_duration_us == 0U) ||
        (config->recovery_duration_us == 0U) ||
        (NavigationIntegrity_Positive(config->error_threshold_m) == 0U) ||
        (NavigationIntegrity_Positive(config->recovery_threshold_m) == 0U) ||
        (config->recovery_threshold_m >= config->error_threshold_m) ||
        (NavigationIntegrity_Positive(config->position_r_scale) == 0U) ||
        (config->position_r_scale < 1.0f) ||
        (NavigationIntegrity_Positive(config->hacc_max_m) == 0U) ||
        (NavigationIntegrity_Positive(config->sacc_max_mps) == 0U))
    { return NAV_INTEGRITY_PROCESS_INVALID; }
    return NAV_INTEGRITY_PROCESS_OK;
}

NavigationIntegrityProcessResult NavigationIntegrity_Reset(
    NavigationIntegrityContext *context, const NavigationIntegrityConfig *config)
{
    if ((context == NULL) ||
        (NavigationIntegrity_ConfigValidate(config) != NAV_INTEGRITY_PROCESS_OK))
    { return NAV_INTEGRITY_PROCESS_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(context, 0, sizeof(*context));
    context->config = *config;
    context->state = NAV_INTEGRITY_NORMAL;
    return NAV_INTEGRITY_PROCESS_OK;
}

static uint8_t NavigationIntegrity_InputValid(const NavigationIntegrityInput *input)
{
    uint8_t axis;
    if ((input == NULL) || (input->timestamp_us == 0ULL) ||
        (input->valid_group_mask > 15U))
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (axis = 0U; axis < 2U; axis++)
    {
        SILVERSTAR_ASSERT(axis < 2U, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                          SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
        if ((((input->valid_group_mask & 1U) != 0U) &&
             !isfinite(input->position_en[axis])) ||
            (((input->valid_group_mask & 4U) != 0U) &&
             !isfinite(input->velocity_en[axis])))
        { return 0U; }
    }
    return 1U;
}

static uint32_t NavigationIntegrity_DurationAdd(uint32_t current, uint32_t delta)
{
    return (current > UINT32_MAX - delta) ? UINT32_MAX : current + delta;
}

static void NavigationIntegrity_ChainReset(NavigationIntegrityContext *context,
                                           NavigationIntegrityDecision *decision)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(decision, NavigationIntegrityDecision,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    context->velocity_chain_valid = 0U;
    context->anchor_valid = 0U;
    context->anchor_trusted = 0U;
    context->abnormal_duration_us = 0U;
    context->reject_duration_us = 0U;
    context->healthy_duration_us = 0U;
    context->integrated_velocity_en[0] = 0.0f;
    context->integrated_velocity_en[1] = 0.0f;
    decision->chain_reset = 1U;
}

static void NavigationIntegrity_ChainStart(NavigationIntegrityContext *context,
    const NavigationIntegrityInput *input, uint8_t position_good)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    context->velocity_chain_valid = 1U;
    context->last_velocity_en[0] = input->velocity_en[0];
    context->last_velocity_en[1] = input->velocity_en[1];
    if (position_good != 0U)
    {
        context->anchor_valid = 1U;
        context->anchor_trusted = (uint8_t)(context->state == NAV_INTEGRITY_NORMAL);
        context->anchor_timestamp_us = input->timestamp_us;
        context->anchor_position_en[0] = input->position_en[0];
        context->anchor_position_en[1] = input->position_en[1];
    }
}

static void NavigationIntegrity_ClosureCalculate(
    const NavigationIntegrityContext *context, const NavigationIntegrityInput *input,
    NavigationIntegrityDecision *decision)
{
    uint8_t axis;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(decision, NavigationIntegrityDecision,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (axis = 0U; axis < 2U; axis++)
    {
        SILVERSTAR_ASSERT(axis < 2U, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                          SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
        decision->position_displacement_en[axis] =
            input->position_en[axis] - context->anchor_position_en[axis];
        decision->integrated_velocity_en[axis] =
            context->integrated_velocity_en[axis];
        decision->closure_en[axis] =
            decision->position_displacement_en[axis] -
            decision->integrated_velocity_en[axis];
    }
    decision->closure_norm_m = hypotf(decision->closure_en[0],
                                      decision->closure_en[1]);
    decision->evidence_valid = (uint8_t)isfinite(decision->closure_norm_m);
}

static void NavigationIntegrity_StateAdvance(NavigationIntegrityContext *context,
    const NavigationIntegrityDecision *decision, uint32_t delta_us)
{
    const NavigationIntegrityConfig *config = &context->config;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(decision, NavigationIntegrityDecision,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (decision->evidence_valid == 0U)
    {
        context->abnormal_duration_us = 0U;
        context->reject_duration_us = 0U;
        context->healthy_duration_us = 0U;
        return;
    }
    if (decision->closure_norm_m > config->error_threshold_m)
    {
        context->healthy_duration_us = 0U;
        if (context->state == NAV_INTEGRITY_NORMAL)
        {
            context->abnormal_duration_us = NavigationIntegrity_DurationAdd(
                context->abnormal_duration_us, delta_us);
            if (context->abnormal_duration_us >= config->suspect_duration_us)
            {
                context->state = NAV_INTEGRITY_SUSPECT;
                context->reject_duration_us = 0U;
            }
        }
        else if (context->state == NAV_INTEGRITY_SUSPECT)
        {
            context->reject_duration_us = NavigationIntegrity_DurationAdd(
                context->reject_duration_us, delta_us);
            if (context->reject_duration_us >= config->reject_duration_us)
            { context->state = NAV_INTEGRITY_REJECTED; }
        }
        return;
    }
    context->abnormal_duration_us = 0U;
    context->reject_duration_us = 0U;
    if ((decision->closure_norm_m >= config->recovery_threshold_m) ||
        (context->anchor_trusted == 0U))
    {
        context->healthy_duration_us = 0U;
        return;
    }
    if (context->state != NAV_INTEGRITY_NORMAL)
    {
        context->healthy_duration_us = NavigationIntegrity_DurationAdd(
            context->healthy_duration_us, delta_us);
        if (context->healthy_duration_us >= config->recovery_duration_us)
        {
            context->state = (context->state == NAV_INTEGRITY_REJECTED) ?
                NAV_INTEGRITY_SUSPECT : NAV_INTEGRITY_NORMAL;
            context->healthy_duration_us = 0U;
        }
    }
}

static void NavigationIntegrity_DecisionFinish(
    const NavigationIntegrityContext *context, NavigationIntegrityDecision *decision)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(decision, NavigationIntegrityDecision,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    decision->state = context->state;
    decision->state_changed = (uint8_t)(decision->previous_state != decision->state);
    if (context->state == NAV_INTEGRITY_REJECTED)
    { decision->admitted_group_mask &= (uint8_t)~1U; }
    if (context->state == NAV_INTEGRITY_SUSPECT)
    { decision->position_r_scale = context->config.position_r_scale; }
}

static uint32_t NavigationIntegrity_DeltaGet(
    const NavigationIntegrityContext *context, const NavigationIntegrityInput *input,
    NavigationIntegrityDecision *decision)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->last_timestamp_us == 0ULL) { return 0U; }
    if ((input->source != context->last_source) ||
        (input->epoch != context->last_epoch))
    { decision->reason = NAV_INTEGRITY_REASON_SOURCE_CHANGE; }
    else if (input->sequence != context->last_sequence + 1U)
    { decision->reason = NAV_INTEGRITY_REASON_SEQUENCE_JUMP; }
    else if ((input->timestamp_us <= context->last_timestamp_us) ||
             (input->timestamp_us - context->last_timestamp_us >
              context->config.max_gap_us))
    { decision->reason = NAV_INTEGRITY_REASON_TIME_GAP; }
    else
    { return (uint32_t)(input->timestamp_us - context->last_timestamp_us); }
    return 0U;
}

static void NavigationIntegrity_AnchorSet(NavigationIntegrityContext *context,
    const NavigationIntegrityInput *input)
{
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    context->anchor_valid = 1U;
    context->anchor_trusted = (uint8_t)(context->state == NAV_INTEGRITY_NORMAL);
    context->anchor_timestamp_us = input->timestamp_us;
    context->anchor_position_en[0] = input->position_en[0];
    context->anchor_position_en[1] = input->position_en[1];
    context->integrated_velocity_en[0] = 0.0f;
    context->integrated_velocity_en[1] = 0.0f;
}

static void NavigationIntegrity_ChainAdvance(NavigationIntegrityContext *context,
    const NavigationIntegrityInput *input, NavigationIntegrityDecision *decision,
    uint32_t delta_us, uint8_t position_good)
{
    uint8_t axis;
    float dt_s = (float)delta_us * 1e-6f;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->velocity_chain_valid == 0U)
    {
        NavigationIntegrity_ChainStart(context, input, position_good);
        if (decision->reason == NAV_INTEGRITY_REASON_HEALTHY)
        { decision->reason = NAV_INTEGRITY_REASON_ANCHOR; }
        return;
    }
    for (axis = 0U; axis < 2U; axis++)
    {
        SILVERSTAR_ASSERT(axis < 2U, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                          SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
        context->integrated_velocity_en[axis] += 0.5f *
            (context->last_velocity_en[axis] + input->velocity_en[axis]) * dt_s;
        context->last_velocity_en[axis] = input->velocity_en[axis];
    }
    if (!isfinite(context->integrated_velocity_en[0]) ||
        !isfinite(context->integrated_velocity_en[1]))
    {
        NavigationIntegrity_ChainReset(context, decision);
        decision->reason = NAV_INTEGRITY_REASON_QUALITY;
        NavigationIntegrity_ChainStart(context, input, position_good);
    }
    else if ((context->anchor_valid == 0U) && (position_good != 0U))
    {
        NavigationIntegrity_AnchorSet(context, input);
        decision->reason = NAV_INTEGRITY_REASON_ANCHOR;
    }
    else if ((context->anchor_valid != 0U) && (position_good != 0U))
    {
        NavigationIntegrity_ClosureCalculate(context, input, decision);
        if ((decision->evidence_valid != 0U) &&
            (decision->closure_norm_m > context->config.error_threshold_m))
        { decision->reason = NAV_INTEGRITY_REASON_CLOSURE_ABNORMAL; }
    }
}

static void NavigationIntegrity_QualityApply(NavigationIntegrityContext *context,
    const NavigationIntegrityInput *input, NavigationIntegrityDecision *decision,
    uint32_t delta_us)
{
    uint8_t position_good;
    uint8_t velocity_good;
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(input, NavigationIntegrityInput,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(decision, NavigationIntegrityDecision,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    position_good = (uint8_t)(((input->valid_group_mask & 1U) != 0U) &&
        (NavigationIntegrity_Positive(input->hacc_m) != 0U) &&
        (input->hacc_m <= context->config.hacc_max_m));
    velocity_good = (uint8_t)(((input->valid_group_mask & 4U) != 0U) &&
        (NavigationIntegrity_Positive(input->sacc_mps) != 0U) &&
        (input->sacc_mps <= context->config.sacc_max_mps));
    if (velocity_good == 0U)
    {
        decision->reason = ((input->valid_group_mask & 4U) == 0U) ?
            NAV_INTEGRITY_REASON_VELOCITY_INVALID : NAV_INTEGRITY_REASON_QUALITY;
    }
    if ((velocity_good == 0U) ||
        ((context->last_timestamp_us != 0ULL) && (delta_us == 0U)))
    { NavigationIntegrity_ChainReset(context, decision); }
    if (velocity_good != 0U)
    { NavigationIntegrity_ChainAdvance(context, input, decision, delta_us, position_good); }
    if ((position_good == 0U) &&
        (decision->reason == NAV_INTEGRITY_REASON_HEALTHY))
    {
        decision->reason = ((input->valid_group_mask & 1U) == 0U) ?
            NAV_INTEGRITY_REASON_POSITION_INVALID : NAV_INTEGRITY_REASON_QUALITY;
    }
}

NavigationIntegrityProcessResult NavigationIntegrity_Receive(
    NavigationIntegrityContext *context, const NavigationIntegrityInput *input,
    NavigationIntegrityDecision *decision)
{
    uint32_t delta_us;
    if ((context == NULL) || (decision == NULL) ||
        (NavigationIntegrity_InputValid(input) == 0U))
    { return NAV_INTEGRITY_PROCESS_INVALID; }
    SILVERSTAR_ASSERT_OBJECT(context, NavigationIntegrityContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(decision, NavigationIntegrityDecision,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(context->state <= NAV_INTEGRITY_REJECTED,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    (void)memset(decision, 0, sizeof(*decision));
    decision->decision_us = input->timestamp_us;
    decision->admitted_group_mask = input->valid_group_mask;
    decision->position_r_scale = 1.0f;
    decision->previous_state = context->state;
    decision->state = context->state;
    decision->reason = NAV_INTEGRITY_REASON_HEALTHY;
    if (context->config.enabled == 0U) { return NAV_INTEGRITY_PROCESS_OK; }
    if ((context->last_timestamp_us != 0ULL) &&
        (input->epoch == context->last_epoch) &&
        (input->source == context->last_source) &&
        (input->sequence == context->last_sequence))
    { return NAV_INTEGRITY_PROCESS_DUPLICATE; }
    delta_us = NavigationIntegrity_DeltaGet(context, input, decision);
    NavigationIntegrity_QualityApply(context, input, decision, delta_us);
    NavigationIntegrity_StateAdvance(context, decision, delta_us);
    context->last_timestamp_us = input->timestamp_us;
    context->last_sequence = input->sequence;
    context->last_source = input->source;
    context->last_epoch = input->epoch;
    NavigationIntegrity_DecisionFinish(context, decision);
    SILVERSTAR_ASSERT(context->velocity_chain_valid <= 1U,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    SILVERSTAR_ASSERT(context->anchor_valid <= context->velocity_chain_valid,
        SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    return NAV_INTEGRITY_PROCESS_OK;
}
