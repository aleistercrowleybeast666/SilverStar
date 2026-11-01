#ifndef __CONTROL_PID_PROJECT_H
#define __CONTROL_PID_PROJECT_H

#include "control_pid.h"

/* Build-time parameter consumer only. No actuator or mission permission. */
ControlPidResult ControlPid_ProjectConfigGet(ControlPidConfig *config);

#endif
