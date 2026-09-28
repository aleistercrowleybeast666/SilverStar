#include "lsm6dsv320x_instance.h"
#include "lsm6dsv320x_device.h"
#include "sensor_imu_adapter.h"
#include "project_resources.h"
#include "platform_critical.h"
#include "platform_time.h"
#include <stddef.h>
#include <string.h>

static SensorImuAdapter s_contexts[PROJECT_LSM6DSV320X_INSTANCE_COUNT];
static SensorHighGState s_high_g_state[PROJECT_LSM6DSV320X_INSTANCE_COUNT];
static SensorHighGSample s_high_g_latest[PROJECT_LSM6DSV320X_INSTANCE_COUNT];
_Static_assert(PROJECT_LSM6DSV320X_INSTANCE_COUNT <= 4U, "IMU context bound exceeded");

const char * Lsm6Dsv320XImuInstance_NameGet(uint8_t instance)
{
    return (instance < PROJECT_LSM6DSV320X_INSTANCE_COUNT) ? "LSM6DSV320X" : "Invalid IMU";
}

SystemDeviceResult Lsm6Dsv320XImuInstance_Init(uint8_t instance)
{
    ProjectLsm6Dsv320XResources resources;
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectLsm6Dsv320XResources_Get(instance, &resources) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_NOT_PRESENT; }
    memset(&s_high_g_state[instance], 0, sizeof(s_high_g_state[instance]));
    memset(&s_high_g_latest[instance], 0, sizeof(s_high_g_latest[instance]));
    return SensorImuAdapter_Init(&s_contexts[instance], Lsm6Dsv320X_ProfileGet(),
        resources.i2c, 0x6AU, instance);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].owner_active = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_Process(uint8_t instance)
{
    SystemDeviceResult low_g;
    SensorHighGSample high_g;
    SensorImuResult result;
    uint64_t now_us;
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    low_g = SensorImuAdapter_Process(&s_contexts[instance]);
    now_us = PlatformTime_Us();
    result = SensorHighG_ReadLsm6Dsv320X(&s_contexts[instance].driver,
        &s_high_g_state[instance], now_us, now_us, &high_g);
    if (result == SENSOR_IMU_OK)
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        s_high_g_latest[instance] = high_g;
        PlatformCritical_Exit(lock);
    }
    return low_g;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_HighGSampleGet(uint8_t instance, SensorHighGSample *sample)
{
    PlatformCriticalState lock;
    if ((instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) || (sample == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    lock = PlatformCritical_Enter();
    *sample = s_high_g_latest[instance];
    PlatformCritical_Exit(lock);
    if ((s_contexts[instance].driver.profile_verified == 0U) ||
        (PlatformTime_Us() < sample->receive_timestamp_us) ||
        (PlatformTime_Us() - sample->receive_timestamp_us > 20000U)) { return SYSTEM_DEVICE_NOT_READY; }
    return (sample->sequence != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(info, 0, sizeof(*info));
    info->device_name = "LSM6DSV320X";
    info->model_name = "LSM6DSV320X";
    info->driver_version = "1.0.0-HARDWARE_UNVERIFIED";
    info->capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_error_count = s_contexts[instance].driver.bus_errors;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(detail, 0, sizeof(*detail));
    detail->valid_frame_count = s_contexts[instance].driver.sample_count;
    detail->config_generation = s_contexts[instance].driver.config_generation;
    detail->config_generation_valid = s_contexts[instance].driver.profile_verified;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 0U);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 1U);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Lsm6Dsv320XImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigCheck(&s_contexts[instance], config, report);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return SensorImuAdapter_ConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult Lsm6Dsv320XImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_LSM6DSV320X_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
