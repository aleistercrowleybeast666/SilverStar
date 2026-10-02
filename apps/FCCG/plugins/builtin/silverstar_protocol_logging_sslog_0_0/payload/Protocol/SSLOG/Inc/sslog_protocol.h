#ifndef __SSLOG_PROTOCOL_H
#define __SSLOG_PROTOCOL_H

#include <stdint.h>

#include "sslog_records.h"

#define FLIGHT_LOG_FILE_HEADER_SIZE       64U
#define FLIGHT_LOG_RECORD_HEADER_SIZE     24U
#define FLIGHT_LOG_RECORD_CRC_SIZE         4U

#define FLIGHT_LOG_MAX_PAYLOAD_SIZE SSLOG_MAX_PAYLOAD_SIZE
#define FLIGHT_LOG_MAX_RECORD_SIZE \
    (FLIGHT_LOG_RECORD_HEADER_SIZE + FLIGHT_LOG_MAX_PAYLOAD_SIZE + \
     FLIGHT_LOG_RECORD_CRC_SIZE)

#define FLIGHT_LOG_PRIMARY_INERTIAL_SOURCE_ID 0U
#define FLIGHT_LOG_PRIMARY_VIRTUAL_IMU_ID     0U

typedef enum
{
    FLIGHT_LOG_EVENT_BOOT = 0x01U,
    FLIGHT_LOG_EVENT_ALIGNMENT_COMPLETE,
    FLIGHT_LOG_EVENT_MISSION_START,
    FLIGHT_LOG_EVENT_INS_RESET,
    FLIGHT_LOG_EVENT_SAMPLE_GAP,
    FLIGHT_LOG_EVENT_LOGGER_OVERFLOW,
    FLIGHT_LOG_EVENT_SD_ERROR,
    FLIGHT_LOG_EVENT_ALIGNMENT_CANDIDATE_READY,
    FLIGHT_LOG_EVENT_ALIGNMENT_APPLIED,
    FLIGHT_LOG_EVENT_ALIGNMENT_REJECTED,
    FLIGHT_LOG_EVENT_IMU_ALGORITHM_MISMATCH,
    FLIGHT_LOG_EVENT_ATTITUDE_INIT_FAILED,
    FLIGHT_LOG_EVENT_ESTIMATOR_PREDICTION_OVERFLOW,
    FLIGHT_LOG_EVENT_SYSTEM_FAULT,
    FLIGHT_LOG_EVENT_SELF_TEST_COMPLETE,
    FLIGHT_LOG_EVENT_GNSS_FIX_ACQUIRED,
    FLIGHT_LOG_EVENT_GNSS_FIX_LOST,
    FLIGHT_LOG_EVENT_ORIGIN_WINDOW_READY,
    FLIGHT_LOG_EVENT_STARTUP_DEVICE_RESULT,
    FLIGHT_LOG_EVENT_STARTUP_CONFIG_MASKS,
    FLIGHT_LOG_EVENT_STARTUP_CONFIG_FAILURES,
    FLIGHT_LOG_EVENT_STARTUP_DEVICE_DETAIL,
    FLIGHT_LOG_EVENT_STARTUP_DEVICE_NAMES,
    FLIGHT_LOG_EVENT_IMU_BIAS_WAIT,
    FLIGHT_LOG_EVENT_IMU_BIAS_COMPLETE,
    FLIGHT_LOG_EVENT_BARO_FUSION_STATE,
    FLIGHT_LOG_EVENT_START_REJECTED,
    FLIGHT_LOG_EVENT_GNSS_CONFIG_TRANSACTION,
    FLIGHT_LOG_EVENT_GNSS_NAV_SAT_DIAGNOSTIC,
    FLIGHT_LOG_EVENT_GNSS_MON_RF_DIAGNOSTIC,
    FLIGHT_LOG_EVENT_GNSS_NAV_SAT_TRANSACTION_DETAIL,
    FLIGHT_LOG_EVENT_GNSS_MON_RF_TRANSACTION_DETAIL,
    FLIGHT_LOG_EVENT_CALIBRATION_START,
    FLIGHT_LOG_EVENT_CALIBRATION_FACE_COMPLETE,
    FLIGHT_LOG_EVENT_CALIBRATION_READY,
    FLIGHT_LOG_EVENT_CALIBRATION_FAILED,
    FLIGHT_LOG_EVENT_CALIBRATION_RESULT,
    FLIGHT_LOG_EVENT_ALIGNMENT_START,
    FLIGHT_LOG_EVENT_ALIGNMENT_READY,
    FLIGHT_LOG_EVENT_ALIGNMENT_FAILED,
    FLIGHT_LOG_EVENT_PARACHUTE_DEPLOY,
    FLIGHT_LOG_EVENT_LANDING,
    FLIGHT_LOG_EVENT_PARACHUTE_DEPLOY_DETAIL,
    FLIGHT_LOG_EVENT_LANDING_IMPACT,
    FLIGHT_LOG_EVENT_SENSOR_SOURCE_CHANGE,
    FLIGHT_LOG_EVENT_GNSS_POSITION_INTEGRITY_STATE_CHANGE,
    FLIGHT_LOG_EVENT_NAV_FUSION_STATE_CHANGE, /* 0x2F; live supervisor transitions only */
    FLIGHT_LOG_EVENT_ID_LIMIT /* exclusive bound; never serialized */
} FlightLogEventId;

