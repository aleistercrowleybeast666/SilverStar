#ifndef __SYSTEM_MAG_CALIBRATION_STORAGE_IF_H
#define __SYSTEM_MAG_CALIBRATION_STORAGE_IF_H

#include <stdint.h>

/* Called only by LoggerTask after the storage session is mounted. */
void SystemMagCalibrationStorage_Service(void);
uint8_t SystemMagCalibrationStorage_LoadCompleteGet(void);

#endif /* __SYSTEM_MAG_CALIBRATION_STORAGE_IF_H */
