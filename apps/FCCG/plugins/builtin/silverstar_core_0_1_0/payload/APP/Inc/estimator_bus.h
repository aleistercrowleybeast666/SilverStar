#ifndef __ESTIMATOR_BUS_H
#define __ESTIMATOR_BUS_H

#include <stdint.h>

#include "system_device_types.h"

#define ESTIMATOR_BUS_DEPTH 64U

typedef SystemInertialIncrement EstimatorPredictionInput;

typedef struct
{
    uint64_t timestamp_us;
    uint64_t receive_timestamp_us;
    uint8_t measurement_timestamp_trusted;
    uint32_t sequence;
    int32_t pressure_raw_pa;
    int32_t height_raw_cm;
    float pressure_pa;
    float altitude_m;
    float variance_m2;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint8_t healthy;
    uint8_t valid;
} EstimatorPressureSnapshot;

typedef struct
{
    uint16_t prediction_count;
    uint32_t prediction_push_count;
    uint32_t prediction_pop_count;
    uint32_t prediction_overflow_count;
} EstimatorBusStats;

typedef enum
{
    ESTIMATOR_BUS_RESULT_OK = 0U,
    ESTIMATOR_BUS_RESULT_EMPTY,
    ESTIMATOR_BUS_RESULT_FULL,
    ESTIMATOR_BUS_RESULT_BAD_PARAM,
    ESTIMATOR_BUS_RESULT_NOT_READY
} EstimatorBusResult;

EstimatorBusResult EstimatorBus_Init(void);
void EstimatorBus_ResetFlightData(void);
EstimatorBusResult EstimatorBus_PredictionPush(
    const SystemInertialIncrement *input);
EstimatorBusResult EstimatorBus_PredictionPop(SystemInertialIncrement *input);
EstimatorBusResult EstimatorBus_PressurePublish(
    const EstimatorPressureSnapshot *snapshot);
uint8_t EstimatorBus_PressureGetLatest(EstimatorPressureSnapshot *snapshot);
void EstimatorBus_StatsGet(EstimatorBusStats *stats);

#endif /* __ESTIMATOR_BUS_H */
