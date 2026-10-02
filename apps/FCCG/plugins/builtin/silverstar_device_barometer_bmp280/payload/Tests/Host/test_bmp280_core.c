#include "bmp280_core.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

typedef struct
{
    uint64_t io_elapsed_us;
    uint8_t registers[256];
    uint32_t config_writes;
    uint32_t forced_writes;
} TestBmp280Bus;

Bmp280BusResult Bmp280Bus_Read(void *bus, uint8_t address,
    uint8_t *bytes, uint8_t length)
{
    TestBmp280Bus *mock = bus;
    if ((mock == NULL) || (bytes == NULL) ||
        ((uint16_t)address + length > 256U)) { return Bmp280BusError; }
    mock->io_elapsed_us += 2000ULL;
    (void)memcpy(bytes, &mock->registers[address], length);
    return Bmp280BusOk;
}

Bmp280BusResult Bmp280Bus_Write(void *bus, uint8_t address,
    uint8_t value)
{
    TestBmp280Bus *mock = bus;
    if (mock == NULL) { return Bmp280BusError; }
    mock->io_elapsed_us += 2000ULL;
    mock->registers[address] = value;
    if (address == 0xF5U) { mock->config_writes++; }
    if (address == 0xF4U) { mock->forced_writes++; }
    return Bmp280BusOk;
}

static void TestBmp280_WordSet(uint8_t *bytes, uint16_t word)
{
    bytes[0] = (uint8_t)(word & 0xFFU);
    bytes[1] = (uint8_t)(word >> 8U);
}

static void TestBmp280_RawSet(uint8_t *bytes, uint32_t raw)
{
    bytes[0] = (uint8_t)(raw >> 12U);
    bytes[1] = (uint8_t)(raw >> 4U);
    bytes[2] = (uint8_t)(raw << 4U);
}

static void TestBmp280_BusSeed(TestBmp280Bus *bus)
{
    static const int32_t trims[12] = {
        27504, 26435, -1000, 36477, -10685, 3024,
        2855, 140, -7, 15500, -14600, 6000
    };
    uint8_t index;
    (void)memset(bus, 0, sizeof(*bus));
    bus->registers[0xD0U] = 0x58U;
    for (index = 0U; index < 12U; index++)
    { TestBmp280_WordSet(&bus->registers[0x88U + index * 2U],
        (uint16_t)trims[index]); }
    TestBmp280_RawSet(&bus->registers[0xF7U], 415148U);
    TestBmp280_RawSet(&bus->registers[0xFAU], 519888U);
}

static void TestBmp280_CompensationVector(void)
{
    TestBmp280Bus bus;
    Bmp280Context context;
    Bmp280Port port;
    TestBmp280_BusSeed(&bus);
    port.bus = &bus;
    Bmp280_Init(&context, &port);
    assert(Bmp280_Step(&context, 1000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 2000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 3000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 4000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 5000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 6000U) == Bmp280StepPending);
    assert(bus.config_writes == 1U && bus.forced_writes == 1U);
    assert(Bmp280_Step(&context, 40000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 55000U) == Bmp280StepPending);
    assert(Bmp280_Step(&context, 56000U) == Bmp280StepSampleReady);
    assert(fabsf(context.sample.temperature_c - 25.08F) < 0.03F);
    assert(fabsf(context.sample.pressure_pa - 100653.0F) < 2.0F);
    assert(context.sample.sequence == 1U);
    assert(context.sample.valid_fields ==
        (SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_TEMPERATURE));
    assert((context.sample.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) == 0U);
}

static void TestBmp280_BadIdentityAndTimeout(void)
{
    TestBmp280Bus bus;
    Bmp280Context context;
    Bmp280Port port;
    TestBmp280_BusSeed(&bus);
    port.bus = &bus;
    bus.registers[0xD0U] = 0U;
    Bmp280_Init(&context, &port);
    assert(Bmp280_Step(&context, 1000U) == Bmp280StepNotPresent);
    assert(context.error_count == 1U);
    TestBmp280_BusSeed(&bus);
    Bmp280_Init(&context, &port);
    for (uint8_t step = 0U; step < 6U; step++)
    { assert(Bmp280_Step(&context, 1000U + step) == Bmp280StepPending); }
    assert(Bmp280_Step(&context, 101006U) == Bmp280StepConversionTimeout);
    assert(context.error_count == 1U);
}

static void TestBmp280_FirstSampleActivationBudget(void)
{
    TestBmp280Bus bus;
    Bmp280Context context;
    Bmp280Port port;
    Bmp280StepResult result = Bmp280StepPending;
    uint64_t time_us = 0ULL;
    TestBmp280_BusSeed(&bus);
    port.bus = &bus;
    Bmp280_Init(&context, &port);
    for (uint8_t step = 0U; step < 64U; step++)
    {
        uint64_t before_io = bus.io_elapsed_us;
        result = Bmp280_Step(&context, time_us);
        if (result == Bmp280StepSampleReady)
        { time_us += bus.io_elapsed_us - before_io; break; }
        assert(result == Bmp280StepPending);
        /*10ms after each Process plus every actual mocked2ms bus operation. */
        time_us += 10000ULL + bus.io_elapsed_us - before_io;
    }
    assert(result == Bmp280StepSampleReady && time_us < 250000ULL);
    assert(fabsf(context.sample.pressure_pa - 100653.0F) < 2.0F);
    (void)printf("bmp280 first sample at %llu us under10ms service/2ms bus\n",
        (unsigned long long)time_us);
}
int main(void)
{
    TestBmp280_FirstSampleActivationBudget();
    TestBmp280_CompensationVector();
    TestBmp280_BadIdentityAndTimeout();
    return 0;
}
