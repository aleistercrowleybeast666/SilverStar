#include "common_spsc_queue.h"
#include <stdint.h>
#include <string.h>

#include "diagnostic_log.h"
#include "host_platform_mock.h"
#include "imu_sample_bus.h"
#include "estimator_task.h"
#include "logger_bus.h"
#include "project_log_config.h"
#include "project_log_decoder_profile.h"
#include "sslog_protocol.h"
#include "system_descriptor_if.h"
#include "system_lifecycle.h"
#include "system_log_policy.h"
#include "system_telemetry_transport_if.h"
#include "system_user_config.h"
#include "test_common.h"

static SystemLifecycleState s_lifecycle_state = SYSTEM_STATE_FLIGHT;
static ImuSampleBusStats s_imu_bus_stats;
static EstimatorOutputSnapshot s_ins_snapshot;
static SystemTelemetryHealth s_telemetry_health;
static SystemDeviceResult s_telemetry_health_result = SYSTEM_DEVICE_OK;
static uint32_t s_imu_bus_stats_get_count;
static uint32_t s_telemetry_health_get_count;
static uint8_t s_ins_snapshot_available = 1U;

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return s_lifecycle_state;
}

void ImuSampleBus_StatsGet(ImuSampleBusStats *stats)
{
    s_imu_bus_stats_get_count++;
    if (stats != NULL)
    {
        *stats = s_imu_bus_stats;
    }
}

uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    if (snapshot != NULL)
    {
        *snapshot = s_ins_snapshot;
    }
    return s_ins_snapshot_available;
}

SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{
    s_telemetry_health_get_count++;
    if ((health != NULL) &&
        (s_telemetry_health_result == SYSTEM_DEVICE_OK))
    {
        *health = s_telemetry_health;
    }
    return s_telemetry_health_result;
}

static uint16_t Test_U16Get(const uint8_t *data)
{
    return (uint16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8U));
}

static uint32_t Test_U32Get(const uint8_t *data)
{
    return (uint32_t)data[0] |
           ((uint32_t)data[1] << 8U) |
           ((uint32_t)data[2] << 16U) |
           ((uint32_t)data[3] << 24U);
}

static void Test_LoggerQueueDrain(void)
{
    FlightLogRecord record;
    uint16_t index;

    for (index = 0U; index < SYSTEM_LOG_RECORD_QUEUE_DEPTH; index++)
    {
        if (LoggerBus_Pop(&record) != LOGGER_BUS_RESULT_OK)
        {
            break;
        }
    }
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
}

static void Test_RecordMetadata(void)
{
    static const FlightLogRecordType navigation_records[7] = {
        FLIGHT_LOG_RECORD_ESKF15_STATE, FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART,
        FLIGHT_LOG_RECORD_ESKF15_INITIAL_STATE, FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART,
        FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT, FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT,
        FLIGHT_LOG_RECORD_NAV_QUALITY
    };
    static const uint16_t navigation_sizes[7] = {144U, 144U, 144U, 144U, 100U, 84U, 100U};
    const SslogRecordMetadata *metadata;
    uint16_t index;

    TEST_CHECK(SslogRecords_RecordCountGet() == SSLOG_RECORD_COUNT);
    TEST_CHECK(SSLOG_RECORD_COUNT == 35U);
    for (index = 0U; index < 7U; index++)
    {
        TEST_CHECK((uint16_t)navigation_records[index] == (uint16_t)(0x21U + index));
        metadata = SslogRecords_MetadataGet(navigation_records[index]);
        TEST_CHECK(metadata != NULL);
        if (metadata != NULL)
        {
            TEST_CHECK(metadata->record_type == navigation_records[index]);
            TEST_CHECK(metadata->record_version == 1U);
            TEST_CHECK(metadata->payload_size == navigation_sizes[index]);
        }
    }
    TEST_CHECK(SslogRecords_MetadataGet((FlightLogRecordType)0x01U) == NULL);
    TEST_CHECK(FLIGHT_LOG_RECORD_STATS == 0x03U);
    TEST_CHECK(FLIGHT_LOG_RECORD_TELEMETRY_DIAG == 0x0CU);
    TEST_CHECK(FLIGHT_LOG_RECORD_MISSION_CONFIG == 0x19U);
    TEST_CHECK(FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR == 0x1AU);
    TEST_CHECK(FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR == 0x1BU);
    TEST_CHECK(FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR == 0x1CU);
    TEST_CHECK(FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR == 0x1DU);
    TEST_CHECK(FLIGHT_LOG_POWER_PAYLOAD_SIZE == 48U);
    TEST_CHECK(FLIGHT_LOG_STATS_PAYLOAD_SIZE == 16U);
    TEST_CHECK(FLIGHT_LOG_TELEMETRY_DIAG_PAYLOAD_SIZE == 48U);
    TEST_CHECK(SslogRecords_MetadataGet((FlightLogRecordType)0x0EU) == NULL);
    TEST_CHECK(SslogRecords_MetadataGet((FlightLogRecordType)0x06U) == NULL);
    TEST_CHECK(FLIGHT_LOG_GNSS_NATIVE_PAYLOAD_SIZE == 112U);
    TEST_CHECK(FLIGHT_LOG_BARO_NATIVE_PAYLOAD_SIZE == 52U);
    TEST_CHECK(FLIGHT_LOG_MAG_NATIVE_PAYLOAD_SIZE == 60U);
    TEST_CHECK(SslogRecords_MetadataGet((FlightLogRecordType)0x12U) == NULL);
    TEST_CHECK(FLIGHT_LOG_DEVICE_DESCRIPTOR_PAYLOAD_SIZE == 26U);
    TEST_CHECK(FLIGHT_LOG_DECODER_PROFILE_DESCRIPTOR_PAYLOAD_SIZE == 64U);
    for (index = 0U; index < SSLOG_RECORD_COUNT; index++)
    {
        metadata = SslogRecords_MetadataByIndexGet(index);
        TEST_CHECK(metadata != NULL);
        if (metadata != NULL)
        {
            TEST_CHECK(metadata->record_version <= 1U);
            TEST_CHECK(metadata->payload_size != 0U);
            TEST_CHECK(metadata->payload_size <= SSLOG_MAX_PAYLOAD_SIZE);
            TEST_CHECK(metadata->name != NULL);
        }
    }
    TEST_CHECK(SslogRecords_MetadataByIndexGet(SSLOG_RECORD_COUNT) == NULL);
    TEST_CHECK(SslogRecords_MetadataGet((FlightLogRecordType)0x7FU) == NULL);
}

