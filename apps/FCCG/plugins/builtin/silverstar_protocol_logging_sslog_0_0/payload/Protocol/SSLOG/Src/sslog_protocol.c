#include "sslog_protocol.h"

#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define SSLOG_RECORD_SYNC 0x31474C46UL

typedef struct
{
    const SslogRecordMetadata *metadata;
    FlightLogRecordType record_type;
    uint16_t payload_size;
    uint16_t total_size;
} SslogRecordDecodeContext;

static void Sslog_U16Put(uint8_t *buffer, uint16_t value)
{
    buffer[0] = (uint8_t)(value & 0xFFU);
    buffer[1] = (uint8_t)((value >> 8U) & 0xFFU);
}

static void Sslog_U32Put(uint8_t *buffer, uint32_t value)
{
    buffer[0] = (uint8_t)(value & 0xFFU);
    buffer[1] = (uint8_t)((value >> 8U) & 0xFFU);
    buffer[2] = (uint8_t)((value >> 16U) & 0xFFU);
    buffer[3] = (uint8_t)((value >> 24U) & 0xFFU);
}

static void Sslog_U64Put(uint8_t *buffer, uint64_t value)
{
    uint8_t index;

    for (index = 0U; index < 8U; index++)
    {
        buffer[index] = (uint8_t)((value >> (index * 8U)) & 0xFFU);
    }
}

static void Sslog_F32Put(uint8_t *buffer, float value)
{
    uint32_t bits;

    (void)memcpy(&bits, &value, sizeof(bits));
    Sslog_U32Put(buffer, bits);
}

static uint16_t Sslog_U16Get(const uint8_t *buffer)
{
    return (uint16_t)((uint16_t)buffer[0] |
        ((uint16_t)buffer[1] << 8U));
}

static uint32_t Sslog_U32Get(const uint8_t *buffer)
{
    return (uint32_t)buffer[0] |
        ((uint32_t)buffer[1] << 8U) |
        ((uint32_t)buffer[2] << 16U) |
        ((uint32_t)buffer[3] << 24U);
}

static uint64_t Sslog_U64Get(const uint8_t *buffer)
{
    uint64_t value = 0U;
    uint8_t index;

    for (index = 0U; index < 8U; index++)
    {
        value |= ((uint64_t)buffer[index] << (index * 8U));
    }
    return value;
}

uint32_t FlightLog_Crc32(const uint8_t *data, uint32_t length)
{
    uint32_t crc = 0xFFFFFFFFUL;
    uint32_t index;
    uint8_t bit;

    if ((data == NULL) || (length > FLIGHT_LOG_MAX_RECORD_SIZE))
    {
        return 0U;
    }
    for (index = 0U; index < length; index++)
    {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; bit++)
        {
            crc = ((crc & 1U) != 0U) ?
                ((crc >> 1U) ^ 0xEDB88320UL) : (crc >> 1U);
        }
    }
    return crc ^ 0xFFFFFFFFUL;
}

FlightLogSerializeResult FlightLog_FileHeaderSerialize(
    const FlightLogFileHeaderInfo *info, uint8_t *buffer,
    uint16_t buffer_capacity, uint16_t *serialized_size)
{
    static const uint8_t magic[8] =
        { 'S', 'S', 'L', 'O', 'G', '0', 0U, 0U };
    uint32_t crc;

    if ((info == NULL) || (buffer == NULL) || (serialized_size == NULL))
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(info, FlightLogFileHeaderInfo,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (buffer_capacity < FLIGHT_LOG_FILE_HEADER_SIZE)
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BUFFER_SMALL;
    }

    (void)memset(buffer, 0, FLIGHT_LOG_FILE_HEADER_SIZE);
    (void)memcpy(&buffer[0], magic, sizeof(magic));
    Sslog_U16Put(&buffer[8], info->profile_id);
    Sslog_U16Put(&buffer[10], FLIGHT_LOG_FILE_HEADER_SIZE);
    Sslog_U16Put(&buffer[12], FLIGHT_LOG_RECORD_HEADER_SIZE);
    Sslog_U16Put(&buffer[14], info->nominal_imu_rate_hz);
    Sslog_U16Put(&buffer[16], info->nominal_ins_rate_hz);
    buffer[18] = info->coordinate_frame;
    (void)memcpy(&buffer[19], info->position_axis_order,
                 sizeof(info->position_axis_order));
    buffer[22] = info->quaternion_order;
    buffer[23] = info->quaternion_semantics;
    Sslog_F32Put(&buffer[24], info->local_gravity_mps2);
    (void)memcpy(&buffer[28], info->air_compatibility_tag,
                 sizeof(info->air_compatibility_tag));
    (void)memcpy(&buffer[36], info->build_tag, sizeof(info->build_tag));
    Sslog_U16Put(&buffer[44], FLIGHT_LOG_RECORD_CRC_SIZE);
    Sslog_U16Put(&buffer[46], info->mechanization_subsample_count);
    (void)memcpy(&buffer[48], info->firmware_version,
                 sizeof(info->firmware_version));
    Sslog_U16Put(&buffer[52], FLIGHT_LOG_MAX_RECORD_SIZE);
    crc = FlightLog_Crc32(buffer, FLIGHT_LOG_FILE_HEADER_SIZE - 4U);
    Sslog_U32Put(&buffer[FLIGHT_LOG_FILE_HEADER_SIZE - 4U], crc);
    *serialized_size = FLIGHT_LOG_FILE_HEADER_SIZE;
    return FLIGHT_LOG_SERIALIZE_RESULT_OK;
}

