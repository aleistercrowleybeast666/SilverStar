#include "system_startup.h"

#include <stddef.h>
#include <string.h>

#include "debug_log.h"
#include "silverstar_assert.h"
#include "system_barometer_if.h"
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
#include "system_console.h"
#include "system_console_if.h"
#endif
#include "system_gnss_if.h"
#include "system_health.h"
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
#include "system_storage_if.h"
#include "system_telemetry_transport_if.h"
#include "system_time.h"
#include "system_user_config.h"
#include "system_user_startup_config.h"

#define SYSTEM_STARTUP_COMMUNICATION_TIMEOUT_US 2000000ULL
#define SYSTEM_STARTUP_CONFIGURATION_TIMEOUT_US 120000000ULL

typedef enum
{
    SystemStartupPhase_Idle = 0,
    SystemStartupPhase_Console,
    SystemStartupPhase_LogicalStart,
    SystemStartupPhase_LogicalConfig,
    SystemStartupPhase_ImuConfig,
    SystemStartupPhase_GnssStart,
    SystemStartupPhase_OtherAdapters,
    SystemStartupPhase_WaitConfig,
    SystemStartupPhase_WaitCommunication,
    SystemStartupPhase_Complete
} SystemStartupPhase;

static SystemStartupReport s_startup_report;
static SystemStartupPhase s_startup_phase;
static uint64_t s_phase_started_us;

static uint8_t SystemStartup_CapabilityEnabled(uint32_t capability_mask)
{
    const SystemProfile *profile = SystemProfile_Get();

    return (uint8_t)((profile != NULL) &&
        ((profile->enabled_capabilities & capability_mask) != 0U));
}

static void SystemStartup_DeviceReset(SystemStartupDeviceReport *device,
                                      SystemStartupDeviceId device_id,
                                      uint32_t capability_mask,
                                      uint8_t safety_critical)
{
    const SystemProfile *profile = SystemProfile_Get();

    if (device == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(device, SystemStartupDeviceReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(device, 0, sizeof(*device));
    device->device_id = device_id;
    device->device_name = "NONE";
    device->model_name = "NONE";
    device->capability_mask = capability_mask;
    device->required = (uint8_t)((profile != NULL) &&
        ((profile->required_capabilities & capability_mask) != 0U));
    device->safety_critical = safety_critical;
    device->init_result = SYSTEM_DEVICE_NOT_EXECUTED;
    device->start_result = SYSTEM_DEVICE_NOT_EXECUTED;
    device->config_result = SYSTEM_DEVICE_NOT_EXECUTED;
    device->persist_result = SYSTEM_DEVICE_NOT_EXECUTED;
    device->verify_result = SYSTEM_DEVICE_NOT_EXECUTED;
    device->communication_result = SYSTEM_DEVICE_NOT_EXECUTED;
}

static void SystemStartup_ReportReset(void)
{
    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(&s_startup_report, 0, sizeof(s_startup_report));
    s_startup_report.gnss_config.uart_baudrate_result =
        SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.uart_settle_result =
        SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.protocol_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.nav_pvt_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.rate_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.dynamic_model_result =
        SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.signals_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.pvt_recovery_result =
        SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.verify_result = SYSTEM_DEVICE_NOT_EXECUTED;
    s_startup_report.gnss_config.verify_read_result =
        SYSTEM_GNSS_CONFIG_READ_NOT_READY;
    s_startup_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_OUTPUT],
        SYSTEM_STARTUP_DEVICE_OUTPUT, SYSTEM_CAPABILITY_OUTPUT, 1U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU],
        SYSTEM_STARTUP_DEVICE_IMU, SYSTEM_CAPABILITY_IMU, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS],
        SYSTEM_STARTUP_DEVICE_GNSS, SYSTEM_CAPABILITY_GNSS, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_MAGNETOMETER],
        SYSTEM_STARTUP_DEVICE_MAGNETOMETER, SYSTEM_CAPABILITY_MAGNETOMETER, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER],
        SYSTEM_STARTUP_DEVICE_BAROMETER, SYSTEM_CAPABILITY_BAROMETER, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION],
        SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION,
        SYSTEM_CAPABILITY_HARDWARE_QUATERNION, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_TELEMETRY],
        SYSTEM_STARTUP_DEVICE_TELEMETRY, SYSTEM_CAPABILITY_TELEMETRY, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_CONSOLE],
        SYSTEM_STARTUP_DEVICE_CONSOLE, SYSTEM_CAPABILITY_CONSOLE, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_POWER],
        SYSTEM_STARTUP_DEVICE_POWER, SYSTEM_CAPABILITY_POWER, 0U);
    SystemStartup_DeviceReset(&s_startup_report.devices[SYSTEM_STARTUP_DEVICE_STORAGE],
        SYSTEM_STARTUP_DEVICE_STORAGE, SYSTEM_CAPABILITY_STORAGE, 0U);
}

