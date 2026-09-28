#ifndef __BMI088_SYNC400_INSTANCE_H
#define __BMI088_SYNC400_INSTANCE_H

#include "system_imu_if.h"

const char * Bmi088Sync400ImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Bmi088Sync400ImuInstance_Init(uint8_t instance);
SystemDeviceResult Bmi088Sync400ImuInstance_Start(uint8_t instance);
SystemDeviceResult Bmi088Sync400ImuInstance_Stop(uint8_t instance);
SystemDeviceResult Bmi088Sync400ImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Bmi088Sync400ImuInstance_Process(uint8_t instance);
SystemDeviceResult Bmi088Sync400ImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Bmi088Sync400ImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Bmi088Sync400ImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Bmi088Sync400ImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Bmi088Sync400ImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Bmi088Sync400ImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Bmi088Sync400ImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Bmi088Sync400ImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Bmi088Sync400ImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmi088Sync400ImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmi088Sync400ImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Bmi088Sync400ImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __BMI088_SYNC400_INSTANCE_H */
