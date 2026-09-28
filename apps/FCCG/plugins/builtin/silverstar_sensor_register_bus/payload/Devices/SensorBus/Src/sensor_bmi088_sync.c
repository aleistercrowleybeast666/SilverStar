#include "sensor_bmi088_sync.h"
#include "silverstar_assert.h"
#include <string.h>

#define BMI088_SYNC_IMAGE_SIZE 6144U
#define BMI088_SYNC_CHUNK_SIZE 32U
#define BMI088_SYNC_RESET_US 30000U
#define BMI088_SYNC_APS_US 450U
#define BMI088_SYNC_ASIC_US 150000U

/* Exact Bosch bmi08x_config_file, pinned in the accompanying license/provenance.
 * The byte image is data, not executable host/plugin code. */
static const uint8_t s_sync_image[BMI088_SYNC_IMAGE_SIZE] =
{
#include "bmi088_sync_image.inc"
};

static SensorImuResult SensorBmi088Sync_ByteWrite(SensorImu *imu,
    uint16_t address, uint8_t value)
{
    if (SensorRegister_Write(&imu->bus, address, &value, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    imu->volatile_writes++;
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorBmi088Sync_Reset(SensorImu *imu, uint64_t now_us)
{
    uint8_t id;
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (SensorRegister_Read(&imu->bus, 0x100U, &id, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (id != 0x0FU) { return SENSOR_IMU_WRONG_ID; }
    if ((SensorBmi088Sync_ByteWrite(imu, 0x7EU, 0xB6U) != SENSOR_IMU_OK) ||
        (SensorBmi088Sync_ByteWrite(imu, 0x114U, 0xB6U) != SENSOR_IMU_OK))
    { return SENSOR_IMU_BUS_ERROR; }
    memset(imu->model_saved, 0, sizeof(imu->model_saved));
    imu->deadline_us = now_us + BMI088_SYNC_RESET_US;
    imu->model_phase = 1U;
    return SENSOR_IMU_BUSY;
}

static SensorImuResult SensorBmi088Sync_ImageChunkWrite(SensorImu *imu)
{
    uint16_t offset = (uint16_t)((uint16_t)imu->model_saved[0] |
        ((uint16_t)imu->model_saved[1] << 8U));
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((offset >= BMI088_SYNC_IMAGE_SIZE) || (offset % BMI088_SYNC_CHUNK_SIZE != 0U))
    { return SENSOR_IMU_BAD_STATE; }
    if ((SensorBmi088Sync_ByteWrite(imu, 0x5BU, (uint8_t)((offset / 2U) & 0x0FU)) != SENSOR_IMU_OK) ||
        (SensorBmi088Sync_ByteWrite(imu, 0x5CU, (uint8_t)((offset / 2U) >> 4U)) != SENSOR_IMU_OK))
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Write(&imu->bus, 0x5EU, &s_sync_image[offset], BMI088_SYNC_CHUNK_SIZE) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    imu->volatile_writes++;
    offset = (uint16_t)(offset + BMI088_SYNC_CHUNK_SIZE);
    imu->model_saved[0] = (uint8_t)offset;
    imu->model_saved[1] = (uint8_t)(offset >> 8U);
    if (offset == BMI088_SYNC_IMAGE_SIZE) { imu->model_phase = 4U; }
    return SENSOR_IMU_BUSY;
}

static SensorImuResult SensorBmi088Sync_FeatureVerify(SensorImu *imu)
{
    uint8_t data[6];
    uint8_t verify[6];
    uint8_t status;
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (SensorRegister_Read(&imu->bus, 0x2AU, &status, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (status != 1U) { return SENSOR_IMU_VERIFY_FAILED; }
    if (SensorRegister_Read(&imu->bus, 0x5EU, data, sizeof(data)) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    /* Bosch feature word 2, mode 1: 400Hz. Preserve other feature words. */
    data[4] = 1U; data[5] = 0U;
    if (SensorRegister_Write(&imu->bus, 0x5EU, data, sizeof(data)) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    imu->volatile_writes++;
    if (SensorRegister_Read(&imu->bus, 0x5EU, verify, sizeof(verify)) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (memcmp(data, verify, sizeof(data)) != 0) { return SENSOR_IMU_VERIFY_FAILED; }
    memset(imu->model_saved, 0, sizeof(imu->model_saved));
    imu->model_phase = 6U;
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorBmi088Sync_Prepare(SensorImu *imu, uint64_t now_us)
{
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (imu->model_phase == 0U) { return SensorBmi088Sync_Reset(imu, now_us); }
    if (imu->model_phase == 1U)
    {
        if (SensorImu_Probe(imu) != SENSOR_IMU_OK) { return SENSOR_IMU_WRONG_ID; }
        if (SensorBmi088Sync_ByteWrite(imu, 0x7CU, 0U) != SENSOR_IMU_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->deadline_us = now_us + BMI088_SYNC_APS_US;
        imu->model_phase = 2U;
        return SENSOR_IMU_BUSY;
    }
    if (imu->model_phase == 2U)
    {
        if (SensorBmi088Sync_ByteWrite(imu, 0x59U, 0U) != SENSOR_IMU_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->model_phase = 3U;
        return SENSOR_IMU_BUSY;
    }
    if (imu->model_phase == 3U) { return SensorBmi088Sync_ImageChunkWrite(imu); }
    if (imu->model_phase == 4U)
    {
        if (SensorBmi088Sync_ByteWrite(imu, 0x59U, 1U) != SENSOR_IMU_OK)
        { return SENSOR_IMU_BUS_ERROR; }
        imu->deadline_us = now_us + BMI088_SYNC_ASIC_US;
        imu->model_phase = 5U;
        return SENSOR_IMU_BUSY;
    }
    if (imu->model_phase == 5U) { return SensorBmi088Sync_FeatureVerify(imu); }
    return (imu->model_phase == 6U) ? SENSOR_IMU_OK : SENSOR_IMU_BAD_STATE;
}

static SensorImuResult SensorBmi088Sync_FrameRead(SensorImu *imu, uint8_t *frame)
{
    uint8_t temperature[2];
    uint8_t gyro_check[6];
    int32_t temp;
    SILVERSTAR_ASSERT_OBJECT(imu, SensorImu, SILVERSTAR_ASSERT_MODULE_DEVICE);
    /* Official synchronized accel output is GP0/GP4, not raw 0x12. */
    if ((SensorRegister_Read(&imu->bus, 0x1EU, frame, 4U) != SENSOR_BUS_OK) ||
        (SensorRegister_Read(&imu->bus, 0x27U, &frame[4], 2U) != SENSOR_BUS_OK) ||
        (SensorRegister_Read(&imu->bus, 0x102U, &frame[6], 6U) != SENSOR_BUS_OK) ||
        (SensorRegister_Read(&imu->bus, 0x22U, temperature, 2U) != SENSOR_BUS_OK) ||
        (SensorRegister_Read(&imu->bus, 0x102U, gyro_check, 6U) != SENSOR_BUS_OK))
    { return SENSOR_IMU_BUS_ERROR; }
    if (memcmp(&frame[6], gyro_check, sizeof(gyro_check)) != 0)
    { imu->history_reset = 1U; return SENSOR_IMU_TIME_ERROR; }
    temp = (int32_t)temperature[0] * 8L + (temperature[1] >> 5U);
    if (temp == 1024L) { return SENSOR_IMU_NOT_READY; }
    if (temp > 1023L) { temp -= 2048L; }
    frame[12] = (uint8_t)((uint16_t)temp & 0xFFU);
    frame[13] = (uint8_t)((uint16_t)temp >> 8U);
    return SENSOR_IMU_OK;
}

static SensorImuResult SensorBmi088Sync_Readback(SensorImu *imu)
{
    uint8_t status;
    uint8_t feature[6];
    if (SensorRegister_Read(&imu->bus, 0x2AU, &status, 1U) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    if (SensorRegister_Read(&imu->bus, 0x5EU, feature, sizeof(feature)) != SENSOR_BUS_OK)
    { return SENSOR_IMU_BUS_ERROR; }
    return ((status == 1U) && (feature[4] == 1U) && (feature[5] == 0U)) ?
        SENSOR_IMU_OK : SENSOR_IMU_VERIFY_FAILED;
}

static const SensorImuProfile s_sync_profile =
{
    .name = "BMI088 Sync400", .auxiliary_address_7bit = 0x68U,
    .accel_full_scale_g = 24.0F, .spi_dummy_bytes = 1U,
    .prepare = SensorBmi088Sync_Prepare, .frame_read = SensorBmi088Sync_FrameRead,
    .extra_verify = SensorBmi088Sync_Readback,
    .id_register = 0U, .expected_id = 0x1EU,
    .power_register = 0x7DU, .stop_value = 0U,
    .second_power_register = 0x111U, .second_stop_value = 0x80U,
    .status_register = 0x2AU, .ready_mask = 1U,
    .sample_length = 14U, .accel_offset = 0U, .gyro_offset = 6U,
    .temperature_offset = 12U, .little_endian = 1U, .spi_supported = 1U,
    .sync_pair_required = 1U, .settle_wait_us = 100000U, .sample_period_us = 2500U,
    .accel_scale_mps2 = 24.0F * 9.80665F / 32768.0F,
    .gyro_scale_radps = 2000.0F * 0.017453292519943295F / 32768.0F,
    .temperature_scale_c = 0.125F, .temperature_offset_c = 23.0F,
    .register_count = 15U,
    .registers = {{0x7CU, 0U, 3U}, {0x7DU, 4U, 4U},
        {0x40U, 0xAAU, 0xFFU}, {0x41U, 3U, 3U},
        {0x10FU, 0U, 7U}, {0x110U, 3U, 7U}, {0x111U, 0U, 0xA0U},
        {0x13EU, 0U, 0xC0U}, {0x115U, 0x80U, 0x80U},
        {0x53U, 0x13U, 0x1FU}, {0x54U, 0x0AU, 0x1FU},
        {0x57U, 1U, 1U}, {0x58U, 0U, 0x44U},
        {0x116U, 1U, 0x0FU}, {0x118U, 1U, 0x81U}}
};

const SensorImuProfile *SensorBmi088Sync_ProfileGet(void)
{
    return &s_sync_profile;
}
