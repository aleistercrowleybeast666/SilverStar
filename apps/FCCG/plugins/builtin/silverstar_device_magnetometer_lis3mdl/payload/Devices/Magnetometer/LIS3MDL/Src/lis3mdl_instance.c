#include "lis3mdl_instance.h"

#include "lis3mdl_adapter.h"
#include "project_resources.h"

#define LIS3MDL_BINDINGS(prefix, count, contexts) \
SystemDeviceResult prefix ## _Start(uint8_t instance) \
{ return instance < count ? Lis3mdlAdapter_Start(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Stop(uint8_t instance) \
{ return instance < count ? Lis3mdlAdapter_Stop(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Process(uint8_t instance) \
{ return instance < count ? Lis3mdlAdapter_Process(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info) \
{ return instance < count ? Lis3mdlAdapter_InfoGet(&contexts[instance], info) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask) \
{ return instance < count ? Lis3mdlAdapter_CapabilitiesGet(&contexts[instance], mask) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health) \
{ return instance < count ? Lis3mdlAdapter_HealthGet(&contexts[instance], health) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemMagnetometerSample *sample) \
{ return instance < count ? Lis3mdlAdapter_LatestSampleGet(&contexts[instance], sample) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result) \
{ return instance < count ? Lis3mdlAdapter_SelfTestRun(&contexts[instance], result) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Lis3mdlAdapter_ConfigApply(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Lis3mdlAdapter_ConfigVerify(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemMagnetometerConfig *config) \
{ return instance < count ? Lis3mdlAdapter_EffectiveConfigGet(&contexts[instance], config) : \
    SYSTEM_DEVICE_NOT_PRESENT; }

#if defined(PROJECT_LIS3MDL_I2C_INSTANCE_COUNT)
static Lis3mdlAdapter s_i2c_contexts[PROJECT_LIS3MDL_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_LIS3MDL_I2C_INSTANCE_COUNT <= 4U,
    "LIS3MDL I2C instance bound exceeded");

SystemDeviceResult Lis3mdlI2cMagnetometerInstance_Init(uint8_t instance)
{
    ProjectLis3mdlI2cResources resources;
    if (instance >= PROJECT_LIS3MDL_I2C_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectLis3mdlI2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Lis3mdlAdapter_InitI2c(&s_i2c_contexts[instance],
        resources.i2c, 0x1CU);
}

LIS3MDL_BINDINGS(Lis3mdlI2cMagnetometerInstance,
    PROJECT_LIS3MDL_I2C_INSTANCE_COUNT, s_i2c_contexts)
#endif

#if defined(PROJECT_LIS3MDL_SPI_INSTANCE_COUNT)
static Lis3mdlAdapter s_spi_contexts[PROJECT_LIS3MDL_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_LIS3MDL_SPI_INSTANCE_COUNT <= 4U,
    "LIS3MDL SPI instance bound exceeded");

SystemDeviceResult Lis3mdlSpiMagnetometerInstance_Init(uint8_t instance)
{
    ProjectLis3mdlSpiResources resources;
    if (instance >= PROJECT_LIS3MDL_SPI_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectLis3mdlSpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Lis3mdlAdapter_InitSpi(&s_spi_contexts[instance],
        resources.spi, resources.cs);
}

LIS3MDL_BINDINGS(Lis3mdlSpiMagnetometerInstance,
    PROJECT_LIS3MDL_SPI_INSTANCE_COUNT, s_spi_contexts)
#endif

#undef LIS3MDL_BINDINGS
