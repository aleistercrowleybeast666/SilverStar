#ifndef __LSM6DSV320X_INSTANCE_H
#define __LSM6DSV320X_INSTANCE_H

#include "system_imu_if.h"
#include "sensor_imu.h"

const char * Lsm6Dsv320XImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Lsm6Dsv320XImuInstance_Init(uint8_t instance);
SystemDeviceResult Lsm6Dsv320XImuInstance_Start(uint8_t instance);
SystemDeviceResult Lsm6Dsv320XImuInstance_Stop(uint8_t instance);
SystemDeviceResult Lsm6Dsv320XImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Lsm6Dsv320XImuInstance_Process(uint8_t instance);
SystemDeviceResult Lsm6Dsv320XImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Lsm6Dsv320XImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Lsm6Dsv320XImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Lsm6Dsv320XImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Lsm6Dsv320XImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Lsm6Dsv320XImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Lsm6Dsv320XImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Lsm6Dsv320XImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Lsm6Dsv320XImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lsm6Dsv320XImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lsm6Dsv320XImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Lsm6Dsv320XImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

SystemDeviceResult Lsm6Dsv320XImuInstance_HighGSampleGet(uint8_t instance, SensorHighGSample *sample);

#endif /* __LSM6DSV320X_INSTANCE_H */
