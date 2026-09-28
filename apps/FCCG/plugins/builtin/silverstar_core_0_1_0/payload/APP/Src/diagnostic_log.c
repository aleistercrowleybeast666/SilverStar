#include "diagnostic_log.h"

#include <stddef.h>
#include <string.h>

#include "imu_sample_bus.h"
#include "estimator_task.h"
#include "logger_bus.h"
#include "silverstar_assert.h"
#include "system_lifecycle.h"
#include "system_log_policy.h"
#include "system_telemetry_transport_if.h"

static uint8_t DiagnosticLog_MissionActive(void)
{
    SystemLifecycleState lifecycle_state = SystemLifecycle_GetState();

    SILVERSTAR_ASSERT(lifecycle_state <= SYSTEM_STATE_FAULT,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    return (uint8_t)((lifecycle_state == SYSTEM_STATE_FLIGHT) ||
                     (lifecycle_state == SYSTEM_STATE_RECOVERY));
}

static uint8_t DiagnosticLog_PeriodReached(
    const DiagnosticLogPeriodicState *state,
    uint64_t now_us,
    const SystemLogStreamConfig *config)
{
    if ((state == NULL) || (config == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(state, DiagnosticLogPeriodicState,
                             SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(config, SystemLogStreamConfig,
                             SILVERSTAR_ASSERT_MODULE_APP);
    return (uint8_t)((config->enabled != 0U) &&
                     (config->period_us != 0U) &&
                     ((now_us - state->last_emission_us) >=
                      config->period_us));
}

static void DiagnosticLog_StatsRecordBuild(FlightLogStatsRecord *record)
{
    ImuSampleBusStats imu_bus_stats;
    EstimatorOutputSnapshot navigation;

    if (record == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogStatsRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    ImuSampleBus_StatsGet(&imu_bus_stats);
    record->imu_queue_overflow_count = imu_bus_stats.overflow_count;
    record->logger_queue_overflow_count = LoggerBus_OverflowCountGet();
    if (Estimator_GetLatestSnapshot(&navigation) != 0U)
    {
        record->ins_update_count = navigation.update_sequence;
        record->health_flags = navigation.health_flags;
    }
}

static void DiagnosticLog_TelemetryRecordMap(
    FlightLogTelemetryDiagnosticRecord *record,
    const SystemTelemetryHealth *health)
{
    if ((record == NULL) || (health == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogTelemetryDiagnosticRecord,
                             SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(health, SystemTelemetryHealth,
                             SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->last_transmit_timestamp_us = health->last_transmit_timestamp_us;
    record->last_receive_timestamp_us = health->last_receive_timestamp_us;
    record->transmit_packet_count = health->transmit_packet_count;
    record->receive_packet_count = health->receive_packet_count;
    record->transmit_error_count = health->transmit_error_count;
    record->receive_error_count = health->receive_error_count;
    record->integrity_error_count = health->integrity_error_count;
    record->last_rssi_dbm = health->last_rssi_dbm;
    record->last_snr_q4 = health->last_snr_q4;
    record->online = health->online;
}

void DiagnosticLog_StatsProcess(DiagnosticLogPeriodicState *state,
                                uint64_t now_us)
{
    SystemLogStreamConfig config;
    FlightLogStatsRecord record;

    if ((state == NULL) || (DiagnosticLog_MissionActive() == 0U) ||
        (SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_STATS, &config) !=
            SYSTEM_DEVICE_OK) ||
        (DiagnosticLog_PeriodReached(state, now_us, &config) == 0U))
    {
        return;
    }
    DiagnosticLog_StatsRecordBuild(&record);
    if (LoggerBus_StatsPush(now_us, &record) == LOGGER_BUS_RESULT_OK)
    {
        state->last_emission_us = now_us;
    }
}

void DiagnosticLog_TelemetryProcess(DiagnosticLogPeriodicState *state,
                                    uint64_t now_us)
{
    SystemLogStreamConfig config;
    SystemTelemetryHealth health;
    FlightLogTelemetryDiagnosticRecord record;

    if (state == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(state, DiagnosticLogPeriodicState,
                             SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(now_us >= state->last_emission_us,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((DiagnosticLog_MissionActive() == 0U) ||
        (SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_TELEMETRY_DIAG,
                                   &config) != SYSTEM_DEVICE_OK) ||
        (DiagnosticLog_PeriodReached(state, now_us, &config) == 0U) ||
        (SystemTelemetry_HealthGet(&health) != SYSTEM_DEVICE_OK))
    {
        return;
    }
    DiagnosticLog_TelemetryRecordMap(&record, &health);
    if (LoggerBus_TelemetryDiagnosticPush(now_us, &record) ==
        LOGGER_BUS_RESULT_OK)
    {
        state->last_emission_us = now_us;
    }
}
