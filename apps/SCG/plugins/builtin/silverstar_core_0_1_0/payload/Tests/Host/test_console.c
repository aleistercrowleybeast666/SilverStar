#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "project_device_instances.h"
#include "system_alignment.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_console.h"
#include "system_console_if.h"
#include "system_estimator_diagnostics.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_lifecycle.h"
#include "system_magnetometer_if.h"
#include "system_mag_calibration.h"
#include "system_output_if.h"
#include "system_power_if.h"
#include "system_profile.h"
#include "system_startup.h"
#include "system_storage_if.h"
#include "system_task_stack.h"
#include "system_telemetry_transport_if.h"
#include "test_common.h"

void TestFixture_MagEnabledSet(uint8_t enabled);

static uint8_t s_locked;
static SystemLifecycleState s_state = SYSTEM_STATE_PREFLIGHT;
static uint8_t s_gnss_available = 1U;
static SystemStartupReport s_startup_report;
static SystemGnssSample s_gnss_sample;
static SystemBarometerSample s_barometer_sample;
static SystemDeviceHealth s_barometer_health;
static SystemDeviceResult s_barometer_sample_result = SYSTEM_DEVICE_OK;
static SystemDeviceResult s_barometer_health_result = SYSTEM_DEVICE_OK;
static uint8_t s_barometer_present = 1U;
static uint8_t s_barometer_supported = 1U;
static uint64_t s_now_us = 1000000ULL;
static SystemLifecycleStartDiagnostic s_start_diagnostic;
static uint32_t s_console_discontinuity_sequence;
static uint8_t s_console_read_buffer[128];
static uint16_t s_console_read_length;
static uint8_t s_console_read_pending;
static char s_console_write_buffer[256];
static SystemStorageHealth s_storage_health;
static uint32_t s_io_rx_bytes = 100U;
static uint32_t s_gnss_ubx_frame_count = 8U;
static uint32_t s_gnss_parser_resync_count = 2U;
static uint32_t s_imu_valid_frame_count = 12U;
static uint32_t s_imu_checksum_error_count = 1U;
static uint32_t s_imu_parser_resync_count = 3U;
static SystemAlignmentStatus s_alignment_status;
static SystemCalibrationStatus s_calibration_status;
static SystemFlightRecoveryStatus s_flight_recovery_status;
static SystemDeviceResult s_console_write_result = SYSTEM_DEVICE_OK;
static SystemMagnetometerSample s_mag_sample;

