#include <math.h>
#include <stdint.h>
#include <string.h>

#include "attitude_alignment.h"
#include "alignment_gravity_known_yaw.h"
#include "attitude_frame.h"
#include "attitude_preflight.h"
#include "attitude_triad.h"
#include "system_user_config.h"
#include "test_common.h"

#define TEST_PI 3.14159265358979323846f
#define TEST_DEG_TO_RAD 0.01745329251994329577f

static AttitudeAlignmentWindowConfig Test_WindowConfigGet(void)
{
    AttitudeAlignmentWindowConfig config;

    (void)memset(&config, 0, sizeof(config));
    config.minimum_samples = 100U;
    config.maximum_samples = 128U;
    config.minimum_duration_us = 500000U;
    config.maximum_gap_us = 10000U;
    config.gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2;
    config.acceleration_tolerance_mps2 = 0.5f;
    config.maximum_gyro_radps = 0.1f;
    config.maximum_quaternion_deviation_rad = 0.0872664626f;
    return config;
}

static AttitudeTriadConfig Test_TriadConfigGet(void)
{
    AttitudeTriadConfig config;

    (void)memset(&config, 0, sizeof(config));
    config.minimum_samples = 100U;
    config.maximum_samples = 128U;
    config.minimum_duration_us = 500000U;
    config.maximum_gap_us = 10000U;
    config.gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2;
    config.acceleration_tolerance_mps2 = 0.5f;
    config.maximum_gyro_radps = 0.1f;
    config.magnetic_magnitude_min_uT = 10.0f;
    config.magnetic_magnitude_max_uT = 100.0f;
    config.magnetic_magnitude_max_deviation_ratio = 0.2f;
    config.magnetic_direction_min_dot = 0.9f;
    config.magnetic_horizontal_min_ratio = 0.1f;
    return config;
}

static void Test_QuaternionFromYaw(float yaw_deg, float q_nb[4])
{
    float half = 0.5f * yaw_deg * TEST_DEG_TO_RAD;

    q_nb[0] = cosf(half);
    q_nb[1] = 0.0f;
    q_nb[2] = 0.0f;
    q_nb[3] = sinf(half);
}

static float Test_AngleDifference(float lhs, float rhs)
{
    float difference = lhs - rhs;

    while (difference > TEST_PI) { difference -= 2.0f * TEST_PI; }
    while (difference < -TEST_PI) { difference += 2.0f * TEST_PI; }
    return fabsf(difference);
}

static void Test_YawCardinalAndSign(void)
{
    static const float yaw_deg[] = {0.0f, 90.0f, -90.0f, 180.0f};
    float q_nb[4];
    float q_negative[4];
    float yaw_rad;
    float yaw_negative_rad;
    uint8_t quaternion_index;
    uint8_t index;

    for (index = 0U; index < 4U; index++)
    {
        Test_QuaternionFromYaw(yaw_deg[index], q_nb);
        for (quaternion_index = 0U; quaternion_index < 4U;
             quaternion_index++)
        {
            q_negative[quaternion_index] = -q_nb[quaternion_index];
        }
        TEST_CHECK(Attitude_YawEnuFromQuaternion(q_nb, &yaw_rad) ==
                   ATTITUDE_YAW_RESULT_OK);
        TEST_CHECK(Attitude_YawEnuFromQuaternion(
            q_negative, &yaw_negative_rad) == ATTITUDE_YAW_RESULT_OK);
        TEST_CHECK(Test_AngleDifference(
            yaw_rad, yaw_deg[index] * TEST_DEG_TO_RAD) < 1.0e-5f);
        TEST_CHECK(Test_AngleDifference(yaw_rad, yaw_negative_rad) <
                   1.0e-6f);
    }
}

static void Test_YawSingularity(void)
{
    const float body_x_up_q[4] =
        {0.70710678f, 0.0f, -0.70710678f, 0.0f};
    float yaw_rad = 123.0f;

    TEST_CHECK(Attitude_YawEnuFromQuaternion(
        body_x_up_q, &yaw_rad) == ATTITUDE_YAW_RESULT_SINGULAR);
    TEST_CHECK(isfinite(yaw_rad));
    TEST_CHECK(Attitude_YawEnuFromQuaternion(NULL, &yaw_rad) ==
               ATTITUDE_YAW_RESULT_BAD_PARAM);
}

