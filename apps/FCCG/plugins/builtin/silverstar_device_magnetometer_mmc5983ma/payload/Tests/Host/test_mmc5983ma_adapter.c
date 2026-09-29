#include "mmc5983ma_adapter.h"

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

static void TestMmc5983ma_RawSet(uint32_t index, uint32_t raw)
{
    s_registers[index * 2U] = (uint8_t)(raw >> 10U);
    s_registers[index * 2U + 1U] = (uint8_t)(raw >> 2U);
    s_registers[6] |= (uint8_t)((raw & 3U) << (6U - index * 2U));
}

static void TestMmc5983ma_Seed(void)
{
    (void)memset(s_registers, 0, sizeof(s_registers));
    s_registers[0x2FU] = 0x30U;
    s_registers[0x07U] = 125U;
    TestMmc5983ma_RawSet(0U, 147456U);
    TestMmc5983ma_RawSet(1U, 122880U);
    TestMmc5983ma_RawSet(2U, 131072U);
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
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x30U) ||
        (address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) ||
        (data == NULL) || (timeout_ms != 2U) ||
        (register_address + length > sizeof(s_registers)))
    { return PLATFORM_IO_ERROR; }
    (void)memcpy(data, &s_registers[register_address], length);
    s_i2c_reads++;
    return PLATFORM_OK;
}

PlatformResult PlatformI2c_MemoryWrite(PlatformI2cId id,
    uint16_t address_7bit, uint16_t register_address,
    PlatformI2cMemoryAddressSize address_size, const uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x30U) ||
        (address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) ||
        (data == NULL) || (length != 1U) || (timeout_ms != 2U) ||
        ((register_address != 0x09U) && (register_address != 0x0AU) &&
            (register_address != 0x0BU)))
    { return PLATFORM_IO_ERROR; }
    if (register_address == 0x09U)
    {
        if (data[0] == 0x01U) { s_registers[0x08U] |= 0x01U; }
        if (data[0] == 0x02U) { s_registers[0x08U] |= 0x02U; }
    }
    else { s_registers[register_address] = data[0]; }
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
        (length > 8U) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    address = (uint16_t)(tx[0] & 0x3FU);
    if (address + length - 1U > sizeof(s_registers))
    { return PLATFORM_IO_ERROR; }
    rx[0] = 0U;
    if ((tx[0] & 0x80U) != 0U)
    {
        (void)memcpy(&rx[1], &s_registers[address], length - 1U);
        s_spi_reads++;
    }
    else
    {
        if ((length != 2U) ||
            ((address != 0x09U) && (address != 0x0AU) &&
                (address != 0x0BU)))
        { return PLATFORM_IO_ERROR; }
        if (address == 0x09U)
        {
            if (tx[1] == 0x01U) { s_registers[0x08U] |= 0x01U; }
            if (tx[1] == 0x02U) { s_registers[0x08U] |= 0x02U; }
        }
        else { s_registers[address] = tx[1]; }
        rx[1] = 0U;
    }
    return PLATFORM_OK;
}

static void TestMmc5983ma_Run(Mmc5983maAdapter *adapter)
{
    SystemMagnetometerConfig config = {
        SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE,
        SYSTEM_MAG_CFG_OUTPUT_RATE | SYSTEM_MAG_CFG_RANGE,
        20U, 800.0F
    };
    SystemDeviceConfigReport report;
    SystemMagnetometerSample sample;
    SystemDeviceHealth health;
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    uint32_t tick;
    assert(Mmc5983maAdapter_Start(adapter) == SYSTEM_DEVICE_OK);
    assert(Mmc5983maAdapter_ConfigApply(adapter, &config, &report) ==
        SYSTEM_DEVICE_CONFIG_DELEGATED);
    assert(Mmc5983maAdapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_NOT_READY);
    for (tick = 0U; tick < 40U; tick++)
    {
        result = Mmc5983maAdapter_Process(adapter);
        if (result == SYSTEM_DEVICE_OK) { break; }
        assert(result == SYSTEM_DEVICE_NOT_READY);
        s_now_us += 1000U;
    }
    assert(result == SYSTEM_DEVICE_OK);
    assert(Mmc5983maAdapter_LatestSampleGet(adapter, &sample) ==
        SYSTEM_DEVICE_OK);
    assert(sample.raw[0] == 16384 && sample.raw[1] == -8192);
    assert(fabsf(sample.magnetic_field_b_uT[0] - 100.0F) < 0.02F);
    assert(fabsf(sample.temperature_c - 25.0F) < 0.01F);
    assert(Mmc5983maAdapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_OK);
    assert(Mmc5983maAdapter_HealthGet(adapter, &health) ==
        SYSTEM_DEVICE_OK);
    assert(health.online == 1U && health.healthy == 1U);
    s_now_us = 300000U;
    assert(Mmc5983maAdapter_HealthGet(adapter, &health) ==
        SYSTEM_DEVICE_OK);
    assert(health.healthy == 0U);
}

int main(void)
{
    Mmc5983maAdapter adapter;
    TestMmc5983ma_Seed();
    assert(Mmc5983maAdapter_InitI2c(&adapter, PLATFORM_I2C_1, 0x30U) ==
        SYSTEM_DEVICE_OK);
    TestMmc5983ma_Run(&adapter);
    assert(s_i2c_reads > 0U && s_spi_reads == 0U);
    TestMmc5983ma_Seed();
    assert(Mmc5983maAdapter_InitSpi(&adapter, PLATFORM_SPI_1,
        PLATFORM_GPIO_0) == SYSTEM_DEVICE_OK);
    TestMmc5983ma_Run(&adapter);
    assert(s_i2c_reads == 0U && s_spi_reads > 0U);
    assert(s_cs_high == 1U);
    return 0;
}
