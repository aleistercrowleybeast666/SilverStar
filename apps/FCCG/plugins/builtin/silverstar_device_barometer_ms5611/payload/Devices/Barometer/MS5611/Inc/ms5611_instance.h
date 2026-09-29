#ifndef __MS5611_INSTANCE_H
#define __MS5611_INSTANCE_H

#include "system_barometer_if.h"

#define MS5611_INSTANCE_DECLARATIONS(prefix) \
SystemDeviceResult prefix ## _Init(uint8_t instance); \
SystemDeviceResult prefix ## _Start(uint8_t instance); \
SystemDeviceResult prefix ## _Stop(uint8_t instance); \
SystemDeviceResult prefix ## _Process(uint8_t instance); \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info); \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask); \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health); \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemBarometerSample *sample); \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result); \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report); \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report); \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemBarometerConfig *config); \
SystemDeviceResult prefix ## _NoiseCharacteristicsGet(uint8_t instance, \
    SystemBarometerNoiseCharacteristics *noise);

MS5611_INSTANCE_DECLARATIONS(Ms5611I2cBarometerInstance)
MS5611_INSTANCE_DECLARATIONS(Ms5611SpiBarometerInstance)

#undef MS5611_INSTANCE_DECLARATIONS

#endif /* __MS5611_INSTANCE_H */

