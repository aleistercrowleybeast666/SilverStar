#include "system_navigation_profile.h"

_Static_assert((SYSTEM_ALIGNMENT_ALGORITHM ==
                SYSTEM_ALIGNMENT_HW_QUAT_6AXIS_KNOWN_YAW) ||
               (SYSTEM_ALIGNMENT_ALGORITHM ==
                SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD) ||
               (SYSTEM_ALIGNMENT_ALGORITHM ==
                SYSTEM_ALIGNMENT_HW_QUAT_9AXIS) ||
               (SYSTEM_ALIGNMENT_ALGORITHM ==
                SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW) ||
               (SYSTEM_ALIGNMENT_ALGORITHM ==
                SYSTEM_ALIGNMENT_VECTOR_CONSTRAINTS) ||
               (SYSTEM_ALIGNMENT_ALGORITHM ==
                SYSTEM_ALIGNMENT_EXTERNAL_ATTITUDE_SOURCE),
               "Unsupported SYSTEM_ALIGNMENT_ALGORITHM");
_Static_assert(SYSTEM_ATTITUDE_POLICY == SYSTEM_ATTITUDE_SOFTWARE_ALWAYS,
               "Unsupported SYSTEM_ATTITUDE_POLICY");
_Static_assert(SYSTEM_MECHANIZATION_ALGORITHM ==
               SYSTEM_MECHANIZATION_CONING2_SCULLING2,
               "Unsupported SYSTEM_MECHANIZATION_ALGORITHM");
_Static_assert((SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_NONE) ||
               (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_KF6) ||
               (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_ESKF15) ||
               (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_SF6),
               "Unsupported SYSTEM_FUSION_ALGORITHM");

static const SystemNavigationProfile s_navigation_profile =
{
    .alignment_algorithm = SYSTEM_ALIGNMENT_ALGORITHM,
    .attitude_policy = SYSTEM_ATTITUDE_POLICY,
    .mechanization_algorithm = SYSTEM_MECHANIZATION_ALGORITHM,
    .fusion_algorithm = SYSTEM_FUSION_ALGORITHM,
    .known_yaw_deg = SYSTEM_ALIGNMENT_KNOWN_YAW_DEG,
    .known_yaw_body_axis = SYSTEM_ALIGNMENT_KNOWN_YAW_BODY_AXIS,
    .magnetic_declination_deg = SYSTEM_ALIGNMENT_MAGNETIC_DECLINATION_DEG,
    .alignment_minimum_samples = SYSTEM_ALIGNMENT_WINDOW_MIN_SAMPLES,
    .alignment_maximum_samples = SYSTEM_ALIGNMENT_WINDOW_MAX_SAMPLES,
    .alignment_minimum_duration_us =
        (uint32_t)SYSTEM_ALIGNMENT_WINDOW_MIN_DURATION_US,
    .alignment_maximum_gap_us =
        (uint32_t)SYSTEM_ALIGNMENT_WINDOW_MAX_GAP_US,
    .alignment_maximum_gyro_radps = SYSTEM_ALIGNMENT_MAX_GYRO_RADPS,
    .alignment_acceleration_tolerance_mps2 =
        SYSTEM_ALIGNMENT_ACCEL_TOLERANCE_MPS2,
    .alignment_maximum_quaternion_deviation_rad =
        SYSTEM_ALIGNMENT_MAX_QUAT_DEVIATION_RAD,
    .alignment_maximum_tilt_error_rad =
        SYSTEM_ALIGNMENT_MAX_TILT_ERROR_RAD
};

static uint8_t s_navigation_profile_frozen;

const SystemNavigationProfile *SystemNavigationProfile_Get(void)
{
    return &s_navigation_profile;
}

uint8_t SystemNavigationProfile_IsFrozen(void)
{
    return s_navigation_profile_frozen;
}

void SystemNavigationProfile_Freeze(void)
{
    s_navigation_profile_frozen = 1U;
}

void SystemNavigationProfile_UnfreezeForRollback(void)
{
    s_navigation_profile_frozen = 0U;
}
