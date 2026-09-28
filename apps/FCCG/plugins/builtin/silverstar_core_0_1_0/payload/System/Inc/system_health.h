#ifndef __SYSTEM_HEALTH_H
#define __SYSTEM_HEALTH_H

#include <stdint.h>

#include "system_capabilities.h"

#define SYSTEM_HEALTH_BLOCK_PROFILE_INVALID     (1UL << 0)
#define SYSTEM_HEALTH_BLOCK_PRIMARY_IMU         (1UL << 1)
#define SYSTEM_HEALTH_BLOCK_ATTITUDE_UNAVAILABLE (1UL << 2)
#define SYSTEM_HEALTH_BLOCK_OUTPUT_NOT_SAFE     (1UL << 3)
#define SYSTEM_HEALTH_BLOCK_REQUIRED_DEVICE     (1UL << 4)
#define SYSTEM_HEALTH_BLOCK_STARTUP_INCOMPLETE  (1UL << 5)
#define SYSTEM_HEALTH_BLOCK_STARTUP_FAILED      (1UL << 6)
#define SYSTEM_HEALTH_BLOCK_CALIBRATION_NOT_READY (1UL << 7)
#define SYSTEM_HEALTH_BLOCK_ALIGNMENT_NOT_READY   (1UL << 8)
#define SYSTEM_HEALTH_BLOCK_ASSERTION_FAULT       (1UL << 9)

typedef enum
{
    SYSTEM_HEALTH_ATTITUDE_UNKNOWN = 0,
    SYSTEM_HEALTH_ATTITUDE_READY,
    SYSTEM_HEALTH_ATTITUDE_CALIBRATION_NOT_READY,
    SYSTEM_HEALTH_ATTITUDE_SOURCE_UNAVAILABLE,
    SYSTEM_HEALTH_ATTITUDE_NO_SAMPLE,
    SYSTEM_HEALTH_ATTITUDE_INVALID,
    SYSTEM_HEALTH_ATTITUDE_STALE
} SystemHealthAttitudeStatus;

typedef struct
{
    uint64_t timestamp_us;
    SystemCapabilities capabilities;
    uint32_t start_blocking_mask;
    uint32_t warning_mask;
    uint32_t sequence;
    SystemHealthAttitudeStatus attitude_status;
    uint8_t ready;
} SystemHealthSnapshot;

void SystemHealth_Init(void);
void SystemHealth_Process(void);
void SystemHealth_SetAttitudeReady(uint8_t ready);
void SystemHealth_SetAttitudeState(uint8_t ready,
                                   SystemHealthAttitudeStatus status);
void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot);
uint8_t SystemHealth_IsReady(void);
const char *SystemHealth_AttitudeStatusText(SystemHealthAttitudeStatus status);

#endif /* __SYSTEM_HEALTH_H */
