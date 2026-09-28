#ifndef __SYSTEM_ESTIMATOR_DIAGNOSTICS_H
#define __SYSTEM_ESTIMATOR_DIAGNOSTICS_H

#include <stdint.h>

/* Public measurement outcome and SSLOG result values are stable across
 * optional estimator implementations. */
typedef enum
{
    SYSTEM_ESTIMATOR_MEAS_ACCEPTED = 0U,
    SYSTEM_ESTIMATOR_MEAS_SOFT_WEIGHTED = 1U,
    SYSTEM_ESTIMATOR_MEAS_REJECTED_NIS = 2U,
    SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID = 3U,
    SYSTEM_ESTIMATOR_MEAS_NUMERIC_ERROR = 4U
} SystemEstimatorMeasurementResult;

typedef enum
{
    SYSTEM_ESTIMATOR_BARO_ORIGIN_UNAVAILABLE = 0,
    SYSTEM_ESTIMATOR_BARO_ORIGIN_COLLECTING,
    SYSTEM_ESTIMATOR_BARO_ORIGIN_READY,
    SYSTEM_ESTIMATOR_BARO_ORIGIN_FROZEN
} SystemEstimatorBaroOriginState;

typedef enum
{
    SYSTEM_ESTIMATOR_BARO_UPDATE_NONE = 0,
    SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED,
    SYSTEM_ESTIMATOR_BARO_UPDATE_SOFTENED,
    SYSTEM_ESTIMATOR_BARO_UPDATE_REJECTED,
    SYSTEM_ESTIMATOR_BARO_UPDATE_NO_SAMPLE,
    SYSTEM_ESTIMATOR_BARO_UPDATE_UNSUPPORTED,
    SYSTEM_ESTIMATOR_BARO_UPDATE_NOT_READY,
    SYSTEM_ESTIMATOR_BARO_UPDATE_STALE,
    SYSTEM_ESTIMATOR_BARO_UPDATE_ORIGIN_NOT_READY,
    SYSTEM_ESTIMATOR_BARO_UPDATE_INVALID,
    SYSTEM_ESTIMATOR_BARO_UPDATE_DISABLED,
    SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP
} SystemEstimatorBaroUpdateState;

typedef enum
{
    SYSTEM_ESTIMATOR_BARO_SKIP_NONE = 0,
    SYSTEM_ESTIMATOR_BARO_SKIP_NO_SAMPLE,
    SYSTEM_ESTIMATOR_BARO_SKIP_UNSUPPORTED,
    SYSTEM_ESTIMATOR_BARO_SKIP_NOT_READY,
    SYSTEM_ESTIMATOR_BARO_SKIP_STALE,
    SYSTEM_ESTIMATOR_BARO_SKIP_ORIGIN_NOT_READY,
    SYSTEM_ESTIMATOR_BARO_SKIP_INVALID,
    SYSTEM_ESTIMATOR_BARO_SKIP_DISABLED,
    SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP
} SystemEstimatorBaroSkipReason;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t last_update_timestamp_us;
    uint32_t sample_age_ms;
    uint32_t last_update_age_ms;
    uint32_t origin_sample_count;
    uint32_t origin_required_count;
    uint32_t accepted_count;
    uint32_t softened_count;
    uint32_t rejected_count;
    uint32_t skipped_count;
    float origin_altitude_m;
    float origin_pressure_pa;
    float relative_altitude_m;
    float measurement_variance;
    float last_innovation;
    float last_innovation_variance;
    float last_nis;
    SystemEstimatorBaroOriginState origin_state;
    SystemEstimatorBaroUpdateState last_update_state;
    SystemEstimatorBaroSkipReason last_skip_reason;
    uint8_t source_supported;
    uint8_t sample_valid;
    uint8_t origin_pressure_valid;
    /* Event admission is independent of the latest scheduling diagnostic. */
    uint64_t wait_start_timestamp_us;
    SystemEstimatorBaroUpdateState event_state;
    SystemEstimatorBaroSkipReason event_reason;
    uint8_t event_anomaly_active;
} SystemEstimatorBaroDiagnostics;

uint8_t SystemEstimatorBaroDiagnostics_EventPending(
    SystemEstimatorBaroDiagnostics *diagnostics);

typedef enum
{
    SYSTEM_ESTIMATOR_MODE_PURE_INS = 0,
    SYSTEM_ESTIMATOR_MODE_KF6,
    SYSTEM_ESTIMATOR_MODE_ESKF15
} SystemEstimatorMode;

