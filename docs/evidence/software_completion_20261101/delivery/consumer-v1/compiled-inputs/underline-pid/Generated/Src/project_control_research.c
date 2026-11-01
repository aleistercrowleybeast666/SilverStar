#include "control_research.h"
#include <stddef.h>

#include "control_pid_project.h"
#include "platform_memory.h"
static PLATFORM_CPU_FAST_BSS ControlPidConfig s_config;
static PLATFORM_CPU_FAST_BSS uint8_t s_started;
static PLATFORM_CPU_FAST_BSS ControlPidContext s_context;

ControlResearchResult ControlResearchBackend_Start(float *limit)
{
    if (limit == NULL) { return ControlResearchResult_InvalidInput; }
    *limit = 0.0f;
    if (ControlPid_ProjectConfigGet(&s_config) != CONTROL_PID_OK)
    { return ControlResearchResult_BackendError; }
    if ((s_config.output_limit <= 0.0f) || (s_config.output_limit > 1.0f))
    { return ControlResearchResult_InvalidInput; }
    if (ControlPid_Start(&s_context, &s_config) != CONTROL_PID_OK)
    { return ControlResearchResult_BackendError; }
    *limit = s_config.output_limit * CONTROL_RESEARCH_TORQUE_REFERENCE_NM;
    s_started = 1U;
    return ControlResearchResult_Ok;
}

ControlResearchResult ControlResearchBackend_Stop(void)
{
    s_started = 0U;
    if (ControlPid_Stop(&s_context) != CONTROL_PID_OK)
    { return ControlResearchResult_BackendError; }
    return ControlResearchResult_Ok;
}

ControlResearchResult ControlResearchBackend_Step(float angle_rad, float rate_radps, float *output)
{
    if (output == NULL) { return ControlResearchResult_InvalidInput; }
    *output = 0.0f;
    if (s_started != 1U) { return ControlResearchResult_Stopped; }
    (void)rate_radps;
    if (ControlPid_Step(&s_context, &s_config, 0.0f, angle_rad, 0.01f, output) != CONTROL_PID_OK)
    { *output = 0.0f; return ControlResearchResult_BackendError; }
    *output *= CONTROL_RESEARCH_TORQUE_REFERENCE_NM;
    return ControlResearchResult_Ok;
}
