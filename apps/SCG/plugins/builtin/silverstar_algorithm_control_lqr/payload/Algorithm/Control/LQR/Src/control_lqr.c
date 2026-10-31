#include "control_lqr.h"
#include <math.h>
#include <stddef.h>

ControlLqrResult ControlLqr_Step(const ControlLqrConfig *config,
    const float error[2], float *output)
{
    float requested;
    if (output == NULL) { return CONTROL_LQR_INVALID_INPUT; }
    *output = 0.0f;
    if ((config == NULL) || (error == NULL) || !isfinite(config->gain[0]) ||
        !isfinite(config->gain[1]) || !isfinite(config->output_limit) ||
        (config->output_limit <= 0.0f) || !isfinite(error[0]) || !isfinite(error[1]))
    { return CONTROL_LQR_INVALID_INPUT; }
    requested = -config->gain[0] * error[0] - config->gain[1] * error[1];
    if (!isfinite(requested)) { return CONTROL_LQR_NUMERIC_ERROR; }
    *output = fminf(config->output_limit, fmaxf(-config->output_limit, requested));
    return CONTROL_LQR_OK;
}