typedef enum
{
    SYSTEM_ESTIMATOR_ATTITUDE_SOURCE_SOFTWARE_INS = 0,
    SYSTEM_ESTIMATOR_ATTITUDE_SOURCE_ESKF15
} SystemEstimatorAttitudeSource;

typedef enum
{
    SYSTEM_ESTIMATOR_POSITION_SOURCE_PURE_INS = 0,
    SYSTEM_ESTIMATOR_POSITION_SOURCE_KF6,
    SYSTEM_ESTIMATOR_POSITION_SOURCE_ESKF15
} SystemEstimatorPositionSource;

typedef struct
{
    uint64_t last_state_timestamp_us;
    uint32_t imu_prediction_count;
    SystemEstimatorMode mode;
    SystemEstimatorAttitudeSource attitude_source;
    SystemEstimatorPositionSource position_source;
    uint8_t initialized;
    uint8_t started;
} SystemEstimatorStatusDiagnostics;

typedef enum
{
    SYSTEM_ESTIMATOR_GNSS_UPDATE_DISABLED = 0,
    SYSTEM_ESTIMATOR_GNSS_UPDATE_WAIT_ORIGIN,
    SYSTEM_ESTIMATOR_GNSS_UPDATE_WAIT_SAMPLE,
    SYSTEM_ESTIMATOR_GNSS_UPDATE_ACCEPTED,
    SYSTEM_ESTIMATOR_GNSS_UPDATE_REJECTED,
    SYSTEM_ESTIMATOR_GNSS_UPDATE_STALE,
    SYSTEM_ESTIMATOR_GNSS_UPDATE_INVALID
} SystemEstimatorGnssUpdateState;

typedef enum
{
    SYSTEM_ESTIMATOR_GNSS_SKIP_NONE = 0,
    SYSTEM_ESTIMATOR_GNSS_SKIP_UNSUPPORTED,
    SYSTEM_ESTIMATOR_GNSS_SKIP_FUSION_MODE_DISABLED,
    SYSTEM_ESTIMATOR_GNSS_SKIP_NO_PREFLIGHT_ORIGIN,
    SYSTEM_ESTIMATOR_GNSS_SKIP_NO_SAMPLE,
    SYSTEM_ESTIMATOR_GNSS_SKIP_WAIT_STATE_CATCHUP,
    SYSTEM_ESTIMATOR_GNSS_SKIP_STALE,
    SYSTEM_ESTIMATOR_GNSS_SKIP_MEASUREMENT_INVALID,
    SYSTEM_ESTIMATOR_GNSS_SKIP_GEODESY_ERROR
} SystemEstimatorGnssSkipReason;

typedef enum
{
    SYSTEM_ESTIMATOR_GNSS_INFLATION_POSITION_HORIZONTAL = 0U,
    SYSTEM_ESTIMATOR_GNSS_INFLATION_POSITION_VERTICAL,
    SYSTEM_ESTIMATOR_GNSS_INFLATION_VELOCITY_HORIZONTAL,
    SYSTEM_ESTIMATOR_GNSS_INFLATION_VELOCITY_VERTICAL,
    SYSTEM_ESTIMATOR_GNSS_INFLATION_NONE = 0xFFU
} SystemEstimatorGnssInflationGroup;

typedef struct
{
    uint32_t quality_reject_mask;
    uint32_t consistency_count;
    uint32_t inflation_attempt_count;
    uint32_t reanchor_count;
    float inflation_factor;
    uint8_t valid;
    uint8_t update_result;
    uint8_t outage;
    uint8_t recovery_active;
    uint8_t reanchor_reason; /* 1: qualified outage, bounded inflation exhausted. */
} SystemEstimatorGnssGroupDiagnostics;

