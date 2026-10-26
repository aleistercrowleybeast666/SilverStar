#include "mmc5983ma_core.h"

#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define MMC5983MA_REGISTER_OUTPUT 0x00U
#define MMC5983MA_REGISTER_TEMPERATURE 0x07U
#define MMC5983MA_REGISTER_STATUS 0x08U
#define MMC5983MA_REGISTER_CONTROL_0 0x09U
#define MMC5983MA_REGISTER_ID 0x2FU
#define MMC5983MA_ID 0x30U
#define MMC5983MA_MAG_DONE 0x01U
#define MMC5983MA_TEMP_DONE 0x02U
#define MMC5983MA_COMMAND_MAG 0x01U
#define MMC5983MA_COMMAND_TEMP 0x02U
#define MMC5983MA_COMMAND_SET 0x08U
#define MMC5983MA_CONFIG_COUNT 2U
#define MMC5983MA_MEASUREMENT_TIMEOUT_US 30000ULL
#define MMC5983MA_PERIOD_US 50000ULL

static const uint8_t s_config_registers[MMC5983MA_CONFIG_COUNT] = {
    0x0AU, /* BW=00, all axes enabled, 8 ms conversion */
    0x0BU  /* continuous mode disabled; explicit 20 Hz one-shot */
};

static Mmc5983maStepResult Mmc5983ma_Fail(Mmc5983maContext *context,
    Mmc5983maStepResult result)
{
    context->error_count++;
    context->state = Mmc5983maStateFailed;
    return result;
}

static Mmc5983maStepResult Mmc5983ma_Publish(Mmc5983maContext *context,
    uint64_t now_us)
{
    context->sample.sequence = ++context->sequence;
    context->last_sample_us = now_us;
    context->state = Mmc5983maStateWaitPeriod;
    return Mmc5983maStepSampleReady;
}

void Mmc5983ma_Init(Mmc5983maContext *context, const Mmc5983maPort *port)
{
    if (context == NULL) { return; }
    (void)memset(context, 0, sizeof(*context));
    if ((port == NULL) || (port->bus == NULL))
    { context->state = Mmc5983maStateFailed; return; }
    context->port = *port;
    context->state = Mmc5983maStateProbe;
}

