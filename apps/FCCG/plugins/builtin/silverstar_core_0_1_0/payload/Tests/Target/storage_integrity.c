#include "storage_integrity.h"
#include <string.h>
#include "ff.h"
#include "sslog_protocol.h"

#define STORAGE_TEST_BYTE_WRITES 10000U
#define STORAGE_TEST_RECORDS 40000U
/* Bench-only static memory; this file is never in the production source graph. */
static FIL s_test_file;
static uint8_t s_test_buffer[550];
static uint8_t s_expected[FLIGHT_LOG_MAX_RECORD_SIZE];
static FlightLogRecord s_test_record;
static FlightLogRecord s_decoded_record;

static uint8_t StorageIntegrity_ByteGet(uint32_t offset)
{ return (uint8_t)((offset * 73U) ^ (offset >> 8U) ^ (offset >> 17U)); }

static StorageIntegrityResult StorageIntegrity_BytesCheck(void)
{
    static const UINT lengths[] = {1,2,3,4,7,31,60,88,91,119,127,255,256,257,511,512,513};
    uint32_t position = 0U;
    UINT transferred;
    if (f_open(&s_test_file, "0:/BYTECHK.BIN", FA_CREATE_NEW | FA_WRITE | FA_READ) != FR_OK)
    { return StorageIntegrityResult_IoError; }
    for (uint32_t index = 0U; index < STORAGE_TEST_BYTE_WRITES; index++)
    {
        UINT length = lengths[index % (sizeof(lengths) / sizeof(lengths[0]))];
        uint8_t *source = s_test_buffer + 1U + index % 31U;
        for (UINT i = 0U; i < length; i++) { source[i] = StorageIntegrity_ByteGet(position + i); }
        if (f_write(&s_test_file, source, length, &transferred) != FR_OK || transferred != length)
        { return StorageIntegrityResult_IoError; }
        position += length;
        if (index % 13U == 0U && f_sync(&s_test_file) != FR_OK)
        { return StorageIntegrityResult_IoError; }
    }
    if (f_size(&s_test_file) != position || f_close(&s_test_file) != FR_OK ||
        f_open(&s_test_file, "0:/BYTECHK.BIN", FA_READ) != FR_OK)
    { return StorageIntegrityResult_IoError; }
    for (uint32_t offset = 0U; offset < position;)
    {
        UINT length = position - offset > 513U ? 513U : position - offset;
        if (f_read(&s_test_file, s_test_buffer + 1U, length, &transferred) != FR_OK || transferred != length)
        { return StorageIntegrityResult_IoError; }
        for (UINT i = 0U; i < length; i++)
        {
            if (s_test_buffer[1U + i] != StorageIntegrity_ByteGet(offset + i))
            { return StorageIntegrityResult_ByteMismatch; }
        }
        offset += length;
    }
    return f_close(&s_test_file) == FR_OK ? StorageIntegrityResult_Ok : StorageIntegrityResult_IoError;
}

static FlightLogSerializeResult StorageIntegrity_RecordBuild(uint32_t index, uint16_t *length)
{
    static const FlightLogRecordType types[] = {
        FLIGHT_LOG_RECORD_IMU_CORRECTED,
        FLIGHT_LOG_RECORD_GNSS_NATIVE, FLIGHT_LOG_RECORD_BARO_NATIVE,
        FLIGHT_LOG_RECORD_ALIGNMENT_RESULT,
        FLIGHT_LOG_RECORD_CALIBRATION_RESULT, FLIGHT_LOG_RECORD_MISSION_CONFIG,
        FLIGHT_LOG_RECORD_INITIAL_STATE, FLIGHT_LOG_RECORD_EVENT, FLIGHT_LOG_RECORD_STATS};
    (void)memset(&s_test_record, 0, sizeof(s_test_record));
    s_test_record.record_type = types[index % (sizeof(types) / sizeof(types[0]))];
    s_test_record.timestamp_us = index * 1000ULL;
    s_test_record.valid_flags = index;
    return FlightLog_RecordSerialize(&s_test_record, index, s_expected, sizeof(s_expected), length);
}

