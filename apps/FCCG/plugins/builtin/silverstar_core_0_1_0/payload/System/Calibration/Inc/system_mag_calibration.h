#ifndef __SYSTEM_MAG_CALIBRATION_H
#define __SYSTEM_MAG_CALIBRATION_H

#include <stdint.h>

#include "system_magnetometer_if.h"

#define SYSTEM_MAG_CAL_PACKET_BYTES 84U
#define SYSTEM_MAG_CAL_PACKET_HEX_CHARS (SYSTEM_MAG_CAL_PACKET_BYTES * 2U)

typedef enum
{
    SystemMagCalibrationResult_Ok = 0,
    SystemMagCalibrationResult_NotReady,
    SystemMagCalibrationResult_InvalidArgument,
    SystemMagCalibrationResult_InvalidObject,
    SystemMagCalibrationResult_WrongDevice,
    SystemMagCalibrationResult_Busy,
    SystemMagCalibrationResult_NotPresent,
    SystemMagCalibrationResult_StorageError
} SystemMagCalibrationResult;

typedef struct
{
    uint32_t generation;
    uint16_t physical_device_id;
    uint8_t instance_id;
    uint8_t active;
    uint8_t saved;
    uint8_t save_pending;
    uint8_t save_failed;
    SystemMagCalibrationResult load_error;
} SystemMagCalibrationStatus;

void SystemMagCalibration_Init(void);
uint8_t SystemMagCalibration_ReadyForMissionGet(void);
uint32_t SystemMagCalibration_GenerationHashGet(void);
SystemMagCalibrationResult SystemMagCalibration_PacketApply(
    uint8_t instance_id, const char *packet_hex);
SystemMagCalibrationResult SystemMagCalibration_SaveRequest(uint8_t instance_id);
SystemMagCalibrationResult SystemMagCalibration_ClearRequest(uint8_t instance_id);
SystemMagCalibrationResult SystemMagCalibration_PendingGet(
    uint8_t *instance_id, uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    uint32_t *request_id);
SystemMagCalibrationResult SystemMagCalibration_SaveComplete(
    uint8_t instance_id, uint32_t request_id, uint8_t success,
    uint32_t generation);
SystemMagCalibrationResult SystemMagCalibration_StoredLoad(
    uint8_t instance_id, const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    uint32_t generation);
SystemMagCalibrationResult SystemMagCalibration_LoadFaultSet(
    uint8_t instance_id, SystemMagCalibrationResult reason);
SystemMagCalibrationResult SystemMagCalibration_StatusGet(
    uint8_t instance_id, SystemMagCalibrationStatus *status);
SystemMagCalibrationResult SystemMagCalibration_SampleApply(
    uint8_t instance_id, SystemMagnetometerSample *sample);

#endif /* __SYSTEM_MAG_CALIBRATION_H */
