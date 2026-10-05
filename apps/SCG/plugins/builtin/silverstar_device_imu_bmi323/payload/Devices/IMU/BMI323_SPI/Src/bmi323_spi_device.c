#include "bmi323_spi_device.h"
#include "silverstar_assert.h"

/* Bosch BMI323_SPI_SensorAPI b3033e78, bmi3_soft_reset / bmi323_spi_init.
 * Word addresses are not byte offsets. Bus callbacks remove protocol dummy
 * bytes; no firmware blob is needed for this documented feature-engine boot. */
static SensorImuResult Bmi323Spi_Prepare(SensorImu *imu, uint64_t now_us)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t bytes[2];
    if (imu->model_phase == 0U)
    {
        if (imu->model_reset == 0U)
        {
            if (SensorRegister_Read(&imu->bus, 0x11U, bytes, 2U) != SENSOR_BUS_OK)
            { return SENSOR_IMU_BUS_ERROR; }
            if ((bytes[0] & 1U) != 0U) { return SENSOR_IMU_OK; }
        }
        bytes[0] = 0xAFU; bytes[1] = 0xDEU;
        if (SensorRegister_Write(&imu->bus, 0x7EU, bytes, 2U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->volatile_writes++;
        imu->model_phase = 1U;
        imu->deadline_us = now_us + 1500U;
        return SENSOR_IMU_BUSY;
    }
    if (imu->model_phase == 1U)
    {
        /* Bosch bmi3_soft_reset: a dummy CHIP_ID read reselects SPI after reset. */
        if ((imu->bus.kind == SENSOR_BUS_SPI) &&
            (SensorRegister_Read(&imu->bus, 0x00U, bytes, 2U) != SENSOR_BUS_OK))
        { return SENSOR_IMU_BUS_ERROR; }
        bytes[0] = 0x2CU; bytes[1] = 1U;
        if (SensorRegister_Write(&imu->bus, 0x12U, bytes, 2U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        bytes[0] = 1U; bytes[1] = 0U;
        if (SensorRegister_Write(&imu->bus, 0x14U, bytes, 2U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        if (SensorRegister_Write(&imu->bus, 0x40U, bytes, 2U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->volatile_writes += 3U;
        imu->model_phase = 2U;
    }
    if (SensorRegister_Read(&imu->bus, 0x11U, bytes, 2U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if ((bytes[0] & 1U) != 0U) { return SENSOR_IMU_OK; }
    imu->retries++;
    if (imu->retries >= 10U) { return SENSOR_IMU_TIMEOUT; }
    imu->deadline_us = now_us + 100000U;
    return SENSOR_IMU_BUSY;
}

static SensorImuResult Bmi323Spi_FrameRead(SensorImu *imu, uint8_t *frame)
{
    uint8_t errors[2];
    if (SensorRegister_Read(&imu->bus, 0x01U, errors, 2U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if ((errors[0] & 0x61U) != 0U) { return SENSOR_IMU_VERIFY_FAILED; }
    return (SensorRegister_Read(&imu->bus, 0x03U, frame, 14U) == SENSOR_BUS_OK) ?
        SENSOR_IMU_OK : SENSOR_IMU_BUS_ERROR;
}

static const SensorImuProfile s_profile =
{
    .name = "BMI323_SPI", .register_width = 2U, .i2c_dummy_bytes = 2U, .spi_dummy_bytes = 1U,
    .prepare = Bmi323Spi_Prepare, .frame_read = Bmi323Spi_FrameRead,
    .id_register = 0x00U, .expected_id = 0x43U,
    .power_register = 0x20U, .stop_value = 0U,
    .second_power_register = 0x21U, .second_stop_value = 0U,
    .data_register = 0x03U, .status_register = 0x02U, .ready_mask = 0xC0U,
    .sample_length = 14U, .accel_offset = 0U, .gyro_offset = 6U,
    .temperature_offset = 12U, .little_endian = 1U, .spi_supported = 1U,
    .settle_wait_us = 100000U, .sample_period_us = 5000U,
    .accel_scale_mps2 = 16.0F * 9.80665F / 32768.0F,
    .gyro_scale_radps = 2000.0F * 0.017453292519943295F / 32768.0F,
    .temperature_scale_c = 1.0F / 512.0F, .temperature_offset_c = 23.0F,
    .fifo_count_register = 0x15U, .fifo_data_register = 0x16U,
    .fifo_frame_length = 16U, .fifo_format = 4U, .fifo_capacity = 2048U,
    .register_count = 5U,
    .registers = {{0x36U, 0x0F01U, 0x0F01U}, {0x20U, 0x40B9U, 0x77FFU},
        {0x21U, 0x40C9U, 0x77FFU}, {0x38U, 5U, 7U}, {0x3BU, 0x0500U, 0x0F00U}}
};

const SensorImuProfile *Bmi323Spi_ProfileGet(void)
{
    return &s_profile;
}
