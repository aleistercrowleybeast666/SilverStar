#ifndef __ICM45686_SPI_INSTANCE_H
#define __ICM45686_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Icm45686SpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Icm45686SpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Icm45686SpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Icm45686SpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Icm45686SpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Icm45686SpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Icm45686SpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Icm45686SpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Icm45686SpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Icm45686SpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Icm45686SpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Icm45686SpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm45686SpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm45686SpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Icm45686SpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm45686SpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm45686SpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Icm45686SpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __ICM45686_SPI_INSTANCE_H */
