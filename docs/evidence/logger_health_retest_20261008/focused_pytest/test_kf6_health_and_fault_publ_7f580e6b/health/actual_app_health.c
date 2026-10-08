#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "test_common.h"
#include "estimator_task.h"
#include "estimator_bus.h"
#include "imu_sample_bus.h"
#include "logger_bus.h"
#include "estimator_barometer_pending.h"
#include "geodesy_local.h"
#include "navigation_kf_replay.h"
#include "ins_mechanization.h"
#include "attitude_frame.h"
#include "system_lifecycle.h"
#include "system_user_config.h"
#include "system_navigation_health.h"
#include "system_estimator_profile.h"
#include "system_estimator_diagnostics.h"
#include "system_gnss_if.h"
#include "platform_critical.h"
#include "silverstar_assert.h"
#define ESTIMATOR_GNSS_ORIGIN_WINDOW_SIZE SYSTEM_BUILD_GNSS_ORIGIN_STORAGE_SAMPLES
#define ESTIMATOR_BARO_ORIGIN_WINDOW_SIZE SYSTEM_ESTIMATOR_BARO_ORIGIN_WINDOW_SAMPLES
typedef struct
{
    uint64_t receive_timestamp_us;
    int32_t latitude_e7;
    int32_t longitude_e7;
    int32_t ellipsoid_height_mm;
    float horizontal_accuracy_m;
    float vertical_accuracy_m;
    float velocity_enu_mps[3];
    float velocity_variance_m2ps2[3];
    uint8_t velocity_valid_mask;
} EstimatorGnssOriginSample;
typedef struct
{
    uint64_t timestamp_us;
    float altitude_m;
    float pressure_pa;
    uint32_t supported_fields;
    uint32_t valid_fields;
} EstimatorBarometerOriginSample;
typedef struct
{
    EstimatorGnssOriginSample samples[ESTIMATOR_GNSS_ORIGIN_WINDOW_SIZE];
    SystemGnssSample latest;
    float enu_m[ESTIMATOR_GNSS_ORIGIN_WINDOW_SIZE][3];
    uint16_t head;
    uint16_t count;
    uint32_t last_sequence;
    uint8_t ready_event_sent;
} EstimatorGnssOriginWindow;
typedef struct
{
    EstimatorBarometerOriginSample samples[ESTIMATOR_BARO_ORIGIN_WINDOW_SIZE];
    uint16_t head;
    uint16_t count;
    uint32_t last_sequence;
    uint8_t ready_event_sent;
} EstimatorBarometerOriginWindow;
typedef struct
{
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    NavigationKfContext kf;
#endif
    GeoLocalFrame gnss_frame;
    SystemGnssSample frozen_gnss;
    float frozen_baro_altitude_m;
    float frozen_baro_pressure_pa;
    float gnss_origin_position_std_m[3];
    float initial_velocity_std_mps[3];
    float baro_origin_std_m;
    float actual_p0_diagonal[6];
    float q_nb[4];
    EstimatorGnssOriginWindow gnss_window;
    EstimatorBarometerOriginWindow baro_window;
    SystemEstimatorGnssDiagnostics gnss_diagnostics;
    SystemKfDiagnostics kf_diagnostics;
    SystemEstimatorBaroDiagnostics baro_diagnostics;
    EstimatorBarometerPendingContext pending_barometer;
    uint32_t last_gnss_sequence;
    uint32_t last_baro_sequence;
    uint32_t output_sequence;
    uint32_t operation_sequence;
    uint32_t logged_reanchor_count[4];
    uint32_t logged_inflation_count[4];
    uint8_t logged_lifecycle_state;
    uint8_t last_gnss_source;
    uint32_t logged_replay_epoch;
    uint16_t gnss_origin_sample_count;
    uint16_t baro_origin_sample_count;
    uint8_t gnss_origin_valid;
    uint8_t gnss_fusion_enabled;
    uint8_t baro_origin_valid;
    uint8_t origin_collection_frozen;
    uint8_t initialized;
    uint8_t mission_running;
} EstimatorRuntime;
static EstimatorRuntime s_estimator;
static EstimatorOutputSnapshot s_snapshot, s_published_snapshot;
static NavigationReplayContext s_replay;
static NavigationReplayStorage s_replay_storage;
static uint32_t s_replay_epoch;
static EstimatorPreparationSnapshot s_preparation;
static uint32_t s_bus_overflow;
static uint8_t s_measurement_fault;
static void Estimator_DiagnosticsPublish(uint64_t time) { (void)time; }
static void Estimator_LogPush(uint64_t time) { (void)time; }
static void Estimator_BarometerDiagnosticsPublish(void) { }
void EstimatorBus_StatsGet(EstimatorBusStats *stats) { memset(stats,0,sizeof(*stats)); stats->prediction_overflow_count=s_bus_overflow; }
void ImuSampleBus_StatsGet(ImuSampleBusStats *stats) { memset(stats,0,sizeof(*stats)); }
uint32_t LoggerBus_OverflowCountGet(void) { return 0U; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_FLIGHT; }
static void Estimator_PredictionLogPush(const SystemInertialIncrement *p, uint32_t op, NavigationReplayResult result, uint8_t attitude) { (void)p;(void)op;(void)result;(void)attitude; }
static void Estimator_GnssUpdate(uint64_t time) {
 if(s_measurement_fault) {
  const float delta[3]={0};
  (void)NavigationReplay_Predict(&s_replay,&s_estimator.kf,time+1U,delta,0.005f);
 }
}
static void Estimator_BarometerUpdate(uint64_t time) { (void)time; }
#include "system_lifecycle.h"

