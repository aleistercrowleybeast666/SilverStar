#ifndef __MPU9250_DEVICE_H
#define __MPU9250_DEVICE_H

#include "sensor_imu.h"

const SensorImuProfile *Mpu9250_ProfileGet(void);

const SensorImuProfile *Mpu9250_FifoProfileGet(void);

#endif /* __MPU9250_DEVICE_H */
