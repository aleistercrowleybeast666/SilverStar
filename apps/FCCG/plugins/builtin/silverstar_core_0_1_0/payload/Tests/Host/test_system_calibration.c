#include <math.h>
#include <stdint.h>
#include <string.h>

#include "imu_six_face_calibration.h"
#include "system_calibration.h"
#include "system_lifecycle.h"
#include "system_user_config.h"
#include "system_user_startup_config.h"
#include "test_common.h"

static uint64_t s_timestamp_us;
static uint32_t s_sequence;
static uint32_t s_alignment_invalidate_count;

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return SYSTEM_STATE_PREFLIGHT;
}

SystemDeviceResult SystemAlignment_CalibrationInvalidate(void)
{
    s_alignment_invalidate_count++;
    return SYSTEM_DEVICE_OK;
}

static SystemCalibrationFace Test_StartupFaceGet(void)
{
    return (SystemCalibrationFace)SYSTEM_IMU_STARTUP_GRAVITY_DIRECTION;
}

static void Test_FaceDirectionGet(SystemCalibrationFace face,
                                  float direction[3])
{
    (void)memset(direction, 0, sizeof(float) * 3U);
    direction[(uint8_t)face / 2U] = (((uint8_t)face & 1U) == 0U) ?
        1.0f : -1.0f;
}

static void Test_SamplePush(const float accel[3], const float gyro[3])
{
    SystemInertialSample sample;

    (void)memset(&sample, 0, sizeof(sample));
    s_timestamp_us += 5000ULL;
    sample.sample_timestamp_us = s_timestamp_us;
    sample.receive_timestamp_us = s_timestamp_us;
    sample.sequence = ++s_sequence;
    (void)memcpy(sample.accel_b_mps2, accel,
                 sizeof(sample.accel_b_mps2));
    (void)memcpy(sample.gyro_b_radps, gyro,
                 sizeof(sample.gyro_b_radps));
    sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL |
                        SYSTEM_INERTIAL_VALID_GYRO;
    SystemCalibration_ImuSampleProcess(&sample);
}

static void Test_FaceSampleMake(SystemCalibrationFace face,
                                const float accel_bias[3],
                                const float accel_scale[3],
                                const float gyro[3],
                                float accel[3])
{
    float direction[3];
    uint8_t index;

    Test_FaceDirectionGet(face, direction);
    for (index = 0U; index < 3U; index++)
    {
        accel[index] = accel_bias[index] +
            ((direction[index] * SYSTEM_LOCAL_GRAVITY_MPS2) /
             accel_scale[index]);
    }
    (void)gyro;
}

static void Test_StableWindowFeed(const float accel[3],
                                  const float gyro[3])
{
    uint16_t index;

    for (index = 0U; index < 430U; index++)
    {
        Test_SamplePush(accel, gyro);
    }
    SystemCalibration_Process();
}

static void Test_None(void)
{
    SystemCalibrationStatus status;
    SystemCalibrationImuCorrection correction;
    uint8_t index;

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mode == SYSTEM_CALIBRATION_MODE_NONE);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    TEST_CHECK(SystemCalibration_ImuCorrectionGet(&correction) ==
               SYSTEM_DEVICE_OK);
    for (index = 0U; index < 3U; index++)
    {
        TEST_CHECK_NEAR(correction.accel_bias_mps2[index], 0.0f, 1.0e-7f);
        TEST_CHECK_NEAR(correction.gyro_bias_radps[index], 0.0f, 1.0e-7f);
        TEST_CHECK_NEAR(correction.accel_scale[index], 1.0f, 1.0e-7f);
        TEST_CHECK_NEAR(correction.gyro_scale[index], 1.0f, 1.0e-7f);
    }
}

static void Test_OneFace(void)
{
    const float accel_bias[3] = {0.08f, -0.06f, 0.04f};
    const float unit_scale[3] = {1.0f, 1.0f, 1.0f};
    const float gyro_bias[3] = {0.010f, -0.008f, 0.006f};
    SystemCalibrationStatus status;
    float accel[3];
    uint8_t index;

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) ==
               SYSTEM_DEVICE_OK);
    Test_FaceSampleMake(Test_StartupFaceGet(), accel_bias, unit_scale,
                        gyro_bias, accel);
    Test_StableWindowFeed(accel, gyro_bias);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    for (index = 0U; index < 3U; index++)
    {
        TEST_CHECK_NEAR(status.correction.accel_bias_mps2[index],
                        accel_bias[index], 1.0e-4f);
        TEST_CHECK_NEAR(status.correction.gyro_bias_radps[index],
                        gyro_bias[index], 1.0e-5f);
        TEST_CHECK_NEAR(status.correction.accel_scale[index], 1.0f,
                        1.0e-7f);
    }
}

