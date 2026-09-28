#include <string.h>
#include "system_calibration.h"
#include "system_lifecycle.h"
#include "platform_critical.h"
#include "air_protocol.h"
#include "test_common.h"

static uint32_t s_invalidations;
static uint32_t s_locks;
static SystemLifecycleState s_state = SYSTEM_STATE_PREFLIGHT;
SystemLifecycleState SystemLifecycle_GetState(void) { return s_state; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
SystemDeviceResult SystemAlignment_CalibrationInvalidate(void)
{ s_invalidations++; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void)
{ s_locks++; return SYSTEM_DEVICE_OK; }

int main(void)
{
    SystemCalibrationStatus before;
    SystemCalibrationStatus after;
    AirCapabilityPayload capability = {0};
    uint8_t frame[AIR_MAX_FRAME_LEN];
    uint8_t length = 0U;
    uint32_t mode;
    uint32_t invalidations;
    uint32_t locks;
    const uint8_t expected = (uint8_t)(1U | SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK);

    SystemCalibration_Init();
    TEST_CHECK(SystemCalibration_CapabilityMaskGet() == expected);
    capability.air_profile_id = AIR_PROFILE_ID_CURRENT;
    capability.command_policy = AIR_COMMAND_POLICY_PREFLIGHT_ONLY;
    capability.sensor_summary_flags = AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED;
    capability.accel_full_scale_g = AIR_ACCEL_FULL_SCALE_G;
    capability.gyro_full_scale_dps = AIR_GYRO_FULL_SCALE_DPS;
    capability.calibration_mode_mask = expected;
    TEST_CHECK(Air_CapabilityBuild(42U, &capability, frame,
        sizeof(frame), &length) == AIR_BUILD_OK);
    TEST_CHECK(frame[4] == expected);
    for (mode = 0U; mode <= 2U; mode++)
    {
        TEST_CHECK(SystemCalibration_StatusGet(&before) == SYSTEM_DEVICE_OK);
        invalidations = s_invalidations;
        locks = s_locks;
        if ((expected & (1U << mode)) != 0U)
        {
            TEST_CHECK(SystemCalibration_Start((SystemCalibrationMode)mode) == SYSTEM_DEVICE_OK);
            TEST_CHECK(s_invalidations == invalidations + 1U);
        }
        else
        {
            TEST_CHECK(SystemCalibration_Start((SystemCalibrationMode)mode) == SYSTEM_DEVICE_UNSUPPORTED);
            TEST_CHECK(SystemCalibration_StatusGet(&after) == SYSTEM_DEVICE_OK);
            TEST_CHECK(memcmp(&before, &after, sizeof(before)) == 0);
            TEST_CHECK(s_invalidations == invalidations);
            TEST_CHECK(s_locks == locks);
        }
    }
    TEST_CHECK(SystemCalibration_Start((SystemCalibrationMode)-1) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemCalibration_Start((SystemCalibrationMode)3U) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
    if (SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK == 0U)
    {
        TEST_CHECK(SystemCalibration_StatusGet(&after) == SYSTEM_DEVICE_OK);
        TEST_CHECK(after.mode == SYSTEM_CALIBRATION_MODE_NONE);
        TEST_CHECK(after.state == SYSTEM_CALIBRATION_STATE_READY);
        TEST_CHECK(after.correction.ready == 1U);
        TEST_CHECK(after.correction.accel_scale[0] == 1.0f);
        TEST_CHECK(after.correction.gyro_scale[2] == 1.0f);
    }
    s_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) == SYSTEM_DEVICE_BAD_STATE);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_BAD_STATE);
    return Test_Finish("calibration_build_gate");
}
