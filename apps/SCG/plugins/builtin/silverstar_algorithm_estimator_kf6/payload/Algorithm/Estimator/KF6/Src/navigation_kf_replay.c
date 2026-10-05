#include "navigation_kf_replay.h"
#include "system_user_config.h"
#include "silverstar_assert.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

static NavigationReplayResult NavigationReplay_Reject(
    NavigationReplayContext *history, NavigationReplayResult result)
{
    if (history != NULL)
    {
        history->diagnostics.last_result = result;
        history->diagnostics.rejection_count++;
        if (result == NAV_REPLAY_HISTORY_MISS)
        { history->diagnostics.history_miss_count++; }
        if (result == NAV_REPLAY_OVERFLOW)
        { history->diagnostics.overflow_count++; }
    }
    return result;
}

void NavigationReplay_Reset(NavigationReplayContext *history,
                            NavigationReplayStorage *storage,
                            const NavigationKfContext *state,
                            uint64_t timestamp_us, uint32_t epoch)
{
    if ((history == NULL) || (storage == NULL) || (state == NULL)) { return; }
    (void)memset(history, 0, sizeof(*history));
    (void)memset(storage, 0, sizeof(*storage));
    history->storage = storage;
    history->epoch = epoch;
    history->present_us = timestamp_us;
    history->epoch_start_us = timestamp_us;
    history->storage->checkpoints[0].timestamp_us = timestamp_us;
    history->storage->checkpoints[0].state = *state;
    history->checkpoint_count = 1U;
    history->receive_tracker = *state;
}

static uint64_t NavigationReplay_EventTimeGet(
    const NavigationReplayContext *history, uint16_t index)
{
    uint16_t slot = history->event_order[index];
    return (slot < NAV_REPLAY_GNSS_CAPACITY) ?
        history->events[slot].measurement_timestamp_us :
        history->barometer[slot - NAV_REPLAY_GNSS_CAPACITY].measurement_timestamp_us;
}

static const NavigationReplayEvent *NavigationReplay_EventGet(
    NavigationReplayContext *history, uint16_t index)
{
    uint16_t slot = history->event_order[index];
    const NavigationReplayBarometerEvent *barometer;
    if (slot < NAV_REPLAY_GNSS_CAPACITY) { return &history->events[slot]; }
    barometer = &history->barometer[slot - NAV_REPLAY_GNSS_CAPACITY];
    (void)memset(&history->event_work, 0, sizeof(history->event_work));
    history->event_work.measurement_timestamp_us = barometer->measurement_timestamp_us;
    history->event_work.receive_timestamp_us = barometer->receive_timestamp_us;
    history->event_work.epoch = barometer->epoch;
    history->event_work.sequence = barometer->sequence;
    history->event_work.source = barometer->source;
    history->event_work.kind = NAV_REPLAY_BAROMETER;
    history->event_work.altitude = barometer->altitude;
    history->event_work.altitude_variance = barometer->altitude_variance;
    return &history->event_work;
}

