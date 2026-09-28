#include "project_device_instances.h"

#include <stddef.h>

#include "system_user_config.h"

static const SystemDeviceDescriptor s_fixture_devices[] =
{
    {1U, 1U, SYSTEM_DEVICE_CLASS_IMU, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_REQUIRED |
     SYSTEM_DESCRIPTOR_FLAG_PRIMARY | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, SYSTEM_IMU_OUTPUT_RATE_HZ, 1U, 1U},
    {14U, 9U, SYSTEM_DEVICE_CLASS_IMU, 1U, 2U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED, 0U, 100U, 2U, 2U},
    {2U, 2U, SYSTEM_DEVICE_CLASS_GNSS, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_PRIMARY,
     0U, SYSTEM_GNSS_NAVIGATION_RATE_HZ, 3U, 3U},
    {15U, 10U, SYSTEM_DEVICE_CLASS_GNSS, 1U, 2U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED, 0U, 10U, 4U, 4U},
    {3U, 1U, SYSTEM_DEVICE_CLASS_BAROMETER, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, SYSTEM_BAROMETER_OUTPUT_RATE_HZ, 1U, 1U},
    {4U, 1U, SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, SYSTEM_HARDWARE_QUATERNION_OUTPUT_RATE_HZ, 1U, 1U},
    {5U, 3U, SYSTEM_DEVICE_CLASS_TELEMETRY, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED, 0U, 0U, 5U, 5U},
    {6U, 4U, SYSTEM_DEVICE_CLASS_CONSOLE, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED, 0U, 0U, 6U, 6U},
    {7U, 5U, SYSTEM_DEVICE_CLASS_POWER, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED, 0U, 50U, 7U, 7U},
    {8U, 6U, SYSTEM_DEVICE_CLASS_STORAGE, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, 0U, 8U, 8U},
    {9U, 6U, SYSTEM_DEVICE_CLASS_LOG_SINK, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, 0U, 9U, 9U},
    {10U, 7U, SYSTEM_DEVICE_CLASS_OUTPUT, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, 0U, 10U, 10U},
    {11U, 7U, SYSTEM_DEVICE_CLASS_MISSION_ACTION, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL,
     0U, 0U, 11U, 11U},
    {12U, 0U, SYSTEM_DEVICE_CLASS_TIME, 0U, 1U,
     SYSTEM_DESCRIPTOR_FLAG_ENABLED | SYSTEM_DESCRIPTOR_FLAG_PRIMARY,
     0U, 1000000U, 12U, 12U}
};

uint16_t SystemDescriptor_DeviceCountGet(void)
{
    return (uint16_t)(sizeof(s_fixture_devices) /
                      sizeof(s_fixture_devices[0]));
}

SystemDeviceResult SystemDescriptor_DeviceGet(
    uint16_t index, SystemDeviceDescriptor *descriptor)
{
    if ((descriptor == NULL) || (index >= SystemDescriptor_DeviceCountGet()))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *descriptor = s_fixture_devices[index];
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemDescriptor_DeviceClassInstanceCountGet(
    SystemDeviceClass device_class)
{
    uint8_t count = 0U;
    uint16_t index;

    for (index = 0U; index < SystemDescriptor_DeviceCountGet(); index++)
    {
        if (s_fixture_devices[index].device_class == device_class) { count++; }
    }
    return count;
}

SystemDeviceResult SystemDescriptor_DeviceFind(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    uint16_t index;

    if (descriptor == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    for (index = 0U; index < SystemDescriptor_DeviceCountGet(); index++)
    {
        if ((s_fixture_devices[index].device_class == device_class) &&
            (s_fixture_devices[index].instance_id == instance_id))
        {
            *descriptor = s_fixture_devices[index];
            return SYSTEM_DEVICE_OK;
        }
    }
    return SYSTEM_DEVICE_NOT_PRESENT;
}

uint16_t SystemDescriptor_AlgorithmCountGet(void) { return 0U; }
SystemDeviceResult SystemDescriptor_AlgorithmGet(
    uint16_t index, SystemAlgorithmDescriptor *descriptor)
{
    (void)index;
    (void)descriptor;
    return SYSTEM_DEVICE_INVALID_ARGUMENT;
}
uint32_t SystemDescriptor_ConfigDigestGet(void) { return 0x12345678UL; }

uint8_t ProjectDeviceInstance_CountGet(SystemDeviceClass device_class)
{
    return SystemDescriptor_DeviceClassInstanceCountGet(device_class);
}

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    return SystemDescriptor_DeviceFind(device_class, instance_id, descriptor);
}

uint8_t ProjectImuInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_IMU); }
uint8_t ProjectGnssInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_GNSS); }
uint8_t ProjectBarometerInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_BAROMETER); }
uint8_t ProjectMagnetometerInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_MAGNETOMETER); }
uint8_t ProjectAttitudeInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION); }
uint8_t ProjectTelemetryInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_TELEMETRY); }
uint8_t ProjectPowerInstance_CountGet(void)
{ return ProjectDeviceInstance_CountGet(SYSTEM_DEVICE_CLASS_POWER); }

