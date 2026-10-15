/* Wire vectors follow contracts/navigation_fusion_timing_records_v2.json.
 * Explicit C field values are checked against independent little-endian bytes.
 * Codec acceptance does not validate timing evidence or imply fusion acceptance. */
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "sslog_protocol.h"
#include "test_common.h"
#ifdef FUSION_TIMING_RECORDS_LOGGER_TEST
#include "logger_bus.h"
#include "system_log_policy.h"
#include "system_user_config.h"
#include "host_platform_mock.h"
#endif

static const uint8_t s_gnss_wire[212] = {
    0x00U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0x08U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x10U, 0x00U, 0x65U, 0x87U, 0x00U, 0x00U, 0xA2U, 0x41U,
    0x00U, 0x00U, 0xC2U, 0x41U, 0x00U, 0x00U, 0xE2U, 0x41U, 0x00U, 0x00U, 0x01U, 0x42U,
    0x00U, 0x00U, 0x11U, 0x42U, 0x00U, 0x00U, 0x21U, 0x42U, 0x00U, 0x00U, 0x31U, 0x42U,
    0x00U, 0x00U, 0x41U, 0x42U, 0x00U, 0x00U, 0x51U, 0x42U, 0x00U, 0x00U, 0x61U, 0x42U,
    0x00U, 0x00U, 0x71U, 0x42U, 0x00U, 0x80U, 0x80U, 0x42U, 0xD3U, 0xD6U, 0xD9U, 0xDCU,
    0x48U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0x50U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x58U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU,
    0x60U, 0x00U, 0x65U, 0x87U, 0x64U, 0x00U, 0x65U, 0x87U, 0x68U, 0x00U, 0x65U, 0x87U,
    0x6CU, 0x00U, 0x65U, 0x87U, 0x70U, 0x00U, 0x65U, 0x87U, 0x63U, 0x66U, 0x69U, 0x6CU,
    0x6FU, 0x72U, 0x75U, 0x78U, 0x00U, 0x80U, 0xF8U, 0x42U, 0x00U, 0x40U, 0x00U, 0x43U,
    0x00U, 0x40U, 0x04U, 0x43U, 0x00U, 0x40U, 0x08U, 0x43U, 0x00U, 0x40U, 0x0CU, 0x43U,
    0x00U, 0x40U, 0x10U, 0x43U, 0x00U, 0x40U, 0x14U, 0x43U, 0x00U, 0x40U, 0x18U, 0x43U,
    0x00U, 0x40U, 0x1CU, 0x43U, 0x00U, 0x40U, 0x20U, 0x43U, 0xA4U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0xACU, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU,
    0xB4U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0xBCU, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x01U, 0x0BU, 0x07U, 0x00U, 0x06U, 0x00U, 0x00U, 0x00U,
    0xCCU, 0x00U, 0x65U, 0x87U, 0xD0U, 0x00U, 0x65U, 0x87U,
};

