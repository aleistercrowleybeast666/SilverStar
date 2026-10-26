#include "mmc5983ma_instance.h"
#include "mmc5983ma_adapter.h"
#include "project_resources.h"

static Mmc5983maAdapter s_contexts[PROJECT_MMC5983MA_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_MMC5983MA_SPI_INSTANCE_COUNT <= 4U, "Mmc5983ma instance bound exceeded");

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_Init(uint8_t instance)
{
    ProjectMmc5983maSpiResources resources;
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMmc5983maSpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_InitSpi(&s_contexts[instance],
        resources.spi, resources.cs);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_InfoGet(&s_contexts[instance], info);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_CapabilitiesGet(&s_contexts[instance], mask);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_LatestSampleGet(uint8_t instance, SystemMagnetometerSample *sample)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_LatestSampleGet(&s_contexts[instance], sample);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_SelfTestRun(&s_contexts[instance], result);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_ConfigApply(uint8_t instance, const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_ConfigVerify(uint8_t instance, const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_ConfigVerify(&s_contexts[instance], config, report);
}

SystemDeviceResult Mmc5983maSpiMagnetometerInstance_EffectiveConfigGet(uint8_t instance, SystemMagnetometerConfig *config)
{
    if (instance >= PROJECT_MMC5983MA_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_EffectiveConfigGet(&s_contexts[instance], config);
}

