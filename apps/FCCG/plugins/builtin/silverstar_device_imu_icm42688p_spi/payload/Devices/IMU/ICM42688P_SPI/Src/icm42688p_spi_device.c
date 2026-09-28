#include "icm42688p_spi_device.h"

/* https://invensense.tdk.com/wp-content/uploads/2021/06/DS-000347-ICM-42688-P-v1.5.pdf; raw 200 Hz, 50 Hz UI filter, no APEX/DMP. */
static const SensorImuProfile s_profile =
{
    .name = "ICM42688P_SPI",
    .id_register = 0x75U, .expected_id = 71U,
    .reset_register = 0x11U, .reset_value = 1U, .reset_mask = 1U,
    .power_register = 0x4EU, .stop_value = 0U,
    .data_register = 0x1DU, .status_register = 0x2DU, .ready_mask = 8U,
    .sample_length = 14U, .accel_offset = 2U, .gyro_offset = 8U,
    .temperature_offset = 0U, .invalid_min_sample = 1U, .spi_supported = 1U,
    .reset_wait_us = 10000U, .settle_wait_us = 100000U, .sample_period_us = 5000U,
    .accel_scale_mps2 = 16.0F * 9.80665F / 32768.0F,
    .gyro_scale_radps = 2000.0F * 0.017453292519943295F / 32768.0F,
    .temperature_scale_c = 1.0F / 132.48F, .temperature_offset_c = 25.0F,
    .fifo_count_register = 0x2EU, .fifo_data_register = 0x30U,
    .fifo_frame_length = 16U, .fifo_format = 2U, .fifo_capacity = 2048U,
    .register_count = 12U,
    .registers = {{0x76U, 0U, 7U}, {0x16U, 0x40U, 0xC0U},
        {0x4CU, 0x30U, 0xF0U}, {0x4DU, 1U, 7U},
        {0x4FU, 7U, 0xEFU}, {0x50U, 7U, 0x6FU},
        {0x52U, 0x33U, 0xFFU}, {0x14U, 3U, 7U}, {0x65U, 8U, 8U}, {0x54U, 1U, 0x1FU}, {0x5FU, 0x0FU, 0x7FU}, {0x4EU, 0x0FU, 0x3FU}}
};
const SensorImuProfile *Icm42688PSpi_ProfileGet(void)
{
    return &s_profile;
}
