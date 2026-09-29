#include "app_tasks.h"

#include <string.h>

#include "FreeRTOS.h"
#include "task.h"
#include "estimator_bus.h"
#include "estimator_task.h"
#include "imu_sample_bus.h"
#include "ins_task.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#include "logger_task.h"
#include "system_log_sink_if.h"
#include "system_storage_if.h"
#endif
#include "silverstar_assert.h"
#include "system_barometer_if.h"
#include "system_alignment.h"
#include "system_alignment_backend.h"
#include "system_calibration.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_indicator.h"
#include "system_inertial.h"
#include "system_lifecycle.h"
#include "system_lifecycle_backend.h"
#include "system_time.h"
#include "system_navigation_health.h"
#include "system_navigation_profile.h"

#define FLIGHT_TASK_FAULT_READY_TRANSITION 0x52445954UL
#define FLIGHT_TASK_FAULT_RECOVERY_INIT 0x52435649UL

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static uint8_t s_fault_event_written;
static uint32_t s_start_diagnostic_sequence[3];
static uint32_t s_calibration_start_sequence;
static uint32_t s_calibration_state_sequence;
static uint32_t s_calibration_face_event_sequence;
static uint32_t s_calibration_diagnostic_sequence;
static uint32_t s_alignment_start_sequence;
static SystemAlignmentState s_logged_alignment_state;
static uint8_t s_alignment_state_known;
static uint32_t s_deploy_log_sequence;
static uint32_t s_deploy_detail_log_sequence;
static uint32_t s_impact_log_sequence;
static uint32_t s_landing_log_sequence;
static uint32_t s_landing_diagnostic_log_sequence;

static uint32_t FlightTask_FloatBitsGet(float value)
{
    uint32_t bits = 0U;

    (void)memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void FlightTask_CalibrationResultWrite(
    const SystemCalibrationStatus *status)
{
    FlightLogCalibrationResultRecord result_record;
    uint8_t axis;

    if (status == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(&result_record, 0, sizeof(result_record));
    result_record.source_id = FLIGHT_LOG_PRIMARY_INERTIAL_SOURCE_ID;
    result_record.virtual_imu_id = FLIGHT_LOG_PRIMARY_VIRTUAL_IMU_ID;
    result_record.mode = (uint8_t)status->mode;
    result_record.state = (uint8_t)status->state;
    result_record.ready = status->ready;
    result_record.completed_face_mask = status->completed_face_mask;
    result_record.samples = status->samples;
    result_record.reject_count = status->reject_count;
    result_record.retry_count = status->retry_count;
    result_record.start_sequence = status->start_sequence;
    (void)memcpy(result_record.accel_bias_mps2,
                 status->correction.accel_bias_mps2,
                 sizeof(result_record.accel_bias_mps2));
    (void)memcpy(result_record.accel_scale,
                 status->correction.accel_scale,
                 sizeof(result_record.accel_scale));
    (void)memcpy(result_record.gyro_bias_radps,
                 status->correction.gyro_bias_radps,
                 sizeof(result_record.gyro_bias_radps));
    (void)memcpy(result_record.gyro_scale,
                 status->correction.gyro_scale,
                 sizeof(result_record.gyro_scale));
    (void)LoggerBus_CalibrationResultPush(SystemTime_GetMonotonicUs(),
                                          &result_record);

    for (axis = 0U; axis < 3U; axis++)
    {
        (void)LoggerBus_EventPush(SystemTime_GetMonotonicUs(),
            FLIGHT_LOG_EVENT_CALIBRATION_RESULT,
            ((uint32_t)status->mode << 24U) | (1UL << 16U) | axis,
            FlightTask_FloatBitsGet(
                status->correction.accel_bias_mps2[axis]));
        (void)LoggerBus_EventPush(SystemTime_GetMonotonicUs(),
            FLIGHT_LOG_EVENT_CALIBRATION_RESULT,
            ((uint32_t)status->mode << 24U) | (2UL << 16U) | axis,
            FlightTask_FloatBitsGet(
                status->correction.accel_scale[axis]));
        (void)LoggerBus_EventPush(SystemTime_GetMonotonicUs(),
            FLIGHT_LOG_EVENT_CALIBRATION_RESULT,
            ((uint32_t)status->mode << 24U) | (3UL << 16U) | axis,
            FlightTask_FloatBitsGet(
                status->correction.gyro_bias_radps[axis]));
        (void)LoggerBus_EventPush(SystemTime_GetMonotonicUs(),
            FLIGHT_LOG_EVENT_CALIBRATION_RESULT,
            ((uint32_t)status->mode << 24U) | (4UL << 16U) | axis,
            FlightTask_FloatBitsGet(
                status->correction.gyro_scale[axis]));
    }
}

static void FlightTask_AlignmentResultWrite(
    const SystemAlignmentStatus *status)
{
    FlightLogAlignmentResultRecord record;
    InsAlignmentSnapshot attitude_snapshot;
    const SystemAlignmentSourceStatus *attitude_status;
    const SystemAlignmentSourceStatus *gnss_status;
    const SystemAlignmentSourceStatus *baro_status;

    if (status == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(&record, 0, sizeof(record));
    record.capability_mask = status->capability_mask;
    record.selected_mask = status->selected_mask;
    record.required_mask = status->required_mask;
    record.ready_mask = status->ready_mask;
    record.unavailable_mask = status->unavailable_mask;
    record.missing_adapter_mask = status->missing_adapter_mask;
    record.start_sequence = status->start_sequence;
    record.state = (uint8_t)status->state;
    record.config_result = (uint8_t)status->config_result;
    record.ready = status->ready;
    record.source_count = SYSTEM_ALIGNMENT_SOURCE_COUNT;
    attitude_status = &status->component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE];
    gnss_status = &status->component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN];
    baro_status = &status->component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN];
    record.attitude_state = (uint8_t)attitude_status->state;
    record.attitude_source =
        (uint8_t)attitude_status->detail.attitude.source;
    record.attitude_timestamp_us =
        attitude_status->detail.attitude.timestamp_us;
    if (Ins_GetAlignmentSnapshot(&attitude_snapshot) != 0U)
    {
        (void)memcpy(record.q_nb, attitude_snapshot.q_nb,
                     sizeof(record.q_nb));
    }
    record.gnss_state = (uint8_t)gnss_status->state;
    record.gnss_origin_lat_e7 = gnss_status->detail.gnss.origin_lat_e7;
    record.gnss_origin_lon_e7 = gnss_status->detail.gnss.origin_lon_e7;
    record.gnss_origin_height_mm = gnss_status->detail.gnss.origin_height_mm;
    record.gnss_sample_count = gnss_status->detail.gnss.sample_count;
    record.gnss_horizontal_accuracy_m =
        gnss_status->detail.gnss.horizontal_accuracy_m;
    record.gnss_vertical_accuracy_m =
        gnss_status->detail.gnss.vertical_accuracy_m;
    record.barometer_state = (uint8_t)baro_status->state;
    record.barometer_sample_count =
        baro_status->detail.barometer.sample_count;
    record.barometer_origin_pressure_pa =
        baro_status->detail.barometer.origin_pressure_pa;
    record.barometer_origin_altitude_m =
        baro_status->detail.barometer.origin_altitude_m;
    (void)LoggerBus_AlignmentResultPush(SystemTime_GetMonotonicUs(), &record);
}

