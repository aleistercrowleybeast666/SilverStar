#include "lis3mdl_core.h"

#include <stddef.h>
#include <string.h>

#define LIS3MDL_REGISTER_ID 0x0FU
#define LIS3MDL_REGISTER_CONTROL_FIRST 0x20U
#define LIS3MDL_REGISTER_STATUS 0x27U
#define LIS3MDL_REGISTER_OUTPUT_FIRST 0x28U
#define LIS3MDL_ID 0x3DU
#define LIS3MDL_NEW_XYZ 0x08U
#define LIS3MDL_CONTROL_COUNT 5U

static const uint8_t s_control_targets[LIS3MDL_CONTROL_COUNT] = {
    0xF4U, /* temperature, ultrahigh-performance XY, 20 Hz */
    0x00U, /* +/-4 gauss */
    0x00U, /* continuous-conversion, 4-wire SPI */
    0x0CU, /* ultrahigh-performance Z, little endian */
    0x40U  /* block data update */
};

static int32_t Lis3mdl_SignedWordGet(const uint8_t *bytes)
{
    uint16_t value = (uint16_t)((uint16_t)bytes[0] |
        ((uint16_t)bytes[1] << 8U));
    return value < 32768U ? (int32_t)value : (int32_t)value - 65536;
}

void Lis3mdl_Init(Lis3mdlContext *context, const Lis3mdlPort *port)
{
    if (context == NULL) { return; }
    (void)memset(context, 0, sizeof(*context));
    if ((port == NULL) || (port->read == NULL) || (port->write == NULL))
    { context->state = Lis3mdlStateFailed; return; }
    context->port = *port;
    context->state = Lis3mdlStateProbe;
}

static Lis3mdlStepResult Lis3mdl_Fail(Lis3mdlContext *context,
    Lis3mdlStepResult result)
{
    context->error_count++;
    context->state = Lis3mdlStateFailed;
    return result;
}

Lis3mdlStepResult Lis3mdl_Step(Lis3mdlContext *context, uint64_t now_us)
{
    uint8_t bytes[8];
    uint8_t index;
    uint8_t register_address;
    int32_t raw;
    if (context == NULL) { return Lis3mdlStepBusError; }
    if (context->state == Lis3mdlStateFailed)
    { return Lis3mdlStepVerifyFailed; }
    if (context->state == Lis3mdlStateProbe)
    {
        if (context->port.read(context->port.bus, LIS3MDL_REGISTER_ID,
                bytes, 1U) != Lis3mdlBusOk)
        { return Lis3mdl_Fail(context, Lis3mdlStepBusError); }
        if (bytes[0] != LIS3MDL_ID)
        { return Lis3mdl_Fail(context, Lis3mdlStepNotPresent); }
        context->state = Lis3mdlStateReadConfig;
    }
    else if (context->state == Lis3mdlStateReadConfig)
    {
        if (context->config_index >= LIS3MDL_CONTROL_COUNT)
        { context->state = Lis3mdlStatePollStatus; return Lis3mdlStepPending; }
        register_address = (uint8_t)(LIS3MDL_REGISTER_CONTROL_FIRST +
            context->config_index);
        if (context->port.read(context->port.bus, register_address,
                bytes, 1U) != Lis3mdlBusOk)
        { return Lis3mdl_Fail(context, Lis3mdlStepBusError); }
        if (bytes[0] == s_control_targets[context->config_index])
        { context->config_index++; }
        else { context->state = Lis3mdlStateApplyConfig; }
    }
    else if (context->state == Lis3mdlStateApplyConfig)
    {
        register_address = (uint8_t)(LIS3MDL_REGISTER_CONTROL_FIRST +
            context->config_index);
        if (context->port.write(context->port.bus, register_address,
                s_control_targets[context->config_index]) != Lis3mdlBusOk)
        { return Lis3mdl_Fail(context, Lis3mdlStepBusError); }
        context->state = Lis3mdlStateVerifyConfig;
    }
    else if (context->state == Lis3mdlStateVerifyConfig)
    {
        register_address = (uint8_t)(LIS3MDL_REGISTER_CONTROL_FIRST +
            context->config_index);
        if (context->port.read(context->port.bus, register_address,
                bytes, 1U) != Lis3mdlBusOk)
        { return Lis3mdl_Fail(context, Lis3mdlStepBusError); }
        if (bytes[0] != s_control_targets[context->config_index])
        { return Lis3mdl_Fail(context, Lis3mdlStepVerifyFailed); }
        context->config_index++;
        context->state = Lis3mdlStateReadConfig;
    }
    else if (context->state == Lis3mdlStatePollStatus)
    {
        if (context->port.read(context->port.bus, LIS3MDL_REGISTER_STATUS,
                bytes, 1U) != Lis3mdlBusOk)
        { return Lis3mdl_Fail(context, Lis3mdlStepBusError); }
        if ((bytes[0] & LIS3MDL_NEW_XYZ) != 0U)
        { context->state = Lis3mdlStateReadSample; }
    }
    else if (context->state == Lis3mdlStateReadSample)
    {
        if (context->port.read(context->port.bus,
                LIS3MDL_REGISTER_OUTPUT_FIRST, bytes, 8U) != Lis3mdlBusOk)
        { return Lis3mdl_Fail(context, Lis3mdlStepBusError); }
        (void)memset(&context->sample, 0, sizeof(context->sample));
        context->sample.sample_timestamp_us = now_us;
        context->sample.receive_timestamp_us = now_us;
        context->sample.sequence = ++context->sequence;
        for (index = 0U; index < 3U; index++)
        {
            raw = Lis3mdl_SignedWordGet(&bytes[index * 2U]);
            context->sample.raw[index] = raw;
            context->sample.magnetic_field_b_uT[index] =
                (float)raw * (100.0F / 6842.0F);
        }
        raw = Lis3mdl_SignedWordGet(&bytes[6]);
        context->sample.temperature_c = 25.0F + (float)raw / 8.0F;
        context->sample.valid_mask = SYSTEM_MAG_VALID_RAW |
            SYSTEM_MAG_VALID_PHYSICAL_UNIT | SYSTEM_MAG_VALID_TEMPERATURE;
        context->sample.calibration_valid = 0U;
        context->last_sample_us = now_us;
        context->state = Lis3mdlStatePollStatus;
        return Lis3mdlStepSampleReady;
    }
    else { return Lis3mdl_Fail(context, Lis3mdlStepVerifyFailed); }
    return Lis3mdlStepPending;
}
