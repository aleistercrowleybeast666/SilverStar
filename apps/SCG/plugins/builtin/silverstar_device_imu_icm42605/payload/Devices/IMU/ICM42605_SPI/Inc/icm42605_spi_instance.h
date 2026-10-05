#ifndef __ICM42605_SPI_INSTANCE_H
#define __ICM42605_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Icm42605SpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Icm42605SpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Icm42605SpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Icm42605SpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Icm42605SpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Icm42605SpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Icm42605SpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Icm42605SpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Icm42605SpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Icm42605SpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Icm42605SpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Icm42605SpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42605SpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42605SpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Icm42605SpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42605SpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42605SpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Icm42605SpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __ICM42605_SPI_INSTANCE_H */
