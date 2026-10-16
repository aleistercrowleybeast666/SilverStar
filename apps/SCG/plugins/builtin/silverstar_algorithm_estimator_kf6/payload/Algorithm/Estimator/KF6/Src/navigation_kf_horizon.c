#include "navigation_kf_horizon.h"
#include "system_user_config.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

static uint8_t KfHorizon_Overlap(const void *a, size_t a_size, const void *b, size_t b_size)
{
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return (uint8_t)((x <= y) ? (y - x < a_size) : (x - y < b_size));
}

static NavigationKfHorizonResult KfHorizon_Fault(NavigationKfHorizon *horizon,
    NavigationKfHorizonResult result)
{
    horizon->faulted = 1U;
    return result;
}

/* Full covariance validation, without the legacy kernel's numerical recovery.
 * A damaged internal state must latch a fault rather than resume from a clamp. */
static uint8_t KfHorizon_StateValid(const NavigationKfContext *state)
{
    float lower[6][6] = {{0.0f}};
    if (state->initialized != 1U) { return 0U; }
    for (uint32_t row = 0U; row < 6U; row++)
    {
        if (!isfinite(state->state[row])) { return 0U; }
        for (uint32_t column = 0U; column < 6U; column++)
        {
            if (column > row) { break; }
            float value = state->covariance[row][column];
            if (!isfinite(value) || (value != state->covariance[column][row])) { return 0U; }
            for (uint32_t k = 0U; k < 6U; k++)
            { if (k >= column) { break; } value -= lower[row][k] * lower[column][k]; }
            if (row == column)
            {
                if (!isfinite(value) || (value <= 0.0f)) { return 0U; }
                lower[row][column] = sqrtf(value);
            }
            else { lower[row][column] = value / lower[column][column]; }
            if (!isfinite(lower[row][column])) { return 0U; }
        }
    }
    return 1U;
}

static uint8_t KfHorizon_ModelEqual(const NavigationKfContext *a, const NavigationKfContext *b)
{
    if (!isfinite(a->baro_std_m) || (a->baro_std_m <= 0.0f) ||
        (a->baro_std_m != b->baro_std_m) || !isfinite(a->nis_max_r_scale) ||
        (a->nis_max_r_scale < 1.0f) || (a->nis_max_r_scale != b->nis_max_r_scale)) { return 0U; }
    for (uint32_t axis = 0U; axis < 3U; axis++)
    {
        if (!isfinite(a->process_accel_std_mps2[axis]) || (a->process_accel_std_mps2[axis] <= 0.0f) ||
            (a->process_accel_std_mps2[axis] != b->process_accel_std_mps2[axis]) ||
            !isfinite(a->nis_soft_threshold[axis]) || (a->nis_soft_threshold[axis] <= 0.0f) ||
            !isfinite(a->nis_hard_threshold[axis]) ||
            (a->nis_hard_threshold[axis] < a->nis_soft_threshold[axis]) ||
            (a->nis_soft_threshold[axis] != b->nis_soft_threshold[axis]) ||
            (a->nis_hard_threshold[axis] != b->nis_hard_threshold[axis])) { return 0U; }
    }
    return 1U;
}

static NavigationKfHorizonResult KfHorizon_Ready(NavigationKfHorizon *horizon)
{
    if (horizon == NULL) { return NAV_KF_HORIZON_INVALID; }
    if ((horizon->initialized != 1U) || (horizon->faulted == 1U)) { return NAV_KF_HORIZON_NOT_READY; }
    if ((horizon->faulted > 1U) || (horizon->body_head >= NAV_KF_HORIZON_BODY_CAPACITY) ||
        (horizon->body_count > NAV_KF_HORIZON_BODY_CAPACITY) ||
        (horizon->event_count > NAV_KF_HORIZON_EVENT_CAPACITY) ||
        (horizon->completion_count > horizon->event_count) ||
        (horizon->completion_read > horizon->completion_count) ||
        (horizon->initial_us > horizon->primary_us) || (horizon->primary_us > horizon->output_us) ||
        (horizon->output_us > horizon->present_us) || (horizon->horizon_us < 10000ULL) ||
        (horizon->horizon_us > 550000ULL) || !KfHorizon_StateValid(&horizon->primary) ||
        !KfHorizon_ModelEqual(&horizon->primary, &horizon->receive_tracker[0]))
    { return KfHorizon_Fault(horizon, NAV_KF_HORIZON_NUMERIC_ERROR); }
    return NAV_KF_HORIZON_OK;
}

