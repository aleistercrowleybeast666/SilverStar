#include "lsm6dsv32x_spi_instance.h"
#include "lsm6dsv32x_spi_device.h"
#include "sensor_imu_adapter.h"
#include "project_resources.h"
#include <stddef.h>
#include <string.h>

static SensorImuAdapter s_contexts[PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT];
_Static_assert(PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT <= 4U, "IMU context bound exceeded");

const char * Lsm6Dsv32XSpiImuInstance_NameGet(uint8_t instance)
{
    return (instance < PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) ? "LSM6DSV32X_SPI" : "Invalid IMU";
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Init(uint8_t instance)
{
    ProjectLsm6Dsv32XSpiResources resources;
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectLsm6Dsv32XSpiResources_Get(instance, &resources) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_NOT_PRESENT; }
    SensorImuSpiResources spi = {resources.spi, resources.cs, (PlatformGpioId)PLATFORM_GPIO_COUNT, resources.drdy, (PlatformGpioId)PLATFORM_GPIO_COUNT};
    return SensorImuAdapter_InitSpi(&s_contexts[instance], Lsm6Dsv32XSpi_ProfileGet(), &spi, instance);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].owner_active = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(info, 0, sizeof(*info));
    info->device_name = "LSM6DSV32X_SPI";
    info->model_name = "LSM6DSV32X_SPI";
    info->driver_version = "1.0.0-HARDWARE_UNVERIFIED";
    info->capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_error_count = s_contexts[instance].driver.bus_errors;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(detail, 0, sizeof(*detail));
    detail->valid_frame_count = s_contexts[instance].driver.sample_count;
    detail->config_generation = s_contexts[instance].driver.config_generation;
    detail->config_generation_valid = s_contexts[instance].driver.profile_verified;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 0U);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 1U);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigCheck(&s_contexts[instance], config, report);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult Lsm6Dsv32XSpiImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_LSM6DSV32X_SPI_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