FlightLogSerializeResult FlightLog_RecordSerialize(
    const FlightLogRecord *record, uint32_t record_sequence,
    uint8_t *buffer, uint16_t buffer_capacity, uint16_t *serialized_size)
{
    const SslogRecordMetadata *metadata;
    uint16_t payload_written;
    uint16_t total_size;
    uint32_t crc;

    if ((record == NULL) || (buffer == NULL) || (serialized_size == NULL))
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    metadata = SslogRecords_MetadataGet(record->record_type);
    if (metadata == NULL)
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_TYPE;
    }
    total_size = (uint16_t)(FLIGHT_LOG_RECORD_HEADER_SIZE +
                            metadata->payload_size +
                            FLIGHT_LOG_RECORD_CRC_SIZE);
    if (buffer_capacity < total_size)
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BUFFER_SMALL;
    }

    (void)memset(buffer, 0, total_size);
    Sslog_U32Put(&buffer[0], SSLOG_RECORD_SYNC);
    buffer[4] = metadata->record_version;
    buffer[5] = (uint8_t)record->record_type;
    Sslog_U16Put(&buffer[6], metadata->payload_size);
    Sslog_U32Put(&buffer[8], record_sequence);
    Sslog_U64Put(&buffer[12], record->timestamp_us);
    Sslog_U32Put(&buffer[20], record->valid_flags);
    payload_written = SslogRecords_PayloadSerialize(
        record, &buffer[FLIGHT_LOG_RECORD_HEADER_SIZE], metadata->payload_size);
    if (payload_written != metadata->payload_size)
    {
        return FLIGHT_LOG_SERIALIZE_RESULT_BAD_TYPE;
    }
    crc = FlightLog_Crc32(
        buffer, FLIGHT_LOG_RECORD_HEADER_SIZE + metadata->payload_size);
    Sslog_U32Put(&buffer[FLIGHT_LOG_RECORD_HEADER_SIZE +
                        metadata->payload_size], crc);
    *serialized_size = total_size;
    return FLIGHT_LOG_SERIALIZE_RESULT_OK;
}

static FlightLogDeserializeResult Sslog_RecordHeaderParse(
    const uint8_t *buffer,
    uint16_t buffer_size,
    SslogRecordDecodeContext *context)
{
    SILVERSTAR_ASSERT_OBJECT(buffer, uint8_t,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    SILVERSTAR_ASSERT_OBJECT(context, SslogRecordDecodeContext,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    if (buffer_size < (FLIGHT_LOG_RECORD_HEADER_SIZE +
                       FLIGHT_LOG_RECORD_CRC_SIZE))
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BUFFER_SMALL;
    }
    if (Sslog_U32Get(&buffer[0]) != SSLOG_RECORD_SYNC)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SYNC;
    }
    context->record_type = (FlightLogRecordType)buffer[5];
    context->metadata = SslogRecords_MetadataGet(context->record_type);
    if (context->metadata == NULL)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_TYPE;
    }
    if (buffer[4] != context->metadata->record_version)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_VERSION;
    }
    context->payload_size = Sslog_U16Get(&buffer[6]);
    if (context->payload_size != context->metadata->payload_size)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_SIZE;
    }
    context->total_size = (uint16_t)(FLIGHT_LOG_RECORD_HEADER_SIZE +
        context->payload_size + FLIGHT_LOG_RECORD_CRC_SIZE);
    if (buffer_size < context->total_size)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BUFFER_SMALL;
    }
    return FLIGHT_LOG_DESERIALIZE_RESULT_OK;
}

FlightLogDeserializeResult FlightLog_RecordDeserialize(
    const uint8_t *buffer, uint16_t buffer_size, FlightLogRecord *record,
    uint32_t *record_sequence, uint16_t *deserialized_size)
{
    SslogRecordDecodeContext context;
    FlightLogDeserializeResult result;
    uint16_t payload_read;
    uint32_t stored_crc;
    uint32_t computed_crc;

    if ((buffer == NULL) || (record == NULL) || (record_sequence == NULL) ||
        (deserialized_size == NULL))
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogRecord,
                             SILVERSTAR_ASSERT_MODULE_PROTOCOL);
    result = Sslog_RecordHeaderParse(buffer, buffer_size, &context);
    if (result != FLIGHT_LOG_DESERIALIZE_RESULT_OK) { return result; }
    stored_crc = Sslog_U32Get(
        &buffer[context.total_size - FLIGHT_LOG_RECORD_CRC_SIZE]);
    computed_crc = FlightLog_Crc32(
        buffer, context.total_size - FLIGHT_LOG_RECORD_CRC_SIZE);
    if (stored_crc != computed_crc)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_CRC;
    }

    (void)memset(record, 0, sizeof(*record));
    record->record_type = context.record_type;
    record->timestamp_us = Sslog_U64Get(&buffer[12]);
    record->valid_flags = Sslog_U32Get(&buffer[20]);
    payload_read = SslogRecords_PayloadDeserialize(record,
        &buffer[FLIGHT_LOG_RECORD_HEADER_SIZE], context.payload_size);
    if (payload_read != context.payload_size)
    {
        return FLIGHT_LOG_DESERIALIZE_RESULT_BAD_TYPE;
    }

    *record_sequence = Sslog_U32Get(&buffer[8]);
    *deserialized_size = context.total_size;
    return FLIGHT_LOG_DESERIALIZE_RESULT_OK;
}