typedef struct
{
    SystemEstimatorGnssGroupDiagnostics group[4];
    uint64_t last_measurement_timestamp_us;
    uint64_t last_state_timestamp_us;
    uint32_t measurement_age_ms;
    uint32_t position_updates;
    uint32_t velocity_updates;
    uint32_t position_accept_count;
    uint32_t position_reject_count;
    uint32_t velocity_accept_count;
    uint32_t velocity_reject_count;
    int32_t origin_lat_e7;
    int32_t origin_lon_e7;
    int32_t origin_height_mm;
    SystemEstimatorGnssUpdateState last_update_state;
    SystemEstimatorGnssSkipReason last_skip_reason;
    uint8_t supported;
    uint8_t gnss_ready;
    uint8_t fusion_enabled;
    uint8_t origin_valid;
    uint8_t origin_ready;

    float position_horizontal_nis;
    float position_vertical_nis;
    float velocity_horizontal_nis;
    float velocity_vertical_nis;
    float innovation_e_m;
    float innovation_n_m;
    float innovation_u_m;
    float innovation_ve_mps;
    float innovation_vn_mps;
    float innovation_vu_mps;
    float position_horizontal_effective_std_m;
    float position_vertical_effective_std_m;
    float velocity_horizontal_effective_std_mps;
    float velocity_vertical_effective_std_mps;
    float covariance_position_e_m2;
    float covariance_position_n_m2;
    float covariance_position_u_m2;
    float covariance_velocity_e_m2ps2;
    float covariance_velocity_n_m2ps2;
    float covariance_velocity_u_m2ps2;
    float last_inflation_factor;
    uint32_t position_horizontal_accept_count;
    uint32_t position_horizontal_reject_count;
    uint32_t position_vertical_accept_count;
    uint32_t position_vertical_reject_count;
    uint32_t velocity_horizontal_accept_count;
    uint32_t velocity_horizontal_reject_count;
    uint32_t velocity_vertical_accept_count;
    uint32_t velocity_vertical_reject_count;
    uint32_t position_horizontal_reject_streak;
    uint32_t position_vertical_reject_streak;
    uint32_t velocity_horizontal_reject_streak;
    uint32_t velocity_vertical_reject_streak;
    uint32_t reacquire_count;
    uint32_t last_inflation_attempt;
    uint8_t reacquire_active_mask;
    SystemEstimatorGnssInflationGroup last_inflation_group;
} SystemEstimatorGnssDiagnostics;

typedef enum
{
    SYSTEM_KF_UPDATE_NONE = 0,
    SYSTEM_KF_UPDATE_GNSS_POSITION,
    SYSTEM_KF_UPDATE_GNSS_VELOCITY,
    SYSTEM_KF_UPDATE_BAROMETER
} SystemKfUpdateType;

typedef struct
{
    uint64_t last_update_timestamp_us;
    uint32_t prediction_count;
    uint32_t sequential_update_count;
    uint32_t position_update_count;
    uint32_t velocity_update_count;
    uint32_t baro_update_count;
    uint32_t innovation_reject_count;
    SystemKfUpdateType last_update_type;
    uint32_t reacquire_count;
    uint8_t initialized;
    uint8_t state_dimension;
    uint8_t reacquire_active_mask;
} SystemKfDiagnostics;

typedef struct
{
    uint64_t last_update_timestamp_us;
    uint32_t bias_samples;
    uint8_t initialized;
    uint8_t started;
    uint8_t attitude_ready;
    uint8_t quaternion_valid;
    uint8_t velocity_valid;
    uint8_t position_valid;
    uint8_t software_attitude_propagation;
    uint8_t bias_ready;
} SystemInsDiagnostics;

void SystemEstimatorBaroDiagnostics_Reset(void);
void SystemEstimatorBaroDiagnostics_UpdateRecord(
    SystemEstimatorBaroDiagnostics *diagnostics,
    SystemEstimatorBaroUpdateState state,
    SystemEstimatorBaroSkipReason reason,
    uint64_t timestamp_us,
    uint8_t count_event);
void SystemEstimatorBaroDiagnostics_Publish(
    const SystemEstimatorBaroDiagnostics *diagnostics);
uint8_t SystemEstimatorBaroDiagnostics_Get(
    SystemEstimatorBaroDiagnostics *diagnostics,
    uint64_t now_us);

void SystemEstimatorStatusDiagnostics_Reset(void);
void SystemEstimatorStatusDiagnostics_Publish(
    const SystemEstimatorStatusDiagnostics *diagnostics);
uint8_t SystemEstimatorStatusDiagnostics_Get(
    SystemEstimatorStatusDiagnostics *diagnostics);

void SystemEstimatorGnssDiagnostics_Reset(void);
void SystemEstimatorGnssDiagnostics_Publish(
    const SystemEstimatorGnssDiagnostics *diagnostics);
uint8_t SystemEstimatorGnssDiagnostics_Get(
    SystemEstimatorGnssDiagnostics *diagnostics,
    uint64_t now_us);

void SystemKfDiagnostics_Reset(void);
void SystemKfDiagnostics_Publish(const SystemKfDiagnostics *diagnostics);
uint8_t SystemKfDiagnostics_Get(SystemKfDiagnostics *diagnostics);

void SystemInsDiagnostics_Reset(void);
void SystemInsDiagnostics_Publish(const SystemInsDiagnostics *diagnostics);
uint8_t SystemInsDiagnostics_Get(SystemInsDiagnostics *diagnostics);

#endif /* __SYSTEM_ESTIMATOR_DIAGNOSTICS_H */
