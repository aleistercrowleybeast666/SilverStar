#include "attitude_triad.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "attitude_frame.h"
#include "silverstar_assert.h"

#define ATTITUDE_TRIAD_VECTOR_NORM_MIN 1.0e-6f
#define ATTITUDE_TRIAD_DEG_TO_RAD      0.01745329251994329577f

typedef struct
{
    float magnetic_direction_b[3];
    float magnetic_norm_uT;
} AttitudeTriadSample;

static float AttitudeTriad_VectorDot(const float a[3], const float b[3])
{
    return (a[0] * b[0]) + (a[1] * b[1]) + (a[2] * b[2]);
}

static float AttitudeTriad_VectorNorm(const float vector[3])
{
    return sqrtf(AttitudeTriad_VectorDot(vector, vector));
}

static uint8_t AttitudeTriad_VectorNormalize(float vector[3])
{
    float norm = AttitudeTriad_VectorNorm(vector);
    uint8_t index;

    if ((!isfinite(norm)) || (norm < ATTITUDE_TRIAD_VECTOR_NORM_MIN))
    {
        return 0U;
    }
    for (index = 0U; index < 3U; index++)
    {
        vector[index] /= norm;
    }
    return 1U;
}

static void AttitudeTriad_VectorCross(const float a[3],
                                      const float b[3],
                                      float out[3])
{
    out[0] = (a[1] * b[2]) - (a[2] * b[1]);
    out[1] = (a[2] * b[0]) - (a[0] * b[2]);
    out[2] = (a[0] * b[1]) - (a[1] * b[0]);
}

static uint8_t AttitudeTriad_VectorFinite(const float vector[3])
{
    return (uint8_t)(isfinite(vector[0]) && isfinite(vector[1]) &&
                     isfinite(vector[2]));
}

static uint8_t AttitudeTriad_WindowConfigValid(
    const AttitudeTriadConfig *config)
{
    return (uint8_t)((config != NULL) &&
        (config->minimum_samples != 0U) &&
        (config->maximum_samples >= config->minimum_samples) &&
        (config->maximum_samples <= ATTITUDE_TRIAD_WINDOW_CAPACITY) &&
        isfinite(config->gravity_mps2) && (config->gravity_mps2 > 0.0f) &&
        isfinite(config->acceleration_tolerance_mps2) &&
        (config->acceleration_tolerance_mps2 > 0.0f) &&
        isfinite(config->maximum_gyro_radps) &&
        (config->maximum_gyro_radps > 0.0f));
}

static uint8_t AttitudeTriad_MagneticConfigValid(
    const AttitudeTriadConfig *config)
{
    return (uint8_t)((config != NULL) &&
        isfinite(config->magnetic_magnitude_min_uT) &&
        isfinite(config->magnetic_magnitude_max_uT) &&
        (config->magnetic_magnitude_min_uT > 0.0f) &&
        (config->magnetic_magnitude_max_uT >
         config->magnetic_magnitude_min_uT) &&
        isfinite(config->magnetic_magnitude_max_deviation_ratio) &&
        (config->magnetic_magnitude_max_deviation_ratio > 0.0f) &&
        isfinite(config->magnetic_direction_min_dot) &&
        (config->magnetic_direction_min_dot > 0.0f) &&
        (config->magnetic_direction_min_dot <= 1.0f) &&
        isfinite(config->magnetic_horizontal_min_ratio) &&
        (config->magnetic_horizontal_min_ratio > 0.0f) &&
        (config->magnetic_horizontal_min_ratio < 1.0f));
}

static uint8_t AttitudeTriad_ConfigValid(const AttitudeTriadConfig *config)
{
    return (uint8_t)((AttitudeTriad_WindowConfigValid(config) != 0U) &&
                     (AttitudeTriad_MagneticConfigValid(config) != 0U));
}

static void AttitudeTriad_AccumulationClear(
    AttitudeTriadAccumulator *context)
{
    uint32_t reject_count = context->reject_count;

    (void)memset(context, 0, sizeof(*context));
    context->reject_count = reject_count;
}

static uint8_t AttitudeTriad_SampleReject(
    AttitudeTriadAccumulator *context)
{
    if (context == NULL)
    {
        return 0U;
    }
    context->reject_count++;
    AttitudeTriad_AccumulationClear(context);
    return 0U;
}