static void Test_FileHeaderAndCrc(void)
{
    static const uint8_t crc_vector[] =
        {'1', '2', '3', '4', '5', '6', '7', '8', '9'};
    FlightLogFileHeaderInfo info;
    uint8_t buffer[FLIGHT_LOG_FILE_HEADER_SIZE];
    uint16_t serialized_size = 0U;
    uint32_t stored_crc;

    (void)memset(&info, 0, sizeof(info));
    info.profile_id = SYSTEM_LOG_PROFILE_ID;
    info.nominal_imu_rate_hz = SYSTEM_IMU_OUTPUT_RATE_HZ;
    info.nominal_ins_rate_hz =
        SYSTEM_IMU_OUTPUT_RATE_HZ / SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT;
    info.coordinate_frame = 1U;
    info.position_axis_order[0] = 1U;
    info.position_axis_order[1] = 2U;
    info.position_axis_order[2] = 3U;
    info.quaternion_order = 1U;
    info.quaternion_semantics = 1U;
    info.local_gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2;
    (void)memcpy(info.air_compatibility_tag, "AIRCPV0", 7U);
    (void)memcpy(info.build_tag, SILVERSTAR_LOG_BUILD_TAG, 8U);
    info.mechanization_subsample_count =
        SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT;
    info.firmware_version[0] = SILVERSTAR_VERSION_MAJOR;
    info.firmware_version[1] = SILVERSTAR_VERSION_MINOR;
    info.firmware_version[2] = SILVERSTAR_VERSION_PATCH;
    info.firmware_version[3] = SILVERSTAR_VERSION_BUILD;
    TEST_CHECK(FlightLog_Crc32(crc_vector, sizeof(crc_vector)) ==
               0xCBF43926UL);
    TEST_CHECK(FlightLog_FileHeaderSerialize(
        &info, buffer, sizeof(buffer), &serialized_size) ==
        FLIGHT_LOG_SERIALIZE_RESULT_OK);
    TEST_CHECK(serialized_size == FLIGHT_LOG_FILE_HEADER_SIZE);
    TEST_CHECK(memcmp(buffer, "SSLOG0", 6U) == 0);
    TEST_CHECK(Test_U16Get(&buffer[10]) == FLIGHT_LOG_FILE_HEADER_SIZE);
    TEST_CHECK(Test_U16Get(&buffer[12]) == FLIGHT_LOG_RECORD_HEADER_SIZE);
    TEST_CHECK(buffer[50] == SILVERSTAR_VERSION_PATCH);
    stored_crc = Test_U32Get(&buffer[FLIGHT_LOG_FILE_HEADER_SIZE - 4U]);
    TEST_CHECK(stored_crc == FlightLog_Crc32(
        buffer, FLIGHT_LOG_FILE_HEADER_SIZE - 4U));
}

