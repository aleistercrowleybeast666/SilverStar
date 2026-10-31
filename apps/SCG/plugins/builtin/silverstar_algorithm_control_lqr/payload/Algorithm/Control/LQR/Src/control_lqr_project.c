#include "control_lqr_project.h"
#include "project_algorithm_parameters.h"
#include <stddef.h>

ControlLqrResult ControlLqr_ProjectConfigGet(ControlLqrConfig *config)
{
    const ControlLqrConfig candidate = {
        {SYSTEM_CONTROL_LQR_K_ANGLE, SYSTEM_CONTROL_LQR_K_RATE},
        SYSTEM_CONTROL_LQR_OUTPUT_LIMIT
    };
    const float zero_error[2] = {0.0f, 0.0f};
    float output;
    ControlLqrResult result;
    if (config == NULL) { return CONTROL_LQR_INVALID_INPUT; }
    result = ControlLqr_Step(&candidate, zero_error, &output);
    if (result != CONTROL_LQR_OK) { return result; }
    *config = candidate;
    return CONTROL_LQR_OK;
}