typedef enum
{
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_INITIAL_SELECTION = 1U,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_FAILOVER,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_RECOVERY,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_CONFIGURATION,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_PRESTART_PRIMARY_UNAVAILABLE,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_GNSS_LIVENESS_TIMEOUT,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_TELEMETRY_CONSECUTIVE_TX_TIMEOUT,
    FLIGHT_LOG_SENSOR_SOURCE_CHANGE_TELEMETRY_INIT_FAILURE
} FlightLogSensorSourceChangeReason;

#define FLIGHT_LOG_SENSOR_SOURCE_CHANGE_ARG0(device_class, old_instance, \
    new_instance, reason) \
    (((uint32_t)(device_class) & 0xFFUL) | \
     (((uint32_t)(old_instance) & 0xFFUL) << 8U) | \
     (((uint32_t)(new_instance) & 0xFFUL) << 16U) | \
     (((uint32_t)(reason) & 0xFFUL) << 24U))
#define FLIGHT_LOG_SENSOR_SOURCE_CHANGE_ARG1(old_descriptor, new_descriptor) \
    (((uint32_t)(old_descriptor) & 0xFFFFUL) | \
     (((uint32_t)(new_descriptor) & 0xFFFFUL) << 16U))

typedef struct
{
    FlightLogEventId event_id;
    uint8_t reserved[3];
    uint32_t arg0;
    uint32_t arg1;
} FlightLogEventRecord;

typedef struct
{
    uint32_t imu_queue_overflow_count;
    uint32_t logger_queue_overflow_count;
    uint32_t ins_update_count;
    uint32_t health_flags;
} FlightLogStatsRecord;

typedef struct
{
    float position_enu_m[3];
    float velocity_enu_mps[3];
    float covariance_diagonal[6];
    float gnss_position_enu_m[3];
    float gnss_velocity_enu_mps[3];
    float baro_relative_altitude_m;
    float last_position_nis;
    float last_velocity_nis;
    float last_baro_nis;
    uint32_t measurement_result_flags;
    uint32_t health_flags;
    uint32_t prediction_queue_overflow_count;
    uint32_t gnss_sequence;
    uint32_t baro_sequence;
    uint64_t gnss_timestamp_us;
    uint64_t baro_timestamp_us;
    uint32_t gnss_measurement_age_us;
    uint32_t baro_measurement_age_us;
    uint8_t gnss_origin_valid;
    uint8_t baro_origin_valid;
    uint8_t initialized;
    uint8_t mission_running;
    float q_nb[4];
    float acceleration_enu_mps2[3];
    uint32_t operation_sequence;
    uint32_t replay_epoch;
} FlightLogEstimatorRecord;

