#include "estimator_bus.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"

static SystemInertialIncrement s_queue[ESTIMATOR_BUS_DEPTH];
static volatile uint16_t s_head;
static volatile uint16_t s_tail;
static uint8_t s_initialized;
static EstimatorPressureSnapshot s_pressure;
static uint8_t s_pressure_valid;
static EstimatorBusStats s_stats;

static uint16_t EstimatorBus_Next(uint16_t index)
{
    index++;
    return (index >= ESTIMATOR_BUS_DEPTH) ? 0U : index;
}

static PlatformCriticalState EstimatorBus_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void EstimatorBus_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

EstimatorBusResult EstimatorBus_Init(void)
{
    if (s_initialized != 0U) { return ESTIMATOR_BUS_RESULT_OK; }
    (void)memset(s_queue, 0, sizeof(s_queue));
    (void)memset(&s_pressure, 0, sizeof(s_pressure));
    (void)memset(&s_stats, 0, sizeof(s_stats));
    s_head = 0U;
    s_tail = 0U;
    s_pressure_valid = 0U;
    s_initialized = 1U;
    return ESTIMATOR_BUS_RESULT_OK;
}

void EstimatorBus_ResetFlightData(void)
{
    uint32_t primask = EstimatorBus_IrqLock();

    s_head = 0U;
    s_tail = 0U;
    s_stats.prediction_count = 0U;
    EstimatorBus_IrqUnlock(primask);
}

EstimatorBusResult EstimatorBus_PredictionPush(
    const SystemInertialIncrement *input)
{
    uint16_t next_head;
    uint32_t primask;

    if (input == NULL) { return ESTIMATOR_BUS_RESULT_BAD_PARAM; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemInertialIncrement,
                             SILVERSTAR_ASSERT_MODULE_APP);
    primask = EstimatorBus_IrqLock();
    if (s_initialized == 0U)
    {
        EstimatorBus_IrqUnlock(primask);
        return ESTIMATOR_BUS_RESULT_NOT_READY;
    }
    next_head = EstimatorBus_Next(s_head);
    if (next_head == s_tail)
    {
        s_stats.prediction_overflow_count++;
        EstimatorBus_IrqUnlock(primask);
        return ESTIMATOR_BUS_RESULT_FULL;
    }
    s_queue[s_head] = *input;
    s_head = next_head;
    s_stats.prediction_push_count++;
    s_stats.prediction_count++;
    EstimatorBus_IrqUnlock(primask);
    return ESTIMATOR_BUS_RESULT_OK;
}

EstimatorBusResult EstimatorBus_PredictionPop(SystemInertialIncrement *input)
{
    uint32_t primask;

    if (input == NULL) { return ESTIMATOR_BUS_RESULT_BAD_PARAM; }
    SILVERSTAR_ASSERT_OBJECT(input, SystemInertialIncrement,
                             SILVERSTAR_ASSERT_MODULE_APP);
    primask = EstimatorBus_IrqLock();
    if (s_initialized == 0U)
    {
        EstimatorBus_IrqUnlock(primask);
        return ESTIMATOR_BUS_RESULT_NOT_READY;
    }
    if (s_tail == s_head)
    {
        EstimatorBus_IrqUnlock(primask);
        return ESTIMATOR_BUS_RESULT_EMPTY;
    }
    *input = s_queue[s_tail];
    s_tail = EstimatorBus_Next(s_tail);
    s_stats.prediction_pop_count++;
    if (s_stats.prediction_count != 0U) { s_stats.prediction_count--; }
    EstimatorBus_IrqUnlock(primask);
    return ESTIMATOR_BUS_RESULT_OK;
}

EstimatorBusResult EstimatorBus_PressurePublish(
    const EstimatorPressureSnapshot *snapshot)
{
    uint32_t primask;

    if (snapshot == NULL) { return ESTIMATOR_BUS_RESULT_BAD_PARAM; }
    primask = EstimatorBus_IrqLock();
    if (s_initialized == 0U)
    {
        EstimatorBus_IrqUnlock(primask);
        return ESTIMATOR_BUS_RESULT_NOT_READY;
    }
    s_pressure = *snapshot;
    s_pressure_valid = snapshot->valid;
    EstimatorBus_IrqUnlock(primask);
    return ESTIMATOR_BUS_RESULT_OK;
}

uint8_t EstimatorBus_PressureGetLatest(EstimatorPressureSnapshot *snapshot)
{
    uint32_t primask;

    if (snapshot == NULL) { return 0U; }
    primask = EstimatorBus_IrqLock();
    if (s_pressure_valid == 0U)
    {
        EstimatorBus_IrqUnlock(primask);
        return 0U;
    }
    *snapshot = s_pressure;
    EstimatorBus_IrqUnlock(primask);
    return 1U;
}

void EstimatorBus_StatsGet(EstimatorBusStats *stats)
{
    uint32_t primask;

    if (stats == NULL) { return; }
    primask = EstimatorBus_IrqLock();
    *stats = s_stats;
    EstimatorBus_IrqUnlock(primask);
}
