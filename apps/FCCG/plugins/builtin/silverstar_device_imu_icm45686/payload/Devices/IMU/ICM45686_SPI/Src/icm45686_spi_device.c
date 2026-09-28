#include "icm45686_spi_device.h"
#include "silverstar_assert.h"

/* TDK official motion.mcu.icm45686.driver 0a5bed6975b5cdee, DS-000577.
 * Preserve interface pad settings across reset. Indirect accesses are split
 * across scheduler calls with >=4 us settling, never use the 426xx bank map. */
static SensorImuResult Icm45686_Reset(SensorImu *imu, uint64_t now_us)
{
    uint8_t value = 2U;
    if (SensorRegister_Read(&imu->bus, 0x2DU, &imu->model_saved[0], 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Read(&imu->bus, 0x32U, &imu->model_saved[1], 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Write(&imu->bus, 0x7FU, &value, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    imu->volatile_writes++;
    imu->model_phase = 1U;
    imu->deadline_us = now_us + 1000U;
    return SENSOR_IMU_BUSY;
}

static SensorImuResult Icm45686_Restore(SensorImu *imu)
{
    uint8_t value;
    if (SensorRegister_Write(&imu->bus, 0x32U, &imu->model_saved[1], 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Write(&imu->bus, 0x2DU, &imu->model_saved[0], 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    imu->volatile_writes += 2U;
    if (SensorRegister_Read(&imu->bus, 0x19U, &value, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    return ((value & 0x80U) != 0U) ? SENSOR_IMU_OK : SENSOR_IMU_TIMEOUT;
}

static SensorImuResult Icm45686_Prepare(SensorImu *imu, uint64_t now_us)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t bytes[3] = {0xA2U, 0x67U, 0U};
    uint8_t expected;
    if ((imu->model_phase == 0U) && (imu->model_reset != 0U))
    { return Icm45686_Reset(imu, now_us); }
    if (imu->model_phase == 1U)
    {
        SensorImuResult result = Icm45686_Restore(imu);
        if (result != SENSOR_IMU_OK) { return result; }
    }
    if (imu->model_phase <= 1U)
    {
        imu->model_saved[2] = 0U;
        if (SensorRegister_Write(&imu->bus, 0x7CU, bytes, 2U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->model_phase = 2U;
        imu->deadline_us = now_us + 4U;
        return SENSOR_IMU_BUSY;
    }
    bytes[1] = (imu->model_saved[2] == 0U) ? 0x67U : 0x58U;
    if ((imu->model_phase == 4U) || (imu->model_phase == 5U))
    {
        if (SensorRegister_Write(&imu->bus, 0x7CU, bytes, 2U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->model_phase = (imu->model_phase == 4U) ? 3U : 2U;
        imu->deadline_us = now_us + 4U;
        return SENSOR_IMU_BUSY;
    }
    if (SensorRegister_Read(&imu->bus, 0x7EU, &bytes[2], 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    /* Independent indirect registers: little endian in SREG_CTRL_A;
     * timestamp enabled, FSYNC disabled in SMC_CONTROL_0. Preserve other bits. */
    expected = (imu->model_saved[2] == 0U) ? (uint8_t)(bytes[2] & (uint8_t)~2U) :
        (uint8_t)((bytes[2] & (uint8_t)~3U) | 1U);
    if (bytes[2] == expected)
    {
        if (imu->model_saved[2] != 0U) { return SENSOR_IMU_OK; }
        imu->model_saved[2] = 1U;
        imu->model_phase = 5U;
        return SENSOR_IMU_BUSY;
    }
    if (imu->model_phase == 3U) { return SENSOR_IMU_VERIFY_FAILED; }
    bytes[2] = expected;
    if (SensorRegister_Write(&imu->bus, 0x7CU, bytes, 3U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    imu->volatile_writes++;
    /* Rewrite address on the next call, after the required bus delay. */
    imu->model_phase = 4U;
    imu->deadline_us = now_us + 4U;
    return SENSOR_IMU_BUSY;
}

static const SensorImuProfile s_profile =
{
    .name = "ICM45686_SPI", .prepare = Icm45686_Prepare,
    .id_register = 0x72U, .expected_id = 0xE9U,
    .power_register = 0x10U, .stop_value = 0U,
    .data_register = 0U, .status_register = 0x19U, .ready_mask = 4U,
    .sample_length = 14U, .accel_offset = 0U, .gyro_offset = 6U,
    .temperature_offset = 12U, .little_endian = 1U,
    .invalid_min_sample = 1U, .spi_supported = 1U,
    .settle_wait_us = 100000U, .sample_period_us = 5000U,
    .accel_scale_mps2 = 16.0F * 9.80665F / 32768.0F,
    .gyro_scale_radps = 2000.0F * 0.017453292519943295F / 32768.0F,
    .temperature_scale_c = 1.0F / 128.0F, .temperature_offset_c = 25.0F,
    .fifo_count_register = 0x12U, .fifo_data_register = 0x14U,
    .fifo_frame_length = 16U, .fifo_format = 3U, .fifo_capacity = 2048U,
    .register_count = 10U,
    .registers = {{0x1DU, 0x47U, 0xFFU},
        {0x1BU, 0x18U, 0x7FU}, {0x1CU, 0x18U, 0xFFU},
        {0x23U, 0U, 0x60U}, {0x28U, 0U, 0xFFU}, {0x22U, 2U, 0x3FU},
        {0x21U, 7U, 0x3FU}, {0x16U, 4U, 4U}, {0x18U, 5U, 7U},
        {0x10U, 0x0FU, 0x0FU}}
};

const SensorImuProfile *Icm45686Spi_ProfileGet(void)
{
    return &s_profile;
}