typedef struct
{
    uint8_t version[4];
    uint32_t profile_id;
    uint32_t device_config_digest;
    uint16_t configured_imu_rate_hz;
    uint16_t configured_gnss_rate_hz;
    uint16_t configured_magnetometer_rate_hz;
    uint16_t configured_barometer_rate_hz;
    uint16_t configured_hardware_quaternion_rate_hz;
    uint16_t mechanization_subsample_count;
    uint16_t expected_ins_rate_hz;
    uint16_t mechanization_min_sample_rate_hz;
    uint16_t mechanization_max_sample_rate_hz;
    uint16_t log_profile_id;
    uint32_t sync_period_us;
    uint16_t aggregation_buffer_size;
    uint8_t normal_queue_depth;
    uint8_t estimator_queue_depth;
    uint16_t device_descriptor_count;
    uint16_t algorithm_descriptor_count;
    uint16_t log_stream_descriptor_count;
    uint16_t reserved;
    float p0_diagonal[6];
    float process_accel_std_mps2[3];
    float measurement_profile[5];
    float nis_profile[7];
} FlightLogSystemConfigRecord;

typedef struct
{
    uint32_t update_sequence;
    float q_nb[4];
    float velocity_enu_mps[3];
    float position_enu_m[3];
    float accel_enu_mps2[3];
    float dt_s;
    uint32_t health_flags;
    uint8_t alignment_valid;
    uint8_t ins_valid;
} FlightLogPureInsRecord;

typedef struct
{
    float position_innovation[3];
    float velocity_innovation[3];
    float baro_innovation;
    float position_variance_r[3];
    float velocity_variance_r[3];
    float baro_variance_r;
    float position_nis;
    float velocity_nis;
    float baro_nis;
    float position_r_scale;
    float velocity_r_scale;
    float baro_r_scale;
    float process_accel_std_mps2[3];
    uint8_t gnss_velocity_valid_mask;
    uint8_t velocity_update_dimension;
    uint8_t position_update_result;
    uint8_t velocity_update_result;
    uint8_t baro_update_result;
} FlightLogKf6DiagnosticRecord;

typedef struct { float covariance_upper_triangle[21]; } FlightLogKf6FullPRecord;

typedef struct
{
    uint16_t source_descriptor_id;
    uint8_t instance_id;
    uint8_t reserved;
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float voltage_v;
    float current_a;
    float power_w;
    float state_of_charge_percent;
    float temperature_c;
    uint32_t valid_mask;
} FlightLogPowerRecord;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t compiled_mask;
    uint32_t enabled_mask;
    uint32_t present_mask;
    uint32_t healthy_mask;
    uint32_t start_blocking_mask;
    uint32_t warning_mask;
    uint32_t sequence;
    uint8_t ready;
} FlightLogHealthRecord;

typedef struct
{
    uint64_t last_transmit_timestamp_us;
    uint64_t last_receive_timestamp_us;
    uint32_t transmit_packet_count;
    uint32_t receive_packet_count;
    uint32_t transmit_error_count;
    uint32_t receive_error_count;
    uint32_t integrity_error_count;
    int16_t last_rssi_dbm;
    int8_t last_snr_q4;
    uint8_t online;
} FlightLogTelemetryDiagnosticRecord;

