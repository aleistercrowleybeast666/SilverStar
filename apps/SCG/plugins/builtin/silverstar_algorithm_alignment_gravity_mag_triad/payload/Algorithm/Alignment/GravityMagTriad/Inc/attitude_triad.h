#ifndef __ATTITUDE_TRIAD_H
#define __ATTITUDE_TRIAD_H

#include <stdint.h>

#define ATTITUDE_TRIAD_WINDOW_CAPACITY 128U

typedef struct
{
    uint16_t minimum_samples;
    uint16_t maximum_samples;
    uint32_t minimum_duration_us;
    uint32_t maximum_gap_us;
    float gravity_mps2;
    float acceleration_tolerance_mps2;
    float maximum_gyro_radps;
    float magnetic_magnitude_min_uT;
    float magnetic_magnitude_max_uT;
    float magnetic_magnitude_max_deviation_ratio;
    float magnetic_direction_min_dot;
    float magnetic_horizontal_min_ratio;
} AttitudeTriadConfig;

typedef struct
{
    float accel_sum_b[3];
    float gyro_sum_b[3];
    float mag_sum_b[3];
    float magnetic_magnitude_sum_uT;
    float accel_samples_b[ATTITUDE_TRIAD_WINDOW_CAPACITY][3];
    float gyro_samples_b[ATTITUDE_TRIAD_WINDOW_CAPACITY][3];
    float mag_samples_b[ATTITUDE_TRIAD_WINDOW_CAPACITY][3];
    float magnetic_magnitude_samples_uT[ATTITUDE_TRIAD_WINDOW_CAPACITY];
    uint64_t timestamp_samples_us[ATTITUDE_TRIAD_WINDOW_CAPACITY];
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint16_t sample_count;
    uint16_t minimum_samples;
    uint16_t head;
    uint32_t reject_count;
    uint8_t valid;
} AttitudeTriadAccumulator;

void AttitudeTriad_Init(AttitudeTriadAccumulator *context);
uint8_t AttitudeTriad_AddStaticSample(
    AttitudeTriadAccumulator *context,
    const AttitudeTriadConfig *config,
    uint64_t timestamp_us,
    const float accel_b[3],
    const float gyro_b[3],
    const float mag_b[3],
    uint8_t magnetic_calibration_valid);
uint8_t AttitudeTriad_GetAverage(
    const AttitudeTriadAccumulator *context,
    float accel_mean_b[3],
    float gyro_mean_b[3],
    float mag_mean_b[3]);
uint8_t AttitudeTriad_BuildBodyToEnu(
    const AttitudeTriadAccumulator *context,
    float magnetic_declination_deg,
    float q_nb_absolute[4]);

#endif /* __ATTITUDE_TRIAD_H */
