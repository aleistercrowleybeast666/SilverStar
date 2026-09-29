#ifndef __LIS3MDL_INSTANCE_H
#define __LIS3MDL_INSTANCE_H

#include "system_magnetometer_if.h"

#define LIS3MDL_INSTANCE_DECLARATIONS(prefix) \
SystemDeviceResult prefix ## _Init(uint8_t instance); \
SystemDeviceResult prefix ## _Start(uint8_t instance); \
SystemDeviceResult prefix ## _Stop(uint8_t instance); \
SystemDeviceResult prefix ## _Process(uint8_t instance); \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info); \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask); \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health); \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemMagnetometerSample *sample); \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result); \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report); \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report); \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemMagnetometerConfig *config);

LIS3MDL_INSTANCE_DECLARATIONS(Lis3mdlI2cMagnetometerInstance)
LIS3MDL_INSTANCE_DECLARATIONS(Lis3mdlSpiMagnetometerInstance)

#undef LIS3MDL_INSTANCE_DECLARATIONS

#endif /* __LIS3MDL_INSTANCE_H */
