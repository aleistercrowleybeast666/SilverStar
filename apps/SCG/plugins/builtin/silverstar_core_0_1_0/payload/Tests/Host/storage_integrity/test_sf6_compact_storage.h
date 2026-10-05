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
#include <math.h>
static uint32_t s_sf6_start_generation;
static uint32_t s_sf6_start_acks;
static uint32_t s_sf6_predict_count;
static uint32_t s_sf6_baro_count;
static uint8_t s_sf6_started;
/* Backend mutates owner state just as EstimatorTask's static s_snapshot. */
static EstimatorOutputSnapshot s_sf6_output;

static void Fixture_Sf6CalibrationBuild(FlightLogCalibrationResultRecord *record)
{
    record->source_id = FLIGHT_LOG_PRIMARY_INERTIAL_SOURCE_ID;
    record->virtual_imu_id = FLIGHT_LOG_PRIMARY_VIRTUAL_IMU_ID;
    record->mode = SYSTEM_CALIBRATION_MODE_NONE;
    record->state = SYSTEM_CALIBRATION_STATE_READY;
    record->ready = 1U; record->start_sequence = SystemCalibration_GenerationGet();
    for (unsigned axis = 0U; axis < 3U; axis++)
    { record->accel_scale[axis] = 1.0f; record->gyro_scale[axis] = 1.0f; }
}

/* Self-consistent synthetic stationary alignment, not a hardware result. */
static void Fixture_Sf6AlignmentBuild(FlightLogRecord *record, uint64_t now)
{
    FlightLogAlignmentResultRecord *result = &record->payload.alignment_result;
    result->capability_mask = SYSTEM_USER_ALIGNMENT_SELECTED_MASK;
    result->selected_mask = SYSTEM_USER_ALIGNMENT_SELECTED_MASK;
    result->required_mask = SYSTEM_USER_ALIGNMENT_REQUIRED_MASK;
    result->ready_mask = result->selected_mask;
    result->start_sequence = 1U;
    result->state = SYSTEM_ALIGNMENT_STATE_READY;
    result->config_result = SYSTEM_ALIGNMENT_CONFIG_OK;
    result->ready = 1U; result->source_count = 2U;
    result->attitude_timestamp_us = now; result->q_nb[0] = 1.0f;
    result->barometer_sample_count = 100U;
    result->barometer_origin_pressure_pa = 101325.0f;
    result->attitude_state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    result->gnss_state = SYSTEM_ALIGNMENT_COMPONENT_DISABLED;
    result->barometer_state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    result->attitude_source = SYSTEM_ALIGNMENT_BUILD_SOURCE;
}