static SystemDeviceResult Test_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT |
        SYSTEM_DEVICE_IO_VALID_RX_BYTES |
        SYSTEM_DEVICE_IO_VALID_DISCONTINUITIES |
        SYSTEM_DEVICE_IO_VALID_RX_ACTIVE;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_type = SYSTEM_DEVICE_TRANSPORT_UART;
    diagnostics->rx_bytes = s_io_rx_bytes;
    diagnostics->rx_discontinuity_count = s_console_discontinuity_sequence;
    diagnostics->rx_active = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssIoDetailGet(SystemGnssIoDetail *detail)
{
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(detail, 0, sizeof(*detail));
    detail->ubx_frame_count = s_gnss_ubx_frame_count;
    detail->parser_resync_count = s_gnss_parser_resync_count;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ImuIoDetailGet(SystemImuIoDetail *detail)
{
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    detail->valid_frame_count = s_imu_valid_frame_count;
    detail->checksum_error_count = s_imu_checksum_error_count;
    detail->parser_resync_count = s_imu_parser_resync_count;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ConsoleRead(uint8_t *data,
                                           uint16_t capacity,
                                           uint16_t *length)
{
    if ((data == NULL) || (length == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *length = 0U;
    if (s_console_read_pending == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    TEST_CHECK(s_console_read_length <= capacity);
    (void)memcpy(data, s_console_read_buffer, s_console_read_length);
    *length = s_console_read_length;
    s_console_read_pending = 0U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ConsoleWrite(const uint8_t *data,
                                             uint16_t length)
{
    if ((data == NULL) || (length >= sizeof(s_console_write_buffer)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_console_write_result != SYSTEM_DEVICE_OK)
    {
        return s_console_write_result;
    }
    (void)memcpy(s_console_write_buffer, data, length);
    s_console_write_buffer[length] = '\0';
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssInfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "MOCK_GNSS";
    info->model_name = "GENERIC";
    info->driver_version = "test";
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_CapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = 0x1234U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_DeviceHealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->started = 1U;
    health->online = 1U;
    health->healthy = 1U;
    health->sample_count = 20U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssSampleGet(SystemGnssSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_gnss_sample;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssConfigGet(SystemGnssConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_GNSS_CFG_NAVIGATION_RATE;
    config->navigation_rate_hz = 25U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ImuSampleGet(SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->sequence = 8U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ImuConfigGet(SystemImuConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->output_rate_hz = 200U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_StorageHealthGet(SystemStorageHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_storage_health;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssHardwareConfigRead(
    SystemGnssHardwareConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    config->valid_mask = SYSTEM_GNSS_HW_CONFIG_VALID_BAUD |
                         SYSTEM_GNSS_HW_CONFIG_VALID_NAV_PVT;
    config->baudrate = 921600U;
    config->navigation_rate_hz = 25U;
    config->output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    config->nav_pvt_rate = 1U;
    config->nav_pvt_known = 1U;
    config->elapsed_ms = 42U;
    config->read_result = SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK;
    config->transaction_id = 9U;
    config->detailed_result = SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK;
    config->expected_class = 0x06U;
    config->expected_id = 0x8BU;
    config->received_class = 0x06U;
    config->received_id = 0x8BU;
    config->response_version = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssSatelliteDiagnosticsRead(
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->sample_timestamp_us = s_now_us;
    diagnostics->receive_timestamp_us = s_now_us;
    diagnostics->sequence = 3U;
    diagnostics->supported_fields = SYSTEM_GNSS_SAT_DIAG_FIELD_COUNTS |
        SYSTEM_GNSS_SAT_DIAG_FIELD_CNO |
        SYSTEM_GNSS_SAT_DIAG_FIELD_QUALITY;
    diagnostics->valid_fields = diagnostics->supported_fields;
    diagnostics->satellite_count = 10U;
    diagnostics->used_count = 7U;
    diagnostics->average_cno_dbhz = 30U;
    diagnostics->maximum_cno_dbhz = 43U;
    diagnostics->average_quality = 4U;
    diagnostics->fresh = 1U;
    diagnostics->read_result = SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK;
    diagnostics->detailed_result =
        SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK;
    diagnostics->transaction_id = 10U;
    diagnostics->response_length = 128U;
    diagnostics->expected_class = 0x01U;
    diagnostics->expected_id = 0x35U;
    diagnostics->received_class = 0x01U;
    diagnostics->received_id = 0x35U;
    diagnostics->expected_ck_a = 0x11U;
    diagnostics->expected_ck_b = 0x22U;
    diagnostics->received_ck_a = 0x11U;
    diagnostics->received_ck_b = 0x22U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssRfDiagnosticsRead(
    SystemGnssRfDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->sample_timestamp_us = s_now_us;
    diagnostics->receive_timestamp_us = s_now_us;
    diagnostics->sequence = 4U;
    diagnostics->supported_fields = SYSTEM_GNSS_RF_DIAG_FIELD_ANTENNA |
        SYSTEM_GNSS_RF_DIAG_FIELD_JAMMING |
        SYSTEM_GNSS_RF_DIAG_FIELD_NOISE |
        SYSTEM_GNSS_RF_DIAG_FIELD_AGC;
    diagnostics->valid_fields = diagnostics->supported_fields;
    diagnostics->noise_per_ms = 11U;
    diagnostics->agc_count = 222U;
    diagnostics->rf_block_count = 1U;
    diagnostics->antenna_status = 2U;
    diagnostics->antenna_power = 1U;
    diagnostics->jamming_state = 2U;
    diagnostics->cw_suppression = 6U;
    diagnostics->jamming_indicator = 6U;
    diagnostics->fresh = 1U;
    diagnostics->read_result = SYSTEM_GNSS_CONFIG_READ_RESPONSE_OK;
    diagnostics->detailed_result =
        SYSTEM_GNSS_TRANSACTION_DETAIL_RESPONSE_OK;
    diagnostics->transaction_id = 11U;
    diagnostics->response_length = 28U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerInfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    info->device_name = "MOCK_BARO";
    info->model_name = "GENERIC";
    info->driver_version = "test";
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerHealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_barometer_health_result != SYSTEM_DEVICE_OK)
    {
        return s_barometer_health_result;
    }
    *health = s_barometer_health;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerSampleGet(
    SystemBarometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_barometer_sample_result != SYSTEM_DEVICE_OK)
    {
        return s_barometer_sample_result;
    }
    *sample = s_barometer_sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemImu_InfoGet(SystemDeviceInfo *info)
{ return Test_GnssInfoGet(info); }
SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *mask)
{ return Test_CapabilitiesGet(mask); }
SystemDeviceResult SystemImu_HealthGet(SystemDeviceHealth *health)
{ return Test_DeviceHealthGet(health); }
SystemDeviceResult SystemImu_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{ return Test_IoDiagnosticsGet(diagnostics); }
SystemDeviceResult SystemImu_IoDetailGet(SystemImuIoDetail *detail)
{ return Test_ImuIoDetailGet(detail); }
SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample)
{ return Test_ImuSampleGet(sample); }
SystemDeviceResult SystemImu_EffectiveConfigGet(SystemImuConfig *config)
{ return Test_ImuConfigGet(config); }

SystemDeviceResult SystemGnss_InfoGet(SystemDeviceInfo *info)
{ return (s_gnss_available != 0U) ? Test_GnssInfoGet(info) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *mask)
{ return (s_gnss_available != 0U) ? Test_CapabilitiesGet(mask) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health)
{ return (s_gnss_available != 0U) ? Test_DeviceHealthGet(health) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{ return (s_gnss_available != 0U) ? Test_IoDiagnosticsGet(diagnostics) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_IoDetailGet(SystemGnssIoDetail *detail)
{ return (s_gnss_available != 0U) ? Test_GnssIoDetailGet(detail) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ return (s_gnss_available != 0U) ? Test_GnssSampleGet(sample) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_EffectiveConfigGet(SystemGnssConfig *config)
{ return (s_gnss_available != 0U) ? Test_GnssConfigGet(config) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_HardwareConfigRead(
    SystemGnssHardwareConfig *config)
{ return (s_gnss_available != 0U) ? Test_GnssHardwareConfigRead(config) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_SatelliteDiagnosticsRead(
    SystemGnssSatelliteDiagnostics *diagnostics)
{ return (s_gnss_available != 0U) ?
    Test_GnssSatelliteDiagnosticsRead(diagnostics) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_LatestSatelliteDiagnosticsGet(
    SystemGnssSatelliteDiagnostics *diagnostics)
{ return SystemGnss_SatelliteDiagnosticsRead(diagnostics); }
SystemDeviceResult SystemGnss_RfDiagnosticsRead(
    SystemGnssRfDiagnostics *diagnostics)
{ return (s_gnss_available != 0U) ? Test_GnssRfDiagnosticsRead(diagnostics) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemGnss_LatestRfDiagnosticsGet(
    SystemGnssRfDiagnostics *diagnostics)
{ return SystemGnss_RfDiagnosticsRead(diagnostics); }

SystemDeviceResult SystemTelemetry_InfoGet(SystemDeviceInfo *info)
{ return Test_GnssInfoGet(info); }
SystemDeviceResult SystemTelemetry_CapabilitiesGet(uint32_t *mask)
{ return Test_CapabilitiesGet(mask); }
SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->online = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemTelemetry_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{ return Test_IoDiagnosticsGet(diagnostics); }

SystemDeviceResult SystemConsoleDevice_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{ return Test_IoDiagnosticsGet(diagnostics); }
SystemDeviceResult SystemConsoleDevice_Read(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{ return Test_ConsoleRead(data, capacity, length); }
SystemDeviceResult SystemConsoleDevice_Write(
    const uint8_t *data, uint16_t length)
{ return Test_ConsoleWrite(data, length); }

SystemDeviceResult SystemBarometer_InfoGet(SystemDeviceInfo *info)
{ return (s_barometer_supported != 0U) ? Test_BarometerInfoGet(info) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *mask)
{ return (s_barometer_supported != 0U) ?
    Test_BarometerCapabilitiesGet(mask) : SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemBarometer_HealthGet(SystemDeviceHealth *health)
{ return (s_barometer_supported != 0U) ? Test_BarometerHealthGet(health) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemBarometer_LatestSampleGet(
    SystemBarometerSample *sample)
{ return (s_barometer_supported != 0U) ? Test_BarometerSampleGet(sample) :
    SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemBarometer_EffectiveConfigGet(
    SystemBarometerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult SystemMagnetometer_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemMagnetometer_CapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = 0U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemMagnetometer_HealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemMagnetometer_LatestSampleGet(
    SystemMagnetometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_mag_sample;
    return (s_mag_sample.valid_mask & SYSTEM_MAG_VALID_PHYSICAL_UNIT) != 0U ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}
SystemDeviceResult SystemMagnetometer_EffectiveConfigGet(
    SystemMagnetometerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult SystemHardwareQuaternion_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = 0U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemHardwareQuaternion_HealthGet(
    SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->started = 1U;
    health->online = 1U;
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemHardwareQuaternion_EffectiveConfigGet(
    SystemHardwareQuaternionConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult SystemPower_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemPower_CapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = 0U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemPower_HealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->started = 1U;
    health->online = 1U;
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemPower_LatestSampleGet(SystemPowerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemPower_EffectiveConfigGet(SystemPowerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult SystemOutput_StatusGet(
    uint8_t channel, SystemOutputStatus *status)
{
    (void)channel;
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

const char *SystemStorage_NameGet(void) { return "MOCK_LOG_STORAGE"; }
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{ return Test_StorageHealthGet(health); }

const SystemStartupReport *SystemStartup_GetReport(void)
{
    return &s_startup_report;
}

const SystemStartupDeviceReport *SystemStartup_GetDeviceReport(
    SystemStartupDeviceId device_id)
{
    return (device_id < SYSTEM_STARTUP_DEVICE_COUNT) ?
        &s_startup_report.devices[device_id] : NULL;
}
static const SystemProfile s_profile =
{
    .profile_id = 0x12345678UL
};

void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot)
{
    if (snapshot != NULL)
    {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        if (s_barometer_present != 0U)
        {
            snapshot->capabilities.present_mask = SYSTEM_CAPABILITY_BAROMETER;
        }
        snapshot->ready = 1U;
        snapshot->attitude_status = SYSTEM_HEALTH_ATTITUDE_READY;
    }
}

const char *SystemHealth_AttitudeStatusText(SystemHealthAttitudeStatus status)
{
    return (status == SYSTEM_HEALTH_ATTITUDE_READY) ? "READY" : "UNKNOWN";
}

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return s_state;
}

SystemDeviceResult SystemFlightRecovery_StatusGet(
    SystemFlightRecoveryStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *status = s_flight_recovery_status;
    return SYSTEM_DEVICE_OK;
}

const char *SystemFlightRecovery_ActionText(SystemMissionAction action)
{
    switch (action)
    {
        case SYSTEM_MISSION_ACTION_START: return "MISSION_START";
        case SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY:
            return "PARACHUTE_DEPLOY";
        default: return "UNKNOWN";
    }
}

const char *SystemFlightRecovery_LandingStateText(
    SystemFlightLandingState state)
{
    switch (state)
    {
        case SYSTEM_FLIGHT_LANDING_STATE_BARO_MONITOR:
            return "BARO_MONITOR";
        case SYSTEM_FLIGHT_LANDING_STATE_BARO_IMU_CANDIDATE:
            return "BARO_IMU_CANDIDATE";
        case SYSTEM_FLIGHT_LANDING_STATE_IMPACT_INHIBIT:
            return "IMPACT_INHIBIT";
        case SYSTEM_FLIGHT_LANDING_STATE_IMPACT_ARMED:
            return "IMPACT_ARMED";
        case SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED:
            return "GROUND_IMPACT_CAPTURED";
        case SYSTEM_FLIGHT_LANDING_STATE_POST_IMPACT_CONFIRM:
            return "POST_IMPACT_CONFIRM";
        case SYSTEM_FLIGHT_LANDING_STATE_LANDED: return "LANDED";
        default: return "WAIT_RECOVERY";
    }
}

const char *SystemFlightRecovery_LandingModeText(SystemLandingMode mode)
{
    switch (mode)
    {
        case SYSTEM_LANDING_MODE_STILLNESS: return "STILLNESS";
        case SYSTEM_LANDING_MODE_IMPACT_THEN_STILLNESS:
            return "IMPACT_THEN_STILLNESS";
        case SYSTEM_LANDING_MODE_BARO_IMU_WINDOW: return "BARO_IMU_WINDOW";
        default: return "UNKNOWN";
    }
}

uint8_t SystemLifecycle_IsConfigurationLocked(void)
{
    return s_locked;
}

SystemDeviceResult SystemAlignment_StatusGet(SystemAlignmentStatus *status)
{
    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *status = s_alignment_status;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_SummaryGet(SystemAlignmentSummary *summary)
{
    if (summary == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(summary, 0, sizeof(*summary));
    summary->start_sequence = s_alignment_status.start_sequence;
    summary->selected_mask = s_alignment_status.selected_mask;
    summary->required_mask = s_alignment_status.required_mask;
    summary->ready_mask = s_alignment_status.ready_mask;
    summary->state = s_alignment_status.state;
    summary->stale_reason = s_alignment_status.stale_reason;
    summary->ready = s_alignment_status.ready;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemTaskStack_SnapshotGet(
    SystemTaskStackSnapshot *snapshot)
{
    uint32_t task;

    if (snapshot == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->valid_mask = (1UL << SYSTEM_TASK_STACK_COUNT) - 1UL;
    for (task = 0U; task < SYSTEM_TASK_STACK_COUNT; task++)
    {
        snapshot->task[task].allocation_words = 256U + task;
        snapshot->task[task].high_water_mark_words = 64U + task;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_DetailGet(SystemAlignmentStatus *detail)
{
    return SystemAlignment_StatusGet(detail);
}

SystemDeviceResult SystemAlignment_Start(void)
{
    if ((s_state != SYSTEM_STATE_BOOT) &&
        (s_state != SYSTEM_STATE_SELF_TEST) &&
        (s_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (s_calibration_status.ready == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
    s_alignment_status.capability_mask = 0x07U;
    s_alignment_status.selected_mask = 0x07U;
    s_alignment_status.required_mask = 0x05U;
    s_alignment_status.config_result = SYSTEM_ALIGNMENT_CONFIG_OK;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].state =
        SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_NOT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Stop(void)
{
    if ((s_state != SYSTEM_STATE_BOOT) &&
        (s_state != SYSTEM_STATE_SELF_TEST) &&
        (s_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_alignment_status.ready = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Reset(void)
{
    if ((s_state != SYSTEM_STATE_BOOT) &&
        (s_state != SYSTEM_STATE_SELF_TEST) &&
        (s_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_alignment_status.capability_mask = 0x07U;
    s_alignment_status.selected_mask = 0x07U;
    s_alignment_status.required_mask = 0x05U;
    s_alignment_status.config_result = SYSTEM_ALIGNMENT_CONFIG_OK;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].state =
        SYSTEM_ALIGNMENT_COMPONENT_NOT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_NOT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_NOT_READY;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_StatusGet(SystemCalibrationStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *status = s_calibration_status;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Start(SystemCalibrationMode mode)
{
    SystemDeviceResult alignment_result;

    if ((s_state != SYSTEM_STATE_BOOT) &&
        (s_state != SYSTEM_STATE_SELF_TEST) &&
        (s_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }

    if (mode > SYSTEM_CALIBRATION_MODE_SIX_FACE)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(&s_calibration_status, 0,
                 sizeof(s_calibration_status));
    s_calibration_status.mode = mode;
    s_calibration_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.state = (mode == SYSTEM_CALIBRATION_MODE_NONE) ?
        SYSTEM_CALIBRATION_STATE_READY :
        ((mode == SYSTEM_CALIBRATION_MODE_SIX_FACE) ?
            SYSTEM_CALIBRATION_STATE_WAIT_FACE :
            SYSTEM_CALIBRATION_STATE_COLLECTING);
    s_calibration_status.ready = (uint8_t)(
        mode == SYSTEM_CALIBRATION_MODE_NONE);
    s_calibration_status.correction.mode = mode;
    s_calibration_status.correction.ready = s_calibration_status.ready;
    s_calibration_status.correction.accel_scale[0] = 1.0f;
    s_calibration_status.correction.accel_scale[1] = 1.0f;
    s_calibration_status.correction.accel_scale[2] = 1.0f;
    s_calibration_status.correction.gyro_scale[0] = 1.0f;
    s_calibration_status.correction.gyro_scale[1] = 1.0f;
    s_calibration_status.correction.gyro_scale[2] = 1.0f;
    alignment_result = SystemAlignment_Reset();
    if (alignment_result != SYSTEM_DEVICE_OK)
    {
        return alignment_result;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_FaceCollect(SystemCalibrationFace face)
{
    if ((s_calibration_status.mode != SYSTEM_CALIBRATION_MODE_SIX_FACE) ||
        (face > SYSTEM_CALIBRATION_FACE_Z_NEGATIVE))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_calibration_status.current_face = face;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_COLLECTING;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Stop(void)
{
    if ((s_state != SYSTEM_STATE_BOOT) &&
        (s_state != SYSTEM_STATE_SELF_TEST) &&
        (s_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_IDLE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Reset(void)
{
    if ((s_state != SYSTEM_STATE_BOOT) &&
        (s_state != SYSTEM_STATE_SELF_TEST) &&
        (s_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    SystemDeviceResult alignment_result;

    (void)memset(&s_calibration_status, 0,
                 sizeof(s_calibration_status));
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
    s_calibration_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.last_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_IDLE;
    alignment_result = SystemAlignment_Reset();
    if (alignment_result != SYSTEM_DEVICE_OK)
    {
        return alignment_result;
    }
    return SYSTEM_DEVICE_OK;
}

const char *SystemCalibration_ModeText(SystemCalibrationMode mode)
{
    if (mode == SYSTEM_CALIBRATION_MODE_NONE) { return "NONE"; }
    if (mode == SYSTEM_CALIBRATION_MODE_ONE_FACE) { return "ONE_FACE"; }
    if (mode == SYSTEM_CALIBRATION_MODE_SIX_FACE) { return "SIX_FACE"; }
    return "NOT_SELECTED";
}

const char *SystemCalibration_StateText(SystemCalibrationState state)
{
    static const char *const text[] = {
        "IDLE", "WAIT_FACE", "COLLECTING", "CHECKING", "READY", "FAILED"
    };
    return (state <= SYSTEM_CALIBRATION_STATE_FAILED) ? text[state] : "FAILED";
}

const char *SystemCalibration_FaceText(SystemCalibrationFace face)
{
    static const char *const text[] = {"X+", "X-", "Y+", "Y-", "Z+", "Z-"};
    return (face <= SYSTEM_CALIBRATION_FACE_Z_NEGATIVE) ? text[face] : "NONE";
}

const char *SystemCalibration_WaitReasonText(
    SystemCalibrationWaitReason reason)
{
    static const char *const text[] = {
        "NONE", "NO_STREAM", "GYRO_MOVING", "ACCEL_MAGNITUDE",
        "GRAVITY_DIRECTION", "VARIANCE", "SAMPLE_GAP"
    };

    return (reason <= SYSTEM_CALIBRATION_WAIT_SAMPLE_GAP) ?
        text[reason] : "UNKNOWN";
}

const char *SystemCalibration_FaceResultText(
    SystemCalibrationFaceResult result)
{
    if (result == SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE) { return "PASSED"; }
    if (result == SYSTEM_CALIBRATION_FACE_RESULT_FAILED) { return "FAILED"; }
    return "NONE";
}

const SystemProfile *SystemProfile_Get(void)
{
    return &s_profile;
}

uint8_t SystemProfile_IsFrozen(void)
{
    return 0U;
}

void SystemCapabilities_Get(SystemCapabilities *capabilities)
{
    if (capabilities != NULL)
    {
        (void)memset(capabilities, 0, sizeof(*capabilities));
    }
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    return s_now_us;
}

uint8_t SystemTime_IsMissionStarted(void)
{
    return 0U;
}

uint64_t SystemTime_GetMissionUs(void)
{
    return 0ULL;
}

static void Test_Execute(const char *line,
                         SystemConsoleExecuteResult expected,
                         const char *response_fragment)
{
    char response[SYSTEM_CONSOLE_RESPONSE_CAPACITY];

    (void)memset(response, 0, sizeof(response));
    TEST_CHECK(SystemConsole_ExecuteLine(line, response,
                                         sizeof(response)) == expected);
    if (strstr(response, response_fragment) == NULL)
    {
        (void)fprintf(stderr,
            "console mismatch command='%s' expected_fragment='%s' response='%s'\n",
            line, response_fragment, response);
    }
    TEST_CHECK(strstr(response, response_fragment) != NULL);
}

static void Test_ExecuteAbsent(const char *line, const char *fragment)
{
    char response[SYSTEM_CONSOLE_RESPONSE_CAPACITY];

    (void)memset(response, 0, sizeof(response));
    TEST_CHECK(SystemConsole_ExecuteLine(line, response,
        sizeof(response)) == SYSTEM_CONSOLE_EXECUTE_OK);
    TEST_CHECK(strstr(response, fragment) == NULL);
}

SystemDeviceResult SystemLifecycle_SubmitStart(
    const SystemLifecycleStartRequest *request)
{
    if (request == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(&s_start_diagnostic, 0, sizeof(s_start_diagnostic));
    s_start_diagnostic.response.source = request->source;
    s_start_diagnostic.response.request_id = request->request_id;
    s_start_diagnostic.response.timestamp_us = s_now_us;
    s_start_diagnostic.response.result = SYSTEM_LIFECYCLE_START_OK;
    s_start_diagnostic.response.reason = SYSTEM_START_REASON_NONE;
    s_start_diagnostic.sequence = 1U;
    s_start_diagnostic.valid = 1U;
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemLifecycle_GetLastStartDiagnostic(
    SystemStartSource source,
    SystemLifecycleStartDiagnostic *diagnostic)
{
    if ((diagnostic == NULL) || (s_start_diagnostic.valid == 0U) ||
        (s_start_diagnostic.response.source != source))
    {
        return 0U;
    }
    *diagnostic = s_start_diagnostic;
    return 1U;
}

const char *SystemLifecycle_StartResultText(SystemLifecycleStartResult result)
{
    return (result == SYSTEM_LIFECYCLE_START_OK) ? "OK" : "FAILED";
}

const char *SystemLifecycle_StartReasonText(SystemLifecycleStartReason reason)
{
    return (reason == SYSTEM_START_REASON_NONE) ? "NONE" : "FAILED";
}

static void Test_ExecuteExact(const char *line, const char *expected)
{
    char response[SYSTEM_CONSOLE_RESPONSE_CAPACITY];

    (void)memset(response, 0, sizeof(response));
    TEST_CHECK(SystemConsole_ExecuteLine(line, response,
                                         sizeof(response)) ==
               SYSTEM_CONSOLE_EXECUTE_OK);
    TEST_CHECK(strcmp(response, expected) == 0);
}

static void Test_NavigationDiagnostics(void)
{
    SystemEstimatorStatusDiagnostics estimator;
    SystemEstimatorGnssDiagnostics gnss;
    SystemKfDiagnostics kf;
    SystemInsDiagnostics ins;

    (void)memset(&estimator, 0, sizeof(estimator));
    estimator.last_state_timestamp_us = 900000ULL;
    estimator.imu_prediction_count = 42U;
    estimator.mode = SYSTEM_ESTIMATOR_MODE_KF6;
    estimator.attitude_source =
        SYSTEM_ESTIMATOR_ATTITUDE_SOURCE_SOFTWARE_INS;
    estimator.position_source = SYSTEM_ESTIMATOR_POSITION_SOURCE_KF6;
    estimator.initialized = 1U;
    estimator.started = 1U;
    SystemEstimatorStatusDiagnostics_Publish(&estimator);

    (void)memset(&gnss, 0, sizeof(gnss));
    gnss.supported = 1U;
    gnss.last_update_state = SYSTEM_ESTIMATOR_GNSS_UPDATE_DISABLED;
    gnss.last_skip_reason =
        SYSTEM_ESTIMATOR_GNSS_SKIP_NO_PREFLIGHT_ORIGIN;
    SystemEstimatorGnssDiagnostics_Publish(&gnss);
    Test_Execute("SYSTEM READY", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ready=1");
    Test_Execute("SYSTEM READY", SYSTEM_CONSOLE_EXECUTE_OK,
                 "gnss_ready=0 gnss_origin_ready=0 gnss_fusion_enabled=0");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "fusion_enabled=0 origin_valid=0");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "last_update_state=DISABLED");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "reason=NO_PREFLIGHT_ORIGIN");

    gnss.gnss_ready = 1U;
    gnss.origin_ready = 1U;
    gnss.origin_valid = 1U;
    gnss.fusion_enabled = 1U;
    gnss.origin_lat_e7 = 311234567;
    gnss.origin_lon_e7 = 1211234567;
    gnss.origin_height_mm = 12345;
    gnss.position_updates = 5U;
    gnss.velocity_updates = 4U;
    gnss.position_accept_count = 4U;
    gnss.position_reject_count = 1U;
    gnss.velocity_accept_count = 3U;
    gnss.velocity_reject_count = 1U;
    gnss.last_measurement_timestamp_us = 990000ULL;
    gnss.last_state_timestamp_us = 1000000ULL;
    gnss.position_horizontal_nis = 1.25f;
    gnss.position_vertical_nis = 2.50f;
    gnss.velocity_horizontal_nis = 3.75f;
    gnss.velocity_vertical_nis = 5.00f;
    gnss.innovation_e_m = 1.0f;
    gnss.innovation_u_m = -2.0f;
    gnss.covariance_position_e_m2 = 4.0f;
    gnss.covariance_velocity_u_m2ps2 = 0.25f;
    gnss.position_horizontal_accept_count = 4U;
    gnss.position_horizontal_reject_count = 1U;
    gnss.position_vertical_accept_count = 3U;
    gnss.position_vertical_reject_count = 2U;
    gnss.velocity_horizontal_accept_count = 3U;
    gnss.velocity_horizontal_reject_count = 1U;
    gnss.velocity_vertical_accept_count = 2U;
    gnss.velocity_vertical_reject_count = 2U;
    gnss.position_horizontal_reject_streak = 5U;
    gnss.reacquire_active_mask = 0x05U;
    gnss.reacquire_count = 2U;
    gnss.last_inflation_group =
        SYSTEM_ESTIMATOR_GNSS_INFLATION_VELOCITY_HORIZONTAL;
    gnss.last_inflation_factor = 1.5f;
    gnss.last_inflation_attempt = 3U;
    gnss.last_update_state = SYSTEM_ESTIMATOR_GNSS_UPDATE_ACCEPTED;
    gnss.last_skip_reason = SYSTEM_ESTIMATOR_GNSS_SKIP_NONE;
    SystemEstimatorGnssDiagnostics_Publish(&gnss);
    Test_Execute("SYSTEM READY", SYSTEM_CONSOLE_EXECUTE_OK,
                 "gnss_ready=1 gnss_origin_ready=1 gnss_fusion_enabled=1");
    Test_Execute("ESTIMATOR STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "initialized=1 started=1 mode=KF6");
    Test_Execute("ESTIMATOR STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "imu_prediction_count=42 last_state_timestamp=900000");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "position_accept_count=4 position_reject_count=1");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "last_update_state=ACCEPTED last_skip_reason=NONE");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "position_horizontal_nis=1.250 position_vertical_nis=2.500");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "position_horizontal_accept_count=4 position_horizontal_reject_count=1");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "reacquire_active_mask=0x05 reacquire_count=2 last_inflation_group=VELOCITY_HORIZONTAL last_inflation_factor=1.500 last_inflation_attempt=3");

    (void)memset(&kf, 0, sizeof(kf));
    kf.initialized = 1U;
    kf.state_dimension = 6U;
    kf.prediction_count = 42U;
    kf.sequential_update_count = 12U;
    kf.position_update_count = 5U;
    kf.velocity_update_count = 4U;
    kf.baro_update_count = 3U;
    kf.last_update_type = SYSTEM_KF_UPDATE_BAROMETER;
    kf.last_update_timestamp_us = 995000ULL;
    kf.innovation_reject_count = 2U;
    kf.reacquire_count = 2U;
    kf.reacquire_active_mask = 0x05U;
    SystemKfDiagnostics_Publish(&kf);
    Test_Execute("KF STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "initialized=1 state_dimension=6 prediction_count=42");
    Test_Execute("KF STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "sequential_update_count=12 position_update_count=5 velocity_update_count=4 baro_update_count=3");
    Test_Execute("KF STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "last_update_type=BAROMETER last_update_time=995000 innovation_reject_count=2");
    Test_Execute("KF STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "reacquire_count=2 reacquire_active_mask=0x05");

    (void)memset(&ins, 0, sizeof(ins));
    ins.initialized = 1U;
    ins.started = 1U;
    ins.attitude_ready = 1U;
    ins.quaternion_valid = 1U;
    ins.velocity_valid = 1U;
    ins.position_valid = 1U;
    ins.software_attitude_propagation = 1U;
    ins.bias_ready = 1U;
    ins.bias_samples = 100U;
    ins.last_update_timestamp_us = 998000ULL;
    SystemInsDiagnostics_Publish(&ins);
    Test_Execute("INS STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "initialized=1 started=1 attitude_ready=1 quaternion_valid=1");
    Test_Execute("INS STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "velocity_valid=1 position_valid=1 software_attitude_propagation=1");
    Test_Execute("INS STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "bias_ready=1 bias_samples=100 last_update_timestamp=998000");
}

static void Test_SensorDiagnostics(void)
{
    SystemEstimatorBaroDiagnostics diagnostics;

    (void)memset(&s_gnss_sample, 0, sizeof(s_gnss_sample));
    s_gnss_sample.sample_timestamp_us = s_now_us;
    s_gnss_sample.sequence = 7U;
    s_gnss_sample.latitude_e7 = 311234567;
    s_gnss_sample.longitude_e7 = 1211234567;
    s_gnss_sample.ellipsoid_height_mm = 12345;
    s_gnss_sample.fix_type = 3U;
    s_gnss_sample.position_usable = 0U;
    s_gnss_sample.position_reject_mask = SYSTEM_GNSS_REJECT_FIX_FLAG;
    s_gnss_sample.velocity_reject_mask = SYSTEM_GNSS_REJECT_SACC;
    s_gnss_sample.supported_fields = SYSTEM_GNSS_FIELD_FIX_TYPE |
        SYSTEM_GNSS_FIELD_POSITION | SYSTEM_GNSS_FIELD_HEIGHT;
    s_gnss_sample.valid_fields = s_gnss_sample.supported_fields;
    Test_ExecuteExact(
        "GNSS 0 SAMPLE",
        "OK GNSS 0 SAMPLE seq=7 lat_e7=311234567 lon_e7=1211234567 fix=3 position_usable=0 velocity_mask=0x00");
    Test_Execute("GNSS 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "fix_type=3 fix_ok=UNSUPPORTED num_sv=UNSUPPORTED");
    Test_Execute("GNSS 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "hacc_mm=UNSUPPORTED vacc_mm=UNSUPPORTED sacc_mmps=UNSUPPORTED");
    Test_Execute("GNSS 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "position_reject_mask=0x00000004");

    (void)memset(&s_barometer_sample, 0, sizeof(s_barometer_sample));
    s_barometer_sample.sample_timestamp_us = s_now_us;
    s_barometer_sample.sequence = 9U;
    s_barometer_sample.pressure_raw_pa = 100100;
    s_barometer_sample.altitude_raw_cm = 1234;
    s_barometer_sample.pressure_pa = 100100.0f;
    s_barometer_sample.altitude_m = 12.34f;
    s_barometer_sample.supported_fields = SYSTEM_BARO_FIELD_PRESSURE |
                                          SYSTEM_BARO_FIELD_ALTITUDE;
    s_barometer_sample.valid_fields = s_barometer_sample.supported_fields;
    s_barometer_sample.valid_mask = s_barometer_sample.valid_fields;
    (void)memset(&s_barometer_health, 0, sizeof(s_barometer_health));
    s_barometer_health.initialized = 1U;
    s_barometer_health.started = 1U;
    s_barometer_health.online = 1U;
    s_barometer_health.healthy = 1U;
    s_barometer_sample_result = SYSTEM_DEVICE_OK;
    s_barometer_health_result = SYSTEM_DEVICE_OK;
    s_barometer_present = 1U;
    Test_ExecuteExact(
        "BARO 0 SAMPLE",
        "OK BARO 0 SAMPLE seq=9 pressure_pa=100100 altitude_cm=1234 valid=0x00000003");
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "sample_valid=1 sample_fresh=1 sample_age_ms=0");
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "temperature_c=UNSUPPORTED altitude_m=12.340 status=OK");

    s_barometer_sample.sample_timestamp_us = s_now_us -
        SYSTEM_ESTIMATOR_MEASUREMENT_MAX_AGE_US - 1ULL;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "status=STALE");
    s_barometer_sample_result = SYSTEM_DEVICE_NOT_READY;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "status=NOT_READY");
    s_barometer_sample_result = SYSTEM_DEVICE_OK;

    s_barometer_present = 0U;
    s_barometer_health.online = 0U;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "present=1");
    s_barometer_present = 1U;
    s_barometer_health.initialized = 0U;
    s_barometer_health.started = 0U;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "status=NOT_CONFIGURED");
    s_barometer_health.initialized = 1U;
    s_barometer_health.started = 1U;
    s_barometer_health.online = 1U;
    s_barometer_sample.sample_timestamp_us = s_now_us;
    s_barometer_sample.valid_fields = 0U;
    s_barometer_sample.valid_mask = 0U;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "status=INVALID");
    s_barometer_health_result = SYSTEM_DEVICE_IO_ERROR;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "status=FAILED");
    s_barometer_health_result = SYSTEM_DEVICE_OK;
    s_barometer_sample.valid_fields = s_barometer_sample.supported_fields;
    s_barometer_sample.valid_mask = s_barometer_sample.valid_fields;

    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    diagnostics.sample_timestamp_us = s_now_us;
    diagnostics.last_update_timestamp_us = s_now_us;
    diagnostics.origin_sample_count = 100U;
    diagnostics.origin_required_count = 100U;
    diagnostics.accepted_count = 4U;
    diagnostics.softened_count = 2U;
    diagnostics.rejected_count = 1U;
    diagnostics.skipped_count = 3U;
    diagnostics.origin_altitude_m = 12.0f;
    diagnostics.origin_pressure_pa = 100100.0f;
    diagnostics.relative_altitude_m = 1.25f;
    diagnostics.measurement_variance = 25.0f;
    diagnostics.last_innovation = 0.5f;
    diagnostics.last_innovation_variance = 26.0f;
    diagnostics.last_nis = 0.01f;
    diagnostics.origin_state = SYSTEM_ESTIMATOR_BARO_ORIGIN_FROZEN;
    diagnostics.last_update_state = SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED;
    diagnostics.last_skip_reason = SYSTEM_ESTIMATOR_BARO_SKIP_NONE;
    diagnostics.source_supported = 1U;
    diagnostics.sample_valid = 1U;
    diagnostics.origin_pressure_valid = 1U;
    diagnostics.origin_state = SYSTEM_ESTIMATOR_BARO_ORIGIN_COLLECTING;
    diagnostics.origin_sample_count = 20U;
    SystemEstimatorBaroDiagnostics_Publish(&diagnostics);
    Test_Execute("ESTIMATOR BARO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "origin_state=COLLECTING origin_sample_count=20");
    diagnostics.origin_state = SYSTEM_ESTIMATOR_BARO_ORIGIN_FROZEN;
    diagnostics.origin_sample_count = 100U;
    SystemEstimatorBaroDiagnostics_Publish(&diagnostics);
    Test_Execute("ESTIMATOR BARO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "origin_state=FROZEN origin_sample_count=100");
    Test_Execute("ESTIMATOR BARO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "last_update_state=ACCEPTED");
    Test_Execute("ESTIMATOR BARO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "accepted_count=4 softened_count=2 rejected_count=1 skipped_count=3");

    s_now_us = (((uint64_t)UINT32_MAX + 10ULL) * 1000ULL);
    s_gnss_sample.sample_timestamp_us = 1ULL;
    Test_Execute("GNSS 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "age_ms=4294967295");
    s_barometer_sample.sample_timestamp_us = 1ULL;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "sample_age_ms=4294967295");
    s_now_us = 1000000ULL;

    s_barometer_supported = 0U;
    Test_Execute("BARO 0 SAMPLE DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "status=UNSUPPORTED");
    s_barometer_supported = 1U;
}

static void Test_ConsoleDiscontinuityClearsPartialLine(void)
{
    const char partial[] = "GARBAGE";
    const char complete[] = "SYSTEM STATUS\r\n";

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    (void)memcpy(s_console_read_buffer, partial, sizeof(partial) - 1U);
    s_console_read_length = (uint16_t)(sizeof(partial) - 1U);
    s_console_read_pending = 1U;
    SystemConsole_Process();
    TEST_CHECK(s_console_write_buffer[0] == '\0');

    s_console_discontinuity_sequence++;
    (void)memcpy(s_console_read_buffer, complete, sizeof(complete) - 1U);
    s_console_read_length = (uint16_t)(sizeof(complete) - 1U);
    s_console_read_pending = 1U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer, "OK SYSTEM STATUS") != NULL);
}

static void Test_IoClear(void)
{
    Test_ExecuteExact("IMU 0 IO CLEAR", "OK IMU 0 IO CLEAR");
    Test_Execute("IMU 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=0");
    Test_Execute("IMU 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "valid_frames=0 checksum_errors=0 parser_resyncs=0");
    Test_Execute("BARO 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=0");
    Test_Execute("ATTITUDE 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "owner=IMU owner_instance=0 physical_device_id=1");
    Test_ExecuteExact("BARO 0 IO CLEAR", "OK BARO 0 IO CLEAR");
    s_io_rx_bytes += 7U;
    s_imu_valid_frame_count += 4U;
    s_imu_checksum_error_count += 2U;
    s_imu_parser_resync_count += 1U;
    Test_Execute("IMU 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=7");
    Test_Execute("IMU 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "valid_frames=4 checksum_errors=2 parser_resyncs=1");

    Test_ExecuteExact("GNSS 0 IO CLEAR", "OK GNSS 0 IO CLEAR");
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=0");
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ubx_frames=0");
    s_io_rx_bytes += 5U;
    s_gnss_ubx_frame_count += 3U;
    s_gnss_parser_resync_count += 1U;
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=5");
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ubx_frames=3");

    Test_ExecuteExact("TELEMETRY 0 IO CLEAR", "OK TELEMETRY 0 IO CLEAR");
    Test_Execute("TELEMETRY 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=0");
    Test_ExecuteExact("SYSTEM CONSOLE IO CLEAR",
                      "OK SYSTEM CONSOLE IO CLEAR");
    Test_Execute("SYSTEM CONSOLE IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "rx_bytes=0");
    Test_Execute("LOG IO CLEAR", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "code=UNSUPPORTED");
}


static void Test_AsyncCalibrationAlignmentEvents(void)
{
    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_console_read_pending = 0U;

    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_ONE_FACE;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_COLLECTING;
    s_calibration_status.diagnostic_sequence = 1U;
    s_calibration_status.diagnostic_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.diagnostic_reason =
        SYSTEM_CALIBRATION_WAIT_GYRO_MOVING;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT CAL DIAG face=NONE reason=GYRO_MOVING") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer, "EVENT CAL DIAG") == NULL);

    s_calibration_status.diagnostic_sequence = 2U;
    s_calibration_status.diagnostic_face =
        SYSTEM_CALIBRATION_FACE_X_POSITIVE;
    s_calibration_status.diagnostic_reason =
        SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT CAL DIAG face=X+ reason=GRAVITY_DIRECTION") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_calibration_status.diagnostic_sequence = 3U;
    s_calibration_status.diagnostic_reason = SYSTEM_CALIBRATION_WAIT_NONE;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT CAL DIAG face=X+ reason=NONE") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_SIX_FACE;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_WAIT_FACE;
    s_calibration_status.ready = 0U;
    s_calibration_status.start_sequence = 1U;
    s_calibration_status.last_face = SYSTEM_CALIBRATION_FACE_X_POSITIVE;
    s_calibration_status.last_face_result =
        SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE;
    s_calibration_status.face_event_sequence = 1U;
    s_calibration_status.samples = 196U;
    s_calibration_status.completed_face_mask = 0x01U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT CAL FACE face=X+ result=PASSED") != NULL);
    TEST_CHECK(strstr(s_console_write_buffer,
        "completed_face_mask=0x01") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_READY;
    s_calibration_status.ready = 1U;
    s_calibration_status.completed_face_mask = 0x3FU;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT CAL COMPLETE mode=SIX_FACE result=PASSED") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_alignment_status.start_sequence = 1U;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    s_alignment_status.ready_mask = 0x07U;
    s_alignment_status.selected_mask = 0x07U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].ready =
        1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].ready =
        1U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT ALIGN COMPLETE result=PASSED") != NULL);
    TEST_CHECK(strstr(s_console_write_buffer,
        "ready_mask=0x00000007") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_STALE;
    s_alignment_status.stale_reason = SYSTEM_ALIGNMENT_STALE_REASON_MOTION;
    s_alignment_status.ready = 0U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT ALIGN STALE reason=MOTION ready_mask=0x00000007") != NULL);
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
        "state=STALE ready=0");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
        "stale_reason=MOTION");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
        "state=STALE ready=0");
}

static void Test_AsyncFlightRecoveryEvents(void)
{
    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_flight_recovery_status.action_event_sequence = 1U;
    s_flight_recovery_status.last_action =
        SYSTEM_MISSION_ACTION_PARACHUTE_DEPLOY;
    s_flight_recovery_status.last_action_result = SYSTEM_DEVICE_IO_ERROR;
    s_flight_recovery_status.last_action_mission_time_ms = 50U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT FLIGHT ACTION_FAILED action=PARACHUTE_DEPLOY result=IO_ERROR time_ms=50") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_flight_recovery_status.action_event_sequence = 2U;
    s_flight_recovery_status.last_action = SYSTEM_MISSION_ACTION_START;
    s_flight_recovery_status.last_action_mission_time_ms = 60U;
    s_console_write_result = SYSTEM_DEVICE_IO_ERROR;
    SystemConsole_Process();
    TEST_CHECK(s_console_write_buffer[0] == '\0');
    s_console_write_result = SYSTEM_DEVICE_OK;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT FLIGHT ACTION_FAILED action=MISSION_START result=IO_ERROR time_ms=60") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_flight_recovery_status.deploy_event_sequence = 1U;
    s_flight_recovery_status.deploy_matched_mask =
        SYSTEM_DEPLOY_TRIGGER_TILT | SYSTEM_DEPLOY_TRIGGER_DELAY;
    s_flight_recovery_status.deploy_tilt_angle_deg = 46.25f;
    s_flight_recovery_status.deploy_vertical_velocity_mps = -1.25f;
    s_flight_recovery_status.deploy_delay_ms = 5000U;
    s_flight_recovery_status.deploy_event_mission_time_ms = 70U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT FLIGHT PARACHUTE_DEPLOY matched_mask=0x05 time_ms=70 tilt_deg=46.25 vz_mps=-1.25 delay_ms=5000") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_flight_recovery_status.impact_event_sequence = 1U;
    s_flight_recovery_status.impact_event_mission_time_ms = 75U;
    s_flight_recovery_status.impact_metric_mps2 = 32.5f;
    s_flight_recovery_status.impact_peak_mps2 = 34.0f;
    s_flight_recovery_status.landing_state =
        SYSTEM_FLIGHT_LANDING_STATE_GROUND_IMPACT_CAPTURED;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT FLIGHT LANDING_IMPACT time_ms=75 metric_mps2=32.50 peak_mps2=34.00 state=GROUND_IMPACT_CAPTURED") != NULL);

    (void)memset(s_console_write_buffer, 0,
                 sizeof(s_console_write_buffer));
    s_flight_recovery_status.landing_event_sequence = 1U;
    s_flight_recovery_status.landing_event_mission_time_ms = 80U;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT FLIGHT LANDING time_ms=80") != NULL);
}

static void Test_MultiInstanceFacade(void)
{
    SystemImuSample imu_zero;
    SystemImuSample imu_one;
    SystemDeviceHealth health_zero;
    SystemDeviceHealth health_one;
    SystemDeviceDescriptor descriptor_zero;
    SystemDeviceDescriptor descriptor_one;

    TEST_CHECK(ProjectImuInstance_CountGet() == 2U);
    TEST_CHECK(ProjectGnssInstance_CountGet() == 2U);
    TEST_CHECK(ProjectImuInstance_LatestSampleGet(0U, &imu_zero) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(ProjectImuInstance_LatestSampleGet(1U, &imu_one) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(imu_zero.sequence == 8U);
    TEST_CHECK(imu_one.sequence == 1008U);
    TEST_CHECK(ProjectImuInstance_HealthGet(0U, &health_zero) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(ProjectImuInstance_HealthGet(1U, &health_one) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(health_zero.health_flags != health_one.health_flags);
    TEST_CHECK(ProjectDeviceInstance_DescriptorGet(
                   SYSTEM_DEVICE_CLASS_IMU, 0U, &descriptor_zero) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(ProjectDeviceInstance_DescriptorGet(
                   SYSTEM_DEVICE_CLASS_IMU, 1U, &descriptor_one) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(descriptor_zero.descriptor_id != descriptor_one.descriptor_id);
    TEST_CHECK(descriptor_zero.physical_device_id !=
               descriptor_one.physical_device_id);
    TEST_CHECK(ProjectImuInstance_LatestSampleGet(2U, &imu_one) ==
               SYSTEM_DEVICE_NOT_PRESENT);
}

static void Test_MagStream(void)
{
    TestFixture_MagEnabledSet(1U);
    (void)memset(&s_mag_sample, 0, sizeof(s_mag_sample));
    s_mag_sample.valid_mask = SYSTEM_MAG_VALID_PHYSICAL_UNIT;
    s_mag_sample.sequence = 17U;
    s_mag_sample.sample_timestamp_us = s_now_us;
    s_mag_sample.magnetic_field_b_uT[0] = 25.5f;
    s_mag_sample.magnetic_field_b_uT[1] = -18.25f;
    s_mag_sample.magnetic_field_b_uT[2] = 42.0f;
    TEST_CHECK(SystemConsole_Init() == SYSTEM_DEVICE_OK);
    Test_Execute("MAG 0 STREAM START", SYSTEM_CONSOLE_EXECUTE_OK,
        "state=STARTED rate_hz=20");
    (void)memset(s_console_write_buffer, 0, sizeof(s_console_write_buffer));
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer,
        "EVENT MAG SAMPLE instance=0 physical_device_id=11 seq=17") != NULL);
    (void)memset(s_console_write_buffer, 0, sizeof(s_console_write_buffer));
    SystemConsole_Process();
    TEST_CHECK(s_console_write_buffer[0] == '\0');
    s_now_us += 50000ULL;
    s_mag_sample.sequence++;
    s_mag_sample.sample_timestamp_us = s_now_us;
    SystemConsole_Process();
    TEST_CHECK(strstr(s_console_write_buffer, "seq=18") != NULL);
    Test_Execute("MAG 0 STREAM STOP", SYSTEM_CONSOLE_EXECUTE_OK,
        "state=STOPPED");
    TestFixture_MagEnabledSet(0U);
}

#define TEST_MAG_PACKET_GOOD \
    "01010B00000000004041000000C1000040400000803F0000000000000000" \
    "000000000000803F0000000000000000000000000000803F00004842CDCC" \
    "4C3ECDCC4C3F9A99993F4B4B4B4B4B4B4B4B58024754EB56"
#define TEST_MAG_PACKET_WRONG_DEVICE \
    "01012A00000000004041000000C1000040400000803F0000000000000000" \
    "000000000000803F0000000000000000000000000000803F00004842CDCC" \
    "4C3ECDCC4C3F9A99993F4B4B4B4B4B4B4B4B580211E8A9C5"

static void Test_MagCalibrationObject(void)
{
    SystemMagnetometerSample sample;
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    uint8_t instance_id = UINT8_MAX;
    uint32_t request_id = 0U;
    TestFixture_MagEnabledSet(1U);
    SystemMagCalibration_Init();
    Test_Execute("MAG 0 CAL APPLY " TEST_MAG_PACKET_WRONG_DEVICE,
        SYSTEM_CONSOLE_EXECUTE_FAILED, "WRONG_DEVICE");
    Test_Execute("MAG 0 CAL APPLY " TEST_MAG_PACKET_GOOD,
        SYSTEM_CONSOLE_EXECUTE_OK, "action=APPLY accepted=1");
    Test_Execute("MAG 0 CAL READ", SYSTEM_CONSOLE_EXECUTE_OK,
        "state=APPLIED generation=0 physical_device_id=11");
    (void)memset(&sample, 0, sizeof(sample));
    sample.valid_mask = SYSTEM_MAG_VALID_PHYSICAL_UNIT;
    sample.magnetic_field_b_uT[0] = 13.0f;
    sample.magnetic_field_b_uT[1] = -6.0f;
    sample.magnetic_field_b_uT[2] = 6.0f;
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) ==
        SystemMagCalibrationResult_Ok);
    TEST_CHECK(sample.magnetic_field_b_uT[0] == 1.0f);
    TEST_CHECK(sample.magnetic_field_b_uT[1] == 2.0f);
    TEST_CHECK(sample.magnetic_field_b_uT[2] == 3.0f);
    TEST_CHECK(sample.calibration_valid == 1U);
    Test_Execute("MAG 0 CAL SAVE", SYSTEM_CONSOLE_EXECUTE_OK,
        "action=SAVE accepted=1");
    TEST_CHECK(SystemMagCalibration_PendingGet(
        &instance_id, packet, &request_id) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(instance_id == 0U && packet[2] == 11U && request_id != 0U);
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U, request_id, 1U, 7U) ==
        SystemMagCalibrationResult_Ok);
    Test_Execute("MAG 0 CAL READ", SYSTEM_CONSOLE_EXECUTE_OK,
        "generation=7 physical_device_id=11 instance=0 saved=1 pending=0");
    Test_Execute("MAG 0 CAL CLEAR", SYSTEM_CONSOLE_EXECUTE_OK,
        "action=CLEAR accepted=1");
    TEST_CHECK(SystemMagCalibration_PendingGet(
        &instance_id, packet, &request_id) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(packet[0] == 0U);
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U, request_id, 1U, 8U) ==
        SystemMagCalibrationResult_Ok);
    Test_Execute("MAG 0 CAL READ", SYSTEM_CONSOLE_EXECUTE_OK,
        "state=EMPTY generation=8");
    TestFixture_MagEnabledSet(0U);
}

int main(void)
{
    char response[64];

    Test_MultiInstanceFacade();

    s_locked = 0U;
    s_gnss_available = 1U;
    s_storage_health.initialized = 1U;
    s_storage_health.mounted = 1U;
    s_storage_health.healthy = 1U;
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    s_alignment_status.capability_mask = 0x07U;
    s_alignment_status.selected_mask = 0x07U;
    s_alignment_status.required_mask = 0x05U;
    s_alignment_status.ready_mask = 0x07U;
    s_alignment_status.config_result = SYSTEM_ALIGNMENT_CONFIG_OK;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.attitude_ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_valid = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.timestamp_us = 900000ULL;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.source =
        SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].ready =
        1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.origin_valid = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.sample_count = 100U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.origin_lat_e7 = 311234567;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.origin_lon_e7 = 1211234567;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.origin_height_mm = 12345;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].ready =
        1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.origin_valid = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.sample_count = 100U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.origin_pressure_pa = 100100.0f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.origin_altitude_m = 12.0f;
    (void)memset(&s_calibration_status, 0,
                 sizeof(s_calibration_status));
    (void)memset(&s_flight_recovery_status, 0,
                 sizeof(s_flight_recovery_status));
    s_console_write_result = SYSTEM_DEVICE_OK;
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_NONE;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_READY;
    s_calibration_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.last_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.ready = 1U;
    s_calibration_status.correction.mode = SYSTEM_CALIBRATION_MODE_NONE;
    s_calibration_status.correction.ready = 1U;
    s_calibration_status.correction.accel_scale[0] = 1.0f;
    s_calibration_status.correction.accel_scale[1] = 1.0f;
    s_calibration_status.correction.accel_scale[2] = 1.0f;
    s_calibration_status.correction.gyro_scale[0] = 1.0f;
    s_calibration_status.correction.gyro_scale[1] = 1.0f;
    s_calibration_status.correction.gyro_scale[2] = 1.0f;
    TEST_CHECK(SystemConsole_Init() == SYSTEM_DEVICE_OK);
    (void)memset(&s_startup_report, 0, sizeof(s_startup_report));
    s_startup_report.completed = 1U;
    s_startup_report.passed = 1U;
    s_startup_report.mission_capable = 1U;
    s_startup_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].device_name =
        "NEO-M9N GNSS";
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].model_name = "NEO-M9N";
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].present = 1U;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].apply_failed_mask =
        1U;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].failed_mask = 1U;
    s_startup_report.gnss_config.signal_complete_timestamp_us = UINT64_MAX;
    s_flight_recovery_status.deploy_trigger_mask =
        SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ;
    s_flight_recovery_status.landing_mode =
        SYSTEM_LANDING_MODE_BARO_IMU_WINDOW;
    s_flight_recovery_status.landing_state =
        SYSTEM_FLIGHT_LANDING_STATE_BARO_MONITOR;
    s_flight_recovery_status.barometer_valid = 1U;
    s_flight_recovery_status.barometer_age_ms = 12U;
    s_flight_recovery_status.barometer_trigger_rate_mps = -0.125f;
    s_flight_recovery_status.impact_capable = 0U;
    s_flight_recovery_status.impact_threshold_mps2 = 15.0f;
    Test_Execute("SYSTEM INFO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "project=SilverStar version=0.1.0");
    Test_Execute("SYSTEM STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK SYSTEM STATUS");
    Test_Execute("SYSTEM STACK", SYSTEM_CONSOLE_EXECUTE_OK,
                 "unit=words");
    Test_Execute("SYSTEM STACK", SYSTEM_CONSOLE_EXECUTE_OK,
                 "DeviceTask=64/256");
    Test_Execute("SYSTEM STACK", SYSTEM_CONSOLE_EXECUTE_OK,
                 "RadioTask=70/262");
    Test_Execute("SYSTEM FLIGHT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "deploy_mask=0x02 matched_mask=0x00");
    Test_Execute("SYSTEM FLIGHT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "landing_mode=BARO_IMU_WINDOW landing_state=BARO_MONITOR baro_valid=1 baro_age_ms=12");
    Test_Execute("SYSTEM FLIGHT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "impact_capable=0 impact_armed=0 impact_threshold_mps2=15.00");
    Test_Execute("SYSTEM READY", SYSTEM_CONSOLE_EXECUTE_OK,
                 "attitude_ready=1 attitude_reason=READY");
    Test_Execute("SYSTEM READY", SYSTEM_CONSOLE_EXECUTE_OK,
                 "alignment_ready=1 imu_alignment_ready=1 attitude_alignment_ready=1 gnss_alignment_ready=1 baro_alignment_ready=1");
    Test_Execute("SYSTEM READY", SYSTEM_CONSOLE_EXECUTE_OK,
                 "calibration_ready=1 calibration_mode=NONE capability_required_for_air_start=1");
    Test_Execute("CAL STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mode=NONE state=READY ready=1 current_face=NONE last_face=NONE last_face_result=NONE completed_face_mask=0x00 samples=0");
    Test_Execute("CAL DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "accel_bias=[0.000000,0.000000,0.000000] accel_scale=[1.000000,1.000000,1.000000]");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=READY ready=1 config=OK capability_mask=0x00000007 selected_mask=0x00000007 required_mask=0x00000005 ready_mask=0x00000007");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "attitude=READY gnss=READY baro=READY");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ALIGN SOURCE name=attitude state=READY");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "source=HARDWARE_QUATERNION quaternion_valid=1 timestamp_us=900000");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ALIGN SOURCE name=gnss state=READY");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "origin_valid=1 lat=311234567 lon=1211234567 height=12345 samples=100");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ALIGN SOURCE name=baro state=READY");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "origin_valid=1 samples=100 pressure_pa=100100.000 altitude_m=12.000");
    s_alignment_status.selected_mask =
        SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
        SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN |
        SYSTEM_ALIGNMENT_SOURCE_MASK_MAGNETIC;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_MAGNETIC].state =
        SYSTEM_ALIGNMENT_COMPONENT_READY;
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mag=READY");
    Test_ExecuteAbsent("ALIGN STATUS", " gnss=");
    s_alignment_status.selected_mask = 0x07U;
    Test_Execute("ALIGN RESET", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=IDLE");
    Test_Execute("CAL STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mode=NONE state=READY ready=1");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=IDLE ready=0 config=OK");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "attitude=NOT_READY gnss=NOT_READY baro=NOT_READY");
    Test_Execute("ALIGN START", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=COLLECTING");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=COLLECTING ready=0 config=OK");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "attitude=COLLECTING gnss=NOT_READY baro=COLLECTING");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ALIGN SOURCE name=attitude state=COLLECTING");
    Test_Execute("ALIGN STOP", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=IDLE");
    Test_Execute("CAL RESET", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mode=NOT_SELECTED state=IDLE ready=0");
    Test_Execute("ALIGN START", SYSTEM_CONSOLE_EXECUTE_FAILED,
                 "reason=CALIBRATION_REQUIRED");
    Test_Execute("CAL START NONE", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mode=NONE state=READY ready=1");
    Test_Execute("ALIGN START", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=COLLECTING");
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_FAILED;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].state =
        SYSTEM_ALIGNMENT_COMPONENT_FAILED;
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=FAILED ready=0 config=OK");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "attitude=FAILED");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ALIGN SOURCE name=attitude state=FAILED");
    Test_NavigationDiagnostics();
    Test_Execute("SYSTEM STARTUP", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mission_capable=1");
    Test_Execute("SYSTEM STARTUP GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "name=NEO-M9N GNSS");
    Test_Execute("SYSTEM STARTUP GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "signal_complete_us=4294967295");
    Test_Execute("SYSTEM STARTUP GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "apply_failed_mask=0x00000001 persist_failed_mask=0x00000000 verify_failed_mask=0x00000000");
    Test_Execute("SYSTEM STARTUP GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "verify_received_id=0x00 verify_response_version=0");
    Test_Execute("GNSS 0 CONFIG SHOW", SYSTEM_CONSOLE_EXECUTE_OK,
                 "source=CACHE");
    Test_Execute("IMU STATUS", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=INSTANCE_REQUIRED");
    Test_Execute("IMU X STATUS", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_INSTANCE reason=FORMAT");
    Test_Execute("IMU -1 STATUS", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_INSTANCE reason=FORMAT");
    Test_Execute("IMU 256 STATUS", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_INSTANCE reason=RANGE");
    Test_Execute("IMU 1 STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK IMU 1 STATUS");
    Test_Execute("IMU 2 STATUS", SYSTEM_CONSOLE_EXECUTE_FAILED,
                 "ERR IMU 2 STATUS code=NOT_PRESENT reason=INSTANCE");
    Test_Execute("IMU LIST", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK IMU LIST count=2 DATA instance=0 descriptor_id=1 physical_device_id=1 shared=1");
    Test_Execute("IMU LIST", SYSTEM_CONSOLE_EXECUTE_OK,
                 "DATA instance=1 descriptor_id=14 physical_device_id=9 shared=0 device=MOCK_IMU_B model=HOST_IMU_B");
    Test_Execute("BARO LIST", SYSTEM_CONSOLE_EXECUTE_OK,
                 "physical_device_id=1 shared=1");
    Test_Execute("ATTITUDE LIST", SYSTEM_CONSOLE_EXECUTE_OK,
                 "descriptor_id=4 physical_device_id=1 shared=1");
    Test_Execute("GNSS 0 INFO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK GNSS 0 INFO device=MOCK_GNSS");
    Test_Execute("GNSS 0 STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "initialized=1 started=1 online=1 healthy=1");
    Test_Execute("IMU 0 STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK IMU 0 STATUS");
    Test_Execute("ATTITUDE 0 STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK ATTITUDE 0 STATUS");
    Test_Execute("POWER 0 STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK POWER 0 STATUS");
    Test_Execute("GNSS 1 SAMPLE", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK GNSS 1 SAMPLE");
    Test_Execute("GNSS LIST", SYSTEM_CONSOLE_EXECUTE_OK,
                 "DATA instance=1 descriptor_id=15 physical_device_id=10 shared=0 device=MOCK_GNSS_B model=HOST_GNSS_B");
    Test_Execute("GNSS 2 SAMPLE", SYSTEM_CONSOLE_EXECUTE_FAILED,
                 "ERR GNSS 2 SAMPLE code=NOT_PRESENT reason=INSTANCE");
    Test_Execute("GNSS 0 CAPABILITIES", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mask=0x00001234");
    Test_Execute("GNSS 0 CONFIG READ", SYSTEM_CONSOLE_EXECUTE_OK,
                 "source=HARDWARE read_result=OK valid_mask=0x00000041");
    Test_Execute("GNSS 0 CONFIG READ", SYSTEM_CONSOLE_EXECUTE_OK,
                 "response_result=RESPONSE_OK failed_group=NONE");
    Test_Execute("GNSS 0 CONFIG READ", SYSTEM_CONSOLE_EXECUTE_OK,
                 "transaction_id=9 detailed_result=RESPONSE_OK");
    Test_Execute("GNSS 0 CONFIG READ", SYSTEM_CONSOLE_EXECUTE_OK,
                 "response_version=1 unsupported_mask=0x00000000");
    Test_Execute("GNSS 0 CONFIG VERIFY", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "DEVICE_OPERATION");
    Test_Execute("GNSS 0 NAV SAT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "satellite_count=10 used_count=7");
    Test_Execute("GNSS 0 NAV SAT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "transaction_id=10 response_result=RESPONSE_OK detailed_result=RESPONSE_OK");
    Test_Execute("GNSS 0 NAV SAT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "expected_class=0x01 expected_id=0x35 received_class=0x01 received_id=0x35");
    Test_Execute("GNSS 0 MON RF", SYSTEM_CONSOLE_EXECUTE_OK,
                 "jamming_indicator=6 noise_per_ms=11 agc_count=222");
    Test_Execute("GNSS 0 MON RF", SYSTEM_CONSOLE_EXECUTE_OK,
                 "jamming_state=2 cw_suppression=6");
    Test_Execute("SYSTEM START", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=PENDING request_id=1");
    Test_Execute("SYSTEM START RESULT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=COMPLETE request_id=1 result=OK reason=NONE");
    Test_Execute("SYSTEM START RESULT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "timestamp_us=1000000");
    Test_Execute("  SYSTEM\tINFO  ", SYSTEM_CONSOLE_EXECUTE_OK,
                 "project=SilverStar");
    Test_Execute("TIME STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK TIME STATUS monotonic_us=1000000");
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "transport=UART owner=GNSS owner_instance=0 physical_device_id=2");
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "ubx_frames=8");
    Test_Execute("IMU 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "valid_frames=12 checksum_errors=1 parser_resyncs=3");
    Test_Execute("BARO 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "transport=UART owner=IMU owner_instance=0 physical_device_id=1");
    Test_Execute("TELEMETRY 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK TELEMETRY 0 IO");
    Test_Execute("SYSTEM CONSOLE IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK SYSTEM CONSOLE IO");
    Test_Execute("LOG INFO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "device=MOCK_LOG_STORAGE model=GENERIC_STORAGE");
    Test_Execute("LOG STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK LOG STATUS initialized=1 mounted=1");
    Test_Execute("IMU 0 HEALTH", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND,
                 "code=BAD_COMMAND reason=UNKNOWN");
    Test_Execute("GNSS 0 HEALTH", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND,
                 "code=BAD_COMMAND reason=UNKNOWN");
    Test_Execute("SYSTEM HEALTH", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND,
                 "code=BAD_COMMAND reason=UNKNOWN");
    Test_Execute("POWER 0 HEALTH", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND,
                 "code=BAD_COMMAND reason=UNKNOWN");
    Test_Execute("LOG HEALTH", SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND,
                 "code=BAD_COMMAND reason=UNKNOWN");
    Test_Execute("TF STATUS", SYSTEM_CONSOLE_EXECUTE_BAD_MODULE,
                 "code=BAD_MODULE reason=UNKNOWN");
    Test_Execute("LOG IO", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "code=UNSUPPORTED");
    Test_Execute("GNSS 0 STATUS DETAIL", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("GNSS 0 STATUS EXTRA", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM INFO EXTRA", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM CAPABILITIES EXTRA",
                 SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM STATUS EXTRA", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM STACK EXTRA", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM PROFILE EXTRA", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM READY EXTRA", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM START RESULT EXTRA",
                 SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("SYSTEM CONSOLE IO CLEAR EXTRA",
                 SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "code=BAD_FORMAT reason=TOKEN_COUNT");
    Test_Execute("BAD STATUS", SYSTEM_CONSOLE_EXECUTE_BAD_MODULE,
                 "code=BAD_MODULE");
    Test_Execute("IMU 0 CONFIG", SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
                 "SUBCOMMAND_REQUIRED");
    Test_Execute("IMU 0 CONFIG VERIFY", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "DEVICE_OPERATION");
    Test_Execute("IMU 0 CONFIG APPLY", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "DEVICE_OPERATION");
    Test_Execute("IMU 0 CONFIG READ", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "HARDWARE_READ");
    Test_Execute("IMU 0 SELFTEST", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "OWNER_TASK_OPERATION");
    Test_Execute("IMU 0 PARAM GET", SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
                 "NO_PUBLIC_PARAMETER");
    Test_IoClear();
    Test_SensorDiagnostics();
    Test_ConsoleDiscontinuityClearsPartialLine();
    Test_AsyncCalibrationAlignmentEvents();
    Test_AsyncFlightRecoveryEvents();
    Test_MagStream();
    Test_MagCalibrationObject();

    s_state = SYSTEM_STATE_FAULT;
    Test_Execute("CAL START NONE", SYSTEM_CONSOLE_EXECUTE_FAILED,
                 "code=BAD_STATE reason=FAULT");
    Test_Execute("ALIGN START", SYSTEM_CONSOLE_EXECUTE_FAILED,
                 "code=BAD_STATE reason=FAULT");
    s_state = SYSTEM_STATE_PREFLIGHT;

    s_gnss_available = 0U;
    Test_Execute("GNSS 0 NAV SAT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "read_result=UNSUPPORTED");
    s_gnss_available = 1U;

    s_locked = 1U;
    s_state = SYSTEM_STATE_FLIGHT;
    Test_Execute("IMU 0 INFO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK IMU 0 INFO");
    Test_Execute("GNSS 0 CONFIG SHOW", SYSTEM_CONSOLE_EXECUTE_OK,
                 "source=CACHE");
    Test_Execute("IMU 0 CONFIG APPLY", SYSTEM_CONSOLE_EXECUTE_LOCKED,
                 "code=LOCKED");
    Test_Execute("SYSTEM STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "state=4");
    Test_Execute("TIME STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "mission_started=0");
    Test_Execute("GNSS 0 NAV SAT", SYSTEM_CONSOLE_EXECUTE_OK,
                 "read_result=OK");
    Test_Execute("GNSS 0 MON RF", SYSTEM_CONSOLE_EXECUTE_OK,
                 "read_result=OK");
    Test_Execute("GNSS 0 IO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "transport=UART");
    Test_Execute("ESTIMATOR STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK ESTIMATOR STATUS");
    Test_Execute("ESTIMATOR GNSS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK ESTIMATOR GNSS");
    Test_Execute("ESTIMATOR BARO", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK ESTIMATOR BARO");
    Test_Execute("KF STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK KF STATUS");
    Test_Execute("INS STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK INS STATUS");
    Test_Execute("ALIGN STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK ALIGN STATUS");
    Test_Execute("ALIGN DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK ALIGN DETAIL");
    Test_Execute("CAL STATUS", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK CAL STATUS");
    Test_Execute("CAL DETAIL", SYSTEM_CONSOLE_EXECUTE_OK,
                 "OK CAL DETAIL");
    Test_Execute("CAL START NONE", SYSTEM_CONSOLE_EXECUTE_LOCKED,
                 "code=LOCKED");
    Test_Execute("CAL RESET", SYSTEM_CONSOLE_EXECUTE_LOCKED,
                 "code=LOCKED");
    Test_Execute("ALIGN START", SYSTEM_CONSOLE_EXECUTE_LOCKED,
                 "code=LOCKED");
    Test_Execute("ALIGN STOP", SYSTEM_CONSOLE_EXECUTE_LOCKED,
                 "code=LOCKED");
    Test_Execute("ALIGN RESET", SYSTEM_CONSOLE_EXECUTE_LOCKED,
                 "code=LOCKED");

    TEST_CHECK(SystemConsole_ExecuteLine(NULL, response,
                                         sizeof(response)) ==
               SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    TEST_CHECK(SystemConsole_ExecuteLine("SYSTEM STATUS", NULL,
                                         sizeof(response)) ==
               SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT);
    return Test_Finish("console");
}
