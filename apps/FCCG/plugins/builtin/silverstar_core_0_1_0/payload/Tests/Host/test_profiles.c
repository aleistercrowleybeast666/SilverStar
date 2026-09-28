#include <math.h>
#include <stdint.h>
#include <stdio.h>

#include "system_estimator_profile.h"
#include "system_log_policy.h"
#include "system_navigation_profile.h"
#include "system_profile.h"
#include "target_build_capabilities.h"
#include "test_common.h"

static int FloatClose(float lhs, float rhs)
{
    return fabsf(lhs - rhs) < 1.0e-6f;
}

static void Test_EstimatorNoiseProfile(
    const SystemEstimatorProfile *estimator)
{
#ifdef TEST_EXPECT_ESTIMATOR_NOISE_OVERRIDES
    TEST_CHECK(FloatClose(estimator->process_accel_std_mps2[0], 0.8f));
    TEST_CHECK(FloatClose(estimator->process_accel_std_mps2[1], 0.9f));
    TEST_CHECK(FloatClose(estimator->process_accel_std_mps2[2], 1.1f));
    TEST_CHECK(FloatClose(
        estimator->gnss_horizontal_position_std_floor_m, 0.7f));
    TEST_CHECK(FloatClose(
        estimator->gnss_vertical_position_std_floor_m, 1.2f));
    TEST_CHECK(FloatClose(estimator->gnss_velocity_std_floor_mps, 0.08f));
    TEST_CHECK(FloatClose(estimator->barometer_altitude_std_m, 3.5f));
#else
    TEST_CHECK(FloatClose(estimator->process_accel_std_mps2[0],
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_VALUE));
    TEST_CHECK(FloatClose(estimator->process_accel_std_mps2[1],
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_VALUE));
    TEST_CHECK(FloatClose(estimator->process_accel_std_mps2[2],
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_VALUE));
    TEST_CHECK(FloatClose(estimator->gnss_horizontal_position_std_floor_m,
        SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_VALUE));
    TEST_CHECK(FloatClose(estimator->gnss_vertical_position_std_floor_m,
        SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_VALUE));
    TEST_CHECK(FloatClose(estimator->gnss_velocity_std_floor_mps,
        SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_VALUE));
    TEST_CHECK(FloatClose(estimator->barometer_altitude_std_m,
        SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_VALUE));
#endif
}

static void Test_GnssDynamicUncertainty(void)
{
    const SystemEstimatorProfile *estimator = SystemEstimatorProfile_Get();
    float horizontal_floor_result = SystemEstimatorProfile_GnssStdResolve(
        SYSTEM_ESTIMATOR_GNSS_STD_HORIZONTAL_POSITION, 0.01f);
    float horizontal_live_result = SystemEstimatorProfile_GnssStdResolve(
        SYSTEM_ESTIMATOR_GNSS_STD_HORIZONTAL_POSITION, 4.0f);
    float vertical_live_result = SystemEstimatorProfile_GnssStdResolve(
        SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_POSITION, 6.0f);
    float velocity_live_result = SystemEstimatorProfile_GnssStdResolve(
        SYSTEM_ESTIMATOR_GNSS_STD_VELOCITY, 0.5f);

    TEST_CHECK(FloatClose(horizontal_floor_result,
        estimator->gnss_horizontal_position_std_floor_m));
    TEST_CHECK(FloatClose(horizontal_live_result,
        4.0f * estimator->gnss_accuracy_scale));
    TEST_CHECK(FloatClose(vertical_live_result,
        6.0f * estimator->gnss_accuracy_scale));
    TEST_CHECK(FloatClose(velocity_live_result,
        0.5f * estimator->gnss_accuracy_scale));
}

int main(void)
{
    const SystemNavigationProfile *navigation =
        SystemNavigationProfile_Get();
    const SystemEstimatorProfile *estimator =
        SystemEstimatorProfile_Get();
    const SystemProfile *system = SystemProfile_Get();

    TEST_CHECK(navigation != NULL);
    TEST_CHECK(estimator != NULL);
    TEST_CHECK(system != NULL);

    TEST_CHECK(navigation->alignment_algorithm ==
               SYSTEM_ALIGNMENT_ALGORITHM);
    TEST_CHECK(SYSTEM_ALIGNMENT_ALGORITHM ==
               SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW);
    TEST_CHECK(FloatClose(SYSTEM_ALIGNMENT_KNOWN_YAW_DEG, 0.0f));
    TEST_CHECK(navigation->alignment_minimum_samples ==
               SYSTEM_ALIGNMENT_WINDOW_MIN_SAMPLES);
    TEST_CHECK(navigation->alignment_maximum_samples ==
               SYSTEM_ALIGNMENT_WINDOW_MAX_SAMPLES);
    TEST_CHECK(navigation->attitude_policy == SYSTEM_ATTITUDE_POLICY);
    TEST_CHECK(navigation->mechanization_algorithm ==
               SYSTEM_MECHANIZATION_ALGORITHM);
    TEST_CHECK(navigation->fusion_algorithm == SYSTEM_FUSION_ALGORITHM);
    TEST_CHECK(FloatClose(navigation->known_yaw_deg,
                          SYSTEM_ALIGNMENT_KNOWN_YAW_DEG));
    TEST_CHECK(navigation->known_yaw_body_axis ==
               SYSTEM_ALIGNMENT_KNOWN_YAW_BODY_AXIS);

    TEST_CHECK(system->profile_id == SYSTEM_PROFILE_ID);
    TEST_CHECK(system->enabled_capabilities ==
               TARGET_COMPILED_SYSTEM_CAPABILITIES);
    TEST_CHECK(system->required_capabilities ==
               SYSTEM_PROFILE_REQUIRED_CAPABILITIES);
    TEST_CHECK(system->optional_capabilities ==
               SYSTEM_PROFILE_OPTIONAL_CAPABILITIES);
    TEST_CHECK((system->enabled_capabilities & SYSTEM_CAPABILITY_IMU) != 0U);
    TEST_CHECK((system->enabled_capabilities & SYSTEM_CAPABILITY_GNSS) != 0U);
    TEST_CHECK((system->enabled_capabilities &
                SYSTEM_CAPABILITY_MAGNETOMETER) == 0U);

    TEST_CHECK(FloatClose(estimator->p0_diagonal[0],
                          SYSTEM_ESTIMATOR_P0_POSITION_E_VARIANCE_M2));
    TEST_CHECK(FloatClose(estimator->p0_diagonal[5],
                          SYSTEM_ESTIMATOR_P0_VELOCITY_U_VARIANCE_M2PS2));
    Test_EstimatorNoiseProfile(estimator);
    Test_GnssDynamicUncertainty();
    TEST_CHECK(FloatClose(estimator->gnss_accuracy_scale,
                          SYSTEM_ESTIMATOR_GNSS_ACCURACY_SCALE));
    TEST_CHECK(FloatClose(estimator->nis_3d_hard,
                          SYSTEM_ESTIMATOR_NIS_3D_HARD_THRESHOLD));

    return Test_Finish("profiles");
}
