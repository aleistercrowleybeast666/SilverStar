#ifndef __SYSTEM_NAVIGATION_PROVENANCE_H
#define __SYSTEM_NAVIGATION_PROVENANCE_H

#include <stdint.h>

/* Producer-owned history, copied with admitted inertial work. valid == 0 is
 * unknown; instance 0 is legal and epoch 0 is used only by non-epoch builds.
 * Never inferred from whichever source is current when a consumer reads it. */
typedef struct
{
    uint32_t calibration_generation;
    uint32_t sensor_epoch;
    uint32_t source_instance;
    uint8_t valid;
} SystemNavigationProvenance;

#endif /* __SYSTEM_NAVIGATION_PROVENANCE_H */
