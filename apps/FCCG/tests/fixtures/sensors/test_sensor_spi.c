#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "sensor_imu_adapter.h"
#include "mpu6000_spi_device.h"
#include "bmi088_spi_device.h"
#include "bmi323_spi_device.h"
#include "platform_critical.h"

static uint8_t s_registers[2][512];
static const SensorImuProfile *s_profile;
static uint8_t s_cs[2];
static uint8_t s_irq[2];
static uint8_t s_fail;
static uint32_t s_transactions;
static uint64_t s_now;

PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }
uint64_t PlatformTime_Us(void) { return s_now; }
void PlatformTime_DelayMs(uint32_t delay_ms) { s_now += (uint64_t)delay_ms * 1000U; }
PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    assert(id <= PLATFORM_GPIO_1);
    s_cs[id] = high;
    return PLATFORM_OK;
}
uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t slot = (uint8_t)(id - PLATFORM_GPIO_2);
    uint8_t pending;
    assert(slot < 2U);
    pending = s_irq[slot]; s_irq[slot] = 0U;
    return pending;
}
PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout_ms)
{
    uint8_t chip = (s_cs[0] == 0U) ? 0U : 1U;
    uint16_t reg = tx[0] & 0x7FU;
    uint16_t offset = (s_profile->register_width == 2U) ? reg * 2U : reg;
    uint8_t dummy = (chip == 0U) ? s_profile->spi_dummy_bytes : s_profile->auxiliary_spi_dummy_bytes;
    assert(id == PLATFORM_SPI_1 && timeout_ms == 2U && length <= 66U);
    assert(s_cs[chip] == 0U && s_cs[1U-chip] != 0U);
    s_transactions++;
    if (s_fail) { return PLATFORM_IO_ERROR; }
    memset(rx, 0xEE, length);
    if (tx[0] & 0x80U)
    {
        memcpy(rx+1U+dummy, &s_registers[chip][offset], length-1U-dummy);
        if ((s_profile->fifo_frame_length != 0U) && (reg == s_profile->fifo_data_register))
        {
            uint16_t count_reg = s_profile->fifo_count_register * (s_profile->register_width == 2U ? 2U : 1U);
            s_registers[0][count_reg] = 0U; s_registers[0][count_reg + 1U] = 0U;
        }
    }
    else
    {
        memcpy(&s_registers[chip][offset], tx+1U, length-1U);
        if (s_profile == Mpu6000Spi_ProfileGet() && reg == 0x6BU && tx[1] == 0x80U)
        { s_registers[0][reg] = 0U; }
        if (s_profile == Bmi323Spi_ProfileGet() && reg == 0x40U)
        { s_registers[0][0x22U] = 1U; }
    }
    return PLATFORM_OK;
}
PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id, uint16_t address,
    uint16_t reg, PlatformI2cMemoryAddressSize width, uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    (void)id;(void)address;(void)reg;(void)width;(void)data;(void)length;(void)timeout_ms;
    assert(0 && "SPI profile must never use I2C"); return PLATFORM_IO_ERROR;
}
PlatformResult PlatformI2c_MemoryWrite(PlatformI2cId id, uint16_t address,
    uint16_t reg, PlatformI2cMemoryAddressSize width, const uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    (void)id;(void)address;(void)reg;(void)width;(void)data;(void)length;(void)timeout_ms;
    assert(0 && "SPI profile must never use I2C"); return PLATFORM_IO_ERROR;
}

static void Model_Test(const SensorImuProfile *profile)
{
    SensorImuAdapter adapter;
    SystemImuSample sample;
    SensorImuSpiResources resources = {PLATFORM_SPI_1, PLATFORM_GPIO_0,
        PLATFORM_GPIO_1, PLATFORM_GPIO_2, (PlatformGpioId)PLATFORM_GPIO_COUNT};
    memset(s_registers, 0, sizeof(s_registers)); s_profile = profile;
    s_now = 1000000U; s_fail = 0U; s_cs[0] = 1U; s_cs[1] = 1U;
    s_irq[0] = 0U; s_irq[1] = 0U;
    s_registers[0][profile->id_register] = profile->expected_id;
    if (profile == Bmi088Spi_ProfileGet())
    { s_registers[1][0U] = 0x0FU; resources.auxiliary_drdy = PLATFORM_GPIO_3; }
    assert(SensorImuAdapter_InitSpi(&adapter, profile, &resources, 7U) == SYSTEM_DEVICE_OK);
    assert(SensorImuAdapter_Start(&adapter) == SYSTEM_DEVICE_OK);
    for (uint8_t i = 0U; i < 50U && adapter.driver.state != SENSOR_IMU_SAMPLE_VERIFY; i++)
    { s_now += 100000U; (void)SensorImuAdapter_Process(&adapter); }
    assert(adapter.driver.state == SENSOR_IMU_SAMPLE_VERIFY);
    s_registers[0][profile->status_register * (profile->register_width == 2U ? 2U : 1U)] = profile->ready_mask;
    s_registers[1][0x0AU] = 0x80U;
    if (profile->fifo_format == 4U)
    { s_registers[0][0x2AU] = 8U; s_registers[0][0x3AU] = 128U; }
    else if (profile->fifo_frame_length != 0U)
    { s_registers[0][profile->fifo_count_register + 1U] = profile->fifo_frame_length; }
    s_now++;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_OK);
    assert(SensorImuAdapter_SampleGet(&adapter, &sample, 0U) == SYSTEM_DEVICE_OK);
    assert(sample.quality_flags & SYSTEM_IMU_QUALITY_TIME_UNCERTAIN);
    uint32_t previous = s_transactions;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_NOT_READY);
    assert(s_transactions == previous + ((profile->fifo_frame_length != 0U) ? 1U : 0U));
    s_irq[0] = 1U;
    if (profile == Bmi088Spi_ProfileGet())
    { assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_NOT_READY); s_irq[1] = 1U; }
    if (profile->fifo_format == 4U)
    { s_registers[0][0x2AU] = 8U; s_registers[0][0x3AU] = 0U; s_registers[0][0x3BU] = 1U; }
    else if (profile->fifo_frame_length != 0U)
    { s_registers[0][profile->fifo_count_register + 1U] = profile->fifo_frame_length; }
    s_now += 5000U;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_OK);
    SystemImuConfig config;
    SystemDeviceConfigReport report;
    assert(SensorImuAdapter_ConfigGet(&adapter, &config) == SYSTEM_DEVICE_OK);
    config.required_mask = config.requested_mask;
    assert(SensorImuAdapter_ConfigApply(&adapter, &config, &report) == SYSTEM_DEVICE_ALREADY_MATCHED);
    assert(report.success && report.persisted == 0U && report.matched_mask == config.requested_mask);
    config.output_rate_hz = 123U;
    assert(SensorImuAdapter_ConfigApply(&adapter, &config, &report) == SYSTEM_DEVICE_UNSUPPORTED);
    s_irq[0] = 1U; s_irq[1] = 1U; s_fail = 1U; s_now++;
    assert(SensorImuAdapter_Process(&adapter) == SYSTEM_DEVICE_IO_ERROR);
    assert(s_cs[0] == 1U && s_cs[1] == 1U);
    printf("%s: SPI command/dummy/CS/DRDY/isolation/timeout-release PASS\n", profile->name);
}

int main(void)
{
    Model_Test(Mpu6000Spi_ProfileGet());
    Model_Test(Bmi088Spi_ProfileGet());
    Model_Test(Bmi323Spi_ProfileGet());
    return 0;
}
