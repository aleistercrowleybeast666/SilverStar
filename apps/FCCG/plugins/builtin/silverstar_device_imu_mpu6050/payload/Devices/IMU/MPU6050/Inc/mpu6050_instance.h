#ifndef __MPU6050_INSTANCE_H
#define __MPU6050_INSTANCE_H

#include "system_imu_if.h"

const char * Mpu6050ImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Mpu6050ImuInstance_Init(uint8_t instance);
SystemDeviceResult Mpu6050ImuInstance_Start(uint8_t instance);
SystemDeviceResult Mpu6050ImuInstance_Stop(uint8_t instance);
SystemDeviceResult Mpu6050ImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Mpu6050ImuInstance_Process(uint8_t instance);
SystemDeviceResult Mpu6050ImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Mpu6050ImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Mpu6050ImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Mpu6050ImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Mpu6050ImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Mpu6050ImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Mpu6050ImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Mpu6050ImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Mpu6050ImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mpu6050ImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mpu6050ImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Mpu6050ImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise);

#endif /* __MPU6050_INSTANCE_H */