static void SystemStartup_InfoCapture(SystemStartupDeviceReport *device,
                                      const char *fallback_name,
                                      SystemDeviceResult info_result,
                                      const SystemDeviceInfo *info)
{
    device->present = 1U;
    device->device_name = fallback_name;
    if ((info_result == SYSTEM_DEVICE_OK) && (info != NULL))
    {
        if (info->device_name != NULL) { device->device_name = info->device_name; }
        if (info->model_name != NULL) { device->model_name = info->model_name; }
    }
}

static void SystemStartup_ConfigCapture(SystemStartupDeviceReport *device,
                                        SystemDeviceResult result,
                                        const SystemDeviceConfigReport *report)
{
    if (device == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(device, SystemStartupDeviceReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    device->config_result = result;
    if (report == NULL) { return; }
    device->requested_mask = report->requested_mask;
    device->applied_mask = report->applied_mask;
    device->delegated_mask = report->delegated_mask;
    device->apply_failed_mask = report->failed_mask |
                                report->verify_failed_mask |
                                report->unsupported_required_mask;
    device->failed_mask = device->apply_failed_mask |
                          device->persist_failed_mask |
                          device->verify_failed_mask;
    device->detail_code = report->detail_code;
    device->retry_count = report->retry_count;
    if ((report->persisted != 0U) &&
        (SystemStartup_DeviceResultIsSuccessful(result) != 0U))
    {
        device->persist_result = SYSTEM_DEVICE_OK;
        device->persist_failed_mask = 0U;
    }
}

static void SystemStartup_OutputStart(void)
{
    SystemStartupDeviceReport *device =
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_OUTPUT];
    SystemOutputStatus status;
    uint8_t channel;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_OUTPUT) == 0U)
    {
        return;
    }

    device->present = 1U;
    device->device_name = SystemOutput_NameGet();
    device->model_name = "Profile Output";
    device->init_result = SystemOutput_Init();
    if (SystemStartup_DeviceResultIsSuccessful(device->init_result) == 0U) { return; }
    device->start_result = SystemOutput_SafeSet();
    device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    device->verify_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    if (SystemStartup_DeviceResultIsSuccessful(device->start_result) == 0U) { return; }
    device->communication_result = SYSTEM_DEVICE_OK;
    for (channel = 1U; channel <= SystemProfile_Get()->output_channel_count; channel++)
    {
        if ((SystemOutput_StatusGet(channel, &status) != SYSTEM_DEVICE_OK) ||
            (status.state != SYSTEM_OUTPUT_SAFE) ||
            (status.physical_active != 0U) || (status.fault != 0U))
        {
            device->communication_result = SYSTEM_DEVICE_VERIFY_FAILED;
            break;
        }
    }
}

#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
static void SystemStartup_ConsoleStart(void)
{
    SystemStartupDeviceReport *device =
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_CONSOLE];
    SystemDeviceInfo info;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_CONSOLE) == 0U)
    {
        return;
    }

    (void)memset(&info, 0, sizeof(info));
    device->init_result = SystemConsoleDevice_Init();
    SystemStartup_InfoCapture(device, SystemConsoleDevice_NameGet(),
        SystemConsoleDevice_InfoGet(&info), &info);
    if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
    {
        device->start_result = SystemConsoleDevice_Start();
    }
    device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    device->verify_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    if ((SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U) &&
        (SystemStartup_DeviceResultIsSuccessful(device->start_result) != 0U))
    {
        device->communication_result = SystemConsole_Init();
        DebugLog_Init();
    }
}
#endif