static void Test_Rejections(void)
{
    const float zero[3] = {0.0f, 0.0f, 0.0f};
    const float unit[3] = {1.0f, 1.0f, 1.0f};
    SystemCalibrationStatus status;
    SystemCalibrationFace face = Test_StartupFaceGet();
    SystemCalibrationFace wrong_face =
        (SystemCalibrationFace)(((uint8_t)face ^ 1U));
    float accel[3];
    float gyro[3] = {0.0f, 0.0f, 0.0f};
    uint16_t index;
    uint32_t diagnostic_sequence;
    uint8_t noisy_axis = (((uint8_t)face / 2U) == 0U) ? 1U : 0U;

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_face == SYSTEM_CALIBRATION_FACE_NONE);
    TEST_CHECK(status.diagnostic_reason ==
               SYSTEM_CALIBRATION_WAIT_NO_STREAM);
    Test_FaceSampleMake(wrong_face, zero, unit, gyro, accel);
    Test_SamplePush(accel, gyro);
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.wait_reason ==
               SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION);
    TEST_CHECK(status.diagnostic_face == SYSTEM_CALIBRATION_FACE_NONE);
    TEST_CHECK(status.diagnostic_reason ==
               SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION);
    diagnostic_sequence = status.diagnostic_sequence;
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_sequence == diagnostic_sequence);

    Test_FaceSampleMake(face, zero, unit, gyro, accel);
    gyro[0] = SYSTEM_IMU_BIAS_MAX_GYRO_RADPS + 0.01f;
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.wait_reason == SYSTEM_CALIBRATION_WAIT_GYRO_MOVING);
    TEST_CHECK(status.diagnostic_reason ==
               SYSTEM_CALIBRATION_WAIT_GYRO_MOVING);
    TEST_CHECK(status.diagnostic_sequence > diagnostic_sequence);
    diagnostic_sequence = status.diagnostic_sequence;
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_sequence == diagnostic_sequence);

    gyro[0] = 0.0f;
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_reason == SYSTEM_CALIBRATION_WAIT_NONE);
    TEST_CHECK(status.diagnostic_sequence > diagnostic_sequence);

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) ==
               SYSTEM_DEVICE_OK);
    for (index = 0U; index < 220U; index++)
    {
        Test_SamplePush(accel, gyro);
    }
    for (index = 0U; index < 220U; index++)
    {
        float noisy[3];

        (void)memcpy(noisy, accel, sizeof(noisy));
        noisy[noisy_axis] += ((index & 1U) == 0U) ? 0.30f : -0.30f;
        Test_SamplePush(noisy, gyro);
        TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
        if (status.retry_count != 0U) { break; }
    }
    TEST_CHECK(status.retry_count != 0U);
    TEST_CHECK(status.wait_reason == SYSTEM_CALIBRATION_WAIT_VARIANCE);
    TEST_CHECK(status.diagnostic_reason == SYSTEM_CALIBRATION_WAIT_VARIANCE);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_COLLECTING);
    TEST_CHECK(status.ready == 0U);
}

