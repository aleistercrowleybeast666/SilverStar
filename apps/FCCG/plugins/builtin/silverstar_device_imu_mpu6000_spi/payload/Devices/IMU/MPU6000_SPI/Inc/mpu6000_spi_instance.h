#ifndef __MPU6000_SPI_INSTANCE_H
#define __MPU6000_SPI_INSTANCE_H

#include "system_imu_if.h"

const char * Mpu6000SpiImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Mpu6000SpiImuInstance_Init(uint8_t instance);
SystemDeviceResult Mpu6000SpiImuInstance_Start(uint8_t instance);
SystemDeviceResult Mpu6000SpiImuInstance_Stop(uint8_t instance);
SystemDeviceResult Mpu6000SpiImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Mpu6000SpiImuInstance_Process(uint8_t instance);
SystemDeviceResult Mpu6000SpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Mpu6000SpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Mpu6000SpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Mpu6000SpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Mpu6000SpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Mpu6000SpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Mpu6000SpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Mpu6000SpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Mpu6000SpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mpu6000SpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mpu6000SpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Mpu6000SpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __MPU6000_SPI_INSTANCE_H */