static void SystemStartup_JyLogicalStart(void)
{
    SystemStartupDeviceReport *device;
    SystemDeviceInfo info;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU];
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_IMU) != 0U)
    {
        (void)memset(&info, 0, sizeof(info));
        device->init_result = SystemImu_Init();
        SystemStartup_InfoCapture(device, SystemImu_NameGet(),
                                  SystemImu_InfoGet(&info), &info);
        if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
        {
            device->start_result = SystemImu_Start();
        }
    }

    device = &s_startup_report.devices[
        SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION];
    if (SystemStartup_CapabilityEnabled(
            SYSTEM_CAPABILITY_HARDWARE_QUATERNION) != 0U)
    {
        (void)memset(&info, 0, sizeof(info));
        device->init_result = SystemHardwareQuaternion_Init();
        SystemStartup_InfoCapture(device, SystemHardwareQuaternion_NameGet(),
            SystemHardwareQuaternion_InfoGet(&info), &info);
        if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
        {
            device->start_result = SystemHardwareQuaternion_Start();
        }
    }

    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_MAGNETOMETER];
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_MAGNETOMETER) != 0U)
    {
        (void)memset(&info, 0, sizeof(info));
        device->init_result = SystemMagnetometer_Init();
        SystemStartup_InfoCapture(device, SystemMagnetometer_NameGet(),
                                  SystemMagnetometer_InfoGet(&info), &info);
        if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
        {
            device->start_result = SystemMagnetometer_Start();
        }
    }

    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER];
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_BAROMETER) != 0U)
    {
        (void)memset(&info, 0, sizeof(info));
        device->init_result = SystemBarometer_Init();
        SystemStartup_InfoCapture(device, SystemBarometer_NameGet(),
                                  SystemBarometer_InfoGet(&info), &info);
        if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
        {
            device->start_result = SystemBarometer_Start();
        }
    }
}

static void SystemStartup_JyLogicalConfig(void)
{
    SystemDeviceConfigReport report;
    SystemStartupDeviceReport *device;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION];
    if (SystemStartup_DeviceResultIsSuccessful(device->start_result) != 0U)
    {
        SystemHardwareQuaternionConfig config;
        (void)memset(&config, 0, sizeof(config));
        config.requested_mask = SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
        config.mode = (SystemNavigationProfile_Get()->alignment_algorithm ==
                       SYSTEM_ALIGNMENT_HW_QUAT_9AXIS) ?
            SYSTEM_HW_QUAT_MODE_9AXIS : SYSTEM_HW_QUAT_MODE_6AXIS;
        config.output_rate_hz = SYSTEM_HARDWARE_QUATERNION_OUTPUT_RATE_HZ;
        (void)memset(&report, 0, sizeof(report));
        result = SystemHardwareQuaternion_ConfigApply(&config, &report);
        SystemStartup_ConfigCapture(device, result, &report);
        device->persist_result = SYSTEM_DEVICE_CONFIG_DELEGATED;
        device->verify_result = SYSTEM_DEVICE_NOT_EXECUTED;
    }

    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_MAGNETOMETER];
    if (SystemStartup_DeviceResultIsSuccessful(device->start_result) != 0U)
    {
        SystemMagnetometerConfig config;
        (void)memset(&config, 0, sizeof(config));
        config.requested_mask = SYSTEM_MAG_CFG_OUTPUT_RATE;
        config.output_rate_hz = SYSTEM_MAGNETOMETER_OUTPUT_RATE_HZ;
        (void)memset(&report, 0, sizeof(report));
        result = SystemMagnetometer_ConfigApply(&config, &report);
        SystemStartup_ConfigCapture(device, result, &report);
        device->persist_result = SYSTEM_DEVICE_CONFIG_DELEGATED;
        device->verify_result = SYSTEM_DEVICE_NOT_EXECUTED;
    }

    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER];
    if (SystemStartup_DeviceResultIsSuccessful(device->start_result) != 0U)
    {
        SystemBarometerConfig config;
        (void)memset(&config, 0, sizeof(config));
        config.requested_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
        config.output_rate_hz = SYSTEM_BAROMETER_OUTPUT_RATE_HZ;
        (void)memset(&report, 0, sizeof(report));
        result = SystemBarometer_ConfigApply(&config, &report);
        SystemStartup_ConfigCapture(device, result, &report);
        device->persist_result = SYSTEM_DEVICE_CONFIG_DELEGATED;
        device->verify_result = SYSTEM_DEVICE_NOT_EXECUTED;
    }
}

