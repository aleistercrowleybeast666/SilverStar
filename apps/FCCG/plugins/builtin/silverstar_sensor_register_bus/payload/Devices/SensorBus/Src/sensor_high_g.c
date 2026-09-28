#include "sensor_imu.h"

#include <math.h>
#include <stddef.h>
#include <string.h>
#include "silverstar_assert.h"

static void SensorHighG_AxesDecode(const SensorImu *imu, const uint8_t data[6],
    SensorHighGSample *sample)
{
    uint8_t axis;
    SILVERSTAR_ASSERT_OBJECT(sample, SensorHighGSample, SILVERSTAR_ASSERT_MODULE_DEVICE);
    for (axis = 0U; axis < 3U; axis++)
    {
        int8_t map = imu->axis_map[axis];
        uint8_t source = (uint8_t)(((map < 0) ? -map : map) - 1);
        uint16_t raw = (uint16_t)((uint16_t)data[source * 2U] | ((uint16_t)data[source * 2U + 1U] << 8U));
        int32_t value = (raw >= 32768U) ? (int32_t)raw - 65536L : (int32_t)raw;
        float magnitude_g;
        sample->raw[axis] = (int16_t)value;
        /* Official ST lsm6dsv320x_from_fs320_to_mg: 10.417 mg/LSB. */
        sample->accel_b_mps2[axis] = (float)value * (10.417F * 0.00980665F) * ((map < 0) ? -1.0F : 1.0F);
        magnitude_g = fabsf((float)value * 0.010417F);
        if (magnitude_g >= 304.0F) { sample->quality_flags |= SENSOR_IMU_QUALITY_NEAR_RANGE; }
        if ((magnitude_g >= 320.0F) || (value == -32768L) || (value == 32767L))
        { sample->quality_flags |= SENSOR_IMU_QUALITY_CLIPPED; }
    }
}

SensorImuResult SensorHighG_ReadLsm6Dsv320X(SensorImu *imu,
    SensorHighGState *state, uint64_t sample_us, uint64_t receive_us,
    SensorHighGSample *sample)
{
    uint8_t control;
    uint8_t status;
    uint8_t data[6];
    if ((imu == NULL) || (state == NULL) || (sample == NULL) || (imu->profile == NULL))
    { return SENSOR_IMU_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (imu->profile->expected_id != 0x73U) { return SENSOR_IMU_UNSUPPORTED; }
    if (imu->profile_verified == 0U) { return SENSOR_IMU_NOT_READY; }
    if (state->config_generation != imu->config_generation)
    {
        memset(state, 0, sizeof(*state)); state->config_generation = imu->config_generation;
    }
    if ((sample_us == 0U) || (receive_us < sample_us) || (sample_us <= state->last_epoch_us))
    { return SENSOR_IMU_TIME_ERROR; }
    if (SensorRegister_Read(&imu->bus, 0x4EU, &control, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if ((control & 0xBFU) != 0x9CU) { return SENSOR_IMU_VERIFY_FAILED; }
    if (SensorRegister_Read(&imu->bus, 0x1EU, &status, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if ((status & 8U) == 0U) { return SENSOR_IMU_NOT_READY; }
    if (SensorRegister_Read(&imu->bus, 0x34U, data, 6U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = sample_us; sample->receive_timestamp_us = receive_us;
    sample->range_g = 320.0F; sample->source_id = imu->source_id;
    sample->config_generation = imu->config_generation;
    sample->quality_flags = SENSOR_IMU_QUALITY_TIME_UNCERTAIN;
    if (state->last_epoch_us == 0U) { sample->quality_flags |= SENSOR_IMU_QUALITY_HISTORY_RESET; }
    SensorHighG_AxesDecode(imu, data, sample);
    state->last_epoch_us = sample_us; sample->sequence = ++state->sequence;
    return SENSOR_IMU_OK;
}
