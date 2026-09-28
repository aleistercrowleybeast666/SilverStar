#include "system_calibration.h"

#include <math.h>
#include <stddef.h>

#include "silverstar_assert.h"

SystemDeviceResult SystemCalibration_ImuCorrectionApply(
    const float raw_accel_b_mps2[3],
    const float raw_gyro_b_radps[3],
    const SystemCalibrationImuCorrection *correction,
    float corrected_accel_b_mps2[3],
    float corrected_gyro_b_radps[3])
{
    float accel[3];
    float gyro[3];
    uint8_t index;

    if ((raw_accel_b_mps2 == NULL) || (raw_gyro_b_radps == NULL) ||
        (correction == NULL) || (corrected_accel_b_mps2 == NULL) ||
        (corrected_gyro_b_radps == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(correction, SystemCalibrationImuCorrection,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < 3U; index++)
    {
        if ((!isfinite(raw_accel_b_mps2[index])) ||
            (!isfinite(raw_gyro_b_radps[index])) ||
            (!isfinite(correction->accel_bias_mps2[index])) ||
            (!isfinite(correction->accel_scale[index])) ||
            (!isfinite(correction->gyro_bias_radps[index])) ||
            (!isfinite(correction->gyro_scale[index])))
        {
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
        accel[index] =
            (raw_accel_b_mps2[index] -
             correction->accel_bias_mps2[index]) *
            correction->accel_scale[index];
        gyro[index] =
            (raw_gyro_b_radps[index] -
             correction->gyro_bias_radps[index]) *
            correction->gyro_scale[index];
        if ((!isfinite(accel[index])) || (!isfinite(gyro[index])))
        {
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
    }
    for (index = 0U; index < 3U; index++)
    {
        corrected_accel_b_mps2[index] = accel[index];
        corrected_gyro_b_radps[index] = gyro[index];
    }
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemCalibration_CapabilityMaskGet(void)
{
    return (uint8_t)(SYSTEM_CALIBRATION_CAPABILITY_NONE |
                     SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK);
}
