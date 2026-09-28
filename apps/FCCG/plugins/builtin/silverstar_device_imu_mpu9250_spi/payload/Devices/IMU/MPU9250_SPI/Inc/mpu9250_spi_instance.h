#ifndef __MPU9250_SPI_INSTANCE_H
#define __MPU9250_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Mpu9250SpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Mpu9250SpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Mpu9250SpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Mpu9250SpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Mpu9250SpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Mpu9250SpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Mpu9250SpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Mpu9250SpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Mpu9250SpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Mpu9250SpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Mpu9250SpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Mpu9250SpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Mpu9250SpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Mpu9250SpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Mpu9250SpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mpu9250SpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mpu9250SpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Mpu9250SpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __MPU9250_SPI_INSTANCE_H */
