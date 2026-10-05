#ifndef __SYSTEM_POWER_IF_H
#define __SYSTEM_POWER_IF_H

#include "system_device_types.h"

#define SYSTEM_POWER_VALID_VOLTAGE     (1UL << 0)
#define SYSTEM_POWER_VALID_CURRENT     (1UL << 1)
#define SYSTEM_POWER_VALID_POWER       (1UL << 2)
#define SYSTEM_POWER_VALID_SOC         (1UL << 3)
#define SYSTEM_POWER_VALID_TEMPERATURE (1UL << 4)

#define SYSTEM_POWER_CFG_VOLTAGE_SCALE  (1UL << 0)
#define SYSTEM_POWER_CFG_VOLTAGE_OFFSET (1UL << 1)
#define SYSTEM_POWER_CFG_CURRENT_SCALE  (1UL << 2)
#define SYSTEM_POWER_CFG_CURRENT_OFFSET (1UL << 3)

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    float voltage_v;
    float current_a;
    float power_w;
    float state_of_charge_percent;
    float temperature_c;
    uint32_t valid_mask;
} SystemPowerSample;

typedef struct
{
    uint32_t requested_mask;
    uint32_t required_mask;
    float voltage_scale;
    float voltage_offset_v;
    float current_scale;
    float current_offset_a;
} SystemPowerConfig;

const char *SystemPower_NameGet(void);
SystemDeviceResult SystemPower_Init(void);
SystemDeviceResult SystemPower_Start(void);
SystemDeviceResult SystemPower_Stop(void);
void SystemPower_Process(void);
SystemDeviceResult SystemPower_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemPower_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemPower_HealthGet(SystemDeviceHealth *health);
SystemDeviceResult SystemPower_LatestSampleGet(SystemPowerSample *sample);
SystemDeviceResult SystemPower_SelfTestRun(SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemPower_ConfigApply(const SystemPowerConfig *config,
                                           SystemDeviceConfigReport *report);
SystemDeviceResult SystemPower_ConfigVerify(const SystemPowerConfig *config,
                                            SystemDeviceConfigReport *report);
SystemDeviceResult SystemPower_EffectiveConfigGet(SystemPowerConfig *config);

#endif /* __SYSTEM_POWER_IF_H */