SystemDeviceResult ProjectImuInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    SystemDeviceResult result;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemImu_InfoGet(info);
        case 1U:
            result = SystemImu_InfoGet(info);
            if (result == SYSTEM_DEVICE_OK)
            {
                info->device_name = "MOCK_IMU_B";
                info->model_name = "HOST_IMU_B";
            }
            return result;
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectGnssInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    SystemDeviceResult result;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (instance_id)
    {
        case 0U: return SystemGnss_InfoGet(info);
        case 1U:
            result = SystemGnss_InfoGet(info);
            if (result == SYSTEM_DEVICE_OK)
            {
                info->device_name = "MOCK_GNSS_B";
                info->model_name = "HOST_GNSS_B";
            }
            return result;
        default: return SYSTEM_DEVICE_NOT_PRESENT;
    }
}

SystemDeviceResult ProjectBarometerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemBarometer_InfoGet(info);
}
SystemDeviceResult ProjectMagnetometerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemMagnetometer_InfoGet(info);
}
SystemDeviceResult ProjectAttitudeInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemHardwareQuaternion_InfoGet(info);
}
SystemDeviceResult ProjectTelemetryInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemTelemetry_InfoGet(info);
}
SystemDeviceResult ProjectPowerInstance_InfoGet(
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemPower_InfoGet(info);
}

SystemDeviceResult ProjectDeviceInstance_InfoGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceInfo *info)
{
    if (SystemDescriptor_DeviceFind(device_class, instance_id,
        &(SystemDeviceDescriptor){0}) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_PRESENT; }
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
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

SystemDeviceResult ProjectImuInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemImu_CapabilitiesGet(mask);
}
SystemDeviceResult ProjectGnssInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_CapabilitiesGet(mask);
}
SystemDeviceResult ProjectBarometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemBarometer_CapabilitiesGet(mask);
}
SystemDeviceResult ProjectMagnetometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemMagnetometer_CapabilitiesGet(mask);
}
SystemDeviceResult ProjectAttitudeInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemHardwareQuaternion_CapabilitiesGet(mask);
}
SystemDeviceResult ProjectTelemetryInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemTelemetry_CapabilitiesGet(mask);
}
SystemDeviceResult ProjectPowerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemPower_CapabilitiesGet(mask);
}

SystemDeviceResult ProjectDeviceInstance_CapabilitiesGet(
    SystemDeviceClass device_class, uint8_t instance_id, uint32_t *mask)
{
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU:
            return ProjectImuInstance_CapabilitiesGet(instance_id, mask);
        case SYSTEM_DEVICE_CLASS_GNSS:
            return ProjectGnssInstance_CapabilitiesGet(instance_id, mask);
        case SYSTEM_DEVICE_CLASS_BAROMETER:
            return ProjectBarometerInstance_CapabilitiesGet(instance_id, mask);
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
            return ProjectMagnetometerInstance_CapabilitiesGet(instance_id, mask);
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
            return ProjectAttitudeInstance_CapabilitiesGet(instance_id, mask);
        case SYSTEM_DEVICE_CLASS_TELEMETRY:
            return ProjectTelemetryInstance_CapabilitiesGet(instance_id, mask);
        case SYSTEM_DEVICE_CLASS_POWER:
            return ProjectPowerInstance_CapabilitiesGet(instance_id, mask);
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemDeviceResult Fixture_DeviceHealthAdjust(
    SystemDeviceResult result, uint8_t instance_id, SystemDeviceHealth *health)
{
    if ((result == SYSTEM_DEVICE_OK) && (instance_id == 1U))
    { health->health_flags ^= 0xB1U; }
    return result;
}

SystemDeviceResult ProjectImuInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Fixture_DeviceHealthAdjust(
        SystemImu_HealthGet(health), instance_id, health);
}
SystemDeviceResult ProjectGnssInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return Fixture_DeviceHealthAdjust(
        SystemGnss_HealthGet(health), instance_id, health);
}
SystemDeviceResult ProjectBarometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemBarometer_HealthGet(health);
}
SystemDeviceResult ProjectMagnetometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemMagnetometer_HealthGet(health);
}
SystemDeviceResult ProjectAttitudeInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemHardwareQuaternion_HealthGet(health);
}
SystemDeviceResult ProjectPowerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemPower_HealthGet(health);
}

