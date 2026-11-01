#include "control_research.h"
#include <stddef.h>

#include "control_lqr_project.h"
#include "platform_memory.h"
static PLATFORM_CPU_FAST_BSS ControlLqrConfig s_config;
static PLATFORM_CPU_FAST_BSS uint8_t s_started;

ControlResearchResult ControlResearchBackend_Start(float *limit)
{
    if (limit == NULL) { return ControlResearchResult_InvalidInput; }
    *limit = 0.0f;
    if (ControlLqr_ProjectConfigGet(&s_config) != CONTROL_LQR_OK)
    { return ControlResearchResult_BackendError; }
    if ((s_config.output_limit <= 0.0f) || (s_config.output_limit > 1.0f))
    { return ControlResearchResult_InvalidInput; }
    *limit = s_config.output_limit * CONTROL_RESEARCH_TORQUE_REFERENCE_NM;
    s_started = 1U;
    return ControlResearchResult_Ok;
}

ControlResearchResult ControlResearchBackend_Stop(void)
{
    s_started = 0U;
    return ControlResearchResult_Ok;
}

ControlResearchResult ControlResearchBackend_Step(float angle_rad, float rate_radps, float *output)
{
    if (output == NULL) { return ControlResearchResult_InvalidInput; }
    *output = 0.0f;
    if (s_started != 1U) { return ControlResearchResult_Stopped; }
    const float error[2] = {angle_rad, rate_radps};
    if (ControlLqr_Step(&s_config, error, output) != CONTROL_LQR_OK)
    { *output = 0.0f; return ControlResearchResult_BackendError; }
    *output *= CONTROL_RESEARCH_TORQUE_REFERENCE_NM;
    return ControlResearchResult_Ok;
}
