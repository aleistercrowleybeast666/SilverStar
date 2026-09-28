#ifndef __SYSTEM_USER_CAPABILITY_VALIDATION_H
#define __SYSTEM_USER_CAPABILITY_VALIDATION_H

#include "system_configuration_types.h"
#include "system_user_alignment_config.h"
#include "system_user_flight_config.h"
#include "system_user_platform_capabilities.h"
#include "target_system_config.h"

#define SYSTEM_USER_ENABLE_IS_BOOLEAN(enable_) \
    (((enable_) == 0U) || ((enable_) == 1U))

_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_IMU_ENABLE),
               "IMU enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_GNSS_ENABLE),
               "GNSS enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(
                   SYSTEM_USER_MAGNETOMETER_ENABLE),
               "Magnetometer enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_BAROMETER_ENABLE),
               "Barometer enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(
                   SYSTEM_USER_HARDWARE_QUATERNION_ENABLE),
               "Hardware quaternion enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_TELEMETRY_ENABLE),
               "Telemetry enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_CONSOLE_ENABLE),
               "Console enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_POWER_ENABLE),
               "Power enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_STORAGE_ENABLE),
               "Storage enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_OUTPUT_ENABLE),
               "Output enable must be boolean");
_Static_assert(SYSTEM_USER_ENABLE_IS_BOOLEAN(SYSTEM_USER_LOG_SINK_ENABLE),
               "Log sink enable must be boolean");
_Static_assert((SYSTEM_USER_LOG_SINK_ENABLE == 0U) ||
               (SYSTEM_USER_STORAGE_ENABLE != 0U),
               "The selected file log sink requires storage");

_Static_assert(SYSTEM_USER_IMU_ENABLE == 1U,
               "SilverStar requires one selected primary IMU");
_Static_assert(SYSTEM_USER_TIME_SOURCE_ENABLE == 1U,
               "SilverStar requires one monotonic time source");

#if !defined(SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_OVERRIDE) || \
    !defined(SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_OVERRIDE) || \
    !defined(SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_OVERRIDE)
_Static_assert(
    SYSTEM_SELECTED_IMU_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE != 0U,
    "Selected IMU needs estimator noise recommendations or all E/N/U overrides");
#endif

#if !defined(SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_OVERRIDE) || \
    !defined(SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_OVERRIDE) || \
    !defined(SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_OVERRIDE)
_Static_assert(
    (SYSTEM_USER_GNSS_ENABLE == 0U) ||
    (SYSTEM_SELECTED_GNSS_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE != 0U),
    "Selected GNSS needs estimator floor recommendations or all floor overrides");
#endif

#if !defined(SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_OVERRIDE)
_Static_assert(
    (SYSTEM_USER_BAROMETER_ENABLE == 0U) ||
    (SYSTEM_SELECTED_BAROMETER_ESTIMATOR_NOISE_RECOMMENDATION_AVAILABLE != 0U),
    "Selected Barometer needs an estimator noise recommendation or override");
#endif

_Static_assert((SYSTEM_ALIGNMENT_ALGORITHM !=
                SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW) ||
               ((SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_SOFTWARE_ALIGNMENT_QUALIFIED != 0U)),
               "Gravity Known Yaw requires qualified accel/gyro software alignment");

_Static_assert((SYSTEM_ALIGNMENT_ALGORITHM !=
                SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD) ||
               ((SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_SOFTWARE_ALIGNMENT_QUALIFIED != 0U) &&
                (SYSTEM_USER_MAGNETOMETER_ENABLE != 0U) &&
                (SYSTEM_SELECTED_MAGNETOMETER_PHYSICAL_UNIT_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_MAGNETOMETER_ABSOLUTE_VECTOR_QUALIFIED != 0U)),
               "TRIAD requires an enabled, absolute-vector-qualified magnetometer");

_Static_assert((SYSTEM_ALIGNMENT_ALGORITHM !=
                SYSTEM_ALIGNMENT_HW_QUAT_6AXIS_KNOWN_YAW) ||
               ((SYSTEM_USER_HARDWARE_QUATERNION_ENABLE != 0U) &&
                (SYSTEM_SELECTED_HARDWARE_QUATERNION_OUTPUT_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_HARDWARE_QUATERNION_PREFLIGHT_ALIGNMENT_6AXIS_QUALIFIED != 0U)),
               "HW 6-axis alignment requires a qualified preflight source");

