/* Host-only terminal trap interception; no MCU recovery is simulated. */
#include <setjmp.h>
#include <stdlib.h>
#include <string.h>
#include "test_common.h"
#include "../../APP/Src/logger_bus.c"
static jmp_buf s_trap;
static uint8_t s_trap_expected;
static uint32_t s_traps;
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
void TestCompact_TerminalTrap(void)
{
    if (!s_trap_expected) { abort(); }
    s_traps++; longjmp(s_trap, 1);
}

static void Test_RecordBoundaries(void)
{
    FlightLogInitialStateRecord initial;
    FlightLogSf6StateRecord sf6;
    FlightLogRecord popped;
    FlightLogEstimatorRecord estimator = {0};
    SystemLogStreamConfig config;
    memset(&initial, 0x3A, sizeof(initial)); memset(&sf6, 0x5B, sizeof(sf6));
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(offsetof(FlightLogRecord, payload) + sizeof(initial) == SYSTEM_LOG_RECORD_SLOT_SIZE);
    TEST_CHECK(offsetof(FlightLogRecord, payload) + sizeof(sf6) == SYSTEM_LOG_ESTIMATOR_SLOT_SIZE);
    TEST_CHECK(LoggerBus_RecordPush(FLIGHT_LOG_RECORD_INITIAL_STATE, 1U, 7U,
        &initial, sizeof(initial), 0U) == LOGGER_BUS_RESULT_OK);
    memset(&popped, 0xFF, sizeof(popped));
    TEST_CHECK(LoggerBus_Pop(&popped) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(!memcmp(&popped.payload.initial_state, &initial, sizeof(initial)));
    for (size_t i = SYSTEM_LOG_RECORD_SLOT_SIZE; i < sizeof(popped); ++i)
    { TEST_CHECK(((const uint8_t *)&popped)[i] == 0U); }
    TEST_CHECK(LoggerBus_RecordPush(FLIGHT_LOG_RECORD_SF6_STATE, 2U, 0U,
        &sf6, sizeof(sf6), 1U) == LOGGER_BUS_RESULT_OK);
    memset(&popped, 0xFF, sizeof(popped));
    TEST_CHECK(LoggerBus_EstimatorPop(&popped) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(!memcmp(&popped.payload.sf6_state, &sf6, sizeof(sf6)));
    for (size_t i = SYSTEM_LOG_ESTIMATOR_SLOT_SIZE; i < sizeof(popped); ++i)
    { TEST_CHECK(((const uint8_t *)&popped)[i] == 0U); }
    TEST_CHECK(LoggerBus_RecordPush(FLIGHT_LOG_RECORD_INITIAL_STATE, 1U, 0U,
        &initial, sizeof(initial) - 1U, 0U) == LOGGER_BUS_RESULT_BAD_PARAM);
    TEST_CHECK(LoggerBus_RecordPush(FLIGHT_LOG_RECORD_INITIAL_STATE, 1U, 0U,
        &initial, sizeof(initial), 1U) == LOGGER_BUS_RESULT_BAD_PARAM);
    TEST_CHECK(LoggerBus_RecordPush((FlightLogRecordType)0xFF, 1U, 0U,
        &initial, sizeof(initial), 0U) == LOGGER_BUS_RESULT_BAD_PARAM);
    TEST_CHECK(LoggerBus_RecordPush(FLIGHT_LOG_RECORD_ESTIMATOR, 1U, 0U,
        &estimator, sizeof(estimator), 1U) == LOGGER_BUS_RESULT_BAD_PARAM);
    TEST_CHECK(SystemLogPolicy_StreamGet(FLIGHT_LOG_RECORD_ESTIMATOR, &config) == SYSTEM_DEVICE_OK);
    config.enabled = 1U;
    TEST_CHECK(SystemLogPolicy_StreamConfigure(&config) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(LoggerBus_EstimatorPush(1U, 0U, &estimator) == LOGGER_BUS_RESULT_OK);
    TEST_CHECK(LoggerBus_Count() == 0U);
}

static void Test_CorruptGeometry(void)
{
    FlightLogRecord record;
    FlightLogInitialStateRecord initial = {0};
    uint16_t original_stride = s_logger_queue.item_size;
    uint16_t original_capacity = s_logger_queue.capacity;
    s_trap_expected = 1U;
    s_logger_queue.item_size = (uint16_t)(sizeof(record) + 1U);
    if (!setjmp(s_trap))
    { (void)LoggerBus_Pop(&record); TEST_CHECK(0); }
    s_logger_queue.item_size = original_stride;
    s_logger_queue.capacity = (uint16_t)(original_capacity + 1U);
    if (!setjmp(s_trap))
    { (void)LoggerBus_InitialStatePush(1U, &initial); TEST_CHECK(0); }
    s_logger_queue.capacity = original_capacity;
    TEST_CHECK(LoggerBus_InitialStatePush(1U, &initial) == LOGGER_BUS_RESULT_OK);
    FlightLogRecordType wrong_lane = FLIGHT_LOG_RECORD_SF6_STATE;
    memcpy(s_logger_queue.storage + s_logger_queue.tail_index * s_logger_queue.item_size,
        &wrong_lane, sizeof(wrong_lane));
    if (!setjmp(s_trap))
    { (void)LoggerBus_Pop(&record); TEST_CHECK(0); }
    TEST_CHECK(LoggerBus_InitialStatePush(1U, &initial) == LOGGER_BUS_RESULT_OK);
    FlightLogRecordType unknown = (FlightLogRecordType)0xFF;
    memcpy(s_logger_queue.storage + s_logger_queue.tail_index * s_logger_queue.item_size,
        &unknown, sizeof(unknown));
    if (!setjmp(s_trap))
    { (void)LoggerBus_Pop(&record); TEST_CHECK(0); }
    s_trap_expected = 0U;
    TEST_CHECK(s_traps == 4U);
    TEST_CHECK(LoggerBus_Count() == 0U);
}

int main(void)
{
    Test_RecordBoundaries(); Test_CorruptGeometry();
    return Test_Finish("compact_log_slots");
}
