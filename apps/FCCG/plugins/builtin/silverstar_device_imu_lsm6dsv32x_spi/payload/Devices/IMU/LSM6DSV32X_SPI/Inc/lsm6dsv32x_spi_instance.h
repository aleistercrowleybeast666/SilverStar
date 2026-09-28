#ifndef __LSM6DSV32X_SPI_INSTANCE_H
#define __LSM6DSV32X_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Lsm6Dsv32XSpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Lsm6Dsv32XSpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __LSM6DSV32X_SPI_INSTANCE_H */
