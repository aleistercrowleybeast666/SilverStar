/* Synthetic numerical acceptance only. Uses the generated project's real kernels
 * and codec. It is not evidence of target scheduling or field performance. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ins_mechanization.h"
#include "attitude_frame.h"
#include "navigation_kf_replay.h"
#include "navigation_integrity.h"
#include "system_user_config.h"
#include "project_log_decoder_profile.h"
#include "project_log_config.h"
#include "project_device_instances.h"
#include "sslog_protocol.h"

static FILE *s_file;
static uint32_t s_sequence, s_operation;
static uint8_t s_reanchor_scenario;
static uint8_t s_integrity_scenario;
static NavigationIntegrityContext s_integrity;
static NavigationKfContext s_kf;
static NavigationReplayContext s_replay;
static NavigationReplayStorage s_storage;
static float s_q[4] = {1.0f, 0.0f, 0.0f, 0.0f};

static void Golden_Write(const FlightLogRecord *record)
{
    uint8_t bytes[FLIGHT_LOG_MAX_RECORD_SIZE];
    uint16_t size;
    if (FlightLog_RecordSerialize(record, s_sequence++, bytes, sizeof(bytes), &size) !=
        FLIGHT_LOG_SERIALIZE_RESULT_OK || fwrite(bytes, 1, size, s_file) != size)
    { exit(3); }
}

static uint8_t Golden_StreamEnabled(FlightLogRecordType type)
{
    uint16_t index;
    for (index = 0U; index < SSLOG_RECORD_COUNT; index++)
    {
        const SystemLogStreamConfig *config =
            ProjectLogConfig_StreamByIndexGet(index);
        if (config == NULL) { exit(3); }
        if (config->record_type == type) { return config->enabled; }
    }
    exit(3);
}

static void Golden_Snapshot(uint64_t timestamp)
{
    FlightLogRecord record = {0};
    record.timestamp_us = timestamp;
    record.record_type = FLIGHT_LOG_RECORD_ESTIMATOR;
    memcpy(record.payload.estimator.q_nb, s_q, sizeof(s_q));
    record.payload.estimator.operation_sequence = s_operation;
    record.payload.estimator.replay_epoch = s_replay.epoch;
    memcpy(record.payload.estimator.position_enu_m, s_kf.state, 3 * sizeof(float));
    memcpy(record.payload.estimator.velocity_enu_mps, s_kf.state + 3, 3 * sizeof(float));
    record.payload.estimator.initialized = 1;
    record.payload.estimator.mission_running = 1;
    record.payload.estimator.gnss_origin_valid = 1;
    record.payload.estimator.baro_origin_valid = 1;
    for (unsigned row = 0; row < 6; row++)
    { record.payload.estimator.covariance_diagonal[row] = s_kf.covariance[row][row]; }
    Golden_Write(&record);
    if (Golden_StreamEnabled(FLIGHT_LOG_RECORD_KF6_FULL_P) != 0U)
    {
        unsigned item = 0U;
        record.record_type = FLIGHT_LOG_RECORD_KF6_FULL_P;
        for (unsigned row = 0U; row < 6U; row++)
        {
            for (unsigned col = row; col < 6U; col++)
            {
                record.payload.kf6_full_p.covariance_upper_triangle[item++] =
                    s_kf.covariance[row][col];
            }
        }
        if (item != 21U) { exit(3); }
        Golden_Write(&record);
    }
}

static void Golden_Bootstrap(void)
{
    FlightLogRecord record = {0};
    ProjectLogDecoderProfile profile;
    ProjectLogDecoderProfile_Get(&profile);
    record.record_type = FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR;
    FlightLogDecoderProfileDescriptorRecord *d = &record.payload.decoder_profile_descriptor;
    d->package_schema_major = profile.package_schema_major;
    d->package_schema_minor = profile.package_schema_minor;
    d->container_format_major = profile.container_format_major;
    d->container_format_minor = profile.container_format_minor;
    memcpy(d->record_catalog_hash_128, profile.record_catalog_hash_128, 16);
    memcpy(d->project_semantics_hash_128, profile.project_semantics_hash_128, 16);
    memcpy(d->generation_profile_hash_128, profile.generation_profile_hash_128, 16);
    Golden_Write(&record);
    memset(&record, 0, sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_SYSTEM_CONFIG;
    record.payload.system_config.version[2] = SILVERSTAR_VERSION_PATCH;
    record.payload.system_config.configured_imu_rate_hz = 200;
    record.payload.system_config.configured_gnss_rate_hz = 25;
    record.payload.system_config.mechanization_subsample_count = 2;
    record.payload.system_config.mechanization_min_sample_rate_hz = 50;
    record.payload.system_config.mechanization_max_sample_rate_hz = 500;
    Golden_Write(&record);
    memset(&record, 0, sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_CALIBRATION_RESULT;
    record.payload.calibration_result.ready = 1;
    record.payload.calibration_result.state = 4;
    for (unsigned axis = 0; axis < 3; axis++)
    {
        record.payload.calibration_result.accel_scale[axis] = 1.0f;
        record.payload.calibration_result.gyro_scale[axis] = 1.0f;
    }
    Golden_Write(&record);
    memset(&record, 0, sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_INITIAL_STATE;
    record.valid_flags = 1;
    record.payload.initial_state.q_nb[0] = 1.0f;
    record.payload.initial_state.origin_valid_flags = 3;
    for (unsigned axis = 0; axis < 6; axis++)
    { record.payload.initial_state.p0_diagonal[axis] = s_kf.covariance[axis][axis]; }
    Golden_Write(&record);
    memset(&record, 0, sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_EVENT;
    record.payload.event.event_id = FLIGHT_LOG_EVENT_MISSION_START;
    Golden_Write(&record);
}

static int Golden_IntegrityInit(void)
{
    const NavigationIntegrityConfig config = {
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_ENABLE,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_MAX_GAP_MS * 1000U,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_SUSPECT_DURATION_MS * 1000U,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_REJECT_DURATION_MS * 1000U,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_RECOVERY_DURATION_MS * 1000U,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_ERROR_THRESHOLD_M,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_RECOVERY_THRESHOLD_M,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_POSITION_R_SCALE,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_HACC_MAX_M,
        SYSTEM_ESTIMATOR_GNSS_INTEGRITY_SACC_MAX_MPS
    };
    return NavigationIntegrity_Reset(&s_integrity, &config) ==
        NAV_INTEGRITY_PROCESS_OK;
}

static int Golden_IntegrityApply(uint64_t now, uint32_t sequence,
    NavigationReplayEvent *event, FlightLogGnssMeasurementRecord *measurement)
{
    NavigationIntegrityInput input = {0};
    NavigationIntegrityDecision decision;
    NavigationIntegrityProcessResult result;
    input.timestamp_us = now;
    input.epoch = s_replay.epoch;
    input.sequence = sequence;
    input.source = 0U;
    input.valid_group_mask = event->valid_group_mask;
    input.position_en[0] = event->position[0];
    input.position_en[1] = event->position[1];
    input.velocity_en[0] = event->velocity[0];
    input.velocity_en[1] = event->velocity[1];
    input.hacc_m = 2.0f;
    input.sacc_mps = 0.24f;
    result = NavigationIntegrity_Receive(&s_integrity, &input, &decision);
    if (result != NAV_INTEGRITY_PROCESS_OK) { return 0; }
    event->integrity_admission_valid = 1U;
    event->integrity_admitted_group_mask = decision.admitted_group_mask;
    measurement->valid_group_mask = decision.admitted_group_mask;
    event->position_variance[0] *= decision.position_r_scale;
    event->position_variance[1] *= decision.position_r_scale;
    measurement->position_variance_m2[0] = event->position_variance[0];
    measurement->position_variance_m2[1] = event->position_variance[1];
    if (decision.state_changed != 0U)
    {
        FlightLogRecord transition = {0};
        transition.record_type = FLIGHT_LOG_RECORD_EVENT;
        transition.timestamp_us = now;
        transition.payload.event.event_id =
            FLIGHT_LOG_EVENT_GNSS_POSITION_INTEGRITY_STATE_CHANGE;
        transition.payload.event.arg0 = (uint32_t)decision.previous_state |
            ((uint32_t)decision.state << 8U) |
            ((uint32_t)decision.reason << 16U) |
            ((uint32_t)decision.chain_reset << 24U);
        transition.payload.event.arg1 = sequence;
        Golden_Write(&transition);
    }
    return 1;
}

static void Golden_RecoveryWrite(uint64_t now, uint32_t sequence,
    const NavigationKfGnssEpoch *epoch, const FlightLogGnssMeasurementRecord *m)
{
    FlightLogRecord recovery = {0};
    recovery.record_type = FLIGHT_LOG_RECORD_GNSS_RECOVERY; recovery.timestamp_us = now;
    recovery.payload.gnss_recovery.source_sequence = sequence;
    recovery.payload.gnss_recovery.estimator_present_timestamp_us = now;
    recovery.payload.gnss_recovery.replay_epoch = s_replay.epoch;
    recovery.payload.gnss_recovery.operation_sequence = s_operation;
    recovery.payload.gnss_recovery.replay_generation = s_replay.diagnostics.replay_count;
    for (unsigned g = 0; g < 4; g++)
    {
        const NavigationKfGnssReacquireGroupState *state = &s_kf.gnss_reacquisition.group[g];
        recovery.payload.gnss_recovery.reanchor_count[g] = s_kf.gnss_reacquisition.reanchor_count[g];
        recovery.payload.gnss_recovery.reanchor_reason[g] = (uint8_t)(s_kf.gnss_reacquisition.reanchor_count[g] != 0);
        recovery.payload.gnss_recovery.valid[g] = (uint8_t)((epoch->valid_group_mask >> g) & 1);
        recovery.payload.gnss_recovery.consistency_count[g] = state->consistent_count;
        recovery.payload.gnss_recovery.inflation_attempt_count[g] = state->inflation_attempt_count;
        recovery.payload.gnss_recovery.inflation_factor[g] = state->last_inflation_factor;
        recovery.payload.gnss_recovery.outage[g] = state->outage;
        recovery.payload.gnss_recovery.recovery_active[g] = state->active;
        recovery.payload.gnss_recovery.update_result[g] = m->group_update_result[g];
    }
    {
        static FlightLogGnssRecoveryRecord previous;
        static uint8_t previous_valid;
        uint8_t changed = (uint8_t)(previous_valid == 0U ||
            previous.replay_epoch != recovery.payload.gnss_recovery.replay_epoch);
        for (unsigned group = 0U; group < 4U; group++)
        {
            const FlightLogGnssRecoveryRecord *now_record =
                &recovery.payload.gnss_recovery;
            if (now_record->outage[group] != previous.outage[group] ||
                now_record->recovery_active[group] != previous.recovery_active[group] ||
                now_record->inflation_factor[group] != previous.inflation_factor[group] ||
                now_record->inflation_attempt_count[group] !=
                    previous.inflation_attempt_count[group] ||
                now_record->reanchor_count[group] != previous.reanchor_count[group])
            { changed = 1U; }
        }
        if (changed != 0U)
        {
            Golden_Write(&recovery);
            previous = recovery.payload.gnss_recovery;
            previous_valid = 1U;
        }
    }
}

static void Golden_GnssNativeWrite(uint64_t now, uint32_t sequence,
    const NavigationKfGnssEpoch *epoch)
{
    FlightLogRecord native = {0};
    native.record_type = FLIGHT_LOG_RECORD_GNSS_NATIVE; native.timestamp_us = now;
    native.payload.gnss_native.source_descriptor_id = PROJECT_DESCRIPTOR_ID_GNSS_0;
    native.payload.gnss_native.sample_timestamp_us = now;
    native.payload.gnss_native.receive_timestamp_us = now;
    native.payload.gnss_native.sequence = sequence;
    if (s_integrity_scenario != 0U)
    { native.payload.gnss_native.longitude_e7 = (int32_t)(18U * sequence); }
    native.payload.gnss_native.fix_type = 3; native.payload.gnss_native.fix_ok = 1;
    native.payload.gnss_native.satellite_count = 12; native.payload.gnss_native.online = 1;
    native.payload.gnss_native.valid_group_mask = epoch->valid_group_mask;
    native.payload.gnss_native.horizontal_accuracy_m = 2.0f;
    native.payload.gnss_native.vertical_accuracy_m = 2.0f;
    native.payload.gnss_native.speed_accuracy_mps = 0.24f;
    native.payload.gnss_native.supported_fields = 7; native.payload.gnss_native.valid_fields = 7;
    native.payload.gnss_native.position_usable = 1; native.payload.gnss_native.velocity_valid_mask = 3;
    memcpy(native.payload.gnss_native.velocity_enu_mps, epoch->velocity_enu_mps, 3 * sizeof(float));
    Golden_Write(&native);
}

static void Golden_GnssEpochPrepare(uint64_t now, uint32_t sequence,
    NavigationKfGnssEpoch *epoch, NavigationReplayEvent *event)
{
    epoch->timestamp_us = now;
    epoch->valid_group_mask = (!s_reanchor_scenario && sequence % 7 == 0) ? 13 : 15; /* bad vertical position */
    for (unsigned axis = 0; axis < 3; axis++)
    {
        epoch->position_std_m[axis] = 2.5f;
        epoch->velocity_std_mps[axis] = 0.3f;
        event->position_variance[axis] = 6.25f;
        event->velocity_variance[axis] = 0.09f;
    }
    epoch->position_enu_m[0] = s_reanchor_scenario ? 0.0f : 0.2f * (float)sequence;
    if (s_integrity_scenario != 0U)
    {
        epoch->position_enu_m[0] = (float)(6378137.0 * 3.141592653589793 / 180.0 *
            (double)(18U * sequence) * 1e-7);
    }
    epoch->velocity_enu_mps[0] = s_reanchor_scenario ? 0.0f : 0.15f;
}