NavigationKfHorizonResult NavigationKfHorizon_Reset(NavigationKfHorizon *horizon,
    const NavigationKfContext *state, uint64_t timestamp_us, uint32_t epoch,
    uint32_t source, uint32_t generation, uint64_t horizon_us)
{
    if ((horizon == NULL) || (state == NULL) ||
        KfHorizon_Overlap(horizon, sizeof(*horizon), state, sizeof(*state))) { return NAV_KF_HORIZON_INVALID; }
    if ((timestamp_us == 0U) || (horizon_us < 10000ULL) || (horizon_us > 550000ULL) ||
        !KfHorizon_ModelEqual(state, state) || !KfHorizon_StateValid(state)) { return NAV_KF_HORIZON_INVALID; }
    memset(horizon, 0, sizeof(*horizon));
    horizon->primary = *state; horizon->predictor = *state;
    for (uint32_t producer = 0U; producer < NAV_KF_HORIZON_SOURCE_COUNT; producer++)
    { horizon->receive_tracker[producer] = *state; horizon->applied_source[producer] = UINT32_MAX; }
    horizon->initial_us = timestamp_us; horizon->present_us = timestamp_us;
    horizon->primary_us = timestamp_us; horizon->output_us = timestamp_us;
    horizon->epoch = epoch; horizon->source = source; horizon->generation = generation;
    horizon->horizon_us = horizon_us; horizon->initialized = 1U; horizon->warmup = 1U;
    return NAV_KF_HORIZON_OK;
}

NavigationKfHorizonResult NavigationKfHorizon_BodyReceive(NavigationKfHorizon *horizon,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s,
    uint32_t source, uint32_t generation)
{
    NavigationKfHorizonResult result = KfHorizon_Ready(horizon);
    NavigationReplayImu *body;
    if (result != NAV_KF_HORIZON_OK) { return result; }
    if ((delta_velocity == NULL) || KfHorizon_Overlap(horizon, sizeof(*horizon), delta_velocity, 3U*sizeof(float)))
    { return NAV_KF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_KF_HORIZON_BUSY; }
    if ((source != horizon->source) || (generation != horizon->generation))
    { return KfHorizon_Fault(horizon, NAV_KF_HORIZON_EPOCH_MISMATCH); }
    if (!isfinite(dt_s) || (dt_s <= 0.0f) || (dt_s > SYSTEM_KF_PREDICTION_DT_MAX_S) ||
        (timestamp_us <= horizon->present_us) ||
        (fabsf((float)(timestamp_us-horizon->present_us)*1.0e-6f-dt_s) > 2.0e-6f))
    { return KfHorizon_Fault(horizon, NAV_KF_HORIZON_DISCONTINUITY); }
    for (uint32_t axis = 0U; axis < 3U; axis++)
    { if (!isfinite(delta_velocity[axis])) { return KfHorizon_Fault(horizon, NAV_KF_HORIZON_DISCONTINUITY); } }
    if (horizon->body_count == NAV_KF_HORIZON_BODY_CAPACITY)
    {
        if (horizon->capacity_count < UINT32_MAX) { horizon->capacity_count++; }
        return KfHorizon_Fault(horizon, NAV_KF_HORIZON_CAPACITY);
    }
    body = &horizon->body[(horizon->body_head+horizon->body_count)%NAV_KF_HORIZON_BODY_CAPACITY];
    body->start_us = horizon->present_us; body->end_us = timestamp_us; body->dt_s = dt_s;
    memcpy(body->delta_velocity, delta_velocity, sizeof(body->delta_velocity));
    horizon->body_count++; horizon->present_us = timestamp_us;
    return NAV_KF_HORIZON_OK;
}

