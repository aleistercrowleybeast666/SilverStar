#include "mpu6050_instance.h"
#include "mpu6050_device.h"
#include "sensor_imu_adapter.h"
#include "project_resources.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "silverstar_assert.h"
#include "project_device_build_capabilities.h"
#include <limits.h>
#include <stddef.h>
#include <string.h>

static SensorImuAdapter s_contexts[PROJECT_MPU6050_INSTANCE_COUNT];
_Static_assert(PROJECT_MPU6050_INSTANCE_COUNT <= 4U, "IMU context bound exceeded");

/* DeviceTask is the sole retry owner. No retry reconstructs driver/selector. */
typedef struct
{
    uint32_t scheduled_ms;
    uint32_t attempt_ms;
    uint8_t prepared;
    uint8_t waiting;
    uint8_t failures;
    uint8_t start_intent;
    uint8_t qualification_revoked;
} Mpu6050RecoveryState;
static Mpu6050RecoveryState s_recovery[PROJECT_MPU6050_INSTANCE_COUNT];
#define MPU6050_RECOVERY_ATTEMPT_MS 2000U
#define MPU6050_RECOVERY_STALE_US 100000ULL
#define MPU6050_RECOVERY_BACKOFF_MAX 5U

static void Mpu6050Recovery_Revoke(uint8_t instance)
{
    SensorImuAdapter *adapter = &s_contexts[instance];
    PlatformCriticalState lock = PlatformCritical_Enter();
    adapter->driver.profile_verified = 0U;
    adapter->driver.state = SENSOR_IMU_FAULT;
    if (adapter->driver.last_result == SENSOR_IMU_OK)
    { adapter->driver.last_result = SENSOR_IMU_NOT_READY; }
    adapter->driver.history_reset = 1U;
    adapter->latest.valid_mask = 0U;
    adapter->latest.sequence = 0U;
    adapter->health.initialized = 0U;
    adapter->health.started = 0U;
    adapter->health.online = 0U;
    adapter->health.healthy = 0U;
    s_recovery[instance].qualification_revoked = 1U;
    PlatformCritical_Exit(lock);
}

static void Mpu6050Recovery_Wait(uint8_t instance)
{
    Mpu6050RecoveryState *recovery = &s_recovery[instance];
    Mpu6050Recovery_Revoke(instance);
    recovery->scheduled_ms = PlatformTime_Ms();
    recovery->waiting = 1U;
    if (recovery->failures < MPU6050_RECOVERY_BACKOFF_MAX + 1U)
    { recovery->failures++; }
}

