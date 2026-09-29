#include "bmp280_instance.h"

#include "bmp280_adapter.h"
#include "project_resources.h"

#define BMP280_BINDINGS(prefix, count, contexts) \
SystemDeviceResult prefix ## _Start(uint8_t instance) \
{ return instance < count ? Bmp280Adapter_Start(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Stop(uint8_t instance) \
{ return instance < count ? Bmp280Adapter_Stop(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Process(uint8_t instance) \
{ return instance < count ? Bmp280Adapter_Process(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info) \
{ return instance < count ? Bmp280Adapter_InfoGet(&contexts[instance], info) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask) \
{ return instance < count ? Bmp280Adapter_CapabilitiesGet(&contexts[instance], mask) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health) \
{ return instance < count ? Bmp280Adapter_HealthGet(&contexts[instance], health) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemBarometerSample *sample) \
{ return instance < count ? Bmp280Adapter_LatestSampleGet(&contexts[instance], sample) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result) \
{ return instance < count ? Bmp280Adapter_SelfTestRun(&contexts[instance], result) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Bmp280Adapter_ConfigApply(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Bmp280Adapter_ConfigVerify(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemBarometerConfig *config) \
{ return instance < count ? Bmp280Adapter_EffectiveConfigGet(&contexts[instance], config) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _NoiseCharacteristicsGet(uint8_t instance, \
    SystemBarometerNoiseCharacteristics *noise) \
{ return instance < count ? Bmp280Adapter_NoiseCharacteristicsGet(&contexts[instance], noise) : \
    SYSTEM_DEVICE_NOT_PRESENT; }

#if defined(PROJECT_BMP280_I2C_INSTANCE_COUNT)
static Bmp280Adapter s_i2c_contexts[PROJECT_BMP280_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_BMP280_I2C_INSTANCE_COUNT <= 4U,
    "BMP280 I2C instance bound exceeded");

SystemDeviceResult Bmp280I2cBarometerInstance_Init(uint8_t instance)
{
    ProjectBmp280I2cResources resources;
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectBmp280I2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_InitI2c(&s_i2c_contexts[instance],
        resources.i2c, 0x76U);
}

BMP280_BINDINGS(Bmp280I2cBarometerInstance,
    PROJECT_BMP280_I2C_INSTANCE_COUNT, s_i2c_contexts)
#endif

#if defined(PROJECT_BMP280_SPI_INSTANCE_COUNT)
static Bmp280Adapter s_spi_contexts[PROJECT_BMP280_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_BMP280_SPI_INSTANCE_COUNT <= 4U,
    "BMP280 SPI instance bound exceeded");

SystemDeviceResult Bmp280SpiBarometerInstance_Init(uint8_t instance)
{
    ProjectBmp280SpiResources resources;
    if (instance >= PROJECT_BMP280_SPI_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectBmp280SpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_InitSpi(&s_spi_contexts[instance],
        resources.spi, resources.cs);
}

BMP280_BINDINGS(Bmp280SpiBarometerInstance,
    PROJECT_BMP280_SPI_INSTANCE_COUNT, s_spi_contexts)
#endif

#undef BMP280_BINDINGS
