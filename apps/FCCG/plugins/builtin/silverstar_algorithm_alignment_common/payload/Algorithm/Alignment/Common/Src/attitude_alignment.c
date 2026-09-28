#include "attitude_alignment.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "attitude_frame.h"
#include "silverstar_assert.h"

#define ATTITUDE_ALIGNMENT_VECTOR_NORM_MIN 1.0e-6f
#define ATTITUDE_ALIGNMENT_DEG_TO_RAD 0.01745329251994329577f
#define ATTITUDE_ALIGNMENT_PI 3.14159265358979323846f
#define ATTITUDE_ALIGNMENT_TWO_PI 6.28318530717958647692f

typedef struct
{
    float quaternion_wxyz[4];
    uint8_t quaternion_present;
} AttitudeAlignmentSample;

static float AttitudeAlignment_VectorDot(const float lhs[3],
                                         const float rhs[3])
{
    return (lhs[0] * rhs[0]) + (lhs[1] * rhs[1]) + (lhs[2] * rhs[2]);
}

static float AttitudeAlignment_VectorNorm(const float vector[3])
{
    return sqrtf(AttitudeAlignment_VectorDot(vector, vector));
}

static uint8_t AttitudeAlignment_VectorFinite(const float vector[3])
{
    return (uint8_t)(isfinite(vector[0]) && isfinite(vector[1]) &&
                     isfinite(vector[2]));
}

static uint8_t AttitudeAlignment_QuaternionFinite(const float q[4])
{
    return (uint8_t)(isfinite(q[0]) && isfinite(q[1]) &&
                     isfinite(q[2]) && isfinite(q[3]));
}

static float AttitudeAlignment_YawDeltaResolve(float current_yaw_rad,
                                                float target_yaw_rad)
{
    float delta_yaw_rad = remainderf(target_yaw_rad - current_yaw_rad,
                                     ATTITUDE_ALIGNMENT_TWO_PI);

    if (delta_yaw_rad > ATTITUDE_ALIGNMENT_PI)
    {
        delta_yaw_rad -= ATTITUDE_ALIGNMENT_TWO_PI;
    }
    else if (delta_yaw_rad < -ATTITUDE_ALIGNMENT_PI)
    {
        delta_yaw_rad += ATTITUDE_ALIGNMENT_TWO_PI;
    }
    return delta_yaw_rad;
}

static uint8_t AttitudeAlignment_Reject(AttitudeAlignmentWindow *context)
{
    uint32_t reject_count;

    if (context == NULL)
    {
        return 0U;
    }
    reject_count = context->reject_count + 1U;
    (void)memset(context, 0, sizeof(*context));
    context->reject_count = reject_count;
    return 0U;
}

static uint8_t AttitudeAlignment_ConfigValid(
    const AttitudeAlignmentWindowConfig *config)
{
    return (uint8_t)((config != NULL) &&
        (config->minimum_samples != 0U) &&
        (config->maximum_samples >= config->minimum_samples) &&
        (config->maximum_samples <= ATTITUDE_ALIGNMENT_WINDOW_CAPACITY) &&
        isfinite(config->gravity_mps2) && (config->gravity_mps2 > 0.0f) &&
        isfinite(config->acceleration_tolerance_mps2) &&
        (config->acceleration_tolerance_mps2 > 0.0f) &&
        isfinite(config->maximum_gyro_radps) &&
        (config->maximum_gyro_radps > 0.0f));
}

void AttitudeAlignmentWindow_Init(AttitudeAlignmentWindow *context)
{
    if (context != NULL)
    {
        (void)memset(context, 0, sizeof(*context));
    }
}

void AttitudeAlignmentWindow_Reset(AttitudeAlignmentWindow *context)
{
    AttitudeAlignmentWindow_Init(context);
}