static void Test_SixFace(void)
{
    static const SystemCalibrationFace order[6] = {
        SYSTEM_CALIBRATION_FACE_Z_POSITIVE,
        SYSTEM_CALIBRATION_FACE_X_NEGATIVE,
        SYSTEM_CALIBRATION_FACE_Y_POSITIVE,
        SYSTEM_CALIBRATION_FACE_Z_NEGATIVE,
        SYSTEM_CALIBRATION_FACE_X_POSITIVE,
        SYSTEM_CALIBRATION_FACE_Y_NEGATIVE
    };
    const float accel_bias[3] = {0.08f, -0.06f, 0.04f};
    const float accel_scale[3] = {1.01f, 0.99f, 1.02f};
    const float gyro_bias[3] = {0.010f, -0.008f, 0.006f};
    SystemCalibrationStatus status;
    SystemCalibrationStatus ready_status;
    ImuSixFaceMeasurements invalid;
    ImuSixFaceCorrection unused;
    float accel[3];
    float gyro[3];
    uint8_t index;
    uint8_t axis;
    uint32_t diagnostic_sequence;
    uint32_t invalidate_count;

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_SIX_FACE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_face == SYSTEM_CALIBRATION_FACE_NONE);
    TEST_CHECK(status.diagnostic_reason == SYSTEM_CALIBRATION_WAIT_NONE);
    (void)memcpy(gyro, gyro_bias, sizeof(gyro));
    Test_FaceSampleMake(SYSTEM_CALIBRATION_FACE_X_NEGATIVE,
                        accel_bias, accel_scale, gyro_bias, accel);
    gyro[0] = SYSTEM_IMU_BIAS_MAX_GYRO_RADPS + 0.01f;
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_FaceCollect(
        SYSTEM_CALIBRATION_FACE_X_NEGATIVE) == SYSTEM_DEVICE_VERIFY_FAILED);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask == 0U);
    TEST_CHECK(status.diagnostic_face ==
               SYSTEM_CALIBRATION_FACE_X_NEGATIVE);
    TEST_CHECK(status.diagnostic_reason ==
               SYSTEM_CALIBRATION_WAIT_GYRO_MOVING);

    gyro[0] = 0.0f;
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_FaceCollect(
        SYSTEM_CALIBRATION_FACE_X_POSITIVE) == SYSTEM_DEVICE_VERIFY_FAILED);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_face ==
               SYSTEM_CALIBRATION_FACE_X_POSITIVE);
    TEST_CHECK(status.diagnostic_reason ==
               SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION);

    (void)memcpy(gyro, gyro_bias, sizeof(gyro));
    Test_FaceSampleMake(order[0], accel_bias, accel_scale, gyro,
                        accel);
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_FaceCollect(order[0]) ==
               SYSTEM_DEVICE_OK);
    Test_StableWindowFeed(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask ==
               (uint8_t)(1U << (uint8_t)order[0]));
    TEST_CHECK(SystemCalibration_Start(
        SYSTEM_CALIBRATION_MODE_SIX_FACE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_WAIT_FACE);
    TEST_CHECK(status.completed_face_mask == 0U);
    TEST_CHECK(status.ready == 0U);

    for (index = 0U; index < 6U; index++)
    {
        for (axis = 0U; axis < 3U; axis++)
        {
            gyro[axis] = gyro_bias[axis];
        }
        Test_FaceSampleMake(order[index], accel_bias, accel_scale,
                            gyro, accel);
        Test_SamplePush(accel, gyro);
        diagnostic_sequence = status.diagnostic_sequence;
        TEST_CHECK(SystemCalibration_FaceCollect(order[index]) ==
                   SYSTEM_DEVICE_OK);
        TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
        TEST_CHECK(status.diagnostic_face == order[index]);
        TEST_CHECK(status.diagnostic_reason ==
                   SYSTEM_CALIBRATION_WAIT_NO_STREAM);
        TEST_CHECK(status.diagnostic_sequence > diagnostic_sequence);
        Test_StableWindowFeed(accel, gyro);
        TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
        TEST_CHECK((status.completed_face_mask &
                    (uint8_t)(1U << (uint8_t)order[index])) != 0U);

        if (index == 1U)
        {
            uint8_t mask_before = status.completed_face_mask;
            float previous = status.six_face_measurements.
                gyro_mean_radps[SYSTEM_CALIBRATION_FACE_X_NEGATIVE][0];

            gyro[0] += 0.006f;
            Test_SamplePush(accel, gyro);
            invalidate_count = s_alignment_invalidate_count;
            TEST_CHECK(SystemCalibration_FaceCollect(order[index]) ==
                       SYSTEM_DEVICE_OK);
            TEST_CHECK(SystemCalibration_StatusGet(&status) ==
                       SYSTEM_DEVICE_OK);
            TEST_CHECK(status.completed_face_mask ==
                (uint8_t)(mask_before &
                    (uint8_t)(~(uint8_t)(1U <<
                        (uint8_t)order[index]))));
            TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_COLLECTING);
            TEST_CHECK(status.ready == 0U);
            TEST_CHECK(s_alignment_invalidate_count ==
                       (invalidate_count + 1U));
            Test_StableWindowFeed(accel, gyro);
            TEST_CHECK(SystemCalibration_StatusGet(&status) ==
                       SYSTEM_DEVICE_OK);
            TEST_CHECK(status.completed_face_mask == mask_before);
            TEST_CHECK(status.six_face_measurements.
                gyro_mean_radps[SYSTEM_CALIBRATION_FACE_X_NEGATIVE][0] >
                previous);
        }
    }
    SystemCalibration_Process();
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask == SYSTEM_CALIBRATION_FACE_MASK_ALL);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    ready_status = status;
    invalidate_count = s_alignment_invalidate_count;
    TEST_CHECK(SystemCalibration_FaceCollect(
        (SystemCalibrationFace)SYSTEM_CALIBRATION_FACE_COUNT) ==
        SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask == SYSTEM_CALIBRATION_FACE_MASK_ALL);
    TEST_CHECK(status.ready == 1U);
    TEST_CHECK(s_alignment_invalidate_count == invalidate_count);

    TEST_CHECK(SystemCalibration_FaceCollect(
        SYSTEM_CALIBRATION_FACE_X_POSITIVE) == SYSTEM_DEVICE_VERIFY_FAILED);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask == SYSTEM_CALIBRATION_FACE_MASK_ALL);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    TEST_CHECK(status.correction.ready == 1U);
    TEST_CHECK(s_alignment_invalidate_count == invalidate_count);

    (void)memcpy(gyro, gyro_bias, sizeof(gyro));
    gyro[1] += 0.006f;
    Test_FaceSampleMake(SYSTEM_CALIBRATION_FACE_X_POSITIVE,
                        accel_bias, accel_scale, gyro, accel);
    Test_SamplePush(accel, gyro);
    TEST_CHECK(SystemCalibration_FaceCollect(
        SYSTEM_CALIBRATION_FACE_X_POSITIVE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask ==
        (uint8_t)(SYSTEM_CALIBRATION_FACE_MASK_ALL &
                  (uint8_t)(~(uint8_t)(1U <<
                      SYSTEM_CALIBRATION_FACE_X_POSITIVE))));
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_COLLECTING);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(status.correction.ready == 0U);
    TEST_CHECK(s_alignment_invalidate_count == (invalidate_count + 1U));
    for (index = SYSTEM_CALIBRATION_FACE_X_NEGATIVE;
         index < SYSTEM_CALIBRATION_FACE_COUNT; index++)
    {
        for (axis = 0U; axis < 3U; axis++)
        {
            TEST_CHECK_NEAR(status.six_face_measurements.
                accel_mean_mps2[index][axis],
                ready_status.six_face_measurements.
                accel_mean_mps2[index][axis], 1.0e-7f);
            TEST_CHECK_NEAR(status.six_face_measurements.
                gyro_mean_radps[index][axis],
                ready_status.six_face_measurements.
                gyro_mean_radps[index][axis], 1.0e-7f);
        }
    }
    Test_StableWindowFeed(accel, gyro);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.completed_face_mask == SYSTEM_CALIBRATION_FACE_MASK_ALL);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    for (axis = 0U; axis < 3U; axis++)
    {
        float expected_gyro = gyro_bias[axis] +
            (((axis == 0U) || (axis == 1U)) ?
                (0.006f / 6.0f) : 0.0f);

        TEST_CHECK_NEAR(status.correction.accel_bias_mps2[axis],
                        accel_bias[axis], 1.0e-4f);
        TEST_CHECK_NEAR(status.correction.accel_scale[axis],
                        accel_scale[axis], 1.0e-4f);
        TEST_CHECK_NEAR(status.correction.gyro_bias_radps[axis],
                        expected_gyro, 1.0e-5f);
        TEST_CHECK_NEAR(status.correction.gyro_scale[axis], 1.0f, 1.0e-7f);
    }

    invalid = status.six_face_measurements;
    invalid.accel_mean_mps2[IMU_SIX_FACE_X_POSITIVE][0] =
        invalid.accel_mean_mps2[IMU_SIX_FACE_X_NEGATIVE][0];
    TEST_CHECK(ImuSixFace_CorrectionCalculate(&invalid,
        SYSTEM_LOCAL_GRAVITY_MPS2, SYSTEM_IMU_CAL_ACCEL_SCALE_MIN,
        SYSTEM_IMU_CAL_ACCEL_SCALE_MAX, &unused) ==
        IMU_SIX_FACE_RESULT_DENOMINATOR);
    invalid = status.six_face_measurements;
    invalid.accel_mean_mps2[0][0] = NAN;
    TEST_CHECK(ImuSixFace_CorrectionCalculate(&invalid,
        SYSTEM_LOCAL_GRAVITY_MPS2, SYSTEM_IMU_CAL_ACCEL_SCALE_MIN,
        SYSTEM_IMU_CAL_ACCEL_SCALE_MAX, &unused) ==
        IMU_SIX_FACE_RESULT_NONFINITE);

    TEST_CHECK(SystemCalibration_Start(
        SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mode == SYSTEM_CALIBRATION_MODE_ONE_FACE);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_COLLECTING);
    TEST_CHECK(status.completed_face_mask == 0U);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mode == SYSTEM_CALIBRATION_MODE_NONE);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    TEST_CHECK(SystemCalibration_Start(
        SYSTEM_CALIBRATION_MODE_SIX_FACE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mode == SYSTEM_CALIBRATION_MODE_SIX_FACE);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_WAIT_FACE);
    TEST_CHECK(status.completed_face_mask == 0U);
}

