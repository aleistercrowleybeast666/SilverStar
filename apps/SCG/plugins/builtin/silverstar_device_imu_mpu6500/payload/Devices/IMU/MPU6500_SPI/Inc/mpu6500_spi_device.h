#ifndef __MPU6500_SPI_DEVICE_H
#define __MPU6500_SPI_DEVICE_H

#include "sensor_imu.h"

const SensorImuProfile *Mpu6500Spi_ProfileGet(void);

const SensorImuProfile *Mpu6500Spi_FifoProfileGet(void);

#endif /* __MPU6500_SPI_DEVICE_H */
