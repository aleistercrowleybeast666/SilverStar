#ifndef __SYSTEM_FLIGHT_RECOVERY_H
#define __SYSTEM_FLIGHT_RECOVERY_H

#include <stdint.h>

#include "system_device_types.h"
#include "system_mission_action_if.h"
#include "system_configuration_types.h"

typedef enum
{
    SYSTEM_FLIGHT_LANDING_STATE_DISABLED = 0,
    SYSTEM_FLIGHT_LANDING_STATE_WAIT_RECOVERY,
    SYSTEM_FLIGHT_LANDING_STATE_BARO_MONITOR,
    SYSTEM_FLIGHT_LANDING_STATE_BARO_IMU_CANDIDATE,
    SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT,
    SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED,
    SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED,
    SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM,
    SYSTEM_FLIGHT_LANDING_STATE_LANDED
} SystemFlightLandingState;

typedef enum
{
    SYSTEM_LANDING_RESET_NONE = 0U,
    SYSTEM_LANDING_RESET_IMU_INVALID,
    SYSTEM_LANDING_RESET_IMU_COVERAGE,
    SYSTEM_LANDING_RESET_IMU_CONTINUOUS_MOTION,
    SYSTEM_LANDING_RESET_BARO_INVALID,
    SYSTEM_LANDING_RESET_BARO_STALE,
    SYSTEM_LANDING_RESET_BARO_COVERAGE,
    SYSTEM_LANDING_RESET_BARO_SLOPE,
    SYSTEM_LANDING_RESET_BARO_SPAN,
    SYSTEM_LANDING_RESET_TIMESTAMP_DISCONTINUITY
} SystemLandingResetReason;

typedef struct
{
    uint64_t evaluation_timestamp_us;
    uint64_t candidate_start_timestamp_us;
    uint32_t sequence;
    uint32_t candidate_elapsed_us;
    float valid_coverage;
    float still_ratio;
    uint32_t maximum_bad_duration_us;
    float baro_slope_mps;
    float baro_span_m;
    float baro_coverage;
    uint8_t transition; /* 1 start, 2 reset, 3 complete. */
    SystemLandingResetReason reset_reason;
} SystemLandingDiagnostic;

typedef struct
{
    uint64_t now_us;
    uint32_t mission_time_ms;

    uint64_t estimator_timestamp_us;
    uint32_t estimator_sequence;
    float q_nb[4];
    float velocity_enu_mps[3];
    float initial_q_nb[4];

    uint64_t ins_timestamp_us;
    uint32_t ins_sequence;
    float linear_accel_n_mps2[3];

    uint64_t inertial_timestamp_us;
    uint32_t inertial_sequence;
    float corrected_accel_b_mps2[3];
    float corrected_gyro_b_radps[3];

    uint64_t barometer_timestamp_us;
    uint32_t barometer_sequence;
    float barometer_altitude_m;

    uint8_t attitude_valid;
    uint8_t velocity_valid;
    uint8_t initial_attitude_valid;
    uint8_t linear_accel_valid;
    uint8_t corrected_accel_valid;
    uint8_t corrected_gyro_valid;
    uint8_t barometer_healthy;
    uint8_t barometer_valid;
} SystemFlightRecoveryInput;

typedef struct
{
    uint64_t last_process_timestamp_us;
    SystemLandingDiagnostic landing_diagnostic;
    uint32_t sequence;

    SystemDeployTriggerMask deploy_trigger_mask;
    SystemBodyAxis rocket_longitudinal_axis;
    SystemTiltReference tilt_reference;
    float initial_rocket_axis_n[3];
    uint8_t initial_rocket_axis_valid;
    uint8_t initialized;

    uint8_t mission_start_action_done;
    SystemDeviceResult mission_start_action_result;

    uint8_t deploy_confirming;
    uint8_t deploy_triggered;
    uint8_t deploy_completed;
    SystemDeployTriggerMask deploy_matched_mask;
    float deploy_trigger_value;
    float deploy_tilt_angle_deg;
    float deploy_vertical_velocity_mps;
    uint32_t deploy_delay_ms;
    SystemDeviceResult deploy_action_result;
    SystemDeviceResult recovery_transition_result;
    uint32_t deploy_event_sequence;
    uint64_t deploy_event_timestamp_us;
    uint32_t deploy_event_mission_time_ms;

    uint8_t landing_enabled;
    SystemLandingMode landing_mode;
    SystemFlightLandingState landing_state;
    uint8_t landing_confirming;
    uint8_t landing_detected;
    uint8_t barometer_valid;
    uint8_t landing_candidate_active;
    uint8_t impact_capable;
    uint8_t impact_armed;
    uint32_t barometer_age_ms;
    uint32_t landing_candidate_elapsed_ms;
    uint32_t landing_candidate_baro_count;
    uint32_t landing_candidate_imu_count;
    float barometer_trigger_rate_mps;
    float landing_candidate_baro_slope_mps;
    float landing_candidate_baro_span_m;
    float landing_candidate_gyro_norm_radps;
    float landing_candidate_accel_norm_mps2;
    float landing_candidate_gravity_error_mps2;
    float impact_threshold_mps2;
    SystemDeviceResult landing_transition_result;
    uint32_t landing_event_sequence;
    uint64_t landing_event_timestamp_us;
    uint32_t landing_event_mission_time_ms;

    uint32_t impact_event_sequence;
    uint64_t impact_event_timestamp_us;
    uint32_t impact_event_mission_time_ms;
    float impact_metric_mps2;
    float impact_peak_mps2;

    uint32_t action_event_sequence;
    SystemMissionAction last_action;
    SystemDeviceResult last_action_result;
    uint64_t last_action_timestamp_us;
    uint32_t last_action_mission_time_ms;
} SystemFlightRecoveryStatus;

SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemFlightRecovery_Init(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemFlightRecovery_Process(
    const SystemFlightRecoveryInput *input);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemFlightRecovery_StatusGet(
    SystemFlightRecoveryStatus *status);
const char *SystemFlightRecovery_DeployTriggerMaskText(
    SystemDeployTriggerMask mask);
const char *SystemFlightRecovery_TiltReferenceText(SystemTiltReference mode);
const char *SystemFlightRecovery_LandingModeText(SystemLandingMode mode);
const char *SystemFlightRecovery_LandingStateText(
    SystemFlightLandingState state);
const char *SystemFlightRecovery_ActionText(SystemMissionAction action);

#endif /* __SYSTEM_FLIGHT_RECOVERY_H */
