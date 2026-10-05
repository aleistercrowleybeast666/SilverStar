#include "bmp280_adapter.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_time.h"

static uint8_t s_registers[256];
static uint64_t s_now_us;
static uint8_t s_cs_high = 1U;
static uint32_t s_i2c_reads;
static uint32_t s_spi_reads;

static void TestBmp280_WordSet(uint8_t *bytes, uint16_t value)
{
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8U);
}

static void TestBmp280_RawSet(uint8_t *bytes, uint32_t raw)
{
    bytes[0] = (uint8_t)(raw >> 12U);
    bytes[1] = (uint8_t)(raw >> 4U);
    bytes[2] = (uint8_t)(raw << 4U);
}

static void TestBmp280_Seed(void)
{
    static const int32_t trims[12] = {
        27504, 26435, -1000, 36477, -10685, 3024,
        2855, 140, -7, 15500, -14600, 6000
    };
    uint8_t index;
    (void)memset(s_registers, 0, sizeof(s_registers));
    s_registers[0xD0U] = 0x58U;
    for (index = 0U; index < 12U; index++)
    { TestBmp280_WordSet(&s_registers[0x88U + index * 2U],
        (uint16_t)trims[index]); }
    TestBmp280_RawSet(&s_registers[0xF7U], 415148U);
    TestBmp280_RawSet(&s_registers[0xFAU], 519888U);
    s_now_us = 0U;
    s_i2c_reads = 0U;
    s_spi_reads = 0U;
}

uint64_t PlatformTime_Us(void) { return s_now_us; }

PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id,
    uint16_t address_7bit, uint16_t register_address,
    PlatformI2cMemoryAddressSize address_size, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x76U) ||
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
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x76U) ||
        (address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) ||
        (data == NULL) || (length != 1U) || (timeout_ms != 2U) ||
        (register_address >= sizeof(s_registers)))
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
    uint16_t index;
    uint16_t register_address;
    if ((id != PLATFORM_SPI_1) || (s_cs_high != 0U) ||
        (tx == NULL) || (rx == NULL) || (length < 2U) ||
        (length > 25U) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    register_address = (uint16_t)((tx[0] & 0x7FU) | 0x80U);
    if (register_address + length - 1U > sizeof(s_registers))
    { return PLATFORM_IO_ERROR; }
    rx[0] = 0U;
    if ((tx[0] & 0x80U) != 0U)
    {
        for (index = 1U; index < length; index++)
        { rx[index] = s_registers[register_address + index - 1U]; }
        s_spi_reads++;
    }
    else
    {
        if (length != 2U) { return PLATFORM_IO_ERROR; }
        s_registers[register_address] = tx[1];
        rx[1] = 0U;
    }
    return PLATFORM_OK;
}

static void TestBmp280_Run(Bmp280Adapter *adapter)
{
    SystemBarometerSample sample;
    SystemDeviceHealth health;
    SystemBarometerConfig config = {SYSTEM_BARO_CFG_OUTPUT_RATE,
        SYSTEM_BARO_CFG_OUTPUT_RATE, 20U};
    SystemDeviceConfigReport report;
    uint8_t step;
    assert(Bmp280Adapter_Start(adapter) == SYSTEM_DEVICE_OK);
    assert(Bmp280Adapter_ConfigApply(adapter, &config, &report) ==
        SYSTEM_DEVICE_CONFIG_DELEGATED);
    assert(Bmp280Adapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_NOT_READY);
    for (step = 0U; step < 6U; step++)
    { (void)Bmp280Adapter_Process(adapter); s_now_us += 1000U; }
    assert(Bmp280Adapter_LatestSampleGet(adapter, &sample) ==
        SYSTEM_DEVICE_NOT_READY);
    s_now_us = 51000U;
    assert(Bmp280Adapter_Process(adapter) == SYSTEM_DEVICE_NOT_READY);
    s_now_us = 52000U;
    assert(Bmp280Adapter_Process(adapter) == SYSTEM_DEVICE_OK);
    assert(Bmp280Adapter_LatestSampleGet(adapter, &sample) == SYSTEM_DEVICE_OK);
    assert(fabsf(sample.pressure_pa - 100653.0F) < 2.0F);
    assert((sample.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) == 0U);
    assert(Bmp280Adapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_OK);
    assert(Bmp280Adapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.online == 1U && health.healthy == 1U);
    s_now_us = 300000U;
    assert(Bmp280Adapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.healthy == 0U);
}

int main(void)
{
    Bmp280Adapter adapter;
    TestBmp280_Seed();
    assert(Bmp280Adapter_InitI2c(&adapter, PLATFORM_I2C_1, 0x76U) ==
        SYSTEM_DEVICE_OK);
    TestBmp280_Run(&adapter);
    assert(s_i2c_reads > 0U && s_spi_reads == 0U);
    TestBmp280_Seed();
    assert(Bmp280Adapter_InitSpi(&adapter, PLATFORM_SPI_1, PLATFORM_GPIO_0) ==
        SYSTEM_DEVICE_OK);
    TestBmp280_Run(&adapter);
    assert(s_i2c_reads == 0U && s_spi_reads > 0U);
    assert(s_cs_high == 1U);
    return 0;
}
