#ifndef __BMI323_SPI_INSTANCE_H
#define __BMI323_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Bmi323SpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Bmi323SpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Bmi323SpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Bmi323SpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Bmi323SpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Bmi323SpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Bmi323SpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Bmi323SpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Bmi323SpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Bmi323SpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Bmi323SpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Bmi323SpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Bmi323SpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Bmi323SpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Bmi323SpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmi323SpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmi323SpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Bmi323SpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __BMI323_SPI_INSTANCE_H */
