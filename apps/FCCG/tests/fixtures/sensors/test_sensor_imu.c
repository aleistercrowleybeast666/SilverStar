#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include "sensor_imu.h"
#include "mpu6000_device.h"
#include "mpu6050_device.h"
#include "mpu6500_device.h"
#include "mpu9250_device.h"
#include "lsm6dsv32x_device.h"
#include "lsm6dsv320x_device.h"
#include "icm42605_device.h"
#include "icm42688p_device.h"

typedef struct
{
    uint8_t registers[256];
    uint8_t fifo[64];
    uint16_t fifo_cursor;
    uint32_t reads;
    uint32_t writes;
    uint8_t fail_reads;
    uint8_t ignore_writes;
    const SensorImuProfile *profile;
} MockBus;

static SensorBusResult Mock_Read(void *context, uint16_t reg, uint8_t *data,
    uint16_t length, uint32_t timeout_us)
{
    MockBus *mock = context;
    assert(timeout_us == 2000U);
    assert((uint32_t)reg + length <= 256U);
    mock->reads++;
    if (mock->fail_reads != 0U) { return SENSOR_BUS_IO_ERROR; }
    if ((reg == mock->profile->fifo_data_register) &&
        (mock->profile->fifo_frame_length != 0U))
    {
        assert(mock->fifo_cursor + length <= sizeof(mock->fifo));
        memcpy(data, &mock->fifo[mock->fifo_cursor], length);
        mock->fifo_cursor += length;
        if (mock->profile->fifo_format == 1U)
        { mock->registers[0x1BU]--; }
    }
    else { memcpy(data, &mock->registers[reg], length); }
    return SENSOR_BUS_OK;
}

static SensorBusResult Mock_Write(void *context, uint16_t reg, const uint8_t *data,
    uint16_t length, uint32_t timeout_us)
{
    MockBus *mock = context;
    assert(timeout_us == 2000U);
    assert((uint32_t)reg + length <= 256U);
    mock->writes++;
    if (mock->ignore_writes == 0U) { memcpy(&mock->registers[reg], data, length); }
    if ((reg == mock->profile->reset_register) &&
        (data[0] == mock->profile->reset_value))
    {
        mock->registers[reg] &= (uint8_t)~mock->profile->reset_mask;
    }
    return SENSOR_BUS_OK;
}

static void Mock_Init(MockBus *mock, SensorImu *imu, const SensorImuProfile *profile,
    SensorBusKind kind)
{
    SensorRegisterBus bus;
    memset(mock, 0, sizeof(*mock));
    mock->profile = profile;
    mock->registers[profile->id_register] = profile->expected_id;
    bus.context = mock;
    bus.read = Mock_Read;
    bus.write = Mock_Write;
    bus.kind = kind;
    assert(SensorImu_Init(imu, &bus, profile, 17U) == SENSOR_IMU_OK);
}

static uint64_t Mock_Configure(MockBus *mock, SensorImu *imu, uint8_t reset)
{
    uint64_t now = 1000000U;
    uint8_t step;
    assert(SensorImu_BeginConfigure(imu, now, reset) == SENSOR_IMU_BUSY);
    for (step = 0U; step < 40U; step++)
    {
        SensorImuResult result;
        now += 100000U;
        result = SensorImu_ProcessConfigure(imu, now);
        assert((result == SENSOR_IMU_BUSY) || (result == SENSOR_IMU_NOT_READY));
        if (imu->state == SENSOR_IMU_SAMPLE_VERIFY) { break; }
    }
    assert(step < 40U);
    assert(imu->profile_verified == 1U);
    assert(imu->state != SENSOR_IMU_READY);
    mock->registers[imu->profile->status_register] = imu->profile->ready_mask;
    return now + 1U;
}