static SystemDeviceResult Mpu6050Recovery_Begin(uint8_t instance)
{
    SensorImuResult result;
    SensorImuAdapter *adapter = &s_contexts[instance];
    SILVERSTAR_ASSERT(s_recovery[instance].prepared != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(adapter->driver.profile != NULL,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    /* Never wrap an epoch and silently reuse a previous configuration ID. */
    if (adapter->driver.config_generation == UINT32_MAX)
    { Mpu6050Recovery_Wait(instance); return SYSTEM_DEVICE_NOT_READY; }
    result = SensorImu_BeginConfigure(&adapter->driver, PlatformTime_Us(), 1U);
    if (result != SENSOR_IMU_BUSY)
    { Mpu6050Recovery_Wait(instance); return SYSTEM_DEVICE_VERIFY_FAILED; }
    s_recovery[instance].waiting = 0U;
    s_recovery[instance].attempt_ms = PlatformTime_Ms();
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

static SystemDeviceResult Mpu6050Recovery_Process(uint8_t instance)
{
    SensorImuAdapter *adapter = &s_contexts[instance];
    Mpu6050RecoveryState *recovery = &s_recovery[instance];
    SystemDeviceResult result;
    uint64_t now_us = PlatformTime_Us();
    SILVERSTAR_ASSERT(recovery->failures <= MPU6050_RECOVERY_BACKOFF_MAX + 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(recovery->waiting <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((recovery->prepared == 0U) || (recovery->start_intent == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    if (recovery->waiting != 0U)
    {
        uint32_t shift = (recovery->failures > 0U) ? recovery->failures - 1U : 0U;
        if ((uint32_t)(PlatformTime_Ms() - recovery->scheduled_ms) < (1000UL << shift))
        { return SYSTEM_DEVICE_NOT_READY; }
        return Mpu6050Recovery_Begin(instance);
    }
    if (((adapter->driver.state == SENSOR_IMU_READY) &&
         ((now_us < adapter->health.last_receive_timestamp_us) ||
          (now_us - adapter->health.last_receive_timestamp_us > MPU6050_RECOVERY_STALE_US))) ||
        ((adapter->driver.state != SENSOR_IMU_READY) &&
         ((uint32_t)(PlatformTime_Ms() - recovery->attempt_ms) >= MPU6050_RECOVERY_ATTEMPT_MS)))
    { Mpu6050Recovery_Wait(instance); return SYSTEM_DEVICE_TIMEOUT; }
    result = SensorImuAdapter_Process(adapter);
    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_NOT_READY))
    { Mpu6050Recovery_Wait(instance); return result; }
    if ((adapter->driver.state == SENSOR_IMU_READY) &&
        (adapter->driver.profile_verified != 0U) && (adapter->latest.sequence != 0U))
    {
        PlatformCriticalState lock = PlatformCritical_Enter();
        adapter->health.initialized = 1U;
        adapter->health.started = 1U;
        recovery->failures = 0U;
        PlatformCritical_Exit(lock);
    }
    return result;
}

SystemDeviceResult Mpu6050ImuInstance_RecoveryPreparedGet(uint8_t instance, uint8_t *prepared)
{
    if ((instance >= PROJECT_MPU6050_INSTANCE_COUNT) || (prepared == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *prepared = 0U;
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        *prepared = s_recovery[instance].prepared;
        return SYSTEM_DEVICE_OK;
    }
    return SYSTEM_DEVICE_UNSUPPORTED;
}

const char * Mpu6050ImuInstance_NameGet(uint8_t instance)
{
    return (instance < PROJECT_MPU6050_INSTANCE_COUNT) ? "MPU6050" : "Invalid IMU";
}

SystemDeviceResult Mpu6050ImuInstance_Init(uint8_t instance)
{
    ProjectMpu6050Resources resources;
    SystemDeviceResult result;
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (ProjectMpu6050Resources_Get(instance, &resources) != SYSTEM_DEVICE_OK) { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        if (s_recovery[instance].prepared != 0U) { return SYSTEM_DEVICE_BUSY; }
        result = SensorImuAdapter_PrepareI2c(&s_contexts[instance], Mpu6050_ProfileGet(),
            resources.i2c, resources.i2c, 0x68U, instance);
        if (result != SYSTEM_DEVICE_OK) { return result; }
        if (SensorImu_AxisMapSet(&s_contexts[instance].driver, resources.axis_map, 0U) != SENSOR_IMU_OK)
        { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
        s_recovery[instance].prepared = 1U;
        return Mpu6050Recovery_Begin(instance);
    }
    result = SensorImuAdapter_Init(&s_contexts[instance], Mpu6050_ProfileGet(),
        resources.i2c, 0x68U, instance);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    return SensorImuAdapter_MountSet(&s_contexts[instance], resources.axis_map);
}

SystemDeviceResult Mpu6050ImuInstance_Start(uint8_t instance)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        if (s_recovery[instance].prepared == 0U) { return SYSTEM_DEVICE_NOT_READY; }
        s_recovery[instance].start_intent = 1U;
        s_contexts[instance].started = 1U;
        if (s_contexts[instance].driver.state == SENSOR_IMU_STOPPED)
        { return Mpu6050Recovery_Begin(instance); }
        return (s_contexts[instance].health.initialized != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_CONFIG_DELEGATED;
    }
    return SensorImuAdapter_Start(&s_contexts[instance]);
}

SystemDeviceResult Mpu6050ImuInstance_Stop(uint8_t instance)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        s_recovery[instance].start_intent = 0U;
        Mpu6050Recovery_Revoke(instance);
    }
    return SensorImuAdapter_Stop(&s_contexts[instance]);
}

SystemDeviceResult Mpu6050ImuInstance_RuntimeOwnerActivate(uint8_t instance)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_contexts[instance].owner_active = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mpu6050ImuInstance_Process(uint8_t instance)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        return Mpu6050Recovery_Process(instance);
    }
    return SensorImuAdapter_Process(&s_contexts[instance]);
}

SystemDeviceResult Mpu6050ImuInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(info, 0, sizeof(*info));
    info->device_name = "MPU6050";
    info->model_name = "MPU6050";
    info->driver_version = "1.0.0-HARDWARE_UNVERIFIED";
    info->capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mpu6050ImuInstance_CapabilitiesGet(uint8_t instance, uint32_t *capability_mask)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO | SYSTEM_IMU_CAP_TEMPERATURE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mpu6050ImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        SystemDeviceResult result = SensorImuAdapter_HealthGet(&s_contexts[instance], health);
        if (result != SYSTEM_DEVICE_OK) { return result; }
        {
            PlatformCriticalState lock = PlatformCritical_Enter();
            /* Physical recovery is not calibration/alignment/mission qualification.
             * This prototype has deliberately no automatic qualification-clear path. */
            if (s_recovery[instance].qualification_revoked != 0U) { health->healthy = 0U; }
            PlatformCritical_Exit(lock);
        }
        return SYSTEM_DEVICE_OK;
    }
    return SensorImuAdapter_HealthGet(&s_contexts[instance], health);
}

