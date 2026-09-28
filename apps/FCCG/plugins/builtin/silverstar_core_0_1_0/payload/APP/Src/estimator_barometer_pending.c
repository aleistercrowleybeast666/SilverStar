#include "estimator_barometer_pending.h"

#include <stddef.h>
#include <string.h>

void EstimatorBarometerPending_Reset(
    EstimatorBarometerPendingContext *context)
{
    if (context == NULL) { return; }
    (void)memset(context, 0, sizeof(*context));
}

uint8_t EstimatorBarometerPending_TryLatch(
    EstimatorBarometerPendingContext *context,
    const EstimatorPressureSnapshot *latest,
    uint32_t last_consumed_sequence)
{
    if ((context == NULL) || (latest == NULL) ||
        (context->valid != 0U) ||
        (latest->sequence == last_consumed_sequence))
    {
        return 0U;
    }
    context->sample = *latest;
    context->valid = 1U;
    return 1U;
}

uint8_t EstimatorBarometerPending_Get(
    const EstimatorBarometerPendingContext *context,
    EstimatorPressureSnapshot *sample)
{
    if ((context == NULL) || (sample == NULL) ||
        (context->valid == 0U))
    {
        return 0U;
    }
    *sample = context->sample;
    return 1U;
}

uint8_t EstimatorBarometerPending_Consume(
    EstimatorBarometerPendingContext *context,
    uint32_t *last_consumed_sequence)
{
    if ((context == NULL) || (last_consumed_sequence == NULL) ||
        (context->valid == 0U))
    {
        return 0U;
    }
    *last_consumed_sequence = context->sample.sequence;
    context->valid = 0U;
    return 1U;
}