static void Golden_Gnss(uint64_t now, uint32_t sequence)
{
    NavigationReplayEvent event = {0};
    NavigationKfGnssEpoch epoch = {0};
    NavigationReplayOutcome outcome;
    FlightLogRecord record = {0};
    FlightLogGnssMeasurementRecord *m = &record.payload.gnss_measurement;
    Golden_GnssEpochPrepare(now, sequence, &epoch, &event);
    Golden_GnssNativeWrite(now, sequence, &epoch);
    record.record_type = FLIGHT_LOG_RECORD_GNSS_MEASUREMENT;
    record.timestamp_us = now;
    m->sample_timestamp_us = now; m->receive_timestamp_us = now;
    m->sequence = sequence; m->valid_group_mask = epoch.valid_group_mask;
    m->position_usable = 1; m->fusion_allowed = 1; m->velocity_valid_mask = 3;
    m->estimator_present_timestamp_us = now; m->replay_epoch = s_replay.epoch;
    m->receive_operation_sequence = ++s_operation;
    m->receive_result = (uint8_t)NavigationReplay_ReceiveTrack(&s_replay, &epoch, &event);
    event.sequence = sequence; event.vertical_valid = 1;
    memcpy(event.position, epoch.position_enu_m, sizeof(event.position));
    memcpy(event.velocity, epoch.velocity_enu_mps, sizeof(event.velocity));
    memcpy(m->position_enu_m, event.position, sizeof(event.position));
    memcpy(m->velocity_enu_mps, event.velocity, sizeof(event.velocity));
    memcpy(m->position_variance_m2, event.position_variance, sizeof(event.position_variance));
    memcpy(m->velocity_variance_m2ps2, event.velocity_variance, sizeof(event.velocity_variance));
    if (s_integrity_scenario != 0U &&
        !Golden_IntegrityApply(now, sequence, &event, m)) { exit(6); }
    m->position_measurement_timestamp_us = now - SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS * 1000ULL;
    m->velocity_measurement_timestamp_us = now - SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS * 1000ULL;
    /* This fixture uses the reference project's older velocity / current position. */
    event.kind = NAV_REPLAY_VELOCITY;
    event.measurement_timestamp_us = m->velocity_measurement_timestamp_us;
    m->velocity_operation_sequence = ++s_operation;
    m->velocity_replay_result = (uint8_t)NavigationReplay_Insert(&s_replay, &s_kf, &event, &outcome);
    m->group_update_result[2] = (uint8_t)outcome.velocity_groups.horizontal_result;
    m->group_update_result[3] = (uint8_t)outcome.velocity_groups.vertical_result;
    memcpy(m->group_nis + 2, outcome.group_nis + 2, 2 * sizeof(float));
    memcpy(m->velocity_innovation_mps, outcome.velocity_innovation, 3 * sizeof(float));
    event.kind = NAV_REPLAY_POSITION;
    event.measurement_timestamp_us = m->position_measurement_timestamp_us;
    m->position_operation_sequence = ++s_operation;
    m->position_replay_result = (uint8_t)NavigationReplay_Insert(&s_replay, &s_kf, &event, &outcome);
    m->group_update_result[0] = (uint8_t)outcome.position_groups.horizontal_result;
    m->group_update_result[1] = (uint8_t)outcome.position_groups.vertical_result;
    memcpy(m->group_nis, outcome.group_nis, 2 * sizeof(float));
    memcpy(m->position_innovation_m, outcome.position_innovation, 3 * sizeof(float));
    m->replay_generation = s_replay.diagnostics.replay_count;
    Golden_Write(&record);
    Golden_RecoveryWrite(now, sequence, &epoch, m);
}

