#include "system_user_config.h"

#if defined(TEST_EXPECT_DEFAULT_JY901B_PROFILE)
#include "jy901b_imu_build_capabilities.h"
#include "jy901b_magnetometer_build_capabilities.h"
#include "jy901b_quaternion_build_capabilities.h"
_Static_assert(SYSTEM_ALIGNMENT_ALGORITHM ==
               SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW,
               "Default alignment must be Gravity Known Yaw");
_Static_assert(SYSTEM_USER_MAGNETOMETER_ENABLE == 0U,
               "Default JY901B magnetometer adapter must be disabled");
_Static_assert(SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE != 0U,
               "Default JY901B accel must be available");
_Static_assert(SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U,
               "Default JY901B gyro must be available");
_Static_assert(JY901B_QUATERNION_BUILD_PREFLIGHT_ALIGNMENT_6AXIS_QUALIFIED == 1U,
               "JY901B 6-axis preflight alignment must be qualified");
_Static_assert(JY901B_QUATERNION_BUILD_PREFLIGHT_ALIGNMENT_9AXIS_QUALIFIED == 1U,
               "JY901B 9-axis preflight alignment must be qualified");
_Static_assert(
    SYSTEM_SELECTED_HARDWARE_QUATERNION_PREFLIGHT_ALIGNMENT_6AXIS_QUALIFIED ==
        1U,
    "Selected 6-axis preflight alignment qualification must be mapped");
_Static_assert(
    SYSTEM_SELECTED_HARDWARE_QUATERNION_PREFLIGHT_ALIGNMENT_9AXIS_QUALIFIED ==
        1U,
    "Selected 9-axis preflight alignment qualification must be mapped");
_Static_assert(JY901B_QUATERNION_BUILD_AUTHORITATIVE_6AXIS_QUALIFIED == 0U,
               "JY901B 6-axis attitude must not be mission-authoritative");
_Static_assert(JY901B_QUATERNION_BUILD_AUTHORITATIVE_9AXIS_QUALIFIED == 0U,
               "JY901B 9-axis attitude must not be mission-authoritative");
_Static_assert(
    SYSTEM_SELECTED_HARDWARE_QUATERNION_AUTHORITATIVE_6AXIS_QUALIFIED == 0U,
    "Selected 6-axis attitude must not be mission-authoritative");
_Static_assert(
    SYSTEM_SELECTED_HARDWARE_QUATERNION_AUTHORITATIVE_9AXIS_QUALIFIED == 0U,
    "Selected 9-axis attitude must not be mission-authoritative");
_Static_assert(JY901B_MAGNETOMETER_BUILD_ABSOLUTE_VECTOR_QUALIFIED == 0U,
               "JY901B magnetic vector must remain unqualified");
_Static_assert(SYSTEM_SELECTED_MAGNETOMETER_ABSOLUTE_VECTOR_QUALIFIED == 0U,
               "Selected magnetic vector must remain unqualified");
_Static_assert(JY901B_IMU_BUILD_LANDING_STILLNESS_QUALIFIED == 1U,
               "JY901B stillness landing must be qualified");
_Static_assert(SYSTEM_SELECTED_IMU_LANDING_STILLNESS_QUALIFIED == 1U,
               "Selected stillness qualification must be mapped");
_Static_assert(JY901B_IMU_BUILD_LANDING_IMPACT_QUALIFIED == 0U,
               "JY901B impact qualification must remain false");
_Static_assert(SYSTEM_SELECTED_IMU_LANDING_IMPACT_QUALIFIED == 0U,
               "Default JY901B impact qualification must remain false");
#endif

int main(void)
{
    return 0;
}