static void SystemStartup_ImuConfig(void)
{
    SystemStartupDeviceReport *device =
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU];
    SystemImuConfig config;
    SystemDeviceConfigReport report;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemStartup_DeviceResultIsSuccessful(device->start_result) == 0U)
    {
        return;
    }
    (void)memset(&config, 0, sizeof(config));
    config.requested_mask = SYSTEM_IMU_CFG_OUTPUT_RATE;
    config.required_mask = SYSTEM_IMU_CFG_OUTPUT_RATE;
    config.output_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ;
    device->requested_mask = config.requested_mask;
    if (SYSTEM_IMU_BOOT_WRITE_CONFIG != 0U)
    {
        (void)memset(&report, 0, sizeof(report));
        result = SystemImu_ConfigApply(&config, &report);
        SystemStartup_ConfigCapture(device, result, &report);
        if ((device->persist_result == SYSTEM_DEVICE_NOT_EXECUTED) &&
            (SystemStartup_DeviceResultIsSuccessful(result) != 0U))
        {
            /* Successful volatile configuration is not a persistence request.
               ConfigVerify below still checks the effective device values. */
            device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        }
    }
    else
    {
        device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }
    if ((SYSTEM_IMU_BOOT_VERIFY_CONFIG != 0U) &&
        (device->config_result != SYSTEM_DEVICE_CONFIG_DELEGATED))
    {
        (void)memset(&report, 0, sizeof(report));
        result = SystemImu_ConfigVerify(&config, &report);
        device->verify_result = result;
        device->verify_failed_mask = report.failed_mask |
                                     report.verify_failed_mask;
        device->failed_mask = device->apply_failed_mask |
                              device->persist_failed_mask |
                              device->verify_failed_mask;
        device->detail_code = report.detail_code;
        device->retry_count += report.retry_count;
    }
    else
    {
        device->verify_result =
            (device->config_result == SYSTEM_DEVICE_CONFIG_DELEGATED) ?
            SYSTEM_DEVICE_NOT_EXECUTED : SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }
}

static void SystemStartup_GnssConfigGet(SystemGnssConfig *config)
{
    if (config == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_GNSS_CFG_NAVIGATION_RATE |
        SYSTEM_GNSS_CFG_CONSTELLATIONS | SYSTEM_GNSS_CFG_DYNAMIC_MODEL |
        SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL | SYSTEM_GNSS_CFG_ENABLED_MESSAGES;
    config->required_mask = SYSTEM_GNSS_CFG_NAVIGATION_RATE |
        SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL | SYSTEM_GNSS_CFG_ENABLED_MESSAGES;
    config->navigation_rate_hz = SYSTEM_GNSS_NAVIGATION_RATE_HZ;
    config->constellation_mask = SYSTEM_GNSS_CONSTELLATION_MASK;
    config->dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL;
    config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL;
    config->enabled_message_mask = SYSTEM_GNSS_ENABLED_MESSAGE_MASK;
}

static void SystemStartup_GnssConfigExecute(
    SystemStartupDeviceReport *device,
    const SystemGnssConfig *config)
{
    SystemDeviceConfigReport report;
    SystemDeviceResult result;

    if ((device == NULL) || (config == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(device, SystemStartupDeviceReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    device->requested_mask = config->requested_mask;
    if (SYSTEM_GNSS_BOOT_WRITE_CONFIG == 0U)
    {
        device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->verify_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        return;
    }
    (void)memset(&report, 0, sizeof(report));
    result = SystemGnss_ConfigApply(config, &report);
    SystemStartup_ConfigCapture(device, result, &report);
    if ((device->persist_result == SYSTEM_DEVICE_NOT_EXECUTED) &&
        (SystemStartup_DeviceResultIsSuccessful(result) != 0U))
    {
        /* Boot initializes RAM. Explicit Save owns BBR/Flash transactions. */
        device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }
    if ((SYSTEM_GNSS_BOOT_VERIFY_CONFIG != 0U) &&
        (device->config_result != SYSTEM_DEVICE_CONFIG_DELEGATED))
    {
        (void)memset(&report, 0, sizeof(report));
        result = SystemGnss_ConfigVerify(config, &report);
        device->verify_result = result;
        device->verify_failed_mask = report.failed_mask |
                                     report.verify_failed_mask;
        device->failed_mask = device->apply_failed_mask |
                              device->persist_failed_mask |
                              device->verify_failed_mask;
        device->detail_code = report.detail_code;
        device->retry_count += report.retry_count;
    }
    else
    {
        device->verify_result =
            (device->config_result == SYSTEM_DEVICE_CONFIG_DELEGATED) ?
            SYSTEM_DEVICE_NOT_EXECUTED : SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }
    (void)SystemGnss_LastConfigReportGet(&s_startup_report.gnss_config);
}

static void SystemStartup_GnssStart(void)
{
    SystemStartupDeviceReport *device =
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS];
    SystemDeviceInfo info;
    SystemGnssConfig config;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_GNSS) == 0U)
    {
        return;
    }

    (void)memset(&info, 0, sizeof(info));
    device->init_result = SystemGnss_Init();
    SystemStartup_InfoCapture(device, SystemGnss_NameGet(),
                              SystemGnss_InfoGet(&info), &info);
    if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
    {
        device->start_result = SystemGnss_Start();
    }
    if (SystemStartup_DeviceResultIsSuccessful(device->start_result) == 0U) { return; }
    SystemStartup_GnssConfigGet(&config);
    SystemStartup_GnssConfigExecute(device, &config);
}

static void SystemStartup_OtherAdaptersStart(void)
{
    SystemStartupDeviceReport *device;
    SystemDeviceInfo info;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_TELEMETRY];
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_TELEMETRY) != 0U)
    {
        (void)memset(&info, 0, sizeof(info));
        device->init_result = SystemTelemetry_Init();
        SystemStartup_InfoCapture(device, SystemTelemetry_NameGet(),
                                  SystemTelemetry_InfoGet(&info), &info);
        if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
        {
            device->start_result = SystemTelemetry_Start();
        }
        if (SYSTEM_TELEMETRY_BOOT_WRITE_CONFIG != 0U)
        {
            device->requested_mask = 1UL;
            device->config_result = device->start_result;
            device->applied_mask =
                (SystemStartup_DeviceResultIsSuccessful(
                    device->start_result) != 0U) ? 1UL : 0UL;
        }
        else
        {
            device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        }
        device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->verify_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }
