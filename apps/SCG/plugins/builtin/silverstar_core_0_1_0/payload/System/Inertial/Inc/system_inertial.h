#ifndef __SYSTEM_INERTIAL_H
#define __SYSTEM_INERTIAL_H

#include "system_inertial_source_if.h"
#include "system_inertial_types.h"

SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemInertial_Init(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemInertial_LatestGet(
    SystemInertialSample *sample);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemInertial_NextGet(
    SystemInertialSample *sample);

#endif /* __SYSTEM_INERTIAL_H */
