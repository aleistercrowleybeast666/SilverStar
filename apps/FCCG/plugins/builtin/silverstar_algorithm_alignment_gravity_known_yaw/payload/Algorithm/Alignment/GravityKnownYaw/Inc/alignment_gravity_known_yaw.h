#ifndef __ALIGNMENT_GRAVITY_KNOWN_YAW_H
#define __ALIGNMENT_GRAVITY_KNOWN_YAW_H

#include <stdint.h>

uint8_t AttitudeAlignment_GravityKnownYawBuild(
    const float acceleration_mean_b_mps2[3],
    float yaw_deg,
    float output_q_nb[4]);

#endif /* __ALIGNMENT_GRAVITY_KNOWN_YAW_H */
