#include "system_mission_process.h"
#include "project_mission_process.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "silverstar_assert.h"
#include "system_time.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct
{
    uint64_t entered_us[PROJECT_MISSION_STAGE_COUNT];
    uint64_t terminal_us;
    uint64_t last_us;
    uint64_t hold_us;
    uint64_t acceleration_us;
    uint64_t navigation_us;
    uint32_t navigation_sequence;
    uint32_t acceleration_sequence;
    uint32_t acceleration_source;
    uint32_t acceleration_epoch;
    uint8_t entered;
    uint8_t holding;
    uint8_t terminated;
    uint8_t time_known;
    uint8_t acceleration_known;
    uint8_t navigation_known;
    uint8_t mission_started;
    uint8_t landed;
    uint8_t ready_function_mask;
} SystemMissionProcessState;

/* FlightTask is the sole writer. Readers take a bounded IRQ snapshot. */
static PLATFORM_CPU_FAST_BSS SystemMissionProcessState s_process;
/* References are constant-eliminated when no data function has dependencies. */
static PLATFORM_CPU_FAST_BSS uint64_t s_ready_timestamp_us[2];

/* The caller holds the IRQ lock. Reject corrupted owned state before readers
 * publish an event or a permission; a later FlightTask poll is not a guard. */
static void SystemMissionProcess_StateValidate(void)
{
    SILVERSTAR_ASSERT(s_process.entered <= PROJECT_MISSION_STAGE_COUNT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_process.holding <= 1U) && (s_process.terminated <= 1U) &&
        (s_process.time_known <= 1U) && (s_process.acceleration_known <= 1U) &&
        (s_process.navigation_known <= 1U) && (s_process.mission_started <= 1U) &&
        (s_process.landed <= 1U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((s_process.ready_function_mask & (uint8_t)~0x0CU) == 0U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(((s_process.entered == 0U) || (s_process.time_known != 0U)) &&
        ((s_process.terminated == 0U) || (s_process.terminal_us == s_process.last_us)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
}

static void SystemMissionProcess_FunctionValidate(const SystemMissionFunctionConfig *config)
{
    SILVERSTAR_ASSERT((config->start_kind <= 5U) && (config->stop_kind <= 5U) &&
        ((config->dependency_mask & (uint8_t)~0x0CU) == 0U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((((config->start_kind != 2U) && (config->start_kind != 3U)) ||
        (config->start_index < PROJECT_MISSION_STAGE_COUNT)) &&
        (((config->stop_kind != 2U) && (config->stop_kind != 3U)) ||
        (config->stop_index < PROJECT_MISSION_STAGE_COUNT)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
}

/* Validate only the history entries used by this read, under the same lock. */
static void SystemMissionProcess_EventTimeValidate(uint32_t index)
{
    uint64_t time = s_process.entered_us[index];
    SILVERSTAR_ASSERT((time <= s_process.last_us) && ((index == 0U) ||
        (time > s_process.entered_us[index - 1U])),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    if (index + 1U < s_process.entered)
    {
        SILVERSTAR_ASSERT((s_process.entered_us[index + 1U] > time) &&
            (s_process.entered_us[index + 1U] <= s_process.last_us),
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    }
}

void SystemMissionProcess_Init(void)
{
    uint32_t lock = PlatformCritical_Enter();
    (void)memset(&s_process, 0, sizeof(s_process));
    if (PROJECT_MISSION_FUNCTION_DEPENDENCIES != 0U)
    { (void)memset(s_ready_timestamp_us, 0, sizeof(s_ready_timestamp_us)); }
    PlatformCritical_Exit(lock);
}

static uint8_t SystemMissionProcess_AccelerationFresh(const SystemMissionProcessInput *input)
{
    uint8_t changed;
    if (((input->valid_mask & SYSTEM_MISSION_PROCESS_VALID_ACCEL) == 0U) ||
        (input->acceleration_timestamp_us == 0U) ||
        (input->acceleration_timestamp_us > input->now_us) ||
        (input->now_us - input->acceleration_timestamp_us > 100000ULL) ||
        !isfinite(input->acceleration_g) || (input->acceleration_g < 0.0f))
    { s_process.holding = 0U; return 0U; }
    changed = (uint8_t)((input->acceleration_source != s_process.acceleration_source) ||
        (input->acceleration_epoch != s_process.acceleration_epoch));
    if ((s_process.acceleration_known != 0U) && (changed == 0U) &&
        ((input->acceleration_timestamp_us <= s_process.acceleration_us) ||
         (input->acceleration_sequence == s_process.acceleration_sequence)))
    { return 0U; }
    if ((changed != 0U) || ((s_process.acceleration_known != 0U) &&
        (input->acceleration_timestamp_us - s_process.acceleration_us >
         PROJECT_MISSION_MAXIMUM_GAP_US))) { s_process.holding = 0U; }
    s_process.acceleration_us = input->acceleration_timestamp_us;
    s_process.acceleration_sequence = input->acceleration_sequence;
    s_process.acceleration_source = input->acceleration_source;
    s_process.acceleration_epoch = input->acceleration_epoch;
    s_process.acceleration_known = 1U;
    return 1U;
}

static uint8_t SystemMissionProcess_ConditionMet(const SystemMissionStageConfig *stage,
    const SystemMissionProcessInput *input)
{
    float value = 0.0f;
    if (stage->signal == 0U) { return (uint8_t)((input->events & stage->event_mask) != 0U); }
    if ((stage->signal != 1U) && (input->mission_started == 0U)) { return 0U; }
    if (stage->signal == 1U)
    {
        if (s_process.entered == 0U) { return 0U; }
        value = (float)(input->now_us - s_process.entered_us[s_process.entered - 1U]) / 1000000.0f;
    }
    else if (stage->signal == 4U)
    {
        value = input->acceleration_g;
    }
    else
    {
        if ((input->valid_mask & SYSTEM_MISSION_PROCESS_VALID_NAV) == 0U) { return 0U; }
        value = (stage->signal == 2U) ? input->altitude_agl_m : input->vertical_velocity_mps;
    }
    if (!isfinite(value)) { return 0U; }
    return (uint8_t)((stage->less_equal != 0U) ? (value <= stage->threshold) : (value >= stage->threshold));
}

static uint8_t SystemMissionProcess_NavigationFresh(const SystemMissionProcessInput *input)
{
    if (((input->valid_mask & SYSTEM_MISSION_PROCESS_VALID_NAV) == 0U) ||
        (input->navigation_timestamp_us == 0U) ||
        (input->navigation_timestamp_us > input->now_us) ||
        (input->now_us - input->navigation_timestamp_us > 100000ULL))
    { s_process.holding = 0U; return 0U; }
    if ((s_process.navigation_known != 0U) &&
        ((input->navigation_timestamp_us <= s_process.navigation_us) ||
         (input->navigation_sequence == s_process.navigation_sequence)))
    { return 0U; }
    if ((s_process.navigation_known != 0U) &&
        (input->navigation_timestamp_us - s_process.navigation_us > PROJECT_MISSION_MAXIMUM_GAP_US))
    { s_process.holding = 0U; }
    s_process.navigation_us = input->navigation_timestamp_us;
    s_process.navigation_sequence = input->navigation_sequence;
    s_process.navigation_known = 1U;
    return 1U;
}

static SystemMissionProcessResult SystemMissionProcess_Transition(
    const SystemMissionProcessInput *input, const SystemMissionStageConfig *stage)
{
    uint64_t time = (stage->signal == 4U) ? input->acceleration_timestamp_us : input->now_us;
    if ((stage->signal == 2U) || (stage->signal == 3U))
    { time = input->navigation_timestamp_us; }
    if (SystemMissionProcess_ConditionMet(stage, input) == 0U)
    { s_process.holding = 0U; return SystemMissionProcessResult_Waiting; }
    if (s_process.holding == 0U)
    { s_process.hold_us = time; s_process.holding = 1U; }
    if ((time < s_process.hold_us) ||
        (time - s_process.hold_us < (uint64_t)stage->hold_ms * 1000ULL))
    { return SystemMissionProcessResult_Waiting; }
    /* Commit the actual transition point, not the eventual radio send time. */
    uint32_t lock = PlatformCritical_Enter();
    s_process.entered_us[s_process.entered] = input->now_us;
    s_process.entered++;
    s_process.holding = 0U;
    PlatformCritical_Exit(lock);
    return SystemMissionProcessResult_Entered;
}

static SystemMissionProcessResult SystemMissionProcess_Terminate(const SystemMissionProcessInput *input)
{
    SystemMissionStageConfig stage;
    SystemMissionProcessResult result = SystemMissionProcessResult_Complete;
    if ((s_process.entered < PROJECT_MISSION_STAGE_COUNT) &&
        (ProjectMissionStage_ConfigGet(s_process.entered, &stage) == SystemMissionProcessResult_Entered) &&
        (stage.signal == 0U) && ((input->events & stage.event_mask) != 0U))
    { result = SystemMissionProcess_Transition(input, &stage); }
    uint32_t lock = PlatformCritical_Enter();
    s_process.terminal_us = input->now_us;
    s_process.terminated = 1U;
    PlatformCritical_Exit(lock);
    return result;
}

SystemMissionProcessResult SystemMissionProcess_Step(const SystemMissionProcessInput *input)
{
    SystemMissionStageConfig stage;
    if ((input == NULL) || (input->mission_started > 1U) || (input->terminated > 1U) ||
        ((input->ready_function_mask & (uint8_t)~0x0CU) != 0U))
    { return SystemMissionProcessResult_Invalid; }
    uint32_t validation_lock = PlatformCritical_Enter();
    SystemMissionProcess_StateValidate();
    PlatformCritical_Exit(validation_lock);
    if (s_process.terminated != 0U) { return SystemMissionProcessResult_Complete; }
    if ((s_process.time_known != 0U) && (input->now_us <= s_process.last_us))
    { return SystemMissionProcessResult_Invalid; }
    if ((s_process.time_known != 0U) &&
        (input->now_us - s_process.last_us > PROJECT_MISSION_MAXIMUM_GAP_US))
    { s_process.holding = 0U; }
    uint32_t state_lock = PlatformCritical_Enter();
    s_process.last_us = input->now_us; s_process.time_known = 1U;
    s_process.mission_started = input->mission_started;
    s_process.landed |= (uint8_t)((input->events & (1UL << 6)) != 0U);
    s_process.ready_function_mask = input->ready_function_mask;
    if (PROJECT_MISSION_FUNCTION_DEPENDENCIES != 0U)
    {
        s_ready_timestamp_us[0] = input->ready_timestamp_us[0];
        s_ready_timestamp_us[1] = input->ready_timestamp_us[1];
    }
    PlatformCritical_Exit(state_lock);
    if (input->terminated != 0U)
    { return SystemMissionProcess_Terminate(input); }
    if (s_process.entered == PROJECT_MISSION_STAGE_COUNT)
    { return SystemMissionProcessResult_Complete; }
    if (ProjectMissionStage_ConfigGet(s_process.entered, &stage) != SystemMissionProcessResult_Entered)
    { return SystemMissionProcessResult_Invalid; }
    if ((stage.signal == 4U) && (SystemMissionProcess_AccelerationFresh(input) == 0U))
    { return SystemMissionProcessResult_Waiting; }
    if (((stage.signal == 2U) || (stage.signal == 3U)) &&
        (SystemMissionProcess_NavigationFresh(input) == 0U))
    { return SystemMissionProcessResult_Waiting; }
    return SystemMissionProcess_Transition(input, &stage);
}

SystemMissionProcessResult SystemMissionProcess_EventGet(uint32_t after_sequence,
    SystemMissionProcessEvent *event)
{
    SystemMissionStageConfig stage;
    uint32_t sequence = after_sequence + 1U;
    uint32_t index = after_sequence / 2U;
    uint32_t lock;
    if ((event == NULL) || (after_sequence >= 2U * PROJECT_MISSION_STAGE_COUNT))
    { return SystemMissionProcessResult_Unavailable; }
    if (ProjectMissionStage_ConfigGet((uint8_t)index, &stage) != SystemMissionProcessResult_Entered)
    { return SystemMissionProcessResult_Invalid; }
    lock = PlatformCritical_Enter();
    SystemMissionProcess_StateValidate();
    if ((index >= s_process.entered) || (((sequence % 2U) == 0U) &&
        (index + 1U >= s_process.entered) && (s_process.terminated == 0U)))
    { PlatformCritical_Exit(lock); return SystemMissionProcessResult_Unavailable; }
    SystemMissionProcess_EventTimeValidate(index);
    event->timestamp_us = ((sequence % 2U) != 0U) ? s_process.entered_us[index] :
        (index + 1U < s_process.entered) ? s_process.entered_us[index + 1U] : s_process.terminal_us;
    PlatformCritical_Exit(lock);
    event->stage_index = (uint8_t)index; event->stage_id_hash = stage.stage_id_hash;
    event->sequence = sequence;
    event->event_code = ((sequence % 2U) != 0U) ? SYSTEM_MISSION_PROCESS_EVENT_ENTER : SYSTEM_MISSION_PROCESS_EVENT_EXIT;
    return SystemMissionProcessResult_Entered;
}

/* Called with the IRQ lock held: all four boundaries use one coherent state. */
static uint8_t SystemMissionProcess_BoundaryReached(uint8_t kind, uint8_t index)
{
    switch (kind)
    {
        case 0U: return 1U;
        case 1U: return s_process.mission_started;
        case 2U: return (uint8_t)(s_process.entered > index);
        case 3U: return (uint8_t)((s_process.entered > index + 1U) ||
            ((s_process.terminated != 0U) && (s_process.entered > index)));
        case 4U: return s_process.landed;
        case 5U: return s_process.terminated;
        default: return 0U;
    }
}

/* The caller holds the IRQ lock. Dependencies are fixed navigation owners;
 * configuration validation rejects cycles and incompatible owner lifetimes. */
static uint8_t SystemMissionProcess_DependenciesReady(uint8_t mask, uint64_t now_us)
{
    SystemMissionFunctionConfig dependency;
    uint8_t index;
    SILVERSTAR_ASSERT((mask & (uint8_t)~0x0CU) == 0U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if ((mask != 0U) && (s_process.mission_started == 0U)) { return 0U; }
    if ((s_process.ready_function_mask & mask) != mask) { return 0U; }
    for (index = 2U; index < 4U; index++)
    {
        if ((mask & (1U << index)) == 0U) { continue; }
        if (PROJECT_MISSION_FUNCTION_DEPENDENCIES != 0U)
        {
            uint64_t timestamp = s_ready_timestamp_us[index - 2U];
            if ((timestamp == 0U) || (timestamp > now_us) ||
                (now_us - timestamp > 100000ULL)) { return 0U; }
        }
        if (ProjectMissionFunction_ConfigGet(index, &dependency) != SystemMissionProcessResult_Entered)
        { return 0U; }
        SystemMissionProcess_FunctionValidate(&dependency);
        if ((SystemMissionProcess_BoundaryReached(dependency.start_kind, dependency.start_index) == 0U) ||
            (SystemMissionProcess_BoundaryReached(dependency.stop_kind, dependency.stop_index) != 0U))
        { return 0U; }
    }
    return 1U;
}

static uint8_t SystemMissionProcess_FunctionActiveGet(uint8_t index)
{
    SystemMissionFunctionConfig config;
    uint8_t active;
    uint64_t now_us = 0U;
    if (ProjectMissionFunction_ConfigGet(index, &config) != SystemMissionProcessResult_Entered) { return 0U; }
    SystemMissionProcess_FunctionValidate(&config);
    if ((PROJECT_MISSION_FUNCTION_DEPENDENCIES != 0U) && (config.dependency_mask != 0U))
    { now_us = SystemTime_GetMonotonicUs(); }
    uint32_t lock = PlatformCritical_Enter();
    SystemMissionProcess_StateValidate();
    active = (uint8_t)((SystemMissionProcess_BoundaryReached(config.start_kind, config.start_index) != 0U) &&
        (SystemMissionProcess_BoundaryReached(config.stop_kind, config.stop_index) == 0U) &&
        (SystemMissionProcess_DependenciesReady(config.dependency_mask, now_us) != 0U));
    PlatformCritical_Exit(lock);
    return active;
}

uint8_t SystemMissionProcess_TelemetryActiveGet(void)
{ return SystemMissionProcess_FunctionActiveGet(0U); }

uint8_t SystemMissionProcess_LoggingActiveGet(void)
{ return SystemMissionProcess_FunctionActiveGet(1U); }

static uint8_t SystemMissionProcess_NavigationStoppedGet(uint8_t index)
{
    SystemMissionFunctionConfig config;
    uint8_t stopped;
    if (ProjectMissionFunction_ConfigGet(index, &config) != SystemMissionProcessResult_Entered) { return 1U; }
    SystemMissionProcess_FunctionValidate(&config);
    uint32_t lock = PlatformCritical_Enter();
    SystemMissionProcess_StateValidate();
    stopped = (uint8_t)((s_process.terminated != 0U) ||
        (SystemMissionProcess_BoundaryReached(config.stop_kind, config.stop_index) != 0U));
    PlatformCritical_Exit(lock);
    return stopped;
}

uint8_t SystemMissionProcess_InsStoppedGet(void)
{ return SystemMissionProcess_NavigationStoppedGet(2U); }

uint8_t SystemMissionProcess_EstimatorStoppedGet(void)
{ return SystemMissionProcess_NavigationStoppedGet(3U); }

SystemMissionControlWindowResult SystemMissionProcess_ControlWindowGet(void)
{
    SystemMissionFunctionConfig config;
    SystemMissionControlWindowResult result = SystemMissionControlWindowResult_Waiting;
    uint32_t lock;
    if (PROJECT_MISSION_CONTROL_ENABLED == 0U)
    { return SystemMissionControlWindowResult_Disabled; }
    if (ProjectMissionFunction_ConfigGet(4U, &config) != SystemMissionProcessResult_Entered)
    { return SystemMissionControlWindowResult_Invalid; }
    SystemMissionProcess_FunctionValidate(&config);
    lock = PlatformCritical_Enter();
    SystemMissionProcess_StateValidate();
    if ((s_process.terminated != 0U) ||
        (SystemMissionProcess_BoundaryReached(config.stop_kind, config.stop_index) != 0U))
    { result = SystemMissionControlWindowResult_Stopped; }
    else if ((s_process.mission_started != 0U) &&
        (SystemMissionProcess_BoundaryReached(config.start_kind, config.start_index) != 0U))
    { result = SystemMissionControlWindowResult_Active; }
    PlatformCritical_Exit(lock);
    return result;
}
