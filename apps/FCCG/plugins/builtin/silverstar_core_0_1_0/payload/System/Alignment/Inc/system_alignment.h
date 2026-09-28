#ifndef __SYSTEM_ALIGNMENT_H
#define __SYSTEM_ALIGNMENT_H

#include <stdint.h>

#include "system_device_types.h"
#include "system_configuration_types.h"

#define SYSTEM_ALIGNMENT_SOURCE_COUNT 6U
#define SYSTEM_ALIGNMENT_SOURCE_ATTITUDE_ID 0U
#define SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN_ID 1U
#define SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN_ID 2U
#define SYSTEM_ALIGNMENT_SOURCE_MAGNETIC_ID 3U
#define SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING_ID 4U
#define SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE_ID 5U
#define SYSTEM_ALIGNMENT_SOURCE_BIT(source_id_) \
    (1UL << (source_id_))

typedef uint32_t SystemAlignmentSourceMask;

typedef enum
{
    SYSTEM_ALIGNMENT_SOURCE_ATTITUDE = SYSTEM_ALIGNMENT_SOURCE_ATTITUDE_ID,
    SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN = SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN_ID,
    SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN = SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN_ID,
    SYSTEM_ALIGNMENT_SOURCE_MAGNETIC = SYSTEM_ALIGNMENT_SOURCE_MAGNETIC_ID,
    SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING =
        SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING_ID,
    SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE =
        SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE_ID
} SystemAlignmentSourceId;

#define SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE \
    SYSTEM_ALIGNMENT_SOURCE_BIT(SYSTEM_ALIGNMENT_SOURCE_ATTITUDE_ID)
#define SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN \
    SYSTEM_ALIGNMENT_SOURCE_BIT(SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN_ID)
#define SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN \
    SYSTEM_ALIGNMENT_SOURCE_BIT(SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN_ID)
#define SYSTEM_ALIGNMENT_SOURCE_MASK_MAGNETIC \
    SYSTEM_ALIGNMENT_SOURCE_BIT(SYSTEM_ALIGNMENT_SOURCE_MAGNETIC_ID)
#define SYSTEM_ALIGNMENT_SOURCE_MASK_DUAL_GNSS_HEADING \
    SYSTEM_ALIGNMENT_SOURCE_BIT(SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING_ID)
#define SYSTEM_ALIGNMENT_SOURCE_MASK_EXTERNAL_ATTITUDE \
    SYSTEM_ALIGNMENT_SOURCE_BIT(SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE_ID)
#define SYSTEM_ALIGNMENT_SOURCE_MASK_DEFINED \
    ((1UL << SYSTEM_ALIGNMENT_SOURCE_COUNT) - 1UL)
#define SYSTEM_ALIGNMENT_AIR_PROFILE_0_SOURCE_MASK \
    (SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE | \
     SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN | \
     SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN)

#define SYSTEM_ALIGNMENT_GUARD_VALID_ACCEL    (1UL << 0)
#define SYSTEM_ALIGNMENT_GUARD_VALID_GYRO     (1UL << 1)

typedef enum
{
    SYSTEM_ALIGNMENT_STATE_IDLE = 0,
    SYSTEM_ALIGNMENT_STATE_COLLECTING,
    SYSTEM_ALIGNMENT_STATE_CHECKING,
    SYSTEM_ALIGNMENT_STATE_READY,
    SYSTEM_ALIGNMENT_STATE_FAILED,
    SYSTEM_ALIGNMENT_STATE_STALE
} SystemAlignmentState;

typedef enum
{
    SYSTEM_ALIGNMENT_STALE_REASON_NONE = 0U,
    SYSTEM_ALIGNMENT_STALE_REASON_MOTION
} SystemAlignmentStaleReason;

typedef enum
{
    SYSTEM_ALIGNMENT_COMPONENT_NOT_READY = 0,
    SYSTEM_ALIGNMENT_COMPONENT_COLLECTING,
    SYSTEM_ALIGNMENT_COMPONENT_READY,
    SYSTEM_ALIGNMENT_COMPONENT_FAILED,
    SYSTEM_ALIGNMENT_COMPONENT_DISABLED
} SystemAlignmentComponentState;

typedef enum
{
    SYSTEM_ALIGNMENT_CONFIG_OK = 0U,
    SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED,
    SYSTEM_ALIGNMENT_CONFIG_REQUIRED_UNAVAILABLE,
    SYSTEM_ALIGNMENT_CONFIG_ADAPTER_UNAVAILABLE
} SystemAlignmentConfigResult;

typedef enum
{
    SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_NONE = 0,
    SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION,
    SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_KNOWN_YAW,
    SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_MAG_TRIAD
} SystemAlignmentAttitudeSource;

typedef enum
{
    SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE = 0,
    SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT
} SystemAlignmentPreflightAttitudeSource;

typedef struct
{
    SystemAlignmentSourceId source_id;
    const char *key;
    SystemAlignmentSourceMask bit;
} SystemAlignmentSourceDescriptor;

