#ifndef __SYSTEM_NAVIGATION_HEALTH_H
#define __SYSTEM_NAVIGATION_HEALTH_H

#include <stdint.h>
#include "system_device_types.h"

#define SYSTEM_NAVIGATION_GROUP_COUNT 5U
#define SYSTEM_NAVIGATION_FUSION_TIMEOUT_US 2000000ULL
#define SYSTEM_NAVIGATION_INVALID_TIMEOUT_US 10000000ULL
#define SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH 5U

typedef enum
{
    SYSTEM_NAVIGATION_UNAVAILABLE = 0,
    SYSTEM_NAVIGATION_ACCEPTED,
    SYSTEM_NAVIGATION_SOFT_WEIGHTED,
    SYSTEM_NAVIGATION_REJECTED,
    SYSTEM_NAVIGATION_RECOVERING,
    SYSTEM_NAVIGATION_DEAD_RECKONING,
    SYSTEM_NAVIGATION_INVALID
} SystemNavigationState;

typedef enum
{
    SYSTEM_NAVIGATION_HEALTH_WARMUP = 0,
    SYSTEM_NAVIGATION_HEALTH_HEALTHY,
    SYSTEM_NAVIGATION_HEALTH_DEGRADED,
    SYSTEM_NAVIGATION_HEALTH_DEAD_RECKONING,
    SYSTEM_NAVIGATION_HEALTH_INVALID
} SystemNavigationHealth;

typedef struct
{
    uint64_t last_receive_us;
    uint64_t last_physically_valid_us;
    uint64_t last_update_attempt_us;
    uint64_t last_successful_fusion_us;
    uint64_t last_recovery_us;
    uint32_t last_sequence;
    uint32_t recovery_count;
    float nis;
    float variance_scale;
    uint8_t state;
    uint8_t quality;
    uint8_t reason;
    uint8_t has_success;
    uint8_t has_receive;
    uint8_t source;
} SystemNavigationGroupHealth;

typedef struct
{
    uint64_t receive_us;
    uint64_t measurement_us;
    uint64_t evaluation_us;
    uint32_t sequence;
    float nis;
    float variance_scale;
    uint8_t physically_valid;
    uint8_t attempted;
    uint8_t effective_update;
    uint8_t soft_weighted;
    uint8_t reason;
    uint8_t source;
} SystemNavigationFusionEvidence;

void SystemNavigationHealth_Reset(uint64_t epoch_us);
void SystemNavigationHealth_EpochSet(uint64_t epoch_us);
void SystemNavigationHealth_ImuQualityRecord(uint32_t quality_flags);
uint8_t SystemNavigationHealth_ChangesGet(uint64_t evaluation_us);
SystemDeviceResult SystemNavigationHealth_Observe(uint8_t group,
    const SystemNavigationFusionEvidence *evidence);
SystemDeviceResult SystemNavigationHealth_GroupGet(uint8_t group,
    uint64_t evaluation_us, SystemNavigationGroupHealth *snapshot);
uint8_t SystemNavigationHealth_DegradedGet(uint64_t evaluation_us);
SystemNavigationHealth SystemNavigationHealth_OverallGet(uint64_t evaluation_us,
    uint8_t required_mask, uint32_t imu_quality_flags);

#endif /* __SYSTEM_NAVIGATION_HEALTH_H */
