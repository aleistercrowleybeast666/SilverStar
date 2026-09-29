#include "mmc5983ma_core.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct
{
    uint8_t registers[64];
    uint32_t operations;
    uint32_t config_writes;
    uint8_t ignore_writes;
    uint8_t stall_mag;
    uint8_t stall_temp;
} TestMmc5983maBus;

static void TestMmc5983ma_RawSet(uint8_t *registers, uint32_t index,
    uint32_t raw)
{
    registers[index * 2U] = (uint8_t)(raw >> 10U);
    registers[index * 2U + 1U] = (uint8_t)(raw >> 2U);
    registers[6] |= (uint8_t)((raw & 3U) << (6U - index * 2U));
}

static void TestMmc5983ma_Seed(TestMmc5983maBus *bus)
{
    (void)memset(bus, 0, sizeof(*bus));
    bus->registers[0x2FU] = 0x30U;
    bus->registers[0x0AU] = 0x01U;
    bus->registers[0x07U] = 125U;
    TestMmc5983ma_RawSet(bus->registers, 0U, 147457U);
    TestMmc5983ma_RawSet(bus->registers, 1U, 122880U);
    TestMmc5983ma_RawSet(bus->registers, 2U, 131072U);
}

static Mmc5983maBusResult TestMmc5983ma_Read(void *owner,
    uint8_t address, uint8_t *bytes, uint8_t length)
{
    TestMmc5983maBus *bus = (TestMmc5983maBus *)owner;
    if ((bus == NULL) || (bytes == NULL) ||
        ((uint16_t)address + length > 64U))
    { return Mmc5983maBusError; }
    bus->operations++;
    (void)memcpy(bytes, &bus->registers[address], length);
    return Mmc5983maBusOk;
}

static Mmc5983maBusResult TestMmc5983ma_Write(void *owner,
    uint8_t address, uint8_t value)
{
    TestMmc5983maBus *bus = (TestMmc5983maBus *)owner;
    if (bus == NULL) { return Mmc5983maBusError; }
    bus->operations++;
    if ((address == 0x0AU) || (address == 0x0BU))
    {
        bus->config_writes++;
        if (bus->ignore_writes == 0U) { bus->registers[address] = value; }
        return Mmc5983maBusOk;
    }
    if (address != 0x09U) { return Mmc5983maBusError; }
    if (value == 0x01U)
    {
        bus->registers[0x08U] &= (uint8_t)~0x01U;
        if (bus->stall_mag == 0U) { bus->registers[0x08U] |= 0x01U; }
    }
    else if (value == 0x02U)
    {
        bus->registers[0x08U] &= (uint8_t)~0x02U;
        if (bus->stall_temp == 0U) { bus->registers[0x08U] |= 0x02U; }
    }
    else if (value != 0x08U) { return Mmc5983maBusError; }
    return Mmc5983maBusOk;
}

static Mmc5983maPort TestMmc5983ma_PortGet(TestMmc5983maBus *bus)
{
    Mmc5983maPort port = { bus, TestMmc5983ma_Read,
        TestMmc5983ma_Write };
    return port;
}

static void TestMmc5983ma_FreshVector(void)
{
    TestMmc5983maBus bus;
    Mmc5983maContext context;
    Mmc5983maPort port;
    Mmc5983maStepResult result = Mmc5983maStepPending;
    uint32_t tick;
    uint32_t before;
    TestMmc5983ma_Seed(&bus);
    port = TestMmc5983ma_PortGet(&bus);
    Mmc5983ma_Init(&context, &port);
    for (tick = 0U; tick < 40U; tick++)
    {
        before = bus.operations;
        result = Mmc5983ma_Step(&context, (uint64_t)tick * 1000ULL);
        assert(bus.operations - before <= 1U);
        if (result == Mmc5983maStepSampleReady) { break; }
        assert(result == Mmc5983maStepPending);
    }
    assert(result == Mmc5983maStepSampleReady);
    assert(bus.config_writes == 1U);
    assert(context.sample.raw[0] == 16385);
    assert(context.sample.raw[1] == -8192);
    assert(context.sample.raw[2] == 0);
    assert(fabsf(context.sample.magnetic_field_b_uT[0] -
        100.0061F) < 0.02F);
    assert(fabsf(context.sample.magnetic_field_b_uT[1] + 50.0F) < 0.02F);
    assert(fabsf(context.sample.temperature_c - 25.0F) < 0.01F);
    assert((context.sample.valid_mask & SYSTEM_MAG_VALID_TEMPERATURE) != 0U);
    assert(context.sample.calibration_valid == 0U);
    assert(Mmc5983ma_Step(&context, (uint64_t)(tick + 1U) * 1000ULL) ==
        Mmc5983maStepPending);
    assert(context.sample.sequence == 1U);
}

static void TestMmc5983ma_IdentityAndReadback(void)
{
    TestMmc5983maBus bus;
    Mmc5983maContext context;
    Mmc5983maPort port;
    uint32_t tick;
    TestMmc5983ma_Seed(&bus);
    port = TestMmc5983ma_PortGet(&bus);
    bus.registers[0x2FU] = 0U;
    Mmc5983ma_Init(&context, &port);
    assert(Mmc5983ma_Step(&context, 0U) == Mmc5983maStepNotPresent);
    TestMmc5983ma_Seed(&bus);
    bus.ignore_writes = 1U;
    Mmc5983ma_Init(&context, &port);
    for (tick = 0U; tick < 8U; tick++)
    {
        if (Mmc5983ma_Step(&context, (uint64_t)tick * 1000ULL) ==
            Mmc5983maStepVerifyFailed)
        { break; }
    }
    assert(context.state == Mmc5983maStateFailed);
}

static void TestMmc5983ma_MeasurementTimeouts(void)
{
    TestMmc5983maBus bus;
    Mmc5983maContext context;
    Mmc5983maPort port;
    Mmc5983maStepResult result = Mmc5983maStepPending;
    uint32_t tick;
    TestMmc5983ma_Seed(&bus);
    port = TestMmc5983ma_PortGet(&bus);
    bus.stall_mag = 1U;
    Mmc5983ma_Init(&context, &port);
    for (tick = 0U; tick < 60U; tick++)
    {
        result = Mmc5983ma_Step(&context, (uint64_t)tick * 1000ULL);
        if (result != Mmc5983maStepPending) { break; }
    }
    assert(result == Mmc5983maStepMeasurementTimeout);
    assert(context.sequence == 0U);
    TestMmc5983ma_Seed(&bus);
    bus.stall_temp = 1U;
    Mmc5983ma_Init(&context, &port);
    for (tick = 0U; tick < 70U; tick++)
    {
        result = Mmc5983ma_Step(&context, (uint64_t)tick * 1000ULL);
        if (result != Mmc5983maStepPending) { break; }
    }
    assert(result == Mmc5983maStepSampleReady);
    assert(context.sample.valid_mask == (SYSTEM_MAG_VALID_RAW |
        SYSTEM_MAG_VALID_PHYSICAL_UNIT));
}

int main(void)
{
    TestMmc5983ma_FreshVector();
    TestMmc5983ma_IdentityAndReadback();
    TestMmc5983ma_MeasurementTimeouts();
    return 0;
}