static uint16_t NavigationReplay_EventStore(
    NavigationReplayContext *history, const NavigationReplayEvent *event)
{
    uint16_t slot;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(event, NavigationReplayEvent,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (event->kind == NAV_REPLAY_BAROMETER)
    {
        for (slot = 0U; slot < NAV_REPLAY_BARO_CAPACITY; slot++)
        {
            NavigationReplayBarometerEvent *barometer = &history->barometer[slot];
            if (barometer->occupied != 0U) { continue; }
            barometer->measurement_timestamp_us = event->measurement_timestamp_us;
            barometer->receive_timestamp_us = event->receive_timestamp_us;
            barometer->epoch = event->epoch;
            barometer->sequence = event->sequence;
            barometer->source = event->source;
            barometer->altitude = event->altitude;
            barometer->altitude_variance = event->altitude_variance;
            barometer->occupied = 1U;
            return (uint16_t)(NAV_REPLAY_GNSS_CAPACITY + slot);
        }
    }
    else
    {
        for (slot = 0U; slot < NAV_REPLAY_GNSS_CAPACITY; slot++)
        {
            if (history->events[slot].kind != 0U) { continue; }
            history->events[slot] = *event;
            return slot;
        }
    }
    return UINT16_MAX;
}

static void NavigationReplay_CheckpointsPrune(NavigationReplayContext *history)
{
    uint16_t guard;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(history->checkpoint_count <= NAV_REPLAY_CHECKPOINT_CAPACITY, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    /* Keep the nearest checkpoint at or before the time-window boundary.
     * Do not silently shorten the promised window at a higher input rate. */
    for (guard = 0U; guard < NAV_REPLAY_CHECKPOINT_CAPACITY; guard++)
    {
        if (!((history->checkpoint_count > 1U) &&
           (history->present_us >= NAV_REPLAY_WINDOW_US) &&
           (history->storage->checkpoints[1].timestamp_us <=
            history->present_us - NAV_REPLAY_WINDOW_US)))
        {
            break;
        }
        history->checkpoint_count--;
        (void)memmove(history->storage->checkpoints, &history->storage->checkpoints[1],
                      history->checkpoint_count * sizeof(history->storage->checkpoints[0]));
    }
    SILVERSTAR_ASSERT(!((history->checkpoint_count > 1U) &&
           (history->present_us >= NAV_REPLAY_WINDOW_US) &&
           (history->storage->checkpoints[1].timestamp_us <=
            history->present_us - NAV_REPLAY_WINDOW_US)), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
}

static void NavigationReplay_ImuPrune(NavigationReplayContext *history, uint64_t oldest)
{
    uint16_t guard;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT((history->imu_count <= NAV_REPLAY_IMU_CAPACITY) && (history->imu_head < NAV_REPLAY_IMU_CAPACITY), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (guard = 0U; guard < NAV_REPLAY_IMU_CAPACITY; guard++)
    {
        if (!((history->imu_count != 0U) &&
           (history->storage->imu[history->imu_head].end_us <= oldest)))
        {
            break;
        }
        history->imu_head = (uint16_t)((history->imu_head + 1U) %
                                       NAV_REPLAY_IMU_CAPACITY);
        history->imu_count--;
    }
    SILVERSTAR_ASSERT(!((history->imu_count != 0U) &&
           (history->storage->imu[history->imu_head].end_us <= oldest)), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
}

static void NavigationReplay_EventsPrune(NavigationReplayContext *history, uint64_t oldest)
{
    uint16_t guard;
    uint16_t remove = 0U;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(history->event_count <= NAV_REPLAY_EVENT_CAPACITY, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (guard = 0U; guard < NAV_REPLAY_EVENT_CAPACITY; guard++)
    {
        if (!((remove < history->event_count) &&
           (NavigationReplay_EventTimeGet(history, remove) < oldest)))
        {
            break;
        }
        uint16_t slot = history->event_order[remove];
        if (slot < NAV_REPLAY_GNSS_CAPACITY) { history->events[slot].kind = 0U; }
        else { history->barometer[slot - NAV_REPLAY_GNSS_CAPACITY].occupied = 0U; }
        remove++;
    }
    SILVERSTAR_ASSERT(!((remove < history->event_count) &&
           (NavigationReplay_EventTimeGet(history, remove) < oldest)), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    if (remove != 0U)
    {
        history->event_count -= remove;
        (void)memmove(history->event_order, &history->event_order[remove],
                      history->event_count * sizeof(history->event_order[0]));
    }
}

static void NavigationReplay_Prune(NavigationReplayContext *history)
{
    uint64_t oldest;
    NavigationReplay_CheckpointsPrune(history);
    oldest = history->storage->checkpoints[0].timestamp_us;
    NavigationReplay_ImuPrune(history, oldest);
    NavigationReplay_EventsPrune(history, oldest);
}

static uint8_t NavigationReplay_ModelMatches(
    const NavigationReplayContext *history, const NavigationKfContext *state)
{
    const NavigationKfContext *initial = &history->storage->checkpoints[0].state;
    return (uint8_t)(
        (memcmp(initial->process_accel_std_mps2, state->process_accel_std_mps2,
                sizeof(state->process_accel_std_mps2)) == 0) &&
        (initial->baro_std_m == state->baro_std_m) &&
        (memcmp(initial->nis_soft_threshold, state->nis_soft_threshold,
                sizeof(state->nis_soft_threshold)) == 0) &&
        (memcmp(initial->nis_hard_threshold, state->nis_hard_threshold,
                sizeof(state->nis_hard_threshold)) == 0) &&
        (initial->nis_max_r_scale == state->nis_max_r_scale));
}

static uint8_t NavigationReplay_EventValid(const NavigationReplayContext *history,
    const NavigationReplayEvent *event)
{
    uint8_t axis;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(event, NavigationReplayEvent,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((event->kind == 0U) || (event->kind > NAV_REPLAY_BAROMETER) ||
        (event->vertical_valid > 1U) || (event->receive_timestamp_us == 0U) ||
        (event->integrity_admission_valid > 1U))
    { return 0U; }
    if ((event->integrity_admission_valid != 0U) &&
        ((event->integrity_admitted_group_mask & (uint8_t)~event->valid_group_mask) != 0U))
    { return 0U; }
    for (axis = 0U; axis < 3U; axis++)
    {
        if (((event->kind & NAV_REPLAY_POSITION) != 0U) &&
            ((event->valid_group_mask & ((axis < 2U) ? 1U : 2U)) != 0U) &&
            ((!isfinite(event->position[axis])) || (!isfinite(event->position_variance[axis])) ||
             (event->position_variance[axis] <= 0.0f)))
        { return 0U; }
        if (((event->kind & NAV_REPLAY_VELOCITY) != 0U) &&
            ((event->valid_group_mask & ((axis < 2U) ? 4U : 8U)) != 0U) &&
            ((!isfinite(event->velocity[axis])) || (!isfinite(event->velocity_variance[axis])) ||
             (event->velocity_variance[axis] <= 0.0f)))
        { return 0U; }
    }
    if (((event->kind & NAV_REPLAY_BAROMETER) != 0U) &&
        ((!isfinite(event->altitude)) || (!isfinite(event->altitude_variance)) ||
         (event->altitude_variance <= 0.0f)))
    { return 0U; }
    return 1U;
}

static uint8_t NavigationReplay_PredictionInputValid(
    const NavigationReplayContext *history, const NavigationKfContext *state,
    const float delta_velocity[3], float dt_s)
{
    uint8_t index;
    if ((history == NULL) || (state == NULL) || (delta_velocity == NULL) ||
        (history->faulted != 0U) || (history->checkpoint_count == 0U) ||
        (!isfinite(dt_s)) || (dt_s <= 0.0f) || (dt_s > SYSTEM_KF_PREDICTION_DT_MAX_S))
    { return 0U; }
    for (index = 0U; index < 3U; index++)
    {
        if (!isfinite(delta_velocity[index]))
        { return 0U; }
    }
    return 1U;
}

static NavigationReplayResult NavigationReplay_PredictionTimeValidate(
    NavigationReplayContext *history, uint64_t timestamp_us, float dt_s)
{
    uint64_t duration_us;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    duration_us = (uint64_t)((double)dt_s * 1000000.0 + 0.5);
    if ((history->prediction_count == 0U) && (history->present_us == 0U) &&
        (timestamp_us >= duration_us))
    {
        history->present_us = timestamp_us - duration_us;
        history->epoch_start_us = history->present_us;
        history->storage->checkpoints[0].timestamp_us = history->present_us;
    }
    if ((timestamp_us <= history->present_us) ||
        (timestamp_us - history->present_us > duration_us + 1U) ||
        (timestamp_us - history->present_us + 1U < duration_us))
    {
        history->faulted = 1U;
        return NavigationReplay_Reject(history, NAV_REPLAY_DISCONTINUITY);
    }
    return NAV_REPLAY_OK;
}

static NavigationReplayResult NavigationReplay_PredictionCapacityValidate(
    NavigationReplayContext *history)
{
    NavigationReplay_Prune(history);
    if ((history->imu_count >= NAV_REPLAY_IMU_CAPACITY) ||
        ((((history->prediction_count + 1U) % NAV_REPLAY_CHECKPOINT_STRIDE) == 0U) &&
         (history->checkpoint_count >= NAV_REPLAY_CHECKPOINT_CAPACITY)))
    {
        history->faulted = 1U;
        return NavigationReplay_Reject(history, NAV_REPLAY_OVERFLOW);
    }
    return NAV_REPLAY_OK;
}

static void NavigationReplay_PredictionStore(
    NavigationReplayContext *history, NavigationKfContext *state,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s)
{
    NavigationReplayImu *imu;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(history->imu_count < NAV_REPLAY_IMU_CAPACITY, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    imu = &history->storage->imu[(history->imu_head + history->imu_count) %
                        NAV_REPLAY_IMU_CAPACITY];
    imu->start_us = history->present_us;
    imu->end_us = timestamp_us;
    imu->dt_s = dt_s;
    (void)memcpy(imu->delta_velocity, delta_velocity, sizeof(imu->delta_velocity));
    history->imu_count++;
    history->prediction_count++;
    history->present_us = timestamp_us;
    *state = history->working;
    if ((history->prediction_count % NAV_REPLAY_CHECKPOINT_STRIDE) == 0U)
    {
        history->storage->checkpoints[history->checkpoint_count].timestamp_us = timestamp_us;
        history->storage->checkpoints[history->checkpoint_count].state = *state;
        history->checkpoint_count++;
        NavigationReplay_Prune(history);
    }
}

NavigationReplayResult NavigationReplay_Predict(
    NavigationReplayContext *history, NavigationKfContext *state,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s)
{
    NavigationReplayResult result;
    if (NavigationReplay_PredictionInputValid(history, state, delta_velocity, dt_s) == 0U)
    { return NavigationReplay_Reject(history, NAV_REPLAY_INVALID); }
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(history->storage, NavigationReplayStorage,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (NavigationReplay_ModelMatches(history, state) == 0U)
    {
        history->faulted = 1U;
        return NavigationReplay_Reject(history, NAV_REPLAY_EPOCH_MISMATCH);
    }
    result = NavigationReplay_PredictionTimeValidate(history, timestamp_us, dt_s);
    if (result != NAV_REPLAY_OK) { return result; }
    result = NavigationReplay_PredictionCapacityValidate(history);
    if (result != NAV_REPLAY_OK) { return result; }
    history->working = *state;
    if (NavigationKf_Predict(&history->working, delta_velocity, dt_s) == 0U)
    {
        history->faulted = 1U;
        return NavigationReplay_Reject(history, NAV_REPLAY_NUMERIC_ERROR);
    }
    NavigationReplay_PredictionStore(history, state, timestamp_us, delta_velocity, dt_s);
    history->diagnostics.last_result = NAV_REPLAY_OK;
    return NAV_REPLAY_OK;
}

NavigationReplayResult NavigationReplay_ReceiveTrack(
    NavigationReplayContext *history, const NavigationKfGnssEpoch *receive_epoch,
    NavigationReplayEvent *event)
{
    uint8_t group;
    const NavigationKfGnssReacquisitionContext *tracker;
    if ((history == NULL) || (receive_epoch == NULL) || (event == NULL) ||
        (receive_epoch->timestamp_us == 0U))
    { return NavigationReplay_Reject(history, NAV_REPLAY_INVALID); }
    if (receive_epoch->timestamp_us < history->epoch_start_us)
    { return NavigationReplay_Reject(history, NAV_REPLAY_HISTORY_MISS); }
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    /* This is the existing availability/consistency implementation. The only
     * clock supplied to it is the actual packet receive clock. Never replay it. */
    NavigationKf_GnssEpochTrack(&history->receive_tracker, receive_epoch);
    tracker = &history->receive_tracker.gnss_reacquisition;
    event->receive_timestamp_us = receive_epoch->timestamp_us;
    event->epoch = history->epoch;
    event->valid_group_mask = receive_epoch->valid_group_mask;
    event->consistency_mask = tracker->consistency_mask;
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        event->evidence[group].availability_timestamp_us =
            tracker->group[group].availability_timestamp_us;
        event->evidence[group].consistency_start_us = tracker->group[group].consistency_start_us;
        event->evidence[group].generation = tracker->group[group].generation;
        event->evidence[group].consistent_count = tracker->group[group].consistent_count;
        event->evidence[group].outage = tracker->group[group].outage;
        event->evidence[group].loss_latched = tracker->group[group].loss_latched;
        event->evidence[group].recovery_valid = (uint8_t)(
            (tracker->previous_epoch.valid_group_mask & NAV_KF_GNSS_GROUP_MASK(group)) != 0U);
    }
    return NAV_REPLAY_OK;
}

static void NavigationReplay_EvidenceApply(NavigationKfContext *state,
                                          const NavigationReplayEvent *event)
{
    uint8_t group;
    NavigationKfGnssReacquisitionContext *reacquisition = &state->gnss_reacquisition;
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(event, NavigationReplayEvent,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        uint8_t bit = NAV_KF_GNSS_GROUP_MASK(group);
        NavigationKfGnssReacquireGroupState *target = &reacquisition->group[group];
        const NavigationReplayGroupEvidence *source = &event->evidence[group];
        if (((group < 2U) && ((event->kind & NAV_REPLAY_POSITION) == 0U)) ||
            ((group >= 2U) && ((event->kind & NAV_REPLAY_VELOCITY) == 0U)))
        { continue; }
        if (target->generation != source->generation)
        {
            (void)memset(target, 0, sizeof(*target));
            target->generation = source->generation;
            target->outage = source->outage;
            reacquisition->active_mask &= (uint8_t)~bit;
        }
        target->availability_timestamp_us = source->availability_timestamp_us;
        target->loss_latched = source->loss_latched;
        target->consistent_count = source->consistent_count;
        target->consistency_start_us = source->consistency_start_us;
        if (source->recovery_valid == 0U)
        {
            target->reject_streak = 0U;
            target->accepted_streak = 0U;
        }
        reacquisition->previous_epoch.valid_group_mask = (uint8_t)(
            (reacquisition->previous_epoch.valid_group_mask & (uint8_t)~bit) |
            ((source->recovery_valid != 0U) ? bit : 0U));
        reacquisition->consistency_mask = (uint8_t)(
            (reacquisition->consistency_mask & (uint8_t)~bit) |
            (event->consistency_mask & bit));
    }
}

static void NavigationReplay_OutcomeReset(NavigationReplayOutcome *outcome)
{
    (void)memset(outcome, 0, sizeof(*outcome));
    outcome->position = NAV_KF_UPDATE_REJECTED_INVALID;
    outcome->velocity = NAV_KF_UPDATE_REJECTED_INVALID;
    outcome->barometer = NAV_KF_UPDATE_REJECTED_INVALID;
    outcome->position_groups.horizontal_result = NAV_KF_UPDATE_REJECTED_INVALID;
    outcome->position_groups.vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
    outcome->velocity_groups.horizontal_result = NAV_KF_UPDATE_REJECTED_INVALID;
    outcome->velocity_groups.vertical_result = NAV_KF_UPDATE_REJECTED_INVALID;
}

static NavigationReplayResult NavigationReplay_GroupRecoveryApply(
    NavigationKfContext *state, const NavigationReplayEvent *event,
    NavigationReplayOutcome *outcome)
{
    uint8_t group;
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(event, NavigationReplayEvent, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    /* Keep the legacy same-epoch ordering: both updates, then all results. */
    for (group = 0U; group < NAV_KF_GNSS_GROUP_COUNT; group++)
    {
        NavigationKfGnssSeparatedUpdateResult *result = (group < 2U) ?
            &outcome->position_groups : &outcome->velocity_groups;
        uint8_t vertical = (uint8_t)(group & 1U);
        if ((vertical != 0U) ? result->vertical_attempted : result->horizontal_attempted)
        {
            NavigationKfUpdateResult recovered = NavigationKf_GnssGroupRecover(state,
                (NavigationKfGnssGroup)group,
                (vertical != 0U) ? result->vertical_result : result->horizontal_result,
                (group < 2U) ? event->position : event->velocity,
                (group < 2U) ? event->position_variance : event->velocity_variance,
                event->receive_timestamp_us);
            if ((recovered == NAV_KF_UPDATE_ACCEPTED) &&
                (((vertical != 0U) ? result->vertical_result : result->horizontal_result) == NAV_KF_UPDATE_REJECTED_NIS))
            {
                if (group < 2U) { outcome->position = NAV_KF_UPDATE_ACCEPTED; }
                else { outcome->velocity = NAV_KF_UPDATE_ACCEPTED; }
            }
            if (vertical != 0U) { result->vertical_result = recovered; }
            else { result->horizontal_result = recovered; }
            if (recovered == NAV_KF_UPDATE_NUMERIC_ERROR) { return NAV_REPLAY_NUMERIC_ERROR; }
        }
        outcome->group_nis[group] = state->last_gnss_group_nis[group];
    }
    return NAV_REPLAY_OK;
}

static void NavigationReplay_GnssPositionApply(NavigationKfContext *state,
    const NavigationReplayEvent *event, NavigationReplayOutcome *outcome,
    uint8_t admitted_mask)
{
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(event, NavigationReplayEvent,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (((event->kind & NAV_REPLAY_POSITION) != 0U) &&
        ((admitted_mask & 3U) != 0U))
    {
        outcome->position = NavigationKf_UpdateGnssPositionGroups(state,
            event->position, event->position_variance, admitted_mask,
            &outcome->position_groups);
        (void)memcpy(outcome->position_innovation, state->last_position_innovation,
                      sizeof(outcome->position_innovation));
    }
}

static NavigationReplayResult NavigationReplay_EventApply(
    const NavigationReplayContext *history, NavigationKfContext *state,
    const NavigationReplayEvent *event,
                                        NavigationReplayOutcome *outcome)
{
    uint8_t admitted_mask = (event->integrity_admission_valid != 0U) ?
        event->integrity_admitted_group_mask : event->valid_group_mask;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, NavigationKfContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(event, NavigationReplayEvent,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    NavigationReplay_OutcomeReset(outcome);
    NavigationReplay_EvidenceApply(state, event);
    NavigationReplay_GnssPositionApply(state, event, outcome, admitted_mask);
    if (((event->kind & NAV_REPLAY_VELOCITY) != 0U) &&
        ((admitted_mask & 12U) != 0U))
    {
        outcome->velocity = NavigationKf_UpdateGnssVelocityGroups(state,
            event->velocity, event->velocity_variance, admitted_mask,
            &outcome->velocity_groups);
        (void)memcpy(outcome->velocity_innovation, state->last_velocity_innovation,
                      sizeof(outcome->velocity_innovation));
    }
    if (NavigationReplay_GroupRecoveryApply(state, event, outcome) != NAV_REPLAY_OK)
    { return NAV_REPLAY_NUMERIC_ERROR; }
    if ((event->kind & NAV_REPLAY_BAROMETER) != 0U)
    {
        outcome->baro_innovation = event->altitude - state->state[2];
        outcome->barometer = NavigationKf_UpdateBaroAltitude(state,
            event->altitude, event->altitude_variance);
        outcome->baro_nis = state->last_baro_nis;
    }
    return ((outcome->position == NAV_KF_UPDATE_NUMERIC_ERROR) ||
            (outcome->velocity == NAV_KF_UPDATE_NUMERIC_ERROR) ||
            (outcome->barometer == NAV_KF_UPDATE_NUMERIC_ERROR)) ?
        NAV_REPLAY_NUMERIC_ERROR : NAV_REPLAY_OK;
}

static uint8_t NavigationReplay_EventBefore(const NavigationReplayEvent *a,
                                           const NavigationReplayEvent *b)
{
    uint8_t a_rank = ((a->kind & NAV_REPLAY_POSITION) != 0U) ? 0U :
                     (((a->kind & NAV_REPLAY_VELOCITY) != 0U) ? 1U : 2U);
    uint8_t b_rank = ((b->kind & NAV_REPLAY_POSITION) != 0U) ? 0U :
                     (((b->kind & NAV_REPLAY_VELOCITY) != 0U) ? 1U : 2U);
    if (a->measurement_timestamp_us != b->measurement_timestamp_us)
    { return (uint8_t)(a->measurement_timestamp_us < b->measurement_timestamp_us); }
    if (a_rank != b_rank) { return (uint8_t)(a_rank < b_rank); }
    if (a->source != b->source) { return (uint8_t)(a->source < b->source); }
    return (uint8_t)(a->sequence < b->sequence);
}

static NavigationReplayResult NavigationReplay_SegmentPredict(
    NavigationReplayContext *history, const NavigationReplayImu *imu,
    uint64_t start_us, uint64_t end_us)
{
    float fraction;
    float delta[3];
    uint8_t axis;
    if (end_us == start_us) { return NAV_REPLAY_OK; }
    if (++history->diagnostics.last_steps > NAV_REPLAY_MAX_STEPS)
    { return NAV_REPLAY_WORK_LIMIT; }
    fraction = (float)(end_us - start_us) / (float)(imu->end_us - imu->start_us);
    for (axis = 0U; axis < 3U; axis++)
    { delta[axis] = imu->delta_velocity[axis] * fraction; }
    return (NavigationKf_Predict(&history->working, delta, imu->dt_s * fraction) != 0U) ?
        NAV_REPLAY_OK : NAV_REPLAY_NUMERIC_ERROR;
}

static NavigationReplayResult NavigationReplay_IntervalApply(
    NavigationReplayContext *history, const NavigationReplayImu *imu,
    uint64_t *cursor, uint64_t end, uint16_t *event_index,
    uint16_t inserted, NavigationReplayOutcome *outcome)
{
    uint16_t guard;
    NavigationReplayOutcome ignored;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(*event_index <= history->event_count, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (guard = 0U; guard < NAV_REPLAY_EVENT_CAPACITY; guard++)
    {
        if (!(((*event_index) < history->event_count) &&
               (NavigationReplay_EventTimeGet(history, (*event_index)) < end ||
                ((imu == NULL) && (NavigationReplay_EventTimeGet(history, (*event_index)) == end))))) { break; }

        const NavigationReplayEvent *event = NavigationReplay_EventGet(history, (*event_index));
        NavigationReplayResult result;
        if (event->measurement_timestamp_us > (*cursor))
        {
            if (imu == NULL) { return NAV_REPLAY_DISCONTINUITY; }
            result = NavigationReplay_SegmentPredict(history, imu, (*cursor),
                event->measurement_timestamp_us);
            if (result != NAV_REPLAY_OK) { return result; }
            (*cursor) = event->measurement_timestamp_us;
        }
        if (++history->diagnostics.last_steps > NAV_REPLAY_MAX_STEPS)
        { return NAV_REPLAY_WORK_LIMIT; }
        result = NavigationReplay_EventApply(history, &history->working, event,
            ((*event_index) == inserted) ? outcome : &ignored);
        if (result != NAV_REPLAY_OK) { return result; }
        (*event_index)++;
    }
    SILVERSTAR_ASSERT(!(((*event_index) < history->event_count) &&
               (NavigationReplay_EventTimeGet(history, (*event_index)) < end ||
                ((imu == NULL) && (NavigationReplay_EventTimeGet(history, (*event_index)) == end)))), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    return NAV_REPLAY_OK;
}

static uint16_t NavigationReplay_FirstEventFind(
    const NavigationReplayContext *history, uint64_t cursor)
{
    uint16_t index;
    for (index = 0U; index < NAV_REPLAY_EVENT_CAPACITY; index++)
    {
        if ((index >= history->event_count) ||
            (NavigationReplay_EventTimeGet(history, index) >= cursor))
        { break; }
    }
    SILVERSTAR_ASSERT((index >= history->event_count) || (NavigationReplay_EventTimeGet(history, index) >= cursor), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    return index;
}

static NavigationReplayResult NavigationReplay_Rebuild(
    NavigationReplayContext *history, uint8_t checkpoint, uint16_t inserted,
    NavigationReplayOutcome *outcome)
{
    uint16_t event_index = 0U;
    uint16_t imu_index;
    uint8_t next_checkpoint = (uint8_t)(checkpoint + 1U);
    uint64_t cursor;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(checkpoint < history->checkpoint_count, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(history->imu_count <= NAV_REPLAY_IMU_CAPACITY,
                      SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    cursor = history->storage->checkpoints[checkpoint].timestamp_us;
    history->working = history->storage->checkpoints[checkpoint].state;
    event_index = NavigationReplay_FirstEventFind(history, cursor);
    for (imu_index = 0U; imu_index <= history->imu_count; imu_index++)
    {
        const NavigationReplayImu *imu = (imu_index < history->imu_count) ?
            &history->storage->imu[(history->imu_head + imu_index) % NAV_REPLAY_IMU_CAPACITY] : NULL;
        uint64_t end = (imu != NULL) ? imu->end_us : history->present_us;
        if ((imu != NULL) && (end <= cursor)) { continue; }
        NavigationReplayResult result = NavigationReplay_IntervalApply(
            history, imu, &cursor, end, &event_index, inserted, outcome);
        if (result != NAV_REPLAY_OK) { return result; }
        if ((imu != NULL) && (end > cursor))
        {
            result = NavigationReplay_SegmentPredict(history, imu, cursor, end);
            if (result != NAV_REPLAY_OK) { return result; }
            cursor = end;
            if ((next_checkpoint < history->checkpoint_count) &&
                (history->storage->checkpoints[next_checkpoint].timestamp_us == cursor))
            {
                history->storage->checkpoints[next_checkpoint].state = history->working;
                next_checkpoint++;
            }
        }
    }
    return NAV_REPLAY_OK;
}

static uint8_t NavigationReplay_InsertInputValid(
    const NavigationReplayContext *history, const NavigationKfContext *state,
    const NavigationReplayEvent *event, const NavigationReplayOutcome *outcome)
{
    if ((history == NULL) || (state == NULL) || (event == NULL) || (outcome == NULL) ||
        (history->faulted != 0U) || (history->checkpoint_count == 0U) ||
        (NavigationReplay_EventValid(history, event) == 0U) ||
        (event->measurement_timestamp_us > history->present_us))
    { return 0U; }
    return 1U;
}

static NavigationReplayResult NavigationReplay_InsertValidate(
    NavigationReplayContext *history, const NavigationKfContext *state,
    const NavigationReplayEvent *event)
{
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    history->diagnostics.last_steps = 0U;
    if ((event->epoch != history->epoch) || (NavigationReplay_ModelMatches(history, state) == 0U))
    { return NavigationReplay_Reject(history, NAV_REPLAY_EPOCH_MISMATCH); }
    uint64_t age = history->present_us - event->measurement_timestamp_us;
    if ((age > NAV_REPLAY_WINDOW_US) ||
        (event->measurement_timestamp_us < history->epoch_start_us) ||
        (event->receive_timestamp_us < history->epoch_start_us) ||
        (event->measurement_timestamp_us < history->storage->checkpoints[0].timestamp_us))
    { return NavigationReplay_Reject(history, NAV_REPLAY_HISTORY_MISS); }
    if (history->event_count >= NAV_REPLAY_EVENT_CAPACITY)
    { return NavigationReplay_Reject(history, NAV_REPLAY_OVERFLOW); }
    return NAV_REPLAY_OK;
}

static uint16_t NavigationReplay_EventIndexFind(
    NavigationReplayContext *history, const NavigationReplayEvent *event)
{
    uint16_t index;
    for (index = 0U; index < NAV_REPLAY_EVENT_CAPACITY; index++)
    {
        if ((index >= history->event_count) ||
            !NavigationReplay_EventBefore(NavigationReplay_EventGet(history, index), event))
        { break; }
    }
    SILVERSTAR_ASSERT((index >= history->event_count) || !NavigationReplay_EventBefore(NavigationReplay_EventGet(history, index), event), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    return index;
}

static NavigationReplayResult NavigationReplay_EventCommit(
    NavigationReplayContext *history, const NavigationReplayEvent *event, uint16_t index)
{
    uint16_t slot;
    if ((index < history->event_count) && !NavigationReplay_EventBefore(event, NavigationReplay_EventGet(history, index)))
    { return NavigationReplay_Reject(history, NAV_REPLAY_INVALID); }
    slot = NavigationReplay_EventStore(history, event);
    if (slot == UINT16_MAX)
    { return NavigationReplay_Reject(history, NAV_REPLAY_OVERFLOW); }
    (void)memmove(&history->event_order[index + 1U], &history->event_order[index],
                  (history->event_count - index) * sizeof(history->event_order[0]));
    history->event_order[index] = slot;
    history->event_count++;
    if (history->event_count > history->diagnostics.event_high_water)
    { history->diagnostics.event_high_water = history->event_count; }
    return NAV_REPLAY_OK;
}

static uint8_t NavigationReplay_CheckpointFind(
    const NavigationReplayContext *history, uint64_t timestamp_us)
{
    uint8_t checkpoint = 0U;
    uint8_t guard;
    for (guard = 0U; guard < NAV_REPLAY_CHECKPOINT_CAPACITY; guard++)
    {
        if ((checkpoint + 1U >= history->checkpoint_count) ||
            (history->storage->checkpoints[checkpoint + 1U].timestamp_us > timestamp_us))
        { break; }
        checkpoint++;
    }
    SILVERSTAR_ASSERT((checkpoint + 1U >= history->checkpoint_count) || (history->storage->checkpoints[checkpoint + 1U].timestamp_us > timestamp_us), SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    return checkpoint;
}

static NavigationReplayResult NavigationReplay_ApplyFailure(
    NavigationReplayContext *history, NavigationReplayOutcome *outcome,
    NavigationReplayResult result)
{
    /* Partial checkpoints must never be reused; current state is uncommitted. */
    history->faulted = 1U;
    NavigationReplay_OutcomeReset(outcome);
    if (result == NAV_REPLAY_NUMERIC_ERROR)
    {
        outcome->position = NAV_KF_UPDATE_NUMERIC_ERROR;
        outcome->velocity = NAV_KF_UPDATE_NUMERIC_ERROR;
        outcome->barometer = NAV_KF_UPDATE_NUMERIC_ERROR;
    }
    return NavigationReplay_Reject(history, result);
}

static NavigationReplayResult NavigationReplay_InsertedApply(
    NavigationReplayContext *history, NavigationKfContext *state,
    const NavigationReplayEvent *event, uint16_t index,
    NavigationReplayOutcome *outcome)
{
    uint64_t age = history->present_us - event->measurement_timestamp_us;
    NavigationReplayResult result;
    SILVERSTAR_ASSERT_OBJECT(history, NavigationReplayContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(index < history->event_count, SILVERSTAR_ASSERT_MODULE_ALGORITHM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((age == 0U) && (index == history->event_count - 1U))
    {
        /* Original current-state fast path, retaining the historical event. */
        history->working = *state;
        result = NavigationReplay_EventApply(history, &history->working, event, outcome);
    }
    else
    {
        uint8_t checkpoint = NavigationReplay_CheckpointFind(history, event->measurement_timestamp_us);
        history->diagnostics.replay_count++;
        if (age > history->diagnostics.max_rewind_age_us)
        { history->diagnostics.max_rewind_age_us = (uint32_t)age; }
        result = NavigationReplay_Rebuild(history, checkpoint, index, outcome);
    }
    if (result != NAV_REPLAY_OK)
    { return NavigationReplay_ApplyFailure(history, outcome, result); }
    *state = history->working;
    if (history->diagnostics.last_steps > history->diagnostics.max_steps)
    { history->diagnostics.max_steps = history->diagnostics.last_steps; }
    history->diagnostics.last_result = result;
    return result;
}

NavigationReplayResult NavigationReplay_Insert(
    NavigationReplayContext *history, NavigationKfContext *state,
    const NavigationReplayEvent *event, NavigationReplayOutcome *outcome)
{
    uint16_t index;
    NavigationReplayResult result;
    if (outcome != NULL) { NavigationReplay_OutcomeReset(outcome); }
    if (NavigationReplay_InsertInputValid(history, state, event, outcome) == 0U)
    { return NavigationReplay_Reject(history, NAV_REPLAY_INVALID); }
    result = NavigationReplay_InsertValidate(history, state, event);
    if (result != NAV_REPLAY_OK) { return result; }
    index = NavigationReplay_EventIndexFind(history, event);
    result = NavigationReplay_EventCommit(history, event, index);
    if (result != NAV_REPLAY_OK) { return result; }
    return NavigationReplay_InsertedApply(history, state, event, index, outcome);
}

void NavigationReplay_RuntimeRecord(NavigationReplayContext *history,
                                    uint64_t elapsed_us)
{
    if (history == NULL) { return; }
    history->diagnostics.last_runtime_us = (elapsed_us > UINT32_MAX) ? UINT32_MAX : (uint32_t)elapsed_us;
    if (history->diagnostics.last_runtime_us > history->diagnostics.max_runtime_us)
    { history->diagnostics.max_runtime_us = history->diagnostics.last_runtime_us; }
}