static uint8_t AttitudeAlignmentWindow_SamplePrepare(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    const float quaternion_wxyz[4],
    AttitudeAlignmentSample *sample)
{
    float acceleration_norm;
    float gyro_norm;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudeAlignmentSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(sample, 0, sizeof(*sample));
    sample->quaternion_present = (quaternion_wxyz != NULL) ? 1U : 0U;
    if ((AttitudeAlignment_VectorFinite(acceleration_b_mps2) == 0U) ||
        (AttitudeAlignment_VectorFinite(gyro_b_radps) == 0U))
    {
        return AttitudeAlignment_Reject(context);
    }
    acceleration_norm = AttitudeAlignment_VectorNorm(acceleration_b_mps2);
    gyro_norm = AttitudeAlignment_VectorNorm(gyro_b_radps);
    if ((!isfinite(acceleration_norm)) || (!isfinite(gyro_norm)) ||
        (fabsf(acceleration_norm - config->gravity_mps2) >
         config->acceleration_tolerance_mps2) ||
        (gyro_norm > config->maximum_gyro_radps))
    {
        return AttitudeAlignment_Reject(context);
    }
    if (sample->quaternion_present != 0U)
    {
        if ((AttitudeAlignment_QuaternionFinite(quaternion_wxyz) == 0U) ||
            (!isfinite(config->maximum_quaternion_deviation_rad)) ||
            (config->maximum_quaternion_deviation_rad <= 0.0f))
        {
            return AttitudeAlignment_Reject(context);
        }
        (void)memcpy(sample->quaternion_wxyz, quaternion_wxyz,
                     sizeof(sample->quaternion_wxyz));
        if (Attitude_QuaternionNormalize(sample->quaternion_wxyz) == 0U)
        {
            return AttitudeAlignment_Reject(context);
        }
    }
    return 1U;
}

static uint8_t AttitudeAlignmentWindow_ContinuityCheck(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    uint64_t timestamp_us,
    AttitudeAlignmentSample *sample)
{
    float dot;
    float minimum_dot;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudeAlignmentSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->sample_count != 0U)
    {
        if ((timestamp_us <= context->last_timestamp_us) ||
            ((config->maximum_gap_us != 0U) &&
             ((timestamp_us - context->last_timestamp_us) >
              config->maximum_gap_us)) ||
            ((sample->quaternion_present != 0U) !=
             (context->quaternion_sample_count != 0U)))
        {
            return AttitudeAlignment_Reject(context);
        }
        if (sample->quaternion_present != 0U)
        {
            dot = Attitude_QuaternionDot(
                context->quaternion_reference_wxyz,
                sample->quaternion_wxyz);
            if (dot < 0.0f)
            {
                dot = -dot;
                for (index = 0U; index < 4U; index++)
                {
                    sample->quaternion_wxyz[index] =
                        -sample->quaternion_wxyz[index];
                }
            }
            minimum_dot = cosf(0.5f *
                config->maximum_quaternion_deviation_rad);
            if ((!isfinite(dot)) || (dot < minimum_dot))
            {
                return AttitudeAlignment_Reject(context);
            }
        }
    }
    else
    {
        context->first_timestamp_us = timestamp_us;
        if (sample->quaternion_present != 0U)
        {
            (void)memcpy(context->quaternion_reference_wxyz,
                         sample->quaternion_wxyz,
                         sizeof(context->quaternion_reference_wxyz));
        }
    }
    return 1U;
}

static void AttitudeAlignmentWindow_SlotPrepare(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    const AttitudeAlignmentSample *sample,
    uint16_t *write_index)
{
    uint16_t slot;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(write_index, uint16_t,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    slot = context->head;
    *write_index = slot;
    if (context->sample_count >= config->maximum_samples)
    {
        for (index = 0U; index < 4U; index++)
        {
            context->quaternion_sum_wxyz[index] -=
                context->quaternion_samples_wxyz[slot][index];
        }
        for (index = 0U; index < 3U; index++)
        {
            context->acceleration_sum_b_mps2[index] -=
                context->acceleration_samples_b_mps2[slot][index];
            context->gyro_sum_b_radps[index] -=
                context->gyro_samples_b_radps[slot][index];
        }
    }
    else
    {
        context->sample_count++;
        if (sample->quaternion_present != 0U)
        {
            context->quaternion_sample_count++;
        }
    }
}

static void AttitudeAlignmentWindow_SampleStore(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    const AttitudeAlignmentSample *sample,
    uint16_t write_index,
    uint64_t timestamp_us,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3])
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudeAlignmentSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memcpy(context->quaternion_samples_wxyz[write_index],
                 sample->quaternion_wxyz,
                 sizeof(context->quaternion_samples_wxyz[write_index]));
    (void)memcpy(context->acceleration_samples_b_mps2[write_index],
                 acceleration_b_mps2,
                 sizeof(context->acceleration_samples_b_mps2[write_index]));
    (void)memcpy(context->gyro_samples_b_radps[write_index],
                 gyro_b_radps,
                 sizeof(context->gyro_samples_b_radps[write_index]));
    context->timestamp_samples_us[write_index] = timestamp_us;
    context->head = (uint16_t)((context->head + 1U) %
                               config->maximum_samples);
    for (index = 0U; index < 4U; index++)
    {
        context->quaternion_sum_wxyz[index] += sample->quaternion_wxyz[index];
    }
    for (index = 0U; index < 3U; index++)
    {
        context->acceleration_sum_b_mps2[index] += acceleration_b_mps2[index];
        context->gyro_sum_b_radps[index] += gyro_b_radps[index];
    }
    context->last_timestamp_us = timestamp_us;
}

