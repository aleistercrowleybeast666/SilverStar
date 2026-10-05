#include <stdint.h>
#include <string.h>

#include "estimator_barometer_pending.h"
#include "test_common.h"

static EstimatorPressureSnapshot Test_SampleMake(uint32_t sequence,
                                                  uint64_t timestamp_us)
{
    EstimatorPressureSnapshot sample;

    (void)memset(&sample, 0, sizeof(sample));
    sample.sequence = sequence;
    sample.timestamp_us = timestamp_us;
    sample.receive_timestamp_us = timestamp_us + 10U;
    sample.altitude_m = 12.0f + (float)sequence;
    sample.valid = 1U;
    return sample;
}

static void Test_FutureSampleIsHeldUntilConsumed(void)
{
    EstimatorBarometerPendingContext pending;
    EstimatorPressureSnapshot first = Test_SampleMake(10U, 2000U);
    EstimatorPressureSnapshot newer = Test_SampleMake(11U, 3000U);
    EstimatorPressureSnapshot observed;
    uint32_t last_consumed = 9U;

    EstimatorBarometerPending_Reset(&pending);
    TEST_CHECK(EstimatorBarometerPending_TryLatch(
        &pending, &first, last_consumed) != 0U);
    TEST_CHECK(EstimatorBarometerPending_TryLatch(
        &pending, &newer, last_consumed) == 0U);
    TEST_CHECK(EstimatorBarometerPending_Get(&pending, &observed) != 0U);
    TEST_CHECK(observed.sequence == 10U &&
               observed.timestamp_us == 2000U);
    TEST_CHECK(last_consumed == 9U);

    TEST_CHECK(EstimatorBarometerPending_Consume(
        &pending, &last_consumed) != 0U);
    TEST_CHECK(last_consumed == 10U);
    TEST_CHECK(EstimatorBarometerPending_Get(&pending, &observed) == 0U);
    TEST_CHECK(EstimatorBarometerPending_TryLatch(
        &pending, &newer, last_consumed) != 0U);
    TEST_CHECK(EstimatorBarometerPending_Get(&pending, &observed) != 0U);
    TEST_CHECK(observed.sequence == 11U);
}

static void Test_ConsumedSequenceIsNotRelatched(void)
{
    EstimatorBarometerPendingContext pending;
    EstimatorPressureSnapshot sample = Test_SampleMake(20U, 5000U);
    uint32_t last_consumed = 20U;

    EstimatorBarometerPending_Reset(&pending);
    TEST_CHECK(EstimatorBarometerPending_TryLatch(
        &pending, &sample, last_consumed) == 0U);
    TEST_CHECK(EstimatorBarometerPending_Consume(
        &pending, &last_consumed) == 0U);
}

int main(void)
{
    Test_FutureSampleIsHeldUntilConsumed();
    Test_ConsumedSequenceIsNotRelatched();
    return Test_Finish("estimator_barometer_pending");
}
