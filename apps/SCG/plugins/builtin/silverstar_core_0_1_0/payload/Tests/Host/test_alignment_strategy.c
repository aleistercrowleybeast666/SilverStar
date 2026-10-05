#include <string.h>

#include "alignment_strategy_binding.h"
#include "test_common.h"

static void Test_ConfigInit(AlignmentStrategyConfig *config)
{
    (void)memset(config, 0, sizeof(*config));
    config->minimum_samples = 2U;
    config->maximum_samples = 4U;
    config->minimum_duration_us = 1000U;
    config->maximum_gap_us = 5000U;
    config->gravity_mps2 = 9.78f;
    config->acceleration_tolerance_mps2 = 0.5f;
    config->maximum_gyro_radps = 0.1f;
    config->maximum_quaternion_deviation_rad = 0.1f;
    config->maximum_tilt_error_rad = 0.1f;
    config->known_yaw_deg = 0.0f;
    config->known_yaw_body_axis = 1;
    config->magnetic_magnitude_min_uT = 10.0f;
    config->magnetic_magnitude_max_uT = 100.0f;
    config->magnetic_magnitude_max_deviation_ratio = 0.2f;
    config->magnetic_direction_min_dot = 0.9f;
    config->magnetic_horizontal_min_ratio = 0.1f;
}

static void Test_SampleInit(AlignmentStrategySample *sample)
{
    (void)memset(sample, 0, sizeof(*sample));
    sample->timestamp_us = 1000ULL;
    sample->acceleration_b_mps2[2] = 9.78f;
    sample->magnetometer_timestamp_us = sample->timestamp_us;
    sample->magnetometer_sequence = 1U;
    sample->magnetic_field_b_uT[0] = 30.0f;
    sample->magnetometer_available = 1U;
    sample->magnetometer_calibrated = 1U;
    sample->quaternion_timestamp_us = sample->timestamp_us;
    sample->quaternion_sequence = 1U;
    sample->quaternion_wxyz[0] = 1.0f;
    sample->quaternion_available = 1U;
    sample->quaternion_mode = 1U;
    sample->quaternion_mode_verified = 1U;
}

static void Test_SelectedRequirements(void)
{
#if defined(TEST_ALIGNMENT_GRAVITY_MAG)
    TEST_CHECK(AlignmentStrategy_MagnetometerRequired() == 1U);
    TEST_CHECK(AlignmentStrategy_HardwareQuaternionRequired() == 0U);
#elif defined(TEST_ALIGNMENT_HW_QUAT)
    TEST_CHECK(AlignmentStrategy_MagnetometerRequired() == 0U);
    TEST_CHECK(AlignmentStrategy_HardwareQuaternionRequired() == 1U);
#else
    TEST_CHECK(AlignmentStrategy_MagnetometerRequired() == 0U);
    TEST_CHECK(AlignmentStrategy_HardwareQuaternionRequired() == 0U);
#endif
}

static void Test_ReadyWindow(void)
{
    AlignmentStrategyContext context;
    AlignmentStrategyConfig config;
    AlignmentStrategySample sample;
    AlignmentStrategyOutput output;
    AlignmentStrategyProcessResult result;

    Test_ConfigInit(&config);
    Test_SampleInit(&sample);
    AlignmentStrategy_Init(&context);
    TEST_CHECK(AlignmentStrategy_SampleProcess(
        NULL, &config, &sample, &output) ==
        ALIGNMENT_STRATEGY_PROCESS_INVALID);
    result = AlignmentStrategy_SampleProcess(
        &context, &config, &sample, &output);
    TEST_CHECK(result == ALIGNMENT_STRATEGY_PROCESS_ACCEPTED);
    sample.timestamp_us += 1000ULL;
    sample.magnetometer_timestamp_us = sample.timestamp_us;
    sample.magnetometer_sequence++;
    sample.quaternion_timestamp_us = sample.timestamp_us;
    sample.quaternion_sequence++;
    result = AlignmentStrategy_SampleProcess(
        &context, &config, &sample, &output);
    TEST_CHECK(result == ALIGNMENT_STRATEGY_PROCESS_READY);
    TEST_CHECK(output.sample_count == 2U);
    TEST_CHECK_NEAR(
        (output.q_nb[0] * output.q_nb[0]) +
        (output.q_nb[1] * output.q_nb[1]) +
        (output.q_nb[2] * output.q_nb[2]) +
        (output.q_nb[3] * output.q_nb[3]),
        1.0f, 0.001f);
#if defined(TEST_ALIGNMENT_GRAVITY_MAG)
    TEST_CHECK(output.magnetic_field_valid == 1U);
#elif defined(TEST_ALIGNMENT_HW_QUAT)
    TEST_CHECK(output.hardware_mode == 1U);
    TEST_CHECK(output.hardware_mode_verified == 1U);
#endif
}

int main(void)
{
    Test_SelectedRequirements();
    Test_ReadyWindow();
    return Test_Finish("alignment_strategy");
}
