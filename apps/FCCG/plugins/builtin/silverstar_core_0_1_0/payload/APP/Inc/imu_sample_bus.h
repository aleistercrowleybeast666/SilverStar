#ifndef __IMU_SAMPLE_BUS_H
#define __IMU_SAMPLE_BUS_H

#include <stdint.h>

#include "system_inertial.h"
#include "system_user_config.h"

#define IMU_SAMPLE_BUS_DEPTH SYSTEM_IMU_SAMPLE_BUS_DEPTH

typedef SystemInertialSample InsImuSample;

typedef struct
{
    uint16_t count;
    uint32_t push_count;
    uint32_t pop_count;
    uint32_t overflow_count;
    uint32_t source_gap_count;
} ImuSampleBusStats;

typedef enum
{
    IMU_SAMPLE_BUS_BIAS_STATE_WAIT_STREAM = 0U,
    IMU_SAMPLE_BUS_BIAS_STATE_SETTLING,
    IMU_SAMPLE_BUS_BIAS_STATE_COLLECTING_WINDOW,
    IMU_SAMPLE_BUS_BIAS_STATE_READY
} ImuSampleBusBiasState;

typedef enum
{
    IMU_SAMPLE_BUS_BIAS_WAIT_NONE = 0U,
    IMU_SAMPLE_BUS_BIAS_WAIT_NO_STREAM,
    IMU_SAMPLE_BUS_BIAS_WAIT_GYRO_MOVING,
    IMU_SAMPLE_BUS_BIAS_WAIT_ACCEL_MAGNITUDE,
    IMU_SAMPLE_BUS_BIAS_WAIT_GRAVITY_DIRECTION,
    IMU_SAMPLE_BUS_BIAS_WAIT_VARIANCE,
    IMU_SAMPLE_BUS_BIAS_WAIT_SAMPLE_GAP
} ImuSampleBusBiasWaitReason;

typedef struct
{
    float accel_bias_b_mps2[3];
    float gyro_bias_b_radps[3];
    uint32_t window_valid_sample_count;
    uint32_t window_reject_count;
    uint32_t retry_count;
    ImuSampleBusBiasState state;
    ImuSampleBusBiasWaitReason wait_reason;
    uint8_t mode;
    uint8_t startup_up_direction;
    uint8_t ready;
} ImuSampleBusBiasSnapshot;

typedef enum
{
    IMU_SAMPLE_BUS_RESULT_OK = 0U,
    IMU_SAMPLE_BUS_RESULT_EMPTY,
    IMU_SAMPLE_BUS_RESULT_FULL,
    IMU_SAMPLE_BUS_RESULT_BAD_PARAM,
    IMU_SAMPLE_BUS_RESULT_NOT_READY
} ImuSampleBusResult;

ImuSampleBusResult ImuSampleBus_Init(void);
void ImuSampleBus_Reset(void);
void ImuSampleBus_Process(void);
ImuSampleBusResult ImuSampleBus_Pop(InsImuSample *sample);
void ImuSampleBus_StatsGet(ImuSampleBusStats *stats);
void ImuSampleBus_BiasSnapshotGet(ImuSampleBusBiasSnapshot *snapshot);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult ImuSampleBus_BiasReset(void);

#endif /* __IMU_SAMPLE_BUS_H */
