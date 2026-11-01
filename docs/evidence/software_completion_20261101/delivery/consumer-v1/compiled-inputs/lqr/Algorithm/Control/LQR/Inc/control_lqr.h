#ifndef __CONTROL_LQR_H
#define __CONTROL_LQR_H

/* Fixed 2-state / 1-input small-angle axis controller. The offline solver is
 * deliberately absent from the target. u = -K [angle_error_rad, rate_radps]. */
typedef enum
{
    CONTROL_LQR_OK = 0,
    CONTROL_LQR_INVALID_INPUT,
    CONTROL_LQR_NUMERIC_ERROR
} ControlLqrResult;

typedef struct
{
    float gain[2];
    float output_limit;
} ControlLqrConfig;

ControlLqrResult ControlLqr_Step(const ControlLqrConfig *config,
    const float error[2], float *output);

#endif
