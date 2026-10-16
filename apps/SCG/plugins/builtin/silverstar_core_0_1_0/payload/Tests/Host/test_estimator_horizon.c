/* Actual KF6 task path, numerical kernels, health, queues and LoggerBus.
 * A frozen preflight frame and device/clock/lifecycle ports are CPU fixtures. */
#ifndef KF_HORIZON_TASK_SOURCE
#define KF_HORIZON_TASK_SOURCE "../../APP/Src/estimator_task.c"
#endif
#include KF_HORIZON_TASK_SOURCE
#include "test_common.h"
#include "host_platform_mock.h"
#include "system_log_policy.h"
#include "system_imu_if.h"
#include <stdlib.h>

_Static_assert(SYSTEM_FUSION_TIMING_MODE == 2U, "This scenario requires the actual KF horizon path");

static SystemGnssSample s_test_sample;
static uint8_t s_test_gnss_source;
static uint8_t s_test_imu_source;
static uint32_t s_test_generation;
static uint8_t s_test_invalid_dt;
static uint32_t s_test_requests;
static uint32_t s_test_completions;
static uint32_t s_test_rejections;
static uint32_t s_test_late;
static uint32_t s_test_faults;
static uint64_t s_test_operation[2048];
static uint8_t s_test_completed[2048];
static uint32_t s_test_unexpected_preflight_calls;
static FILE *s_test_wire;
static uint32_t s_test_wire_sequence;

/* This unit enters after preflight. These unavailable ports must never be used
 * by the exercised numerical/task path; complete mission preparation is tested
 * separately with the real INS/alignment implementations. */
uint8_t Ins_GetLatestSnapshot(InsOutputSnapshot *snapshot)
{ (void)snapshot; s_test_unexpected_preflight_calls++; return 0U; }
uint8_t Ins_GetInitialAttitude(float q_nb[4])
{ (void)q_nb; s_test_unexpected_preflight_calls++; return 0U; }
SystemDeviceResult InsTask_PrepareNavigation(const float q_nb[4])
{ (void)q_nb; s_test_unexpected_preflight_calls++; return SYSTEM_DEVICE_NOT_READY; }
uint8_t SystemAlignment_IsCollecting(void)
{ s_test_unexpected_preflight_calls++; return 0U; }
uint8_t SystemAlignment_IsReady(void)
{ s_test_unexpected_preflight_calls++; return 0U; }
SystemDeviceResult SystemAlignment_PreflightQuaternionGet(
    float quaternion_wxyz[4], SystemAlignmentPreflightAttitudeSource *source)
{
    (void)quaternion_wxyz; (void)source;
    s_test_unexpected_preflight_calls++; return SYSTEM_DEVICE_NOT_READY;
}
void vTaskDelay(TickType_t ticks)
{ (void)ticks; s_test_unexpected_preflight_calls++; }
const char *SystemBarometer_NameGet(void) { return "HostBarometer"; }

SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_FLIGHT; }
uint32_t SystemCalibration_GenerationGet(void) { return s_test_generation; }
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ *sample = s_test_sample; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{
    memset(time,0,sizeof(*time)); time->sequence = s_test_sample.sequence;
    time->time_of_week_ms = (uint32_t)(s_test_sample.sample_timestamp_us/1000ULL);
    return SYSTEM_DEVICE_OK;
}
const char *SystemGnss_NameGet(void) { return "HostGnss"; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = s_test_imu_source; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{
    if (s_test_gnss_source == UINT8_MAX) { return SYSTEM_DEVICE_NOT_READY; }
    *instance = s_test_gnss_source; return SYSTEM_DEVICE_OK;
}

static void HorizonTest_RecordsDrain(void)
{
    FlightLogRecord record, restored;
    while (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
    {
        uint8_t wire[284]; uint16_t size = 0U, consumed = 0U; uint32_t sequence = 0U;
        uint32_t encoded_sequence = s_test_wire_sequence++;
        TEST_CHECK(FlightLog_RecordSerialize(&record,encoded_sequence,wire,sizeof(wire),&size) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
        if (s_test_wire != NULL) { TEST_CHECK(fwrite(wire,1U,size,s_test_wire) == size); }
        TEST_CHECK(FlightLog_RecordDeserialize(wire,size,&restored,&sequence,&consumed) == FLIGHT_LOG_DESERIALIZE_RESULT_OK);
        TEST_CHECK(sequence == encoded_sequence && consumed == size && restored.record_type == record.record_type);
        TEST_CHECK(record.record_type != FLIGHT_LOG_RECORD_GNSS_MEASUREMENT && record.record_type != FLIGHT_LOG_RECORD_BARO_MEASUREMENT);
        if (record.record_type == FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT)
        {
            const FlightLogFusionHorizonMeasurementRecord *value = &record.payload.fusion_horizon_measurement;
            TEST_CHECK(value->algorithm_id == 1U && value->algorithm_revision == 2U && value->numerical_revision == 1U);
            TEST_CHECK(value->fusion_timing_mode == 2U && value->epoch == s_replay_epoch);
            TEST_CHECK(value->evaluation_timestamp_us == record.timestamp_us && value->operation_sequence < 2048U);
            if (value->phase == 0U)
            {
                s_test_requests++;
                TEST_CHECK(value->admitted == 0U && value->effective_update == 0U && value->application_timestamp_us == 0U);
                TEST_CHECK(value->update_result == 255U && value->nis == -1.0f);
                if (value->execution_result == SYSTEM_FUSION_EXEC_QUEUED)
                {
                    uint8_t found = 0U;
                    s_test_operation[value->operation_sequence] = value->measurement_timestamp_us;
                    for (uint16_t index = 0U; index < s_horizon_fusion.event_count; index++)
                    {
                        const NavigationKfHorizonEvent *queued = &s_horizon_fusion.event[index];
                        if (queued->operation_sequence == value->operation_sequence)
                        {
                            found = 1U;
                            TEST_CHECK(memcmp(value->prepared_variance,queued->variance,sizeof(value->prepared_variance)) == 0);
                        }
                    }
                    TEST_CHECK(found == 1U);
                }
                else { s_test_rejections++; }
                if (value->execution_result == SYSTEM_FUSION_EXEC_LATE) { s_test_late++; }
            }
            else
            {
                s_test_completions++;
                TEST_CHECK(value->phase == 1U && value->admitted == 1U && value->execution_result == SYSTEM_FUSION_EXEC_COMPLETE);
                TEST_CHECK(value->application_timestamp_us == value->measurement_timestamp_us);
                TEST_CHECK(value->application_timestamp_us == s_test_operation[value->operation_sequence]);
                TEST_CHECK(s_test_completed[value->operation_sequence] == 0U);
                s_test_completed[value->operation_sequence] = 1U;
                TEST_CHECK(isfinite(value->nis) && value->nis >= 0.0f && value->effective_variance[0] > 0.0f);
            }
        }
        if (record.record_type == FLIGHT_LOG_RECORD_FUSION_HORIZON_STATUS)
        {
            const FlightLogFusionHorizonStatusRecord *value = &record.payload.fusion_horizon_status;
            TEST_CHECK(value->algorithm_id == 1U && value->numerical_revision == 1U && value->fusion_timing_mode == 2U);
            TEST_CHECK(value->output_state_timestamp_us == value->output_covariance_timestamp_us);
            TEST_CHECK(value->output_state_timestamp_us == s_published_snapshot.timestamp_us);
            TEST_CHECK(value->horizon_initialized == s_horizon_fusion.initialized);
            TEST_CHECK(value->work_count <= NAV_KF_HORIZON_MAX_WORK);
            if (value->phase == 2U) { s_test_faults++; }
        }
    }
}

static void HorizonTest_Reset(void)
{
    const FlightLogRecordType streams[] = {FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT,
        FLIGHT_LOG_RECORD_FUSION_HORIZON_STATUS,FLIGHT_LOG_RECORD_ESTIMATOR_STEP,
        FLIGHT_LOG_RECORD_ESTIMATOR,FLIGHT_LOG_RECORD_KF6_FULL_P,FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC,
        FLIGHT_LOG_RECORD_INERTIAL_INCREMENT};
    HostPlatformMock_Reset(); TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK); TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    for (uint32_t i = 0U; i < sizeof(streams)/sizeof(streams[0]); i++)
    {
        SystemLogStreamConfig config;
        TEST_CHECK(SystemLogPolicy_StreamGet(streams[i],&config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U; config.decimation = 1U;
        if (config.policy == SSLOG_STREAM_POLICY_PERIODIC) { config.period_us = 1U; }
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    }
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    memset(&s_estimator,0,sizeof(s_estimator)); memset(&s_test_sample,0,sizeof(s_test_sample));
    s_test_imu_source = 0U; s_test_gnss_source = 0U; s_test_generation = 7U; s_test_invalid_dt = 0U;
    s_test_sample.position_usable = 1U; s_test_sample.online = 1U; s_test_sample.fix_type = 3U; s_test_sample.fix_ok = 1U;
    s_test_sample.supported_fields = 0x3FFU; s_test_sample.valid_fields = 0x3FFU;
    s_test_sample.valid_group_mask = 15U; s_test_sample.physical_valid_group_mask = 15U;
    s_test_sample.satellite_count = 16U; s_test_sample.velocity_valid_mask = 7U;
    s_test_sample.latitude_e7 = 300000000; s_test_sample.longitude_e7 = 1200000000;
    s_test_sample.horizontal_accuracy_m = 1.0f; s_test_sample.vertical_accuracy_m = 2.0f;
    s_test_sample.speed_accuracy_mps = .2f; s_test_sample.measurement_timestamp_trusted = 1U;
    for (uint32_t axis = 0U; axis < 3U; axis++) { s_test_sample.velocity_variance_m2ps2[axis] = .04f; }
    s_estimator.frozen_gnss = s_test_sample; s_estimator.gnss_origin_valid = 1U; s_estimator.gnss_fusion_enabled = 1U;
    s_estimator.baro_origin_valid = 1U; s_estimator.frozen_baro_altitude_m = 10.0f;
    s_estimator.baro_diagnostics.source_supported = 1U; s_estimator.q_nb[0] = 1.0f;
    s_estimator.last_gnss_source = UINT8_MAX;
    TEST_CHECK(GeoLocalFrame_Init(&s_estimator.gnss_frame,300000000,1200000000,0) != 0U);
    NavigationKf_Init(&s_estimator.kf); Estimator_KfProfileApply(SystemEstimatorProfile_Get());
    Estimator_FusionReset(); Estimator_KfRuntimeInitialize(1U); SystemNavigationHealth_Reset(0U);
    Estimator_SnapshotPublish(1000000ULL);
    /* The actual mission adapter logs its initialized estimator/P pair at0.
     * Exercise that owning writer too; never seed replay from a later output. */
    Estimator_LogPush(0U);
    s_test_wire_sequence = 0U;
    s_test_sample.receive_timestamp_us = UINT64_MAX;
    s_test_requests = 0U; s_test_completions = 0U; s_test_rejections = 0U; s_test_late = 0U; s_test_faults = 0U;
    memset(s_test_operation,0,sizeof(s_test_operation)); memset(s_test_completed,0,sizeof(s_test_completed));
}

static void HorizonTest_Receive(uint64_t now_us, uint32_t sequence, uint8_t valid)
{
    s_test_sample.receive_timestamp_us = now_us; s_test_sample.sample_timestamp_us = now_us-2500ULL;
    s_test_sample.sequence = sequence; s_test_sample.fix_ok = valid;
    s_test_sample.valid_group_mask = valid ? 15U : 0U; s_test_sample.physical_valid_group_mask = s_test_sample.valid_group_mask;
}

static void HorizonTest_Body(uint32_t cycle)
{
    SystemInertialIncrement input = {0};
    FlightLogInertialIncrementRecord raw = {0};
    input.timestamp_us = 1000000ULL+(uint64_t)cycle*5000ULL; input.sequence = cycle;
    input.dt_s = s_test_invalid_dt ? NAN : .005f;
    input.delta_velocity_b_sculling_corrected[2] = SYSTEM_KF_GRAVITY_MPS2*.005f;
    raw.interval_start_timestamp_us = input.timestamp_us-5000ULL;
    raw.interval_end_timestamp_us = input.timestamp_us; raw.sequence = input.sequence; raw.dt_s = input.dt_s;
    memcpy(raw.delta_theta_b_corrected,input.delta_theta_b_corrected,sizeof(raw.delta_theta_b_corrected));
    memcpy(raw.delta_velocity_b_sculling_corrected,input.delta_velocity_b_sculling_corrected,
        sizeof(raw.delta_velocity_b_sculling_corrected));
    /* Explicit CPU input production, outside the INS scheduler. */
    TEST_CHECK(LoggerBus_InertialIncrementPush(input.timestamp_us,
        SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO,&raw) == LOGGER_BUS_RESULT_OK);
    HostPlatformMock_TimeSetUs(input.timestamp_us);
    Estimator_PredictionProcess(&input);
}

static void HorizonTest_Run(uint32_t scenario)
{
    SystemNavigationGroupHealth health;
    NavigationKfContext before;
    const uint32_t end_cycle = (SYSTEM_FUSION_HORIZON_MS+4U)/5U+6U;
    const uint64_t end_us = 1000000ULL+(uint64_t)end_cycle*5000ULL;
    HorizonTest_Reset();
    if (scenario == 11U)
    {
        s_test_sample.satellite_count = 4U;
        s_test_sample.horizontal_accuracy_m = 1.234567f;
        s_test_sample.vertical_accuracy_m = 2.345678f;
        s_test_sample.speed_accuracy_mps = .234567f;
    }
    if (scenario == 9U || scenario == 10U)
    {
        EstimatorPressureSnapshot pressure = {0};
        s_test_gnss_source = UINT8_MAX;
        pressure.timestamp_us = 1002500ULL; pressure.receive_timestamp_us = 1005000ULL;
        pressure.sequence = 1U; pressure.altitude_m = 10.5f; pressure.variance_m2 = 1.0f;
        pressure.valid = 1U; pressure.healthy = 1U; pressure.measurement_timestamp_trusted = 1U;
        TEST_CHECK(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
        HorizonTest_Body(1U); HorizonTest_RecordsDrain();
        TEST_CHECK(s_test_requests == 1U && s_test_completions == 0U);
        if (scenario == 10U)
        {
            pressure.timestamp_us += 5000ULL; pressure.receive_timestamp_us += 5000ULL;
            pressure.sequence = 2U; pressure.valid = 0U;
            TEST_CHECK(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
            EstimatorPressureSnapshot received = {0};
            TEST_CHECK(EstimatorBus_PressureGetLatest(&received) == 0U);
            TEST_CHECK(EstimatorBus_PressureReceiptGetLatest(&received) == ESTIMATOR_BUS_RESULT_OK);
            TEST_CHECK(received.sequence == 2U && received.valid == 0U && received.receive_timestamp_us == pressure.receive_timestamp_us);
        }
        for (uint32_t cycle = 2U; cycle <= end_cycle; cycle++)
        { HorizonTest_Body(cycle); HorizonTest_RecordsDrain(); }
        TEST_CHECK(s_test_completions == 1U && s_published_snapshot.baro_update_count == 1U);
        TEST_CHECK(SystemNavigationHealth_GroupGet(4U,end_us,&health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.source == 1U && health.has_success == (uint8_t)(scenario == 9U));
        TEST_CHECK(s_published_snapshot.initialized == 1U && s_test_faults == 0U);
        return;
    }
    if (scenario == 8U)
    {
        before = s_estimator.kf; s_test_invalid_dt = 1U;
        HorizonTest_Body(1U); HorizonTest_RecordsDrain();
        TEST_CHECK(s_published_snapshot.initialized == 0U && s_published_snapshot.mission_running == 0U);
        TEST_CHECK(s_published_snapshot.timestamp_us == 1000000ULL && memcmp(&before,&s_estimator.kf,sizeof(before)) == 0);
        TEST_CHECK(s_test_faults == 1U); return;
    }
    HorizonTest_Receive(1005000ULL,1U,1U); HorizonTest_Body(1U); HorizonTest_RecordsDrain();
    TEST_CHECK(s_published_snapshot.timestamp_us == 1005000ULL && s_published_snapshot.initialized == 1U);
    TEST_CHECK(s_snapshot.measurement_attempt_mask == 0U && s_test_requests == 4U && s_test_completions == 0U);
    TEST_CHECK(s_horizon_fusion.primary_us == 1000000ULL && s_horizon_fusion.output_us == 1005000ULL);
    if (scenario == 1U) { s_test_gnss_source = 1U; s_test_sample.receive_timestamp_us = UINT64_MAX; }
    if (scenario == 2U) { s_test_gnss_source = UINT8_MAX; }
    if (scenario == 3U) { s_test_generation++; }
    if (scenario == 4U) { s_test_imu_source = 1U; }
    if (scenario == 5U) { s_horizon_fusion.body_count = NAV_KF_HORIZON_BODY_CAPACITY+1U; }
    if (scenario >= 3U && scenario <= 5U)
    {
        before = s_estimator.kf; HorizonTest_Body(2U); HorizonTest_RecordsDrain();
        TEST_CHECK(memcmp(&before,&s_estimator.kf,sizeof(before)) == 0 && s_test_faults == 1U);
        TEST_CHECK(s_published_snapshot.initialized == 0U && s_published_snapshot.mission_running == 0U);
        TEST_CHECK(s_published_snapshot.timestamp_us == 1005000ULL); return;
    }
    if (scenario == 6U) { HorizonTest_Receive(1010000ULL,2U,0U); }
    for (uint32_t cycle = 2U; cycle <= end_cycle; cycle++)
    {
        HorizonTest_Body(cycle); HorizonTest_RecordsDrain();
        TEST_CHECK(s_published_snapshot.initialized == 1U && s_published_snapshot.timestamp_us == 1000000ULL+(uint64_t)cycle*5000ULL);
        TEST_CHECK(fabsf(s_published_snapshot.acceleration_enu_mps2[0]) < .00001f);
    }
    TEST_CHECK(s_test_completions == 4U);
    TEST_CHECK(s_published_snapshot.gnss_position_update_count == 2U && s_published_snapshot.gnss_velocity_update_count == 2U);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U,end_us,&health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(health.has_success == (uint8_t)(scenario != 1U && scenario != 2U && scenario != 6U));
    if (scenario == 6U) { TEST_CHECK(s_test_rejections == 4U); }
    if (scenario == 7U)
    {
        HorizonTest_Receive(end_us+5000ULL,2U,1U); s_test_sample.sample_timestamp_us = 1001000ULL;
        HorizonTest_Body(end_cycle+1U); HorizonTest_RecordsDrain();
        TEST_CHECK(s_test_late == 4U && s_test_completions == 4U);
    }
    if (scenario == 1U || scenario == 2U)
    {
        s_test_gnss_source = 1U; s_test_sample.receive_timestamp_us = UINT64_MAX;
        HorizonTest_Body(end_cycle+1U); HorizonTest_RecordsDrain();
        HorizonTest_Receive(end_us+10000ULL,2U,1U);
        const uint32_t recovery_steps = (SYSTEM_FUSION_HORIZON_MS+4U)/5U+4U;
        for (uint32_t cycle = end_cycle+2U; cycle <= end_cycle+recovery_steps; cycle++)
        { HorizonTest_Body(cycle); HorizonTest_RecordsDrain(); }
        TEST_CHECK(SystemNavigationHealth_GroupGet(0U,end_us+(uint64_t)recovery_steps*5000ULL,&health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.source == 1U && health.has_success == 1U && s_test_completions == 8U);
    }
}

int main(int argc, char **argv)
{
    EstimatorPressureSnapshot unavailable;
    memset(&unavailable,0xA5,sizeof(unavailable));
    const EstimatorPressureSnapshot before = unavailable;
    TEST_CHECK(EstimatorBus_PressureReceiptGetLatest(NULL) == ESTIMATOR_BUS_RESULT_BAD_PARAM);
    TEST_CHECK(EstimatorBus_PressureReceiptGetLatest(&unavailable) == ESTIMATOR_BUS_RESULT_NOT_READY);
    TEST_CHECK(memcmp(&before,&unavailable,sizeof(before)) == 0);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(EstimatorBus_PressureReceiptGetLatest(&unavailable) == ESTIMATOR_BUS_RESULT_EMPTY);
    TEST_CHECK(memcmp(&before,&unavailable,sizeof(before)) == 0);
    if (argc == 3) { s_test_wire = fopen(argv[2],"wb"); TEST_CHECK(s_test_wire != NULL); }
    if (argc >= 2) { HorizonTest_Run((uint32_t)strtoul(argv[1],NULL,10)); }
    else { for (uint32_t scenario = 0U; scenario < 12U; scenario++) { HorizonTest_Run(scenario); } }
    TEST_CHECK(s_test_unexpected_preflight_calls == 0U);
    if (s_test_wire != NULL) { TEST_CHECK(fclose(s_test_wire) == 0); }
    return Test_Finish("kf_horizon_backend_actual");
}
