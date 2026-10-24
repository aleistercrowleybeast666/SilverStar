#ifndef __SYSTEM_MAG_CALIBRATION_STORAGE_IF_H
#define __SYSTEM_MAG_CALIBRATION_STORAGE_IF_H

#include <stdint.h>

/* Sole filesystem owner calls once per iteration: LoggerTask with logging,
 * otherwise the maintenance SerialTask. These owners are compile-time exclusive.
 * Service runs independently of
 * ordinary log session admission/finalization. Bounded to one endpoint load or
 * one pending save; mounts TF without opening a log or creating a mission.
 * An unavailable card completes the attempt with an explicit load/save fault. */
void SystemMagCalibrationStorage_Service(void);
uint8_t SystemMagCalibrationStorage_LoadCompleteGet(void);

#endif /* __SYSTEM_MAG_CALIBRATION_STORAGE_IF_H */
