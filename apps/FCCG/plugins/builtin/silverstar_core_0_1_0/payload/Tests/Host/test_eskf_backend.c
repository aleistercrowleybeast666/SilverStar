/* Actual backend/kernel/replay/clock/queues/LoggerBus. Only device inputs and
 * source identity are fixtures; no estimator or log producer is mocked. */
#include <math.h>
#include <string.h>
#include <stdio.h>
#include "test_common.h"
#include "host_platform_mock.h"
#include "system_navigation_backend.h"
#include "system_navigation_health.h"
#include "system_calibration.h"
#include "system_source_selector.h"
#include "system_time.h"
#include "system_log_policy.h"
#include "estimator_bus.h"
#include "logger_bus.h"
#ifdef TEST_ESKF_BACKEND_EXPORT
#include "../../APP/Src/flight_task.c"
#include "../../APP/Src/logger_task.c"
#endif

static SystemGnssSample s_gnss;
static uint32_t s_measurements;
static uint32_t s_invalid_measurements;
static uint32_t s_body_records;
static uint32_t s_state_records;
static uint32_t s_covariance_parts;
static uint32_t s_failover_measurements;
static uint8_t s_gnss_source = 2U;
#ifdef TEST_ESKF_BACKEND_EXPORT
static const char *s_export_path;
static FILE *s_export_file;