NavigationKfHorizonResult NavigationKfHorizon_ReceiveTrack(NavigationKfHorizon *horizon,
    const NavigationKfGnssEpoch *receive_epoch, NavigationReplayEvent *event)
{
    NavigationKfHorizonResult ready = KfHorizon_Ready(horizon);
    SystemFusionExecutionResult receipt;
    NavigationKfGnssReacquisitionContext *tracker;
    if (ready != NAV_KF_HORIZON_OK) { return ready; }
    if ((receive_epoch == NULL) || (event == NULL) ||
        KfHorizon_Overlap(horizon,sizeof(*horizon),event,sizeof(*event)) ||
        KfHorizon_Overlap(horizon,sizeof(*horizon),receive_epoch,sizeof(*receive_epoch)) ||
        KfHorizon_Overlap(event,sizeof(*event),receive_epoch,sizeof(*receive_epoch)) ||
        (event->source >= NAV_KF_HORIZON_SOURCE_COUNT) || (receive_epoch->valid_group_mask > 15U))
    { return NAV_KF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_KF_HORIZON_BUSY; }
    if ((event->calibration_generation != horizon->generation) ||
        (receive_epoch->timestamp_us < horizon->initial_us)) { return NAV_KF_HORIZON_EPOCH_MISMATCH; }
    if (!KfHorizon_StateValid(&horizon->receive_tracker[event->source]) ||
        !KfHorizon_ModelEqual(&horizon->primary,&horizon->receive_tracker[event->source]))
    { return KfHorizon_Fault(horizon,NAV_KF_HORIZON_NUMERIC_ERROR); }
    receipt = SystemFusionTiming_ReceiptCheck(&horizon->receipt[event->source],event->sequence,0x80U);
    if (receipt == SYSTEM_FUSION_EXEC_DUPLICATE) { return NAV_KF_HORIZON_DUPLICATE; }
    if (receipt != SYSTEM_FUSION_EXEC_COMPLETE) { return NAV_KF_HORIZON_DISCONTINUITY; }
    if ((receive_epoch->timestamp_us > horizon->present_us) ||
        (receive_epoch->timestamp_us <= horizon->last_receive_us[event->source])) { return NAV_KF_HORIZON_INVALID; }
    if (horizon->present_us-receive_epoch->timestamp_us > 500000ULL) { return NAV_KF_HORIZON_STALE; }
    NavigationKf_GnssEpochTrack(&horizon->receive_tracker[event->source],receive_epoch);
    tracker = &horizon->receive_tracker[event->source].gnss_reacquisition;
    event->receive_timestamp_us = receive_epoch->timestamp_us; event->epoch = horizon->epoch;
    event->valid_group_mask = receive_epoch->valid_group_mask; event->consistency_mask = tracker->consistency_mask;
    for (uint32_t group = 0U; group < 4U; group++)
    {
        const NavigationKfGnssReacquireGroupState *state = &tracker->group[group];
        event->evidence[group].availability_timestamp_us = state->availability_timestamp_us;
        event->evidence[group].consistency_start_us = state->consistency_start_us;
        event->evidence[group].generation = state->generation;
        event->evidence[group].consistent_count = state->consistent_count;
        event->evidence[group].outage = state->outage; event->evidence[group].loss_latched = state->loss_latched;
        event->evidence[group].recovery_valid = (uint8_t)((tracker->previous_epoch.valid_group_mask & (1U<<group)) != 0U);
    }
    SystemFusionTiming_ReceiptCommit(&horizon->receipt[event->source],event->sequence,0x80U);
    horizon->last_receive_us[event->source] = receive_epoch->timestamp_us;
    return NAV_KF_HORIZON_OK;
}

