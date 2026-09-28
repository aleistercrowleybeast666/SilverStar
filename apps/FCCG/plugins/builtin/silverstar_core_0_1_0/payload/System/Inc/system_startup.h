#ifndef __SYSTEM_STARTUP_H
#define __SYSTEM_STARTUP_H

#include <stddef.h>
#include <stdint.h>

#include "system_device_types.h"
#include "system_gnss_if.h"

typedef enum
{
    SYSTEM_STARTUP_DEVICE_OUTPUT = 0,
    SYSTEM_STARTUP_DEVICE_IMU,
    SYSTEM_STARTUP_DEVICE_GNSS,
    SYSTEM_STARTUP_DEVICE_MAGNETOMETER,
    SYSTEM_STARTUP_DEVICE_BAROMETER,
    SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION,
    SYSTEM_STARTUP_DEVICE_TELEMETRY,
    SYSTEM_STARTUP_DEVICE_CONSOLE,
    SYSTEM_STARTUP_DEVICE_POWER,
    SYSTEM_STARTUP_DEVICE_STORAGE,
    SYSTEM_STARTUP_DEVICE_COUNT
} SystemStartupDeviceId;

typedef struct
{
    SystemStartupDeviceId device_id;
    const char *device_name;
    const char *model_name;
    uint32_t capability_mask;
    SystemDeviceResult init_result;
    SystemDeviceResult start_result;
    SystemDeviceResult config_result;
    SystemDeviceResult persist_result;
    SystemDeviceResult verify_result;
    SystemDeviceResult communication_result;
    uint32_t requested_mask;
    uint32_t applied_mask;
    uint32_t delegated_mask;
    uint32_t failed_mask;
    uint32_t apply_failed_mask;
    uint32_t persist_failed_mask;
    uint32_t verify_failed_mask;
    uint32_t detail_code;
    uint32_t retry_count;
    uint8_t required;
    uint8_t safety_critical;
    uint8_t present;
} SystemStartupDeviceReport;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t required_failure_mask;
    uint32_t optional_failure_mask;
    uint32_t warning_mask;
    uint8_t device_count;
    uint8_t completed;
    uint8_t passed;
    uint8_t mission_capable;
    uint8_t degraded;
    SystemGnssConfigTransactionReport gnss_config;
    SystemStartupDeviceReport devices[SYSTEM_STARTUP_DEVICE_COUNT];
} SystemStartupReport;

typedef enum
{
    SYSTEM_STARTUP_OK = 0,
    SYSTEM_STARTUP_DEGRADED,
    SYSTEM_STARTUP_MISSION_BLOCKED,
    SYSTEM_STARTUP_TIME_ERROR,
    SYSTEM_STARTUP_STATE_ERROR,
    SYSTEM_STARTUP_OUTPUT_SAFETY_ERROR
} SystemStartupResult;

/*
 * Startup is the authority for interpreting device init/start return values.
 * Logical adapters that share one physical device may legitimately report
 * ALREADY_MATCHED, while delegated/no-action configuration results are also
 * successful outcomes. Keep this policy in one place so composition layers do
 * not reinterpret the enum differently.
 */
static inline uint8_t SystemStartup_DeviceResultIsSuccessful(
    SystemDeviceResult result)
{
    return (uint8_t)((result == SYSTEM_DEVICE_OK) ||
                     (result == SYSTEM_DEVICE_ALREADY_MATCHED) ||
                     (result == SYSTEM_DEVICE_VALUE_ADJUSTED) ||
                     (result == SYSTEM_DEVICE_CONFIG_NO_ACTION) ||
                     (result == SYSTEM_DEVICE_CONFIG_DELEGATED));
}

static inline uint8_t SystemStartup_DeviceReportIsAvailable(
    const SystemStartupDeviceReport *device)
{
    return (uint8_t)((device != NULL) &&
                     (device->present != 0U) &&
                     (SystemStartup_DeviceResultIsSuccessful(
                         device->init_result) != 0U) &&
                     (SystemStartup_DeviceResultIsSuccessful(
                         device->start_result) != 0U));
}

SYSTEM_WARN_UNUSED_RESULT SystemStartupResult SystemStartup_Run(void);
uint8_t SystemStartup_ResultIsFatal(SystemStartupResult result);
const SystemStartupReport *SystemStartup_GetReport(void);
const SystemStartupDeviceReport *SystemStartup_GetDeviceReport(
    SystemStartupDeviceId device_id);
void SystemStartup_ProcessDevices(void);

#endif /* __SYSTEM_STARTUP_H */
