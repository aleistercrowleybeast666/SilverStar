#include "control_research.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "silverstar_assert.h"
#include "system_lifecycle.h"
#include "system_time.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

#define CONTROL_RESEARCH_FAULT 0x4354524CUL

typedef struct
{
    uint64_t last_poll_us;
    uint64_t start_us;
    uint64_t next_us;
    uint64_t navigation_us;
    uint64_t imu_us;
    uint32_t navigation_sequence;
    uint32_t imu_sequence;
    SystemNavigationProvenance provenance;
    float limit;
    ControlResearchState state;
    uint8_t backend_started;
} ControlResearchContext;

/* Private CPU-only values, copied under the publication lock; never DMA. */
static PLATFORM_CPU_FAST_BSS ControlResearchContext s_control;
static PLATFORM_CPU_FAST_BSS ControlResearchSnapshot s_output;

static void ControlResearch_Revoke(ControlResearchResult result)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_output.ready = 0U;
    s_output.command = 0.0f;
    s_output.state = s_control.state;
    s_output.result = result;
    PlatformCritical_Exit(lock);
}

static void ControlResearch_StateRequire(void)
{
    uint8_t valid = (uint8_t)(((uint32_t)s_control.state <= ControlResearchState_Disabled) &&
        (s_control.backend_started <= 1U) &&
        (((s_control.state == ControlResearchState_Starting) || (s_control.state == ControlResearchState_Running)) ||
         (s_control.backend_started == 0U)) &&
        ((s_control.state != ControlResearchState_Running) ||
         ((s_control.backend_started == 1U) && (s_control.next_us != 0U) &&
          isfinite(s_control.limit) && (s_control.limit > 0.0f) && (s_control.limit <= 1.0f))));
    if (valid == 0U) { ControlResearch_Revoke(ControlResearchResult_InvalidState); }
    SILVERSTAR_ASSERT(valid != 0U, SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

static ControlResearchResult ControlResearch_Terminate(ControlResearchResult result,
    ControlResearchState state)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_control.state = state;
    ControlResearch_Revoke(result);
    PlatformCritical_Exit(lock);
    if (s_control.backend_started != 0U)
    {
        s_control.backend_started = 0U;
        if (ControlResearchBackend_Stop() != ControlResearchResult_Ok)
        { result = ControlResearchResult_BackendError; s_control.state = ControlResearchState_Failed; }
    }
    ControlResearch_Revoke(result);
    if (s_control.state == ControlResearchState_Failed)
    { SystemLifecycle_EnterFault(CONTROL_RESEARCH_FAULT); }
    return result;
}

void ControlResearch_Init(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    (void)memset(&s_control, 0, sizeof(s_control));
    (void)memset(&s_output, 0, sizeof(s_output));
    s_control.state = ControlResearchState_Waiting;
    s_output.state = ControlResearchState_Waiting;
    s_output.result = ControlResearchResult_Waiting;
    PlatformCritical_Exit(lock);
}

static uint8_t ControlResearch_ProvenanceEqual(const SystemNavigationProvenance *a,
    const SystemNavigationProvenance *b)
{
    return (uint8_t)((a->valid == 1U) && (b->valid == 1U) &&
        (a->calibration_generation != 0U) &&
        (a->calibration_generation == b->calibration_generation) &&
        (a->source_instance == b->source_instance) && (a->sensor_epoch == b->sensor_epoch));
}

static ControlResearchResult ControlResearch_InputCheck(uint64_t now_us,
    const ControlResearchInput *input, float *angle)
{
    float norm = 0.0f;
    if ((input == NULL) || (angle == NULL)) { return ControlResearchResult_InvalidInput; }
    if ((input->navigation_us == 0U) || (input->imu_us == 0U) ||
        (input->navigation_us > now_us) || (input->imu_us > now_us) ||
        (now_us - input->navigation_us > CONTROL_RESEARCH_INPUT_AGE_US) ||
        (now_us - input->imu_us > CONTROL_RESEARCH_INPUT_AGE_US)) { return ControlResearchResult_Stale; }
    uint64_t skew = (input->navigation_us > input->imu_us) ?
        input->navigation_us - input->imu_us : input->imu_us - input->navigation_us;
    if (skew > CONTROL_RESEARCH_INPUT_SKEW_US) { return ControlResearchResult_Stale; }
    if (ControlResearch_ProvenanceEqual(&input->navigation_provenance, &input->imu_provenance) == 0U)
    { return ControlResearchResult_SourceChanged; }
    if ((s_control.state == ControlResearchState_Running) &&
        (ControlResearch_ProvenanceEqual(&s_control.provenance, &input->navigation_provenance) == 0U))
    { return ControlResearchResult_SourceChanged; }
    for (uint8_t index = 0U; index < 4U; index++)
    {
        if (!isfinite(input->q_nb[index])) { return ControlResearchResult_InvalidInput; }
        norm += input->q_nb[index] * input->q_nb[index];
    }
    if (!isfinite(norm) || (fabsf(norm - 1.0f) > 0.001f) ||
        (fabsf(input->q_nb[1]) > 0.01f) || (fabsf(input->q_nb[3]) > 0.01f) ||
        !isfinite(input->rate_radps) || (fabsf(input->rate_radps) > 20.0f))
    { return ControlResearchResult_InvalidInput; }
    float x = 2.0f * (input->q_nb[1] * input->q_nb[3] + input->q_nb[0] * input->q_nb[2]);
    float z = 1.0f - 2.0f * (input->q_nb[1] * input->q_nb[1] + input->q_nb[2] * input->q_nb[2]);
    *angle = atan2f(x, z);
    if (!isfinite(*angle) || (fabsf(*angle) > 0.35f)) { return ControlResearchResult_InvalidInput; }
    return ControlResearchResult_Ok;
}

static ControlResearchResult ControlResearch_Publish(uint64_t now_us,
    const ControlResearchInput *input, float angle)
{
    float command = 0.0f;
    ControlResearchResult result = ControlResearchBackend_Step(angle, input->rate_radps, &command);
    if ((result != ControlResearchResult_Ok) || !isfinite(command) || (fabsf(command) > s_control.limit))
    { return ControlResearch_Terminate(ControlResearchResult_BackendError, ControlResearchState_Failed); }
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint64_t publication_us = SystemTime_GetMonotonicUs();
    if ((publication_us < now_us) || (publication_us < s_control.next_us) ||
        (publication_us - s_control.next_us > CONTROL_RESEARCH_LATENESS_US))
    {
        PlatformCritical_Exit(lock);
        return ControlResearch_Terminate(ControlResearchResult_Timing, ControlResearchState_Failed);
    }
    SystemLifecycleState lifecycle = SystemLifecycle_GetState();
    if (((lifecycle != SYSTEM_STATE_FLIGHT) && (lifecycle != SYSTEM_STATE_RECOVERY)) ||
        (SystemMissionProcess_ControlWindowGet() != SystemMissionControlWindowResult_Active))
    {
        PlatformCritical_Exit(lock);
        return ControlResearch_Terminate(ControlResearchResult_Stopped, ControlResearchState_Stopped);
    }
    if (ControlResearch_PublicationCheck(&input->navigation_provenance,
        input->navigation_us, input->navigation_sequence) != ControlResearchResult_Ok)
    {
        PlatformCritical_Exit(lock);
        return ControlResearch_Terminate(ControlResearchResult_SourceChanged, ControlResearchState_Failed);
    }
    if (s_output.sequence == UINT32_MAX) { s_output.ready = 0U; s_output.command = 0.0f; }
    SILVERSTAR_ASSERT(s_output.sequence < UINT32_MAX, SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    s_output.published_us = publication_us;
    s_output.scheduled_us = s_control.next_us;
    s_output.navigation_us = input->navigation_us;
    s_output.imu_us = input->imu_us;
    s_output.sequence++;
    s_output.command = command;
    s_output.angle_rad = angle;
    s_output.rate_radps = input->rate_radps;
    s_output.state = ControlResearchState_Running;
    s_output.result = ControlResearchResult_Ok;
    s_output.ready = 1U;
    s_control.navigation_us = input->navigation_us;
    s_control.imu_us = input->imu_us;
    s_control.navigation_sequence = input->navigation_sequence;
    s_control.imu_sequence = input->imu_sequence;
    s_control.provenance = input->navigation_provenance;
    s_control.state = ControlResearchState_Running;
    PlatformCritical_Exit(lock);
    s_control.next_us += CONTROL_RESEARCH_PERIOD_US;
    return ControlResearchResult_Ok;
}

static ControlResearchResult ControlResearch_ActiveProcess(uint64_t now_us,
    ControlResearchResult input_result, const ControlResearchInput *input)
{
    float angle = 0.0f;
    if (s_control.state == ControlResearchState_Waiting)
    {
        s_control.state = ControlResearchState_Starting;
        s_control.start_us = now_us;
        if (ControlResearchBackend_Start(&s_control.limit) != ControlResearchResult_Ok)
        { return ControlResearch_Terminate(ControlResearchResult_BackendError, ControlResearchState_Failed); }
        s_control.backend_started = 1U;
    }
    if (input_result != ControlResearchResult_Ok)
    {
        if ((input_result == ControlResearchResult_Unavailable) &&
            (s_control.state == ControlResearchState_Starting) &&
            (now_us - s_control.start_us <= CONTROL_RESEARCH_INPUT_AGE_US))
        { ControlResearch_Revoke(ControlResearchResult_Waiting); return ControlResearchResult_Waiting; }
        return ControlResearch_Terminate(input_result, ControlResearchState_Failed);
    }
    ControlResearchResult checked = ControlResearch_InputCheck(now_us, input, &angle);
    if (checked != ControlResearchResult_Ok)
    { return ControlResearch_Terminate(checked, ControlResearchState_Failed); }
    if (s_control.next_us == 0U) { s_control.next_us = now_us; }
    if (now_us < s_control.next_us) { return ControlResearchResult_Waiting; }
    if ((now_us - s_control.next_us > CONTROL_RESEARCH_LATENESS_US) ||
        (s_control.next_us > UINT64_MAX - CONTROL_RESEARCH_PERIOD_US))
    { return ControlResearch_Terminate(ControlResearchResult_Timing, ControlResearchState_Failed); }
    if ((input->navigation_sequence <= s_control.navigation_sequence) ||
        (input->imu_sequence <= s_control.imu_sequence) ||
        (input->navigation_us <= s_control.navigation_us) || (input->imu_us <= s_control.imu_us))
    { return ControlResearch_Terminate(ControlResearchResult_Stale, ControlResearchState_Failed); }
    return ControlResearch_Publish(now_us, input, angle);
}

ControlResearchResult ControlResearch_Process(uint64_t now_us,
    SystemMissionControlWindowResult window, ControlResearchResult input_result,
    const ControlResearchInput *input)
{
    ControlResearch_StateRequire();
    if (s_control.state == ControlResearchState_Failed) { return ControlResearchResult_InvalidState; }
    if (s_control.state == ControlResearchState_Stopped) { return ControlResearchResult_Stopped; }
    if (s_control.state == ControlResearchState_Disabled) { return ControlResearchResult_Disabled; }
    if (window == SystemMissionControlWindowResult_Disabled)
    { return ControlResearch_Terminate(ControlResearchResult_Disabled, ControlResearchState_Disabled); }
    if ((window == SystemMissionControlWindowResult_Stopped) || (SystemLifecycle_GetState() == SYSTEM_STATE_FAULT))
    { return ControlResearch_Terminate(ControlResearchResult_Stopped, ControlResearchState_Stopped); }
    if ((window == SystemMissionControlWindowResult_Active) &&
        (SystemLifecycle_GetState() != SYSTEM_STATE_FLIGHT) &&
        (SystemLifecycle_GetState() != SYSTEM_STATE_RECOVERY))
    { return ControlResearch_Terminate(ControlResearchResult_Stopped, ControlResearchState_Stopped); }
    if ((now_us == 0U) || (now_us <= s_control.last_poll_us))
    { return ControlResearch_Terminate(ControlResearchResult_Timing, ControlResearchState_Failed); }
    s_control.last_poll_us = now_us;
    if (window == SystemMissionControlWindowResult_Waiting)
    {
        if (s_control.state != ControlResearchState_Waiting)
        { return ControlResearch_Terminate(ControlResearchResult_InvalidState, ControlResearchState_Failed); }
        ControlResearch_Revoke(ControlResearchResult_Waiting);
        return ControlResearchResult_Waiting;
    }
    if (window != SystemMissionControlWindowResult_Active)
    { return ControlResearch_Terminate(ControlResearchResult_InvalidState, ControlResearchState_Failed); }
    return ControlResearch_ActiveProcess(now_us, input_result, input);
}

ControlResearchResult ControlResearch_SnapshotGet(ControlResearchSnapshot *snapshot)
{
    if (snapshot == NULL) { return ControlResearchResult_InvalidInput; }
    PlatformCriticalState lock = PlatformCritical_Enter();
    ControlResearch_StateRequire();
    ControlResearchSnapshot candidate = s_output;
    uint8_t intact = (uint8_t)((candidate.ready <= 1U) &&
        ((uint32_t)candidate.state <= ControlResearchState_Disabled) &&
        ((uint32_t)candidate.result <= ControlResearchResult_InvalidState) &&
        ((candidate.ready == 0U) || ((candidate.state == ControlResearchState_Running) &&
         (candidate.result == ControlResearchResult_Ok) &&
         (candidate.sequence != 0U) && (candidate.published_us != 0U) && isfinite(candidate.command) &&
         isfinite(candidate.angle_rad) && isfinite(candidate.rate_radps) &&
         (fabsf(candidate.command) <= 1.0f))));
    if (intact == 0U) { ControlResearch_Revoke(ControlResearchResult_InvalidState); }
    SILVERSTAR_ASSERT(intact != 0U, SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    uint64_t now_us = SystemTime_GetMonotonicUs();
    SystemLifecycleState lifecycle = SystemLifecycle_GetState();
    uint8_t ready = (uint8_t)((candidate.ready == 1U) &&
        (s_control.state == ControlResearchState_Running) && (s_control.backend_started == 1U) &&
        (now_us >= candidate.published_us) &&
        (now_us - candidate.published_us <= CONTROL_RESEARCH_PERIOD_US + CONTROL_RESEARCH_LATENESS_US) &&
        (now_us >= candidate.navigation_us) && (now_us >= candidate.imu_us) &&
        (now_us - candidate.navigation_us <= CONTROL_RESEARCH_INPUT_AGE_US) &&
        (now_us - candidate.imu_us <= CONTROL_RESEARCH_INPUT_AGE_US) &&
        ((lifecycle == SYSTEM_STATE_FLIGHT) || (lifecycle == SYSTEM_STATE_RECOVERY)) &&
        (SystemMissionProcess_ControlWindowGet() == SystemMissionControlWindowResult_Active) &&
        (ControlResearch_PublicationCheck(&s_control.provenance, candidate.navigation_us,
            s_control.navigation_sequence) == ControlResearchResult_Ok));
    if (ready == 0U) { candidate.ready = 0U; candidate.command = 0.0f; }
    *snapshot = candidate;
    PlatformCritical_Exit(lock);
    return ready ? ControlResearchResult_Ok : ControlResearchResult_Unavailable;
}
