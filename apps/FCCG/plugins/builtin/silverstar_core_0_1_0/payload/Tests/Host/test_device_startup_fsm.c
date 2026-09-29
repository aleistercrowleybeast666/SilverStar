#include "system_device_startup.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

typedef struct
{
    uint32_t probed_baud[8];
    uint8_t probe_count;
    uint8_t read_count;
    uint8_t apply_count;
    uint8_t verify_count;
    uint8_t sample_count;
    uint32_t applied_mask;
} TestOwner;

static SystemDeviceStartupStepResult Test_ProbeStart(void *context,
    const SystemDeviceStartupCandidate *candidate)
{
    TestOwner *owner = (TestOwner *)context;
    owner->probed_baud[owner->probe_count++] = candidate->baudrate;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_ProbePoll(void *context)
{
    TestOwner *owner = (TestOwner *)context;
    return (owner->probed_baud[owner->probe_count - 1U] == 9600U) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult Test_Read(void *context,
    uint32_t *difference_mask)
{
    TestOwner *owner = (TestOwner *)context;
    owner->read_count++;
    *difference_mask = 0x05U;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_Apply(void *context,
    uint32_t difference_mask, uint8_t *reconnect_required)
{
    TestOwner *owner = (TestOwner *)context;
    assert(owner->read_count == 1U);
    owner->apply_count++;
    owner->applied_mask = difference_mask;
    *reconnect_required = 1U;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_Reconnect(void *context)
{
    TestOwner *owner = (TestOwner *)context;
    assert(owner->apply_count == 1U);
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_Verify(void *context)
{
    TestOwner *owner = (TestOwner *)context;
    assert(owner->applied_mask == 0x05U);
    owner->verify_count++;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_Sample(void *context)
{
    TestOwner *owner = (TestOwner *)context;
    assert(owner->verify_count == 1U);
    owner->sample_count++;
    return (owner->sample_count == 3U) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static const SystemDeviceStartupOperations s_operations =
{
    Test_ProbeStart, Test_ProbePoll, Test_Read, Test_Apply,
    Test_Reconnect, Test_Verify, Test_Sample
};

static void Test_TargetFactoryCandidateOrder(void)
{
    const SystemDeviceStartupCandidate supported[] =
    { {230400U, 1U}, {9600U, 1U}, {4800U, 1U} };
    SystemDeviceStartupConfig config;
    SystemDeviceStartup startup;
    TestOwner owner;
    uint32_t tick;

    (void)memset(&owner, 0, sizeof(owner));
    (void)memset(&config, 0, sizeof(config));
    config.persistence = SystemDeviceStartupPersistence_Persistent;
    config.target.baudrate = 230400U;
    config.target.protocol = 1U;
    config.factory.baudrate = 115200U;
    config.factory.protocol = 1U;
    config.supported_candidates = supported;
    config.supported_candidate_count = 3U;
    config.probe_timeout_ms = 3U;
    config.stage_timeout_ms = 3U;
    config.sample_timeout_ms = 5U;
    config.operations = &s_operations;
    config.owner = &owner;
    assert(SystemDeviceStartup_Init(&startup, &config) ==
        SystemDeviceStartupResult_Ok);
    assert(startup.candidate_count == 4U);
    for (tick = 0U; tick < 40U; tick++)
    { SystemDeviceStartup_Tick(&startup, tick); }
    assert(startup.state == SystemDeviceStartupState_Ready);
    assert(startup.failure == SystemDeviceStartupFailure_None);
    assert(owner.probe_count == 3U);
    assert(owner.probed_baud[0] == 230400U);
    assert(owner.probed_baud[1] == 115200U);
    assert(owner.probed_baud[2] == 9600U);
    assert(owner.read_count == 1U);
    assert(owner.apply_count == 1U);
    assert(owner.applied_mask == 0x05U);
    assert(owner.verify_count == 1U);
    assert(owner.sample_count == 3U);
}

static void Test_ExhaustedCandidatesFail(void)
{
    SystemDeviceStartupConfig config;
    SystemDeviceStartup startup;
    TestOwner owner;
    uint32_t tick;

    (void)memset(&owner, 0, sizeof(owner));
    (void)memset(&config, 0, sizeof(config));
    config.persistence = SystemDeviceStartupPersistence_None;
    config.target.baudrate = 230400U;
    config.factory.baudrate = 9600U;
    config.probe_timeout_ms = 3U;
    config.stage_timeout_ms = 3U;
    config.sample_timeout_ms = 3U;
    config.operations = &s_operations;
    config.owner = &owner;
    assert(SystemDeviceStartup_Init(&startup, &config) ==
        SystemDeviceStartupResult_Ok);
    for (tick = 0U; tick < 40U; tick++)
    { SystemDeviceStartup_Tick(&startup, tick); }
    assert(startup.state == SystemDeviceStartupState_Failed);
    assert(startup.failure == SystemDeviceStartupFailure_NotPresent);
    assert(owner.probe_count == 1U);
    assert(owner.read_count == 0U);
}

static SystemDeviceStartupStepResult Test_ReadNoChange(void *context,
    uint32_t *difference_mask)
{
    TestOwner *owner = (TestOwner *)context;
    owner->read_count++;
    *difference_mask = 0U;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_ProbeAlwaysReady(void *context)
{
    (void)context;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Test_SampleNeverReady(void *context)
{
    TestOwner *owner = (TestOwner *)context;
    owner->sample_count++;
    return SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult Test_VerifyNoChange(void *context)
{
    TestOwner *owner = (TestOwner *)context;
    assert(owner->applied_mask == 0U);
    owner->verify_count++;
    return SystemDeviceStartupStep_Ok;
}

static void Test_NoDifferenceSkipsWriteAndSampleIsBounded(void)
{
    SystemDeviceStartupOperations operations = s_operations;
    SystemDeviceStartupConfig config;
    SystemDeviceStartup startup;
    TestOwner owner;
    uint32_t tick;

    (void)memset(&owner, 0, sizeof(owner));
    (void)memset(&config, 0, sizeof(config));
    operations.probe_poll = Test_ProbeAlwaysReady;
    operations.config_read = Test_ReadNoChange;
    operations.config_verify = Test_VerifyNoChange;
    operations.sample_poll = Test_SampleNeverReady;
    config.persistence = SystemDeviceStartupPersistence_None;
    config.target.baudrate = 230400U;
    config.probe_timeout_ms = 3U;
    config.stage_timeout_ms = 3U;
    config.sample_timeout_ms = 4U;
    config.operations = &operations;
    config.owner = &owner;
    assert(SystemDeviceStartup_Init(&startup, &config) ==
        SystemDeviceStartupResult_Ok);
    for (tick = 0U; tick < 30U; tick++)
    { SystemDeviceStartup_Tick(&startup, tick); }
    assert(startup.state == SystemDeviceStartupState_Failed);
    assert(startup.failure == SystemDeviceStartupFailure_SampleTimeout);
    assert(owner.read_count == 1U);
    assert(owner.apply_count == 0U);
    assert(owner.verify_count == 1U);
    assert(owner.sample_count <= 5U);
}

static void Test_InvalidCandidateListRejected(void)
{
    SystemDeviceStartupCandidate candidates[9];
    SystemDeviceStartupConfig config;
    SystemDeviceStartup startup;
    TestOwner owner;
    uint8_t index;

    (void)memset(&owner, 0, sizeof(owner));
    (void)memset(&config, 0, sizeof(config));
    for (index = 0U; index < 9U; index++)
    {
        candidates[index].baudrate = 4800U + ((uint32_t)index * 100U);
        candidates[index].protocol = 1U;
    }
    config.persistence = SystemDeviceStartupPersistence_Persistent;
    config.target.baudrate = 230400U;
    config.factory.baudrate = 9600U;
    config.supported_candidates = candidates;
    config.supported_candidate_count = 9U;
    config.probe_timeout_ms = 3U;
    config.stage_timeout_ms = 3U;
    config.sample_timeout_ms = 3U;
    config.operations = &s_operations;
    config.owner = &owner;
    assert(SystemDeviceStartup_Init(&startup, &config) ==
        SystemDeviceStartupResult_CandidateLimit);
}

int main(void)
{
    Test_TargetFactoryCandidateOrder();
    Test_ExhaustedCandidatesFail();
    Test_NoDifferenceSkipsWriteAndSampleIsBounded();
    Test_InvalidCandidateListRejected();
    return 0;
}