SystemDeviceResult SystemLogSink_Init(void)
{ return (s_export_path != NULL) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemLogSink_SessionBegin(const SystemLogSessionInfo *session)
{
    if (session == NULL || s_export_path == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_export_file = fopen(s_export_path, "wb");
    return (s_export_file != NULL) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}
SystemDeviceResult SystemLogSink_Write(const uint8_t *data, uint32_t length, uint32_t *written)
{
    if (data == NULL || written == NULL || s_export_file == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *written = (uint32_t)fwrite(data, 1U, length, s_export_file);
    return (*written == length) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}
SystemDeviceResult SystemLogSink_Flush(void)
{ return (s_export_file != NULL && fflush(s_export_file) == 0) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR; }
SystemDeviceResult SystemLogSink_SessionEnd(void)
{
    int result = (s_export_file != NULL) ? fclose(s_export_file) : 0;
    s_export_file = NULL;
    return (result == 0) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}
#endif

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ *sample = s_gnss; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{
    memset(time, 0, sizeof(*time));
    time->sequence = s_gnss.sequence;
    time->time_of_week_ms = (uint32_t)(s_gnss.sample_timestamp_us / 1000ULL);
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = 1U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{ *instance = s_gnss_source; return SYSTEM_DEVICE_OK; }

static void Test_RecordsDrain(void)
{
    FlightLogRecord record;
    while (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
    {
#ifdef TEST_ESKF_BACKEND_EXPORT
        if (s_export_file != NULL) { TEST_CHECK(LoggerTask_RecordAppend(&record) == 1U); }
#endif
        if (record.record_type == FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT)
        {
            const FlightLogEskf15MeasurementRecord *value = &record.payload.eskf15_measurement;
            s_measurements++;
            if ((value->group < 4U) && (value->source_id == 3U)) { s_failover_measurements++; }
            TEST_CHECK(value->epoch == 77U);
            TEST_CHECK(value->calibration_generation == SystemCalibration_GenerationGet());
            TEST_CHECK(value->calibration_generation != value->epoch);
            TEST_CHECK(value->receive_timestamp_us <= value->evaluation_timestamp_us);
            TEST_CHECK(value->measurement_timestamp_us < value->receive_timestamp_us);
            if (value->physically_valid == 0U)
            {
                s_invalid_measurements++;
                TEST_CHECK(value->admitted == 0U);
            }
            else if (value->admitted != 0U)
            {
                TEST_CHECK(isfinite(value->nis));
                TEST_CHECK(value->effective_variance[0] > 0.0f);
            }
        }
        if (record.record_type == FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT) { s_body_records++; }
        if (record.record_type == FLIGHT_LOG_RECORD_ESKF15_STATE) { s_state_records++; }
        if ((record.record_type == FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART) ||
            (record.record_type == FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART)) { s_covariance_parts++; }
    }
}

int main(int argc, char **argv)
{
    const FlightLogRecordType streams[] = { FLIGHT_LOG_RECORD_ESKF15_STATE,
        FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART, FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE,
        FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART, FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT,
        FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT, FLIGHT_LOG_RECORD_NAV_QUALITY };
    const float q[4] = {1.0f, 0.0f, 0.0f, 0.0f};
    EstimatorOutputSnapshot output = {0};
    EstimatorPressureSnapshot pressure = {0};
    SystemInertialIncrement input = {0};
    SystemNavigationGroupHealth health;
    uint16_t cycle;
    uint8_t group;
    uint64_t last_success = 0ULL;
    SystemCalibrationStatus calibration = {0};
    SystemDeviceResult calibration_result;
#ifdef TEST_ESKF_BACKEND_EXPORT
    if (argc == 2) { s_export_path = argv[1]; }
    else if (argc != 1) { return 2; }
#else
    (void)argc;
    (void)argv;
#endif
    HostPlatformMock_Reset();
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    HostPlatformMock_TimeSetUs(10000000ULL);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    for (group = 0U; group < sizeof(streams) / sizeof(streams[0]); group++)
    {
        SystemLogStreamConfig config;
        TEST_CHECK(SystemLogPolicy_StreamGet(streams[group], &config) == SYSTEM_DEVICE_OK);
#ifdef TEST_ESKF_BACKEND_EXPORT
        if (s_export_path != NULL) { TEST_CHECK(config.enabled == 1U && config.decimation == 1U); }
#endif
        config.enabled = 1U; config.decimation = 1U;
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    }
#ifdef TEST_ESKF_BACKEND_EXPORT
    if (s_export_path != NULL)
    {
        TEST_CHECK(LoggerTask_SessionOpen() == 1U);
        TEST_CHECK(LoggerBus_SystemConfigPush(SystemTime_GetMonotonicUs()) == LOGGER_BUS_RESULT_OK);
        Test_RecordsDrain();
    }
#endif
    SystemCalibration_Init();
    calibration_result = SystemCalibration_StatusGet(&calibration);
    TEST_CHECK(calibration_result == SYSTEM_DEVICE_OK);
    if (calibration_result != SYSTEM_DEVICE_OK) { return Test_Finish("eskf_backend_actual"); }
    TEST_CHECK(calibration.mode == SYSTEM_CALIBRATION_MODE_NONE && calibration.ready != 0U);
#ifdef TEST_ESKF_BACKEND_EXPORT
    FlightTask_CalibrationResultWrite(&calibration);
#endif
    TEST_CHECK(LoggerBus_MissionConfigPush(SystemTime_GetMonotonicUs()) == LOGGER_BUS_RESULT_OK);
    Test_RecordsDrain();
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    s_gnss.position_usable = 1U; s_gnss.online = 1U;
    s_gnss.latitude_e7 = 300000000; s_gnss.longitude_e7 = 1200000000;
    s_gnss.horizontal_accuracy_m = 1.0f; s_gnss.vertical_accuracy_m = 2.0f;
    s_gnss.velocity_valid_mask = 7U; s_gnss.valid_group_mask = 15U;
    s_gnss.physical_valid_group_mask = 15U;
    s_gnss.supported_fields = 0x3FFU; s_gnss.valid_fields = s_gnss.supported_fields;
    s_gnss.fix_type = 3U; s_gnss.fix_ok = 1U; s_gnss.speed_accuracy_mps = 0.2f;
    s_gnss.satellite_count = 8U; s_gnss.measurement_timestamp_trusted = 1U;
    for (group = 0U; group < 3U; group++) { s_gnss.velocity_variance_m2ps2[group] = 0.04f; }
    TEST_CHECK(SystemNavigationBackend_Initialize(q, &s_gnss, 10.0f, 77U, 1U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemNavigationBackend_SnapshotGet(&output) == SYSTEM_DEVICE_OK);
    TEST_CHECK(output.predict_count == 0U && output.update_sequence == 0U);
    TEST_CHECK(fabsf(output.q_nb[0] - 1.0f) < 0.00001f);
    for (group = 0U; group < 6U; group++)
    { TEST_CHECK(isfinite(output.covariance_diagonal[group]) && output.covariance_diagonal[group] > 0.0f); }
    s_gnss.receive_timestamp_us = UINT64_MAX;
    pressure.altitude_m = 10.1f; pressure.pressure_pa = 101325.0f;
    pressure.variance_m2 = 1.0f; pressure.valid = 1U; pressure.healthy = 1U;
    pressure.measurement_timestamp_trusted = 1U;
    input.dt_s = 0.004f;
    input.body_accel_mps2[0][0] = 0.5f; input.body_accel_mps2[1][0] = 0.5f;
    input.body_accel_mps2[0][2] = 9.80665f; input.body_accel_mps2[1][2] = 9.80665f;
    for (cycle = 1U; cycle <= 200U; cycle++)
    {
        input.timestamp_us = 10000000ULL + (uint64_t)cycle * 4000ULL;
        input.sequence = cycle;
        HostPlatformMock_TimeSetUs(input.timestamp_us);
        if ((cycle >= 20U) && ((cycle % 10U) == 0U))
        {
            s_gnss.sequence++;
            s_gnss.receive_timestamp_us = input.timestamp_us;
            s_gnss.sample_timestamp_us = input.timestamp_us - 40000ULL;
            s_gnss.valid_group_mask = (cycle == 180U) ? 0U : 15U;
            s_gnss.physical_valid_group_mask = s_gnss.valid_group_mask;
            s_gnss.fix_ok = (uint8_t)(cycle != 180U);
            pressure.sequence++;
            pressure.receive_timestamp_us = input.timestamp_us;
            pressure.timestamp_us = input.timestamp_us - 40000ULL;
            if (cycle == 190U)
            {
                /* Fresh flags on an old receive time cannot admit stale data. */
                s_gnss.receive_timestamp_us -= 4000000ULL;
                s_gnss.sample_timestamp_us -= 4000000ULL;
                pressure.receive_timestamp_us -= 4000000ULL;
                pressure.timestamp_us -= 4000000ULL;
            }
            TEST_CHECK(EstimatorBus_PressurePublish(&pressure) == ESTIMATOR_BUS_RESULT_OK);
        }
        if (cycle == 195U)
        {
            /* Different physical source reuses its own sequence number. */
            s_gnss_source = 3U;
            s_gnss.receive_timestamp_us = input.timestamp_us;
            s_gnss.sample_timestamp_us = input.timestamp_us - 40000ULL;
        }
        {
            SystemDeviceResult result = SystemNavigationBackend_Predict(&input, &output);
            if ((cycle == 1U) || ((cycle % 20U) == 0U) || (result != SYSTEM_DEVICE_OK))
            { printf("cycle=%u result=%u accel=%f,%f,%f velocity=%f,%f,%f counts=%u/%u/%u\n",
                (unsigned)cycle, (unsigned)result, (double)output.acceleration_enu_mps2[0],
                (double)output.acceleration_enu_mps2[1], (double)output.acceleration_enu_mps2[2],
                (double)output.velocity_enu_mps[0], (double)output.velocity_enu_mps[1],
                (double)output.velocity_enu_mps[2], (unsigned)output.gnss_position_update_count,
                (unsigned)output.gnss_velocity_update_count, (unsigned)output.baro_update_count); }
            TEST_CHECK(result == SYSTEM_DEVICE_OK);
        }
        TEST_CHECK(output.initialized == 1U && output.mission_running == 1U);
        TEST_CHECK(output.timestamp_us == input.timestamp_us && output.predict_count == cycle);
        TEST_CHECK(isfinite(output.acceleration_enu_mps2[0]));
        if (cycle < 20U)
        { TEST_CHECK(fabsf(output.acceleration_enu_mps2[0] - 0.5f) < 0.00001f); }
        if ((cycle == 179U) || (cycle == 189U))
        {
            TEST_CHECK(SystemNavigationHealth_GroupGet(0U, input.timestamp_us, &health) == SYSTEM_DEVICE_OK);
            last_success = health.last_successful_fusion_us;
        }
        if ((cycle == 180U) || (cycle == 190U))
        {
            TEST_CHECK(SystemNavigationHealth_GroupGet(0U, input.timestamp_us, &health) == SYSTEM_DEVICE_OK);
            TEST_CHECK(health.last_successful_fusion_us == last_success);
        }
        Test_RecordsDrain();
    }
    TEST_CHECK(output.gnss_position_update_count > 0U && output.gnss_velocity_update_count > 0U);
    TEST_CHECK(output.baro_update_count > 0U && output.baro_relative_altitude_m > 0.09f);
    TEST_CHECK(output.last_gnss_sequence == s_gnss.sequence && output.last_baro_sequence == pressure.sequence);
    TEST_CHECK(s_measurements >= 95U && s_invalid_measurements >= 9U);
    TEST_CHECK(s_body_records > 0U && s_state_records > 0U && s_covariance_parts >= 8U);
    TEST_CHECK(s_failover_measurements == 8U);
    for (group = 0U; group < 5U; group++)
    {
        TEST_CHECK(SystemNavigationHealth_GroupGet(group, input.timestamp_us, &health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.has_success && health.last_successful_fusion_us == input.timestamp_us);
    }
#ifdef TEST_ESKF_BACKEND_EXPORT
    if (s_export_file != NULL)
    {
        TEST_CHECK(LoggerBus_Count() == 0U && LoggerBus_OverflowCountGet() == 0U);
        TEST_CHECK(LoggerTask_Flush() == 1U);
        LoggerTask_Close();
        TEST_CHECK(s_diagnostics.io_fault == 0U && s_diagnostics.discarded_bytes == 0U);
        printf("ACTUAL_BACKEND_LOG path=%s serialized=%lu generation=%lu\n", s_export_path,
            (unsigned long)s_diagnostics.serialized_count, (unsigned long)SystemCalibration_GenerationGet());
    }
#endif
    return Test_Finish("eskf_backend_actual");
}
