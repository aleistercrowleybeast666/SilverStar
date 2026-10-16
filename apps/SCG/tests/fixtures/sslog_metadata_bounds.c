/* Fault seam for the metadata dependency of the ACTUAL frame codec.
 * A large backing array safely exposes writes beyond the advertised capacity.
 * This is not a complete-record codec or hardware fixture. */
#include "sslog_protocol.h"
#include <string.h>

static SslogRecordMetadata s_test_metadata = {FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT,1U,120U,"FaultMetadata"};

void Test_MetadataBounds(uint32_t payload_size, uint32_t decode, uint32_t result[4]);

const SslogRecordMetadata *SslogRecords_MetadataGet(FlightLogRecordType type)
{ return (type == s_test_metadata.record_type) ? &s_test_metadata : NULL; }
uint16_t SslogRecords_PayloadSerialize(const FlightLogRecord *record, uint8_t *buffer, uint16_t capacity)
{
    (void)record;
    if (capacity == 0U) { return 0U; }
    if (capacity < 120U) { return 0U; }
    memset(buffer,0x3C,120U); return 120U;
}
uint16_t SslogRecords_PayloadDeserialize(FlightLogRecord *record, const uint8_t *buffer, uint16_t size)
{
    if (size == 0U) { return 0U; }
    if (size < 120U) { return 0U; }
    memcpy(&record->payload,buffer,120U); return 120U;
}

void Test_MetadataBounds(uint32_t payload_size, uint32_t decode, uint32_t result[4])
{
    uint8_t backing[284], before[284];
    FlightLogRecord record, previous;
    uint16_t size = 0xBEEFU;
    uint32_t sequence = 0xDEADBEEFUL;
    s_test_metadata.payload_size = (uint16_t)payload_size;
    memset(backing,0xA5,sizeof(backing)); memset(&record,0,sizeof(record));
    record.record_type = FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT;
    memcpy(before,backing,sizeof(before));
    if (decode == 0U)
    {
        result[0] = (uint32_t)FlightLog_RecordSerialize(&record,17U,backing,32U,&size);
        result[1] = (uint32_t)(memcmp(before,backing,sizeof(backing)) != 0);
        result[2] = (uint32_t)(memcmp(before+32,backing+32,sizeof(backing)-32U) != 0);
    }
    else
    {
        uint16_t total = (uint16_t)(28U+s_test_metadata.payload_size);
        backing[0] = 'F'; backing[1] = 'L'; backing[2] = 'G'; backing[3] = '1';
        backing[4] = 1U; backing[5] = 0x2DU;
        backing[6] = (uint8_t)payload_size; backing[7] = (uint8_t)(payload_size>>8U);
        if ((total >= 4U) && (total <= sizeof(backing)))
        {
            uint32_t crc = FlightLog_Crc32(backing,(uint32_t)total-4U);
            for (uint32_t i = 0U; i < 4U; i++) { backing[total-4U+i] = (uint8_t)(crc>>(8U*i)); }
        }
        memset(&record,0x5A,sizeof(record)); previous = record;
        result[0] = (uint32_t)FlightLog_RecordDeserialize(backing,32U,&record,&sequence,&size);
        result[1] = (uint32_t)(memcmp(&record,&previous,sizeof(record)) != 0);
        result[2] = (uint32_t)(sequence != 0xDEADBEEFUL);
    }
    result[3] = size;
}
