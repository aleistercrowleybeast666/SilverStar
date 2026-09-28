#ifndef __SYSTEM_INERTIAL_TYPES_H
#define __SYSTEM_INERTIAL_TYPES_H

#include <stdint.h>

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
} SystemInertialSample;

#endif /* __SYSTEM_INERTIAL_TYPES_H */