static Mmc5983maStepResult Mmc5983ma_Probe(Mmc5983maContext *context)
{
    uint8_t bytes[1];
    if (Mmc5983maBus_Read(context->port.bus, MMC5983MA_REGISTER_ID,
            bytes, 1U) != Mmc5983maBusOk)
    { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
    if (bytes[0] != MMC5983MA_ID)
    { return Mmc5983ma_Fail(context, Mmc5983maStepNotPresent); }
    context->state = Mmc5983maStateReadConfig;
    return Mmc5983maStepPending;
}

static Mmc5983maStepResult Mmc5983ma_ConfigureStep(Mmc5983maContext *context)
{
    uint8_t bytes[1];
    SILVERSTAR_ASSERT(context->config_index <= MMC5983MA_CONFIG_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (context->state != Mmc5983maStateReadConfig)
    {
        SILVERSTAR_ASSERT(context->config_index < MMC5983MA_CONFIG_COUNT,
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    }
    if (context->state == Mmc5983maStateReadConfig)
    {
        if (context->config_index >= MMC5983MA_CONFIG_COUNT)
        { context->state = Mmc5983maStateSet; return Mmc5983maStepPending; }
        if (Mmc5983maBus_Read(context->port.bus,
                s_config_registers[context->config_index],
                bytes, 1U) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        if (bytes[0] == 0U) { context->config_index++; }
        else { context->state = Mmc5983maStateApplyConfig; }
    }
    else if (context->state == Mmc5983maStateApplyConfig)
    {
        if (Mmc5983maBus_Write(context->port.bus,
                s_config_registers[context->config_index],
                0U) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        context->state = Mmc5983maStateVerifyConfig;
    }
    else if (context->state == Mmc5983maStateVerifyConfig)
    {
        if (Mmc5983maBus_Read(context->port.bus,
                s_config_registers[context->config_index],
                bytes, 1U) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        if (bytes[0] != 0U)
        { return Mmc5983ma_Fail(context, Mmc5983maStepVerifyFailed); }
        context->config_index++;
        context->state = Mmc5983maStateReadConfig;
    }
    return Mmc5983maStepPending;
}

static Mmc5983maStepResult Mmc5983ma_MagneticStart(Mmc5983maContext *context, uint64_t now_us)
{
    if (context->state == Mmc5983maStateSet)
    {
        if (Mmc5983maBus_Write(context->port.bus,
                MMC5983MA_REGISTER_CONTROL_0,
                MMC5983MA_COMMAND_SET) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        context->state = Mmc5983maStateTriggerMag;
    }
    else if (context->state == Mmc5983maStateTriggerMag)
    {
        if (Mmc5983maBus_Write(context->port.bus,
                MMC5983MA_REGISTER_CONTROL_0,
                MMC5983MA_COMMAND_MAG) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        context->operation_started_us = now_us;
        context->state = Mmc5983maStatePollMag;
    }
    return Mmc5983maStepPending;
}

static Mmc5983maStepResult Mmc5983ma_MagneticPoll(Mmc5983maContext *context, uint64_t now_us)
{
    uint8_t bytes[1];
    if ((now_us < context->operation_started_us) ||
        ((now_us - context->operation_started_us) >
            MMC5983MA_MEASUREMENT_TIMEOUT_US))
    { return Mmc5983ma_Fail(context, Mmc5983maStepMeasurementTimeout); }
    if (Mmc5983maBus_Read(context->port.bus,
            MMC5983MA_REGISTER_STATUS, bytes, 1U) != Mmc5983maBusOk)
    { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
    if ((bytes[0] & MMC5983MA_MAG_DONE) != 0U)
    { context->state = Mmc5983maStateReadMag; }
    return Mmc5983maStepPending;
}

static Mmc5983maStepResult Mmc5983ma_MagneticRead(Mmc5983maContext *context, uint64_t now_us)
{
    uint8_t bytes[7];
    uint8_t index;
    uint32_t unsigned_raw;
    int32_t centered_raw;
    if (Mmc5983maBus_Read(context->port.bus, MMC5983MA_REGISTER_OUTPUT,
            bytes, 7U) != Mmc5983maBusOk)
    { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
    (void)memset(&context->sample, 0, sizeof(context->sample));
    context->sample.sample_timestamp_us = now_us;
    context->sample.receive_timestamp_us = now_us;
    for (index = 0U; index < 3U; index++)
    {
        unsigned_raw = ((uint32_t)bytes[index * 2U] << 10U) |
            ((uint32_t)bytes[index * 2U + 1U] << 2U) |
            (((uint32_t)bytes[6] >> (6U - index * 2U)) & 0x03U);
        centered_raw = (int32_t)unsigned_raw - 131072;
        context->sample.raw[index] = centered_raw;
        context->sample.magnetic_field_b_uT[index] =
            (float)centered_raw * (100.0F / 16384.0F);
    }
    context->sample.valid_mask = MMC5983MA_SAMPLE_VALID_RAW |
        MMC5983MA_SAMPLE_VALID_PHYSICAL_UNIT;
    context->sample.calibration_valid = 0U;
    context->state = Mmc5983maStateTriggerTemp;
    return Mmc5983maStepPending;
}

static Mmc5983maStepResult Mmc5983ma_TemperatureStep(Mmc5983maContext *context, uint64_t now_us)
{
    uint8_t bytes[1];
    if (context->state == Mmc5983maStateTriggerTemp)
    {
        if (Mmc5983maBus_Write(context->port.bus,
                MMC5983MA_REGISTER_CONTROL_0,
                MMC5983MA_COMMAND_TEMP) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        context->operation_started_us = now_us;
        context->state = Mmc5983maStatePollTemp;
    }
    else if (context->state == Mmc5983maStatePollTemp)
    {
        if ((now_us < context->operation_started_us) ||
            ((now_us - context->operation_started_us) >
                MMC5983MA_MEASUREMENT_TIMEOUT_US))
        { return Mmc5983ma_Publish(context, now_us); }
        if (Mmc5983maBus_Read(context->port.bus,
                MMC5983MA_REGISTER_STATUS, bytes, 1U) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        if ((bytes[0] & MMC5983MA_TEMP_DONE) != 0U)
        { context->state = Mmc5983maStateReadTemp; }
    }
    else if (context->state == Mmc5983maStateReadTemp)
    {
        if (Mmc5983maBus_Read(context->port.bus,
                MMC5983MA_REGISTER_TEMPERATURE,
                bytes, 1U) != Mmc5983maBusOk)
        { return Mmc5983ma_Fail(context, Mmc5983maStepBusError); }
        context->sample.temperature_c = -75.0F + (float)bytes[0] * 0.8F;
        context->sample.valid_mask |= MMC5983MA_SAMPLE_VALID_TEMPERATURE;
        return Mmc5983ma_Publish(context, now_us);
    }
    return Mmc5983maStepPending;
}

static Mmc5983maStepResult Mmc5983ma_PeriodWait(Mmc5983maContext *context, uint64_t now_us)
{
    if ((now_us >= context->last_sample_us) &&
        ((now_us - context->last_sample_us) >= MMC5983MA_PERIOD_US))
    { context->state = Mmc5983maStateSet; }
    return Mmc5983maStepPending;
}

Mmc5983maStepResult Mmc5983ma_Step(Mmc5983maContext *context, uint64_t now_us)
{
    if (context == NULL) { return Mmc5983maStepBusError; }
    SILVERSTAR_ASSERT((uint32_t)context->state <= (uint32_t)Mmc5983maStateFailed,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (context->state == Mmc5983maStateFailed) { return Mmc5983maStepVerifyFailed; }
    SILVERSTAR_ASSERT(context->port.bus != NULL,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    switch (context->state)
    {
    case Mmc5983maStateProbe: return Mmc5983ma_Probe(context);
    case Mmc5983maStateReadConfig:
    case Mmc5983maStateApplyConfig:
    case Mmc5983maStateVerifyConfig: return Mmc5983ma_ConfigureStep(context);
    case Mmc5983maStateSet:
    case Mmc5983maStateTriggerMag: return Mmc5983ma_MagneticStart(context, now_us);
    case Mmc5983maStatePollMag: return Mmc5983ma_MagneticPoll(context, now_us);
    case Mmc5983maStateReadMag: return Mmc5983ma_MagneticRead(context, now_us);
    case Mmc5983maStateTriggerTemp:
    case Mmc5983maStatePollTemp:
    case Mmc5983maStateReadTemp: return Mmc5983ma_TemperatureStep(context, now_us);
    case Mmc5983maStateWaitPeriod: return Mmc5983ma_PeriodWait(context, now_us);
    case Mmc5983maStateFailed: return Mmc5983maStepVerifyFailed;
    default: return Mmc5983ma_Fail(context, Mmc5983maStepVerifyFailed);
    }
}
