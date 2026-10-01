/* Actual SF6/backend/INS prediction/clock/queues/log codecs. Only sensor inputs
 * and source identity are fixtures. Export uses actual LoggerTask bootstrap. */
#include <math.h>
#include <string.h>
#include <stdio.h>
#include "test_common.h"
#include "host_platform_mock.h"
#include "system_navigation_backend.h"
#include "system_navigation_health.h"
#include "system_source_selector.h"
#include "system_time.h"
#include "system_user_config.h"
#include "system_barometer_if.h"
#include "system_log_policy.h"
#include "estimator_bus.h"
#include "logger_bus.h"
#ifdef TEST_SF6_BACKEND_EXPORT
#include "../../APP/Src/logger_task.c"
static const char *s_export_path;
static FILE *s_export_file;
SystemDeviceResult SystemLogSink_Init(void)
{ return s_export_path != NULL ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemLogSink_SessionBegin(const SystemLogSessionInfo *session)
{
    if (session == NULL || s_export_path == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_export_file = fopen(s_export_path, "wb");
    return s_export_file != NULL ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}
SystemDeviceResult SystemLogSink_Write(const uint8_t *data, uint32_t length, uint32_t *written)
{
    if (data == NULL || written == NULL || s_export_file == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *written = (uint32_t)fwrite(data, 1U, length, s_export_file);
    return *written == length ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}
SystemDeviceResult SystemLogSink_Flush(void)
{ return s_export_file != NULL && fflush(s_export_file) == 0 ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR; }
SystemDeviceResult SystemLogSink_SessionEnd(void)
{
    int result = s_export_file != NULL ? fclose(s_export_file) : 0;
    s_export_file = NULL;
    return result == 0 ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}
#endif

static SystemGnssSample s_gnss;
static uint32_t s_measurements;
static uint32_t s_states;
static uint32_t s_invalid;
static uint32_t s_sequence;

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ *sample = s_gnss; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{ *instance = 2U; return SYSTEM_DEVICE_OK; }

static void Test_RecordsDrain(void)
{
    FlightLogRecord record, decoded;
    uint8_t wire[300];
    uint16_t length = 0U, consumed = 0U;
    uint32_t sequence = 0U;
    while (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
    {
        TEST_CHECK(FlightLog_RecordSerialize(&record, s_sequence++, wire, sizeof(wire), &length) ==
            FLIGHT_LOG_SERIALIZE_RESULT_OK);
        TEST_CHECK(FlightLog_RecordDeserialize(wire, length, &decoded, &sequence, &consumed) ==
            FLIGHT_LOG_DESERIALIZE_RESULT_OK);
        TEST_CHECK(sequence + 1U == s_sequence && consumed == length);
#ifdef TEST_SF6_BACKEND_EXPORT
        if (s_export_file != NULL) { TEST_CHECK(LoggerTask_RecordAppend(&record) == 1U); }
#endif
        if (record.record_type == FLIGHT_LOG_RECORD_SF6_STATE)
        {
            s_states++;
            TEST_CHECK(length == 100U);
            TEST_CHECK(decoded.payload.sf6_state.algorithm_id == 3U);
            for (uint8_t axis = 0U; axis < 6U; axis++)
            { TEST_CHECK_NEAR(decoded.payload.sf6_state.gain[axis], 0.2f, 1.0e-6f); }
            wire[30] ^= 1U;
            TEST_CHECK(FlightLog_RecordDeserialize(wire, length, &decoded, &sequence, &consumed) ==
                FLIGHT_LOG_DESERIALIZE_RESULT_BAD_CRC);
        }
        if (record.record_type == FLIGHT_LOG_RECORD_SF6_MEASUREMENT)
        {
            const FlightLogSf6MeasurementRecord *value = &decoded.payload.sf6_measurement;
            s_measurements++;
            TEST_CHECK(length == 84U && value->group < 5U);
            if (value->result == 0U)
            {
                TEST_CHECK(value->measurement_timestamp_us <= value->receive_timestamp_us);
                TEST_CHECK(value->boundary_timestamp_us <= value->measurement_timestamp_us);
                TEST_CHECK(value->measurement_timestamp_us - value->boundary_timestamp_us <= 20000ULL);
                TEST_CHECK(value->effective_update == 1U);
            }
            else { s_invalid++; TEST_CHECK(value->effective_update == 0U); }
        }
        TEST_CHECK(record.record_type != FLIGHT_LOG_RECORD_ESTIMATOR &&
            record.record_type != FLIGHT_LOG_RECORD_KF6_FULL_P &&
            record.record_type != FLIGHT_LOG_RECORD_ESKF15_STATE);
    }
}

static void Test_GnssPrepare(void)
{
    memset(&s_gnss, 0, sizeof(s_gnss));
    s_gnss.position_usable = 1U; s_gnss.online = 1U;
    s_gnss.latitude_e7 = 300000000; s_gnss.longitude_e7 = 1200000000;
    s_gnss.horizontal_accuracy_m = 1.0f; s_gnss.vertical_accuracy_m = 2.0f;
    s_gnss.velocity_valid_mask = 7U; s_gnss.valid_group_mask = 15U;
    s_gnss.physical_valid_group_mask = 15U;
    s_gnss.supported_fields = 0x3FFU; s_gnss.valid_fields = s_gnss.supported_fields;
    s_gnss.fix_type = 3U; s_gnss.fix_ok = 1U; s_gnss.speed_accuracy_mps = 0.2f;
    s_gnss.satellite_count = 8U; s_gnss.measurement_timestamp_trusted = 1U;
    s_gnss.sequence = UINT32_MAX - 10U;
    for (uint8_t axis = 0U; axis < 3U; axis++) { s_gnss.velocity_variance_m2ps2[axis] = 0.04f; }
}

int main(int argc, char **argv)
{
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    const FlightLogRecordType streams[] = {FLIGHT_LOG_RECORD_SF6_STATE, FLIGHT_LOG_RECORD_SF6_MEASUREMENT};
    EstimatorOutputSnapshot output = {0};
    EstimatorPressureSnapshot pressure = {0};
    SystemInertialIncrement input = {0};
    uint32_t previous_position = 0U, previous_velocity = 0U, previous_baro = 0U;
#ifdef TEST_SF6_BACKEND_EXPORT
    if (argc == 2) { s_export_path = argv[1]; }
    else if (argc != 1) { return 2; }
#else
    (void)argc; (void)argv;
#endif
    HostPlatformMock_Reset();
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    for (uint8_t index = 0U; index < 2U; index++)
    {
        SystemLogStreamConfig config;
        TEST_CHECK(SystemLogPolicy_StreamGet(streams[index], &config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U;
        /* Keep the schema's PERIODIC/EVERY mode. 4 ms period exercises every
         * state publication without bypassing the declared mode contract. */
        if (config.policy == SSLOG_STREAM_POLICY_PERIODIC) { config.period_us = 4000U; }
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    }
#ifdef TEST_SF6_BACKEND_EXPORT
    if (s_export_path != NULL) { TEST_CHECK(LoggerTask_SessionOpen() == 1U); Test_RecordsDrain(); }
#endif
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    Test_GnssPrepare();
    TEST_CHECK(SystemNavigationBackend_Initialize(q, &s_gnss, 10.0f, 77U, 1U) == SYSTEM_DEVICE_OK);
    /* A production session records mission start. Keep the exact decoder's
     * calibration-selection boundary contract in the exported Host fixture. */
    TEST_CHECK(LoggerBus_EventPush(10000000ULL, (FlightLogEventId)0x03U, 0U, 0U) ==
        LOGGER_BUS_RESULT_OK);
    TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_OK);
    for (uint8_t axis = 0U; axis < 6U; axis++) { TEST_CHECK(isnan(output.covariance_diagonal[axis])); }
    s_gnss.receive_timestamp_us = UINT64_MAX;
    pressure.altitude_m = 10.5f; pressure.pressure_pa = 101325.0f;
    pressure.valid = 1U; pressure.healthy = 1U; pressure.measurement_timestamp_trusted = 1U;
    pressure.supported_fields = SYSTEM_BARO_FIELD_ALTITUDE;
    pressure.valid_fields = SYSTEM_BARO_VALID_ALTITUDE;
    input.dt_s = 0.004f;
    input.delta_velocity_b_sculling_corrected[0] = 0.002f;
    input.delta_velocity_b_sculling_corrected[2] = SYSTEM_INS_GRAVITY_MPS2 * input.dt_s;
    for (uint32_t cycle = 1U; cycle <= 1000U; cycle++)
    {
        input.timestamp_us = 10000000ULL + (uint64_t)cycle * 4000ULL; input.sequence = cycle;
        HostPlatformMock_TimeSetUs(input.timestamp_us);
        if (cycle <= 400U && cycle % 25U == 0U)
        {
            s_gnss.sequence++; s_gnss.receive_timestamp_us = input.timestamp_us;
            s_gnss.sample_timestamp_us = input.timestamp_us - 40000ULL;
            s_gnss.velocity_enu_mps[0] = cycle == 200U ? NAN : 0.5f;
            if (cycle == 250U) { s_gnss.measurement_timestamp_trusted = 0U; }
            else { s_gnss.measurement_timestamp_trusted = 1U; }
            if (cycle == 300U) { s_gnss.sample_timestamp_us = input.timestamp_us + 1000ULL; }
        }
        if (cycle <= 400U && cycle % 10U == 0U)
        {
            pressure.sequence++; pressure.receive_timestamp_us = input.timestamp_us;
            pressure.timestamp_us = input.timestamp_us - 20000ULL;
            pressure.altitude_m = cycle == 210U ? NAN : 10.5f;
            TEST_CHECK(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
        }
        TEST_CHECK(SystemNavigationBackend_Predict(&input, &output) == SYSTEM_DEVICE_OK);
        TEST_CHECK(output.timestamp_us == input.timestamp_us && output.predict_count == cycle);
        TEST_CHECK(isfinite(output.position_enu_m[0]) && isfinite(output.velocity_enu_mps[0]));
        TEST_CHECK(isnan(output.last_position_nis) && isnan(output.position_r_scale));
        if (cycle % 25U != 0U || cycle > 400U)
        {
            TEST_CHECK(output.gnss_position_update_count == previous_position);
            TEST_CHECK(output.gnss_velocity_update_count == previous_velocity);
        }
        if (cycle % 10U != 0U || cycle > 400U) { TEST_CHECK(output.baro_update_count == previous_baro); }
        previous_position = output.gnss_position_update_count;
        previous_velocity = output.gnss_velocity_update_count; previous_baro = output.baro_update_count;
        Test_RecordsDrain();
    }
    TEST_CHECK(s_states == 1000U && s_measurements == 104U && s_invalid > 0U);
    TEST_CHECK(previous_position > 0U && previous_velocity > 0U && previous_baro > 0U);
    TEST_CHECK(SystemNavigationHealth_DegradedGet(input.timestamp_us) != 0U);
    TEST_CHECK(LoggerBus_OverflowCountGet() == 0U);
#ifdef TEST_SF6_BACKEND_EXPORT
    if (s_export_file != NULL) { TEST_CHECK(LoggerTask_Flush() == 1U); LoggerTask_Close(); }
#endif
    SystemNavigationBackend_Reset();
    TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(SystemNavigationBackend_Predict(&input, &output) == SYSTEM_DEVICE_NOT_READY);
    return Test_Finish("sf6_backend_actual");
}
