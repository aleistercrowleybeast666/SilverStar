#include "system_estimator_profile.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "system_gnss_if.h"
#include "silverstar_assert.h"

static const SystemEstimatorProfile s_estimator_profile =
{
    .p0_diagonal =
    {
        SYSTEM_ESTIMATOR_P0_POSITION_E_VARIANCE_M2,
        SYSTEM_ESTIMATOR_P0_POSITION_N_VARIANCE_M2,
        SYSTEM_ESTIMATOR_P0_POSITION_U_VARIANCE_M2,
        SYSTEM_ESTIMATOR_P0_VELOCITY_E_VARIANCE_M2PS2,
        SYSTEM_ESTIMATOR_P0_VELOCITY_N_VARIANCE_M2PS2,
        SYSTEM_ESTIMATOR_P0_VELOCITY_U_VARIANCE_M2PS2
    },
    .process_accel_std_mps2 =
    {
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_VALUE,
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_VALUE,
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_VALUE
    },
    .gnss_accuracy_scale = SYSTEM_ESTIMATOR_GNSS_ACCURACY_SCALE,
    .gnss_horizontal_position_std_floor_m =
        SYSTEM_ESTIMATOR_GNSS_HORIZONTAL_STD_FLOOR_M_VALUE,
    .gnss_vertical_position_std_floor_m =
        SYSTEM_ESTIMATOR_GNSS_VERTICAL_STD_FLOOR_M_VALUE,
    .gnss_velocity_std_floor_mps =
        SYSTEM_ESTIMATOR_GNSS_VELOCITY_STD_FLOOR_MPS_VALUE,
    .barometer_altitude_std_m =
        SYSTEM_ESTIMATOR_BAROMETER_ALTITUDE_STD_M_VALUE,
    .nis_3d_soft = SYSTEM_ESTIMATOR_NIS_3D_SOFT_THRESHOLD,
    .nis_3d_hard = SYSTEM_ESTIMATOR_NIS_3D_HARD_THRESHOLD,
    .nis_2d_soft = SYSTEM_ESTIMATOR_NIS_2D_SOFT_THRESHOLD,
    .nis_2d_hard = SYSTEM_ESTIMATOR_NIS_2D_HARD_THRESHOLD,
    .nis_1d_soft = SYSTEM_ESTIMATOR_NIS_1D_SOFT_THRESHOLD,
    .nis_1d_hard = SYSTEM_ESTIMATOR_NIS_1D_HARD_THRESHOLD,
    .nis_max_r_scale = SYSTEM_ESTIMATOR_NIS_MAX_R_SCALE
};

static uint8_t s_estimator_profile_frozen;

static float SystemEstimatorProfile_Max(float lhs, float rhs)
{
    return (lhs > rhs) ? lhs : rhs;
}

const SystemEstimatorProfile *SystemEstimatorProfile_Get(void)
{
    return &s_estimator_profile;
}

uint8_t SystemEstimatorProfile_IsFrozen(void)
{
    return s_estimator_profile_frozen;
}

void SystemEstimatorProfile_Freeze(void)
{
    s_estimator_profile_frozen = 1U;
}

void SystemEstimatorProfile_UnfreezeForRollback(void)
{
    s_estimator_profile_frozen = 0U;
}

float SystemEstimatorProfile_GnssStdResolve(
    SystemEstimatorGnssStdKind kind,
    float reported_std)
{
    float floor;

    SILVERSTAR_ASSERT(kind <= SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_VELOCITY,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(isfinite(reported_std) && (reported_std >= 0.0f),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_FLOAT_NOT_FINITE);
    if (kind == SYSTEM_ESTIMATOR_GNSS_STD_HORIZONTAL_POSITION)
    {
        floor = s_estimator_profile.gnss_horizontal_position_std_floor_m;
    }
    else if (kind == SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_POSITION)
    {
        floor = s_estimator_profile.gnss_vertical_position_std_floor_m;
    }
    else if ((kind == SYSTEM_ESTIMATOR_GNSS_STD_VELOCITY) ||
             (kind == SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_VELOCITY))
    {
        floor = s_estimator_profile.gnss_velocity_std_floor_mps;
    }
    else
    {
        return 0.0f;
    }

    return SystemEstimatorProfile_Max(
        reported_std * s_estimator_profile.gnss_accuracy_scale,
        floor) * ((kind == SYSTEM_ESTIMATOR_GNSS_STD_VERTICAL_VELOCITY) ?
                   SYSTEM_ESTIMATOR_GNSS_VELOCITY_VERTICAL_SCALE : 1.0f);
}

void SystemEstimatorProfile_BuildP0(float p0[6][6],
                                    const float position_std_m[3],
                                    const float velocity_std_mps[3],
                                    uint8_t velocity_valid_mask)
{
    uint32_t index;

    if (p0 == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(p0, float, SILVERSTAR_ASSERT_MODULE_SYSTEM);

    (void)memset(p0, 0, sizeof(float) * 36U);
    for (index = 0U; index < 6U; index++)
    {
        p0[index][index] = s_estimator_profile.p0_diagonal[index];
    }

    if (position_std_m != NULL)
    {
        for (index = 0U; index < 3U; index++)
        {
            float floor_m = (index == 2U) ?
                s_estimator_profile.gnss_vertical_position_std_floor_m :
                s_estimator_profile.gnss_horizontal_position_std_floor_m;
            float std_m = position_std_m[index] *
                s_estimator_profile.gnss_accuracy_scale;

            if (std_m > 0.0f)
            {
                std_m = SystemEstimatorProfile_Max(std_m, floor_m);
                p0[index][index] = SystemEstimatorProfile_Max(
                    p0[index][index], std_m * std_m);
            }
        }
    }

    if (velocity_std_mps != NULL)
    {
        const uint8_t axis_mask[3] =
        {
            SYSTEM_GNSS_VEL_VALID_E,
            SYSTEM_GNSS_VEL_VALID_N,
            SYSTEM_GNSS_VEL_VALID_U
        };

        for (index = 0U; index < 3U; index++)
        {
            float std_mps = velocity_std_mps[index];

            if (((velocity_valid_mask & axis_mask[index]) != 0U) &&
                (std_mps > 0.0f))
            {
                std_mps = SystemEstimatorProfile_Max(
                    std_mps * s_estimator_profile.gnss_accuracy_scale,
                    s_estimator_profile.gnss_velocity_std_floor_mps);
                p0[index + 3U][index + 3U] = SystemEstimatorProfile_Max(
                    p0[index + 3U][index + 3U], std_mps * std_mps);
            }
        }
    }
}
