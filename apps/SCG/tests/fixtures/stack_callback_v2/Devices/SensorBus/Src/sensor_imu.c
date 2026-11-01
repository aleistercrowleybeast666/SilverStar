#include "sensor_imu.h"
#include "silverstar_assert.h"

#include <limits.h>
#include <math.h>
#include <stddef.h>
#include <string.h>

#define SENSOR_IMU_RETRY_MAX 3U
#define SENSOR_IMU_SAMPLE_TIMEOUT_US 1000000U
#define SENSOR_IMU_NEAR_RANGE_RAW 31129
#define SENSOR_IMU_FRAME_MAX 16U

static SensorImuResult SensorImu_Fail(SensorImu *imu, SensorImuResult result)
{
    imu->last_result = result;
    imu->state = SENSOR_IMU_FAULT;
    imu->profile_verified = 0U;
    return result;
}

static SensorImuResult SensorImu_RegisterMatch(SensorImu *imu,
    const SensorImuRegister *reg, uint8_t apply)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t bytes[2] = {0U, 0U};
    uint16_t actual;
    uint16_t expected;
    uint8_t width = (imu->profile->register_width == 2U) ? 2U : 1U;

    if (SensorRegister_Read(&imu->bus, reg->address, bytes, width) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SENSOR_IMU_BUS_ERROR;
    }
    actual = (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
    if ((actual & reg->mask) == (reg->value & reg->mask))
    {
        return SENSOR_IMU_OK;
    }
    if (apply == 0U)
    {
        imu->verify_errors++;
        return SENSOR_IMU_VERIFY_FAILED;
    }
    expected = (uint16_t)((actual & (uint16_t)~reg->mask) | (reg->value & reg->mask));
    bytes[0] = (uint8_t)expected;
    bytes[1] = (uint8_t)(expected >> 8U);
    if (SensorRegister_Write(&imu->bus, reg->address, bytes, width) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SENSOR_IMU_BUS_ERROR;
    }
    imu->volatile_writes++;
    if (SensorRegister_Read(&imu->bus, reg->address, bytes, width) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SENSOR_IMU_BUS_ERROR;
    }
    actual = (uint16_t)((uint16_t)bytes[0] | ((uint16_t)bytes[1] << 8U));
    if ((actual & reg->mask) != (reg->value & reg->mask))
    {
        imu->verify_errors++;
        return SENSOR_IMU_VERIFY_FAILED;
    }
    return SENSOR_IMU_OK;
}

static int16_t SensorImu_Int16Read(const uint8_t *data, uint8_t little_endian)
{
    uint16_t raw;
    int32_t value;

    raw = (little_endian != 0U) ?
        (uint16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8U)) :
        (uint16_t)(((uint16_t)data[0] << 8U) | (uint16_t)data[1]);
    value = (raw >= 32768U) ? (int32_t)raw - 65536L : (int32_t)raw;
    return (int16_t)value;
}

static uint32_t SensorImu_RangeFlags(int16_t value)
{
    if ((value == INT16_MIN) || (value == INT16_MAX))
    {
        return SENSOR_IMU_QUALITY_CLIPPED | SENSOR_IMU_QUALITY_NEAR_RANGE;
    }
    if ((value >= SENSOR_IMU_NEAR_RANGE_RAW) ||
        (value <= -SENSOR_IMU_NEAR_RANGE_RAW))
    {
        return SENSOR_IMU_QUALITY_NEAR_RANGE;
    }
    return 0U;
}

