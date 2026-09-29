#ifndef __INS_TASK_H
#define __INS_TASK_H

#include <stdint.h>

#include "system_device_types.h"
#include "system_hardware_quaternion_if.h"
#include "system_alignment.h"
#include "system_navigation_profile.h"

typedef struct
{
    uint64_t timestamp_us;
    uint32_t update_seq;

    float q_nb[4];
    float velocity_n_mps[3];
    float position_n_m[3];
    float accel_n_mps2[3];
    float dt_s;
    uint32_t health_flags;
    uint8_t alignment_valid;
    uint8_t ins_valid;
    uint8_t mission_running;
} InsOutputSnapshot;

typedef struct
{
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint32_t sample_count;
    uint32_t reject_count;
    SystemAlignmentAlgorithm algorithm;
    SystemHardwareQuaternionMode hardware_mode;
    float q_nb[4];
    float acceleration_mean_b_mps2[3];
    float gyro_mean_b_radps[3];
    float magnetic_field_mean_b_uT[3];
    float minimum_pair_sine;
    float rms_mismatch_rad;
    float max_mismatch_rad;
    uint8_t constraint_count;
    uint8_t valid_pair_count;
    uint8_t mode_verified;
    uint8_t valid;
} InsAlignmentSnapshot;

void AppTask_Ins(void *argument);
SystemDeviceResult InsTask_PrepareStart(void);
SystemDeviceResult InsTask_InitializeMission(void);
SystemDeviceResult InsTask_PrepareNavigation(const float q_nb[4]);
void InsTask_AbortMission(void);
uint8_t Ins_IsMissionRunning(void);
uint8_t Ins_IsReadyForMission(void);
uint8_t Ins_GetInitialAttitude(float q_nb[4]);
uint8_t Ins_GetAlignmentSnapshot(InsAlignmentSnapshot *snapshot);
uint8_t Ins_GetLatestSnapshot(InsOutputSnapshot *snapshot);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult InsTask_AlignmentReset(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult
InsTask_AttitudeAlignmentStatusGet(SystemAlignmentAttitudeStatus *status);

#endif /* __INS_TASK_H */
