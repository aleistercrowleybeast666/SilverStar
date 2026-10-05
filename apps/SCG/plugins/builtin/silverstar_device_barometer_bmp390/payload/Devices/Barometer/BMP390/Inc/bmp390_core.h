#ifndef __BMP390_CORE_H
#define __BMP390_CORE_H

#include <stdint.h>

#include "system_barometer_if.h"

typedef enum
{
    Bmp390BusOk = 0,
    Bmp390BusError
} Bmp390BusResult;

typedef Bmp390BusResult (*Bmp390ReadOperation)(void *bus, uint8_t register_address,
    uint8_t *bytes, uint8_t length);
typedef Bmp390BusResult (*Bmp390WriteOperation)(void *bus, uint8_t register_address,
    uint8_t value);

typedef struct
{
    void *bus;
    Bmp390ReadOperation read;
    Bmp390WriteOperation write;
} Bmp390Port;

typedef enum
{
    Bmp390StateProbe = 0,
    Bmp390StateReadTrim,
    Bmp390StateReadOsr,
    Bmp390StateApplyOsr,
    Bmp390StateVerifyOsr,
    Bmp390StateReadFilter,
    Bmp390StateApplyFilter,
    Bmp390StateVerifyFilter,
    Bmp390StateStartConversion,
    Bmp390StateWaitConversion,
    Bmp390StateReadSample,
    Bmp390StateFailed
} Bmp390State;

typedef enum
{
    Bmp390StepPending = 0,
    Bmp390StepSampleReady,
    Bmp390StepNotPresent,
    Bmp390StepBusError,
    Bmp390StepInvalidTrim,
    Bmp390StepVerifyFailed,
    Bmp390StepConversionTimeout,
    Bmp390StepInvalidSample
} Bmp390StepResult;

typedef struct
{
    uint8_t bytes[21];
} Bmp390Trim;

typedef struct
{
    Bmp390Port port;
    Bmp390Trim trim;
    SystemBarometerSample sample;
    Bmp390State state;
    uint64_t conversion_started_us;
    uint64_t cycle_started_us;
    uint32_t error_count;
    uint32_t sequence;
} Bmp390Context;

void Bmp390_Init(Bmp390Context *context, const Bmp390Port *port);
Bmp390StepResult Bmp390_Step(Bmp390Context *context, uint64_t now_us);
Bmp390StepResult Bmp390_Compensate(const Bmp390Trim *trim,
    uint32_t raw_pressure, uint32_t raw_temperature,
    float *pressure_pa, float *temperature_c);

#endif /* __BMP390_CORE_H */