static void Golden_Baro(uint64_t now, uint32_t sequence)
{
    NavigationReplayEvent event = {0};
    NavigationReplayOutcome outcome;
    FlightLogRecord record = {0};
    FlightLogBaroMeasurementRecord *m = &record.payload.baro_measurement;
    event.measurement_timestamp_us = now - SYSTEM_ESTIMATOR_BARO_MEASUREMENT_DELAY_MS * 1000ULL;
    event.receive_timestamp_us = now; event.epoch = s_replay.epoch;
    event.sequence = sequence; event.source = 1; event.kind = NAV_REPLAY_BAROMETER;
    event.altitude = 0.1f * sinf((float)sequence * 0.1f); event.altitude_variance = 6.25f;
    FlightLogRecord native = {0};
    native.record_type = FLIGHT_LOG_RECORD_BARO_NATIVE; native.timestamp_us = now;
    native.payload.baro_native.source_descriptor_id = PROJECT_DESCRIPTOR_ID_BARO_0;
    native.payload.baro_native.sample_timestamp_us = now;
    native.payload.baro_native.receive_timestamp_us = now;
    native.payload.baro_native.sequence = sequence;
    native.payload.baro_native.altitude_m = event.altitude;
    native.payload.baro_native.altitude_variance_m2 = event.altitude_variance;
    native.payload.baro_native.healthy = 1; native.payload.baro_native.valid_mask = 3;
    native.payload.baro_native.supported_fields = 3; native.payload.baro_native.valid_fields = 3;
    Golden_Write(&native);
    record.timestamp_us = now; record.record_type = FLIGHT_LOG_RECORD_BARO_MEASUREMENT;
    m->sample_timestamp_us = now; m->receive_timestamp_us = now; m->sequence = sequence;
    m->relative_altitude_m = event.altitude; m->variance_m2 = event.altitude_variance;
    m->valid_mask = 3; m->measurement_timestamp_us = event.measurement_timestamp_us;
    m->estimator_present_timestamp_us = now; m->operation_sequence = ++s_operation;
    m->replay_epoch = s_replay.epoch;
    m->replay_result = (uint8_t)NavigationReplay_Insert(&s_replay, &s_kf, &event, &outcome);
    m->update_result = (uint8_t)outcome.barometer; m->nis = outcome.baro_nis;
    m->innovation_m = outcome.baro_innovation; m->replay_generation = s_replay.diagnostics.replay_count;
    Golden_Write(&record);
}

