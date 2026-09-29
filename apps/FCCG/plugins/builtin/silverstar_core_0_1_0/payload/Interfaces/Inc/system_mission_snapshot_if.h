#ifndef __SYSTEM_MISSION_SNAPSHOT_IF_H
#define __SYSTEM_MISSION_SNAPSHOT_IF_H

#include <stdint.h>

typedef enum
{
    SystemMissionSnapshotResult_Ok = 0,
    SystemMissionSnapshotResult_NotReady,
    SystemMissionSnapshotResult_TooLarge,
    SystemMissionSnapshotResult_DataError,
    SystemMissionSnapshotResult_StorageError
} SystemMissionSnapshotResult;

typedef struct
{
    uint32_t mission_id;
    uint32_t commit_generation;
    uint32_t snapshot_sequence;
    uint32_t calibration_generation;
    uint32_t imu_correction_hash;
    uint32_t mag_calibration_generation;
    uint32_t mag_calibration_set_hash;
    uint8_t imu_source_instance;
    uint8_t gnss_source_instance;
    uint8_t snapshot_base_instance;
} SystemMissionSnapshotStatus;

SystemMissionSnapshotResult SystemMissionSnapshot_Create(
    SystemMissionSnapshotStatus *status);
SystemMissionSnapshotResult SystemMissionSnapshot_FinalStatusWrite(
    uint64_t timestamp_us, uint8_t logger_fault);

#endif /* __SYSTEM_MISSION_SNAPSHOT_IF_H */
