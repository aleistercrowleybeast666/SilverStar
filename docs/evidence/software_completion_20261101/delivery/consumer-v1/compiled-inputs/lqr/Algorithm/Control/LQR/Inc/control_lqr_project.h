#ifndef __CONTROL_LQR_PROJECT_H
#define __CONTROL_LQR_PROJECT_H

#include "control_lqr.h"

/* Build-time parameter consumer only. No actuator or mission permission. */
ControlLqrResult ControlLqr_ProjectConfigGet(ControlLqrConfig *config);

#endif