SystemDeviceResult ProjectDeviceInstance_HealthGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceHealth *health)
{
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
        default: return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

SystemDeviceResult ProjectImuInstance_LatestSampleGet(
    uint8_t instance_id, SystemImuSample *sample)
{
    SystemDeviceResult result;
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    result = SystemImu_LatestSampleGet(sample);
    if ((result == SYSTEM_DEVICE_OK) && (instance_id == 1U))
    {
        sample->sequence += 1000U;
        sample->accel_raw[0] += 1000;
    }
    return result;
}

SystemDeviceResult ProjectGnssInstance_LatestSampleGet(
    uint8_t instance_id, SystemGnssSample *sample)
{
    SystemDeviceResult result;
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    result = SystemGnss_LatestSampleGet(sample);
    if ((result == SYSTEM_DEVICE_OK) && (instance_id == 1U))
    {
        sample->sequence += 1000U;
        sample->latitude_e7 += 1000;
    }
    return result;
}

SystemDeviceResult ProjectBarometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemBarometerSample *sample)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemBarometer_LatestSampleGet(sample);
}
SystemDeviceResult ProjectMagnetometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemMagnetometer_LatestSampleGet(sample);
}
SystemDeviceResult ProjectAttitudeInstance_LatestSampleGet(
    uint8_t instance_id, SystemHardwareQuaternionSample *sample)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemHardwareQuaternion_LatestSampleGet(sample);
}
SystemDeviceResult ProjectPowerInstance_LatestSampleGet(
    uint8_t instance_id, SystemPowerSample *sample)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemPower_LatestSampleGet(sample);
}

SystemDeviceResult ProjectImuInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemImuConfig *config)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemImu_EffectiveConfigGet(config);
}
SystemDeviceResult ProjectGnssInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemGnssConfig *config)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_EffectiveConfigGet(config);
}
SystemDeviceResult ProjectBarometerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemBarometerConfig *config)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemBarometer_EffectiveConfigGet(config);
}
SystemDeviceResult ProjectMagnetometerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemMagnetometerConfig *config)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemMagnetometer_EffectiveConfigGet(config);
}
SystemDeviceResult ProjectAttitudeInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemHardwareQuaternionConfig *config)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemHardwareQuaternion_EffectiveConfigGet(config);
}
SystemDeviceResult ProjectPowerInstance_EffectiveConfigGet(
    uint8_t instance_id, SystemPowerConfig *config)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemPower_EffectiveConfigGet(config);
}

SystemDeviceResult ProjectGnssInstance_HardwareConfigRead(
    uint8_t instance_id, SystemGnssHardwareConfig *config)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_HardwareConfigRead(config);
}
SystemDeviceResult ProjectGnssInstance_SatelliteDiagnosticsRead(
    uint8_t instance_id, SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_SatelliteDiagnosticsRead(diagnostics);
}
SystemDeviceResult ProjectGnssInstance_RfDiagnosticsRead(
    uint8_t instance_id, SystemGnssRfDiagnostics *diagnostics)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_RfDiagnosticsRead(diagnostics);
}
SystemDeviceResult ProjectImuInstance_IoDetailGet(
    uint8_t instance_id, SystemImuIoDetail *detail)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemImu_IoDetailGet(detail);
}
SystemDeviceResult ProjectGnssInstance_IoDetailGet(
    uint8_t instance_id, SystemGnssIoDetail *detail)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_IoDetailGet(detail);
}
SystemDeviceResult ProjectImuInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemImu_IoDiagnosticsGet(diagnostics);
}
SystemDeviceResult ProjectGnssInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance_id >= 2U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemGnss_IoDiagnosticsGet(diagnostics);
}
SystemDeviceResult ProjectTelemetryInstance_IoDiagnosticsGet(
    uint8_t instance_id, SystemDeviceIoDiagnostics *diagnostics)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemTelemetry_IoDiagnosticsGet(diagnostics);
}
SystemDeviceResult ProjectTelemetryInstance_HealthGet(
    uint8_t instance_id, SystemTelemetryHealth *health)
{
    if (instance_id != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    return SystemTelemetry_HealthGet(health);
}

static SystemDeviceResult Fixture_IoDirectGet(
    const SystemDeviceDescriptor *descriptor,
    SystemDeviceIoDiagnostics *diagnostics)
{
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
    uint16_t index;

    if ((diagnostics == NULL) || (owner_descriptor == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    result = SystemDescriptor_DeviceFind(
        device_class, instance_id, &requested);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    for (index = 0U; index < SystemDescriptor_DeviceCountGet(); index++)
    {
        candidate = s_fixture_devices[index];
        if (candidate.physical_device_id != requested.physical_device_id)
        { continue; }
        result = Fixture_IoDirectGet(&candidate, diagnostics);
        if (result == SYSTEM_DEVICE_OK)
        {
            *owner_descriptor = candidate;
            return SYSTEM_DEVICE_OK;
        }
        if (result != SYSTEM_DEVICE_UNSUPPORTED) { return result; }
    }
    return SYSTEM_DEVICE_UNSUPPORTED;
}