#endif

    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_POWER];
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_POWER) != 0U)
    {
        (void)memset(&info, 0, sizeof(info));
        device->init_result = SystemPower_Init();
        SystemStartup_InfoCapture(device, SystemPower_NameGet(),
                                  SystemPower_InfoGet(&info), &info);
        if (SystemStartup_DeviceResultIsSuccessful(device->init_result) != 0U)
        {
            device->start_result = SystemPower_Start();
        }
        device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->verify_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }

    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_STORAGE];
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_STORAGE) != 0U)
    {
        device->present = 1U;
        device->device_name = SystemStorage_NameGet();
        device->model_name = SystemStorage_NameGet();
        device->init_result = SystemStorage_Init();
        device->start_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->config_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->persist_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
        device->verify_result = SYSTEM_DEVICE_CONFIG_NO_ACTION;
    }
}

static void SystemStartup_CommunicationProcess(void)
{
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_IMU) != 0U)
    { SystemImu_Process(); }
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_GNSS) != 0U)
    { SystemGnss_Process(); }
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_TELEMETRY) != 0U)
    { SystemTelemetry_Process(); }
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_CONSOLE) != 0U)
    { SystemConsoleDevice_Process(); }
#endif
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_POWER) != 0U)
    { SystemPower_Process(); }
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_OUTPUT) != 0U)
    { SystemOutput_Process(); }
}

static void SystemStartup_SensorCommunicationEvaluate(void)
{
    SystemStartupDeviceReport *device;
    SystemImuSample imu_sample;
    SystemGnssSample gnss_sample;
    SystemMagnetometerSample mag_sample;
    SystemBarometerSample baro_sample;
    SystemHardwareQuaternionSample quaternion_sample;
    SystemPowerSample power_sample;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_IMU) != 0U) &&
        (SystemImu_LatestSampleGet(&imu_sample) == SYSTEM_DEVICE_OK))
    { device->communication_result = SYSTEM_DEVICE_OK; }
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_GNSS) != 0U) &&
        (SystemGnss_LatestSampleGet(&gnss_sample) == SYSTEM_DEVICE_OK))
    { device->communication_result = SYSTEM_DEVICE_OK; }
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_MAGNETOMETER];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_MAGNETOMETER) != 0U) &&
        (SystemMagnetometer_LatestSampleGet(&mag_sample) == SYSTEM_DEVICE_OK))
    { device->communication_result = SYSTEM_DEVICE_OK; }
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_BAROMETER) != 0U) &&
        (SystemBarometer_LatestSampleGet(&baro_sample) == SYSTEM_DEVICE_OK))
    { device->communication_result = SYSTEM_DEVICE_OK; }
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION];
    if ((SystemStartup_CapabilityEnabled(
             SYSTEM_CAPABILITY_HARDWARE_QUATERNION) != 0U) &&
        (SystemHardwareQuaternion_LatestSampleGet(&quaternion_sample) ==
         SYSTEM_DEVICE_OK))
    { device->communication_result = SYSTEM_DEVICE_OK; }
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_POWER];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_POWER) != 0U) &&
        (SystemPower_LatestSampleGet(&power_sample) == SYSTEM_DEVICE_OK))
    { device->communication_result = SYSTEM_DEVICE_OK; }
}