static void Test_GravityKnownYaw(float yaw_deg)
{
    AttitudeAlignmentWindow context;
    AttitudeAlignmentWindowConfig config = Test_WindowConfigGet();
    float acceleration[3] = {0.0f, 0.0f, SYSTEM_LOCAL_GRAVITY_MPS2};
    float gyro[3] = {0.0f, 0.0f, 0.0f};
    float acceleration_average[3];
    float gyro_average[3];
    float q_nb[4];
    float body_x[3] = {1.0f, 0.0f, 0.0f};
    float body_x_n[3];
    float acceleration_n[3];
    float yaw_rad;
    uint16_t index;

    AttitudeAlignmentWindow_Init(&context);
    for (index = 0U; index < 101U; index++)
    {
        TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
            &context, &config, 1000000ULL + ((uint64_t)index * 5000ULL),
            acceleration, gyro) != 0U);
    }
    TEST_CHECK(context.valid != 0U);
    TEST_CHECK(AttitudeAlignmentWindow_GetInertialAverage(
        &context, acceleration_average, gyro_average) != 0U);
    TEST_CHECK(AttitudeAlignment_GravityKnownYawBuild(
        acceleration_average, yaw_deg, q_nb) != 0U);
    TEST_CHECK_NEAR(sqrtf(Attitude_QuaternionDot(q_nb, q_nb)),
                    1.0f, 1.0e-6f);
    Attitude_RotateVector(q_nb, acceleration_average, acceleration_n);
    TEST_CHECK_NEAR(acceleration_n[0], 0.0f, 1.0e-4f);
    TEST_CHECK_NEAR(acceleration_n[1], 0.0f, 1.0e-4f);
    TEST_CHECK(acceleration_n[2] > 0.0f);
    Attitude_RotateVector(q_nb, body_x, body_x_n);
    TEST_CHECK_NEAR(body_x_n[0], cosf(yaw_deg * TEST_DEG_TO_RAD),
                    1.0e-5f);
    TEST_CHECK_NEAR(body_x_n[1], sinf(yaw_deg * TEST_DEG_TO_RAD),
                    1.0e-5f);
    TEST_CHECK(Attitude_YawEnuFromQuaternion(q_nb, &yaw_rad) ==
               ATTITUDE_YAW_RESULT_OK);
    TEST_CHECK(Test_AngleDifference(
        yaw_rad, yaw_deg * TEST_DEG_TO_RAD) < 1.0e-5f);
}

static void Test_GravityKnownYawWindowQuality(void)
{
    AttitudeAlignmentWindow context;
    AttitudeAlignmentWindowConfig config = Test_WindowConfigGet();
    float acceleration[3] = {0.0f, 0.0f, SYSTEM_LOCAL_GRAVITY_MPS2};
    float gyro[3] = {0.0f, 0.0f, 0.0f};

    AttitudeAlignmentWindow_Init(&context);
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &context, &config, 1000ULL, acceleration, gyro) != 0U);
    TEST_CHECK(context.valid == 0U);
    gyro[0] = 0.2f;
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &context, &config, 6000ULL, acceleration, gyro) == 0U);
    TEST_CHECK(context.reject_count == 1U);
    TEST_CHECK(context.valid == 0U);
    gyro[0] = 0.0f;
    acceleration[2] = SYSTEM_LOCAL_GRAVITY_MPS2 + 1.0f;
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &context, &config, 11000ULL, acceleration, gyro) == 0U);
    TEST_CHECK(context.reject_count == 2U);
}

static void Test_GravityKnownYawTiltedAndSingular(void)
{
    const float yaw_deg = 37.0f;
    const float vertical_component = 0.8660254038f;
    float acceleration_b[3] = {
        0.3f * SYSTEM_LOCAL_GRAVITY_MPS2,
        -0.4f * SYSTEM_LOCAL_GRAVITY_MPS2,
        vertical_component * SYSTEM_LOCAL_GRAVITY_MPS2
    };
    float singular_acceleration_b[3] = {
        SYSTEM_LOCAL_GRAVITY_MPS2, 0.0f, 0.0f
    };
    float acceleration_n[3];
    float q_nb[4];
    float yaw_rad;

    TEST_CHECK(AttitudeAlignment_GravityKnownYawBuild(
        acceleration_b, yaw_deg, q_nb) != 0U);
    Attitude_RotateVector(q_nb, acceleration_b, acceleration_n);
    TEST_CHECK_NEAR(acceleration_n[0], 0.0f, 1.0e-4f);
    TEST_CHECK_NEAR(acceleration_n[1], 0.0f, 1.0e-4f);
    TEST_CHECK_NEAR(acceleration_n[2], SYSTEM_LOCAL_GRAVITY_MPS2,
                    1.0e-4f);
    TEST_CHECK(Attitude_YawEnuFromQuaternion(q_nb, &yaw_rad) ==
               ATTITUDE_YAW_RESULT_OK);
    TEST_CHECK(Test_AngleDifference(
        yaw_rad, yaw_deg * TEST_DEG_TO_RAD) < 1.0e-5f);

    /* Body +X vertical has no horizontal projection, so ENU yaw is
       intentionally undefined rather than silently invented. */
    TEST_CHECK(AttitudeAlignment_GravityKnownYawBuild(
        singular_acceleration_b, yaw_deg, q_nb) == 0U);
}

