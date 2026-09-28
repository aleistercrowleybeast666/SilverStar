#include "app_tasks.h"

#include <stddef.h>
#include <string.h>

#include "FreeRTOS.h"
#include "task.h"
#include "estimator_bus.h"
#include "imu_sample_bus.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "diagnostic_log.h"
#include "device_native_log.h"
#include "logger_bus.h"
#endif
#include "silverstar_assert.h"
#include "system_barometer_if.h"
#include "system_gnss_if.h"
#include "system_health.h"
#include "system_imu_if.h"
#include "system_lifecycle.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "system_log_policy.h"
#endif
#include "system_startup.h"
#include "system_time.h"

static void DeviceTask_PublishBarometer(void)
{
    static uint32_t last_sequence;
    SystemBarometerSample sample;
    SystemDeviceHealth health;
    EstimatorPressureSnapshot snapshot;

    if ((SystemBarometer_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK) ||
        (sample.sequence == last_sequence))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(&sample, SystemBarometerSample,
                             SILVERSTAR_ASSERT_MODULE_APP);
    last_sequence = sample.sequence;
    snapshot.timestamp_us = sample.sample_timestamp_us;
    snapshot.receive_timestamp_us = sample.receive_timestamp_us;
    snapshot.measurement_timestamp_trusted = sample.measurement_timestamp_trusted;
    snapshot.sequence = sample.sequence;
    snapshot.pressure_raw_pa = sample.pressure_raw_pa;
    snapshot.height_raw_cm = sample.altitude_raw_cm;
    snapshot.pressure_pa = sample.pressure_pa;
    snapshot.altitude_m = sample.altitude_m;
    snapshot.variance_m2 = sample.altitude_variance_m2;
    snapshot.supported_fields = sample.supported_fields;
    snapshot.valid_fields = sample.valid_fields;
    (void)memset(&health, 0, sizeof(health));
    snapshot.healthy = (uint8_t)(
        (SystemBarometer_HealthGet(&health) == SYSTEM_DEVICE_OK) &&
        (health.online != 0U) && (health.healthy != 0U));
    snapshot.valid = (uint8_t)((sample.valid_fields &
        (SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE)) != 0U);
    (void)EstimatorBus_PressurePublish(&snapshot);
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void DeviceTask_LogGnssState(void)
{
    static uint32_t last_sequence;
    static uint8_t state_known;
    static uint8_t last_usable;
    SystemGnssSample sample;
    uint8_t usable;

    if ((SystemGnss_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK) ||
        (sample.sequence == last_sequence))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(&sample, SystemGnssSample,
                             SILVERSTAR_ASSERT_MODULE_APP);
    last_sequence = sample.sequence;
    usable = (uint8_t)(sample.position_usable != 0U);
    if ((state_known == 0U) || (usable != last_usable))
    {
        (void)LoggerBus_EventPush(
            SystemTime_GetMonotonicUs(),
            (usable != 0U) ? FLIGHT_LOG_EVENT_GNSS_FIX_ACQUIRED :
                             FLIGHT_LOG_EVENT_GNSS_FIX_LOST,
            sample.position_reject_mask,
            sample.velocity_reject_mask);
        state_known = 1U;
        last_usable = usable;
    }
}

static void DeviceTask_LogGnssSatelliteDiagnostic(void)
{
    static uint32_t last_satellite_sequence;
    SystemGnssSatelliteDiagnostics satellite;
    SystemDeviceResult satellite_result;
    uint32_t arg0;
    uint32_t arg1;

    (void)memset(&satellite, 0, sizeof(satellite));
    satellite_result =
        SystemGnss_LatestSatelliteDiagnosticsGet(&satellite);
    SILVERSTAR_ASSERT_OBJECT(&satellite, SystemGnssSatelliteDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_APP);
    if (((satellite_result == SYSTEM_DEVICE_OK) ||
         (satellite_result == SYSTEM_DEVICE_NOT_READY)) &&
        (satellite.sequence != last_satellite_sequence))
    {
        last_satellite_sequence = satellite.sequence;
        if (satellite_result == SYSTEM_DEVICE_OK)
        {
            arg0 = (uint32_t)satellite.satellite_count |
                ((uint32_t)satellite.used_count << 8U) |
                ((uint32_t)satellite.average_cno_dbhz << 16U) |
                ((uint32_t)satellite.maximum_cno_dbhz << 24U);
            arg1 = (uint32_t)satellite.average_quality |
                (satellite.valid_fields << 8U);
            (void)LoggerBus_EventPush(satellite.sample_timestamp_us,
                FLIGHT_LOG_EVENT_GNSS_NAV_SAT_DIAGNOSTIC, arg0, arg1);
        }
        arg0 = satellite.sequence;
        arg1 = (uint32_t)satellite.response_length |
            ((uint32_t)satellite.read_result << 16U) |
            ((uint32_t)satellite.detailed_result << 20U);
        (void)LoggerBus_EventPush(satellite.sample_timestamp_us,
            FLIGHT_LOG_EVENT_GNSS_NAV_SAT_TRANSACTION_DETAIL, arg0, arg1);
    }
}

static void DeviceTask_LogGnssRfDiagnostic(void)
{
    static uint32_t last_rf_sequence;
    SystemGnssRfDiagnostics rf;
    SystemDeviceResult rf_result;
    uint32_t arg0;
    uint32_t arg1;

    (void)memset(&rf, 0, sizeof(rf));
    rf_result = SystemGnss_LatestRfDiagnosticsGet(&rf);
    SILVERSTAR_ASSERT_OBJECT(&rf, SystemGnssRfDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_APP);
    if (((rf_result == SYSTEM_DEVICE_OK) ||
         (rf_result == SYSTEM_DEVICE_NOT_READY)) &&
        (rf.sequence != last_rf_sequence))
    {
        last_rf_sequence = rf.sequence;
        if (rf_result == SYSTEM_DEVICE_OK)
        {
            arg0 = (uint32_t)rf.antenna_status |
                ((uint32_t)rf.antenna_power << 8U) |
                ((uint32_t)rf.jamming_indicator << 16U) |
                ((uint32_t)rf.rf_block_count << 24U);
            arg1 = (uint32_t)rf.noise_per_ms |
                ((uint32_t)rf.agc_count << 16U);
            (void)LoggerBus_EventPush(rf.sample_timestamp_us,
                FLIGHT_LOG_EVENT_GNSS_MON_RF_DIAGNOSTIC, arg0, arg1);
        }
        arg0 = rf.sequence;
        arg1 = (uint32_t)rf.response_length |
            ((uint32_t)rf.read_result << 16U) |
            ((uint32_t)rf.detailed_result << 20U) |
            ((uint32_t)(rf.jamming_state & 0x03U) << 24U);
        (void)LoggerBus_EventPush(rf.sample_timestamp_us,
            FLIGHT_LOG_EVENT_GNSS_MON_RF_TRANSACTION_DETAIL, arg0, arg1);
    }
}

static void DeviceTask_LogGnssDiagnostics(void)
{
    DeviceTask_LogGnssSatelliteDiagnostic();
    DeviceTask_LogGnssRfDiagnostic();
}

static void DeviceTask_LogHealthPeriodic(
    uint64_t now_us,
    const SystemLogStreamConfig *config)
{
    static uint64_t last_health_log_us;
    SystemHealthSnapshot health;
    FlightLogHealthRecord health_record;

    SILVERSTAR_ASSERT_OBJECT(config, SystemLogStreamConfig,
                             SILVERSTAR_ASSERT_MODULE_APP);
    if ((config->enabled != 0U) &&
        ((now_us - last_health_log_us) >= config->period_us))
    {
        SystemHealth_GetSnapshot(&health);
        health_record.timestamp_us = health.timestamp_us;
        health_record.compiled_mask = health.capabilities.compiled_mask;
        health_record.enabled_mask = health.capabilities.enabled_mask;
        health_record.present_mask = health.capabilities.present_mask;
        health_record.healthy_mask = health.capabilities.healthy_mask;
        health_record.start_blocking_mask = health.start_blocking_mask;
        health_record.warning_mask = health.warning_mask;
        health_record.sequence = health.sequence;
        health_record.ready = health.ready;
        (void)LoggerBus_HealthPush(now_us, &health_record);
        last_health_log_us = now_us;
    }
}

static void DeviceTask_LogPeriodic(void)
{
    static DiagnosticLogPeriodicState stats_log_state;
    SystemLogStreamConfig power_config;
    SystemLogStreamConfig health_config;
    SystemLifecycleState state = SystemLifecycle_GetState();
    uint64_t now_us;

    SILVERSTAR_ASSERT(state <= SYSTEM_STATE_FAULT,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if ((state != SYSTEM_STATE_FLIGHT) && (state != SYSTEM_STATE_RECOVERY))
    { return; }
    if ((SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_POWER,
                                   &power_config) != SYSTEM_DEVICE_OK) ||
        (SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_HEALTH,
                                   &health_config) != SYSTEM_DEVICE_OK))
    { return; }
    SILVERSTAR_ASSERT((power_config.enabled <= 1U) &&
                      (health_config.enabled <= 1U),
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    now_us = SystemTime_GetMonotonicUs();
    DeviceNativeLog_PowerProcess(now_us, &power_config);
    DeviceTask_LogHealthPeriodic(now_us, &health_config);
    DiagnosticLog_StatsProcess(&stats_log_state, now_us);
}
#endif

void AppTask_Device(void *argument)
{
    (void)argument;
    (void)SystemImu_RuntimeOwnerActivate();
    (void)SystemGnss_RuntimeOwnerActivate();

    for (;;)
    {
        SystemStartup_ProcessDevices();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        DeviceNativeLog_Process();
#endif
        ImuSampleBus_Process();
        DeviceTask_PublishBarometer();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        DeviceTask_LogGnssState();
        DeviceTask_LogGnssDiagnostics();
#endif
        SystemHealth_Process();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        DeviceTask_LogPeriodic();
#endif
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
}
