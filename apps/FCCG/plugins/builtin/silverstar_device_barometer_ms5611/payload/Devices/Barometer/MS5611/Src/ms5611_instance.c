#include "ms5611_instance.h"

#include "ms5611_adapter.h"
#include "project_resources.h"

#define MS5611_BINDINGS(prefix, count, contexts) \
SystemDeviceResult prefix ## _Start(uint8_t instance) \
{ return instance < count ? Ms5611Adapter_Start(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Stop(uint8_t instance) \
{ return instance < count ? Ms5611Adapter_Stop(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _Process(uint8_t instance) \
{ return instance < count ? Ms5611Adapter_Process(&contexts[instance]) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _InfoGet(uint8_t instance, SystemDeviceInfo *info) \
{ return instance < count ? Ms5611Adapter_InfoGet(&contexts[instance], info) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _CapabilitiesGet(uint8_t instance, uint32_t *mask) \
{ return instance < count ? Ms5611Adapter_CapabilitiesGet(&contexts[instance], mask) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _HealthGet(uint8_t instance, SystemDeviceHealth *health) \
{ return instance < count ? Ms5611Adapter_HealthGet(&contexts[instance], health) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _LatestSampleGet(uint8_t instance, \
    SystemBarometerSample *sample) \
{ return instance < count ? Ms5611Adapter_LatestSampleGet(&contexts[instance], sample) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _SelfTestRun(uint8_t instance, \
    SystemDeviceSelfTestResult *result) \
{ return instance < count ? Ms5611Adapter_SelfTestRun(&contexts[instance], result) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigApply(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Ms5611Adapter_ConfigApply(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _ConfigVerify(uint8_t instance, \
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report) \
{ return instance < count ? Ms5611Adapter_ConfigVerify(&contexts[instance], config, report) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _EffectiveConfigGet(uint8_t instance, \
    SystemBarometerConfig *config) \
{ return instance < count ? Ms5611Adapter_EffectiveConfigGet(&contexts[instance], config) : \
    SYSTEM_DEVICE_NOT_PRESENT; } \
SystemDeviceResult prefix ## _NoiseCharacteristicsGet(uint8_t instance, \
    SystemBarometerNoiseCharacteristics *noise) \
{ return instance < count ? Ms5611Adapter_NoiseCharacteristicsGet(&contexts[instance], noise) : \
    SYSTEM_DEVICE_NOT_PRESENT; }

#if defined(PROJECT_MS5611_I2C_INSTANCE_COUNT)
static Ms5611Adapter s_i2c_contexts[PROJECT_MS5611_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_MS5611_I2C_INSTANCE_COUNT <= 4U,
    "MS5611 I2C instance bound exceeded");

SystemDeviceResult Ms5611I2cBarometerInstance_Init(uint8_t instance)
{
    ProjectMs5611I2cResources resources;
    if (instance >= PROJECT_MS5611_I2C_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMs5611I2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_InitI2c(&s_i2c_contexts[instance],
        resources.i2c, 0x77U);
}

MS5611_BINDINGS(Ms5611I2cBarometerInstance,
    PROJECT_MS5611_I2C_INSTANCE_COUNT, s_i2c_contexts)
#endif

#if defined(PROJECT_MS5611_SPI_INSTANCE_COUNT)
static Ms5611Adapter s_spi_contexts[PROJECT_MS5611_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_MS5611_SPI_INSTANCE_COUNT <= 4U,
    "MS5611 SPI instance bound exceeded");

SystemDeviceResult Ms5611SpiBarometerInstance_Init(uint8_t instance)
{
    ProjectMs5611SpiResources resources;
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMs5611SpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_InitSpi(&s_spi_contexts[instance],
        resources.spi, resources.cs);
}

MS5611_BINDINGS(Ms5611SpiBarometerInstance,
    PROJECT_MS5611_SPI_INSTANCE_COUNT, s_spi_contexts)
#endif

#undef MS5611_BINDINGS

