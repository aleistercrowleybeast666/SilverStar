#include "system_version.h"
#include "system_console.h"

#include <math.h>
#include <stddef.h>
#include <stdarg.h>
#include "common_format.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include <string.h>

#include "system_alignment.h"
#include "system_calibration.h"
#include "system_capabilities.h"
#include "system_barometer.h"
#include "system_barometer_if.h"
#include "system_console_if.h"
#include "system_estimator_diagnostics.h"
#include "system_flight_recovery.h"
#include "system_gnss_if.h"
#include "system_health.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_lifecycle.h"
#include "system_magnetometer_if.h"
#include "system_output_if.h"
#include "system_power_if.h"
#include "system_profile.h"
#include "system_startup.h"
#include "system_storage_if.h"
#include "system_task_stack.h"
#include "system_telemetry_transport_if.h"
#include "system_time.h"
#include "system_user_config.h"


typedef enum
{
    SYSTEM_CONSOLE_MODULE_SYSTEM = 0,
    SYSTEM_CONSOLE_MODULE_IMU,
    SYSTEM_CONSOLE_MODULE_GNSS,
    SYSTEM_CONSOLE_MODULE_BARO,
    SYSTEM_CONSOLE_MODULE_MAG,
    SYSTEM_CONSOLE_MODULE_ATTITUDE,
    SYSTEM_CONSOLE_MODULE_ESTIMATOR,
    SYSTEM_CONSOLE_MODULE_KF,
    SYSTEM_CONSOLE_MODULE_INS,
    SYSTEM_CONSOLE_MODULE_CAL,
    SYSTEM_CONSOLE_MODULE_ALIGN,
    SYSTEM_CONSOLE_MODULE_TELEMETRY,
    SYSTEM_CONSOLE_MODULE_POWER,
    SYSTEM_CONSOLE_MODULE_OUTPUT,
    SYSTEM_CONSOLE_MODULE_LOG,
    SYSTEM_CONSOLE_MODULE_TIME,
    SYSTEM_CONSOLE_MODULE_INVALID
} SystemConsoleModule;

typedef enum
{
    SYSTEM_CONSOLE_SENSOR_OK = 0,
    SYSTEM_CONSOLE_SENSOR_UNSUPPORTED,
    SYSTEM_CONSOLE_SENSOR_NOT_PRESENT,
    SYSTEM_CONSOLE_SENSOR_NOT_CONFIGURED,
    SYSTEM_CONSOLE_SENSOR_NOT_READY,
    SYSTEM_CONSOLE_SENSOR_STALE,
    SYSTEM_CONSOLE_SENSOR_INVALID,
    SYSTEM_CONSOLE_SENSOR_FAILED
} SystemConsoleSensorStatus;

static char s_line[SYSTEM_CONSOLE_LINE_CAPACITY];
static uint16_t s_line_length;
static char s_response[SYSTEM_CONSOLE_RESPONSE_CAPACITY];
static uint32_t s_console_start_request_id;
static uint32_t s_console_discontinuity_sequence;
static uint32_t s_console_calibration_face_event_sequence;
static uint32_t s_console_calibration_completion_sequence;
static uint32_t s_console_calibration_diagnostic_sequence;
static uint32_t s_console_alignment_completion_sequence;
static uint32_t s_console_flight_action_sequence;
static uint32_t s_console_deploy_event_sequence;
static uint32_t s_console_impact_event_sequence;
static uint32_t s_console_landing_event_sequence;
static SystemAlignmentState s_console_alignment_state;
static char s_async_event[320];

#define SYSTEM_CONSOLE_MAX_READ_CHUNKS_PER_CYCLE 8U
#define SYSTEM_CONSOLE_TOKEN_COUNT_MAX 5U

typedef struct
{
    char *scan;
    uint16_t remaining;
} SystemConsoleTokenCursor;

static uint16_t SystemConsole_TextLengthGet(const char *text,
                                            uint16_t capacity)
{
    uint16_t index;

    if (text == NULL) { return capacity; }
    for (index = 0U; index < capacity; index++)
    {
        if (text[index] == '\0') { return index; }
    }
    return capacity;
}

static void SystemConsole_TextAppend(char *text, uint16_t capacity,
    const char *format, ...)
{
    size_t length;
    va_list arguments;

    if ((text == NULL) || (format == NULL) || (capacity == 0U))
    {
        return;
    }
    length = SystemConsole_TextLengthGet(text, capacity);
    if (length >= capacity)
    {
        return;
    }
    va_start(arguments, format);
    (void)CommonFormat_VPrint(&text[length], (size_t)capacity - length,
                    format, arguments);
    va_end(arguments);
}

static void SystemConsole_AlignmentSourcesAppend(
    const SystemAlignmentStatus *status,
    char *text,
    uint16_t capacity,
    const char *suffix)
{
    uint32_t source;

    if ((status == NULL) || (text == NULL) || (suffix == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (source = 0U; source < SYSTEM_ALIGNMENT_SOURCE_COUNT; source++)
    {
        const SystemAlignmentSourceDescriptor *descriptor;

        if ((status->selected_mask & SYSTEM_ALIGNMENT_SOURCE_BIT(source)) ==
            0U)
        {
            continue;
        }
        descriptor = SystemAlignment_SourceDescriptorGet(
            (SystemAlignmentSourceId)source);
        if (descriptor != NULL)
        {
            SystemConsole_TextAppend(text, capacity, " %s%s=%s",
                descriptor->key, suffix,
                SystemAlignment_ComponentStateText(
                    status->component[source].state));
        }
    }
}

static void SystemConsole_AlignmentReadyFieldsAppend(
    const SystemAlignmentSummary *summary,
    char *text,
    uint16_t capacity)
{
    uint32_t source;

    if ((summary == NULL) || (text == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(summary, SystemAlignmentSummary,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (source = 0U; source < SYSTEM_ALIGNMENT_SOURCE_COUNT; source++)
    {
        const SystemAlignmentSourceDescriptor *descriptor;

        if ((summary->selected_mask & SYSTEM_ALIGNMENT_SOURCE_BIT(source)) ==
            0U)
        {
            continue;
        }
        descriptor = SystemAlignment_SourceDescriptorGet(
            (SystemAlignmentSourceId)source);
        if (descriptor != NULL)
        {
            SystemConsole_TextAppend(text, capacity,
                " %s_alignment_ready=%u", descriptor->key,
                (unsigned int)((summary->ready_mask &
                    SYSTEM_ALIGNMENT_SOURCE_BIT(source)) != 0U));
        }
    }
}

typedef struct
{
    SystemDeviceIoDiagnostics diagnostics;
    SystemImuIoDetail imu_detail;
    SystemGnssIoDetail gnss_detail;
    uint16_t physical_device_id;
    SystemDeviceClass owner_class;
    uint8_t owner_instance_id;
    uint8_t valid;
} SystemConsoleIoBaseline;

static SystemConsoleIoBaseline
    s_io_baselines[SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX];

static const char *SystemConsole_SensorStatusText(
    SystemConsoleSensorStatus status)
{
    switch (status)
    {
        case SYSTEM_CONSOLE_SENSOR_OK: return "OK";
        case SYSTEM_CONSOLE_SENSOR_UNSUPPORTED: return "UNSUPPORTED";
        case SYSTEM_CONSOLE_SENSOR_NOT_PRESENT: return "NOT_PRESENT";
        case SYSTEM_CONSOLE_SENSOR_NOT_CONFIGURED: return "NOT_CONFIGURED";
        case SYSTEM_CONSOLE_SENSOR_NOT_READY: return "NOT_READY";
        case SYSTEM_CONSOLE_SENSOR_STALE: return "STALE";
        case SYSTEM_CONSOLE_SENSOR_INVALID: return "INVALID";
        case SYSTEM_CONSOLE_SENSOR_FAILED: return "FAILED";
        default: return "FAILED";
    }
}

static void SystemConsole_FieldFloatFormat(char *text,
                                            uint16_t capacity,
                                            uint8_t supported,
                                            uint8_t valid,
                                            float value,
                                            float scale)
{
    if (supported == 0U)
    {
        (void)CommonFormat_Print(text, capacity, "UNSUPPORTED");
    }
    else if ((valid == 0U) || (!isfinite(value)))
    {
        (void)CommonFormat_Print(text, capacity, "INVALID");
    }
    else
    {
        (void)CommonFormat_Print(text, capacity, "%.3f", (double)(value * scale));
    }
}

static void SystemConsole_FieldUnsignedFormat(char *text,
                                               uint16_t capacity,
                                               uint8_t supported,
                                               uint8_t valid,
                                               unsigned long value)
{
    if (supported == 0U)
    {
        (void)CommonFormat_Print(text, capacity, "UNSUPPORTED");
    }
    else if (valid == 0U)
    {
        (void)CommonFormat_Print(text, capacity, "INVALID");
    }
    else
    {
        (void)CommonFormat_Print(text, capacity, "%lu", value);
    }
}

static void SystemConsole_FieldSignedFormat(char *text,
                                             uint16_t capacity,
                                             uint8_t supported,
                                             uint8_t valid,
                                             long value)
{
    if (supported == 0U)
    {
        (void)CommonFormat_Print(text, capacity, "UNSUPPORTED");
    }
    else if (valid == 0U)
    {
        (void)CommonFormat_Print(text, capacity, "INVALID");
    }
    else
    {
        (void)CommonFormat_Print(text, capacity, "%ld", value);
    }
}

static void SystemConsole_AgeFormat(char *text,
                                     uint16_t capacity,
                                     uint64_t age_ms)
{
    if (age_ms == UINT64_MAX)
    {
        (void)CommonFormat_Print(text, capacity, "INVALID");
    }
    else
    {
        uint32_t display_ms = (age_ms > UINT32_MAX) ?
            UINT32_MAX : (uint32_t)age_ms;

        (void)CommonFormat_Print(text, capacity, "%lu",
                       (unsigned long)display_ms);
    }
}

static unsigned long SystemConsole_TimestampDisplay(uint64_t timestamp_us)
{
    return (unsigned long)((timestamp_us > UINT32_MAX) ?
        UINT32_MAX : (uint32_t)timestamp_us);
}

static SystemConsoleModule SystemConsole_CapabilityModuleParse(
    const char *module)
{
    if (module == NULL) { return SYSTEM_CONSOLE_MODULE_INVALID; }
    if (strcmp(module, "IMU") == 0) { return SYSTEM_CONSOLE_MODULE_IMU; }
    if (strcmp(module, "GNSS") == 0) { return SYSTEM_CONSOLE_MODULE_GNSS; }
    if (strcmp(module, "BARO") == 0) { return SYSTEM_CONSOLE_MODULE_BARO; }
    if (strcmp(module, "MAG") == 0) { return SYSTEM_CONSOLE_MODULE_MAG; }
    if (strcmp(module, "ATTITUDE") == 0) { return SYSTEM_CONSOLE_MODULE_ATTITUDE; }
    if (strcmp(module, "TELEMETRY") == 0) { return SYSTEM_CONSOLE_MODULE_TELEMETRY; }
    if (strcmp(module, "POWER") == 0) { return SYSTEM_CONSOLE_MODULE_POWER; }
    return SYSTEM_CONSOLE_MODULE_INVALID;
}

static SystemConsoleModule SystemConsole_ModuleParse(const char *module)
{
    SystemConsoleModule parsed;

    if (module == NULL) { return SYSTEM_CONSOLE_MODULE_INVALID; }
    parsed = SystemConsole_CapabilityModuleParse(module);
    if (parsed != SYSTEM_CONSOLE_MODULE_INVALID) { return parsed; }
    if (strcmp(module, "SYSTEM") == 0) { return SYSTEM_CONSOLE_MODULE_SYSTEM; }
    if (strcmp(module, "ESTIMATOR") == 0) { return SYSTEM_CONSOLE_MODULE_ESTIMATOR; }
    if (strcmp(module, "KF") == 0) { return SYSTEM_CONSOLE_MODULE_KF; }
    if (strcmp(module, "INS") == 0) { return SYSTEM_CONSOLE_MODULE_INS; }
    if (strcmp(module, "CAL") == 0) { return SYSTEM_CONSOLE_MODULE_CAL; }
    if (strcmp(module, "ALIGN") == 0) { return SYSTEM_CONSOLE_MODULE_ALIGN; }
    if (strcmp(module, "OUTPUT") == 0) { return SYSTEM_CONSOLE_MODULE_OUTPUT; }
    if (strcmp(module, "LOG") == 0) { return SYSTEM_CONSOLE_MODULE_LOG; }
    if (strcmp(module, "TIME") == 0) { return SYSTEM_CONSOLE_MODULE_TIME; }
    return SYSTEM_CONSOLE_MODULE_INVALID;
}

static uint8_t SystemConsole_ModuleIsIndexed(SystemConsoleModule module)
{
    return (uint8_t)((module == SYSTEM_CONSOLE_MODULE_IMU) ||
        (module == SYSTEM_CONSOLE_MODULE_GNSS) ||
        (module == SYSTEM_CONSOLE_MODULE_BARO) ||
        (module == SYSTEM_CONSOLE_MODULE_MAG) ||
        (module == SYSTEM_CONSOLE_MODULE_ATTITUDE) ||
        (module == SYSTEM_CONSOLE_MODULE_TELEMETRY) ||
        (module == SYSTEM_CONSOLE_MODULE_POWER));
}

static SystemDeviceClass SystemConsole_DeviceClassGet(
    SystemConsoleModule module)
{
    SILVERSTAR_ASSERT_OBJECT(&module, SystemConsoleModule,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (module)
    {
        case SYSTEM_CONSOLE_MODULE_IMU: return SYSTEM_DEVICE_CLASS_IMU;
        case SYSTEM_CONSOLE_MODULE_GNSS: return SYSTEM_DEVICE_CLASS_GNSS;
        case SYSTEM_CONSOLE_MODULE_BARO: return SYSTEM_DEVICE_CLASS_BAROMETER;
        case SYSTEM_CONSOLE_MODULE_MAG:
            return SYSTEM_DEVICE_CLASS_MAGNETOMETER;
        case SYSTEM_CONSOLE_MODULE_ATTITUDE:
            return SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION;
        case SYSTEM_CONSOLE_MODULE_TELEMETRY:
            return SYSTEM_DEVICE_CLASS_TELEMETRY;
        case SYSTEM_CONSOLE_MODULE_POWER: return SYSTEM_DEVICE_CLASS_POWER;
        case SYSTEM_CONSOLE_MODULE_SYSTEM:
        case SYSTEM_CONSOLE_MODULE_ESTIMATOR:
        case SYSTEM_CONSOLE_MODULE_KF:
        case SYSTEM_CONSOLE_MODULE_INS:
        case SYSTEM_CONSOLE_MODULE_CAL:
        case SYSTEM_CONSOLE_MODULE_ALIGN:
        case SYSTEM_CONSOLE_MODULE_OUTPUT:
        case SYSTEM_CONSOLE_MODULE_LOG:
        case SYSTEM_CONSOLE_MODULE_TIME:
        case SYSTEM_CONSOLE_MODULE_INVALID:
        default: return SYSTEM_DEVICE_CLASS_TIME;
    }
}

static const char *SystemConsole_DeviceErrorText(SystemDeviceResult result)
{
    SILVERSTAR_ASSERT_OBJECT(&result, SystemDeviceResult,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(result <= SYSTEM_DEVICE_NOT_PRESENT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (result)
    {
        case SYSTEM_DEVICE_OK: return "OK";
        case SYSTEM_DEVICE_ALREADY_MATCHED: return "ALREADY_MATCHED";
        case SYSTEM_DEVICE_NOT_READY: return "NOT_READY";
        case SYSTEM_DEVICE_OFFLINE: return "OFFLINE";
        case SYSTEM_DEVICE_UNSUPPORTED: return "UNSUPPORTED";
        case SYSTEM_DEVICE_INVALID_ARGUMENT: return "BAD_PARAM";
        case SYSTEM_DEVICE_TIMEOUT: return "TIMEOUT";
        case SYSTEM_DEVICE_IO_ERROR: return "IO_ERROR";
        case SYSTEM_DEVICE_VERIFY_FAILED: return "VERIFY_FAILED";
        case SYSTEM_DEVICE_BAD_STATE: return "BAD_STATE";
        case SYSTEM_DEVICE_VALUE_ADJUSTED: return "VALUE_ADJUSTED";
        case SYSTEM_DEVICE_CONFIG_NO_ACTION: return "NO_ACTION";
        case SYSTEM_DEVICE_CONFIG_DELEGATED: return "DELEGATED";
        case SYSTEM_DEVICE_NOT_EXECUTED: return "NOT_EXECUTED";
        case SYSTEM_DEVICE_BUSY: return "BUSY";
        case SYSTEM_DEVICE_NOT_PRESENT: return "NOT_PRESENT";
        case SYSTEM_DEVICE_INTERNAL_ERROR: return "INTERNAL";
        default: return "INTERNAL";
    }
}

static const char *SystemConsole_LifecycleStateText(SystemLifecycleState state)
{
    switch (state)
    {
        case SYSTEM_STATE_BOOT: return "BOOT";
        case SYSTEM_STATE_SELF_TEST: return "SELF_TEST";
        case SYSTEM_STATE_PREFLIGHT: return "PREFLIGHT";
        case SYSTEM_STATE_READY: return "READY";
        case SYSTEM_STATE_FLIGHT: return "FLIGHT";
        case SYSTEM_STATE_RECOVERY: return "RECOVERY";
        case SYSTEM_STATE_LANDED: return "LANDED";
        case SYSTEM_STATE_POSTFLIGHT: return "POSTFLIGHT";
        case SYSTEM_STATE_FAULT:
        default: return "FAULT";
    }
}


static const char *SystemConsole_GnssConfigReadResultText(
    SystemGnssConfigReadResult result)
{
    switch (result)
    {
        case SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK: return "RESPONSE_OK";
        case SYSTEM_GNSS_CONFIG_READ_NAK: return "NAK";
        case SYSTEM_GNSS_CONFIG_READ_TX_ERROR: return "TX_ERROR";
        case SYSTEM_GNSS_CONFIG_READ_CHECKSUM_ERROR:
            return "CHECKSUM_ERROR";
        case SYSTEM_GNSS_CONFIG_READ_MALFORMED_RESPONSE:
            return "MALFORMED_RESPONSE";
        case SYSTEM_GNSS_CONFIG_READ_TIMEOUT: return "TIMEOUT";
        case SYSTEM_GNSS_CONFIG_READ_IO_ERROR: return "IO_ERROR";
        case SYSTEM_GNSS_CONFIG_READ_NOT_READY:
        default: return "NOT_READY";
    }
}

static const char *SystemConsole_GnssConfigReadGroupText(
    SystemGnssConfigReadGroup group)
{
    switch (group)
    {
        case SYSTEM_GNSS_CONFIG_READ_GROUP_UART: return "UART";
        case SYSTEM_GNSS_CONFIG_READ_GROUP_PROTOCOL: return "PROTOCOL";
        case SYSTEM_GNSS_CONFIG_READ_GROUP_NAV_PVT: return "NAV_PVT";
        case SYSTEM_GNSS_CONFIG_READ_GROUP_RATE: return "RATE";
        case SYSTEM_GNSS_CONFIG_READ_GROUP_DYNAMIC_MODEL:
            return "DYNAMIC";
        case SYSTEM_GNSS_CONFIG_READ_GROUP_SIGNALS: return "SIGNALS";
        case SYSTEM_GNSS_CONFIG_READ_GROUP_NONE:
        default: return "NONE";
    }
}

static const char *SystemConsole_GnssTransactionDetailText(
    SystemGnssTransactionDetail detail)
{
    SILVERSTAR_ASSERT_OBJECT(&detail, SystemGnssTransactionDetail,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(
        detail <= SYSTEM_GNSS_TRANSACTION_DETAIL_RX_DISCONTINUITY,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    switch (detail)
    {
        case SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK:
            return "RESPONSE_OK";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_NAK: return "NAK";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_BUSY: return "BUSY";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_VERSION:
            return "BAD_VERSION";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LAYER:
            return "BAD_LAYER";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_POSITION:
            return "BAD_POSITION";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_BAD_LENGTH:
            return "BAD_LENGTH";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_KEY_MISMATCH:
            return "KEY_MISMATCH";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_VALUE_LENGTH_MISMATCH:
            return "VALUE_LENGTH_MISMATCH";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_COUNT_OVERFLOW:
            return "COUNT_OVERFLOW";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_CHECKSUM_ERROR:
            return "CHECKSUM_ERROR";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_TX_ERROR: return "TX_ERROR";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_TIMEOUT: return "TIMEOUT";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_NOT_READY: return "NOT_READY";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_RX_DISCONTINUITY:
            return "RX_DISCONTINUITY";
        case SYSTEM_GNSS_TRANSACTION_DETAIL_NONE:
        default: return "NONE";
    }
}

static SystemConsoleExecuteResult SystemConsole_ErrorWrite(
    char *response,
    uint16_t capacity,
    const char *module,
    const char *command,
    const char *code,
    const char *reason,
    SystemConsoleExecuteResult result)
{
    (void)CommonFormat_Print(response, capacity,
                   "ERR %s %s code=%s reason=%s",
                   module, command, code, reason);
    return result;
}

static uint8_t SystemConsole_CommandIsInspection(const char *command)
{
    return (uint8_t)((strcmp(command, "INFO") == 0) ||
                     (strcmp(command, "STATUS") == 0) ||
                     (strcmp(command, "CAPABILITIES") == 0) ||
                     (strcmp(command, "SAMPLE") == 0) ||
                     (strcmp(command, "IO") == 0) ||
                     (strcmp(command, "LIST") == 0));
}

static uint8_t SystemConsole_CommandAllowedInFlight(const char *module,
                                                     const char *command,
                                                     const char *subcommand)
{
    SILVERSTAR_ASSERT_OBJECT(module, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemConsole_CommandIsInspection(command) != 0U)
    {
        return 1U;
    }
    if ((strcmp(command, "CONFIG") == 0) && (subcommand != NULL) &&
        ((strcmp(subcommand, "SHOW") == 0) ||
         (strcmp(subcommand, "READ") == 0) ||
         (strcmp(subcommand, "VERIFY") == 0)))
    {
        return 1U;
    }
    if ((strcmp(module, "SYSTEM") == 0) &&
        (strcmp(command, "CONSOLE") == 0))
    {
        return 1U;
    }
    if ((strcmp(module, "SYSTEM") == 0) &&
        ((strcmp(command, "START") == 0) ||
         (strcmp(command, "STARTUP") == 0) ||
         (strcmp(command, "PROFILE") == 0) ||
         (strcmp(command, "READY") == 0) ||
         (strcmp(command, "FLIGHT") == 0)))
    {
        return 1U;
    }
    if ((strcmp(module, "GNSS") == 0) &&
        ((strcmp(command, "NAV") == 0) ||
         (strcmp(command, "MON") == 0)))
    {
        return 1U;
    }
    if ((strcmp(module, "ESTIMATOR") == 0) &&
        ((strcmp(command, "BARO") == 0) ||
         (strcmp(command, "GNSS") == 0)))
    {
        return 1U;
    }
    if ((strcmp(module, "ALIGN") == 0) &&
        ((strcmp(command, "STATUS") == 0) ||
         (strcmp(command, "DETAIL") == 0)))
    {
        return 1U;
    }
    if ((strcmp(module, "CAL") == 0) &&
        ((strcmp(command, "STATUS") == 0) ||
         (strcmp(command, "DETAIL") == 0)))
    {
        return 1U;
    }
    return (uint8_t)((strcmp(module, "TIME") == 0) &&
                     (strcmp(command, "STATUS") == 0));
}

static SystemDeviceResult SystemConsole_InfoGet(SystemConsoleModule module,
    uint8_t instance_id, SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(info, SystemDeviceInfo,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (module)
    {
        case SYSTEM_CONSOLE_MODULE_IMU:
        case SYSTEM_CONSOLE_MODULE_GNSS:
        case SYSTEM_CONSOLE_MODULE_BARO:
        case SYSTEM_CONSOLE_MODULE_MAG:
        case SYSTEM_CONSOLE_MODULE_ATTITUDE:
        case SYSTEM_CONSOLE_MODULE_TELEMETRY:
        case SYSTEM_CONSOLE_MODULE_POWER:
            return ProjectDeviceInstance_InfoGet(
                SystemConsole_DeviceClassGet(module), instance_id, info);
        case SYSTEM_CONSOLE_MODULE_LOG:
            info->device_name = SystemStorage_NameGet();
            info->model_name = "GENERIC_STORAGE";
            info->driver_version = "SystemStorageService";
            info->capability_mask = 0U;
            info->configuration_mask = 0U;
            return SYSTEM_DEVICE_OK;
        case SYSTEM_CONSOLE_MODULE_SYSTEM:
        case SYSTEM_CONSOLE_MODULE_ESTIMATOR:
        case SYSTEM_CONSOLE_MODULE_KF:
        case SYSTEM_CONSOLE_MODULE_INS:
        case SYSTEM_CONSOLE_MODULE_CAL:
        case SYSTEM_CONSOLE_MODULE_ALIGN:
        case SYSTEM_CONSOLE_MODULE_OUTPUT:
        case SYSTEM_CONSOLE_MODULE_TIME:
        case SYSTEM_CONSOLE_MODULE_INVALID:
        default:
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemDeviceResult SystemConsole_CapabilitiesGet(
    SystemConsoleModule module,
    uint8_t instance_id,
    uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(mask, uint32_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (module)
    {
        case SYSTEM_CONSOLE_MODULE_IMU:
        case SYSTEM_CONSOLE_MODULE_GNSS:
        case SYSTEM_CONSOLE_MODULE_BARO:
        case SYSTEM_CONSOLE_MODULE_MAG:
        case SYSTEM_CONSOLE_MODULE_ATTITUDE:
        case SYSTEM_CONSOLE_MODULE_TELEMETRY:
        case SYSTEM_CONSOLE_MODULE_POWER:
            return ProjectDeviceInstance_CapabilitiesGet(
                SystemConsole_DeviceClassGet(module), instance_id, mask);
        case SYSTEM_CONSOLE_MODULE_SYSTEM:
        case SYSTEM_CONSOLE_MODULE_ESTIMATOR:
        case SYSTEM_CONSOLE_MODULE_KF:
        case SYSTEM_CONSOLE_MODULE_INS:
        case SYSTEM_CONSOLE_MODULE_CAL:
        case SYSTEM_CONSOLE_MODULE_ALIGN:
        case SYSTEM_CONSOLE_MODULE_OUTPUT:
        case SYSTEM_CONSOLE_MODULE_LOG:
        case SYSTEM_CONSOLE_MODULE_TIME:
        case SYSTEM_CONSOLE_MODULE_INVALID:
        default:
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemDeviceResult SystemConsole_DeviceHealthGet(
    SystemConsoleModule module,
    uint8_t instance_id,
    SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (module)
    {
        case SYSTEM_CONSOLE_MODULE_IMU:
        case SYSTEM_CONSOLE_MODULE_GNSS:
        case SYSTEM_CONSOLE_MODULE_BARO:
        case SYSTEM_CONSOLE_MODULE_MAG:
        case SYSTEM_CONSOLE_MODULE_ATTITUDE:
        case SYSTEM_CONSOLE_MODULE_POWER:
            return ProjectDeviceInstance_HealthGet(
                SystemConsole_DeviceClassGet(module), instance_id, health);
        case SYSTEM_CONSOLE_MODULE_SYSTEM:
        case SYSTEM_CONSOLE_MODULE_ESTIMATOR:
        case SYSTEM_CONSOLE_MODULE_KF:
        case SYSTEM_CONSOLE_MODULE_INS:
        case SYSTEM_CONSOLE_MODULE_CAL:
        case SYSTEM_CONSOLE_MODULE_ALIGN:
        case SYSTEM_CONSOLE_MODULE_TELEMETRY:
        case SYSTEM_CONSOLE_MODULE_OUTPUT:
        case SYSTEM_CONSOLE_MODULE_LOG:
        case SYSTEM_CONSOLE_MODULE_TIME:
        case SYSTEM_CONSOLE_MODULE_INVALID:
        default:
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemDeviceResult SystemConsole_TelemetryHealthWrite(
    uint8_t instance_id, const char *module_text, const char *command,
    char *response, uint16_t capacity)
{
    SystemTelemetryHealth health;
    SystemDeviceResult result = ProjectTelemetryInstance_HealthGet(
        instance_id, &health);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s %s initialized=%u started=%u online=%u healthy=%u tx=%lu rx=%lu integrity_errors=%lu",
            module_text, command, (unsigned int)health.initialized,
            (unsigned int)health.started, (unsigned int)health.online,
            (unsigned int)health.healthy,
            (unsigned long)health.transmit_packet_count,
            (unsigned long)health.receive_packet_count,
            (unsigned long)health.integrity_error_count);
    }
    return result;
}

static SystemDeviceResult SystemConsole_StorageHealthWrite(
    const char *command, char *response, uint16_t capacity)
{
    SystemStorageHealth health;
    SystemDeviceResult result = SystemStorage_HealthGet(&health);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK LOG %s initialized=%u mounted=%u open=%u healthy=%u writes=%lu syncs=%lu errors=%lu",
            command, (unsigned int)health.initialized,
            (unsigned int)health.mounted, (unsigned int)health.file_open,
            (unsigned int)health.healthy, (unsigned long)health.write_count,
            (unsigned long)health.sync_count, (unsigned long)health.error_count);
    }
    return result;
}

static SystemDeviceResult SystemConsole_OutputHealthWrite(
    const char *command, char *response, uint16_t capacity)
{
    SystemOutputStatus output_1;
    SystemOutputStatus output_2;
    SystemDeviceResult result = SystemOutput_StatusGet(1U, &output_1);

    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (result == SYSTEM_DEVICE_OK)
    {
        result = SystemOutput_StatusGet(2U, &output_2);
    }
    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK OUTPUT %s ch1_state=%u ch1_active=%u ch1_fault=%u ch2_state=%u ch2_active=%u ch2_fault=%u",
            command, (unsigned int)output_1.state,
            (unsigned int)output_1.physical_active,
            (unsigned int)output_1.fault, (unsigned int)output_2.state,
            (unsigned int)output_2.physical_active,
            (unsigned int)output_2.fault);
    }
    return result;
}

static SystemDeviceResult SystemConsole_DeviceHealthWrite(
    SystemConsoleModule module, const char *module_text,
    uint8_t instance_id, const char *command,
    char *response, uint16_t capacity)
{
    SystemDeviceHealth health;
    SystemDeviceResult result = SystemConsole_DeviceHealthGet(
        module, instance_id, &health);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s %s initialized=%u started=%u online=%u healthy=%u samples=%lu errors=%lu timeouts=%lu",
            module_text, command, (unsigned int)health.initialized,
            (unsigned int)health.started, (unsigned int)health.online,
            (unsigned int)health.healthy, (unsigned long)health.sample_count,
            (unsigned long)health.error_count,
            (unsigned long)health.timeout_count);
    }
    return result;
}

static SystemConsoleExecuteResult SystemConsole_HealthExecute(
    SystemConsoleModule module,
    const char *module_text,
    uint8_t instance_id,
    const char *command,
    char *response,
    uint16_t capacity)
{
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(module_text, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (module == SYSTEM_CONSOLE_MODULE_TELEMETRY)
    {
        result = SystemConsole_TelemetryHealthWrite(
            instance_id, module_text, command, response, capacity);
    }
    else if (module == SYSTEM_CONSOLE_MODULE_LOG)
    {
        result = SystemConsole_StorageHealthWrite(command, response, capacity);
    }
    else if (module == SYSTEM_CONSOLE_MODULE_OUTPUT)
    {
        result = SystemConsole_OutputHealthWrite(command, response, capacity);
    }
    else
    {
        result = SystemConsole_DeviceHealthWrite(
            module, module_text, instance_id, command, response, capacity);
    }
    if (result == SYSTEM_DEVICE_OK) { return SYSTEM_CONSOLE_EXECUTE_OK; }
    return SystemConsole_ErrorWrite(response, capacity, module_text, command,
                                    SystemConsole_DeviceErrorText(result),
                                    "DEVICE",
                                    (result == SYSTEM_DEVICE_UNSUPPORTED) ?
                                        SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED :
                                        SYSTEM_CONSOLE_EXECUTE_FAILED);
}

static SystemDeviceResult SystemConsole_ImuConfigShowWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemImuConfig config;
    SystemDeviceResult result = ProjectImuInstance_EffectiveConfigGet(
        instance_id, &config);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CONFIG SHOW mask=0x%08lX rate_hz=%u accel_bw_millihz=%ld gyro_bw_millihz=%ld accel_range_millig=%ld gyro_range_dps=%ld",
            module_text, (unsigned long)config.requested_mask,
            (unsigned int)config.output_rate_hz,
            (long)(config.accel_bandwidth_hz * 1000.0f),
            (long)(config.gyro_bandwidth_hz * 1000.0f),
            (long)(config.accel_range_g * 1000.0f),
            (long)config.gyro_range_dps);
    }
    return result;
}

static SystemDeviceResult SystemConsole_GnssConfigShowWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemGnssConfig config;
    SystemDeviceResult result = ProjectGnssInstance_EffectiveConfigGet(
        instance_id, &config);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CONFIG SHOW source=CACHE mask=0x%08lX rate_hz=%u constellations=0x%08lX dynamic_model=%u protocol=%u messages=0x%08lX",
            module_text, (unsigned long)config.requested_mask,
            (unsigned int)config.navigation_rate_hz,
            (unsigned long)config.constellation_mask,
            (unsigned int)config.dynamic_model,
            (unsigned int)config.output_protocol,
            (unsigned long)config.enabled_message_mask);
    }
    return result;
}

static SystemDeviceResult SystemConsole_BarometerConfigShowWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemBarometerConfig config;
    SystemDeviceResult result = ProjectBarometerInstance_EffectiveConfigGet(
        instance_id, &config);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CONFIG SHOW mask=0x%08lX rate_hz=%u",
            module_text, (unsigned long)config.requested_mask,
            (unsigned int)config.output_rate_hz);
    }
    return result;
}

static SystemDeviceResult SystemConsole_MagnetometerConfigShowWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemMagnetometerConfig config;
    SystemDeviceResult result =
        ProjectMagnetometerInstance_EffectiveConfigGet(instance_id, &config);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CONFIG SHOW mask=0x%08lX rate_hz=%u range_milliuT=%ld",
            module_text, (unsigned long)config.requested_mask,
            (unsigned int)config.output_rate_hz,
            (long)(config.range_uT * 1000.0f));
    }
    return result;
}

