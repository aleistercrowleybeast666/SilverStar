#ifndef __SYSTEM_HARDWARE_QUATERNION_IF_H
#define __SYSTEM_HARDWARE_QUATERNION_IF_H

#include "system_device_types.h"

#define SYSTEM_HW_QUAT_CAP_OUTPUT      (1UL << 0)
#define SYSTEM_HW_QUAT_CAP_6AXIS       (1UL << 1)
#define SYSTEM_HW_QUAT_CAP_9AXIS       (1UL << 2)
#define SYSTEM_HW_QUAT_CAP_CONFIG_MODE (1UL << 3)

typedef enum
{
    SYSTEM_HW_QUAT_MODE_UNKNOWN = 0,
    SYSTEM_HW_QUAT_MODE_6AXIS,
    SYSTEM_HW_QUAT_MODE_9AXIS
} SystemHardwareQuaternionMode;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float quaternion_wxyz[4];
    SystemHardwareQuaternionMode mode;
    uint8_t mode_verified;
    /* Runtime device diagnostic only; never implies build qualification. */
    uint8_t algorithm_healthy;
    uint8_t normalized;
    uint8_t valid;
} SystemHardwareQuaternionSample;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    SystemHardwareQuaternionMode mode;
    uint16_t output_rate_hz;
} SystemHardwareQuaternionConfig;

const char *SystemHardwareQuaternion_NameGet(void);
SystemDeviceResult SystemHardwareQuaternion_Init(void);
SystemDeviceResult SystemHardwareQuaternion_Start(void);
SystemDeviceResult SystemHardwareQuaternion_Stop(void);
void SystemHardwareQuaternion_Process(void);
SystemDeviceResult SystemHardwareQuaternion_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(
    uint32_t *capability_mask);
SystemDeviceResult SystemHardwareQuaternion_HealthGet(
    SystemDeviceHealth *health);
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample);
SystemDeviceResult SystemHardwareQuaternion_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemHardwareQuaternion_ConfigApply(
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemHardwareQuaternion_ConfigVerify(
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemHardwareQuaternion_EffectiveConfigGet(
    SystemHardwareQuaternionConfig *config);

#endif /* __SYSTEM_HARDWARE_QUATERNION_IF_H */
