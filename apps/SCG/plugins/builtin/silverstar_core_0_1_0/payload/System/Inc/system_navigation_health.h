#ifndef __SYSTEM_NAVIGATION_HEALTH_H
#define __SYSTEM_NAVIGATION_HEALTH_H

#include <stdint.h>
#include "system_device_types.h"

#define SYSTEM_NAVIGATION_GROUP_COUNT 5U
#define SYSTEM_NAVIGATION_FUSION_TIMEOUT_US 2000000ULL
#define SYSTEM_NAVIGATION_INVALID_TIMEOUT_US 10000000ULL
#define SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH 5U
#define SYSTEM_NAVIGATION_REASON_SOURCE_WAIT 0x40U
#define SYSTEM_NAVIGATION_DELAYED_SOURCE_COUNT 4U
#ifndef SYSTEM_FUSION_CONFIGURED_MASK
#define SYSTEM_FUSION_CONFIGURED_MASK 0x1FU
#endif
#ifndef SYSTEM_FUSION_REQUIRED_HEALTH_MASK
#define SYSTEM_FUSION_REQUIRED_HEALTH_MASK 0x0FU
#endif

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

typedef struct
{
    uint64_t receive_us;
    uint64_t evaluation_us;
    uint32_t sequence;
    float variance_scale;
    uint8_t physically_valid;
    uint8_t source;
    uint8_t reason;
} SystemNavigationReceiveEvidence;

void SystemNavigationHealth_Reset(uint64_t epoch_us);
void SystemNavigationHealth_EpochSet(uint64_t epoch_us);
void SystemNavigationHealth_ImuQualityRecord(uint32_t quality_flags);
uint8_t SystemNavigationHealth_ChangesGet(uint64_t evaluation_us);
/* Fusion evaluations cannot precede the epoch or an earlier successful
 * evaluation; physical/receive timestamps may predate the epoch (delayed GNSS).
 * An ordinary rejected evidence update leaves group state unchanged. */
SystemDeviceResult SystemNavigationHealth_Observe(uint8_t group,
    const SystemNavigationFusionEvidence *evidence);
/* Separate receive/fusion lifecycle for a bounded delayed executor. Do not mix
 * with Observe before a lifecycle Reset. SourceSelect is authoritative even
 * when the new selected producer has not supplied a packet. A completion must
 * come from caller-owned admitted queue evidence; watermarks alone do not
 * establish membership of every historical packet. FusionOnly accepts valid,
 * attempted completions with finite nonnegative NIS. Health restoration needs
 * a receipt strictly after a source/invalid-receipt barrier. Mission recovery
 * diagnostics survive source selection; only current-source certificates reset. */
void SystemNavigationHealth_DelayedReset(uint64_t epoch_us);
SystemDeviceResult SystemNavigationHealth_SourceSelect(uint8_t group,
    uint8_t source, uint64_t evaluation_us);
/* No active producer: withdraw the live certificate without inventing a
 * receipt. Retain producer watermarks; queued pre-barrier completions cannot
 * restore health. A future real post-barrier receipt and fusion are required. */
SystemDeviceResult SystemNavigationHealth_SourceUnavailable(uint8_t group,
    uint64_t evaluation_us);
SystemDeviceResult SystemNavigationHealth_ReceiveOnly(uint8_t group,
    const SystemNavigationReceiveEvidence *evidence);
SystemDeviceResult SystemNavigationHealth_FusionOnly(uint8_t group,
    const SystemNavigationFusionEvidence *evidence);
void SystemNavigationHealth_ModelMismatchRecord(void);
/* On an ordinary error, snapshot is unchanged. Latched faults still produce an
 * INVALID snapshot even when the evaluation time predates the epoch. */
SystemDeviceResult SystemNavigationHealth_GroupGet(uint8_t group,
    uint64_t evaluation_us, SystemNavigationGroupHealth *snapshot);
uint8_t SystemNavigationHealth_DegradedGet(uint64_t evaluation_us);
SystemNavigationHealth SystemNavigationHealth_OverallGet(uint64_t evaluation_us,
    uint8_t required_mask, uint32_t imu_quality_flags);

#endif /* __SYSTEM_NAVIGATION_HEALTH_H */
