/* Actual LoggerTask byte batching and SSLOG codec; only sink/clock/queue
 * occupancy are fixtures. FatFs/DMA integration is a separate strict gate. */
#include <string.h>
#include "test_common.h"
#include "host_platform_mock.h"
#include "../../APP/Src/logger_task.c"

static uint8_t s_sink_bytes[32768];
static uint8_t s_expected_bytes[32768];
static uint32_t s_sink_length;
static uint32_t s_sink_calls;
static uint32_t s_sync_calls;
static uint64_t s_now;
static uint16_t s_fixture_queue_count;
static uint8_t s_short_write;
static uint8_t s_fail_sync;

uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }
uint32_t LoggerBus_OverflowCountGet(void) { return 0U; }
uint16_t LoggerBus_Count(void) { return s_fixture_queue_count; }
SystemDeviceResult SystemLogSink_Write(const uint8_t *data, uint32_t length, uint32_t *written)
{
    uint32_t count = s_short_write ? length / 2U : length;
    TEST_CHECK(s_sink_length + count <= sizeof(s_sink_bytes));
    memcpy(s_sink_bytes + s_sink_length, data, count);
    s_sink_length += count;
    s_sink_calls++;
    *written = count;
    return s_short_write ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemLogSink_Flush(void)
{ s_sync_calls++; return s_fail_sync ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemLogSink_SessionEnd(void) { return SYSTEM_DEVICE_OK; }

static void Fixture_Reset(void)
{
    memset(&s_logger, 0, sizeof(s_logger));
    memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    memset(s_sink_bytes, 0, sizeof(s_sink_bytes));
    s_sink_length = 0U; s_sink_calls = 0U; s_sync_calls = 0U;
    s_short_write = 0U; s_fail_sync = 0U;
    s_fixture_queue_count = 1U; s_now = 1ULL;
    s_logger.session_active = 1U;
}

static void Test_Unaligned119ByteRecords(void)
{
    FlightLogRecord record = {0};
    uint32_t expected_length = 37U;
    Fixture_Reset();
    memset(s_expected_bytes, 0xA5, 37U);
    TEST_CHECK(LoggerTask_SinkWrite(s_expected_bytes, 37U) == 1U);
    record.record_type = FLIGHT_LOG_RECORD_MISSION_CONFIG;
    for (uint32_t index = 0U; index < 100U; ++index)
    {
        uint16_t length = 0U;
        uint32_t calls = s_sink_calls;
        record.timestamp_us = index;
        TEST_CHECK(FlightLog_RecordSerialize(&record, index, s_expected_bytes + expected_length,
            (uint16_t)(sizeof(s_expected_bytes) - expected_length), &length) == FLIGHT_LOG_SERIALIZE_RESULT_OK);
        TEST_CHECK(length == 119U);
        expected_length += length;
        TEST_CHECK(LoggerTask_RecordAppend(&record) == 1U);
        TEST_CHECK(s_sink_length + s_logger.aggregate_length == expected_length);
        TEST_CHECK(s_logger.sink_offset_mod_quantum == s_sink_length % 512U);
        if (calls != s_sink_calls)
        {
            TEST_CHECK(s_sink_length % 512U == 0U);
            TEST_CHECK(s_logger.aggregate_length < 512U + 119U);
        }
    }
    TEST_CHECK(LoggerTask_Flush() == 1U);
    TEST_CHECK(s_logger.aggregate_length == 0U && s_sink_length == expected_length);
    TEST_CHECK(memcmp(s_sink_bytes, s_expected_bytes, expected_length) == 0);
    TEST_CHECK(s_sync_calls == 1U && s_sink_calls >= 4U);
}

static void Test_FlushAndUncertainWrite(void)
{
    FlightLogRecord record = {0};
    Fixture_Reset();
    record.record_type = FLIGHT_LOG_RECORD_MISSION_CONFIG;
    s_fixture_queue_count = 0U;
    TEST_CHECK(LoggerTask_RecordAppend(&record) == 1U);
    TEST_CHECK(s_sink_length == 119U && s_sync_calls == 1U);
    s_fixture_queue_count = 1U;
    TEST_CHECK(LoggerTask_RecordAppend(&record) == 1U);
    s_now += SYSTEM_LOG_SYNC_PERIOD_US;
    LoggerTask_PeriodicFlushTry(s_now);
    TEST_CHECK(s_sink_length == 238U && s_sync_calls == 2U);
    memset(s_aggregate_buffer, 0x5A, 900U);
    s_logger.aggregate_length = 900U;
    s_short_write = 1U;
    TEST_CHECK(LoggerTask_StreamingWrite() == 0U);
    TEST_CHECK(s_logger.sink_offset_mod_quantum == 238U);
    TEST_CHECK(s_logger.aggregate_length == 900U && s_diagnostics.io_fault == 1U);
    TEST_CHECK(s_diagnostics.append_failure_count == 1U);
    LoggerTask_Close();
    TEST_CHECK(s_logger.aggregate_length == 0U && s_diagnostics.discarded_bytes == 900U);
    TEST_CHECK(s_logger.session_active == 0U);
    Fixture_Reset();
    s_logger.aggregate_length = 119U; s_fail_sync = 1U;
    TEST_CHECK(LoggerTask_Flush() == 0U);
    TEST_CHECK(s_logger.aggregate_length == 0U && s_logger.sink_offset_mod_quantum == 119U);
    TEST_CHECK(s_diagnostics.io_fault == 1U && s_diagnostics.flush_failure_count == 1U);
}

int main(void)
{
    HostPlatformMock_Reset();
    Test_Unaligned119ByteRecords();
    Test_FlushAndUncertainWrite();
    return Test_Finish("logger_streaming_actual");
}
