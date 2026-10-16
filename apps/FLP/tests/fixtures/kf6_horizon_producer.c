/* Native generated mode2/HMS configuration, owning KF task and wire writers.
 * Nominal-rate CPU input production; no INS/preflight/device/hardware claim. */
int HorizonFixture_OriginalMain(int argc, char **argv);
#define main HorizonFixture_OriginalMain
#include KF_HORIZON_FIXTURE_SOURCE
#undef main
#include "horizon_log_bootstrap.h"

int main(int argc, char **argv)
{
    float diagonal[6];
    TEST_CHECK(argc == 2);
    if (argc != 2) { return Test_Finish("kf_horizon_log"); }
    s_test_wire = fopen(argv[1],"wb"); TEST_CHECK(s_test_wire != NULL);
    if (s_test_wire == NULL) { return Test_Finish("kf_horizon_log"); }
    HorizonTest_Reset(); HorizonLog_BootstrapWrite(); HorizonTest_RecordsDrain();
    for (uint32_t axis = 0U; axis < 6U; axis++) { diagonal[axis] = s_estimator.kf.covariance[axis][axis]; }
    HorizonLog_MissionWrite(diagonal);
    for (uint32_t cycle = 1U; cycle <= 80U; cycle++)
    {
        SystemInertialIncrement input = {0};
        FlightLogInertialIncrementRecord raw = {0};
        input.timestamp_us = 1000000ULL+(uint64_t)cycle*10000ULL;
        input.sequence = cycle; input.dt_s = .01f;
        input.delta_velocity_b_sculling_corrected[2] = SYSTEM_KF_GRAVITY_MPS2*.01f;
        raw.interval_start_timestamp_us = input.timestamp_us-10000ULL;
        raw.interval_end_timestamp_us = input.timestamp_us; raw.sequence = cycle; raw.dt_s = input.dt_s;
        memcpy(raw.delta_velocity_b_sculling_corrected,input.delta_velocity_b_sculling_corrected,
            sizeof(raw.delta_velocity_b_sculling_corrected));
        TEST_CHECK(LoggerBus_InertialIncrementPush(input.timestamp_us,
            SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO,&raw) == LOGGER_BUS_RESULT_OK);
        if (cycle % 4U == 1U) { HorizonTest_Receive(input.timestamp_us,(cycle+3U)/4U,1U); }
        HostPlatformMock_TimeSetUs(input.timestamp_us); Estimator_PredictionProcess(&input);
        HorizonTest_RecordsDrain();
    }
    TEST_CHECK(s_test_completions > 0U && s_test_faults == 0U);
    TEST_CHECK(s_test_unexpected_preflight_calls == 0U);
    TEST_CHECK(fclose(s_test_wire) == 0);
    return Test_Finish("kf_horizon_log");
}