static NavigationKfHorizonResult KfHorizon_EventValidate(const NavigationKfHorizon *horizon,
    const NavigationKfHorizonEvent *event)
{
    uint32_t dimension = ((event->group & 1U) || (event->group == 4U)) ? 1U : 2U;
    if ((event->group >= 5U) || (event->source >= NAV_KF_HORIZON_SOURCE_COUNT) ||
        ((event->group == 4U) && (event->source != SYSTEM_FUSION_BAROMETER_SOURCE)) ||
        (event->physically_valid > 1U) || (event->consistency_valid > 1U) ||
        !isfinite(event->quality_scale) || (event->quality_scale < 1.0f) ||
        !isfinite(event->consistency_scale) || (event->consistency_scale < 1.0f) ||
        (event->source_us == 0U) || (event->source_us > event->receive_us) ||
        (event->receive_us > horizon->present_us) || (event->evidence.outage > 1U) ||
        (event->evidence.loss_latched > 1U) || (event->evidence.recovery_valid > 1U)) { return NAV_KF_HORIZON_INVALID; }
    if ((event->epoch != horizon->epoch) || (event->generation != horizon->generation) ||
        (event->source_us < horizon->initial_us)) { return NAV_KF_HORIZON_EPOCH_MISMATCH; }
    if ((horizon->present_us-event->source_us > 600000ULL) ||
        (horizon->present_us-event->receive_us > 500000ULL)) { return NAV_KF_HORIZON_STALE; }
    for (uint32_t axis = 0U; axis < 2U; axis++)
    {
        if ((axis < dimension) && (!isfinite(event->observation[axis]) ||
            !isfinite(event->variance[axis]) || (event->variance[axis] <= 0.0f) ||
            !isfinite(event->base_variance[axis]) || (event->base_variance[axis] <= 0.0f)))
        { return NAV_KF_HORIZON_INVALID; }
    }
    return NAV_KF_HORIZON_OK;
}

static uint8_t KfHorizon_EventBefore(const NavigationKfHorizonEvent *a, const NavigationKfHorizonEvent *b)
{
    return (uint8_t)((a->source_us < b->source_us) ||
        ((a->source_us == b->source_us) && (a->group < b->group)));
}

NavigationKfHorizonResult NavigationKfHorizon_Insert(NavigationKfHorizon *horizon,
    const NavigationKfHorizonEvent *event)
{
    NavigationKfHorizonResult result = KfHorizon_Ready(horizon);
    SystemFusionReceipt *receipt;
    SystemFusionExecutionResult checked;
    uint8_t bit;
    uint16_t slot;
    if (result != NAV_KF_HORIZON_OK) { return result; }
    if ((event == NULL) || KfHorizon_Overlap(horizon,sizeof(*horizon),event,sizeof(*event)))
    { return NAV_KF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_KF_HORIZON_BUSY; }
    if (horizon->body_count == 0U) { return NAV_KF_HORIZON_NOT_READY; }
    result = KfHorizon_EventValidate(horizon,event);
    if (result != NAV_KF_HORIZON_OK) { return result; }
    receipt = (event->group == 4U) ? &horizon->barometer : &horizon->receipt[event->source];
    bit = (uint8_t)(1U<<event->group);
    checked = SystemFusionTiming_ReceiptCheck(receipt,event->sequence,bit);
    if (checked == SYSTEM_FUSION_EXEC_DUPLICATE) { return NAV_KF_HORIZON_DUPLICATE; }
    if (checked != SYSTEM_FUSION_EXEC_COMPLETE) { return NAV_KF_HORIZON_DISCONTINUITY; }
    SystemFusionTiming_ReceiptCommit(receipt,event->sequence,bit);
    if (event->physically_valid != 1U) { return NAV_KF_HORIZON_INVALID; }
    if (event->source_us < horizon->primary_us)
    {
        if (horizon->late_count < UINT32_MAX) { horizon->late_count++; }
        return NAV_KF_HORIZON_LATE;
    }
    if (horizon->event_count == NAV_KF_HORIZON_EVENT_CAPACITY)
    {
        if (horizon->capacity_count < UINT32_MAX) { horizon->capacity_count++; }
        return NAV_KF_HORIZON_CAPACITY;
    }
    slot = horizon->event_count;
    for (uint16_t limit = 0U; limit < NAV_KF_HORIZON_EVENT_CAPACITY; limit++)
    {
        if ((slot == 0U) || !KfHorizon_EventBefore(event,&horizon->event[slot-1U])) { break; }
        horizon->event[slot] = horizon->event[slot-1U]; slot--;
    }
    horizon->event[slot] = *event; horizon->event[slot].result = NAV_KF_UPDATE_REJECTED_INVALID;
    horizon->event[slot].effective_update = 0U; horizon->event[slot].nis = -1.0f;
    horizon->event_count++;
    return NAV_KF_HORIZON_QUEUED;
}