static void Model_Test(const SensorImuProfile *profile)
{
    MockBus mock;
    SensorImu imu;
    SensorImuSample sample;
    uint64_t epoch;
    uint32_t writes;
    int8_t mapping[3] = {-1, 2, 3};
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    assert(SensorImu_AxisMapSet(&imu, mapping, 5U) == SENSOR_IMU_OK);
    epoch = Mock_Configure(&mock, &imu, 1U);
    assert(SensorImu_Verify(&imu) == SENSOR_IMU_OK);
    mock.registers[profile->data_register + profile->accel_offset +
        ((profile->little_endian != 0U) ? 1U : 0U)] = 0x80U;
    if (profile->invalid_min_sample != 0U)
    {
        assert(SensorImu_Read(&imu, epoch, epoch + 20U, &sample) == SENSOR_IMU_NOT_READY);
        mock.registers[profile->data_register + profile->accel_offset] = 0x7FU;
        mock.registers[profile->data_register + profile->accel_offset + 1U] = 0xFFU;
    }
    assert(SensorImu_Read(&imu, epoch, epoch + 20U, &sample) == SENSOR_IMU_OK);
    assert(imu.state == SENSOR_IMU_READY);
    assert(sample.source_id == 17U && sample.calibration_generation == 5U);
    assert(sample.accel_raw[0] == (profile->invalid_min_sample != 0U ? 32767 : -32768));
    assert(profile->invalid_min_sample != 0U ? sample.accel_b_mps2[0] < 0.0F : sample.accel_b_mps2[0] > 0.0F);
    assert((sample.quality_flags & SENSOR_IMU_QUALITY_CLIPPED) != 0U);
    assert(SensorImu_Read(&imu, epoch, epoch, &sample) == SENSOR_IMU_TIME_ERROR);
    assert(SensorImu_BeginConfigure(&imu, epoch, 1U) == SENSOR_IMU_BAD_STATE);
    assert(SensorImu_AxisMapSet(&imu, mapping, 6U) == SENSOR_IMU_BAD_STATE);
    writes = mock.writes;
    imu.state = SENSOR_IMU_STOPPED;
    epoch = Mock_Configure(&mock, &imu, 0U);
    assert(mock.writes == writes);
    assert(SensorImu_Read(&imu, epoch + 1U, epoch + 2U, &sample) == SENSOR_IMU_OK);
    mock.registers[profile->registers[0].address] ^= profile->registers[0].mask;
    assert(SensorImu_Verify(&imu) == SENSOR_IMU_VERIFY_FAILED);
    assert(imu.state == SENSOR_IMU_FAULT);
    assert(SensorImu_Read(&imu, epoch + 100U, epoch + 100U, &sample) == SENSOR_IMU_NOT_READY);
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    mock.registers[profile->id_register] ^= 1U;
    assert(SensorImu_BeginConfigure(&imu, 1U, 1U) == SENSOR_IMU_WRONG_ID);
    assert(mock.writes == 0U);
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    mock.ignore_writes = 1U;
    assert(SensorImu_BeginConfigure(&imu, 1U, 0U) == SENSOR_IMU_BUSY);
    for (uint8_t i = 0U; i < 36U && imu.state != SENSOR_IMU_FAULT; i++)
    {
        SensorImuResult result = SensorImu_ProcessConfigure(&imu, 2U + i);
        assert(result == SENSOR_IMU_BUSY || result == SENSOR_IMU_VERIFY_FAILED);
    }
    assert(imu.state == SENSOR_IMU_FAULT && mock.writes == 3U);
    printf("%s: ID/reset/readback/SI/clip/epoch/idempotence/errors PASS\n", profile->name);
}

static void Fifo_Test(void)
{
    MockBus mock;
    SensorImu imu;
    SensorImuSample samples[4];
    uint8_t count;
    uint64_t epoch;
    Mock_Init(&mock, &imu, Mpu6000_FifoProfileGet(), SENSOR_BUS_SPI);
    epoch = Mock_Configure(&mock, &imu, 0U);
    mock.registers[0x72] = 0U;
    mock.registers[0x73] = 42U;
    assert(SensorImu_DrainFifo(&imu, epoch, epoch + 200U, samples, 4U, &count) == SENSOR_IMU_OK);
    assert(count == 3U);
    assert(samples[0].sample_timestamp_us == epoch - 10000U);
    assert(samples[1].sample_timestamp_us == epoch - 5000U);
    assert(samples[2].sample_timestamp_us == epoch);
    assert(samples[0].receive_timestamp_us == samples[2].receive_timestamp_us);
    mock.registers[0x72] = 4U;
    mock.registers[0x73] = 0U;
    assert(SensorImu_DrainFifo(&imu, epoch, epoch, samples, 4U, &count) == SENSOR_IMU_FIFO_OVERFLOW);
    assert(imu.state == SENSOR_IMU_FAULT);
}