static void Test_RecordEndianAndUnknownType(void)
{
    FlightLogRecord record;
    FlightLogRecord decoded;
    uint8_t buffer[FLIGHT_LOG_MAX_RECORD_SIZE];
    uint16_t serialized_size = 0U;
    uint16_t deserialized_size = 0U;
    uint32_t record_sequence = 0U;
    uint32_t stored_crc;

    (void)memset(&record, 0, sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_EVENT;
    record.timestamp_us = 0x0102030405060708ULL;
    record.valid_flags = 0xA1B2C3D4UL;
    record.payload.event.event_id = FLIGHT_LOG_EVENT_MISSION_START;
    record.payload.event.arg0 = 0x11223344UL;
    record.payload.event.arg1 = 0x55667788UL;
    TEST_CHECK(FlightLog_RecordSerialize(
        &record, 0x89ABCDEFUL, buffer, sizeof(buffer), &serialized_size) ==
        FLIGHT_LOG_SERIALIZE_RESULT_OK);
    TEST_CHECK(serialized_size == (FLIGHT_LOG_RECORD_HEADER_SIZE +
               FLIGHT_LOG_EVENT_PAYLOAD_SIZE + FLIGHT_LOG_RECORD_CRC_SIZE));
    TEST_CHECK(Test_U32Get(&buffer[0]) == 0x31474C46UL);
    TEST_CHECK(buffer[4] == 0U);
    TEST_CHECK(buffer[5] == FLIGHT_LOG_RECORD_EVENT);
    TEST_CHECK(Test_U16Get(&buffer[6]) == FLIGHT_LOG_EVENT_PAYLOAD_SIZE);
    TEST_CHECK(Test_U32Get(&buffer[8]) == 0x89ABCDEFUL);
    TEST_CHECK(buffer[12] == 0x08U && buffer[19] == 0x01U);
    TEST_CHECK(Test_U32Get(&buffer[20]) == 0xA1B2C3D4UL);
    TEST_CHECK(buffer[24] == FLIGHT_LOG_EVENT_MISSION_START);
    TEST_CHECK(Test_U32Get(&buffer[28]) == 0x11223344UL);
    TEST_CHECK(Test_U32Get(&buffer[32]) == 0x55667788UL);
    stored_crc = Test_U32Get(&buffer[serialized_size - 4U]);
    TEST_CHECK(stored_crc == FlightLog_Crc32(buffer, serialized_size - 4U));

    TEST_CHECK(FlightLog_RecordDeserialize(buffer, serialized_size, &decoded,
        &record_sequence, &deserialized_size) ==
        FLIGHT_LOG_DESERIALIZE_RESULT_OK);
    TEST_CHECK(deserialized_size == serialized_size);
    TEST_CHECK(record_sequence == 0x89ABCDEFUL);
    TEST_CHECK(decoded.record_type == FLIGHT_LOG_RECORD_EVENT);
    TEST_CHECK(decoded.timestamp_us == 0x0102030405060708ULL);
    TEST_CHECK(decoded.valid_flags == 0xA1B2C3D4UL);
    TEST_CHECK(decoded.payload.event.event_id ==
        FLIGHT_LOG_EVENT_MISSION_START);
    TEST_CHECK(decoded.payload.event.arg0 == 0x11223344UL);
    TEST_CHECK(decoded.payload.event.arg1 == 0x55667788UL);

    TEST_CHECK(FlightLog_RecordDeserialize(buffer, serialized_size - 1U,
        &decoded, &record_sequence, &deserialized_size) ==
        FLIGHT_LOG_DESERIALIZE_RESULT_BUFFER_SMALL);
    buffer[0] ^= 0x01U;
    TEST_CHECK(FlightLog_RecordDeserialize(buffer, serialized_size, &decoded,
        &record_sequence, &deserialized_size) ==
        FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SYNC);
    buffer[0] ^= 0x01U;
    buffer[4] = 1U;
    TEST_CHECK(FlightLog_RecordDeserialize(buffer, serialized_size, &decoded,
        &record_sequence, &deserialized_size) ==
        FLIGHT_LOG_DESERIALIZE_RESULT_BAD_VERSION);
    buffer[4] = 0U;
    buffer[6] ^= 0x01U;
    TEST_CHECK(FlightLog_RecordDeserialize(buffer, serialized_size, &decoded,
        &record_sequence, &deserialized_size) ==
        FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SIZE);
    buffer[6] ^= 0x01U;
    buffer[24] ^= 0x01U;
    TEST_CHECK(FlightLog_RecordDeserialize(buffer, serialized_size, &decoded,
        &record_sequence, &deserialized_size) ==
        FLIGHT_LOG_DESERIALIZE_RESULT_BAD_CRC);
    buffer[24] ^= 0x01U;

    record.record_type = (FlightLogRecordType)0x7FU;
    TEST_CHECK(FlightLog_RecordSerialize(
        &record, 0U, buffer, sizeof(buffer), &serialized_size) ==
               FLIGHT_LOG_SERIALIZE_RESULT_BAD_TYPE);
}

static void Test_GeneratedPayloadRoundTrip(void)
{
    FlightLogRecord source;
    FlightLogRecord decoded;
    uint8_t first[SSLOG_MAX_PAYLOAD_SIZE];
    uint8_t second[SSLOG_MAX_PAYLOAD_SIZE];
    uint16_t index;

    for (index = 0U; index < SSLOG_RECORD_COUNT; index++)
    {
        const SslogRecordMetadata *metadata =
            SslogRecords_MetadataByIndexGet(index);
        uint16_t first_size;
        uint16_t decoded_size;
        uint16_t second_size;

        TEST_CHECK(metadata != NULL);
        if (metadata == NULL)
        {
            continue;
        }
        (void)memset(&source, 0, sizeof(source));
        (void)memset(&decoded, 0, sizeof(decoded));
        (void)memset(&source.payload, 0xA5, sizeof(source.payload));
        source.record_type = metadata->record_type;
        decoded.record_type = metadata->record_type;

        first_size = SslogRecords_PayloadSerialize(&source, first,
            sizeof(first));
        decoded_size = SslogRecords_PayloadDeserialize(&decoded, first,
            first_size);
        second_size = SslogRecords_PayloadSerialize(&decoded, second,
            sizeof(second));
        TEST_CHECK(first_size == metadata->payload_size);
        TEST_CHECK(decoded_size == metadata->payload_size);
        TEST_CHECK(second_size == metadata->payload_size);
        TEST_CHECK(memcmp(first, second, metadata->payload_size) == 0);
        TEST_CHECK(SslogRecords_PayloadSerialize(&source, first,
            (uint16_t)(metadata->payload_size - 1U)) == 0U);
        TEST_CHECK(SslogRecords_PayloadDeserialize(&decoded, first,
            (uint16_t)(metadata->payload_size - 1U)) == 0U);
    }
}

static void Test_DiagnosticRecordCodec(void)
{
    FlightLogRecord source;
    FlightLogRecord decoded;
    uint8_t payload[FLIGHT_LOG_TELEMETRY_DIAG_PAYLOAD_SIZE];
    uint16_t payload_size;

    (void)memset(&source, 0, sizeof(source));
    (void)memset(&decoded, 0, sizeof(decoded));
    source.record_type = FLIGHT_LOG_RECORD_STATS;
    source.payload.stats.imu_queue_overflow_count = 0x01020304UL;
    source.payload.stats.logger_queue_overflow_count = 0x11121314UL;
    source.payload.stats.ins_update_count = 0x21222324UL;
    source.payload.stats.health_flags = 0x31323334UL;
    decoded.record_type = FLIGHT_LOG_RECORD_STATS;
    payload_size = SslogRecords_PayloadSerialize(
        &source, payload, sizeof(payload));
    TEST_CHECK(payload_size == FLIGHT_LOG_STATS_PAYLOAD_SIZE);
    TEST_CHECK(payload[0] == 0x04U && payload[3] == 0x01U);
    TEST_CHECK(Test_U32Get(&payload[4]) == 0x11121314UL);
    TEST_CHECK(Test_U32Get(&payload[8]) == 0x21222324UL);
    TEST_CHECK(Test_U32Get(&payload[12]) == 0x31323334UL);
    TEST_CHECK(SslogRecords_PayloadDeserialize(
        &decoded, payload, payload_size) == payload_size);
    TEST_CHECK(decoded.payload.stats.health_flags == 0x31323334UL);

    (void)memset(&source, 0, sizeof(source));
    (void)memset(&decoded, 0, sizeof(decoded));
    source.record_type = FLIGHT_LOG_RECORD_TELEMETRY_DIAG;
    source.payload.telemetry_diagnostic.last_transmit_timestamp_us =
        0x0102030405060708ULL;
    source.payload.telemetry_diagnostic.last_receive_timestamp_us =
        0x1112131415161718ULL;
    source.payload.telemetry_diagnostic.transmit_packet_count = 0x21222324UL;
    source.payload.telemetry_diagnostic.receive_packet_count = 0x31323334UL;
    source.payload.telemetry_diagnostic.transmit_error_count = 0x41424344UL;
    source.payload.telemetry_diagnostic.receive_error_count = 0x51525354UL;
    source.payload.telemetry_diagnostic.integrity_error_count = 0x61626364UL;
    source.payload.telemetry_diagnostic.last_rssi_dbm = -123;
    source.payload.telemetry_diagnostic.last_snr_q4 = -7;
    source.payload.telemetry_diagnostic.online = 1U;
    decoded.record_type = FLIGHT_LOG_RECORD_TELEMETRY_DIAG;
    payload_size = SslogRecords_PayloadSerialize(
        &source, payload, sizeof(payload));
    TEST_CHECK(payload_size == FLIGHT_LOG_TELEMETRY_DIAG_PAYLOAD_SIZE);
    TEST_CHECK(payload[0] == 0x08U && payload[7] == 0x01U);
    TEST_CHECK(Test_U32Get(&payload[16]) == 0x21222324UL);
    TEST_CHECK(payload[36] == 0x85U && payload[37] == 0xFFU);
    TEST_CHECK(payload[38] == 0xF9U && payload[39] == 1U);
    TEST_CHECK(payload[40] == 0U && payload[47] == 0U);
    TEST_CHECK(SslogRecords_PayloadDeserialize(
        &decoded, payload, payload_size) == payload_size);
    TEST_CHECK(decoded.payload.telemetry_diagnostic.
               last_receive_timestamp_us == 0x1112131415161718ULL);
    TEST_CHECK(decoded.payload.telemetry_diagnostic.last_rssi_dbm == -123);
    TEST_CHECK(decoded.payload.telemetry_diagnostic.last_snr_q4 == -7);
    TEST_CHECK(decoded.payload.telemetry_diagnostic.online == 1U);
}

static void Test_InstanceSourceCodec(void)
{
    FlightLogRecord source;
    FlightLogRecord decoded;
    uint8_t payload[SSLOG_MAX_PAYLOAD_SIZE];
    uint16_t payload_size;

    (void)memset(&source, 0, sizeof(source));
    (void)memset(&decoded, 0, sizeof(decoded));
    source.record_type = FLIGHT_LOG_RECORD_GNSS_NATIVE;
    source.payload.gnss_native.source_descriptor_id = 0x1234U;
    source.payload.gnss_native.instance_id = 7U;
    source.payload.gnss_native.sequence = 0x01020304UL;
    decoded.record_type = FLIGHT_LOG_RECORD_GNSS_NATIVE;
    payload_size = SslogRecords_PayloadSerialize(
        &source, payload, sizeof(payload));
    TEST_CHECK(payload_size == FLIGHT_LOG_GNSS_NATIVE_PAYLOAD_SIZE);
    TEST_CHECK(payload[0] == 0x34U);
    TEST_CHECK(payload[1] == 0x12U);
    TEST_CHECK(payload[2] == 7U);
    TEST_CHECK(payload[3] == 0U);
    TEST_CHECK(SslogRecords_PayloadDeserialize(
        &decoded, payload, payload_size) == payload_size);
    TEST_CHECK(decoded.payload.gnss_native.source_descriptor_id == 0x1234U);
    TEST_CHECK(decoded.payload.gnss_native.instance_id == 7U);
    TEST_CHECK(decoded.payload.gnss_native.sequence == 0x01020304UL);
}

static void Test_SourceChangeEventPacking(void)
{
    uint32_t arg0 = FLIGHT_LOG_SENSOR_SOURCE_CHANGE_ARG0(
        SYSTEM_DEVICE_CLASS_IMU, 1U, 2U,
        FLIGHT_LOG_SENSOR_SOURCE_CHANGE_FAILOVER);
    uint32_t arg1 = FLIGHT_LOG_SENSOR_SOURCE_CHANGE_ARG1(
        0x1234U, 0xABCDU);

    TEST_CHECK((arg0 & 0xFFUL) == SYSTEM_DEVICE_CLASS_IMU);
    TEST_CHECK(((arg0 >> 8U) & 0xFFUL) == 1U);
    TEST_CHECK(((arg0 >> 16U) & 0xFFUL) == 2U);
    TEST_CHECK(((arg0 >> 24U) & 0xFFUL) ==
               FLIGHT_LOG_SENSOR_SOURCE_CHANGE_FAILOVER);
    TEST_CHECK((arg1 & 0xFFFFUL) == 0x1234U);
    TEST_CHECK(((arg1 >> 16U) & 0xFFFFUL) == 0xABCDU);
}

static void Test_GeneratedStreamConfiguration(void)
{
    SystemLogStreamConfig runtime;
    const SystemLogStreamConfig *generated;
    SystemDeviceResult result;
    uint16_t index;

    TEST_CHECK(SystemLogPolicy_StreamCountGet() == SSLOG_RECORD_COUNT);
    for (index = 0U; index < SSLOG_RECORD_COUNT; index++)
    {
        generated = ProjectLogConfig_StreamByIndexGet(index);
        TEST_CHECK(generated != NULL);
        if (generated == NULL)
        {
            return;
        }
        result = SystemLogPolicy_StreamByIndexGet(index, &runtime);
        TEST_CHECK(result == SYSTEM_DEVICE_OK);
        if (result != SYSTEM_DEVICE_OK)
        {
            return;
        }
        TEST_CHECK(runtime.record_type == generated->record_type);
        TEST_CHECK(runtime.enabled == generated->enabled);
        TEST_CHECK(runtime.policy == generated->policy);
        TEST_CHECK(runtime.decimation == generated->decimation);
        TEST_CHECK(runtime.period_us == generated->period_us);
    }
    TEST_CHECK(index == SSLOG_RECORD_COUNT);
}

static void Test_StreamConfiguration(void)
{
    SystemLogStreamConfig config;
    SystemLogStreamConfig full_rate;
    SystemDeviceResult result;

    SystemLogPolicy_Init();
    Test_GeneratedStreamConfiguration();
    result = SystemLogPolicy_StreamGet(
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC, &config);
    TEST_CHECK(result == SYSTEM_DEVICE_OK);
    if (result != SYSTEM_DEVICE_OK)
    {
        return;
    }
    if (TEST_EXPECT_ESTIMATOR_CONFIG_ENABLED != 0U)
    {
        config.enabled = 1U;
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    }
    result = SystemLogPolicy_StreamGet(
        FLIGHT_LOG_RECORD_IMU_CORRECTED, &full_rate);
    TEST_CHECK(result == SYSTEM_DEVICE_OK);
    if (result != SYSTEM_DEVICE_OK)
    {
        return;
    }
    full_rate.decimation = 2U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&full_rate) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    full_rate.decimation = 1U;
    full_rate.period_us = 10000U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&full_rate) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    full_rate.period_us = 0U;
    full_rate.policy = SSLOG_STREAM_POLICY_DECIMATION;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&full_rate) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    config.decimation = 3U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    SystemLogPolicy_EmissionReset();
    TEST_CHECK(SystemLogPolicy_ShouldEmit(
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC) == config.enabled);
    TEST_CHECK(SystemLogPolicy_ShouldEmit(
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC) == 0U);
    TEST_CHECK(SystemLogPolicy_ShouldEmit(
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC) == 0U);
    TEST_CHECK(SystemLogPolicy_ShouldEmit(
        FLIGHT_LOG_RECORD_KF6_DIAGNOSTIC) == config.enabled);
    SystemLogPolicy_Freeze();
    config.decimation = 2U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) ==
               SYSTEM_DEVICE_BAD_STATE);
    SystemLogPolicy_UnfreezeForRollback();
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
}