static SensorImuResult SensorImu_SampleDecode(SensorImu *imu,
    const uint8_t *frame, uint64_t sample_us, uint64_t receive_us,
    SensorImuSample *sample)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t axis;
    const SensorImuProfile *profile = imu->profile;

    if ((sample_us == 0U) || (receive_us < sample_us) ||
        ((imu->sample_count != 0U) && (sample_us <= imu->last_sample_us)))
    {
        imu->time_errors++;
        return SENSOR_IMU_TIME_ERROR;
    }
    memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = sample_us;
    sample->receive_timestamp_us = receive_us;
    sample->source_id = imu->source_id;
    sample->config_generation = imu->config_generation;
    sample->calibration_generation = imu->calibration_generation;
    for (axis = 0U; axis < SENSOR_IMU_AXIS_COUNT; axis++)
    {
        int8_t map = imu->axis_map[axis];
        uint8_t source = (uint8_t)(((map < 0) ? -map : map) - 1);
        float sign = (map < 0) ? -1.0F : 1.0F;
        int16_t accel = SensorImu_Int16Read(
            &frame[profile->accel_offset + 2U * source], profile->little_endian);
        int16_t gyro = SensorImu_Int16Read(
            &frame[profile->gyro_offset + 2U * source], profile->little_endian);
        if ((profile->invalid_min_sample != 0U) &&
            ((accel == INT16_MIN) || (gyro == INT16_MIN)))
        {
            return SENSOR_IMU_NOT_READY;
        }
        sample->accel_raw[axis] = accel;
        sample->gyro_raw[axis] = gyro;
        sample->accel_b_mps2[axis] = sign * (float)accel * profile->accel_scale_mps2;
        sample->gyro_b_radps[axis] = sign * (float)gyro * profile->gyro_scale_radps;
        sample->quality_flags |= SensorImu_RangeFlags(accel) | SensorImu_RangeFlags(gyro);
    }
    sample->temperature_c = (float)SensorImu_Int16Read(
        &frame[profile->temperature_offset], profile->little_endian) *
        profile->temperature_scale_c + profile->temperature_offset_c;
    if (imu->history_reset != 0U)
    {
        sample->quality_flags |= SENSOR_IMU_QUALITY_HISTORY_RESET;
        imu->history_reset = 0U;
    }
    imu->sample_count++;
    sample->sequence = imu->sample_count;
    imu->last_sample_us = sample_us;
    imu->last_result = SENSOR_IMU_OK;
    imu->state = SENSOR_IMU_READY;
    return SENSOR_IMU_OK;
}

SensorImuResult SensorImu_Init(SensorImu *imu, const SensorRegisterBus *bus,
    const SensorImuProfile *profile, uint32_t source_id)
{
    if ((imu == NULL) || (bus == NULL) || (profile == NULL) ||
        (bus->read == NULL) || (bus->write == NULL) ||
        (profile->register_count > SENSOR_IMU_CONFIG_MAX) ||
        (profile->sample_length > SENSOR_IMU_FRAME_MAX) ||
        (profile->fifo_frame_length > SENSOR_IMU_FRAME_MAX) ||
        (profile->fifo_format > 4U) ||
        ((uint16_t)profile->accel_offset + 6U > profile->sample_length) ||
        ((uint16_t)profile->gyro_offset + 6U > profile->sample_length) ||
        ((uint16_t)profile->temperature_offset + 2U > profile->sample_length) ||
        (profile->sample_period_us == 0U) ||
        !isfinite(profile->accel_scale_mps2) || !isfinite(profile->gyro_scale_radps) ||
        !isfinite(profile->temperature_scale_c) || !isfinite(profile->temperature_offset_c) ||
        (profile->accel_scale_mps2 <= 0.0F) || (profile->gyro_scale_radps <= 0.0F) ||
        ((bus->kind != SENSOR_BUS_I2C) && (bus->kind != SENSOR_BUS_SPI)))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((bus->kind == SENSOR_BUS_SPI) && (profile->spi_supported == 0U))
    {
        return SENSOR_IMU_UNSUPPORTED;
    }
    memset(imu, 0, sizeof(*imu));
    imu->bus = *bus;
    imu->profile = profile;
    imu->source_id = source_id;
    imu->axis_map[0] = 1;
    imu->axis_map[1] = 2;
    imu->axis_map[2] = 3;
    return SENSOR_IMU_OK;
}

