/* Explicit compact-profile fixture. Original all-stream DefaultFrame stress
 * remains unchanged. Sensor/time/SD scheduling are Host models; ImuSampleBus,
 * DeviceNativeLog, SF6 core/backend, LoggerBus/Task and FatFs are actual code. */
#ifndef __TEST_SF6_COMPACT_STORAGE_H
#define __TEST_SF6_COMPACT_STORAGE_H
#include "system_navigation_backend.h"
#include "system_barometer_if.h"
#include "system_estimator_profile.h"
#include "estimator_bus.h"
#include "platform_time.h"
static uint32_t s_sf6_start_generation;
static uint32_t s_sf6_start_acks;
static uint32_t s_sf6_predict_count;
static uint32_t s_sf6_baro_count;
static uint8_t s_sf6_started;

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ (void)sample; return SYSTEM_DEVICE_NOT_READY; }
PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }

static void Fixture_Sf6StartTry(uint64_t now)
{
    LoggerBusStartRecords records = {0};
    LoggerTaskDiagnostics status;
    LoggerBusResult result;
    if (LoggerTask_DiagnosticsGet(&status) != SYSTEM_DEVICE_OK || !status.snapshot_ready) { abort(); }
    records.identity.ready = status.snapshot_ready;
    records.identity.mission_id = status.snapshot_mission_id;
    records.identity.commit_generation = status.snapshot_commit_generation;
    records.initial.q_nb[0] = 1.0f;
    result = LoggerBus_StartRecordsPush(now, &records, &s_sf6_start_generation);
    if (result != LOGGER_BUS_RESULT_OK && result != LOGGER_BUS_RESULT_BUSY) { abort(); }
    if (!s_sf6_start_generation || LoggerBus_StartAcknowledgedGet() != s_sf6_start_generation) { return; }
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    SystemGnssSample origin = {0};
    if (SystemNavigationBackend_Initialize(q, &origin, 0.0f, 1U, 1U, 1U) != SYSTEM_DEVICE_OK) { abort(); }
    s_sf6_started = 1U; s_sf6_start_acks++; s_lifecycle = SYSTEM_STATE_FLIGHT;
}

static void Fixture_Sf6CompactFrame(uint32_t frame, uint64_t now)
{
    InsImuSample consumed;
    FlightLogRecord record = {0};
    SystemInertialIncrement increment = {0};
    EstimatorOutputSnapshot output;
    if (frame == 0U && (ImuSampleBus_Init() != IMU_SAMPLE_BUS_RESULT_OK ||
        EstimatorBus_Init() != ESTIMATOR_BUS_RESULT_OK)) { abort(); }
    s_device_steps++; s_flight_steps++;
    if (frame == 1U) { Fixture_ResultCheck(LoggerBus_CalibrationResultPush(now, &record.payload.calibration_result)); }
    if (frame == 1000U)
    {
        Fixture_ResultCheck(LoggerBus_AlignmentResultPush(now, &record.payload.alignment_result));
        Fixture_ResultCheck(LoggerBus_AlignmentEvidencePush(now, &record.payload.alignment_evidence));
    }
    if (frame >= 1200U && !s_sf6_started) { Fixture_Sf6StartTry(now); }
    s_source_sample.sequence = frame + 1U;
    s_source_sample.sample_timestamp_us = now; s_source_sample.receive_timestamp_us = now;
    s_source_sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    s_source_sample.accel_b_mps2[2] = SYSTEM_INS_GRAVITY_MPS2;
    s_source_sample_pending = 1U;
    ImuSampleBus_Process();
    if (ImuSampleBus_Pop(&consumed) != IMU_SAMPLE_BUS_RESULT_OK || consumed.sequence != frame + 1U) { abort(); }
    if (frame % 10U == 0U)
    {
        s_barometer[0].sequence = frame / 10U + 1U;
        s_barometer[0].sample_timestamp_us = now; s_barometer[0].receive_timestamp_us = now;
        s_barometer[0].pressure_pa = 101325.0f; s_barometer[0].altitude_m = 0.0f;
        s_barometer[0].supported_fields = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
        s_barometer[0].valid_fields = SYSTEM_BARO_VALID_PRESSURE | SYSTEM_BARO_VALID_ALTITUDE;
        DeviceNativeLog_Process();
        if (s_sf6_started)
        {
            EstimatorPressureSnapshot pressure = {0};
            pressure.sequence = s_barometer[0].sequence; pressure.timestamp_us = now;
            pressure.receive_timestamp_us = now; pressure.pressure_pa = 101325.0f;
            pressure.valid = 1U; pressure.healthy = 1U; pressure.measurement_timestamp_trusted = 1U;
            pressure.supported_fields = s_barometer[0].supported_fields; pressure.valid_fields = s_barometer[0].valid_fields;
            if (EstimatorBus_PressurePublish(&pressure) != ESTIMATOR_BUS_RESULT_OK) { abort(); }
            record.payload.baro_measurement.sample_timestamp_us = now;
            Fixture_ResultCheck(LoggerBus_BaroMeasurementPush(now, pressure.valid_fields, &record.payload.baro_measurement));
            s_sf6_baro_count++;
        }
    }
    if (!s_sf6_started) { return; }
    increment.sequence = consumed.sequence; increment.timestamp_us = now; increment.dt_s = 0.005f;
    increment.delta_velocity_b_sculling_corrected[2] = SYSTEM_INS_GRAVITY_MPS2 * increment.dt_s;
    record.payload.inertial_increment.sequence = increment.sequence;
    record.payload.inertial_increment.dt_s = increment.dt_s;
    Fixture_ResultCheck(LoggerBus_InertialIncrementPush(now, 3U, &record.payload.inertial_increment));
    if (SystemNavigationBackend_Predict(&increment, &output) != SYSTEM_DEVICE_OK) { abort(); }
    if (!s_overflow_test && (output.health_flags & ESTIMATOR_HEALTH_LOG_EVENT_FAILED)) { abort(); }
    record.payload.estimator_step.source_sequence = increment.sequence;
    record.payload.estimator_step.interval_end_timestamp_us = now;
    Fixture_ResultCheck(LoggerBus_EstimatorStepPush(now, &record.payload.estimator_step));
    s_sf6_predict_count++;
    if (frame % 200U == 0U)
    {
        record.payload.stats.logger_queue_overflow_count = LoggerBus_OverflowCountGet();
        Fixture_ResultCheck(LoggerBus_StatsPush(now, &record.payload.stats));
        Fixture_ResultCheck(LoggerBus_HealthPush(now, &record.payload.health));
        Fixture_ResultCheck(LoggerBus_TelemetryDiagnosticPush(now, &record.payload.telemetry_diagnostic));
    }
}
#endif
