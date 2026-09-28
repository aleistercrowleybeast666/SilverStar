/* Exercise the real APP correction/pairing and common frontend at 400 Hz.
 * Device acquisition is synthetic; no claim about physical IRQ timing is made. */
#include <math.h>
#include <stdio.h>
#include "host_platform_mock.h"
#include "test_common.h"
#include "navigation_eskf_replay.h"
#include "ins_task.c"

static NavigationEskfState s_test_state;
static NavigationEskfWorkspace s_test_workspace;
static NavigationEskfReplay s_test_history;
static NavigationEskfHistoryInput s_test_body[NAV_ESKF_HISTORY_CAPACITY];

int main(void)
{
    const NavigationEskfConfig config = {
        SYSTEM_ESKF_GRAVITY_MPS2, SYSTEM_ESKF_GYRO_NOISE_DENSITY,
        SYSTEM_ESKF_ACCEL_NOISE_DENSITY, SYSTEM_ESKF_GYRO_BIAS_RW,
        SYSTEM_ESKF_ACCEL_BIAS_RW,
        {SYSTEM_ESKF_NIS_1D_SOFT, SYSTEM_ESKF_NIS_2D_SOFT},
        {SYSTEM_ESKF_NIS_1D_HARD, SYSTEM_ESKF_NIS_2D_HARD},
        SYSTEM_ESKF_NIS_MAX_R_SCALE
    };
    float nominal[16] = {0};
    float covariance[NAV_ESKF_DIM][NAV_ESKF_DIM] = {{0}};
    InsImuSample raw = {0};
    InsAlgorithmSample corrected;
    InsState inertial;
    NavigationEskfBodyInput body = {0};
    uint32_t published = 0U;
    uint16_t maximum_history = 0U;
    HostPlatformMock_Reset();
    SystemCalibration_Init();
    InsInertial_Reset(&s_navigation_input.inertial);
    nominal[6] = 1.0f;
    for (uint32_t axis = 0U; axis < NAV_ESKF_DIM; axis++)
    { covariance[axis][axis] = 0.01f; }
    TEST_CHECK(NavigationEskf_Initialize(&s_test_state, &s_test_workspace,
        nominal, (const float (*)[NAV_ESKF_DIM])covariance, 1000000ULL,
        1U, SystemCalibration_GenerationGet()) == NAV_ESKF_OK);
    TEST_CHECK(NavigationEskfReplay_Reset(&s_test_history, &s_test_state,
        s_test_body) == NAV_ESKF_REPLAY_OK);
    raw.accel_b_mps2[2] = config.gravity_mps2;
    raw.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    raw.quality_flags = SYSTEM_IMU_QUALITY_TIME_UNCERTAIN;
    for (uint32_t index = 0U; index <= 800U; index++)
    {
        InsInertialUpdateResult result;
        /* Actual 1 ms polling can observe alternating 2/3 ms proxy spacing.
         * Two intervals are still a measured 5 ms, not a fabricated 2.5 ms clock. */
        raw.sample_timestamp_us = 1000000ULL + (uint64_t)(index / 2U) * 5000ULL +
            (uint64_t)(index % 2U) * 2000ULL;
        raw.receive_timestamp_us = raw.sample_timestamp_us;
        raw.sequence = index + 1U;
        TEST_CHECK(InsTask_SampleCorrect(&raw, &corrected) == 1U);
        TEST_CHECK(corrected.timestamp_us == raw.sample_timestamp_us);
        TEST_CHECK(corrected.quality_flags == SYSTEM_IMU_QUALITY_TIME_UNCERTAIN);
        if (s_navigation_input.inertial.sample_count == 2U)
        { InsTask_BodyPairBuild(&corrected); }
        result = InsInertial_Update(&s_navigation_input.inertial, &corrected, &inertial);
        if (result != INS_INERTIAL_UPDATE_READY)
        { TEST_CHECK(result == INS_INERTIAL_UPDATE_WAITING); continue; }
        published++;
        TEST_CHECK(inertial.timestamp_us - inertial.interval_start_timestamp_us == 5000ULL);
        TEST_CHECK_NEAR(inertial.dt_s, 0.005f, 1.0e-8f);
        memcpy(body.gyro_radps, s_eskf_gyro_pair, sizeof(body.gyro_radps));
        memcpy(body.accel_mps2, s_eskf_accel_pair, sizeof(body.accel_mps2));
        body.start_us = inertial.interval_start_timestamp_us;
        body.end_us = inertial.timestamp_us; body.dt_s = inertial.dt_s;
        body.source = 1U; body.generation = SystemCalibration_GenerationGet();
        body.quality_flags = s_eskf_quality_flags;
        TEST_CHECK(body.quality_flags == SYSTEM_IMU_QUALITY_TIME_UNCERTAIN);
        TEST_CHECK(NavigationEskfReplay_Predict(&s_test_history, &s_test_state,
            &s_test_workspace, &config, &body) == NAV_ESKF_REPLAY_OK);
        if (s_test_history.body_count > maximum_history)
        { maximum_history = s_test_history.body_count; }
    }
    TEST_CHECK(published == 400U);
    TEST_CHECK(maximum_history == 120U);
    TEST_CHECK(s_test_history.body_count == 120U);
    TEST_CHECK(s_test_history.overflows == 0U);
    TEST_CHECK(s_test_state.timestamp_us == 3000000ULL);
    TEST_CHECK_NEAR(s_test_state.position[2], 0.0f, 1.0e-4f);
    TEST_CHECK_NEAR(s_test_state.velocity[2], 0.0f, 1.0e-4f);
    (void)printf("raw=801 intervals=800 BODY=400 duration_us=2000000 max_history=120/192\n");
    return Test_Finish("eskf_actual_app_body_cadence");
}
