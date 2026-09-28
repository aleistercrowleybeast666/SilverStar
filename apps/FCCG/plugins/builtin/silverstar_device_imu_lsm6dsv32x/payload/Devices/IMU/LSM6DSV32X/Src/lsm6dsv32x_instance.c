#include "lsm6dsv32x_instance.h"
#include "lsm6dsv32x_device.h"
#include "sensor_imu_adapter.h"
#include "project_resources.h"
#include <stddef.h>
#include <string.h>

static SensorImuAdapter s_contexts[PROJECT_LSM6DSV32X_INSTANCE_COUNT];
_Static_assert(PROJECT_LSM6DSV32X_INSTANCE_COUNT <= 4U, "IMU context bound exceeded");

const char * Lsm6Dsv32XImuInstance_NameGet(uint8_t instance)
{
    return (instance < PROJECT_LSM6DSV32X_INSTANCE_COUNT) ? "LSM6DSV32X" : "Invalid IMU";
}

SystemDeviceResult Lsm6Dsv32XImuInstance_Init(uint8_t instance)
{
    ProjectLsm6Dsv32XResources resources;
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectLsm6Dsv32XResources_Get(instance, &resources) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SensorImuAdapter_Init(&s_contexts[instance], Lsm6Dsv32X_ProfileGet(),
        resources.i2c, 0x6AU, instance);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].owner_active = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XImuInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(info, 0, sizeof(*info));
    info->device_name = "LSM6DSV32X";
    info->model_name = "LSM6DSV32X";
    info->driver_version = "1.0.0-HARDWARE_UNVERIFIED";
    info->capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_error_count = s_contexts[instance].driver.bus_errors;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(detail, 0, sizeof(*detail));
    detail->valid_frame_count = s_contexts[instance].driver.sample_count;
    detail->config_generation = s_contexts[instance].driver.config_generation;
    detail->config_generation_valid = s_contexts[instance].driver.profile_verified;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv32XImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 0U);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 1U);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Lsm6Dsv32XImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigCheck(&s_contexts[instance], config, report);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult Lsm6Dsv32XImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_LSM6DSV32X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
