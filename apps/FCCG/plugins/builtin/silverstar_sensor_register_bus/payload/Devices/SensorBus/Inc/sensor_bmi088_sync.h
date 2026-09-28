#ifndef __SENSOR_BMI088_SYNC_H
#define __SENSOR_BMI088_SYNC_H

#include "sensor_imu.h"

/* Bosch INT3(G) -> INT1(A), monitored by one MCU IRQ; INT2(A) -> second
 * MCU IRQ. The generated Sync400 plugin requires both declared physical nets.
 * Configuration image is volatile SRAM initialization, never OTP/NVM. */
const SensorImuProfile *SensorBmi088Sync_ProfileGet(void);

#endif /* __SENSOR_BMI088_SYNC_H */