typedef struct
{
    uint8_t alignment_algorithm;
    uint8_t hardware_mode;
    uint8_t mode_verified;
    uint8_t origin_valid_flags;
    uint16_t alignment_sample_count;
    uint16_t gnss_sample_count;
    uint16_t barometer_sample_count;
    uint16_t reserved;
    float q_nb[4];
    float acceleration_mean_b_mps2[3];
    float gyro_mean_b_radps[3];
    float magnetic_field_mean_b_uT[3];
    int32_t gnss_origin_latitude_e7;
    int32_t gnss_origin_longitude_e7;
    int32_t gnss_origin_height_mm;
    float gnss_origin_position_std_m[3];
    float initial_velocity_enu_mps[3];
    float initial_velocity_std_mps[3];
    float barometer_origin_altitude_m;
    float barometer_origin_std_m;
    float p0_diagonal[6];
} FlightLogInitialStateRecord;

typedef struct
{
    uint16_t source_descriptor_id;
    uint8_t instance_id;
    uint8_t reserved;
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t latitude_e7;
    int32_t longitude_e7;
    int32_t ellipsoid_height_mm;
    int32_t msl_height_mm;
    float velocity_enu_mps[3];
    float velocity_variance_m2ps2[3];
    float horizontal_accuracy_m;
    float vertical_accuracy_m;
    float speed_accuracy_mps;
    uint8_t velocity_valid_mask;
    uint8_t fix_type;
    uint8_t position_usable;
    uint8_t course_usable;
    uint8_t online;
    uint8_t fix_ok;
    uint8_t satellite_count;
    uint8_t valid_group_mask;
    uint8_t measurement_timestamp_trusted;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint32_t group_reject_mask[4];
} FlightLogGnssNativeRecord;

typedef struct
{
    uint16_t source_descriptor_id;
    uint8_t instance_id;
    uint8_t reserved;
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float pressure_pa;
    float altitude_m;
    float altitude_variance_m2;
    uint32_t valid_mask;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint8_t healthy;
    uint8_t measurement_timestamp_trusted;
    uint16_t reserved_quality;
} FlightLogBaroNativeRecord;

typedef struct
{
    uint16_t source_descriptor_id;
    uint8_t instance_id;
    uint8_t reserved;
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t raw[3];
    float magnetic_field_b_uT[3];
    float temperature_c;
    uint32_t valid_mask;
    uint8_t calibration_valid;
} FlightLogMagNativeRecord;

typedef struct
{
    uint64_t interval_start_timestamp_us;
    uint64_t interval_end_timestamp_us;
    uint32_t sequence;
    float dt_s;
    float delta_theta_b_corrected[3];
    float delta_velocity_b_sculling_corrected[3];
    uint32_t health_flags;
} FlightLogInertialIncrementRecord;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float position_enu_m[3];
    float velocity_enu_mps[3];
    float position_variance_m2[3];
    float velocity_variance_m2ps2[3];
    uint8_t velocity_valid_mask;
    uint8_t position_usable;
    uint8_t fusion_allowed;
    uint8_t reserved;
    uint64_t position_measurement_timestamp_us;
    uint64_t velocity_measurement_timestamp_us;
    uint64_t estimator_present_timestamp_us;
    uint32_t receive_operation_sequence;
    uint32_t position_operation_sequence;
    uint32_t velocity_operation_sequence;
    uint32_t replay_epoch;
    uint32_t replay_generation;
    uint8_t valid_group_mask;
    uint8_t position_replay_result;
    uint8_t velocity_replay_result;
    uint8_t receive_result;
    uint8_t group_update_result[4];
    float group_nis[4];
    float position_innovation_m[3];
    float velocity_innovation_mps[3];
} FlightLogGnssMeasurementRecord;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float relative_altitude_m;
    float variance_m2;
    uint32_t valid_mask;
    uint64_t measurement_timestamp_us;
    uint64_t estimator_present_timestamp_us;
    uint32_t operation_sequence;
    uint32_t replay_epoch;
    uint32_t replay_generation;
    uint8_t update_result;
    uint8_t replay_result;
    uint8_t measurement_timestamp_trusted;
    uint8_t reserved;
    float innovation_m;
    float nis;
} FlightLogBaroMeasurementRecord;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint16_t source_id;
    uint16_t virtual_imu_id;
    uint32_t valid_mask;
    float accel_b_mps2[3];
    float gyro_b_radps[3];
    float temperature_c;
    uint8_t calibration_mode;
    uint8_t correction_valid;
    uint16_t reserved;
} FlightLogImuCorrectedRecord;

