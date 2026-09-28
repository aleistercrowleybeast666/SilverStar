#ifndef __SENSOR_IMU_H
#define __SENSOR_IMU_H

#include "sensor_register_bus.h"

#define SENSOR_IMU_CONFIG_MAX 16U
#define SENSOR_IMU_AXIS_COUNT 3U
#define SENSOR_IMU_FIFO_BATCH_MAX 4U
#define SENSOR_IMU_QUALITY_NEAR_RANGE (1UL << 0)
#define SENSOR_IMU_QUALITY_CLIPPED (1UL << 1)
#define SENSOR_IMU_QUALITY_TIME_UNCERTAIN (1UL << 2)
#define SENSOR_IMU_QUALITY_HISTORY_RESET (1UL << 3)

typedef enum
{
    SENSOR_IMU_OK = 0,
    SENSOR_IMU_BUSY,
    SENSOR_IMU_NOT_READY,
    SENSOR_IMU_INVALID_ARGUMENT,
    SENSOR_IMU_WRONG_ID,
    SENSOR_IMU_UNSUPPORTED,
    SENSOR_IMU_BUS_ERROR,
    SENSOR_IMU_VERIFY_FAILED,
    SENSOR_IMU_TIMEOUT,
    SENSOR_IMU_TIME_ERROR,
    SENSOR_IMU_FIFO_OVERFLOW,
    SENSOR_IMU_BAD_STATE
} SensorImuResult;

typedef enum
{
    SENSOR_IMU_IDLE = 0,
    SENSOR_IMU_RESET_WAIT,
    SENSOR_IMU_APPLY,
    SENSOR_IMU_SETTLE,
    SENSOR_IMU_SAMPLE_VERIFY,
    SENSOR_IMU_READY,
    SENSOR_IMU_STOPPED,
    SENSOR_IMU_FAULT
} SensorImuState;

typedef struct
{
    uint16_t address;
    uint16_t value;
    uint16_t mask;
} SensorImuRegister;

typedef struct SensorImu SensorImu;
typedef SensorImuResult (*SensorImuPrepare)(SensorImu *imu, uint64_t now_us);
typedef SensorImuResult (*SensorImuFrameRead)(SensorImu *imu, uint8_t *frame);
typedef SensorImuResult (*SensorImuExtraVerify)(SensorImu *imu);

/* Each model provides a complete, documented fixed raw-data profile. Requests
 * for a different ODR/range/FIFO layout require a separately verified profile. */
typedef struct
{
    const char *name;
    /* Zero means the conventional byte register bus. Bosch BMI323 uses
     * 16-bit little-endian words and two I2C dummy bytes. BMI088 uses bit 8
     * of the logical register for its separately addressed gyroscope. */
    uint8_t register_width;
    uint8_t i2c_dummy_bytes;
    uint8_t auxiliary_address_7bit;
    uint8_t spi_dummy_bytes;
    uint8_t auxiliary_spi_dummy_bytes;
    float accel_full_scale_g;
    SensorImuPrepare prepare;
    SensorImuFrameRead frame_read;
    SensorImuExtraVerify extra_verify;
    uint8_t id_register;
    uint8_t expected_id;
    uint8_t reset_register;
    uint8_t reset_value;
    uint8_t reset_mask;
    uint16_t power_register;
    uint16_t stop_value;
    uint16_t second_power_register;
    uint16_t second_stop_value;
    uint16_t third_power_register;
    uint16_t third_stop_value;
    uint8_t data_register;
    uint8_t status_register;
    uint8_t ready_mask;
    uint8_t sample_length;
    uint8_t accel_offset;
    uint8_t gyro_offset;
    uint8_t temperature_offset;
    uint8_t little_endian;
    uint8_t invalid_min_sample;
    uint8_t spi_supported;
    uint8_t sync_pair_required; /* Separate gyro-input and synchronized-ready IRQs required. */
    uint8_t register_count;
    uint8_t fifo_count_register;
    uint8_t fifo_data_register;
    uint8_t fifo_frame_length;
    uint8_t fifo_format; /* 0 MPU, 1 ST tagged, 2 ICM426xx, 3 ICM45686, 4 BMI323. */
    uint16_t fifo_capacity;
    uint32_t reset_wait_us;
    uint32_t settle_wait_us;
    uint32_t sample_period_us;
    float accel_scale_mps2;
    float gyro_scale_radps;
    float temperature_scale_c;
    float temperature_offset_c;
    SensorImuRegister registers[SENSOR_IMU_CONFIG_MAX];
} SensorImuProfile;

typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t source_id;
    uint32_t config_generation;
    uint32_t calibration_generation;
    uint32_t quality_flags;
    int16_t accel_raw[3];
    int16_t gyro_raw[3];
    float accel_b_mps2[3];
    float gyro_b_radps[3];
    float temperature_c;
} SensorImuSample;

/* Independent high-g channel: never silently substituted for the low-g INS
 * accelerometer. Units/range/generation travel with this separate output. */
typedef struct
{
    uint64_t sample_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t sequence;
    uint32_t config_generation;
    uint32_t source_id;
    uint32_t quality_flags;
    int16_t raw[3];
    float accel_b_mps2[3];
    float range_g;
} SensorHighGSample;

typedef struct
{
    uint64_t last_epoch_us;
    uint32_t sequence;
    uint32_t config_generation;
} SensorHighGState;

struct SensorImu
{
    SensorRegisterBus bus;
    const SensorImuProfile *profile;
    SensorImuState state;
    SensorImuResult last_result;
    uint64_t deadline_us;
    uint64_t last_process_us;
    uint64_t last_sample_us;
    uint32_t source_id;
    uint32_t config_generation;
    uint32_t calibration_generation;
    uint32_t sample_count;
    uint32_t bus_errors;
    uint32_t verify_errors;
    uint32_t time_errors;
    uint32_t fifo_overflows;
    uint32_t volatile_writes;
    uint8_t next_register;
    uint8_t retries;
    uint8_t profile_verified;
    uint8_t history_reset;
    uint8_t model_phase;
    uint8_t model_reset;
    uint8_t model_saved[4];
    uint8_t fifo_pending[14];
    uint8_t fifo_pending_mask;
    int8_t axis_map[3];
};

SensorImuResult SensorImu_Init(SensorImu *imu, const SensorRegisterBus *bus,
    const SensorImuProfile *profile, uint32_t source_id);
SensorImuResult SensorImu_Probe(SensorImu *imu);
SensorImuResult SensorImu_BeginConfigure(SensorImu *imu, uint64_t now_us,
    uint8_t reset_required);
SensorImuResult SensorImu_ProcessConfigure(SensorImu *imu, uint64_t now_us);
SensorImuResult SensorImu_Verify(SensorImu *imu);
SensorImuResult SensorImu_Read(SensorImu *imu, uint64_t sample_us,
    uint64_t receive_us, SensorImuSample *sample);
SensorImuResult SensorImu_Stop(SensorImu *imu);
SensorImuResult SensorImu_Start(SensorImu *imu, uint64_t now_us);
SensorImuResult SensorImu_AxisMapSet(SensorImu *imu, const int8_t axis_map[3],
    uint32_t calibration_generation);
SensorImuResult SensorImu_DrainFifo(SensorImu *imu, uint64_t last_drdy_us,
    uint64_t receive_us, SensorImuSample *samples, uint8_t capacity,
    uint8_t *sample_count);
SensorImuResult SensorHighG_ReadLsm6Dsv320X(SensorImu *imu,
    SensorHighGState *state, uint64_t sample_us, uint64_t receive_us,
    SensorHighGSample *sample);

#endif /* __SENSOR_IMU_H */