SensorImuResult SensorImu_Probe(SensorImu *imu)
{
    uint8_t actual[2] = {0U, 0U};
    if ((imu == NULL) || (imu->profile == NULL))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((imu->bus.kind == SENSOR_BUS_SPI) &&
        (imu->profile->auxiliary_address_7bit != 0U))
    {
        /* BMI088 selects SPI after the first CS transaction following POR. */
        if (SensorRegister_Read(&imu->bus, imu->profile->id_register, actual, 1U) != SENSOR_BUS_OK)
        { return SENSOR_IMU_BUS_ERROR; }
    }
    if (SensorRegister_Read(&imu->bus, imu->profile->id_register,
        actual, (imu->profile->register_width == 2U) ? 2U : 1U) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        /* AN-000364: first ICM45686 I2C transaction may NACK. A single,
         * bounded identity read retry is harmless for the other devices. */
        if (SensorRegister_Read(&imu->bus, imu->profile->id_register,
            actual, (imu->profile->register_width == 2U) ? 2U : 1U) != SENSOR_BUS_OK)
        {
            return SENSOR_IMU_BUS_ERROR;
        }
    }
    return (actual[0] == imu->profile->expected_id) ? SENSOR_IMU_OK : SENSOR_IMU_WRONG_ID;
}

SensorImuResult SensorImu_BeginConfigure(SensorImu *imu, uint64_t now_us,
    uint8_t reset_required)
{
    SensorImuResult result;
    if ((imu == NULL) || (imu->profile == NULL))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((imu->state == SENSOR_IMU_READY) || (imu->state == SENSOR_IMU_APPLY) ||
        (imu->state == SENSOR_IMU_RESET_WAIT))
    {
        return SENSOR_IMU_BAD_STATE;
    }
    result = SensorImu_Probe(imu);
    if (result != SENSOR_IMU_OK)
    {
        return SensorImu_Fail(imu, result);
    }
    imu->profile_verified = 0U;
    imu->next_register = 0U;
    imu->retries = 0U;
    imu->config_generation++;
    imu->history_reset = 1U;
    imu->last_sample_us = 0U;
    imu->fifo_pending_mask = 0U;
    imu->last_process_us = now_us;
    imu->deadline_us = now_us;
    imu->state = SENSOR_IMU_APPLY;
    imu->model_phase = 0U;
    imu->model_reset = reset_required;
    if (imu->profile->prepare != NULL)
    {
        imu->state = SENSOR_IMU_RESET_WAIT;
        return SENSOR_IMU_BUSY;
    }
    if (reset_required != 0U)
    {
        if (SensorRegister_Write(&imu->bus, imu->profile->reset_register,
            &imu->profile->reset_value, 1U) != SENSOR_BUS_OK)
        {
            imu->bus_errors++;
            return SensorImu_Fail(imu, SENSOR_IMU_BUS_ERROR);
        }
        imu->volatile_writes++;
        imu->deadline_us = now_us + imu->profile->reset_wait_us;
        imu->state = SENSOR_IMU_RESET_WAIT;
    }
    return SENSOR_IMU_BUSY;
}

static SensorImuResult SensorImu_ResetComplete(SensorImu *imu)
{
    uint8_t actual;
    if (SensorRegister_Read(&imu->bus, imu->profile->reset_register,
        &actual, 1U) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SensorImu_Fail(imu, SENSOR_IMU_BUS_ERROR);
    }
    if ((actual & imu->profile->reset_mask) != 0U)
    {
        return SensorImu_Fail(imu, SENSOR_IMU_TIMEOUT);
    }
    imu->state = SENSOR_IMU_APPLY;
    return SENSOR_IMU_BUSY;
}

static SensorImuResult SensorImu_ApplyNext(SensorImu *imu, uint64_t now_us)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    SensorImuResult result;
    if (imu->next_register >= imu->profile->register_count)
    {
        imu->profile_verified = 1U;
        imu->deadline_us = now_us + imu->profile->settle_wait_us;
        imu->state = SENSOR_IMU_SETTLE;
        return SENSOR_IMU_BUSY;
    }
    result = SensorImu_RegisterMatch(imu,
        &imu->profile->registers[imu->next_register], 1U);
    if (result != SENSOR_IMU_OK)
    {
        imu->retries++;
        if (imu->retries >= SENSOR_IMU_RETRY_MAX)
        {
            return SensorImu_Fail(imu, result);
        }
        return SENSOR_IMU_BUSY;
    }
    imu->retries = 0U;
    imu->next_register++;
    return SENSOR_IMU_BUSY;
}

