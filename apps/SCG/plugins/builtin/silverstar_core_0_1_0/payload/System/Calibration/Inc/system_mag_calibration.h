#ifndef __SYSTEM_MAG_CALIBRATION_H
#define __SYSTEM_MAG_CALIBRATION_H

#include <stdint.h>

#include "system_magnetometer_if.h"
#include "system_installation_calibration_if.h"

#define SYSTEM_MAG_CAL_PACKET_BYTES 84U
#define SYSTEM_MAG_CAL_PACKET_HEX_CHARS (SYSTEM_MAG_CAL_PACKET_BYTES * 2U)
#define SYSTEM_MAG_CAL_RECORD_BYTES \
    (SYSTEM_INSTALLATION_CAL_HEADER_BYTES + SYSTEM_MAG_CAL_PACKET_BYTES)

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
    uint32_t configuration_digest;
    uint32_t intrinsic_crc;
    uint16_t physical_device_id;
    uint8_t instance_id;
    uint8_t active;
    uint8_t saved;
    uint8_t save_pending;
    uint8_t save_failed;
    SystemMagCalibrationResult load_error;
} SystemMagCalibrationStatus;

typedef struct
{
    SystemMagCalibrationStatus status;
    float bias[3];
    float matrix[3][3];
} SystemMagCalibrationSnapshot;

void SystemMagCalibration_Init(void);
uint8_t SystemMagCalibration_ReadyForMissionGet(void);
uint32_t SystemMagCalibration_GenerationHashGet(void);
/* New correction/save/clear requests and stored loads require an enabled MAG
 * endpoint with physical-unit output, independently of any IMU or chip command.
 * Absent/disabled endpoints return NotPresent; unsupported/unavailable unit
 * capability returns NotReady. Rejected operations do not alter stored state.
 * Completion and diagnostic bookkeeping still validate the endpoint but do not
 * require an available unit capability. Generated endpoint identities are fixed. */
SystemMagCalibrationResult SystemMagCalibration_PacketApply(
    uint8_t instance_id, const char *packet_hex);
SystemMagCalibrationResult SystemMagCalibration_SaveRequest(uint8_t instance_id);
SystemMagCalibrationResult SystemMagCalibration_ClearRequest(uint8_t instance_id);
SystemMagCalibrationResult SystemMagCalibration_PendingGet(
    uint8_t *instance_id, uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    uint32_t *request_id);
/* Storage boundary: legacy unbound packets are rejected by RecordLoad.
 * Explicit maintenance APPLY followed by SAVE rebinds a reviewed legacy
 * packet to the current endpoint/configuration. No automatic migration. */
SystemMagCalibrationResult SystemMagCalibration_PendingRecordGet(
    uint8_t *instance_id, uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES],
    uint32_t *request_id);
SystemMagCalibrationResult SystemMagCalibration_RecordLoad(
    uint8_t instance_id, const uint8_t *record, uint16_t length,
    uint32_t generation);
/* Logger's boot loader only, inside its already acquired MagWrite operation.
 * This is not a wire/control entry and never acquires a nested reservation. */
SystemMagCalibrationResult SystemMagCalibration_RecordLoadOwned(
    uint8_t instance_id,const uint8_t *record,uint16_t length,uint32_t generation);
SystemMagCalibrationResult SystemMagCalibration_SaveComplete(
    uint8_t instance_id, uint32_t request_id, uint8_t success,
    uint32_t generation);
SystemMagCalibrationResult SystemMagCalibration_LoadFaultSet(
    uint8_t instance_id, SystemMagCalibrationResult reason);
/* Diagnostics require an enabled endpoint but remain readable when its unit
 * capability is unavailable. Failed reads leave the destination unchanged. */
SystemMagCalibrationResult SystemMagCalibration_StatusGet(
    uint8_t instance_id, SystemMagCalibrationStatus *status);
/* One coherent active snapshot, including trial/rollback status. It is not a
 * claim of persistence. Failure leaves output unchanged; no identity fallback. */
SystemMagCalibrationResult SystemMagCalibration_SnapshotGet(
    uint8_t instance_id, SystemMagCalibrationSnapshot *snapshot);
/* The sample is caller-owned. Nonzero physical/descriptor IDs and the instance
 * must match the endpoint; zero IDs permit an unstamped driver sample.
 * Any failure leaves the sample unchanged, and callers must honor the result.
 * Success publishes all three corrected axes and identity together. */
SystemMagCalibrationResult SystemMagCalibration_SampleApply(
    uint8_t instance_id, SystemMagnetometerSample *sample);

#endif /* __SYSTEM_MAG_CALIBRATION_H */