static void StFifo_Test(const SensorImuProfile *profile)
{
    MockBus mock;
    SensorImu imu;
    SensorImuSample samples[4];
    uint8_t count;
    uint64_t epoch;
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    epoch = Mock_Configure(&mock, &imu, 1U);
    mock.registers[0x1BU] = 4U;
    mock.fifo[0] = 1U << 3U; mock.fifo[7] = 2U << 3U;
    mock.fifo[14] = 1U << 3U; mock.fifo[21] = 2U << 3U;
    mock.fifo[9] = 0x80U;
    assert(SensorImu_DrainFifo(&imu, epoch, epoch+50U, samples, 1U, &count) == SENSOR_IMU_OK);
    assert(count == 1U && samples[0].sample_timestamp_us == epoch-4167U);
    assert(samples[0].accel_raw[0] == -32768);
    assert(samples[0].quality_flags & SENSOR_IMU_QUALITY_CLIPPED);
    assert(samples[0].quality_flags & SENSOR_IMU_QUALITY_TIME_UNCERTAIN);
    assert(mock.registers[0x1BU] == 2U);
    assert(SensorImu_DrainFifo(&imu, epoch, epoch+50U, samples, 1U, &count) == SENSOR_IMU_OK);
    assert(count == 1U && samples[0].sample_timestamp_us == epoch);
    mock.registers[0x1BU] = 1U; mock.fifo[28] = 1U << 3U;
    assert(SensorImu_DrainFifo(&imu, epoch+4167U, epoch+4167U, samples, 1U, &count) == SENSOR_IMU_NOT_READY);
    assert(imu.fifo_pending_mask == 1U && count == 0U);
    mock.registers[0x1BU] = 1U; mock.fifo[35] = 1U << 3U;
    assert(SensorImu_DrainFifo(&imu, epoch+8334U, epoch+8334U, samples, 1U, &count) == SENSOR_IMU_TIME_ERROR);
    assert(imu.state == SENSOR_IMU_FAULT);
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    epoch = Mock_Configure(&mock, &imu, 1U); mock.registers[0x1CU] = 0x40U;
    assert(SensorImu_DrainFifo(&imu, epoch, epoch, samples, 1U, &count) == SENSOR_IMU_FIFO_OVERFLOW);
    printf("%s FIFO tags/pairing/backlog epochs/partial/overflow PASS\n", profile->name);
}

