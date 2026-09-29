#include "ms5611_core.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define MS5611_RESET_COMMAND 0x1EU
#define MS5611_PROM_READ_FIRST 0xA0U
#define MS5611_ADC_READ_COMMAND 0x00U
#define MS5611_START_PRESSURE_OSR4096 0x48U
#define MS5611_START_TEMPERATURE_OSR4096 0x58U
#define MS5611_RESET_WAIT_US 3000ULL
#define MS5611_CONVERSION_WAIT_US 10000ULL
#define MS5611_CONVERSION_TIMEOUT_US 30000ULL
#define MS5611_CYCLE_PERIOD_US 50000ULL

static uint64_t Ms5611_ElapsedGet(uint64_t now_us, uint64_t started_us)
{
    return now_us >= started_us ? now_us - started_us : 0ULL;
}

uint8_t Ms5611_Crc4Get(const uint16_t prom[8])
{
    uint16_t remainder = 0U;
    uint8_t index;
    uint8_t bit;
    uint16_t word;
    if (prom == NULL) { return 0xFFU; }
    for (index = 0U; index < 16U; index++)
    {
        word = prom[index / 2U];
        if (index == 15U) { word &= 0xFFF0U; }
        remainder ^= (index & 1U) == 0U ?
            (uint16_t)(word >> 8U) : (uint16_t)(word & 0x00FFU);
        for (bit = 0U; bit < 8U; bit++)
        {
            remainder = (remainder & 0x8000U) != 0U ?
                (uint16_t)((remainder << 1U) ^ 0x3000U) :
                (uint16_t)(remainder << 1U);
        }
    }
    return (uint8_t)((remainder >> 12U) & 0x0FU);
}

Ms5611StepResult Ms5611_Compensate(const uint16_t prom[8],
    uint32_t raw_pressure, uint32_t raw_temperature,
    float *pressure_pa, float *temperature_c)
{
    int64_t delta_temperature;
    int64_t temperature;
    int64_t offset;
    int64_t sensitivity;
    int64_t temperature_second;
    int64_t offset_second;
    int64_t sensitivity_second;
    int64_t temperature_delta;
    int64_t pressure;
    uint8_t index;
    if ((prom == NULL) || (pressure_pa == NULL) ||
        (temperature_c == NULL) || (raw_pressure == 0U) ||
        (raw_temperature == 0U) || (raw_pressure > 0xFFFFFFU) ||
        (raw_temperature > 0xFFFFFFU))
    { return Ms5611StepInvalidSample; }
    for (index = 1U; index <= 6U; index++)
    {
        if ((prom[index] == 0U) || (prom[index] == 0xFFFFU))
        { return Ms5611StepInvalidProm; }
    }
    delta_temperature = (int64_t)raw_temperature -
        (int64_t)prom[5] * 256LL;
    temperature = 2000LL + delta_temperature * (int64_t)prom[6] /
        (1LL << 23U);
    offset = (int64_t)prom[2] * (1LL << 16U) +
        (int64_t)prom[4] * delta_temperature / (1LL << 7U);
    sensitivity = (int64_t)prom[1] * (1LL << 15U) +
        (int64_t)prom[3] * delta_temperature / (1LL << 8U);
    temperature_second = 0LL;
    offset_second = 0LL;
    sensitivity_second = 0LL;
    if (temperature < 2000LL)
    {
        temperature_delta = temperature - 2000LL;
        temperature_second = delta_temperature * delta_temperature /
            (1LL << 31U);
        offset_second = 5LL * temperature_delta * temperature_delta / 2LL;
        sensitivity_second = 5LL * temperature_delta * temperature_delta / 4LL;
        if (temperature < -1500LL)
        {
            temperature_delta = temperature + 1500LL;
            offset_second += 7LL * temperature_delta * temperature_delta;
            sensitivity_second += 11LL * temperature_delta *
                temperature_delta / 2LL;
        }
    }
    temperature -= temperature_second;
    offset -= offset_second;
    sensitivity -= sensitivity_second;
    pressure = ((int64_t)raw_pressure * sensitivity / (1LL << 21U) -
        offset) / (1LL << 15U);
    *pressure_pa = (float)pressure;
    *temperature_c = (float)temperature / 100.0F;
    if ((!isfinite(*pressure_pa)) || (!isfinite(*temperature_c)) ||
        (*pressure_pa < 1000.0F) || (*pressure_pa > 120000.0F) ||
        (*temperature_c < -40.0F) || (*temperature_c > 85.0F))
    { return Ms5611StepInvalidSample; }
    return Ms5611StepSampleReady;
}

void Ms5611_Init(Ms5611Context *context, const Ms5611Port *port)
{
    if (context == NULL) { return; }
    (void)memset(context, 0, sizeof(*context));
    if ((port == NULL) || (port->write == NULL) || (port->read == NULL))
    { context->state = Ms5611StateFailed; return; }
    context->port = *port;
    context->state = Ms5611StateReset;
}

static Ms5611StepResult Ms5611_Fail(Ms5611Context *context,
    Ms5611StepResult result)
{
    context->error_count++;
    context->state = Ms5611StateFailed;
    return result;
}