SystemDeviceResult Mpu6050ImuInstance_IoDiagnosticsGet(uint8_t instance, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_error_count = s_contexts[instance].driver.bus_errors;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mpu6050ImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(detail, 0, sizeof(*detail));
    detail->valid_frame_count = s_contexts[instance].driver.sample_count;
    detail->config_generation = s_contexts[instance].driver.config_generation;
    detail->config_generation_valid = s_contexts[instance].driver.profile_verified;
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        {
            SystemDeviceHealth health;
            if ((SensorImuAdapter_HealthGet(&s_contexts[instance], &health) != SYSTEM_DEVICE_OK) ||
                (health.initialized == 0U) || (health.online == 0U))
            { detail->config_generation_valid = 0U; }
        }
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Mpu6050ImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        SystemDeviceHealth health;
        if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
        if ((SensorImuAdapter_HealthGet(&s_contexts[instance], &health) != SYSTEM_DEVICE_OK) ||
            (health.initialized == 0U) || (health.online == 0U)) { return SYSTEM_DEVICE_NOT_READY; }
    }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 0U);
}

SystemDeviceResult Mpu6050ImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        SystemDeviceHealth health;
        if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
        if ((SensorImuAdapter_HealthGet(&s_contexts[instance], &health) != SYSTEM_DEVICE_OK) ||
            (health.initialized == 0U) || (health.online == 0U)) { return SYSTEM_DEVICE_NOT_READY; }
    }
    return SensorImuAdapter_SampleGet(&s_contexts[instance], sample, 1U);
}

SystemDeviceResult Mpu6050ImuInstance_SelfTestRun(uint8_t instance, SystemDeviceSelfTestResult *result)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Mpu6050ImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        return SensorImuAdapter_ConfigRequest(&s_contexts[instance], config, report);
    }
    return SensorImuAdapter_ConfigApply(&s_contexts[instance], config, report);
}

SystemDeviceResult Mpu6050ImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        if ((config == NULL) || (report == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
        if (s_contexts[instance].driver.state != SENSOR_IMU_READY)
        { memset(report, 0, sizeof(*report)); return SYSTEM_DEVICE_BUSY; }
    }
    return SensorImuAdapter_ConfigCheck(&s_contexts[instance], config, report);
}

SystemDeviceResult Mpu6050ImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (SILVERSTAR_BUILD_COMPACT_ENABLED != 0U)
    {
        SystemDeviceHealth health;
        if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
        if ((SensorImuAdapter_HealthGet(&s_contexts[instance], &health) != SYSTEM_DEVICE_OK) ||
            (health.initialized == 0U) || (health.online == 0U))
        { memset(config, 0, sizeof(*config)); return SYSTEM_DEVICE_NOT_READY; }
    }
    return SensorImuAdapter_ConfigGet(&s_contexts[instance], config);
}

SystemDeviceResult Mpu6050ImuInstance_NoiseCharacteristicsGet(uint8_t instance, SystemImuNoiseCharacteristics *noise)
{
    if (instance >= PROJECT_MPU6050_INSTANCE_COUNT) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