static void Test_AlignmentWindowRejectResets(void)
{
    AttitudeAlignmentWindow context;
    AttitudeAlignmentWindowConfig config = Test_WindowConfigGet();
    float acceleration[3] = {0.0f, 0.0f, SYSTEM_LOCAL_GRAVITY_MPS2};
    float gyro[3] = {0.0f, 0.0f, 0.0f};
    float q_reference[4];
    float q_deviated[4];

    AttitudeAlignmentWindow_Init(&context);
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &context, &config, 1000ULL, acceleration, gyro) != 0U);
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &context, &config, 12000ULL, acceleration, gyro) == 0U);
    TEST_CHECK(context.reject_count == 1U);
    TEST_CHECK(context.sample_count == 0U);
    TEST_CHECK(context.valid == 0U);
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &context, &config, 13000ULL, acceleration, gyro) != 0U);
    TEST_CHECK(context.reject_count == 1U);
    TEST_CHECK(context.sample_count == 1U);

    Test_QuaternionFromYaw(0.0f, q_reference);
    Test_QuaternionFromYaw(20.0f, q_deviated);
    AttitudeAlignmentWindow_Init(&context);
    TEST_CHECK(AttitudeAlignmentWindow_Add(
        &context, &config, 20000ULL, acceleration, gyro,
        q_reference) != 0U);
    TEST_CHECK(AttitudeAlignmentWindow_Add(
        &context, &config, 25000ULL, acceleration, gyro,
        q_deviated) == 0U);
    TEST_CHECK(context.reject_count == 1U);
    TEST_CHECK(context.sample_count == 0U);
    TEST_CHECK(context.valid == 0U);
}

static void Test_HardwareQuaternionWindowSignAlignment(void)
{
    AttitudeAlignmentWindow context;
    AttitudeAlignmentWindowConfig config = Test_WindowConfigGet();
    float acceleration[3] = {0.0f, 0.0f, SYSTEM_LOCAL_GRAVITY_MPS2};
    float gyro[3] = {0.0f, 0.0f, 0.0f};
    float quaternion[4];
    float sample_q[4];
    float q_average[4];
    float acceleration_average[3];
    float gyro_average[3];
    uint8_t component;
    uint16_t index;

    Test_QuaternionFromYaw(30.0f, quaternion);
    AttitudeAlignmentWindow_Init(&context);
    for (index = 0U; index < 101U; index++)
    {
        for (component = 0U; component < 4U; component++)
        {
            sample_q[component] = ((index & 1U) != 0U) ?
                -quaternion[component] : quaternion[component];
        }
        TEST_CHECK(AttitudeAlignmentWindow_Add(
            &context, &config, 1000000ULL + ((uint64_t)index * 5000ULL),
            acceleration, gyro, sample_q) != 0U);
    }
    TEST_CHECK(AttitudeAlignmentWindow_GetAverage(
        &context, q_average, acceleration_average, gyro_average) != 0U);
    TEST_CHECK(fabsf(Attitude_QuaternionDot(q_average, quaternion)) >
               0.99999f);
}

static void Test_TriadDeclination(float declination_deg)
{
    AttitudeTriadAccumulator context;
    AttitudeTriadConfig config = Test_TriadConfigGet();
    float accel[3] = {0.0f, 0.0f, SYSTEM_LOCAL_GRAVITY_MPS2};
    float gyro[3] = {0.0f, 0.0f, 0.0f};
    float mag[3];
    float q_nb[4];
    float body_x[3] = {1.0f, 0.0f, 0.0f};
    float body_x_n[3];
    float declination_rad = declination_deg * TEST_DEG_TO_RAD;
    uint16_t index;

    /* For identity body-to-ENU, magnetic north is east of true north by
       positive declination.  No hardware quaternion is supplied. */
    mag[0] = 50.0f * sinf(declination_rad);
    mag[1] = 50.0f * cosf(declination_rad);
    mag[2] = 0.0f;
    AttitudeTriad_Init(&context);
    for (index = 0U; index < 101U; index++)
    {
        TEST_CHECK(AttitudeTriad_AddStaticSample(
            &context, &config,
            2000000ULL + ((uint64_t)index * 5000ULL),
            accel, gyro, mag, 1U) != 0U);
    }
    TEST_CHECK(context.valid != 0U);
    TEST_CHECK(AttitudeTriad_BuildBodyToEnu(
        &context, declination_deg, q_nb) != 0U);
    Attitude_RotateVector(q_nb, body_x, body_x_n);
    TEST_CHECK_NEAR(body_x_n[0], 1.0f, 1.0e-5f);
    TEST_CHECK_NEAR(body_x_n[1], 0.0f, 1.0e-5f);
}

