#include <stdarg.h>
#include <stdint.h>
#include <string.h>

#include "debug_log.h"
#include "system_barometer_if.h"
#include "system_console.h"
#include "system_console_if.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_lifecycle.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "system_log_policy.h"
#endif
#include "system_magnetometer_if.h"
#include "system_navigation_profile.h"
#include "system_output_if.h"
#include "system_power_if.h"
#include "system_profile.h"
#include "system_startup.h"
#include "system_storage_if.h"
#include "system_telemetry_transport_if.h"
#include "system_time.h"
#include "system_user_startup_config.h"
#include "test_common.h"

static SystemProfile s_profile;
static SystemNavigationProfile s_navigation;
static SystemDeviceResult s_output_init_result;
static SystemDeviceResult s_output_safe_result;
static SystemDeviceResult s_imu_init_result;
static SystemDeviceResult s_gnss_init_result;
static SystemDeviceResult s_gnss_sample_result;
static uint64_t s_now_us;
static uint32_t s_health_process_count;
static uint32_t s_preflight_count;
static uint32_t s_debug_print_count;
static uint32_t s_imu_apply_count;
static uint32_t s_gnss_apply_count;
static uint32_t s_gnss_verify_count;
static uint32_t s_gnss_capabilities;
static uint32_t s_mag_init_count;
static uint32_t s_imu_process_count;
static uint32_t s_gnss_process_count;
static uint32_t s_imu_init_count;
static uint32_t s_gnss_init_count;
static uint8_t s_async_config;
static uint8_t s_async_busy_ticks;
static uint32_t s_power_process_count;
static uint32_t s_output_process_count;

static SystemDeviceResult Test_InfoFill(SystemDeviceInfo *info,
                                        const char *device_name,
                                        const char *model_name)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = device_name;
    info->model_name = model_name;
    info->driver_version = "test";
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ConfigApply(
    uint32_t requested_mask,
    uint32_t required_mask,
    SystemDeviceConfigReport *report)
{
    if (report == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = requested_mask;
    report->required_mask = required_mask;
    report->supported_mask = requested_mask;
    report->applied_mask = requested_mask;
    report->persisted = 1U;
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ConfigVerify(
    uint32_t requested_mask,
    uint32_t required_mask,
    SystemDeviceConfigReport *report)
{
    SystemDeviceResult result = Test_ConfigApply(
        requested_mask, required_mask, report);

    if (result == SYSTEM_DEVICE_OK)
    {
        report->matched_mask = requested_mask;
        report->applied_mask = 0U;
        report->persisted = 0U;
    }
    return result;
}

const SystemProfile *SystemProfile_Get(void) { return &s_profile; }
const SystemNavigationProfile *SystemNavigationProfile_Get(void)
{ return &s_navigation; }

SystemDeviceResult SystemTime_Init(void)
{
    s_now_us = 0ULL;
    return SYSTEM_DEVICE_OK;
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    s_now_us += 500000ULL;
    return s_now_us;
}

void SystemLifecycle_Init(void) {}
SystemDeviceResult SystemLifecycle_EnterSelfTest(void)
{ return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemLifecycle_EnterPreflight(void)
{
    s_preflight_count++;
    return SYSTEM_DEVICE_OK;
}

void SystemHealth_Init(void) {}
void SystemHealth_Process(void) { s_health_process_count++; }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
void SystemLogPolicy_Init(void) {}
#endif
SystemDeviceResult SystemConsole_Init(void) { return SYSTEM_DEVICE_OK; }
void DebugLog_Init(void) {}
void DebugLog_Print(const char *format, ...)
{
    va_list arguments;

    va_start(arguments, format);
    va_end(arguments);
    s_debug_print_count++;
}

const char *SystemOutput_NameGet(void) { return "Mock Output"; }
SystemDeviceResult SystemOutput_Init(void) { return s_output_init_result; }
SystemDeviceResult SystemOutput_SafeSet(void) { return s_output_safe_result; }
SystemDeviceResult SystemOutput_StatusGet(
    uint8_t channel, SystemOutputStatus *status)
{
    if ((status == NULL) || (channel == 0U) ||
        (channel > s_profile.output_channel_count))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(status, 0, sizeof(*status));
    status->channel = channel;
    status->state = SYSTEM_OUTPUT_SAFE;
    return SYSTEM_DEVICE_OK;
}
void SystemOutput_Process(void) { s_output_process_count++; }

const char *SystemConsoleDevice_NameGet(void) { return "Mock Console"; }
SystemDeviceResult SystemConsoleDevice_Init(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemConsoleDevice_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemConsoleDevice_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock Console Adapter", "Console"); }
SystemDeviceResult SystemConsoleDevice_HealthGet(SystemConsoleHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->started = 1U;
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}
void SystemConsoleDevice_Process(void) {}

const char *SystemImu_NameGet(void) { return "Mock IMU"; }
SystemDeviceResult SystemImu_Init(void)
{ s_imu_init_count++; return s_imu_init_result; }
SystemDeviceResult SystemImu_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemImu_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock IMU Adapter", "Mock IMU"); }
SystemDeviceResult SystemImu_ConfigApply(
    const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_imu_apply_count++;
    if (s_async_config != 0U)
    {
        (void)Test_ConfigApply(config->requested_mask,
            config->required_mask, report);
        report->delegated_mask = report->applied_mask;
        report->applied_mask = 0U;
        report->persisted = 0U;
        return SYSTEM_DEVICE_CONFIG_DELEGATED;
    }
    return Test_ConfigApply(
        config->requested_mask, config->required_mask, report);
}
SystemDeviceResult SystemImu_ConfigVerify(
    const SystemImuConfig *config, SystemDeviceConfigReport *report)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_async_config != 0U) && (s_async_busy_ticks > 0U))
    { s_async_busy_ticks--; return SYSTEM_DEVICE_BUSY; }
    return Test_ConfigVerify(
        config->requested_mask, config->required_mask, report);
}
SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_OK;
}
void SystemImu_Process(void) { s_imu_process_count++; }