void AttitudeTriad_Init(AttitudeTriadAccumulator *context)
{
    if (context != NULL)
    {
        (void)memset(context, 0, sizeof(*context));
    }
}

static uint8_t AttitudeTriad_SamplePrepare(
    AttitudeTriadAccumulator *context,
    const AttitudeTriadConfig *config,
    const float accel_b[3],
    const float gyro_b[3],
    const float mag_b[3],
    uint8_t magnetic_calibration_valid,
    AttitudeTriadSample *sample)
{
    float accel_norm;
    float gyro_norm;
    float mag_horizontal_b[3];
    float projection;
    float up_b[3];
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudeTriadSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((magnetic_calibration_valid == 0U) ||
        (AttitudeTriad_VectorFinite(accel_b) == 0U) ||
        (AttitudeTriad_VectorFinite(gyro_b) == 0U) ||
        (AttitudeTriad_VectorFinite(mag_b) == 0U))
    {
        return AttitudeTriad_SampleReject(context);
    }
    accel_norm = AttitudeTriad_VectorNorm(accel_b);
    gyro_norm = AttitudeTriad_VectorNorm(gyro_b);
    sample->magnetic_norm_uT = AttitudeTriad_VectorNorm(mag_b);
    if ((!isfinite(accel_norm)) || (!isfinite(gyro_norm)) ||
        (!isfinite(sample->magnetic_norm_uT)) ||
        (gyro_norm > config->maximum_gyro_radps) ||
        (fabsf(accel_norm - config->gravity_mps2) >
         config->acceleration_tolerance_mps2) ||
        (sample->magnetic_norm_uT < config->magnetic_magnitude_min_uT) ||
        (sample->magnetic_norm_uT > config->magnetic_magnitude_max_uT))
    {
        return AttitudeTriad_SampleReject(context);
    }
    (void)memcpy(up_b, accel_b, sizeof(up_b));
    (void)memcpy(sample->magnetic_direction_b, mag_b,
                 sizeof(sample->magnetic_direction_b));
    if ((AttitudeTriad_VectorNormalize(up_b) == 0U) ||
        (AttitudeTriad_VectorNormalize(sample->magnetic_direction_b) == 0U))
    {
        return AttitudeTriad_SampleReject(context);
    }
    projection = AttitudeTriad_VectorDot(mag_b, up_b);
    for (index = 0U; index < 3U; index++)
    {
        mag_horizontal_b[index] = mag_b[index] - (projection * up_b[index]);
    }
    if ((AttitudeTriad_VectorNorm(mag_horizontal_b) /
         sample->magnetic_norm_uT) < config->magnetic_horizontal_min_ratio)
    {
        return AttitudeTriad_SampleReject(context);
    }
    return 1U;
}

static uint8_t AttitudeTriad_ContinuityCheck(
    AttitudeTriadAccumulator *context,
    const AttitudeTriadConfig *config,
    uint64_t timestamp_us,
    const AttitudeTriadSample *sample)
{
    float mean_mag_direction_b[3];
    float mean_mag_norm;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudeTriadSample,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (context->sample_count == 0U)
    {
        context->first_timestamp_us = timestamp_us;
        return 1U;
    }
    if ((timestamp_us <= context->last_timestamp_us) ||
        ((config->maximum_gap_us != 0U) &&
         ((timestamp_us - context->last_timestamp_us) >
          config->maximum_gap_us)))
    {
        return AttitudeTriad_SampleReject(context);
    }
    mean_mag_norm = context->magnetic_magnitude_sum_uT /
                    (float)context->sample_count;
    if (fabsf(sample->magnetic_norm_uT - mean_mag_norm) >
        (mean_mag_norm * config->magnetic_magnitude_max_deviation_ratio))
    {
        return AttitudeTriad_SampleReject(context);
    }
    (void)memcpy(mean_mag_direction_b, context->mag_sum_b,
                 sizeof(mean_mag_direction_b));
    if ((AttitudeTriad_VectorNormalize(mean_mag_direction_b) == 0U) ||
        (AttitudeTriad_VectorDot(mean_mag_direction_b,
                                 sample->magnetic_direction_b) <
         config->magnetic_direction_min_dot))
    {
        return AttitudeTriad_SampleReject(context);
    }
    return 1U;
}

