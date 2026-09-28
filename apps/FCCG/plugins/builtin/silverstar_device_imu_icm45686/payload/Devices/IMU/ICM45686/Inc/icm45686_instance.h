#ifndef __ICM45686_INSTANCE_H
#define __ICM45686_INSTANCE_H

#include "system_imu_if.h"

const char * Icm45686ImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Icm45686ImuInstance_Init(uint8_t instance);
SystemDeviceResult Icm45686ImuInstance_Start(uint8_t instance);
SystemDeviceResult Icm45686ImuInstance_Stop(uint8_t instance);
SystemDeviceResult Icm45686ImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Icm45686ImuInstance_Process(uint8_t instance);
SystemDeviceResult Icm45686ImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Icm45686ImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Icm45686ImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Icm45686ImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Icm45686ImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Icm45686ImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm45686ImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm45686ImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Icm45686ImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm45686ImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm45686ImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Icm45686ImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __ICM45686_INSTANCE_H */
