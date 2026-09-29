#ifndef __MS5611_CORE_H
#define __MS5611_CORE_H

#include <stdint.h>

#include "system_barometer_if.h"

typedef enum
{
    Ms5611BusOk = 0,
    Ms5611BusError
} Ms5611BusResult;

typedef Ms5611BusResult (*Ms5611CommandWriteOperation)(void *bus,
    uint8_t command);
typedef Ms5611BusResult (*Ms5611CommandReadOperation)(void *bus,
    uint8_t command, uint8_t *bytes, uint8_t length);

typedef struct
{
    void *bus;
    Ms5611CommandWriteOperation write;
    Ms5611CommandReadOperation read;
} Ms5611Port;

typedef enum
{
    Ms5611StateReset = 0,
    Ms5611StateWaitReset,
    Ms5611StateReadProm,
    Ms5611StateCheckProm,
    Ms5611StateStartTemperature,
    Ms5611StateWaitTemperature,
    Ms5611StateReadTemperature,
    Ms5611StateStartPressure,
    Ms5611StateWaitPressure,
    Ms5611StateReadPressure,
    Ms5611StateFailed
} Ms5611State;

typedef enum
{
    Ms5611StepPending = 0,
    Ms5611StepSampleReady,
    Ms5611StepBusError,
    Ms5611StepPromCrcError,
    Ms5611StepInvalidProm,
    Ms5611StepConversionTimeout,
    Ms5611StepInvalidSample
} Ms5611StepResult;

typedef struct
{
    Ms5611Port port;
    SystemBarometerSample sample;
    uint16_t prom[8];
    uint32_t raw_temperature;
    Ms5611State state;
    uint64_t phase_started_us;
    uint64_t cycle_started_us;
    uint32_t error_count;
    uint32_t sequence;
    uint8_t prom_index;
} Ms5611Context;

void Ms5611_Init(Ms5611Context *context, const Ms5611Port *port);
Ms5611StepResult Ms5611_Step(Ms5611Context *context, uint64_t now_us);
uint8_t Ms5611_Crc4Get(const uint16_t prom[8]);
Ms5611StepResult Ms5611_Compensate(const uint16_t prom[8],
    uint32_t raw_pressure, uint32_t raw_temperature,
    float *pressure_pa, float *temperature_c);

#endif /* __MS5611_CORE_H */