static PlatformCriticalState EstimatorTask_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void EstimatorTask_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

static void EstimatorTask_SnapshotCommit(void)
{
    uint32_t primask = EstimatorTask_IrqLock();

    s_published_snapshot = s_snapshot;
    EstimatorTask_IrqUnlock(primask);
}

static uint32_t Estimator_OperationNext(void)
{
    SILVERSTAR_ASSERT(s_estimator.operation_sequence < UINT32_MAX,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    return ++s_estimator.operation_sequence;
}

static uint32_t Estimator_CoreHealthFlagsMap(uint32_t core_flags, uint8_t faulted)
{
    SILVERSTAR_ASSERT((core_flags & ~(NAV_KF_HEALTH_INVALID_INPUT |
        NAV_KF_HEALTH_MATRIX_NOT_SPD | NAV_KF_HEALTH_NUMERIC_ERROR |
        NAV_KF_HEALTH_COVARIANCE_RECOVERED)) == 0U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(faulted <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    return (faulted != 0U) ? ESTIMATOR_HEALTH_KF_NUMERIC_ERROR : ESTIMATOR_HEALTH_NONE;
}

static void Estimator_FaultSnapshotPublish(void)
{
    PlatformCriticalState state = EstimatorTask_IrqLock();
    uint32_t health = s_snapshot.health_flags | ESTIMATOR_HEALTH_KF_NUMERIC_ERROR;

    SILVERSTAR_ASSERT(s_published_snapshot.initialized <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_published_snapshot.mission_running <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    /* Restore the last published state, never a partially updated measurement
     * or a new successful timestamp/sequence. All readers see invalid at once. */
    s_snapshot = s_published_snapshot;
    s_snapshot.health_flags |= health;
    s_snapshot.initialized = 0U;
    s_published_snapshot = s_snapshot;
    EstimatorTask_IrqUnlock(state);
}

static uint8_t Estimator_ReplayFaultStop(void)
{
    SILVERSTAR_ASSERT(s_replay.faulted <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_replay.faulted == 0U) { return 0U; }
    Estimator_FaultSnapshotPublish();
    return 1U;
}

static void Estimator_SnapshotPublish(uint64_t timestamp_us)
{
    EstimatorBusStats bus_stats;
    uint8_t row;

    if (Estimator_ReplayFaultStop() != 0U) { return; }
    SILVERSTAR_ASSERT(s_estimator.output_sequence < UINT32_MAX,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    EstimatorBus_StatsGet(&bus_stats);
    s_snapshot.timestamp_us = timestamp_us;
    s_snapshot.update_sequence = ++s_estimator.output_sequence;
    memcpy(s_snapshot.position_enu_m, s_estimator.kf.state,
           sizeof(s_snapshot.position_enu_m));
    memcpy(s_snapshot.velocity_enu_mps, &s_estimator.kf.state[3],
           sizeof(s_snapshot.velocity_enu_mps));
    memcpy(s_snapshot.q_nb, s_estimator.q_nb, sizeof(s_snapshot.q_nb));
    memcpy(s_snapshot.covariance, s_estimator.kf.covariance,
           sizeof(s_snapshot.covariance));
    for (row = 0U; row < 6U; row++)
    {
        s_snapshot.covariance_diagonal[row] =
            s_estimator.kf.covariance[row][row];
    }
    SILVERSTAR_ASSERT(row == 6U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_LOOP_BOUND);
    memcpy(s_snapshot.process_accel_std_mps2,
           s_estimator.kf.process_accel_std_mps2,
           sizeof(s_snapshot.process_accel_std_mps2));
    s_snapshot.last_position_nis = s_estimator.kf.last_position_nis;
    s_snapshot.last_velocity_nis = s_estimator.kf.last_velocity_nis;
    s_snapshot.last_baro_nis = s_estimator.kf.last_baro_nis;
    s_snapshot.predict_count = s_estimator.kf.predict_count;
    s_snapshot.prediction_queue_overflow_count =
        bus_stats.prediction_overflow_count;
    s_snapshot.health_flags |= Estimator_CoreHealthFlagsMap(
        s_estimator.kf.health_flags, s_replay.faulted);
    s_snapshot.initialized = s_estimator.initialized;
    s_snapshot.mission_running = s_estimator.mission_running;
    s_snapshot.gnss_origin_valid = s_estimator.gnss_origin_valid;
    s_snapshot.baro_origin_valid = s_estimator.baro_origin_valid;
    EstimatorTask_SnapshotCommit();
    Estimator_DiagnosticsPublish(timestamp_us);
}

static void Estimator_AccelerationPublish(const float delta_velocity[3], float dt_s)
{
    uint8_t axis;

    if ((delta_velocity == NULL) || (dt_s <= 0.0f)) { return; }
    SILVERSTAR_ASSERT_OBJECT(delta_velocity, float, SILVERSTAR_ASSERT_MODULE_APP);
    for (axis = 0U; axis < 3U; axis++)
    {
        s_snapshot.acceleration_enu_mps2[axis] = delta_velocity[axis] / dt_s;
    }
}

static NavigationReplayResult Estimator_PredictionApply(
    const SystemInertialIncrement *prediction, const float delta_velocity[3])
{
    uint32_t operation_sequence = Estimator_OperationNext();
    NavigationReplayResult result = NavigationReplay_Predict(
        &s_replay, &s_estimator.kf, prediction->timestamp_us,
        delta_velocity, prediction->dt_s);
    (void)operation_sequence;
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Estimator_PredictionLogPush(prediction, operation_sequence, result, 1U);
#endif
    return result;
}

static uint8_t Estimator_KfPredictionApply(
    const SystemInertialIncrement *prediction, float delta_velocity_enu_mps[3])
{
    float q_start[4];

    SILVERSTAR_ASSERT_OBJECT(prediction, SystemInertialIncrement,
                             SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(delta_velocity_enu_mps != NULL,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    memcpy(q_start, s_estimator.q_nb, sizeof(q_start));
    Ins_TransformDeltaVelocityToNavigation(
        q_start, prediction->delta_velocity_b_sculling_corrected,
        prediction->dt_s, SYSTEM_KF_GRAVITY_MPS2, delta_velocity_enu_mps);
    if (Attitude_PropagateQuaternionBodyIncrement(
            q_start, prediction->delta_theta_b_corrected,
            s_estimator.q_nb) == 0U)
    {
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        Estimator_PredictionLogPush(prediction, Estimator_OperationNext(), NAV_REPLAY_INVALID, 0U);
#endif
        Estimator_FaultSnapshotPublish();
        return 0U;
    }
    if (Estimator_PredictionApply(prediction, delta_velocity_enu_mps) != NAV_REPLAY_OK)
    {
        /* Ordinary invalid input stays rejected; only a terminal replay
         * certificate invalidates the last successful publication. */
        (void)Estimator_ReplayFaultStop();
        return 0U;
    }
    return 1U;
}

static void Estimator_PredictionProcess(
    const SystemInertialIncrement *prediction)
{
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    float delta_velocity_enu_mps[3];
#endif
    SystemLifecycleState lifecycle_state = SystemLifecycle_GetState();

    if (prediction == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(prediction, SystemInertialIncrement,
                             SILVERSTAR_ASSERT_MODULE_APP);
    if ((s_estimator.mission_running == 0U) ||
        ((lifecycle_state != SYSTEM_STATE_FLIGHT) &&
         (lifecycle_state != SYSTEM_STATE_RECOVERY)))
    {
        return;
    }
#if (SYSTEM_BUILD_NAVIGATION_BACKEND_ENABLED != 0U)
    if (Estimator_NavigationBackendSelected() != 0U)
    { Estimator_BackendPredictionProcess(prediction); return; }
#endif
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED == 0U)
    Estimator_PureInsPublish(prediction->timestamp_us);
    Estimator_DiagnosticsPublish(prediction->timestamp_us);
#else
    /* An invalidated output remains unavailable until explicit mission reset;
     * a later packet must not republish it as newly initialized. */
    if ((s_snapshot.initialized == 0U) &&
        ((s_snapshot.health_flags & ESTIMATOR_HEALTH_KF_NUMERIC_ERROR) != 0U))
    { return; }
    if (Estimator_KfPredictionApply(prediction, delta_velocity_enu_mps) == 0U)
    { return; }
    Estimator_AccelerationPublish(delta_velocity_enu_mps, prediction->dt_s);
    s_snapshot.measurement_attempt_mask = 0U;
    s_snapshot.position_update_result = SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    s_snapshot.velocity_update_result = SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    s_snapshot.baro_update_result = SYSTEM_ESTIMATOR_MEAS_REJECTED_INVALID;
    s_snapshot.velocity_update_dimension = 0U;
    s_snapshot.position_r_scale = 1.0f;
    s_snapshot.velocity_r_scale = 1.0f;
    s_snapshot.baro_r_scale = 1.0f;
    Estimator_GnssUpdate(prediction->timestamp_us);
    if (Estimator_ReplayFaultStop() != 0U) { return; }
    Estimator_BarometerUpdate(prediction->timestamp_us);
    if (Estimator_ReplayFaultStop() != 0U) { return; }
    if (SystemNavigationHealth_DegradedGet(prediction->timestamp_us) != 0U)
    { s_snapshot.health_flags |= ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    else { s_snapshot.health_flags &= ~ESTIMATOR_HEALTH_FUSION_TIMEOUT; }
    Estimator_SnapshotPublish(prediction->timestamp_us);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    Estimator_LogPush(prediction->timestamp_us);
#endif
#endif /* SYSTEM_BUILD_ESTIMATOR_ENABLED */
}

void EstimatorTask_RollbackMissionStart(void)
{
    uint32_t primask;

    /*
     * Roll back only the mission-start transaction.  The preflight origin
     * windows are deliberately preserved so a failed START attempt does not
     * force Alignment to collect them from scratch again.  Frozen origin
     * results are invalidated and will be recomputed from the preserved
     * windows on the next START attempt.
     */
    s_estimator.mission_running = 0U;
    s_estimator.initialized = 0U;
    s_preparation.initialized = 0U;
    s_preparation.generation++;
    /* Owner fields must be coherent before SnapshotPublish copies them. */
    s_estimator.gnss_origin_valid = 0U;
    s_estimator.gnss_fusion_enabled = 0U;
    s_estimator.baro_origin_valid = 0U;
#if (SYSTEM_BUILD_NAVIGATION_BACKEND_ENABLED != 0U)
    if (Estimator_NavigationBackendSelected() != 0U)
    { SystemNavigationBackend_Reset(); }
#endif
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    NavigationKf_Reset(&s_estimator.kf);
    NavigationReplay_Reset(&s_replay, &s_replay_storage, &s_estimator.kf, 0U, ++s_replay_epoch);
#endif
    s_snapshot.initialized = 0U;
    s_snapshot.mission_running = 0U;
    s_snapshot.gnss_origin_valid = 0U;
    s_snapshot.baro_origin_valid = 0U;
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    Estimator_SnapshotPublish(0U);
#else
    EstimatorTask_SnapshotCommit();
#endif
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    Estimator_LogPush(0U);
#endif
#endif
    EstimatorBarometerPending_Reset(&s_estimator.pending_barometer);

    s_estimator.gnss_origin_sample_count = 0U;
    s_estimator.baro_origin_sample_count = 0U;
    s_estimator.baro_diagnostics.origin_sample_count = 0U;
    s_estimator.baro_diagnostics.origin_state =
        (s_estimator.baro_diagnostics.source_supported != 0U) ?
            SYSTEM_ESTIMATOR_BARO_ORIGIN_COLLECTING :
            SYSTEM_ESTIMATOR_BARO_ORIGIN_UNAVAILABLE;
    Estimator_BarometerDiagnosticsPublish();
    Estimator_DiagnosticsPublish(0U);

    /* Resume collection only after all rollback-visible state is coherent. */
    primask = EstimatorTask_IrqLock();
    s_estimator.origin_collection_frozen = 0U;
    EstimatorTask_IrqUnlock(primask);
    SILVERSTAR_ASSERT(s_estimator.mission_running == 0U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
    SILVERSTAR_ASSERT(s_estimator.initialized == 0U,
                      SILVERSTAR_ASSERT_MODULE_APP,
                      SILVERSTAR_ASSERT_REASON_POSTCONDITION);
}

uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    EstimatorOutputSnapshot published;
    uint32_t primask;

    if (snapshot == NULL)
    {
        return 0U;
    }
    primask = EstimatorTask_IrqLock();
    published = s_published_snapshot;
    EstimatorTask_IrqUnlock(primask);
    *snapshot = published;
    return published.initialized;
}

static void InsTask_NavigationDiagnosticsApply(SystemInsDiagnostics *diagnostics)
{
    EstimatorOutputSnapshot navigation;

    if (diagnostics == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemInsDiagnostics,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (Estimator_GetLatestSnapshot(&navigation) == 0U)
    {
        /* The getter still copies an invalid snapshot. Do not fall back to
         * healthy pure-INS diagnostic flags after the selected navigation fails. */
        if ((navigation.mission_running != 0U) &&
            ((navigation.health_flags & ESTIMATOR_HEALTH_KF_NUMERIC_ERROR) != 0U))
        {
            diagnostics->quaternion_valid = 0U;
            diagnostics->velocity_valid = 0U;
            diagnostics->position_valid = 0U;
            diagnostics->software_attitude_propagation = 0U;
        }
        return;
    }
    diagnostics->last_update_timestamp_us = navigation.timestamp_us;
    diagnostics->quaternion_valid = navigation.initialized;
    diagnostics->velocity_valid = navigation.initialized;
    diagnostics->position_valid = navigation.initialized;
    diagnostics->software_attitude_propagation = (uint8_t)(
        (navigation.mission_running != 0U) && (navigation.predict_count != 0U));
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
    /* For a non-NULL output the getter always copies the published snapshot;
     * its return is navigation validity, which must not suppress fault evidence. */
    (void)Estimator_GetLatestSnapshot(&navigation);
    record->ins_update_count = navigation.update_sequence;
    record->health_flags = navigation.health_flags;
}
/* Production application functions are extracted unchanged above this fixture.
 * Host stubs cover task locks, no available sensor packet, and log sinks only.
 * Actual KF6/replay/attitude/mechanization code is linked. No MCU recovery. */
static void Test_Seed(void)
{
    memset(&s_estimator, 0, sizeof(s_estimator));
    memset(&s_snapshot, 0, sizeof(s_snapshot));
    memset(&s_published_snapshot, 0, sizeof(s_published_snapshot));
    NavigationKf_Init(&s_estimator.kf);
    NavigationKf_Reset(&s_estimator.kf);
    s_estimator.q_nb[0] = 1.0f;
    s_estimator.initialized = 1U;
    s_estimator.mission_running = 1U;
    s_estimator.gnss_origin_valid = 1U;
    s_estimator.baro_origin_valid = 1U;
    s_estimator.gnss_window.count = 5U;
    NavigationReplay_Reset(&s_replay, &s_replay_storage, &s_estimator.kf, 1000000ULL, 7U);
    s_measurement_fault = 0U;
    Estimator_SnapshotPublish(1000000ULL);
}

static void Test_Predict(void)
{
    SystemInertialIncrement input = {0};
    input.timestamp_us = 1005000ULL;
    input.dt_s = 0.005f;
    input.delta_velocity_b_sculling_corrected[2] = SYSTEM_KF_GRAVITY_MPS2 * input.dt_s;
    Estimator_PredictionProcess(&input);
}

static void Test_Healthy(void)
{
    EstimatorOutputSnapshot output;
    TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 1U);
    TEST_CHECK(output.initialized == 1U);
    /* No sensor packet is supplied here; supervisor timeout is legitimate. */
    TEST_CHECK((output.health_flags & ~ESTIMATOR_HEALTH_FUSION_TIMEOUT) == 0U);
    TEST_CHECK(output.prediction_queue_overflow_count == 0U);
    TEST_CHECK(s_replay.faulted == 0U);
}

int main(int argc, char **argv)
{
    unsigned scenario = (argc == 2) ? (unsigned)strtoul(argv[1], NULL, 10) : 999U;
    Test_Seed();
    if (scenario < 16U)
    {
        s_estimator.kf.health_flags = scenario;
        Estimator_SnapshotPublish(1000000ULL);
        Test_Healthy();
        TEST_CHECK(s_estimator.kf.health_flags == scenario);
        /* Every raw-bit combination also preserves the application's single
         * terminal-fault identity when the real replay model contract fails. */
        s_estimator.kf.process_accel_std_mps2[0] *= 2.0f;
        Test_Predict();
        EstimatorOutputSnapshot output;
        TEST_CHECK(s_replay.faulted == 1U);
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U);
        TEST_CHECK(output.health_flags == ESTIMATOR_HEALTH_KF_NUMERIC_ERROR);
        TEST_CHECK(output.timestamp_us == 1000000ULL && output.update_sequence == 2U);
        TEST_CHECK(output.prediction_queue_overflow_count == 0U);
        TEST_CHECK(s_estimator.kf.health_flags == scenario);
    }
    else if (scenario == 16U)
    {
        s_estimator.kf.covariance[2][2] = -1.0f;
        TEST_CHECK(NavigationKf_UpdateBaroAltitude(&s_estimator.kf, 0.0f, 1.0f) == NAV_KF_UPDATE_NUMERIC_ERROR);
        TEST_CHECK((s_estimator.kf.health_flags & NAV_KF_HEALTH_COVARIANCE_RECOVERED) != 0U);
        Test_Predict();
        Test_Healthy();
    }
    else if (scenario == 17U || scenario == 18U)
    {
        const float observation[3] = {(scenario == 17U) ? NAN : 10000000.0f,
            (scenario == 17U) ? 0.0f : 10000000.0f,
            (scenario == 17U) ? 0.0f : 10000000.0f};
        const float variance[3] = {1.0f, 1.0f, 1.0f};
        if (scenario == 17U)
        {
            NavigationKfGnssSeparatedUpdateResult separated;
            (void)NavigationKf_UpdateGnssPositionSeparated(&s_estimator.kf, observation, variance, &separated);
            TEST_CHECK(separated.horizontal_result == NAV_KF_UPDATE_REJECTED_INVALID);
            TEST_CHECK(separated.vertical_result == NAV_KF_UPDATE_ACCEPTED);
        }
        else
        { TEST_CHECK(NavigationKf_UpdateGnssPosition(&s_estimator.kf, observation, variance) == NAV_KF_UPDATE_REJECTED_NIS); }
        Test_Predict();
        Test_Healthy();
    }
    else if (scenario == 19U || scenario == 20U)
    {
        EstimatorOutputSnapshot output;
        if (scenario == 19U) { s_estimator.kf.process_accel_std_mps2[0] *= 2.0f; }
        else { s_measurement_fault = 1U; }
        Test_Predict();
        TEST_CHECK(s_replay.faulted == 1U);
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U);
        TEST_CHECK(output.initialized == 0U);
        TEST_CHECK(output.health_flags == ESTIMATOR_HEALTH_KF_NUMERIC_ERROR);
        TEST_CHECK(output.timestamp_us == 1000000ULL);
        TEST_CHECK(output.update_sequence == 1U);
        TEST_CHECK(output.prediction_queue_overflow_count == 0U);
        FlightLogStatsRecord stats;
        DiagnosticLog_StatsRecordBuild(&stats);
        TEST_CHECK(stats.health_flags == ESTIMATOR_HEALTH_KF_NUMERIC_ERROR);
        SystemInsDiagnostics diagnostics = {0};
        diagnostics.quaternion_valid = diagnostics.velocity_valid = diagnostics.position_valid = 1U;
        diagnostics.software_attitude_propagation = 1U;
        InsTask_NavigationDiagnosticsApply(&diagnostics);
        TEST_CHECK(diagnostics.quaternion_valid == 0U && diagnostics.velocity_valid == 0U);
        TEST_CHECK(diagnostics.position_valid == 0U && diagnostics.software_attitude_propagation == 0U);
        Test_Predict();
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U && output.timestamp_us == 1000000ULL);
    }
    else if (scenario == 21U)
    {
        EstimatorOutputSnapshot output;
        EstimatorTask_RollbackMissionStart();
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 0U);
        TEST_CHECK(output.gnss_origin_valid == 0U && output.baro_origin_valid == 0U);
        TEST_CHECK(s_estimator.gnss_origin_valid == 0U && s_estimator.baro_origin_valid == 0U);
        TEST_CHECK(s_estimator.gnss_window.count == 5U);
        TEST_CHECK(s_estimator.origin_collection_frozen == 0U);
    }
    else if (scenario == 22U)
    {
        s_bus_overflow = 3U;
        Estimator_SnapshotPublish(1000000ULL);
        EstimatorOutputSnapshot output;
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) == 1U);
        TEST_CHECK(output.prediction_queue_overflow_count == 3U);
        TEST_CHECK(output.health_flags == 0U);
    }
    else { TEST_CHECK(0); }
    return Test_Finish("estimator_health");
}

#include "platform_time.h"
PlatformResult PlatformTime_Init(void) { return PLATFORM_OK; }
uint64_t PlatformTime_Us(void) { return 1000000ULL; }
