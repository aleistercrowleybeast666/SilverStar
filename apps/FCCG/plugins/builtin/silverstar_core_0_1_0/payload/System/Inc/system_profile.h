#ifndef __SYSTEM_PROFILE_H
#define __SYSTEM_PROFILE_H

#include <stdint.h>

#include "system_capabilities.h"
typedef struct
{
    uint32_t profile_id;
    uint8_t output_channel_count;
    uint32_t enabled_capabilities;
    uint32_t required_capabilities;
    uint32_t optional_capabilities;
} SystemProfile;

const SystemProfile *SystemProfile_Get(void);
uint8_t SystemProfile_IsFrozen(void);
void SystemProfile_Freeze(void);
void SystemProfile_UnfreezeForRollback(void);

#endif /* __SYSTEM_PROFILE_H */
