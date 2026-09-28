#ifndef __SYSTEM_MAGNETOMETER_IF_H
#define __SYSTEM_MAGNETOMETER_IF_H

#include "system_device_types.h"

#define SYSTEM_MAG_VALID_RAW           (1UL << 0)
#define SYSTEM_MAG_VALID_PHYSICAL_UNIT (1UL << 1)
#define SYSTEM_MAG_VALID_CALIBRATED    (1UL << 2)
#define SYSTEM_MAG_VALID_TEMPERATURE   (1UL << 3)

#define SYSTEM_MAG_CAP_RAW_OUTPUT          (1UL << 0)
#define SYSTEM_MAG_CAP_PHYSICAL_UNIT       (1UL << 1)
#define SYSTEM_MAG_CAP_TEMPERATURE         (1UL << 2)
#define SYSTEM_MAG_CAP_SELF_TEST           (1UL << 3)
#define SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE  (1UL << 4)
#define SYSTEM_MAG_CAP_CONFIG_RANGE        (1UL << 5)
#define SYSTEM_MAG_CAP_DEVICE_CALIBRATION  (1UL << 6)

#define SYSTEM_MAG_CFG_OUTPUT_RATE (1UL << 0)
#define SYSTEM_MAG_CFG_RANGE       (1UL << 1)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    int32_t raw[3];
    float magnetic_field_b_uT[3];
    float temperature_c;
    uint32_t valid_mask;
    uint8_t calibration_valid;
} SystemMagnetometerSample;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    uint16_t output_rate_hz;
    float range_uT;
} SystemMagnetometerConfig;

const char *SystemMagnetometer_NameGet(void);
SystemDeviceResult SystemMagnetometer_Init(void);
SystemDeviceResult SystemMagnetometer_Start(void);
SystemDeviceResult SystemMagnetometer_Stop(void);
void SystemMagnetometer_Process(void);
SystemDeviceResult SystemMagnetometer_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemMagnetometer_CapabilitiesGet(
    uint32_t *capability_mask);
SystemDeviceResult SystemMagnetometer_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemMagnetometer_LatestSampleGet(
    SystemMagnetometerSample *sample);
SystemDeviceResult SystemMagnetometer_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemMagnetometer_ConfigApply(
    const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemMagnetometer_ConfigVerify(
    const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult SystemMagnetometer_EffectiveConfigGet(
    SystemMagnetometerConfig *config);

#endif /* __SYSTEM_MAGNETOMETER_IF_H */