static void Test_GnssFill(FlightLogRecord *record)
{
    (void)memset(record, 0, sizeof(*record));
    record->record_type = FLIGHT_LOG_RECORD_GNSS_MEASUREMENT;
    record->timestamp_us = 0x123456789ABCDEF0ULL;
    record->valid_flags = 0xBADC0FFEU;
    record->payload.gnss_measurement.sample_timestamp_us = 0xFEDCBA9800000000ULL;
    record->payload.gnss_measurement.receive_timestamp_us = 0xFEDCBA9800000008ULL;
    record->payload.gnss_measurement.sequence = 0x87650010U;
    record->payload.gnss_measurement.position_enu_m[0] = 20.25F;
    record->payload.gnss_measurement.position_enu_m[1] = 24.25F;
    record->payload.gnss_measurement.position_enu_m[2] = 28.25F;
    record->payload.gnss_measurement.velocity_enu_mps[0] = 32.25F;
    record->payload.gnss_measurement.velocity_enu_mps[1] = 36.25F;
    record->payload.gnss_measurement.velocity_enu_mps[2] = 40.25F;
    record->payload.gnss_measurement.position_variance_m2[0] = 44.25F;
    record->payload.gnss_measurement.position_variance_m2[1] = 48.25F;
    record->payload.gnss_measurement.position_variance_m2[2] = 52.25F;
    record->payload.gnss_measurement.velocity_variance_m2ps2[0] = 56.25F;
    record->payload.gnss_measurement.velocity_variance_m2ps2[1] = 60.25F;
    record->payload.gnss_measurement.velocity_variance_m2ps2[2] = 64.25F;
    record->payload.gnss_measurement.velocity_valid_mask = 0xD3U;
    record->payload.gnss_measurement.position_usable = 0xD6U;
    record->payload.gnss_measurement.fusion_allowed = 0xD9U;
    record->payload.gnss_measurement.reserved = 0xDCU;
    record->payload.gnss_measurement.position_measurement_timestamp_us = 0xFEDCBA9800000048ULL;
    record->payload.gnss_measurement.velocity_measurement_timestamp_us = 0xFEDCBA9800000050ULL;
    record->payload.gnss_measurement.estimator_present_timestamp_us = 0xFEDCBA9800000058ULL;
    record->payload.gnss_measurement.receive_operation_sequence = 0x87650060U;
    record->payload.gnss_measurement.position_operation_sequence = 0x87650064U;
    record->payload.gnss_measurement.velocity_operation_sequence = 0x87650068U;
    record->payload.gnss_measurement.replay_epoch = 0x8765006CU;
    record->payload.gnss_measurement.replay_generation = 0x87650070U;
    record->payload.gnss_measurement.valid_group_mask = 0x63U;
    record->payload.gnss_measurement.position_replay_result = 0x66U;
    record->payload.gnss_measurement.velocity_replay_result = 0x69U;
    record->payload.gnss_measurement.receive_result = 0x6CU;
    record->payload.gnss_measurement.group_update_result[0] = 0x6FU;
    record->payload.gnss_measurement.group_update_result[1] = 0x72U;
    record->payload.gnss_measurement.group_update_result[2] = 0x75U;
    record->payload.gnss_measurement.group_update_result[3] = 0x78U;
    record->payload.gnss_measurement.group_nis[0] = 124.25F;
    record->payload.gnss_measurement.group_nis[1] = 128.25F;
    record->payload.gnss_measurement.group_nis[2] = 132.25F;
    record->payload.gnss_measurement.group_nis[3] = 136.25F;
    record->payload.gnss_measurement.position_innovation_m[0] = 140.25F;
    record->payload.gnss_measurement.position_innovation_m[1] = 144.25F;
    record->payload.gnss_measurement.position_innovation_m[2] = 148.25F;
    record->payload.gnss_measurement.velocity_innovation_mps[0] = 152.25F;
    record->payload.gnss_measurement.velocity_innovation_mps[1] = 156.25F;
    record->payload.gnss_measurement.velocity_innovation_mps[2] = 160.25F;
    record->payload.gnss_measurement.position_source_timestamp_us = 0xFEDCBA98000000A4ULL;
    record->payload.gnss_measurement.velocity_source_timestamp_us = 0xFEDCBA98000000ACULL;
    record->payload.gnss_measurement.position_application_timestamp_us = 0xFEDCBA98000000B4ULL;
    record->payload.gnss_measurement.velocity_application_timestamp_us = 0xFEDCBA98000000BCULL;
    record->payload.gnss_measurement.fusion_timing_mode = 0x1U;
    record->payload.gnss_measurement.position_timing_flags = 0xBU;
    record->payload.gnss_measurement.velocity_timing_flags = 0x7U;
    record->payload.gnss_measurement.position_execution_result = 0x0U;
    record->payload.gnss_measurement.velocity_execution_result = 0x6U;
    record->payload.gnss_measurement.timing_reserved[0] = 0x0U;
    record->payload.gnss_measurement.timing_reserved[1] = 0x0U;
    record->payload.gnss_measurement.timing_reserved[2] = 0x0U;
    record->payload.gnss_measurement.source_id = 0x876500CCU;
    record->payload.gnss_measurement.calibration_generation = 0x876500D0U;
}

