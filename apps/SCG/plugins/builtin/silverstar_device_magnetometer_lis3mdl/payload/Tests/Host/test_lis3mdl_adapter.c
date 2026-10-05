#include "lis3mdl_adapter.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_time.h"

static uint8_t s_registers[64];
static uint64_t s_now_us;
static uint8_t s_cs_high;
static uint32_t s_i2c_reads;
static uint32_t s_spi_reads;

static void TestLis3mdl_RawSet(uint8_t *bytes, int32_t raw)
{
    uint16_t value = (uint16_t)raw;
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8U);
}

static void TestLis3mdl_Seed(void)
{
    (void)memset(s_registers, 0, sizeof(s_registers));
    s_registers[0x0FU] = 0x3DU;
    s_registers[0x20U] = 0x10U;
    s_registers[0x22U] = 0x03U;
    s_registers[0x27U] = 0x08U;
    TestLis3mdl_RawSet(&s_registers[0x28U], 6842);
    TestLis3mdl_RawSet(&s_registers[0x2AU], -3421);
    TestLis3mdl_RawSet(&s_registers[0x2CU], 0);
    TestLis3mdl_RawSet(&s_registers[0x2EU], 16);
    s_now_us = 0U;
    s_cs_high = 1U;
    s_i2c_reads = 0U;
    s_spi_reads = 0U;
}

uint64_t PlatformTime_Us(void) { return s_now_us; }

PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id,
    uint16_t address_7bit, uint16_t register_address,
    PlatformI2cMemoryAddressSize address_size, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    uint16_t address = register_address & 0x7FU;
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x1CU) ||
        (address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) ||
        (data == NULL) || (timeout_ms != 2U) ||
        (address + length > sizeof(s_registers)) ||
        ((length > 1U) && ((register_address & 0x80U) == 0U)))
    { return PLATFORM_IO_ERROR; }
    (void)memcpy(data, &s_registers[address], length);
    if (address == 0x28U) { s_registers[0x27U] = 0U; }
    s_i2c_reads++;
    return PLATFORM_OK;
}

PlatformResult PlatformI2c_MemoryWrite(PlatformI2cId id,
    uint16_t address_7bit, uint16_t register_address,
    PlatformI2cMemoryAddressSize address_size, const uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x1CU) ||
        (address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) ||
        (data == NULL) || (length != 1U) || (timeout_ms != 2U) ||
        (register_address < 0x20U) || (register_address > 0x24U))
    { return PLATFORM_IO_ERROR; }
    s_registers[register_address] = data[0];
    return PLATFORM_OK;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t logical_high)
{
    if (id != PLATFORM_GPIO_0) { return PLATFORM_IO_ERROR; }
    s_cs_high = logical_high;
    return PLATFORM_OK;
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id,
    const uint8_t *tx, uint8_t *rx, uint16_t length,
    uint32_t timeout_ms)
{
    uint16_t address;
    if ((id != PLATFORM_SPI_1) || (s_cs_high != 0U) ||
        (tx == NULL) || (rx == NULL) || (length < 2U) ||
        (length > 9U) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    address = (uint16_t)(tx[0] & 0x3FU);
    if (address + length - 1U > sizeof(s_registers))
    { return PLATFORM_IO_ERROR; }
    rx[0] = 0U;
    if ((tx[0] & 0x80U) != 0U)
    {
        if ((length > 2U) && ((tx[0] & 0x40U) == 0U))
        { return PLATFORM_IO_ERROR; }
        (void)memcpy(&rx[1], &s_registers[address], length - 1U);
        if (address == 0x28U) { s_registers[0x27U] = 0U; }
        s_spi_reads++;
    }
    else
    {
        if ((length != 2U) || (address < 0x20U) || (address > 0x24U))
        { return PLATFORM_IO_ERROR; }
        s_registers[address] = tx[1];
        rx[1] = 0U;
    }
    return PLATFORM_OK;
}

static void TestLis3mdl_Run(Lis3mdlAdapter *adapter)
{
    SystemMagnetometerConfig config = {
        SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE,
        SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE,
        20U, 400.0F
    };
    SystemDeviceConfigReport report;
    SystemMagnetometerSample sample;
    SystemDeviceHealth health;
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    uint32_t tick;
    assert(Lis3mdlAdapter_Start(adapter) == SYSTEM_DEVICE_OK);
    assert(Lis3mdlAdapter_ConfigApply(adapter, &config, &report) ==
        SYSTEM_DEVICE_CONFIG_DELEGATED);
    assert(Lis3mdlAdapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_NOT_READY);
    for (tick = 0U; tick < 40U; tick++)
    {
        result = Lis3mdlAdapter_Process(adapter);
        if (result == SYSTEM_DEVICE_OK) { break; }
        assert(result == SYSTEM_DEVICE_NOT_READY);
        s_now_us += 1000U;
    }
    assert(result == SYSTEM_DEVICE_OK);
    assert(Lis3mdlAdapter_LatestSampleGet(adapter, &sample) == SYSTEM_DEVICE_OK);
    assert(sample.raw[0] == 6842 && sample.raw[1] == -3421);
    assert(fabsf(sample.magnetic_field_b_uT[0] - 100.0F) < 0.02F);
    assert(fabsf(sample.temperature_c - 27.0F) < 0.01F);
    assert(Lis3mdlAdapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_OK);
    assert(Lis3mdlAdapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.online == 1U && health.healthy == 1U);
    s_now_us = 300000U;
    assert(Lis3mdlAdapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.healthy == 0U);
}

int main(void)
{
    Lis3mdlAdapter adapter;
    TestLis3mdl_Seed();
    assert(Lis3mdlAdapter_InitI2c(&adapter, PLATFORM_I2C_1, 0x1CU) ==
        SYSTEM_DEVICE_OK);
    TestLis3mdl_Run(&adapter);
    assert(s_i2c_reads > 0U && s_spi_reads == 0U);
    TestLis3mdl_Seed();
    assert(Lis3mdlAdapter_InitSpi(&adapter, PLATFORM_SPI_1, PLATFORM_GPIO_0) ==
        SYSTEM_DEVICE_OK);
    TestLis3mdl_Run(&adapter);
    assert(s_i2c_reads == 0U && s_spi_reads > 0U);
    assert(s_cs_high == 1U);
    return 0;
}
