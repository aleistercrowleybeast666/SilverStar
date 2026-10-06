/* Real FlightTask alignment event writer, LoggerBus and LoggerTask/SSLOG.
 * Coherent alignment status/sensor inputs and storage timing are Host fixtures;
 * this is not alignment-algorithm or SD/hardware qualification. */
#include <stdio.h>
#include <string.h>
#include "test_common.h"
#include "system_log_policy.h"
#include "platform_critical.h"
#include "../../APP/Src/flight_task.c"
#include "../../APP/Src/logger_task.c"

static uint64_t s_now;
static SystemAlignmentStatus s_status;
static InsAlignmentSnapshot s_snapshot;
static uint32_t s_mag_hash = 77U;
static unsigned s_sync_calls;
static uint8_t s_sync_fail;
static unsigned s_write_calls;

PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }
SystemDeviceResult SystemAlignment_StatusGet(SystemAlignmentStatus *status)
{ *status = s_status; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemAlignment_SummaryGet(SystemAlignmentSummary *summary)
{ memset(summary, 0, sizeof(*summary)); summary->state = s_status.state;
  summary->ready = s_status.ready; summary->start_sequence = s_status.start_sequence;
  return SYSTEM_DEVICE_OK; }
uint8_t Ins_GetAlignmentSnapshot(InsAlignmentSnapshot *snapshot)
{ *snapshot = s_snapshot; return 1U; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = 0U; return SYSTEM_DEVICE_OK; }
SystemMagCalibrationResult SystemMagCalibration_StatusGet(
    uint8_t instance, SystemMagCalibrationStatus *status)
{ (void)instance; memset(status, 0, sizeof(*status)); status->generation = 11U;
  status->saved = 1U; return SystemMagCalibrationResult_Ok; }
uint32_t SystemMagCalibration_GenerationHashGet(void) { return s_mag_hash; }
SystemDeviceResult SystemLogSink_Write(const uint8_t *data, uint32_t length, uint32_t *written)
{ TEST_CHECK(data != NULL && length != 0U); s_write_calls++; *written = length;
  return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemLogSink_Flush(void)
{ s_sync_calls++; return s_sync_fail ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemLogSink_SessionEnd(void) { return SYSTEM_DEVICE_OK; }

static void Test_Reset(void)
{
    LoggerBus_Reset();
    memset(&s_logger, 0, sizeof(s_logger)); memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    s_logger.session_active = 1U; s_alignment_start_sequence = 0U; s_alignment_state_known = 0U;
    memset(&s_status, 0, sizeof(s_status)); s_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_status.start_sequence = 1U; s_status.ready = 1U;
    memset(&s_snapshot, 0, sizeof(s_snapshot)); s_snapshot.first_timestamp_us = 10U;
    s_snapshot.last_timestamp_us = 20U; s_snapshot.constraint_count = 2U;
    s_snapshot.valid_pair_count = 9U; s_snapshot.minimum_pair_sine = 0.5f;
    s_mag_hash = 77U; s_now = 100U; s_sync_calls = 0U; s_write_calls = 0U; s_sync_fail = 0U;
}

static unsigned Test_DrainEvidence(uint64_t expected_time, uint32_t expected_hash)
{
    FlightLogRecord record; unsigned evidence = 0U;
    for (unsigned i = 0U; i < SYSTEM_LOG_RECORD_QUEUE_DEPTH + 16U; ++i)
    {
        if (LoggerBus_NextPop(&record) != LOGGER_BUS_RESULT_OK) { break; }
        if (record.record_type == FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE)
        {
            evidence++; TEST_CHECK(record.timestamp_us == expected_time);
            TEST_CHECK(record.payload.alignment_evidence.first_timestamp_us == 10U);
            TEST_CHECK(record.payload.alignment_evidence.last_timestamp_us == 20U);
            TEST_CHECK(record.payload.alignment_evidence.valid_pair_count == 9U);
            TEST_CHECK(record.payload.alignment_evidence.mag_calibration_set_hash == expected_hash);
        }
        if (s_logger.session_active != 0U)
        { TEST_CHECK(LoggerTask_RecordAppend(&record) != 0U); }
        else { TEST_CHECK(s_diagnostics.io_fault == 1U); }
    }
    return evidence;
}

static void Test_BootAndSlowStorage(void)
{
    LoggerBusDiagnostics diagnostics; FlightLogAlignmentEvidenceRecord evidence = {0};
    Test_Reset();
    LoggerBusResult result = LoggerBus_AlignmentEvidencePush(100U, &evidence);
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    printf("BOOT_EVIDENCE result=%u count=%u accepted=%lu suppressed=%lu\n",
        (unsigned)result, LoggerBus_Count(), (unsigned long)diagnostics.accepted_count,
        (unsigned long)diagnostics.bootstrap_suppressed_count);
    TEST_CHECK(result == LOGGER_BUS_RESULT_OK && LoggerBus_Count() == 1U);
    TEST_CHECK(diagnostics.accepted_count == 1U && diagnostics.bootstrap_suppressed_count == 0U);
    SystemLogStreamConfig raw_config = {0};
    SystemDeviceResult stream_result = SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_GNSS_NATIVE, &raw_config);
    TEST_CHECK(stream_result == SYSTEM_DEVICE_OK);
    if (stream_result != SYSTEM_DEVICE_OK) { return; }
    if (raw_config.enabled != 0U)
    {
        FlightLogGnssNativeRecord raw = {0};
        TEST_CHECK(LoggerBus_GnssNativePush(100U, 0U, &raw) == LOGGER_BUS_RESULT_OK);
    }
    else
    {
        /* SF6 minimal excludes GNSS; its actual enabled barometer remains raw. */
        FlightLogBaroNativeRecord raw = {0};
        stream_result = SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_BARO_NATIVE, &raw_config);
        TEST_CHECK(stream_result == SYSTEM_DEVICE_OK);
        if (stream_result != SYSTEM_DEVICE_OK) { return; }
        TEST_CHECK(raw_config.enabled != 0U);
        TEST_CHECK(LoggerBus_BaroNativePush(100U, 0U, &raw) == LOGGER_BUS_RESULT_OK);
    }
    TEST_CHECK(LoggerBus_DiagnosticsGet(&diagnostics) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Count() == 1U && diagnostics.accepted_count == 1U);
    TEST_CHECK(diagnostics.bootstrap_suppressed_count == 1U);
    Test_Reset();
    FlightTask_AlignmentEventsProcess(s_now);
    s_now = 200U; FlightTask_AlignmentEventsProcess(s_now);
    unsigned count = Test_DrainEvidence(100U, 77U);
    printf("SLOW_BOOT_ALIGNMENT evidence=%u known=%u\n", count, s_alignment_state_known);
    TEST_CHECK(count == 1U);
    TEST_CHECK(LoggerBus_StartupStateGet() == LOGGER_BOOTSTRAP);
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    FlightTask_AlignmentEventsProcess(s_now);
    TEST_CHECK(LoggerBus_Count() == 0U);
}

static void Test_FullQueueRetryOwnership(void)
{
    Test_Reset();
    for (unsigned i = 0U; i < SYSTEM_LOG_RECORD_QUEUE_DEPTH; ++i)
    { TEST_CHECK(LoggerBus_EventPush(1U, FLIGHT_LOG_EVENT_MISSION_START, i, 0U) == LOGGER_BUS_RESULT_OK); }
    FlightTask_AlignmentEventsProcess(s_now);
    s_now = 200U; FlightTask_AlignmentEventsProcess(s_now);
    TEST_CHECK(Test_DrainEvidence(100U, 77U) == 0U);
    memset(&s_snapshot, 0xEE, sizeof(s_snapshot)); s_mag_hash = 999U;
    s_now = 900U; FlightTask_AlignmentEventsProcess(s_now);
    unsigned count = Test_DrainEvidence(100U, 77U);
    printf("FULL_RETRY_ALIGNMENT evidence=%u accepted_time=100 captured_hash=77\n", count);
    TEST_CHECK(count == 1U);
    FlightTask_AlignmentEventsProcess(s_now); TEST_CHECK(LoggerBus_Count() == 0U);
}

static void Test_NewAlignmentGeneration(void)
{
    Test_Reset();
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    FlightTask_AlignmentEventsProcess(s_now);
    unsigned first = Test_DrainEvidence(100U, 77U);
    TEST_CHECK(first == 1U);
    s_status.start_sequence = 2U; s_mag_hash = 88U; s_now = 300U;
    FlightTask_AlignmentEventsProcess(s_now);
    unsigned second = Test_DrainEvidence(300U, 88U);
    TEST_CHECK(second == 1U);
    FlightTask_AlignmentEventsProcess(s_now); TEST_CHECK(LoggerBus_Count() == 0U);
    printf("NEW_GENERATION_ALIGNMENT start_sequence=2 first=%u second=%u duplicate_queue=%u\n",
        first, second, LoggerBus_Count());
}

static void Test_PendingAcrossNewGenerationAndFault(void)
{
    FlightLogRecord record; FlightLogAlignmentEvidenceRecord evidence = {0};
    Test_Reset();
    for (unsigned i = 0U; i < SYSTEM_LOG_RECORD_QUEUE_DEPTH; ++i)
    { TEST_CHECK(LoggerBus_EventPush(1U, FLIGHT_LOG_EVENT_MISSION_START, i, 0U) == LOGGER_BUS_RESULT_OK); }
    FlightTask_AlignmentEventsProcess(s_now);
    s_status.start_sequence = 2U; s_mag_hash = 88U; s_now = 300U;
    FlightTask_AlignmentEventsProcess(s_now);
    TEST_CHECK(Test_DrainEvidence(100U, 77U) == 0U);
    FlightTask_AlignmentEventsProcess(s_now);
    unsigned count = 0U;
    for (unsigned i = 0U; i < 16U; ++i)
    {
        if (LoggerBus_NextPop(&record) != LOGGER_BUS_RESULT_OK) { break; }
        if (record.record_type == FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE)
        {
            TEST_CHECK(record.timestamp_us == ((count == 0U) ? 100U : 300U));
            TEST_CHECK(record.payload.alignment_evidence.mag_calibration_set_hash == ((count == 0U) ? 77U : 88U));
            count++;
        }
    }
    TEST_CHECK(count == 2U);
    FlightTask_AlignmentEventsProcess(s_now); TEST_CHECK(LoggerBus_Count() == 0U);
    Test_Reset(); s_diagnostics.io_fault = 1U; LoggerTask_Close();
    TEST_CHECK(LoggerBus_AlignmentEvidencePush(s_now, &evidence) == LOGGER_BUS_RESULT_BAD_STATE);
    FlightTask_AlignmentEventsProcess(s_now);
    /* Ordinary event/result admission remains existing behavior. Evidence is
     * rejected, retains its original data and never fabricates durable success. */
    TEST_CHECK(Test_DrainEvidence(100U, 77U) == 0U);
    memset(&s_snapshot, 0xEE, sizeof(s_snapshot)); s_mag_hash = 999U; s_now = 900U;
    FlightTask_AlignmentEventsProcess(s_now);
    TEST_CHECK(LoggerBus_Count() == 0U && s_diagnostics.io_fault == 1U);
    /* Explicit test-only quiescent reset, not firmware media recovery. */
    LoggerBus_Reset();
    memset(&s_logger, 0, sizeof(s_logger)); memset(&s_diagnostics, 0, sizeof(s_diagnostics));
    s_logger.session_active = 1U;
    FlightTask_AlignmentEventsProcess(s_now);
    unsigned retained = Test_DrainEvidence(100U, 77U);
    TEST_CHECK(retained == 1U);
    printf("PENDING_ALIGNMENT generations=%u retained_after_test_reset=%u\n", count, retained);
}

static void Test_NoStorage(void)
{
    Test_Reset();
    TEST_CHECK(LoggerBus_DisableForBootNoStorage() == LOGGER_BUS_RESULT_OK);
    FlightTask_AlignmentEventsProcess(s_now);
    FlightTask_AlignmentEventsProcess(s_now);
    TEST_CHECK(LoggerBus_Count() == 0U);
    TEST_CHECK(LoggerBus_StartupStateGet() == LOGGER_DISABLED_NO_STORAGE);
}

static void Test_EvidenceFlushAndFault(void)
{
    FlightLogRecord record; FlightLogAlignmentEvidenceRecord evidence = {0};
    Test_Reset();
    TEST_CHECK(LoggerBus_AlignmentEvidencePush(s_now, &evidence) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_EventPush(1U, FLIGHT_LOG_EVENT_ALIGNMENT_START, 0U, 0U) == LOGGER_BUS_RESULT_OK);
    if (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
    {
        TEST_CHECK(record.record_type == FLIGHT_LOG_RECORD_ALIGNMENT_EVIDENCE);
        TEST_CHECK(LoggerTask_RecordAppend(&record) != 0U);
        TEST_CHECK(s_logger.critical_pending == 1U && s_sync_calls == 0U);
        s_now += LOGGER_CRITICAL_FLUSH_MAX_US;
        LoggerTask_PeriodicFlushTry(s_now);
        TEST_CHECK(s_write_calls != 0U && s_sync_calls == 1U && s_diagnostics.io_fault == 0U);
    }
    else { TEST_CHECK(0); }
    Test_Reset();
    TEST_CHECK(LoggerBus_AlignmentEvidencePush(s_now, &evidence) == LOGGER_BUS_RESULT_OK);
    if (LoggerBus_NextPop(&record) == LOGGER_BUS_RESULT_OK)
    {
        s_sync_fail = 1U;
        TEST_CHECK(LoggerTask_RecordAppend(&record) == 0U);
        LoggerTask_Close();
        TEST_CHECK(s_diagnostics.io_fault == 1U && s_logger.session_active == 0U);
    }
    else { TEST_CHECK(0); }
}

int main(void)
{
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    Test_BootAndSlowStorage(); Test_FullQueueRetryOwnership(); Test_NewAlignmentGeneration();
    Test_EvidenceFlushAndFault(); Test_PendingAcrossNewGenerationAndFault(); Test_NoStorage();
    return Test_Finish("logger_alignment");
}