const char *SystemGnss_NameGet(void) { return "Mock GNSS"; }
SystemDeviceResult SystemGnss_Init(void)
{ s_gnss_init_count++; return s_gnss_init_result; }
SystemDeviceResult SystemGnss_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemGnss_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock GNSS Adapter", "Mock GNSS"); }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = s_gnss_capabilities;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemGnss_ConfigApply(
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_gnss_capabilities & SYSTEM_GNSS_CAP_READ_ONLY) != 0U)
    { (void)memset(report, 0, sizeof(*report));
      return SYSTEM_DEVICE_CONFIG_NO_ACTION; }
    s_gnss_apply_count++;
    if (s_async_config != 0U)
    {
        (void)Test_ConfigApply(config->requested_mask,
            config->required_mask, report);
        report->delegated_mask = report->applied_mask;
        report->applied_mask = 0U;
        report->persisted = 0U;
        return SYSTEM_DEVICE_CONFIG_DELEGATED;
    }
    return Test_ConfigApply(
        config->requested_mask, config->required_mask, report);
}
SystemDeviceResult SystemGnss_ConfigVerify(
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_gnss_capabilities & SYSTEM_GNSS_CAP_READ_ONLY) != 0U)
    { (void)memset(report, 0, sizeof(*report));
      return SYSTEM_DEVICE_CONFIG_NO_ACTION; }
    s_gnss_verify_count++;
    if ((s_async_config != 0U) && (s_async_busy_ticks > 0U))
    { s_async_busy_ticks--; return SYSTEM_DEVICE_BUSY; }
    return Test_ConfigVerify(
        config->requested_mask, config->required_mask, report);
}
SystemDeviceResult SystemGnss_LastConfigReportGet(
    SystemGnssConfigTransactionReport *report)
{
    if (report == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return s_gnss_sample_result;
}
void SystemGnss_Process(void) { s_gnss_process_count++; }

const char *SystemHardwareQuaternion_NameGet(void)
{ return "Mock Hardware Attitude"; }
SystemDeviceResult SystemHardwareQuaternion_Init(void)
{ return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemHardwareQuaternion_Start(void)
{ return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemHardwareQuaternion_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock Attitude Adapter", "Quaternion"); }
SystemDeviceResult SystemHardwareQuaternion_ConfigApply(
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return Test_ConfigApply(config->requested_mask, 0U, report);
}
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->valid = 1U;
    sample->normalized = 1U;
    return SYSTEM_DEVICE_OK;
}

const char *SystemMagnetometer_NameGet(void) { return "Mock Magnetometer"; }
SystemDeviceResult SystemMagnetometer_Init(void)
{
    s_mag_init_count++;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemMagnetometer_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemMagnetometer_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock Magnetometer Adapter", "Magnetometer"); }
SystemDeviceResult SystemMagnetometer_ConfigApply(
    const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return Test_ConfigApply(config->requested_mask, config->required_mask, report);
}
SystemDeviceResult SystemMagnetometer_LatestSampleGet(
    SystemMagnetometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_OK;
}

const char *SystemBarometer_NameGet(void) { return "Mock Barometer"; }
SystemDeviceResult SystemBarometer_Init(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemBarometer_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemBarometer_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock Barometer Adapter", "Barometer"); }
SystemDeviceResult SystemBarometer_ConfigApply(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    return Test_ConfigApply(config->requested_mask, config->required_mask, report);
}
SystemDeviceResult SystemBarometer_LatestSampleGet(
    SystemBarometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_OK;
}

const char *SystemTelemetry_NameGet(void) { return "Mock Telemetry"; }
SystemDeviceResult SystemTelemetry_Init(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemTelemetry_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemTelemetry_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock Telemetry Adapter", "Telemetry"); }
SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->started = 1U;
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}
void SystemTelemetry_Process(void) {}

const char *SystemPower_NameGet(void) { return "Mock Power"; }
SystemDeviceResult SystemPower_Init(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemPower_Start(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemPower_InfoGet(SystemDeviceInfo *info)
{ return Test_InfoFill(info, "Mock Power Service", "Power"); }
SystemDeviceResult SystemPower_LatestSampleGet(SystemPowerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_OK;
}
void SystemPower_Process(void) { s_power_process_count++; }

const char *SystemStorage_NameGet(void) { return "Mock Storage"; }
SystemDeviceResult SystemStorage_Init(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}

static void Test_Reset(void)
{
    (void)memset(&s_profile, 0, sizeof(s_profile));
    (void)memset(&s_navigation, 0, sizeof(s_navigation));
    s_profile.output_channel_count = 2U;
    s_profile.enabled_capabilities = SYSTEM_CAPABILITY_IMU |
        SYSTEM_CAPABILITY_GNSS | SYSTEM_CAPABILITY_BAROMETER |
        SYSTEM_CAPABILITY_HARDWARE_QUATERNION |
        SYSTEM_CAPABILITY_TELEMETRY | SYSTEM_CAPABILITY_CONSOLE |
        SYSTEM_CAPABILITY_POWER | SYSTEM_CAPABILITY_STORAGE |
        SYSTEM_CAPABILITY_OUTPUT;
    s_profile.required_capabilities = SYSTEM_CAPABILITY_IMU |
                                      SYSTEM_CAPABILITY_OUTPUT;
    s_profile.optional_capabilities = SYSTEM_CAPABILITY_GNSS |
        SYSTEM_CAPABILITY_MAGNETOMETER | SYSTEM_CAPABILITY_BAROMETER |
        SYSTEM_CAPABILITY_HARDWARE_QUATERNION |
        SYSTEM_CAPABILITY_TELEMETRY | SYSTEM_CAPABILITY_CONSOLE |
        SYSTEM_CAPABILITY_POWER | SYSTEM_CAPABILITY_STORAGE;
    s_navigation.alignment_algorithm =
        SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW;
    s_output_init_result = SYSTEM_DEVICE_OK;
    s_output_safe_result = SYSTEM_DEVICE_OK;
    s_imu_init_result = SYSTEM_DEVICE_OK;
    s_gnss_init_result = SYSTEM_DEVICE_OK;
    s_gnss_sample_result = SYSTEM_DEVICE_OK;
    s_health_process_count = 0U;
    s_preflight_count = 0U;
    s_debug_print_count = 0U;
    s_imu_apply_count = 0U;
    s_gnss_apply_count = 0U;
    s_gnss_verify_count = 0U;
    s_gnss_capabilities = 0U;
    s_mag_init_count = 0U;
    s_imu_process_count = 0U;
    s_gnss_process_count = 0U;
    s_imu_init_count = 0U;
    s_gnss_init_count = 0U;
    s_async_config = 0U;
    s_async_busy_ticks = 0U;
    s_power_process_count = 0U;
    s_output_process_count = 0U;
}

static SystemStartupResult Test_StartupComplete(void)
{
    SystemStartupResult result = SystemStartup_Run();
    uint16_t tick;

    if (SystemStartup_ResultIsFatal(result) != 0U) { return result; }
    for (tick = 0U; tick < 256U; tick++)
    {
        if (SystemStartup_GetReport()->completed != 0U) { break; }
        SystemStartup_ProcessDevices();
    }
    if (SystemStartup_GetReport()->completed == 0U)
    { return SYSTEM_STARTUP_STATE_ERROR; }
    if (SystemStartup_GetReport()->mission_capable == 0U)
    { return SYSTEM_STARTUP_MISSION_BLOCKED; }
    return (SystemStartup_GetReport()->degraded != 0U) ?
        SYSTEM_STARTUP_DEGRADED : SYSTEM_STARTUP_OK;
}

static void Test_AllEnabledDevicesPass(void)
{
    const SystemStartupReport *report;
    const SystemStartupDeviceReport *imu;

    Test_Reset();
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_OK);
    report = SystemStartup_GetReport();
    imu = SystemStartup_GetDeviceReport(SYSTEM_STARTUP_DEVICE_IMU);
    TEST_CHECK(report->completed != 0U);
    TEST_CHECK(report->mission_capable != 0U);
    TEST_CHECK(report->degraded == 0U);
    TEST_CHECK(report->required_failure_mask == 0U);
    TEST_CHECK(report->optional_failure_mask == 0U);
    TEST_CHECK(imu != NULL && imu->required != 0U && imu->present != 0U);
    TEST_CHECK(strcmp(imu->device_name, "Mock IMU Adapter") == 0);
    TEST_CHECK(imu->requested_mask == SYSTEM_IMU_CFG_OUTPUT_RATE);
#if SYSTEM_IMU_BOOT_WRITE_CONFIG
    TEST_CHECK(s_imu_apply_count == 1U);
    TEST_CHECK(imu->persist_result == SYSTEM_DEVICE_OK);
#else
    TEST_CHECK(s_imu_apply_count == 0U);
    TEST_CHECK(imu->persist_result == SYSTEM_DEVICE_CONFIG_NO_ACTION);
#endif
    TEST_CHECK(s_mag_init_count == 0U);
    TEST_CHECK(report->devices[SYSTEM_STARTUP_DEVICE_MAGNETOMETER].present == 0U);
    TEST_CHECK(s_preflight_count == 1U && s_health_process_count == 1U);
    TEST_CHECK(s_debug_print_count == (SYSTEM_STARTUP_DEVICE_COUNT + 1U));
}

static void Test_DeviceInitStartsAfterSchedulerTick(void)
{
    uint16_t tick;

    Test_Reset();
    TEST_CHECK(SystemStartup_Run() == SYSTEM_STARTUP_OK);
    TEST_CHECK(SystemStartup_GetReport()->completed == 0U);
    TEST_CHECK(s_imu_init_count == 0U);
    TEST_CHECK(s_gnss_init_count == 0U);
    SystemStartup_ProcessDevices();
    TEST_CHECK(s_imu_init_count == 0U);
    TEST_CHECK(s_gnss_init_count == 0U);
    SystemStartup_ProcessDevices();
    TEST_CHECK(s_imu_init_count == 1U);
    TEST_CHECK(s_gnss_init_count == 0U);
    for (tick = 0U; tick < 32U; tick++)
    {
        if (SystemStartup_GetReport()->completed != 0U) { break; }
        SystemStartup_ProcessDevices();
    }
    TEST_CHECK(SystemStartup_GetReport()->completed != 0U);
    TEST_CHECK(SystemStartup_GetReport()->mission_capable != 0U);
}

static void Test_DelegatedConfigWaitsWithoutBlocking(void)
{
#if (SYSTEM_IMU_BOOT_WRITE_CONFIG != 0U) && \
    (SYSTEM_GNSS_BOOT_WRITE_CONFIG != 0U)
    uint16_t tick;

    Test_Reset();
    s_async_config = 1U;
    s_async_busy_ticks = 6U;
    TEST_CHECK(SystemStartup_Run() == SYSTEM_STARTUP_OK);
    for (tick = 0U; tick < 7U; tick++)
    { SystemStartup_ProcessDevices(); }
    TEST_CHECK(SystemStartup_GetReport()->completed == 0U);
    TEST_CHECK(s_preflight_count == 0U);
    for (tick = 0U; tick < 32U; tick++)
    {
        if (SystemStartup_GetReport()->completed != 0U) { break; }
        SystemStartup_ProcessDevices();
    }
    TEST_CHECK(SystemStartup_GetReport()->completed != 0U);
    TEST_CHECK(SystemStartup_GetReport()->mission_capable != 0U);
    TEST_CHECK(SystemStartup_GetDeviceReport(SYSTEM_STARTUP_DEVICE_IMU)->
        verify_result == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemStartup_GetDeviceReport(SYSTEM_STARTUP_DEVICE_GNSS)->
        verify_result == SYSTEM_DEVICE_OK);
#endif
}

static void Test_OptionalFailureDegrades(void)
{
    const SystemStartupReport *report;

    Test_Reset();
    s_gnss_init_result = SYSTEM_DEVICE_IO_ERROR;
    s_gnss_sample_result = SYSTEM_DEVICE_NOT_READY;
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_DEGRADED);
    report = SystemStartup_GetReport();
    TEST_CHECK(report->mission_capable != 0U);
    TEST_CHECK(report->degraded != 0U);
    TEST_CHECK((report->optional_failure_mask &
                (1UL << SYSTEM_STARTUP_DEVICE_GNSS)) != 0U);
}

static void Test_RequiredFailureBlocks(void)
{
    const SystemStartupReport *report;

    Test_Reset();
    s_imu_init_result = SYSTEM_DEVICE_IO_ERROR;
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_MISSION_BLOCKED);
    report = SystemStartup_GetReport();
    TEST_CHECK(report->mission_capable == 0U);
    TEST_CHECK((report->required_failure_mask &
                (1UL << SYSTEM_STARTUP_DEVICE_IMU)) != 0U);
    TEST_CHECK(SystemStartup_ResultIsFatal(SYSTEM_STARTUP_MISSION_BLOCKED) ==
               0U);
}

static void Test_ProfileCanRequireGnss(void)
{
    Test_Reset();
    s_profile.required_capabilities |= SYSTEM_CAPABILITY_GNSS;
    s_gnss_init_result = SYSTEM_DEVICE_IO_ERROR;
    s_gnss_sample_result = SYSTEM_DEVICE_NOT_READY;
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_MISSION_BLOCKED);
    TEST_CHECK((SystemStartup_GetReport()->required_failure_mask &
                (1UL << SYSTEM_STARTUP_DEVICE_GNSS)) != 0U);
}

static void Test_OutputSafetyFailureIsFatal(void)
{
    Test_Reset();
    s_output_safe_result = SYSTEM_DEVICE_IO_ERROR;
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_OUTPUT_SAFETY_ERROR);
    TEST_CHECK(SystemStartup_ResultIsFatal(
        SYSTEM_STARTUP_OUTPUT_SAFETY_ERROR) != 0U);
    TEST_CHECK(s_preflight_count == 0U);
    TEST_CHECK(s_health_process_count == 0U);
}

static void Test_GnssConfigurationSwitches(void)
{
    const SystemStartupDeviceReport *gnss;

    Test_Reset();
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_OK);
    gnss = SystemStartup_GetDeviceReport(SYSTEM_STARTUP_DEVICE_GNSS);
    TEST_CHECK(gnss != NULL);
#if SYSTEM_GNSS_BOOT_WRITE_CONFIG
    TEST_CHECK(s_gnss_apply_count == 1U);
#if SYSTEM_GNSS_BOOT_VERIFY_CONFIG
    TEST_CHECK(s_gnss_verify_count == 1U);
#else
    TEST_CHECK(s_gnss_verify_count == 0U);
#endif
#else
    TEST_CHECK(s_gnss_apply_count == 0U);
    TEST_CHECK(s_gnss_verify_count == 0U);
    TEST_CHECK(gnss->config_result == SYSTEM_DEVICE_CONFIG_NO_ACTION);
    TEST_CHECK(gnss->verify_result == SYSTEM_DEVICE_CONFIG_NO_ACTION);
#endif
}

