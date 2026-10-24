#include "system_user_config.h"

#if defined(TEST_EXPECT_SELECTED_PROVIDER_PROFILE)
/* Actual composition; separate from the three-interface runtime mock. */
_Static_assert(SYSTEM_USER_ALIGNMENT_SELECTED_MASK ==
    (SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
     ((SYSTEM_USER_GNSS_ENABLE != 0U) ?
        SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN : 0U) |
     ((SYSTEM_USER_BAROMETER_ENABLE != 0U) ?
        SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN : 0U)),
    "Selected provider alignment mask must follow its enabled origins");
_Static_assert(SYSTEM_USER_ALIGNMENT_REQUIRED_MASK ==
    (SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
     ((SYSTEM_USER_BAROMETER_ENABLE != 0U) ?
        SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN : 0U)),
    "Selected provider required mask must preserve attitude/barometer policy");
_Static_assert(SYSTEM_ALIGNMENT_ALGORITHM == TEST_EXPECT_ALIGNMENT_ALGORITHM,
    "Selected provider alignment must match SourceGraph");
#endif

#if defined(TEST_EXPECT_JY901B_PROFILE)
#include "jy901b_imu_build_capabilities.h"
#include "jy901b_magnetometer_build_capabilities.h"
#include "jy901b_quaternion_build_capabilities.h"
_Static_assert(SYSTEM_ALIGNMENT_ALGORITHM ==
               SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW,
               "Default alignment must be Gravity Known Yaw");
/* Explicit capture profiles enable MAG without granting absolute-vector
 * qualification. The generator tests separately prove the default-off profile. */
_Static_assert((JY901B_MAGNETOMETER_ADAPTER_ENABLE == 0U) ||
               (SYSTEM_USER_MAGNETOMETER_ENABLE != 0U),
               "Enabled JY901B magnetic capture requires the logical MAG capability");
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
