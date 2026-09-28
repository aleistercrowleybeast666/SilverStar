#ifndef __ALIGNMENT_STRATEGY_TYPES_H
#define __ALIGNMENT_STRATEGY_TYPES_H

#include <stdint.h>

typedef enum
{
    ALIGNMENT_STRATEGY_PROCESS_INVALID = 0,
    ALIGNMENT_STRATEGY_PROCESS_WAITING,
    ALIGNMENT_STRATEGY_PROCESS_REJECTED,
    ALIGNMENT_STRATEGY_PROCESS_ACCEPTED,
    ALIGNMENT_STRATEGY_PROCESS_READY
} AlignmentStrategyProcessResult;

typedef struct
{
    uint16_t minimum_samples;
    uint16_t maximum_samples;
    uint32_t minimum_duration_us;
    uint32_t maximum_gap_us;
    float gravity_mps2;
    float acceleration_tolerance_mps2;
    float maximum_gyro_radps;
    float maximum_quaternion_deviation_rad;
    float maximum_tilt_error_rad;
    float known_yaw_deg;
    int8_t known_yaw_body_axis;
    float magnetic_declination_deg;
    float magnetic_magnitude_min_uT;
    float magnetic_magnitude_max_uT;
    float magnetic_magnitude_max_deviation_ratio;
    float magnetic_direction_min_dot;
    float magnetic_horizontal_min_ratio;
} AlignmentStrategyConfig;

typedef struct
{
    uint64_t timestamp_us;
    float acceleration_b_mps2[3];
    float gyro_b_radps[3];
    uint64_t magnetometer_timestamp_us;
    uint32_t magnetometer_sequence;
    float magnetic_field_b_uT[3];
    uint8_t magnetometer_available;
    uint8_t magnetometer_calibrated;
    uint64_t quaternion_timestamp_us;
    uint32_t quaternion_sequence;
    float quaternion_wxyz[4];
    uint8_t quaternion_available;
    uint8_t quaternion_mode;
    uint8_t quaternion_mode_verified;
} AlignmentStrategySample;

typedef struct
{
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint32_t sample_count;
    uint32_t reject_count;
    float q_nb[4];
    float acceleration_mean_b_mps2[3];
    float gyro_mean_b_radps[3];
    float magnetic_field_mean_b_uT[3];
    uint8_t hardware_mode;
    uint8_t hardware_mode_verified;
    uint8_t magnetic_field_valid;
} AlignmentStrategyOutput;

#endif /* __ALIGNMENT_STRATEGY_TYPES_H */
