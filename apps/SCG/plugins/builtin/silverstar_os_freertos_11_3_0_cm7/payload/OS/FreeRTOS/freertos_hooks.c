#include "FreeRTOS.h"
#include "task.h"

#include "platform_memory.h"
#include "silverstar_assert.h"
#include "system_task_stack.h"
#include "system_lifecycle.h"

static StaticTask_t s_idle_task_control;
static PLATFORM_CPU_FAST_BSS StackType_t
    s_idle_task_stack[configMINIMAL_STACK_SIZE];

void vApplicationGetIdleTaskMemory(
    StaticTask_t **task_control,
    StackType_t **stack,
    configSTACK_DEPTH_TYPE *stack_words)
{
    if ((task_control == NULL) || (stack == NULL) || (stack_words == NULL))
    {
        return;
    }
    *task_control = &s_idle_task_control;
    *stack = s_idle_task_stack;
    *stack_words = configMINIMAL_STACK_SIZE;
}

void vApplicationStackOverflowHook(TaskHandle_t task, char *task_name)
{
    taskDISABLE_INTERRUPTS();
    if (task == (TaskHandle_t)&s_idle_task_control)
    {
        SilverStarAssert_StackOverflowContextSet((uintptr_t)task,
            (uintptr_t)task_name, (uint32_t)SYSTEM_TASK_STACK_COUNT, "IDLE",
            (uint32_t)SystemLifecycle_GetState(), 0U, 0U);
    }
    else
    {
        SystemTaskStack_OverflowContextSet((uintptr_t)task, (uintptr_t)task_name);
    }
    SilverStarAssert_Fail(SILVERSTAR_ASSERT_MODULE_OS, __FILE__,
                          (uint32_t)__LINE__,
                          SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}
