#include "sensor_bmi088_fifo.h"
#include "silverstar_assert.h"
#include <limits.h>
#include <stddef.h>
#include <string.h>

/* Bosch BMI08x SensorAPI c1ed227e: accel tagged byte stream and separate gyro
 * headerless XYZ FIFO. Neither FIFO supplies an authoritative paired epoch. */
SensorImuResult SensorBmi088Fifo_Enable(SensorImu *imu)
{
    static const SensorImuRegister config[4] =
    { {0x45U, 0U, 0xF0U}, {0x48U, 1U, 1U}, {0x49U, 0x40U, 0x4CU}, {0x13EU, 0x40U, 0xC3U} };
    uint8_t index;
    if ((imu == NULL) || (imu->profile == NULL) ||
        (imu->profile->expected_id != 0x1EU) || (imu->profile->auxiliary_address_7bit == 0U))
    { return SENSOR_IMU_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((imu->state == SENSOR_IMU_READY) || (imu->profile_verified == 0U))
    { return SENSOR_IMU_BAD_STATE; }
    for (index = 0U; index < 4U; index++)
    {
        uint8_t value;
        uint8_t expected;
        if (SensorRegister_Read(&imu->bus, config[index].address, &value, 1U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        expected = (uint8_t)((value & (uint8_t)~config[index].mask) | config[index].value);
        if (value != expected)
        {
            if (SensorRegister_Write(&imu->bus, config[index].address, &expected, 1U) != SENSOR_BUS_OK)
            { return SENSOR_IMU_BUS_ERROR; }
            imu->volatile_writes++;
        }
        if (SensorRegister_Read(&imu->bus, config[index].address, &value, 1U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        if (value != expected) { return SENSOR_IMU_VERIFY_FAILED; }
    }
    /* This explicit raw-capture mode is not the default paired-IMU profile. */
    imu->profile_verified = 0U;
    imu->state = SENSOR_IMU_STOPPED;
    return SENSOR_IMU_OK;
}

static void SensorBmi088Fifo_EventInit(const SensorImu *imu,
    SensorBmi088FifoKind kind, SensorBmi088FifoEvent *event)
{
    memset(event, 0, sizeof(*event));
    event->kind = kind;
    event->source_id = imu->source_id;
    event->config_generation = imu->config_generation;
    event->quality_flags = SENSOR_IMU_QUALITY_TIME_UNCERTAIN;
}

static void SensorBmi088Fifo_AxesDecode(const SensorImu *imu,
    const uint8_t *bytes, SensorBmi088FifoEvent *event)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t axis;
    float scale = (event->kind == SENSOR_BMI088_FIFO_ACCEL) ?
        imu->profile->accel_scale_mps2 : imu->profile->gyro_scale_radps;
    for (axis = 0U; axis < 3U; axis++)
    {
        uint16_t bits = (uint16_t)((uint16_t)bytes[2U*axis] | ((uint16_t)bytes[2U*axis+1U] << 8U));
        int32_t signed_value = (bits >= 32768U) ? (int32_t)bits - 65536L : (int32_t)bits;
        event->raw[axis] = (int16_t)signed_value;
        event->si[axis] = (float)signed_value * scale;
        if ((signed_value == INT16_MIN) || (signed_value == INT16_MAX))
        { event->quality_flags |= SENSOR_IMU_QUALITY_CLIPPED; }
        if ((signed_value <= -31129L) || (signed_value >= 31129L))
        { event->quality_flags |= SENSOR_IMU_QUALITY_NEAR_RANGE; }
    }
}

SensorImuResult SensorBmi088Fifo_AccelRead(SensorImu *imu, SensorBmi088FifoEvent *event)
{
    uint8_t bytes[6];
    uint8_t header;
    uint16_t available;
    if ((imu == NULL) || (event == NULL) || (imu->profile == NULL) ||
        (imu->profile->expected_id != 0x1EU) || (imu->profile->auxiliary_address_7bit == 0U))
    { return SENSOR_IMU_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    SensorBmi088Fifo_EventInit(imu, SENSOR_BMI088_FIFO_ACCEL, event);
    if (SensorRegister_Read(&imu->bus, 0x24U, bytes, 2U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    available = (uint16_t)((uint16_t)bytes[0] | ((uint16_t)(bytes[1] & 0x3FU) << 8U));
    if (available == 0U) { return SENSOR_IMU_NOT_READY; }
    if (available >= 1024U) { imu->fifo_overflows++; return SENSOR_IMU_FIFO_OVERFLOW; }
    if (SensorRegister_Read(&imu->bus, 0x26U, &header, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (header == 0x80U) { return SENSOR_IMU_NOT_READY; }
    if ((header == 0x40U) || (header == 0x50U))
    { imu->history_reset = 1U; return SENSOR_IMU_TIME_ERROR; }
    if (header == 0x44U)
    {
        if (SensorRegister_Read(&imu->bus, 0x26U, bytes, 3U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        event->kind = SENSOR_BMI088_FIFO_TIME;
        event->sensor_ticks = (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8U) | ((uint32_t)bytes[2] << 16U);
        return SENSOR_IMU_OK;
    }
    if ((header != 0x84U) || (available < 7U)) { return SENSOR_IMU_VERIFY_FAILED; }
    if (SensorRegister_Read(&imu->bus, 0x26U, bytes, 6U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    SensorBmi088Fifo_AxesDecode(imu, bytes, event);
    return SENSOR_IMU_OK;
}

SensorImuResult SensorBmi088Fifo_GyroRead(SensorImu *imu, SensorBmi088FifoEvent *event)
{
    uint8_t bytes[6];
    uint8_t status;
    if ((imu == NULL) || (event == NULL) || (imu->profile == NULL) ||
        (imu->profile->expected_id != 0x1EU) || (imu->profile->auxiliary_address_7bit == 0U))
    { return SENSOR_IMU_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    SensorBmi088Fifo_EventInit(imu, SENSOR_BMI088_FIFO_GYRO, event);
    if (SensorRegister_Read(&imu->bus, 0x10EU, &status, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if ((status & 0x80U) != 0U) { imu->fifo_overflows++; return SENSOR_IMU_FIFO_OVERFLOW; }
    if ((status & 0x7FU) == 0U) { return SENSOR_IMU_NOT_READY; }
    if (SensorRegister_Read(&imu->bus, 0x13FU, bytes, 6U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    SensorBmi088Fifo_AxesDecode(imu, bytes, event);
    return SENSOR_IMU_OK;
}
