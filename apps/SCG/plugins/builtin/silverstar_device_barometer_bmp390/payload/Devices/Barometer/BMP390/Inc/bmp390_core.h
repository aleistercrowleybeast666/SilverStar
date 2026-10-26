#ifndef __BMP390_CORE_H
#define __BMP390_CORE_H

#include <stdint.h>

#define BMP390_SAMPLE_FIELD_PRESSURE (1UL << 0)
#define BMP390_SAMPLE_FIELD_TEMPERATURE (1UL << 3)

/* Native driver value; the System-facing adapter performs the conversion.
 * Preserve every field and its representation; no RAM or record reduction. */
typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint8_t measurement_timestamp_trusted;
    uint32_t sequence;
    int32_t pressure_raw_pa;
    int32_t altitude_raw_cm;
    float pressure_pa;
    float altitude_m;
    float altitude_variance_m2;
    float temperature_c;
    uint32_t supported_fields;
    uint32_t valid_fields;
    uint32_t valid_mask;
} Bmp390Sample;

typedef enum
{
    Bmp390BusOk = 0,
    Bmp390BusError
} Bmp390BusResult;

typedef struct
{
    void *bus;
} Bmp390Port;

Bmp390BusResult Bmp390Bus_Read(void *bus, uint8_t register_address, uint8_t *bytes, uint8_t length);
Bmp390BusResult Bmp390Bus_Write(void *bus, uint8_t register_address, uint8_t value);

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
    Bmp390Sample sample;
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