static void Test_ImuCorrection(void)
{
    const float raw_accel[3] = {2.0f, -3.0f, 4.0f};
    const float raw_gyro[3] = {0.5f, -0.25f, 1.0f};
    SystemCalibrationImuCorrection correction = {
        .accel_bias_mps2 = {1.0f, -1.0f, 0.5f},
        .gyro_bias_radps = {0.1f, -0.05f, 0.2f},
        .accel_scale = {2.0f, 0.5f, 1.5f},
        .gyro_scale = {0.5f, 2.0f, 1.25f}
    };
    float corrected_accel[3];
    float corrected_gyro[3];

    TEST_CHECK(SystemCalibration_CapabilityMaskGet() ==
               SYSTEM_CALIBRATION_CAPABILITY_MASK_ALL);
    TEST_CHECK(SystemCalibration_ImuCorrectionApply(
        raw_accel, raw_gyro, &correction, corrected_accel,
        corrected_gyro) == SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(corrected_accel[0], 2.0f, 1.0e-7f);
    TEST_CHECK_NEAR(corrected_accel[1], -1.0f, 1.0e-7f);
    TEST_CHECK_NEAR(corrected_accel[2], 5.25f, 1.0e-7f);
    TEST_CHECK_NEAR(corrected_gyro[0], 0.2f, 1.0e-7f);
    TEST_CHECK_NEAR(corrected_gyro[1], -0.4f, 1.0e-7f);
    TEST_CHECK_NEAR(corrected_gyro[2], 1.0f, 1.0e-7f);

    TEST_CHECK(SystemCalibration_ImuCorrectionApply(
        raw_accel, raw_gyro, NULL, corrected_accel,
        corrected_gyro) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    correction.accel_scale[0] = NAN;
    TEST_CHECK(SystemCalibration_ImuCorrectionApply(
        raw_accel, raw_gyro, &correction, corrected_accel,
        corrected_gyro) == SYSTEM_DEVICE_VERIFY_FAILED);
}

int main(void)
{
    SystemCalibrationStatus status;
    uint32_t diagnostic_sequence;

#ifdef TEST_EXPECT_DEFAULT_Y_POSITIVE
    TEST_CHECK(SYSTEM_IMU_STARTUP_GRAVITY_DIRECTION ==
               SYSTEM_AXIS_DIRECTION_Y_POSITIVE);
#endif
    SystemCalibration_Init();
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.mode == SYSTEM_CALIBRATION_MODE_NOT_SELECTED);
    TEST_CHECK(status.state == SYSTEM_CALIBRATION_STATE_IDLE);
    TEST_CHECK(status.ready == 0U);
    Test_None();
    Test_OneFace();
    Test_Rejections();
    Test_SixFace();
    Test_ImuCorrection();
    TEST_CHECK(SystemCalibration_Start(
        SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.diagnostic_reason ==
               SYSTEM_CALIBRATION_WAIT_NO_STREAM);
    diagnostic_sequence = status.diagnostic_sequence;
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(status.mode == SYSTEM_CALIBRATION_MODE_NOT_SELECTED);
    TEST_CHECK(status.diagnostic_reason == SYSTEM_CALIBRATION_WAIT_NONE);
    TEST_CHECK(status.diagnostic_sequence > diagnostic_sequence);
    TEST_CHECK(s_alignment_invalidate_count >= 6U);
    return Test_Finish("system_calibration");
}