SensorImuResult SensorImu_ProcessConfigure(SensorImu *imu, uint64_t now_us)
{
    if ((imu == NULL) || (imu->profile == NULL))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (now_us < imu->last_process_us)
    {
        imu->time_errors++;
        return SensorImu_Fail(imu, SENSOR_IMU_TIME_ERROR);
    }
    imu->last_process_us = now_us;
    if (imu->state == SENSOR_IMU_READY)
    {
        return SENSOR_IMU_OK;
    }
    if (imu->state == SENSOR_IMU_FAULT)
    {
        return imu->last_result;
    }
    if (now_us < imu->deadline_us)
    {
        return SENSOR_IMU_BUSY;
    }
    if (imu->state == SENSOR_IMU_RESET_WAIT)
    {
        if (imu->profile->prepare != NULL)
        {
            SensorImuResult result = imu->profile->prepare(imu, now_us);
            if (result == SENSOR_IMU_BUSY) { return result; }
            if (result != SENSOR_IMU_OK) { return SensorImu_Fail(imu, result); }
            imu->state = SENSOR_IMU_APPLY;
            return SENSOR_IMU_BUSY;
        }
        return SensorImu_ResetComplete(imu);
    }
    if (imu->state == SENSOR_IMU_APPLY)
    {
        return SensorImu_ApplyNext(imu, now_us);
    }
    if (imu->state == SENSOR_IMU_SETTLE)
    {
        imu->state = SENSOR_IMU_SAMPLE_VERIFY;
        imu->deadline_us = now_us + SENSOR_IMU_SAMPLE_TIMEOUT_US;
        return SENSOR_IMU_NOT_READY;
    }
    if (imu->state == SENSOR_IMU_SAMPLE_VERIFY)
    {
        return SensorImu_Fail(imu, SENSOR_IMU_TIMEOUT);
    }
    return SENSOR_IMU_BAD_STATE;
}

SensorImuResult SensorImu_Verify(SensorImu *imu)
{
    uint8_t index;
    SensorImuResult result;
    if ((imu == NULL) || (imu->profile == NULL))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (imu->profile->extra_verify != NULL)
    {
        result = imu->profile->extra_verify(imu);
        if (result != SENSOR_IMU_OK) { return SensorImu_Fail(imu, result); }
    }
    for (index = 0U; index < imu->profile->register_count; index++)
    {
        result = SensorImu_RegisterMatch(imu, &imu->profile->registers[index], 0U);
        if (result != SENSOR_IMU_OK)
        {
            return SensorImu_Fail(imu, result);
        }
    }
    imu->profile_verified = 1U;
    return SENSOR_IMU_OK;
}

SensorImuResult SensorImu_Read(SensorImu *imu, uint64_t sample_us,
    uint64_t receive_us, SensorImuSample *sample)
{
    uint8_t status[2] = {0U, 0U};
    uint8_t frame[SENSOR_IMU_FRAME_MAX];
    if ((imu == NULL) || (sample == NULL) || (imu->profile == NULL))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((imu->profile_verified == 0U) ||
        ((imu->state != SENSOR_IMU_READY) && (imu->state != SENSOR_IMU_SAMPLE_VERIFY)))
    {
        return SENSOR_IMU_NOT_READY;
    }
    if (SensorRegister_Read(&imu->bus, imu->profile->status_register,
        status, (imu->profile->register_width == 2U) ? 2U : 1U) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SENSOR_IMU_BUS_ERROR;
    }
    if ((status[0] & imu->profile->ready_mask) != imu->profile->ready_mask)
    {
        return SENSOR_IMU_NOT_READY;
    }
    if (imu->profile->frame_read != NULL)
    {
        SensorImuResult result = imu->profile->frame_read(imu, frame);
        if (result != SENSOR_IMU_OK) { return result; }
    }
    else if (SensorRegister_Read(&imu->bus, imu->profile->data_register, frame,
        imu->profile->sample_length) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SENSOR_IMU_BUS_ERROR;
    }
    return SensorImu_SampleDecode(imu, frame, sample_us, receive_us, sample);
}

