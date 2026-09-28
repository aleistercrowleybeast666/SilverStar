#ifndef __SENSOR_BMI088_FIFO_H
#define __SENSOR_BMI088_FIFO_H

#include "sensor_imu.h"

typedef enum
{
    SENSOR_BMI088_FIFO_ACCEL = 0,
    SENSOR_BMI088_FIFO_GYRO,
    SENSOR_BMI088_FIFO_TIME
} SensorBmi088FifoKind;

/* Raw independent channels only. No fabricated accel/gyro pairing or host
 * clock mapping. A Bosch data-sync wiring/configuration profile is separate. */
typedef struct
{
    SensorBmi088FifoKind kind;
    uint32_t sensor_ticks;
    uint32_t source_id;
    uint32_t config_generation;
    uint32_t quality_flags;
    int16_t raw[3];
    float si[3];
} SensorBmi088FifoEvent;

SensorImuResult SensorBmi088Fifo_Enable(SensorImu *imu);
SensorImuResult SensorBmi088Fifo_AccelRead(SensorImu *imu, SensorBmi088FifoEvent *event);
SensorImuResult SensorBmi088Fifo_GyroRead(SensorImu *imu, SensorBmi088FifoEvent *event);

#endif /* __SENSOR_BMI088_FIFO_H */