static int Golden_FlightStep(uint32_t index, InsInertialContext *frontend)
{
        InsAlgorithmSample sample = {0}; InsState increment;
        FlightLogRecord record = {0};
        sample.timestamp_us = (uint64_t)index * 5000ULL;
        sample.valid_flags = 3;
        sample.accel_b_mps2[0] = 0.01f * (float)(index % 11);
        sample.accel_b_mps2[2] = SYSTEM_KF_GRAVITY_MPS2;
        sample.gyro_b_radps[2] = 0.001f * (float)(index % 7);
        if (s_reanchor_scenario)
        {
            sample.gyro_b_radps[2] = 0.0f;
            sample.accel_b_mps2[0] = (index >= 100 && index <= 300) ? 2000.0f : 0.0f;
        }
        record.record_type = FLIGHT_LOG_RECORD_IMU_CORRECTED; record.timestamp_us = sample.timestamp_us;
        record.valid_flags = 3; record.payload.imu_corrected.sample_timestamp_us = sample.timestamp_us;
        record.payload.imu_corrected.receive_timestamp_us = sample.timestamp_us;
        record.payload.imu_corrected.sequence = index + 1; record.payload.imu_corrected.valid_mask = 3;
        record.payload.imu_corrected.correction_valid = 1;
        memcpy(record.payload.imu_corrected.accel_b_mps2, sample.accel_b_mps2, 3 * sizeof(float));
        memcpy(record.payload.imu_corrected.gyro_b_radps, sample.gyro_b_radps, 3 * sizeof(float));
        Golden_Write(&record);
        if (InsInertial_Update(frontend, &sample, &increment) != INS_INERTIAL_UPDATE_READY) { return 0; }
        memset(&record, 0, sizeof(record));
        record.timestamp_us = sample.timestamp_us; record.record_type = FLIGHT_LOG_RECORD_INERTIAL_INCREMENT;
        record.valid_flags = 1;
        FlightLogInertialIncrementRecord *i = &record.payload.inertial_increment;
        i->sequence = increment.update_count; i->interval_start_timestamp_us = increment.interval_start_timestamp_us;
        i->interval_end_timestamp_us = increment.timestamp_us; i->dt_s = increment.dt_s;
        memcpy(i->delta_theta_b_corrected, increment.delta_theta_b_coning_corrected, 3 * sizeof(float));
        memcpy(i->delta_velocity_b_sculling_corrected, increment.delta_velocity_b_sculling_corrected, 3 * sizeof(float));
        Golden_Write(&record);
        float dv[3], q_next[4];
        Ins_TransformDeltaVelocityToNavigation(s_q, i->delta_velocity_b_sculling_corrected,
            i->dt_s, SYSTEM_KF_GRAVITY_MPS2, dv);
        if (!Attitude_PropagateQuaternionBodyIncrement(s_q, i->delta_theta_b_corrected, q_next)) { return 4; }
        memcpy(s_q, q_next, sizeof(s_q));
        memset(&record.payload, 0, sizeof(record.payload));
        record.record_type = FLIGHT_LOG_RECORD_ESTIMATOR_STEP;
        record.payload.estimator_step.operation_sequence = ++s_operation;
        record.payload.estimator_step.replay_result = (uint8_t)NavigationReplay_Predict(
            &s_replay, &s_kf, sample.timestamp_us, dv, increment.dt_s);
        record.payload.estimator_step.estimator_present_timestamp_us = s_replay.present_us;
        record.payload.estimator_step.interval_end_timestamp_us = sample.timestamp_us;
        record.payload.estimator_step.source_sequence = increment.update_count;
        record.payload.estimator_step.replay_epoch = 1; record.payload.estimator_step.attitude_result = 1;
        record.payload.estimator_step.replay_generation = s_replay.diagnostics.replay_count;
        Golden_Write(&record);
        if (index >= 80 && index % 8 == 0 && (!s_reanchor_scenario || index < 100 || index > 400)) { Golden_Gnss(sample.timestamp_us, index / 8); }
        if (index >= 80) { Golden_Baro(sample.timestamp_us, index / 2); }
        Golden_Snapshot(sample.timestamp_us);
    return 0;
}

