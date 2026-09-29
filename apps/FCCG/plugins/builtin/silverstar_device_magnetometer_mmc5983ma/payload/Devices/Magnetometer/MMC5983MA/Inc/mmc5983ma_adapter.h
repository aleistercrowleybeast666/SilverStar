#ifndef __MMC5983MA_ADAPTER_H
#define __MMC5983MA_ADAPTER_H

#include "mmc5983ma_core.h"
#include "platform_gpio.h"
#include "platform_i2c.h"
#include "platform_spi.h"

typedef enum
{
    Mmc5983maInterfaceI2c = 0,
    Mmc5983maInterfaceSpi
} Mmc5983maInterface;

typedef struct
{
    Mmc5983maContext core;
    SystemDeviceHealth health;
    Mmc5983maInterface interface;
    PlatformI2cId i2c;
    PlatformSpiId spi;
    PlatformGpioId cs;
    uint16_t address_7bit;
} Mmc5983maAdapter;

SystemDeviceResult Mmc5983maAdapter_InitI2c(Mmc5983maAdapter *adapter,
    PlatformI2cId i2c, uint16_t address_7bit);
SystemDeviceResult Mmc5983maAdapter_InitSpi(Mmc5983maAdapter *adapter,
    PlatformSpiId spi, PlatformGpioId cs);
SystemDeviceResult Mmc5983maAdapter_Start(Mmc5983maAdapter *adapter);
SystemDeviceResult Mmc5983maAdapter_Stop(Mmc5983maAdapter *adapter);
SystemDeviceResult Mmc5983maAdapter_Process(Mmc5983maAdapter *adapter);
SystemDeviceResult Mmc5983maAdapter_InfoGet(const Mmc5983maAdapter *adapter,
    SystemDeviceInfo *info);
SystemDeviceResult Mmc5983maAdapter_CapabilitiesGet(
    const Mmc5983maAdapter *adapter, uint32_t *mask);
SystemDeviceResult Mmc5983maAdapter_HealthGet(const Mmc5983maAdapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult Mmc5983maAdapter_LatestSampleGet(
    const Mmc5983maAdapter *adapter, SystemMagnetometerSample *sample);
SystemDeviceResult Mmc5983maAdapter_SelfTestRun(
    const Mmc5983maAdapter *adapter, SystemDeviceSelfTestResult *result);
SystemDeviceResult Mmc5983maAdapter_ConfigApply(Mmc5983maAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mmc5983maAdapter_ConfigVerify(const Mmc5983maAdapter *adapter,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult Mmc5983maAdapter_EffectiveConfigGet(
    const Mmc5983maAdapter *adapter, SystemMagnetometerConfig *config);
#endif /* __MMC5983MA_ADAPTER_H */
