/* Actual owning backend, horizon, health, queues, LoggerBus and wire codecs.
 * Device/time/identity boundaries are CPU-only fixtures. No physical IO. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "test_common.h"
#include "host_platform_mock.h"
#include "system_user_config.h"
#include "logger_bus.h"
#include "system_log_policy.h"

_Static_assert(SYSTEM_FUSION_TIMING_MODE == 2U, "This scenario requires the actual horizon backend");
#ifndef ESKF_HORIZON_BACKEND_SOURCE
#define ESKF_HORIZON_BACKEND_SOURCE "../../Algorithm/Estimator/ESKF15/Src/navigation_eskf_backend.c"
#endif
#include ESKF_HORIZON_BACKEND_SOURCE

static SystemGnssSample s_test_sample;
static uint8_t s_test_source;
static uint8_t s_test_imu_source;
static uint32_t s_test_generation;
static uint32_t s_test_quality;
static uint32_t s_test_request_count;
static uint32_t s_test_completion_count;
static uint32_t s_test_status_count;
static uint32_t s_test_fault_status_count;
static uint32_t s_test_rejected_count;
static uint32_t s_test_old_source_completion_count;
static uint32_t s_test_late_count;
static uint64_t s_test_request_source[2048];
static uint8_t s_test_completed[2048];
static FILE *s_test_wire;
static uint32_t s_test_wire_sequence;

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ *sample = s_test_sample; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{
    memset(time,0,sizeof(*time)); time->sequence = s_test_sample.sequence;
    time->time_of_week_ms = (uint32_t)(s_test_sample.sample_timestamp_us/1000ULL);
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = s_test_imu_source; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{
    if (s_test_source == UINT8_MAX-1U) { return SYSTEM_DEVICE_BAD_STATE; }
    if (s_test_source == UINT8_MAX) { return SYSTEM_DEVICE_NOT_READY; }
    *instance = s_test_source; return SYSTEM_DEVICE_OK;
}
uint32_t SystemCalibration_GenerationGet(void) { return s_test_generation; }

static void HorizonTest_RecordsDrain(void)
{
    FlightLogRecord record, restored;
    while (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
    {
        uint8_t wire[284];
        uint16_t size = 0U, consumed = 0U;
        uint32_t sequence = 0U;
        uint32_t encoded_sequence = s_test_wire_sequence++;
        TEST_CHECK(FlightLog_RecordSerialize(&record,encoded_sequence,wire,sizeof(wire),&size) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
        if (s_test_wire != NULL) { TEST_CHECK(fwrite(wire,1U,size,s_test_wire) == size); }
        TEST_CHECK(FlightLog_RecordDeserialize(wire,size,&restored,&sequence,&consumed) == FLIGHT_LOG_DESERIALIZE_RESULT_OK);
        TEST_CHECK(consumed == size && sequence == encoded_sequence && restored.record_type == record.record_type);
        TEST_CHECK(record.record_type != FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT);
        if (record.record_type == FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT)
        {
            const FlightLogFusionHorizonMeasurementRecord *value = &record.payload.fusion_horizon_measurement;
            TEST_CHECK(value->algorithm_id == 2U && value->numerical_revision == 2U && value->fusion_timing_mode == 2U);
            TEST_CHECK(value->epoch == 77U && value->calibration_generation == s_test_generation);
            TEST_CHECK(value->evaluation_timestamp_us == record.timestamp_us && value->operation_sequence < 2048U);
            if (value->phase == 0U)
            {
                s_test_request_count++;
                TEST_CHECK(value->admitted == 0U && value->effective_update == 0U && value->application_timestamp_us == 0U);
                TEST_CHECK(value->update_result == 255U && value->nis == -1.0f);
                if (value->execution_result == SYSTEM_FUSION_EXEC_QUEUED)
                {
                    uint8_t found = 0U;
                    s_test_request_source[value->operation_sequence] = value->measurement_timestamp_us;
                    for (uint16_t index = 0U; index < s_horizon.event_count; index++)
                    {
                        const NavigationEskfHorizonEvent *queued = &s_horizon.event[index];
                        if (queued->operation_sequence == value->operation_sequence)
                        {
                            found = 1U;
                            TEST_CHECK(memcmp(value->prepared_variance,queued->event.measurement.variance,
                                sizeof(value->prepared_variance)) == 0);
                        }
                    }
                    TEST_CHECK(found == 1U);
                }
                else { s_test_rejected_count++; }
                if (value->execution_result == SYSTEM_FUSION_EXEC_LATE) { s_test_late_count++; }
            }
            else
            {
                s_test_completion_count++;
                TEST_CHECK(value->phase == 1U && value->admitted == 1U && value->execution_result == SYSTEM_FUSION_EXEC_COMPLETE);
                TEST_CHECK(value->application_timestamp_us == value->measurement_timestamp_us);
                TEST_CHECK(value->application_timestamp_us <= value->evaluation_timestamp_us);
                TEST_CHECK(s_test_request_source[value->operation_sequence] == value->application_timestamp_us);
                TEST_CHECK(s_test_completed[value->operation_sequence] == 0U);
                s_test_completed[value->operation_sequence] = 1U;
                TEST_CHECK(isfinite(value->nis) && value->nis >= 0.0f && value->effective_variance[0] > 0.0f);
                if (value->group < 4U && value->source_id == 0U && s_test_source != 0U)
                { s_test_old_source_completion_count++; }
            }
        }
        if (record.record_type == FLIGHT_LOG_RECORD_FUSION_HORIZON_STATUS)
        {
            const FlightLogFusionHorizonStatusRecord *value = &record.payload.fusion_horizon_status;
            s_test_status_count++;
            TEST_CHECK(value->algorithm_id == 2U && value->numerical_revision == 2U && value->fusion_timing_mode == 2U);
            TEST_CHECK(value->output_state_timestamp_us == value->output_covariance_timestamp_us);
            TEST_CHECK(value->output_state_timestamp_us == s_state.timestamp_us);
            TEST_CHECK(value->horizon_initialized == s_horizon.initialized);
            TEST_CHECK(value->primary_timestamp_us <= value->input_present_timestamp_us);
            TEST_CHECK(value->work_count <= NAV_ESKF_HORIZON_MAX_WORK);
            if (value->phase == 2U) { s_test_fault_status_count++; }
        }
    }
}

static void HorizonTest_Reset(EstimatorOutputSnapshot *output)
{
    const FlightLogRecordType streams[] = {FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT,
        FLIGHT_LOG_RECORD_FUSION_HORIZON_STATUS, FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT,
        FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE, FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART,
        FLIGHT_LOG_RECORD_ESKF15_STATE, FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART};
    const float quaternion[4] = {1.0f,0.0f,0.0f,0.0f};
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
    s_test_source = 0U; s_test_imu_source = 0U; s_test_generation = 7U;
    s_test_quality = 0U;
    memset(&s_test_sample,0,sizeof(s_test_sample)); memset(output,0,sizeof(*output));
    s_test_sample.position_usable = 1U; s_test_sample.online = 1U;
    s_test_sample.latitude_e7 = 300000000; s_test_sample.longitude_e7 = 1200000000;
    s_test_sample.horizontal_accuracy_m = 1.0f; s_test_sample.vertical_accuracy_m = 2.0f;
    s_test_sample.velocity_valid_mask = 7U; s_test_sample.valid_group_mask = 15U;
    s_test_sample.physical_valid_group_mask = 15U; s_test_sample.supported_fields = 0x3FFU;
    s_test_sample.valid_fields = s_test_sample.supported_fields; s_test_sample.fix_type = 3U;
    s_test_sample.fix_ok = 1U; s_test_sample.speed_accuracy_mps = 0.2f;
    s_test_sample.satellite_count = 16U; s_test_sample.measurement_timestamp_trusted = 1U;
    for (uint32_t axis = 0U; axis < 3U; axis++) { s_test_sample.velocity_variance_m2ps2[axis] = .04f; }
    TEST_CHECK(SystemNavigationBackend_Initialize(quaternion,&s_test_sample,10.0f,1U,77U,1U) == SYSTEM_DEVICE_OK);
    s_test_sample.receive_timestamp_us = UINT64_MAX;
    s_test_request_count = 0U; s_test_completion_count = 0U; s_test_status_count = 0U;
    s_test_fault_status_count = 0U; s_test_rejected_count = 0U; s_test_old_source_completion_count = 0U; s_test_late_count = 0U;
    s_test_wire_sequence = 0U;
    memset(s_test_request_source,0,sizeof(s_test_request_source)); memset(s_test_completed,0,sizeof(s_test_completed));
}

static void HorizonTest_Receive(uint64_t now_us, uint32_t sequence, uint8_t valid)
{
    s_test_sample.receive_timestamp_us = now_us; s_test_sample.sample_timestamp_us = now_us-2500ULL;
    s_test_sample.sequence = sequence; s_test_sample.fix_ok = valid;
    s_test_sample.valid_group_mask = valid ? 15U : 0U;
    s_test_sample.physical_valid_group_mask = s_test_sample.valid_group_mask;
}

static SystemDeviceResult HorizonTest_Body(uint32_t cycle, EstimatorOutputSnapshot *output)
{
    SystemInertialIncrement input = {0};
    input.timestamp_us = 1000000ULL+(uint64_t)cycle*5000ULL; input.sequence = cycle; input.dt_s = .005f;
    input.quality_flags = s_test_quality;
    input.body_accel_mps2[0][2] = SYSTEM_ESKF_GRAVITY_MPS2;
    input.body_accel_mps2[1][2] = SYSTEM_ESKF_GRAVITY_MPS2;
    HostPlatformMock_TimeSetUs(input.timestamp_us);
    return SystemNavigationBackend_Predict(&input,output);
}

static void HorizonTest_Run(uint32_t scenario)
{
    EstimatorOutputSnapshot output;
    SystemNavigationGroupHealth health;
    NavigationEskfState before;
    const uint32_t horizon_steps = (SYSTEM_FUSION_HORIZON_MS+4U)/5U;
    const uint32_t end_cycle = horizon_steps+6U;
    const uint64_t end_us = 1000000ULL+(uint64_t)end_cycle*5000ULL;
    HorizonTest_Reset(&output);
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
        s_test_source = UINT8_MAX;
        pressure.timestamp_us = 1002500ULL; pressure.receive_timestamp_us = 1005000ULL;
        pressure.sequence = 1U; pressure.altitude_m = 10.5f; pressure.variance_m2 = 1.0f;
        pressure.valid = 1U; pressure.healthy = 1U; pressure.measurement_timestamp_trusted = 1U;
        TEST_CHECK(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
        TEST_CHECK(HorizonTest_Body(1U,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain();
        TEST_CHECK(s_test_request_count == 1U && s_test_completion_count == 0U);
        if (scenario == 10U)
        {
            pressure.timestamp_us += 5000ULL; pressure.receive_timestamp_us += 5000ULL;
            pressure.sequence = 2U; pressure.valid = 0U;
            TEST_CHECK(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
        }
        for (uint32_t cycle = 2U; cycle <= end_cycle; cycle++)
        { TEST_CHECK(HorizonTest_Body(cycle,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain(); }
        TEST_CHECK(s_test_completion_count == 1U && output.baro_update_count == 1U);
        TEST_CHECK(SystemNavigationHealth_GroupGet(4U,end_us,&health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.source == 1U && health.has_success == (uint8_t)(scenario == 9U));
        TEST_CHECK(output.initialized == 1U && s_test_fault_status_count == 0U);
        return;
    }
    if (scenario == 8U)
    {
        before = s_state; s_test_quality = 0x10U;
        TEST_CHECK(HorizonTest_Body(1U,&output) == SYSTEM_DEVICE_VERIFY_FAILED); HorizonTest_RecordsDrain();
        TEST_CHECK(memcmp(&before,&s_state,sizeof(before)) == 0);
        TEST_CHECK(output.initialized == 0U && output.mission_running == 0U && s_test_fault_status_count == 1U);
        TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_NOT_READY);
        return;
    }
    HorizonTest_Receive(1005000ULL,1U,1U);
    TEST_CHECK(HorizonTest_Body(1U,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain();
    TEST_CHECK(output.measurement_attempt_mask == 0U && output.gnss_position_update_count == 0U);
    TEST_CHECK(s_test_request_count == 4U && s_test_completion_count == 0U);
    TEST_CHECK(s_horizon.primary.timestamp_us == 1000000ULL && s_state.timestamp_us == 1005000ULL);
    TEST_CHECK((output.health_flags & ESTIMATOR_HEALTH_FUSION_TIMEOUT) != 0U);
    if (scenario == 1U) { s_test_source = 1U; s_test_sample.receive_timestamp_us = UINT64_MAX; }
    if (scenario == 2U) { s_test_source = UINT8_MAX; }
    if (scenario == 3U) { s_test_generation++; }
    if (scenario == 4U) { s_test_imu_source = 2U; }
    if (scenario == 5U) { s_horizon.body_count = NAV_ESKF_HORIZON_BODY_CAPACITY+1U; }
    if (scenario == 12U) { s_test_source = UINT8_MAX-1U; }
    if ((scenario >= 3U && scenario <= 5U) || scenario == 12U)
    {
        before = s_state;
        TEST_CHECK(HorizonTest_Body(2U,&output) == SYSTEM_DEVICE_VERIFY_FAILED); HorizonTest_RecordsDrain();
        TEST_CHECK(memcmp(&before,&s_state,sizeof(before)) == 0);
        TEST_CHECK(output.initialized == 0U && output.mission_running == 0U && s_test_fault_status_count == 1U);
        TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_NOT_READY);
        TEST_CHECK(HorizonTest_Body(3U,&output) == SYSTEM_DEVICE_VERIFY_FAILED);
        return;
    }
    if (scenario == 6U) { HorizonTest_Receive(1010000ULL,2U,0U); }
    for (uint32_t cycle = 2U; cycle <= end_cycle; cycle++)
    {
        TEST_CHECK(HorizonTest_Body(cycle,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain();
        TEST_CHECK(output.timestamp_us == 1000000ULL+(uint64_t)cycle*5000ULL);
        TEST_CHECK(fabsf(output.acceleration_enu_mps2[0]) < .00001f);
    }
    TEST_CHECK(s_test_completion_count == 4U && s_test_status_count == end_cycle);
    TEST_CHECK(SystemNavigationHealth_GroupGet(0U,end_us,&health) == SYSTEM_DEVICE_OK);
    if (scenario == 1U || scenario == 2U || scenario == 6U)
    { TEST_CHECK(health.has_success == 0U && s_test_old_source_completion_count == (scenario == 6U ? 0U : 4U)); }
    else { TEST_CHECK(health.has_success == 1U && health.last_successful_fusion_us >= 1002500ULL+(uint64_t)SYSTEM_FUSION_HORIZON_MS*1000ULL); }
    if (scenario == 6U) { TEST_CHECK(s_test_rejected_count == 4U); }
    if (scenario == 7U)
    {
        HorizonTest_Receive(end_us+5000ULL,2U,1U); s_test_sample.sample_timestamp_us = 1001000ULL;
        TEST_CHECK(HorizonTest_Body(end_cycle+1U,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain();
        TEST_CHECK(s_test_late_count == 4U && s_test_completion_count == 4U);
    }
    if (scenario == 1U || scenario == 2U)
    {
        s_test_source = 1U; s_test_sample.receive_timestamp_us = UINT64_MAX;
        TEST_CHECK(HorizonTest_Body(end_cycle+1U,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain();
        HorizonTest_Receive(end_us+10000ULL,2U,1U);
        for (uint32_t cycle = end_cycle+2U; cycle <= end_cycle+horizon_steps+4U; cycle++)
        { TEST_CHECK(HorizonTest_Body(cycle,&output) == SYSTEM_DEVICE_OK); HorizonTest_RecordsDrain(); }
        TEST_CHECK(SystemNavigationHealth_GroupGet(0U,end_us+(uint64_t)(horizon_steps+4U)*5000ULL,&health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.source == 1U && health.has_success == 1U && s_test_completion_count == 8U);
    }
}

int main(int argc, char **argv)
{
    if (argc == 3) { s_test_wire = fopen(argv[2],"wb"); TEST_CHECK(s_test_wire != NULL); }
    if (argc >= 2) { HorizonTest_Run((uint32_t)strtoul(argv[1],NULL,10)); }
    else { for (uint32_t scenario = 0U; scenario < 13U; scenario++) { HorizonTest_Run(scenario); } }
    if (s_test_wire != NULL) { TEST_CHECK(fclose(s_test_wire) == 0); }
    return Test_Finish("eskf_horizon_backend_actual");
}
