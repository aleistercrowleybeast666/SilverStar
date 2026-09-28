#ifndef __MPU6050_DEVICE_H
#define __MPU6050_DEVICE_H

#include "sensor_imu.h"

const SensorImuProfile *Mpu6050_ProfileGet(void);

const SensorImuProfile *Mpu6050_FifoProfileGet(void);

#endif /* __MPU6050_DEVICE_H */
