#include "ins_mechanization.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "attitude_frame.h"
#include "silverstar_assert.h"
#include "system_user_config.h"

#define INS_MECHANIZATION_DT_MIN_S \
    ((1.0f / (float)SYSTEM_MECHANIZATION_SAMPLE_RATE_MAX_HZ) * \
     (1.0f - SYSTEM_MECHANIZATION_DT_TOLERANCE_RATIO))
#define INS_MECHANIZATION_DT_MAX_S \
    ((1.0f / (float)SYSTEM_MECHANIZATION_SAMPLE_RATE_MIN_HZ) * \
     (1.0f + SYSTEM_MECHANIZATION_DT_TOLERANCE_RATIO))

typedef enum
{
    INS_SAMPLE_PREPARE_REJECTED = 0,
    INS_SAMPLE_PREPARE_WAITING,
    INS_SAMPLE_PREPARE_READY
} InsSamplePrepareResult;

typedef struct
{
    InsAlgorithmSample current_sample;
    float delta_theta_1[3];
    float delta_theta_2[3];
    float delta_velocity_1[3];
    float delta_velocity_2[3];
    float delta_theta_sum[3];
    float delta_velocity_sum[3];
    float previous_velocity[3];
    float current_velocity[3];
    float current_position[3];
    float q_nb_start[4];
    float q_nb_end[4];
    float total_dt;
} InsMechanizationWork;

static void Ins_VectorCross(const float a[3], const float b[3], float out[3])
{
    out[0] = (a[1] * b[2]) - (a[2] * b[1]);
    out[1] = (a[2] * b[0]) - (a[0] * b[2]);
    out[2] = (a[0] * b[1]) - (a[1] * b[0]);
}

static uint8_t Ins_SampleDtValid(float dt_s)
{
    return ((dt_s >= INS_MECHANIZATION_DT_MIN_S) &&
            (dt_s <= INS_MECHANIZATION_DT_MAX_S)) ? 1U : 0U;
}

static void Ins_StateCopyNavigation(const InsMechanizationContext *context,
                                    InsState *state)
{
    memcpy(state->velocity_n_mps,
           context->velocity_n_mps,
           sizeof(state->velocity_n_mps));
    memcpy(state->position_n_m,
           context->position_n_m,
           sizeof(state->position_n_m));
    if (context->q_nb_propagated_valid != 0U)
    {
        memcpy(state->q_nb,
               context->q_nb_propagated,
               sizeof(state->q_nb));
    }
    state->update_count = context->update_count;
    state->health_flags = context->health_flags;
}

void InsMechanization_Init(InsMechanizationContext *context,
                           float gravity_mps2)
{
    if (context == NULL)
    {
        return;
    }

    memset(context, 0, sizeof(*context));
    context->gravity_mps2 = gravity_mps2;
}

void InsMechanization_ResetNavigation(InsMechanizationContext *context)
{
    if (context == NULL)
    {
        return;
    }

    InsInertial_Reset(&context->inertial);
    memset(context->velocity_n_mps, 0, sizeof(context->velocity_n_mps));
    memset(context->position_n_m, 0, sizeof(context->position_n_m));
    memset(context->q_nb_propagated, 0, sizeof(context->q_nb_propagated));
    context->update_count = 0U;
    context->health_flags = INS_HEALTH_NONE;
    context->q_nb_propagated_valid = 0U;
}