static NavigationKfHorizonResult KfHorizon_PropagateTo(NavigationKfHorizon *horizon,
    NavigationKfContext *state, uint64_t *timestamp_us, uint64_t target)
{
    for (uint16_t index = 0U; index < NAV_KF_HORIZON_BODY_CAPACITY; index++)
    {
        const NavigationReplayImu *body;
        uint64_t end_us;
        float fragment_dt, delta[3];
        if ((*timestamp_us == target) || (index >= horizon->body_count)) { break; }
        body = &horizon->body[(horizon->body_head+index)%NAV_KF_HORIZON_BODY_CAPACITY];
        if (body->end_us <= *timestamp_us) { continue; }
        if ((body->start_us > *timestamp_us) || (body->end_us <= body->start_us) ||
            !isfinite(body->dt_s) || (body->dt_s <= 0.0f)) { return NAV_KF_HORIZON_DISCONTINUITY; }
        end_us = (target < body->end_us) ? target : body->end_us;
        fragment_dt = body->dt_s;
        memcpy(delta,body->delta_velocity,sizeof(delta));
        if ((*timestamp_us != body->start_us) || (end_us != body->end_us))
        {
            float fraction = (float)(end_us-*timestamp_us)/(float)(body->end_us-body->start_us);
            fragment_dt *= fraction;
            for (uint32_t axis = 0U; axis < 3U; axis++) { delta[axis] *= fraction; }
        }
        if (horizon->last_work >= NAV_KF_HORIZON_MAX_WORK) { return NAV_KF_HORIZON_CAPACITY; }
        horizon->last_work++;
        if (NavigationKf_PredictInterval(state,delta,fragment_dt,body->dt_s) != NAV_KF_PREDICT_OK)
        { return NAV_KF_HORIZON_NUMERIC_ERROR; }
        *timestamp_us = end_us;
    }
    return (*timestamp_us == target) ? NAV_KF_HORIZON_OK : NAV_KF_HORIZON_DISCONTINUITY;
}

static void KfHorizon_EvidenceApply(NavigationKfHorizon *horizon, const NavigationKfHorizonEvent *event)
{
    NavigationKfGnssReacquisitionContext *reacquisition = &horizon->candidate.gnss_reacquisition;
    NavigationKfGnssReacquireGroupState *target = &reacquisition->group[event->group];
    const NavigationReplayGroupEvidence *source = &event->evidence;
    uint8_t bit = (uint8_t)(1U<<event->group);
    if ((horizon->candidate_source[event->group] != event->source) || (target->generation != source->generation))
    {
        memset(target,0,sizeof(*target)); target->generation = source->generation;
        target->outage = source->outage; reacquisition->active_mask &= (uint8_t)~bit;
    }
    horizon->candidate_source[event->group] = event->source;
    target->availability_timestamp_us = source->availability_timestamp_us;
    target->loss_latched = source->loss_latched; target->consistent_count = source->consistent_count;
    target->consistency_start_us = source->consistency_start_us;
    if (source->recovery_valid == 0U) { target->reject_streak = 0U; target->accepted_streak = 0U; }
    reacquisition->previous_epoch.valid_group_mask = (uint8_t)(
        (reacquisition->previous_epoch.valid_group_mask & (uint8_t)~bit) | (source->recovery_valid ? bit : 0U));
    reacquisition->consistency_mask = (uint8_t)((reacquisition->consistency_mask & (uint8_t)~bit) |
        (event->consistency_valid ? bit : 0U));
}