static void AttitudeAlignmentWindow_StatusUpdate(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    const AttitudeAlignmentSample *sample)
{
    uint16_t oldest_index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(config, AttitudeAlignmentWindowConfig,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    oldest_index = (uint16_t)((context->head + config->maximum_samples -
                              context->sample_count) %
                             config->maximum_samples);
    context->first_timestamp_us =
        context->timestamp_samples_us[oldest_index];
    if (sample->quaternion_present != 0U)
    {
        (void)memcpy(context->quaternion_reference_wxyz,
                     context->quaternion_samples_wxyz[oldest_index],
                     sizeof(context->quaternion_reference_wxyz));
    }
    context->valid = (uint8_t)(
        (context->sample_count >= config->minimum_samples) &&
        ((context->last_timestamp_us - context->first_timestamp_us) >=
         config->minimum_duration_us));
}

static uint8_t AttitudeAlignmentWindow_SampleAdd(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    uint64_t timestamp_us,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    const float quaternion_wxyz[4])
{
    AttitudeAlignmentSample sample;
    uint16_t write_index;

    if ((context == NULL) ||
        (AttitudeAlignment_ConfigValid(config) == 0U) ||
        (acceleration_b_mps2 == NULL) || (gyro_b_radps == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (AttitudeAlignmentWindow_SamplePrepare(
            context, config, acceleration_b_mps2, gyro_b_radps,
            quaternion_wxyz, &sample) == 0U)
    {
        return 0U;
    }
    if (AttitudeAlignmentWindow_ContinuityCheck(
            context, config, timestamp_us, &sample) == 0U)
    {
        return 0U;
    }
    AttitudeAlignmentWindow_SlotPrepare(
        context, config, &sample, &write_index);
    AttitudeAlignmentWindow_SampleStore(
        context, config, &sample, write_index, timestamp_us,
        acceleration_b_mps2, gyro_b_radps);
    AttitudeAlignmentWindow_StatusUpdate(context, config, &sample);
    return 1U;
}

uint8_t AttitudeAlignmentWindow_Add(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    uint64_t timestamp_us,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    const float quaternion_wxyz[4])
{
    if (quaternion_wxyz == NULL)
    {
        return 0U;
    }
    return AttitudeAlignmentWindow_SampleAdd(
        context, config, timestamp_us, acceleration_b_mps2,
        gyro_b_radps, quaternion_wxyz);
}

uint8_t AttitudeAlignmentWindow_AddInertial(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    uint64_t timestamp_us,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3])
{
    return AttitudeAlignmentWindow_SampleAdd(
        context, config, timestamp_us, acceleration_b_mps2,
        gyro_b_radps, NULL);
}

uint8_t AttitudeAlignmentWindow_GetInertialAverage(
    const AttitudeAlignmentWindow *context,
    float acceleration_b_mps2[3],
    float gyro_b_radps[3])
{
    uint8_t index;

    if ((context == NULL) || (acceleration_b_mps2 == NULL) ||
        (gyro_b_radps == NULL) || (context->valid == 0U) ||
        (context->sample_count == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < 3U; index++)
    {
        acceleration_b_mps2[index] =
            context->acceleration_sum_b_mps2[index] /
            (float)context->sample_count;
        gyro_b_radps[index] = context->gyro_sum_b_radps[index] /
                              (float)context->sample_count;
    }
    return 1U;
}

uint8_t AttitudeAlignmentWindow_GetAverage(
    const AttitudeAlignmentWindow *context,
    float quaternion_wxyz[4],
    float acceleration_b_mps2[3],
    float gyro_b_radps[3])
{
    uint8_t index;

    if ((context == NULL) || (quaternion_wxyz == NULL) ||
        (context->quaternion_sample_count != context->sample_count) ||
        (context->quaternion_sample_count == 0U) ||
        (AttitudeAlignmentWindow_GetInertialAverage(
            context, acceleration_b_mps2, gyro_b_radps) == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeAlignmentWindow,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < 4U; index++)
    {
        quaternion_wxyz[index] = context->quaternion_sum_wxyz[index] /
                                 (float)context->quaternion_sample_count;
    }
    return Attitude_QuaternionNormalize(quaternion_wxyz);
}

uint8_t AttitudeAlignment_ApplyKnownYaw(
    const float source_q_nb[4],
    int8_t yaw_body_axis,
    float yaw_deg,
    float output_q_nb[4])
{
    float q_source[4];
    float axis_b[3] = {0.0f, 0.0f, 0.0f};
    float axis_n[3];
    float horizontal_norm;
    float current_yaw_rad;
    float target_yaw_rad;
    float delta_yaw_rad;
    float yaw_rotation_q[4];
    uint8_t axis_index;
    float axis_sign;

    if ((source_q_nb == NULL) || (output_q_nb == NULL) ||
        (yaw_body_axis == 0) || (yaw_body_axis < -3) ||
        (yaw_body_axis > 3) || (!isfinite(yaw_deg)))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(source_q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(output_q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    axis_index = (uint8_t)((yaw_body_axis < 0) ?
        (-yaw_body_axis - 1) : (yaw_body_axis - 1));
    axis_sign = (yaw_body_axis < 0) ? -1.0f : 1.0f;
    axis_b[axis_index] = axis_sign;
    (void)memcpy(q_source, source_q_nb, sizeof(q_source));
    if (Attitude_QuaternionNormalize(q_source) == 0U)
    {
        return 0U;
    }
    Attitude_RotateVector(q_source, axis_b, axis_n);
    horizontal_norm = sqrtf((axis_n[0] * axis_n[0]) +
                            (axis_n[1] * axis_n[1]));
    if ((!isfinite(horizontal_norm)) ||
        (horizontal_norm < ATTITUDE_ALIGNMENT_VECTOR_NORM_MIN))
    {
        return 0U;
    }
    current_yaw_rad = atan2f(axis_n[1], axis_n[0]);
    target_yaw_rad = yaw_deg * ATTITUDE_ALIGNMENT_DEG_TO_RAD;
    delta_yaw_rad = AttitudeAlignment_YawDeltaResolve(
        current_yaw_rad, target_yaw_rad);
    yaw_rotation_q[0] = cosf(0.5f * delta_yaw_rad);
    yaw_rotation_q[1] = 0.0f;
    yaw_rotation_q[2] = 0.0f;
    yaw_rotation_q[3] = sinf(0.5f * delta_yaw_rad);
    Attitude_QuaternionMultiply(yaw_rotation_q, q_source, output_q_nb);
    return Attitude_QuaternionNormalize(output_q_nb);
}

uint8_t AttitudeAlignment_ApplyKnownHeading(
    const float source_q_nb[4],
    int8_t heading_body_axis,
    float heading_deg,
    float output_q_nb[4])
{
    return AttitudeAlignment_ApplyKnownYaw(source_q_nb,
        heading_body_axis, heading_deg, output_q_nb);
}

uint8_t AttitudeAlignment_TiltConsistent(
    const float q_nb[4],
    const float acceleration_b_mps2[3],
    float maximum_tilt_error_rad)
{
    float q_normalized[4];
    float acceleration_unit_b[3];
    float acceleration_n[3];
    float norm;
    float minimum_vertical_component;
    uint8_t index;

    if ((q_nb == NULL) || (acceleration_b_mps2 == NULL) ||
        (maximum_tilt_error_rad <= 0.0f))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(acceleration_b_mps2, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memcpy(q_normalized, q_nb, sizeof(q_normalized));
    if (Attitude_QuaternionNormalize(q_normalized) == 0U)
    {
        return 0U;
    }
    norm = AttitudeAlignment_VectorNorm(acceleration_b_mps2);
    if ((!isfinite(norm)) || (norm < ATTITUDE_ALIGNMENT_VECTOR_NORM_MIN))
    {
        return 0U;
    }
    for (index = 0U; index < 3U; index++)
    {
        acceleration_unit_b[index] = acceleration_b_mps2[index] / norm;
    }
    Attitude_RotateVector(q_normalized,
                          acceleration_unit_b,
                          acceleration_n);
    minimum_vertical_component = cosf(maximum_tilt_error_rad);
    return (uint8_t)(isfinite(acceleration_n[2]) &&
                     (acceleration_n[2] >= minimum_vertical_component));
}
