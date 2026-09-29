#include "bmp390_core.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define BMP390_REGISTER_CHIP_ID 0x00U
#define BMP390_REGISTER_STATUS 0x03U
#define BMP390_REGISTER_PRESS_XLSB 0x04U
#define BMP390_REGISTER_PWR_CTRL 0x1BU
#define BMP390_REGISTER_OSR 0x1CU
#define BMP390_REGISTER_FILTER 0x1FU
#define BMP390_REGISTER_TRIM 0x31U
#define BMP390_CHIP_ID 0x60U
#define BMP390_STATUS_PRESS_TEMP_READY 0x60U
#define BMP390_OSR_PRESS_8_TEMP_1 0x03U
#define BMP390_FILTER_BYPASS 0x00U
#define BMP390_PRESS_TEMP_FORCED 0x13U
#define BMP390_CONVERSION_MIN_US 22000ULL
#define BMP390_CONVERSION_TIMEOUT_US 40000ULL
#define BMP390_CYCLE_PERIOD_US 50000ULL

static uint16_t Bmp390_WordGet(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
}

static float Bmp390_SignedByteGet(uint8_t value)
{
    return (float)(value < 128U ? (int32_t)value : (int32_t)value - 256);
}

static float Bmp390_SignedWordGet(const uint8_t *bytes)
{
    uint16_t value = Bmp390_WordGet(bytes);
    return (float)(value < 32768U ? (int32_t)value :
        (int32_t)value - 65536);
}

Bmp390StepResult Bmp390_Compensate(const Bmp390Trim *trim,
    uint32_t raw_pressure, uint32_t raw_temperature,
    float *pressure_pa, float *temperature_c)
{
    const uint8_t *b;
    float t1;
    float t2;
    float t3;
    float p1;
    float p2;
    float p3;
    float p4;
    float p5;
    float p6;
    float p7;
    float p8;
    float p9;
    float p10;
    float p11;
    float delta;
    float t_lin;
    float t_sq;
    float pressure_raw;
    float pressure;
    if ((trim == NULL) || (pressure_pa == NULL) ||
        (temperature_c == NULL))
    { return Bmp390StepInvalidSample; }
    b = trim->bytes;
    if ((Bmp390_WordGet(&b[0]) == 0U) ||
        (Bmp390_WordGet(&b[2]) == 0U) ||
        (Bmp390_WordGet(&b[11]) == 0U))
    { return Bmp390StepInvalidTrim; }
    if ((raw_pressure == 0U) || (raw_temperature == 0U) ||
        (raw_pressure > 0xFFFFFFU) || (raw_temperature > 0xFFFFFFU))
    { return Bmp390StepInvalidSample; }
    t1 = (float)Bmp390_WordGet(&b[0]) * 256.0F;
    t2 = (float)Bmp390_WordGet(&b[2]) / 1073741824.0F;
    t3 = Bmp390_SignedByteGet(b[4]) / 281474976710656.0F;
    p1 = (Bmp390_SignedWordGet(&b[5]) - 16384.0F) / 1048576.0F;
    p2 = (Bmp390_SignedWordGet(&b[7]) - 16384.0F) / 536870912.0F;
    p3 = Bmp390_SignedByteGet(b[9]) / 4294967296.0F;
    p4 = Bmp390_SignedByteGet(b[10]) / 137438953472.0F;
    p5 = (float)Bmp390_WordGet(&b[11]) * 8.0F;
    p6 = (float)Bmp390_WordGet(&b[13]) / 64.0F;
    p7 = Bmp390_SignedByteGet(b[15]) / 256.0F;
    p8 = Bmp390_SignedByteGet(b[16]) / 32768.0F;
    p9 = Bmp390_SignedWordGet(&b[17]) / 281474976710656.0F;
    p10 = Bmp390_SignedByteGet(b[19]) / 281474976710656.0F;
    p11 = Bmp390_SignedByteGet(b[20]) / 36893488147419103232.0F;
    delta = (float)raw_temperature - t1;
    t_lin = delta * t2 + delta * delta * t3;
    t_sq = t_lin * t_lin;
    pressure_raw = (float)raw_pressure;
    pressure = p5 + p6 * t_lin + p7 * t_sq + p8 * t_sq * t_lin;
    pressure += pressure_raw *
        (p1 + p2 * t_lin + p3 * t_sq + p4 * t_sq * t_lin);
    pressure += pressure_raw * pressure_raw * (p9 + p10 * t_lin);
    pressure += pressure_raw * pressure_raw * pressure_raw * p11;
    if ((!isfinite(pressure)) || (!isfinite(t_lin)) ||
        (pressure < 30000.0F) || (pressure > 120000.0F) ||
        (t_lin < -40.0F) || (t_lin > 85.0F))
    { return Bmp390StepInvalidSample; }
    *pressure_pa = pressure;
    *temperature_c = t_lin;
    return Bmp390StepSampleReady;
}

void Bmp390_Init(Bmp390Context *context, const Bmp390Port *port)
{
    if (context == NULL) { return; }
    (void)memset(context, 0, sizeof(*context));
    if ((port == NULL) || (port->read == NULL) || (port->write == NULL))
    { context->state = Bmp390StateFailed; return; }
    context->port = *port;
    context->state = Bmp390StateProbe;
}