static NavigationKfUpdateResult KfHorizon_GnssApply(NavigationKfHorizon *horizon,
    NavigationKfHorizonEvent *event)
{
    float observation[3] = {0.0f,0.0f,0.0f}, variance[3] = {1.0f,1.0f,1.0f};
    uint32_t start = (event->group & 1U) ? 2U : 0U;
    uint32_t dimension = (start == 0U) ? 2U : 1U;
    uint8_t bit = (uint8_t)(1U<<event->group);
    NavigationKfGnssSeparatedUpdateResult outcome;
    NavigationKfUpdateResult result;
    KfHorizon_EvidenceApply(horizon,event);
    for (uint32_t axis = 0U; axis < 2U; axis++)
    { if (axis < dimension) { observation[start+axis] = event->observation[axis]; variance[start+axis] = event->variance[axis]; } }
    if (event->group < 2U)
    { result = NavigationKf_UpdateGnssPositionGroups(&horizon->candidate,observation,variance,bit,&outcome); }
    else { result = NavigationKf_UpdateGnssVelocityGroups(&horizon->candidate,observation,variance,bit,&outcome); }
    if (result == NAV_KF_UPDATE_NUMERIC_ERROR) { return result; }
    event->nis = horizon->candidate.last_gnss_group_nis[event->group];
    for (uint32_t axis = 0U; axis < 2U; axis++)
    {
        if (axis >= dimension) { break; }
        event->innovation[axis] = (event->group < 2U) ? horizon->candidate.last_position_innovation[start+axis] :
            horizon->candidate.last_velocity_innovation[start+axis];
        event->effective_variance[axis] = (event->group < 2U) ? horizon->candidate.last_position_effective_variance[start+axis] :
            horizon->candidate.last_velocity_effective_variance[start+axis];
    }
    return NavigationKf_GnssGroupRecover(&horizon->candidate,(NavigationKfGnssGroup)event->group,
        (start == 0U) ? outcome.horizontal_result : outcome.vertical_result,observation,variance,event->receive_us);
}

static NavigationKfHorizonResult KfHorizon_MeasurementApply(NavigationKfHorizon *horizon, uint16_t index)
{
    NavigationKfHorizonEvent *event = &horizon->event[index];
    if (KfHorizon_EventValidate(horizon,event) != NAV_KF_HORIZON_OK) { return NAV_KF_HORIZON_NUMERIC_ERROR; }
    if (event->group < 4U) { event->result = KfHorizon_GnssApply(horizon,event); }
    else
    {
        event->innovation[0] = event->observation[0]-horizon->candidate.state[2];
        event->result = NavigationKf_UpdateBaroAltitude(&horizon->candidate,event->observation[0],event->variance[0]);
        event->nis = horizon->candidate.last_baro_nis;
        event->effective_variance[0] = event->variance[0];
        if (event->result == NAV_KF_UPDATE_SOFT_WEIGHTED)
        { event->effective_variance[0] *= fminf(horizon->candidate.nis_max_r_scale,
            event->nis/horizon->candidate.nis_soft_threshold[0]); }
    }
    event->robust_scale = event->effective_variance[0]/event->variance[0];
    event->effective_update = (uint8_t)((event->result == NAV_KF_UPDATE_ACCEPTED) ||
        (event->result == NAV_KF_UPDATE_SOFT_WEIGHTED));
    return ((event->result == NAV_KF_UPDATE_NUMERIC_ERROR) || !KfHorizon_StateValid(&horizon->candidate)) ?
        NAV_KF_HORIZON_NUMERIC_ERROR : NAV_KF_HORIZON_OK;
}

