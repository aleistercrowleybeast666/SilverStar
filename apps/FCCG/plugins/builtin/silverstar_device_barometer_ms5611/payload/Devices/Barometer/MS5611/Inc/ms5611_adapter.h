#ifndef __MS5611_ADAPTER_H
#define __MS5611_ADAPTER_H

#include "ms5611_core.h"
#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_spi.h"

typedef enum
{
    Ms5611InterfaceI2c = 0,
    Ms5611InterfaceSpi
} Ms5611Interface;

typedef struct
{
    Ms5611Context core;
    SystemDeviceHealth health;
    Ms5611Interface interface;
    PlatformI2cId i2c;
    PlatformSpiId spi;
    PlatformGpioId cs;
    uint16_t address_7bit;
} Ms5611Adapter;

SystemDeviceResult Ms5611Adapter_InitI2c(Ms5611Adapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit);
SystemDeviceResult Ms5611Adapter_InitSpi(Ms5611Adapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs);
SystemDeviceResult Ms5611Adapter_Start(Ms5611Adapter *adapter);
SystemDeviceResult Ms5611Adapter_Stop(Ms5611Adapter *adapter);
SystemDeviceResult Ms5611Adapter_Process(Ms5611Adapter *adapter);
SystemDeviceResult Ms5611Adapter_InfoGet(const Ms5611Adapter *adapter,
    SystemDeviceInfo *info);
SystemDeviceResult Ms5611Adapter_CapabilitiesGet(
    const Ms5611Adapter *adapter, uint32_t *mask);
SystemDeviceResult Ms5611Adapter_HealthGet(const Ms5611Adapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult Ms5611Adapter_LatestSampleGet(
    const Ms5611Adapter *adapter, SystemBarometerSample *sample);
SystemDeviceResult Ms5611Adapter_SelfTestRun(
    const Ms5611Adapter *adapter, SystemDeviceSelfTestResult *result);
SystemDeviceResult Ms5611Adapter_ConfigApply(Ms5611Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Ms5611Adapter_ConfigVerify(const Ms5611Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Ms5611Adapter_EffectiveConfigGet(
    const Ms5611Adapter *adapter, SystemBarometerConfig *config);
SystemDeviceResult Ms5611Adapter_NoiseCharacteristicsGet(
    const Ms5611Adapter *adapter,
    SystemBarometerNoiseCharacteristics *noise);

#endif /* __MS5611_ADAPTER_H */
