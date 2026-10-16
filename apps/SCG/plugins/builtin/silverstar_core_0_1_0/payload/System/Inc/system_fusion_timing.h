#ifndef __SYSTEM_FUSION_TIMING_H
#define __SYSTEM_FUSION_TIMING_H

#include <stdint.h>
#include <stddef.h>
#include "project_device_instances.h"

/* Wire authority: contracts/navigation_fusion_timing_records_v2.json.
 * These constants implement that contract; the catalog is verified against it. */
#define SYSTEM_FUSION_TIMING_CURRENT 0U
#define SYSTEM_FUSION_TIMING_LEGACY_REPLAY 1U
#define SYSTEM_FUSION_TIMING_HORIZON 2U
#define SYSTEM_FUSION_CURRENT_MAX_AGE_US 500000ULL
#define SYSTEM_FUSION_SOURCE_RESOLVED 0x01U
#define SYSTEM_FUSION_APPLICATION_EPOCH_VALID 0x02U
#define SYSTEM_FUSION_TRUSTED_SOURCE 0x04U
#define SYSTEM_FUSION_DELAY_FALLBACK 0x08U
#define SYSTEM_FUSION_LEGACY_PRESENT_OVERRIDE 0x10U
#define SYSTEM_FUSION_REPLAY_NOT_RUN 255U
#define SYSTEM_FUSION_BAROMETER_SOURCE 1U
#define SYSTEM_FUSION_SOURCE_COUNT PROJECT_GNSS_INSTANCE_COUNT_MAX

_Static_assert((SYSTEM_FUSION_SOURCE_COUNT > 0U) && (SYSTEM_FUSION_SOURCE_COUNT <= 4U),
    "Fusion receipt sources must match the bounded GNSS selector namespace");

typedef enum
{
    SYSTEM_FUSION_EXEC_COMPLETE = 0,
    SYSTEM_FUSION_EXEC_INVALID = 1,
    SYSTEM_FUSION_EXEC_STALE = 2,
    SYSTEM_FUSION_EXEC_DUPLICATE = 3,
    SYSTEM_FUSION_EXEC_EPOCH_MISMATCH = 4,
    SYSTEM_FUSION_EXEC_DISCONTINUITY = 5,
    SYSTEM_FUSION_EXEC_NUMERIC_ERROR = 6,
    SYSTEM_FUSION_EXEC_NOT_READY = 7,
    SYSTEM_FUSION_EXEC_HISTORY_MISS = 8,
    SYSTEM_FUSION_EXEC_CAPACITY = 9,
    SYSTEM_FUSION_EXEC_WORK_LIMIT = 10,
    SYSTEM_FUSION_EXEC_QUEUED = 11,
    SYSTEM_FUSION_EXEC_WARMUP = 12,
    SYSTEM_FUSION_EXEC_LATE = 13,
    SYSTEM_FUSION_EXEC_MODEL_MISMATCH = 14,
    SYSTEM_FUSION_EXEC_BUSY = 15
} SystemFusionExecutionResult;

/* One serial-number watermark per source and namespace. No numerical history.
 * A mission/calibration reset clears it. Serial deltas >= 2^31 are ambiguous
 * or old and rejected; UINT32_MAX -> 0 is the normal wrap. */
typedef struct
{
    uint32_t sequence;
    uint8_t groups;
} SystemFusionReceipt;

static inline SystemFusionExecutionResult SystemFusionTiming_CurrentValidate(
    uint64_t source_us, uint64_t receive_us, uint64_t present_us, uint64_t epoch_start_us)
{
    if ((source_us == 0U) || (receive_us == 0U) ||
        (source_us > receive_us) || (receive_us > present_us))
    { return SYSTEM_FUSION_EXEC_INVALID; }
    if ((source_us < epoch_start_us) || (receive_us < epoch_start_us))
    { return SYSTEM_FUSION_EXEC_EPOCH_MISMATCH; }
    if ((present_us - source_us > SYSTEM_FUSION_CURRENT_MAX_AGE_US) ||
        (present_us - receive_us > SYSTEM_FUSION_CURRENT_MAX_AGE_US))
    { return SYSTEM_FUSION_EXEC_STALE; }
    return SYSTEM_FUSION_EXEC_COMPLETE;
}

static inline SystemFusionExecutionResult SystemFusionTiming_ReceiptCheck(
    const SystemFusionReceipt *receipt, uint32_t sequence, uint8_t groups)
{
    if ((receipt == NULL) || (groups == 0U)) { return SYSTEM_FUSION_EXEC_INVALID; }
    if (receipt->groups == 0U) { return SYSTEM_FUSION_EXEC_COMPLETE; }
    if (sequence == receipt->sequence)
    {
        return ((receipt->groups & groups) != 0U) ?
            SYSTEM_FUSION_EXEC_DUPLICATE : SYSTEM_FUSION_EXEC_COMPLETE;
    }
    return ((uint32_t)(sequence - receipt->sequence) < 0x80000000UL) ?
        SYSTEM_FUSION_EXEC_COMPLETE : SYSTEM_FUSION_EXEC_DISCONTINUITY;
}

static inline void SystemFusionTiming_ReceiptCommit(
    SystemFusionReceipt *receipt, uint32_t sequence, uint8_t groups)
{
    if ((receipt == NULL) || (groups == 0U)) { return; }
    if (receipt->sequence != sequence) { receipt->groups = 0U; }
    receipt->sequence = sequence;
    receipt->groups |= groups;
}

#endif /* __SYSTEM_FUSION_TIMING_H */