typedef struct
{
    uint64_t timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    const char *device_name;
    SystemAlignmentComponentState state;
    SystemAlignmentAttitudeSource source;
    SystemAlignmentAlgorithm algorithm;
    float quaternion_wxyz[4];
    float acceleration_mean_b_mps2[3];
    float gyro_mean_b_radps[3];
    float magnetic_field_mean_b_uT[3];
    float final_yaw_deg;
    float known_yaw_deg;
    float magnetic_declination_deg;
    uint64_t window_start_timestamp_us;
    uint64_t window_end_timestamp_us;
    uint32_t sample_count;
    uint32_t reject_count;
    uint8_t attitude_ready;
    uint8_t quaternion_valid;
    uint8_t final_quaternion_frozen;
} SystemAlignmentAttitudeStatus;

typedef struct
{
    uint64_t observation_timestamp_us;
    uint64_t inertial_sample_timestamp_us;
    uint64_t inertial_receive_timestamp_us;
    uint32_t inertial_sequence;
    float corrected_accel_b_mps2[3];
    float corrected_gyro_b_radps[3];
    uint32_t valid_mask;
} SystemAlignmentGuardSample;

typedef struct
{
    int32_t origin_lat_e7;
    int32_t origin_lon_e7;
    int32_t origin_height_mm;
    uint32_t sample_count;
    const char *device_name;
    float horizontal_accuracy_m;
    float vertical_accuracy_m;
    SystemAlignmentComponentState state;
    uint8_t supported;
    uint8_t origin_valid;
    uint8_t ready;
} SystemAlignmentGnssStatus;

typedef struct
{
    uint32_t sample_count;
    const char *device_name;
    float origin_pressure_pa;
    float origin_altitude_m;
    SystemAlignmentComponentState state;
    uint8_t supported;
    uint8_t origin_valid;
    uint8_t ready;
} SystemAlignmentBarometerStatus;

typedef union
{
    SystemAlignmentAttitudeStatus attitude;
    SystemAlignmentGnssStatus gnss;
    SystemAlignmentBarometerStatus barometer;
} SystemAlignmentSourceDetail;

typedef struct
{
    SystemAlignmentSourceDetail detail;
    SystemAlignmentComponentState state;
    uint8_t supported;
    uint8_t selected;
    uint8_t required;
    uint8_t ready;
} SystemAlignmentSourceStatus;

typedef struct
{
    SystemAlignmentSourceStatus component[SYSTEM_ALIGNMENT_SOURCE_COUNT];
    uint32_t start_sequence;
    SystemAlignmentSourceMask capability_mask;
    SystemAlignmentSourceMask selected_mask;
    SystemAlignmentSourceMask required_mask;
    SystemAlignmentSourceMask ready_mask;
    SystemAlignmentSourceMask unavailable_mask;
    SystemAlignmentSourceMask missing_adapter_mask;
    SystemAlignmentState state;
    SystemAlignmentStaleReason stale_reason;
    SystemAlignmentConfigResult config_result;
    uint8_t ready;
} SystemAlignmentStatus;

typedef struct
{
    uint32_t start_sequence;
    SystemAlignmentSourceMask selected_mask;
    SystemAlignmentSourceMask required_mask;
    SystemAlignmentSourceMask ready_mask;
    SystemAlignmentState state;
    SystemAlignmentStaleReason stale_reason;
    SystemAlignmentPreflightAttitudeSource preflight_attitude_source;
    uint8_t ready;
} SystemAlignmentSummary;

void SystemAlignment_Init(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_Start(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_Stop(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_Process(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_StatusGet(
    SystemAlignmentStatus *status);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_DetailGet(
    SystemAlignmentStatus *detail);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_SummaryGet(
    SystemAlignmentSummary *summary);
uint8_t SystemAlignment_IsReady(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult
SystemAlignment_PreflightQuaternionGet(
    float quaternion_wxyz[4],
    SystemAlignmentPreflightAttitudeSource *source);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_Reset(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult
SystemAlignment_CalibrationInvalidate(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_PrepareMission(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_OriginsFreeze(void);
void SystemAlignment_MissionPreparationAbort(void);
uint8_t SystemAlignment_IsCollecting(void);
SystemAlignmentSourceMask SystemAlignment_CapabilityMaskGet(void);
SystemAlignmentConfigResult SystemAlignment_MasksValidate(
    SystemAlignmentSourceMask capability_mask,
    SystemAlignmentSourceMask selected_mask,
    SystemAlignmentSourceMask required_mask,
    SystemAlignmentSourceMask *unavailable_mask);
const SystemAlignmentSourceDescriptor *SystemAlignment_SourceDescriptorGet(
    SystemAlignmentSourceId source_id);
const SystemAlignmentSourceStatus *SystemAlignment_SourceStatusGet(
    const SystemAlignmentStatus *status,
    SystemAlignmentSourceId source_id);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemAlignment_SourceDetailFormat(
    const SystemAlignmentStatus *status,
    SystemAlignmentSourceId source_id,
    char *text,
    uint16_t capacity);
const char *SystemAlignment_StateText(SystemAlignmentState state);
const char *SystemAlignment_StaleReasonText(
    SystemAlignmentStaleReason reason);
const char *SystemAlignment_ComponentStateText(
    SystemAlignmentComponentState state);
const char *SystemAlignment_ConfigResultText(
    SystemAlignmentConfigResult result);
const char *SystemAlignment_AttitudeSourceText(
    SystemAlignmentAttitudeSource source);

#endif /* __SYSTEM_ALIGNMENT_H */
