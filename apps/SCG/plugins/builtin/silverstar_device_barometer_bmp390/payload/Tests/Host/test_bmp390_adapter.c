#include "bmp390_adapter.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_time.h"

static uint8_t s_registers[256];
static uint64_t s_now_us;
static uint8_t s_cs_high;
static uint32_t s_i2c_reads;
static uint32_t s_spi_reads;

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

static void TestBmp390_Seed(void)
{
    uint8_t *trim;
    (void)memset(s_registers, 0, sizeof(s_registers));
    s_registers[0x00U] = 0x60U;
    s_registers[0x1CU] = 0x02U;
    s_registers[0x1FU] = 0x08U;
    trim = &s_registers[0x31U];
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
    TestBmp390_RawSet(&s_registers[0x04U], 2000000U);
    TestBmp390_RawSet(&s_registers[0x07U], 6120000U);
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
    if (register_address == 0x1BU) { s_registers[0x03U] = 0x60U; }
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
        (length > 26U) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    address = (uint16_t)(tx[0] & 0x7FU);
    rx[0] = 0U;
    if ((tx[0] & 0x80U) != 0U)
    {
        if (address + length - 2U > sizeof(s_registers))
        { return PLATFORM_IO_ERROR; }
        rx[1] = 0xA5U;
        (void)memcpy(&rx[2], &s_registers[address], length - 2U);
        s_spi_reads++;
    }
    else
    {
        if (length != 2U) { return PLATFORM_IO_ERROR; }
        s_registers[address] = tx[1];
        if (address == 0x1BU) { s_registers[0x03U] = 0x60U; }
        rx[1] = 0U;
    }
    return PLATFORM_OK;
}

static void TestBmp390_Run(Bmp390Adapter *adapter)
{
    SystemBarometerConfig config = {SYSTEM_BARO_CFG_OUTPUT_RATE,
        SYSTEM_BARO_CFG_OUTPUT_RATE, 20U};
    SystemDeviceConfigReport report;
    SystemBarometerSample sample;
    SystemDeviceHealth health;
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    uint32_t step;
    assert(Bmp390Adapter_Start(adapter) == SYSTEM_DEVICE_OK);
    assert(Bmp390Adapter_ConfigApply(adapter, &config, &report) ==
        SYSTEM_DEVICE_CONFIG_DELEGATED);
    assert(Bmp390Adapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_NOT_READY);
    for (step = 0U; step < 100U; step++)
    {
        result = Bmp390Adapter_Process(adapter);
        if (result == SYSTEM_DEVICE_OK) { break; }
        assert(result == SYSTEM_DEVICE_NOT_READY);
        s_now_us += 1000U;
    }
    assert(result == SYSTEM_DEVICE_OK);
    assert(Bmp390Adapter_LatestSampleGet(adapter, &sample) == SYSTEM_DEVICE_OK);
    assert(fabsf(sample.pressure_pa - 100276.62F) < 3.0F);
    assert((sample.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) == 0U);
    assert(Bmp390Adapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_OK);
    assert(Bmp390Adapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.online == 1U && health.healthy == 1U);
    s_now_us = 300000U;
    assert(Bmp390Adapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.healthy == 0U);
}

int main(void)
{
    Bmp390Adapter adapter;
    TestBmp390_Seed();
    assert(Bmp390Adapter_InitI2c(&adapter, PLATFORM_I2C_1, 0x76U) ==
        SYSTEM_DEVICE_OK);
    TestBmp390_Run(&adapter);
    assert(s_i2c_reads > 0U && s_spi_reads == 0U);
    TestBmp390_Seed();
    assert(Bmp390Adapter_InitSpi(&adapter, PLATFORM_SPI_1, PLATFORM_GPIO_0) ==
        SYSTEM_DEVICE_OK);
    TestBmp390_Run(&adapter);
    assert(s_i2c_reads == 0U && s_spi_reads > 0U);
    assert(s_cs_high == 1U);
    return 0;
}