static const uint8_t s_baro_wire[100] = {
    0x00U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0x08U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x10U, 0x00U, 0x65U, 0x87U, 0x00U, 0x00U, 0xA2U, 0x41U,
    0x00U, 0x00U, 0xC2U, 0x41U, 0x1CU, 0x00U, 0x65U, 0x87U, 0x20U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x28U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU,
    0x30U, 0x00U, 0x65U, 0x87U, 0x34U, 0x00U, 0x65U, 0x87U, 0x38U, 0x00U, 0x65U, 0x87U,
    0xBBU, 0xBEU, 0xC1U, 0xC4U, 0x00U, 0x80U, 0x80U, 0x42U, 0x00U, 0x80U, 0x88U, 0x42U,
    0x48U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0x50U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x01U, 0x0BU, 0x00U, 0x00U, 0x5CU, 0x00U, 0x65U, 0x87U,
    0x60U, 0x00U, 0x65U, 0x87U,
};

static void Test_BaroFill(FlightLogRecord *record)
{
    (void)memset(record, 0, sizeof(*record));
    record->record_type = FLIGHT_LOG_RECORD_BARO_MEASUREMENT;
    record->timestamp_us = 0x123456789ABCDEF0ULL;
    record->valid_flags = 0xBADC0FFEU;
    record->payload.baro_measurement.sample_timestamp_us = 0xFEDCBA9800000000ULL;
    record->payload.baro_measurement.receive_timestamp_us = 0xFEDCBA9800000008ULL;
    record->payload.baro_measurement.sequence = 0x87650010U;
    record->payload.baro_measurement.relative_altitude_m = 20.25F;
    record->payload.baro_measurement.variance_m2 = 24.25F;
    record->payload.baro_measurement.valid_mask = 0x8765001CU;
    record->payload.baro_measurement.measurement_timestamp_us = 0xFEDCBA9800000020ULL;
    record->payload.baro_measurement.estimator_present_timestamp_us = 0xFEDCBA9800000028ULL;
    record->payload.baro_measurement.operation_sequence = 0x87650030U;
    record->payload.baro_measurement.replay_epoch = 0x87650034U;
    record->payload.baro_measurement.replay_generation = 0x87650038U;
    record->payload.baro_measurement.update_result = 0xBBU;
    record->payload.baro_measurement.replay_result = 0xBEU;
    record->payload.baro_measurement.measurement_timestamp_trusted = 0xC1U;
    record->payload.baro_measurement.reserved = 0xC4U;
    record->payload.baro_measurement.innovation_m = 64.25F;
    record->payload.baro_measurement.nis = 68.25F;
    record->payload.baro_measurement.source_timestamp_us = 0xFEDCBA9800000048ULL;
    record->payload.baro_measurement.application_timestamp_us = 0xFEDCBA9800000050ULL;
    record->payload.baro_measurement.fusion_timing_mode = 0x1U;
    record->payload.baro_measurement.timing_flags = 0xBU;
    record->payload.baro_measurement.execution_result = 0x0U;
    record->payload.baro_measurement.timing_reserved = 0x0U;
    record->payload.baro_measurement.source_id = 0x8765005CU;
    record->payload.baro_measurement.calibration_generation = 0x87650060U;
}

static const uint8_t s_eskf_wire[116] = {
    0x00U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0x08U, 0x00U, 0x00U, 0x00U,
    0x98U, 0xBAU, 0xDCU, 0xFEU, 0x10U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU,
    0x18U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU, 0x20U, 0x00U, 0x65U, 0x87U,
    0x24U, 0x00U, 0x65U, 0x87U, 0x28U, 0x00U, 0x65U, 0x87U, 0x2CU, 0x00U, 0x65U, 0x87U,
    0x97U, 0x9AU, 0x9DU, 0xA0U, 0x00U, 0x00U, 0x51U, 0x42U, 0x00U, 0x00U, 0x61U, 0x42U,
    0x00U, 0x00U, 0x71U, 0x42U, 0x00U, 0x80U, 0x80U, 0x42U, 0x00U, 0x80U, 0x88U, 0x42U,
    0x00U, 0x80U, 0x90U, 0x42U, 0x00U, 0x80U, 0x98U, 0x42U, 0x00U, 0x80U, 0xA0U, 0x42U,
    0x00U, 0x80U, 0xA8U, 0x42U, 0x00U, 0x80U, 0xB0U, 0x42U, 0x00U, 0x80U, 0xB8U, 0x42U,
    0x00U, 0x80U, 0xC0U, 0x42U, 0x64U, 0x00U, 0x00U, 0x00U, 0x98U, 0xBAU, 0xDCU, 0xFEU,
    0x01U, 0x0BU, 0x00U, 0x00U, 0x70U, 0x00U, 0x65U, 0x87U,
};

