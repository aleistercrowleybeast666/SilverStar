#ifndef __SYSTEM_USER_INERTIAL_CONFIG_H
#define __SYSTEM_USER_INERTIAL_CONFIG_H

#include <stdint.h>

#include "system_inertial_source_if.h"

#define SYSTEM_USER_INERTIAL_PRIMARY_SOURCE_ID 0UL
#define SYSTEM_USER_INERTIAL_SOURCE_FIFO_DEPTH 1U

typedef struct
{
    SystemInertialSourceDescriptor primary_source;
    SystemInertialSourceCorrection source_correction;
    SystemInertialTimeSyncConfig time_sync;
    uint16_t source_fifo_depth;
} SystemUserInertialConfig;

const SystemUserInertialConfig *SystemUserInertial_ConfigGet(void);

#endif /* __SYSTEM_USER_INERTIAL_CONFIG_H */