static void Fixture_Sf6EvidenceBuild(FlightLogAlignmentEvidenceRecord *record, uint64_t now)
{
    record->alignment_algorithm = SYSTEM_ALIGNMENT_ALGORITHM;
    record->constraint_count = SYSTEM_ALIGNMENT_CONSTRAINT_COUNT;
    record->valid_pair_count = 1U;
    record->yaw_authoritative = SYSTEM_ALIGNMENT_EXTERNAL_YAW_AUTHORITATIVE;
    record->imu_source_instance = 0U;
    record->magnetometer_instance = 0xFFU; record->external_source_instance = 0xFFU;
    record->flags = 1U | 8U;
    record->first_timestamp_us = now - 4995000ULL; record->last_timestamp_us = now;
    record->minimum_pair_sine = 1.0f;
}

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
    records.identity.snapshot_sequence = status.snapshot_sequence;
    records.identity.imu_calibration_generation = status.snapshot_calibration_generation;
    records.identity.mag_calibration_set_hash = status.snapshot_mag_calibration_set_hash;
    records.identity.base_instance = status.snapshot_base_instance;
    records.initial.alignment_algorithm = SYSTEM_ALIGNMENT_ALGORITHM;
    records.initial.origin_valid_flags = 2U;
    records.initial.alignment_sample_count = 1000U;
    records.initial.barometer_sample_count = 100U;
    records.initial.q_nb[0] = 1.0f;
    records.initial.acceleration_mean_b_mps2[2] = SYSTEM_INS_GRAVITY_MPS2;
    const SystemEstimatorProfile *profile = SystemEstimatorProfile_Get();
    if (profile == NULL) { abort(); }
    records.initial.barometer_origin_std_m = profile->barometer_altitude_std_m;
    memcpy(records.initial.p0_diagonal, profile->p0_diagonal, sizeof(profile->p0_diagonal));
    for (unsigned axis = 0U; axis < 3U; axis++)
    { records.initial.initial_velocity_std_mps[axis] = sqrtf(profile->p0_diagonal[axis + 3U]); }
    result = LoggerBus_StartRecordsPush(now, &records, &s_sf6_start_generation);
    if (result != LOGGER_BUS_RESULT_OK && result != LOGGER_BUS_RESULT_BUSY) { abort(); }
    if (!s_sf6_start_generation || LoggerBus_StartAcknowledgedGet() != s_sf6_start_generation) { return; }
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    SystemGnssSample origin = {0};
    if (SystemNavigationBackend_Initialize(q, &origin, 0.0f, 1U, 1U, 1U) != SYSTEM_DEVICE_OK) { abort(); }
    memset(&s_sf6_output, 0, sizeof(s_sf6_output));
    s_sf6_started = 1U; s_sf6_start_acks++; s_lifecycle = SYSTEM_STATE_FLIGHT;
}

static void Fixture_Sf6CompactFrame(uint32_t frame, uint64_t now)
{
    InsImuSample consumed;
    FlightLogRecord record = {0};
    SystemInertialIncrement increment = {0};
    EstimatorOutputSnapshot *output = &s_sf6_output;
    if (frame == 0U && (ImuSampleBus_Init() != IMU_SAMPLE_BUS_RESULT_OK ||
        EstimatorBus_Init() != ESTIMATOR_BUS_RESULT_OK)) { abort(); }
    s_device_steps++; s_flight_steps++;
    if (frame == 1U)
    {
        Fixture_Sf6CalibrationBuild(&record.payload.calibration_result);
        Fixture_ResultCheck(LoggerBus_CalibrationResultPush(now, &record.payload.calibration_result));
    }
    if (frame == 1000U)
    {
        Fixture_Sf6AlignmentBuild(&record, now);
        Fixture_ResultCheck(LoggerBus_AlignmentResultPush(now, &record.payload.alignment_result));
        memset(&record, 0, sizeof(record));
        Fixture_Sf6EvidenceBuild(&record.payload.alignment_evidence, now);
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
            s_sf6_baro_count++;
        }
    }
    if (!s_sf6_started) { return; }
    increment.sequence = consumed.sequence; increment.timestamp_us = now; increment.dt_s = 0.005f;
    increment.delta_velocity_b_sculling_corrected[2] = SYSTEM_INS_GRAVITY_MPS2 * increment.dt_s;
    record.payload.inertial_increment.sequence = increment.sequence;
    record.payload.inertial_increment.dt_s = increment.dt_s;
    record.payload.inertial_increment.interval_start_timestamp_us = now - 5000ULL;
    record.payload.inertial_increment.interval_end_timestamp_us = now;
    memcpy(record.payload.inertial_increment.delta_theta_b_corrected,
        increment.delta_theta_b_corrected, sizeof(increment.delta_theta_b_corrected));
    memcpy(record.payload.inertial_increment.delta_velocity_b_sculling_corrected,
        increment.delta_velocity_b_sculling_corrected, sizeof(increment.delta_velocity_b_sculling_corrected));
    Fixture_ResultCheck(LoggerBus_InertialIncrementPush(now, 3U, &record.payload.inertial_increment));
    if (SystemNavigationBackend_Predict(&increment, output) != SYSTEM_DEVICE_OK) { abort(); }
    if (!s_overflow_test && (output->health_flags & ESTIMATOR_HEALTH_LOG_EVENT_FAILED)) { abort(); }
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