static NavigationKfHorizonResult KfHorizon_AccelerationBuild(const NavigationKfHorizon *horizon, float acceleration[3])
{
    float duration = 0.0f, delta[3] = {0.0f,0.0f,0.0f};
    memcpy(acceleration,horizon->output_acceleration,3U*sizeof(float));
    for (uint16_t index = 0U; index < NAV_KF_HORIZON_BODY_CAPACITY; index++)
    {
        const NavigationReplayImu *body;
        if (index >= horizon->body_count) { break; }
        body = &horizon->body[(horizon->body_head+index)%NAV_KF_HORIZON_BODY_CAPACITY];
        if (body->end_us <= horizon->output_us) { continue; }
        if (body->start_us < horizon->output_us) { return NAV_KF_HORIZON_DISCONTINUITY; }
        duration += body->dt_s;
        for (uint32_t axis = 0U; axis < 3U; axis++) { delta[axis] += body->delta_velocity[axis]; }
    }
    if (horizon->present_us != horizon->output_us)
    {
        if (!isfinite(duration) || (duration <= 0.0f)) { return NAV_KF_HORIZON_NUMERIC_ERROR; }
        for (uint32_t axis = 0U; axis < 3U; axis++) { acceleration[axis] = delta[axis]/duration; }
    }
    for (uint32_t axis = 0U; axis < 3U; axis++)
    { if (!isfinite(acceleration[axis])) { return NAV_KF_HORIZON_NUMERIC_ERROR; } }
    return NAV_KF_HORIZON_OK;
}

static NavigationKfHorizonResult KfHorizon_PrimaryBuild(NavigationKfHorizon *horizon,
    uint64_t target, uint16_t *ready_count)
{
    uint64_t time_us = horizon->primary_us;
    horizon->candidate = horizon->primary; *ready_count = 0U;
    memcpy(horizon->candidate_source,horizon->applied_source,sizeof(horizon->candidate_source));
    for (uint16_t index = 0U; index < NAV_KF_HORIZON_EVENT_CAPACITY; index++)
    {
        NavigationKfHorizonResult result;
        if ((index >= horizon->event_count) || (horizon->event[index].source_us > target)) { break; }
        horizon->failure_operation = horizon->event[index].operation_sequence; horizon->failure_operation_valid = 1U;
        result = KfHorizon_PropagateTo(horizon,&horizon->candidate,&time_us,horizon->event[index].source_us);
        if (result != NAV_KF_HORIZON_OK) { return result; }
        if (horizon->last_work >= NAV_KF_HORIZON_MAX_WORK) { return NAV_KF_HORIZON_CAPACITY; }
        horizon->last_work++;
        result = KfHorizon_MeasurementApply(horizon,index);
        if (result != NAV_KF_HORIZON_OK) { return result; }
        (*ready_count)++;
    }
    horizon->failure_operation_valid = 0U;
    return KfHorizon_PropagateTo(horizon,&horizon->candidate,&time_us,target);
}

