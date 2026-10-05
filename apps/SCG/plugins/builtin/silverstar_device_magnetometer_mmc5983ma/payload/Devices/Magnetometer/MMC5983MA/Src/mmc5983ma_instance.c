#include "mmc5983ma_instance.h"

#include "mmc5983ma_adapter.h"
#include "project_resources.h"

#define MMC5983MA_BINDINGS(prefix, count, contexts) \
SystemDeviceResult prefix ## _Start(uint8_t instance) \
{ return instance < count ? Mmc5983maAdapter_Start(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Stop(uint8_t instance) \
{ return instance < count ? Mmc5983maAdapter_Stop(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Process(uint8_t instance) \
{ return instance < count ? Mmc5983maAdapter_Process(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info) \
{ return instance < count ? Mmc5983maAdapter_InfoGet(&contexts[instance], info) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask) \
{ return instance < count ? Mmc5983maAdapter_CapabilitiesGet(&contexts[instance], mask) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health) \
{ return instance < count ? Mmc5983maAdapter_HealthGet(&contexts[instance], health) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemMagnetometerSample *sample) \
{ return instance < count ? Mmc5983maAdapter_LatestSampleGet(&contexts[instance], sample) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result) \
{ return instance < count ? Mmc5983maAdapter_SelfTestRun(&contexts[instance], result) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Mmc5983maAdapter_ConfigApply(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Mmc5983maAdapter_ConfigVerify(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemMagnetometerConfig *config) \
{ return instance < count ? Mmc5983maAdapter_EffectiveConfigGet(&contexts[instance], config) : \
    SYSTEM_DEVICE_NOT_PRESENT; }

#if defined(PROJECT_MMC5983MA_I2C_INSTANCE_COUNT)
static Mmc5983maAdapter s_i2c_contexts[PROJECT_MMC5983MA_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_MMC5983MA_I2C_INSTANCE_COUNT <= 4U,
    "MMC5983MA I2C instance bound exceeded");

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_Init(uint8_t instance)
{
    ProjectMmc5983maI2cResources resources;
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMmc5983maI2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_InitI2c(&s_i2c_contexts[instance],
        resources.i2c, 0x30U);
}

MMC5983MA_BINDINGS(Mmc5983maI2cMagnetometerInstance,
    PROJECT_MMC5983MA_I2C_INSTANCE_COUNT, s_i2c_contexts)
#endif

#if defined(PROJECT_MMC5983MA_SPI_INSTANCE_COUNT)
static Mmc5983maAdapter s_spi_contexts[PROJECT_MMC5983MA_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_MMC5983MA_SPI_INSTANCE_COUNT <= 4U,
    "MMC5983MA SPI instance bound exceeded");

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_Init(uint8_t instance)
{
    ProjectMmc5983maSpiResources resources;
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMmc5983maSpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_InitSpi(&s_spi_contexts[instance],
        resources.spi, resources.cs);
}

MMC5983MA_BINDINGS(Mmc5983maSpiMagnetometerInstance,
    PROJECT_MMC5983MA_SPI_INSTANCE_COUNT, s_spi_contexts)
#endif

#undef MMC5983MA_BINDINGS