static uint8_t FlightTask_AlignmentStateEventWrite(
    const SystemAlignmentSummary *summary,
    uint64_t now_us)
{
    SystemAlignmentStatus detail;

    if ((summary == NULL) ||
        (SystemAlignment_StatusGet(&detail) != SYSTEM_DEVICE_OK) ||
        (detail.state != summary->state) ||
        (detail.start_sequence != summary->start_sequence))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(summary, SystemAlignmentSummary,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (detail.state == SYSTEM_ALIGNMENT_STATE_READY)
    {
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_ALIGNMENT_READY,
            detail.ready_mask,
            detail.required_mask);
    }
    else if (detail.state == SYSTEM_ALIGNMENT_STATE_FAILED)
    {
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_ALIGNMENT_FAILED,
            detail.unavailable_mask,
            detail.missing_adapter_mask);
    }
    else if (detail.state == SYSTEM_ALIGNMENT_STATE_STALE)
    {
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_ALIGNMENT_REJECTED,
            (uint32_t)detail.state,
            (uint32_t)detail.stale_reason);
    }
    else
    {
        return 1U;
    }
    FlightTask_AlignmentResultWrite(&detail);
    return 1U;
}

static void FlightTask_AlignmentEventsProcess(uint64_t now_us)
{
    SystemAlignmentSummary alignment;

    SILVERSTAR_ASSERT_OBJECT(s_start_diagnostic_sequence, uint32_t,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (SystemAlignment_SummaryGet(&alignment) != SYSTEM_DEVICE_OK) { return; }
    if (alignment.start_sequence != s_alignment_start_sequence)
    {
        s_alignment_start_sequence = alignment.start_sequence;
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_ALIGNMENT_START, 0U, 0U);
    }
    if ((s_alignment_state_known != 0U) &&
        (alignment.state == s_logged_alignment_state))
    {
        return;
    }
    if (((alignment.state == SYSTEM_ALIGNMENT_STATE_READY) ||
         (alignment.state == SYSTEM_ALIGNMENT_STATE_FAILED) ||
         (alignment.state == SYSTEM_ALIGNMENT_STATE_STALE)) &&
        (FlightTask_AlignmentStateEventWrite(&alignment, now_us) == 0U))
    {
        return;
    }
    s_logged_alignment_state = alignment.state;
    s_alignment_state_known = 1U;
}

