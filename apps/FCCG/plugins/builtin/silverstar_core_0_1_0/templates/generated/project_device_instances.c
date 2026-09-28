#include "project_device_instances.h"

#include <stddef.h>

#include "silverstar_assert.h"

static SystemDeviceResult ProjectDeviceInstance_Validate(
    SystemDeviceClass device_class, uint8_t instance_id)
{
    SystemDeviceDescriptor descriptor;

    return SystemDescriptor_DeviceFind(device_class, instance_id, &descriptor);
}

uint8_t ProjectDeviceInstance_CountGet(SystemDeviceClass device_class)
{
    return SystemDescriptor_DeviceClassInstanceCountGet(device_class);
}

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    SystemDeviceResult result = ProjectDeviceInstance_Validate(
        device_class, instance_id);

    if (result != SYSTEM_DEVICE_OK) { return result; }
    return SystemDescriptor_DeviceFind(
        device_class, instance_id, descriptor);
}

SystemDeviceResult ProjectDeviceInstance_InfoGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceInfo *info)
{
    SystemDeviceResult result;

    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(info, SystemDeviceInfo,
        SILVERSTAR_ASSERT_MODULE_GENERATED);
    result = ProjectDeviceInstance_Validate(device_class, instance_id);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU:
            return ProjectImuInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_GNSS:
            return ProjectGnssInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_BAROMETER:
            return ProjectBarometerInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
            return ProjectMagnetometerInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
            return ProjectAttitudeInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_TELEMETRY:
            return ProjectTelemetryInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_POWER:
            return ProjectPowerInstance_InfoGet(instance_id, info);
        case SYSTEM_DEVICE_CLASS_CONSOLE:
        case SYSTEM_DEVICE_CLASS_STORAGE:
        case SYSTEM_DEVICE_CLASS_LOG_SINK:
        case SYSTEM_DEVICE_CLASS_OUTPUT:
        case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
        case SYSTEM_DEVICE_CLASS_TIME:
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

SystemDeviceResult ProjectDeviceInstance_CapabilitiesGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    uint32_t *capability_mask)
{
    SystemDeviceResult result;

    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(capability_mask, uint32_t,
        SILVERSTAR_ASSERT_MODULE_GENERATED);
    result = ProjectDeviceInstance_Validate(device_class, instance_id);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU:
            return ProjectImuInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_GNSS:
            return ProjectGnssInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_BAROMETER:
            return ProjectBarometerInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
            return ProjectMagnetometerInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
            return ProjectAttitudeInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_TELEMETRY:
            return ProjectTelemetryInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_POWER:
            return ProjectPowerInstance_CapabilitiesGet(
                instance_id, capability_mask);
        case SYSTEM_DEVICE_CLASS_CONSOLE:
        case SYSTEM_DEVICE_CLASS_STORAGE:
        case SYSTEM_DEVICE_CLASS_LOG_SINK:
        case SYSTEM_DEVICE_CLASS_OUTPUT:
        case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
        case SYSTEM_DEVICE_CLASS_TIME:
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

SystemDeviceResult ProjectDeviceInstance_HealthGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceHealth *health)
{
    SystemDeviceResult result;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_GENERATED);
    result = ProjectDeviceInstance_Validate(device_class, instance_id);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU:
            return ProjectImuInstance_HealthGet(instance_id, health);
        case SYSTEM_DEVICE_CLASS_GNSS:
            return ProjectGnssInstance_HealthGet(instance_id, health);
        case SYSTEM_DEVICE_CLASS_BAROMETER:
            return ProjectBarometerInstance_HealthGet(instance_id, health);
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
            return ProjectMagnetometerInstance_HealthGet(instance_id, health);
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
            return ProjectAttitudeInstance_HealthGet(instance_id, health);
        case SYSTEM_DEVICE_CLASS_POWER:
            return ProjectPowerInstance_HealthGet(instance_id, health);
        case SYSTEM_DEVICE_CLASS_TELEMETRY:
        case SYSTEM_DEVICE_CLASS_CONSOLE:
        case SYSTEM_DEVICE_CLASS_STORAGE:
        case SYSTEM_DEVICE_CLASS_LOG_SINK:
        case SYSTEM_DEVICE_CLASS_OUTPUT:
        case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
        case SYSTEM_DEVICE_CLASS_TIME:
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemDeviceResult ProjectDeviceInstance_IoDirectGet(
    const SystemDeviceDescriptor *descriptor,
    SystemDeviceIoDiagnostics *diagnostics)
{
    if ((descriptor == NULL) || (diagnostics == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_GENERATED);
    switch (descriptor->device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU:
            return ProjectImuInstance_IoDiagnosticsGet(
                descriptor->instance_id, diagnostics);
        case SYSTEM_DEVICE_CLASS_GNSS:
            return ProjectGnssInstance_IoDiagnosticsGet(
                descriptor->instance_id, diagnostics);
        case SYSTEM_DEVICE_CLASS_TELEMETRY:
            return ProjectTelemetryInstance_IoDiagnosticsGet(
                descriptor->instance_id, diagnostics);
        case SYSTEM_DEVICE_CLASS_BAROMETER:
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
        case SYSTEM_DEVICE_CLASS_CONSOLE:
        case SYSTEM_DEVICE_CLASS_POWER:
        case SYSTEM_DEVICE_CLASS_STORAGE:
        case SYSTEM_DEVICE_CLASS_LOG_SINK:
        case SYSTEM_DEVICE_CLASS_OUTPUT:
        case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
        case SYSTEM_DEVICE_CLASS_TIME:
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

SystemDeviceResult ProjectDeviceInstance_IoDiagnosticsGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceIoDiagnostics *diagnostics,
    SystemDeviceDescriptor *owner_descriptor)
{
    SystemDeviceDescriptor requested;
    SystemDeviceDescriptor candidate;
    SystemDeviceResult result;
    uint16_t count;
    uint16_t index;

    if ((diagnostics == NULL) || (owner_descriptor == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_GENERATED);
    result = ProjectDeviceInstance_DescriptorGet(
        device_class, instance_id, &requested);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if (requested.physical_device_id == PROJECT_PHYSICAL_DEVICE_ID_NONE)
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    count = SystemDescriptor_DeviceCountGet();
    for (index = 0U; index < SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX; index++)
    {
        if (index >= count) { break; }
        result = SystemDescriptor_DeviceGet(index, &candidate);
        if (result != SYSTEM_DEVICE_OK) { return result; }
        if (candidate.physical_device_id != requested.physical_device_id)
        {
            continue;
        }
        result = ProjectDeviceInstance_IoDirectGet(&candidate, diagnostics);
        if (result == SYSTEM_DEVICE_OK)
        {
            *owner_descriptor = candidate;
            return SYSTEM_DEVICE_OK;
        }
        if (result != SYSTEM_DEVICE_UNSUPPORTED) { return result; }
    }
    return SYSTEM_DEVICE_UNSUPPORTED;
}

uint8_t ProjectImuInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_IMU);
}

SystemDeviceResult ProjectImuInstance_Init(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemImu_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_Start(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemImu_Start();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_Stop(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemImu_Stop();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_RuntimeOwnerActivate(
    uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemImu_RuntimeOwnerActivate();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_Process(uint8_t instance_id)
{
    switch (instance_id)
    {
        /* The renderer replaces this reference operation with the direct
         * instance-aware Process operation declared by the selected plugin. */
        case 0U: return SystemImu_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_LatestSampleGet(
    uint8_t instance_id, SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_LatestSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_NextSampleGet(
    uint8_t instance_id, SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_NextSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_SelfTestRun(result);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_ConfigApply(
    uint8_t instance_id, const SystemImuConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_ConfigApply(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_ConfigVerify(
    uint8_t instance_id, const SystemImuConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_ConfigVerify(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemImuConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_EffectiveConfigGet(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_NoiseCharacteristicsGet(
    uint8_t instance_id, SystemImuNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_NoiseCharacteristicsGet(noise);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_IoDetailGet(
    uint8_t instance_id, SystemImuIoDetail *detail)
{
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_IoDetailGet(detail);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectImuInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_IoDiagnosticsGet(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

uint8_t ProjectGnssInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_GNSS);
}

SystemDeviceResult ProjectGnssInstance_Init(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemGnss_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_Start(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemGnss_Start();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_Stop(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemGnss_Stop();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_RuntimeOwnerActivate(
    uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemGnss_RuntimeOwnerActivate();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_Process(uint8_t instance_id)
{
    switch (instance_id)
    {
        /* Replaced by the selected plugin's direct Process operation. */
        case 0U: return SystemGnss_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_LatestSampleGet(
    uint8_t instance_id, SystemGnssSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_LatestSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_TimeGet(
    uint8_t instance_id, SystemGnssTime *time)
{
    if (time == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_TimeGet(time);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_SelfTestRun(result);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_ConfigApply(
    uint8_t instance_id, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_ConfigApply(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_ConfigVerify(
    uint8_t instance_id, const SystemGnssConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_ConfigVerify(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemGnssConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_EffectiveConfigGet(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_NoiseCharacteristicsGet(
    uint8_t instance_id, SystemGnssNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_NoiseCharacteristicsGet(noise);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_HardwareConfigRead(
    uint8_t instance_id, SystemGnssHardwareConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_HardwareConfigRead(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance_id, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_SatelliteDiagnosticsRead(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_RfDiagnosticsRead(
    uint8_t instance_id, SystemGnssRfDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_RfDiagnosticsRead(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_LastConfigReportGet(
    uint8_t instance_id, SystemGnssConfigTransactionReport *report)
{
    if (report == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_LastConfigReportGet(report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_LatestSatelliteDiagnosticsGet(
    uint8_t instance_id, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_LatestSatelliteDiagnosticsGet(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_LatestRfDiagnosticsGet(
    uint8_t instance_id, SystemGnssRfDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_LatestRfDiagnosticsGet(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_IoDetailGet(
    uint8_t instance_id, SystemGnssIoDetail *detail)
{
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_IoDetailGet(detail);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_IoDiagnosticsGet(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

uint8_t ProjectBarometerInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_BAROMETER);
}

SystemDeviceResult ProjectBarometerInstance_Init(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemBarometer_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_Start(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemBarometer_Start();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_Stop(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemBarometer_Stop();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemBarometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_LatestSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_SelfTestRun(result);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_ConfigApply(
    uint8_t instance_id, const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_ConfigApply(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_ConfigVerify(
    uint8_t instance_id, const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_ConfigVerify(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemBarometerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_EffectiveConfigGet(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_NoiseCharacteristicsGet(
    uint8_t instance_id, SystemBarometerNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemBarometer_NoiseCharacteristicsGet(noise);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

uint8_t ProjectMagnetometerInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_MAGNETOMETER);
}

SystemDeviceResult ProjectMagnetometerInstance_Init(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_Start(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_Start();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_Stop(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_Stop();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_LatestSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_SelfTestRun(result);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_ConfigApply(
    uint8_t instance_id, const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_ConfigApply(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_ConfigVerify(
    uint8_t instance_id, const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_ConfigVerify(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectMagnetometerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemMagnetometerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemMagnetometer_EffectiveConfigGet(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

uint8_t ProjectAttitudeInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
}

SystemDeviceResult ProjectAttitudeInstance_Init(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_Start(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_Start();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_Stop(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_Stop();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U:
            return SystemHardwareQuaternion_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_LatestSampleGet(
    uint8_t instance_id, SystemHardwareQuaternionSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_LatestSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_SelfTestRun(result);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_ConfigApply(
    uint8_t instance_id, const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_ConfigApply(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_ConfigVerify(
    uint8_t instance_id, const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_ConfigVerify(config, report);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectAttitudeInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemHardwareQuaternionConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemHardwareQuaternion_EffectiveConfigGet(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

uint8_t ProjectTelemetryInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_TELEMETRY);
}

SystemDeviceResult ProjectTelemetryInstance_Init(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_Start(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_Start();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_Stop(uint8_t instance_id)
{
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_Stop();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_Send(
    uint8_t instance_id, const uint8_t *data, uint16_t length)
{
    if ((data == NULL) || (length == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_Send(data, length);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_Receive(
    uint8_t instance_id, uint8_t *data, uint16_t capacity,
    uint16_t *length)
{
    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_Receive(data, capacity, length);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_Process(uint8_t instance_id)
{
    switch (instance_id)
    {
        /* Replaced by the selected plugin's direct Process operation. */
        case 0U: return SystemTelemetry_Init();
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_HealthGet(
    uint8_t instance_id, SystemTelemetryHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_IoDiagnosticsGet(diagnostics);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_SelfTestRun(
    uint8_t instance_id, SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_SelfTestRun(result);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectTelemetryInstance_MtuGet(
    uint8_t instance_id, uint16_t *mtu)
{
    if (mtu == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemTelemetry_MtuGet(mtu);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

uint8_t ProjectPowerInstance_CountGet(void)
{
    return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_POWER);
}

SystemDeviceResult ProjectPowerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemPower_InfoGet(info);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectPowerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemPower_CapabilitiesGet(capability_mask);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectPowerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemPower_HealthGet(health);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectPowerInstance_LatestSampleGet(
    uint8_t instance_id, SystemPowerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemPower_LatestSampleGet(sample);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectPowerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemPowerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemPower_EffectiveConfigGet(config);
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}