static void Test_StatsProducer(void)
{
    DiagnosticLogPeriodicState state = {0ULL};
    DiagnosticLogPeriodicState empty_ins_state = {0ULL};
    FlightLogRecord record;
    SystemLogStreamConfig config;
    uint16_t index;

    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    LoggerBus_Reset();
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    (void)memset(&s_imu_bus_stats, 0, sizeof(s_imu_bus_stats));
    (void)memset(&s_ins_snapshot, 0, sizeof(s_ins_snapshot));
    s_imu_bus_stats.overflow_count = 23UL;
    s_imu_bus_stats_get_count = 0U;
    s_ins_snapshot.update_sequence = 456UL;
    s_ins_snapshot.health_flags = 0xA5A55A5AUL;
    s_ins_snapshot_available = 1U;
    TEST_CHECK(SystemLogPolicy_StreamGet(
        FLIGHT_LOG_RECORD_STATS, &config) == SYSTEM_DEVICE_OK);
    config.enabled = 1U;
    config.period_us = 1000000UL;
    config.decimation = 1U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    for (index = 0U; index < SYSTEM_LOG_RECORD_QUEUE_DEPTH; index++)
    {
        TEST_CHECK(LoggerBus_EventPush(index, FLIGHT_LOG_EVENT_BOOT,
            index, 0U) == LOGGER_BUS_RESULT_OK);
    }
    TEST_CHECK(LoggerBus_EventPush(999ULL, FLIGHT_LOG_EVENT_BOOT,
        0U, 0U) == LOGGER_BUS_RESULT_FULL);
    Test_LoggerQueueDrain();
    DiagnosticLog_StatsProcess(&state, 999999ULL);
    TEST_CHECK(s_imu_bus_stats_get_count == 0U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    DiagnosticLog_StatsProcess(&state, 1000000ULL);
    TEST_CHECK(s_imu_bus_stats_get_count == 1U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.record_type == FLIGHT_LOG_RECORD_STATS);
    TEST_CHECK(record.timestamp_us == 1000000ULL);
    TEST_CHECK(record.payload.stats.imu_queue_overflow_count == 23UL);
    TEST_CHECK(record.payload.stats.logger_queue_overflow_count == 1UL);
    TEST_CHECK(record.payload.stats.ins_update_count == 456UL);
    TEST_CHECK(record.payload.stats.health_flags == 0xA5A55A5AUL);
    DiagnosticLog_StatsProcess(&state, 1000000ULL);
    TEST_CHECK(s_imu_bus_stats_get_count == 1U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);

    s_ins_snapshot_available = 0U;
    SystemLogPolicy_EmissionReset();
    DiagnosticLog_StatsProcess(&empty_ins_state, 1000000ULL);
    TEST_CHECK(s_imu_bus_stats_get_count == 2U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.payload.stats.ins_update_count == 0U);
    TEST_CHECK(record.payload.stats.health_flags == 0U);
    config.enabled = 0U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    empty_ins_state.last_emission_us = 0ULL;
    DiagnosticLog_StatsProcess(&empty_ins_state, 2000000ULL);
    TEST_CHECK(s_imu_bus_stats_get_count == 2U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    config.enabled = 1U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    DiagnosticLog_StatsProcess(&empty_ins_state, 2000000ULL);
    TEST_CHECK(s_imu_bus_stats_get_count == 2U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
}

static void Test_TelemetryDiagnosticProducer(void)
{
    DiagnosticLogPeriodicState state = {0ULL};
    DiagnosticLogPeriodicState retry_state = {0ULL};
    FlightLogRecord record;
    SystemLogStreamConfig config;

    LoggerBus_Reset();
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    s_lifecycle_state = SYSTEM_STATE_RECOVERY;
    (void)memset(&s_telemetry_health, 0, sizeof(s_telemetry_health));
    s_telemetry_health.last_transmit_timestamp_us = 101ULL;
    s_telemetry_health.last_receive_timestamp_us = 202ULL;
    s_telemetry_health.transmit_packet_count = 303UL;
    s_telemetry_health.receive_packet_count = 404UL;
    s_telemetry_health.transmit_error_count = 5UL;
    s_telemetry_health.receive_error_count = 6UL;
    s_telemetry_health.integrity_error_count = 7UL;
    s_telemetry_health.last_rssi_dbm = -88;
    s_telemetry_health.last_snr_q4 = -9;
    s_telemetry_health.online = 1U;
    s_telemetry_health_result = SYSTEM_DEVICE_OK;
    s_telemetry_health_get_count = 0U;
    TEST_CHECK(SystemLogPolicy_StreamGet(
        FLIGHT_LOG_RECORD_TELEMETRY_DIAG, &config) == SYSTEM_DEVICE_OK);
    config.enabled = 1U;
    config.period_us = 200000UL;
    config.decimation = 1U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    DiagnosticLog_TelemetryProcess(&state, 199999ULL);
    TEST_CHECK(s_telemetry_health_get_count == 0U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    DiagnosticLog_TelemetryProcess(&state, 200000ULL);
    TEST_CHECK(s_telemetry_health_get_count == 1U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.record_type == FLIGHT_LOG_RECORD_TELEMETRY_DIAG);
    TEST_CHECK(record.timestamp_us == 200000ULL);
    TEST_CHECK(record.payload.telemetry_diagnostic.
               last_transmit_timestamp_us == 101ULL);
    TEST_CHECK(record.payload.telemetry_diagnostic.
               last_receive_timestamp_us == 202ULL);
    TEST_CHECK(record.payload.telemetry_diagnostic.
               transmit_packet_count == 303UL);
    TEST_CHECK(record.payload.telemetry_diagnostic.
               receive_packet_count == 404UL);
    TEST_CHECK(record.payload.telemetry_diagnostic.transmit_error_count == 5UL);
    TEST_CHECK(record.payload.telemetry_diagnostic.receive_error_count == 6UL);
    TEST_CHECK(record.payload.telemetry_diagnostic.integrity_error_count == 7UL);
    TEST_CHECK(record.payload.telemetry_diagnostic.last_rssi_dbm == -88);
    TEST_CHECK(record.payload.telemetry_diagnostic.last_snr_q4 == -9);
    TEST_CHECK(record.payload.telemetry_diagnostic.online == 1U);
    DiagnosticLog_TelemetryProcess(&state, 200000ULL);
    TEST_CHECK(s_telemetry_health_get_count == 1U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);

    s_telemetry_health_result = SYSTEM_DEVICE_IO_ERROR;
    SystemLogPolicy_EmissionReset();
    DiagnosticLog_TelemetryProcess(&retry_state, 200000ULL);
    TEST_CHECK(s_telemetry_health_get_count == 2U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    s_telemetry_health_result = SYSTEM_DEVICE_OK;
    DiagnosticLog_TelemetryProcess(&retry_state, 200001ULL);
    TEST_CHECK(s_telemetry_health_get_count == 3U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    config.enabled = 0U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    retry_state.last_emission_us = 0ULL;
    DiagnosticLog_TelemetryProcess(&retry_state, 400000ULL);
    TEST_CHECK(s_telemetry_health_get_count == 3U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    config.enabled = 1U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    DiagnosticLog_TelemetryProcess(&retry_state, 400000ULL);
    TEST_CHECK(s_telemetry_health_get_count == 3U);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
}

static void Test_DescriptorBundle(void)
{
    FlightLogRecord record;
    uint16_t device_count = 0U;
    uint16_t algorithm_count = 0U;
    uint16_t stream_count = 0U;
    uint16_t total_count;

    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    LoggerBus_Reset();
    TEST_CHECK(LoggerBus_SystemConfigPush(1234ULL) == LOGGER_BUS_RESULT_OK);
    total_count = LoggerBus_Count();
    TEST_CHECK(total_count == (uint16_t)(1U +
               SystemDescriptor_DeviceCountGet() +
               SystemDescriptor_AlgorithmCountGet() +
               SSLOG_RECORD_COUNT));
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.record_type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG);
    TEST_CHECK(record.payload.system_config.version[2] ==
               SILVERSTAR_VERSION_PATCH);
    TEST_CHECK(record.payload.system_config.device_descriptor_count ==
               SystemDescriptor_DeviceCountGet());
    TEST_CHECK(record.payload.system_config.algorithm_descriptor_count ==
               SystemDescriptor_AlgorithmCountGet());
    TEST_CHECK(record.payload.system_config.log_stream_descriptor_count ==
               SSLOG_RECORD_COUNT);
    while (LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK)
    {
        if (record.record_type == FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR)
        {
            TEST_CHECK(record.payload.device_descriptor.descriptor_id != 0U);
            if ((record.payload.device_descriptor.flags &
                 SYSTEM_DESCRIPTOR_FLAG_SHARED_PHYSICAL) != 0U)
            {
                TEST_CHECK(record.payload.device_descriptor.
                           physical_device_id != 0U);
            }
            device_count++;
        }
        else if (record.record_type ==
                 FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR)
        {
            algorithm_count++;
        }
        else if (record.record_type ==
                 FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR)
        {
            stream_count++;
            TEST_CHECK(record.payload.stream_descriptor.record_version ==
                   SslogRecords_MetadataGet((FlightLogRecordType)record.payload.stream_descriptor.record_type)->record_version);
            TEST_CHECK(record.payload.stream_descriptor.decimation != 0U);
        }
    }
    TEST_CHECK(device_count == SystemDescriptor_DeviceCountGet());
    TEST_CHECK(algorithm_count == SystemDescriptor_AlgorithmCountGet());
    TEST_CHECK(stream_count == SSLOG_RECORD_COUNT);
}

static void Test_DecoderProfileDescriptor(void)
{
    ProjectLogDecoderProfile profile;
    FlightLogRecord record;
    FlightLogRecord decoded;
    uint8_t payload[FLIGHT_LOG_DECODER_PROFILE_DESCRIPTOR_PAYLOAD_SIZE];
    uint16_t payload_size;

    ProjectLogDecoderProfile_Get(&profile);
    LoggerBus_Reset();
    TEST_CHECK(LoggerBus_DecoderProfileDescriptorPush(4321ULL) ==
               LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.record_type ==
               FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR);
    TEST_CHECK(record.timestamp_us == 4321ULL);
    TEST_CHECK(record.payload.decoder_profile_descriptor.
               package_schema_major == 1U);
    TEST_CHECK(record.payload.decoder_profile_descriptor.
               package_schema_minor == 2U);
    TEST_CHECK(record.payload.decoder_profile_descriptor.
               container_format_major == 0U);
    TEST_CHECK(memcmp(record.payload.decoder_profile_descriptor.
               record_catalog_hash_128,
               profile.record_catalog_hash_128, 16U) == 0);
    TEST_CHECK(memcmp(record.payload.decoder_profile_descriptor.
               project_semantics_hash_128,
               profile.project_semantics_hash_128, 16U) == 0);
    TEST_CHECK(memcmp(record.payload.decoder_profile_descriptor.
               generation_profile_hash_128,
               profile.generation_profile_hash_128, 16U) == 0);
    payload_size = SslogRecords_PayloadSerialize(
        &record, payload, sizeof(payload));
    TEST_CHECK(payload_size == sizeof(payload));
    TEST_CHECK(payload[0] == 1U && payload[1] == 0U);
    TEST_CHECK(payload[2] == 2U && payload[3] == 0U);
    TEST_CHECK(payload[4] == 0U && payload[5] == 0U);
    (void)memset(&decoded, 0, sizeof(decoded));
    decoded.record_type = FLIGHT_LOG_RECORD_DECODER_PROFILE_DESCRIPTOR;
    TEST_CHECK(SslogRecords_PayloadDeserialize(
        &decoded, payload, sizeof(payload)) == sizeof(payload));
    TEST_CHECK(memcmp(&record.payload.decoder_profile_descriptor,
        &decoded.payload.decoder_profile_descriptor,
        sizeof(record.payload.decoder_profile_descriptor)) == 0);
}

static void Test_QueueOverflowAndFinalization(void)
{
    uint16_t index;

    LoggerBus_Reset();
    for (index = 0U; index < SYSTEM_LOG_RECORD_QUEUE_DEPTH; index++)
    {
        TEST_CHECK(LoggerBus_EventPush(
            index, FLIGHT_LOG_EVENT_BOOT, index, 0U) ==
            LOGGER_BUS_RESULT_OK);
    }
    TEST_CHECK(LoggerBus_EventPush(
        999U, FLIGHT_LOG_EVENT_BOOT, 0U, 0U) == LOGGER_BUS_RESULT_FULL);
    TEST_CHECK(LoggerBus_OverflowCountGet() == 1U);
    TEST_CHECK(LoggerBus_FinalizationArm(1000ULL) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_FinalizationProcess(
        1000ULL + ((uint64_t)SYSTEM_LOG_POST_LANDING_GRACE_MS * 1000ULL) -
        1ULL) == LOGGER_BUS_FINALIZATION_ARMED);
    TEST_CHECK(LoggerBus_FinalizationProcess(
        1000ULL + ((uint64_t)SYSTEM_LOG_POST_LANDING_GRACE_MS * 1000ULL)) ==
        LOGGER_BUS_FINALIZATION_DRAINING);
    TEST_CHECK(LoggerBus_EventPush(
        2000ULL, FLIGHT_LOG_EVENT_BOOT, 0U, 0U) ==
        LOGGER_BUS_RESULT_BAD_STATE);
    LoggerBus_FinalizationComplete();
    TEST_CHECK(LoggerBus_FinalizationStateGet() ==
               LOGGER_BUS_FINALIZATION_FINALIZED);
}

static void Test_BootstrapAdmission(void)
{
    FlightLogRecord record = {0};
    LoggerBusDiagnostics diagnostics;
    SystemLogStreamConfig config;
    LoggerBus_Reset();
    TEST_CHECK(SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_GNSS_NATIVE, &config) == SYSTEM_DEVICE_OK);
    config.enabled = 1U;
    config.decimation = 1U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    for (unsigned index = 0U; index < 1000U; index++)
    {
        TEST_CHECK(LoggerBus_GnssNativePush(index, 0U, &record.payload.gnss_native) == LOGGER_BUS_RESULT_OK);
    }
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(diagnostics.startup_state == LOGGER_BOOTSTRAP);
    TEST_CHECK(diagnostics.bootstrap_suppressed_count == 1000U);
    TEST_CHECK(diagnostics.accepted_count == 0U && diagnostics.overflow_count == 0U);
    TEST_CHECK(LoggerBus_CalibrationResultPush(1U, &record.payload.calibration_result) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_AlignmentResultPush(2U, &record.payload.alignment_result) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_InitialStatePush(3U, &record.payload.initial_state) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_MissionConfigPush(4U) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_FULL);
    for (unsigned index = 0U; index < 4U; index++)
    { TEST_CHECK(LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK); }
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_GnssNativePush(5U, 0U, &record.payload.gnss_native) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(record.record_type == FLIGHT_LOG_RECORD_GNSS_NATIVE);
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(diagnostics.accepted_count == 5U && diagnostics.dequeued_count == 5U);
    TEST_CHECK(diagnostics.normal_high_water == 4U && diagnostics.overflow_count == 0U);
    TEST_CHECK(diagnostics.bootstrap_suppressed_count == 1000U);
    LoggerBus_Reset();
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(diagnostics.startup_state == LOGGER_BOOTSTRAP);
}

static void Test_QueueCounterWrap(void)
{
    static const uint16_t capacities[] = {1U, 3U, 48U, 64U, 80U};
    uint32_t storage[80];
    for (unsigned c = 0U; c < sizeof(capacities) / sizeof(capacities[0]); c++)
    {
        CommonSpscQueue queue;
        uint32_t output;
        uint32_t next = 0U;
        TEST_CHECK(CommonSpscQueue_Init(&queue, storage, capacities[c], sizeof(output)) == COMMON_SPSC_QUEUE_RESULT_OK);
        for (uint32_t value = 0U; value < 140000U; value++)
        {
            if (CommonSpscQueue_Count(&queue) == capacities[c])
            {
                TEST_CHECK(CommonSpscQueue_Pop(&queue, &output) == COMMON_SPSC_QUEUE_RESULT_OK);
                TEST_CHECK(output == next++);
            }
            TEST_CHECK(CommonSpscQueue_Push(&queue, &value) == COMMON_SPSC_QUEUE_RESULT_OK);
        }
        while (CommonSpscQueue_Pop(&queue, &output) == COMMON_SPSC_QUEUE_RESULT_OK)
        { TEST_CHECK(output == next++); }
        TEST_CHECK(next == 140000U && CommonSpscQueue_Count(&queue) == 0U);
    }
}

static void Test_QueuePressureFairness(void)
{
    FlightLogEskf15BodyInputRecord body = {0};
    FlightLogRecord record;
    SystemLogStreamConfig config;
    for (uint8_t phase = 0U; phase < 2U; ++phase)
    {
        uint8_t run = 0U;
        uint8_t observed_other = 0U;
        uint16_t normal_depth = (phase == 0U) ? 60U : 5U;
        uint16_t estimator_depth = (phase == 0U) ? 8U : 40U;
        LoggerBus_Reset();
        TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT, &config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U; config.decimation = 1U;
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
        for (uint16_t index = 0U; index < normal_depth; ++index)
        { TEST_CHECK(LoggerBus_EventPush(index, FLIGHT_LOG_EVENT_SAMPLE_GAP, index, 0U) == LOGGER_BUS_RESULT_OK); }
        for (uint16_t index = 0U; index < estimator_depth; ++index)
        { TEST_CHECK(LoggerBus_Eskf15BodyInputPush(index, &body) == LOGGER_BUS_RESULT_OK); }
        for (uint8_t index = 0U; index < 16U; ++index)
        {
            uint8_t estimator;
            TEST_CHECK(LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK);
            estimator = (uint8_t)(record.record_type == FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT);
            if (index == 0U) { TEST_CHECK(estimator == phase); }
            if (estimator == phase) { run++; }
            else { observed_other++; run = 0U; }
            TEST_CHECK(run <= 3U);
            TEST_CHECK((estimator ? LoggerBus_Eskf15BodyInputPush(1000ULL + index, &body) :
                LoggerBus_EventPush(1000ULL + index, FLIGHT_LOG_EVENT_SAMPLE_GAP, index, 0U)) == LOGGER_BUS_RESULT_OK);
        }
        TEST_CHECK(observed_other >= 4U);
        TEST_CHECK(LoggerBus_Count() == normal_depth + estimator_depth);
    }
    LoggerBus_Reset();
}

static LoggerBusResult Test_CovariancePop(uint8_t phase, FlightLogRecord *record)
{
    return (phase == 0U) ? LoggerBus_EstimatorPop(record) : LoggerBus_Pop(record);
}

static void Test_Eskf15CovarianceSnapshot(void)
{
    FlightLogEskf15CovariancePartRecord identity = {0};
    FlightLogEskf15StateRecord state_record = {0};
    FlightLogEskf15BodyInputRecord body_record = {0};
    FlightLogRecord record;
    SystemLogStreamConfig config;
    LoggerBusDiagnostics before;
    LoggerBusDiagnostics after;
    float covariance[225];
    uint16_t index;
    uint16_t row;
    uint16_t column;
    uint8_t phase;
    uint8_t part;
    uint8_t fragments = 0U;
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    SystemLogPolicy_UnfreezeForRollback();
    LoggerBus_Reset();
    identity.algorithm_id = 2U;
    identity.snapshot_id = 17U;
    identity.epoch = 3U;
    for (index = 0U; index < 225U; index++) { covariance[index] = (float)index; }
    for (phase = 0U; phase < 2U; phase++)
    {
        FlightLogRecordType type = (phase == 0U) ? FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART :
            FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART;
        identity.phase = phase;
        TEST_CHECK(SystemLogPolicy_StreamGet(type, &config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U;
        if (phase != 0U) { config.period_us = 1000U; }
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
        if (phase != 0U) { TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK); }
        TEST_CHECK(LoggerBus_Eskf15CovariancePush(2000ULL, &identity, covariance) == LOGGER_BUS_RESULT_OK);
        row = 0U; column = 0U;
        for (part = 0U; part < 4U; part++)
        {
            const FlightLogEskf15CovariancePartRecord *payload;
            TEST_CHECK(Test_CovariancePop(phase, &record) == LOGGER_BUS_RESULT_OK);
            TEST_CHECK(record.record_type == type && record.timestamp_us == 2000ULL);
            payload = (phase == 0U) ? &record.payload.eskf15_initial_p_part : &record.payload.eskf15_full_p_part;
            TEST_CHECK(payload->part_index == part && payload->part_count == 4U);
            TEST_CHECK(payload->offset == (uint16_t)(part * 30U) && payload->count == 30U);
            TEST_CHECK(payload->snapshot_id == 17U && payload->epoch == 3U && payload->phase == phase);
            for (index = 0U; index < 30U; index++)
            {
                TEST_CHECK(payload->values[index] == covariance[row * 15U + column]);
                column++;
                if (column == 15U) { row++; column = row; }
            }
        }
        TEST_CHECK(row == 15U && Test_CovariancePop(phase, &record) == LOGGER_BUS_RESULT_EMPTY);
    }
    TEST_CHECK(LoggerBus_Eskf15CovariancePush(2500ULL, &identity, covariance) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    TEST_CHECK(LoggerBus_Eskf15CovariancePush(3000ULL, &identity, covariance) == LOGGER_BUS_RESULT_OK);
    for (part = 0U; part < 4U; part++) { TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_OK); }
    TEST_CHECK(LoggerBus_Pop(&record) == LOGGER_BUS_RESULT_EMPTY);
    for (phase = 0U; phase < 2U; phase++)
    {
        uint16_t depth = (phase == 0U) ? SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH : SYSTEM_LOG_RECORD_QUEUE_DEPTH;
        FlightLogRecordType filler = (phase == 0U) ? FLIGHT_LOG_RECORD_ESKF15_BODY_INPUT : FLIGHT_LOG_RECORD_ESKF15_STATE;
        FlightLogRecordType type = (phase == 0U) ? FLIGHT_LOG_RECORD_ESKF15_INITIAL_P_PART : FLIGHT_LOG_RECORD_ESKF15_FULL_P_PART;
        identity.phase = phase;
        fragments = 0U;
        LoggerBus_Reset();
        TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(SystemLogPolicy_StreamGet(filler, &config) == SYSTEM_DEVICE_OK);
        config.enabled = 1U;
        config.decimation = 1U;
        TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
        for (index = 0U; index < depth - 2U; index++)
        {
            uint64_t timestamp = 4000ULL + (uint64_t)index * config.period_us;
            TEST_CHECK(((phase == 0U) ? LoggerBus_Eskf15BodyInputPush(timestamp, &body_record) :
                LoggerBus_Eskf15StatePush(timestamp, &state_record)) == LOGGER_BUS_RESULT_OK);
        }
        TEST_CHECK(LoggerBus_DiagnosticsGet(&before) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(LoggerBus_Eskf15CovariancePush(5000ULL, &identity, covariance) == LOGGER_BUS_RESULT_FULL);
        TEST_CHECK(LoggerBus_DiagnosticsGet(&after) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(after.accepted_count == before.accepted_count + 2U);
        TEST_CHECK(after.overflow_count == before.overflow_count + 2U);
        TEST_CHECK(((phase == 0U) ? after.estimator_high_water : after.normal_high_water) == depth);
        for (index = 0U; index < depth; index++)
        {
            TEST_CHECK(Test_CovariancePop(phase, &record) == LOGGER_BUS_RESULT_OK);
            if (record.record_type == type) { fragments++; }
        }
        TEST_CHECK(fragments == 2U && Test_CovariancePop(phase, &record) == LOGGER_BUS_RESULT_EMPTY);
    }
}

int main(void)
{
    HostPlatformMock_Reset();
    Test_QueueCounterWrap();
    Test_RecordMetadata();
    Test_FileHeaderAndCrc();
    Test_RecordEndianAndUnknownType();
    Test_GeneratedPayloadRoundTrip();
    Test_DiagnosticRecordCodec();
    Test_InstanceSourceCodec();
    Test_SourceChangeEventPacking();
    Test_StreamConfiguration();
    Test_StatsProducer();
    Test_TelemetryDiagnosticProducer();
    Test_DescriptorBundle();
    Test_DecoderProfileDescriptor();
    Test_BootstrapAdmission();
    Test_QueueOverflowAndFinalization();
    Test_Eskf15CovarianceSnapshot();
    Test_QueuePressureFairness();
    return Test_Finish("logger");
}
