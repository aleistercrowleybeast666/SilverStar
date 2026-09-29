#include "ms5611_adapter.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_time.h"

static uint16_t s_prom[8];
static uint64_t s_now_us;
static uint8_t s_cs_high;
static uint8_t s_last_conversion;
static uint32_t s_i2c_reads;
static uint32_t s_spi_reads;

static void TestMs5611_Seed(void)
{
    static const uint16_t coefficients[6] = {
        40127U, 36924U, 23317U, 23282U, 33464U, 28312U
    };
    uint8_t index;
    (void)memset(s_prom, 0, sizeof(s_prom));
    for (index = 0U; index < 6U; index++)
    { s_prom[index + 1U] = coefficients[index]; }
    s_prom[7] = Ms5611_Crc4Get(s_prom);
    s_now_us = 0U;
    s_cs_high = 1U;
    s_last_conversion = 0U;
    s_i2c_reads = 0U;
    s_spi_reads = 0U;
}

static PlatformResult TestMs5611_CommandWrite(uint8_t command)
{
    if ((command == 0x58U) || (command == 0x48U))
    { s_last_conversion = command; return PLATFORM_OK; }
    return command == 0x1EU ? PLATFORM_OK : PLATFORM_IO_ERROR;
}

static PlatformResult TestMs5611_CommandRead(uint8_t command,
    uint8_t *data, uint16_t length)
{
    uint32_t raw;
    if (data == NULL) { return PLATFORM_IO_ERROR; }
    if ((command >= 0xA0U) && (command <= 0xAEU) &&
        ((command & 1U) == 0U) && (length == 2U))
    {
        uint16_t value = s_prom[(command - 0xA0U) / 2U];
        data[0] = (uint8_t)(value >> 8U);
        data[1] = (uint8_t)value;
        return PLATFORM_OK;
    }
    if ((command != 0x00U) || (length != 3U))
    { return PLATFORM_IO_ERROR; }
    raw = s_last_conversion == 0x58U ? 8569150U : 9085466U;
    data[0] = (uint8_t)(raw >> 16U);
    data[1] = (uint8_t)(raw >> 8U);
    data[2] = (uint8_t)raw;
    return PLATFORM_OK;
}

uint64_t PlatformTime_Us(void) { return s_now_us; }

PlatformResult PlatformI2c_Write(PlatformI2cId id, uint16_t address_7bit,
    const uint8_t *data, uint16_t length, uint32_t timeout_ms)
{
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x77U) ||
        (data == NULL) || (length != 1U) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    return TestMs5611_CommandWrite(data[0]);
}

PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id,
    uint16_t address_7bit, uint16_t register_address,
    PlatformI2cMemoryAddressSize address_size, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    PlatformResult result;
    if ((id != PLATFORM_I2C_1) || (address_7bit != 0x77U) ||
        (address_size != PLATFORM_I2C_MEMORY_ADDRESS_8_BIT) ||
        (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    result = TestMs5611_CommandRead((uint8_t)register_address, data, length);
    if (result == PLATFORM_OK) { s_i2c_reads++; }
    return result;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t logical_high)
{
    if (id != PLATFORM_GPIO_0) { return PLATFORM_IO_ERROR; }
    s_cs_high = logical_high;
    return PLATFORM_OK;
}

PlatformResult PlatformSpi_Write(PlatformSpiId id, const uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    if ((id != PLATFORM_SPI_1) || (s_cs_high != 0U) ||
        (data == NULL) || (length != 1U) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    return TestMs5611_CommandWrite(data[0]);
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id,
    const uint8_t *tx, uint8_t *rx, uint16_t length,
    uint32_t timeout_ms)
{
    PlatformResult result;
    if ((id != PLATFORM_SPI_1) || (s_cs_high != 0U) ||
        (tx == NULL) || (rx == NULL) ||
        ((length != 3U) && (length != 4U)) || (timeout_ms != 2U))
    { return PLATFORM_IO_ERROR; }
    rx[0] = 0U;
    result = TestMs5611_CommandRead(tx[0], &rx[1],
        (uint16_t)(length - 1U));
    if (result == PLATFORM_OK) { s_spi_reads++; }
    return result;
}

static void TestMs5611_Run(Ms5611Adapter *adapter)
{
    SystemBarometerConfig config = {SYSTEM_BARO_CFG_OUTPUT_RATE,
        SYSTEM_BARO_CFG_OUTPUT_RATE, 20U};
    SystemDeviceConfigReport report;
    SystemBarometerSample sample;
    SystemDeviceHealth health;
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    uint32_t step;
    assert(Ms5611Adapter_Start(adapter) == SYSTEM_DEVICE_OK);
    assert(Ms5611Adapter_ConfigApply(adapter, &config, &report) ==
        SYSTEM_DEVICE_CONFIG_DELEGATED);
    assert(Ms5611Adapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_NOT_READY);
    for (step = 0U; step < 100U; step++)
    {
        result = Ms5611Adapter_Process(adapter);
        if (result == SYSTEM_DEVICE_OK) { break; }
        assert(result == SYSTEM_DEVICE_NOT_READY);
        s_now_us += 1000U;
    }
    assert(result == SYSTEM_DEVICE_OK);
    assert(Ms5611Adapter_LatestSampleGet(adapter, &sample) ==
        SYSTEM_DEVICE_OK);
    assert(fabsf(sample.pressure_pa - 100009.0F) < 2.0F);
    assert((sample.valid_fields & SYSTEM_BARO_FIELD_ALTITUDE) == 0U);
    assert(Ms5611Adapter_ConfigVerify(adapter, &config, &report) ==
        SYSTEM_DEVICE_OK);
    assert(Ms5611Adapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.online == 1U && health.healthy == 1U);
    s_now_us = 300000U;
    assert(Ms5611Adapter_HealthGet(adapter, &health) == SYSTEM_DEVICE_OK);
    assert(health.healthy == 0U);
}

int main(void)
{
    Ms5611Adapter adapter;
    TestMs5611_Seed();
    assert(Ms5611Adapter_InitI2c(&adapter, PLATFORM_I2C_1, 0x77U) ==
        SYSTEM_DEVICE_OK);
    TestMs5611_Run(&adapter);
    assert(s_i2c_reads > 0U && s_spi_reads == 0U);
    TestMs5611_Seed();
    assert(Ms5611Adapter_InitSpi(&adapter, PLATFORM_SPI_1, PLATFORM_GPIO_0) ==
        SYSTEM_DEVICE_OK);
    TestMs5611_Run(&adapter);
    assert(s_i2c_reads == 0U && s_spi_reads > 0U);
    assert(s_cs_high == 1U);
    return 0;
}