static Bmp390StepResult Bmp390_Fail(Bmp390Context *context,
    Bmp390StepResult result)
{
    context->error_count++;
    context->state = Bmp390StateFailed;
    return result;
}

Bmp390StepResult Bmp390_Step(Bmp390Context *context, uint64_t now_us)
{
    uint8_t bytes[21];
    uint32_t raw_pressure;
    uint32_t raw_temperature;
    float pressure;
    float temperature;
    uint64_t elapsed;
    Bmp390StepResult result;
    if (context == NULL) { return Bmp390StepBusError; }
    if (context->state == Bmp390StateFailed)
    { return Bmp390StepVerifyFailed; }
    if (context->state == Bmp390StateProbe)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_CHIP_ID,
                bytes, 1U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        if (bytes[0] != BMP390_CHIP_ID)
        { return Bmp390_Fail(context, Bmp390StepNotPresent); }
        context->state = Bmp390StateReadTrim;
    }
    else if (context->state == Bmp390StateReadTrim)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_TRIM,
                bytes, 21U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        (void)memcpy(context->trim.bytes, bytes, 21U);
        if ((Bmp390_WordGet(&bytes[0]) == 0U) ||
            (Bmp390_WordGet(&bytes[2]) == 0U) ||
            (Bmp390_WordGet(&bytes[11]) == 0U))
        { return Bmp390_Fail(context, Bmp390StepInvalidTrim); }
        context->state = Bmp390StateReadOsr;
    }
    else if (context->state == Bmp390StateReadOsr)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_OSR,
                bytes, 1U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        context->state = bytes[0] == BMP390_OSR_PRESS_8_TEMP_1 ?
            Bmp390StateVerifyOsr : Bmp390StateApplyOsr;
    }
    else if (context->state == Bmp390StateApplyOsr)
    {
        if (context->port.write(context->port.bus, BMP390_REGISTER_OSR,
                BMP390_OSR_PRESS_8_TEMP_1) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        context->state = Bmp390StateVerifyOsr;
    }
    else if (context->state == Bmp390StateVerifyOsr)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_OSR,
                bytes, 1U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        if (bytes[0] != BMP390_OSR_PRESS_8_TEMP_1)
        { return Bmp390_Fail(context, Bmp390StepVerifyFailed); }
        context->state = Bmp390StateReadFilter;
    }
    else if (context->state == Bmp390StateReadFilter)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_FILTER,
                bytes, 1U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        context->state = bytes[0] == BMP390_FILTER_BYPASS ?
            Bmp390StateVerifyFilter : Bmp390StateApplyFilter;
    }
    else if (context->state == Bmp390StateApplyFilter)
    {
        if (context->port.write(context->port.bus, BMP390_REGISTER_FILTER,
                BMP390_FILTER_BYPASS) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        context->state = Bmp390StateVerifyFilter;
    }
    else if (context->state == Bmp390StateVerifyFilter)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_FILTER,
                bytes, 1U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        if (bytes[0] != BMP390_FILTER_BYPASS)
        { return Bmp390_Fail(context, Bmp390StepVerifyFailed); }
        context->state = Bmp390StateStartConversion;
    }
    else if (context->state == Bmp390StateStartConversion)
    {
        elapsed = now_us >= context->cycle_started_us ?
            now_us - context->cycle_started_us : 0ULL;
        if ((context->sequence != 0U) &&
            (elapsed < BMP390_CYCLE_PERIOD_US))
        { return Bmp390StepPending; }
        if (context->port.write(context->port.bus, BMP390_REGISTER_PWR_CTRL,
                BMP390_PRESS_TEMP_FORCED) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        context->cycle_started_us = now_us;
        context->conversion_started_us = now_us;
        context->state = Bmp390StateWaitConversion;
    }
    else if (context->state == Bmp390StateWaitConversion)
    {
        elapsed = now_us >= context->conversion_started_us ?
            now_us - context->conversion_started_us : 0ULL;
        if (elapsed < BMP390_CONVERSION_MIN_US)
        { return Bmp390StepPending; }
        if (elapsed > BMP390_CONVERSION_TIMEOUT_US)
        { return Bmp390_Fail(context, Bmp390StepConversionTimeout); }
        if (context->port.read(context->port.bus, BMP390_REGISTER_STATUS,
                bytes, 1U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        if ((bytes[0] & BMP390_STATUS_PRESS_TEMP_READY) ==
            BMP390_STATUS_PRESS_TEMP_READY)
        { context->state = Bmp390StateReadSample; }
    }
    else if (context->state == Bmp390StateReadSample)
    {
        if (context->port.read(context->port.bus, BMP390_REGISTER_PRESS_XLSB,
                bytes, 6U) != Bmp390BusOk)
        { return Bmp390_Fail(context, Bmp390StepBusError); }
        raw_pressure = (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8U) |
            ((uint32_t)bytes[2] << 16U);
        raw_temperature = (uint32_t)bytes[3] | ((uint32_t)bytes[4] << 8U) |
            ((uint32_t)bytes[5] << 16U);
        result = Bmp390_Compensate(&context->trim, raw_pressure,
            raw_temperature, &pressure, &temperature);
        if (result != Bmp390StepSampleReady)
        { return Bmp390_Fail(context, result); }
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
        context->state = Bmp390StateStartConversion;
        return Bmp390StepSampleReady;
    }
    else { return Bmp390_Fail(context, Bmp390StepVerifyFailed); }
    return Bmp390StepPending;
}
