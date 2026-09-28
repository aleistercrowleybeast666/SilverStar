#ifndef __JY901B_INSTANCE_H
#define __JY901B_INSTANCE_H

#include <stdint.h>

#include "system_barometer_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"

const char *Jy901bImuInstance_NameGet(uint8_t instance);
SystemDeviceResult Jy901bImuInstance_Init(uint8_t instance);
SystemDeviceResult Jy901bImuInstance_Start(uint8_t instance);
SystemDeviceResult Jy901bImuInstance_Stop(uint8_t instance);
SystemDeviceResult Jy901bImuInstance_RuntimeOwnerActivate(uint8_t instance);
SystemDeviceResult Jy901bImuInstance_Process(uint8_t instance);
SystemDeviceResult Jy901bImuInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Jy901bImuInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Jy901bImuInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Jy901bImuInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Jy901bImuInstance_IoDetailGet(
    uint8_t instance, SystemImuIoDetail *detail);
SystemDeviceResult Jy901bImuInstance_LatestSampleGet(
    uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Jy901bImuInstance_NextSampleGet(
    uint8_t instance, SystemImuSample *sample);
SystemDeviceResult Jy901bImuInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Jy901bImuInstance_ConfigApply(
    uint8_t instance, const SystemImuConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bImuInstance_ConfigVerify(
    uint8_t instance, const SystemImuConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bImuInstance_EffectiveConfigGet(
    uint8_t instance, SystemImuConfig *config);
SystemDeviceResult Jy901bImuInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemImuNoiseCharacteristics *noise);

const char *Jy901bBarometerInstance_NameGet(uint8_t instance);
SystemDeviceResult Jy901bBarometerInstance_Init(uint8_t instance);
SystemDeviceResult Jy901bBarometerInstance_Start(uint8_t instance);
SystemDeviceResult Jy901bBarometerInstance_Stop(uint8_t instance);
void Jy901bBarometerInstance_Process(uint8_t instance);
SystemDeviceResult Jy901bBarometerInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Jy901bBarometerInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Jy901bBarometerInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Jy901bBarometerInstance_LatestSampleGet(
    uint8_t instance, SystemBarometerSample *sample);
SystemDeviceResult Jy901bBarometerInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Jy901bBarometerInstance_ConfigApply(
    uint8_t instance, const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bBarometerInstance_ConfigVerify(
    uint8_t instance, const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bBarometerInstance_EffectiveConfigGet(
    uint8_t instance, SystemBarometerConfig *config);
SystemDeviceResult Jy901bBarometerInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemBarometerNoiseCharacteristics *noise);

const char *Jy901bMagnetometerInstance_NameGet(uint8_t instance);
SystemDeviceResult Jy901bMagnetometerInstance_Init(uint8_t instance);
SystemDeviceResult Jy901bMagnetometerInstance_Start(uint8_t instance);
SystemDeviceResult Jy901bMagnetometerInstance_Stop(uint8_t instance);
void Jy901bMagnetometerInstance_Process(uint8_t instance);
SystemDeviceResult Jy901bMagnetometerInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Jy901bMagnetometerInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Jy901bMagnetometerInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Jy901bMagnetometerInstance_LatestSampleGet(
    uint8_t instance, SystemMagnetometerSample *sample);
SystemDeviceResult Jy901bMagnetometerInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Jy901bMagnetometerInstance_ConfigApply(
    uint8_t instance, const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bMagnetometerInstance_ConfigVerify(
    uint8_t instance, const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bMagnetometerInstance_EffectiveConfigGet(
    uint8_t instance, SystemMagnetometerConfig *config);

const char *Jy901bQuaternionInstance_NameGet(uint8_t instance);
SystemDeviceResult Jy901bQuaternionInstance_Init(uint8_t instance);
SystemDeviceResult Jy901bQuaternionInstance_Start(uint8_t instance);
SystemDeviceResult Jy901bQuaternionInstance_Stop(uint8_t instance);
void Jy901bQuaternionInstance_Process(uint8_t instance);
SystemDeviceResult Jy901bQuaternionInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Jy901bQuaternionInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask);
SystemDeviceResult Jy901bQuaternionInstance_HealthGet(
    uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Jy901bQuaternionInstance_LatestSampleGet(
    uint8_t instance, SystemHardwareQuaternionSample *sample);
SystemDeviceResult Jy901bQuaternionInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Jy901bQuaternionInstance_ConfigApply(
    uint8_t instance, const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bQuaternionInstance_ConfigVerify(
    uint8_t instance, const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report);
SystemDeviceResult Jy901bQuaternionInstance_EffectiveConfigGet(
    uint8_t instance, SystemHardwareQuaternionConfig *config);

#endif /* __JY901B_INSTANCE_H */
