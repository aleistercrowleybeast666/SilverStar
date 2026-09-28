#ifndef __LSM6DSV32X_INSTANCE_H
#define __LSM6DSV32X_INSTANCE_H

#include "system_imu_if.h"

const char * Lsm6Dsv32XImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XImuInstance_Init(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XImuInstance_Start(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XImuInstance_Stop(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XImuInstance_Process(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Lsm6Dsv32XImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Lsm6Dsv32XImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Lsm6Dsv32XImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Lsm6Dsv32XImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Lsm6Dsv32XImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Lsm6Dsv32XImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Lsm6Dsv32XImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Lsm6Dsv32XImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lsm6Dsv32XImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lsm6Dsv32XImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Lsm6Dsv32XImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __LSM6DSV32X_INSTANCE_H */
