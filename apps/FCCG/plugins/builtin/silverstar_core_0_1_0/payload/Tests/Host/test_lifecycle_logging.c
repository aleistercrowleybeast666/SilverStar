#include <setjmp.h>
#include <stdint.h>
#include <string.h>

#include "app_tasks.h"
#include "estimator_bus.h"
#include "estimator_task.h"
#include "ins_task.h"
#include "logger_bus.h"
#include "logger_task.h"
#include "system_alignment.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_flight_recovery.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_health.h"
#include "system_imu_if.h"
#include "system_inertial.h"
#include "system_lifecycle.h"
#include "system_log_sink_if.h"
#include "system_storage_if.h"
#include "system_output_if.h"
#include "system_profile.h"
#include "system_startup.h"
#include "system_user_config.h"
#include "task.h"
#include "test_common.h"

#define TEST_LOGGER_TIME_STEP_US       300000ULL
#define TEST_LOGGER_RETRY_ADVANCE_US  1000000ULL
#define TEST_START_REQUEST_ID              91U
#define TEST_STARTUP_DEVICE_COUNT           2U
#define TEST_STARTUP_EVENT_COUNT           \
    (2U + (5U * TEST_STARTUP_DEVICE_COUNT))
#define TEST_SERIALIZED_EVENT_CAPACITY          32U
#define TEST_LOGGER_QUEUE_CAPACITY               8U

static jmp_buf s_task_exit;
static uint32_t s_delay_count;
static uint32_t s_delay_limit;
static uint8_t s_enable_sink_after_first_delay;
static uint8_t s_disable_sink_after_first_delay;
static uint8_t s_enable_event_after_first_delay;
static uint8_t s_complete_startup_after_delay;
static uint32_t s_first_delay_ticks;

static uint8_t s_ready;
static uint8_t s_mission_started;
static uint64_t s_now_us;
static uint32_t s_abort_count;
static uint32_t s_system_config_push_count;
static uint32_t s_mission_config_push_count;
static uint32_t s_decoder_profile_push_count;
static uint32_t s_initial_state_push_count;
static uint32_t s_calibration_result_push_count;
static FlightLogCalibrationResultRecord s_calibration_result_record;
static uint32_t s_event_push_count;
static uint32_t s_guard_sequence;
static uint8_t s_calibration_diagnostic_logged;
static uint32_t s_deploy_event_push_count;
static uint32_t s_landing_event_push_count;
static uint32_t s_finalization_arm_count;
static uint64_t s_finalization_landing_timestamp_us;
static uint64_t s_finalization_deadline_us;
static LoggerBusFinalizationState s_finalization_state;
static LoggerBusStartupState s_startup_state;
static FlightLogRecord s_logger_records[TEST_LOGGER_QUEUE_CAPACITY];
static uint8_t s_logger_record_count;
static uint8_t s_logger_record_index;
static SystemFlightRecoveryStatus s_flight_recovery_status;
static LoggerBusResult s_system_config_push_result;
static LoggerBusResult s_mission_config_push_result;
static LoggerBusResult s_initial_state_push_result;
static LoggerBusResult s_event_push_result;

static uint8_t s_log_sink_available;
static uint8_t s_mission_directory_available;
static SystemDeviceResult s_sink_init_result;
static uint32_t s_sink_init_count;
static uint32_t s_sink_begin_count;
static uint32_t s_sink_write_count;
static uint32_t s_sink_flush_count;
static uint32_t s_sink_end_count;
static uint32_t s_landing_critical_flush_count;
static uint8_t s_fail_final_flush_once;
static uint8_t s_short_write_once;
static uint32_t s_final_flush_failure_count;
static FlightLogEventId s_last_serialized_event;
static uint32_t s_header_serialize_count;
static uint32_t s_record_serialize_count;
static FlightLogEventId s_serialized_events[TEST_SERIALIZED_EVENT_CAPACITY];
static SystemStartupReport s_startup_report;

void vTaskDelay(TickType_t ticks)
{
    if (s_delay_count == 0U) { s_first_delay_ticks = ticks; }
    s_delay_count++;
    if (s_complete_startup_after_delay != 0U && s_delay_count == 2U)
    { s_startup_report.completed = 1U; }
    if ((s_enable_sink_after_first_delay != 0U) && (s_delay_count == 1U))
    {
        s_sink_init_result = SYSTEM_DEVICE_OK;
        s_now_us += TEST_LOGGER_RETRY_ADVANCE_US;
    }
    if ((s_disable_sink_after_first_delay != 0U) && (s_delay_count == 1U))
    { s_log_sink_available = 0U; }
    if ((s_enable_event_after_first_delay != 0U) && (s_delay_count == 1U))
    {
        s_event_push_result = LOGGER_BUS_RESULT_OK;
    }
    if (s_delay_count >= s_delay_limit)
    {
        longjmp(s_task_exit, 1);
    }
}

uint8_t SystemHealth_IsReady(void)
{
    return s_ready;
}

void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot)
{
    if (snapshot != NULL)
    {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        snapshot->ready = s_ready;
        snapshot->attitude_status = SYSTEM_HEALTH_ATTITUDE_READY;
    }
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    s_now_us += TEST_LOGGER_TIME_STEP_US;
    return s_now_us;
}

uint8_t SystemTime_IsMissionStarted(void)
{
    return s_mission_started;
}

uint64_t SystemTime_GetMissionUs(void)
{
    return s_now_us;
}

void SystemTime_MissionStart(uint64_t timestamp_us)
{
    (void)timestamp_us;
    s_mission_started = 1U;
}

