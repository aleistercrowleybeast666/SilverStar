#include "mpu6000_device.h"

/* Model-specific register evidence: https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map1.pdf
 * Raw data only; no DMP/SFLP, OTP, factory offset or NVM writes. */
static const SensorImuProfile s_fifo_profile =
{
    .name = "MPU6000",
    .id_register = 117U,
    .reset_register = 107U,
    .reset_value = 128U,
    .reset_mask = 128U,
    .power_register = 107U,
    .stop_value = 64U,
    .data_register = 59U,
    .status_register = 58U,
    .ready_mask = 1U,
    .sample_length = 14U,
    .accel_offset = 0U,
    .gyro_offset = 8U,
    .temperature_offset = 6U,
    .reset_wait_us = 100000U,
    .settle_wait_us = 100000U,
    .sample_period_us = 5000U,
    .accel_scale_mps2 = (16.0F * 9.80665F / 32768.0F),
    .gyro_scale_radps = (2000.0F * 0.017453292519943295F / 32768.0F),
    .fifo_count_register = 114U,
    .fifo_data_register = 116U,
    .fifo_frame_length = 14U,
    .fifo_capacity = 1024U,
    .expected_id = 104U,
    .spi_supported = 1U,
    .temperature_scale_c = (1.0F / 340.0F),
    .temperature_offset_c = 36.53F,
    .register_count = 9U,
    .registers = {
        {0x6BU, 0x01U, 0x7FU},
        {0x6CU, 0x00U, 0x3FU},
        {0x19U, 0x04U, 0xFFU},
        {0x1AU, 0x03U, 0x07U},
        {0x1BU, 0x18U, 0xFBU},
        {0x1CU, 0x18U, 0xF8U},
        {0x23U, 0xF8U, 0xFFU},
        {0x6AU, 0x40U, 0xE0U},
        {0x38U, 0x01U, 0x11U}
    }
};

static const SensorImuProfile s_profile =
{
    .name = "MPU6000",
    .id_register = 117U,
    .reset_register = 107U,
    .reset_value = 128U,
    .reset_mask = 128U,
    .power_register = 107U,
    .stop_value = 64U,
    .data_register = 59U,
    .status_register = 58U,
    .ready_mask = 1U,
    .sample_length = 14U,
    .accel_offset = 0U,
    .gyro_offset = 8U,
    .temperature_offset = 6U,
    .reset_wait_us = 100000U,
    .settle_wait_us = 100000U,
    .sample_period_us = 5000U,
    .accel_scale_mps2 = (16.0F * 9.80665F / 32768.0F),
    .gyro_scale_radps = (2000.0F * 0.017453292519943295F / 32768.0F),
    .fifo_count_register = 114U,
    .fifo_data_register = 116U,
    .fifo_frame_length = 0U,
    .fifo_capacity = 1024U,
    .expected_id = 104U,
    .spi_supported = 1U,
    .temperature_scale_c = (1.0F / 340.0F),
    .temperature_offset_c = 36.53F,
    .register_count = 9U,
    .registers = {
        {0x6BU, 0x01U, 0x7FU},
        {0x6CU, 0x00U, 0x3FU},
        {0x19U, 0x04U, 0xFFU},
        {0x1AU, 0x03U, 0x07U},
        {0x1BU, 0x18U, 0xFBU},
        {0x1CU, 0x18U, 0xF8U},
        {0x23U, 0x00U, 0xFFU},
        {0x6AU, 0x00U, 0xE0U},
        {0x38U, 0x01U, 0x11U}
    }
};

const SensorImuProfile *Mpu6000_ProfileGet(void)
{
    return &s_profile;
}

const SensorImuProfile *Mpu6000_FifoProfileGet(void)
{
    return &s_fifo_profile;
}
