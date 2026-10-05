#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "sensor_bmi088_sync.h"
#include "sensor_imu_adapter.h"
#include "platform_critical.h"

static uint8_t s_regs[2][256];
static uint8_t s_image[6144];
static uint8_t s_feature[6];
static uint8_t s_irq[2];
static uint8_t s_cs[2];
static uint64_t s_now;
static uint64_t s_aps_time;
static uint64_t s_init_time;
static uint32_t s_image_bytes;
static uint32_t s_writes;
static uint16_t s_fail_chunk;
static uint8_t s_bad_asic;
static uint8_t s_bad_readback;
static uint8_t s_cross_irq;
static uint8_t s_torn;
static uint8_t s_reentry;
static SensorImuAdapter *s_active;

PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint64_t PlatformTime_Us(void) { return s_now; }
void PlatformTime_DelayMs(uint32_t delay_ms) { s_now += (uint64_t)delay_ms * 1000U; }
uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t index = (uint8_t)(id - PLATFORM_GPIO_2);
    assert(index < 2U);
    uint8_t value = s_irq[index]; s_irq[index] = 0U;
    return value;
}
PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    assert(id <= PLATFORM_GPIO_1); s_cs[id] = high; return PLATFORM_OK;
}
static PlatformResult Mock_Read(uint8_t chip, uint16_t reg, uint8_t *data, uint16_t length)
{
    assert(reg + length <= 256U);
    if (chip == 0U && reg == 0x2AU)
    {
        assert(s_now >= s_init_time + 150000U);
        data[0] = s_bad_asic ? 0U : 1U; return PLATFORM_OK;
    }
    if (chip == 0U && reg == 0x5EU)
    {
        assert(length == 6U); memcpy(data, s_feature, length);
        if (s_bad_readback) { data[4] ^= 2U; }
        return PLATFORM_OK;
    }
    if (chip == 0U && reg == 0x1EU && s_reentry)
    {
        s_reentry = 0U;
        assert(SensorImuAdapter_Process(s_active) == SYSTEM_DEVICE_BUSY);
    }
    memcpy(data, &s_regs[chip][reg], length);
    if (chip == 1U && reg == 2U)
    {
        if (s_cross_irq) { s_irq[1] = 1U; s_cross_irq = 0U; }
        if (s_torn) { s_regs[1][2]++; }
    }
    return PLATFORM_OK;
}
static PlatformResult Mock_Write(uint8_t chip, uint16_t reg, const uint8_t *data, uint16_t length)
{
    assert(reg + length <= 256U); s_writes++;
    if (chip == 0U && reg == 0x5EU && length == 32U)
    {
        uint16_t word = (uint16_t)((uint16_t)s_regs[0][0x5BU] | ((uint16_t)s_regs[0][0x5CU] << 4U));
        uint16_t offset = (uint16_t)(word * 2U);
        assert(offset == s_image_bytes && offset + length <= sizeof(s_image));
        if (offset == s_fail_chunk) { return PLATFORM_IO_ERROR; }
        memcpy(&s_image[offset], data, length); s_image_bytes += length;
        return PLATFORM_OK;
    }
    if (chip == 0U && reg == 0x5EU)
    { assert(length == 6U); memcpy(s_feature, data, length); return PLATFORM_OK; }
    memcpy(&s_regs[chip][reg], data, length);
    if (chip == 0U && reg == 0x7CU) { s_aps_time = s_now; }
    if (chip == 0U && reg == 0x59U && data[0] == 0U)
    { assert(s_now >= s_aps_time + 450U); }
    if (chip == 0U && reg == 0x59U && data[0] == 1U)
    { assert(s_image_bytes == 6144U); s_init_time = s_now; }
    return PLATFORM_OK;
}
PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id, uint16_t address,
    uint16_t reg, PlatformI2cMemoryAddressSize width, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    assert(id == PLATFORM_I2C_1 && width == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT && timeout_ms == 2U);
    assert(address == 0x18U || address == 0x68U);
    return Mock_Read(address == 0x18U ? 0U : 1U, reg, data, length);
}
PlatformResult PlatformI2c_MemoryWrite(PlatformI2cId id, uint16_t address,
    uint16_t reg, PlatformI2cMemoryAddressSize width, const uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    assert(id == PLATFORM_I2C_1 && width == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT && timeout_ms == 2U);
    assert(address == 0x18U || address == 0x68U);
    return Mock_Write(address == 0x18U ? 0U : 1U, reg, data, length);
}
PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout_ms)
{
    uint8_t chip = s_cs[0] == 0U ? 0U : 1U;
    uint16_t reg = tx[0] & 0x7FU;
    assert(id == PLATFORM_SPI_1 && timeout_ms == 2U && length <= 66U);
    assert(s_cs[chip] == 0U && s_cs[1U-chip] == 1U);
    memset(rx, 0xEE, length);
    if (tx[0] & 0x80U)
    {
        uint16_t skip = chip == 0U ? 2U : 1U;
        return Mock_Read(chip, reg, rx + skip, (uint16_t)(length - skip));
    }
    return Mock_Write(chip, reg, tx + 1U, (uint16_t)(length - 1U));
}
static void Mock_Init(SensorImuAdapter *adapter, uint8_t spi)
{
    memset(s_regs, 0, sizeof(s_regs)); memset(s_irq, 0, sizeof(s_irq));
    memset(s_image, 0, sizeof(s_image)); memset(s_feature, 0, sizeof(s_feature));
    s_regs[0][0] = 0x1EU; s_regs[1][0] = 0x0FU;
    s_regs[0][0x1EU] = 0xFFU; s_regs[0][0x1FU] = 0x7FU;
    s_regs[0][0x27U] = 0U; s_regs[0][0x28U] = 0x80U;
    s_regs[1][2] = 0xFEU; s_regs[1][3] = 0xFFU;
    s_now = 1000000U; s_image_bytes = 0U; s_writes = 0U; s_fail_chunk = 65535U;
    s_bad_asic = 0U; s_bad_readback = 0U; s_cross_irq = 0U; s_torn = 0U; s_reentry = 0U;
    s_cs[0] = 1U; s_cs[1] = 1U; s_active = adapter;
    if (spi)
    {
        SensorImuSpiResources resources = {PLATFORM_SPI_1, PLATFORM_GPIO_0, PLATFORM_GPIO_1, PLATFORM_GPIO_2, PLATFORM_GPIO_3};
        assert(SensorImuAdapter_InitSpi(adapter, SensorBmi088Sync_ProfileGet(), &resources, 17U) == SYSTEM_DEVICE_OK);
    }
    else
    {
        assert(SensorImuAdapter_InitI2c(adapter, SensorBmi088Sync_ProfileGet(), PLATFORM_I2C_1, PLATFORM_I2C_1, 0x18U, 17U) == SYSTEM_DEVICE_OK);
        adapter->spi_resources.drdy = PLATFORM_GPIO_2; adapter->spi_resources.auxiliary_drdy = PLATFORM_GPIO_3;
    }
    assert(SensorImuAdapter_Start(adapter) == SYSTEM_DEVICE_OK);
}
static SystemDeviceResult Mock_Configure(SensorImuAdapter *adapter)
{
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    for (uint16_t index = 0U; index < 1000U; index++)
    {
        s_now += 1000U; result = SensorImuAdapter_Process(adapter);
        if (adapter->driver.state == SENSOR_IMU_SAMPLE_VERIFY || adapter->driver.state == SENSOR_IMU_FAULT) { break; }
    }
    return result;
}
static SystemDeviceResult Mock_Pair(SensorImuAdapter *adapter)
{
    s_now += 2500U; s_irq[0] = 1U; s_irq[1] = 1U;
    return SensorImuAdapter_Process(adapter);
}
static void Sync_Test(uint8_t spi)
{
    SensorImuAdapter adapter; SystemImuSample sample; SystemImuConfig config; SystemDeviceConfigReport report;
    Mock_Init(&adapter, spi);
    assert(Mock_Configure(&adapter) == SYSTEM_DEVICE_NOT_READY);
    assert(adapter.driver.state == SENSOR_IMU_SAMPLE_VERIFY && s_image_bytes == 6144U);
    assert(s_image[0] == 0xC8U && s_image[1] == 0x2EU && s_feature[4] == 1U);
    assert(SensorImuAdapter_ConfigGet(&adapter, &config) == SYSTEM_DEVICE_OK);
    assert(SensorImuAdapter_SampleGet(&adapter, &sample, 0U) == SYSTEM_DEVICE_NOT_READY);
    assert(s_regs[0][0x53] == 0x13U && s_regs[0][0x54] == 0x0AU && s_regs[0][0x57] == 1U);
    s_cross_irq = 1U;
    assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED);
    assert(adapter.driver.state == SENSOR_IMU_SAMPLE_VERIFY);
    assert(SensorImuAdapter_SampleGet(&adapter, &sample, 0U) == SYSTEM_DEVICE_NOT_READY);
    assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_OK);
    assert(SensorImuAdapter_SampleGet(&adapter, &sample, 1U) == SYSTEM_DEVICE_OK);
    assert(sample.accel_raw[0] == 32767 && sample.accel_raw[2] == -32768 && sample.gyro_raw[0] == -2);
    assert(sample.quality_flags & SYSTEM_IMU_QUALITY_TIME_UNCERTAIN);
    assert(sample.quality_flags & SYSTEM_IMU_QUALITY_CLIPPED);
    assert(SensorImuAdapter_ConfigGet(&adapter, &config) == SYSTEM_DEVICE_OK && config.output_rate_hz == 400U);
    uint32_t writes = s_writes;
    assert(SensorImuAdapter_ConfigCheck(&adapter, &config, &report) == SYSTEM_DEVICE_ALREADY_MATCHED);
    assert(s_writes == writes && report.persisted == 0U);
    s_feature[4] = 2U;
    assert(SensorImuAdapter_ConfigCheck(&adapter, &config, &report) == SYSTEM_DEVICE_VERIFY_FAILED);
    assert(adapter.driver.state == SENSOR_IMU_FAULT && adapter.driver.profile_verified == 0U);
    Mock_Init(&adapter, spi); (void)Mock_Configure(&adapter);
    assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_OK);
    s_now += 2500U; s_irq[0] = 1U; /* Ready without preceding gyro: reject. */
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED);
    assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED); /* Observable gap. */
    assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_OK);
    s_reentry = 1U; assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_OK);
    s_cross_irq = 1U; assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED);
    s_torn = 1U; assert(Mock_Pair(&adapter) == SYSTEM_DEVICE_IO_ERROR); s_torn = 0U;
    s_now += 2500U; s_irq[1] = 1U;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_NOT_READY);
    s_now += 3000U; s_irq[0] = 1U;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED);
    assert(adapter.driver.time_errors >= 3U);
    Mock_Init(&adapter, spi); s_bad_asic = 1U;
    assert(Mock_Configure(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED && adapter.driver.state == SENSOR_IMU_FAULT);
    Mock_Init(&adapter, spi); s_fail_chunk = 32U;
    assert(Mock_Configure(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED && s_image_bytes == 32U);
    Mock_Init(&adapter, spi); s_bad_readback = 1U;
    assert(Mock_Configure(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED && adapter.driver.profile_verified == 0U);
    Mock_Init(&adapter, spi); (void)Mock_Configure(&adapter);
    s_now += 1000001U;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_VERIFY_FAILED); /* No wire/IRQ never READY. */
    printf("BMI088 Sync400 %s: official image/reset/readback/pairing/order/gap/reentry/cross-epoch/stall/errors PASS\n", spi ? "SPI" : "I2C");
}
int main(void)
{
    Sync_Test(0U); Sync_Test(1U); return 0;
}
