#ifndef __ALIGNMENT_STRATEGY_BINDING_H
#define __ALIGNMENT_STRATEGY_BINDING_H

#include <stdint.h>

#include "alignment_strategy_types.h"

typedef struct
{
    float acceleration_sum_b_mps2[3];
    float gyro_sum_b_radps[3];
    float magnetic_sum_b_uT[3];
    uint64_t first_timestamp_us;
    uint64_t last_timestamp_us;
    uint32_t last_magnetometer_sequence;
    uint32_t reject_count;
    uint16_t sample_count;
    uint8_t magnetometer_seen;
} AlignmentStrategyContext;

void AlignmentStrategy_Init(AlignmentStrategyContext *context);
uint8_t AlignmentStrategy_MagnetometerRequired(void);
uint8_t AlignmentStrategy_HardwareQuaternionRequired(void);
AlignmentStrategyProcessResult AlignmentStrategy_SampleProcess(
    AlignmentStrategyContext *context,
    const AlignmentStrategyConfig *config,
    const AlignmentStrategySample *sample,
    AlignmentStrategyOutput *output);

#endif /* __ALIGNMENT_STRATEGY_BINDING_H */
