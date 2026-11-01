#include "control_pid_project.h"
#include "project_algorithm_parameters.h"
#include <stddef.h>

ControlPidResult ControlPid_ProjectConfigGet(ControlPidConfig *config)
{
    const ControlPidConfig candidate = {
        SYSTEM_CONTROL_PID_KP, SYSTEM_CONTROL_PID_KI, SYSTEM_CONTROL_PID_KD,
        SYSTEM_CONTROL_PID_DERIVATIVE_TAU_S, SYSTEM_CONTROL_PID_INTEGRAL_LIMIT,
        SYSTEM_CONTROL_PID_OUTPUT_LIMIT, SYSTEM_CONTROL_PID_SAMPLE_PERIOD_S
    };
    ControlPidContext validation;
    ControlPidResult result;
    if (config == NULL) { return CONTROL_PID_INVALID_INPUT; }
    result = ControlPid_Start(&validation, &candidate);
    if (result != CONTROL_PID_OK) { return result; }
    *config = candidate;
    return CONTROL_PID_OK;
}
