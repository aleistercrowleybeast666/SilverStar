#ifndef __SYSTEM_NAVIGATION_PROFILE_H
#define __SYSTEM_NAVIGATION_PROFILE_H

#include <stdint.h>

#include "system_configuration_types.h"
#include "system_user_config.h"

typedef struct
{
    SystemAlignmentAlgorithm alignment_algorithm;
    SystemAttitudePolicy attitude_policy;
    SystemMechanizationAlgorithm mechanization_algorithm;
    SystemFusionAlgorithm fusion_algorithm;
    float known_yaw_deg;
    int8_t known_yaw_body_axis;
    float magnetic_declination_deg;
    uint16_t alignment_minimum_samples;
    uint16_t alignment_maximum_samples;
    uint32_t alignment_minimum_duration_us;
    uint32_t alignment_maximum_gap_us;
    float alignment_maximum_gyro_radps;
    float alignment_acceleration_tolerance_mps2;
    float alignment_maximum_quaternion_deviation_rad;
    float alignment_maximum_tilt_error_rad;
} SystemNavigationProfile;

const SystemNavigationProfile *SystemNavigationProfile_Get(void);
uint8_t SystemNavigationProfile_IsFrozen(void);
void SystemNavigationProfile_Freeze(void);
void SystemNavigationProfile_UnfreezeForRollback(void);

#endif /* __SYSTEM_NAVIGATION_PROFILE_H */
