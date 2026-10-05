#include "silverstar_assert.h"

#include <stddef.h>

static volatile SilverStarAssertFaultRecord s_assert_fault;

static void SilverStarAssert_TaskNameCopy(const char *stable_name)
{
    uint32_t index;

    /* Only a trusted static name is read; the original hook pointer is
     * retained as an address because the overflowing TCB may be corrupt. */
    for (index = 0U; index < SILVERSTAR_FAULT_TASK_NAME_SIZE; index++)
    {
        s_assert_fault.task_name[index] = '\0';
    }
    for (index = 0U; index < (SILVERSTAR_FAULT_TASK_NAME_SIZE - 1U); index++)
    {
        if ((stable_name == NULL) || (stable_name[index] == '\0')) { break; }
        s_assert_fault.task_name[index] = stable_name[index];
    }
}

void SilverStarAssert_StackOverflowContextSet(
    uintptr_t task_handle, uintptr_t task_name_address,
    uint32_t task_id, const char *stable_name, uint32_t system_state,
    uint32_t high_water_mark_words, uint8_t high_water_mark_valid)
{
    s_assert_fault.fault_type = SILVERSTAR_FAULT_STACK_OVERFLOW;
    s_assert_fault.task_handle = task_handle;
    s_assert_fault.task_name_address = task_name_address;
    s_assert_fault.task_id = task_id;
    s_assert_fault.system_state = system_state;
    s_assert_fault.high_water_mark_words = high_water_mark_words;
    s_assert_fault.high_water_mark_valid = high_water_mark_valid;
    SilverStarAssert_TaskNameCopy(stable_name);
}

void SilverStarAssert_Check(uint8_t condition,
                            SilverStarAssertModuleId module_id,
                            const char *file_name,
                            uint32_t line,
                            SilverStarAssertReasonId reason_id)
{
    if (condition == 0U)
    {
        SilverStarAssert_Fail(module_id, file_name, line, reason_id);
    }
}

void SilverStarAssert_ObjectCheck(const volatile void *object,
                                  uint32_t alignment,
                                  SilverStarAssertModuleId module_id,
                                  const char *file_name,
                                  uint32_t line)
{
    uintptr_t address;

    SilverStarAssert_Check((uint8_t)(object != NULL), module_id, file_name,
                           line, SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    address = (uintptr_t)object;
    SilverStarAssert_Check(
        (uint8_t)((alignment != 0U) && ((address % alignment) == 0U)),
        module_id, file_name, line,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

SILVERSTAR_NORETURN void SilverStarAssert_Fail(
    SilverStarAssertModuleId module_id,
    const char *file_name,
    uint32_t line,
    SilverStarAssertReasonId reason_id)
{
    s_assert_fault.file_name = file_name;
    s_assert_fault.timestamp_us = 0U;
    s_assert_fault.line = line;
    s_assert_fault.sequence++;
    s_assert_fault.module_id = module_id;
    s_assert_fault.reason_id = reason_id;
    s_assert_fault.timestamp_valid = 0U;
    s_assert_fault.active = 1U;
    __sync_synchronize();
    __builtin_trap();
    for (;;)
    {
        /* Deterministic fail-stop if a debugger resumes after the trap. */
    }
}

uint8_t SilverStarAssert_FaultedGet(void)
{
    return s_assert_fault.active;
}

uint8_t SilverStarAssert_FaultRecordGet(SilverStarAssertFaultRecord *record)
{
    if (record == NULL) { return 0U; }
    *record = s_assert_fault;
    return record->active;
}
