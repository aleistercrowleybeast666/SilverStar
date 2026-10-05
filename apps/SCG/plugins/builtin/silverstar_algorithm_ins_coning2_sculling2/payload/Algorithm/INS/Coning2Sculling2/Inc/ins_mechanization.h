#ifndef __INS_MECHANIZATION_H
#define __INS_MECHANIZATION_H

#include <stdint.h>

#define INS_ALGORITHM_VALID_ACCEL (1U << 0)
#define INS_ALGORITHM_VALID_GYRO  (1U << 1)
#define INS_ALGORITHM_VALID_QUAT  (1U << 2)

#define INS_HEALTH_NONE               0U
#define INS_HEALTH_SAMPLE_GAP         (1U << 0)
#define INS_HEALTH_INVALID_SAMPLE     (1U << 1)
#define INS_HEALTH_INVALID_QUATERNION (1U << 2)
#define INS_HEALTH_IMU_ALGORITHM_MISMATCH   (1U << 3)
#define INS_HEALTH_IMU_ALGORITHM_UNVERIFIED (1U << 4)
#define INS_HEALTH_CYCLE_DRAIN_LIMIT         (1U << 5)

typedef struct
{
    uint64_t timestamp_us;
    float accel_b_mps2[3];
    float gyro_b_radps[3];
    float q_nb[4];
    uint32_t valid_flags;
    uint32_t quality_flags;
} InsAlgorithmSample;

typedef struct
{
    uint64_t timestamp_us;
    uint64_t interval_start_timestamp_us;
    float delta_theta_b[3];
    float delta_theta_b_coning_corrected[3];
    float delta_velocity_b[3];
    float delta_velocity_b_rotation_corrected[3];
    float delta_velocity_b_sculling_corrected[3];
    float delta_velocity_n_basic[3];
    float delta_velocity_n_corrected[3];

    float accel_n_mps2[3];
    float velocity_n_mps[3];
    float position_n_m[3];
    float q_nb[4];

    float dt_s;
    uint32_t update_count;
    uint32_t health_flags;
    uint8_t valid;
} InsState;

typedef struct
{
    InsAlgorithmSample sample_history[2];
    uint8_t sample_count;
    uint32_t update_count;
    uint32_t health_flags;
} InsInertialContext;

typedef enum
{
    INS_INERTIAL_UPDATE_READY = 0,
    INS_INERTIAL_UPDATE_WAITING,
    INS_INERTIAL_UPDATE_INVALID
} InsInertialUpdateResult;

typedef struct
{
    InsInertialContext inertial;
    float velocity_n_mps[3];
    float position_n_m[3];
    float q_nb_propagated[4];
    float gravity_mps2;

    uint32_t update_count;
    uint32_t health_flags;
    uint8_t q_nb_propagated_valid;
} InsMechanizationContext;

void InsInertial_Reset(InsInertialContext *context);
InsInertialUpdateResult InsInertial_Update(InsInertialContext *context,
    const InsAlgorithmSample *sample, InsState *increment);

void InsMechanization_Init(InsMechanizationContext *context,
                           float gravity_mps2);
void InsMechanization_ResetNavigation(InsMechanizationContext *context);
uint8_t InsMechanization_ResetNavigationWithAttitude(
    InsMechanizationContext *context,
    const float initial_q_nb[4]);
void Ins_ComputeSubIntervalIncrement(const InsAlgorithmSample *previous,
                                     const InsAlgorithmSample *current,
                                     float delta_theta_b[3],
                                     float delta_velocity_b[3],
                                     float *dt_s);
void Ins_ComputeSecondOrderConing(const float delta_theta_1[3],
                                  const float delta_theta_2[3],
                                  float corrected[3]);
void Ins_ComputeSecondOrderSculling(const float delta_theta_1[3],
                                    const float delta_velocity_1[3],
                                    const float delta_theta_2[3],
                                    const float delta_velocity_2[3],
                                    float delta_velocity_corrected_b[3]);
void Ins_TransformDeltaVelocityToNavigation(const float q_nb_start[4],
                                             const float delta_velocity_b[3],
                                             float total_dt_s,
                                             float gravity_mps2,
                                             float delta_velocity_n[3]);
void Ins_IntegrateVelocity(const float previous_velocity_n[3],
                           const float delta_velocity_n[3],
                           float current_velocity_n[3]);
void Ins_IntegratePositionTrapezoidal(const float previous_position_n[3],
                                      const float previous_velocity_n[3],
                                      const float current_velocity_n[3],
                                      float dt_s,
                                      float current_position_n[3]);
uint8_t InsMechanization_Update(InsMechanizationContext *context,
                                const InsAlgorithmSample *sample,
                                InsState *state);

#endif /* __INS_MECHANIZATION_H */
