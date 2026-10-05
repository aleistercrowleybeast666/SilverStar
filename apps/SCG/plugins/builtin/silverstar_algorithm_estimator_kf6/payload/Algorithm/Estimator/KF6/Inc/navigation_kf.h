#ifndef __NAVIGATION_KF_H
#define __NAVIGATION_KF_H

#include <stdint.h>

#define NAV_KF_HEALTH_NONE                 0U
#define NAV_KF_HEALTH_INVALID_INPUT        (1U << 0)
#define NAV_KF_HEALTH_MATRIX_NOT_SPD       (1U << 1)
#define NAV_KF_HEALTH_NUMERIC_ERROR        (1U << 2)
#define NAV_KF_HEALTH_COVARIANCE_RECOVERED (1U << 3)

typedef enum
{
    NAV_KF_UPDATE_ACCEPTED = 0U,
    NAV_KF_UPDATE_SOFT_WEIGHTED,
    NAV_KF_UPDATE_REJECTED_NIS,
    NAV_KF_UPDATE_REJECTED_INVALID,
    NAV_KF_UPDATE_NUMERIC_ERROR
} NavigationKfUpdateResult;

typedef enum
{
    NAV_KF_GNSS_GROUP_POSITION_HORIZONTAL = 0U,
    NAV_KF_GNSS_GROUP_POSITION_VERTICAL,
    NAV_KF_GNSS_GROUP_VELOCITY_HORIZONTAL,
    NAV_KF_GNSS_GROUP_VELOCITY_VERTICAL,
    NAV_KF_GNSS_GROUP_COUNT
} NavigationKfGnssGroup;

#define NAV_KF_GNSS_GROUP_MASK(group) \
    ((uint8_t)(1U << (uint8_t)(group)))

typedef struct
{
    uint64_t availability_timestamp_us;
    uint64_t consistency_start_us;
    uint32_t generation; /* receive-side loss/reset certificate */
    uint8_t outage;
    uint8_t loss_latched;
    uint32_t reject_streak;
    uint32_t consistent_count;
    uint32_t accepted_streak;
    uint32_t inflation_attempt_count;
    uint32_t epochs_since_inflation;
    float last_inflation_factor;
    uint8_t active;
} NavigationKfGnssReacquireGroupState;

typedef struct
{
    uint64_t timestamp_us;
    float position_enu_m[3];
    float velocity_enu_mps[3];
    float position_std_m[3];
    float velocity_std_mps[3];
    uint8_t valid_group_mask;
} NavigationKfGnssEpoch;

typedef struct
{
    NavigationKfGnssEpoch previous_epoch;
    NavigationKfGnssReacquireGroupState group[NAV_KF_GNSS_GROUP_COUNT];
    uint32_t reacquire_count;
    uint32_t reanchor_count[NAV_KF_GNSS_GROUP_COUNT];
    uint32_t last_inflation_attempt;
    float last_inflation_factor;
    uint8_t consistency_mask;
    uint8_t active_mask;
    uint8_t last_inflation_group;
    uint8_t previous_epoch_valid;
} NavigationKfGnssReacquisitionContext;

typedef struct
{
    NavigationKfUpdateResult horizontal_result;
    NavigationKfUpdateResult vertical_result;
    uint8_t horizontal_attempted;
    uint8_t vertical_attempted;
} NavigationKfGnssSeparatedUpdateResult;

