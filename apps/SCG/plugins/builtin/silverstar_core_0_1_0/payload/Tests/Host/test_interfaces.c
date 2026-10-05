#include <stddef.h>

#include "system_console_if.h"
#include "system_descriptor_if.h"
#include "system_device_types.h"
#include "system_mission_action_if.h"
#include "system_power_if.h"
#include "system_storage_if.h"
#include "test_common.h"

_Static_assert(offsetof(SystemInertialIncrement, timestamp_us) == 0U,
               "timestamp_us layout changed");
_Static_assert(offsetof(SystemInertialIncrement, sequence) == 8U,
               "sequence layout changed");
_Static_assert(offsetof(SystemInertialIncrement, dt_s) == 12U,
               "dt_s layout changed");
_Static_assert(offsetof(SystemInertialIncrement,
                        delta_theta_b_corrected) == 16U,
               "body delta-theta layout changed");
_Static_assert(offsetof(SystemInertialIncrement,
                        delta_velocity_b_sculling_corrected) == 28U,
               "body delta-velocity layout changed");
_Static_assert(sizeof(SystemInertialIncrement) == 40U,
               "inertial increment layout changed");

_Static_assert(offsetof(SystemPowerSample, sample_timestamp_us) == 0U,
               "power sample time layout changed");
_Static_assert(offsetof(SystemPowerSample, receive_timestamp_us) == 8U,
               "power receive time layout changed");
_Static_assert(offsetof(SystemPowerSample, sequence) == 16U,
               "power sequence layout changed");
_Static_assert(offsetof(SystemPowerSample, voltage_v) == 20U,
               "power voltage layout changed");
_Static_assert(offsetof(SystemPowerSample, valid_mask) == 40U,
               "power validity layout changed");

int main(void)
{
    SystemInertialIncrement increment = {0};
    SystemPowerSample power = {0};

    increment.timestamp_us = 100U;
    increment.sequence = 4U;
    increment.dt_s = 0.01f;
    increment.delta_theta_b_corrected[0] = 0.1f;
    increment.delta_velocity_b_sculling_corrected[2] = 0.2f;
    TEST_CHECK(increment.timestamp_us == 100U);
    TEST_CHECK(increment.sequence == 4U);
    TEST_CHECK_NEAR(increment.delta_velocity_b_sculling_corrected[2],
                    0.2f, 1.0e-7f);

    power.sample_timestamp_us = 200U;
    power.receive_timestamp_us = 230U;
    TEST_CHECK(power.receive_timestamp_us != power.sample_timestamp_us);
    TEST_CHECK(sizeof(SystemDeviceInfo) != 0U);
    TEST_CHECK(sizeof(SystemDeviceDescriptor) != 0U);
    TEST_CHECK(sizeof(SystemAlgorithmDescriptor) != 0U);
    TEST_CHECK(SYSTEM_MISSION_ACTION_START == 0U);
    TEST_CHECK(SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY == 1U);
    TEST_CHECK(SYSTEM_DEVICE_CLASS_IMU == 1U);
    TEST_CHECK(SYSTEM_ALGORITHM_CLASS_FUSION == 4U);
    return Test_Finish("interfaces");
}
