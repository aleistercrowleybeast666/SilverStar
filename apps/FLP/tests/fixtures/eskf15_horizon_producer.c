/* Native generated mode2/HMS configuration, owning ESKF backend/wire writers.
 * Nominal-rate CPU input production; no INS/preflight/device/hardware claim. */
int HorizonFixture_OriginalMain(int argc, char **argv);
#define main HorizonFixture_OriginalMain
#include ESKF_HORIZON_FIXTURE_SOURCE
#undef main
#include "horizon_log_bootstrap.h"

int main(int argc, char **argv)
{
    EstimatorOutputSnapshot output;
    float diagonal[6];
    TEST_CHECK(argc == 2);
    if (argc != 2) { return Test_Finish("eskf_horizon_log"); }
    s_test_wire = fopen(argv[1],"wb"); TEST_CHECK(s_test_wire != NULL);
    if (s_test_wire == NULL) { return Test_Finish("eskf_horizon_log"); }
    HorizonTest_Reset(&output); HorizonLog_BootstrapWrite(); HorizonTest_RecordsDrain();
    for (uint32_t axis = 0U; axis < 6U; axis++) { diagonal[axis] = s_state.covariance[axis][axis]; }
    HorizonLog_MissionWrite(diagonal);
    for (uint32_t cycle = 1U; cycle <= 80U; cycle++)
    {
        SystemInertialIncrement input = {0};
        input.timestamp_us = 1000000ULL+(uint64_t)cycle*10000ULL;
        input.sequence = cycle; input.dt_s = .01f;
        input.body_accel_mps2[0][2] = SYSTEM_ESKF_GRAVITY_MPS2;
        input.body_accel_mps2[1][2] = SYSTEM_ESKF_GRAVITY_MPS2;
        if (cycle % 4U == 1U) { HorizonTest_Receive(input.timestamp_us,(cycle+3U)/4U,1U); }
        HostPlatformMock_TimeSetUs(input.timestamp_us);
        TEST_CHECK(SystemNavigationBackend_Predict(&input,&output) == SYSTEM_DEVICE_OK);
        HorizonTest_RecordsDrain();
    }
    TEST_CHECK(s_test_completion_count > 0U && s_test_fault_status_count == 0U);
    TEST_CHECK(fclose(s_test_wire) == 0);
    return Test_Finish("eskf_horizon_log");
}
