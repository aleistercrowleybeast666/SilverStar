#ifndef __ESTIMATOR_BAROMETER_PENDING_H
#define __ESTIMATOR_BAROMETER_PENDING_H

#include <stdint.h>

#include "estimator_bus.h"

typedef struct
{
    EstimatorPressureSnapshot sample;
    uint8_t valid;
} EstimatorBarometerPendingContext;

void EstimatorBarometerPending_Reset(
    EstimatorBarometerPendingContext *context);
uint8_t EstimatorBarometerPending_TryLatch(
    EstimatorBarometerPendingContext *context,
    const EstimatorPressureSnapshot *latest,
    uint32_t last_consumed_sequence);
uint8_t EstimatorBarometerPending_Get(
    const EstimatorBarometerPendingContext *context,
    EstimatorPressureSnapshot *sample);
uint8_t EstimatorBarometerPending_Consume(
    EstimatorBarometerPendingContext *context,
    uint32_t *last_consumed_sequence);

#endif /* __ESTIMATOR_BAROMETER_PENDING_H */