NavigationKfHorizonResult NavigationKfHorizon_Advance(NavigationKfHorizon *horizon, NavigationKfContext *output)
{
    NavigationKfHorizonResult result = KfHorizon_Ready(horizon);
    uint64_t target, output_us;
    uint16_t ready_count;
    float acceleration[3];
    if (result != NAV_KF_HORIZON_OK) { return result; }
    if ((output == NULL) || KfHorizon_Overlap(horizon,sizeof(*horizon),output,sizeof(*output)))
    { return NAV_KF_HORIZON_INVALID; }
    if (horizon->completion_count != 0U) { return NAV_KF_HORIZON_BUSY; }
    if (horizon->body_count == 0U) { return NAV_KF_HORIZON_NOT_READY; }
    if (!KfHorizon_ModelEqual(&horizon->primary,output))
    { return KfHorizon_Fault(horizon,NAV_KF_HORIZON_EPOCH_MISMATCH); }
    target = (horizon->present_us-horizon->initial_us < horizon->horizon_us) ?
        horizon->initial_us : horizon->present_us-horizon->horizon_us;
    horizon->last_work = 0U; horizon->failure_operation_valid = 0U;
    result = KfHorizon_AccelerationBuild(horizon,acceleration);
    if (result != NAV_KF_HORIZON_OK) { return KfHorizon_Fault(horizon,result); }
    result = KfHorizon_PrimaryBuild(horizon,target,&ready_count);
    if (result != NAV_KF_HORIZON_OK) { return KfHorizon_Fault(horizon,result); }
    horizon->predictor = horizon->candidate; output_us = target;
    result = KfHorizon_PropagateTo(horizon,&horizon->predictor,&output_us,horizon->present_us);
    if ((result != NAV_KF_HORIZON_OK) || !KfHorizon_StateValid(&horizon->predictor))
    { return KfHorizon_Fault(horizon,(result == NAV_KF_HORIZON_OK) ? NAV_KF_HORIZON_NUMERIC_ERROR : result); }
    horizon->primary = horizon->candidate; horizon->primary_us = target;
    *output = horizon->predictor; horizon->output_us = output_us;
    memcpy(horizon->applied_source,horizon->candidate_source,sizeof(horizon->applied_source));
    memcpy(horizon->output_acceleration,acceleration,sizeof(acceleration));
    horizon->completion_count = ready_count; horizon->completion_read = 0U;
    horizon->warmup = (uint8_t)(horizon->present_us-horizon->initial_us < horizon->horizon_us);
    if (horizon->last_work > horizon->maximum_work) { horizon->maximum_work = horizon->last_work; }
    for (uint16_t limit = 0U; limit < NAV_KF_HORIZON_BODY_CAPACITY; limit++)
    {
        if ((horizon->body_count == 0U) || (horizon->body[horizon->body_head].end_us > target)) { break; }
        horizon->body_head = (uint16_t)((horizon->body_head+1U)%NAV_KF_HORIZON_BODY_CAPACITY); horizon->body_count--;
    }
    return horizon->warmup ? NAV_KF_HORIZON_WARMUP : NAV_KF_HORIZON_OK;
}

NavigationKfHorizonResult NavigationKfHorizon_CompletionPop(NavigationKfHorizon *horizon,
    NavigationKfHorizonEvent *event)
{
    NavigationKfHorizonResult result = KfHorizon_Ready(horizon);
    uint16_t remaining;
    if (result != NAV_KF_HORIZON_OK) { return result; }
    if ((event == NULL) || KfHorizon_Overlap(horizon,sizeof(*horizon),event,sizeof(*event)))
    { return NAV_KF_HORIZON_INVALID; }
    if (horizon->completion_count == 0U) { return NAV_KF_HORIZON_EMPTY; }
    *event = horizon->event[horizon->completion_read]; horizon->completion_read++;
    if (horizon->completion_read != horizon->completion_count) { return NAV_KF_HORIZON_OK; }
    remaining = (uint16_t)(horizon->event_count-horizon->completion_count);
    for (uint16_t index = 0U; index < NAV_KF_HORIZON_EVENT_CAPACITY; index++)
    { if (index >= remaining) { break; } horizon->event[index] = horizon->event[index+horizon->completion_count]; }
    horizon->event_count = remaining; horizon->completion_count = 0U; horizon->completion_read = 0U;
    return NAV_KF_HORIZON_OK;
}
