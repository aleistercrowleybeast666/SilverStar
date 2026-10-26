#include "mmc5983ma_instance.h"
#include "mmc5983ma_adapter.h"
#include "project_resources.h"

static Mmc5983maAdapter s_contexts[PROJECT_MMC5983MA_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_MMC5983MA_I2C_INSTANCE_COUNT <= 4U, "Mmc5983ma instance bound exceeded");

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_Init(uint8_t instance)
{
    ProjectMmc5983maI2cResources resources;
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectMmc5983maI2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_InitI2c(&s_contexts[instance],
        resources.i2c, 0x30U);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_InfoGet(&s_contexts[instance], info);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_CapabilitiesGet(&s_contexts[instance], mask);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_LatestSampleGet(uint8_t instance, SystemMagnetometerSample *sample)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_LatestSampleGet(&s_contexts[instance], sample);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_SelfTestRun(&s_contexts[instance], result);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_ConfigApply(uint8_t instance, const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_ConfigVerify(uint8_t instance, const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_ConfigVerify(&s_contexts[instance], config, report);
}

SystemDeviceResult Mmc5983maI2cMagnetometerInstance_EffectiveConfigGet(uint8_t instance, SystemMagnetometerConfig *config)
{
    if (instance >= PROJECT_MMC5983MA_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Mmc5983maAdapter_EffectiveConfigGet(&s_contexts[instance], config);
}

