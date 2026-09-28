#ifndef __ATTITUDE_ALIGNMENT_H
#define __ATTITUDE_ALIGNMENT_H

#include <stdint.h>

#define ATTITUDE_ALIGNMENT_WINDOW_CAPACITY 128U

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
} AttitudeAlignmentWindowConfig;

typedef struct
{
    float quaternion_reference_wxyz[4];
    float quaternion_sum_wxyz[4];
    float acceleration_sum_b_mps2[3];
    float gyro_sum_b_radps[3];
    float quaternion_samples_wxyz[ATTITUDE_ALIGNMENT_WINDOW_CAPACITY][4];
    float acceleration_samples_b_mps2[ATTITUDE_ALIGNMENT_WINDOW_CAPACITY][3];
    float gyro_samples_b_radps[ATTITUDE_ALIGNMENT_WINDOW_CAPACITY][3];
    uint64_t timestamp_samples_us[ATTITUDE_ALIGNMENT_WINDOW_CAPACITY];
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint32_t sample_count;
    uint32_t quaternion_sample_count;
    uint32_t reject_count;
    uint16_t head;
    uint8_t valid;
} AttitudeAlignmentWindow;

void AttitudeAlignmentWindow_Init(AttitudeAlignmentWindow *context);
void AttitudeAlignmentWindow_Reset(AttitudeAlignmentWindow *context);
uint8_t AttitudeAlignmentWindow_Add(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    uint64_t timestamp_us,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3],
    const float quaternion_wxyz[4]);
uint8_t AttitudeAlignmentWindow_AddInertial(
    AttitudeAlignmentWindow *context,
    const AttitudeAlignmentWindowConfig *config,
    uint64_t timestamp_us,
    const float acceleration_b_mps2[3],
    const float gyro_b_radps[3]);
uint8_t AttitudeAlignmentWindow_GetAverage(
    const AttitudeAlignmentWindow *context,
    float quaternion_wxyz[4],
    float acceleration_b_mps2[3],
    float gyro_b_radps[3]);
uint8_t AttitudeAlignmentWindow_GetInertialAverage(
    const AttitudeAlignmentWindow *context,
    float acceleration_b_mps2[3],
    float gyro_b_radps[3]);
uint8_t AttitudeAlignment_ApplyKnownYaw(
    const float source_q_nb[4],
    int8_t yaw_body_axis,
    float yaw_deg,
    float output_q_nb[4]);
/* Legacy source name; semantics are SilverStar ENU yaw, not compass heading. */
uint8_t AttitudeAlignment_ApplyKnownHeading(
    const float source_q_nb[4],
    int8_t heading_body_axis,
    float heading_deg,
    float output_q_nb[4]);
uint8_t AttitudeAlignment_TiltConsistent(
    const float q_nb[4],
    const float acceleration_b_mps2[3],
    float maximum_tilt_error_rad);

#endif /* __ATTITUDE_ALIGNMENT_H */