static void IcmFifo_Test(const SensorImuProfile *profile)
{
    MockBus mock; SensorImu imu; SensorImuSample sample[4];
    uint8_t count; uint64_t epoch;
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    epoch = Mock_Configure(&mock, &imu, 1U);
    mock.registers[0x2FU] = 48U;
    for (uint8_t i = 0U; i < 3U; i++)
    {
        uint16_t tick = (uint16_t)(63000U + (uint32_t)i * 5000U);
        mock.fifo[16U*i] = 0x68U;
        mock.fifo[16U*i+1U] = 0x7FU; mock.fifo[16U*i+2U] = 0xFFU;
        mock.fifo[16U*i+13U] = 2U;
        mock.fifo[16U*i+14U] = (uint8_t)(tick >> 8U);
        mock.fifo[16U*i+15U] = (uint8_t)tick;
    }
    assert(SensorImu_DrainFifo(&imu, epoch, epoch+100U, sample, 1U, &count) == SENSOR_IMU_OK);
    assert(count == 1U && sample[0].sample_timestamp_us == epoch-10000U);
    assert(sample[0].accel_raw[0] == 32767 && sample[0].temperature_c > 25.96F);
    mock.registers[0x2FU] = 32U;
    /* The MCU polls 1 ms later; the physical sample is still exactly 5 ms newer. */
    assert(SensorImu_DrainFifo(&imu, epoch+1000U, epoch+1000U, sample, 1U, &count) == SENSOR_IMU_OK);
    assert(sample[0].sample_timestamp_us == epoch-5000U);
    mock.registers[0x2FU] = 16U;
    assert(SensorImu_DrainFifo(&imu, epoch+2000U, epoch+2000U, sample, 1U, &count) == SENSOR_IMU_OK);
    assert(sample[0].sample_timestamp_us == epoch);
    mock.fifo_cursor = 32U;
    assert(SensorImu_DrainFifo(&imu, epoch+3000U, epoch+3000U, sample, 1U, &count) == SENSOR_IMU_TIME_ERROR);
    assert(imu.state == SENSOR_IMU_FAULT && count == 0U);
    Mock_Init(&mock, &imu, profile, SENSOR_BUS_I2C);
    epoch = Mock_Configure(&mock, &imu, 1U); mock.registers[0x2FU] = 16U;
    mock.fifo[0] = 0x78U;
    assert(SensorImu_DrainFifo(&imu, epoch, epoch, sample, 1U, &count) == SENSOR_IMU_VERIFY_FAILED);
    printf("%s FIFO native tick/wrap/backlog/header rejection PASS\n", profile->name);
}

static void HighG_Test(void)
{
    MockBus mock;
    SensorImu imu;
    SensorHighGState state = {0};
    SensorHighGSample high_g;
    SensorImuSample low_g;
    uint64_t epoch;
    Mock_Init(&mock, &imu, Lsm6Dsv320X_ProfileGet(), SENSOR_BUS_I2C);
    epoch = Mock_Configure(&mock, &imu, 1U);
    assert(mock.registers[0x4EU] == 0x9CU);
    mock.registers[0x1EU] = 0x0BU;
    mock.registers[0x35U] = 0x80U;
    assert(SensorHighG_ReadLsm6Dsv320X(&imu, &state, epoch, epoch, &high_g) == SENSOR_IMU_OK);
    assert(high_g.raw[0] == -32768 && high_g.accel_b_mps2[0] < -3000.0F);
    assert(high_g.range_g == 320.0F && high_g.quality_flags & SENSOR_IMU_QUALITY_CLIPPED);
    assert(SensorImu_Read(&imu, epoch, epoch, &low_g) == SENSOR_IMU_OK);
    assert(low_g.accel_raw[0] == 0 && !(low_g.quality_flags & SENSOR_IMU_QUALITY_CLIPPED));
    assert(SensorHighG_ReadLsm6Dsv320X(&imu, &state, epoch, epoch, &high_g) == SENSOR_IMU_TIME_ERROR);
    assert(SensorImu_Stop(&imu) == SENSOR_IMU_OK && mock.registers[0x4EU] == 4U);
    assert(SensorHighG_ReadLsm6Dsv320X(&imu, &state, epoch+1U, epoch+1U, &high_g) == SENSOR_IMU_NOT_READY);
    puts("LSM6DSV320X independent high-g/readback/range/clip/stop PASS");
}

int main(void)
{
    const SensorImuProfile *profiles[8] = {Mpu6000_ProfileGet(), Mpu6050_ProfileGet(),
        Mpu6500_ProfileGet(), Mpu9250_ProfileGet(), Lsm6Dsv32X_ProfileGet(), Lsm6Dsv320X_ProfileGet(),
        Icm42605_ProfileGet(), Icm42688P_ProfileGet()};
    for (uint8_t i = 0U; i < 8U; i++) { Model_Test(profiles[i]); }
    Fifo_Test();
    StFifo_Test(Lsm6Dsv32X_ProfileGet());
    StFifo_Test(Lsm6Dsv320X_ProfileGet());
    IcmFifo_Test(Icm42605_ProfileGet());
    IcmFifo_Test(Icm42688P_ProfileGet());
    HighG_Test();
    puts("sensor model mock suite PASS (HARDWARE_UNVERIFIED)");
    return 0;
}
