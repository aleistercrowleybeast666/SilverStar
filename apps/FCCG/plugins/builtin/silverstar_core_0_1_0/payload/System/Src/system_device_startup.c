#include "system_device_startup.h"
#include "silverstar_assert.h"

#include <stddef.h>
#include <string.h>

static uint8_t SystemDeviceStartup_CandidateEquals(
    const SystemDeviceStartupCandidate *left,
    const SystemDeviceStartupCandidate *right)
{
    return (uint8_t)((left->baudrate == right->baudrate) &&
                     (left->protocol == right->protocol));
}

static SystemDeviceStartupResult SystemDeviceStartup_CandidateAdd(
    SystemDeviceStartup *startup, const SystemDeviceStartupCandidate *candidate)
{
    uint8_t index;

    if (candidate->baudrate == 0U)
    { return SystemDeviceStartupResult_InvalidArgument; }
    for (index = 0U; index < startup->candidate_count; index++)
    {
        if (SystemDeviceStartup_CandidateEquals(
                &startup->candidates[index], candidate) != 0U)
        { return SystemDeviceStartupResult_Ok; }
    }
    if (startup->candidate_count >= SYSTEM_DEVICE_STARTUP_MAX_CANDIDATES)
    { return SystemDeviceStartupResult_CandidateLimit; }
    startup->candidates[startup->candidate_count++] = *candidate;
    return SystemDeviceStartupResult_Ok;
}

