#ifndef __IMU_SIX_FACE_CALIBRATION_H
#define __IMU_SIX_FACE_CALIBRATION_H

#include <stdint.h>

#define IMU_SIX_FACE_COUNT 6U
#define IMU_SIX_FACE_AXIS_COUNT 3U

typedef enum
{
    IMU_SIX_FACE_X_POSITIVE = 0U,
    IMU_SIX_FACE_X_NEGATIVE,
    IMU_SIX_FACE_Y_POSITIVE,
    IMU_SIX_FACE_Y_NEGATIVE,
    IMU_SIX_FACE_Z_POSITIVE,
    IMU_SIX_FACE_Z_NEGATIVE
} ImuSixFace;

typedef enum
{
    IMU_SIX_FACE_RESULT_OK = 0U,
    IMU_SIX_FACE_RESULT_INVALID_ARGUMENT,
    IMU_SIX_FACE_RESULT_NONFINITE,
    IMU_SIX_FACE_RESULT_DENOMINATOR,
    IMU_SIX_FACE_RESULT_SCALE_RANGE
} ImuSixFaceResult;

typedef struct
{
    float accel_mean_mps2[IMU_SIX_FACE_COUNT][IMU_SIX_FACE_AXIS_COUNT];
    float gyro_mean_radps[IMU_SIX_FACE_COUNT][IMU_SIX_FACE_AXIS_COUNT];
} ImuSixFaceMeasurements;

typedef struct
{
    float accel_bias_mps2[IMU_SIX_FACE_AXIS_COUNT];
    float accel_scale[IMU_SIX_FACE_AXIS_COUNT];
    float gyro_bias_radps[IMU_SIX_FACE_AXIS_COUNT];
    float gyro_scale[IMU_SIX_FACE_AXIS_COUNT];
} ImuSixFaceCorrection;

ImuSixFaceResult ImuSixFace_CorrectionCalculate(
    const ImuSixFaceMeasurements *measurements,
    float gravity_mps2,
    float scale_min,
    float scale_max,
    ImuSixFaceCorrection *correction);

#endif /* __IMU_SIX_FACE_CALIBRATION_H */