static uint16_t AttitudeTriad_SlotPrepare(
    AttitudeTriadAccumulator *context,
    const AttitudeTriadConfig *config)
{
    uint16_t write_index;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(config, AttitudeTriadConfig,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    context->minimum_samples = config->minimum_samples;
    write_index = context->head;
    if (context->sample_count >= config->maximum_samples)
    {
        for (index = 0U; index < 3U; index++)
        {
            context->accel_sum_b[index] -=
                context->accel_samples_b[write_index][index];
            context->gyro_sum_b[index] -=
                context->gyro_samples_b[write_index][index];
            context->mag_sum_b[index] -=
                context->mag_samples_b[write_index][index];
        }
        context->magnetic_magnitude_sum_uT -=
            context->magnetic_magnitude_samples_uT[write_index];
    }
    else
    {
        context->sample_count++;
    }
    return write_index;
}

static void AttitudeTriad_SampleStore(
    AttitudeTriadAccumulator *context,
    const AttitudeTriadConfig *config,
    uint64_t timestamp_us,
    const float accel_b[3],
    const float gyro_b[3],
    const float mag_b[3],
    float mag_norm,
    uint16_t write_index)
{
    uint16_t oldest_index;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(config, AttitudeTriadConfig,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memcpy(context->accel_samples_b[write_index], accel_b,
                 sizeof(context->accel_samples_b[write_index]));
    (void)memcpy(context->gyro_samples_b[write_index], gyro_b,
                 sizeof(context->gyro_samples_b[write_index]));
    (void)memcpy(context->mag_samples_b[write_index], mag_b,
                 sizeof(context->mag_samples_b[write_index]));
    context->magnetic_magnitude_samples_uT[write_index] = mag_norm;
    context->timestamp_samples_us[write_index] = timestamp_us;
    context->head = (uint16_t)((context->head + 1U) % config->maximum_samples);
    for (index = 0U; index < 3U; index++)
    {
        context->accel_sum_b[index] += accel_b[index];
        context->gyro_sum_b[index] += gyro_b[index];
        context->mag_sum_b[index] += mag_b[index];
    }
    context->magnetic_magnitude_sum_uT += mag_norm;
    context->last_timestamp_us = timestamp_us;
    oldest_index = (uint16_t)((context->head + config->maximum_samples -
                              context->sample_count) %
                             config->maximum_samples);
    context->first_timestamp_us = context->timestamp_samples_us[oldest_index];
    context->valid = (uint8_t)(
        (context->sample_count >= config->minimum_samples) &&
        ((context->last_timestamp_us - context->first_timestamp_us) >=
         config->minimum_duration_us));
}

uint8_t AttitudeTriad_AddStaticSample(
    AttitudeTriadAccumulator *context,
    const AttitudeTriadConfig *config,
    uint64_t timestamp_us,
    const float accel_b[3],
    const float gyro_b[3],
    const float mag_b[3],
    uint8_t magnetic_calibration_valid)
{
    AttitudeTriadSample sample;
    uint16_t write_index;

    if ((context == NULL) || (AttitudeTriad_ConfigValid(config) == 0U) ||
        (accel_b == NULL) || (gyro_b == NULL) || (mag_b == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (AttitudeTriad_SamplePrepare(
            context, config, accel_b, gyro_b, mag_b,
            magnetic_calibration_valid, &sample) == 0U)
    {
        return 0U;
    }
    if (AttitudeTriad_ContinuityCheck(
            context, config, timestamp_us, &sample) == 0U)
    {
        return 0U;
    }
    write_index = AttitudeTriad_SlotPrepare(context, config);
    AttitudeTriad_SampleStore(
        context, config, timestamp_us, accel_b, gyro_b, mag_b,
        sample.magnetic_norm_uT, write_index);
    return 1U;
}

uint8_t AttitudeTriad_GetAverage(
    const AttitudeTriadAccumulator *context,
    float accel_mean_b[3],
    float gyro_mean_b[3],
    float mag_mean_b[3])
{
    uint8_t index;

    if ((context == NULL) || (accel_mean_b == NULL) ||
        (gyro_mean_b == NULL) || (mag_mean_b == NULL) ||
        (context->valid == 0U) || (context->sample_count == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(accel_mean_b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (index = 0U; index < 3U; index++)
    {
        accel_mean_b[index] = context->accel_sum_b[index] /
                              (float)context->sample_count;
        gyro_mean_b[index] = context->gyro_sum_b[index] /
                             (float)context->sample_count;
        mag_mean_b[index] = context->mag_sum_b[index] /
                            (float)context->sample_count;
    }
    return 1U;
}

static void AttitudeTriad_DeclinationApply(
    const float north_magnetic_b[3],
    const float east_magnetic_b[3],
    float magnetic_declination_deg,
    float north_true_b[3],
    float east_true_b[3])
{
    float declination_rad;
    float cosine;
    float sine;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(north_magnetic_b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(east_magnetic_b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    declination_rad = magnetic_declination_deg * ATTITUDE_TRIAD_DEG_TO_RAD;
    cosine = cosf(declination_rad);
    sine = sinf(declination_rad);
    for (index = 0U; index < 3U; index++)
    {
        north_true_b[index] = (cosine * north_magnetic_b[index]) -
                              (sine * east_magnetic_b[index]);
        east_true_b[index] = (sine * north_magnetic_b[index]) +
                             (cosine * east_magnetic_b[index]);
    }
}

static uint8_t AttitudeTriad_TrueHorizontalBasisBuild(
    float up_b[3],
    const float mag_b[3],
    float magnetic_declination_deg,
    float north_true_b[3],
    float east_true_b[3])
{
    float east_magnetic_b[3];
    float north_magnetic_b[3];
    float mag_norm;
    float projection;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(up_b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(mag_b, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (AttitudeTriad_VectorNormalize(up_b) == 0U)
    {
        return 0U;
    }
    mag_norm = AttitudeTriad_VectorNorm(mag_b);
    if ((!isfinite(mag_norm)) || (mag_norm < ATTITUDE_TRIAD_VECTOR_NORM_MIN))
    {
        return 0U;
    }
    projection = AttitudeTriad_VectorDot(mag_b, up_b);
    for (index = 0U; index < 3U; index++)
    {
        north_magnetic_b[index] = mag_b[index] - (projection * up_b[index]);
    }
    if (AttitudeTriad_VectorNormalize(north_magnetic_b) == 0U)
    {
        return 0U;
    }
    AttitudeTriad_VectorCross(north_magnetic_b, up_b, east_magnetic_b);
    if (AttitudeTriad_VectorNormalize(east_magnetic_b) == 0U)
    {
        return 0U;
    }
    AttitudeTriad_DeclinationApply(
        north_magnetic_b, east_magnetic_b, magnetic_declination_deg,
        north_true_b, east_true_b);
    if (AttitudeTriad_VectorNormalize(east_true_b) == 0U)
    {
        return 0U;
    }
    AttitudeTriad_VectorCross(up_b, east_true_b, north_true_b);
    if (AttitudeTriad_VectorNormalize(north_true_b) == 0U)
    {
        return 0U;
    }
    AttitudeTriad_VectorCross(north_true_b, up_b, east_true_b);
    return AttitudeTriad_VectorNormalize(east_true_b);
}

uint8_t AttitudeTriad_BuildBodyToEnu(
    const AttitudeTriadAccumulator *context,
    float magnetic_declination_deg,
    float q_nb_absolute[4])
{
    float up_b[3];
    float gyro_mean_b[3];
    float mag_b[3];
    float north_true_b[3];
    float east_true_b[3];
    float matrix_nb[3][3];
    uint8_t index;

    if ((context == NULL) || (q_nb_absolute == NULL) ||
        (!isfinite(magnetic_declination_deg)) ||
        (AttitudeTriad_GetAverage(context, up_b, gyro_mean_b, mag_b) == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(context, AttitudeTriadAccumulator,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(q_nb_absolute, float,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if (AttitudeTriad_TrueHorizontalBasisBuild(
            up_b, mag_b, magnetic_declination_deg,
            north_true_b, east_true_b) == 0U)
    {
        return 0U;
    }
    for (index = 0U; index < 3U; index++)
    {
        matrix_nb[0][index] = east_true_b[index];
        matrix_nb[1][index] = north_true_b[index];
        matrix_nb[2][index] = up_b[index];
    }
    return Attitude_RotationMatrixToQuaternionWxyz(
        (const float (*)[3])matrix_nb, q_nb_absolute);
}