typedef struct
{
    float state[6];
    float covariance[6][6];

    float process_accel_std_mps2[3];
    float baro_std_m;
    float nis_soft_threshold[3];
    float nis_hard_threshold[3];
    float nis_max_r_scale;

    float last_position_nis;
    float last_velocity_nis;
    float last_baro_nis;
    float last_gnss_group_nis[NAV_KF_GNSS_GROUP_COUNT];
    float last_position_innovation[3];
    float last_velocity_innovation[3];
    float last_position_effective_variance[3];
    float last_velocity_effective_variance[3];

    uint32_t predict_count;
    uint32_t position_accept_count;
    uint32_t position_soft_count;
    uint32_t position_reject_count;
    uint32_t velocity_accept_count;
    uint32_t velocity_soft_count;
    uint32_t velocity_reject_count;
    uint32_t baro_accept_count;
    uint32_t baro_soft_count;
    uint32_t baro_reject_count;
    uint32_t numeric_error_count;
    uint32_t gnss_group_accept_count[NAV_KF_GNSS_GROUP_COUNT];
    uint32_t gnss_group_soft_count[NAV_KF_GNSS_GROUP_COUNT];
    uint32_t gnss_group_reject_count[NAV_KF_GNSS_GROUP_COUNT];

    NavigationKfGnssReacquisitionContext gnss_reacquisition;

    uint32_t health_flags;
    uint8_t initialized;
} NavigationKfContext;

NavigationKfUpdateResult NavigationKf_UpdateGnssPositionGroups(
    NavigationKfContext *context, const float position_enu_m[3],
    const float variance_m2[3], uint8_t valid_group_mask,
    NavigationKfGnssSeparatedUpdateResult *result);
NavigationKfUpdateResult NavigationKf_UpdateGnssVelocityGroups(
    NavigationKfContext *context, const float velocity_enu_mps[3],
    const float variance_m2ps2[3], uint8_t valid_group_mask,
    NavigationKfGnssSeparatedUpdateResult *result);

void NavigationKf_Init(NavigationKfContext *context);
void NavigationKf_Reset(NavigationKfContext *context);
uint8_t NavigationKf_ResetWithCovariance(
    NavigationKfContext *context,
    const float *covariance);
uint8_t NavigationKf_Predict(NavigationKfContext *context,
                             const float delta_velocity_enu_mps[3],
                             float dt_s);
NavigationKfUpdateResult NavigationKf_UpdateGnssPosition(
    NavigationKfContext *context,
    const float position_enu_m[3],
    const float variance_m2[3]);
NavigationKfUpdateResult NavigationKf_UpdateGnssPositionSeparated(
    NavigationKfContext *context,
    const float position_enu_m[3],
    const float variance_m2[3],
    NavigationKfGnssSeparatedUpdateResult *separated_result);
NavigationKfUpdateResult NavigationKf_UpdateGnssVelocity2D(
    NavigationKfContext *context,
    const float velocity_enu_mps[2],
    const float variance_m2ps2[2]);
NavigationKfUpdateResult NavigationKf_UpdateGnssVelocity3D(
    NavigationKfContext *context,
    const float velocity_enu_mps[3],
    const float variance_m2ps2[3]);
NavigationKfUpdateResult NavigationKf_UpdateGnssVelocitySeparated(
    NavigationKfContext *context,
    const float velocity_enu_mps[3],
    const float variance_m2ps2[3],
    uint8_t vertical_valid,
    NavigationKfGnssSeparatedUpdateResult *separated_result);
NavigationKfUpdateResult NavigationKf_UpdateBaroAltitude(
    NavigationKfContext *context,
    float altitude_up_m,
    float variance_m2);
void NavigationKf_SetProcessAccelStd(NavigationKfContext *context,
                                     const float accel_std_mps2[3]);
void NavigationKf_SetBaroStd(NavigationKfContext *context,
                             float altitude_std_m);
void NavigationKf_SetNisThresholds(
    NavigationKfContext *context,
    const float soft_threshold[3],
    const float hard_threshold[3],
    float maximum_r_scale);
void NavigationKf_GnssEpochTrack(
    NavigationKfContext *context,
    const NavigationKfGnssEpoch *epoch);
NavigationKfUpdateResult NavigationKf_GnssGroupRecover(
    NavigationKfContext *context, NavigationKfGnssGroup group,
    NavigationKfUpdateResult result, const float observation[3],
    const float variance[3], uint64_t receive_timestamp_us);
void NavigationKf_GnssGroupResultProcess(
    NavigationKfContext *context,
    NavigationKfGnssGroup group,
    NavigationKfUpdateResult result);

#endif /* __NAVIGATION_KF_H */
