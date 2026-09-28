#include "imu_six_face_calibration.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define IMU_SIX_FACE_DENOMINATOR_EPSILON_MPS2 1.0e-6f

static ImuSixFaceResult ImuSixFace_MeasurementsAccumulate(
    const ImuSixFaceMeasurements *measurements,
    ImuSixFaceCorrection *correction)
{
    uint8_t axis;
    uint8_t face;

    SILVERSTAR_ASSERT_OBJECT(measurements, ImuSixFaceMeasurements,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(correction, ImuSixFaceCorrection,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (face = 0U; face < IMU_SIX_FACE_COUNT; face++)
    {
        for (axis = 0U; axis < IMU_SIX_FACE_AXIS_COUNT; axis++)
        {
            if ((!isfinite(measurements->accel_mean_mps2[face][axis])) ||
                (!isfinite(measurements->gyro_mean_radps[face][axis])))
            {
                return IMU_SIX_FACE_RESULT_NONFINITE;
            }
            correction->gyro_bias_radps[axis] +=
                measurements->gyro_mean_radps[face][axis];
        }
    }
    return IMU_SIX_FACE_RESULT_OK;
}

static ImuSixFaceResult ImuSixFace_AxisCorrectionCalculate(
    const ImuSixFaceMeasurements *measurements,
    float gravity_mps2,
    float scale_min,
    float scale_max,
    ImuSixFaceCorrection *correction)
{
    uint8_t axis;

    SILVERSTAR_ASSERT_OBJECT(measurements, ImuSixFaceMeasurements,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(correction, ImuSixFaceCorrection,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    for (axis = 0U; axis < IMU_SIX_FACE_AXIS_COUNT; axis++)
    {
        uint8_t positive_face = (uint8_t)(axis * 2U);
        uint8_t negative_face = (uint8_t)(positive_face + 1U);
        float positive = measurements->accel_mean_mps2[positive_face][axis];
        float negative = measurements->accel_mean_mps2[negative_face][axis];
        float denominator = positive - negative;
        float scale;

        if ((!isfinite(denominator)) ||
            (denominator <= IMU_SIX_FACE_DENOMINATOR_EPSILON_MPS2))
        {
            return IMU_SIX_FACE_RESULT_DENOMINATOR;
        }
        scale = (2.0f * gravity_mps2) / denominator;
        if ((!isfinite(scale)) || (scale < scale_min) || (scale > scale_max))
        {
            return IMU_SIX_FACE_RESULT_SCALE_RANGE;
        }
        correction->accel_bias_mps2[axis] = (positive + negative) * 0.5f;
        correction->accel_scale[axis] = scale;
        correction->gyro_bias_radps[axis] /= (float)IMU_SIX_FACE_COUNT;
        correction->gyro_scale[axis] = 1.0f;
        if ((!isfinite(correction->accel_bias_mps2[axis])) ||
            (!isfinite(correction->gyro_bias_radps[axis])))
        {
            return IMU_SIX_FACE_RESULT_NONFINITE;
        }
    }
    return IMU_SIX_FACE_RESULT_OK;
}

ImuSixFaceResult ImuSixFace_CorrectionCalculate(
    const ImuSixFaceMeasurements *measurements,
    float gravity_mps2,
    float scale_min,
    float scale_max,
    ImuSixFaceCorrection *correction)
{
    ImuSixFaceResult result;

    if ((measurements == NULL) || (correction == NULL) ||
        (!isfinite(gravity_mps2)) || (gravity_mps2 <= 0.0f) ||
        (!isfinite(scale_min)) || (!isfinite(scale_max)) ||
        (scale_min <= 0.0f) || (scale_max < scale_min))
    {
        return IMU_SIX_FACE_RESULT_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(measurements, ImuSixFaceMeasurements,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(correction, ImuSixFaceCorrection,
                             SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    (void)memset(correction, 0, sizeof(*correction));
    result = ImuSixFace_MeasurementsAccumulate(measurements, correction);
    if (result != IMU_SIX_FACE_RESULT_OK)
    {
        return result;
    }
    return ImuSixFace_AxisCorrectionCalculate(
        measurements, gravity_mps2, scale_min, scale_max, correction);
}
