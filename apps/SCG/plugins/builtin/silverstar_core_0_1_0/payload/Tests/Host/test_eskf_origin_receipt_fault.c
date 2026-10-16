/* Actual backend lifecycle with CPU-only device ports. Missing origin remains
 * ordinary; corrupt owned selector state must withdraw READY in every mode. */
#include <string.h>
#include "test_common.h"
#include "host_platform_mock.h"
#include ESKF_HORIZON_BACKEND_SOURCE

static SystemDeviceResult s_selected_result = SYSTEM_DEVICE_OK;
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ (void)sample; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{ (void)time; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = 0U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{ if (s_selected_result == SYSTEM_DEVICE_OK) { *instance = 0U; } return s_selected_result; }
uint32_t SystemCalibration_GenerationGet(void) { return 7U; }

static SystemDeviceResult OriginFault_Body(uint32_t cycle, EstimatorOutputSnapshot *output)
{
    SystemInertialIncrement input = {0};
    input.timestamp_us = 1000000ULL + (uint64_t)cycle * 5000ULL;
    input.sequence = cycle; input.dt_s = .005f;
    input.body_accel_mps2[0][2] = SYSTEM_ESKF_GRAVITY_MPS2;
    input.body_accel_mps2[1][2] = SYSTEM_ESKF_GRAVITY_MPS2;
    HostPlatformMock_TimeSetUs(input.timestamp_us);
    return SystemNavigationBackend_Predict(&input, output);
}

int main(void)
{
    EstimatorOutputSnapshot output = {0};
    const SystemGnssSample no_origin = {0};
    const float quaternion[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    HostPlatformMock_Reset();
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(SystemNavigationBackend_Initialize(quaternion, &no_origin, 0.0f, 0U, 77U, 1U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_frame.valid == 0U);
    TEST_CHECK(OriginFault_Body(1U, &output) == SYSTEM_DEVICE_OK);
    s_selected_result = SYSTEM_DEVICE_NOT_READY;
    TEST_CHECK(OriginFault_Body(2U, &output) == SYSTEM_DEVICE_OK);
    TEST_CHECK(output.initialized == 1U && s_frame.valid == 0U);
    s_selected_result = SYSTEM_DEVICE_BAD_STATE;
    TEST_CHECK(OriginFault_Body(3U, &output) == SYSTEM_DEVICE_VERIFY_FAILED);
    TEST_CHECK(output.initialized == 0U && output.mission_running == 0U);
    TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(OriginFault_Body(4U, &output) == SYSTEM_DEVICE_VERIFY_FAILED);
    return Test_Finish("eskf_origin_receipt_fault");
}