typedef struct
{
    uint16_t source_id;
    uint16_t virtual_imu_id;
    uint8_t mode;
    uint8_t state;
    uint8_t ready;
    uint8_t completed_face_mask;
    uint32_t samples;
    uint32_t reject_count;
    uint32_t retry_count;
    uint32_t start_sequence;
    float accel_bias_mps2[3];
    float accel_scale[3];
    float gyro_bias_radps[3];
    float gyro_scale[3];
} FlightLogCalibrationResultRecord;

typedef struct
{
    uint32_t capability_mask;
    uint32_t selected_mask;
    uint32_t required_mask;
    uint32_t ready_mask;
    uint32_t unavailable_mask;
    uint32_t missing_adapter_mask;
    uint32_t start_sequence;
    uint8_t state;
    uint8_t config_result;
    uint8_t ready;
    uint8_t source_count;
    uint64_t attitude_timestamp_us;
    float q_nb[4];
    int32_t gnss_origin_lat_e7;
    int32_t gnss_origin_lon_e7;
    int32_t gnss_origin_height_mm;
    uint32_t gnss_sample_count;
    float gnss_horizontal_accuracy_m;
    float gnss_vertical_accuracy_m;
    uint32_t barometer_sample_count;
    float barometer_origin_pressure_pa;
    float barometer_origin_altitude_m;
    uint8_t attitude_state;
    uint8_t gnss_state;
    uint8_t barometer_state;
    uint8_t attitude_source;
} FlightLogAlignmentResultRecord;

typedef struct
{
    uint8_t alignment_algorithm;
    uint8_t constraint_count;
    uint8_t valid_pair_count;
    uint8_t yaw_authoritative;
    uint8_t imu_source_instance;
    uint8_t magnetometer_instance;
    uint8_t external_source_instance;
    uint8_t failure_reason;
    uint16_t magnetometer_physical_device_id;
    uint16_t flags;
    uint32_t mag_calibration_generation;
    uint32_t mag_calibration_set_hash;
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    float minimum_pair_sine;
    float rms_mismatch_rad;
    float max_mismatch_rad;
} FlightLogAlignmentEvidenceRecord;

typedef struct
{
    uint32_t mission_id;
    uint32_t commit_generation;
    uint32_t snapshot_sequence;
    uint32_t imu_calibration_generation;
    uint32_t mag_calibration_set_hash;
    uint8_t base_instance;
    uint8_t ready;
    uint16_t reserved;
} FlightLogMissionSnapshotIdentityRecord;

typedef struct
{
    uint16_t physical_device_id;
    uint8_t instance_id;
    uint8_t active;
    uint8_t saved;
    uint8_t load_error;
    uint16_t reserved;
    uint32_t generation;
    uint32_t calibration_set_hash;
} FlightLogMagCalibrationIdentityRecord;

typedef struct
{
    uint8_t alignment_algorithm;
    uint8_t rocket_longitudinal_axis;
    uint8_t deploy_trigger_mask;
    uint8_t tilt_reference;
    uint8_t landing_enable;
    uint8_t landing_mode;
    uint8_t impact_capable;
    float known_yaw_deg;
    float magnetic_declination_deg;
    float tilt_threshold_deg;
    float apogee_vz_threshold_mps;
    uint32_t deploy_confirm_ms;
    uint32_t deploy_delay_ms;
    uint32_t baro_trigger_window_ms;
    uint32_t baro_trigger_min_samples;
    float baro_trigger_rate_mps;
    uint32_t candidate_duration_ms;
    float baro_confirm_rate_mps;
    float baro_max_span_m;
    uint32_t candidate_baro_min_samples;
    uint32_t candidate_imu_min_samples;
    uint32_t candidate_min_coverage_percent;
    uint32_t impact_inhibit_ms;
    float impact_threshold_mps2;
    float still_gyro_threshold_radps;
    float still_accel_tolerance_mps2;
    uint32_t landing_confirm_ms;
    uint32_t landing_sample_max_age_ms;
} FlightLogMissionConfigRecord;

