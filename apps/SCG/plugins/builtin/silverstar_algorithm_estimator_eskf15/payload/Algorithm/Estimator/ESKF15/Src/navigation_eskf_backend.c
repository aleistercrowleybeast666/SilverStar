#include "system_navigation_backend.h"
#include "navigation_eskf_replay.h"
#include "navigation_eskf_horizon.h"
#include "navigation_eskf_config.h"
#include "navigation_quality.h"
#include "geodesy_local.h"
#include "estimator_bus.h"
#include "system_navigation_health.h"
#include "system_source_selector.h"
#include "system_time.h"
#include "system_calibration.h"
#include "system_gnss_quality.h"
#include "system_user_config.h"
#include "system_fusion_timing.h"
_Static_assert((SYSTEM_FUSION_TIMING_MODE == 0U) || (SYSTEM_FUSION_TIMING_MODE == 1U) ||
    (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON),
    "Unsupported fusion timing mode");
#include "platform_memory.h"
#include "silverstar_assert.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include <math.h>
#include <string.h>

/* Runtime evidence is owned by navigation even when SSLOG is not selected.
 * The optional logging adapter below maps fields explicitly; no wire-layout cast. */
typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint64_t measurement_timestamp_us;
    uint64_t evaluation_timestamp_us;
    uint32_t operation_sequence;
    uint32_t epoch;
    uint32_t source_id;
    uint32_t calibration_generation;
    uint8_t group;
    uint8_t physically_valid;
    uint8_t admitted;
    uint8_t update_result;
    float observation[2];
    float innovation[2];
    float base_variance[2];
    float effective_variance[2];
    float nis;
    float quality_scale;
    float consistency_scale;
    float robust_scale;
    uint64_t application_timestamp_us;
    uint32_t source_sequence;
    uint8_t timing_flags;
    uint8_t execution_result;
    uint8_t phase;
    uint8_t effective_update;
    float prepared_variance[2];
} BackendMeasurementContext;

/* EstimatorTask is the only runtime owner. No DMA, heap, or replay side effects. */
static NavigationEskfState s_state; /* CPU main SRAM, never DMA. */
static NavigationEskfHorizon s_horizon; /* CPU main SRAM, independently collectable. */
static PLATFORM_ESKF_WORK_BSS NavigationEskfWorkspace s_work;
static PLATFORM_ESKF_HISTORY_BSS NavigationEskfReplay s_history;
static NavigationEskfHistoryInput s_body_history[NAV_ESKF_HISTORY_CAPACITY];
static SystemFusionReceipt s_current_gnss[SYSTEM_FUSION_SOURCE_COUNT];
static SystemFusionReceipt s_current_baro;
static float s_current_endpoint_rate[3];
static uint64_t s_current_epoch_start_us;
static uint8_t s_current_endpoint_valid;
static uint8_t s_current_faulted;
static PLATFORM_ESKF_WINDOW_BSS NavigationWindowContext s_eskf_window;
static GeoLocalFrame s_frame;
static float s_baro_origin;
static uint8_t s_baro_origin_valid;
static uint32_t s_gnss_sequence;
static uint32_t s_baro_sequence;
static uint32_t s_operation;
static uint32_t s_snapshot_id;
static uint32_t s_log_failures;
static uint64_t s_native_week_us;
static uint32_t s_native_tow_ms;
static uint8_t s_gnss_seen;
static uint8_t s_baro_seen;
static uint8_t s_active;
static uint8_t s_started;
static uint8_t s_gnss_source;
static uint32_t s_imu_quality_flags;
static uint32_t s_calibration_generation;

static uint64_t Backend_EvaluationTimeGet(void)
{
    return (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) ?
        s_horizon.present_us : s_state.timestamp_us;
}

static SystemFusionExecutionResult Backend_HorizonExecutionGet(NavigationEskfHorizonResult result)
{
    switch (result)
    {
        case NAV_ESKF_HORIZON_OK: return SYSTEM_FUSION_EXEC_COMPLETE;
        case NAV_ESKF_HORIZON_QUEUED: return SYSTEM_FUSION_EXEC_QUEUED;
        case NAV_ESKF_HORIZON_WARMUP: return SYSTEM_FUSION_EXEC_WARMUP;
        case NAV_ESKF_HORIZON_STALE: return SYSTEM_FUSION_EXEC_STALE;
        case NAV_ESKF_HORIZON_LATE: return SYSTEM_FUSION_EXEC_LATE;
        case NAV_ESKF_HORIZON_CAPACITY: return SYSTEM_FUSION_EXEC_CAPACITY;
        case NAV_ESKF_HORIZON_DUPLICATE: return SYSTEM_FUSION_EXEC_DUPLICATE;
        case NAV_ESKF_HORIZON_EPOCH_MISMATCH: return SYSTEM_FUSION_EXEC_EPOCH_MISMATCH;
        case NAV_ESKF_HORIZON_DISCONTINUITY: return SYSTEM_FUSION_EXEC_DISCONTINUITY;
        case NAV_ESKF_HORIZON_NUMERIC_ERROR: return SYSTEM_FUSION_EXEC_NUMERIC_ERROR;
        case NAV_ESKF_HORIZON_MODEL_MISMATCH: return SYSTEM_FUSION_EXEC_MODEL_MISMATCH;
        case NAV_ESKF_HORIZON_NOT_READY: return SYSTEM_FUSION_EXEC_NOT_READY;
        case NAV_ESKF_HORIZON_BUSY: return SYSTEM_FUSION_EXEC_BUSY;
        case NAV_ESKF_HORIZON_EMPTY:
        case NAV_ESKF_HORIZON_INVALID:
        default: return SYSTEM_FUSION_EXEC_INVALID;
    }
}

/* EstimatorTask is the sole writer. A live DAP reader accepts only equal,
 * even sequence values around a read of this history-insertion evidence. */
typedef struct
{
    uint32_t sequence;
    uint64_t last_start_us;
    uint64_t last_end_us;
    uint64_t max_duration_end_us;
    uint64_t first_long_duration_end_us;
    uint64_t last_long_duration_end_us;
    uint32_t last_duration_us;
    uint32_t max_duration_us;
    uint32_t duration_over_20ms_count;
    uint32_t insert_count;
    uint8_t last_group;
    uint8_t max_group;
} EskfReplayTimingDiagnostics;

static volatile EskfReplayTimingDiagnostics s_eskf_replay_timing;

static void Backend_ReplayTimingRecord(uint64_t start_us, uint64_t end_us,
    uint8_t group)
{
    uint64_t elapsed_us = (end_us >= start_us) ? end_us - start_us : 0U;
    uint32_t duration_us = (elapsed_us > UINT32_MAX) ? UINT32_MAX : (uint32_t)elapsed_us;

    s_eskf_replay_timing.sequence++;
    s_eskf_replay_timing.last_end_us = end_us;
    s_eskf_replay_timing.last_duration_us = duration_us;
    s_eskf_replay_timing.last_group = group;
    if (duration_us > s_eskf_replay_timing.max_duration_us)
    {
        s_eskf_replay_timing.max_duration_us = duration_us;
        s_eskf_replay_timing.max_duration_end_us = end_us;
        s_eskf_replay_timing.max_group = group;
    }
    if ((duration_us >= 20000U) &&
        (s_eskf_replay_timing.duration_over_20ms_count < UINT32_MAX))
    {
        if (s_eskf_replay_timing.first_long_duration_end_us == 0U)
        { s_eskf_replay_timing.first_long_duration_end_us = end_us; }
        s_eskf_replay_timing.last_long_duration_end_us = end_us;
        s_eskf_replay_timing.duration_over_20ms_count++;
    }
    if (s_eskf_replay_timing.insert_count < UINT32_MAX)
    { s_eskf_replay_timing.insert_count++; }
    s_eskf_replay_timing.sequence++;
}

static const NavigationEskfConfig s_config = {
    SYSTEM_ESKF_GRAVITY_MPS2, SYSTEM_ESKF_GYRO_NOISE_DENSITY,
    SYSTEM_ESKF_ACCEL_NOISE_DENSITY, SYSTEM_ESKF_GYRO_BIAS_RW,
    SYSTEM_ESKF_ACCEL_BIAS_RW,
    {SYSTEM_ESKF_NIS_1D_SOFT, SYSTEM_ESKF_NIS_2D_SOFT},
    {SYSTEM_ESKF_NIS_1D_HARD, SYSTEM_ESKF_NIS_2D_HARD},
    SYSTEM_ESKF_NIS_MAX_R_SCALE,
    (uint8_t)((1U - SYSTEM_ESKF_NIS_SOFT_ENABLED) |
        ((1U - SYSTEM_ESKF_NIS_HARD_ENABLED) << 1U))
};
static const NavigationWindowConfig s_window_config = {
    10000000ULL, 5000000ULL, 6000000ULL, 120000U, 10.0f, 4.0f
};
static const float s_initial_diagonal[NAV_ESKF_DIM] = {
    SYSTEM_ESKF_P0_POSITION_E, SYSTEM_ESKF_P0_POSITION_N, SYSTEM_ESKF_P0_POSITION_U,
    SYSTEM_ESKF_P0_VELOCITY_E, SYSTEM_ESKF_P0_VELOCITY_N, SYSTEM_ESKF_P0_VELOCITY_U,
    SYSTEM_ESKF_P0_THETA_X, SYSTEM_ESKF_P0_THETA_Y, SYSTEM_ESKF_P0_THETA_Z,
    SYSTEM_ESKF_P0_GYRO_BIAS_X, SYSTEM_ESKF_P0_GYRO_BIAS_Y, SYSTEM_ESKF_P0_GYRO_BIAS_Z,
    SYSTEM_ESKF_P0_ACCEL_BIAS_X, SYSTEM_ESKF_P0_ACCEL_BIAS_Y, SYSTEM_ESKF_P0_ACCEL_BIAS_Z
};

