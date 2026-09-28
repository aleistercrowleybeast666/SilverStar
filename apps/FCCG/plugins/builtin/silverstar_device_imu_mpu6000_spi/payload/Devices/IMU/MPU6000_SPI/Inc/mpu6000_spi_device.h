#ifndef __MPU6000_SPI_DEVICE_H
#define __MPU6000_SPI_DEVICE_H

#include "sensor_imu.h"

const SensorImuProfile *Mpu6000Spi_ProfileGet(void);

const SensorImuProfile *Mpu6000Spi_FifoProfileGet(void);

#endif /* __MPU6000_SPI_DEVICE_H */
