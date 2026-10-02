#include "ms5611_core.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

typedef struct
{
    uint16_t prom[8];
    uint8_t last_conversion;
    uint32_t reset_count;
    uint32_t temperature_start_count;
    uint32_t pressure_start_count;
} TestMs5611Bus;

Ms5611BusResult Ms5611Bus_Write(void *bus, uint8_t command)
{
    TestMs5611Bus *mock = (TestMs5611Bus *)bus;
    if (mock == NULL) { return Ms5611BusError; }
    if (command == 0x1EU) { mock->reset_count++; return Ms5611BusOk; }
    if (command == 0x58U)
    { mock->last_conversion = command; mock->temperature_start_count++; return Ms5611BusOk; }
    if (command == 0x48U)
    { mock->last_conversion = command; mock->pressure_start_count++; return Ms5611BusOk; }
    return Ms5611BusError;
}

Ms5611BusResult Ms5611Bus_Read(void *bus, uint8_t command,
    uint8_t *bytes, uint8_t length)
{
    TestMs5611Bus *mock = (TestMs5611Bus *)bus;
    uint32_t raw;
    if ((mock == NULL) || (bytes == NULL)) { return Ms5611BusError; }
    if ((command >= 0xA0U) && (command <= 0xAEU) &&
        ((command & 1U) == 0U) && (length == 2U))
    {
        uint16_t word = mock->prom[(command - 0xA0U) / 2U];
        bytes[0] = (uint8_t)(word >> 8U);
        bytes[1] = (uint8_t)word;
        return Ms5611BusOk;
    }
    if ((command != 0x00U) || (length != 3U))
    { return Ms5611BusError; }
    raw = mock->last_conversion == 0x58U ? 8569150U : 9085466U;
    bytes[0] = (uint8_t)(raw >> 16U);
    bytes[1] = (uint8_t)(raw >> 8U);
    bytes[2] = (uint8_t)raw;
    return Ms5611BusOk;
}

static void TestMs5611_Seed(TestMs5611Bus *bus)
{
    static const uint16_t coefficients[6] = {
        40127U, 36924U, 23317U, 23282U, 33464U, 28312U
    };
    uint8_t index;
    (void)memset(bus, 0, sizeof(*bus));
    for (index = 0U; index < 6U; index++)
    { bus->prom[index + 1U] = coefficients[index]; }
    bus->prom[7] = Ms5611_Crc4Get(bus->prom);
}

static void TestMs5611_OfficialVectorAndBoundedCycle(void)
{
    TestMs5611Bus bus;
    Ms5611Context context;
    Ms5611Port port;
    Ms5611StepResult result = Ms5611StepPending;
    uint64_t time_us;
    TestMs5611_Seed(&bus);
    port.bus = &bus;
    Ms5611_Init(&context, &port);
    for (time_us = 0U; time_us < 100000U; time_us += 1000U)
    {
        result = Ms5611_Step(&context, time_us);
        if (result == Ms5611StepSampleReady) { break; }
        assert(result == Ms5611StepPending);
    }
    assert(result == Ms5611StepSampleReady);
    assert(bus.reset_count == 1U);
    assert(bus.temperature_start_count == 1U);
    assert(bus.pressure_start_count == 1U);
    assert(fabsf(context.sample.pressure_pa - 100009.0F) < 2.0F);
    assert(fabsf(context.sample.temperature_c - 20.07F) < 0.02F);
    assert((context.sample.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) == 0U);
    assert(Ms5611_Step(&context, time_us + 1000U) == Ms5611StepPending);
    assert(bus.temperature_start_count == 1U);
    assert(Ms5611_Step(&context, time_us + 50000U) == Ms5611StepPending);
    assert(bus.temperature_start_count == 2U);
}

static void TestMs5611_CrcAndTimeout(void)
{
    TestMs5611Bus bus;
    Ms5611Context context;
    Ms5611Port port;
    uint64_t time_us;
    TestMs5611_Seed(&bus);
    bus.prom[1] ^= 1U;
    port.bus = &bus;
    Ms5611_Init(&context, &port);
    for (time_us = 0U; time_us < 30000U; time_us += 1000U)
    {
        if (Ms5611_Step(&context, time_us) == Ms5611StepPromCrcError)
        { break; }
    }
    assert(context.state == Ms5611StateFailed);
    TestMs5611_Seed(&bus);
    Ms5611_Init(&context, &port);
    for (time_us = 0U; time_us < 30000U; time_us += 1000U)
    {
        (void)Ms5611_Step(&context, time_us);
        if (context.state == Ms5611StateWaitTemperature) { break; }
    }
    assert(context.state == Ms5611StateWaitTemperature);
    assert(Ms5611_Step(&context, time_us + 31000U) ==
        Ms5611StepConversionTimeout);
    assert(context.state == Ms5611StateFailed);
}

int main(void)
{
    TestMs5611_OfficialVectorAndBoundedCycle();
    TestMs5611_CrcAndTimeout();
    return 0;
}
