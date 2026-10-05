#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "bmi088_device.h"
#include "bmi323_device.h"
#include "icm45686_device.h"
#include "sensor_bmi088_fifo.h"

typedef struct
{
    const SensorImuProfile *profile;
    uint8_t registers[1024];
    uint8_t endian;
    uint8_t timestamp_control;
    uint8_t feature_stuck;
    uint8_t reset_stuck;
    uint16_t indirect;
    uint32_t writes;
    uint8_t fifo[48];
    uint16_t fifo_cursor;
    uint32_t fifo_count_reads;
} Mock;

static uint16_t Mock_Address(const Mock *mock, uint16_t address)
{
    return (mock->profile->register_width == 2U) ? address * 2U : address;
}

static SensorBusResult Mock_Read(void *context, uint16_t address, uint8_t *data,
    uint16_t length, uint32_t timeout_us)
{
    Mock *mock = context;
    uint16_t offset = Mock_Address(mock, address);
    assert(timeout_us == 2000U && offset + length <= sizeof(mock->registers));
    if (((mock->profile->fifo_frame_length != 0U) && address == mock->profile->fifo_data_register) ||
        (mock->profile == Bmi088_ProfileGet() && (address == 0x26U || address == 0x13FU)))
    {
        assert(mock->fifo_cursor + length <= sizeof(mock->fifo));
        memcpy(data, &mock->fifo[mock->fifo_cursor], length); mock->fifo_cursor += length;
    }
    else if (mock->profile == Icm45686_ProfileGet() && address == 0x7EU)
    {
        assert(length == 1U);
        assert(mock->indirect == 0xA267U || mock->indirect == 0xA258U);
        data[0] = (mock->indirect == 0xA267U) ? mock->endian : mock->timestamp_control;
    }
    else { memcpy(data, &mock->registers[offset], length); }
    if (address == mock->profile->fifo_count_register) { mock->fifo_count_reads++; }
    return SENSOR_BUS_OK;
}

static SensorBusResult Mock_Write(void *context, uint16_t address, const uint8_t *data,
    uint16_t length, uint32_t timeout_us)
{
    Mock *mock = context;
    uint16_t offset = Mock_Address(mock, address);
    assert(timeout_us == 2000U && offset + length <= sizeof(mock->registers));
    if (mock->profile == Icm45686_ProfileGet() && address == 0x7CU)
    {
        assert(length == 2U || length == 3U);
        mock->indirect = ((uint16_t)data[0] << 8U) | data[1];
        if (length == 3U)
        {
            if (mock->indirect == 0xA267U) { mock->endian = data[2]; }
            else { assert(mock->indirect == 0xA258U); mock->timestamp_control = data[2]; }
            mock->writes++;
        }
        return SENSOR_BUS_OK;
    }
    mock->writes++;
    memcpy(&mock->registers[offset], data, length);
    if (mock->profile == Bmi323_ProfileGet() && address == 0x40U && !mock->feature_stuck)
    { mock->registers[0x22U] = 1U; }
    if (mock->profile == Icm45686_ProfileGet() && address == 0x7FU && !mock->reset_stuck)
    { mock->registers[0x19U] = 0x80U; }
    return SENSOR_BUS_OK;
}

static void Mock_Init(Mock *mock, SensorImu *imu, const SensorImuProfile *profile)
{
    SensorRegisterBus bus;
    memset(mock, 0, sizeof(*mock)); mock->profile = profile;
    mock->registers[Mock_Address(mock, profile->id_register)] = profile->expected_id;
    if (profile == Bmi088_ProfileGet()) { mock->registers[0x100U] = 0x0FU; }
    if (profile == Icm45686_ProfileGet()) { mock->endian = 0xA2U; }
    bus.context = mock; bus.read = Mock_Read; bus.write = Mock_Write; bus.kind = SENSOR_BUS_I2C;
    assert(SensorImu_Init(imu, &bus, profile, 31U) == SENSOR_IMU_OK);
}