static void SystemStartup_ServiceCommunicationEvaluate(void)
{
    SystemStartupDeviceReport *device;
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    SystemTelemetryHealth telemetry_health;
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    SystemConsoleHealth console_health;
#endif
    SystemStorageHealth storage_health;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
#if (SILVERSTAR_PROTOCOL_TELEMETRY_ENABLED != 0U)
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_TELEMETRY];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_TELEMETRY) != 0U) &&
        (SystemTelemetry_HealthGet(&telemetry_health) == SYSTEM_DEVICE_OK) &&
        (telemetry_health.initialized != 0U) &&
        (telemetry_health.started != 0U) && (telemetry_health.healthy != 0U))
    { device->communication_result = SYSTEM_DEVICE_OK; }
#endif
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_CONSOLE];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_CONSOLE) != 0U) &&
        (SystemConsoleDevice_HealthGet(&console_health) == SYSTEM_DEVICE_OK) &&
        (console_health.initialized != 0U) &&
        (console_health.started != 0U) && (console_health.healthy != 0U))
    { device->communication_result = SYSTEM_DEVICE_OK; }
#endif
    device = &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_STORAGE];
    if ((SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_STORAGE) != 0U) &&
        (SystemStorage_HealthGet(&storage_health) == SYSTEM_DEVICE_OK) &&
        (storage_health.initialized != 0U))
    { device->communication_result = SYSTEM_DEVICE_OK; }
}

static uint8_t SystemStartup_CommunicationEvaluate(void)
{
    SystemStartupDeviceReport *device;
    uint8_t pending = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemStartup_CommunicationProcess();
    SystemStartup_SensorCommunicationEvaluate();
    SystemStartup_ServiceCommunicationEvaluate();
    for (device = &s_startup_report.devices[0];
         device < &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_COUNT]; device++)
    {
        if ((device->present != 0U) &&
            (device->communication_result == SYSTEM_DEVICE_NOT_EXECUTED))
        { pending = 1U; }
    }
    return pending;
}

static uint8_t SystemStartup_DeviceFailed(const SystemStartupDeviceReport *device)
{
    const SystemDeviceResult results[] =
    {
        device->init_result, device->start_result, device->config_result,
        device->persist_result, device->verify_result,
        device->communication_result
    };
    uint8_t index;

    if (device == NULL) { return 1U; }
    SILVERSTAR_ASSERT_OBJECT(device, SystemStartupDeviceReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemStartup_CapabilityEnabled(device->capability_mask) == 0U)
    {
        return 0U;
    }
    if (device->present == 0U) { return 1U; }
    for (index = 0U; index < (uint8_t)(sizeof(results) / sizeof(results[0])); index++)
    {
        if ((results[index] != SYSTEM_DEVICE_NOT_EXECUTED) &&
            (SystemStartup_DeviceResultIsSuccessful(results[index]) == 0U))
        {
            return 1U;
        }
    }
    return 0U;
}

static void SystemStartup_ReportFinalize(void)
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < SYSTEM_STARTUP_DEVICE_COUNT; index++)
    {
        SystemStartupDeviceReport *device = &s_startup_report.devices[index];
        uint32_t bit = 1UL << index;
        if (SystemStartup_DeviceFailed(device) == 0U) { continue; }
        if ((device->required != 0U) || (device->safety_critical != 0U))
        { s_startup_report.required_failure_mask |= bit; }
        else
        { s_startup_report.optional_failure_mask |= bit; }
    }
    s_startup_report.warning_mask = s_startup_report.optional_failure_mask;
    s_startup_report.mission_capable =
        (s_startup_report.required_failure_mask == 0U) ? 1U : 0U;
    s_startup_report.passed = s_startup_report.mission_capable;
    s_startup_report.degraded =
        (s_startup_report.optional_failure_mask != 0U) ? 1U : 0U;
    s_startup_report.timestamp_us = SystemTime_GetMonotonicUs();
    /* Publish completion only after every report field is final. */
    s_startup_report.completed = 1U;
}

