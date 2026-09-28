#ifndef __ICM42605_INSTANCE_H
#define __ICM42605_INSTANCE_H

#include "system_imu_if.h"

const char * Icm42605ImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Icm42605ImuInstance_Init(uint8_t instance);
SystemDeviceResult Icm42605ImuInstance_Start(uint8_t instance);
SystemDeviceResult Icm42605ImuInstance_Stop(uint8_t instance);
SystemDeviceResult Icm42605ImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Icm42605ImuInstance_Process(uint8_t instance);
SystemDeviceResult Icm42605ImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Icm42605ImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Icm42605ImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Icm42605ImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Icm42605ImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Icm42605ImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42605ImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42605ImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Icm42605ImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42605ImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42605ImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Icm42605ImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __ICM42605_INSTANCE_H */