void SystemTime_MissionStop(uint64_t timestamp_us)
{
    (void)timestamp_us;
    s_mission_started = 0U;
}

void SystemTime_MissionReset(void)
{
    s_mission_started = 0U;
}

void SystemProfile_Freeze(void) {}
void SystemProfile_UnfreezeForRollback(void) {}
void SystemLogPolicy_Freeze(void) {}
void SystemLogPolicy_UnfreezeForRollback(void) {}
void SystemNavigationProfile_Freeze(void) {}
void SystemNavigationProfile_UnfreezeForRollback(void) {}
void SystemEstimatorProfile_Freeze(void) {}
void SystemEstimatorProfile_UnfreezeForRollback(void) {}

static const SystemProfile s_profile =
{
    .profile_id = SYSTEM_PROFILE_ID
};

const SystemProfile *SystemProfile_Get(void)
{
    return &s_profile;
}

static SystemDeviceResult Mock_OutputInit(void)
{
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_OutputSetSafe(void)
{
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_OutputArm(uint8_t channel)
{
    (void)channel;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_OutputActivate(uint8_t channel,
                                                uint32_t duration_ms)
{
    (void)channel;
    (void)duration_ms;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_OutputDeactivate(uint8_t channel)
{
    (void)channel;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_OutputStatusGet(uint8_t channel,
                                                SystemOutputStatus *status)
{
    (void)channel;
    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(status, 0, sizeof(*status));
    return SYSTEM_DEVICE_OK;
}

const char *SystemOutput_NameGet(void) { return "Host Output"; }
SystemDeviceResult SystemOutput_Init(void) { return Mock_OutputInit(); }
SystemDeviceResult SystemOutput_SafeSet(void)
{ return Mock_OutputSetSafe(); }
SystemDeviceResult SystemOutput_Arm(uint8_t channel)
{ return Mock_OutputArm(channel); }
SystemDeviceResult SystemOutput_Activate(
    uint8_t channel, uint32_t duration_ms)
{ return Mock_OutputActivate(channel, duration_ms); }
SystemDeviceResult SystemOutput_Deactivate(uint8_t channel)
{ return Mock_OutputDeactivate(channel); }
SystemDeviceResult SystemOutput_StatusGet(
    uint8_t channel, SystemOutputStatus *status)
{ return Mock_OutputStatusGet(channel, status); }

SystemDeviceResult InsTask_PrepareStart(void)
{
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult EstimatorTask_FreezeOrigins(void)
{
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult EstimatorTask_PrepareNavigation(void)
{
    /* This logging fixture has no navigation producer or collected origins. */
    return SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult InsTask_InitializeMission(void)
{
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult EstimatorTask_InitializeMission(void)
{
    return SYSTEM_DEVICE_OK;
}

void InsTask_AbortMission(void)
{
    s_abort_count++;
}

void EstimatorTask_AbortMission(void)
{
    s_abort_count++;
}

void EstimatorTask_RollbackMissionStart(void)
{
    s_abort_count++;
}

void ImuSampleBus_Reset(void) {}
void EstimatorBus_ResetFlightData(void) {}
uint8_t EstimatorBus_PressureGetLatest(EstimatorPressureSnapshot *snapshot)
{
    (void)snapshot;
    return 0U;
}

void SystemCalibration_Process(void) {}

uint8_t SystemCalibration_IsReady(void)
{
    return 1U;
}

SystemDeviceResult SystemCalibration_StatusGet(SystemCalibrationStatus *status)
{
    uint8_t axis;

    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    status->mode = SYSTEM_CALIBRATION_MODE_NONE;
    status->state = SYSTEM_CALIBRATION_STATE_READY;
    status->ready = 1U;
    status->start_sequence = 1U;
    status->state_sequence = 1U;
    status->diagnostic_sequence = 1U;
    status->diagnostic_face = SYSTEM_CALIBRATION_FACE_NONE;
    status->diagnostic_reason = SYSTEM_CALIBRATION_WAIT_NO_STREAM;
    status->correction.mode = SYSTEM_CALIBRATION_MODE_NONE;
    status->correction.ready = 1U;
    for (axis = 0U; axis < 3U; axis++)
    {
        status->correction.accel_scale[axis] = 1.0f;
        status->correction.gyro_scale[axis] = 1.0f;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionGet(
    SystemCalibrationImuCorrection *correction)
{
    uint8_t index;

    if (correction == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(correction, 0, sizeof(*correction));
    correction->ready = 1U;
    for (index = 0U; index < 3U; index++)
    {
        correction->accel_scale[index] = 1.0f;
        correction->gyro_scale[index] = 1.0f;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionApply(
    const float raw_accel_b_mps2[3],
    const float raw_gyro_b_radps[3],
    const SystemCalibrationImuCorrection *correction,
    float corrected_accel_b_mps2[3],
    float corrected_gyro_b_radps[3])
{
    if ((raw_accel_b_mps2 == NULL) || (raw_gyro_b_radps == NULL) ||
        (correction == NULL) || (corrected_accel_b_mps2 == NULL) ||
        (corrected_gyro_b_radps == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memcpy(corrected_accel_b_mps2, raw_accel_b_mps2,
                 sizeof(float) * 3U);
    (void)memcpy(corrected_gyro_b_radps, raw_gyro_b_radps,
                 sizeof(float) * 3U);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{
    if (sample == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = s_now_us + TEST_LOGGER_TIME_STEP_US;
    sample->receive_timestamp_us = sample->sample_timestamp_us;
    sample->sequence = ++s_guard_sequence;
    sample->accel_b_mps2[1] = 9.80665f;
    sample->valid_mask = SYSTEM_INERTIAL_VALID_ACCEL |
                         SYSTEM_INERTIAL_VALID_GYRO;
    return SYSTEM_DEVICE_OK;
}

uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    if (snapshot != NULL) { (void)memset(snapshot, 0, sizeof(*snapshot)); }
    return 0U;
}

uint8_t Ins_GetLatestSnapshot(InsOutputSnapshot *snapshot)
{
    if (snapshot != NULL) { (void)memset(snapshot, 0, sizeof(*snapshot)); }
    return 0U;
}

SystemDeviceResult SystemFlightRecovery_Init(void)
{
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemFlightRecovery_Process(
    const SystemFlightRecoveryInput *input)
{
    return (input != NULL) ? SYSTEM_DEVICE_OK :
        SYSTEM_DEVICE_INVALID_ARGUMENT;
}

SystemDeviceResult SystemFlightRecovery_StatusGet(
    SystemFlightRecoveryStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *status = s_flight_recovery_status;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult InsTask_AlignmentReset(void)
{
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult EstimatorTask_OriginsReset(void)
{
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult InsTask_AttitudeAlignmentStatusGet(
    SystemAlignmentAttitudeStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    status->state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    status->source =
        SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION;
    status->attitude_ready = 1U;
    status->quaternion_valid = 1U;
    status->timestamp_us = s_now_us + TEST_LOGGER_TIME_STEP_US;
    status->receive_timestamp_us = status->timestamp_us;
    status->sequence = s_guard_sequence + 1U;
    status->quaternion_wxyz[0] = 1.0f;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult EstimatorTask_GnssAlignmentStatusGet(
    SystemAlignmentGnssStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    /* Normal lifecycle scenarios explicitly supply the now-required GNSS origin. */
    status->state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    status->supported = 1U;
    status->ready = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult EstimatorTask_BarometerAlignmentStatusGet(
    SystemAlignmentBarometerStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    status->state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    status->supported = 1U;
    status->ready = 1U;
    return SYSTEM_DEVICE_OK;
}

uint8_t Ins_GetAlignmentSnapshot(InsAlignmentSnapshot *snapshot)
{
    if (snapshot == NULL)
    {
        return 0U;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->q_nb[0] = 1.0f;
    snapshot->sample_count = 100U;
    snapshot->valid = 1U;
    return 1U;
}

uint8_t Ins_GetInitialAttitude(float q_nb[4])
{
    if (q_nb == NULL)
    {
        return 0U;
    }
    q_nb[0] = 1.0f;
    q_nb[1] = 0.0f;
    q_nb[2] = 0.0f;
    q_nb[3] = 0.0f;
    return 1U;
}

uint8_t Estimator_GetInitialStateSnapshot(
    EstimatorInitialStateSnapshot *snapshot)
{
    if (snapshot == NULL)
    {
        return 0U;
    }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->valid = 1U;
    return 1U;
}

LoggerBusResult LoggerBus_SystemConfigPush(uint64_t timestamp_us)
{
    (void)timestamp_us;
    s_system_config_push_count++;
    return s_system_config_push_result;
}

LoggerBusResult LoggerBus_MissionConfigPush(uint64_t timestamp_us)
{
    (void)timestamp_us;
    s_mission_config_push_count++;
    return s_mission_config_push_result;
}

LoggerBusResult LoggerBus_StreamingReady(void)
{
    if (LoggerBus_Count() == 0U) { s_startup_state = LOGGER_STREAMING_READY; }
    return LoggerBus_Count() == 0U ? LOGGER_BUS_RESULT_OK : LOGGER_BUS_RESULT_FULL;
}

LoggerBusStartupState LoggerBus_StartupStateGet(void) { return s_startup_state; }

LoggerBusResult LoggerBus_DecoderProfileDescriptorPush(uint64_t timestamp_us)
{
    (void)timestamp_us;
    s_decoder_profile_push_count++;
    return LOGGER_BUS_RESULT_OK;
}

LoggerBusResult LoggerBus_InitialStatePush(
    uint64_t timestamp_us,
    const FlightLogInitialStateRecord *record)
{
    (void)timestamp_us;
    if (record == NULL)
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    s_initial_state_push_count++;
    return s_initial_state_push_result;
}

LoggerBusResult LoggerBus_CalibrationResultPush(
    uint64_t timestamp_us,
    const FlightLogCalibrationResultRecord *record)
{
    (void)timestamp_us;
    if (record == NULL)
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    s_calibration_result_record = *record;
    s_calibration_result_push_count++;
    return LOGGER_BUS_RESULT_OK;
}

LoggerBusResult LoggerBus_AlignmentResultPush(
    uint64_t timestamp_us,
    const FlightLogAlignmentResultRecord *record)
{
    (void)timestamp_us;
    return (record != NULL) ? LOGGER_BUS_RESULT_OK : LOGGER_BUS_RESULT_BAD_PARAM;
}

LoggerBusResult LoggerBus_EventPush(uint64_t timestamp_us,
                                    FlightLogEventId event_id,
                                    uint32_t arg0,
                                    uint32_t arg1)
{
    (void)timestamp_us;
    (void)arg0;
    (void)arg1;
    if (event_id == FLIGHT_LOG_EVENT_IMU_BIAS_WAIT)
    {
        s_calibration_diagnostic_logged = 1U;
    }
    if (event_id == FLIGHT_LOG_EVENT_PARACHUTE_DEPLOY)
    {
        s_deploy_event_push_count++;
    }
    if (event_id == FLIGHT_LOG_EVENT_LANDING)
    {
        s_landing_event_push_count++;
    }
    s_event_push_count++;
    return s_event_push_result;
}

LoggerBusResult LoggerBus_FinalizationArm(uint64_t landing_timestamp_us)
{
    s_finalization_arm_count++;
    s_finalization_landing_timestamp_us = landing_timestamp_us;
    if (s_finalization_state == LOGGER_BUS_FINALIZATION_IDLE)
    {
        s_finalization_deadline_us = landing_timestamp_us +
            ((uint64_t)SYSTEM_LOG_POST_LANDING_GRACE_MS * 1000ULL);
        s_finalization_state = LOGGER_BUS_FINALIZATION_ARMED;
        return LOGGER_BUS_RESULT_OK;
    }
    return (s_finalization_state == LOGGER_BUS_FINALIZATION_ARMED) ?
        LOGGER_BUS_RESULT_OK : LOGGER_BUS_RESULT_BAD_STATE;
}

LoggerBusFinalizationState LoggerBus_FinalizationProcess(uint64_t now_us)
{
    if ((s_finalization_state == LOGGER_BUS_FINALIZATION_ARMED) &&
        (now_us >= s_finalization_deadline_us))
    {
        s_finalization_state = LOGGER_BUS_FINALIZATION_DRAINING;
    }
    return s_finalization_state;
}

void LoggerBus_FinalizationComplete(void)
{
    if (s_finalization_state == LOGGER_BUS_FINALIZATION_DRAINING)
    {
        s_finalization_state = LOGGER_BUS_FINALIZATION_FINALIZED;
    }
}

LoggerBusFinalizationState LoggerBus_FinalizationStateGet(void)
{
    return s_finalization_state;
}

LoggerBusResult LoggerBus_NextPop(FlightLogRecord *record)
{
    if (record == NULL)
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    if (s_logger_record_index >= s_logger_record_count)
    {
        return LOGGER_BUS_RESULT_EMPTY;
    }
    *record = s_logger_records[s_logger_record_index];
    s_logger_record_index++;
    return LOGGER_BUS_RESULT_OK;
}

uint16_t LoggerBus_Count(void)
{
    return (uint16_t)(s_logger_record_count - s_logger_record_index);
}

static SystemDeviceResult Mock_LogInit(void)
{
    s_sink_init_count++;
    return s_sink_init_result;
}

static SystemDeviceResult Mock_LogSessionBegin(
    const SystemLogSessionInfo *session)
{
    if (session == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    s_sink_begin_count++;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_LogWrite(const uint8_t *data,
                                         uint32_t length,
                                         uint32_t *written_length)
{
    if ((data == NULL) || (length == 0U) || (written_length == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    s_sink_write_count++;
    if (s_short_write_once != 0U && s_sink_write_count > 1U)
    {
        s_short_write_once = 0U;
        *written_length = length / 2U;
        return SYSTEM_DEVICE_IO_ERROR;
    }
    *written_length = length;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_LogFlush(void)
{
    s_sink_flush_count++;
    if (s_last_serialized_event == FLIGHT_LOG_EVENT_LANDING)
    {
        s_landing_critical_flush_count++;
    }
    if ((s_fail_final_flush_once != 0U) &&
        (s_finalization_state == LOGGER_BUS_FINALIZATION_DRAINING) &&
        (LoggerBus_Count() == 0U))
    {
        s_fail_final_flush_once = 0U;
        s_final_flush_failure_count++;
        return SYSTEM_DEVICE_IO_ERROR;
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_LogSessionEnd(void)
{
    s_sink_end_count++;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_LogHealthGet(SystemLogSinkHealth *health)
{
    if (health == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = 1U;
    health->session_active = 1U;
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    health->initialized = s_log_sink_available;
    health->mounted = s_log_sink_available;
    health->healthy = s_log_sink_available;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_MissionIdGet(uint32_t *mission_id)
{
    if (mission_id == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mission_id = ((s_log_sink_available != 0U) &&
        (s_mission_directory_available != 0U)) ? 1U : 0U;
    return (*mission_id != 0U) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

const char *SystemLogSink_NameGet(void) { return "Host TF"; }
SystemDeviceResult SystemLogSink_Init(void)
{
    return (s_log_sink_available != 0U) ?
        Mock_LogInit() : SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemLogSink_SessionBegin(
    const SystemLogSessionInfo *session)
{
    return (s_log_sink_available != 0U) ?
        Mock_LogSessionBegin(session) : SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemLogSink_Write(
    const uint8_t *data, uint32_t length, uint32_t *written_length)
{
    return (s_log_sink_available != 0U) ?
        Mock_LogWrite(data, length, written_length) :
        SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemLogSink_Flush(void)
{
    return (s_log_sink_available != 0U) ?
        Mock_LogFlush() : SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemLogSink_SessionEnd(void)
{
    return (s_log_sink_available != 0U) ?
        Mock_LogSessionEnd() : SYSTEM_DEVICE_UNSUPPORTED;
}
SystemDeviceResult SystemLogSink_HealthGet(SystemLogSinkHealth *health)
{
    return (s_log_sink_available != 0U) ?
        Mock_LogHealthGet(health) : SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Test_AttitudeCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_HW_QUAT_CAP_OUTPUT;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_ImuCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_GNSS_CAP_POSITION;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_VALID_PRESSURE | SYSTEM_BARO_VALID_ALTITUDE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(uint32_t *mask)
{ return Test_AttitudeCapabilitiesGet(mask); }
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->quaternion_wxyz[0] = 1.0f;
    sample->valid = 1U;
    sample->normalized = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *mask)
{ return Test_ImuCapabilitiesGet(mask); }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *mask)
{ return Test_GnssCapabilitiesGet(mask); }
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *mask)
{ return Test_BarometerCapabilitiesGet(mask); }

const SystemStartupReport *SystemStartup_GetReport(void)
{
    return &s_startup_report;
}

void SystemIndicator_Process(void)
{
}

FlightLogSerializeResult FlightLog_FileHeaderSerialize(
    const FlightLogFileHeaderInfo *info,
    uint8_t *buffer,
    uint16_t buffer_capacity,
    uint16_t *serialized_size)
{
    if ((info == NULL) || (buffer == NULL) || (buffer_capacity == 0U) ||
        (serialized_size == NULL))
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_PARAM;
    }
    buffer[0] = 0x53U;
    *serialized_size = 1U;
    s_header_serialize_count++;
    return FLIGHT_LOG_SERIALIZE_RESULT_OK;
}

FlightLogSerializeResult FlightLog_RecordSerialize(
    const FlightLogRecord *record,
    uint32_t record_sequence,
    uint8_t *buffer,
    uint16_t buffer_capacity,
    uint16_t *serialized_size)
{
    (void)record_sequence;
    if ((record == NULL) || (buffer == NULL) || (buffer_capacity == 0U) ||
        (serialized_size == NULL))
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_PARAM;
    }
    if ((record->record_type != FLIGHT_LOG_RECORD_EVENT) ||
        (s_record_serialize_count >= TEST_SERIALIZED_EVENT_CAPACITY))
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_TYPE;
    }
    s_serialized_events[s_record_serialize_count] =
        record->payload.event.event_id;
    s_last_serialized_event = record->payload.event.event_id;
    s_record_serialize_count++;
    buffer[0] = (uint8_t)record->payload.event.event_id;
    *serialized_size = 1U;
    return FLIGHT_LOG_SERIALIZE_RESULT_OK;
}

static void Test_StateReset(void)
{
    s_delay_count = 0U;
    s_delay_limit = 1U;
    s_enable_sink_after_first_delay = 0U;
    s_disable_sink_after_first_delay = 0U;
    s_complete_startup_after_delay = 0U;
    s_first_delay_ticks = 0U;
    s_startup_state = LOGGER_BOOTSTRAP;
    s_ready = 1U;
    s_mission_started = 0U;
    s_now_us = 0U;
    s_abort_count = 0U;
    s_system_config_push_count = 0U;
    s_mission_config_push_count = 0U;
    s_decoder_profile_push_count = 0U;
    s_initial_state_push_count = 0U;
    s_calibration_result_push_count = 0U;
    (void)memset(&s_calibration_result_record, 0,
                 sizeof(s_calibration_result_record));
    s_event_push_count = 0U;
    s_guard_sequence = 0U;
    s_calibration_diagnostic_logged = 0U;
    s_system_config_push_result = LOGGER_BUS_RESULT_OK;
    s_mission_config_push_result = LOGGER_BUS_RESULT_OK;
    s_initial_state_push_result = LOGGER_BUS_RESULT_OK;
    s_event_push_result = LOGGER_BUS_RESULT_OK;
    s_enable_event_after_first_delay = 0U;
    s_deploy_event_push_count = 0U;
    s_landing_event_push_count = 0U;
    s_finalization_arm_count = 0U;
    s_finalization_landing_timestamp_us = 0ULL;
    s_finalization_deadline_us = 0ULL;
    s_finalization_state = LOGGER_BUS_FINALIZATION_IDLE;
    (void)memset(s_logger_records, 0, sizeof(s_logger_records));
    s_logger_record_count = 0U;
    s_logger_record_index = 0U;
    (void)memset(&s_flight_recovery_status, 0,
                 sizeof(s_flight_recovery_status));
    s_log_sink_available = 0U;
    s_mission_directory_available = 1U;
    s_sink_init_result = SYSTEM_DEVICE_OK;
    s_sink_init_count = 0U;
    s_sink_begin_count = 0U;
    s_sink_write_count = 0U;
    s_sink_flush_count = 0U;
    s_sink_end_count = 0U;
    s_landing_critical_flush_count = 0U;
    s_fail_final_flush_once = 0U;
    s_final_flush_failure_count = 0U;
    s_last_serialized_event = (FlightLogEventId)0U;
    s_header_serialize_count = 0U;
    s_record_serialize_count = 0U;
    (void)memset(s_serialized_events, 0, sizeof(s_serialized_events));
    (void)memset(&s_startup_report, 0, sizeof(s_startup_report));
}

static void Test_LoggerEventQueuePush(uint64_t timestamp_us,
                                      FlightLogEventId event_id)
{
    FlightLogRecord *record;

    TEST_CHECK(s_logger_record_count < TEST_LOGGER_QUEUE_CAPACITY);
    if (s_logger_record_count >= TEST_LOGGER_QUEUE_CAPACITY)
    {
        return;
    }
    record = &s_logger_records[s_logger_record_count];
    (void)memset(record, 0, sizeof(*record));
    record->record_type = FLIGHT_LOG_RECORD_EVENT;
    record->timestamp_us = timestamp_us;
    record->payload.event.event_id = event_id;
    s_logger_record_count++;
}

static void Test_FlightTaskRunWithStorage(uint8_t storage_ready)
{
    SystemLifecycleStartRequest request;

    /* FlightTask begins after the LoggerTask has admitted a writable session. */
    s_log_sink_available = storage_ready;
    s_startup_state = (storage_ready != 0U) ?
        LOGGER_STREAMING_READY : LOGGER_BOOTSTRAP;
    SystemLifecycle_Init();
    SystemAlignment_Init();
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterSelfTest() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterPreflight() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    request.source = SYSTEM_START_SOURCE_CONSOLE;
    request.request_id = TEST_START_REQUEST_ID;
    TEST_CHECK(SystemLifecycle_SubmitStart(&request) == SYSTEM_DEVICE_OK);
    if (setjmp(s_task_exit) == 0)
    {
        AppTask_Flight(NULL);
    }
}

static void Test_FlightTaskRun(void)
{
    Test_FlightTaskRunWithStorage(1U);
}

static void Test_PostStartStorageLossAndFullBusKeepsFlight(void)
{
    Test_StateReset();
    s_disable_sink_after_first_delay = 1U;
    s_system_config_push_result = LOGGER_BUS_RESULT_FULL;
    s_mission_config_push_result = LOGGER_BUS_RESULT_FULL;
    s_initial_state_push_result = LOGGER_BUS_RESULT_FULL;
    s_event_push_result = LOGGER_BUS_RESULT_FULL;
    Test_FlightTaskRun();

    TEST_CHECK(s_log_sink_available == 0U);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(SystemLifecycle_IsConfigurationLocked() != 0U);
    TEST_CHECK(s_mission_started != 0U);
    TEST_CHECK(s_system_config_push_count == 1U);
    TEST_CHECK(s_mission_config_push_count == 1U);
    TEST_CHECK(s_initial_state_push_count == 1U);
    TEST_CHECK(s_event_push_count >= 3U);
    TEST_CHECK(s_calibration_diagnostic_logged != 0U);
    TEST_CHECK(s_abort_count == 0U);
}

LoggerBusResult LoggerBus_LandingDiagnosticPush(
    uint64_t timestamp_us, const FlightLogLandingDiagnosticRecord *record)
{
    (void)timestamp_us;
    return (record != NULL) ? LOGGER_BUS_RESULT_OK : LOGGER_BUS_RESULT_BAD_PARAM;
}

static void Test_NoneCalibrationResultSnapshot(void)
{
    uint8_t axis;

    Test_StateReset();
    Test_FlightTaskRun();

    TEST_CHECK(s_calibration_result_push_count == 1U);
    TEST_CHECK(s_calibration_result_record.source_id ==
               FLIGHT_LOG_PRIMARY_INERTIAL_SOURCE_ID);
    TEST_CHECK(s_calibration_result_record.virtual_imu_id ==
               FLIGHT_LOG_PRIMARY_VIRTUAL_IMU_ID);
    TEST_CHECK(s_calibration_result_record.mode ==
               (uint8_t)SYSTEM_CALIBRATION_MODE_NONE);
    TEST_CHECK(s_calibration_result_record.state ==
               (uint8_t)SYSTEM_CALIBRATION_STATE_READY);
    TEST_CHECK(s_calibration_result_record.ready == 1U);
    TEST_CHECK(s_calibration_result_record.completed_face_mask == 0U);
    TEST_CHECK(s_calibration_result_record.samples == 0U);
    TEST_CHECK(s_calibration_result_record.reject_count == 0U);
    TEST_CHECK(s_calibration_result_record.retry_count == 0U);
    TEST_CHECK(s_calibration_result_record.start_sequence == 1U);
    for (axis = 0U; axis < 3U; axis++)
    {
        TEST_CHECK_NEAR(
            s_calibration_result_record.accel_bias_mps2[axis],
            0.0f, 1.0e-7f);
        TEST_CHECK_NEAR(
            s_calibration_result_record.gyro_bias_radps[axis],
            0.0f, 1.0e-7f);
        TEST_CHECK_NEAR(
            s_calibration_result_record.accel_scale[axis],
            1.0f, 1.0e-7f);
        TEST_CHECK_NEAR(
            s_calibration_result_record.gyro_scale[axis],
            1.0f, 1.0e-7f);
    }
}

static void Test_StartRequiresStorage(void)
{
    SystemLifecycleStartDiagnostic diagnostic;
    Test_StateReset();
    Test_FlightTaskRunWithStorage(0U);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_READY);
    TEST_CHECK(s_mission_started == 0U);
    TEST_CHECK(s_system_config_push_count == 0U);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_CONSOLE, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.reason ==
        SYSTEM_START_REASON_STORAGE_NOT_READY);
}

static void Test_StartRequiresMissionDirectory(void)
{
    SystemLifecycleStartDiagnostic diagnostic;
    Test_StateReset();
    s_mission_directory_available = 0U;
    Test_FlightTaskRunWithStorage(1U);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_READY);
    TEST_CHECK(s_mission_started == 0U);
    TEST_CHECK(SystemLifecycle_GetLastStartDiagnostic(
        SYSTEM_START_SOURCE_CONSOLE, &diagnostic) != 0U);
    TEST_CHECK(diagnostic.response.reason ==
        SYSTEM_START_REASON_STORAGE_NOT_READY);
}

static void Test_StartRecordFailureDoesNotRollback(void)
{
    Test_StateReset();
    s_initial_state_push_result = LOGGER_BUS_RESULT_BAD_PARAM;
    s_event_push_result = LOGGER_BUS_RESULT_BAD_PARAM;
    Test_FlightTaskRun();

    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(s_mission_started != 0U);
    TEST_CHECK(s_system_config_push_count == 1U);
    TEST_CHECK(s_mission_config_push_count == 1U);
    TEST_CHECK(s_initial_state_push_count == 1U);
    TEST_CHECK(s_event_push_count >= 3U);
    TEST_CHECK(s_abort_count == 0U);
}

static void Test_PostStartMissingTfDoesNotChangeFlightState(void)
{
    Test_StateReset();
    Test_FlightTaskRun();
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);

    s_delay_count = 0U;
    s_delay_limit = 1U;
    s_log_sink_available = 0U;
    if (setjmp(s_task_exit) == 0)
    {
        AppTask_Logger(NULL);
    }
    TEST_CHECK(s_sink_init_count == 0U);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(s_mission_started != 0U);
}

static void Test_FlightRecoveryEventRetry(void)
{
    Test_StateReset();
    s_event_push_result = LOGGER_BUS_RESULT_FULL;
    s_enable_event_after_first_delay = 1U;
    s_delay_limit = 3U;
    s_flight_recovery_status.deploy_event_sequence = 1U;
    s_flight_recovery_status.deploy_event_timestamp_us = 123U;
    s_flight_recovery_status.deploy_trigger_mask =
        SYSTEM_DEPLOY_TRIGGER_APOGEE_VZ;
    s_flight_recovery_status.deploy_trigger_value = -2.5f;
    s_flight_recovery_status.landing_event_sequence = 1U;
    s_flight_recovery_status.landing_event_timestamp_us = 456U;
    Test_FlightTaskRun();

    TEST_CHECK(s_deploy_event_push_count == 2U);
    TEST_CHECK(s_landing_event_push_count == 2U);
    TEST_CHECK(s_finalization_arm_count == 1U);
    TEST_CHECK(s_finalization_landing_timestamp_us == 456U);
    TEST_CHECK(s_finalization_state == LOGGER_BUS_FINALIZATION_ARMED);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
}

static void Test_LoggerFinalizesAfterLandingGrace(void)
{
    const uint64_t landing_timestamp_us = 1000000ULL;

    Test_StateReset();
    s_log_sink_available = 1U;
    s_startup_report.completed = 1U;
    s_startup_report.passed = 1U;
    TEST_CHECK(LoggerBus_FinalizationArm(landing_timestamp_us) ==
               LOGGER_BUS_RESULT_OK);
    Test_LoggerEventQueuePush(landing_timestamp_us,
                              FLIGHT_LOG_EVENT_LANDING);
    Test_LoggerEventQueuePush(landing_timestamp_us + 500000ULL,
                              FLIGHT_LOG_EVENT_BOOT);
    s_delay_limit = 3U;

    if (setjmp(s_task_exit) == 0)
    {
        AppTask_Logger(NULL);
    }

    TEST_CHECK(s_logger_record_index == s_logger_record_count);
    TEST_CHECK(s_record_serialize_count == 2U);
    TEST_CHECK(s_serialized_events[0] == FLIGHT_LOG_EVENT_LANDING);
    TEST_CHECK(s_serialized_events[1] == FLIGHT_LOG_EVENT_BOOT);
    TEST_CHECK(s_landing_critical_flush_count >= 1U);
    TEST_CHECK(s_sink_flush_count >= 3U);
    TEST_CHECK(s_sink_end_count == 1U);
    TEST_CHECK(s_sink_begin_count == 1U);
    TEST_CHECK(s_decoder_profile_push_count == 1U);
    TEST_CHECK(s_finalization_state == LOGGER_BUS_FINALIZATION_FINALIZED);
}

static void Test_FinalFlushFailureLatchesWithoutPrematureFinalize(void)
{
    const uint64_t landing_timestamp_us = 1000000ULL;

    Test_StateReset();
    s_log_sink_available = 1U;
    s_startup_report.completed = 1U;
    s_startup_report.passed = 1U;
    TEST_CHECK(LoggerBus_FinalizationArm(landing_timestamp_us) ==
               LOGGER_BUS_RESULT_OK);
    Test_LoggerEventQueuePush(landing_timestamp_us,
                              FLIGHT_LOG_EVENT_LANDING);
    s_fail_final_flush_once = 1U;
    s_delay_limit = 7U;

    if (setjmp(s_task_exit) == 0)
    {
        AppTask_Logger(NULL);
    }

    TEST_CHECK(s_final_flush_failure_count == 1U);
    TEST_CHECK(s_finalization_state == LOGGER_BUS_FINALIZATION_DRAINING);
    TEST_CHECK(s_sink_end_count == 1U);
    TEST_CHECK(s_sink_begin_count == 1U);
    LoggerTaskDiagnostics diagnostics;
    TEST_CHECK(LoggerTask_DiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK);
    TEST_CHECK(diagnostics.io_fault == 1U);
    TEST_CHECK(diagnostics.flush_failure_count == 1U);
}

uint32_t LoggerBus_OverflowCountGet(void) { return 0U; }

static void Test_PartialWriteNeverReplaysAggregate(void)
{
    LoggerTaskDiagnostics diagnostics;
    Test_StateReset();
    s_log_sink_available = 1U;
    s_startup_report.completed = 1U;
    s_startup_report.passed = 1U;
    s_short_write_once = 1U;
    s_delay_limit = 10U;
    if (setjmp(s_task_exit) == 0) { AppTask_Logger(NULL); }
    TEST_CHECK(s_short_write_once == 0U);
    TEST_CHECK(s_sink_write_count == 2U);
    TEST_CHECK(s_sink_begin_count == 1U);
    TEST_CHECK(s_sink_end_count == 1U);
    TEST_CHECK(LoggerTask_DiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK);
    TEST_CHECK(diagnostics.io_fault == 1U);
    TEST_CHECK(diagnostics.append_failure_count == 1U);
    TEST_CHECK(diagnostics.discarded_bytes > 0U);
}

static void Test_StartupReportBackfillsAfterLateOpen(void)
{
    uint32_t index;

    Test_StateReset();
    s_log_sink_available = 1U;
    s_sink_init_result = SYSTEM_DEVICE_IO_ERROR;
    s_enable_sink_after_first_delay = 1U;
    s_delay_limit = 4U;
    s_startup_report.completed = 1U;
    s_startup_report.passed = 1U;
    s_startup_report.mission_capable = 1U;
    s_startup_report.degraded = 1U;
    s_startup_report.warning_mask = 0x2U;
    s_startup_report.device_count = TEST_STARTUP_DEVICE_COUNT;
    s_startup_report.timestamp_us = 123456ULL;
    for (index = 0U; index < TEST_STARTUP_DEVICE_COUNT; index++)
    {
        SystemStartupDeviceReport *device =
            &s_startup_report.devices[index];
        device->device_id = (SystemStartupDeviceId)index;
        device->device_name = (index == 0U) ? "IMU" : "GNSS";
        device->model_name = (index == 0U) ? "JY901B" : "NEO-M9N";
        device->present = 1U;
        device->capability_mask = 1UL << index;
        device->init_result = SYSTEM_DEVICE_OK;
        device->start_result = SYSTEM_DEVICE_OK;
        device->config_result = SYSTEM_DEVICE_OK;
        device->persist_result = SYSTEM_DEVICE_OK;
        device->verify_result = SYSTEM_DEVICE_OK;
        device->communication_result = SYSTEM_DEVICE_OK;
    }

    if (setjmp(s_task_exit) == 0)
    {
        AppTask_Logger(NULL);
    }

    TEST_CHECK(s_sink_init_count >= 2U);
    TEST_CHECK(s_sink_begin_count == 1U);
    TEST_CHECK(s_decoder_profile_push_count == 1U);
    TEST_CHECK(s_header_serialize_count == 1U);
    TEST_CHECK(s_record_serialize_count == TEST_STARTUP_EVENT_COUNT);
    TEST_CHECK(s_serialized_events[0] ==
               FLIGHT_LOG_EVENT_SELF_TEST_COMPLETE);
    for (index = 0U; index < TEST_STARTUP_DEVICE_COUNT; index++)
    {
        uint32_t event_base = 1U + (index * 5U);
        TEST_CHECK(s_serialized_events[event_base] ==
                   FLIGHT_LOG_EVENT_STARTUP_DEVICE_RESULT);
        TEST_CHECK(s_serialized_events[event_base + 1U] ==
                   FLIGHT_LOG_EVENT_STARTUP_CONFIG_MASKS);
        TEST_CHECK(s_serialized_events[event_base + 2U] ==
                   FLIGHT_LOG_EVENT_STARTUP_CONFIG_FAILURES);
        TEST_CHECK(s_serialized_events[event_base + 3U] ==
                   FLIGHT_LOG_EVENT_STARTUP_DEVICE_DETAIL);
        TEST_CHECK(s_serialized_events[event_base + 4U] ==
                   FLIGHT_LOG_EVENT_STARTUP_DEVICE_NAMES);
    }
    TEST_CHECK(s_serialized_events[TEST_STARTUP_EVENT_COUNT - 1U] ==
               FLIGHT_LOG_EVENT_GNSS_CONFIG_TRANSACTION);
    TEST_CHECK(s_sink_write_count >= 3U);
    TEST_CHECK(s_sink_flush_count >= 3U);
    TEST_CHECK(s_sink_end_count == 0U);
}

static void Test_IncompleteStartupKeepsSession(void)
{
    LoggerTaskDiagnostics diagnostics;
    Test_StateReset();
    s_log_sink_available = 1U;
    s_complete_startup_after_delay = 1U;
    s_delay_limit = 6U;
    if (setjmp(s_task_exit) == 0) { AppTask_Logger(NULL); }
    TEST_CHECK(s_first_delay_ticks == pdMS_TO_TICKS(2U));
    TEST_CHECK(s_sink_begin_count == 1U && s_sink_end_count == 0U);
    TEST_CHECK(s_record_serialize_count == 2U);
    TEST_CHECK(LoggerTask_DiagnosticsGet(&diagnostics) == SYSTEM_DEVICE_OK);
    TEST_CHECK(diagnostics.open_attempt_count == 1U && diagnostics.open_failure_count == 0U);
    TEST_CHECK(diagnostics.streaming_ready_us != 0ULL && diagnostics.io_fault == 0U);
}

int main(void)
{
    Test_StartRequiresStorage();
    Test_StartRequiresMissionDirectory();
    Test_PostStartStorageLossAndFullBusKeepsFlight();
    Test_NoneCalibrationResultSnapshot();
    Test_StartRecordFailureDoesNotRollback();
    Test_PostStartMissingTfDoesNotChangeFlightState();
    Test_FlightRecoveryEventRetry();
    Test_LoggerFinalizesAfterLandingGrace();
    Test_FinalFlushFailureLatchesWithoutPrematureFinalize();
    Test_PartialWriteNeverReplaysAggregate();
    Test_StartupReportBackfillsAfterLateOpen();
    Test_IncompleteStartupKeepsSession();
    return Test_Finish("lifecycle_logging");
}