typedef struct
{
    uint16_t descriptor_id;
    uint16_t physical_device_id;
    uint8_t device_class;
    uint8_t instance_id;
    uint16_t driver_id;
    uint16_t flags;
    uint32_t capability_mask;
    uint32_t configured_rate_hz;
    uint32_t driver_name_hash;
    uint32_t model_name_hash;
} FlightLogDeviceDescriptorRecord;

typedef struct
{
    uint16_t descriptor_id;
    uint8_t algorithm_class;
    uint8_t instance_id;
    uint16_t algorithm_id;
    uint16_t flags;
    uint32_t config_digest;
    uint32_t name_hash;
} FlightLogAlgorithmDescriptorRecord;

typedef struct
{
    uint8_t record_type;
    uint8_t record_version;
    uint8_t enabled;
    uint8_t policy;
    uint16_t decimation;
    uint16_t reserved;
    uint32_t period_us;
} FlightLogStreamDescriptorRecord;

typedef struct
{
    uint16_t package_schema_major;
    uint16_t package_schema_minor;
    uint16_t container_format_major;
    uint16_t container_format_minor;
    uint8_t record_catalog_hash_128[16];
    uint8_t project_semantics_hash_128[16];
    uint8_t generation_profile_hash_128[16];
    uint8_t reserved[8];
} FlightLogDecoderProfileDescriptorRecord;

typedef struct
{
    uint64_t estimator_present_timestamp_us;
    uint64_t interval_end_timestamp_us;
    uint32_t operation_sequence;
    uint32_t source_sequence;
    uint32_t replay_epoch;
    uint32_t replay_generation;
    uint8_t replay_result;
    uint8_t attitude_result;
    uint16_t reserved;
} FlightLogEstimatorStepRecord;

typedef struct
{
    uint64_t estimator_present_timestamp_us;
    uint32_t source_sequence;
    uint32_t replay_epoch;
    uint32_t quality_reject_mask[4];
    uint32_t consistency_count[4];
    uint32_t inflation_attempt_count[4];
    uint32_t reanchor_count[4];
    float inflation_factor[4];
    uint8_t valid[4];
    uint8_t update_result[4];
    uint8_t outage[4];
    uint8_t recovery_active[4];
    uint8_t reanchor_reason[4];
    uint32_t operation_sequence;
    uint32_t replay_generation;
} FlightLogGnssRecoveryRecord;

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
    uint8_t transition;
    uint8_t reset_reason;
    uint16_t reserved;
} FlightLogLandingDiagnosticRecord;

typedef struct
{
    uint32_t snapshot_id;
    uint32_t epoch;
    uint32_t source_id;
    uint32_t calibration_generation;
    uint8_t algorithm_id;
    uint8_t algorithm_revision;
    uint8_t quality_revision;
    uint8_t health;
    float position_enu_m[3];
    float velocity_enu_mps[3];
    float q_nb[4];
    float gyro_bias_radps[3];
    float accel_bias_mps2[3];
    float p_diagonal[15];
} FlightLogEskf15StateRecord;

typedef struct
{
    uint32_t snapshot_id;
    uint32_t epoch;
    uint32_t source_id;
    uint32_t calibration_generation;
    uint8_t algorithm_id;
    uint8_t phase;
    uint8_t part_index;
    uint8_t part_count;
    uint16_t offset;
    uint16_t count;
    float values[30];
} FlightLogEskf15CovariancePartRecord;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint64_t measurement_timestamp_us;
    uint64_t evaluation_timestamp_us;
    uint32_t operation_sequence;
    uint32_t epoch;
    uint32_t source_id;
    uint32_t calibration_generation;
    uint8_t group;
    uint8_t physically_valid;
    uint8_t admitted;
    uint8_t update_result;
    float observation[2];
    float innovation[2];
    float base_variance[2];
    float effective_variance[2];
    float nis;
    float quality_scale;
    float consistency_scale;
    float robust_scale;
} FlightLogEskf15MeasurementRecord;

