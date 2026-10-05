#include <string.h>

#include "system_imu_if.h"
#include "system_inertial.h"
#include "test_common.h"

static SystemImuSample s_device_sample;

static SystemDeviceResult Test_LatestGet(SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_device_sample;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_NextGet(SystemImuSample *sample)
{
    return Test_LatestGet(sample);
}

SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample)
{
    return Test_LatestGet(sample);
}

SystemDeviceResult SystemImu_NextSampleGet(SystemImuSample *sample)
{
    return Test_NextGet(sample);
}

static void Test_IdentitySet(float matrix[3][3])
{
    uint8_t axis;

    (void)memset(matrix, 0, sizeof(float) * 9U);
    for (axis = 0U; axis < 3U; axis++)
    {
        matrix[axis][axis] = 1.0f;
    }
}

int main(void)
{
    SystemInertialSample latest;
    SystemInertialSample next;
    SystemInertialSourceSample measured;
    SystemInertialSourceSample corrected;
    SystemInertialSourceCorrection correction;
    uint8_t axis;

    (void)memset(&s_device_sample, 0, sizeof(s_device_sample));
    s_device_sample.sample_timestamp_us = 123456ULL;
    s_device_sample.receive_timestamp_us = 123500ULL;
    s_device_sample.sequence = 77U;
    s_device_sample.temperature_c = 31.25f;
    s_device_sample.valid_mask = SYSTEM_IMU_VALID_ACCEL |
                                   SYSTEM_IMU_VALID_GYRO |
                                   SYSTEM_IMU_VALID_TEMPERATURE;
    for (axis = 0U; axis < 3U; axis++)
    {
        s_device_sample.accel_raw[axis] = 100 + axis;
        s_device_sample.gyro_raw[axis] = -100 - axis;
        s_device_sample.accel_b_mps2[axis] = 1.25f + axis;
        s_device_sample.gyro_b_radps[axis] = -0.25f - axis;
    }
    TEST_CHECK(SystemInertial_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemInertial_LatestGet(&latest) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemInertial_NextGet(&next) == SYSTEM_DEVICE_OK);
    TEST_CHECK(latest.sample_timestamp_us ==
               s_device_sample.sample_timestamp_us);
    TEST_CHECK(latest.receive_timestamp_us ==
               s_device_sample.receive_timestamp_us);
    TEST_CHECK(latest.sequence == s_device_sample.sequence);
    TEST_CHECK(latest.valid_mask == s_device_sample.valid_mask);
    TEST_CHECK(memcmp(latest.accel_raw, s_device_sample.accel_raw,
                      sizeof(latest.accel_raw)) == 0);
    TEST_CHECK(memcmp(latest.gyro_raw, s_device_sample.gyro_raw,
                      sizeof(latest.gyro_raw)) == 0);
    TEST_CHECK(memcmp(latest.accel_b_mps2,
                      s_device_sample.accel_b_mps2,
                      sizeof(latest.accel_b_mps2)) == 0);
    TEST_CHECK(memcmp(latest.gyro_b_radps,
                      s_device_sample.gyro_b_radps,
                      sizeof(latest.gyro_b_radps)) == 0);
    TEST_CHECK(next.sample_timestamp_us == latest.sample_timestamp_us &&
               next.receive_timestamp_us == latest.receive_timestamp_us &&
               next.sequence == latest.sequence &&
               next.valid_mask == latest.valid_mask &&
               next.temperature_c == latest.temperature_c);
    TEST_CHECK(memcmp(next.accel_b_mps2, latest.accel_b_mps2,
                      sizeof(next.accel_b_mps2)) == 0);
    TEST_CHECK(memcmp(next.gyro_b_radps, latest.gyro_b_radps,
                      sizeof(next.gyro_b_radps)) == 0);

    (void)memset(&measured, 0, sizeof(measured));
    measured.source_id = 9U;
    measured.sequence = 12U;
    measured.sample_timestamp_us = 5000ULL;
    measured.receive_timestamp_us = 5100ULL;
    measured.timestamp_quality = SYSTEM_INERTIAL_TIMESTAMP_DRDY_CAPTURE;
    measured.valid_mask = SYSTEM_INERTIAL_SOURCE_VALID_6DOF;
    measured.accel_mps2[0] = 2.0f;
    measured.accel_mps2[1] = 4.0f;
    measured.accel_mps2[2] = 6.0f;
    measured.gyro_radps[0] = 1.0f;
    measured.gyro_radps[1] = 2.0f;
    measured.gyro_radps[2] = 3.0f;
    TEST_CHECK((measured.valid_mask &
                SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ) ==
               SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ);
    measured.valid_mask = SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ;
    TEST_CHECK((measured.valid_mask &
                SYSTEM_INERTIAL_SOURCE_VALID_GYRO_XYZ) == 0U);
    measured.valid_mask = SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X;
    TEST_CHECK(measured.valid_mask == SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X);
    measured.valid_mask = SYSTEM_INERTIAL_SOURCE_VALID_6DOF;

    (void)memset(&correction, 0, sizeof(correction));
    Test_IdentitySet(correction.accel_matrix);
    Test_IdentitySet(correction.gyro_matrix);
    correction.accel_bias_mps2[0] = 1.0f;
    correction.accel_bias_mps2[1] = 1.0f;
    correction.accel_bias_mps2[2] = 1.0f;
    correction.gyro_bias_radps[0] = 1.0f;
    correction.gyro_bias_radps[1] = 1.0f;
    correction.gyro_bias_radps[2] = 1.0f;

    correction.mode = SYSTEM_INERTIAL_CORRECTION_NONE;
    TEST_CHECK(SystemInertialSource_CorrectionApply(
        &measured, &correction, &corrected) == SYSTEM_DEVICE_OK);
    TEST_CHECK(memcmp(&measured, &corrected, sizeof(measured)) == 0);

    correction.mode = SYSTEM_INERTIAL_CORRECTION_BIAS_ONLY;
    TEST_CHECK(SystemInertialSource_CorrectionApply(
        &measured, &correction, &corrected) == SYSTEM_DEVICE_OK);
    TEST_CHECK(corrected.accel_mps2[0] == 1.0f &&
               corrected.accel_mps2[1] == 3.0f &&
               corrected.accel_mps2[2] == 5.0f);
    TEST_CHECK(corrected.gyro_radps[0] == 0.0f &&
               corrected.gyro_radps[1] == 1.0f &&
               corrected.gyro_radps[2] == 2.0f);

    correction.mode = SYSTEM_INERTIAL_CORRECTION_DIAGONAL;
    correction.accel_matrix[0][0] = 2.0f;
    correction.accel_matrix[1][1] = 2.0f;
    correction.accel_matrix[2][2] = 2.0f;
    TEST_CHECK(SystemInertialSource_CorrectionApply(
        &measured, &correction, &corrected) == SYSTEM_DEVICE_OK);
    TEST_CHECK(corrected.accel_mps2[0] == 2.0f &&
               corrected.accel_mps2[1] == 6.0f &&
               corrected.accel_mps2[2] == 10.0f);

    correction.mode = SYSTEM_INERTIAL_CORRECTION_FULL_MATRIX;
    Test_IdentitySet(correction.accel_matrix);
    correction.accel_matrix[0][0] = 0.0f;
    correction.accel_matrix[0][1] = 1.0f;
    correction.accel_matrix[1][0] = 1.0f;
    correction.accel_matrix[1][1] = 0.0f;
    TEST_CHECK(SystemInertialSource_CorrectionApply(
        &measured, &correction, &corrected) == SYSTEM_DEVICE_OK);
    TEST_CHECK(corrected.accel_mps2[0] == 3.0f &&
               corrected.accel_mps2[1] == 1.0f &&
               corrected.accel_mps2[2] == 5.0f);
    measured.valid_mask = SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X;
    TEST_CHECK(SystemInertialSource_CorrectionApply(
        &measured, &correction, &corrected) == SYSTEM_DEVICE_UNSUPPORTED);
    return Test_Finish("system_inertial");
}
