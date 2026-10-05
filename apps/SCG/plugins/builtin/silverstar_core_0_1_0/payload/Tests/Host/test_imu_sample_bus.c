#include <string.h>

#include "imu_sample_bus.h"
#include "system_calibration.h"
#include "system_lifecycle.h"
#include "test_common.h"

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif

static SystemInertialSample s_source_sample;
static uint8_t s_source_sample_pending;

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static FlightLogImuCorrectedRecord s_corrected_record;
static uint32_t s_corrected_record_count;
static uint64_t s_corrected_timestamp_us;
static uint32_t s_corrected_valid_flags;
#endif

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return SYSTEM_STATE_FLIGHT;
}

SystemDeviceResult SystemInertial_NextGet(SystemInertialSample *sample)
{
    if ((sample == NULL) || (s_source_sample_pending == 0U))
    {
        return (sample == NULL) ? SYSTEM_DEVICE_INVALID_ARGUMENT :
                                  SYSTEM_DEVICE_NOT_READY;
    }
    *sample = s_source_sample;
    s_source_sample_pending = 0U;
    return SYSTEM_DEVICE_OK;
}

void SystemCalibration_ImuSampleProcess(
    const SystemInertialSample *sample)
{
    (void)sample;
}

SystemDeviceResult SystemCalibration_StatusGet(
    SystemCalibrationStatus *status)
{
    uint8_t axis;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(status, 0, sizeof(*status));
    status->mode = SYSTEM_CALIBRATION_MODE_NONE;
    status->state = SYSTEM_CALIBRATION_STATE_READY;
    status->ready = 1U;
    status->correction.mode = SYSTEM_CALIBRATION_MODE_NONE;
    status->correction.ready = 1U;
    for (axis = 0U; axis < 3U; axis++)
    {
        status->correction.accel_scale[axis] = 1.0f;
        status->correction.gyro_scale[axis] = 1.0f;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionGet(
    SystemCalibrationImuCorrection *correction)
{
    SystemCalibrationStatus status;
    SystemDeviceResult result;

    if (correction == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    result = SystemCalibration_StatusGet(&status);
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    *correction = status.correction;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionApply(
    const float raw_accel_b_mps2[3],
    const float raw_gyro_b_radps[3],
    const SystemCalibrationImuCorrection *correction,
    float corrected_accel_b_mps2[3],
    float corrected_gyro_b_radps[3])
{
    uint8_t axis;

    if ((raw_accel_b_mps2 == NULL) || (raw_gyro_b_radps == NULL) ||
        (correction == NULL) || (corrected_accel_b_mps2 == NULL) ||
        (corrected_gyro_b_radps == NULL) || (correction->ready == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    for (axis = 0U; axis < 3U; axis++)
    {
        corrected_accel_b_mps2[axis] =
            (raw_accel_b_mps2[axis] -
             correction->accel_bias_mps2[axis]) *
            correction->accel_scale[axis];
        corrected_gyro_b_radps[axis] =
            (raw_gyro_b_radps[axis] -
             correction->gyro_bias_radps[axis]) *
            correction->gyro_scale[axis];
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Reset(void)
{
    return SYSTEM_DEVICE_OK;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
LoggerBusResult LoggerBus_ImuCorrectedPush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogImuCorrectedRecord *record)
{
    if (record == NULL)
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    s_corrected_record = *record;
    s_corrected_timestamp_us = timestamp_us;
    s_corrected_valid_flags = valid_flags;
    s_corrected_record_count++;
    return LOGGER_BUS_RESULT_OK;
}
#endif

static void Test_NoneCorrectionRecord(void)
{
    InsImuSample queued;
    uint8_t axis;

    (void)memset(&s_source_sample, 0, sizeof(s_source_sample));
    s_source_sample.sample_timestamp_us = 123456ULL;
    s_source_sample.receive_timestamp_us = 123460ULL;
    s_source_sample.sequence = 7U;
    s_source_sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL |
                                 SYSTEM_INERTIAL_VALID_GYRO;
    s_source_sample.accel_b_mps2[0] = 1.25f;
    s_source_sample.accel_b_mps2[1] = -2.5f;
    s_source_sample.accel_b_mps2[2] = 9.75f;
    s_source_sample.gyro_b_radps[0] = 0.1f;
    s_source_sample.gyro_b_radps[1] = -0.2f;
    s_source_sample.gyro_b_radps[2] = 0.3f;
    s_source_sample.temperature_c = 24.5f;
    s_source_sample_pending = 1U;
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    (void)memset(&s_corrected_record, 0, sizeof(s_corrected_record));
    s_corrected_record_count = 0U;
    s_corrected_timestamp_us = 0ULL;
    s_corrected_valid_flags = 0U;
#endif

    TEST_CHECK(ImuSampleBus_Init() == IMU_SAMPLE_BUS_RESULT_OK);
    ImuSampleBus_Reset();
    ImuSampleBus_Process();
    TEST_CHECK(ImuSampleBus_Pop(&queued) == IMU_SAMPLE_BUS_RESULT_OK);
    TEST_CHECK(queued.sequence == s_source_sample.sequence);

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    TEST_CHECK(s_corrected_record_count == 1U);
    TEST_CHECK(s_corrected_timestamp_us ==
               s_source_sample.sample_timestamp_us);
    TEST_CHECK(s_corrected_valid_flags == s_source_sample.valid_mask);
    TEST_CHECK(s_corrected_record.calibration_mode ==
               (uint8_t)SYSTEM_CALIBRATION_MODE_NONE);
    TEST_CHECK(s_corrected_record.correction_valid == 1U);
    TEST_CHECK(s_corrected_record.sequence == s_source_sample.sequence);
    for (axis = 0U; axis < 3U; axis++)
    {
        TEST_CHECK_NEAR(s_corrected_record.accel_b_mps2[axis],
                        s_source_sample.accel_b_mps2[axis], 1.0e-7f);
        TEST_CHECK_NEAR(s_corrected_record.gyro_b_radps[axis],
                        s_source_sample.gyro_b_radps[axis], 1.0e-7f);
    }
#else
    (void)axis;
#endif
}

int main(void)
{
    Test_NoneCorrectionRecord();
    return Test_Finish("imu_sample_bus");
}
