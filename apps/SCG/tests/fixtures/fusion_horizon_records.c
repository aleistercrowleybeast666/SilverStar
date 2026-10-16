#include "sslog_protocol.h"
#include <string.h>

int Test_HorizonSerialize(uint32_t kind, const void *payload, uint8_t *wire, uint16_t capacity);
int Test_HorizonDeserialize(const uint8_t *wire, uint16_t size, void *payload);

int Test_HorizonSerialize(uint32_t kind, const void *payload, uint8_t *wire, uint16_t capacity)
{
    FlightLogRecord record;
    uint16_t size = 0U;
    memset(&record, 0, sizeof(record));
    record.record_type = (FlightLogRecordType)kind;
    record.timestamp_us = 0x1020304050607080ULL;
    record.valid_flags = 0x12345678UL;
    if (kind == FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT)
    { memcpy(&record.payload.fusion_horizon_measurement, payload, sizeof(FlightLogFusionHorizonMeasurementRecord)); }
    else if (kind == FLIGHT_LOG_RECORD_FUSION_HORIZON_STATUS)
    { memcpy(&record.payload.fusion_horizon_status, payload, sizeof(FlightLogFusionHorizonStatusRecord)); }
    else { return -1; }
    if (FlightLog_RecordSerialize(&record, 0x89ABCDEFUL, wire, capacity, &size) != FLIGHT_LOG_SERIALIZE_RESULT_OK)
    { return -2; }
    return (int)size;
}

int Test_HorizonDeserialize(const uint8_t *wire, uint16_t size, void *payload)
{
    FlightLogRecord record;
    uint32_t sequence = 0U;
    uint16_t consumed = 0U;
    FlightLogDeserializeResult result = FlightLog_RecordDeserialize(wire, size, &record, &sequence, &consumed);
    if (result != FLIGHT_LOG_DESERIALIZE_RESULT_OK) { return (int)result; }
    if ((sequence != 0x89ABCDEFUL) || (consumed != size) ||
        (record.timestamp_us != 0x1020304050607080ULL) || (record.valid_flags != 0x12345678UL)) { return -1; }
    if (record.record_type == FLIGHT_LOG_RECORD_FUSION_HORIZON_MEASUREMENT)
    { memcpy(payload, &record.payload.fusion_horizon_measurement, sizeof(FlightLogFusionHorizonMeasurementRecord)); }
    else if (record.record_type == FLIGHT_LOG_RECORD_FUSION_HORIZON_STATUS)
    { memcpy(payload, &record.payload.fusion_horizon_status, sizeof(FlightLogFusionHorizonStatusRecord)); }
    else { return -2; }
    return 0;
}