static SystemDeviceResult SystemConsole_AttitudeConfigShowWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemHardwareQuaternionConfig config;
    SystemDeviceResult result =
        ProjectAttitudeInstance_EffectiveConfigGet(instance_id, &config);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CONFIG SHOW mask=0x%08lX mode=%u rate_hz=%u",
            module_text, (unsigned long)config.requested_mask,
            (unsigned int)config.mode,
            (unsigned int)config.output_rate_hz);
    }
    return result;
}

static SystemDeviceResult SystemConsole_PowerConfigShowWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemPowerConfig config;
    SystemDeviceResult result = ProjectPowerInstance_EffectiveConfigGet(
        instance_id, &config);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CONFIG SHOW mask=0x%08lX voltage_scale_ppm=%ld voltage_offset_uv=%ld",
            module_text, (unsigned long)config.requested_mask,
            (long)(config.voltage_scale * 1000000.0f),
            (long)(config.voltage_offset_v * 1000000.0f));
    }
    return result;
}

static SystemDeviceResult SystemConsole_ConfigShowWrite(
    SystemConsoleModule module, uint8_t instance_id,
    const char *module_text, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (module)
    {
    case SYSTEM_CONSOLE_MODULE_IMU:
        return SystemConsole_ImuConfigShowWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_GNSS:
        return SystemConsole_GnssConfigShowWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_BARO:
        return SystemConsole_BarometerConfigShowWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_MAG:
        return SystemConsole_MagnetometerConfigShowWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_ATTITUDE:
        return SystemConsole_AttitudeConfigShowWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_POWER:
        return SystemConsole_PowerConfigShowWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_SYSTEM:
    case SYSTEM_CONSOLE_MODULE_ESTIMATOR:
    case SYSTEM_CONSOLE_MODULE_KF:
    case SYSTEM_CONSOLE_MODULE_INS:
    case SYSTEM_CONSOLE_MODULE_CAL:
    case SYSTEM_CONSOLE_MODULE_ALIGN:
    case SYSTEM_CONSOLE_MODULE_TELEMETRY:
    case SYSTEM_CONSOLE_MODULE_OUTPUT:
    case SYSTEM_CONSOLE_MODULE_LOG:
    case SYSTEM_CONSOLE_MODULE_TIME:
    case SYSTEM_CONSOLE_MODULE_INVALID:
    default:
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemConsoleExecuteResult SystemConsole_ConfigShowExecute(
    SystemConsoleModule module,
    const char *module_text,
    uint8_t instance_id,
    char *response,
    uint16_t capacity)
{
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(module_text, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = SystemConsole_ConfigShowWrite(
        module, instance_id, module_text, response, capacity);
    if (result == SYSTEM_DEVICE_OK) { return SYSTEM_CONSOLE_EXECUTE_OK; }
    return SystemConsole_ErrorWrite(response, capacity, module_text,
                                    "CONFIG_SHOW",
                                    SystemConsole_DeviceErrorText(result),
                                    "DEVICE",
                                    (result == SYSTEM_DEVICE_UNSUPPORTED) ?
                                        SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED :
                                        SYSTEM_CONSOLE_EXECUTE_FAILED);
}

static void SystemConsole_StartupSummaryWrite(
    const SystemStartupReport *report, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM STARTUP completed=%u passed=%u mission_capable=%u degraded=%u required_fail=0x%08lX optional_fail=0x%08lX warning=0x%08lX devices=%u",
        (unsigned int)report->completed, (unsigned int)report->passed,
        (unsigned int)report->mission_capable,
        (unsigned int)report->degraded,
        (unsigned long)report->required_failure_mask,
        (unsigned long)report->optional_failure_mask,
        (unsigned long)report->warning_mask,
        (unsigned int)report->device_count);
}

static uint8_t SystemConsole_StartupDeviceIdParse(
    const char *subcommand, SystemStartupDeviceId *device_id)
{
    if ((subcommand == NULL) || (device_id == NULL)) { return 0U; }
    if (strcmp(subcommand, "IMU") == 0)
    { *device_id = SYSTEM_STARTUP_DEVICE_IMU; }
    else if (strcmp(subcommand, "GNSS") == 0)
    { *device_id = SYSTEM_STARTUP_DEVICE_GNSS; }
    else if (strcmp(subcommand, "TELEMETRY") == 0)
    { *device_id = SYSTEM_STARTUP_DEVICE_TELEMETRY; }
    else { return 0U; }
    return 1U;
}

static void SystemConsole_StartupDeviceWrite(
    const SystemStartupDeviceReport *device, const char *subcommand,
    char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(device, SystemStartupDeviceReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM STARTUP %s id=%u name=%s model=%s required=%u present=%u init=%s start=%s config=%s persist=%s verify=%s communication=%s requested=0x%08lX applied=0x%08lX delegated=0x%08lX failed=0x%08lX detail=%lu retry=%lu",
        subcommand, (unsigned int)device->device_id,
        device->device_name, device->model_name,
        (unsigned int)device->required, (unsigned int)device->present,
        SystemConsole_DeviceErrorText(device->init_result),
        SystemConsole_DeviceErrorText(device->start_result),
        SystemConsole_DeviceErrorText(device->config_result),
        SystemConsole_DeviceErrorText(device->persist_result),
        SystemConsole_DeviceErrorText(device->verify_result),
        SystemConsole_DeviceErrorText(device->communication_result),
        (unsigned long)device->requested_mask,
        (unsigned long)device->applied_mask,
        (unsigned long)device->delegated_mask,
        (unsigned long)device->failed_mask,
        (unsigned long)device->detail_code,
        (unsigned long)device->retry_count);
}

static void SystemConsole_StartupGnssDetailAppend(
    const SystemStartupReport *report,
    const SystemStartupDeviceReport *device,
    char *response,
    uint16_t capacity)
{
    const SystemGnssConfigTransactionReport *gnss;
    uint16_t used;

    SILVERSTAR_ASSERT_OBJECT(report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    gnss = &report->gnss_config;
    used = SystemConsole_TextLengthGet(response, capacity);
    if (used >= capacity) { return; }
    (void)CommonFormat_Print(&response[used], (uint16_t)(capacity - used),
        " failed_step=%u ack=%u write_layers=0x%02X uart=%s uart_settle=%s protocol=%s nav_pvt=%s rate=%s dynamic_model=%s signals=%s pvt_recovery=%s baseline_pvt=%lu recovered_pvt=%lu signal_complete_us=%lu verify_read_result=%s verify_failed_group=%s verify_failed_key=0x%08lX verify_response_length=%u verify_nak_class=0x%02X verify_nak_id=0x%02X verify_valid_mask=0x%08lX apply_failed_mask=0x%08lX persist_failed_mask=0x%08lX verify_failed_mask=0x%08lX verify_detailed_result=%s verify_expected_class=0x%02X verify_expected_id=0x%02X verify_received_class=0x%02X verify_received_id=0x%02X verify_response_version=%u",
        (unsigned int)gnss->failed_stage,
        (unsigned int)gnss->ack_result,
        (unsigned int)gnss->write_layers,
        SystemConsole_DeviceErrorText(gnss->uart_baudrate_result),
        SystemConsole_DeviceErrorText(gnss->uart_settle_result),
        SystemConsole_DeviceErrorText(gnss->protocol_result),
        SystemConsole_DeviceErrorText(gnss->nav_pvt_result),
        SystemConsole_DeviceErrorText(gnss->rate_result),
        SystemConsole_DeviceErrorText(gnss->dynamic_model_result),
        SystemConsole_DeviceErrorText(gnss->signals_result),
        SystemConsole_DeviceErrorText(gnss->pvt_recovery_result),
        (unsigned long)gnss->baseline_pvt_sequence,
        (unsigned long)gnss->recovered_pvt_sequence,
        SystemConsole_TimestampDisplay(gnss->signal_complete_timestamp_us),
        SystemConsole_GnssConfigReadResultText(gnss->verify_read_result),
        SystemConsole_GnssConfigReadGroupText(gnss->verify_failed_group),
        (unsigned long)gnss->verify_failed_key,
        (unsigned int)gnss->verify_response_length,
        (unsigned int)gnss->verify_nak_class,
        (unsigned int)gnss->verify_nak_id,
        (unsigned long)gnss->verify_valid_mask,
        (unsigned long)device->apply_failed_mask,
        (unsigned long)device->persist_failed_mask,
        (unsigned long)device->verify_failed_mask,
        SystemConsole_GnssTransactionDetailText(gnss->verify_detailed_result),
        (unsigned int)gnss->verify_expected_class,
        (unsigned int)gnss->verify_expected_id,
        (unsigned int)gnss->verify_received_class,
        (unsigned int)gnss->verify_received_id,
        (unsigned int)gnss->verify_response_version);
}

static void SystemConsole_StartupDeviceDetailAppend(
    const SystemStartupDeviceReport *device,
    char *response,
    uint16_t capacity)
{
    uint16_t used = SystemConsole_TextLengthGet(response, capacity);

    if (used >= capacity) { return; }
    (void)CommonFormat_Print(&response[used], (uint16_t)(capacity - used),
        " apply_failed_mask=0x%08lX persist_failed_mask=0x%08lX verify_failed_mask=0x%08lX",
        (unsigned long)device->apply_failed_mask,
        (unsigned long)device->persist_failed_mask,
        (unsigned long)device->verify_failed_mask);
}

static SystemConsoleExecuteResult SystemConsole_StartupExecute(
    const char *subcommand,
    char *response,
    uint16_t capacity)
{
    const SystemStartupReport *report = SystemStartup_GetReport();
    const SystemStartupDeviceReport *device;
    SystemStartupDeviceId device_id;

    if (report == NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", "STARTUP",
            "NOT_READY", "NO_REPORT", SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(report, SystemStartupReport,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (subcommand == NULL)
    {
        SystemConsole_StartupSummaryWrite(report, response, capacity);
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    if (SystemConsole_StartupDeviceIdParse(subcommand, &device_id) == 0U)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", "STARTUP",
            "BAD_PARAM", "DETAIL", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
    }
    device = SystemStartup_GetDeviceReport(device_id);
    if (device == NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", "STARTUP",
            "NOT_READY", "DETAIL", SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SystemConsole_StartupDeviceWrite(device, subcommand, response, capacity);
    if (device_id == SYSTEM_STARTUP_DEVICE_GNSS)
    {
        SystemConsole_StartupGnssDetailAppend(report, device, response,
                                              capacity);
    }
    else
    {
        SystemConsole_StartupDeviceDetailAppend(device, response, capacity);
    }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static const char *SystemConsole_IoTransportText(
    SystemDeviceTransportType transport)
{
    if (transport == SYSTEM_DEVICE_TRANSPORT_UART) { return "UART"; }
    if (transport == SYSTEM_DEVICE_TRANSPORT_SPI) { return "SPI"; }
    return "NONE";
}

static const char *SystemConsole_DeviceClassText(SystemDeviceClass owner)
{
    switch (owner)
    {
        case SYSTEM_DEVICE_CLASS_IMU: return "IMU";
        case SYSTEM_DEVICE_CLASS_GNSS: return "GNSS";
        case SYSTEM_DEVICE_CLASS_BAROMETER: return "BARO";
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER: return "MAG";
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION: return "ATTITUDE";
        case SYSTEM_DEVICE_CLASS_TELEMETRY: return "TELEMETRY";
        case SYSTEM_DEVICE_CLASS_CONSOLE: return "CONSOLE";
        case SYSTEM_DEVICE_CLASS_POWER: return "POWER";
        case SYSTEM_DEVICE_CLASS_STORAGE: return "STORAGE";
        case SYSTEM_DEVICE_CLASS_LOG_SINK: return "LOG_SINK";
        case SYSTEM_DEVICE_CLASS_OUTPUT: return "OUTPUT";
        case SYSTEM_DEVICE_CLASS_MISSION_ACTION: return "MISSION_ACTION";
        case SYSTEM_DEVICE_CLASS_TIME: return "TIME";
        default: return "SELF";
    }
}

static SystemConsoleIoBaseline *SystemConsole_IoBaselineFind(
    uint16_t physical_device_id)
{
    uint16_t index;

    for (index = 0U; index < SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX; index++)
    {
        if ((s_io_baselines[index].valid != 0U) &&
            (s_io_baselines[index].physical_device_id == physical_device_id))
        {
            return &s_io_baselines[index];
        }
    }
    return NULL;
}

static SystemConsoleIoBaseline *SystemConsole_IoBaselineSlotGet(
    uint16_t physical_device_id)
{
    SystemConsoleIoBaseline *baseline =
        SystemConsole_IoBaselineFind(physical_device_id);
    uint16_t index;

    if (baseline != NULL) { return baseline; }
    for (index = 0U; index < SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX; index++)
    {
        if (s_io_baselines[index].valid == 0U)
        {
            return &s_io_baselines[index];
        }
    }
    return NULL;
}

static void SystemConsole_IoDiagnosticsBaselineApply(
    SystemDeviceIoDiagnostics *diagnostics,
    const SystemDeviceIoDiagnostics *baseline)
{
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(baseline, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    diagnostics->rx_bytes -= baseline->rx_bytes;
    diagnostics->tx_bytes -= baseline->tx_bytes;
    diagnostics->rx_event_count -= baseline->rx_event_count;
    diagnostics->rx_idle_event_count -= baseline->rx_idle_event_count;
    diagnostics->rx_transfer_complete_count -=
        baseline->rx_transfer_complete_count;
    diagnostics->rx_discarded_bytes -= baseline->rx_discarded_bytes;
    diagnostics->uart_overrun_error_count -=
        baseline->uart_overrun_error_count;
    diagnostics->uart_framing_error_count -=
        baseline->uart_framing_error_count;
    diagnostics->uart_noise_error_count -= baseline->uart_noise_error_count;
    diagnostics->uart_parity_error_count -= baseline->uart_parity_error_count;
    diagnostics->dma_error_count -= baseline->dma_error_count;
    diagnostics->rx_restart_count -= baseline->rx_restart_count;
    diagnostics->rx_restart_failure_count -=
        baseline->rx_restart_failure_count;
    diagnostics->rx_discontinuity_count -=
        baseline->rx_discontinuity_count;
    diagnostics->integrity_error_count -= baseline->integrity_error_count;
    diagnostics->timeout_count -= baseline->timeout_count;
    diagnostics->transport_error_count -= baseline->transport_error_count;
    diagnostics->spi_error_count -= baseline->spi_error_count;
    diagnostics->spi_timeout_count -= baseline->spi_timeout_count;
    diagnostics->busy_timeout_count -= baseline->busy_timeout_count;
}

static SystemDeviceResult SystemConsole_IoDiagnosticsRawGet(
    SystemConsoleModule module,
    uint8_t instance_id,
    SystemDeviceIoDiagnostics *diagnostics,
    SystemDeviceDescriptor *owner_descriptor)
{
    if ((diagnostics == NULL) || (owner_descriptor == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (module == SYSTEM_CONSOLE_MODULE_SYSTEM)
    {
        if (SystemDescriptor_DeviceFind(SYSTEM_DEVICE_CLASS_CONSOLE, 0U,
            owner_descriptor) != SYSTEM_DEVICE_OK)
        {
            return SYSTEM_DEVICE_NOT_PRESENT;
        }
        return SystemConsoleDevice_IoDiagnosticsGet(diagnostics);
    }
    if (SystemConsole_ModuleIsIndexed(module) == 0U)
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    return ProjectDeviceInstance_IoDiagnosticsGet(
        SystemConsole_DeviceClassGet(module), instance_id,
        diagnostics, owner_descriptor);
}

static SystemDeviceResult SystemConsole_IoDiagnosticsGet(
    SystemConsoleModule module,
    uint8_t instance_id,
    SystemDeviceIoDiagnostics *diagnostics,
    SystemDeviceDescriptor *owner_descriptor)
{
    SystemConsoleIoBaseline *baseline;
    SystemDeviceResult result;

    result = SystemConsole_IoDiagnosticsRawGet(
        module, instance_id, diagnostics, owner_descriptor);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    baseline = SystemConsole_IoBaselineFind(
        owner_descriptor->physical_device_id);
    if (baseline != NULL)
    {
        SystemConsole_IoDiagnosticsBaselineApply(
            diagnostics, &baseline->diagnostics);
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SystemConsole_IoBaselineCapture(
    SystemConsoleModule module, uint8_t instance_id)
{
    SystemDeviceDescriptor owner_descriptor;
    SystemConsoleIoBaseline *slot;
    SystemConsoleIoBaseline baseline;
    SystemDeviceResult result;

    (void)memset(&baseline, 0, sizeof(baseline));
    SILVERSTAR_ASSERT_OBJECT(&baseline, SystemConsoleIoBaseline,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = SystemConsole_IoDiagnosticsRawGet(
        module, instance_id, &baseline.diagnostics, &owner_descriptor);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    baseline.physical_device_id = owner_descriptor.physical_device_id;
    baseline.owner_class = owner_descriptor.device_class;
    baseline.owner_instance_id = owner_descriptor.instance_id;
    if (owner_descriptor.device_class == SYSTEM_DEVICE_CLASS_IMU)
    {
        result = ProjectImuInstance_IoDetailGet(
            owner_descriptor.instance_id, &baseline.imu_detail);
        if (result != SYSTEM_DEVICE_OK) { return result; }
    }
    else if (owner_descriptor.device_class == SYSTEM_DEVICE_CLASS_GNSS)
    {
        result = ProjectGnssInstance_IoDetailGet(
            owner_descriptor.instance_id, &baseline.gnss_detail);
        if (result != SYSTEM_DEVICE_OK) { return result; }
    }
    slot = SystemConsole_IoBaselineSlotGet(baseline.physical_device_id);
    if (slot == NULL) { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    baseline.valid = 1U;
    *slot = baseline;
    return SYSTEM_DEVICE_OK;
}

static SystemConsoleExecuteResult SystemConsole_IoClearExecute(
    SystemConsoleModule module,
    const char *module_text,
    uint8_t instance_id,
    char *response,
    uint16_t capacity)
{
    SystemDeviceResult result = SystemConsole_IoBaselineCapture(
        module, instance_id);

    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            "IO_CLEAR", SystemConsole_DeviceErrorText(result), "DEVICE",
            (result == SYSTEM_DEVICE_UNSUPPORTED) ?
                SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED :
                SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    (void)CommonFormat_Print(response, capacity, "OK %s IO CLEAR", module_text);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static int SystemConsole_IoDiagnosticsWrite(
    const SystemDeviceIoDiagnostics *diagnostics,
    const SystemDeviceDescriptor *owner_descriptor,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(owner_descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    return CommonFormat_Print(response, capacity,
        "OK %s IO transport=%s owner=%s owner_instance=%u physical_device_id=%u supported_mask=0x%08lX valid_mask=0x%08lX rx_active=%u rx_bytes=%lu tx_bytes=%lu rx_events=%lu idle_events=%lu tc_events=%lu discarded=%lu ore=%lu framing=%lu noise=%lu parity=%lu dma_errors=%lu restarts=%lu restart_failures=%lu discontinuities=%lu integrity_errors=%lu timeouts=%lu transport_errors=%lu spi_errors=%lu spi_timeouts=%lu busy_timeouts=%lu",
        module_text, SystemConsole_IoTransportText(diagnostics->transport_type),
        SystemConsole_DeviceClassText(owner_descriptor->device_class),
        (unsigned int)owner_descriptor->instance_id,
        (unsigned int)owner_descriptor->physical_device_id,
        (unsigned long)diagnostics->supported_mask,
        (unsigned long)diagnostics->valid_mask,
        (unsigned int)diagnostics->rx_active,
        (unsigned long)diagnostics->rx_bytes,
        (unsigned long)diagnostics->tx_bytes,
        (unsigned long)diagnostics->rx_event_count,
        (unsigned long)diagnostics->rx_idle_event_count,
        (unsigned long)diagnostics->rx_transfer_complete_count,
        (unsigned long)diagnostics->rx_discarded_bytes,
        (unsigned long)diagnostics->uart_overrun_error_count,
        (unsigned long)diagnostics->uart_framing_error_count,
        (unsigned long)diagnostics->uart_noise_error_count,
        (unsigned long)diagnostics->uart_parity_error_count,
        (unsigned long)diagnostics->dma_error_count,
        (unsigned long)diagnostics->rx_restart_count,
        (unsigned long)diagnostics->rx_restart_failure_count,
        (unsigned long)diagnostics->rx_discontinuity_count,
        (unsigned long)diagnostics->integrity_error_count,
        (unsigned long)diagnostics->timeout_count,
        (unsigned long)diagnostics->transport_error_count,
        (unsigned long)diagnostics->spi_error_count,
        (unsigned long)diagnostics->spi_timeout_count,
        (unsigned long)diagnostics->busy_timeout_count);
}

static void SystemConsole_GnssIoBaselineApply(
    SystemGnssIoDetail *detail, const SystemConsoleIoBaseline *baseline)
{
    if (baseline == NULL) { return; }
    detail->ubx_frame_count -= baseline->gnss_detail.ubx_frame_count;
    detail->ubx_checksum_error_count -=
        baseline->gnss_detail.ubx_checksum_error_count;
    detail->nmea_sentence_count -= baseline->gnss_detail.nmea_sentence_count;
    detail->nmea_checksum_ok_count -= baseline->gnss_detail.nmea_checksum_ok_count;
    detail->nmea_checksum_error_count -=
        baseline->gnss_detail.nmea_checksum_error_count;
    detail->unknown_byte_count -= baseline->gnss_detail.unknown_byte_count;
    detail->parser_resync_count -= baseline->gnss_detail.parser_resync_count;
}

static void SystemConsole_ImuIoBaselineApply(
    SystemImuIoDetail *detail, const SystemConsoleIoBaseline *baseline)
{
    if (baseline == NULL) { return; }
    detail->valid_frame_count -= baseline->imu_detail.valid_frame_count;
    detail->checksum_error_count -= baseline->imu_detail.checksum_error_count;
    detail->parser_resync_count -= baseline->imu_detail.parser_resync_count;
}

static void SystemConsole_GnssIoDetailAppend(
    uint8_t instance_id,
    const SystemConsoleIoBaseline *baseline,
    char *response,
    uint16_t capacity,
    uint16_t used)
{
    SystemGnssIoDetail detail;

    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (ProjectGnssInstance_IoDetailGet(instance_id, &detail) !=
        SYSTEM_DEVICE_OK) { return; }
    SystemConsole_GnssIoBaselineApply(&detail, baseline);
    (void)CommonFormat_Print(&response[used], (uint16_t)(capacity - used),
        " ubx_frames=%lu ubx_checksum_errors=%lu nmea_sentences=%lu nmea_checksum_ok=%lu nmea_checksum_errors=%lu unknown_bytes=%lu parser_resyncs=%lu",
        (unsigned long)detail.ubx_frame_count,
        (unsigned long)detail.ubx_checksum_error_count,
        (unsigned long)detail.nmea_sentence_count,
        (unsigned long)detail.nmea_checksum_ok_count,
        (unsigned long)detail.nmea_checksum_error_count,
        (unsigned long)detail.unknown_byte_count,
        (unsigned long)detail.parser_resync_count);
}

static void SystemConsole_ImuIoDetailAppend(
    uint8_t instance_id,
    const SystemConsoleIoBaseline *baseline,
    char *response,
    uint16_t capacity,
    uint16_t used)
{
    SystemImuIoDetail detail;

    if (ProjectImuInstance_IoDetailGet(instance_id, &detail) !=
        SYSTEM_DEVICE_OK) { return; }
    SystemConsole_ImuIoBaselineApply(&detail, baseline);
    (void)CommonFormat_Print(&response[used], (uint16_t)(capacity - used),
        " valid_frames=%lu checksum_errors=%lu parser_resyncs=%lu",
        (unsigned long)detail.valid_frame_count,
        (unsigned long)detail.checksum_error_count,
        (unsigned long)detail.parser_resync_count);
}

static SystemConsoleExecuteResult SystemConsole_IoExecute(
    SystemConsoleModule module,
    const char *module_text,
    uint8_t instance_id,
    char *response,
    uint16_t capacity)
{
    SystemDeviceIoDiagnostics diagnostics;
    SystemDeviceDescriptor owner_descriptor;
    SystemConsoleIoBaseline *baseline;
    SystemDeviceResult result;
    int used;

    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    (void)memset(&owner_descriptor, 0, sizeof(owner_descriptor));
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(&owner_descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = SystemConsole_IoDiagnosticsGet(
        module, instance_id, &diagnostics, &owner_descriptor);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text, "IO",
            SystemConsole_DeviceErrorText(result), "DEVICE",
            (result == SYSTEM_DEVICE_UNSUPPORTED) ?
                SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED :
                SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    used = SystemConsole_IoDiagnosticsWrite(
        &diagnostics, &owner_descriptor, module_text, response, capacity);
    if ((used <= 0) || ((uint16_t)used >= capacity))
    {
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    baseline = SystemConsole_IoBaselineFind(
        owner_descriptor.physical_device_id);
    if (owner_descriptor.device_class == SYSTEM_DEVICE_CLASS_GNSS)
    {
        SystemConsole_GnssIoDetailAppend(owner_descriptor.instance_id,
            baseline, response, capacity, (uint16_t)used);
    }
    else if (owner_descriptor.device_class == SYSTEM_DEVICE_CLASS_IMU)
    {
        SystemConsole_ImuIoDetailAppend(owner_descriptor.instance_id,
            baseline, response, capacity, (uint16_t)used);
    }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemFlightExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemFlightRecoveryStatus flight;

    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "FLIGHT", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    if (SystemFlightRecovery_StatusGet(&flight) != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "FLIGHT", "NOT_READY", "FLIGHT_RECOVERY",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&flight, SystemFlightRecoveryStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM FLIGHT deploy_mask=0x%02lX matched_mask=0x%02lX deploy_triggered=%u tilt_deg=%.2f vz_mps=%.2f delay_ms=%lu landing_mode=%s landing_state=%s baro_valid=%u baro_age_ms=%lu baro_trigger_rate_mps=%.3f candidate_active=%u candidate_elapsed_ms=%lu candidate_baro_samples=%lu candidate_imu_samples=%lu baro_slope_mps=%.3f baro_span_m=%.3f gyro_norm_radps=%.3f accel_norm_mps2=%.3f accel_g_error_mps2=%.3f impact_capable=%u impact_armed=%u impact_threshold_mps2=%.2f",
        (unsigned long)flight.deploy_trigger_mask,
        (unsigned long)flight.deploy_matched_mask,
        (unsigned int)flight.deploy_triggered,
        (double)flight.deploy_tilt_angle_deg,
        (double)flight.deploy_vertical_velocity_mps,
        (unsigned long)flight.deploy_delay_ms,
        SystemFlightRecovery_LandingModeText(flight.landing_mode),
        SystemFlightRecovery_LandingStateText(flight.landing_state),
        (unsigned int)flight.barometer_valid,
        (unsigned long)flight.barometer_age_ms,
        (double)flight.barometer_trigger_rate_mps,
        (unsigned int)flight.landing_candidate_active,
        (unsigned long)flight.landing_candidate_elapsed_ms,
        (unsigned long)flight.landing_candidate_baro_count,
        (unsigned long)flight.landing_candidate_imu_count,
        (double)flight.landing_candidate_baro_slope_mps,
        (double)flight.landing_candidate_baro_span_m,
        (double)flight.landing_candidate_gyro_norm_radps,
        (double)flight.landing_candidate_accel_norm_mps2,
        (double)flight.landing_candidate_gravity_error_mps2,
        (unsigned int)flight.impact_capable,
        (unsigned int)flight.impact_armed,
        (double)flight.impact_threshold_mps2);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemConsoleExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    if ((subcommand != NULL) && (strcmp(subcommand, "IO") == 0))
    {
        return SystemConsole_IoExecute(SYSTEM_CONSOLE_MODULE_SYSTEM,
            "SYSTEM CONSOLE", 0U, response, capacity);
    }
    return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
        "CONSOLE", "BAD_COMMAND", "UNKNOWN_SUBCOMMAND",
        SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
}

static SystemConsoleExecuteResult SystemConsole_SystemStartResultWrite(
    char *response, uint16_t capacity)
{
    SystemLifecycleStartDiagnostic diagnostic;

    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((SystemLifecycle_GetLastStartDiagnostic(
            SYSTEM_START_SOURCE_CONSOLE, &diagnostic) == 0U) ||
        (diagnostic.response.request_id != s_console_start_request_id))
    {
        (void)CommonFormat_Print(response, capacity,
            "OK SYSTEM START RESULT state=PENDING request_id=%lu",
            (unsigned long)s_console_start_request_id);
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM START RESULT state=COMPLETE request_id=%lu result=%s reason=%s timestamp_us=%lu",
        (unsigned long)diagnostic.response.request_id,
        SystemLifecycle_StartResultText(diagnostic.response.result),
        SystemLifecycle_StartReasonText(diagnostic.response.reason),
        SystemConsole_TimestampDisplay(diagnostic.response.timestamp_us));
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemStartExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemLifecycleStartRequest request;
    SystemDeviceResult submit_result;

    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((subcommand != NULL) && (strcmp(subcommand, "RESULT") == 0))
    {
        return SystemConsole_SystemStartResultWrite(response, capacity);
    }
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "START", "BAD_COMMAND", "UNKNOWN_SUBCOMMAND",
            SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
    }
    request.source = SYSTEM_START_SOURCE_CONSOLE;
    request.request_id = ++s_console_start_request_id;
    submit_result = SystemLifecycle_SubmitStart(&request);
    if (submit_result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK SYSTEM START state=PENDING request_id=%lu",
            (unsigned long)request.request_id);
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", "START",
        SystemConsole_DeviceErrorText(submit_result),
        (submit_result == SYSTEM_DEVICE_BUSY) ?
            "REQUEST_PENDING" : "SUBMIT_FAILED",
        SYSTEM_CONSOLE_EXECUTE_FAILED);
}

static SystemConsoleExecuteResult SystemConsole_SystemStatusExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemHealthSnapshot health;

    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "STATUS", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    SystemHealth_GetSnapshot(&health);
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM STATUS state=%u ready=%u block=0x%08lX warn=0x%08lX attitude=%s",
        (unsigned int)SystemLifecycle_GetState(), (unsigned int)health.ready,
        (unsigned long)health.start_blocking_mask,
        (unsigned long)health.warning_mask,
        SystemHealth_AttitudeStatusText(health.attitude_status));
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemStackExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemTaskStackSnapshot stack;
    SystemDeviceResult result;

    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "STACK", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemTaskStack_SnapshotGet(&stack);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "STACK", SystemConsole_DeviceErrorText(result),
            "STACK_UNAVAILABLE", SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&stack, SystemTaskStackSnapshot,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM STACK unit=words valid_mask=0x%02lX DeviceTask=%lu/%lu InsTask=%lu/%lu EstimatorTask=%lu/%lu FlightTask=%lu/%lu LoggerTask=%lu/%lu SerialTask=%lu/%lu RadioTask=%lu/%lu",
        (unsigned long)stack.valid_mask,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_DEVICE].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_DEVICE].allocation_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_INS].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_INS].allocation_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_ESTIMATOR].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_ESTIMATOR].allocation_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_FLIGHT].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_FLIGHT].allocation_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_LOGGER].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_LOGGER].allocation_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_SERIAL].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_SERIAL].allocation_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_RADIO].high_water_mark_words,
        (unsigned long)stack.task[SYSTEM_TASK_STACK_RADIO].allocation_words);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemInfoExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "INFO", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM INFO project=SilverStar version=" SILVERSTAR_VERSION_STRING " profile=0x%08lX",
        (unsigned long)SystemProfile_Get()->profile_id);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemCapabilitiesExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemCapabilities capabilities;

    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "CAPABILITIES", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    SystemCapabilities_Get(&capabilities);
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM CAPABILITIES compiled=0x%08lX enabled=0x%08lX present=0x%08lX healthy=0x%08lX",
        (unsigned long)capabilities.compiled_mask,
        (unsigned long)capabilities.enabled_mask,
        (unsigned long)capabilities.present_mask,
        (unsigned long)capabilities.healthy_mask);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemProfileExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "PROFILE", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM PROFILE id=0x%08lX frozen=%u",
        (unsigned long)SystemProfile_Get()->profile_id,
        (unsigned int)SystemProfile_IsFrozen());
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemReadyExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemHealthSnapshot health;
    SystemEstimatorGnssDiagnostics gnss_diagnostics;
    SystemCalibrationStatus calibration;
    SystemAlignmentSummary alignment;

    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            "READY", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    SystemHealth_GetSnapshot(&health);
    (void)memset(&gnss_diagnostics, 0, sizeof(gnss_diagnostics));
    (void)memset(&calibration, 0, sizeof(calibration));
    (void)memset(&alignment, 0, sizeof(alignment));
    SILVERSTAR_ASSERT_OBJECT(&alignment, SystemAlignmentSummary,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)SystemEstimatorGnssDiagnostics_Get(
        &gnss_diagnostics, SystemTime_GetMonotonicUs());
    if (SystemAlignment_SummaryGet(&alignment) != SYSTEM_DEVICE_OK)
    { (void)memset(&alignment, 0, sizeof(alignment)); }
    if (SystemCalibration_StatusGet(&calibration) != SYSTEM_DEVICE_OK)
    { (void)memset(&calibration, 0, sizeof(calibration)); }
    (void)CommonFormat_Print(response, capacity,
        "OK SYSTEM READY ready=%u block=0x%08lX attitude_ready=%u attitude_reason=%s gnss_ready=%u gnss_origin_ready=%u gnss_fusion_enabled=%u alignment_ready=%u imu_alignment_ready=%u",
        (unsigned int)health.ready,
        (unsigned long)health.start_blocking_mask,
        (unsigned int)(health.attitude_status == SYSTEM_HEALTH_ATTITUDE_READY),
        SystemHealth_AttitudeStatusText(health.attitude_status),
        (unsigned int)gnss_diagnostics.gnss_ready,
        (unsigned int)gnss_diagnostics.origin_ready,
        (unsigned int)gnss_diagnostics.fusion_enabled,
        (unsigned int)alignment.ready,
        (unsigned int)calibration.ready);
    SystemConsole_AlignmentReadyFieldsAppend(&alignment, response, capacity);
    SystemConsole_TextAppend(response, capacity,
        " calibration_ready=%u calibration_mode=%s capability_required_for_air_start=1",
        (unsigned int)calibration.ready,
        SystemCalibration_ModeText(calibration.mode));
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemUnsupportedExecute(
    const char *command, const char *subcommand,
    char *response, uint16_t capacity)
{
    if ((strcmp(command, "SELFTEST") == 0) && (subcommand != NULL))
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            command, "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", command,
        "UNSUPPORTED", "NOT_IMPLEMENTED", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED);
}

