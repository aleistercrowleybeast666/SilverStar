#ifndef __BMP280_CORE_H
#define __BMP280_CORE_H

#include <stdint.h>

#define BMP280_SAMPLE_FIELD_PRESSURE (1UL << 0)
#define BMP280_SAMPLE_FIELD_TEMPERATURE (1UL << 3)

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
} Bmp280Sample;

typedef enum
{
    Bmp280BusOk = 0,
    Bmp280BusError
} Bmp280BusResult;

/* Stored bus data; operations have fixed direct call targets. */
typedef struct
{
    void *bus;
} Bmp280Port;

Bmp280BusResult Bmp280Bus_Read(void *bus, uint8_t register_address, uint8_t *bytes, uint8_t length);
Bmp280BusResult Bmp280Bus_Write(void *bus, uint8_t register_address, uint8_t value);

typedef enum
{
    Bmp280StateProbe = 0,
    Bmp280StateReadTrim,
    Bmp280StateReadConfig,
    Bmp280StateApplyConfig,
    Bmp280StateVerifyConfig,
    Bmp280StateStartConversion,
    Bmp280StateWaitConversion,
    Bmp280StateReadSample,
    Bmp280StateFailed
} Bmp280State;

typedef enum
{
    Bmp280StepPending = 0,
    Bmp280StepSampleReady,
    Bmp280StepNotPresent,
    Bmp280StepBusError,
    Bmp280StepInvalidTrim,
    Bmp280StepVerifyFailed,
    Bmp280StepConversionTimeout,
    Bmp280StepInvalidSample
} Bmp280StepResult;

typedef struct
{
    uint16_t t1;
    int16_t t2;
    int16_t t3;
    uint16_t p1;
    int16_t p2;
    int16_t p3;
    int16_t p4;
    int16_t p5;
    int16_t p6;
    int16_t p7;
    int16_t p8;
    int16_t p9;
} Bmp280Trim;

typedef struct
{
    Bmp280Port port;
    Bmp280Trim trim;
    Bmp280Sample sample;
    Bmp280State state;
    uint64_t conversion_started_us;
    uint32_t error_count;
    uint32_t sequence;
} Bmp280Context;

void Bmp280_Init(Bmp280Context *context, const Bmp280Port *port);
Bmp280StepResult Bmp280_Step(Bmp280Context *context, uint64_t now_us);
Bmp280StepResult Bmp280_Compensate(const Bmp280Trim *trim,
    uint32_t raw_pressure, uint32_t raw_temperature,
    float *pressure_pa, float *temperature_c);

#endif /* __BMP280_CORE_H */
