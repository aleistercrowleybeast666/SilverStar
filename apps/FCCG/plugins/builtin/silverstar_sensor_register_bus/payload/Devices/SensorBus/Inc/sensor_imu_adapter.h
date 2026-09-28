#ifndef __SENSOR_IMU_ADAPTER_H
#define __SENSOR_IMU_ADAPTER_H

#include "sensor_imu.h"
#include "system_imu_if.h"
#include "platform_i2c.h"
#include "platform_spi.h"
#include "platform_gpio.h"

typedef struct
{
    PlatformSpiId spi;
    PlatformGpioId cs;
    PlatformGpioId auxiliary_cs;
    PlatformGpioId drdy;
    PlatformGpioId auxiliary_drdy;
} SensorImuSpiResources;

typedef struct
{
    SensorImu driver;
    PlatformI2cId bus_id;
    PlatformI2cId auxiliary_bus_id;
    uint16_t address_7bit;
    SensorImuSpiResources spi_resources;
    uint8_t drdy_seen;
    uint8_t auxiliary_drdy_seen;
    uint32_t consumed_sequence;
    uint8_t started;
    uint8_t owner_active;
    uint8_t processing;
    SystemImuSample latest;
    SystemDeviceHealth health;
} SensorImuAdapter;

SystemDeviceResult SensorImuAdapter_Init(SensorImuAdapter *adapter,
    const SensorImuProfile *profile, PlatformI2cId bus_id,
    uint16_t address_7bit, uint32_t source_id);
SystemDeviceResult SensorImuAdapter_InitI2c(SensorImuAdapter *adapter,
    const SensorImuProfile *profile, PlatformI2cId bus_id,
    PlatformI2cId auxiliary_bus_id, uint16_t address_7bit, uint32_t source_id);
SystemDeviceResult SensorImuAdapter_Start(SensorImuAdapter *adapter);
SystemDeviceResult SensorImuAdapter_InitSpi(SensorImuAdapter *adapter,
    const SensorImuProfile *profile, const SensorImuSpiResources *resources,
    uint32_t source_id);
SystemDeviceResult SensorImuAdapter_Stop(SensorImuAdapter *adapter);
SystemDeviceResult SensorImuAdapter_Process(SensorImuAdapter *adapter);
SystemDeviceResult SensorImuAdapter_HealthGet(SensorImuAdapter *adapter,
    SystemDeviceHealth *health);
SystemDeviceResult SensorImuAdapter_SampleGet(SensorImuAdapter *adapter,
    SystemImuSample *sample, uint8_t consume);
SystemDeviceResult SensorImuAdapter_ConfigGet(SensorImuAdapter *adapter,
    SystemImuConfig *config);
SystemDeviceResult SensorImuAdapter_ConfigCheck(SensorImuAdapter *adapter,
    const SystemImuConfig *config, SystemDeviceConfigReport *report);
SystemDeviceResult SensorImuAdapter_ConfigApply(SensorImuAdapter *adapter,
    const SystemImuConfig *config, SystemDeviceConfigReport *report);

#endif /* __SENSOR_IMU_ADAPTER_H */
