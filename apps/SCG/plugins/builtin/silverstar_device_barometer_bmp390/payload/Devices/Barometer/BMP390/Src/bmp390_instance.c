#include "bmp390_instance.h"

#include "bmp390_adapter.h"
#include "project_resources.h"

#define BMP390_BINDINGS(prefix, count, contexts) \
SystemDeviceResult prefix ## _Start(uint8_t instance) \
{ return instance < count ? Bmp390Adapter_Start(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Stop(uint8_t instance) \
{ return instance < count ? Bmp390Adapter_Stop(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Process(uint8_t instance) \
{ return instance < count ? Bmp390Adapter_Process(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info) \
{ return instance < count ? Bmp390Adapter_InfoGet(&contexts[instance], info) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask) \
{ return instance < count ? Bmp390Adapter_CapabilitiesGet(&contexts[instance], mask) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health) \
{ return instance < count ? Bmp390Adapter_HealthGet(&contexts[instance], health) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemBarometerSample *sample) \
{ return instance < count ? Bmp390Adapter_LatestSampleGet(&contexts[instance], sample) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result) \
{ return instance < count ? Bmp390Adapter_SelfTestRun(&contexts[instance], result) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Bmp390Adapter_ConfigApply(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Bmp390Adapter_ConfigVerify(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemBarometerConfig *config) \
{ return instance < count ? Bmp390Adapter_EffectiveConfigGet(&contexts[instance], config) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _NoiseCharacteristicsGet(uint8_t instance, \
    SystemBarometerNoiseCharacteristics *noise) \
{ return instance < count ? Bmp390Adapter_NoiseCharacteristicsGet(&contexts[instance], noise) : \
    SYSTEM_DEVICE_NOT_PRESENT; }

#if defined(PROJECT_BMP390_I2C_INSTANCE_COUNT)
static Bmp390Adapter s_i2c_contexts[PROJECT_BMP390_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_BMP390_I2C_INSTANCE_COUNT <= 4U,
    "BMP390 I2C instance bound exceeded");

SystemDeviceResult Bmp390I2cBarometerInstance_Init(uint8_t instance)
{
    ProjectBmp390I2cResources resources;
    if (instance >= PROJECT_BMP390_I2C_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectBmp390I2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp390Adapter_InitI2c(&s_i2c_contexts[instance],
        resources.i2c, 0x76U);
}

BMP390_BINDINGS(Bmp390I2cBarometerInstance,
    PROJECT_BMP390_I2C_INSTANCE_COUNT, s_i2c_contexts)
#endif

#if defined(PROJECT_BMP390_SPI_INSTANCE_COUNT)
static Bmp390Adapter s_spi_contexts[PROJECT_BMP390_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_BMP390_SPI_INSTANCE_COUNT <= 4U,
    "BMP390 SPI instance bound exceeded");

SystemDeviceResult Bmp390SpiBarometerInstance_Init(uint8_t instance)
{
    ProjectBmp390SpiResources resources;
    if (instance >= PROJECT_BMP390_SPI_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectBmp390SpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp390Adapter_InitSpi(&s_spi_contexts[instance],
        resources.spi, resources.cs);
}

BMP390_BINDINGS(Bmp390SpiBarometerInstance,
    PROJECT_BMP390_SPI_INSTANCE_COUNT, s_spi_contexts)
#endif

#undef BMP390_BINDINGS
