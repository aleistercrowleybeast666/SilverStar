#ifndef __SYSTEM_INERTIAL_TYPES_H
#define __SYSTEM_INERTIAL_TYPES_H

#include <stdint.h>
#include "system_imu_epoch_if.h"

#define SYSTEM_INERTIAL_VALID_ACCEL       (1UL << 0)
#define SYSTEM_INERTIAL_VALID_GYRO        (1UL << 1)
#define SYSTEM_INERTIAL_VALID_TEMPERATURE (1UL << 2)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t accel_raw[3];
    int32_t gyro_raw[3];
    float accel_b_mps2[3];
    float gyro_b_radps[3];
    float temperature_c;
    uint32_t valid_mask;
    uint32_t quality_flags; /* Device evidence, preserved without changing raw values. */
#if (SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U)
    uint32_t source_id;
    uint32_t config_epoch;
#endif
} SystemInertialSample;

static inline uint32_t SystemInertialSample_SourceGet(const SystemInertialSample *sample)
{
#if (SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U)
    return sample->source_id;
#else
    (void)sample;
    return 0U;
#endif
}

static inline uint32_t SystemInertialSample_EpochGet(const SystemInertialSample *sample)
{
#if (SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U)
    return sample->config_epoch;
#else
    (void)sample;
    return 0U;
#endif
}

static inline void SystemInertialSample_EpochSet(SystemInertialSample *sample,
    uint32_t source, uint32_t epoch)
{
#if (SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U)
    sample->source_id = source;
    sample->config_epoch = epoch;
#else
    (void)sample;
    (void)source;
    (void)epoch;
#endif
}

#endif /* __SYSTEM_INERTIAL_TYPES_H */
