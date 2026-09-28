#ifndef __SYSTEM_INERTIAL_SOURCE_IF_H
#define __SYSTEM_INERTIAL_SOURCE_IF_H

#include <stdint.h>

#include "system_device_types.h"

#define SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_X (1UL << 0)
#define SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_Y (1UL << 1)
#define SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_Z (1UL << 2)
#define SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X  (1UL << 3)
#define SYSTEM_INERTIAL_SOURCE_VALID_GYRO_Y  (1UL << 4)
#define SYSTEM_INERTIAL_SOURCE_VALID_GYRO_Z  (1UL << 5)
#define SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ \
    (SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_X | \
     SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_Y | \
     SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_Z)
#define SYSTEM_INERTIAL_SOURCE_VALID_GYRO_XYZ \
    (SYSTEM_INERTIAL_SOURCE_VALID_GYRO_X | \
     SYSTEM_INERTIAL_SOURCE_VALID_GYRO_Y | \
     SYSTEM_INERTIAL_SOURCE_VALID_GYRO_Z)
#define SYSTEM_INERTIAL_SOURCE_VALID_6DOF \
    (SYSTEM_INERTIAL_SOURCE_VALID_ACCEL_XYZ | \
     SYSTEM_INERTIAL_SOURCE_VALID_GYRO_XYZ)

typedef uint32_t SystemInertialSourceId;

typedef enum
{
    SYSTEM_INERTIAL_TIMESTAMP_UNKNOWN = 0U,
    SYSTEM_INERTIAL_TIMESTAMP_HARDWARE,
    SYSTEM_INERTIAL_TIMESTAMP_DRDY_CAPTURE,
    SYSTEM_INERTIAL_TIMESTAMP_SOFTWARE_ESTIMATED,
    SYSTEM_INERTIAL_TIMESTAMP_RECEIVE_ONLY
} SystemInertialTimestampQuality;

typedef enum
{
    SYSTEM_INERTIAL_SYNC_PASSTHROUGH = 0U,
    SYSTEM_INERTIAL_SYNC_NEAREST,
    SYSTEM_INERTIAL_SYNC_HOLD_LAST,
    SYSTEM_INERTIAL_SYNC_LINEAR_INTERPOLATE
} SystemInertialTimeSyncPolicy;

typedef enum
{
    SYSTEM_INERTIAL_CORRECTION_NONE = 0U,
    SYSTEM_INERTIAL_CORRECTION_BIAS_ONLY,
    SYSTEM_INERTIAL_CORRECTION_DIAGONAL,
    SYSTEM_INERTIAL_CORRECTION_FULL_MATRIX
} SystemInertialCorrectionMode;

typedef struct
{
    SystemInertialSourceId source_id;
    uint32_t sequence;
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    SystemInertialTimestampQuality timestamp_quality;
    uint32_t valid_mask;
    float accel_mps2[3];
    float gyro_radps[3];
} SystemInertialSourceSample;

typedef struct
{
    SystemInertialCorrectionMode mode;
    float accel_bias_mps2[3];
    float gyro_bias_radps[3];
    float accel_matrix[3][3];
    float gyro_matrix[3][3];
} SystemInertialSourceCorrection;

typedef struct
{
    SystemInertialSourceId source_id;
    const char *name;
    SystemInertialTimestampQuality timestamp_quality;
    float sensor_to_body[3][3];
} SystemInertialSourceDescriptor;

typedef struct
{
    SystemInertialTimeSyncPolicy policy;
    SystemInertialSourceId master_source;
    uint32_t max_skew_us;
    uint32_t stale_us;
} SystemInertialTimeSyncConfig;

SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult
SystemInertialSource_CorrectionApply(
    const SystemInertialSourceSample *measured,
    const SystemInertialSourceCorrection *correction,
    SystemInertialSourceSample *corrected);

#endif /* __SYSTEM_INERTIAL_SOURCE_IF_H */
