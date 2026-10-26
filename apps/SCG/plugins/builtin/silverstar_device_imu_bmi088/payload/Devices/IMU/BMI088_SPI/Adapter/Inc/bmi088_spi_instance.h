#ifndef __BMI088_SPI_INSTANCE_H
#define __BMI088_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Bmi088SpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Bmi088SpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Bmi088SpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Bmi088SpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Bmi088SpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Bmi088SpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Bmi088SpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Bmi088SpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Bmi088SpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Bmi088SpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Bmi088SpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Bmi088SpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Bmi088SpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Bmi088SpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Bmi088SpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmi088SpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmi088SpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Bmi088SpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __BMI088_SPI_INSTANCE_H */
