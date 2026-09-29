#include "bmp390_core.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct
{
    uint8_t registers[256];
    uint32_t osr_writes;
    uint32_t filter_writes;
    uint32_t forced_writes;
} TestBmp390Bus;

static void TestBmp390_WordSet(uint8_t *bytes, uint16_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8U);
}

static void TestBmp390_RawSet(uint8_t *bytes, uint32_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8U);
    bytes[2] = (uint8_t)(value >> 16U);
}

static void TestBmp390_BusSeed(TestBmp390Bus *bus)
{
    uint8_t *trim;
    (void)memset(bus, 0, sizeof(*bus));
    bus->registers[0x00U] = 0x60U;
    bus->registers[0x1CU] = 0x02U;
    bus->registers[0x1FU] = 0x08U;
    trim = &bus->registers[0x31U];
    TestBmp390_WordSet(&trim[0], 20000U);
    TestBmp390_WordSet(&trim[2], 26844U);
    trim[4] = (uint8_t)-3;
    TestBmp390_WordSet(&trim[5], 32000U);
    TestBmp390_WordSet(&trim[7], 16800U);
    trim[9] = 2U;
    trim[10] = (uint8_t)-1;
    TestBmp390_WordSet(&trim[11], 8800U);
    TestBmp390_WordSet(&trim[13], 100U);
    trim[15] = 3U;
    trim[16] = (uint8_t)-2;
    TestBmp390_WordSet(&trim[17], 500U);
    trim[19] = (uint8_t)-1;
    trim[20] = 1U;
    TestBmp390_RawSet(&bus->registers[0x04U], 2000000U);
    TestBmp390_RawSet(&bus->registers[0x07U], 6120000U);
}

static Bmp390BusResult TestBmp390_Read(void *bus, uint8_t address,
    uint8_t *bytes, uint8_t length)
{
    TestBmp390Bus *mock = (TestBmp390Bus *)bus;
    if ((mock == NULL) || (bytes == NULL) ||
        ((uint16_t)address + length > 256U))
    { return Bmp390BusError; }
    (void)memcpy(bytes, &mock->registers[address], length);
    return Bmp390BusOk;
}

static Bmp390BusResult TestBmp390_Write(void *bus, uint8_t address,
    uint8_t value)
{
    TestBmp390Bus *mock = (TestBmp390Bus *)bus;
    if (mock == NULL) { return Bmp390BusError; }
    mock->registers[address] = value;
    if (address == 0x1CU) { mock->osr_writes++; }
    if (address == 0x1FU) { mock->filter_writes++; }
    if (address == 0x1BU)
    {
        mock->forced_writes++;
        mock->registers[0x03U] = 0x60U;
    }
    return Bmp390BusOk;
}

static void TestBmp390_CompensationAndReadback(void)
{
    TestBmp390Bus bus;
    Bmp390Context context;
    Bmp390Port port;
    Bmp390StepResult result = Bmp390StepPending;
    uint64_t now_us;
    TestBmp390_BusSeed(&bus);
    port.bus = &bus;
    port.read = TestBmp390_Read;
    port.write = TestBmp390_Write;
    Bmp390_Init(&context, &port);
    for (now_us = 0U; now_us < 100000U; now_us += 1000U)
    {
        result = Bmp390_Step(&context, now_us);
        if (result == Bmp390StepSampleReady) { break; }
        assert(result == Bmp390StepPending);
    }
    assert(result == Bmp390StepSampleReady);
    assert(bus.osr_writes == 1U && bus.filter_writes == 1U);
    assert(bus.forced_writes == 1U);
    assert(fabsf(context.sample.temperature_c - 24.9898F) < 0.03F);
    assert(fabsf(context.sample.pressure_pa - 100276.62F) < 3.0F);
    assert(context.sample.sequence == 1U);
    assert((context.sample.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) == 0U);
    TestBmp390_BusSeed(&bus);
    bus.registers[0x1CU] = 0x03U;
    bus.registers[0x1FU] = 0x00U;
    Bmp390_Init(&context, &port);
    for (now_us = 0U; now_us < 100000U; now_us += 1000U)
    {
        result = Bmp390_Step(&context, now_us);
        if (result == Bmp390StepSampleReady) { break; }
        assert(result == Bmp390StepPending);
    }
    assert(result == Bmp390StepSampleReady);
    assert(bus.osr_writes == 0U && bus.filter_writes == 0U);
}

static void TestBmp390_BadIdentityAndTimeout(void)
{
    TestBmp390Bus bus;
    Bmp390Context context;
    Bmp390Port port;
    uint64_t now_us;
    TestBmp390_BusSeed(&bus);
    port.bus = &bus;
    port.read = TestBmp390_Read;
    port.write = TestBmp390_Write;
    bus.registers[0x00U] = 0U;
    Bmp390_Init(&context, &port);
    assert(Bmp390_Step(&context, 0U) == Bmp390StepNotPresent);
    TestBmp390_BusSeed(&bus);
    Bmp390_Init(&context, &port);
    for (now_us = 0U; now_us < 30000U; now_us += 1000U)
    {
        (void)Bmp390_Step(&context, now_us);
        if (context.state == Bmp390StateWaitConversion) { break; }
    }
    assert(context.state == Bmp390StateWaitConversion);
    assert(Bmp390_Step(&context, now_us + 41000U) ==
        Bmp390StepConversionTimeout);
}

int main(void)
{
    TestBmp390_CompensationAndReadback();
    TestBmp390_BadIdentityAndTimeout();
    return 0;
}