typedef struct
{
    uint64_t interval_start_timestamp_us;
    uint64_t interval_end_timestamp_us;
    uint32_t sequence;
    uint32_t source_id;
    uint32_t calibration_generation;
    uint32_t quality_flags;
    float dt_s;
    float body_gyro_radps[6];
    float body_accel_mps2[6];
} FlightLogEskf15BodyInputRecord;

typedef struct
{
    uint64_t native_epoch_us;
    uint64_t receive_us;
    uint64_t evaluation_us;
    uint64_t window_start_us;
    uint64_t window_end_us;
    uint64_t evidence_age_us;
    uint32_t native_sequence;
    uint32_t source_id;
    uint32_t calibration_generation;
    uint32_t covered_us;
    uint32_t position_epoch_count;
    uint32_t velocity_epoch_count;
    float closure_en_m[2];
    float closure_norm_m;
    float variance_scale;
    uint8_t quality_revision;
    uint8_t physical_mask;
    uint8_t admitted_mask;
    uint8_t accepted_mask;
    uint8_t nav_output_valid;
    uint8_t health;
    uint8_t evidence_valid;
    uint8_t numsv;
    uint8_t window_reason;
    uint8_t numsv_valid;
    uint8_t window_index;
    uint8_t quality_degraded_mask;
} FlightLogNavigationQualityRecord;

typedef struct
{
    uint32_t snapshot_id;
    uint8_t algorithm_id;
    uint8_t algorithm_revision;
    uint8_t health;
    uint8_t reserved;
    float position_enu_m[3];
    float velocity_enu_mps[3];
    float q_nb[4];
    float gain[6];
} FlightLogSf6StateRecord;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint64_t measurement_timestamp_us;
    uint64_t evaluation_timestamp_us;
    uint64_t boundary_timestamp_us;
    uint32_t sequence;
    uint8_t group;
    uint8_t physically_valid;
    uint8_t result;
    uint8_t effective_update;
    float observation[2];
} FlightLogSf6MeasurementRecord;

typedef union
{
    FlightLogSf6StateRecord sf6_state;
    FlightLogSf6MeasurementRecord sf6_measurement;
    FlightLogNavigationQualityRecord navigation_quality;
    FlightLogEskf15BodyInputRecord eskf15_body_input;
    FlightLogEskf15StateRecord eskf15_state;
    FlightLogEskf15CovariancePartRecord eskf15_full_p_part;
    FlightLogEskf15StateRecord eskf15_initial_state;
    FlightLogEskf15CovariancePartRecord eskf15_initial_p_part;
    FlightLogEskf15MeasurementRecord eskf15_measurement;

    FlightLogLandingDiagnosticRecord landing_diagnostic;
    FlightLogGnssRecoveryRecord gnss_recovery;
    FlightLogEstimatorStepRecord estimator_step;
    FlightLogEventRecord event;
    FlightLogStatsRecord stats;
    FlightLogEstimatorRecord estimator;
    FlightLogSystemConfigRecord system_config;
    FlightLogPureInsRecord pure_ins;
    FlightLogKf6DiagnosticRecord kf6_diagnostic;
    FlightLogKf6FullPRecord kf6_full_p;
    FlightLogPowerRecord power;
    FlightLogHealthRecord health;
    FlightLogTelemetryDiagnosticRecord telemetry_diagnostic;
    FlightLogInitialStateRecord initial_state;
    FlightLogGnssNativeRecord gnss_native;
    FlightLogBaroNativeRecord baro_native;
    FlightLogMagNativeRecord mag_native;
    FlightLogInertialIncrementRecord inertial_increment;
    FlightLogGnssMeasurementRecord gnss_measurement;
    FlightLogBaroMeasurementRecord baro_measurement;
    FlightLogImuCorrectedRecord imu_corrected;
    FlightLogCalibrationResultRecord calibration_result;
    FlightLogAlignmentResultRecord alignment_result;
    FlightLogAlignmentEvidenceRecord alignment_evidence;
    FlightLogMissionSnapshotIdentityRecord mission_snapshot_identity;
    FlightLogMagCalibrationIdentityRecord mag_calibration_identity;
    FlightLogMissionConfigRecord mission_config;
    FlightLogDeviceDescriptorRecord device_descriptor;
    FlightLogAlgorithmDescriptorRecord algorithm_descriptor;
    FlightLogStreamDescriptorRecord stream_descriptor;
    FlightLogDecoderProfileDescriptorRecord decoder_profile_descriptor;
} FlightLogPayload;