uint8_t InsMechanization_ResetNavigationWithAttitude(
    InsMechanizationContext *context,
    const float initial_q_nb[4])
{
    float normalized_q_nb[4];

    if ((context == NULL) || (initial_q_nb == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, InsMechanizationContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(initial_q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    memcpy(normalized_q_nb, initial_q_nb, sizeof(normalized_q_nb));
    InsMechanization_ResetNavigation(context);
    if (Attitude_QuaternionNormalize(normalized_q_nb) == 0U)
    {
        return 0U;
    }

    memcpy(context->q_nb_propagated,
           normalized_q_nb,
           sizeof(context->q_nb_propagated));
    context->q_nb_propagated_valid = 1U;
    return 1U;
}

void Ins_ComputeSubIntervalIncrement(const InsAlgorithmSample *previous,
                                     const InsAlgorithmSample *current,
                                     float delta_theta_b[3],
                                     float delta_velocity_b[3],
                                     float *dt_s)
{
    float dt = 0.0f;
    uint8_t i;

    if ((previous == NULL) || (current == NULL) ||
        (delta_theta_b == NULL) || (delta_velocity_b == NULL) ||
        (dt_s == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(previous, InsAlgorithmSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(current, InsAlgorithmSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    if (current->timestamp_us > previous->timestamp_us)
    {
        dt = (float)(current->timestamp_us - previous->timestamp_us) * 1.0e-6f;
    }

    for (i = 0U; i < 3U; i++)
    {
        delta_theta_b[i] = 0.5f *
                           (previous->gyro_b_radps[i] + current->gyro_b_radps[i]) * dt;
        delta_velocity_b[i] = 0.5f *
                              (previous->accel_b_mps2[i] + current->accel_b_mps2[i]) * dt;
    }
    *dt_s = dt;
}

void Ins_ComputeSecondOrderConing(const float delta_theta_1[3],
                                  const float delta_theta_2[3],
                                  float corrected[3])
{
    float coning_cross[3];
    uint8_t i;

    if ((delta_theta_1 == NULL) || (delta_theta_2 == NULL) ||
        (corrected == NULL))
    {
        return;
    }

    Ins_VectorCross(delta_theta_1, delta_theta_2, coning_cross);
    for (i = 0U; i < 3U; i++)
    {
        corrected[i] = delta_theta_1[i] + delta_theta_2[i] +
                       ((2.0f / 3.0f) * coning_cross[i]);
    }
}

void Ins_ComputeSecondOrderSculling(const float delta_theta_1[3],
                                    const float delta_velocity_1[3],
                                    const float delta_theta_2[3],
                                    const float delta_velocity_2[3],
                                    float delta_velocity_corrected_b[3])
{
    float delta_theta_sum[3];
    float delta_velocity_sum[3];
    float rotation_cross[3];
    float sculling_cross_1[3];
    float sculling_cross_2[3];
    uint8_t i;

    if ((delta_theta_1 == NULL) || (delta_velocity_1 == NULL) ||
        (delta_theta_2 == NULL) || (delta_velocity_2 == NULL) ||
        (delta_velocity_corrected_b == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(delta_theta_1, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(delta_velocity_corrected_b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);

    for (i = 0U; i < 3U; i++)
    {
        delta_theta_sum[i] = delta_theta_1[i] + delta_theta_2[i];
        delta_velocity_sum[i] = delta_velocity_1[i] + delta_velocity_2[i];
    }

    Ins_VectorCross(delta_theta_sum, delta_velocity_sum, rotation_cross);
    Ins_VectorCross(delta_theta_1, delta_velocity_2, sculling_cross_1);
    Ins_VectorCross(delta_velocity_1, delta_theta_2, sculling_cross_2);

    for (i = 0U; i < 3U; i++)
    {
        delta_velocity_corrected_b[i] = delta_velocity_sum[i] +
                                        (0.5f * rotation_cross[i]) +
                                        ((2.0f / 3.0f) *
                                         (sculling_cross_1[i] + sculling_cross_2[i]));
    }
}

void Ins_TransformDeltaVelocityToNavigation(const float q_nb_start[4],
                                             const float delta_velocity_b[3],
                                             float total_dt_s,
                                             float gravity_mps2,
                                             float delta_velocity_n[3])
{
    float rotated_delta_velocity[3];

    if ((q_nb_start == NULL) || (delta_velocity_b == NULL) ||
        (delta_velocity_n == NULL) || (!isfinite(gravity_mps2)) ||
        (gravity_mps2 <= 0.0f))
    {
        return;
    }

    Attitude_RotateVector(q_nb_start, delta_velocity_b, rotated_delta_velocity);
    delta_velocity_n[0] = rotated_delta_velocity[0];
    delta_velocity_n[1] = rotated_delta_velocity[1];
    delta_velocity_n[2] = rotated_delta_velocity[2] -
                          (gravity_mps2 * total_dt_s);
}

void Ins_IntegrateVelocity(const float previous_velocity_n[3],
                           const float delta_velocity_n[3],
                           float current_velocity_n[3])
{
    uint8_t i;

    if ((previous_velocity_n == NULL) || (delta_velocity_n == NULL) ||
        (current_velocity_n == NULL))
    {
        return;
    }

    for (i = 0U; i < 3U; i++)
    {
        current_velocity_n[i] = previous_velocity_n[i] + delta_velocity_n[i];
    }
}

void Ins_IntegratePositionTrapezoidal(const float previous_position_n[3],
                                      const float previous_velocity_n[3],
                                      const float current_velocity_n[3],
                                      float dt_s,
                                      float current_position_n[3])
{
    uint8_t i;

    if ((previous_position_n == NULL) || (previous_velocity_n == NULL) ||
        (current_velocity_n == NULL) || (current_position_n == NULL))
    {
        return;
    }

    for (i = 0U; i < 3U; i++)
    {
        current_position_n[i] = previous_position_n[i] +
                                (0.5f *
                                 (previous_velocity_n[i] + current_velocity_n[i]) * dt_s);
    }
}

static InsSamplePrepareResult InsMechanization_SamplePrepare(
    InsInertialContext *context,
    const InsAlgorithmSample *sample,
    InsState *state,
    InsMechanizationWork *work)
{
    SILVERSTAR_ASSERT_OBJECT(context, InsInertialContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, InsAlgorithmSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, InsState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, InsMechanizationWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(state, 0, sizeof(*state));
    if ((sample->valid_flags &
         (INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO)) !=
        (INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO))
    {
        context->health_flags |= INS_HEALTH_INVALID_SAMPLE;
        state->health_flags = context->health_flags;
        return INS_SAMPLE_PREPARE_REJECTED;
    }
    work->current_sample = *sample;
    if (context->sample_count == 0U)
    {
        context->sample_history[0] = work->current_sample;
        context->sample_count = 1U;
        return INS_SAMPLE_PREPARE_WAITING;
    }
    if (context->sample_count == 1U)
    {
        context->sample_history[1] = work->current_sample;
        context->sample_count = 2U;
        return INS_SAMPLE_PREPARE_WAITING;
    }
    return INS_SAMPLE_PREPARE_READY;
}

static uint8_t InsMechanization_IncrementsPrepare(
    InsInertialContext *context,
    InsState *state,
    InsMechanizationWork *work)
{
    float dt_1;
    float dt_2;

    SILVERSTAR_ASSERT_OBJECT(context, InsInertialContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, InsMechanizationWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    Ins_ComputeSubIntervalIncrement(
        &context->sample_history[0], &context->sample_history[1],
        work->delta_theta_1, work->delta_velocity_1, &dt_1);
    Ins_ComputeSubIntervalIncrement(
        &context->sample_history[1], &work->current_sample,
        work->delta_theta_2, work->delta_velocity_2, &dt_2);
    if ((Ins_SampleDtValid(dt_1) == 0U) || (Ins_SampleDtValid(dt_2) == 0U))
    {
        context->health_flags |= INS_HEALTH_SAMPLE_GAP;
        context->sample_history[0] = work->current_sample;
        context->sample_count = 1U;
        state->timestamp_us = work->current_sample.timestamp_us;
        state->health_flags = context->health_flags;
        return 0U;
    }
    work->total_dt = dt_1 + dt_2;
    return 1U;
}

static void InsMechanization_CorrectionsCompute(
    InsMechanizationWork *work,
    InsState *state)
{
    float rotation_cross[3];
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(work, InsMechanizationWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, InsState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < 3U; index++)
    {
        work->delta_theta_sum[index] =
            work->delta_theta_1[index] + work->delta_theta_2[index];
        work->delta_velocity_sum[index] =
            work->delta_velocity_1[index] + work->delta_velocity_2[index];
    }
    Ins_VectorCross(work->delta_theta_sum,
                    work->delta_velocity_sum, rotation_cross);
    Ins_ComputeSecondOrderConing(
        work->delta_theta_1, work->delta_theta_2,
        state->delta_theta_b_coning_corrected);
    Ins_ComputeSecondOrderSculling(
        work->delta_theta_1, work->delta_velocity_1,
        work->delta_theta_2, work->delta_velocity_2,
        state->delta_velocity_b_sculling_corrected);
    for (index = 0U; index < 3U; index++)
    {
        state->delta_theta_b[index] = work->delta_theta_sum[index];
        state->delta_velocity_b[index] = work->delta_velocity_sum[index];
        state->delta_velocity_b_rotation_corrected[index] =
            work->delta_velocity_sum[index] + (0.5f * rotation_cross[index]);
    }
}

static uint8_t InsMechanization_NavigationCompute(
    InsMechanizationContext *context,
    InsMechanizationWork *work,
    InsState *state)
{
    SILVERSTAR_ASSERT_OBJECT(context, InsMechanizationContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(work, InsMechanizationWork,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memcpy(work->q_nb_start, context->q_nb_propagated,
                 sizeof(work->q_nb_start));
    Ins_TransformDeltaVelocityToNavigation(
        work->q_nb_start, state->delta_velocity_b, work->total_dt,
        context->gravity_mps2, state->delta_velocity_n_basic);
    Ins_TransformDeltaVelocityToNavigation(
        work->q_nb_start, state->delta_velocity_b_sculling_corrected,
        work->total_dt, context->gravity_mps2,
        state->delta_velocity_n_corrected);
    (void)memcpy(work->previous_velocity, context->velocity_n_mps,
                 sizeof(work->previous_velocity));
    Ins_IntegrateVelocity(work->previous_velocity,
                          state->delta_velocity_n_corrected,
                          work->current_velocity);
    Ins_IntegratePositionTrapezoidal(
        context->position_n_m, work->previous_velocity,
        work->current_velocity, work->total_dt, work->current_position);
    if (Attitude_PropagateQuaternionBodyIncrement(
            work->q_nb_start, state->delta_theta_b_coning_corrected,
            work->q_nb_end) == 0U)
    {
        context->health_flags |= INS_HEALTH_INVALID_QUATERNION;
        state->health_flags = context->health_flags;
        return 0U;
    }
    (void)memcpy(context->velocity_n_mps, work->current_velocity,
                 sizeof(work->current_velocity));
    (void)memcpy(context->position_n_m, work->current_position,
                 sizeof(work->current_position));
    (void)memcpy(context->q_nb_propagated, work->q_nb_end,
                 sizeof(context->q_nb_propagated));
    context->update_count++;
    return 1U;
}

static void InsMechanization_StatePublish(
    InsMechanizationContext *context,
    const InsMechanizationWork *work,
    InsState *state)
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, InsMechanizationContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, InsState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    state->timestamp_us = work->current_sample.timestamp_us;
    state->dt_s = work->total_dt;
    state->update_count = context->update_count;
    state->health_flags = context->health_flags;
    state->valid = 1U;
    (void)memcpy(state->q_nb, work->q_nb_end, sizeof(state->q_nb));
    for (index = 0U; index < 3U; index++)
    {
        state->accel_n_mps2[index] =
            state->delta_velocity_n_corrected[index] / work->total_dt;
        state->velocity_n_mps[index] = work->current_velocity[index];
        state->position_n_m[index] = work->current_position[index];
    }
}

void InsInertial_Reset(InsInertialContext *context)
{
    if (context == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(context, InsInertialContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(context, 0, sizeof(*context));
}

InsInertialUpdateResult InsInertial_Update(InsInertialContext *context,
    const InsAlgorithmSample *sample, InsState *state)
{
    InsMechanizationWork work;
    InsSamplePrepareResult prepare_result;

    if ((context == NULL) || (sample == NULL) || (state == NULL))
    {
        return INS_INERTIAL_UPDATE_INVALID;
    }
    SILVERSTAR_ASSERT_OBJECT(context, InsInertialContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, InsState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    prepare_result = InsMechanization_SamplePrepare(context, sample, state, &work);
    if (prepare_result != INS_SAMPLE_PREPARE_READY)
    {
        return (prepare_result == INS_SAMPLE_PREPARE_WAITING) ?
            INS_INERTIAL_UPDATE_WAITING : INS_INERTIAL_UPDATE_INVALID;
    }
    if (InsMechanization_IncrementsPrepare(context, state, &work) == 0U)
    {
        return INS_INERTIAL_UPDATE_INVALID;
    }
    InsMechanization_CorrectionsCompute(&work, state);
    state->interval_start_timestamp_us = context->sample_history[0].timestamp_us;
    state->timestamp_us = sample->timestamp_us;
    state->dt_s = work.total_dt;
    state->update_count = ++context->update_count;
    state->health_flags = context->health_flags;
    state->valid = 1U;
    context->sample_history[0] = *sample;
    context->sample_count = 1U;
    return INS_INERTIAL_UPDATE_READY;
}

uint8_t InsMechanization_Update(InsMechanizationContext *context,
                                const InsAlgorithmSample *sample,
                                InsState *state)
{
    InsMechanizationWork work;

    if ((context == NULL) || (sample == NULL) || (state == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, InsMechanizationContext,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(state, InsState,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->q_nb_propagated_valid == 0U)
    {
        context->health_flags |= INS_HEALTH_INVALID_QUATERNION;
        (void)memset(state, 0, sizeof(*state));
        Ins_StateCopyNavigation(context, state);
        return 0U;
    }
    if (InsInertial_Update(&context->inertial, sample, state) !=
        INS_INERTIAL_UPDATE_READY)
    {
        context->health_flags |= state->health_flags;
        Ins_StateCopyNavigation(context, state);
        return 0U;
    }
    context->health_flags |= state->health_flags;
    work.current_sample = *sample;
    work.total_dt = state->dt_s;
    if (InsMechanization_NavigationCompute(context, &work, state) == 0U)
    {
        state->valid = 0U;
        return 0U;
    }
    InsMechanization_StatePublish(context, &work, state);
    return 1U;
}
