#include "system_mag_calibration.h"

#include <stddef.h>

void SystemMagCalibration_Init(void)
{
    /* No generated MAG endpoint and no calibration state. */
}

uint8_t SystemMagCalibration_ReadyForMissionGet(void)
{
    return 1U; /* Optional module is absent, not awaiting physical calibration. */
}

uint32_t SystemMagCalibration_GenerationHashGet(void)
{
    return 0U;
}

SystemMagCalibrationResult SystemMagCalibration_PacketApply(
    uint8_t instance_id, const char *packet_hex)
{
    (void)instance_id;
    return packet_hex == NULL ? SystemMagCalibrationResult_InvalidArgument :
        SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_SaveRequest(uint8_t instance_id)
{
    (void)instance_id;
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_ClearRequest(uint8_t instance_id)
{
    (void)instance_id;
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_PendingGet(
    uint8_t *instance_id, uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    uint32_t *request_id)
{
    if ((instance_id == NULL) || (packet == NULL) || (request_id == NULL))
    { return SystemMagCalibrationResult_InvalidArgument; }
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_PendingRecordGet(
    uint8_t *instance_id, uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES],
    uint32_t *request_id)
{
    if ((instance_id == NULL) || (record == NULL) || (request_id == NULL))
    { return SystemMagCalibrationResult_InvalidArgument; }
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_RecordLoad(
    uint8_t instance_id, const uint8_t *record, uint16_t length,
    uint32_t generation)
{
    (void)instance_id;
    (void)generation;
    if ((record == NULL) || (length != SYSTEM_MAG_CAL_RECORD_BYTES))
    { return SystemMagCalibrationResult_InvalidArgument; }
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_RecordLoadOwned(
    uint8_t instance_id, const uint8_t *record, uint16_t length,
    uint32_t generation)
{
    return SystemMagCalibration_RecordLoad(instance_id, record, length, generation);
}

SystemMagCalibrationResult SystemMagCalibration_SaveComplete(
    uint8_t instance_id, uint32_t request_id, uint8_t success, uint32_t generation)
{
    (void)instance_id;
    (void)request_id;
    (void)success;
    (void)generation;
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_LoadFaultSet(
    uint8_t instance_id, SystemMagCalibrationResult reason)
{
    (void)instance_id;
    (void)reason;
    return SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_StatusGet(
    uint8_t instance_id, SystemMagCalibrationStatus *status)
{
    (void)instance_id;
    return status == NULL ? SystemMagCalibrationResult_InvalidArgument :
        SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_SnapshotGet(
    uint8_t instance_id, SystemMagCalibrationSnapshot *snapshot)
{
    (void)instance_id;
    return snapshot == NULL ? SystemMagCalibrationResult_InvalidArgument :
        SystemMagCalibrationResult_NotPresent;
}

SystemMagCalibrationResult SystemMagCalibration_SampleApply(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    (void)instance_id;
    return sample == NULL ? SystemMagCalibrationResult_InvalidArgument :
        SystemMagCalibrationResult_NotPresent;
}