static SystemConsoleExecuteResult SystemConsole_SystemExecute(
    const char *command,
    const char *subcommand,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (strcmp(command, "FLIGHT") == 0)
    { return SystemConsole_SystemFlightExecute(subcommand, response, capacity); }
    if (strcmp(command, "CONSOLE") == 0)
    { return SystemConsole_SystemConsoleExecute(subcommand, response, capacity); }
    if (strcmp(command, "START") == 0)
    { return SystemConsole_SystemStartExecute(subcommand, response, capacity); }
    if (strcmp(command, "STARTUP") == 0)
    { return SystemConsole_StartupExecute(subcommand, response, capacity); }
    if (strcmp(command, "STATUS") == 0)
    { return SystemConsole_SystemStatusExecute(subcommand, response, capacity); }
    if (strcmp(command, "STACK") == 0)
    { return SystemConsole_SystemStackExecute(subcommand, response, capacity); }
    if (strcmp(command, "INFO") == 0)
    { return SystemConsole_SystemInfoExecute(subcommand, response, capacity); }
    if (strcmp(command, "CAPABILITIES") == 0)
    {
        return SystemConsole_SystemCapabilitiesExecute(
            subcommand, response, capacity);
    }
    if (strcmp(command, "PROFILE") == 0)
    { return SystemConsole_SystemProfileExecute(subcommand, response, capacity); }
    if (strcmp(command, "READY") == 0)
    { return SystemConsole_SystemReadyExecute(subcommand, response, capacity); }
    if ((strcmp(command, "SELFTEST") == 0) ||
        (strcmp(command, "PARAM") == 0))
    {
        return SystemConsole_SystemUnsupportedExecute(
            command, subcommand, response, capacity);
    }
    return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", command,
                                    "BAD_COMMAND", "UNKNOWN",
                                    SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
}

