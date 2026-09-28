#include "system_inertial.h"

#include <stddef.h>
#include <string.h>

#include "system_imu_if.h"
#include "silverstar_assert.h"
#include "system_user_inertial_config.h"

static uint8_t s_initialized;

_Static_assert(SYSTEM_INERTIAL_VALID_ACCEL == SYSTEM_IMU_VALID_ACCEL &&
               SYSTEM_INERTIAL_VALID_GYRO == SYSTEM_IMU_VALID_GYRO &&
               SYSTEM_INERTIAL_VALID_TEMPERATURE ==
                   SYSTEM_IMU_VALID_TEMPERATURE,
               "Virtual IMU validity bits must preserve device values");

static void SystemInertial_DeviceSampleCopy(
    const SystemImuSample *source,
    SystemInertialSample *destination)
{
    destination->sample_timestamp_us = source->sample_timestamp_us;
    destination->receive_timestamp_us = source->receive_timestamp_us;
    destination->sequence = source->sequence;
    (void)memcpy(destination->accel_raw, source->accel_raw,
                 sizeof(destination->accel_raw));
    (void)memcpy(destination->gyro_raw, source->gyro_raw,
                 sizeof(destination->gyro_raw));
    (void)memcpy(destination->accel_b_mps2, source->accel_b_mps2,
                 sizeof(destination->accel_b_mps2));
    (void)memcpy(destination->gyro_b_radps, source->gyro_b_radps,
                 sizeof(destination->gyro_b_radps));
    destination->temperature_c = source->temperature_c;
    destination->valid_mask = source->valid_mask;
    destination->quality_flags = source->quality_flags;
}

SystemDeviceResult SystemInertial_Init(void)
{
    const SystemUserInertialConfig *config = SystemUserInertial_ConfigGet();

    s_initialized = 0U;
    if ((config == NULL) ||
        (config->time_sync.policy != SYSTEM_INERTIAL_SYNC_PASSTHROUGH) ||
        (config->source_correction.mode != SYSTEM_INERTIAL_CORRECTION_NONE))
    {
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    s_initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{
    SystemImuSample device_sample;
    SystemDeviceResult result;

    if (sample == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemImu_LatestSampleGet(&device_sample);
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    SystemInertial_DeviceSampleCopy(&device_sample, sample);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemInertial_NextGet(SystemInertialSample *sample)
{
    SystemImuSample device_sample;
    SystemDeviceResult result;

    if (sample == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemImu_NextSampleGet(&device_sample);
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    SystemInertial_DeviceSampleCopy(&device_sample, sample);
    return SYSTEM_DEVICE_OK;
}

static void SystemInertial_VectorBiasApply(float vector[3],
    const float bias[3], uint32_t valid_mask, uint32_t first_bit)
{
    uint8_t axis;

    for (axis = 0U; axis < 3U; axis++)
    {
        if ((valid_mask & (first_bit << axis)) != 0U)
        {
            vector[axis] -= bias[axis];
        }
    }
}

static void SystemInertial_VectorDiagonalApply(float vector[3],
    const float matrix[3][3], uint32_t valid_mask, uint32_t first_bit)
{
    uint8_t axis;

    for (axis = 0U; axis < 3U; axis++)
    {
        if ((valid_mask & (first_bit << axis)) != 0U)
        {
            vector[axis] *= matrix[axis][axis];
        }
    }
}

static void SystemInertial_VectorMatrixApply(float vector[3],
    const float matrix[3][3])
{
    float measured[3];
    uint8_t row;
    uint8_t column;

    (void)memcpy(measured, vector, sizeof(measured));
    for (row = 0U; row < 3U; row++)
    {
        vector[row] = 0.0f;
        for (column = 0U; column < 3U; column++)
        {
            vector[row] += matrix[row][column] * measured[column];
        }
    }
}

static void SystemInertial_CorrectionModeApply(
    SystemInertialSourceSample *corrected,
    const SystemInertialSourceSample *measured,
    const SystemInertialSourceCorrection *correction,
    uint32_t accel_mask,
    uint32_t gyro_mask)
{
    SILVERSTAR_ASSERT_OBJECT(corrected, SystemInertialSourceSample,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(correction, SystemInertialSourceCorrection,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemInertial_VectorBiasApply(corrected->accel_mps2,
        correction->accel_bias_mps2, measured->valid_mask,
        SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_X);
    SystemInertial_VectorBiasApply(corrected->gyro_radps,
        correction->gyro_bias_radps, measured->valid_mask,
        SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X);
    if (correction->mode == SYSTEM_INERTIAL_CORRECTION_DIAGONAL)
    {
        SystemInertial_VectorDiagonalApply(corrected->accel_mps2,
            correction->accel_matrix, measured->valid_mask,
            SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_X);
        SystemInertial_VectorDiagonalApply(corrected->gyro_radps,
            correction->gyro_matrix, measured->valid_mask,
            SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X);
    }
    else if (correction->mode == SYSTEM_INERTIAL_CORRECTION_FULL_MATRIX)
    {
        if (accel_mask != 0U)
        {
            SystemInertial_VectorMatrixApply(corrected->accel_mps2,
                correction->accel_matrix);
        }
        if (gyro_mask != 0U)
        {
            SystemInertial_VectorMatrixApply(corrected->gyro_radps,
                correction->gyro_matrix);
        }
    }
}

SystemDeviceResult SystemInertialSource_CorrectionApply(
    const SystemInertialSourceSample *measured,
    const SystemInertialSourceCorrection *correction,
    SystemInertialSourceSample *corrected)
{
    uint32_t accel_mask;
    uint32_t gyro_mask;

    if ((measured == NULL) || (correction == NULL) || (corrected == NULL) ||
        (correction->mode > SYSTEM_INERTIAL_CORRECTION_FULL_MATRIX))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(measured, SystemInertialSourceSample,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    *corrected = *measured;
    if (correction->mode == SYSTEM_INERTIAL_CORRECTION_NONE)
    {
        return SYSTEM_DEVICE_OK;
    }

    accel_mask = measured->valid_mask &
        SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ;
    gyro_mask = measured->valid_mask &
        SYSTEM_INERTIAL_SOURCE_VALID_GYRO_XYZ;
    if ((correction->mode == SYSTEM_INERTIAL_CORRECTION_FULL_MATRIX) &&
        (((accel_mask != 0U) &&
          (accel_mask != SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ)) ||
         ((gyro_mask != 0U) &&
          (gyro_mask != SYSTEM_INERTIAL_SOURCE_VALID_GYRO_XYZ))))
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }

    SystemInertial_CorrectionModeApply(
        corrected, measured, correction, accel_mask, gyro_mask);
    return SYSTEM_DEVICE_OK;
}
