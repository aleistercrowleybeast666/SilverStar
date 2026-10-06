#ifndef __SYSTEM_IMU_EPOCH_IF_H
#define __SYSTEM_IMU_EPOCH_IF_H

#include "system_device_types.h"

/* Emitted by the authoritative composition forced include. Legacy/non-MPU
 * builds have no witness state and retain their existing sample layout. */
#ifndef SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED
#define SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED 0U
#endif

typedef struct
{
    uint32_t source_id;
    uint32_t epoch;
    uint32_t revision;
    uint32_t calibration_generation;
    uint32_t alignment_generation;
} SystemImuEpochToken;

/* DeviceTask owns Publish/Revoke; CAL/ALIGN own their witness transactions.
 * All state access is bounded and IRQ coherent. No backend runs under a lock. */
void SystemImuEpoch_Init(void);
void SystemImuEpoch_Revoke(void);
void SystemImuEpoch_SamplePublish(uint32_t source_id, uint32_t epoch,
    uint8_t configured, uint8_t usable);
/* Identity remains current for same-epoch fault data. START usability is a
 * separate check; revoked/stale epochs never enter the quality pipeline. */
uint8_t SystemImuEpoch_SampleIsCurrent(uint32_t source_id, uint32_t epoch);
uint8_t SystemImuEpoch_PhysicalIsReady(void);
uint8_t SystemImuEpoch_RevisionIsCurrent(uint32_t revision);
uint8_t SystemImuEpoch_IsQualified(void);
uint8_t SystemImuEpoch_RecoveryIsQualified(void);
void SystemImuEpoch_CalibrationInvalidate(void);
void SystemImuEpoch_AlignmentInvalidate(void);
SystemDeviceResult SystemImuEpoch_CalibrationBegin(uint32_t generation,
    uint8_t identity, uint32_t *revision);
uint8_t SystemImuEpoch_CalibrationCommit(uint32_t revision, uint32_t generation);
uint8_t SystemImuEpoch_CalibrationIsReady(uint32_t generation, uint8_t identity);
SystemDeviceResult SystemImuEpoch_AlignmentBegin(uint32_t generation,
    SystemImuEpochToken *token);
uint8_t SystemImuEpoch_AlignmentCommit(const SystemImuEpochToken *token,
    uint8_t ready);
uint8_t SystemImuEpoch_AlignmentIsReady(uint32_t generation);
uint8_t SystemImuEpoch_OriginsCommit(const SystemImuEpochToken *token);
SystemDeviceResult SystemImuEpoch_StartReserve(SystemImuEpochToken *token);
/* Caller holds its publication lock through this check and FLIGHT assignment. */
uint8_t SystemImuEpoch_StartIsCurrent(const SystemImuEpochToken *token);
#endif /* __SYSTEM_IMU_EPOCH_IF_H */
