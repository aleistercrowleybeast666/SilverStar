#ifndef __LIS3MDL_ADAPTER_H
#define __LIS3MDL_ADAPTER_H

#include "lis3mdl_core.h"
#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_spi.h"

typedef enum
{
    Lis3mdlInterfaceI2c = 0,
    Lis3mdlInterfaceSpi
} Lis3mdlInterface;

typedef struct
{
    Lis3mdlContext core;
    SystemDeviceHealth health;
    Lis3mdlInterface interface;
    PlatformI2cId i2c;
    PlatformSpiId spi;
    PlatformGpioId cs;
    uint16_t address_7bit;
} Lis3mdlAdapter;

SystemDeviceResult Lis3mdlAdapter_InitI2c(Lis3mdlAdapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit);
SystemDeviceResult Lis3mdlAdapter_InitSpi(Lis3mdlAdapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs);
SystemDeviceResult Lis3mdlAdapter_Start(Lis3mdlAdapter *adapter);
SystemDeviceResult Lis3mdlAdapter_Stop(Lis3mdlAdapter *adapter);
SystemDeviceResult Lis3mdlAdapter_Process(Lis3mdlAdapter *adapter);
SystemDeviceResult Lis3mdlAdapter_InfoGet(const Lis3mdlAdapter *adapter,
    SystemDeviceInfo *info);
SystemDeviceResult Lis3mdlAdapter_CapabilitiesGet(
    const Lis3mdlAdapter *adapter, uint32_t *mask);
SystemDeviceResult Lis3mdlAdapter_HealthGet(const Lis3mdlAdapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult Lis3mdlAdapter_LatestSampleGet(
    const Lis3mdlAdapter *adapter, SystemMagnetometerSample *sample);
SystemDeviceResult Lis3mdlAdapter_SelfTestRun(
    const Lis3mdlAdapter *adapter, SystemDeviceSelfTestResult *result);
SystemDeviceResult Lis3mdlAdapter_ConfigApply(Lis3mdlAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lis3mdlAdapter_ConfigVerify(const Lis3mdlAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Lis3mdlAdapter_EffectiveConfigGet(
    const Lis3mdlAdapter *adapter, SystemMagnetometerConfig *config);
#endif /* __LIS3MDL_ADAPTER_H */