typedef struct
{
    FlightLogRecordType record_type;
    uint64_t timestamp_us;
    uint32_t valid_flags;
    FlightLogPayload payload;
} FlightLogRecord;

typedef struct
{
    uint16_t profile_id;
    uint16_t nominal_imu_rate_hz;
    uint16_t nominal_ins_rate_hz;
    uint8_t coordinate_frame;
    uint8_t position_axis_order[3];
    uint8_t quaternion_order;
    uint8_t quaternion_semantics;
    float local_gravity_mps2;
    uint8_t air_compatibility_tag[8];
    uint8_t build_tag[8];
    uint16_t mechanization_subsample_count;
    uint8_t firmware_version[4];
} FlightLogFileHeaderInfo;

typedef enum
{
    FLIGHT_LOG_SERIALIZE_RESULT_OK = 0U,
    FLIGHT_LOG_SERIALIZE_RESULT_BAD_PARAM,
    FLIGHT_LOG_SERIALIZE_RESULT_BUFFER_SMALL,
    FLIGHT_LOG_SERIALIZE_RESULT_BAD_TYPE
} FlightLogSerializeResult;

typedef enum
{
    FLIGHT_LOG_DESERIALIZE_RESULT_OK = 0U,
    FLIGHT_LOG_DESERIALIZE_RESULT_BAD_PARAM,
    FLIGHT_LOG_DESERIALIZE_RESULT_BUFFER_SMALL,
    FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SYNC,
    FLIGHT_LOG_DESERIALIZE_RESULT_BAD_TYPE,
    FLIGHT_LOG_DESERIALIZE_RESULT_BAD_VERSION,
    FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SIZE,
    FLIGHT_LOG_DESERIALIZE_RESULT_BAD_CRC
} FlightLogDeserializeResult;

uint32_t FlightLog_Crc32(const uint8_t *data, uint32_t length);
FlightLogSerializeResult FlightLog_FileHeaderSerialize(
    const FlightLogFileHeaderInfo *info, uint8_t *buffer,
    uint16_t buffer_capacity, uint16_t *serialized_size);
FlightLogSerializeResult FlightLog_RecordSerialize(
    const FlightLogRecord *record, uint32_t record_sequence,
    uint8_t *buffer, uint16_t buffer_capacity, uint16_t *serialized_size);
FlightLogDeserializeResult FlightLog_RecordDeserialize(
    const uint8_t *buffer, uint16_t buffer_size, FlightLogRecord *record,
    uint32_t *record_sequence, uint16_t *deserialized_size);
uint16_t SslogRecords_PayloadSerialize(const FlightLogRecord *record,
    uint8_t *buffer, uint16_t buffer_capacity);
uint16_t SslogRecords_PayloadDeserialize(FlightLogRecord *record,
    const uint8_t *buffer, uint16_t buffer_size);

#endif /* __SSLOG_PROTOCOL_H */