static void SystemStartup_ReportPrint(void)
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    DebugLog_Print("STARTUP completed=%u passed=%u mission_capable=%u degraded=%u required=0x%08lX optional=0x%08lX warnings=0x%08lX",
        (unsigned int)s_startup_report.completed,
        (unsigned int)s_startup_report.passed,
        (unsigned int)s_startup_report.mission_capable,
        (unsigned int)s_startup_report.degraded,
        (unsigned long)s_startup_report.required_failure_mask,
        (unsigned long)s_startup_report.optional_failure_mask,
        (unsigned long)s_startup_report.warning_mask);
    for (index = 0U; index < SYSTEM_STARTUP_DEVICE_COUNT; index++)
    {
        const SystemStartupDeviceReport *device = &s_startup_report.devices[index];
        DebugLog_Print("STARTUP device=%u name=%s model=%s required=%u init=%u start=%u config=%u persist=%u verify=%u comm=%u requested=0x%08lX applied=0x%08lX delegated=0x%08lX failed=0x%08lX apply_failed=0x%08lX persist_failed=0x%08lX verify_failed=0x%08lX detail=%lu retry=%lu",
            (unsigned int)device->device_id, device->device_name,
            device->model_name, (unsigned int)device->required,
            (unsigned int)device->init_result, (unsigned int)device->start_result,
            (unsigned int)device->config_result, (unsigned int)device->persist_result,
            (unsigned int)device->verify_result,
            (unsigned int)device->communication_result,
            (unsigned long)device->requested_mask,
            (unsigned long)device->applied_mask,
            (unsigned long)device->delegated_mask,
            (unsigned long)device->failed_mask,
            (unsigned long)device->apply_failed_mask,
            (unsigned long)device->persist_failed_mask,
            (unsigned long)device->verify_failed_mask,
            (unsigned long)device->detail_code,
            (unsigned long)device->retry_count);
    }
}

static uint8_t SystemStartup_ConfigVerifyPending(void)
{
    SystemStartupDeviceReport *imu =
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU];
    SystemStartupDeviceReport *gnss =
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS];
    SystemDeviceConfigReport report;
    SystemDeviceResult result;

    if ((imu->config_result == SYSTEM_DEVICE_CONFIG_DELEGATED) &&
        (imu->verify_result == SYSTEM_DEVICE_NOT_EXECUTED))
    {
        SystemImuConfig config;
        (void)memset(&config, 0, sizeof(config));
        config.requested_mask = SYSTEM_IMU_CFG_OUTPUT_RATE;
        config.required_mask = SYSTEM_IMU_CFG_OUTPUT_RATE;
        config.output_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ;
        (void)memset(&report, 0, sizeof(report));
        result = SystemImu_ConfigVerify(&config, &report);
        if (result != SYSTEM_DEVICE_BUSY)
        {
            imu->verify_result = result;
            imu->verify_failed_mask = report.failed_mask |
                                      report.verify_failed_mask;
            imu->failed_mask |= imu->verify_failed_mask;
            imu->applied_mask = report.applied_mask;
            imu->detail_code = report.detail_code;
        }
    }
    if ((gnss->config_result == SYSTEM_DEVICE_CONFIG_DELEGATED) &&
        (gnss->verify_result == SYSTEM_DEVICE_NOT_EXECUTED))
    {
        SystemGnssConfig config;
        SystemStartup_GnssConfigGet(&config);
        (void)memset(&report, 0, sizeof(report));
        result = SystemGnss_ConfigVerify(&config, &report);
        if (result != SYSTEM_DEVICE_BUSY)
        {
            gnss->verify_result = result;
            gnss->verify_failed_mask = report.failed_mask |
                                       report.verify_failed_mask;
            gnss->failed_mask |= gnss->verify_failed_mask;
            gnss->applied_mask = report.applied_mask;
            gnss->detail_code = report.detail_code;
            (void)SystemGnss_LastConfigReportGet(&s_startup_report.gnss_config);
        }
    }
    return (uint8_t)(
        ((imu->config_result == SYSTEM_DEVICE_CONFIG_DELEGATED) &&
         (imu->verify_result == SYSTEM_DEVICE_NOT_EXECUTED)) ||
        ((gnss->config_result == SYSTEM_DEVICE_CONFIG_DELEGATED) &&
         (gnss->verify_result == SYSTEM_DEVICE_NOT_EXECUTED)));
}

static void SystemStartup_TimeoutMark(void)
{
    SystemStartupDeviceReport *device;

    for (device = &s_startup_report.devices[0];
         device < &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_COUNT];
         device++)
    {
        if ((device->present != 0U) &&
            (device->communication_result == SYSTEM_DEVICE_NOT_EXECUTED))
        { device->communication_result = SYSTEM_DEVICE_TIMEOUT; }
    }
}

