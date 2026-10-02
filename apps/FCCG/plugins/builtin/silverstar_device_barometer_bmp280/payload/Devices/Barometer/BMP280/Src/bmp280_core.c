#include "bmp280_core.h"
#include "silverstar_assert.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define BMP280_REGISTER_CHIP_ID 0xD0U
#define BMP280_REGISTER_TRIM 0x88U
#define BMP280_REGISTER_STATUS 0xF3U
#define BMP280_REGISTER_CTRL_MEAS 0xF4U
#define BMP280_REGISTER_CONFIG 0xF5U
#define BMP280_REGISTER_PRESS_MSB 0xF7U
#define BMP280_CHIP_ID 0x58U
#define BMP280_CONFIG_FILTER_4 0x08U
#define BMP280_CTRL_TEMP_2_PRESS_16_FORCED 0x55U
#define BMP280_CONVERSION_MIN_US 45000ULL
#define BMP280_CONVERSION_TIMEOUT_US 100000ULL

static uint16_t Bmp280_WordGet(const uint8_t *bytes)
{
    return (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
}

static void Bmp280_TrimParse(Bmp280Trim *trim, const uint8_t *bytes)
{
    trim->t1 = Bmp280_WordGet(&bytes[0]);
    trim->t2 = (int16_t)Bmp280_WordGet(&bytes[2]);
    trim->t3 = (int16_t)Bmp280_WordGet(&bytes[4]);
    trim->p1 = Bmp280_WordGet(&bytes[6]);
    trim->p2 = (int16_t)Bmp280_WordGet(&bytes[8]);
    trim->p3 = (int16_t)Bmp280_WordGet(&bytes[10]);
    trim->p4 = (int16_t)Bmp280_WordGet(&bytes[12]);
    trim->p5 = (int16_t)Bmp280_WordGet(&bytes[14]);
    trim->p6 = (int16_t)Bmp280_WordGet(&bytes[16]);
    trim->p7 = (int16_t)Bmp280_WordGet(&bytes[18]);
    trim->p8 = (int16_t)Bmp280_WordGet(&bytes[20]);
    trim->p9 = (int16_t)Bmp280_WordGet(&bytes[22]);
}

Bmp280StepResult Bmp280_Compensate(const Bmp280Trim *trim,
    uint32_t raw_pressure, uint32_t raw_temperature,
    float *pressure_pa, float *temperature_c)
{
    float var1;
    float var2;
    float t_fine;
    float pressure;
    if ((trim == NULL) || (pressure_pa == NULL) ||
        (temperature_c == NULL) || (trim->t1 == 0U) || (trim->p1 == 0U))
    { return Bmp280StepInvalidTrim; }
    if ((raw_pressure > 0xFFFFFU) || (raw_temperature > 0xFFFFFU))
    { return Bmp280StepInvalidSample; }
    var1 = ((float)raw_temperature / 16384.0F -
        (float)trim->t1 / 1024.0F) * (float)trim->t2;
    var2 = ((float)raw_temperature / 131072.0F -
        (float)trim->t1 / 8192.0F);
    var2 = var2 * var2 * (float)trim->t3;
    t_fine = var1 + var2;
    *temperature_c = t_fine / 5120.0F;
    var1 = t_fine / 2.0F - 64000.0F;
    var2 = var1 * var1 * (float)trim->p6 / 32768.0F;
    var2 += var1 * (float)trim->p5 * 2.0F;
    var2 = var2 / 4.0F + (float)trim->p4 * 65536.0F;
    var1 = ((float)trim->p3 * var1 * var1 / 524288.0F +
        (float)trim->p2 * var1) / 524288.0F;
    var1 = (1.0F + var1 / 32768.0F) * (float)trim->p1;
    if ((!isfinite(var1)) || (fabsf(var1) < 0.000001F))
    { return Bmp280StepInvalidTrim; }
    pressure = 1048576.0F - (float)raw_pressure;
    pressure = (pressure - var2 / 4096.0F) * 6250.0F / var1;
    var1 = (float)trim->p9 * pressure * pressure / 2147483648.0F;
    var2 = pressure * (float)trim->p8 / 32768.0F;
    pressure += (var1 + var2 + (float)trim->p7) / 16.0F;
    if ((!isfinite(pressure)) || (!isfinite(*temperature_c)) ||
        (pressure < 30000.0F) || (pressure > 110000.0F) ||
        (*temperature_c < -40.0F) || (*temperature_c > 85.0F))
    { return Bmp280StepInvalidSample; }
    *pressure_pa = pressure;
    return Bmp280StepSampleReady;
}

void Bmp280_Init(Bmp280Context *context, const Bmp280Port *port)
{
    if (context == NULL) { return; }
    (void)memset(context, 0, sizeof(*context));
    if ((port == NULL) || (port->bus == NULL))
    { context->state = Bmp280StateFailed; return; }
    context->port = *port;
    context->state = Bmp280StateProbe;
}

static Bmp280StepResult Bmp280_Fail(Bmp280Context *context,
    Bmp280StepResult result)
{
    context->error_count++;
    context->state = Bmp280StateFailed;
    return result;
}

static Bmp280StepResult Bmp280_ConfigureStep(Bmp280Context *context, uint64_t now_us)
{
    (void)now_us; /* This phase performs no conversion wait. */
    uint8_t bytes[24];
    if (context->state == Bmp280StateProbe)
    {
        if (Bmp280Bus_Read(context->port.bus, BMP280_REGISTER_CHIP_ID,
                bytes, 1U) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        if (bytes[0] != BMP280_CHIP_ID)
        { return Bmp280_Fail(context, Bmp280StepNotPresent); }
        context->state = Bmp280StateReadTrim;
    }
    else if (context->state == Bmp280StateReadTrim)
    {
        if (Bmp280Bus_Read(context->port.bus, BMP280_REGISTER_TRIM,
                bytes, 24U) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        Bmp280_TrimParse(&context->trim, bytes);
        if ((context->trim.t1 == 0U) || (context->trim.p1 == 0U))
        { return Bmp280_Fail(context, Bmp280StepInvalidTrim); }
        context->state = Bmp280StateReadConfig;
    }
    else if (context->state == Bmp280StateReadConfig)
    {
        if (Bmp280Bus_Read(context->port.bus, BMP280_REGISTER_CONFIG,
                bytes, 1U) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        context->state = bytes[0] == BMP280_CONFIG_FILTER_4 ?
            Bmp280StateVerifyConfig : Bmp280StateApplyConfig;
    }
    else if (context->state == Bmp280StateApplyConfig)
    {
        if (Bmp280Bus_Write(context->port.bus, BMP280_REGISTER_CONFIG,
                BMP280_CONFIG_FILTER_4) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        context->state = Bmp280StateVerifyConfig;
    }
    else if (context->state == Bmp280StateVerifyConfig)
    {
        if (Bmp280Bus_Read(context->port.bus, BMP280_REGISTER_CONFIG,
                bytes, 1U) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        if (bytes[0] != BMP280_CONFIG_FILTER_4)
        { return Bmp280_Fail(context, Bmp280StepVerifyFailed); }
        context->state = Bmp280StateStartConversion;
    }
    return Bmp280StepPending;
}

static Bmp280StepResult Bmp280_ConversionStep(Bmp280Context *context, uint64_t now_us)
{
    uint8_t bytes[1];
    if (context->state == Bmp280StateStartConversion)
    {
        if (Bmp280Bus_Write(context->port.bus, BMP280_REGISTER_CTRL_MEAS,
                BMP280_CTRL_TEMP_2_PRESS_16_FORCED) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        context->conversion_started_us = now_us;
        context->state = Bmp280StateWaitConversion;
    }
    else if (context->state == Bmp280StateWaitConversion)
    {
        uint64_t elapsed = now_us >= context->conversion_started_us ?
            now_us - context->conversion_started_us : 0ULL;
        if (elapsed < BMP280_CONVERSION_MIN_US) { return Bmp280StepPending; }
        if (elapsed > BMP280_CONVERSION_TIMEOUT_US)
        { return Bmp280_Fail(context, Bmp280StepConversionTimeout); }
        if (Bmp280Bus_Read(context->port.bus, BMP280_REGISTER_STATUS,
                bytes, 1U) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        if ((bytes[0] & 0x08U) == 0U)
        { context->state = Bmp280StateReadSample; }
    }
    return Bmp280StepPending;
}

static Bmp280StepResult Bmp280_SampleStep(Bmp280Context *context, uint64_t now_us)
{
    uint8_t bytes[6];
    uint32_t raw_pressure, raw_temperature;
    float pressure, temperature;
    Bmp280StepResult result;
    if (context->state == Bmp280StateReadSample)
    {
        if (Bmp280Bus_Read(context->port.bus, BMP280_REGISTER_PRESS_MSB,
                bytes, 6U) != Bmp280BusOk)
        { return Bmp280_Fail(context, Bmp280StepBusError); }
        raw_pressure = ((uint32_t)bytes[0] << 12U) |
            ((uint32_t)bytes[1] << 4U) | ((uint32_t)bytes[2] >> 4U);
        raw_temperature = ((uint32_t)bytes[3] << 12U) |
            ((uint32_t)bytes[4] << 4U) | ((uint32_t)bytes[5] >> 4U);
        result = Bmp280_Compensate(&context->trim, raw_pressure,
            raw_temperature, &pressure, &temperature);
        if (result != Bmp280StepSampleReady)
        { return Bmp280_Fail(context, result); }
        (void)memset(&context->sample, 0, sizeof(context->sample));
        context->sample.sample_timestamp_us = now_us;
        context->sample.receive_timestamp_us = now_us;
        context->sample.measurement_timestamp_trusted = 0U;
        context->sample.sequence = ++context->sequence;
        context->sample.pressure_pa = pressure;
        context->sample.pressure_raw_pa = (int32_t)lroundf(pressure);
        context->sample.temperature_c = temperature;
        context->sample.supported_fields = SYSTEM_BARO_FIELD_PRESSURE |
            SYSTEM_BARO_FIELD_TEMPERATURE;
        context->sample.valid_fields = context->sample.supported_fields;
        context->sample.valid_mask = context->sample.valid_fields;
        context->state = Bmp280StateStartConversion;
        return Bmp280StepSampleReady;
    }
    return Bmp280StepPending;
}

Bmp280StepResult Bmp280_Step(Bmp280Context *context, uint64_t now_us)
{
    if (context == NULL) { return Bmp280StepBusError; }
    SILVERSTAR_ASSERT((uint32_t)context->state <= (uint32_t)Bmp280StateFailed,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (context->state == Bmp280StateFailed) { return Bmp280StepVerifyFailed; }
    SILVERSTAR_ASSERT(context->port.bus != NULL,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (context->state == Bmp280StateProbe || context->state == Bmp280StateReadTrim || context->state == Bmp280StateReadConfig || context->state == Bmp280StateApplyConfig || context->state == Bmp280StateVerifyConfig)
    { return Bmp280_ConfigureStep(context, now_us); }
    if (context->state == Bmp280StateStartConversion || context->state == Bmp280StateWaitConversion)
    { return Bmp280_ConversionStep(context, now_us); }
    if (context->state == Bmp280StateReadSample)
    { return Bmp280_SampleStep(context, now_us); }
    return Bmp280_Fail(context, Bmp280StepVerifyFailed);
}
