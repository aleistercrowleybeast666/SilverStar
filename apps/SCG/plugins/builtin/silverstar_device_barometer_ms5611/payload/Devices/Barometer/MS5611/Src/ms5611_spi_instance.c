#include "ms5611_instance.h"
#include "ms5611_adapter.h"
#include "project_resources.h"

static Ms5611Adapter s_contexts[PROJECT_MS5611_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_MS5611_SPI_INSTANCE_COUNT <= 4U, "Ms5611 instance bound exceeded");

SystemDeviceResult Ms5611SpiBarometerInstance_Init(uint8_t instance)
{
    ProjectMs5611SpiResources resources;
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMs5611SpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_InitSpi(&s_contexts[instance],
        resources.spi, resources.cs);
}

SystemDeviceResult Ms5611SpiBarometerInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Ms5611SpiBarometerInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Ms5611SpiBarometerInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Ms5611SpiBarometerInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_InfoGet(&s_contexts[instance], info);
}

SystemDeviceResult Ms5611SpiBarometerInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_CapabilitiesGet(&s_contexts[instance], mask);
}

SystemDeviceResult Ms5611SpiBarometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Ms5611SpiBarometerInstance_LatestSampleGet(uint8_t instance, SystemBarometerSample *sample)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_LatestSampleGet(&s_contexts[instance], sample);
}

SystemDeviceResult Ms5611SpiBarometerInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_SelfTestRun(&s_contexts[instance], result);
}

SystemDeviceResult Ms5611SpiBarometerInstance_ConfigApply(uint8_t instance, const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Ms5611SpiBarometerInstance_ConfigVerify(uint8_t instance, const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_ConfigVerify(&s_contexts[instance], config, report);
}

SystemDeviceResult Ms5611SpiBarometerInstance_EffectiveConfigGet(uint8_t instance, SystemBarometerConfig *config)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_EffectiveConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult Ms5611SpiBarometerInstance_NoiseCharacteristicsGet(uint8_t instance, SystemBarometerNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_MS5611_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Ms5611Adapter_NoiseCharacteristicsGet(&s_contexts[instance], noise);
}

