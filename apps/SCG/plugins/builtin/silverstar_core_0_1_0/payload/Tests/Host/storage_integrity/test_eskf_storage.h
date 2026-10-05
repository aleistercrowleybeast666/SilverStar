/* Storage throughput model: actual LoggerBus admission/cadence, not an
 * estimator correctness fixture. Sample values identify synthetic inputs. */
#ifndef __TEST_ESKF_STORAGE_H
#define __TEST_ESKF_STORAGE_H

static uint32_t s_eskf_body_attempts;
static uint32_t s_eskf_measurement_attempts;
static uint32_t s_eskf_covariance_attempts;

static void Fixture_EskfCovariance(uint32_t frame, uint64_t now, uint8_t phase)
{
    FlightLogEskf15CovariancePartRecord identity = {0};
    float covariance[225] = {0};
    identity.snapshot_id = frame;
    identity.epoch = 1U;
    identity.source_id = 1U;
    identity.algorithm_id = 2U;
    identity.phase = phase;
    for (uint32_t axis = 0U; axis < 15U; ++axis) { covariance[axis * 15U + axis] = 1.0f; }
    s_eskf_covariance_attempts++;
    Fixture_ResultCheck(LoggerBus_Eskf15CovariancePush(now, &identity, covariance));
}

static void Fixture_EskfMeasurement(uint32_t frame, uint64_t now, uint8_t group)
{
    FlightLogEskf15MeasurementRecord measurement = {0};
    measurement.sample_timestamp_us = now - 40000ULL;
    measurement.receive_timestamp_us = now;
    measurement.measurement_timestamp_us = now - 40000ULL;
    measurement.evaluation_timestamp_us = now;
    measurement.operation_sequence = frame * 5U + group;
    measurement.epoch = 1U;
    measurement.source_id = (group == 4U) ? 1U : 2U;
    measurement.group = group;
    measurement.physically_valid = 1U;
    measurement.admitted = 1U;
    measurement.base_variance[0] = 1.0f;
    measurement.base_variance[1] = 1.0f;
    measurement.effective_variance[0] = 1.0f;
    measurement.effective_variance[1] = 1.0f;
    measurement.quality_scale = 1.0f;
    measurement.consistency_scale = 1.0f;
    measurement.robust_scale = 1.0f;
    s_eskf_measurement_attempts++;
    Fixture_ResultCheck(LoggerBus_Eskf15MeasurementPush(now, &measurement));
}

static void Fixture_EskfFrame(uint32_t frame, uint64_t now)
{
    FlightLogRecord record = {0};
    FlightLogEskf15StateRecord state = {0};
    state.snapshot_id = frame;
    state.epoch = 1U;
    state.source_id = 1U;
    state.algorithm_id = 2U;
    state.algorithm_revision = 1U;
    state.quality_revision = 3U;
    state.q_nb[0] = 1.0f;
    for (uint32_t axis = 0U; axis < 15U; ++axis) { state.p_diagonal[axis] = 1.0f; }
    if (frame == 1200U)
    {
        Fixture_ResultCheck(LoggerBus_Eskf15InitialStatePush(now, &state));
        Fixture_EskfCovariance(frame, now, 0U);
    }
    if (frame % 2U != 0U) { return; }
    record.payload.eskf15_body_input.interval_start_timestamp_us = now - 10000ULL;
    record.payload.eskf15_body_input.interval_end_timestamp_us = now;
    record.payload.eskf15_body_input.sequence = frame / 2U;
    record.payload.eskf15_body_input.source_id = 1U;
    record.payload.eskf15_body_input.dt_s = 0.01f;
    record.payload.eskf15_body_input.body_accel_mps2[2] = 9.78f;
    record.payload.eskf15_body_input.body_accel_mps2[5] = 9.78f;
    s_eskf_body_attempts++;
    Fixture_ResultCheck(LoggerBus_Eskf15BodyInputPush(now, &record.payload.eskf15_body_input));
    Fixture_ResultCheck(LoggerBus_Eskf15StatePush(now, &state));
    Fixture_EskfCovariance(frame, now, 1U);
    Fixture_EskfMeasurement(frame, now, 4U);
    if (frame % 8U == 0U)
    {
        for (uint8_t group = 0U; group < 4U; ++group) { Fixture_EskfMeasurement(frame, now, group); }
        memset(&record, 0, sizeof(record));
        record.payload.navigation_quality.quality_revision = 3U;
        record.payload.navigation_quality.evaluation_us = now;
        record.payload.navigation_quality.source_id = 2U;
        Fixture_ResultCheck(LoggerBus_NavigationQualityPush(now, &record.payload.navigation_quality));
    }
}

#endif
