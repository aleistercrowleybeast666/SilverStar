#ifndef __CONTROL_PID_H
#define __CONTROL_PID_H

#include <stdint.h>

typedef enum
{
    CONTROL_PID_OK = 0,
    CONTROL_PID_INVALID_INPUT,
    CONTROL_PID_STOPPED,
    CONTROL_PID_NUMERIC_ERROR
} ControlPidResult;

/* e = reference - measurement; derivative acts on measurement, no setpoint kick.
 * kp [output/input], ki [output/(input*s)], kd [output*s/input]. */
typedef struct
{
    float kp, ki, kd;
    float derivative_tau_s, integral_limit, output_limit, sample_period_s;
} ControlPidConfig;

typedef struct
{
    float integral, previous_measurement, derivative;
    uint8_t started, has_previous;
} ControlPidContext;

ControlPidResult ControlPid_Start(ControlPidContext *context, const ControlPidConfig *config);
ControlPidResult ControlPid_Stop(ControlPidContext *context);
ControlPidResult ControlPid_Step(ControlPidContext *context, const ControlPidConfig *config,
    float reference, float measurement, float dt_s, float *output);

#endif