SystemDeviceStartupResult SystemDeviceStartup_Init(
    SystemDeviceStartup *startup, const SystemDeviceStartupConfig *config)
{
    SystemDeviceStartupResult result;
    uint8_t index;

    if ((startup == NULL) || (config == NULL) || (config->operations == NULL) ||
        (config->operations->probe_start == NULL) ||
        (config->operations->probe_poll == NULL) ||
        (config->operations->config_read == NULL) ||
        (config->operations->config_apply == NULL) ||
        (config->operations->reconnect == NULL) ||
        (config->operations->config_verify == NULL) ||
        (config->operations->sample_poll == NULL) ||
        (config->probe_timeout_ms == 0U) ||
        (config->stage_timeout_ms == 0U) ||
        (config->sample_timeout_ms == 0U) ||
        ((config->persistence != SystemDeviceStartupPersistence_None) &&
         (config->persistence != SystemDeviceStartupPersistence_Persistent)) ||
        ((config->supported_candidate_count != 0U) &&
         (config->supported_candidates == NULL)))
    { return SystemDeviceStartupResult_InvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(startup, SystemDeviceStartup,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(config, SystemDeviceStartupConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(startup, 0, sizeof(*startup));
    startup->config = *config;
    result = SystemDeviceStartup_CandidateAdd(startup, &config->target);
    if (result != SystemDeviceStartupResult_Ok) { return result; }
    if (config->persistence == SystemDeviceStartupPersistence_Persistent)
    {
        result = SystemDeviceStartup_CandidateAdd(startup, &config->factory);
        if (result != SystemDeviceStartupResult_Ok) { return result; }
        for (index = 0U; index < config->supported_candidate_count; index++)
        {
            result = SystemDeviceStartup_CandidateAdd(startup,
                &config->supported_candidates[index]);
            if (result != SystemDeviceStartupResult_Ok) { return result; }
        }
    }
    return SystemDeviceStartupResult_Ok;
}

static void SystemDeviceStartup_StateSet(SystemDeviceStartup *startup,
    SystemDeviceStartupState state, uint32_t now_ms)
{
    startup->state = state;
    startup->state_entered_ms = now_ms;
}

static void SystemDeviceStartup_Fail(SystemDeviceStartup *startup,
    SystemDeviceStartupFailure failure, uint32_t now_ms)
{
    startup->failure = failure;
    SystemDeviceStartup_StateSet(startup,
        SystemDeviceStartupState_Failed, now_ms);
}

static void SystemDeviceStartup_ProbeNext(SystemDeviceStartup *startup,
    uint32_t now_ms)
{
    startup->candidate_index++;
    startup->probe_started = 0U;
    if (startup->candidate_index >= startup->candidate_count)
    { SystemDeviceStartup_Fail(startup,
        SystemDeviceStartupFailure_NotPresent, now_ms); }
    else
    { SystemDeviceStartup_StateSet(startup,
        SystemDeviceStartupState_Probing, now_ms); }
}

static void SystemDeviceStartup_ProbeTick(SystemDeviceStartup *startup,
    uint32_t now_ms)
{
    SystemDeviceStartupStepResult result;
    const SystemDeviceStartupOperations *operations = startup->config.operations;

    SILVERSTAR_ASSERT_OBJECT(startup, SystemDeviceStartup,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(startup->candidate_index < startup->candidate_count,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);

    if (startup->probe_started == 0U)
    {
        if ((uint32_t)(now_ms - startup->state_entered_ms) >=
            startup->config.probe_timeout_ms)
        { SystemDeviceStartup_ProbeNext(startup, now_ms); return; }
        result = operations->probe_start(startup->config.owner,
            &startup->candidates[startup->candidate_index]);
        if (result == SystemDeviceStartupStep_Failed)
        { SystemDeviceStartup_ProbeNext(startup, now_ms); return; }
        if (result == SystemDeviceStartupStep_Pending) { return; }
        startup->probe_started = 1U;
        return;
    }
    result = operations->probe_poll(startup->config.owner);
    if (result == SystemDeviceStartupStep_Ok)
    { SystemDeviceStartup_StateSet(startup,
        SystemDeviceStartupState_Identified, now_ms); }
    else if ((result == SystemDeviceStartupStep_Failed) ||
             ((uint32_t)(now_ms - startup->state_entered_ms) >=
              startup->config.probe_timeout_ms))
    { SystemDeviceStartup_ProbeNext(startup, now_ms); }
}

static void SystemDeviceStartup_ReadTick(SystemDeviceStartup *startup,
    uint32_t now_ms)
{
    SystemDeviceStartupStepResult result =
        startup->config.operations->config_read(startup->config.owner,
            &startup->difference_mask);

    if (result == SystemDeviceStartupStep_Ok)
    {
        SystemDeviceStartup_StateSet(startup,
            (startup->difference_mask == 0U) ?
            SystemDeviceStartupState_VerifyingConfig :
            SystemDeviceStartupState_ApplyingConfig, now_ms);
    }
    else if ((result == SystemDeviceStartupStep_Failed) ||
             ((uint32_t)(now_ms - startup->state_entered_ms) >=
              startup->config.stage_timeout_ms))
    { SystemDeviceStartup_Fail(startup,
        SystemDeviceStartupFailure_ConfigRead, now_ms); }
}

static void SystemDeviceStartup_ApplyTick(SystemDeviceStartup *startup,
    uint32_t now_ms)
{
    SystemDeviceStartupStepResult result =
        startup->config.operations->config_apply(startup->config.owner,
            startup->difference_mask, &startup->reconnect_required);

    if (result == SystemDeviceStartupStep_Ok)
    {
        SystemDeviceStartup_StateSet(startup,
            (startup->reconnect_required != 0U) ?
            SystemDeviceStartupState_Reconnecting :
            SystemDeviceStartupState_VerifyingConfig, now_ms);
    }
    else if ((result == SystemDeviceStartupStep_Failed) ||
             ((uint32_t)(now_ms - startup->state_entered_ms) >=
              startup->config.stage_timeout_ms))
    { SystemDeviceStartup_Fail(startup,
        SystemDeviceStartupFailure_ConfigApply, now_ms); }
}

static void SystemDeviceStartup_StageTick(SystemDeviceStartup *startup,
    uint32_t now_ms, SystemDeviceStartupStepResult result,
    SystemDeviceStartupState next_state,
    SystemDeviceStartupFailure failure)
{
    if (result == SystemDeviceStartupStep_Ok)
    { SystemDeviceStartup_StateSet(startup, next_state, now_ms); }
    else if ((result == SystemDeviceStartupStep_Failed) ||
             ((uint32_t)(now_ms - startup->state_entered_ms) >=
              startup->config.stage_timeout_ms))
    { SystemDeviceStartup_Fail(startup, failure, now_ms); }
}

void SystemDeviceStartup_Tick(SystemDeviceStartup *startup, uint32_t now_ms)
{
    SystemDeviceStartupStepResult result;

    if (startup == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(startup, SystemDeviceStartup,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(startup->state <= SystemDeviceStartupState_Failed,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    switch (startup->state)
    {
        case SystemDeviceStartupState_Uninitialized:
            SystemDeviceStartup_StateSet(startup,
                SystemDeviceStartupState_Probing, now_ms);
            break;
        case SystemDeviceStartupState_Probing:
            SystemDeviceStartup_ProbeTick(startup, now_ms);
            break;
        case SystemDeviceStartupState_Identified:
            SystemDeviceStartup_StateSet(startup,
                SystemDeviceStartupState_ReadingConfig, now_ms);
            break;
        case SystemDeviceStartupState_ReadingConfig:
            SystemDeviceStartup_ReadTick(startup, now_ms);
            break;
        case SystemDeviceStartupState_ApplyingConfig:
            SystemDeviceStartup_ApplyTick(startup, now_ms);
            break;
        case SystemDeviceStartupState_Reconnecting:
            result = startup->config.operations->reconnect(startup->config.owner);
            SystemDeviceStartup_StageTick(startup, now_ms, result,
                SystemDeviceStartupState_VerifyingConfig,
                SystemDeviceStartupFailure_Reconnect);
            break;
        case SystemDeviceStartupState_VerifyingConfig:
            result = startup->config.operations->config_verify(startup->config.owner);
            SystemDeviceStartup_StageTick(startup, now_ms, result,
                SystemDeviceStartupState_WaitingSample,
                SystemDeviceStartupFailure_ConfigVerify);
            break;
        case SystemDeviceStartupState_WaitingSample:
            result = startup->config.operations->sample_poll(startup->config.owner);
            if (result == SystemDeviceStartupStep_Ok)
            { SystemDeviceStartup_StateSet(startup,
                SystemDeviceStartupState_Ready, now_ms); }
            else if ((result == SystemDeviceStartupStep_Failed) ||
                     ((uint32_t)(now_ms - startup->state_entered_ms) >=
                      startup->config.sample_timeout_ms))
            { SystemDeviceStartup_Fail(startup,
                SystemDeviceStartupFailure_SampleTimeout, now_ms); }
            break;
        case SystemDeviceStartupState_Ready:
        case SystemDeviceStartupState_Failed:
        default:
            break;
    }
}
