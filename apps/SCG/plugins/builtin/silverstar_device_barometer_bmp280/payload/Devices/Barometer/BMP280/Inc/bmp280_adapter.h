#ifndef __BMP280_ADAPTER_H
#define __BMP280_ADAPTER_H

#include "bmp280_core.h"
#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_spi.h"

typedef enum
{
    Bmp280InterfaceI2c = 0,
    Bmp280InterfaceSpi
} Bmp280Interface;

typedef struct
{
    Bmp280Context core;
    SystemDeviceHealth health;
    Bmp280Interface interface;
    PlatformI2cId i2c;
    PlatformSpiId spi;
    PlatformGpioId cs;
    uint16_t address_7bit;
} Bmp280Adapter;

SystemDeviceResult Bmp280Adapter_InitI2c(Bmp280Adapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit);
SystemDeviceResult Bmp280Adapter_InitSpi(Bmp280Adapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs);
SystemDeviceResult Bmp280Adapter_Start(Bmp280Adapter *adapter);
SystemDeviceResult Bmp280Adapter_Stop(Bmp280Adapter *adapter);
SystemDeviceResult Bmp280Adapter_Process(Bmp280Adapter *adapter);
SystemDeviceResult Bmp280Adapter_InfoGet(const Bmp280Adapter *adapter,
    SystemDeviceInfo *info);
SystemDeviceResult Bmp280Adapter_CapabilitiesGet(
    const Bmp280Adapter *adapter, uint32_t *mask);
SystemDeviceResult Bmp280Adapter_HealthGet(const Bmp280Adapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult Bmp280Adapter_LatestSampleGet(
    const Bmp280Adapter *adapter, SystemBarometerSample *sample);
SystemDeviceResult Bmp280Adapter_SelfTestRun(
    const Bmp280Adapter *adapter, SystemDeviceSelfTestResult *result);
SystemDeviceResult Bmp280Adapter_ConfigApply(Bmp280Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmp280Adapter_ConfigVerify(const Bmp280Adapter *adapter,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Bmp280Adapter_EffectiveConfigGet(
    const Bmp280Adapter *adapter, SystemBarometerConfig *config);
SystemDeviceResult Bmp280Adapter_NoiseCharacteristicsGet(
    const Bmp280Adapter *adapter,
    SystemBarometerNoiseCharacteristics *noise);

#endif /* __BMP280_ADAPTER_H */