static void Test_ReadOnlyGnssNeverConfigured(void)
{
    const SystemStartupDeviceReport *gnss;
    Test_Reset();
    s_gnss_capabilities = SYSTEM_GNSS_CAP_READ_ONLY |
        SYSTEM_GNSS_CAP_POSITION;
    TEST_CHECK(Test_StartupComplete() == SYSTEM_STARTUP_OK);
    gnss = SystemStartup_GetDeviceReport(SYSTEM_STARTUP_DEVICE_GNSS);
    TEST_CHECK(gnss != NULL);
    TEST_CHECK(s_gnss_apply_count == 0U);
    TEST_CHECK(s_gnss_verify_count == 0U);
    TEST_CHECK(gnss->config_result == SYSTEM_DEVICE_CONFIG_NO_ACTION);
    TEST_CHECK(gnss->verify_result == SYSTEM_DEVICE_CONFIG_NO_ACTION);
}

static void Test_ProcessUsesEnabledCapabilities(void)
{
    Test_Reset();
    SystemStartup_ProcessDevices();
    TEST_CHECK(s_imu_process_count == 1U);
    TEST_CHECK(s_gnss_process_count == 1U);
    TEST_CHECK(s_power_process_count == 1U);
    TEST_CHECK(s_output_process_count == 1U);

    s_profile.enabled_capabilities &= ~SYSTEM_CAPABILITY_GNSS;
    SystemStartup_ProcessDevices();
    TEST_CHECK(s_imu_process_count == 2U);
    TEST_CHECK(s_gnss_process_count == 1U);
    TEST_CHECK(s_power_process_count == 2U);
    TEST_CHECK(s_output_process_count == 2U);
}

int main(void)
{
    TEST_CHECK(SystemStartup_DeviceResultIsSuccessful(
        SYSTEM_DEVICE_ALREADY_MATCHED) != 0U);
    TEST_CHECK(SystemStartup_DeviceResultIsSuccessful(
        SYSTEM_DEVICE_CONFIG_DELEGATED) != 0U);
    TEST_CHECK(SystemStartup_DeviceResultIsSuccessful(
        SYSTEM_DEVICE_IO_ERROR) == 0U);
    Test_AllEnabledDevicesPass();
    Test_DeviceInitStartsAfterSchedulerTick();
    Test_DelegatedConfigWaitsWithoutBlocking();
    Test_OptionalFailureDegrades();
    Test_RequiredFailureBlocks();
    Test_ProfileCanRequireGnss();
    Test_OutputSafetyFailureIsFatal();
    Test_GnssConfigurationSwitches();
    Test_ReadOnlyGnssNeverConfigured();
    Test_ProcessUsesEnabledCapabilities();
    TEST_CHECK(SystemStartup_GetDeviceReport(SYSTEM_STARTUP_DEVICE_COUNT) ==
               NULL);
    return Test_Finish("system_startup");
}
