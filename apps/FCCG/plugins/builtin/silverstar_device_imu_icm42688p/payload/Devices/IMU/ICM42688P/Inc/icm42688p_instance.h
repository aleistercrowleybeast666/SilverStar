#ifndef __ICM42688P_INSTANCE_H
#define __ICM42688P_INSTANCE_H

#include "system_imu_if.h"

const char * Icm42688PImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Icm42688PImuInstance_Init(uint8_t instance);
SystemDeviceResult Icm42688PImuInstance_Start(uint8_t instance);
SystemDeviceResult Icm42688PImuInstance_Stop(uint8_t instance);
SystemDeviceResult Icm42688PImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Icm42688PImuInstance_Process(uint8_t instance);
SystemDeviceResult Icm42688PImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Icm42688PImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Icm42688PImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Icm42688PImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Icm42688PImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Icm42688PImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42688PImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42688PImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Icm42688PImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42688PImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42688PImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Icm42688PImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __ICM42688P_INSTANCE_H */