static void FlightTask_CalibrationTerminalEventsProcess(
    const SystemCalibrationStatus *calibration,
    uint64_t now_us)
{
    if (calibration == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(calibration, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (calibration->face_event_sequence !=
        s_calibration_face_event_sequence)
    {
        s_calibration_face_event_sequence = calibration->face_event_sequence;
        if (calibration->last_face_result ==
            SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE)
        {
            (void)LoggerBus_EventPush(now_us,
                FLIGHT_LOG_EVENT_CALIBRATION_FACE_COMPLETE,
                (uint32_t)calibration->last_face,
                (uint32_t)calibration->completed_face_mask);
        }
    }
    if (calibration->state_sequence == s_calibration_state_sequence)
    {
        return;
    }
    s_calibration_state_sequence = calibration->state_sequence;
    if (calibration->state == SYSTEM_CALIBRATION_STATE_READY)
    {
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_CALIBRATION_READY,
            (uint32_t)calibration->mode,
            (uint32_t)calibration->completed_face_mask);
        FlightTask_CalibrationResultWrite(calibration);
    }
    else if (calibration->state == SYSTEM_CALIBRATION_STATE_FAILED)
    {
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_CALIBRATION_FAILED,
            (uint32_t)calibration->mode,
            (uint32_t)calibration->wait_reason);
        FlightTask_CalibrationResultWrite(calibration);
    }
}

static void FlightTask_CalibrationEventsProcess(uint64_t now_us)
{
    SystemCalibrationStatus calibration;

    SILVERSTAR_ASSERT_OBJECT(s_start_diagnostic_sequence, uint32_t,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (SystemCalibration_StatusGet(&calibration) != SYSTEM_DEVICE_OK)
    {
        return;
    }
    if (calibration.diagnostic_sequence != s_calibration_diagnostic_sequence)
    {
        s_calibration_diagnostic_sequence = calibration.diagnostic_sequence;
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_IMU_BIAS_WAIT,
            (uint32_t)calibration.diagnostic_face,
            (uint32_t)calibration.diagnostic_reason);
    }
    if (calibration.start_sequence != s_calibration_start_sequence)
    {
        s_calibration_start_sequence = calibration.start_sequence;
        (void)LoggerBus_EventPush(now_us,
            FLIGHT_LOG_EVENT_CALIBRATION_START,
            (uint32_t)calibration.mode, 0U);
    }
    FlightTask_CalibrationTerminalEventsProcess(&calibration, now_us);
}

static void FlightTask_PreflightEventsProcess(void)
{
    uint64_t now_us = SystemTime_GetMonotonicUs();

    FlightTask_CalibrationEventsProcess(now_us);
    FlightTask_AlignmentEventsProcess(now_us);
}

static void FlightTask_StartDiagnosticProcess(void)
{
    SystemLifecycleStartDiagnostic diagnostic;
    uint8_t source;

    SILVERSTAR_ASSERT_OBJECT(s_start_diagnostic_sequence, uint32_t,
        SILVERSTAR_ASSERT_MODULE_APP);
    for (source = 0U; source < 3U; source++)
    {
        if ((SystemLifecycle_GetLastStartDiagnostic(
                (SystemStartSource)source, &diagnostic) == 0U) ||
            (diagnostic.sequence == s_start_diagnostic_sequence[source]))
        {
            continue;
        }
        s_start_diagnostic_sequence[source] = diagnostic.sequence;
        if (diagnostic.response.result != SYSTEM_LIFECYCLE_START_OK)
        {
            (void)LoggerBus_EventPush(
                diagnostic.response.timestamp_us,
                FLIGHT_LOG_EVENT_START_REJECTED,
                ((uint32_t)diagnostic.response.result << 16U) |
                    (uint32_t)diagnostic.response.reason,
                ((uint32_t)source << 24U) |
                    (diagnostic.response.request_id & 0x00FFFFFFUL));
        }
    }
}

static void FlightTask_FaultEventProcess(void)
{
    if (SystemLifecycle_GetState() != SYSTEM_STATE_FAULT)
    {
        s_fault_event_written = 0U;
        return;
    }
    if ((s_fault_event_written == 0U) &&
        (LoggerBus_EventPush(SystemTime_GetMonotonicUs(),
                             FLIGHT_LOG_EVENT_SYSTEM_FAULT,
                             SystemLifecycle_GetFaultReason(),
                             0U) == LOGGER_BUS_RESULT_OK))
    {
        s_fault_event_written = 1U;
    }
}
#endif