int main(int argc, char **argv)
{
    s_reanchor_scenario = (uint8_t)(argc == 3 && strcmp(argv[2], "reanchor") == 0);
    s_integrity_scenario = (uint8_t)(argc == 3 && strcmp(argv[2], "integrity") == 0);
    if ((argc != 2 && argc != 3) || (s_file = fopen(argv[1], "wb")) == NULL) { return 1; }
    FlightLogFileHeaderInfo header = {0};
    uint8_t bytes[FLIGHT_LOG_MAX_RECORD_SIZE]; uint16_t size;
    header.nominal_imu_rate_hz = 200; header.nominal_ins_rate_hz = 100;
    header.local_gravity_mps2 = SYSTEM_KF_GRAVITY_MPS2;
    header.firmware_version[2] = SILVERSTAR_VERSION_PATCH;
    header.coordinate_frame = 1; header.quaternion_order = 1; header.quaternion_semantics = 1;
    header.mechanization_subsample_count = 2;
    header.position_axis_order[0] = 3; header.position_axis_order[1] = 1; header.position_axis_order[2] = 2;
    if (FlightLog_FileHeaderSerialize(&header, bytes, sizeof(bytes), &size) !=
        FLIGHT_LOG_SERIALIZE_RESULT_OK || fwrite(bytes, 1, size, s_file) != size) { return 2; }
    NavigationKf_Init(&s_kf);
    float process[3] = {SYSTEM_ESTIMATOR_PROCESS_ACCEL_E_STD_MPS2_OVERRIDE,
        SYSTEM_ESTIMATOR_PROCESS_ACCEL_N_STD_MPS2_OVERRIDE, SYSTEM_ESTIMATOR_PROCESS_ACCEL_U_STD_MPS2_OVERRIDE};
    NavigationKf_SetProcessAccelStd(&s_kf, process);
    NavigationReplay_Reset(&s_replay, &s_storage, &s_kf, 0, 1);
    if (!Golden_IntegrityInit()) { return 6; }
    Golden_Bootstrap();
    InsInertialContext frontend; InsInertial_Reset(&frontend);
    for (uint32_t index = 0; index <=
         (s_reanchor_scenario ? 4000U : (s_integrity_scenario ? 3200U : 800U)); index++)
    {
        if (Golden_FlightStep(index, &frontend) != 0) { return 4; }
    }
    return fclose(s_file) == 0 ? 0 : 5;
}

