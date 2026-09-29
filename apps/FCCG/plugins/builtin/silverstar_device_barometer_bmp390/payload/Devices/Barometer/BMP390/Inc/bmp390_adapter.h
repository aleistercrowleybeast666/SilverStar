#ifndef __BMP390_ADAPTER_H
#define __BMP390_ADAPTER_H

#include "bmp390_core.h"
#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_spi.h"

typedef enum
{
    Bmp390InterfaceI2c = 0,
    Bmp390InterfaceSpi
} Bmp390Interface;

typedef struct
{
    Bmp390Context core;
    SystemDeviceHealth health;
    Bmp390Interface interface;
    PlatformI2cId i2c;
    PlatformSpiId spi;
    PlatformGpioId cs;
    uint16_t address_7bit;
} Bmp390Adapter;

SystemDeviceResult Bmp390Adapter_InitI2c(Bmp390Adapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit);
SystemDeviceResult Bmp390Adapter_InitSpi(Bmp390Adapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs);
SystemDeviceResult Bmp390Adapter_Start(Bmp390Adapter *adapter);
SystemDeviceResult Bmp390Adapter_Stop(Bmp390Adapter *adapter);
SystemDeviceResult Bmp390Adapter_Process(Bmp390Adapter *adapter);
SystemDeviceResult Bmp390Adapter_InfoGet(const Bmp390Adapter *adapter,
    SystemDeviceInfo *info);
SystemDeviceResult Bmp390Adapter_CapabilitiesGet(
    const Bmp390Adapter *adapter, uint32_t *mask);
SystemDeviceResult Bmp390Adapter_HealthGet(const Bmp390Adapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult Bmp390Adapter_LatestSampleGet(
    const Bmp390Adapter *adapter, SystemBarometerSample *sample);
SystemDeviceResult Bmp390Adapter_SelfTestRun(
    const Bmp390Adapter *adapter, SystemDeviceSelfTestResult *result);
SystemDeviceResult Bmp390Adapter_ConfigApply(Bmp390Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmp390Adapter_ConfigVerify(const Bmp390Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmp390Adapter_EffectiveConfigGet(
    const Bmp390Adapter *adapter, SystemBarometerConfig *config);
SystemDeviceResult Bmp390Adapter_NoiseCharacteristicsGet(
    const Bmp390Adapter *adapter,
    SystemBarometerNoiseCharacteristics *noise);

#endif /* __BMP390_ADAPTER_H */