static SensorImuResult Mock_Configure(SensorImu *imu, uint8_t reset, uint64_t *now)
{
    SensorImuResult result;
    result = SensorImu_BeginConfigure(imu, *now, reset);
    if (result != SENSOR_IMU_BUSY) { return result; }
    for (uint8_t step = 0U; step < 60U; step++)
    {
        *now += 100000U;
        result = SensorImu_ProcessConfigure(imu, *now);
        if (imu->state == SENSOR_IMU_SAMPLE_VERIFY) { return SENSOR_IMU_OK; }
        if (result != SENSOR_IMU_BUSY) { return result; }
    }
    return SENSOR_IMU_TIMEOUT;
}

static void Model_Test(const SensorImuProfile *profile)
{
    Mock mock; SensorImu imu; SensorImuSample sample;
    uint64_t now = 1000000U; uint32_t writes;
    uint16_t data = (profile == Bmi088_ProfileGet()) ? 0x12U : Mock_Address(&(Mock){.profile=profile}, profile->data_register);
    Mock_Init(&mock, &imu, profile);
    assert(Mock_Configure(&imu, 1U, &now) == SENSOR_IMU_OK);
    assert(imu.state == SENSOR_IMU_SAMPLE_VERIFY);
    assert(SensorImu_Verify(&imu) == SENSOR_IMU_OK);
    mock.registers[Mock_Address(&mock, profile->status_register)] = profile->ready_mask;
    mock.registers[data] = 0xFFU; mock.registers[data+1U] = 0x7FU;
    if (profile == Bmi088_ProfileGet())
    {
        assert(SensorImu_Read(&imu, now+1U, now+2U, &sample) == SENSOR_IMU_NOT_READY);
        mock.registers[0x10AU] = 0x80U;
        mock.registers[0x22U] = 0x3EU;
    }
    assert(SensorImu_Read(&imu, now+1U, now+2U, &sample) == SENSOR_IMU_OK);
    assert(sample.accel_raw[0] == 32767);
    assert(sample.quality_flags & SENSOR_IMU_QUALITY_CLIPPED);
    if (profile == Bmi088_ProfileGet()) { assert(sample.temperature_c == 85.0F); }
    writes = mock.writes; imu.state = SENSOR_IMU_STOPPED;
    assert(Mock_Configure(&imu, 0U, &now) == SENSOR_IMU_OK);
    assert(mock.writes == writes);
    mock.registers[Mock_Address(&mock, profile->registers[0].address)] ^= 0xFFU;
    mock.registers[Mock_Address(&mock, profile->registers[0].address)+1U] ^= 0xFFU;
    assert(SensorImu_Verify(&imu) == SENSOR_IMU_VERIFY_FAILED);
    printf("%s: distinct reset/readback/layout/temperature/zero-write restart PASS\n", profile->name);
}

static void Fifo_Test(const SensorImuProfile *profile)
{
    Mock mock; SensorImu imu; SensorImuSample samples[2]; uint8_t count;
    uint64_t now = 1000000U;
    Mock_Init(&mock, &imu, profile);
    assert(Mock_Configure(&imu, 1U, &now) == SENSOR_IMU_OK);
    uint16_t count_reg = Mock_Address(&mock, profile->fifo_count_register);
    mock.registers[count_reg] = (profile->fifo_format == 4U) ? 16U : 2U;
    for (uint8_t i=0U; i<2U; i++)
    {
        uint16_t tick = (uint16_t)(65500U + (uint32_t)i * ((profile->fifo_format == 4U) ? 128U : 5000U));
        uint8_t offset = profile->fifo_format == 4U ? 0U : 1U;
        if (offset) { mock.fifo[16U*i] = 0x68U; }
        mock.fifo[16U*i+offset] = 0xFFU; mock.fifo[16U*i+offset+1U] = 0x7FU;
        mock.fifo[16U*i+14U] = (uint8_t)tick; mock.fifo[16U*i+15U] = (uint8_t)(tick>>8U);
    }
    assert(SensorImu_DrainFifo(&imu, now, now, samples, 1U, &count) == SENSOR_IMU_OK);
    assert(samples[0].sample_timestamp_us == now-5000U && samples[0].accel_raw[0] == 32767);
    mock.registers[count_reg] = (profile->fifo_format == 4U) ? 8U : 1U;
    assert(SensorImu_DrainFifo(&imu, now+1000U, now+1000U, samples, 1U, &count) == SENSOR_IMU_OK);
    assert(samples[0].sample_timestamp_us == now);
    assert(mock.fifo_count_reads == ((profile->fifo_format == 4U) ? 2U : 4U));
    mock.fifo_cursor = 16U;
    assert(SensorImu_DrainFifo(&imu, now+2000U, now+2000U, samples, 1U, &count) == SENSOR_IMU_TIME_ERROR);
    assert(imu.state == SENSOR_IMU_FAULT);
    printf("%s FIFO native time/count/endian/wrap/duplicate PASS\n", profile->name);
}

