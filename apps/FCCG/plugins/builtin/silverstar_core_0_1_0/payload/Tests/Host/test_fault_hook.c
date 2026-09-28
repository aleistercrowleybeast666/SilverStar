#include <setjmp.h>
#define main Test_StartupFixtureMain
#include "test_runtime_startup.c"
#undef main

static jmp_buf s_fail_stop;
SILVERSTAR_NORETURN void Test_FailStop(SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    TEST_CHECK(module == SILVERSTAR_ASSERT_MODULE_OS);
    TEST_CHECK(file != NULL && line != 0U);
    TEST_CHECK(reason == SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    longjmp(s_fail_stop, 1);
}

/* Execute the real OS hook, replacing only its terminal fail-stop instruction.
 * The fault recorder and task registry remain production implementations. */
#define configMINIMAL_STACK_SIZE 128U
#define configSTACK_DEPTH_TYPE uint32_t
#define taskDISABLE_INTERRUPTS() ((void)0)
#define SilverStarAssert_Fail Test_FailStop
#include "../../OS/FreeRTOS/freertos_hooks.c"
#undef SilverStarAssert_Fail

int main(void)
{
    SilverStarAssertFaultRecord record;
    SystemTaskStackSnapshot snapshot;
    TEST_CHECK(AppTasks_Init() == AppTasksInitResult_Ok);
    TEST_CHECK(SystemTaskStack_SnapshotGet(&snapshot) == SYSTEM_DEVICE_OK);
    if (setjmp(s_fail_stop) == 0)
    {
        vApplicationStackOverflowHook(s_telemetry_handle, (char *)(uintptr_t)1U);
    }
    TEST_CHECK(SilverStarAssert_FaultRecordGet(&record) == 0U);
    TEST_CHECK(record.fault_type == SILVERSTAR_FAULT_STACK_OVERFLOW);
    TEST_CHECK(record.task_handle == (uintptr_t)s_telemetry_handle);
    TEST_CHECK(record.task_name_address == 1U);
    TEST_CHECK(strcmp(record.task_name, "Telemetry") == 0);
    TEST_CHECK(record.high_water_mark_valid == 1U);
    TEST_CHECK(record.high_water_mark_words == 123U);
    if (setjmp(s_fail_stop) == 0)
    {
        vApplicationStackOverflowHook((TaskHandle_t)&s_idle_task_control, NULL);
    }
    TEST_CHECK(SilverStarAssert_FaultRecordGet(&record) == 0U);
    TEST_CHECK(strcmp(record.task_name, "IDLE") == 0);
    TEST_CHECK(record.task_id == SYSTEM_TASK_STACK_COUNT);
    TEST_CHECK(record.high_water_mark_valid == 0U);
    return Test_Finish("fault_hook");
}
