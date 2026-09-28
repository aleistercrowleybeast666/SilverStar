#ifndef __ALIGNMENT_STRATEGY_BINDING_H
#define __ALIGNMENT_STRATEGY_BINDING_H

#include <stdint.h>

#include "alignment_strategy_types.h"
#include "attitude_triad.h"

typedef struct
{
    AttitudeTriadAccumulator triad;
    uint32_t last_magnetometer_sequence;
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