static SystemCalibrationMode SystemConsole_CalibrationModeParse(
    const char *text)
{
    if ((text != NULL) && (strcmp(text, "NONE") == 0))
    {
        return SYSTEM_CALIBRATION_MODE_NONE;
    }
    if ((text != NULL) && (strcmp(text, "ONE_FACE") == 0))
    {
        return SYSTEM_CALIBRATION_MODE_ONE_FACE;
    }
    if ((text != NULL) && (strcmp(text, "SIX_FACE") == 0))
    {
        return SYSTEM_CALIBRATION_MODE_SIX_FACE;
    }
    return SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
}

static SystemCalibrationFace SystemConsole_CalibrationFaceParse(
    const char *text)
{
    if ((text != NULL) && (strcmp(text, "X+") == 0))
    { return SYSTEM_CALIBRATION_FACE_X_POSITIVE; }
    if ((text != NULL) && (strcmp(text, "X-") == 0))
    { return SYSTEM_CALIBRATION_FACE_X_NEGATIVE; }
    if ((text != NULL) && (strcmp(text, "Y+") == 0))
    { return SYSTEM_CALIBRATION_FACE_Y_POSITIVE; }
    if ((text != NULL) && (strcmp(text, "Y-") == 0))
    { return SYSTEM_CALIBRATION_FACE_Y_NEGATIVE; }
    if ((text != NULL) && (strcmp(text, "Z+") == 0))
    { return SYSTEM_CALIBRATION_FACE_Z_POSITIVE; }
    if ((text != NULL) && (strcmp(text, "Z-") == 0))
    { return SYSTEM_CALIBRATION_FACE_Z_NEGATIVE; }
    return SYSTEM_CALIBRATION_FACE_NONE;
}

static SystemConsoleExecuteResult SystemConsole_CalibrationStartExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemCalibrationStatus status;
    SystemCalibrationMode mode = SystemConsole_CalibrationModeParse(subcommand);
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (mode == SYSTEM_CALIBRATION_MODE_NOT_SELECTED)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", "START",
            "BAD_PARAM", "MODE", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemCalibration_Start(mode);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", "START",
            SystemConsole_DeviceErrorText(result),
            (result == SYSTEM_DEVICE_BAD_STATE) ?
                SystemConsole_LifecycleStateText(SystemLifecycle_GetState()) :
                "START_FAILED",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    result = SystemCalibration_StatusGet(&status);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", "START",
            SystemConsole_DeviceErrorText(result), "STATUS_FAILED",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK CAL START mode=%s state=%s ready=%u",
        SystemCalibration_ModeText(status.mode),
        SystemCalibration_StateText(status.state),
        (unsigned int)status.ready);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_CalibrationFaceExecute(
    const char *subcommand, char *response, uint16_t capacity)
{
    SystemCalibrationStatus status;
    SystemCalibrationFace face = SystemConsole_CalibrationFaceParse(subcommand);
    SystemDeviceResult result;
    SystemDeviceResult status_result;

    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (face == SYSTEM_CALIBRATION_FACE_NONE)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", "FACE",
            "BAD_PARAM", "FACE", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemCalibration_FaceCollect(face);
    status_result = SystemCalibration_StatusGet(&status);
    if (status_result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", "FACE",
            SystemConsole_DeviceErrorText(status_result), "STATUS_FAILED",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", "FACE",
            SystemConsole_DeviceErrorText(result),
            SystemCalibration_WaitReasonText(status.wait_reason),
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK CAL FACE face=%s accepted=1 state=%s completed_face_mask=0x%02X",
        SystemCalibration_FaceText(face),
        SystemCalibration_StateText(status.state),
        (unsigned int)status.completed_face_mask);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_CalibrationStopResetExecute(
    const char *command, const char *subcommand,
    char *response, uint16_t capacity)
{
    SystemCalibrationStatus status;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", command,
            "BAD_FORMAT", "TOKEN_COUNT", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = (strcmp(command, "STOP") == 0) ?
        SystemCalibration_Stop() : SystemCalibration_Reset();
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", command,
            SystemConsole_DeviceErrorText(result),
            (result == SYSTEM_DEVICE_BAD_STATE) ?
                SystemConsole_LifecycleStateText(SystemLifecycle_GetState()) :
                "ACTION_FAILED",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    result = SystemCalibration_StatusGet(&status);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", command,
            SystemConsole_DeviceErrorText(result), "STATUS_FAILED",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK CAL %s mode=%s state=%s ready=%u completed_face_mask=0x%02X",
        command, SystemCalibration_ModeText(status.mode),
        SystemCalibration_StateText(status.state), (unsigned int)status.ready,
        (unsigned int)status.completed_face_mask);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static void SystemConsole_CalibrationStatusWrite(
    const SystemCalibrationStatus *status, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK CAL STATUS mode=%s state=%s ready=%u current_face=%s last_face=%s last_face_result=%s completed_face_mask=0x%02X samples=%lu",
        SystemCalibration_ModeText(status->mode),
        SystemCalibration_StateText(status->state),
        (unsigned int)status->ready,
        SystemCalibration_FaceText(status->current_face),
        SystemCalibration_FaceText(status->last_face),
        SystemCalibration_FaceResultText(status->last_face_result),
        (unsigned int)status->completed_face_mask,
        (unsigned long)status->samples);
}

static void SystemConsole_CalibrationDetailWrite(
    const SystemCalibrationStatus *status, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK CAL DETAIL mode=%s state=%s ready=%u current_face=%s last_face=%s last_face_result=%s completed_face_mask=0x%02X samples=%lu reject_count=%lu retry_count=%lu wait_reason=%s accel_bias=[%.6f,%.6f,%.6f] accel_scale=[%.6f,%.6f,%.6f] gyro_bias=[%.6f,%.6f,%.6f] gyro_scale=[%.6f,%.6f,%.6f] face_xp_acc=[%.6f,%.6f,%.6f] face_xn_acc=[%.6f,%.6f,%.6f] face_yp_acc=[%.6f,%.6f,%.6f] face_yn_acc=[%.6f,%.6f,%.6f] face_zp_acc=[%.6f,%.6f,%.6f] face_zn_acc=[%.6f,%.6f,%.6f]",
        SystemCalibration_ModeText(status->mode),
        SystemCalibration_StateText(status->state),
        (unsigned int)status->ready,
        SystemCalibration_FaceText(status->current_face),
        SystemCalibration_FaceText(status->last_face),
        SystemCalibration_FaceResultText(status->last_face_result),
        (unsigned int)status->completed_face_mask,
        (unsigned long)status->samples,
        (unsigned long)status->reject_count,
        (unsigned long)status->retry_count,
        SystemCalibration_WaitReasonText(status->wait_reason),
        (double)status->correction.accel_bias_mps2[0],
        (double)status->correction.accel_bias_mps2[1],
        (double)status->correction.accel_bias_mps2[2],
        (double)status->correction.accel_scale[0],
        (double)status->correction.accel_scale[1],
        (double)status->correction.accel_scale[2],
        (double)status->correction.gyro_bias_radps[0],
        (double)status->correction.gyro_bias_radps[1],
        (double)status->correction.gyro_bias_radps[2],
        (double)status->correction.gyro_scale[0],
        (double)status->correction.gyro_scale[1],
        (double)status->correction.gyro_scale[2],
        (double)status->six_face_measurements.accel_mean_mps2[0][0],
        (double)status->six_face_measurements.accel_mean_mps2[0][1],
        (double)status->six_face_measurements.accel_mean_mps2[0][2],
        (double)status->six_face_measurements.accel_mean_mps2[1][0],
        (double)status->six_face_measurements.accel_mean_mps2[1][1],
        (double)status->six_face_measurements.accel_mean_mps2[1][2],
        (double)status->six_face_measurements.accel_mean_mps2[2][0],
        (double)status->six_face_measurements.accel_mean_mps2[2][1],
        (double)status->six_face_measurements.accel_mean_mps2[2][2],
        (double)status->six_face_measurements.accel_mean_mps2[3][0],
        (double)status->six_face_measurements.accel_mean_mps2[3][1],
        (double)status->six_face_measurements.accel_mean_mps2[3][2],
        (double)status->six_face_measurements.accel_mean_mps2[4][0],
        (double)status->six_face_measurements.accel_mean_mps2[4][1],
        (double)status->six_face_measurements.accel_mean_mps2[4][2],
        (double)status->six_face_measurements.accel_mean_mps2[5][0],
        (double)status->six_face_measurements.accel_mean_mps2[5][1],
        (double)status->six_face_measurements.accel_mean_mps2[5][2]);
}

