/* Host-only memory-fault injection into the actual owning mission engine.
 * Only the terminal trap is intercepted; this is not MCU recovery. */
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "platform_critical.h"

static jmp_buf s_fault_return;
static uint32_t s_lock_depth;
static uint8_t s_config_error;
static uint64_t s_now_us = 30U;
static _Noreturn void MissionReview_TerminalTrap(void)
{ longjmp(s_fault_return, 1); }
#define __builtin_trap() MissionReview_TerminalTrap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "system_mission_process.c"

static SystemMissionProcessEvent s_event;
static SystemMissionProcessEvent s_event_before;

PlatformCriticalState PlatformCritical_Enter(void)
{ uint32_t previous = s_lock_depth; s_lock_depth++; return previous; }
void PlatformCritical_Exit(PlatformCriticalState previous)
{ assert(s_lock_depth == previous + 1U); s_lock_depth = previous; }
uint64_t SystemTime_GetMonotonicUs(void) { return s_now_us; }
uint8_t ProjectMissionStage_CountGet(void) { return PROJECT_MISSION_STAGE_COUNT; }

SystemMissionProcessResult ProjectMissionStage_ConfigGet(uint8_t index,
    SystemMissionStageConfig *config)
{
    static const SystemMissionStageConfig stages[2] = {
        {11U, 0U, 1U, 0.0f, 0U, 0U}, {22U, 0U, 2U, 0.0f, 0U, 0U}};
    if ((index >= 2U) || (config == NULL) || (s_config_error != 0U))
    { return SystemMissionProcessResult_Invalid; }
    *config = stages[index];
    return SystemMissionProcessResult_Entered;
}

SystemMissionProcessResult ProjectMissionFunction_ConfigGet(uint8_t index,
    SystemMissionFunctionConfig *config)
{
    static const SystemMissionFunctionConfig functions[5] = {
        {1U, 0U, 5U, 0U, 8U}, {0U, 0U, 5U, 0U, 0U},
        {1U, 0U, 5U, 0U, 0U}, {1U, 0U, 5U, 0U, 0U},
        {1U, 0U, 5U, 0U, 8U}};
    if ((index >= 5U) || (config == NULL)) { return SystemMissionProcessResult_Invalid; }
    *config = functions[index];
    return SystemMissionProcessResult_Entered;
}

static void MissionReview_Start(void)
{
    SystemMissionProcessInput input;
    (void)memset(&input, 0, sizeof(input));
    SystemMissionProcess_Init();
    input.now_us = 10U; input.events = 1U; input.mission_started = 1U;
    input.ready_function_mask = 8U; input.ready_timestamp_us[1] = 10U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    input.now_us = 20U; input.events = 2U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    (void)memset(&s_event, 0xa5, sizeof(s_event)); s_event_before = s_event;
    assert(s_lock_depth == 0U);
}

static int MissionReview_Normal(const char *mode)
{
    SystemMissionProcessInput invalid;
    (void)memset(&invalid, 0, sizeof(invalid));
    if (strcmp(mode, "config-error") == 0)
    {
        s_config_error = 1U;
        assert(SystemMissionProcess_EventGet(0U, &s_event) == SystemMissionProcessResult_Invalid);
        assert(memcmp(&s_event, &s_event_before, sizeof(s_event)) == 0);
    }
    else
    {
        assert(SystemMissionProcess_EventGet(UINT32_MAX, &s_event) == SystemMissionProcessResult_Unavailable);
        assert(memcmp(&s_event, &s_event_before, sizeof(s_event)) == 0);
        assert(SystemMissionProcess_EventGet(0U, NULL) == SystemMissionProcessResult_Unavailable);
        invalid.mission_started = 2U;
        assert(SystemMissionProcess_Step(&invalid) == SystemMissionProcessResult_Invalid);
        assert(s_process.entered == 2U);
        assert(SystemMissionProcess_EventGet(0U, &s_event) == SystemMissionProcessResult_Entered);
        assert(s_event.timestamp_us == 10U && s_event.sequence == 1U);
        assert(SystemMissionProcess_TelemetryActiveGet() == 1U);
        assert(SystemMissionProcess_LoggingActiveGet() == 1U);
        assert(SystemMissionProcess_InsStoppedGet() == 0U);
        assert(SystemMissionProcess_EstimatorStoppedGet() == 0U);
    }
    assert(s_lock_depth == 0U && SilverStarAssert_FaultedGet() == 0U);
    puts("normal/error output transaction PASS"); return 0;
}

int main(int argc, char **argv)
{
    const char *volatile mode = argc == 2 ? argv[1] : "normal";
    MissionReview_Start();
    if ((strcmp(mode, "normal") == 0) || (strcmp(mode, "config-error") == 0))
    { return MissionReview_Normal(mode); }
    if (strcmp(mode, "event-count") == 0) { s_process.entered = 255U; }
    else if (strcmp(mode, "active-count") == 0) { s_process.entered = 255U; }
    else if (strcmp(mode, "navigation-count") == 0) { s_process.entered = 255U; }
    else if (strcmp(mode, "active-terminated") == 0) { s_process.terminated = 2U; }
    else if (strcmp(mode, "event-future") == 0) { s_process.entered_us[0] = 21U; }
    else if (strcmp(mode, "event-order") == 0) { s_process.entered_us[1] = 9U; }
    else if (strcmp(mode, "ready-mask") == 0) { s_process.ready_function_mask = 0x88U; }
    else if (strcmp(mode, "mission-flag") == 0) { s_process.mission_started = 2U; }
    else { assert(0); }
    if (setjmp(s_fault_return) == 0)
    {
        if (strncmp(mode, "event-", 6U) == 0)
        { (void)SystemMissionProcess_EventGet(0U, &s_event); }
        else if (strcmp(mode, "navigation-count") == 0)
        { (void)SystemMissionProcess_EstimatorStoppedGet(); }
        else { (void)SystemMissionProcess_TelemetryActiveGet(); }
        fprintf(stderr, "UNSAFE: %s returned without the internal-state fault\n", mode);
        return 1;
    }
    SilverStarAssertFaultRecord record;
    assert(SilverStarAssert_FaultRecordGet(&record) == 1U);
    assert(record.module_id == SILVERSTAR_ASSERT_MODULE_SYSTEM);
    assert(s_lock_depth != 0U); /* The assertion used a coherent IRQ snapshot. */
    assert(memcmp(&s_event, &s_event_before, sizeof(s_event)) == 0);
    printf("bounded fail-stop before publication: %s reason=%u PASS\n", mode, (unsigned)record.reason_id);
    return 0;
}
