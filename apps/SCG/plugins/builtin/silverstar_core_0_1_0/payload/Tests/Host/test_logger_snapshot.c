#include <stdio.h>
#include <string.h>
#include "logger_bus.h"
#include "common_spsc_queue.h"
#include "platform_critical.h"
#include "system_descriptor_if.h"
#include "system_log_policy.h"
#include "system_user_config.h"
#include "test_common.h"
#ifdef LOGGER_SNAPSHOT_START_TEST
#include "../../APP/Src/logger_task.c"
static uint64_t s_now;
static unsigned s_flush_failure;
static unsigned s_sync_count;
static unsigned s_write_failure;
uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }
SystemDeviceResult SystemLogSink_Write(const uint8_t *data, uint32_t length, uint32_t *written)
{
    (void)data;
    *written = s_write_failure ? 0U : length;
    return s_write_failure ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemLogSink_Flush(void)
{ s_sync_count++; return s_flush_failure ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemLogSink_SessionEnd(void) { return SYSTEM_DEVICE_OK; }
#endif

static unsigned s_inject;
static unsigned s_pending;
static unsigned s_locked;
PlatformCriticalState PlatformCritical_Enter(void) { return s_locked++; }
void PlatformCritical_Exit(PlatformCriticalState state)
{
    s_locked = state;
    if ((s_locked == 0U) && (s_pending != 0U))
    {
        s_pending = 0U;
        for (unsigned i = 0U; i < SYSTEM_LOG_RECORD_QUEUE_DEPTH; ++i)
        { (void)LoggerBus_EventPush(999U, FLIGHT_LOG_EVENT_MISSION_START, i, 0U); }
    }
}
CommonSpscQueueResult __real_CommonSpscQueue_Push(CommonSpscQueue *, const void *);
CommonSpscQueueResult __wrap_CommonSpscQueue_Push(CommonSpscQueue *q, const void *item)
{
    CommonSpscQueueResult r = __real_CommonSpscQueue_Push(q, item);
    const FlightLogRecord *record = item;
    if ((s_inject != 0U) && (r == COMMON_SPSC_QUEUE_RESULT_OK) &&
        (record->record_type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG))
    { s_inject = 0U; s_pending = 1U; }
    return r;
}
static unsigned Test_Drain(unsigned *config, unsigned *streams)
{
    FlightLogRecord record;
    unsigned descriptors = 0U;
    *config = 0U; *streams = 0U;
    for (unsigned i = 0U; i < 512U; ++i)
    {
        if (LoggerBus_NextPop(&record) != LOGGER_BUS_RESULT_OK) { break; }
        if ((s_inject != 0U) && (record.record_type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG))
        { s_inject = 0U; s_pending = 1U; PlatformCritical_Exit(0U); }
        *config += record.record_type == FLIGHT_LOG_RECORD_SYSTEM_CONFIG;
        *streams += record.record_type == FLIGHT_LOG_RECORD_LOG_STREAM_DESCRIPTOR;
        descriptors += (record.record_type == FLIGHT_LOG_RECORD_DEVICE_DESCRIPTOR) ||
            (record.record_type == FLIGHT_LOG_RECORD_ALGORITHM_DESCRIPTOR);
    }
    return descriptors;
}
#ifdef LOGGER_SNAPSHOT_START_TEST
static void Test_Start(void)
{
    LoggerBusStartRecords input = {0};
    FlightLogRecord record;
    uint32_t generation = 0U;
    unsigned initial = 0U, identity = 0U, mag = 0U, event = 0U;
    LoggerBus_Reset();
    memset(&s_logger, 0, sizeof(s_logger));
    memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    s_now = 1000U; s_logger.session_active = 1U;
    input.initial.gnss_origin_height_mm = 12345;
    input.identity.commit_generation = 77U;
    input.mag_count = 1U; input.mag[0].generation = 88U;
    TEST_CHECK(LoggerBus_StartRecordsPush(321U, &input, &generation) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(generation != 0U && LoggerBus_StartAcknowledgedGet() == 0U);
    memset(&input, 0xEE, sizeof(input));
    /* A repeated accepted token must not dereference modified caller payload. */
    TEST_CHECK(LoggerBus_StartRecordsPush(999U, &input, &generation) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_SystemConfigPush(987U) == LOGGER_BUS_RESULT_BUSY);
    for (unsigned i = 0U; i < 128U; ++i)
    {
        if (LoggerBus_NextPop(&record) != LOGGER_BUS_RESULT_OK) { break; }
        TEST_CHECK(record.timestamp_us == 321U);
        if (record.record_type == FLIGHT_LOG_RECORD_INITIAL_STATE)
        { initial++; TEST_CHECK(record.payload.initial_state.gnss_origin_height_mm == 12345); }
        if (record.record_type == FLIGHT_LOG_RECORD_MISSION_SNAPSHOT_IDENTITY)
        { identity++; TEST_CHECK(record.payload.mission_snapshot_identity.commit_generation == 77U); }
        if (record.record_type == FLIGHT_LOG_RECORD_MAG_CALIBRATION_IDENTITY)
        { mag++; TEST_CHECK(record.payload.mag_calibration_identity.generation == 88U); }
        if (record.record_type == FLIGHT_LOG_RECORD_EVENT) { event++; }
        TEST_CHECK(LoggerTask_RecordAppend(&record) != 0U);
    }
    TEST_CHECK(initial == 1U && identity == 1U && mag == 1U && event == 1U);
    TEST_CHECK(LoggerBus_StartBarrierGet() == generation);
    TEST_CHECK(LoggerBus_Count() == 1U && LoggerBus_StartAcknowledgedGet() == 0U);
    /* Continuous ordinary traffic cannot prevent the mandatory sync barrier. */
    TEST_CHECK(LoggerBus_EventPush(222U, FLIGHT_LOG_EVENT_MISSION_START, 0U, 0U) == LOGGER_BUS_RESULT_OK);
    unsigned before = s_sync_count;
    TEST_CHECK(LoggerTask_StartBarrierProcess() == 1U);
    TEST_CHECK(s_sync_count == before + 1U && LoggerBus_StartAcknowledgedGet() == generation);
    TEST_CHECK(LoggerBus_StartRecordsPush(888U, &input, &generation) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Count() == 1U);
    LoggerBus_Reset();
    generation = 0U; memset(&input, 0, sizeof(input));
    TEST_CHECK(LoggerBus_StartRecordsPush(555U, &input, &generation) == LOGGER_BUS_RESULT_OK);
    for (unsigned i = 0U; i < 128U; ++i)
    { if (LoggerBus_NextPop(&record) != LOGGER_BUS_RESULT_OK) { break; }
      TEST_CHECK(LoggerTask_RecordAppend(&record) != 0U); }
    s_flush_failure = 1U;
    TEST_CHECK(LoggerTask_StartBarrierProcess() == 0U);
    LoggerTask_Close();
    TEST_CHECK(LoggerBus_StartAcknowledgedGet() == 0U);
    TEST_CHECK(LoggerBus_StartBarrierGet() == 0U && LoggerBus_Count() == 1U);
    TEST_CHECK(s_diagnostics.io_fault == 1U);
    TEST_CHECK(LoggerBus_SystemConfigPush(444U) == LOGGER_BUS_RESULT_BAD_STATE);
    s_flush_failure = 0U;
}
#endif
int main(void)
{
    unsigned config, streams;
    unsigned expected = SystemDescriptor_DeviceCountGet() + SystemDescriptor_AlgorithmCountGet();
    LoggerBusDiagnostics d;
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    LoggerBus_Reset();
    s_inject = 1U;
    LoggerBusResult r = LoggerBus_SystemConfigPush(123U);
    unsigned descriptors = Test_Drain(&config, &streams);
    printf("PREEMPT result=%u config=%u descriptors=%u streams=%u expected=%u\n",
        (unsigned)r, config, descriptors, streams, expected);
    TEST_CHECK(r == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(config == 1U && descriptors == expected && streams == SSLOG_RECORD_COUNT);
    LoggerBus_Reset();
    unsigned required = 1U + expected + SSLOG_RECORD_COUNT;
    unsigned prefill = (SYSTEM_LOG_RECORD_QUEUE_DEPTH >= required) ?
        SYSTEM_LOG_RECORD_QUEUE_DEPTH - required + 1U : 1U;
    for (unsigned i = 0U; i < prefill; ++i)
    { TEST_CHECK(LoggerBus_EventPush(i, FLIGHT_LOG_EVENT_MISSION_START, 0U, 0U) == LOGGER_BUS_RESULT_OK); }
    r = LoggerBus_SystemConfigPush(456U);
    TEST_CHECK(LoggerBus_DiagnosticsGet(&d) == LOGGER_BUS_RESULT_OK);
    printf("PREFILL result=%u capacity_reject=%lu overflow=%lu count=%u\n",
        (unsigned)r, (unsigned long)d.capacity_reject_count,
        (unsigned long)d.overflow_count, LoggerBus_Count());
    descriptors = Test_Drain(&config, &streams);
    TEST_CHECK(r == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(config == 1U && descriptors == expected && streams == SSLOG_RECORD_COUNT);
#ifdef LOGGER_SNAPSHOT_START_TEST
    Test_Start();
#endif
    return Test_Finish("logger_snapshot");
}
