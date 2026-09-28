#include "bmi088_device.h"
#include "silverstar_assert.h"

/* Bosch BMI08x_SensorAPI c1ed227e. Logical bit 8 selects the gyro's
 * separate address/CS. This polling profile exposes unsynchronized clocks
 * as time uncertain, never falsely advertises hardware data synchronization. */
static SensorImuResult Bmi088_Prepare(SensorImu *imu, uint64_t now_us)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t value;
    if (imu->model_phase == 0U)
    {
        if (SensorRegister_Read(&imu->bus, 0x100U, &value, 1U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        if (value != 0x0FU) { return SENSOR_IMU_WRONG_ID; }
        if (imu->model_reset == 0U) { return SENSOR_IMU_OK; }
        value = 0xB6U;
        if (SensorRegister_Write(&imu->bus, 0x7EU, &value, 1U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        if (SensorRegister_Write(&imu->bus, 0x114U, &value, 1U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->volatile_writes += 2U;
        imu->model_phase = 1U;
        imu->deadline_us = now_us + 30000U;
        return SENSOR_IMU_BUSY;
    }
    if (SensorRegister_Read(&imu->bus, 0x100U, &value, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (value != 0x0FU) { return SENSOR_IMU_WRONG_ID; }
    return SensorImu_Probe(imu);
}

static SensorImuResult Bmi088_FrameRead(SensorImu *imu, uint8_t *frame)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t value;
    uint8_t temperature[2];
    int32_t temp;
    if (SensorRegister_Read(&imu->bus, 0x10AU, &value, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if ((value & 0x80U) == 0U) { return SENSOR_IMU_NOT_READY; }
    if (SensorRegister_Read(&imu->bus, 0x12U, frame, 6U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Read(&imu->bus, 0x102U, &frame[6], 6U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Read(&imu->bus, 0x22U, temperature, 2U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    temp = (int32_t)temperature[0] * 8L + (temperature[1] >> 5U);
    if (temp == 1024L) { return SENSOR_IMU_NOT_READY; }
    if (temp > 1023L) { temp -= 2048L; }
    frame[12] = (uint8_t)((uint16_t)temp & 0xFFU);
    frame[13] = (uint8_t)((uint16_t)temp >> 8U);
    return SENSOR_IMU_OK;
}

static const SensorImuProfile s_profile =
{
    .name = "BMI088", .auxiliary_address_7bit = 0x68U, .accel_full_scale_g = 24.0F,
    .spi_dummy_bytes = 1U, .auxiliary_spi_dummy_bytes = 0U,
    .prepare = Bmi088_Prepare, .frame_read = Bmi088_FrameRead,
    .id_register = 0x00U, .expected_id = 0x1EU,
    .power_register = 0x7DU, .stop_value = 0U,
    .second_power_register = 0x111U, .second_stop_value = 0x80U,
    .data_register = 0x12U, .status_register = 0x03U, .ready_mask = 0x80U,
    .sample_length = 14U, .accel_offset = 0U, .gyro_offset = 6U,
    .temperature_offset = 12U, .little_endian = 1U, .spi_supported = 1U,
    .settle_wait_us = 100000U, .sample_period_us = 5000U,
    .accel_scale_mps2 = 24.0F * 9.80665F / 32768.0F,
    .gyro_scale_radps = 2000.0F * 0.017453292519943295F / 32768.0F,
    .temperature_scale_c = 0.125F, .temperature_offset_c = 23.0F,
    .register_count = 13U,
    .registers = {{0x7CU, 0U, 3U}, {0x7DU, 4U, 4U},
        {0x40U, 0xA9U, 0xFFU}, {0x41U, 3U, 3U},
        {0x10FU, 0U, 7U}, {0x110U, 4U, 7U}, {0x111U, 0U, 0xA0U},
        {0x13EU, 0U, 0xC0U}, {0x115U, 0x80U, 0x80U},
        {0x53U, 0x0AU, 0x0FU}, {0x58U, 4U, 4U},
        {0x116U, 1U, 3U}, {0x118U, 1U, 1U}}
};

const SensorImuProfile *Bmi088_ProfileGet(void)
{
    return &s_profile;
}