SensorImuResult SensorImu_Stop(SensorImu *imu)
{
    uint8_t bytes[2];
    uint8_t width;
    uint16_t registers[3];
    uint16_t values[3];
    uint8_t index;
    if ((imu == NULL) || (imu->profile == NULL)) { return SENSOR_IMU_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    width = (imu->profile->register_width == 2U) ? 2U : 1U;
    registers[0] = imu->profile->power_register; values[0] = imu->profile->stop_value;
    registers[1] = imu->profile->second_power_register; values[1] = imu->profile->second_stop_value;
    registers[2] = imu->profile->third_power_register; values[2] = imu->profile->third_stop_value;
    for (index = 0U; index < 3U; index++)
    {
        if ((index != 0U) && (registers[index] == 0U)) { continue; }
        bytes[0] = (uint8_t)values[index]; bytes[1] = (uint8_t)(values[index] >> 8U);
        if (SensorRegister_Write(&imu->bus, registers[index], bytes, width) != SENSOR_BUS_OK)
        {
            imu->bus_errors++;
            return SensorImu_Fail(imu, SENSOR_IMU_BUS_ERROR);
        }
        imu->volatile_writes++;
    }
    imu->state = SENSOR_IMU_STOPPED;
    imu->profile_verified = 0U;
    return SENSOR_IMU_OK;
}

SensorImuResult SensorImu_Start(SensorImu *imu, uint64_t now_us)
{
    /* Stop/start establishes a new sampling history. A volatile device reset
     * clears queued frames before the verified profile enables its FIFO again. */
    return SensorImu_BeginConfigure(imu, now_us, 1U);
}

SensorImuResult SensorImu_AxisMapSet(SensorImu *imu, const int8_t axis_map[3],
    uint32_t calibration_generation)
{
    uint8_t index;
    uint8_t seen = 0U;
    int8_t map[3];
    if ((imu == NULL) || (axis_map == NULL))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (imu->state == SENSOR_IMU_READY)
    {
        return SENSOR_IMU_BAD_STATE;
    }
    for (index = 0U; index < SENSOR_IMU_AXIS_COUNT; index++)
    {
        int16_t axis = axis_map[index];
        uint8_t bit;
        if (axis < 0) { axis = -axis; }
        if ((axis < 1) || (axis > 3)) { return SENSOR_IMU_INVALID_ARGUMENT; }
        bit = (uint8_t)(1U << (uint8_t)(axis - 1));
        if ((seen & bit) != 0U) { return SENSOR_IMU_INVALID_ARGUMENT; }
        seen |= bit;
        map[index] = axis_map[index];
    }
    memcpy(imu->axis_map, map, sizeof(map));
    imu->calibration_generation = calibration_generation;
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorImu_FifoCountRead(SensorImu *imu, uint16_t *bytes)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t count[2];
    if ((imu->profile->fifo_format == 2U) || (imu->profile->fifo_format == 3U))
    {
        uint8_t status;
        if (SensorRegister_Read(&imu->bus, imu->profile->status_register,
            &status, 1U) != SENSOR_BUS_OK)
        { imu->bus_errors++; return SENSOR_IMU_BUS_ERROR; }
        if ((status & 2U) != 0U)
        { imu->fifo_overflows++; return SensorImu_Fail(imu, SENSOR_IMU_FIFO_OVERFLOW); }
    }
    if (imu->profile->fifo_format == 3U)
    {
        /* ICM45686 AN-000364 section 2.2: discard the first count read. */
        if (SensorRegister_Read(&imu->bus, imu->profile->fifo_count_register,
            count, 2U) != SENSOR_BUS_OK)
        { imu->bus_errors++; return SENSOR_IMU_BUS_ERROR; }
    }
    if (SensorRegister_Read(&imu->bus, imu->profile->fifo_count_register,
        count, 2U) != SENSOR_BUS_OK)
    {
        imu->bus_errors++;
        return SENSOR_IMU_BUS_ERROR;
    }
    if (imu->profile->fifo_format == 4U)
    {
        uint16_t words = (uint16_t)((uint16_t)count[0] | ((uint16_t)count[1] << 8U));
        if (words > 1024U) { return SensorImu_Fail(imu, SENSOR_IMU_FIFO_OVERFLOW); }
        *bytes = (uint16_t)(words * 2U);
    }
    else if (imu->profile->fifo_format == 3U)
    {
        uint16_t records = (uint16_t)((uint16_t)count[0] | ((uint16_t)count[1] << 8U));
        if (records >= 2048U) { return SensorImu_Fail(imu, SENSOR_IMU_FIFO_OVERFLOW); }
        *bytes = (uint16_t)(records * 16U);
    }
    else { *bytes = (uint16_t)(((uint16_t)count[0] << 8U) | count[1]); }
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorImu_BmiFifoDecode(SensorImu *imu,
    const uint8_t *packet, uint8_t *frame, uint64_t *epoch)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint16_t tick = (uint16_t)SensorImu_Int16Read(&packet[14], 1U);
    uint16_t previous = (uint16_t)((uint16_t)imu->fifo_pending[0] |
        ((uint16_t)imu->fifo_pending[1] << 8U));
    /* Bosch reserves these sentinels for samples not yet available. */
    if (((uint16_t)SensorImu_Int16Read(packet, 1U) == 0x7F01U) ||
        ((uint16_t)SensorImu_Int16Read(&packet[6], 1U) == 0x7F02U) ||
        ((uint16_t)SensorImu_Int16Read(&packet[12], 1U) == 0x8000U))
    { return SENSOR_IMU_NOT_READY; }
    if (imu->fifo_pending_mask != 0U)
    {
        uint16_t elapsed = (uint16_t)(tick - previous);
        if ((elapsed == 0U) || (elapsed >= 32768U))
        { imu->time_errors++; return SensorImu_Fail(imu, SENSOR_IMU_TIME_ERROR); }
        /* SENSOR_TIME LSB is 39.0625 us; 200 Hz has exactly 128 ticks. */
        *epoch = imu->last_sample_us + (uint64_t)elapsed * 625U / 16U;
    }
    memcpy(frame, packet, 14U);
    imu->fifo_pending[0] = (uint8_t)tick;
    imu->fifo_pending[1] = (uint8_t)(tick >> 8U);
    imu->fifo_pending_mask = 1U;
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorImu_FifoEpochMap(SensorImu *imu, uint64_t receive_us,
    uint64_t *epoch)
{
    /* Fixed-rate FIFOs without a native timestamp retain physical sample spacing
     * while the 1 ms task drains a backlog. The initial MCU anchor is uncertain. */
    if (imu->last_sample_us != 0U)
    {
        uint64_t period = imu->profile->sample_period_us;
        if ((imu->profile->fifo_format == 1U) && (period == 4167U))
        {
            /* 240 Hz is exactly 12500/3 us, not 4167 us forever. Derive the
             * fractional phase from accepted sequence; no extra sample queue. */
            period = (((uint64_t)imu->sample_count + 1U) * 12500U / 3U) -
                ((uint64_t)imu->sample_count * 12500U / 3U);
        }
        uint64_t next = imu->last_sample_us + period;
        uint64_t difference = (next > *epoch) ? next - *epoch : *epoch - next;
        if ((next > receive_us) || (difference > 2ULL * imu->profile->sample_period_us))
        { imu->time_errors++; return SensorImu_Fail(imu, SENSOR_IMU_TIME_ERROR); }
        *epoch = next;
    }
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorImu_IcmFifoDecode(SensorImu *imu,
    const uint8_t *packet, uint8_t *frame, uint64_t *epoch)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint16_t tick;
    uint16_t previous;
    int16_t temperature;
    uint16_t encoded;
    /* Only the configured uncompressed 16-byte accel+gyro+ODR-timestamp
     * layout is admitted. Empty, 20-bit, FSYNC and ODR-change packets fail. */
    if ((packet[0] != 0x68U) || (packet[13] == 0x80U))
    { return SensorImu_Fail(imu, SENSOR_IMU_VERIFY_FAILED); }
    tick = (uint16_t)SensorImu_Int16Read(&packet[14], imu->profile->little_endian);
    previous = (uint16_t)((uint16_t)imu->fifo_pending[0] |
        ((uint16_t)imu->fifo_pending[1] << 8U));
    if (imu->fifo_pending_mask != 0U)
    {
        uint16_t elapsed = (uint16_t)(tick - previous);
        if ((elapsed == 0U) || (elapsed >= 32768U))
        { imu->time_errors++; return SensorImu_Fail(imu, SENSOR_IMU_TIME_ERROR); }
        *epoch = imu->last_sample_us + elapsed;
    }
    memcpy(&frame[imu->profile->accel_offset], &packet[1], 6U);
    memcpy(&frame[imu->profile->gyro_offset], &packet[7], 6U);
    temperature = (int16_t)(((packet[13] >= 128U) ? (int16_t)packet[13] - 256 :
        (int16_t)packet[13]) * 64);
    encoded = (uint16_t)temperature;
    frame[imu->profile->temperature_offset] = (imu->profile->little_endian != 0U) ?
        (uint8_t)encoded : (uint8_t)(encoded >> 8U);
    frame[imu->profile->temperature_offset + 1U] = (imu->profile->little_endian != 0U) ?
        (uint8_t)(encoded >> 8U) : (uint8_t)encoded;
    imu->fifo_pending[0] = (uint8_t)tick;
    imu->fifo_pending[1] = (uint8_t)(tick >> 8U);
    imu->fifo_pending_mask = 1U;
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorImu_StFifoEntryRead(SensorImu *imu)
{
    uint8_t entry[7];
    uint8_t tag;
    uint8_t mask;
    if (SensorRegister_Read(&imu->bus, 0x78U, entry, 7U) != SENSOR_BUS_OK)
    { imu->bus_errors++; return SENSOR_IMU_BUS_ERROR; }
    tag = entry[0] >> 3U;
    /* Only uncompressed low-g and gyro are enabled by this profile. */
    if ((tag != 1U) && (tag != 2U)) { return SENSOR_IMU_VERIFY_FAILED; }
    mask = (uint8_t)(1U << (tag - 1U));
    if ((imu->fifo_pending_mask & mask) != 0U)
    { imu->history_reset = 1U; imu->fifo_pending_mask = 0U; return SENSOR_IMU_TIME_ERROR; }
    memcpy(&imu->fifo_pending[(tag == 1U) ? 2U : 8U], &entry[1], 6U);
    imu->fifo_pending_mask |= mask;
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorImu_StFifoDrain(SensorImu *imu,
    uint64_t last_drdy_us, uint64_t receive_us, SensorImuSample *samples,
    uint8_t capacity, uint8_t *sample_count)
{
    uint8_t status[2];
    uint16_t entries;
    uint16_t pairs;
    uint8_t entry;
    SensorImuResult result;
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (SensorRegister_Read(&imu->bus, 0x1BU, status, 2U) != SENSOR_BUS_OK)
    { imu->bus_errors++; return SENSOR_IMU_BUS_ERROR; }
    entries = (uint16_t)((uint16_t)status[0] | ((uint16_t)(status[1] & 1U) << 8U));
    if ((status[1] & 0x68U) != 0U)
    { imu->fifo_overflows++; return SensorImu_Fail(imu, SENSOR_IMU_FIFO_OVERFLOW); }
    if (entries == 0U) { return SENSOR_IMU_NOT_READY; }
    pairs = (uint16_t)((entries + ((imu->fifo_pending_mask != 0U) ? 1U : 0U)) / 2U);
    if ((pairs > 0U) && (last_drdy_us < (uint64_t)(pairs - 1U) * imu->profile->sample_period_us))
    { imu->time_errors++; return SENSOR_IMU_TIME_ERROR; }
    /* Temperature is a current bounded read, not silently tagged as a FIFO epoch. */
    if (SensorRegister_Read(&imu->bus, 0x20U, imu->fifo_pending, 2U) != SENSOR_BUS_OK)
    { imu->bus_errors++; return SENSOR_IMU_BUS_ERROR; }
    for (entry = 0U; (entry < 2U * SENSOR_IMU_FIFO_BATCH_MAX) &&
        (entry < entries) && (*sample_count < capacity); entry++)
    {
        result = SensorImu_StFifoEntryRead(imu);
        if (result != SENSOR_IMU_OK) { return SensorImu_Fail(imu, result); }
        if (imu->fifo_pending_mask == 3U)
        {
            uint64_t epoch = last_drdy_us - (uint64_t)(pairs - *sample_count - 1U) * imu->profile->sample_period_us;
            result = SensorImu_FifoEpochMap(imu, receive_us, &epoch);
            if (result != SENSOR_IMU_OK) { return result; }
            result = SensorImu_SampleDecode(imu, imu->fifo_pending, epoch, receive_us, &samples[*sample_count]);
            imu->fifo_pending_mask = 0U;
            if (result != SENSOR_IMU_OK) { return result; }
            samples[*sample_count].quality_flags |= SENSOR_IMU_QUALITY_TIME_UNCERTAIN;
            (*sample_count)++;
        }
    }
    return (*sample_count != 0U) ? SENSOR_IMU_OK : SENSOR_IMU_NOT_READY;
}

static SensorImuResult SensorImu_FifoSampleRead(SensorImu *imu, uint64_t epoch,
    uint64_t receive_us, SensorImuSample *sample)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    uint8_t packet[SENSOR_IMU_FRAME_MAX];
    uint8_t frame[SENSOR_IMU_FRAME_MAX];
    SensorImuResult result;
    if (SensorRegister_Read(&imu->bus, imu->profile->fifo_data_register,
        packet, imu->profile->fifo_frame_length) != SENSOR_BUS_OK)
    { imu->bus_errors++; return SENSOR_IMU_BUS_ERROR; }
    if (imu->profile->fifo_format == 4U)
    { result = SensorImu_BmiFifoDecode(imu, packet, frame, &epoch); }
    else if (imu->profile->fifo_format >= 2U)
    { result = SensorImu_IcmFifoDecode(imu, packet, frame, &epoch); }
    else
    {
        memcpy(frame, packet, imu->profile->fifo_frame_length);
        result = SensorImu_FifoEpochMap(imu, receive_us, &epoch);
    }
    if (result != SENSOR_IMU_OK) { return result; }
    result = SensorImu_SampleDecode(imu, frame, epoch, receive_us, sample);
    if (result == SENSOR_IMU_OK) { sample->quality_flags |= SENSOR_IMU_QUALITY_TIME_UNCERTAIN; }
    else { imu->fifo_pending_mask = 0U; imu->history_reset = 1U; }
    return result;
}

SensorImuResult SensorImu_DrainFifo(SensorImu *imu, uint64_t last_drdy_us,
    uint64_t receive_us, SensorImuSample *samples, uint8_t capacity,
    uint8_t *sample_count)
{
    uint16_t bytes;
    uint16_t queued;
    uint8_t index;
    if ((imu == NULL) || (imu->profile == NULL) || (samples == NULL) ||
        (sample_count == NULL) || (capacity == 0U) ||
        (capacity > SENSOR_IMU_FIFO_BATCH_MAX))
    {
        return SENSOR_IMU_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    *sample_count = 0U;
    if (imu->profile->fifo_frame_length == 0U) { return SENSOR_IMU_UNSUPPORTED; }
    if ((imu->profile_verified == 0U) ||
        ((imu->state != SENSOR_IMU_READY) && (imu->state != SENSOR_IMU_SAMPLE_VERIFY)))
    {
        return SENSOR_IMU_NOT_READY;
    }
    if (imu->profile->fifo_format == 1U)
    { return SensorImu_StFifoDrain(imu, last_drdy_us, receive_us, samples, capacity, sample_count); }
    SensorImuResult count_result = SensorImu_FifoCountRead(imu, &bytes);
    if (count_result != SENSOR_IMU_OK)
    {
        return count_result;
    }
    if ((bytes >= imu->profile->fifo_capacity) ||
        ((bytes % imu->profile->fifo_frame_length) != 0U))
    {
        imu->fifo_overflows++;
        return SensorImu_Fail(imu, SENSOR_IMU_FIFO_OVERFLOW);
    }
    queued = bytes / imu->profile->fifo_frame_length;
    if (queued == 0U) { return SENSOR_IMU_NOT_READY; }
    if (last_drdy_us < (uint64_t)(queued - 1U) * imu->profile->sample_period_us)
    {
        imu->time_errors++;
        return SENSOR_IMU_TIME_ERROR;
    }
    for (index = 0U; (index < capacity) && (index < queued); index++)
    {
        SensorImuResult result;
        uint64_t epoch = last_drdy_us -
            (uint64_t)(queued - index - 1U) * imu->profile->sample_period_us;
        result = SensorImu_FifoSampleRead(imu, epoch, receive_us, &samples[index]);
        if (result != SENSOR_IMU_OK) { return result; }
        (*sample_count)++;
    }
    return SENSOR_IMU_OK;
}
