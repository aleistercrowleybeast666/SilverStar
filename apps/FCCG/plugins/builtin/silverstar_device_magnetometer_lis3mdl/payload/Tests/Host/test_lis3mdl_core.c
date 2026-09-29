#include "lis3mdl_core.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct
{
    uint8_t registers[64];
    uint32_t config_writes;
    uint8_t ignore_writes;
} TestLis3mdlBus;

static void TestLis3mdl_RawSet(uint8_t *bytes, int32_t raw)
{
    uint16_t value = (uint16_t)raw;
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8U);
}

static void TestLis3mdl_Seed(TestLis3mdlBus *bus)
{
    (void)memset(bus, 0, sizeof(*bus));
    bus->registers[0x0FU] = 0x3DU;
    bus->registers[0x20U] = 0x10U;
    bus->registers[0x22U] = 0x03U;
    bus->registers[0x27U] = 0x08U;
    TestLis3mdl_RawSet(&bus->registers[0x28U], 6842);
    TestLis3mdl_RawSet(&bus->registers[0x2AU], -3421);
    TestLis3mdl_RawSet(&bus->registers[0x2CU], 0);
    TestLis3mdl_RawSet(&bus->registers[0x2EU], 16);
}

static Lis3mdlBusResult TestLis3mdl_Read(void *owner, uint8_t address,
    uint8_t *bytes, uint8_t length)
{
    TestLis3mdlBus *bus = (TestLis3mdlBus *)owner;
    if ((bus == NULL) || (bytes == NULL) ||
        ((uint16_t)address + length > 64U))
    { return Lis3mdlBusError; }
    (void)memcpy(bytes, &bus->registers[address], length);
    if ((address == 0x28U) && (length == 8U))
    { bus->registers[0x27U] = 0U; }
    return Lis3mdlBusOk;
}

static Lis3mdlBusResult TestLis3mdl_Write(void *owner, uint8_t address,
    uint8_t value)
{
    TestLis3mdlBus *bus = (TestLis3mdlBus *)owner;
    if ((bus == NULL) || (address < 0x20U) || (address > 0x24U))
    { return Lis3mdlBusError; }
    bus->config_writes++;
    if (bus->ignore_writes == 0U) { bus->registers[address] = value; }
    return Lis3mdlBusOk;
}

static void TestLis3mdl_FreshVector(void)
{
    TestLis3mdlBus bus;
    Lis3mdlContext context;
    Lis3mdlPort port;
    Lis3mdlStepResult result = Lis3mdlStepPending;
    uint32_t tick;
    TestLis3mdl_Seed(&bus);
    port.bus = &bus;
    port.read = TestLis3mdl_Read;
    port.write = TestLis3mdl_Write;
    Lis3mdl_Init(&context, &port);
    for (tick = 0U; tick < 40U; tick++)
    {
        result = Lis3mdl_Step(&context, (uint64_t)tick * 1000ULL);
        if (result == Lis3mdlStepSampleReady) { break; }
        assert(result == Lis3mdlStepPending);
    }
    assert(result == Lis3mdlStepSampleReady);
    assert(bus.config_writes == 4U);
    assert(context.sample.raw[0] == 6842);
    assert(context.sample.raw[1] == -3421);
    assert(fabsf(context.sample.magnetic_field_b_uT[0] - 100.0F) < 0.02F);
    assert(fabsf(context.sample.magnetic_field_b_uT[1] + 50.0F) < 0.02F);
    assert(fabsf(context.sample.temperature_c - 27.0F) < 0.01F);
    assert(context.sample.calibration_valid == 0U);
    assert(Lis3mdl_Step(&context, 50000ULL) == Lis3mdlStepPending);
    assert(Lis3mdl_Step(&context, 51000ULL) == Lis3mdlStepPending);
    assert(context.sample.sequence == 1U);
}

static void TestLis3mdl_IdentityAndReadback(void)
{
    TestLis3mdlBus bus;
    Lis3mdlContext context;
    Lis3mdlPort port;
    uint32_t tick;
    TestLis3mdl_Seed(&bus);
    port.bus = &bus;
    port.read = TestLis3mdl_Read;
    port.write = TestLis3mdl_Write;
    bus.registers[0x0FU] = 0U;
    Lis3mdl_Init(&context, &port);
    assert(Lis3mdl_Step(&context, 0U) == Lis3mdlStepNotPresent);
    TestLis3mdl_Seed(&bus);
    bus.ignore_writes = 1U;
    Lis3mdl_Init(&context, &port);
    for (tick = 0U; tick < 8U; tick++)
    {
        if (Lis3mdl_Step(&context, (uint64_t)tick * 1000ULL) ==
            Lis3mdlStepVerifyFailed)
        { break; }
    }
    assert(context.state == Lis3mdlStateFailed);
}

int main(void)
{
    TestLis3mdl_FreshVector();
    TestLis3mdl_IdentityAndReadback();
    return 0;
}
