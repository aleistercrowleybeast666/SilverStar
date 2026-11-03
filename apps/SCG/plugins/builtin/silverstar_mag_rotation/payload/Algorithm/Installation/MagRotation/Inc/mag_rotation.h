#ifndef __MAG_ROTATION_H
#define __MAG_ROTATION_H
#include <stdint.h>

typedef enum
{
    MagRotationResult_Waiting = 0,
    MagRotationResult_Training,
    MagRotationResult_Candidate,
    MagRotationResult_Accepted,
    MagRotationResult_Unobservable,
    MagRotationResult_Disturbed,
    MagRotationResult_Stale,
    MagRotationResult_WrongSource
} MagRotationResult;

/* q maps the intrinsically corrected, fixed-reference magnetic vector into
 * the selected IMU body convention. No position or field is estimated. */
typedef struct
{
    float q[4], previous[3], previous_magnitude;
    float h[3][3], gradient[3], residual_sum, energy;
    float relative_rms;
    uint64_t previous_us;
    uint16_t pairs;
    uint8_t validation, good_windows, last_window_pairs;
} MagRotationFit;

void MagRotation_Reset(MagRotationFit *fit);
MagRotationResult MagRotation_Step(MagRotationFit *fit, uint64_t time_us, const float field[3],
                                   const float average_gyro[3]);
void MagRotation_VectorRotate(const float q[4], const float input[3], float output[3]);
uint32_t MagRotation_Encode(const float q[4]);
void MagRotation_Decode(uint32_t packed, float q[4]);
#endif