Ms5611StepResult Ms5611_Step(Ms5611Context *context, uint64_t now_us)
{
    uint8_t bytes[3];
    uint32_t raw_pressure;
    float pressure;
    float temperature;
    Ms5611StepResult result;
    if (context == NULL) { return Ms5611StepBusError; }
    if (context->state == Ms5611StateFailed)
    { return Ms5611StepInvalidSample; }
    if (context->state == Ms5611StateReset)
    {
        if (context->port.write(context->port.bus,
                MS5611_RESET_COMMAND) != Ms5611BusOk)
        { return Ms5611_Fail(context, Ms5611StepBusError); }
        context->phase_started_us = now_us;
        context->state = Ms5611StateWaitReset;
    }
    else if (context->state == Ms5611StateWaitReset)
    {
        if (Ms5611_ElapsedGet(now_us, context->phase_started_us) <
            MS5611_RESET_WAIT_US)
        { return Ms5611StepPending; }
        context->state = Ms5611StateReadProm;
    }
    else if (context->state == Ms5611StateReadProm)
    {
        uint8_t command = (uint8_t)(MS5611_PROM_READ_FIRST +
            (uint8_t)(2U * context->prom_index));
        if (context->port.read(context->port.bus, command, bytes, 2U) !=
            Ms5611BusOk)
        { return Ms5611_Fail(context, Ms5611StepBusError); }
        context->prom[context->prom_index] =
            (uint16_t)(((uint16_t)bytes[0] << 8U) | bytes[1]);
        context->prom_index++;
        if (context->prom_index == 8U)
        { context->state = Ms5611StateCheckProm; }
    }
    else if (context->state == Ms5611StateCheckProm)
    {
        if (Ms5611_Crc4Get(context->prom) !=
            (uint8_t)(context->prom[7] & 0x0FU))
        { return Ms5611_Fail(context, Ms5611StepPromCrcError); }
        context->state = Ms5611StateStartTemperature;
    }
    else if (context->state == Ms5611StateStartTemperature)
    {
        if ((context->sequence != 0U) &&
            (Ms5611_ElapsedGet(now_us, context->cycle_started_us) <
                MS5611_CYCLE_PERIOD_US))
        { return Ms5611StepPending; }
        if (context->port.write(context->port.bus,
                MS5611_START_TEMPERATURE_OSR4096) != Ms5611BusOk)
        { return Ms5611_Fail(context, Ms5611StepBusError); }
        context->cycle_started_us = now_us;
        context->phase_started_us = now_us;
        context->state = Ms5611StateWaitTemperature;
    }
    else if (context->state == Ms5611StateWaitTemperature)
    {
        if (Ms5611_ElapsedGet(now_us, context->phase_started_us) <
            MS5611_CONVERSION_WAIT_US)
        { return Ms5611StepPending; }
        if (Ms5611_ElapsedGet(now_us, context->phase_started_us) >
            MS5611_CONVERSION_TIMEOUT_US)
        { return Ms5611_Fail(context, Ms5611StepConversionTimeout); }
        context->state = Ms5611StateReadTemperature;
    }
    else if (context->state == Ms5611StateReadTemperature)
    {
        if (context->port.read(context->port.bus,
                MS5611_ADC_READ_COMMAND, bytes, 3U) != Ms5611BusOk)
        { return Ms5611_Fail(context, Ms5611StepBusError); }
        context->raw_temperature = ((uint32_t)bytes[0] << 16U) |
            ((uint32_t)bytes[1] << 8U) | bytes[2];
        if (context->raw_temperature == 0U)
        { return Ms5611_Fail(context, Ms5611StepInvalidSample); }
        context->state = Ms5611StateStartPressure;
    }
    else if (context->state == Ms5611StateStartPressure)
    {
        if (context->port.write(context->port.bus,
                MS5611_START_PRESSURE_OSR4096) != Ms5611BusOk)
        { return Ms5611_Fail(context, Ms5611StepBusError); }
        context->phase_started_us = now_us;
        context->state = Ms5611StateWaitPressure;
    }
    else if (context->state == Ms5611StateWaitPressure)
    {
        if (Ms5611_ElapsedGet(now_us, context->phase_started_us) <
            MS5611_CONVERSION_WAIT_US)
        { return Ms5611StepPending; }
        if (Ms5611_ElapsedGet(now_us, context->phase_started_us) >
            MS5611_CONVERSION_TIMEOUT_US)
        { return Ms5611_Fail(context, Ms5611StepConversionTimeout); }
        context->state = Ms5611StateReadPressure;
    }
    else if (context->state == Ms5611StateReadPressure)
    {
        if (context->port.read(context->port.bus,
                MS5611_ADC_READ_COMMAND, bytes, 3U) != Ms5611BusOk)
        { return Ms5611_Fail(context, Ms5611StepBusError); }
        raw_pressure = ((uint32_t)bytes[0] << 16U) |
            ((uint32_t)bytes[1] << 8U) | bytes[2];
        result = Ms5611_Compensate(context->prom, raw_pressure,
            context->raw_temperature, &pressure, &temperature);
        if (result != Ms5611StepSampleReady)
        { return Ms5611_Fail(context, result); }
        (void)memset(&context->sample, 0, sizeof(context->sample));
        context->sample.sample_timestamp_us = now_us;
        context->sample.receive_timestamp_us = now_us;
        context->sample.sequence = ++context->sequence;
        context->sample.pressure_pa = pressure;
        context->sample.pressure_raw_pa = (int32_t)lroundf(pressure);
        context->sample.temperature_c = temperature;
        context->sample.supported_fields = SYSTEM_BARO_FIELD_PRESSURE |
            SYSTEM_BARO_FIELD_TEMPERATURE;
        context->sample.valid_fields = context->sample.supported_fields;
        context->sample.valid_mask = context->sample.valid_fields;
        context->state = Ms5611StateStartTemperature;
        return Ms5611StepSampleReady;
    }
    else { return Ms5611_Fail(context, Ms5611StepInvalidSample); }
    return Ms5611StepPending;
}
