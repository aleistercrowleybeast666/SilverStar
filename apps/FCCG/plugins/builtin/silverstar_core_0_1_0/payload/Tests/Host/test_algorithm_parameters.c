#include <stdio.h>
#include <string.h>
#include "ins_mechanization.h"
#include "navigation_kf.h"
#include "system_estimator_profile.h"
#include "test_common.h"

static void Test_VectorPrint(const float *value, unsigned int count)
{
    unsigned int index;
    for (index = 0U; index < count; index++)
    {
        (void)printf("%a ", (double)value[index]);
    }
    (void)printf("\n");
}

static void Test_FilterInitialize(NavigationKfContext *context)
{
    float p0[6][6];
    const SystemEstimatorProfile *profile = SystemEstimatorProfile_Get();
    const float soft[3] = {profile->nis_1d_soft, profile->nis_2d_soft, profile->nis_3d_soft};
    const float hard[3] = {profile->nis_1d_hard, profile->nis_2d_hard, profile->nis_3d_hard};
    NavigationKf_Init(context);
    SystemEstimatorProfile_BuildP0(p0, NULL, NULL, 0U);
    TEST_CHECK(NavigationKf_ResetWithCovariance(context, &p0[0][0]) != 0U);
    NavigationKf_SetProcessAccelStd(context, profile->process_accel_std_mps2);
    NavigationKf_SetBaroStd(context, profile->barometer_altitude_std_m);
    NavigationKf_SetNisThresholds(context, soft, hard, profile->nis_max_r_scale);
    Test_VectorPrint(&context->covariance[0][0], 36U);
    Test_VectorPrint(profile->process_accel_std_mps2, 3U);
    Test_VectorPrint(soft, 3U);
    Test_VectorPrint(hard, 3U);
}

static void Test_MeasurementApply(NavigationKfContext *context, unsigned int step)
{
    float position[3] = {0.03f * (float)step, 0.01f, 0.15f};
    float velocity[3] = {0.15f, -0.03f, 0.01f};
    float variance[3];
    float sigma;
    unsigned int index;
    for (index = 0U; index < 3U; index++)
    {
        sigma = SystemEstimatorProfile_GnssStdResolve(
            (index == 2U) ? SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_POSITION :
                           SYSTEM_ESTIMATOR_GNSS_STD_HORIZONTAL_POSITION, 0.1f);
        variance[index] = sigma * sigma;
    }
    (void)NavigationKf_UpdateGnssPosition(context, position, variance);
    for (index = 0U; index < 3U; index++)
    {
        sigma = SystemEstimatorProfile_GnssStdResolve(
            (index == 2U) ? SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_VELOCITY :
                           SYSTEM_ESTIMATOR_GNSS_STD_VELOCITY, 0.05f);
        variance[index] = sigma * sigma;
    }
    (void)NavigationKf_UpdateGnssVelocity3D(context, velocity, variance);
    (void)NavigationKf_UpdateBaroAltitude(context, 0.15f, context->baro_std_m * context->baro_std_m);
}

static void Test_SampleBuild(InsAlgorithmSample *sample, unsigned int step)
{
    (void)memset(sample, 0, sizeof(*sample));
    sample->timestamp_us = 1000000ULL + (uint64_t)step * 5000ULL;
    sample->valid_flags = INS_ALGORITHM_VALID_ACCEL | INS_ALGORITHM_VALID_GYRO;
    sample->accel_b_mps2[0] = (step % 80U < 40U) ? 0.2f : -0.1f;
    sample->accel_b_mps2[1] = 0.05f;
    sample->accel_b_mps2[2] = 9.78f;
    sample->gyro_b_radps[0] = 0.001f;
    sample->gyro_b_radps[1] = -0.002f;
    sample->gyro_b_radps[2] = 0.005f;
}

static void Test_NavigationRun(void)
{
    InsMechanizationContext ins;
    NavigationKfContext kf;
    InsAlgorithmSample sample;
    InsState state;
    const float attitude[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    unsigned int step;
    InsMechanization_Init(&ins, SYSTEM_INS_GRAVITY_MPS2);
    TEST_CHECK(InsMechanization_ResetNavigationWithAttitude(&ins, attitude) != 0U);
    Test_FilterInitialize(&kf);
    for (step = 0U; step <= 2000U; step++)
    {
        Test_SampleBuild(&sample, step);
        if (InsMechanization_Update(&ins, &sample, &state) != 0U)
        {
            float delta_velocity[3];
            Ins_TransformDeltaVelocityToNavigation(attitude,
                state.delta_velocity_b_sculling_corrected, state.dt_s,
                SYSTEM_KF_GRAVITY_MPS2, delta_velocity);
            TEST_CHECK(NavigationKf_Predict(&kf, delta_velocity, state.dt_s) != 0U);
            if (step % 8U == 0U)
            {
                Test_MeasurementApply(&kf, step);
            }
            Test_VectorPrint(state.q_nb, 4U);
            Test_VectorPrint(state.position_n_m, 3U);
            Test_VectorPrint(state.velocity_n_mps, 3U);
            Test_VectorPrint(kf.state, 6U);
            Test_VectorPrint(&kf.covariance[0][0], 36U);
        }
    }
}

int main(void)
{
    Test_NavigationRun();
    return Test_Finish("algorithm_parameters");
}
