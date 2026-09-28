#ifndef __JY901B_SENSOR_ADAPTER_H
#define __JY901B_SENSOR_ADAPTER_H

#include "system_imu_if.h"
#include "jy901b_device.h"

SystemDeviceResult Jy901bAdapter_SharedInit(uint8_t instance);
SystemDeviceResult Jy901bAdapter_SharedStart(uint8_t instance);
SystemDeviceResult Jy901bAdapter_SharedStop(uint8_t instance);
void Jy901bAdapter_SharedProcess(uint8_t instance);
SystemDeviceResult Jy901bAdapter_SharedHealthGet(uint8_t instance, SystemDeviceHealth *health);
SystemDeviceResult Jy901bAdapter_FrameHealthGet(uint8_t instance, IMUFrameType frame_type,
                                                 SystemDeviceHealth *health);
SystemDeviceResult Jy901bAdapter_SharedSnapshotGet(uint8_t instance, IMUData *snapshot);
SystemDeviceResult Jy901bAdapter_ConfigAccessCheck(uint8_t instance);
SystemDeviceResult Jy901bAdapter_AlgorithmStage(uint8_t instance, IMUAlgorithm algorithm);
SystemDeviceResult Jy901bAdapter_OutputRateValueGet(uint16_t rate_hz,
                                                     IMUOutputRate *value);

#endif /* __JY901B_SENSOR_ADAPTER_H */