_Static_assert((SYSTEM_ALIGNMENT_ALGORITHM !=
                SYSTEM_ALIGNMENT_HW_QUAT_9AXIS) ||
               ((SYSTEM_USER_HARDWARE_QUATERNION_ENABLE != 0U) &&
                (SYSTEM_SELECTED_HARDWARE_QUATERNION_OUTPUT_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_HARDWARE_QUATERNION_PREFLIGHT_ALIGNMENT_9AXIS_QUALIFIED != 0U)),
               "HW 9-axis alignment requires a qualified preflight source");

_Static_assert(((SYSTEM_USER_ALIGNMENT_REQUIRED_MASK &
                 SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN) == 0U) ||
               ((SYSTEM_USER_BAROMETER_ENABLE != 0U) &&
                (SYSTEM_SELECTED_BAROMETER_DIRECT_ALTITUDE_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_BAROMETER_ALIGNMENT_ORIGIN_QUALIFIED != 0U)),
               "Required Barometer origin needs a qualified altitude source");

_Static_assert(((SYSTEM_USER_ALIGNMENT_REQUIRED_MASK &
                 SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) == 0U) ||
               ((SYSTEM_USER_GNSS_ENABLE != 0U) &&
                (SYSTEM_SELECTED_GNSS_POSITION_AVAILABLE != 0U)),
               "Required GNSS origin needs a selected position source");

_Static_assert((SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE == 0U) ||
               (SYSTEM_FLIGHT_LANDING_MODE != SYSTEM_LANDING_MODE_STILLNESS) ||
               ((SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_LANDING_STILLNESS_QUALIFIED != 0U)),
               "Stillness landing requires a stillness-qualified IMU");

_Static_assert((SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE == 0U) ||
               (SYSTEM_FLIGHT_LANDING_MODE !=
                SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS) ||
               ((SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_LANDING_STILLNESS_QUALIFIED != 0U) &&
                (SYSTEM_SELECTED_IMU_LANDING_IMPACT_QUALIFIED != 0U)),
               "Impact landing requires stillness- and impact-qualified IMU data");

_Static_assert((SYSTEM_FLIGHT_LANDING_DETECTION_ENABLE == 0U) ||
               (SYSTEM_FLIGHT_LANDING_MODE !=
                SYSTEM_LANDING_MODE_BARO_IMU_WINDOW) ||
               ((SYSTEM_SELECTED_IMU_ACCEL_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_LANDING_STILLNESS_QUALIFIED != 0U) &&
                (SYSTEM_USER_BAROMETER_ENABLE != 0U) &&
                (SYSTEM_SELECTED_BAROMETER_DIRECT_ALTITUDE_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_BAROMETER_LANDING_WINDOW_QUALIFIED != 0U)),
               "Baro/IMU landing requires qualified IMU and direct altitude");

_Static_assert(((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK &
                 SYSTEM_DEPLOY_TRIGGER_TILT) == 0U) ||
               ((SYSTEM_SELECTED_IMU_GYRO_AVAILABLE != 0U) &&
                (SYSTEM_SELECTED_IMU_SOFTWARE_PROPAGATION_QUALIFIED != 0U)),
               "TILT deploy requires selected gyro software propagation");

_Static_assert(((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK &
                 SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ) == 0U) ||
               (SYSTEM_BUILD_NAVIGATION_VERTICAL_VELOCITY_AVAILABLE != 0U),
               "APOGEE_VZ deploy requires navigation vertical velocity");

_Static_assert(((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK &
                 SYSTEM_DEPLOY_TRIGGER_DELAY) == 0U) ||
               (SYSTEM_BUILD_MISSION_MONOTONIC_TIME_AVAILABLE != 0U),
               "DELAY deploy requires mission monotonic time");

_Static_assert((SYSTEM_USER_MISSION_ACTION_ENABLE != 0U) &&
               (SYSTEM_SELECTED_MISSION_ACTION_START_AVAILABLE != 0U),
               "The current flight profile requires a START action");
_Static_assert((SYSTEM_FLIGHT_DEPLOY_TRIGGER_MASK == 0U) ||
               ((SYSTEM_USER_MISSION_ACTION_ENABLE != 0U) &&
                (SYSTEM_SELECTED_MISSION_ACTION_PARACHUTE_DEPLOY_AVAILABLE != 0U)),
               "Automatic deploy requires a parachute-deploy Mission Action");


#endif /* __SYSTEM_USER_CAPABILITY_VALIDATION_H */
