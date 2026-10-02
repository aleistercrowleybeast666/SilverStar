#include "bmp280_instance.h"
#include "bmp280_adapter.h"
#include "project_resources.h"

static Bmp280Adapter s_contexts[PROJECT_BMP280_I2C_INSTANCE_COUNT];
_Static_assert(PROJECT_BMP280_I2C_INSTANCE_COUNT <= 4U, "Bmp280 instance bound exceeded");

SystemDeviceResult Bmp280I2cBarometerInstance_Init(uint8_t instance)
{
    ProjectBmp280I2cResources resources;
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (ProjectBmp280I2cResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_InitI2c(&s_contexts[instance],
        resources.i2c, 0x76U);
}

SystemDeviceResult Bmp280I2cBarometerInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Bmp280I2cBarometerInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Bmp280I2cBarometerInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Bmp280I2cBarometerInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_InfoGet(&s_contexts[instance], info);
}

SystemDeviceResult Bmp280I2cBarometerInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_CapabilitiesGet(&s_contexts[instance], mask);
}

SystemDeviceResult Bmp280I2cBarometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Bmp280I2cBarometerInstance_LatestSampleGet(uint8_t instance, SystemBarometerSample *sample)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_LatestSampleGet(&s_contexts[instance], sample);
}

SystemDeviceResult Bmp280I2cBarometerInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_SelfTestRun(&s_contexts[instance], result);
}

SystemDeviceResult Bmp280I2cBarometerInstance_ConfigApply(uint8_t instance, const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Bmp280I2cBarometerInstance_ConfigVerify(uint8_t instance, const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_ConfigVerify(&s_contexts[instance], config, report);
}

SystemDeviceResult Bmp280I2cBarometerInstance_EffectiveConfigGet(uint8_t instance, SystemBarometerConfig *config)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_EffectiveConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult Bmp280I2cBarometerInstance_NoiseCharacteristicsGet(uint8_t instance, SystemBarometerNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_BMP280_I2C_INSTANCE_COUNT) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Bmp280Adapter_NoiseCharacteristicsGet(&s_contexts[instance], noise);
}