void SystemNavigationBackend_Reset(void)
{
    s_active = 0U; s_started = 0U; s_gnss_seen = 0U; s_baro_seen = 0U;
    s_state.initialized = 0U; s_operation = 0U; s_snapshot_id = 0U;
    memset(&s_frame, 0, sizeof(s_frame));
    s_baro_origin = 0.0f; s_baro_origin_valid = 0U;
    s_native_week_us = 0U; s_native_tow_ms = 0U; s_log_failures = 0U;
    s_imu_quality_flags = 0U;
    if (SYSTEM_FUSION_TIMING_MODE != SYSTEM_FUSION_TIMING_LEGACY_REPLAY)
    {
        memset(s_current_gnss, 0, sizeof(s_current_gnss));
        memset(&s_current_baro, 0, sizeof(s_current_baro));
        memset(s_current_endpoint_rate, 0, sizeof(s_current_endpoint_rate));
        s_current_epoch_start_us = 0U; s_current_endpoint_valid = 0U; s_current_faulted = 0U;
    }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { s_horizon.initialized = 0U; }
    (void)NavigationWindow_Reset(&s_eskf_window);
}

SystemDeviceResult SystemNavigationBackend_Initialize(const float q_nb[4],
    const SystemGnssSample *origin, float barometer_origin_m,
    uint8_t barometer_origin_valid, uint32_t generation, uint8_t activate)
{
    float nominal[16] = {0.0f};
    uint32_t axis;
    uint8_t source;
    if ((q_nb == NULL) || (origin == NULL) || (barometer_origin_valid > 1U) ||
        !isfinite(barometer_origin_m))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(origin, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SystemNavigationBackend_Reset();
    if ((NavigationEskf_ConfigValidate(&s_config) != NAV_ESKF_OK) ||
        (NavigationWindow_ConfigValidate(&s_window_config) != NAV_QUALITY_OK))
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    if (SystemSourceSelector_ImuActiveInstanceGet(&source) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_READY; }
    memcpy(&nominal[6], q_nb, 4U * sizeof(float));
    if (origin->position_usable != 0U)
    {
        if ((SystemSourceSelector_GnssActiveInstanceGet(&s_gnss_source) != SYSTEM_DEVICE_OK) ||
            (GeoLocalFrame_Init(&s_frame, origin->latitude_e7, origin->longitude_e7,
                               origin->ellipsoid_height_mm) == 0U))
        { return SYSTEM_DEVICE_NOT_READY; }
        for (axis = 0U; axis < 3U; axis++)
        {
            if ((origin->velocity_valid_mask & (1U << axis)) != 0U)
            { nominal[3U + axis] = origin->velocity_enu_mps[axis]; }
        }
    }
    memset(s_work.f, 0, sizeof(s_work.f));
    for (axis = 0U; axis < NAV_ESKF_DIM; axis++)
    { s_work.f[axis][axis] = s_initial_diagonal[axis]; }
    if (NavigationEskf_Initialize(&s_state, &s_work, nominal,
            (const float (*)[NAV_ESKF_DIM])s_work.f, 0U, source, generation) != NAV_ESKF_OK)
    { return SYSTEM_DEVICE_VERIFY_FAILED; }
    if (SYSTEM_FUSION_TIMING_MODE == 1U)
    {
        if (NavigationEskfReplay_Reset(&s_history, &s_state, s_body_history) != NAV_ESKF_REPLAY_OK)
        { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    }
    s_baro_origin = barometer_origin_m;
    s_baro_origin_valid = barometer_origin_valid; s_active = activate;
    s_calibration_generation = SystemCalibration_GenerationGet();
    SystemNavigationHealth_Reset(0U);
    return SYSTEM_DEVICE_OK;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void Backend_LogResult(LoggerBusResult result)
{
    if (result != LOGGER_BUS_RESULT_OK)
    { s_log_failures++; }
}

static void Backend_HorizonMeasurementLog(const BackendMeasurementContext *measurement)
{
    FlightLogFusionHorizonMeasurementRecord record = {0};
    record.sample_timestamp_us = measurement->sample_timestamp_us;
    record.receive_timestamp_us = measurement->receive_timestamp_us;
    record.measurement_timestamp_us = measurement->measurement_timestamp_us;
    record.application_timestamp_us = measurement->application_timestamp_us;
    record.evaluation_timestamp_us = measurement->evaluation_timestamp_us;
    record.operation_sequence = measurement->operation_sequence; record.epoch = measurement->epoch;
    record.source_id = measurement->source_id; record.calibration_generation = measurement->calibration_generation;
    record.source_sequence = measurement->source_sequence;
    record.algorithm_id = 2U; record.algorithm_revision = NAV_ESKF_REVISION;
    record.numerical_revision = NAV_ESKF_NUMERICAL_REVISION_STABLE_RESET;
    record.phase = measurement->phase; record.group = measurement->group;
    record.physically_valid = measurement->physically_valid; record.admitted = measurement->admitted;
    record.update_result = measurement->update_result; record.fusion_timing_mode = SYSTEM_FUSION_TIMING_HORIZON;
    record.timing_flags = measurement->timing_flags; record.execution_result = measurement->execution_result;
    record.effective_update = measurement->effective_update;
    memcpy(record.observation,measurement->observation,sizeof(record.observation));
    memcpy(record.innovation,measurement->innovation,sizeof(record.innovation));
    memcpy(record.prepared_variance,measurement->prepared_variance,sizeof(record.prepared_variance));
    memcpy(record.effective_variance,measurement->effective_variance,sizeof(record.effective_variance));
    record.nis = measurement->nis; record.quality_scale = measurement->quality_scale;
    record.consistency_scale = measurement->consistency_scale; record.robust_scale = measurement->robust_scale;
    Backend_LogResult(LoggerBus_FusionHorizonMeasurementPush(measurement->evaluation_timestamp_us,&record));
}

static void Backend_MeasurementLog(const BackendMeasurementContext *measurement)
{
    FlightLogEskf15MeasurementRecord record;
    SILVERSTAR_ASSERT_OBJECT(measurement, BackendMeasurementContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(measurement->group < 5U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { Backend_HorizonMeasurementLog(measurement); return; }
    record.sample_timestamp_us = measurement->sample_timestamp_us;
    record.receive_timestamp_us = measurement->receive_timestamp_us;
    record.measurement_timestamp_us = measurement->measurement_timestamp_us;
    record.evaluation_timestamp_us = measurement->evaluation_timestamp_us;
    record.operation_sequence = measurement->operation_sequence;
    record.epoch = measurement->epoch;
    record.source_id = measurement->source_id;
    record.calibration_generation = measurement->calibration_generation;
    record.group = measurement->group;
    record.physically_valid = measurement->physically_valid;
    record.admitted = measurement->admitted;
    record.update_result = measurement->update_result;
    record.nis = measurement->nis;
    record.quality_scale = measurement->quality_scale;
    record.consistency_scale = measurement->consistency_scale;
    record.robust_scale = measurement->robust_scale;
    record.application_timestamp_us = measurement->application_timestamp_us;
    record.fusion_timing_mode = SYSTEM_FUSION_TIMING_MODE;
    record.timing_flags = measurement->timing_flags;
    record.execution_result = measurement->execution_result;
    record.timing_reserved = 0U;
    record.source_sequence = measurement->source_sequence;
    memcpy(record.observation, measurement->observation, sizeof(record.observation));
    memcpy(record.innovation, measurement->innovation, sizeof(record.innovation));
    memcpy(record.base_variance, measurement->base_variance, sizeof(record.base_variance));
    memcpy(record.effective_variance, measurement->effective_variance, sizeof(record.effective_variance));
    Backend_LogResult(LoggerBus_Eskf15MeasurementPush(s_state.timestamp_us, &record));
}

static void Backend_StateRecordBuild(FlightLogEskf15StateRecord *record)
{
    uint32_t axis;
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogEskf15StateRecord, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memset(record, 0, sizeof(*record));
    record->snapshot_id = s_snapshot_id; record->epoch = s_state.generation;
    record->source_id = s_state.source; record->calibration_generation = s_calibration_generation;
    record->algorithm_id = 2U; record->algorithm_revision = NAV_ESKF_REVISION;
    record->quality_revision = NAV_QUALITY_REVISION;
    record->health = (uint8_t)SystemNavigationHealth_OverallGet(s_state.timestamp_us,
        SYSTEM_FUSION_REQUIRED_HEALTH_MASK, s_imu_quality_flags);
    memcpy(record->position_enu_m, s_state.position, sizeof(s_state.position));
    memcpy(record->velocity_enu_mps, s_state.velocity, sizeof(s_state.velocity));
    memcpy(record->q_nb, s_state.quaternion, sizeof(s_state.quaternion));
    memcpy(record->gyro_bias_radps, s_state.gyro_bias, sizeof(s_state.gyro_bias));
    memcpy(record->accel_bias_mps2, s_state.accel_bias, sizeof(s_state.accel_bias));
    for (axis = 0U; axis < NAV_ESKF_DIM; axis++)
    { record->p_diagonal[axis] = s_state.covariance[axis][axis]; }
}

static void Backend_CovarianceLog(uint8_t initial)
{
    FlightLogEskf15CovariancePartRecord identity;
    SILVERSTAR_ASSERT(initial <= 1U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    memset(&identity, 0, sizeof(identity));
    identity.snapshot_id = s_snapshot_id; identity.epoch = s_state.generation;
    identity.source_id = s_state.source; identity.calibration_generation = s_calibration_generation;
    identity.algorithm_id = 2U; identity.phase = (uint8_t)(initial == 0U);
    Backend_LogResult(LoggerBus_Eskf15CovariancePush(s_state.timestamp_us,
        &identity, &s_state.covariance[0][0]));
}

static void Backend_StateLog(uint8_t initial)
{
    FlightLogEskf15StateRecord record;
    SILVERSTAR_ASSERT(initial <= 1U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    s_snapshot_id++;
    Backend_StateRecordBuild(&record);
    Backend_LogResult(initial ? LoggerBus_Eskf15InitialStatePush(s_state.timestamp_us, &record) :
        LoggerBus_Eskf15StatePush(s_state.timestamp_us, &record));
    Backend_CovarianceLog(initial);
}

static void Backend_BodyLog(const NavigationEskfBodyInput *body, uint32_t sequence)
{
    FlightLogEskf15BodyInputRecord record;
    SILVERSTAR_ASSERT_OBJECT(body, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memset(&record, 0, sizeof(record));
    record.interval_start_timestamp_us = body->start_us;
    record.interval_end_timestamp_us = body->end_us;
    record.sequence = sequence; record.source_id = body->source;
    record.calibration_generation = s_calibration_generation; record.quality_flags = body->quality_flags;
    record.dt_s = body->dt_s;
    memcpy(record.body_gyro_radps, body->gyro_radps, sizeof(record.body_gyro_radps));
    memcpy(record.body_accel_mps2, body->accel_mps2, sizeof(record.body_accel_mps2));
    Backend_LogResult(LoggerBus_Eskf15BodyInputPush(body->end_us, &record));
}

#endif

static float Backend_ConsistencyGet(const SystemGnssSample *sample, const float position[3])
{
    NavigationWindowSample window_sample;
    SystemGnssTime native;
    uint8_t source;
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(position, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((SystemGnss_TimeGet(&native) != SYSTEM_DEVICE_OK) ||
        (native.sequence != sample->sequence) || (native.time_of_week_ms >= 604800000U) ||
        (SystemSourceSelector_GnssActiveInstanceGet(&source) != SYSTEM_DEVICE_OK)) { return 1.0f; }
    if ((native.time_of_week_ms < s_native_tow_ms) && ((s_native_tow_ms - native.time_of_week_ms) > 302400000U))
    { s_native_week_us += 604800000000ULL; }
    s_native_tow_ms = native.time_of_week_ms;
    memset(&window_sample, 0, sizeof(window_sample));
    window_sample.epoch_us = s_native_week_us + (uint64_t)native.time_of_week_ms * 1000ULL;
    window_sample.sequence = sample->sequence; window_sample.source = source;
    window_sample.generation = s_state.generation;
    memcpy(window_sample.position_en, position, sizeof(window_sample.position_en));
    memcpy(window_sample.velocity_en, sample->velocity_enu_mps, sizeof(window_sample.velocity_en));
    window_sample.position_valid = (uint8_t)((sample->valid_group_mask & 1U) != 0U);
    window_sample.velocity_valid = (uint8_t)((sample->valid_group_mask & 4U) != 0U);
    (void)NavigationWindow_Receive(&s_eskf_window, &s_window_config, &window_sample);
    return NavigationWindow_VarianceScale(&s_eskf_window, &s_window_config, window_sample.epoch_us);
}

static void Backend_AngularRateGet(uint64_t epoch_us, float rate[3])
{
    uint16_t index;
    SILVERSTAR_ASSERT_OBJECT(rate, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memset(rate, 0, 3U * sizeof(float));
    for (index = 0U; index < s_history.body_count; index++)
    {
        const NavigationEskfHistoryInput *body = &s_history.body[index];
        uint64_t start_us = (index == 0U) ? s_history.anchor.timestamp_us : s_history.body[index - 1U].end_us;
        if ((epoch_us >= start_us) && (epoch_us <= body->end_us))
        {
            uint8_t half = (uint8_t)((epoch_us - start_us) > ((body->end_us - start_us) / 2U));
            memcpy(rate, body->gyro_radps[half], 3U * sizeof(float)); return;
        }
    }
}


static void Backend_OutcomeSnapshotWrite(const BackendMeasurementContext *record,
    const SystemNavigationFusionEvidence *evidence, EstimatorOutputSnapshot *output)
{
    uint8_t axis, first = (record->group & 1U) ? 2U : 0U;
    uint8_t count = (record->group & 1U) ? 1U : 2U;
    SystemEstimatorMeasurementResult result = (record->update_result <= 4U) ?
        (SystemEstimatorMeasurementResult)record->update_result : SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    SILVERSTAR_ASSERT_OBJECT(output, EstimatorOutputSnapshot, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(record->group < 5U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (record->group < 4U)
    {
        output->measurement_attempt_mask |= (record->group < 2U) ?
            ESTIMATOR_ATTEMPT_GNSS_POSITION : ESTIMATOR_ATTEMPT_GNSS_VELOCITY;
        for (axis = 0U; axis < count; axis++)
        {
            if (record->group < 2U)
            {
                output->position_innovation[first + axis] = record->innovation[axis];
                output->position_variance_r[first + axis] = record->effective_variance[axis];
            }
            else
            {
                output->velocity_innovation[first + axis] = record->innovation[axis];
                output->velocity_variance_r[first + axis] = record->effective_variance[axis];
            }
        }
        if (record->group < 2U)
        {
            output->last_position_nis = record->nis; output->position_r_scale = evidence->variance_scale;
            if (record->group == 0U || result < output->position_update_result) { output->position_update_result = result; }
            if (evidence->effective_update) { output->gnss_position_update_count++; } else { output->position_reject_count++; }
        }
        else
        {
            output->last_velocity_nis = record->nis; output->velocity_r_scale = evidence->variance_scale;
            if (record->group == 2U || result < output->velocity_update_result) { output->velocity_update_result = result; }
            if (evidence->effective_update) { output->gnss_velocity_update_count++; } else { output->velocity_reject_count++; }
        }
    }
    else
    {
        output->measurement_attempt_mask |= ESTIMATOR_ATTEMPT_BAROMETER;
        output->baro_update_result = result; output->baro_innovation = record->innovation[0];
        output->baro_variance_r = record->effective_variance[0]; output->last_baro_nis = record->nis;
        output->baro_r_scale = evidence->variance_scale;
        if (evidence->effective_update) { output->baro_update_count++; } else { output->baro_reject_count++; }
    }
}

static void Backend_OutcomePublish(const NavigationEskfReplayEvent *event,
    BackendMeasurementContext *record, NavigationEskfReplayResult replay,
    const NavigationEskfOutcome *outcome, EstimatorOutputSnapshot *output)
{
    SystemNavigationFusionEvidence evidence;
    SILVERSTAR_ASSERT_OBJECT(event, NavigationEskfReplayEvent, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(outcome, NavigationEskfOutcome, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memset(&evidence, 0, sizeof(evidence));
    record->operation_sequence = ++s_operation; record->epoch = s_state.generation;
    record->source_id = event->source; record->calibration_generation = s_calibration_generation;
    record->group = event->measurement.group; record->physically_valid = event->measurement.physically_valid;
    record->measurement_timestamp_us = event->measurement_us; record->receive_timestamp_us = event->receive_us;
    record->evaluation_timestamp_us = s_state.timestamp_us;
    record->source_sequence = event->sequence;
    if (SYSTEM_FUSION_TIMING_MODE == 0U)
    {
        (void)replay;
        record->admitted = (uint8_t)(((record->timing_flags & SYSTEM_FUSION_APPLICATION_EPOCH_VALID) != 0U) && record->physically_valid);
        record->update_result = record->admitted ? (uint8_t)outcome->result : (uint8_t)(16U + record->execution_result);
    }
    else
    {
        record->admitted = (uint8_t)((replay == NAV_ESKF_REPLAY_OK) && record->physically_valid);
        record->update_result = (uint8_t)((replay == NAV_ESKF_REPLAY_OK) ? outcome->result : 16U + replay);
    }
    record->nis = outcome->nis; record->robust_scale = outcome->r_scale;
    memcpy(record->innovation, outcome->innovation, sizeof(record->innovation));
    memcpy(record->effective_variance, outcome->effective_variance, sizeof(record->effective_variance));
    memcpy(record->observation, event->measurement.observation, sizeof(record->observation));
    evidence.receive_us = event->receive_us; evidence.measurement_us = event->measurement_us;
    evidence.evaluation_us = s_state.timestamp_us; evidence.sequence = event->sequence;
    evidence.source = (uint8_t)event->source;
    evidence.nis = outcome->nis;
    evidence.variance_scale = record->quality_scale * record->consistency_scale * outcome->r_scale;
    evidence.physically_valid = record->physically_valid; evidence.attempted = record->admitted;
    evidence.effective_update = (uint8_t)(record->admitted && (outcome->gain_norm > 0.0f) &&
        ((outcome->result == NAV_ESKF_OK) || (outcome->result == NAV_ESKF_SOFT_WEIGHTED)));
    evidence.soft_weighted = (uint8_t)(evidence.variance_scale > 1.0f);
    evidence.reason = record->update_result;
    if (SystemNavigationHealth_Observe(event->measurement.group, &evidence) != SYSTEM_DEVICE_OK)
    { s_log_failures++; }
    Backend_OutcomeSnapshotWrite(record, &evidence, output);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_MeasurementLog(record);
#endif
}

static SystemFusionExecutionResult Backend_LegacyExecutionGet(NavigationEskfReplayResult result)
{
    switch (result)
    {
        case NAV_ESKF_REPLAY_OK: return SYSTEM_FUSION_EXEC_COMPLETE;
        case NAV_ESKF_REPLAY_HISTORY_MISS: return SYSTEM_FUSION_EXEC_HISTORY_MISS;
        case NAV_ESKF_REPLAY_OVERFLOW: return SYSTEM_FUSION_EXEC_CAPACITY;
        case NAV_ESKF_REPLAY_DUPLICATE: return SYSTEM_FUSION_EXEC_DUPLICATE;
        case NAV_ESKF_REPLAY_NUMERIC_ERROR: return SYSTEM_FUSION_EXEC_NUMERIC_ERROR;
        case NAV_ESKF_REPLAY_INVALID:
        default: return SYSTEM_FUSION_EXEC_INVALID;
    }
}
static SystemDeviceResult Backend_CurrentFaultStop(EstimatorOutputSnapshot *output)
{
    s_active = 0U;
    output->initialized = 0U;
    output->mission_running = 0U;
    output->health_flags |= ESTIMATOR_HEALTH_KF_NUMERIC_ERROR;
    SystemNavigationHealth_ImuQualityRecord(0x10U);
    return SYSTEM_DEVICE_VERIFY_FAILED;
}

static void Backend_HorizonStatusLog(uint64_t evaluation_us, NavigationEskfHorizonResult result)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    FlightLogFusionHorizonStatusRecord record = {0};
    record.input_present_timestamp_us = s_horizon.present_us;
    record.primary_timestamp_us = s_horizon.primary.timestamp_us;
    record.output_state_timestamp_us = s_state.timestamp_us;
    record.output_covariance_timestamp_us = s_state.timestamp_us;
    record.operation_sequence = s_operation; record.epoch = s_state.generation;
    record.source_id = s_state.source; record.calibration_generation = s_calibration_generation;
    record.horizon_us = (uint32_t)s_horizon.horizon_us;
    record.work_count = s_horizon.last_work; record.maximum_work = s_horizon.maximum_work;
    record.late_count = s_horizon.late_count; record.capacity_count = s_horizon.capacity_count;
    record.failure_operation_sequence = s_horizon.failure_operation;
    record.failure_operation_valid = s_horizon.failure_operation_valid;
    record.horizon_initialized = s_horizon.initialized;
    record.body_count = s_horizon.body_count; record.event_count = s_horizon.event_count;
    record.completion_count = s_horizon.completion_count;
    record.algorithm_id = 2U; record.algorithm_revision = NAV_ESKF_REVISION;
    record.numerical_revision = NAV_ESKF_NUMERICAL_REVISION_STABLE_RESET;
    record.fusion_timing_mode = SYSTEM_FUSION_TIMING_HORIZON;
    record.phase = (uint8_t)(s_horizon.faulted ? 2U : (s_horizon.warmup ? 0U : 1U));
    record.execution_result = (uint8_t)Backend_HorizonExecutionGet(result);
    Backend_LogResult(LoggerBus_FusionHorizonStatusPush(evaluation_us,&record));
#else
    (void)evaluation_us; (void)result;
#endif
}

static void Backend_HorizonRequest(const NavigationEskfReplayEvent *event,
    BackendMeasurementContext *record)
{
    NavigationEskfHorizonEvent queued = {0};
    SystemNavigationReceiveEvidence evidence = {0};
    SystemDeviceResult received;
    record->operation_sequence = ++s_operation; record->epoch = s_state.generation;
    record->source_id = event->source; record->calibration_generation = s_calibration_generation;
    record->source_sequence = event->sequence; record->group = event->measurement.group;
    record->physically_valid = event->measurement.physically_valid;
    record->receive_timestamp_us = event->receive_us; record->measurement_timestamp_us = event->measurement_us;
    record->evaluation_timestamp_us = Backend_EvaluationTimeGet();
    record->update_result = 255U; record->nis = -1.0f; record->robust_scale = 1.0f;
    memcpy(record->observation,event->measurement.observation,sizeof(record->observation));
    memcpy(record->prepared_variance,event->measurement.variance,sizeof(record->prepared_variance));
    if (record->execution_result == SYSTEM_FUSION_EXEC_COMPLETE)
    {
        evidence.receive_us = event->receive_us; evidence.evaluation_us = record->evaluation_timestamp_us;
        evidence.sequence = event->sequence; evidence.source = (uint8_t)event->source;
        evidence.variance_scale = record->quality_scale*record->consistency_scale;
        evidence.physically_valid = event->measurement.physically_valid;
        evidence.reason = evidence.physically_valid ? 0U : (uint8_t)NAV_ESKF_INVALID_INPUT;
        received = SystemNavigationHealth_ReceiveOnly(event->measurement.group,&evidence);
        if (received == SYSTEM_DEVICE_OK)
        {
            queued.event = *event; queued.sample_us = record->sample_timestamp_us;
            queued.operation_sequence = record->operation_sequence; queued.timing_flags = record->timing_flags;
            queued.quality_scale = record->quality_scale; queued.consistency_scale = record->consistency_scale;
            memcpy(queued.base_variance,record->base_variance,sizeof(queued.base_variance));
            record->execution_result = (uint8_t)Backend_HorizonExecutionGet(NavigationEskfHorizon_Insert(&s_horizon,&queued));
        }
        else
        {
            record->execution_result = SYSTEM_FUSION_EXEC_DISCONTINUITY;
            if (received != SYSTEM_DEVICE_BAD_STATE)
            { s_horizon.faulted = 1U; }
        }
    }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_MeasurementLog(record);
#endif
}

static SystemDeviceResult Backend_HorizonCompletionPublish(const NavigationEskfHorizonEvent *completed,
    EstimatorOutputSnapshot *output)
{
    BackendMeasurementContext record = {0};
    SystemNavigationFusionEvidence evidence = {0};
    const NavigationEskfReplayEvent *event = &completed->event;
    const NavigationEskfOutcome *outcome = &completed->outcome;
    record.sample_timestamp_us = completed->sample_us; record.receive_timestamp_us = event->receive_us;
    record.measurement_timestamp_us = event->measurement_us; record.application_timestamp_us = event->measurement_us;
    record.evaluation_timestamp_us = s_state.timestamp_us; record.operation_sequence = completed->operation_sequence;
    record.epoch = s_state.generation; record.source_id = event->source;
    record.calibration_generation = s_calibration_generation; record.source_sequence = event->sequence;
    record.group = event->measurement.group; record.physically_valid = event->measurement.physically_valid;
    record.phase = 1U; record.admitted = 1U; record.update_result = (uint8_t)outcome->result;
    record.quality_scale = completed->quality_scale; record.consistency_scale = completed->consistency_scale;
    record.nis = outcome->nis; record.robust_scale = outcome->r_scale;
    record.timing_flags = completed->timing_flags | SYSTEM_FUSION_APPLICATION_EPOCH_VALID;
    record.execution_result = SYSTEM_FUSION_EXEC_COMPLETE;
    record.effective_update = (uint8_t)((outcome->gain_norm > 0.0f) &&
        ((outcome->result == NAV_ESKF_OK) || (outcome->result == NAV_ESKF_SOFT_WEIGHTED)));
    memcpy(record.observation,event->measurement.observation,sizeof(record.observation));
    memcpy(record.base_variance,completed->base_variance,sizeof(record.base_variance));
    memcpy(record.prepared_variance,event->measurement.variance,sizeof(record.prepared_variance));
    memcpy(record.innovation,outcome->innovation,sizeof(record.innovation));
    memcpy(record.effective_variance,outcome->effective_variance,sizeof(record.effective_variance));
    evidence.receive_us = event->receive_us; evidence.measurement_us = event->measurement_us;
    evidence.evaluation_us = s_state.timestamp_us; evidence.sequence = event->sequence;
    evidence.source = (uint8_t)event->source; evidence.physically_valid = 1U; evidence.attempted = 1U;
    evidence.effective_update = record.effective_update; evidence.nis = outcome->nis;
    evidence.variance_scale = completed->quality_scale*completed->consistency_scale*outcome->r_scale;
    evidence.soft_weighted = (uint8_t)(evidence.variance_scale > 1.0f); evidence.reason = record.update_result;
    if (SystemNavigationHealth_FusionOnly(record.group,&evidence) != SYSTEM_DEVICE_OK)
    { s_horizon.faulted = 1U; return SYSTEM_DEVICE_VERIFY_FAILED; }
    Backend_OutcomeSnapshotWrite(&record,&evidence,output);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_MeasurementLog(&record);
#endif
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Backend_HorizonCompletionsDrain(EstimatorOutputSnapshot *output)
{
    for (uint16_t index = 0U; index < NAV_ESKF_HORIZON_EVENT_CAPACITY; index++)
    {
        NavigationEskfHorizonEvent completed;
        NavigationEskfHorizonResult result = NavigationEskfHorizon_CompletionPop(&s_horizon,&completed);
        if (result == NAV_ESKF_HORIZON_EMPTY) { return SYSTEM_DEVICE_OK; }
        if ((result != NAV_ESKF_HORIZON_OK) ||
            (Backend_HorizonCompletionPublish(&completed,output) != SYSTEM_DEVICE_OK))
        { return SYSTEM_DEVICE_VERIFY_FAILED; }
    }
    return (s_horizon.completion_count == 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_VERIFY_FAILED;
}

static SystemFusionExecutionResult Backend_CurrentPredict(const NavigationEskfBodyInput *body)
{
    if (s_current_faulted || !s_state.initialized) { return SYSTEM_FUSION_EXEC_NOT_READY; }
    if (SystemCalibration_GenerationGet() != s_calibration_generation)
    { s_current_faulted = 1U; return SYSTEM_FUSION_EXEC_EPOCH_MISMATCH; }
    if ((body->start_us != s_state.timestamp_us) || (body->end_us <= body->start_us) ||
        (s_current_endpoint_valid && ((body->quality_flags & 0x08U) != 0U)))
    { s_current_faulted = 1U; return SYSTEM_FUSION_EXEC_DISCONTINUITY; }
    if (NavigationEskf_Predict(&s_state, &s_work, &s_config, body) != NAV_ESKF_OK)
    { s_current_faulted = 1U; return SYSTEM_FUSION_EXEC_NUMERIC_ERROR; }
    memcpy(s_current_endpoint_rate, body->gyro_radps[1], sizeof(s_current_endpoint_rate));
    s_current_endpoint_valid = 1U;
    return SYSTEM_FUSION_EXEC_COMPLETE;
}

static SystemFusionExecutionResult Backend_CurrentEventValidate(const NavigationEskfReplayEvent *event)
{
    if (s_current_faulted || !s_current_endpoint_valid) { return SYSTEM_FUSION_EXEC_NOT_READY; }
    if ((event->generation != s_state.generation) || (SystemCalibration_GenerationGet() != s_calibration_generation))
    { return SYSTEM_FUSION_EXEC_EPOCH_MISMATCH; }
    if ((event->measurement.group >= 5U) || (event->source >= SYSTEM_FUSION_SOURCE_COUNT) ||
        ((event->measurement.group == 4U) && (event->source != SYSTEM_FUSION_BAROMETER_SOURCE)))
    { return SYSTEM_FUSION_EXEC_INVALID; }
    return SystemFusionTiming_CurrentValidate(event->receive_us, event->receive_us,
        s_state.timestamp_us, s_current_epoch_start_us);
}

static SystemFusionExecutionResult Backend_CurrentPacketAdmit(SystemFusionReceipt *receipt,
    uint32_t sequence, uint64_t receive_us)
{
    SystemFusionExecutionResult result;
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { if (s_horizon.faulted || !s_horizon.body_seen) { return SYSTEM_FUSION_EXEC_NOT_READY; } }
    else if (s_current_faulted || !s_current_endpoint_valid) { return SYSTEM_FUSION_EXEC_NOT_READY; }
    if (SystemCalibration_GenerationGet() != s_calibration_generation)
    { return SYSTEM_FUSION_EXEC_EPOCH_MISMATCH; }
    result = SystemFusionTiming_CurrentValidate(receive_us, receive_us,
        Backend_EvaluationTimeGet(), s_current_epoch_start_us);
    if (result != SYSTEM_FUSION_EXEC_COMPLETE) { return result; }
    result = SystemFusionTiming_ReceiptCheck(receipt, sequence, 0x80U);
    if (result == SYSTEM_FUSION_EXEC_COMPLETE)
    { SystemFusionTiming_ReceiptCommit(receipt, sequence, 0x80U); }
    return result;
}

static SystemFusionExecutionResult Backend_CurrentEventApply(const NavigationEskfReplayEvent *event,
    BackendMeasurementContext *record, NavigationEskfOutcome *outcome)
{
    SystemFusionExecutionResult result;
    SystemFusionReceipt *receipt;
    NavigationEskfResult updated;
    uint8_t group_mask;
    if (record->execution_result != SYSTEM_FUSION_EXEC_COMPLETE)
    { return (SystemFusionExecutionResult)record->execution_result; }
    result = Backend_CurrentEventValidate(event);
    if (result != SYSTEM_FUSION_EXEC_COMPLETE) { return result; }
    receipt = (event->measurement.group == 4U) ? &s_current_baro : &s_current_gnss[event->source];
    group_mask = (uint8_t)(1U << event->measurement.group);
    result = SystemFusionTiming_ReceiptCheck(receipt, event->sequence, group_mask);
    if (result != SYSTEM_FUSION_EXEC_COMPLETE) { return result; }
    SystemFusionTiming_ReceiptCommit(receipt, event->sequence, group_mask);
    result = SystemFusionTiming_CurrentValidate(event->measurement_us, event->receive_us,
        s_state.timestamp_us, s_current_epoch_start_us);
    if (result != SYSTEM_FUSION_EXEC_COMPLETE) { return result; }
    if (event->measurement.physically_valid != 1U) { return SYSTEM_FUSION_EXEC_INVALID; }
    record->application_timestamp_us = s_state.timestamp_us;
    record->timing_flags |= SYSTEM_FUSION_APPLICATION_EPOCH_VALID;
    updated = NavigationEskf_Update(&s_state, &s_work, &s_config, &event->measurement, outcome);
    if ((updated == NAV_ESKF_NUMERIC_ERROR) || (updated == NAV_ESKF_MODEL_MISMATCH))
    { s_current_faulted = 1U; return SYSTEM_FUSION_EXEC_NUMERIC_ERROR; }
    return SYSTEM_FUSION_EXEC_COMPLETE;
}

static void Backend_EventApply(NavigationEskfReplayEvent *event, BackendMeasurementContext *record,
    EstimatorOutputSnapshot *output)
{
    NavigationEskfOutcome outcome;
    NavigationEskfReplayResult result;
    SILVERSTAR_ASSERT_OBJECT(event, NavigationEskfReplayEvent, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(record, BackendMeasurementContext, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    event->generation = s_state.generation;
    if (event->measurement.group < 4U)
    {
        event->measurement.lever_arm_b_m[0] = SYSTEM_ESKF_LEVER_ARM_BODY_X_M;
        event->measurement.lever_arm_b_m[1] = SYSTEM_ESKF_LEVER_ARM_BODY_Y_M;
        event->measurement.lever_arm_b_m[2] = SYSTEM_ESKF_LEVER_ARM_BODY_Z_M;
    }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { Backend_HorizonRequest(event,record); return; }
    if (SYSTEM_FUSION_TIMING_MODE == 1U)
    {
        Backend_AngularRateGet(event->measurement_us, event->measurement.angular_rate_b_radps);
    }
    else
    {
        memcpy(event->measurement.angular_rate_b_radps, s_current_endpoint_rate, sizeof(s_current_endpoint_rate));
    }
    memset(&outcome, 0, sizeof(outcome)); outcome.r_scale = 1.0f;
    s_eskf_replay_timing.sequence++;
    s_eskf_replay_timing.last_start_us = SystemTime_GetMonotonicUs();
    s_eskf_replay_timing.sequence++;
    if (SYSTEM_FUSION_TIMING_MODE == 1U)
    {
        result = NavigationEskfReplay_Insert(&s_history, &s_state, &s_work, &s_config, event, &outcome);
        record->execution_result = (uint8_t)Backend_LegacyExecutionGet(result);
        if ((result == NAV_ESKF_REPLAY_OK) && event->measurement.physically_valid)
        {
            record->application_timestamp_us = event->measurement_us;
            record->timing_flags |= SYSTEM_FUSION_APPLICATION_EPOCH_VALID;
        }
    }
    else
    {
        record->execution_result = (uint8_t)Backend_CurrentEventApply(event, record, &outcome);
        result = (record->execution_result == SYSTEM_FUSION_EXEC_COMPLETE) ? NAV_ESKF_REPLAY_OK : NAV_ESKF_REPLAY_INVALID;
    }
    Backend_ReplayTimingRecord(s_eskf_replay_timing.last_start_us,
        SystemTime_GetMonotonicUs(), event->measurement.group);
    Backend_OutcomePublish(event, record, result, &outcome, output);
}

static float Backend_AccuracyVariance(float reported, float floor)
{
    float sigma = fmaxf(reported, floor);
    return sigma * sigma;
}

static void Backend_GnssGroupApply(const SystemGnssSample *sample, const float position[3],
    uint8_t group, float quality, float consistency, SystemFusionExecutionResult packet_result,
    EstimatorOutputSnapshot *output)
{
    NavigationEskfReplayEvent event;
    BackendMeasurementContext record;
    uint8_t axis, first = (group & 1U) ? 2U : 0U, count = (group & 1U) ? 1U : 2U;
    uint32_t delay = (group < 2U) ? SYSTEM_ESTIMATOR_GNSS_POSITION_MEASUREMENT_DELAY_MS :
        SYSTEM_ESTIMATOR_GNSS_VELOCITY_MEASUREMENT_DELAY_MS;
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(group < 4U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    memset(&event, 0, sizeof(event)); memset(&record, 0, sizeof(record));
    event.receive_us = sample->receive_timestamp_us; event.sequence = sample->sequence;
    event.source = s_gnss_source; event.measurement.group = group;
    event.measurement.physically_valid = (uint8_t)((sample->valid_group_mask & (1U << group)) != 0U);
    record.sample_timestamp_us = sample->sample_timestamp_us;
    record.execution_result = (uint8_t)packet_result;
    record.quality_scale = quality; record.consistency_scale = (group == 0U) ? consistency : 1.0f;
    if (SystemTime_MeasurementTimestampResolve(event.receive_us, sample->sample_timestamp_us,
        sample->measurement_timestamp_trusted, delay, &event.measurement_us) != SYSTEM_MEASUREMENT_TIME_OK)
    { event.measurement.physically_valid = 0U; }
    else { record.timing_flags = SYSTEM_FUSION_SOURCE_RESOLVED | (sample->measurement_timestamp_trusted ? SYSTEM_FUSION_TRUSTED_SOURCE : SYSTEM_FUSION_DELAY_FALLBACK); }
    for (axis = 0U; axis < count; axis++)
    {
        float variance = (group < 2U) ? Backend_AccuracyVariance(
            (group == 0U) ? sample->horizontal_accuracy_m : sample->vertical_accuracy_m,
            (group == 0U) ? SYSTEM_ESKF_GNSS_POSITION_STD_HORIZONTAL : SYSTEM_ESKF_GNSS_POSITION_STD_VERTICAL) :
            fmaxf(sample->velocity_variance_m2ps2[first + axis],
                  SYSTEM_ESKF_GNSS_VELOCITY_STD * SYSTEM_ESKF_GNSS_VELOCITY_STD);
        record.base_variance[axis] = variance;
        event.measurement.observation[axis] = (group < 2U) ? position[first + axis] : sample->velocity_enu_mps[first + axis];
        event.measurement.variance[axis] = variance * quality * record.consistency_scale;
    }
    Backend_EventApply(&event, &record, output);
}

static void Backend_NavigationQualityLog(const SystemGnssSample *sample, uint64_t evaluation_us)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    FlightLogNavigationQualityRecord record = {0};
    SystemNavigationGroupHealth health;
    SystemGnssTime native;
    uint8_t group, source = 0U;
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(&record, FlightLogNavigationQualityRecord, SILVERSTAR_ASSERT_MODULE_APP);
    record.receive_us = sample->receive_timestamp_us; record.evaluation_us = evaluation_us;
    if ((SystemGnss_TimeGet(&native) == SYSTEM_DEVICE_OK) && (native.sequence == sample->sequence))
    { record.native_epoch_us = s_native_week_us + (uint64_t)native.time_of_week_ms * 1000ULL; }
    record.native_sequence = sample->sequence;
    if (SystemSourceSelector_GnssActiveInstanceGet(&source) == SYSTEM_DEVICE_OK) { record.source_id = source; }
    record.calibration_generation = s_calibration_generation;
    record.quality_revision = NAV_QUALITY_REVISION;
    record.physical_mask = sample->physical_valid_group_mask;
    record.quality_degraded_mask = sample->quality_degraded_group_mask;
    record.numsv = sample->satellite_count;
    record.numsv_valid = (uint8_t)((sample->valid_fields & SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U);
    record.window_start_us = s_eskf_window.completed_start_us; record.window_end_us = s_eskf_window.completed_us;
    record.covered_us = s_eskf_window.completed_covered_us; record.window_index = s_eskf_window.completed_window_index;
    record.position_epoch_count = s_eskf_window.completed_position_epochs;
    record.velocity_epoch_count = s_eskf_window.completed_velocity_epochs;
    record.evidence_age_us = (record.native_epoch_us >= s_eskf_window.completed_us) ?
        record.native_epoch_us - s_eskf_window.completed_us : UINT64_MAX;
    record.evidence_valid = (uint8_t)(s_eskf_window.evidence_valid && (record.native_epoch_us != 0U) &&
        (record.evidence_age_us <= 6000000ULL));
    record.window_reason = record.evidence_valid ? 1U : (s_eskf_window.evidence_valid ? 4U : 0U);
    record.variance_scale = record.evidence_valid ? s_eskf_window.variance_scale : 1.0f;
    memcpy(record.closure_en_m, s_eskf_window.closure_en, sizeof(record.closure_en_m));
    record.closure_norm_m = s_eskf_window.closure_norm_m;
    for (group = 0U; group < 4U; group++)
    {
        if ((SystemNavigationHealth_GroupGet(group, evaluation_us, &health) == SYSTEM_DEVICE_OK) &&
            (health.last_sequence == sample->sequence) && (health.last_receive_us == sample->receive_timestamp_us))
        {
            if (health.last_update_attempt_us == evaluation_us) { record.admitted_mask |= (uint8_t)(1U << group); }
            if (health.has_success && (health.last_successful_fusion_us == evaluation_us))
            { record.accepted_mask |= (uint8_t)(1U << group); }
        }
    }
    record.health = (uint8_t)SystemNavigationHealth_OverallGet(evaluation_us,
        SYSTEM_FUSION_REQUIRED_HEALTH_MASK, 0U);
    record.nav_output_valid = (uint8_t)(record.health != SYSTEM_NAVIGATION_HEALTH_INVALID);
    if (LoggerBus_NavigationQualityPush(evaluation_us, &record) != LOGGER_BUS_RESULT_OK)
    { s_log_failures++; }
#else
    (void)sample; (void)evaluation_us;
#endif
}

/* Select the live producer independently of whether it has delivered a packet.
 * Use this captured identity for the whole receive transaction. */
static SystemDeviceResult Backend_HorizonGnssSourceSelect(uint8_t *source)
{
    SystemDeviceResult selected = SystemSourceSelector_GnssActiveInstanceGet(source);
    for (uint8_t group = 0U; group < 4U; group++)
    {
        SystemDeviceResult health = (selected == SYSTEM_DEVICE_OK) ?
            SystemNavigationHealth_SourceSelect(group,*source,Backend_EvaluationTimeGet()) :
            SystemNavigationHealth_SourceUnavailable(group,Backend_EvaluationTimeGet());
        if (health != SYSTEM_DEVICE_OK) { s_horizon.faulted = 1U; return SYSTEM_DEVICE_VERIFY_FAILED; }
    }
    return selected;
}

static void Backend_GnssUpdate(EstimatorOutputSnapshot *output)
{
    SystemGnssSample sample;
    float position[3], quality, consistency;
    uint8_t group, source;
    SystemFusionExecutionResult packet_result = SYSTEM_FUSION_EXEC_COMPLETE;
    SILVERSTAR_ASSERT_OBJECT(output, EstimatorOutputSnapshot, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(s_state.initialized != 0U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) &&
        (Backend_HorizonGnssSourceSelect(&source) != SYSTEM_DEVICE_OK)) { return; }
    /* A mission without a preflight frame cannot adopt a later moving fix. */
    if (s_frame.valid == 0U) { return; }
    if (((SYSTEM_FUSION_TIMING_MODE != SYSTEM_FUSION_TIMING_HORIZON) &&
         (SystemSourceSelector_GnssActiveInstanceGet(&source) != SYSTEM_DEVICE_OK)) ||
        (SystemGnss_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK) ||
        (sample.receive_timestamp_us > Backend_EvaluationTimeGet()) ||
        (s_gnss_seen && (source == s_gnss_source) &&
         (sample.sequence == s_gnss_sequence))) { return; }
    if (SYSTEM_FUSION_TIMING_MODE != SYSTEM_FUSION_TIMING_LEGACY_REPLAY)
    {
        packet_result = (source < SYSTEM_FUSION_SOURCE_COUNT) ?
            Backend_CurrentPacketAdmit(&s_current_gnss[source], sample.sequence, sample.receive_timestamp_us) :
            SYSTEM_FUSION_EXEC_INVALID;
    }
    if (source != s_gnss_source)
    {
        s_gnss_source = source; s_native_week_us = 0U; s_native_tow_ms = 0U;
        (void)NavigationWindow_Reset(&s_eskf_window);
    }
    s_gnss_seen = 1U; s_gnss_sequence = sample.sequence;
    if (SystemGnssQuality_Evaluate(&sample, Backend_EvaluationTimeGet()) != SYSTEM_DEVICE_OK)
    { sample.valid_group_mask = 0U; sample.physical_valid_group_mask = 0U; }
    output->last_gnss_timestamp_us = sample.receive_timestamp_us;
    output->last_gnss_sequence = sample.sequence;
    output->gnss_velocity_valid_mask = sample.velocity_valid_mask;
    output->velocity_update_dimension = (sample.velocity_valid_mask == 7U) ? 3U :
        ((sample.velocity_valid_mask & 3U) == 3U) ? 2U : 0U;
    memcpy(output->gnss_velocity_enu_mps, sample.velocity_enu_mps, sizeof(output->gnss_velocity_enu_mps));
    if (GeoLocalFrame_ToEnu(&s_frame,
        (sample.valid_group_mask & 1U) ? sample.latitude_e7 : s_frame.origin_lat_e7,
        (sample.valid_group_mask & 1U) ? sample.longitude_e7 : s_frame.origin_lon_e7,
        (sample.valid_group_mask & 2U) ? sample.ellipsoid_height_mm : s_frame.origin_height_mm, position) == 0U)
    { memset(position, 0, sizeof(position)); sample.valid_group_mask &= (uint8_t)~3U; }
    memcpy(output->gnss_position_enu_m, position, sizeof(position));
    quality = NavigationQuality_SatelliteVarianceScale(sample.satellite_count,
        (uint8_t)((sample.valid_fields & SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U));
    consistency = (packet_result == SYSTEM_FUSION_EXEC_COMPLETE) ? Backend_ConsistencyGet(&sample, position) : 1.0f;
    for (group = 0U; group < 4U; group++)
    { Backend_GnssGroupApply(&sample, position, group, quality, consistency, packet_result, output); }
    Backend_NavigationQualityLog(&sample, Backend_EvaluationTimeGet());
}

static uint8_t Backend_BarometerReceiptGet(EstimatorPressureSnapshot *sample)
{
    EstimatorBusResult result;
    if (SYSTEM_FUSION_TIMING_MODE != SYSTEM_FUSION_TIMING_HORIZON)
    { return EstimatorBus_PressureGetLatest(sample); }
    result = EstimatorBus_PressureReceiptGetLatest(sample);
    if (result == ESTIMATOR_BUS_RESULT_EMPTY) { return 0U; }
    if (result != ESTIMATOR_BUS_RESULT_OK) { s_horizon.faulted = 1U; return 0U; }
    return 1U;
}

static void Backend_BarometerUpdate(EstimatorOutputSnapshot *output)
{
    EstimatorPressureSnapshot sample;
    NavigationEskfReplayEvent event;
    BackendMeasurementContext record;
    if ((SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) &&
        (SystemNavigationHealth_SourceSelect(4U,SYSTEM_FUSION_BAROMETER_SOURCE,Backend_EvaluationTimeGet()) != SYSTEM_DEVICE_OK))
    { s_horizon.faulted = 1U; return; }
    if ((s_baro_origin_valid == 0U) ||
        (Backend_BarometerReceiptGet(&sample) == 0U) ||
        (sample.receive_timestamp_us > Backend_EvaluationTimeGet()) ||
        (s_baro_seen && (sample.sequence == s_baro_sequence))) { return; }
    SILVERSTAR_ASSERT(sample.valid <= 1U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(sample.healthy <= 1U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    s_baro_seen = 1U; s_baro_sequence = sample.sequence;
    output->last_baro_timestamp_us = sample.receive_timestamp_us;
    output->last_baro_sequence = sample.sequence;
    output->baro_relative_altitude_m = sample.altitude_m - s_baro_origin;
    memset(&event, 0, sizeof(event)); memset(&record, 0, sizeof(record));
    event.receive_us = sample.receive_timestamp_us; event.sequence = sample.sequence;
    event.source = (SYSTEM_FUSION_TIMING_MODE != SYSTEM_FUSION_TIMING_LEGACY_REPLAY) ? SYSTEM_FUSION_BAROMETER_SOURCE : s_state.source;
    event.measurement.group = 4U;
    event.measurement.physically_valid = (uint8_t)(sample.valid && sample.healthy &&
        (Backend_EvaluationTimeGet() - sample.receive_timestamp_us <= SYSTEM_ESTIMATOR_MEASUREMENT_MAX_AGE_US));
    event.measurement.observation[0] = sample.altitude_m - s_baro_origin;
    event.measurement.variance[0] = fmaxf(sample.variance_m2,
        SYSTEM_ESKF_BARO_STD_M * SYSTEM_ESKF_BARO_STD_M);
    record.sample_timestamp_us = sample.timestamp_us;
    if (SYSTEM_FUSION_TIMING_MODE != SYSTEM_FUSION_TIMING_LEGACY_REPLAY)
    {
        record.execution_result = (uint8_t)Backend_CurrentPacketAdmit(&s_current_baro,
            sample.sequence, sample.receive_timestamp_us);
    }
    record.base_variance[0] = event.measurement.variance[0];
    record.quality_scale = 1.0f; record.consistency_scale = 1.0f;
    if (SystemTime_MeasurementTimestampResolve(event.receive_us, sample.timestamp_us,
        sample.measurement_timestamp_trusted, SYSTEM_ESTIMATOR_BARO_MEASUREMENT_DELAY_MS,
        &event.measurement_us) != SYSTEM_MEASUREMENT_TIME_OK)
    { event.measurement.physically_valid = 0U; }
    else { record.timing_flags = SYSTEM_FUSION_SOURCE_RESOLVED | (sample.measurement_timestamp_trusted ? SYSTEM_FUSION_TRUSTED_SOURCE : SYSTEM_FUSION_DELAY_FALLBACK); }
    Backend_EventApply(&event, &record, output);
}

static SystemDeviceResult Backend_HorizonCycle(const NavigationEskfBodyInput *body,
    EstimatorOutputSnapshot *output, uint64_t previous_output_us)
{
    NavigationEskfHorizonResult result;
    uint8_t source;
    if ((SystemCalibration_GenerationGet() != s_calibration_generation) ||
        (SystemSourceSelector_ImuActiveInstanceGet(&source) != SYSTEM_DEVICE_OK) || (source != s_state.source))
    { s_horizon.faulted = 1U; result = NAV_ESKF_HORIZON_EPOCH_MISMATCH; }
    else { result = NavigationEskfHorizon_BodyReceive(&s_horizon,body); }
    if (result == NAV_ESKF_HORIZON_OK)
    {
        Backend_GnssUpdate(output);
        if (!s_horizon.faulted) { Backend_BarometerUpdate(output); }
        result = s_horizon.faulted ? NAV_ESKF_HORIZON_NOT_READY :
            NavigationEskfHorizon_Advance(&s_horizon,&s_state,&s_work,&s_config);
    }
    if ((result != NAV_ESKF_HORIZON_OK) && (result != NAV_ESKF_HORIZON_WARMUP))
    {
        /* First-interval epoch setup is provisional until prediction commits.
         * Restore its timestamp together with the unchanged nominal/full P. */
        if (s_state.timestamp_us == body->start_us) { s_state.timestamp_us = previous_output_us; }
        s_horizon.faulted = 1U;
        if (result == NAV_ESKF_HORIZON_MODEL_MISMATCH) { SystemNavigationHealth_ModelMismatchRecord(); }
        Backend_HorizonStatusLog(body->end_us,result);
        return Backend_CurrentFaultStop(output);
    }
    memcpy(output->acceleration_enu_mps2,s_horizon.output_acceleration,sizeof(s_horizon.output_acceleration));
    if (Backend_HorizonCompletionsDrain(output) != SYSTEM_DEVICE_OK)
    {
        s_horizon.faulted = 1U; Backend_HorizonStatusLog(body->end_us,NAV_ESKF_HORIZON_NUMERIC_ERROR);
        return Backend_CurrentFaultStop(output);
    }
    if (SystemNavigationHealth_OverallGet(s_state.timestamp_us,
        SYSTEM_FUSION_REQUIRED_HEALTH_MASK,s_imu_quality_flags) == SYSTEM_NAVIGATION_HEALTH_INVALID)
    {
        s_horizon.faulted = 1U; Backend_HorizonStatusLog(body->end_us,NAV_ESKF_HORIZON_NOT_READY);
        return Backend_CurrentFaultStop(output);
    }
    output->predict_count++; output->update_sequence++;
    if (SystemNavigationBackend_SnapshotGet(output) != SYSTEM_DEVICE_OK)
    {
        s_horizon.faulted = 1U; Backend_HorizonStatusLog(body->end_us,NAV_ESKF_HORIZON_NOT_READY);
        return Backend_CurrentFaultStop(output);
    }
    Backend_HorizonStatusLog(body->end_us,result);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_StateLog(0U);
#endif
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemNavigationBackend_SnapshotGet(EstimatorOutputSnapshot *output)
{
    uint32_t row, column;
    if (output == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (!s_state.initialized) { return SYSTEM_DEVICE_NOT_READY; }
    if ((SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) && s_horizon.faulted)
    { return SYSTEM_DEVICE_NOT_READY; }
    if (SYSTEM_FUSION_TIMING_MODE == 0U)
    {
        if (s_current_faulted != 0U) { return SYSTEM_DEVICE_NOT_READY; }
    }
    SILVERSTAR_ASSERT_OBJECT(output, EstimatorOutputSnapshot, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    output->timestamp_us = s_state.timestamp_us;
    output->initialized = s_state.initialized; output->mission_running = s_active;
    output->gnss_origin_valid = s_frame.valid;
    output->baro_origin_valid = s_baro_origin_valid;
    if (!s_frame.valid) { output->health_flags |= ESTIMATOR_HEALTH_GNSS_ORIGIN_UNAVAILABLE; }
    if (!s_baro_origin_valid)
    {
        output->health_flags |= ESTIMATOR_HEALTH_BARO_ORIGIN_UNAVAILABLE;
        output->baro_relative_altitude_m = NAN;
    }
    else { output->health_flags &= ~ESTIMATOR_HEALTH_BARO_ORIGIN_UNAVAILABLE; }
    memcpy(output->position_enu_m, s_state.position, sizeof(s_state.position));
    memcpy(output->velocity_enu_mps, s_state.velocity, sizeof(s_state.velocity));
    memcpy(output->q_nb, s_state.quaternion, sizeof(s_state.quaternion));
    for (row = 0U; row < 6U; row++)
    {
        output->covariance_diagonal[row] = s_state.covariance[row][row];
        for (column = 0U; column < 6U; column++)
        { output->covariance[row][column] = s_state.covariance[row][column]; }
    }
    if (SystemNavigationHealth_DegradedGet(s_state.timestamp_us) ||
        ((SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) && s_horizon.warmup))
    { output->health_flags |= ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    else { output->health_flags &= ~ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    if (s_log_failures != 0U) { output->health_flags |= ESTIMATOR_HEALTH_LOG_EVENT_FAILED; }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Backend_PredictionEpochStart(const NavigationEskfBodyInput *body)
{
    SILVERSTAR_ASSERT_OBJECT(body, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT(s_state.initialized != 0U, SILVERSTAR_ASSERT_MODULE_ALGORITHM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_started != 0U) { return SYSTEM_DEVICE_OK; }
    s_state.timestamp_us = body->start_us;
    if (SYSTEM_FUSION_TIMING_MODE == 1U)
    {
        if (NavigationEskfReplay_Reset(&s_history, &s_state, s_body_history) != NAV_ESKF_REPLAY_OK)
        { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    }
    else
    {
        s_current_epoch_start_us = body->start_us;
        if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
        {
            if (NavigationEskfHorizon_Reset(&s_horizon,&s_state,&s_work,&s_config,
                (uint64_t)SYSTEM_FUSION_HORIZON_MS*1000ULL) != NAV_ESKF_HORIZON_OK)
            { return SYSTEM_DEVICE_VERIFY_FAILED; }
        }
    }
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { SystemNavigationHealth_DelayedReset(body->start_us); }
    else { SystemNavigationHealth_EpochSet(body->start_us); }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_StateLog(1U);
#endif
    s_started = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Backend_PredictionInputBuild(const SystemInertialIncrement *input,
    NavigationEskfBodyInput *body)
{
    uint64_t duration;
    SILVERSTAR_ASSERT_OBJECT(input, SystemInertialIncrement, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(body, NavigationEskfBodyInput, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    duration = (uint64_t)llroundf(input->dt_s * 1000000.0f);
    if (input->timestamp_us < duration) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    memset(body, 0, sizeof(*body));
    body->start_us = input->timestamp_us - duration;
    body->end_us = input->timestamp_us;
    body->quality_flags = input->quality_flags;
    s_imu_quality_flags = body->quality_flags;
    body->dt_s = input->dt_s;
    body->source = s_state.source; body->generation = s_state.generation;
    memcpy(body->gyro_radps, input->body_gyro_radps, sizeof(body->gyro_radps));
    memcpy(body->accel_mps2, input->body_accel_mps2, sizeof(body->accel_mps2));
    return Backend_PredictionEpochStart(body);
}

static SystemDeviceResult Backend_PresentOrReplayCycle(const NavigationEskfBodyInput *body,
    EstimatorOutputSnapshot *output, uint64_t previous_timestamp_us)
{
    float previous_velocity[3];
    uint8_t axis;
    memcpy(previous_velocity,s_state.velocity,sizeof(previous_velocity));
    if ((SYSTEM_FUSION_TIMING_MODE == 1U) ?
        (NavigationEskfReplay_Predict(&s_history,&s_state,&s_work,&s_config,body) != NAV_ESKF_REPLAY_OK) :
        (Backend_CurrentPredict(body) != SYSTEM_FUSION_EXEC_COMPLETE))
    {
        if (SYSTEM_FUSION_TIMING_MODE == 0U)
        {
            /* Initial epoch setup cannot partly commit a failed numerical state. */
            s_state.timestamp_us = previous_timestamp_us;
            return Backend_CurrentFaultStop(output);
        }
        SystemNavigationHealth_ImuQualityRecord(0x10U);
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    for (axis = 0U; axis < 3U; axis++)
    { output->acceleration_enu_mps2[axis] = (s_state.velocity[axis]-previous_velocity[axis])/body->dt_s; }
    Backend_GnssUpdate(output); Backend_BarometerUpdate(output);
    if ((SYSTEM_FUSION_TIMING_MODE == 0U) && (s_current_faulted != 0U))
    { return Backend_CurrentFaultStop(output); }
    output->predict_count++; output->update_sequence++;
    if (SystemNavigationBackend_SnapshotGet(output) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_INTERNAL_ERROR; }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_StateLog(0U);
#endif
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemNavigationBackend_Predict(
    const SystemInertialIncrement *input, EstimatorOutputSnapshot *output)
{
    NavigationEskfBodyInput body;
    SystemDeviceResult prepared;
    const uint64_t previous_timestamp_us = s_state.timestamp_us;
    if ((input == NULL) || (output == NULL) || !isfinite(input->dt_s) ||
        (input->dt_s <= 0.0f) || (input->dt_s > NAV_ESKF_MAX_DT_S))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemInertialIncrement, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(output, EstimatorOutputSnapshot, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    if ((SYSTEM_FUSION_TIMING_MODE == 0U) && (s_current_faulted != 0U))
    { return Backend_CurrentFaultStop(output); }
    if ((SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) && s_horizon.faulted)
    { return Backend_CurrentFaultStop(output); }
    if (!s_active || !s_state.initialized) { return SYSTEM_DEVICE_NOT_READY; }
    prepared = Backend_PredictionInputBuild(input, &body);
    if (prepared != SYSTEM_DEVICE_OK)
    {
        if ((SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON) &&
            (prepared != SYSTEM_DEVICE_INVALID_ARGUMENT))
        {
            s_state.timestamp_us = previous_timestamp_us; s_horizon.faulted = 1U;
            Backend_HorizonStatusLog(input->timestamp_us,NAV_ESKF_HORIZON_NUMERIC_ERROR);
            return Backend_CurrentFaultStop(output);
        }
        return prepared;
    }
    output->measurement_attempt_mask = 0U;
    output->position_update_result = SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    output->velocity_update_result = SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    output->baro_update_result = SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    SystemNavigationHealth_ImuQualityRecord(body.quality_flags);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Backend_BodyLog(&body, input->sequence);
#endif
    if (SYSTEM_FUSION_TIMING_MODE == SYSTEM_FUSION_TIMING_HORIZON)
    { return Backend_HorizonCycle(&body,output,previous_timestamp_us); }
    return Backend_PresentOrReplayCycle(&body,output,previous_timestamp_us);
}

void SystemNavigationBackend_BodyInputFill(SystemInertialIncrement *input,
    const float *gyro_pair, const float *accel_pair, uint32_t quality_flags)
{
    SILVERSTAR_ASSERT_OBJECT(input, SystemInertialIncrement, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(gyro_pair, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    SILVERSTAR_ASSERT_OBJECT(accel_pair, float, SILVERSTAR_ASSERT_MODULE_ALGORITHM);
    memcpy(input->body_gyro_radps, gyro_pair, sizeof(input->body_gyro_radps));
    memcpy(input->body_accel_mps2, accel_pair, sizeof(input->body_accel_mps2));
    input->quality_flags = quality_flags;
}
