#ifndef __SYSTEM_ESTIMATOR_PROFILE_H
#define __SYSTEM_ESTIMATOR_PROFILE_H

#include <stdint.h>

#include "system_user_config.h"

typedef struct
{
    float p0_diagonal[6];
    float process_accel_std_mps2[3];
    float gnss_accuracy_scale;
    float gnss_horizontal_position_std_floor_m;
    float gnss_vertical_position_std_floor_m;
    float gnss_velocity_std_floor_mps;
    float barometer_altitude_std_m;
    float nis_3d_soft;
    float nis_3d_hard;
    float nis_2d_soft;
    float nis_2d_hard;
    float nis_1d_soft;
    float nis_1d_hard;
    float nis_max_r_scale;
} SystemEstimatorProfile;

typedef enum
{
    SYSTEM_ESTIMATOR_GNSS_STD_HORIZONTAL_POSITION = 0,
    SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_POSITION,
    SYSTEM_ESTIMATOR_GNSS_STD_VELOCITY,
    SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_VELOCITY
} SystemEstimatorGnssStdKind;

const SystemEstimatorProfile *SystemEstimatorProfile_Get(void);
uint8_t SystemEstimatorProfile_IsFrozen(void);
void SystemEstimatorProfile_Freeze(void);
void SystemEstimatorProfile_UnfreezeForRollback(void);
float SystemEstimatorProfile_GnssStdResolve(
    SystemEstimatorGnssStdKind kind,
    float reported_std);
void SystemEstimatorProfile_BuildP0(float p0[6][6],
                                    const float position_std_m[3],
                                    const float velocity_std_mps[3],
                                    uint8_t velocity_valid_mask);

#endif /* __SYSTEM_ESTIMATOR_PROFILE_H */
