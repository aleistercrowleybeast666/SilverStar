#include "lsm6dsv32x_spi_device.h"

/* Model-specific register evidence: https://github.com/STMicroelectronics/lsm6dsv32x_spi-pid
 * Raw data only; no DMP/SFLP, OTP, factory offset or NVM writes. */
static const SensorImuProfile s_profile =
{
    .name = "LSM6DSV32X_SPI",
    .id_register = 15U,
    .expected_id = 112U,
    .reset_register = 18U,
    .reset_value = 1U,
    .reset_mask = 1U,
    .power_register = 16U,
    .stop_value = 0U,
    .second_power_register = 17U,
    .second_stop_value = 0U,
    .data_register = 32U,
    .status_register = 30U,
    .ready_mask = 3U,
    .sample_length = 14U,
    .fifo_frame_length = 14U, .fifo_format = 1U,
    .fifo_count_register = 0x1BU, .fifo_data_register = 0x78U,
    .accel_offset = 8U,
    .gyro_offset = 2U,
    .temperature_offset = 0U,
    .little_endian = 1U,
    .spi_supported = 1U,
    .reset_wait_us = 10000U,
    .settle_wait_us = 100000U,
    .sample_period_us = 4167U,
    .accel_scale_mps2 = (0.488F * 0.00980665F),
    .gyro_scale_radps = (0.070F * 0.017453292519943295F),
    .temperature_scale_c = (1.0F / 256.0F),
    .temperature_offset_c = 25.0F,
    .register_count = 8U,
    .registers = {
        {0x12U, 0x44U, 0x45U},
        {0x0AU, 0x06U, 0xFFU},
        {0x09U, 0x77U, 0xFFU},
        {0x15U, 0x04U, 0x07U},
        {0x17U, 0x02U, 0x03U},
        {0x10U, 0x07U, 0x7FU},
        {0x11U, 0x07U, 0x7FU},
        {0x0DU, 0x03U, 0x03U}
    }
};

const SensorImuProfile *Lsm6Dsv32XSpi_ProfileGet(void)
{
    return &s_profile;
}