static void Test_TriadMagQualityIsolation(void)
{
    AttitudeTriadAccumulator triad;
    AttitudeTriadConfig triad_config = Test_TriadConfigGet();
    AttitudeAlignmentWindow gravity_window;
    AttitudeAlignmentWindowConfig window_config = Test_WindowConfigGet();
    float accel[3] = {0.0f, 0.0f, SYSTEM_LOCAL_GRAVITY_MPS2};
    float gyro[3] = {0.0f, 0.0f, 0.0f};
    float bad_mag[3] = {0.0f, 0.0f, 500.0f};

    AttitudeTriad_Init(&triad);
    TEST_CHECK(AttitudeTriad_AddStaticSample(
        &triad, &triad_config, 1000ULL,
        accel, gyro, bad_mag, 1U) == 0U);
    TEST_CHECK(triad.reject_count == 1U);

    AttitudeAlignmentWindow_Init(&gravity_window);
    TEST_CHECK(AttitudeAlignmentWindow_AddInertial(
        &gravity_window, &window_config, 1000ULL,
        accel, gyro) != 0U);
    TEST_CHECK(gravity_window.reject_count == 0U);
}

static AttitudePreflightSample Test_PreflightSampleMake(
    const float quaternion[4],
    uint64_t timestamp_us,
    uint32_t sequence)
{
    AttitudePreflightSample sample;

    (void)memset(&sample, 0, sizeof(sample));
    (void)memcpy(sample.quaternion_wxyz, quaternion,
                 sizeof(sample.quaternion_wxyz));
    sample.sample_timestamp_us = timestamp_us;
    sample.receive_timestamp_us = timestamp_us + 100U;
    sample.sequence = sequence;
    sample.valid = 1U;
    return sample;
}

static void Test_FinalQuaternionFreeze(void)
{
    float final_q[4];
    float later_hardware_q[4];
    AttitudePreflightContext preflight;
    AttitudePreflightSample sample;
    AttitudePreflightSample mission;

    Test_QuaternionFromYaw(45.0f, final_q);
    Test_QuaternionFromYaw(-80.0f, later_hardware_q);
    AttitudePreflight_Init(&preflight);
    sample = Test_PreflightSampleMake(final_q, 2000000ULL, 2U);
    TEST_CHECK(AttitudePreflight_LatestUpdate(&preflight, &sample) ==
               ATTITUDE_PREFLIGHT_RESULT_OK);
    TEST_CHECK(AttitudePreflight_MissionFreeze(
        &preflight, 5000000ULL, UINT64_MAX) ==
        ATTITUDE_PREFLIGHT_RESULT_OK);
    sample = Test_PreflightSampleMake(later_hardware_q, 5010000ULL, 3U);
    TEST_CHECK(AttitudePreflight_LatestUpdate(&preflight, &sample) ==
               ATTITUDE_PREFLIGHT_RESULT_FROZEN);
    TEST_CHECK(AttitudePreflight_MissionGet(&preflight, &mission) != 0U);
    TEST_CHECK(fabsf(Attitude_QuaternionDot(
        mission.quaternion_wxyz, final_q)) > 0.99999f);
}

int main(void)
{
    Test_YawCardinalAndSign();
    Test_YawSingularity();
    Test_GravityKnownYaw(0.0f);
    Test_GravityKnownYaw(90.0f);
    Test_GravityKnownYaw(-90.0f);
    Test_GravityKnownYaw(180.0f);
    Test_GravityKnownYawWindowQuality();
    Test_GravityKnownYawTiltedAndSingular();
    Test_AlignmentWindowRejectResets();
    Test_HardwareQuaternionWindowSignAlignment();
    Test_TriadDeclination(0.0f);
    Test_TriadDeclination(15.0f);
    Test_TriadDeclination(-15.0f);
    Test_TriadMagQualityIsolation();
    Test_FinalQuaternionFreeze();
    return Test_Finish("attitude_alignment");
}