static void Test_EskfFill(FlightLogRecord *record)
{
    (void)memset(record, 0, sizeof(*record));
    record->record_type = FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT;
    record->timestamp_us = 0x123456789ABCDEF0ULL;
    record->valid_flags = 0xBADC0FFEU;
    record->payload.eskf15_measurement.sample_timestamp_us = 0xFEDCBA9800000000ULL;
    record->payload.eskf15_measurement.receive_timestamp_us = 0xFEDCBA9800000008ULL;
    record->payload.eskf15_measurement.measurement_timestamp_us = 0xFEDCBA9800000010ULL;
    record->payload.eskf15_measurement.evaluation_timestamp_us = 0xFEDCBA9800000018ULL;
    record->payload.eskf15_measurement.operation_sequence = 0x87650020U;
    record->payload.eskf15_measurement.epoch = 0x87650024U;
    record->payload.eskf15_measurement.source_id = 0x87650028U;
    record->payload.eskf15_measurement.calibration_generation = 0x8765002CU;
    record->payload.eskf15_measurement.group = 0x97U;
    record->payload.eskf15_measurement.physically_valid = 0x9AU;
    record->payload.eskf15_measurement.admitted = 0x9DU;
    record->payload.eskf15_measurement.update_result = 0xA0U;
    record->payload.eskf15_measurement.observation[0] = 52.25F;
    record->payload.eskf15_measurement.observation[1] = 56.25F;
    record->payload.eskf15_measurement.innovation[0] = 60.25F;
    record->payload.eskf15_measurement.innovation[1] = 64.25F;
    record->payload.eskf15_measurement.base_variance[0] = 68.25F;
    record->payload.eskf15_measurement.base_variance[1] = 72.25F;
    record->payload.eskf15_measurement.effective_variance[0] = 76.25F;
    record->payload.eskf15_measurement.effective_variance[1] = 80.25F;
    record->payload.eskf15_measurement.nis = 84.25F;
    record->payload.eskf15_measurement.quality_scale = 88.25F;
    record->payload.eskf15_measurement.consistency_scale = 92.25F;
    record->payload.eskf15_measurement.robust_scale = 96.25F;
    record->payload.eskf15_measurement.application_timestamp_us = 0xFEDCBA9800000064ULL;
    record->payload.eskf15_measurement.fusion_timing_mode = 0x1U;
    record->payload.eskf15_measurement.timing_flags = 0xBU;
    record->payload.eskf15_measurement.execution_result = 0x0U;
    record->payload.eskf15_measurement.timing_reserved = 0x0U;
    record->payload.eskf15_measurement.source_sequence = 0x87650070U;
}


static void Test_ExactWire(const FlightLogRecord *record, const uint8_t *expected,
                           uint16_t size, uint16_t prefix_size)
{
    FlightLogRecord decoded = {0};
    uint8_t actual[SSLOG_MAX_PAYLOAD_SIZE + 1U];
    uint8_t roundtrip[SSLOG_MAX_PAYLOAD_SIZE];
    const SslogRecordMetadata *metadata = SslogRecords_MetadataGet(record->record_type);
    TEST_CHECK(metadata != NULL);
    TEST_CHECK(metadata->record_version == 2U && metadata->payload_size == size);
    (void)memset(actual, 0xA5, sizeof(actual));
    TEST_CHECK(SslogRecords_PayloadSerialize(record, actual, size) == size);
    TEST_CHECK(memcmp(actual, expected, prefix_size) == 0);
    TEST_CHECK(memcmp(actual, expected, size) == 0);
    TEST_CHECK(actual[size] == 0xA5U);
    decoded.record_type = record->record_type;
    TEST_CHECK(SslogRecords_PayloadDeserialize(&decoded, expected, size) == size);
    TEST_CHECK(memcmp(&decoded.payload, &record->payload, sizeof(decoded.payload)) == 0);
    TEST_CHECK(SslogRecords_PayloadSerialize(&decoded, roundtrip, size) == size);
    TEST_CHECK(memcmp(expected, roundtrip, size) == 0);
}

