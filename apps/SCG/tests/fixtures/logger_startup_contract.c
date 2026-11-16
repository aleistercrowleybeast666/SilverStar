/* Actual logger and codec; only report/I/O/IRQ ports and terminal trap are Host.
 * The oversized pre-fix case fails its first sink write before any array walk,
 * so demonstrating publication before validation never relies on a C overread. */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static jmp_buf s_trap_return;
static _Noreturn void Test_Trap(void) { longjmp(s_trap_return, 1); }
#define __builtin_trap() Test_Trap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "logger_task.c"

#define CHECK(condition) do { if (!(condition)) { \
    (void)fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
    exit(1); } } while (0)

static SystemStartupReport s_report;
static uint32_t s_write_calls;
static uint32_t s_flush_calls;
static uint32_t s_lock_depth;
static uint8_t s_write_fails;
static uint8_t s_null_report;

const SystemStartupReport *SystemStartup_GetReport(void)
{ return (s_null_report != 0U) ? NULL : &s_report; }
uint64_t SystemTime_GetMonotonicUs(void) { return 1000ULL; }
uint32_t LoggerBus_OverflowCountGet(void) { return 0U; }
uint16_t LoggerBus_Count(void) { return 0U; }
PlatformCriticalState PlatformCritical_Enter(void) { return s_lock_depth++; }
void PlatformCritical_Exit(PlatformCriticalState state) { s_lock_depth = state; }
SystemDeviceResult SystemLogSink_Write(const uint8_t *data, uint32_t length,
                                      uint32_t *written)
{
    CHECK(data != NULL && length > 0U && written != NULL);
    s_write_calls++;
    *written = (s_write_fails != 0U) ? 0U : length;
    return (s_write_fails != 0U) ? SYSTEM_DEVICE_IO_ERROR : SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemLogSink_Flush(void)
{ s_flush_calls++; return SYSTEM_DEVICE_OK; }

int main(int argc, char **argv)
{
    uint8_t result;
    uint8_t expects_trap;
    SilverStarAssertFaultRecord fault;
    CHECK(argc == 2);
    s_logger.session_active = 1U;
    s_report.completed = 1U;
    s_report.passed = 1U;
    s_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    for (uint8_t index = 0U; index < SYSTEM_STARTUP_DEVICE_COUNT; ++index)
    {
        s_report.devices[index].device_id = (SystemStartupDeviceId)index;
        s_report.devices[index].device_name = "Device";
        s_report.devices[index].model_name = "Model";
    }
    expects_trap = (uint8_t)(strcmp(argv[1], "oversized") == 0 ||
        strcmp(argv[1], "completed-domain") == 0 || strcmp(argv[1], "passed-domain") == 0);
    if (strcmp(argv[1], "oversized") == 0)
    { s_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT + 1U; s_write_fails = 1U; }
    else if (strcmp(argv[1], "completed-domain") == 0) { s_report.completed = 2U; }
    else if (strcmp(argv[1], "passed-domain") == 0) { s_report.passed = 2U; }
    else if (strcmp(argv[1], "incomplete") == 0)
    { s_report.completed = 0U; s_report.device_count = 255U; s_report.passed = 255U; }
    else if (strcmp(argv[1], "null") == 0) { s_null_report = 1U; }
    else if (strcmp(argv[1], "io-failure") == 0) { s_write_fails = 1U; }
    else if (strcmp(argv[1], "device-failure") == 0)
    { s_report.passed = 0U; s_report.required_failure_mask = 1U; }
    else { CHECK(strcmp(argv[1], "normal") == 0); }
    if (setjmp(s_trap_return) != 0)
    {
        CHECK(expects_trap != 0U);
        CHECK(SilverStarAssert_FaultRecordGet(&fault) == 1U);
        CHECK(fault.module_id == SILVERSTAR_ASSERT_MODULE_APP);
        CHECK(fault.reason_id == ((strcmp(argv[1], "oversized") == 0) ?
            SILVERSTAR_ASSERT_REASON_LENGTH_RANGE : SILVERSTAR_ASSERT_REASON_STATE_INVARIANT));
        CHECK(strstr(fault.file_name, "logger_task.c") != NULL);
        CHECK(s_logger.record_sequence == 0U && s_logger.aggregate_length == 0U);
        CHECK(s_diagnostics.serialized_count == 0U && s_diagnostics.io_fault == 0U);
        CHECK(s_write_calls == 0U && s_flush_calls == 0U && s_lock_depth == 0U);
        printf("%s: actual fail-stop before serialization/I/O PASS\n", argv[1]);
        return 0;
    }
    result = LoggerTask_StartupReportWrite();
    printf("%s: result=%u serialized=%lu writes=%lu flushes=%lu fault=%u\n",
        argv[1], result, (unsigned long)s_diagnostics.serialized_count,
        (unsigned long)s_write_calls, (unsigned long)s_flush_calls,
        SilverStarAssert_FaultedGet());
    CHECK(expects_trap == 0U);
    CHECK(SilverStarAssert_FaultedGet() == 0U && s_lock_depth == 0U);
    if (s_null_report != 0U || s_report.completed == 0U)
    { CHECK(result == 0U && s_write_calls == 0U && s_diagnostics.serialized_count == 0U); }
    else if (s_write_fails != 0U)
    { CHECK(result == 0U && s_write_calls == 1U && s_diagnostics.io_fault == 1U); }
    else
    {
        CHECK(result == 1U && s_diagnostics.io_fault == 0U);
        CHECK(s_diagnostics.serialized_count == 2U + 5U * SYSTEM_STARTUP_DEVICE_COUNT);
        CHECK(s_logger.record_sequence == s_diagnostics.serialized_count);
        CHECK(s_write_calls > 0U && s_flush_calls == s_write_calls);
    }
    puts("PASS");
    return 0;
}