static SystemConsoleExecuteResult SystemConsole_CalibrationStatusExecute(
    const char *command, const char *subcommand,
    char *response, uint16_t capacity)
{
    SystemCalibrationStatus status;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", command,
            "BAD_FORMAT", "TOKEN_COUNT", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemCalibration_StatusGet(&status);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity, "CAL", command,
            SystemConsole_DeviceErrorText(result), "STATUS_UNAVAILABLE",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    if (strcmp(command, "STATUS") == 0)
    { SystemConsole_CalibrationStatusWrite(&status, response, capacity); }
    else
    { SystemConsole_CalibrationDetailWrite(&status, response, capacity); }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_CalibrationExecute(
    const char *command,
    const char *subcommand,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (strcmp(command, "START") == 0)
    { return SystemConsole_CalibrationStartExecute(subcommand, response, capacity); }
    if (strcmp(command, "FACE") == 0)
    { return SystemConsole_CalibrationFaceExecute(subcommand, response, capacity); }
    if ((strcmp(command, "STOP") == 0) || (strcmp(command, "RESET") == 0))
    {
        return SystemConsole_CalibrationStopResetExecute(
            command, subcommand, response, capacity);
    }
    if ((strcmp(command, "STATUS") == 0) || (strcmp(command, "DETAIL") == 0))
    {
        return SystemConsole_CalibrationStatusExecute(
            command, subcommand, response, capacity);
    }
    return SystemConsole_ErrorWrite(response, capacity, "CAL", command,
        "BAD_COMMAND", "UNKNOWN", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
}

static SystemConsoleExecuteResult SystemConsole_AlignmentStartExecute(
    char *response, uint16_t capacity)
{
    SystemAlignmentStatus status;
    SystemDeviceResult result = SystemAlignment_Start();

    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ALIGN", "START",
            SystemConsole_DeviceErrorText(result),
            (result == SYSTEM_DEVICE_BAD_STATE) ?
                SystemConsole_LifecycleStateText(SystemLifecycle_GetState()) :
            ((result == SYSTEM_DEVICE_NOT_READY) ?
                "CALIBRATION_REQUIRED" : "START_FAILED"),
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    if (SystemAlignment_StatusGet(&status) != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ALIGN", "START", "NOT_READY",
            "STATUS_UNAVAILABLE", SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK ALIGN START accepted=1 state=%s ready=%u config=%s unavailable_mask=0x%08lX missing_adapter_mask=0x%08lX",
        SystemAlignment_StateText(status.state), (unsigned int)status.ready,
        SystemAlignment_ConfigResultText(status.config_result),
        (unsigned long)status.unavailable_mask,
        (unsigned long)status.missing_adapter_mask);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_AlignmentStopResetExecute(
    const char *command, char *response, uint16_t capacity)
{
    SystemDeviceResult result = (strcmp(command, "RESET") == 0) ?
        SystemAlignment_Reset() : SystemAlignment_Stop();
    const char *failure = (strcmp(command, "RESET") == 0) ?
        "RESET_FAILED" : "STOP_FAILED";

    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ALIGN", command,
            SystemConsole_DeviceErrorText(result),
            (result == SYSTEM_DEVICE_BAD_STATE) ?
                SystemConsole_LifecycleStateText(SystemLifecycle_GetState()) :
                failure,
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    (void)CommonFormat_Print(response, capacity,
        "OK ALIGN %s state=IDLE", command);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static void SystemConsole_AlignmentStatusWrite(
    const SystemAlignmentStatus *status, char *response, uint16_t capacity)
{
    const SystemAlignmentAttitudeStatus *attitude;

    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    attitude = &status->component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude;
    (void)CommonFormat_Print(response, capacity,
        "OK ALIGN STATUS state=%s ready=%u config=%s capability_mask=0x%08lX selected_mask=0x%08lX required_mask=0x%08lX ready_mask=0x%08lX unavailable_mask=0x%08lX missing_adapter_mask=0x%08lX stale_reason=%s attitude_algorithm=%u attitude_source=%s final_yaw_deg=%.3f known_yaw_deg=%.3f declination_deg=%.3f final_q_frozen=%u",
        SystemAlignment_StateText(status->state),
        (unsigned int)status->ready,
        SystemAlignment_ConfigResultText(status->config_result),
        (unsigned long)status->capability_mask,
        (unsigned long)status->selected_mask,
        (unsigned long)status->required_mask,
        (unsigned long)status->ready_mask,
        (unsigned long)status->unavailable_mask,
        (unsigned long)status->missing_adapter_mask,
        SystemAlignment_StaleReasonText(status->stale_reason),
        (unsigned int)attitude->algorithm,
        SystemAlignment_AttitudeSourceText(attitude->source),
        (double)attitude->final_yaw_deg, (double)attitude->known_yaw_deg,
        (double)attitude->magnetic_declination_deg,
        (unsigned int)attitude->final_quaternion_frozen);
    SystemConsole_AlignmentSourcesAppend(status, response, capacity, "");
}

static void SystemConsole_AlignmentDetailsAppend(
    const SystemAlignmentStatus *status, char *response, uint16_t capacity)
{
    uint32_t source;

    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (source = 0U; source < SYSTEM_ALIGNMENT_SOURCE_COUNT; source++)
    {
        char detail[384];

        if ((status->selected_mask & SYSTEM_ALIGNMENT_SOURCE_BIT(source)) == 0U)
        { continue; }
        if (SystemAlignment_SourceDetailFormat(status,
                (SystemAlignmentSourceId)source,
                detail, sizeof(detail)) == SYSTEM_DEVICE_OK)
        {
            SystemConsole_TextAppend(response, capacity, "\r\n%s", detail);
        }
    }
}

static void SystemConsole_AlignmentDetailWrite(
    const SystemAlignmentStatus *status, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK ALIGN DETAIL state=%s ready=%u config=%s capability_mask=0x%08lX selected_mask=0x%08lX required_mask=0x%08lX ready_mask=0x%08lX stale_reason=%s",
        SystemAlignment_StateText(status->state),
        (unsigned int)status->ready,
        SystemAlignment_ConfigResultText(status->config_result),
        (unsigned long)status->capability_mask,
        (unsigned long)status->selected_mask,
        (unsigned long)status->required_mask,
        (unsigned long)status->ready_mask,
        SystemAlignment_StaleReasonText(status->stale_reason));
    SystemConsole_AlignmentDetailsAppend(status, response, capacity);
}

static SystemConsoleExecuteResult SystemConsole_AlignmentQueryExecute(
    const char *command, char *response, uint16_t capacity)
{
    SystemAlignmentStatus status;
    SystemDeviceResult result = (strcmp(command, "DETAIL") == 0) ?
        SystemAlignment_DetailGet(&status) :
        SystemAlignment_StatusGet(&status);

    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ALIGN", command,
            SystemConsole_DeviceErrorText(result), "STATUS_UNAVAILABLE",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    if (strcmp(command, "STATUS") == 0)
    { SystemConsole_AlignmentStatusWrite(&status, response, capacity); }
    else
    { SystemConsole_AlignmentDetailWrite(&status, response, capacity); }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_AlignmentExecute(
    const char *command,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (strcmp(command, "START") == 0)
    { return SystemConsole_AlignmentStartExecute(response, capacity); }
    if ((strcmp(command, "RESET") == 0) || (strcmp(command, "STOP") == 0))
    {
        return SystemConsole_AlignmentStopResetExecute(
            command, response, capacity);
    }
    if ((strcmp(command, "STATUS") == 0) || (strcmp(command, "DETAIL") == 0))
    { return SystemConsole_AlignmentQueryExecute(command, response, capacity); }
    return SystemConsole_ErrorWrite(response, capacity, "ALIGN", command,
        "BAD_COMMAND", "UNKNOWN", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
}

static SystemConsoleExecuteResult SystemConsole_GnssConfigReadExecute(
    uint8_t instance_id,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SystemGnssHardwareConfig config;
    SystemDeviceResult result;

    (void)memset(&config, 0, sizeof(config));
    SILVERSTAR_ASSERT_OBJECT(&config, SystemGnssHardwareConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = ProjectGnssInstance_HardwareConfigRead(instance_id, &config);
    (void)CommonFormat_Print(response, capacity,
        "OK %s CONFIG READ source=HARDWARE read_result=%s valid_mask=0x%08lX baudrate=%lu protocol=%u protocol_in=0x%02X nav_pvt_rate=%u nav_pvt_known=%u navigation_rate=%u dynamic_model=%u constellation_mask=0x%08lX elapsed_ms=%lu response_result=%s failed_group=%s failed_key=0x%08lX nak_class=0x%02X nak_id=0x%02X response_length=%u transaction_id=%lu detailed_result=%s expected_class=0x%02X expected_id=0x%02X received_class=0x%02X received_id=0x%02X response_version=%u unsupported_mask=0x%08lX",
        module_text,
        SystemConsole_DeviceErrorText(result),
        (unsigned long)config.valid_mask,
        (unsigned long)config.baudrate,
        (unsigned int)config.output_protocol,
        (unsigned int)config.protocol_in,
        (unsigned int)config.nav_pvt_rate,
        (unsigned int)config.nav_pvt_known,
        (unsigned int)config.navigation_rate_hz,
        (unsigned int)config.dynamic_model,
        (unsigned long)config.constellation_mask,
        (unsigned long)config.elapsed_ms,
        SystemConsole_GnssConfigReadResultText(config.read_result),
        SystemConsole_GnssConfigReadGroupText(config.failed_group),
        (unsigned long)config.failed_key,
        (unsigned int)config.nak_class,
        (unsigned int)config.nak_id,
        (unsigned int)config.response_length,
        (unsigned long)config.transaction_id,
        SystemConsole_GnssTransactionDetailText(config.detailed_result),
        (unsigned int)config.expected_class,
        (unsigned int)config.expected_id,
        (unsigned int)config.received_class,
        (unsigned int)config.received_id,
        (unsigned int)config.response_version,
        (unsigned long)config.unsupported_mask);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_GnssNavSatExecute(
    uint8_t instance_id,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SystemGnssSatelliteDiagnostics diagnostics;
    SystemDeviceResult result;

    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemGnssSatelliteDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = ProjectGnssInstance_SatelliteDiagnosticsRead(
        instance_id, &diagnostics);
    (void)CommonFormat_Print(response, capacity,
        "OK %s NAV SAT read_result=%s supported_mask=0x%08lX valid_mask=0x%08lX sequence=%lu satellite_count=%u used_count=%u average_cno_dbhz=%u maximum_cno_dbhz=%u average_quality=%u fresh=%u transaction_id=%lu response_result=%s detailed_result=%s response_length=%u expected_class=0x%02X expected_id=0x%02X received_class=0x%02X received_id=0x%02X expected_ck_a=0x%02X expected_ck_b=0x%02X received_ck_a=0x%02X received_ck_b=0x%02X",
        module_text,
        SystemConsole_DeviceErrorText(result),
        (unsigned long)diagnostics.supported_fields,
        (unsigned long)diagnostics.valid_fields,
        (unsigned long)diagnostics.sequence,
        (unsigned int)diagnostics.satellite_count,
        (unsigned int)diagnostics.used_count,
        (unsigned int)diagnostics.average_cno_dbhz,
        (unsigned int)diagnostics.maximum_cno_dbhz,
        (unsigned int)diagnostics.average_quality,
        (unsigned int)diagnostics.fresh,
        (unsigned long)diagnostics.transaction_id,
        SystemConsole_GnssConfigReadResultText(diagnostics.read_result),
        SystemConsole_GnssTransactionDetailText(
            diagnostics.detailed_result),
        (unsigned int)diagnostics.response_length,
        (unsigned int)diagnostics.expected_class,
        (unsigned int)diagnostics.expected_id,
        (unsigned int)diagnostics.received_class,
        (unsigned int)diagnostics.received_id,
        (unsigned int)diagnostics.expected_ck_a,
        (unsigned int)diagnostics.expected_ck_b,
        (unsigned int)diagnostics.received_ck_a,
        (unsigned int)diagnostics.received_ck_b);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_GnssMonRfExecute(
    uint8_t instance_id,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SystemGnssRfDiagnostics diagnostics;
    SystemDeviceResult result;

    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemGnssRfDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = ProjectGnssInstance_RfDiagnosticsRead(
        instance_id, &diagnostics);
    (void)CommonFormat_Print(response, capacity,
        "OK %s MON RF read_result=%s supported_mask=0x%08lX valid_mask=0x%08lX sequence=%lu rf_block_count=%u antenna_status=%u antenna_power=%u jamming_indicator=%u noise_per_ms=%u agc_count=%u fresh=%u transaction_id=%lu response_result=%s detailed_result=%s response_length=%u jamming_state=%u cw_suppression=%u",
        module_text,
        SystemConsole_DeviceErrorText(result),
        (unsigned long)diagnostics.supported_fields,
        (unsigned long)diagnostics.valid_fields,
        (unsigned long)diagnostics.sequence,
        (unsigned int)diagnostics.rf_block_count,
        (unsigned int)diagnostics.antenna_status,
        (unsigned int)diagnostics.antenna_power,
        (unsigned int)diagnostics.jamming_indicator,
        (unsigned int)diagnostics.noise_per_ms,
        (unsigned int)diagnostics.agc_count,
        (unsigned int)diagnostics.fresh,
        (unsigned long)diagnostics.transaction_id,
        SystemConsole_GnssConfigReadResultText(diagnostics.read_result),
        SystemConsole_GnssTransactionDetailText(
            diagnostics.detailed_result),
        (unsigned int)diagnostics.response_length,
        (unsigned int)diagnostics.jamming_state,
        (unsigned int)diagnostics.cw_suppression);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_TimeExecute(
    const char *command,
    char *response,
    uint16_t capacity)
{
    if (strcmp(command, "STATUS") != 0)
    {
        return SystemConsole_ErrorWrite(response, capacity, "TIME", command,
                                        "BAD_COMMAND", "UNKNOWN",
                                        SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
    }
    (void)CommonFormat_Print(response, capacity,
                   "OK TIME STATUS monotonic_us=%lu mission_started=%u mission_us=%lu",
                   SystemConsole_TimestampDisplay(
                       SystemTime_GetMonotonicUs()),
                   (unsigned int)SystemTime_IsMissionStarted(),
                   SystemConsole_TimestampDisplay(
                       SystemTime_GetMissionUs()));
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_DeviceConfigExecute(
    SystemConsoleModule module, const char *module_text,
    uint8_t instance_id, const char *subcommand,
    char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(module_text, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (subcommand == NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            "CONFIG", "BAD_FORMAT", "SUBCOMMAND_REQUIRED",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    if (strcmp(subcommand, "SHOW") == 0)
    {
        return SystemConsole_ConfigShowExecute(
            module, module_text, instance_id, response, capacity);
    }
    if ((module == SYSTEM_CONSOLE_MODULE_GNSS) &&
        (strcmp(subcommand, "READ") == 0))
    {
        return SystemConsole_GnssConfigReadExecute(
            instance_id, module_text, response, capacity);
    }
    if (strcmp(subcommand, "READ") == 0)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            "CONFIG_READ", "UNSUPPORTED", "HARDWARE_READ",
            SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED);
    }
    if ((strcmp(subcommand, "VERIFY") == 0) ||
        (strcmp(subcommand, "APPLY") == 0))
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            (strcmp(subcommand, "VERIFY") == 0) ?
                "CONFIG_VERIFY" : "CONFIG_APPLY",
            "UNSUPPORTED", "DEVICE_OPERATION",
            SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED);
    }
    return SystemConsole_ErrorWrite(response, capacity, module_text,
        "CONFIG", "BAD_COMMAND", "UNKNOWN_SUBCOMMAND",
        SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
}

static SystemConsoleExecuteResult SystemConsole_DeviceIoExecute(
    SystemConsoleModule module, const char *module_text,
    uint8_t instance_id, const char *subcommand,
    char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(module_text, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((subcommand != NULL) && (strcmp(subcommand, "CLEAR") == 0))
    {
        return SystemConsole_IoClearExecute(
            module, module_text, instance_id, response, capacity);
    }
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            "IO", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    return SystemConsole_IoExecute(
        module, module_text, instance_id, response, capacity);
}

static SystemConsoleExecuteResult SystemConsole_DeviceInfoExecute(
    SystemConsoleModule module, const char *module_text,
    uint8_t instance_id, const char *subcommand,
    char *response, uint16_t capacity)
{
    SystemDeviceInfo info;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(module_text, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            "INFO", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemConsole_InfoGet(module, instance_id, &info);
    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s INFO device=%s model=%s driver=%s",
            module_text, info.device_name, info.model_name,
            info.driver_version);
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    return SystemConsole_ErrorWrite(response, capacity, module_text, "INFO",
        SystemConsole_DeviceErrorText(result), "DEVICE",
        (result == SYSTEM_DEVICE_UNSUPPORTED) ?
            SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED : SYSTEM_CONSOLE_EXECUTE_FAILED);
}

static SystemConsoleExecuteResult SystemConsole_DeviceCapabilitiesExecute(
    SystemConsoleModule module, const char *module_text,
    uint8_t instance_id, const char *subcommand,
    char *response, uint16_t capacity)
{
    uint32_t capability_mask;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT_OBJECT(module_text, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            "CAPABILITIES", "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemConsole_CapabilitiesGet(
        module, instance_id, &capability_mask);
    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s CAPABILITIES mask=0x%08lX",
            module_text, (unsigned long)capability_mask);
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    return SystemConsole_ErrorWrite(response, capacity, module_text,
        "CAPABILITIES", SystemConsole_DeviceErrorText(result), "DEVICE",
        (result == SYSTEM_DEVICE_UNSUPPORTED) ?
            SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED : SYSTEM_CONSOLE_EXECUTE_FAILED);
}

static SystemConsoleExecuteResult SystemConsole_DeviceExecute(
    SystemConsoleModule module,
    const char *module_text,
    uint8_t instance_id,
    const char *command,
    const char *subcommand,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(command, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (strcmp(command, "STATUS") == 0)
    {
        if (subcommand != NULL)
        {
            return SystemConsole_ErrorWrite(response, capacity, module_text,
                command, "BAD_FORMAT", "TOKEN_COUNT",
                SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
        }
        return SystemConsole_HealthExecute(
            module, module_text, instance_id, command, response, capacity);
    }
    if (strcmp(command, "CONFIG") == 0)
    {
        return SystemConsole_DeviceConfigExecute(
            module, module_text, instance_id, subcommand, response, capacity);
    }
    if (strcmp(command, "IO") == 0)
    {
        return SystemConsole_DeviceIoExecute(
            module, module_text, instance_id, subcommand, response, capacity);
    }
    if (strcmp(command, "INFO") == 0)
    {
        return SystemConsole_DeviceInfoExecute(
            module, module_text, instance_id, subcommand, response, capacity);
    }
    if (strcmp(command, "CAPABILITIES") == 0)
    {
        return SystemConsole_DeviceCapabilitiesExecute(
            module, module_text, instance_id, subcommand, response, capacity);
    }
    if (strcmp(command, "SELFTEST") == 0)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            command, "UNSUPPORTED", "OWNER_TASK_OPERATION",
            SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED);
    }
    if (strcmp(command, "PARAM") == 0)
    {
        return SystemConsole_ErrorWrite(response, capacity, module_text,
            command, "UNSUPPORTED", "NO_PUBLIC_PARAMETER",
            SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED);
    }
    return SystemConsole_ErrorWrite(response, capacity, module_text,
        command, "BAD_COMMAND", "UNKNOWN",
        SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
}

typedef struct
{
    char hacc_mm[24];
    char vacc_mm[24];
    char sacc_mmps[24];
    char fix_type[16];
    char fix_ok[16];
    char satellite_count[16];
    char latitude_e7[24];
    char longitude_e7[24];
    char height_mm[24];
    char age_text[24];
} SystemConsoleGnssSampleFields;

static void SystemConsole_GnssAccuracyFieldsFormat(
    const SystemGnssSample *sample, SystemConsoleGnssSampleFields *fields)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_FieldFloatFormat(fields->hacc_mm, sizeof(fields->hacc_mm),
        (uint8_t)((sample->supported_fields &
                   SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY) != 0U),
        (uint8_t)((sample->valid_fields &
                   SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY) != 0U),
        sample->horizontal_accuracy_m, 1000.0f);
    SystemConsole_FieldFloatFormat(fields->vacc_mm, sizeof(fields->vacc_mm),
        (uint8_t)((sample->supported_fields &
                   SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY) != 0U),
        (uint8_t)((sample->valid_fields &
                   SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY) != 0U),
        sample->vertical_accuracy_m, 1000.0f);
    SystemConsole_FieldFloatFormat(fields->sacc_mmps, sizeof(fields->sacc_mmps),
        (uint8_t)((sample->supported_fields &
                   SYSTEM_GNSS_FIELD_SPEED_ACCURACY) != 0U),
        (uint8_t)((sample->valid_fields &
                   SYSTEM_GNSS_FIELD_SPEED_ACCURACY) != 0U),
        sample->speed_accuracy_mps, 1000.0f);
}

static void SystemConsole_GnssFixFieldsFormat(
    const SystemGnssSample *sample, SystemConsoleGnssSampleFields *fields)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_FieldUnsignedFormat(fields->fix_type,
        sizeof(fields->fix_type),
        (uint8_t)((sample->supported_fields & SYSTEM_GNSS_FIELD_FIX_TYPE) != 0U),
        (uint8_t)((sample->valid_fields & SYSTEM_GNSS_FIELD_FIX_TYPE) != 0U),
        (unsigned long)sample->fix_type);
    SystemConsole_FieldUnsignedFormat(fields->fix_ok, sizeof(fields->fix_ok),
        (uint8_t)((sample->supported_fields & SYSTEM_GNSS_FIELD_FIX_OK) != 0U),
        (uint8_t)((sample->valid_fields & SYSTEM_GNSS_FIELD_FIX_OK) != 0U),
        (unsigned long)sample->fix_ok);
    SystemConsole_FieldUnsignedFormat(fields->satellite_count,
        sizeof(fields->satellite_count),
        (uint8_t)((sample->supported_fields &
                   SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U),
        (uint8_t)((sample->valid_fields &
                   SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U),
        (unsigned long)sample->satellite_count);
}

static void SystemConsole_GnssPositionFieldsFormat(
    const SystemGnssSample *sample, SystemConsoleGnssSampleFields *fields)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_FieldSignedFormat(fields->latitude_e7,
        sizeof(fields->latitude_e7),
        (uint8_t)((sample->supported_fields & SYSTEM_GNSS_FIELD_POSITION) != 0U),
        (uint8_t)((sample->valid_fields & SYSTEM_GNSS_FIELD_POSITION) != 0U),
        (long)sample->latitude_e7);
    SystemConsole_FieldSignedFormat(fields->longitude_e7,
        sizeof(fields->longitude_e7),
        (uint8_t)((sample->supported_fields & SYSTEM_GNSS_FIELD_POSITION) != 0U),
        (uint8_t)((sample->valid_fields & SYSTEM_GNSS_FIELD_POSITION) != 0U),
        (long)sample->longitude_e7);
    SystemConsole_FieldSignedFormat(fields->height_mm, sizeof(fields->height_mm),
        (uint8_t)((sample->supported_fields & SYSTEM_GNSS_FIELD_HEIGHT) != 0U),
        (uint8_t)((sample->valid_fields & SYSTEM_GNSS_FIELD_HEIGHT) != 0U),
        (long)sample->ellipsoid_height_mm);
}

static void SystemConsole_GnssSampleFieldsFormat(
    const SystemGnssSample *sample, SystemConsoleGnssSampleFields *fields)
{
    uint64_t now_us = SystemTime_GetMonotonicUs();
    uint64_t age_ms = UINT64_MAX;

    SILVERSTAR_ASSERT_OBJECT(fields, SystemConsoleGnssSampleFields,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((sample->sample_timestamp_us != 0U) &&
        (sample->sample_timestamp_us <= now_us))
    { age_ms = (now_us - sample->sample_timestamp_us) / 1000ULL; }
    SystemConsole_GnssAccuracyFieldsFormat(sample, fields);
    SystemConsole_GnssFixFieldsFormat(sample, fields);
    SystemConsole_GnssPositionFieldsFormat(sample, fields);
    SystemConsole_AgeFormat(fields->age_text, sizeof(fields->age_text), age_ms);
}

static void SystemConsole_GnssSampleDetailWrite(
    const SystemDeviceInfo *info,
    const SystemGnssSample *sample,
    const SystemConsoleGnssSampleFields *fields,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK %s SAMPLE DETAIL device=%s model=%s supported_mask=0x%08lX valid_mask=0x%08lX fix_type=%s fix_ok=%s num_sv=%s lat_e7=%s lon_e7=%s height_mm=%s hacc_mm=%s vacc_mm=%s sacc_mmps=%s age_ms=%s position_usable=%u velocity_mask=0x%02X position_reject_mask=0x%08lX velocity_reject_mask=0x%08lX quality_degraded=%u",
        module_text,
        (info->device_name != NULL) ? info->device_name : "UNKNOWN",
        (info->model_name != NULL) ? info->model_name : "UNKNOWN",
        (unsigned long)sample->supported_fields,
        (unsigned long)sample->valid_fields,
        fields->fix_type, fields->fix_ok, fields->satellite_count,
        fields->latitude_e7, fields->longitude_e7, fields->height_mm,
        fields->hacc_mm, fields->vacc_mm, fields->sacc_mmps, fields->age_text,
        (unsigned int)sample->position_usable,
        (unsigned int)sample->velocity_valid_mask,
        (unsigned long)sample->position_reject_mask,
        (unsigned long)sample->velocity_reject_mask,
        (unsigned int)sample->quality_degraded);
}

static SystemConsoleExecuteResult SystemConsole_GnssSampleDetailExecute(
    uint8_t instance_id,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SystemConsoleGnssSampleFields fields;
    SystemDeviceInfo info;
    SystemGnssSample sample;
    SystemDeviceResult result;

    (void)memset(&info, 0, sizeof(info));
    (void)memset(&fields, 0, sizeof(fields));
    SILVERSTAR_ASSERT_OBJECT(&fields, SystemConsoleGnssSampleFields,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)ProjectDeviceInstance_InfoGet(
        SYSTEM_DEVICE_CLASS_GNSS, instance_id, &info);
    result = ProjectGnssInstance_LatestSampleGet(instance_id, &sample);
    if (result != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, module_text, "SAMPLE_DETAIL",
            SystemConsole_DeviceErrorText(result), "DEVICE",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SystemConsole_GnssSampleFieldsFormat(&sample, &fields);
    SystemConsole_GnssSampleDetailWrite(
        &info, &sample, &fields, module_text, response, capacity);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

typedef struct
{
    SystemDeviceInfo info;
    SystemDeviceHealth health;
    SystemBarometerSample sample;
    SystemDeviceResult sample_result;
    SystemDeviceResult health_result;
    SystemConsoleSensorStatus status;
    uint64_t now_us;
    uint64_t age_ms;
    uint32_t supported_fields;
    uint32_t valid_fields;
    float altitude_m;
    char pressure_pa[24];
    char temperature_c[24];
    char altitude_text[24];
    char age_text[24];
    uint8_t supported;
    uint8_t present;
    uint8_t configured;
    uint8_t sample_valid;
    uint8_t sample_fresh;
} SystemConsoleBarometerSampleView;

static void SystemConsole_BarometerSampleFreshnessUpdate(
    SystemConsoleBarometerSampleView *view)
{
    SILVERSTAR_ASSERT_OBJECT(view, SystemConsoleBarometerSampleView,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (view->sample_result != SYSTEM_DEVICE_OK) { return; }
    view->supported_fields = view->sample.supported_fields;
    view->valid_fields = view->sample.valid_fields;
    if ((view->sample.sample_timestamp_us != 0U) &&
        (view->sample.sample_timestamp_us <= view->now_us))
    {
        view->age_ms = (view->now_us -
            view->sample.sample_timestamp_us) / 1000ULL;
        view->sample_fresh = (uint8_t)((view->now_us -
            view->sample.sample_timestamp_us) <=
            SYSTEM_ESTIMATOR_MEASUREMENT_MAX_AGE_US);
    }
    view->sample_valid = (uint8_t)(SystemBarometer_AltitudeResolve(
        &view->sample, &view->altitude_m) == SYSTEM_DEVICE_OK);
}

static void SystemConsole_BarometerSampleStateUpdate(
    SystemConsoleBarometerSampleView *view)
{
    SILVERSTAR_ASSERT_OBJECT(view, SystemConsoleBarometerSampleView,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (view->health_result != SYSTEM_DEVICE_OK)
    { view->status = SYSTEM_CONSOLE_SENSOR_FAILED; }
    else if (view->present == 0U)
    { view->status = SYSTEM_CONSOLE_SENSOR_NOT_PRESENT; }
    else if (view->configured == 0U)
    { view->status = SYSTEM_CONSOLE_SENSOR_NOT_CONFIGURED; }
    else if (view->sample_result == SYSTEM_DEVICE_NOT_READY)
    { view->status = SYSTEM_CONSOLE_SENSOR_NOT_READY; }
    else if (view->sample_result != SYSTEM_DEVICE_OK)
    { view->status = SYSTEM_CONSOLE_SENSOR_FAILED; }
    else if (view->sample_fresh == 0U)
    { view->status = SYSTEM_CONSOLE_SENSOR_STALE; }
    else if (view->sample_valid == 0U)
    { view->status = SYSTEM_CONSOLE_SENSOR_INVALID; }
    else
    { view->status = SYSTEM_CONSOLE_SENSOR_OK; }
}

static void SystemConsole_BarometerSampleCollect(
    uint8_t instance_id, SystemConsoleBarometerSampleView *view)
{
    SystemDeviceResult capability_result;

    (void)memset(view, 0, sizeof(*view));
    SILVERSTAR_ASSERT_OBJECT(view, SystemConsoleBarometerSampleView,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    view->now_us = SystemTime_GetMonotonicUs();
    view->age_ms = UINT64_MAX;
    capability_result = ProjectDeviceInstance_CapabilitiesGet(
        SYSTEM_DEVICE_CLASS_BAROMETER, instance_id,
        &view->supported_fields);
    view->supported = (uint8_t)(capability_result == SYSTEM_DEVICE_OK);
    if (view->supported == 0U)
    {
        view->status = SYSTEM_CONSOLE_SENSOR_UNSUPPORTED;
        view->sample_result = SYSTEM_DEVICE_UNSUPPORTED;
        view->health_result = SYSTEM_DEVICE_UNSUPPORTED;
        return;
    }
    (void)ProjectDeviceInstance_InfoGet(
        SYSTEM_DEVICE_CLASS_BAROMETER, instance_id, &view->info);
    view->health_result = ProjectDeviceInstance_HealthGet(
        SYSTEM_DEVICE_CLASS_BAROMETER, instance_id, &view->health);
    view->sample_result = ProjectBarometerInstance_LatestSampleGet(
        instance_id, &view->sample);
    view->present = 1U;
    view->configured = (uint8_t)((view->health.initialized != 0U) &&
                                 (view->health.started != 0U));
    SystemConsole_BarometerSampleFreshnessUpdate(view);
    SystemConsole_BarometerSampleStateUpdate(view);
}

static void SystemConsole_BarometerSampleFieldsFormat(
    SystemConsoleBarometerSampleView *view)
{
    SILVERSTAR_ASSERT_OBJECT(view, SystemConsoleBarometerSampleView,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_FieldFloatFormat(view->pressure_pa,
        sizeof(view->pressure_pa),
        (uint8_t)((view->supported_fields & SYSTEM_BARO_FIELD_PRESSURE) != 0U),
        (uint8_t)((view->valid_fields & SYSTEM_BARO_FIELD_PRESSURE) != 0U),
        view->sample.pressure_pa, 1.0f);
    SystemConsole_FieldFloatFormat(view->temperature_c,
        sizeof(view->temperature_c),
        (uint8_t)((view->supported_fields &
                   SYSTEM_BARO_FIELD_TEMPERATURE) != 0U),
        (uint8_t)((view->valid_fields & SYSTEM_BARO_FIELD_TEMPERATURE) != 0U),
        view->sample.temperature_c, 1.0f);
    SystemConsole_FieldFloatFormat(view->altitude_text,
        sizeof(view->altitude_text),
        (uint8_t)((view->supported_fields &
            (SYSTEM_BARO_FIELD_ALTITUDE | SYSTEM_BARO_FIELD_PRESSURE)) != 0U),
        view->sample_valid, view->altitude_m, 1.0f);
    SystemConsole_AgeFormat(view->age_text, sizeof(view->age_text),
                            view->age_ms);
}

static void SystemConsole_BarometerSampleDetailWrite(
    const SystemConsoleBarometerSampleView *view,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(view, SystemConsoleBarometerSampleView,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK %s SAMPLE DETAIL device=%s model=%s supported=%u present=%u configured=%u supported_mask=0x%08lX valid_mask=0x%08lX sample_valid=%u sample_fresh=%u sample_age_ms=%s pressure_pa=%s temperature_c=%s altitude_m=%s status=%s",
        module_text,
        (view->info.device_name != NULL) ? view->info.device_name : "NONE",
        (view->info.model_name != NULL) ? view->info.model_name : "NONE",
        (unsigned int)view->supported, (unsigned int)view->present,
        (unsigned int)view->configured,
        (unsigned long)view->supported_fields,
        (unsigned long)view->valid_fields,
        (unsigned int)view->sample_valid,
        (unsigned int)view->sample_fresh,
        view->age_text, view->pressure_pa, view->temperature_c,
        view->altitude_text, SystemConsole_SensorStatusText(view->status));
}

static SystemConsoleExecuteResult SystemConsole_BarometerSampleDetailExecute(
    uint8_t instance_id,
    const char *module_text,
    char *response,
    uint16_t capacity)
{
    SystemConsoleBarometerSampleView view;

    SystemConsole_BarometerSampleCollect(instance_id, &view);
    SystemConsole_BarometerSampleFieldsFormat(&view);
    SystemConsole_BarometerSampleDetailWrite(
        &view, module_text, response, capacity);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static const char *SystemConsole_BarometerOriginStateText(
    SystemEstimatorBaroOriginState state)
{
    switch (state)
    {
        case SYSTEM_ESTIMATOR_BARO_ORIGIN_UNAVAILABLE: return "UNAVAILABLE";
        case SYSTEM_ESTIMATOR_BARO_ORIGIN_COLLECTING: return "COLLECTING";
        case SYSTEM_ESTIMATOR_BARO_ORIGIN_READY: return "READY";
        case SYSTEM_ESTIMATOR_BARO_ORIGIN_FROZEN: return "FROZEN";
        default: return "UNAVAILABLE";
    }
}

static const char *SystemConsole_BarometerUpdateStateText(
    SystemEstimatorBaroUpdateState state)
{
    SILVERSTAR_ASSERT_OBJECT(&state, SystemEstimatorBaroUpdateState,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (state)
    {
        case SYSTEM_ESTIMATOR_BARO_UPDATE_NONE: return "NONE";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED: return "ACCEPTED";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_SOFTENED: return "SOFTENED";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_REJECTED: return "REJECTED";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_NO_SAMPLE: return "NO_SAMPLE";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_UNSUPPORTED: return "UNSUPPORTED";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_NOT_READY: return "NOT_READY";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_STALE: return "STALE";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_ORIGIN_NOT_READY:
            return "ORIGIN_NOT_READY";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_INVALID: return "INVALID";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_DISABLED: return "DISABLED";
        case SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP:
            return "WAIT_STATE_CATCHUP";
        default: return "NONE";
    }
}

static const char *SystemConsole_BarometerSkipReasonText(
    SystemEstimatorBaroSkipReason reason)
{
    switch (reason)
    {
        case SYSTEM_ESTIMATOR_BARO_SKIP_NONE: return "NONE";
        case SYSTEM_ESTIMATOR_BARO_SKIP_NO_SAMPLE: return "NO_SAMPLE";
        case SYSTEM_ESTIMATOR_BARO_SKIP_UNSUPPORTED: return "UNSUPPORTED";
        case SYSTEM_ESTIMATOR_BARO_SKIP_NOT_READY: return "NOT_READY";
        case SYSTEM_ESTIMATOR_BARO_SKIP_STALE: return "STALE";
        case SYSTEM_ESTIMATOR_BARO_SKIP_ORIGIN_NOT_READY:
            return "ORIGIN_NOT_READY";
        case SYSTEM_ESTIMATOR_BARO_SKIP_INVALID: return "INVALID";
        case SYSTEM_ESTIMATOR_BARO_SKIP_DISABLED: return "DISABLED";
        case SYSTEM_ESTIMATOR_BARO_SKIP_WAIT_STATE_CATCHUP:
            return "WAIT_STATE_CATCHUP";
        default: return "NONE";
    }
}

static SystemConsoleExecuteResult SystemConsole_EstimatorBarometerExecute(
    char *response,
    uint16_t capacity)
{
    SystemEstimatorBaroDiagnostics diagnostics;
    char origin_pressure_pa[24];
    char sample_age_text[24];
    char update_age_text[24];

    if (SystemEstimatorBaroDiagnostics_Get(
            &diagnostics, SystemTime_GetMonotonicUs()) == 0U)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ESTIMATOR", "BARO",
            "NOT_READY", "DIAGNOSTICS",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemEstimatorBaroDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_FieldFloatFormat(
        origin_pressure_pa, sizeof(origin_pressure_pa),
        diagnostics.origin_pressure_valid,
        diagnostics.origin_pressure_valid,
        diagnostics.origin_pressure_pa, 1.0f);
    SystemConsole_AgeFormat(
        sample_age_text, sizeof(sample_age_text),
        (diagnostics.sample_age_ms == UINT32_MAX) ?
            UINT64_MAX : (uint64_t)diagnostics.sample_age_ms);
    SystemConsole_AgeFormat(
        update_age_text, sizeof(update_age_text),
        (diagnostics.last_update_age_ms == UINT32_MAX) ?
            UINT64_MAX : (uint64_t)diagnostics.last_update_age_ms);
    (void)CommonFormat_Print(response, capacity,
        "OK ESTIMATOR BARO source_supported=%u sample_valid=%u sample_age_ms=%s origin_state=%s origin_sample_count=%lu origin_required_count=%lu origin_altitude_m=%.3f origin_pressure_pa=%s relative_altitude_m=%.3f measurement_variance=%.3f last_update_state=%s last_innovation=%.3f last_innovation_variance=%.3f last_nis=%.3f accepted_count=%lu softened_count=%lu rejected_count=%lu skipped_count=%lu last_skip_reason=%s last_update_age_ms=%s",
        (unsigned int)diagnostics.source_supported,
        (unsigned int)diagnostics.sample_valid,
        sample_age_text,
        SystemConsole_BarometerOriginStateText(diagnostics.origin_state),
        (unsigned long)diagnostics.origin_sample_count,
        (unsigned long)diagnostics.origin_required_count,
        (double)diagnostics.origin_altitude_m,
        origin_pressure_pa,
        (double)diagnostics.relative_altitude_m,
        (double)diagnostics.measurement_variance,
        SystemConsole_BarometerUpdateStateText(
            diagnostics.last_update_state),
        (double)diagnostics.last_innovation,
        (double)diagnostics.last_innovation_variance,
        (double)diagnostics.last_nis,
        (unsigned long)diagnostics.accepted_count,
        (unsigned long)diagnostics.softened_count,
        (unsigned long)diagnostics.rejected_count,
        (unsigned long)diagnostics.skipped_count,
        SystemConsole_BarometerSkipReasonText(
            diagnostics.last_skip_reason),
        update_age_text);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static const char *SystemConsole_EstimatorModeText(
    SystemEstimatorMode mode)
{
    return (mode == SYSTEM_ESTIMATOR_MODE_KF6) ? "KF6" : "PURE_INS";
}

static const char *SystemConsole_EstimatorAttitudeSourceText(
    SystemEstimatorAttitudeSource source)
{
    (void)source;
    return "SOFTWARE_INS";
}

static const char *SystemConsole_EstimatorPositionSourceText(
    SystemEstimatorPositionSource source)
{
    return (source == SYSTEM_ESTIMATOR_POSITION_SOURCE_KF6) ?
        "KF6" : "PURE_INS";
}

static SystemConsoleExecuteResult SystemConsole_EstimatorStatusExecute(
    char *response,
    uint16_t capacity)
{
    SystemEstimatorStatusDiagnostics diagnostics;

    if (SystemEstimatorStatusDiagnostics_Get(&diagnostics) == 0U)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ESTIMATOR", "STATUS",
            "NOT_READY", "DIAGNOSTICS",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemEstimatorStatusDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK ESTIMATOR STATUS state=%u initialized=%u started=%u mode=%s attitude_source=%s position_source=%s imu_prediction_count=%lu last_state_timestamp=%lu",
        (unsigned int)SystemLifecycle_GetState(),
        (unsigned int)diagnostics.initialized,
        (unsigned int)diagnostics.started,
        SystemConsole_EstimatorModeText(diagnostics.mode),
        SystemConsole_EstimatorAttitudeSourceText(
            diagnostics.attitude_source),
        SystemConsole_EstimatorPositionSourceText(
            diagnostics.position_source),
        (unsigned long)diagnostics.imu_prediction_count,
        SystemConsole_TimestampDisplay(
            diagnostics.last_state_timestamp_us));
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static const char *SystemConsole_EstimatorGnssUpdateStateText(
    SystemEstimatorGnssUpdateState state)
{
    SILVERSTAR_ASSERT_OBJECT(&state, SystemEstimatorGnssUpdateState,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (state)
    {
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_WAIT_ORIGIN:
            return "WAIT_ORIGIN";
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_WAIT_SAMPLE:
            return "WAIT_SAMPLE";
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_ACCEPTED:
            return "ACCEPTED";
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_REJECTED:
            return "REJECTED";
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_STALE:
            return "STALE";
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_INVALID:
            return "INVALID";
        case SYSTEM_ESTIMATOR_GNSS_UPDATE_DISABLED:
        default:
            return "DISABLED";
    }
}

static const char *SystemConsole_EstimatorGnssSkipReasonText(
    SystemEstimatorGnssSkipReason reason)
{
    SILVERSTAR_ASSERT_OBJECT(&reason, SystemEstimatorGnssSkipReason,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (reason)
    {
        case SYSTEM_ESTIMATOR_GNSS_SKIP_UNSUPPORTED:
            return "UNSUPPORTED";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_FUSION_MODE_DISABLED:
            return "FUSION_MODE_DISABLED";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_NO_PREFLIGHT_ORIGIN:
            return "NO_PREFLIGHT_ORIGIN";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_NO_SAMPLE:
            return "NO_SAMPLE";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_WAIT_STATE_CATCHUP:
            return "WAIT_STATE_CATCHUP";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_STALE:
            return "STALE";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_MEASUREMENT_INVALID:
            return "MEASUREMENT_INVALID";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_GEODESY_ERROR:
            return "GEODESY_ERROR";
        case SYSTEM_ESTIMATOR_GNSS_SKIP_NONE:
        default:
            return "NONE";
    }
}

static const char *SystemConsole_GnssInflationGroupText(
    SystemEstimatorGnssInflationGroup group)
{
    switch (group)
    {
        case SYSTEM_ESTIMATOR_GNSS_INFLATION_POSITION_HORIZONTAL:
            return "POSITION_HORIZONTAL";
        case SYSTEM_ESTIMATOR_GNSS_INFLATION_POSITION_VERTICAL:
            return "POSITION_VERTICAL";
        case SYSTEM_ESTIMATOR_GNSS_INFLATION_VELOCITY_HORIZONTAL:
            return "VELOCITY_HORIZONTAL";
        case SYSTEM_ESTIMATOR_GNSS_INFLATION_VELOCITY_VERTICAL:
            return "VELOCITY_VERTICAL";
        case SYSTEM_ESTIMATOR_GNSS_INFLATION_NONE:
        default: return "NONE";
    }
}

static void SystemConsole_EstimatorGnssSummaryWrite(
    const SystemEstimatorGnssDiagnostics *diagnostics,
    const char *measurement_age_text,
    char *response,
    uint16_t capacity)
{
    const char *state_text;
    const char *reason_text;

    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemEstimatorGnssDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    state_text = SystemConsole_EstimatorGnssUpdateStateText(
        diagnostics->last_update_state);
    reason_text = SystemConsole_EstimatorGnssSkipReasonText(
        diagnostics->last_skip_reason);
    (void)CommonFormat_Print(response, capacity,
        "OK ESTIMATOR GNSS supported=%u fusion_enabled=%u origin_valid=%u origin_lat_e7=%ld origin_lon_e7=%ld origin_height_mm=%ld position_updates=%lu velocity_updates=%lu position_accept_count=%lu position_reject_count=%lu velocity_accept_count=%lu velocity_reject_count=%lu last_update_state=%s last_skip_reason=%s reason=%s last_measurement_timestamp=%lu last_state_timestamp=%lu measurement_age_ms=%s",
        (unsigned int)diagnostics->supported,
        (unsigned int)diagnostics->fusion_enabled,
        (unsigned int)diagnostics->origin_valid,
        (long)diagnostics->origin_lat_e7,
        (long)diagnostics->origin_lon_e7,
        (long)diagnostics->origin_height_mm,
        (unsigned long)diagnostics->position_updates,
        (unsigned long)diagnostics->velocity_updates,
        (unsigned long)diagnostics->position_accept_count,
        (unsigned long)diagnostics->position_reject_count,
        (unsigned long)diagnostics->velocity_accept_count,
        (unsigned long)diagnostics->velocity_reject_count,
        state_text, reason_text, reason_text,
        SystemConsole_TimestampDisplay(diagnostics->last_measurement_timestamp_us),
        SystemConsole_TimestampDisplay(diagnostics->last_state_timestamp_us),
        measurement_age_text);
}

static void SystemConsole_EstimatorGnssDetailAppend(
    const SystemEstimatorGnssDiagnostics *diagnostics,
    char *response,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemEstimatorGnssDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_TextAppend(response, capacity,
        " position_horizontal_nis=%.3f position_vertical_nis=%.3f velocity_horizontal_nis=%.3f velocity_vertical_nis=%.3f innovation_e=%.3f innovation_n=%.3f innovation_u=%.3f innovation_ve=%.3f innovation_vn=%.3f innovation_vu=%.3f position_horizontal_effective_std_m=%.3f position_vertical_effective_std_m=%.3f velocity_horizontal_effective_std_mps=%.3f velocity_vertical_effective_std_mps=%.3f P_E=%.6g P_N=%.6g P_U=%.6g P_vE=%.6g P_vN=%.6g P_vU=%.6g position_horizontal_accept_count=%lu position_horizontal_reject_count=%lu position_vertical_accept_count=%lu position_vertical_reject_count=%lu velocity_horizontal_accept_count=%lu velocity_horizontal_reject_count=%lu velocity_vertical_accept_count=%lu velocity_vertical_reject_count=%lu position_horizontal_reject_streak=%lu position_vertical_reject_streak=%lu velocity_horizontal_reject_streak=%lu velocity_vertical_reject_streak=%lu reacquire_active_mask=0x%02X reacquire_count=%lu last_inflation_group=%s last_inflation_factor=%.3f last_inflation_attempt=%lu",
        (double)diagnostics->position_horizontal_nis,
        (double)diagnostics->position_vertical_nis,
        (double)diagnostics->velocity_horizontal_nis,
        (double)diagnostics->velocity_vertical_nis,
        (double)diagnostics->innovation_e_m,
        (double)diagnostics->innovation_n_m,
        (double)diagnostics->innovation_u_m,
        (double)diagnostics->innovation_ve_mps,
        (double)diagnostics->innovation_vn_mps,
        (double)diagnostics->innovation_vu_mps,
        (double)diagnostics->position_horizontal_effective_std_m,
        (double)diagnostics->position_vertical_effective_std_m,
        (double)diagnostics->velocity_horizontal_effective_std_mps,
        (double)diagnostics->velocity_vertical_effective_std_mps,
        (double)diagnostics->covariance_position_e_m2,
        (double)diagnostics->covariance_position_n_m2,
        (double)diagnostics->covariance_position_u_m2,
        (double)diagnostics->covariance_velocity_e_m2ps2,
        (double)diagnostics->covariance_velocity_n_m2ps2,
        (double)diagnostics->covariance_velocity_u_m2ps2,
        (unsigned long)diagnostics->position_horizontal_accept_count,
        (unsigned long)diagnostics->position_horizontal_reject_count,
        (unsigned long)diagnostics->position_vertical_accept_count,
        (unsigned long)diagnostics->position_vertical_reject_count,
        (unsigned long)diagnostics->velocity_horizontal_accept_count,
        (unsigned long)diagnostics->velocity_horizontal_reject_count,
        (unsigned long)diagnostics->velocity_vertical_accept_count,
        (unsigned long)diagnostics->velocity_vertical_reject_count,
        (unsigned long)diagnostics->position_horizontal_reject_streak,
        (unsigned long)diagnostics->position_vertical_reject_streak,
        (unsigned long)diagnostics->velocity_horizontal_reject_streak,
        (unsigned long)diagnostics->velocity_vertical_reject_streak,
        (unsigned int)diagnostics->reacquire_active_mask,
        (unsigned long)diagnostics->reacquire_count,
        SystemConsole_GnssInflationGroupText(
            diagnostics->last_inflation_group),
        (double)diagnostics->last_inflation_factor,
        (unsigned long)diagnostics->last_inflation_attempt);
}

static SystemConsoleExecuteResult SystemConsole_EstimatorGnssExecute(
    char *response,
    uint16_t capacity)
{
    SystemEstimatorGnssDiagnostics diagnostics;
    char measurement_age_text[24];

    if (SystemEstimatorGnssDiagnostics_Get(
            &diagnostics, SystemTime_GetMonotonicUs()) == 0U)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "ESTIMATOR", "GNSS",
            "NOT_READY", "DIAGNOSTICS",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemEstimatorGnssDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_AgeFormat(
        measurement_age_text, sizeof(measurement_age_text),
        (diagnostics.measurement_age_ms == UINT32_MAX) ?
            UINT64_MAX : (uint64_t)diagnostics.measurement_age_ms);
    SystemConsole_EstimatorGnssSummaryWrite(
        &diagnostics, measurement_age_text, response, capacity);
    SystemConsole_EstimatorGnssDetailAppend(&diagnostics, response, capacity);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static const char *SystemConsole_KfUpdateTypeText(SystemKfUpdateType type)
{
    switch (type)
    {
        case SYSTEM_KF_UPDATE_GNSS_POSITION: return "GNSS_POSITION";
        case SYSTEM_KF_UPDATE_GNSS_VELOCITY: return "GNSS_VELOCITY";
        case SYSTEM_KF_UPDATE_BAROMETER: return "BAROMETER";
        case SYSTEM_KF_UPDATE_NONE:
        default: return "NONE";
    }
}

static SystemConsoleExecuteResult SystemConsole_KfStatusExecute(
    char *response,
    uint16_t capacity)
{
    SystemKfDiagnostics diagnostics;

    if (SystemKfDiagnostics_Get(&diagnostics) == 0U)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "KF", "STATUS",
            "NOT_READY", "DIAGNOSTICS",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemKfDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK KF STATUS initialized=%u state_dimension=%u prediction_count=%lu sequential_update_count=%lu position_update_count=%lu velocity_update_count=%lu baro_update_count=%lu last_update_type=%s last_update_time=%lu innovation_reject_count=%lu",
        (unsigned int)diagnostics.initialized,
        (unsigned int)diagnostics.state_dimension,
        (unsigned long)diagnostics.prediction_count,
        (unsigned long)diagnostics.sequential_update_count,
        (unsigned long)diagnostics.position_update_count,
        (unsigned long)diagnostics.velocity_update_count,
        (unsigned long)diagnostics.baro_update_count,
        SystemConsole_KfUpdateTypeText(diagnostics.last_update_type),
        SystemConsole_TimestampDisplay(
            diagnostics.last_update_timestamp_us),
        (unsigned long)diagnostics.innovation_reject_count);
    SystemConsole_TextAppend(response, capacity,
        " reacquire_count=%lu reacquire_active_mask=0x%02X",
        (unsigned long)diagnostics.reacquire_count,
        (unsigned int)diagnostics.reacquire_active_mask);
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_InsStatusExecute(
    char *response,
    uint16_t capacity)
{
    SystemInsDiagnostics diagnostics;

    if (SystemInsDiagnostics_Get(&diagnostics) == 0U)
    {
        return SystemConsole_ErrorWrite(
            response, capacity, "INS", "STATUS",
            "NOT_READY", "DIAGNOSTICS",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    SILVERSTAR_ASSERT_OBJECT(&diagnostics, SystemInsDiagnostics,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity,
        "OK INS STATUS initialized=%u started=%u attitude_ready=%u quaternion_valid=%u velocity_valid=%u position_valid=%u software_attitude_propagation=%u bias_ready=%u bias_samples=%lu last_update_timestamp=%lu",
        (unsigned int)diagnostics.initialized,
        (unsigned int)diagnostics.started,
        (unsigned int)diagnostics.attitude_ready,
        (unsigned int)diagnostics.quaternion_valid,
        (unsigned int)diagnostics.velocity_valid,
        (unsigned int)diagnostics.position_valid,
        (unsigned int)diagnostics.software_attitude_propagation,
        (unsigned int)diagnostics.bias_ready,
        (unsigned long)diagnostics.bias_samples,
        SystemConsole_TimestampDisplay(
            diagnostics.last_update_timestamp_us));
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemDeviceResult SystemConsole_ImuSampleWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemImuSample sample;
    SystemDeviceResult result = ProjectImuInstance_LatestSampleGet(
        instance_id, &sample);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s SAMPLE seq=%lu sample_us=%lu receive_us=%lu valid=0x%08lX",
            module_text,
            (unsigned long)sample.sequence,
            SystemConsole_TimestampDisplay(sample.sample_timestamp_us),
            SystemConsole_TimestampDisplay(sample.receive_timestamp_us),
            (unsigned long)sample.valid_mask);
    }
    return result;
}

static SystemDeviceResult SystemConsole_GnssSampleWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemGnssSample sample;
    SystemDeviceResult result = ProjectGnssInstance_LatestSampleGet(
        instance_id, &sample);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s SAMPLE seq=%lu lat_e7=%ld lon_e7=%ld fix=%u position_usable=%u velocity_mask=0x%02X",
            module_text,
            (unsigned long)sample.sequence, (long)sample.latitude_e7,
            (long)sample.longitude_e7, (unsigned int)sample.fix_type,
            (unsigned int)sample.position_usable,
            (unsigned int)sample.velocity_valid_mask);
    }
    return result;
}

static SystemDeviceResult SystemConsole_BarometerSampleWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemBarometerSample sample;
    SystemDeviceResult result = ProjectBarometerInstance_LatestSampleGet(
        instance_id, &sample);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s SAMPLE seq=%lu pressure_pa=%ld altitude_cm=%ld valid=0x%08lX",
            module_text,
            (unsigned long)sample.sequence, (long)sample.pressure_raw_pa,
            (long)sample.altitude_raw_cm, (unsigned long)sample.valid_mask);
    }
    return result;
}

static SystemDeviceResult SystemConsole_MagnetometerSampleWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemMagnetometerSample sample;
    SystemDeviceResult result = ProjectMagnetometerInstance_LatestSampleGet(
        instance_id, &sample);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s SAMPLE seq=%lu raw=%ld,%ld,%ld physical_valid=%u calibration_valid=%u",
            module_text,
            (unsigned long)sample.sequence, (long)sample.raw[0],
            (long)sample.raw[1], (long)sample.raw[2],
            (unsigned int)((sample.valid_mask &
                            SYSTEM_MAG_VALID_PHYSICAL_UNIT) != 0U),
            (unsigned int)sample.calibration_valid);
    }
    return result;
}

static SystemDeviceResult SystemConsole_AttitudeSampleWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemHardwareQuaternionSample sample;
    SystemDeviceResult result =
        ProjectAttitudeInstance_LatestSampleGet(instance_id, &sample);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s SAMPLE seq=%lu mode=%u normalized=%u valid=%u",
            module_text,
            (unsigned long)sample.sequence, (unsigned int)sample.mode,
            (unsigned int)sample.normalized, (unsigned int)sample.valid);
    }
    return result;
}

static SystemDeviceResult SystemConsole_PowerSampleWrite(
    uint8_t instance_id, const char *module_text,
    char *response, uint16_t capacity)
{
    SystemPowerSample sample;
    SystemDeviceResult result = ProjectPowerInstance_LatestSampleGet(
        instance_id, &sample);

    if (result == SYSTEM_DEVICE_OK)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK %s SAMPLE seq=%lu millivolts=%ld valid=0x%08lX sample_us=%lu receive_us=%lu",
            module_text,
            (unsigned long)sample.sequence,
            (long)(sample.voltage_v * 1000.0f),
            (unsigned long)sample.valid_mask,
            SystemConsole_TimestampDisplay(sample.sample_timestamp_us),
            SystemConsole_TimestampDisplay(sample.receive_timestamp_us));
    }
    return result;
}

static SystemDeviceResult SystemConsole_SampleWrite(
    SystemConsoleModule module, uint8_t instance_id,
    const char *module_text, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (module)
    {
    case SYSTEM_CONSOLE_MODULE_IMU:
        return SystemConsole_ImuSampleWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_GNSS:
        return SystemConsole_GnssSampleWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_BARO:
        return SystemConsole_BarometerSampleWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_MAG:
        return SystemConsole_MagnetometerSampleWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_ATTITUDE:
        return SystemConsole_AttitudeSampleWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_POWER:
        return SystemConsole_PowerSampleWrite(
            instance_id, module_text, response, capacity);
    case SYSTEM_CONSOLE_MODULE_SYSTEM:
    case SYSTEM_CONSOLE_MODULE_ESTIMATOR:
    case SYSTEM_CONSOLE_MODULE_KF:
    case SYSTEM_CONSOLE_MODULE_INS:
    case SYSTEM_CONSOLE_MODULE_CAL:
    case SYSTEM_CONSOLE_MODULE_ALIGN:
    case SYSTEM_CONSOLE_MODULE_TELEMETRY:
    case SYSTEM_CONSOLE_MODULE_OUTPUT:
    case SYSTEM_CONSOLE_MODULE_LOG:
    case SYSTEM_CONSOLE_MODULE_TIME:
    case SYSTEM_CONSOLE_MODULE_INVALID:
    default:
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemConsoleExecuteResult SystemConsole_SampleExecute(
    SystemConsoleModule module,
    const char *module_text,
    uint8_t instance_id,
    char *response,
    uint16_t capacity)
{
    SystemDeviceResult result =
        SystemConsole_SampleWrite(
            module, instance_id, module_text, response, capacity);

    if (result == SYSTEM_DEVICE_OK) { return SYSTEM_CONSOLE_EXECUTE_OK; }
    return SystemConsole_ErrorWrite(response, capacity, module_text, "SAMPLE",
                                    SystemConsole_DeviceErrorText(result),
                                    "DEVICE",
                                    (result == SYSTEM_DEVICE_UNSUPPORTED) ?
                                        SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED :
                                        SYSTEM_CONSOLE_EXECUTE_FAILED);
}

static uint8_t SystemConsole_AsyncWrite(const char *text)
{
    uint16_t length;

    if (text == NULL)
    {
        return 0U;
    }
    length = SystemConsole_TextLengthGet(text, sizeof(s_async_event));
    if (length == 0U) { return 0U; }
    return (uint8_t)(SystemConsoleDevice_Write((const uint8_t *)text,
                                                length) == SYSTEM_DEVICE_OK);
}

static uint8_t SystemConsole_CalibrationDiagnosticAsyncWrite(
    const SystemCalibrationStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT CAL DIAG face=%s reason=%s\r\n",
        SystemCalibration_FaceText(status->diagnostic_face),
        SystemCalibration_WaitReasonText(status->diagnostic_reason));
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_calibration_diagnostic_sequence = status->diagnostic_sequence;
    return 1U;
}

static uint8_t SystemConsole_CalibrationFaceAsyncWrite(
    const SystemCalibrationStatus *status)
{
    const char *result_text;

    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result_text = (status->last_face_result ==
                   SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE) ?
        "PASSED" : "FAILED";
    if (status->last_face_result == SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE)
    {
        (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
            "EVENT CAL FACE face=%s result=%s samples=%lu completed_face_mask=0x%02X\r\n",
            SystemCalibration_FaceText(status->last_face), result_text,
            (unsigned long)status->samples,
            (unsigned int)status->completed_face_mask);
    }
    else
    {
        (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
            "EVENT CAL FACE face=%s result=%s reason=%s completed_face_mask=0x%02X\r\n",
            SystemCalibration_FaceText(status->last_face), result_text,
            SystemCalibration_WaitReasonText(status->wait_reason),
            (unsigned int)status->completed_face_mask);
    }
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_calibration_face_event_sequence = status->face_event_sequence;
    return 1U;
}

static uint8_t SystemConsole_CalibrationCompletionAsyncWrite(
    const SystemCalibrationStatus *status)
{
    const char *result_text =
        (status->state == SYSTEM_CALIBRATION_STATE_READY) ?
            "PASSED" : "FAILED";

    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT CAL COMPLETE mode=%s result=%s samples=%lu completed_face_mask=0x%02X reason=%s\r\n",
        SystemCalibration_ModeText(status->mode), result_text,
        (unsigned long)status->samples,
        (unsigned int)status->completed_face_mask,
        SystemCalibration_WaitReasonText(status->wait_reason));
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_calibration_completion_sequence = status->start_sequence;
    return 1U;
}

static uint8_t SystemConsole_CalibrationAsyncProcess(void)
{
    SystemCalibrationStatus status;

    if (SystemCalibration_StatusGet(&status) != SYSTEM_DEVICE_OK)
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(&status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (status.diagnostic_sequence !=
        s_console_calibration_diagnostic_sequence)
    { return SystemConsole_CalibrationDiagnosticAsyncWrite(&status); }
    if (status.face_event_sequence !=
        s_console_calibration_face_event_sequence)
    { return SystemConsole_CalibrationFaceAsyncWrite(&status); }
    if ((status.start_sequence !=
         s_console_calibration_completion_sequence) &&
        ((status.state == SYSTEM_CALIBRATION_STATE_READY) ||
         (status.state == SYSTEM_CALIBRATION_STATE_FAILED)))
    { return SystemConsole_CalibrationCompletionAsyncWrite(&status); }
    return 0U;
}

static uint8_t SystemConsole_AlignmentCompletionAsyncWrite(
    const SystemAlignmentSummary *summary)
{
    SystemAlignmentStatus detail;
    const char *result_text;

    if ((summary == NULL) ||
        (SystemAlignment_StatusGet(&detail) != SYSTEM_DEVICE_OK) ||
        (detail.start_sequence != summary->start_sequence) ||
        (detail.state != summary->state))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(summary, SystemAlignmentSummary,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result_text = (detail.state == SYSTEM_ALIGNMENT_STATE_READY) ?
        "PASSED" : "FAILED";
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT ALIGN COMPLETE result=%s ready_mask=0x%08lX",
        result_text,
        (unsigned long)detail.ready_mask);
    SystemConsole_AlignmentSourcesAppend(&detail, s_async_event,
                                         sizeof(s_async_event), "");
    SystemConsole_TextAppend(s_async_event, sizeof(s_async_event), "\r\n");
    if (SystemConsole_AsyncWrite(s_async_event) == 0U)
    {
        return 0U;
    }
    s_console_alignment_completion_sequence = detail.start_sequence;
    return 1U;
}

static uint8_t SystemConsole_AlignmentAsyncProcess(void)
{
    SystemAlignmentSummary summary;

    if (SystemAlignment_SummaryGet(&summary) != SYSTEM_DEVICE_OK)
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(&summary, SystemAlignmentSummary,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((summary.state == SYSTEM_ALIGNMENT_STATE_STALE) &&
        (s_console_alignment_state != SYSTEM_ALIGNMENT_STATE_STALE))
    {
        (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
            "EVENT ALIGN STALE reason=%s ready_mask=0x%08lX\r\n",
            SystemAlignment_StaleReasonText(summary.stale_reason),
            (unsigned long)summary.ready_mask);
        if (SystemConsole_AsyncWrite(s_async_event) != 0U)
        {
            s_console_alignment_state = summary.state;
            return 1U;
        }
        return 0U;
    }
    s_console_alignment_state = summary.state;
    if ((summary.start_sequence ==
         s_console_alignment_completion_sequence) ||
        ((summary.state != SYSTEM_ALIGNMENT_STATE_READY) &&
         (summary.state != SYSTEM_ALIGNMENT_STATE_FAILED)))
    {
        return 0U;
    }
    return SystemConsole_AlignmentCompletionAsyncWrite(&summary);
}

static uint8_t SystemConsole_FlightActionFailureAsyncWrite(
    const SystemFlightRecoveryStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT FLIGHT ACTION_FAILED action=%s result=%s time_ms=%lu\r\n",
        SystemFlightRecovery_ActionText(status->last_action),
        SystemConsole_DeviceErrorText(status->last_action_result),
        (unsigned long)status->last_action_mission_time_ms);
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_flight_action_sequence = status->action_event_sequence;
    return 1U;
}

static uint8_t SystemConsole_FlightDeployAsyncWrite(
    const SystemFlightRecoveryStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT FLIGHT PARACHUTE_DEPLOY matched_mask=0x%02lX time_ms=%lu tilt_deg=%.2f vz_mps=%.2f delay_ms=%lu\r\n",
        (unsigned long)status->deploy_matched_mask,
        (unsigned long)status->deploy_event_mission_time_ms,
        (double)status->deploy_tilt_angle_deg,
        (double)status->deploy_vertical_velocity_mps,
        (unsigned long)status->deploy_delay_ms);
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_deploy_event_sequence = status->deploy_event_sequence;
    return 1U;
}

static uint8_t SystemConsole_FlightImpactAsyncWrite(
    const SystemFlightRecoveryStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT FLIGHT LANDING_IMPACT time_ms=%lu metric_mps2=%.2f peak_mps2=%.2f state=%s\r\n",
        (unsigned long)status->impact_event_mission_time_ms,
        (double)status->impact_metric_mps2,
        (double)status->impact_peak_mps2,
        SystemFlightRecovery_LandingStateText(status->landing_state));
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_impact_event_sequence = status->impact_event_sequence;
    return 1U;
}

static uint8_t SystemConsole_FlightLandingAsyncWrite(
    const SystemFlightRecoveryStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(s_async_event, sizeof(s_async_event),
        "EVENT FLIGHT LANDING time_ms=%lu\r\n",
        (unsigned long)status->landing_event_mission_time_ms);
    if (SystemConsole_AsyncWrite(s_async_event) == 0U) { return 0U; }
    s_console_landing_event_sequence = status->landing_event_sequence;
    return 1U;
}

static uint8_t SystemConsole_FlightRecoveryAsyncProcess(void)
{
    SystemFlightRecoveryStatus status;

    if (SystemFlightRecovery_StatusGet(&status) != SYSTEM_DEVICE_OK)
    { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(&status, SystemFlightRecoveryStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (status.action_event_sequence != s_console_flight_action_sequence)
    {
        if (status.last_action_result != SYSTEM_DEVICE_OK)
        { return SystemConsole_FlightActionFailureAsyncWrite(&status); }
        s_console_flight_action_sequence = status.action_event_sequence;
    }
    if (status.deploy_event_sequence != s_console_deploy_event_sequence)
    { return SystemConsole_FlightDeployAsyncWrite(&status); }
    if (status.impact_event_sequence != s_console_impact_event_sequence)
    { return SystemConsole_FlightImpactAsyncWrite(&status); }
    if (status.landing_event_sequence != s_console_landing_event_sequence)
    { return SystemConsole_FlightLandingAsyncWrite(&status); }
    return 0U;
}

static void SystemConsole_AsyncEventProcess(void)
{
    /* Emit at most one asynchronous line per 1 ms console cycle. This keeps
       command responses responsive and bounds TX-ring pressure. */
    if (SystemConsole_FlightRecoveryAsyncProcess() != 0U) { return; }
    if (SystemConsole_CalibrationAsyncProcess() != 0U) { return; }
    (void)SystemConsole_AlignmentAsyncProcess();
}

SystemDeviceResult SystemConsole_Init(void)
{
    SystemDeviceIoDiagnostics diagnostics;

    SILVERSTAR_ASSERT_OBJECT(&s_line[0], char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    s_line_length = 0U;
    s_console_start_request_id = 0U;
    s_console_discontinuity_sequence = 0U;
    s_console_calibration_face_event_sequence = 0U;
    s_console_calibration_completion_sequence = 0U;
    s_console_calibration_diagnostic_sequence = 0U;
    s_console_alignment_completion_sequence = 0U;
    s_console_flight_action_sequence = 0U;
    s_console_deploy_event_sequence = 0U;
    s_console_impact_event_sequence = 0U;
    s_console_landing_event_sequence = 0U;
    s_console_alignment_state = SYSTEM_ALIGNMENT_STATE_IDLE;
    (void)memset(s_line, 0, sizeof(s_line));
    (void)memset(s_async_event, 0, sizeof(s_async_event));
    (void)memset(s_io_baselines, 0, sizeof(s_io_baselines));
    if (SystemConsoleDevice_IoDiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK)
    {
        s_console_discontinuity_sequence =
            diagnostics.rx_discontinuity_count;
    }
    {
        SystemCalibrationStatus calibration;
        SystemAlignmentSummary alignment;
        SystemFlightRecoveryStatus flight_recovery;

        if (SystemCalibration_StatusGet(&calibration) == SYSTEM_DEVICE_OK)
        {
            s_console_calibration_face_event_sequence =
                calibration.face_event_sequence;
            s_console_calibration_completion_sequence =
                calibration.start_sequence;
            s_console_calibration_diagnostic_sequence =
                calibration.diagnostic_sequence;
        }
        if (SystemAlignment_SummaryGet(&alignment) == SYSTEM_DEVICE_OK)
        {
            s_console_alignment_completion_sequence =
                alignment.start_sequence;
            s_console_alignment_state = alignment.state;
        }
        if (SystemFlightRecovery_StatusGet(&flight_recovery) ==
            SYSTEM_DEVICE_OK)
        {
            s_console_flight_action_sequence =
                flight_recovery.action_event_sequence;
            s_console_deploy_event_sequence =
                flight_recovery.deploy_event_sequence;
            s_console_impact_event_sequence =
                flight_recovery.impact_event_sequence;
            s_console_landing_event_sequence =
                flight_recovery.landing_event_sequence;
        }
    }
    return SYSTEM_DEVICE_OK;
}

static char *SystemConsole_TokenNext(SystemConsoleTokenCursor *cursor)
{
    char *token;
    char *scan;
    uint16_t remaining;
    uint16_t index;

    if ((cursor == NULL) || (cursor->scan == NULL))
    {
        return NULL;
    }
    SILVERSTAR_ASSERT_OBJECT(cursor, SystemConsoleTokenCursor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    scan = cursor->scan;
    remaining = cursor->remaining;
    for (index = 0U; index < SYSTEM_CONSOLE_LINE_CAPACITY; index++)
    {
        if ((remaining == 0U) ||
            ((scan[0] != ' ') && (scan[0] != '\t')))
        {
            break;
        }
        scan++;
        remaining--;
    }
    if ((remaining == 0U) || (scan[0] == '\0'))
    {
        cursor->scan = NULL;
        cursor->remaining = 0U;
        return NULL;
    }

    token = scan;
    for (index = 0U; index < SYSTEM_CONSOLE_LINE_CAPACITY; index++)
    {
        if ((remaining == 0U) || (scan[0] == '\0') ||
            (scan[0] == ' ') || (scan[0] == '\t'))
        {
            break;
        }
        scan++;
        remaining--;
    }
    if ((remaining == 0U) || (scan[0] == '\0'))
    {
        cursor->scan = NULL;
        cursor->remaining = 0U;
    }
    else
    {
        scan[0] = '\0';
        cursor->scan = scan + 1;
        cursor->remaining = (uint16_t)(remaining - 1U);
    }
    return token;
}

typedef struct
{
    char storage[SYSTEM_CONSOLE_LINE_CAPACITY];
    char *tokens[SYSTEM_CONSOLE_TOKEN_COUNT_MAX];
    char addressed_module[32];
    char *module_token;
    char *module_text;
    char *command;
    char *subcommand;
    char *extra;
    SystemConsoleModule module;
    uint8_t token_count;
    uint8_t instance_id;
    uint8_t list_requested;
} SystemConsoleCommand;

static SystemConsoleExecuteResult SystemConsole_InstanceParseErrorWrite(
    const SystemConsoleCommand *parsed,
    const char *reason,
    char *response,
    uint16_t capacity)
{
    return SystemConsole_ErrorWrite(response, capacity,
        parsed->module_token, parsed->tokens[1], "BAD_INSTANCE", reason,
        SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
}

static SystemConsoleExecuteResult SystemConsole_InstanceParse(
    SystemConsoleCommand *parsed, char *response, uint16_t capacity)
{
    uint32_t value = 0U;
    uint16_t index;
    char *instance_text = parsed->tokens[1];

    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < SYSTEM_CONSOLE_LINE_CAPACITY; index++)
    {
        char character = instance_text[index];

        if (character == '\0') { break; }
        if ((character < '0') || (character > '9'))
        {
            return SystemConsole_InstanceParseErrorWrite(
                parsed, "FORMAT", response, capacity);
        }
        value = (value * 10U) + (uint32_t)(character - '0');
        if (value > UINT8_MAX)
        {
            return SystemConsole_InstanceParseErrorWrite(
                parsed, "RANGE", response, capacity);
        }
    }
    if ((index == 0U) || (index >= SYSTEM_CONSOLE_LINE_CAPACITY))
    {
        return SystemConsole_InstanceParseErrorWrite(
            parsed, "FORMAT", response, capacity);
    }
    parsed->instance_id = (uint8_t)value;
    (void)CommonFormat_Print(parsed->addressed_module,
        sizeof(parsed->addressed_module), "%s %u", parsed->module_token,
        (unsigned int)parsed->instance_id);
    parsed->module_text = parsed->addressed_module;
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_IndexedCommandParse(
    SystemConsoleCommand *parsed, char *response, uint16_t capacity)
{
    SystemDeviceDescriptor descriptor;
    SystemConsoleExecuteResult result;

    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((parsed->token_count == 2U) &&
        (strcmp(parsed->tokens[1], "LIST") == 0))
    {
        parsed->list_requested = 1U;
        parsed->command = parsed->tokens[1];
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    if (parsed->token_count < 3U)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_token,
            (parsed->token_count == 2U) ? parsed->tokens[1] : "PARSE",
            "BAD_FORMAT", "INSTANCE_REQUIRED",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    if (parsed->token_count > 4U)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_token, parsed->tokens[2],
            "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    result = SystemConsole_InstanceParse(parsed, response, capacity);
    if (result != SYSTEM_CONSOLE_EXECUTE_OK) { return result; }
    parsed->command = parsed->tokens[2];
    if (parsed->token_count == 4U) { parsed->subcommand = parsed->tokens[3]; }
    if (ProjectDeviceInstance_DescriptorGet(
            SystemConsole_DeviceClassGet(parsed->module),
            parsed->instance_id, &descriptor) != SYSTEM_DEVICE_OK)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_text, parsed->command, "NOT_PRESENT", "INSTANCE",
            SYSTEM_CONSOLE_EXECUTE_FAILED);
    }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_SystemCommandParse(
    SystemConsoleCommand *parsed, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (parsed->token_count < 2U)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", "PARSE",
            "BAD_FORMAT", "TOKEN_COUNT", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    if (parsed->token_count > 4U)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_token, parsed->tokens[1],
            "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    parsed->command = parsed->tokens[1];
    if (parsed->token_count >= 3U) { parsed->subcommand = parsed->tokens[2]; }
    if (parsed->token_count == 4U) { parsed->extra = parsed->tokens[3]; }
    if ((parsed->extra != NULL) &&
        ((parsed->module != SYSTEM_CONSOLE_MODULE_SYSTEM) ||
         (strcmp(parsed->command, "CONSOLE") != 0) ||
         (strcmp(parsed->subcommand, "IO") != 0) ||
         (strcmp(parsed->extra, "CLEAR") != 0)))
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_token, parsed->command,
            "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_CommandParse(
    const char *line, SystemConsoleCommand *parsed,
    char *response, uint16_t capacity)
{
    SystemConsoleTokenCursor cursor;
    char *overflow;
    uint16_t line_length;
    uint8_t index;

    if ((line == NULL) || (parsed == NULL) ||
        (response == NULL) || (capacity == 0U))
    { return SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT; }
    (void)memset(parsed, 0, sizeof(*parsed));
    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    line_length = SystemConsole_TextLengthGet(line, sizeof(parsed->storage));
    if ((line_length == 0U) || (line_length >= sizeof(parsed->storage)))
    { return SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT; }
    (void)memcpy(parsed->storage, line, (size_t)line_length + 1U);
    cursor.scan = parsed->storage;
    cursor.remaining = (uint16_t)(line_length + 1U);
    for (index = 0U; index < SYSTEM_CONSOLE_TOKEN_COUNT_MAX; index++)
    {
        parsed->tokens[index] = SystemConsole_TokenNext(&cursor);
        if (parsed->tokens[index] == NULL) { break; }
        parsed->token_count++;
    }
    overflow = SystemConsole_TokenNext(&cursor);
    if (parsed->token_count == 0U)
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM", "PARSE",
            "BAD_FORMAT", "TOKEN_COUNT", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    parsed->module_token = parsed->tokens[0];
    parsed->module_text = parsed->module_token;
    parsed->module = SystemConsole_ModuleParse(parsed->module_token);
    if (parsed->module == SYSTEM_CONSOLE_MODULE_INVALID)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_token,
            (parsed->token_count >= 2U) ? parsed->tokens[1] : "PARSE",
            "BAD_MODULE", "UNKNOWN", SYSTEM_CONSOLE_EXECUTE_BAD_MODULE);
    }
    if (overflow != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_token,
            (parsed->token_count >= 2U) ? parsed->tokens[1] : "PARSE",
            "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    if (SystemConsole_ModuleIsIndexed(parsed->module) != 0U)
    {
        return SystemConsole_IndexedCommandParse(parsed, response, capacity);
    }
    return SystemConsole_SystemCommandParse(parsed, response, capacity);
}

static SystemConsoleExecuteResult SystemConsole_CommandValidate(
    const SystemConsoleCommand *parsed, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((parsed->subcommand != NULL) &&
        ((strcmp(parsed->command, "STATUS") == 0) ||
         (strcmp(parsed->command, "INFO") == 0) ||
         (strcmp(parsed->command, "CAPABILITIES") == 0)))
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_text, parsed->command, "BAD_FORMAT", "TOKEN_COUNT",
            SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    if ((SystemLifecycle_IsConfigurationLocked() != 0U) &&
        (SystemConsole_CommandAllowedInFlight(
            parsed->module_token, parsed->command, parsed->subcommand) == 0U))
    {
        return SystemConsole_ErrorWrite(response, capacity, "SYSTEM",
            parsed->command, "LOCKED", "FLIGHT",
            SYSTEM_CONSOLE_EXECUTE_LOCKED);
    }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static SystemConsoleExecuteResult SystemConsole_ListExecute(
    const SystemConsoleCommand *parsed, char *response, uint16_t capacity)
{
    SystemDeviceDescriptor descriptor;
    SystemDeviceInfo info;
    SystemDeviceClass device_class = SystemConsole_DeviceClassGet(
        parsed->module);
    uint16_t device_count = SystemDescriptor_DeviceCountGet();
    uint16_t index;

    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(response, char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(response, capacity, "OK %s LIST count=%u",
        parsed->module_token,
        (unsigned int)ProjectDeviceInstance_CountGet(device_class));
    for (index = 0U; index < SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX; index++)
    {
        if (index >= device_count) { break; }
        if (SystemDescriptor_DeviceGet(index, &descriptor) != SYSTEM_DEVICE_OK)
        { return SYSTEM_CONSOLE_EXECUTE_FAILED; }
        if (descriptor.device_class != device_class) { continue; }
        (void)memset(&info, 0, sizeof(info));
        (void)ProjectDeviceInstance_InfoGet(
            device_class, descriptor.instance_id, &info);
        SystemConsole_TextAppend(response, capacity,
            " DATA instance=%u descriptor_id=%u physical_device_id=%u shared=%u device=%s model=%s",
            (unsigned int)descriptor.instance_id,
            (unsigned int)descriptor.descriptor_id,
            (unsigned int)descriptor.physical_device_id,
            (unsigned int)((descriptor.flags &
                SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL) != 0U),
            (info.device_name != NULL) ? info.device_name : "UNKNOWN",
            (info.model_name != NULL) ? info.model_name : "UNKNOWN");
    }
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

static uint8_t SystemConsole_CoreModuleTryExecute(
    const SystemConsoleCommand *parsed, char *response, uint16_t capacity,
    SystemConsoleExecuteResult *result)
{
    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (parsed->module == SYSTEM_CONSOLE_MODULE_SYSTEM)
    {
        *result = SystemConsole_SystemExecute(
            parsed->command, parsed->subcommand, response, capacity);
        return 1U;
    }
    if (parsed->module == SYSTEM_CONSOLE_MODULE_TIME)
    {
        if (parsed->subcommand != NULL)
        {
            *result = SystemConsole_ErrorWrite(response, capacity,
                parsed->module_text, parsed->command,
                "BAD_FORMAT", "TOKEN_COUNT",
                SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
        }
        else
        { *result = SystemConsole_TimeExecute(parsed->command, response, capacity); }
        return 1U;
    }
    if (parsed->module == SYSTEM_CONSOLE_MODULE_CAL)
    {
        *result = SystemConsole_CalibrationExecute(
            parsed->command, parsed->subcommand, response, capacity);
        return 1U;
    }
    if (parsed->module != SYSTEM_CONSOLE_MODULE_ALIGN) { return 0U; }
    if (parsed->subcommand != NULL)
    {
        *result = SystemConsole_ErrorWrite(response, capacity,
            parsed->module_text, parsed->command,
            "BAD_FORMAT", "TOKEN_COUNT", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    }
    else
    { *result = SystemConsole_AlignmentExecute(parsed->command, response, capacity); }
    return 1U;
}

static SystemConsoleExecuteResult SystemConsole_SampleCommandExecute(
    const SystemConsoleCommand *parsed, char *response, uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((parsed->subcommand != NULL) &&
        (strcmp(parsed->subcommand, "DETAIL") == 0))
    {
        if (parsed->module == SYSTEM_CONSOLE_MODULE_GNSS)
        {
            return SystemConsole_GnssSampleDetailExecute(
                parsed->instance_id, parsed->module_text, response, capacity);
        }
        if (parsed->module == SYSTEM_CONSOLE_MODULE_BARO)
        {
            return SystemConsole_BarometerSampleDetailExecute(
                parsed->instance_id, parsed->module_text, response, capacity);
        }
    }
    if (parsed->subcommand != NULL)
    {
        return SystemConsole_ErrorWrite(response, capacity,
            parsed->module_text, "SAMPLE", "BAD_COMMAND", "UNKNOWN_SUBCOMMAND",
            SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND);
    }
    return SystemConsole_SampleExecute(
        parsed->module, parsed->module_text, parsed->instance_id,
        response, capacity);
}

static uint8_t SystemConsole_DiagnosticsTryExecute(
    const SystemConsoleCommand *parsed, char *response, uint16_t capacity,
    SystemConsoleExecuteResult *result)
{
    SILVERSTAR_ASSERT_OBJECT(parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((parsed->module == SYSTEM_CONSOLE_MODULE_ESTIMATOR) &&
        (strcmp(parsed->command, "STATUS") == 0) &&
        (parsed->subcommand == NULL))
    { *result = SystemConsole_EstimatorStatusExecute(response, capacity); }
    else if ((parsed->module == SYSTEM_CONSOLE_MODULE_ESTIMATOR) &&
             (strcmp(parsed->command, "GNSS") == 0) &&
             (parsed->subcommand == NULL))
    { *result = SystemConsole_EstimatorGnssExecute(response, capacity); }
    else if ((parsed->module == SYSTEM_CONSOLE_MODULE_KF) &&
             (strcmp(parsed->command, "STATUS") == 0) &&
             (parsed->subcommand == NULL))
    { *result = SystemConsole_KfStatusExecute(response, capacity); }
    else if ((parsed->module == SYSTEM_CONSOLE_MODULE_INS) &&
             (strcmp(parsed->command, "STATUS") == 0) &&
             (parsed->subcommand == NULL))
    { *result = SystemConsole_InsStatusExecute(response, capacity); }
    else if ((parsed->module == SYSTEM_CONSOLE_MODULE_ESTIMATOR) &&
             (strcmp(parsed->command, "BARO") == 0) &&
             (parsed->subcommand == NULL))
    { *result = SystemConsole_EstimatorBarometerExecute(response, capacity); }
    else if ((parsed->module == SYSTEM_CONSOLE_MODULE_GNSS) &&
             (strcmp(parsed->command, "NAV") == 0) &&
             (parsed->subcommand != NULL) &&
             (strcmp(parsed->subcommand, "SAT") == 0))
    {
        *result = SystemConsole_GnssNavSatExecute(
            parsed->instance_id, parsed->module_text, response, capacity);
    }
    else if ((parsed->module == SYSTEM_CONSOLE_MODULE_GNSS) &&
             (strcmp(parsed->command, "MON") == 0) &&
             (parsed->subcommand != NULL) &&
             (strcmp(parsed->subcommand, "RF") == 0))
    {
        *result = SystemConsole_GnssMonRfExecute(
            parsed->instance_id, parsed->module_text, response, capacity);
    }
    else
    { return 0U; }
    return 1U;
}

SystemConsoleExecuteResult SystemConsole_ExecuteLine(const char *line,
                                                     char *response,
                                                     uint16_t capacity)
{
    SystemConsoleCommand parsed;
    SystemConsoleExecuteResult result;

    result = SystemConsole_CommandParse(line, &parsed, response, capacity);
    if (result != SYSTEM_CONSOLE_EXECUTE_OK) { return result; }
    SILVERSTAR_ASSERT_OBJECT(&parsed, SystemConsoleCommand,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = SystemConsole_CommandValidate(&parsed, response, capacity);
    if (result != SYSTEM_CONSOLE_EXECUTE_OK) { return result; }
    if (parsed.list_requested != 0U)
    { return SystemConsole_ListExecute(&parsed, response, capacity); }
    if (parsed.extra != NULL)
    {
        return SystemConsole_IoClearExecute(SYSTEM_CONSOLE_MODULE_SYSTEM,
            "SYSTEM CONSOLE", 0U, response, capacity);
    }
    if (SystemConsole_CoreModuleTryExecute(
            &parsed, response, capacity, &result) != 0U)
    { return result; }
    if (strcmp(parsed.command, "SAMPLE") == 0)
    { return SystemConsole_SampleCommandExecute(&parsed, response, capacity); }
    if (SystemConsole_DiagnosticsTryExecute(
            &parsed, response, capacity, &result) != 0U)
    { return result; }
    return SystemConsole_DeviceExecute(
        parsed.module, parsed.module_text, parsed.instance_id,
        parsed.command, parsed.subcommand, response, capacity);
}

static void SystemConsole_DiscontinuityProcess(void)
{
    SystemDeviceIoDiagnostics diagnostics;

    if ((SystemConsoleDevice_IoDiagnosticsGet(&diagnostics) ==
         SYSTEM_DEVICE_OK) &&
        (diagnostics.rx_discontinuity_count !=
         s_console_discontinuity_sequence))
    {
        s_line_length = 0U;
        s_console_discontinuity_sequence =
            diagnostics.rx_discontinuity_count;
    }
}

static void SystemConsole_ResponseWrite(void)
{
    uint16_t response_length = SystemConsole_TextLengthGet(
        s_response, sizeof(s_response));

    (void)SystemConsoleDevice_Write(
        (const uint8_t *)s_response, response_length);
}

static void SystemConsole_CompletedLineProcess(void)
{
    if (s_line_length == 0U) { return; }
    s_line[s_line_length] = '\0';
    (void)SystemConsole_ExecuteLine(s_line, s_response, sizeof(s_response));
    SystemConsole_TextAppend(s_response, sizeof(s_response), "\r\n");
    SystemConsole_ResponseWrite();
    s_line_length = 0U;
}

static void SystemConsole_LineTooLongWrite(void)
{
    s_line_length = 0U;
    (void)CommonFormat_Print(s_response, sizeof(s_response),
        "ERR SYSTEM PARSE code=BAD_FORMAT reason=LINE_TOO_LONG\r\n");
    SystemConsole_ResponseWrite();
}

static void SystemConsole_ByteProcess(uint8_t byte)
{
    if ((byte == '\r') || (byte == '\n'))
    {
        SystemConsole_CompletedLineProcess();
    }
    else if (s_line_length < (sizeof(s_line) - 1U))
    {
        s_line[s_line_length++] = (char)byte;
    }
    else
    {
        SystemConsole_LineTooLongWrite();
    }
}

static void SystemConsole_ReadChunkProcess(
    const uint8_t *data, uint16_t length)
{
    uint16_t index;

    SILVERSTAR_ASSERT_OBJECT(data, uint8_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < length; index++)
    {
        SystemConsole_ByteProcess(data[index]);
    }
}

void SystemConsole_Process(void)
{
    uint8_t data[SYSTEM_CONSOLE_READ_CHUNK];
    uint16_t length;
    uint8_t read_index;

    SILVERSTAR_ASSERT_OBJECT(&s_line[0], char,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemConsole_AsyncEventProcess();
    SystemConsole_DiscontinuityProcess();
    for (read_index = 0U;
         read_index < SYSTEM_CONSOLE_MAX_READ_CHUNKS_PER_CYCLE;
         read_index++)
    {
        if (SystemConsoleDevice_Read(data, sizeof(data), &length) !=
            SYSTEM_DEVICE_OK)
        { break; }
        if (length > sizeof(data))
        {
            s_line_length = 0U;
            break;
        }
        SystemConsole_ReadChunkProcess(data, length);
    }
}