static void Bmi088Fifo_Test(void)
{
    Mock mock; SensorImu imu; SensorBmi088FifoEvent event; uint64_t now = 1000000U;
    Mock_Init(&mock, &imu, Bmi088_ProfileGet());
    assert(Mock_Configure(&imu, 1U, &now) == SENSOR_IMU_OK);
    assert(SensorBmi088Fifo_Enable(&imu) == SENSOR_IMU_OK);
    assert(imu.profile_verified == 0U && imu.state == SENSOR_IMU_STOPPED);
    assert(mock.registers[0x48U] == 1U && mock.registers[0x49U] == 0x40U);
    assert(mock.registers[0x13EU] == 0x40U);
    mock.registers[0x24U] = 11U;
    mock.fifo[0] = 0x84U; mock.fifo[1] = 0xFFU; mock.fifo[2] = 0x7FU;
    mock.fifo[7] = 0x44U; mock.fifo[8] = 0xFFU; mock.fifo[9] = 0xFEU; mock.fifo[10] = 0xFDU;
    assert(SensorBmi088Fifo_AccelRead(&imu, &event) == SENSOR_IMU_OK);
    assert(event.kind == SENSOR_BMI088_FIFO_ACCEL && event.raw[0] == 32767);
    assert(event.si[0] > 235.0F && event.quality_flags & SENSOR_IMU_QUALITY_CLIPPED);
    assert(SensorBmi088Fifo_AccelRead(&imu, &event) == SENSOR_IMU_OK);
    assert(event.kind == SENSOR_BMI088_FIFO_TIME && event.sensor_ticks == 0xFDFEFFU);
    mock.fifo_cursor = 0U; mock.registers[0x10EU] = 1U;
    mock.fifo[0] = 0U; mock.fifo[1] = 0x80U;
    assert(SensorBmi088Fifo_GyroRead(&imu, &event) == SENSOR_IMU_OK);
    assert(event.kind == SENSOR_BMI088_FIFO_GYRO && event.raw[0] == -32768);
    assert(event.quality_flags & SENSOR_IMU_QUALITY_TIME_UNCERTAIN);
    mock.registers[0x10EU] = 0x80U;
    assert(SensorBmi088Fifo_GyroRead(&imu, &event) == SENSOR_IMU_FIFO_OVERFLOW);
    mock.fifo_cursor = 0U; mock.fifo[0] = 0x40U;
    assert(SensorBmi088Fifo_AccelRead(&imu, &event) == SENSOR_IMU_TIME_ERROR);
    puts("BMI088 independent FIFO/config/readback/tag/time/overflow PASS (no synchronized navigation qualification)");
}

int main(void)
{
    Mock mock; SensorImu imu; uint64_t now = 1000000U;
    Model_Test(Bmi088_ProfileGet()); Model_Test(Bmi323_ProfileGet()); Model_Test(Icm45686_ProfileGet());
    Fifo_Test(Bmi323_ProfileGet()); Fifo_Test(Icm45686_ProfileGet());
    Bmi088Fifo_Test();
    Mock_Init(&mock, &imu, Bmi088_ProfileGet()); mock.registers[0x100U] = 0U;
    assert(Mock_Configure(&imu, 1U, &now) == SENSOR_IMU_WRONG_ID && mock.writes == 0U);
    Mock_Init(&mock, &imu, Bmi323_ProfileGet()); mock.feature_stuck = 1U;
    assert(Mock_Configure(&imu, 1U, &now) == SENSOR_IMU_TIMEOUT);
    Mock_Init(&mock, &imu, Icm45686_ProfileGet()); mock.reset_stuck = 1U;
    assert(Mock_Configure(&imu, 1U, &now) == SENSOR_IMU_TIMEOUT);
    puts("special sensor failure injection PASS (HARDWARE_UNVERIFIED)");
    return 0;
}