SystemStartupResult SystemStartup_Run(void)
{
    SILVERSTAR_ASSERT_OBJECT(&s_startup_report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    s_startup_phase = SystemStartupPhase_Idle;
    SystemStartup_ReportReset();
    if (SystemTime_Init() != SYSTEM_DEVICE_OK) { return SYSTEM_STARTUP_TIME_ERROR; }
    SystemLifecycle_Init();
    SystemHealth_Init();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemLogPolicy_Init();
#endif
    if (SystemLifecycle_EnterSelfTest() != SYSTEM_DEVICE_OK)
    { return SYSTEM_STARTUP_STATE_ERROR; }

    SystemStartup_OutputStart();
    if (SystemStartup_DeviceFailed(
        &s_startup_report.devices[SYSTEM_STARTUP_DEVICE_OUTPUT]) != 0U)
    {
        SystemStartup_ReportFinalize();
        return SYSTEM_STARTUP_OUTPUT_SAFETY_ERROR;
    }
    s_startup_phase = SystemStartupPhase_Console;
    return SYSTEM_STARTUP_OK;
}

uint8_t SystemStartup_ResultIsFatal(SystemStartupResult result)
{
    return (uint8_t)((result == SYSTEM_STARTUP_TIME_ERROR) ||
                     (result == SYSTEM_STARTUP_STATE_ERROR) ||
                     (result == SYSTEM_STARTUP_OUTPUT_SAFETY_ERROR));
}

const SystemStartupReport *SystemStartup_GetReport(void)
{
    return &s_startup_report;
}

const SystemStartupDeviceReport *SystemStartup_GetDeviceReport(
    SystemStartupDeviceId device_id)
{
    if (device_id >= SYSTEM_STARTUP_DEVICE_COUNT) { return NULL; }
    return &s_startup_report.devices[device_id];
}

void SystemStartup_ProcessDevices(void)
{
    uint64_t now_us;

    switch (s_startup_phase)
    {
        case SystemStartupPhase_Console:
#if (SILVERSTAR_PROTOCOL_MAINTENANCE_ENABLED != 0U)
            SystemStartup_ConsoleStart();
#endif
            s_startup_phase = SystemStartupPhase_LogicalStart;
            return;
        case SystemStartupPhase_LogicalStart:
            SystemStartup_JyLogicalStart();
            s_startup_phase = SystemStartupPhase_LogicalConfig;
            return;
        case SystemStartupPhase_LogicalConfig:
            SystemStartup_JyLogicalConfig();
            s_startup_phase = SystemStartupPhase_ImuConfig;
            return;
        case SystemStartupPhase_ImuConfig:
            SystemStartup_ImuConfig();
            s_startup_phase = SystemStartupPhase_GnssStart;
            return;
        case SystemStartupPhase_GnssStart:
            SystemStartup_GnssStart();
            s_startup_phase = SystemStartupPhase_OtherAdapters;
            return;
        case SystemStartupPhase_OtherAdapters:
            SystemStartup_OtherAdaptersStart();
            s_phase_started_us = SystemTime_GetMonotonicUs();
            s_startup_phase = SystemStartupPhase_WaitConfig;
            return;
        case SystemStartupPhase_WaitConfig:
            SystemStartup_CommunicationProcess();
            if (SystemStartup_ConfigVerifyPending() != 0U)
            {
                now_us = SystemTime_GetMonotonicUs();
                if ((now_us - s_phase_started_us) <
                    SYSTEM_STARTUP_CONFIGURATION_TIMEOUT_US)
                { return; }
                if (s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU].verify_result ==
                    SYSTEM_DEVICE_NOT_EXECUTED)
                { s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU].verify_result =
                    SYSTEM_DEVICE_TIMEOUT; }
                if (s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].verify_result ==
                    SYSTEM_DEVICE_NOT_EXECUTED)
                { s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].verify_result =
                    SYSTEM_DEVICE_TIMEOUT; }
            }
            s_phase_started_us = SystemTime_GetMonotonicUs();
            s_startup_phase = SystemStartupPhase_WaitCommunication;
            return;
        case SystemStartupPhase_WaitCommunication:
            now_us = SystemTime_GetMonotonicUs();
            if ((SystemStartup_CommunicationEvaluate() != 0U) &&
                ((now_us - s_phase_started_us) <
                    SYSTEM_STARTUP_COMMUNICATION_TIMEOUT_US))
            { return; }
            SystemStartup_TimeoutMark();
            SystemStartup_ReportFinalize();
            if (SystemLifecycle_EnterPreflight() != SYSTEM_DEVICE_OK)
            { DebugLog_Print("STARTUP preflight transition failed"); }
            SystemHealth_Process();
            SystemStartup_ReportPrint();
            s_startup_phase = SystemStartupPhase_Complete;
            return;
        case SystemStartupPhase_Idle:
        case SystemStartupPhase_Complete:
        default:
            break;
    }
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_IMU) != 0U)
    { SystemImu_Process(); }
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_GNSS) != 0U)
    { SystemGnss_Process(); }
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_POWER) != 0U)
    { SystemPower_Process(); }
    if (SystemStartup_CapabilityEnabled(SYSTEM_CAPABILITY_OUTPUT) != 0U)
    { SystemOutput_Process(); }
}