static void FlightTask_RecoveryEstimatorInputApply(
    SystemFlightRecoveryInput *input)
{
    EstimatorOutputSnapshot estimator;
    EstimatorPressureSnapshot pressure;

    if (input == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (Estimator_GetLatestSnapshot(&estimator) != 0U)
    {
        input->estimator_timestamp_us = estimator.timestamp_us;
        input->estimator_sequence = estimator.update_sequence;
        (void)memcpy(input->q_nb, estimator.q_nb, sizeof(input->q_nb));
        (void)memcpy(input->velocity_enu_mps,
                     estimator.velocity_enu_mps,
                     sizeof(input->velocity_enu_mps));
        input->attitude_valid = (uint8_t)(
            (estimator.initialized != 0U) &&
            (estimator.mission_running != 0U) &&
            ((estimator.health_flags & ESTIMATOR_HEALTH_KF_NUMERIC_ERROR) == 0U) &&
            (SystemNavigationHealth_OverallGet(SystemTime_GetMonotonicUs(),
                (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_NONE) ? 0U : 0x0FU,
                0U) != SYSTEM_NAVIGATION_HEALTH_INVALID));
        input->velocity_valid = input->attitude_valid;
        input->ins_timestamp_us = estimator.timestamp_us;
        input->ins_sequence = estimator.update_sequence;
        (void)memcpy(input->linear_accel_n_mps2,
                     estimator.acceleration_enu_mps2,
                     sizeof(input->linear_accel_n_mps2));
        input->linear_accel_valid = input->attitude_valid;
    }
    if (EstimatorBus_PressureGetLatest(&pressure) != 0U)
    {
        input->barometer_timestamp_us = pressure.timestamp_us;
        input->barometer_sequence = pressure.sequence;
        input->barometer_altitude_m = pressure.altitude_m;
        input->barometer_healthy = pressure.healthy;
        input->barometer_valid = (uint8_t)(
            (pressure.healthy != 0U) &&
            (pressure.valid != 0U) &&
            ((pressure.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) != 0U));
    }
}

static void FlightTask_RecoveryInitialInputApply(
    SystemFlightRecoveryInput *input)
{
    float initial_q_nb[4];

    if (input == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (Ins_GetInitialAttitude(initial_q_nb) != 0U)
    {
        (void)memcpy(input->initial_q_nb, initial_q_nb,
                     sizeof(input->initial_q_nb));
        input->initial_attitude_valid = 1U;
    }
}

static void FlightTask_RecoveryInertialInputApply(
    SystemFlightRecoveryInput *input)
{
    SystemCalibrationImuCorrection correction;
    SystemInertialSample inertial;

    if (input == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemFlightRecoveryInput,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (SystemInertial_LatestGet(&inertial) != SYSTEM_DEVICE_OK) { return; }
    /* Keep the observation identity even when correction rejects its values. */
    input->inertial_timestamp_us = inertial.sample_timestamp_us;
    input->inertial_sequence = inertial.sequence;
    if (((inertial.valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL |
                                 SYSTEM_INERTIAL_VALID_GYRO)) != 0U) &&
        (SystemCalibration_ImuCorrectionGet(&correction) ==
         SYSTEM_DEVICE_OK) &&
        (SystemCalibration_ImuCorrectionApply(
             inertial.accel_b_mps2, inertial.gyro_b_radps, &correction,
             input->corrected_accel_b_mps2,
             input->corrected_gyro_b_radps) == SYSTEM_DEVICE_OK))
    {
        input->corrected_accel_valid = (uint8_t)(
            (inertial.valid_mask & SYSTEM_INERTIAL_VALID_ACCEL) != 0U);
        input->corrected_gyro_valid = (uint8_t)(
            (inertial.valid_mask & SYSTEM_INERTIAL_VALID_GYRO) != 0U);
    }
}

static void FlightTask_FlightRecoveryInputGet(
    SystemFlightRecoveryInput *input)
{
    if (input == NULL) { return; }
    (void)memset(input, 0, sizeof(*input));
    if (SystemTime_IsMissionStarted() != 0U)
    {
        input->mission_time_ms =
            (uint32_t)(SystemTime_GetMissionUs() / 1000ULL);
    }
    FlightTask_RecoveryEstimatorInputApply(input);
    FlightTask_RecoveryInitialInputApply(input);
    FlightTask_RecoveryInertialInputApply(input);
    /* A higher-priority producer can publish while snapshots are acquired. */
    input->now_us = SystemTime_GetMonotonicUs();
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void FlightTask_LandingDiagnosticLogProcess(const SystemFlightRecoveryStatus *status)
{
    const SystemLandingDiagnostic *diagnostic = &status->landing_diagnostic;
    FlightLogLandingDiagnosticRecord record;
    SILVERSTAR_ASSERT_OBJECT(status, SystemFlightRecoveryStatus, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(diagnostic->transition <= 3U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (diagnostic->sequence == s_landing_diagnostic_log_sequence) { return; }
    (void)memset(&record, 0, sizeof(record));
    record.evaluation_timestamp_us = diagnostic->evaluation_timestamp_us;
    record.candidate_start_timestamp_us = diagnostic->candidate_start_timestamp_us;
    record.sequence = diagnostic->sequence;
    record.candidate_elapsed_us = diagnostic->candidate_elapsed_us;
    record.valid_coverage = diagnostic->valid_coverage;
    record.still_ratio = diagnostic->still_ratio;
    record.maximum_bad_duration_us = diagnostic->maximum_bad_duration_us;
    record.baro_slope_mps = diagnostic->baro_slope_mps;
    record.baro_span_m = diagnostic->baro_span_m;
    record.baro_coverage = diagnostic->baro_coverage;
    record.transition = diagnostic->transition;
    record.reset_reason = (uint8_t)diagnostic->reset_reason;
    if (LoggerBus_LandingDiagnosticPush(record.evaluation_timestamp_us, &record) == LOGGER_BUS_RESULT_OK)
    { s_landing_diagnostic_log_sequence = diagnostic->sequence; }
}

static void FlightTask_FlightRecoveryEventsProcess(void)
{
    SystemFlightRecoveryStatus status;

    SILVERSTAR_ASSERT_OBJECT(s_start_diagnostic_sequence, uint32_t,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (SystemFlightRecovery_StatusGet(&status) != SYSTEM_DEVICE_OK)
    {
        return;
    }
    FlightTask_LandingDiagnosticLogProcess(&status);
    if (status.deploy_event_sequence != s_deploy_log_sequence)
    {
        if (LoggerBus_EventPush(
                status.deploy_event_timestamp_us,
                FLIGHT_LOG_EVENT_PARACHUTE_DEPLOY,
                (uint32_t)status.deploy_trigger_mask,
                FlightTask_FloatBitsGet(status.deploy_trigger_value)) ==
            LOGGER_BUS_RESULT_OK)
        {
            s_deploy_log_sequence = status.deploy_event_sequence;
        }
    }
    if (status.deploy_event_sequence != s_deploy_detail_log_sequence)
    {
        if (LoggerBus_EventPush(
                status.deploy_event_timestamp_us,
                FLIGHT_LOG_EVENT_PARACHUTE_DEPLOY_DETAIL,
                (uint32_t)status.deploy_matched_mask,
                FlightTask_FloatBitsGet(status.deploy_trigger_value)) ==
            LOGGER_BUS_RESULT_OK)
        {
            s_deploy_detail_log_sequence = status.deploy_event_sequence;
        }
    }
    if (status.impact_event_sequence != s_impact_log_sequence)
    {
        if (LoggerBus_EventPush(
                status.impact_event_timestamp_us,
                FLIGHT_LOG_EVENT_LANDING_IMPACT,
                FlightTask_FloatBitsGet(status.impact_metric_mps2),
                FlightTask_FloatBitsGet(status.impact_peak_mps2)) ==
            LOGGER_BUS_RESULT_OK)
        {
            s_impact_log_sequence = status.impact_event_sequence;
        }
    }
    if (status.landing_event_sequence != s_landing_log_sequence)
    {
        if (LoggerBus_EventPush(status.landing_event_timestamp_us,
                                FLIGHT_LOG_EVENT_LANDING,
                                0U, 0U) == LOGGER_BUS_RESULT_OK)
        {
            (void)LoggerBus_FinalizationArm(
                status.landing_event_timestamp_us);
            s_landing_log_sequence = status.landing_event_sequence;
        }
    }
}
#endif

static SystemDeviceResult FlightTask_PrepareStart(void)
{
    return SystemAlignment_PrepareMission();
}

static SystemDeviceResult FlightTask_FreezeOrigins(void)
{
    return SystemAlignment_OriginsFreeze();
}

static SystemDeviceResult FlightTask_AlignmentReset(void)
{
    SystemDeviceResult attitude_result = InsTask_AlignmentReset();
    SystemDeviceResult origin_result = EstimatorTask_OriginsReset();

    if (attitude_result != SYSTEM_DEVICE_OK)
    {
        return attitude_result;
    }
    return origin_result;
}

static SystemDeviceResult FlightTask_AttitudeAlignmentStatusGet(
    SystemAlignmentSourceStatus *status)
{
    SystemDeviceResult result;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    result = InsTask_AttitudeAlignmentStatusGet(&status->detail.attitude);
    status->state = status->detail.attitude.state;
    status->ready = status->detail.attitude.attitude_ready;
    return result;
}

static SystemDeviceResult FlightTask_GnssAlignmentStatusGet(
    SystemAlignmentSourceStatus *status)
{
    SystemDeviceResult result;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    result = EstimatorTask_GnssAlignmentStatusGet(&status->detail.gnss);
    status->state = status->detail.gnss.state;
    status->ready = status->detail.gnss.ready;
    return result;
}

static SystemDeviceResult FlightTask_BarometerAlignmentStatusGet(
    SystemAlignmentSourceStatus *status)
{
    SystemDeviceResult result;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    result = EstimatorTask_BarometerAlignmentStatusGet(
        &status->detail.barometer);
    status->state = status->detail.barometer.state;
    status->ready = status->detail.barometer.ready;
    return result;
}

static SystemDeviceResult FlightTask_AlignmentGuardSampleGet(
    SystemAlignmentGuardSample *sample)
{
    SystemCalibrationImuCorrection correction;
    SystemInertialSample inertial;
    SystemDeviceResult result;

    if (sample == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemAlignmentGuardSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(sample, 0, sizeof(*sample));
    result = SystemInertial_LatestGet(&inertial);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    result = SystemCalibration_ImuCorrectionGet(&correction);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    result = SystemCalibration_ImuCorrectionApply(
        inertial.accel_b_mps2, inertial.gyro_b_radps, &correction,
        sample->corrected_accel_b_mps2,
        sample->corrected_gyro_b_radps);
    if (result != SYSTEM_DEVICE_OK) { return result; }

    sample->observation_timestamp_us = SystemTime_GetMonotonicUs();
    sample->inertial_sample_timestamp_us = inertial.sample_timestamp_us;
    sample->inertial_receive_timestamp_us = inertial.receive_timestamp_us;
    sample->inertial_sequence = inertial.sequence;
    if ((inertial.valid_mask & SYSTEM_INERTIAL_VALID_ACCEL) != 0U)
    {
        sample->valid_mask |= SYSTEM_ALIGNMENT_GUARD_VALID_ACCEL;
    }
    if ((inertial.valid_mask & SYSTEM_INERTIAL_VALID_GYRO) != 0U)
    {
        sample->valid_mask |= SYSTEM_ALIGNMENT_GUARD_VALID_GYRO;
    }
    return SYSTEM_DEVICE_OK;
}

static void FlightTask_AlignmentAbort(void)
{
    InsTask_AbortMission();
    EstimatorTask_RollbackMissionStart();
}

SystemDeviceResult SystemAlignmentBackend_Reset(void)
{
    return FlightTask_AlignmentReset();
}

SystemDeviceResult SystemAlignmentBackend_PrepareMission(void)
{
    return InsTask_PrepareStart();
}

SystemDeviceResult SystemAlignmentBackend_FreezeSources(void)
{
    return EstimatorTask_FreezeOrigins();
}

SystemDeviceResult SystemAlignmentBackend_GuardSampleGet(
    SystemAlignmentGuardSample *sample)
{
    return FlightTask_AlignmentGuardSampleGet(sample);
}

void SystemAlignmentBackend_MissionPreparationAbort(void)
{
    FlightTask_AlignmentAbort();
}

SystemDeviceResult SystemAlignmentBackend_SourceStatusGet(
    SystemAlignmentSourceId source_id,
    SystemAlignmentSourceStatus *status)
{
    switch (source_id)
    {
        case SYSTEM_ALIGNMENT_SOURCE_ATTITUDE:
            return FlightTask_AttitudeAlignmentStatusGet(status);
        case SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN:
            return FlightTask_GnssAlignmentStatusGet(status);
        case SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN:
            return FlightTask_BarometerAlignmentStatusGet(status);
        case SYSTEM_ALIGNMENT_SOURCE_MAGNETIC:
        case SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING:
        case SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE:
        default:
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

static SystemDeviceResult FlightTask_InitializeNavigation(void)
{
    SystemDeviceResult result;

    result = InsTask_InitializeMission();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    result = EstimatorTask_InitializeMission();
    if (result != SYSTEM_DEVICE_OK)
    {
        InsTask_AbortMission();
    }
    return result;
}

static SystemDeviceResult FlightTask_ResetFlightQueues(void)
{
    ImuSampleBus_Reset();
    EstimatorBus_ResetFlightData();
    return SYSTEM_DEVICE_OK;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void FlightTask_InitialStateRecordBuild(
    const InsAlignmentSnapshot *alignment,
    const EstimatorInitialStateSnapshot *estimator,
    FlightLogInitialStateRecord *record)
{
    if ((alignment == NULL) || (estimator == NULL) || (record == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(alignment, InsAlignmentSnapshot,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogInitialStateRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->alignment_algorithm = (uint8_t)alignment->algorithm;
    record->hardware_mode = (uint8_t)alignment->hardware_mode;
    record->mode_verified = alignment->mode_verified;
    record->origin_valid_flags =
        (uint8_t)((estimator->gnss_origin_valid != 0U ? 1U : 0U) |
                  (estimator->barometer_origin_valid != 0U ? 2U : 0U));
    record->alignment_sample_count =
        (alignment->sample_count > UINT16_MAX) ? UINT16_MAX :
                                               (uint16_t)alignment->sample_count;
    record->gnss_sample_count = estimator->gnss_sample_count;
    record->barometer_sample_count = estimator->barometer_sample_count;
    (void)memcpy(record->q_nb, alignment->q_nb, sizeof(record->q_nb));
    (void)memcpy(record->acceleration_mean_b_mps2,
                 alignment->acceleration_mean_b_mps2,
                 sizeof(record->acceleration_mean_b_mps2));
    (void)memcpy(record->gyro_mean_b_radps, alignment->gyro_mean_b_radps,
                 sizeof(record->gyro_mean_b_radps));
    (void)memcpy(record->magnetic_field_mean_b_uT,
                 alignment->magnetic_field_mean_b_uT,
                 sizeof(record->magnetic_field_mean_b_uT));
    record->gnss_origin_latitude_e7 = estimator->gnss_origin_latitude_e7;
    record->gnss_origin_longitude_e7 = estimator->gnss_origin_longitude_e7;
    record->gnss_origin_height_mm = estimator->gnss_origin_height_mm;
    (void)memcpy(record->gnss_origin_position_std_m,
                 estimator->gnss_origin_position_std_m,
                 sizeof(record->gnss_origin_position_std_m));
    (void)memcpy(record->initial_velocity_enu_mps,
                 estimator->initial_velocity_enu_mps,
                 sizeof(record->initial_velocity_enu_mps));
    (void)memcpy(record->initial_velocity_std_mps,
                 estimator->initial_velocity_std_mps,
                 sizeof(record->initial_velocity_std_mps));
    record->barometer_origin_altitude_m =
        estimator->barometer_origin_altitude_m;
    record->barometer_origin_std_m = estimator->barometer_origin_std_m;
    (void)memcpy(record->p0_diagonal, estimator->p0_diagonal,
                 sizeof(record->p0_diagonal));
}

static void FlightTask_WriteStartRecords(void)
{
    InsAlignmentSnapshot alignment;
    EstimatorInitialStateSnapshot estimator;
    FlightLogInitialStateRecord initial_record;
    LoggerBusResult config_log_result;
    LoggerBusResult mission_config_log_result;
    LoggerBusResult initial_log_result;
    LoggerBusResult event_log_result;
    uint64_t timestamp_us = SystemTime_GetMonotonicUs();

    mission_config_log_result = LoggerBus_MissionConfigPush(timestamp_us);
    if ((Ins_GetAlignmentSnapshot(&alignment) == 0U) ||
        (Estimator_GetInitialStateSnapshot(&estimator) == 0U))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(&alignment, InsAlignmentSnapshot,
        SILVERSTAR_ASSERT_MODULE_APP);
    FlightTask_InitialStateRecordBuild(&alignment, &estimator,
                                       &initial_record);

    config_log_result = LoggerBus_SystemConfigPush(timestamp_us);
    initial_log_result = LoggerBus_InitialStatePush(timestamp_us,
                                                     &initial_record);
    event_log_result = LoggerBus_EventPush(timestamp_us,
                                           FLIGHT_LOG_EVENT_MISSION_START,
                                           0U,
                                           0U);
    if ((mission_config_log_result != LOGGER_BUS_RESULT_OK) ||
        (config_log_result != LOGGER_BUS_RESULT_OK) ||
        (initial_log_result != LOGGER_BUS_RESULT_OK) ||
        (event_log_result != LOGGER_BUS_RESULT_OK))
    {
        /*
         * START is already committed.  LoggerBus owns queue-overflow
         * diagnostics, so an incomplete start record must not roll back the
         * lifecycle or navigation state.
         */
        return;
    }
}
#endif

static void FlightTask_AbortStart(void)
{
    SystemAlignment_MissionPreparationAbort();
    ImuSampleBus_Reset();
    EstimatorBus_ResetFlightData();
}

static void FlightTask_RuntimeInitialize(void)
{
    SystemDeviceResult result = SystemFlightRecovery_Init();

    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        SystemLifecycle_EnterFault(FLIGHT_TASK_FAULT_RECOVERY_INIT);
    }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SILVERSTAR_ASSERT_OBJECT(s_start_diagnostic_sequence, uint32_t,
        SILVERSTAR_ASSERT_MODULE_APP);
    s_fault_event_written = 0U;
    s_calibration_start_sequence = 0U;
    s_calibration_state_sequence = 0U;
    s_calibration_face_event_sequence = 0U;
    s_calibration_diagnostic_sequence = 0U;
    s_alignment_start_sequence = 0U;
    s_alignment_state_known = 0U;
    s_deploy_log_sequence = 0U;
    s_deploy_detail_log_sequence = 0U;
    s_impact_log_sequence = 0U;
    s_landing_log_sequence = 0U;
    (void)memset(s_start_diagnostic_sequence, 0,
                 sizeof(s_start_diagnostic_sequence));
#endif
}

SystemDeviceResult SystemLifecycleBackend_PrepareStart(void)
{
    return FlightTask_PrepareStart();
}

SystemDeviceResult SystemLifecycleBackend_FreezeOrigins(void)
{
    return FlightTask_FreezeOrigins();
}

SystemDeviceResult SystemLifecycleBackend_InitializeNavigation(void)
{
    return FlightTask_InitializeNavigation();
}

SystemDeviceResult SystemLifecycleBackend_ResetFlightQueues(void)
{
    return FlightTask_ResetFlightQueues();
}

uint8_t SystemLifecycleBackend_StorageReadyGet(void)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    LoggerTaskDiagnostics logger;
    SystemLogSinkHealth sink;
    SystemStorageHealth storage;
    uint32_t mission_id = 0U;
    if ((LoggerBus_StartupStateGet() != LOGGER_STREAMING_READY) ||
        (LoggerTask_DiagnosticsGet(&logger) != SYSTEM_DEVICE_OK) ||
        (SystemLogSink_HealthGet(&sink) != SYSTEM_DEVICE_OK) ||
        (SystemStorage_HealthGet(&storage) != SYSTEM_DEVICE_OK) ||
        (SystemStorage_MissionIdGet(&mission_id) != SYSTEM_DEVICE_OK))
    { return 0U; }
    SILVERSTAR_ASSERT(logger.snapshot_ready <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(sink.session_active <= 1U,
        SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    return (uint8_t)((logger.io_fault == 0U) &&
        (logger.snapshot_ready != 0U) &&
        (logger.snapshot_mission_id == mission_id) &&
        (logger.snapshot_commit_generation != 0U) &&
        (logger.snapshot_calibration_generation ==
         SystemCalibration_GenerationGet()) &&
        (mission_id != 0U) &&
        (sink.initialized != 0U) && (sink.session_active != 0U) &&
        (sink.healthy != 0U) && (storage.initialized != 0U) &&
        (storage.mounted != 0U) && (storage.healthy != 0U));
#else
    return 0U;
#endif
}

void SystemLifecycleBackend_AbortStart(void)
{
    FlightTask_AbortStart();
}

void AppTask_Flight(void *argument)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemLifecycleState previous_state;
#endif
    SystemDeviceResult alignment_process_result;
    SystemFlightRecoveryInput flight_recovery_input;

    (void)argument;
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SILVERSTAR_ASSERT_OBJECT(s_start_diagnostic_sequence, uint32_t,
        SILVERSTAR_ASSERT_MODULE_APP);
#endif
    FlightTask_RuntimeInitialize();
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    previous_state = SystemLifecycle_GetState();
#endif

    for (;;)
    {
        SystemCalibration_Process();
        alignment_process_result = SystemAlignment_Process();
        if (alignment_process_result != SYSTEM_DEVICE_OK)
        {
            /* Registration is fixed for the task lifetime; retry next cycle. */
        }
        if ((SystemLifecycle_GetState() == SYSTEM_STATE_PREFLIGHT) ||
            (SystemLifecycle_GetState() == SYSTEM_STATE_READY))
        {
            /* The preparation snapshot records the exact result and clears READY
             * on failure; the bounded FlightTask period permits a fresh retry. */
            (void)EstimatorTask_PrepareNavigation();
        }
        if ((SystemLifecycle_GetState() == SYSTEM_STATE_PREFLIGHT) &&
            (SystemHealth_IsReady() != 0U))
        {
            if (SystemLifecycle_EnterReady() != SYSTEM_DEVICE_OK)
            {
                SystemLifecycle_EnterFault(
                    FLIGHT_TASK_FAULT_READY_TRANSITION);
            }
        }
        SystemLifecycle_Process();
        FlightTask_FlightRecoveryInputGet(&flight_recovery_input);
        if (SystemFlightRecovery_Process(&flight_recovery_input) !=
            SYSTEM_DEVICE_OK)
        {
            /* Action/result diagnostics are latched in the manager snapshot. */
        }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
        FlightTask_PreflightEventsProcess();
        FlightTask_StartDiagnosticProcess();
        FlightTask_FlightRecoveryEventsProcess();
        if ((previous_state != SYSTEM_STATE_FLIGHT) &&
            (SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT))
        {
            FlightTask_WriteStartRecords();
        }
        previous_state = SystemLifecycle_GetState();
        FlightTask_FaultEventProcess();
#endif
        SystemIndicator_Process();
        vTaskDelay(pdMS_TO_TICKS(2U));
    }
}
