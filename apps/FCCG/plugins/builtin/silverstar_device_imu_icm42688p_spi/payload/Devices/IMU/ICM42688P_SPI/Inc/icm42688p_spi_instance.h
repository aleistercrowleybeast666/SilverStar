#ifndef __ICM42688P_SPI_INSTANCE_H
#define __ICM42688P_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Icm42688PSpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Icm42688PSpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Icm42688PSpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Icm42688PSpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Icm42688PSpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Icm42688PSpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Icm42688PSpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Icm42688PSpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Icm42688PSpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Icm42688PSpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Icm42688PSpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Icm42688PSpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42688PSpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Icm42688PSpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Icm42688PSpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42688PSpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Icm42688PSpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Icm42688PSpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __ICM42688P_SPI_INSTANCE_H */
