#include "system_capabilities.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_barometer_if.h"
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
#include "system_console_if.h"
#endif
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#include "system_output_if.h"
#include "system_power_if.h"
#include "system_profile.h"
#include "system_storage_if.h"
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
#include "system_telemetry_transport_if.h"
#endif
#include "target_build_capabilities.h"

static SystemCapabilities s_capabilities;

static uint32_t SystemCapabilities_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemCapabilities_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static uint32_t SystemCapabilities_ProfileMask(const SystemProfile *profile)
{
    return (profile != NULL) ? profile->enabled_capabilities : 0U;
}

static uint8_t SystemCapabilities_DeviceHealthy(
    const SystemDeviceHealth *health)
{
    return (uint8_t)((health->initialized != 0U) &&
                     (health->online != 0U) &&
                     (health->healthy != 0U));
}

static uint8_t SystemCapabilities_OutputHealthy(uint8_t channel_count)
{
    SystemOutputStatus status;
    uint16_t channel;

    if (channel_count == 0U)
    {
        return 0U;
    }
    for (channel = 1U; channel <= channel_count; channel++)
    {
        if ((SystemOutput_StatusGet((uint8_t)channel, &status) !=
             SYSTEM_DEVICE_OK) ||
            (status.state == SYSTEM_OUTPUT_FAULT) ||
            (status.fault != 0U))
        {
            return 0U;
        }
    }
    return 1U;
}

static uint32_t SystemCapabilities_SensorHealthMaskGet(void)
{
    SystemDeviceHealth device_health;
    uint32_t healthy_mask = 0U;

    (void)memset(&device_health, 0, sizeof(device_health));
    SILVERSTAR_ASSERT_OBJECT(&device_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((SystemImu_HealthGet(&device_health) == SYSTEM_DEVICE_OK) &&
        (SystemCapabilities_DeviceHealthy(&device_health) != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_IMU;
    }
    if ((SystemGnss_HealthGet(&device_health) == SYSTEM_DEVICE_OK) &&
        (SystemCapabilities_DeviceHealthy(&device_health) != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_GNSS;
    }
    if ((SystemMagnetometer_HealthGet(&device_health) == SYSTEM_DEVICE_OK) &&
        (SystemCapabilities_DeviceHealthy(&device_health) != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_MAGNETOMETER;
    }
    if ((SystemBarometer_HealthGet(&device_health) == SYSTEM_DEVICE_OK) &&
        (SystemCapabilities_DeviceHealthy(&device_health) != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_BAROMETER;
    }
    if ((SystemHardwareQuaternion_HealthGet(&device_health) ==
         SYSTEM_DEVICE_OK) &&
        (SystemCapabilities_DeviceHealthy(&device_health) != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_HARDWARE_QUATERNION;
    }
    return healthy_mask;
}

static uint32_t SystemCapabilities_ServiceHealthMaskGet(
    uint8_t output_channel_count)
{
    SystemDeviceHealth device_health;
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    SystemTelemetryHealth telemetry_health;
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    SystemConsoleHealth console_health;
#endif
    SystemStorageHealth storage_health;
    uint32_t healthy_mask = 0U;

    (void)memset(&device_health, 0, sizeof(device_health));
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    (void)memset(&telemetry_health, 0, sizeof(telemetry_health));
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    (void)memset(&console_health, 0, sizeof(console_health));
#endif
    (void)memset(&storage_health, 0, sizeof(storage_health));
    SILVERSTAR_ASSERT_OBJECT(&device_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    if ((SystemTelemetry_HealthGet(&telemetry_health) == SYSTEM_DEVICE_OK) &&
        (telemetry_health.initialized != 0U) &&
        (telemetry_health.healthy != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_TELEMETRY;
    }
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    if ((SystemConsoleDevice_HealthGet(&console_health) == SYSTEM_DEVICE_OK) &&
        (console_health.initialized != 0U) && (console_health.healthy != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_CONSOLE;
    }
#endif
    if ((SystemPower_HealthGet(&device_health) == SYSTEM_DEVICE_OK) &&
        (device_health.initialized != 0U) && (device_health.healthy != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_POWER;
    }
    if ((SystemStorage_HealthGet(&storage_health) == SYSTEM_DEVICE_OK) &&
        (storage_health.initialized != 0U) && (storage_health.healthy != 0U))
    {
        healthy_mask |= SYSTEM_CAPABILITY_STORAGE;
    }
    if (SystemCapabilities_OutputHealthy(output_channel_count) != 0U)
    {
        healthy_mask |= SYSTEM_CAPABILITY_OUTPUT;
    }
    return healthy_mask;
}

SystemDeviceResult SystemCapabilities_Refresh(void)
{
    const SystemProfile *profile = SystemProfile_Get();
    SystemCapabilities next;
    uint32_t primask;
    uint32_t healthy_mask;

    if (profile == NULL)
    {
        return SYSTEM_DEVICE_INTERNAL_ERROR;
    }

    SILVERSTAR_ASSERT_OBJECT(profile, SystemProfile,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(&next, 0, sizeof(next));

    next.compiled_mask = TARGET_COMPILED_SYSTEM_CAPABILITIES;
    next.enabled_mask = SystemCapabilities_ProfileMask(profile);
    next.present_mask = next.compiled_mask & next.enabled_mask;
    healthy_mask = SystemCapabilities_SensorHealthMaskGet();
    healthy_mask |= SystemCapabilities_ServiceHealthMaskGet(
        profile->output_channel_count);
    next.healthy_mask = healthy_mask & next.present_mask;
    primask = SystemCapabilities_IrqLock();
    s_capabilities = next;
    SystemCapabilities_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

void SystemCapabilities_Get(SystemCapabilities *capabilities)
{
    uint32_t primask;

    if (capabilities != NULL)
    {
        primask = SystemCapabilities_IrqLock();
        *capabilities = s_capabilities;
        SystemCapabilities_IrqUnlock(primask);
    }
}

uint8_t SystemCapabilities_RequiredAvailable(uint32_t required_mask)
{
    SystemCapabilities capabilities;
    uint32_t available_mask;

    SystemCapabilities_Get(&capabilities);
    available_mask = capabilities.present_mask & capabilities.healthy_mask;

    return (uint8_t)((available_mask & required_mask) == required_mask);
}