static StorageIntegrityResult StorageIntegrity_RecordsCheck(void)
{
    FlightLogFileHeaderInfo header = {0};
    UINT transferred;
    uint16_t length;
    uint32_t expected_size = FLIGHT_LOG_FILE_HEADER_SIZE;
    if (FlightLog_FileHeaderSerialize(&header, s_expected, sizeof(s_expected), &length) != FLIGHT_LOG_SERIALIZE_RESULT_OK)
    { return StorageIntegrityResult_CodecError; }
    if (f_open(&s_test_file, "0:/LOGCHK.BIN", FA_CREATE_NEW | FA_WRITE | FA_READ) != FR_OK ||
        f_write(&s_test_file, s_expected, length, &transferred) != FR_OK || transferred != length)
    { return StorageIntegrityResult_IoError; }
    for (uint32_t index = 0U; index < STORAGE_TEST_RECORDS; index++)
    {
        uint8_t *source = s_test_buffer + 1U + index % 31U;
        if (StorageIntegrity_RecordBuild(index, &length) != FLIGHT_LOG_SERIALIZE_RESULT_OK)
        { return StorageIntegrityResult_CodecError; }
        (void)memcpy(source, s_expected, length);
        if (f_write(&s_test_file, source, length, &transferred) != FR_OK || transferred != length)
        { return StorageIntegrityResult_IoError; }
        expected_size += length;
        if (index % 47U == 0U && f_sync(&s_test_file) != FR_OK)
        { return StorageIntegrityResult_IoError; }
    }
    if (f_size(&s_test_file) != expected_size || f_close(&s_test_file) != FR_OK ||
        f_open(&s_test_file, "0:/LOGCHK.BIN", FA_READ) != FR_OK)
    { return StorageIntegrityResult_IoError; }
    if (FlightLog_FileHeaderSerialize(&header, s_expected, sizeof(s_expected), &length) != FLIGHT_LOG_SERIALIZE_RESULT_OK)
    { return StorageIntegrityResult_CodecError; }
    if (f_read(&s_test_file, s_test_buffer + 1U, length, &transferred) != FR_OK || transferred != length ||
        memcmp(s_expected, s_test_buffer + 1U, length) != 0)
    { return StorageIntegrityResult_ByteMismatch; }
    for (uint32_t index = 0U; index < STORAGE_TEST_RECORDS; index++)
    {
        uint32_t sequence;
        uint16_t consumed;
        if (StorageIntegrity_RecordBuild(index, &length) != FLIGHT_LOG_SERIALIZE_RESULT_OK)
        { return StorageIntegrityResult_CodecError; }
        if (f_read(&s_test_file, s_test_buffer + 1U, length, &transferred) != FR_OK || transferred != length ||
            memcmp(s_expected, s_test_buffer + 1U, length) != 0)
        { return StorageIntegrityResult_ByteMismatch; }
        if (FlightLog_RecordDeserialize(s_test_buffer + 1U, length, &s_decoded_record,
            &sequence, &consumed) != FLIGHT_LOG_DESERIALIZE_RESULT_OK || sequence != index || consumed != length)
        { return StorageIntegrityResult_CodecError; }
    }
    if (f_read(&s_test_file, s_test_buffer, 1U, &transferred) != FR_OK || transferred != 0U ||
        f_close(&s_test_file) != FR_OK) { return StorageIntegrityResult_IoError; }
    return StorageIntegrityResult_Ok;
}

StorageIntegrityResult StorageIntegrity_Run(void)
{
    StorageIntegrityResult result = StorageIntegrity_BytesCheck();
    if (result == StorageIntegrityResult_Ok) { result = StorageIntegrity_RecordsCheck(); }
    /* Best effort only; keep failed files for independent offline inspection. */
    if (result != StorageIntegrityResult_Ok) { (void)f_close(&s_test_file); }
    return result;
}