static void Test_PayloadBounds(const FlightLogRecord *record, uint16_t size)
{
    uint8_t bytes[SSLOG_MAX_PAYLOAD_SIZE];
    uint8_t untouched[SSLOG_MAX_PAYLOAD_SIZE];
    FlightLogRecord decoded;
    FlightLogRecord before;
    (void)memset(untouched, 0xA5, sizeof(untouched));
    for (uint16_t capacity = 0U; capacity < size; capacity++)
    {
        (void)memcpy(bytes, untouched, sizeof(bytes));
        TEST_CHECK(SslogRecords_PayloadSerialize(record, bytes, capacity) == 0U);
        TEST_CHECK(memcmp(bytes, untouched, sizeof(bytes)) == 0);
        (void)memset(&decoded, 0x5A, sizeof(decoded));
        decoded.record_type = record->record_type;
        (void)memcpy(&before, &decoded, sizeof(before));
        TEST_CHECK(SslogRecords_PayloadDeserialize(&decoded, bytes, capacity) == 0U);
        TEST_CHECK(memcmp(&before, &decoded, sizeof(decoded)) == 0);
    }
}

static void Test_FrameBounds(const FlightLogRecord *record, uint16_t payload_size)
{
    uint8_t bytes[FLIGHT_LOG_MAX_RECORD_SIZE];
    uint8_t untouched[FLIGHT_LOG_MAX_RECORD_SIZE];
    FlightLogRecord decoded;
    FlightLogRecord before;
    uint32_t sequence = 0U;
    uint16_t written = 0U;
    const uint16_t total = (uint16_t)(FLIGHT_LOG_RECORD_HEADER_SIZE + payload_size + FLIGHT_LOG_RECORD_CRC_SIZE);
    (void)memset(untouched, 0xA5, sizeof(untouched));
    for (uint16_t capacity = 0U; capacity < total; capacity++)
    {
        (void)memcpy(bytes, untouched, sizeof(bytes));
        written = 0xBEEFU;
        TEST_CHECK(FlightLog_RecordSerialize(record, 0x12345678U, bytes, capacity, &written) == FLIGHT_LOG_SERIALIZE_RESULT_BUFFER_SMALL);
        TEST_CHECK(written == 0xBEEFU && memcmp(bytes, untouched, sizeof(bytes)) == 0);
    }
    TEST_CHECK(FlightLog_RecordSerialize(record, 0x12345678U, bytes, total, &written) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
    TEST_CHECK(written == total && bytes[4] == 2U);
    for (uint16_t length = 0U; length < total; length++)
    {
        (void)memset(&decoded, 0x5A, sizeof(decoded));
        (void)memcpy(&before, &decoded, sizeof(before));
        sequence = 0xDEADBEEFU; written = 0xBEEFU;
        TEST_CHECK(FlightLog_RecordDeserialize(bytes, length, &decoded, &sequence, &written) == FLIGHT_LOG_DESERIALIZE_RESULT_BUFFER_SMALL);
        TEST_CHECK(sequence == 0xDEADBEEFU && written == 0xBEEFU);
        TEST_CHECK(memcmp(&before, &decoded, sizeof(decoded)) == 0);
    }
    TEST_CHECK(FlightLog_RecordDeserialize(bytes, total, &decoded, &sequence, &written) == FLIGHT_LOG_DESERIALIZE_RESULT_OK);
    TEST_CHECK(sequence == 0x12345678U && written == total);
    TEST_CHECK(decoded.timestamp_us == record->timestamp_us && decoded.valid_flags == record->valid_flags);
    TEST_CHECK(memcmp(&decoded.payload, &record->payload, sizeof(decoded.payload)) == 0);
    bytes[4] = 1U;
    TEST_CHECK(FlightLog_RecordDeserialize(bytes, total, &decoded, &sequence, &written) == FLIGHT_LOG_DESERIALIZE_RESULT_BAD_VERSION);
    bytes[4] = 2U; bytes[6]--;
    TEST_CHECK(FlightLog_RecordDeserialize(bytes, total, &decoded, &sequence, &written) == FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SIZE);
    bytes[6]++; bytes[FLIGHT_LOG_RECORD_HEADER_SIZE] ^= 1U;
    TEST_CHECK(FlightLog_RecordDeserialize(bytes, total, &decoded, &sequence, &written) == FLIGHT_LOG_DESERIALIZE_RESULT_BAD_CRC);
}

static void Test_CurrentPrefix(FlightLogRecord *record, const uint8_t *legacy,
                               uint16_t size, uint16_t prefix, uint16_t mode_offset)
{
    uint8_t bytes[SSLOG_MAX_PAYLOAD_SIZE];
    if (record->record_type == FLIGHT_LOG_RECORD_GNSS_MEASUREMENT)
    { record->payload.gnss_measurement.fusion_timing_mode = 0U; }
    else if (record->record_type == FLIGHT_LOG_RECORD_BARO_MEASUREMENT)
    { record->payload.baro_measurement.fusion_timing_mode = 0U; }
    else { record->payload.eskf15_measurement.fusion_timing_mode = 0U; }
    TEST_CHECK(SslogRecords_PayloadSerialize(record, bytes, size) == size);
    TEST_CHECK(memcmp(bytes, legacy, prefix) == 0);
    TEST_CHECK(bytes[mode_offset] == 0U);
}

static void Test_OpaqueEvidence(void)
{
    FlightLogRecord record = {0};
    FlightLogRecord decoded = {0};
    uint8_t wire[100];
    record.record_type = FLIGHT_LOG_RECORD_BARO_MEASUREMENT;
    record.payload.baro_measurement.receive_timestamp_us = UINT64_MAX;
    record.payload.baro_measurement.source_timestamp_us = UINT64_MAX;
    record.payload.baro_measurement.fusion_timing_mode = 255U;
    record.payload.baro_measurement.timing_flags = 255U;
    record.payload.baro_measurement.execution_result = 255U;
    record.payload.baro_measurement.timing_reserved = 255U;
    decoded.record_type = record.record_type;
    /* Fault or unknown semantic evidence is retained by the transport codec;
     * the exact-revision semantic validator must reject it for replay claims. */
    TEST_CHECK(SslogRecords_PayloadSerialize(&record, wire, sizeof(wire)) == sizeof(wire));
    TEST_CHECK(SslogRecords_PayloadDeserialize(&decoded, wire, sizeof(wire)) == sizeof(wire));
    TEST_CHECK(memcmp(&record.payload, &decoded.payload, sizeof(record.payload)) == 0);
}

#ifdef FUSION_TIMING_RECORDS_LOGGER_TEST
static void Test_LoggerCapacity(void)
{
    FlightLogRecord source;
    FlightLogRecord popped;
    SystemLogStreamConfig config = {0};
    LoggerBusDiagnostics diagnostics;
    HostPlatformMock_Reset();
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    LoggerBus_Reset();
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    config.enabled = 1U; config.decimation = 1U; config.policy = SSLOG_STREAM_POLICY_EVERY;
    config.record_type = FLIGHT_LOG_RECORD_GNSS_MEASUREMENT;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    Test_GnssFill(&source);
    TEST_CHECK(offsetof(FlightLogRecord, payload) + sizeof(source.payload.gnss_measurement) <= SYSTEM_LOG_ESTIMATOR_SLOT_SIZE);
    for (uint16_t i = 0U; i < SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH; i++)
    {
        source.payload.gnss_measurement.sequence = i;
        TEST_CHECK(LoggerBus_GnssMeasurementPush(i + 1U, 0U, &source.payload.gnss_measurement) == LOGGER_BUS_RESULT_OK);
    }
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(diagnostics.estimator_count == SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH && diagnostics.capacity_reject_count == 0U);
    TEST_CHECK(LoggerBus_GnssMeasurementPush(999U, 0U, &source.payload.gnss_measurement) == LOGGER_BUS_RESULT_FULL);
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(diagnostics.estimator_count == SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH && diagnostics.capacity_reject_count == 1U);
    for (uint16_t i = 0U; i < SYSTEM_LOG_ESTIMATOR_QUEUE_DEPTH; i++)
    {
        source.payload.gnss_measurement.sequence = i;
        TEST_CHECK(LoggerBus_EstimatorPop(&popped) == LOGGER_BUS_RESULT_OK);
        TEST_CHECK(popped.record_type == source.record_type);
        TEST_CHECK(memcmp(&popped.payload, &source.payload, sizeof(source.payload)) == 0);
    }
    TEST_CHECK(LoggerBus_EstimatorPop(&popped) == LOGGER_BUS_RESULT_EMPTY);
    config.record_type = FLIGHT_LOG_RECORD_BARO_MEASUREMENT;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    Test_BaroFill(&source);
    TEST_CHECK(LoggerBus_BaroMeasurementPush(1000U, 0U, &source.payload.baro_measurement) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_EstimatorPop(&popped) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(memcmp(&popped.payload, &source.payload, sizeof(source.payload)) == 0);
    config.record_type = FLIGHT_LOG_RECORD_ESKF15_MEASUREMENT;
#if SYSTEM_BUILD_ESKF15_ENABLED != 0U
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_OK);
    Test_EskfFill(&source);
    TEST_CHECK(LoggerBus_Eskf15MeasurementPush(1001U, &source.payload.eskf15_measurement) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_EstimatorPop(&popped) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(memcmp(&popped.payload, &source.payload, sizeof(source.payload)) == 0);
#else
    LoggerBusDiagnostics before;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemLogPolicy_IsEnabled(config.record_type) == 0U);
    TEST_CHECK(LoggerBus_DiagnosticsGet(&before) == LOGGER_BUS_RESULT_OK);
    Test_EskfFill(&source);
    /* Disabled streams are filtered before queue admission; OK is not delivery. */
    TEST_CHECK(LoggerBus_Eskf15MeasurementPush(1001U, &source.payload.eskf15_measurement) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_EstimatorPop(&popped) == LOGGER_BUS_RESULT_EMPTY);
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(diagnostics.accepted_count == before.accepted_count && diagnostics.estimator_count == 0U);
    (void)puts("FCCG_HOST_NOT_APPLICABLE|fusion_timing_eskf_queue_positive|ESKF not selected; unsupported-stream rejection exercised");
#endif
}
#endif

int main(void)
{
    FlightLogRecord record;
    Test_GnssFill(&record);
    Test_ExactWire(&record, s_gnss_wire, 212U, 164U);
    Test_PayloadBounds(&record, 212U);
    Test_FrameBounds(&record, 212U);
    Test_CurrentPrefix(&record, s_gnss_wire, 212U, 164U, 196U);
    Test_BaroFill(&record);
    Test_ExactWire(&record, s_baro_wire, 100U, 72U);
    Test_PayloadBounds(&record, 100U);
    Test_FrameBounds(&record, 100U);
    Test_CurrentPrefix(&record, s_baro_wire, 100U, 72U, 88U);
    Test_EskfFill(&record);
    Test_ExactWire(&record, s_eskf_wire, 116U, 100U);
    Test_PayloadBounds(&record, 116U);
    Test_FrameBounds(&record, 116U);
    Test_CurrentPrefix(&record, s_eskf_wire, 116U, 100U, 108U);
    Test_OpaqueEvidence();
#ifdef FUSION_TIMING_RECORDS_LOGGER_TEST
    Test_LoggerCapacity();
#endif
    (void)printf("timing record RAM: header=%zu GNSS=%zu BARO=%zu ESKF=%zu record=%zu\n",
        offsetof(FlightLogRecord, payload), sizeof(FlightLogGnssMeasurementRecord),
        sizeof(FlightLogBaroMeasurementRecord), sizeof(FlightLogEskf15MeasurementRecord), sizeof(FlightLogRecord));
    return Test_Finish("fusion_timing_records");
}

