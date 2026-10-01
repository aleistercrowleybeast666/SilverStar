#include "system_navigation_health.h"

#include <math.h>
#include <stddef.h>
#include <string.h>
#include "platform_critical.h"
#include "platform_memory.h"
#include "silverstar_assert.h"

_Static_assert(sizeof(SystemNavigationGroupHealth) == 64U,
    "Navigation group health must retain its bounded memory footprint");

static PLATFORM_NAV_HEALTH_BSS SystemNavigationGroupHealth s_groups[SYSTEM_NAVIGATION_GROUP_COUNT];
static uint64_t s_epoch_us;
static uint32_t s_imu_faults;
static uint32_t s_imu_quality;
static uint8_t s_model_mismatch;
static uint8_t s_previous_state[SYSTEM_NAVIGATION_GROUP_COUNT];

/* Called only while the group owner is protected by PlatformCritical. */
static void SystemNavigationHealth_GroupValidate(const SystemNavigationGroupHealth *state)
{
    SILVERSTAR_ASSERT(state->state <= SYSTEM_NAVIGATION_INVALID && state->quality <= 3U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(state->has_receive <= 1U && state->has_success <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

void SystemNavigationHealth_Reset(uint64_t epoch_us)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    memset(s_groups, 0, sizeof(s_groups));
    s_epoch_us = epoch_us;
    s_imu_faults = 0U;
    s_imu_quality = 0U;
    s_model_mismatch = 0U;
    memset(s_previous_state, 0, sizeof(s_previous_state));
    PlatformCritical_Exit(lock);
}

SystemDeviceResult SystemNavigationHealth_Observe(uint8_t group,
    const SystemNavigationFusionEvidence *evidence)
{
    SystemNavigationGroupHealth *state;
    PlatformCriticalState lock;
    if ((group >= SYSTEM_NAVIGATION_GROUP_COUNT) || (evidence == NULL) ||
        (evidence->measurement_us > evidence->evaluation_us) ||
        (evidence->receive_us > evidence->evaluation_us) ||
        (evidence->physically_valid > 1U) || (evidence->attempted > 1U) ||
        (evidence->effective_update > 1U) || (evidence->soft_weighted > 1U) ||
        !isfinite(evidence->variance_scale) || (evidence->variance_scale < 1.0f))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((evidence->effective_update != 0U) &&
        ((evidence->physically_valid == 0U) || (evidence->attempted == 0U) || !isfinite(evidence->nis)))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(evidence, SystemNavigationFusionEvidence, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(group < SYSTEM_NAVIGATION_GROUP_COUNT, SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    lock = PlatformCritical_Enter();
    state = &s_groups[group];
    SystemNavigationHealth_GroupValidate(state);
    if (evidence->evaluation_us < ((state->has_success != 0U) ?
        state->last_successful_fusion_us : s_epoch_us))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_BAD_STATE; }
    if ((state->has_receive != 0U) && (evidence->source == state->source) &&
        ((evidence->sequence == state->last_sequence) ||
         (evidence->receive_us <= state->last_receive_us)))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_BAD_STATE; }
    state->has_receive = 1U;
    state->last_receive_us = evidence->receive_us;
    state->last_sequence = evidence->sequence;
    state->source = evidence->source;
    state->nis = evidence->nis;
    state->variance_scale = evidence->variance_scale;
    state->reason = evidence->reason;
    if (evidence->reason == SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH)
    { s_model_mismatch = 1U; }
    state->quality = (evidence->physically_valid == 0U) ? 3U :
        (evidence->variance_scale > 1.0f) ? 2U : 1U;
    if (evidence->physically_valid != 0U) { state->last_physically_valid_us = evidence->receive_us; }
    if (evidence->attempted != 0U) { state->last_update_attempt_us = evidence->evaluation_us; }
    if (evidence->effective_update != 0U)
    {
        uint64_t baseline = (state->has_success != 0U) ? state->last_successful_fusion_us : s_epoch_us;
        if ((evidence->evaluation_us >= baseline) &&
            (evidence->evaluation_us - baseline >= SYSTEM_NAVIGATION_FUSION_TIMEOUT_US))
        { state->last_recovery_us = evidence->evaluation_us; state->recovery_count++; }
        state->last_successful_fusion_us = evidence->evaluation_us;
        state->has_success = 1U;
        state->state = (evidence->soft_weighted != 0U) ?
            SYSTEM_NAVIGATION_SOFT_WEIGHTED : SYSTEM_NAVIGATION_ACCEPTED;
    }
    else { state->state = SYSTEM_NAVIGATION_REJECTED; }
    PlatformCritical_Exit(lock);
    return SYSTEM_DEVICE_OK;
}

void SystemNavigationHealth_EpochSet(uint64_t epoch_us)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_epoch_us = epoch_us;
    PlatformCritical_Exit(lock);
}

SystemDeviceResult SystemNavigationHealth_GroupGet(uint8_t group,
    uint64_t evaluation_us, SystemNavigationGroupHealth *snapshot)
{
    uint64_t baseline;
    PlatformCriticalState lock;
    if ((group >= SYSTEM_NAVIGATION_GROUP_COUNT) || (snapshot == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(snapshot, SystemNavigationGroupHealth, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(group < SYSTEM_NAVIGATION_GROUP_COUNT, SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    lock = PlatformCritical_Enter();
    SystemNavigationHealth_GroupValidate(&s_groups[group]);
    baseline = (s_groups[group].has_success != 0U) ? s_groups[group].last_successful_fusion_us : s_epoch_us;
    if ((s_model_mismatch == 0U) && (s_imu_faults == 0U) && (evaluation_us < baseline))
    { PlatformCritical_Exit(lock); return SYSTEM_DEVICE_BAD_STATE; }
    *snapshot = s_groups[group];
    if (s_model_mismatch != 0U)
    {
        snapshot->state = SYSTEM_NAVIGATION_INVALID;
        snapshot->reason = SYSTEM_NAVIGATION_REASON_MODEL_MISMATCH;
        PlatformCritical_Exit(lock);
        return SYSTEM_DEVICE_OK;
    }
    if (s_imu_faults != 0U)
    {
        snapshot->state = SYSTEM_NAVIGATION_INVALID;
        snapshot->reason = (uint8_t)(0x80U | s_imu_faults);
        PlatformCritical_Exit(lock);
        return SYSTEM_DEVICE_OK;
    }
    PlatformCritical_Exit(lock);
    if (evaluation_us - baseline >= SYSTEM_NAVIGATION_INVALID_TIMEOUT_US)
    { snapshot->state = SYSTEM_NAVIGATION_INVALID; snapshot->reason = 2U; }
    else if (evaluation_us - baseline >= SYSTEM_NAVIGATION_FUSION_TIMEOUT_US)
    { snapshot->state = SYSTEM_NAVIGATION_DEAD_RECKONING; snapshot->reason = 1U; }
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemNavigationHealth_DegradedGet(uint64_t evaluation_us)
{
    SystemNavigationGroupHealth snapshot;
    uint8_t group, mask = 0U;
    for (group = 0U; group < SYSTEM_NAVIGATION_GROUP_COUNT; group++)
    {
        if ((SystemNavigationHealth_GroupGet(group, evaluation_us, &snapshot) != SYSTEM_DEVICE_OK) ||
            (snapshot.state >= SYSTEM_NAVIGATION_DEAD_RECKONING))
        { mask |= (uint8_t)(1U << group); }
    }
    return mask;
}

void SystemNavigationHealth_ImuQualityRecord(uint32_t quality_flags)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    /* A lost/invalid inertial interval cannot be repaired by later good GNSS.
       A lifecycle initialization is required to clear this latch. */
    s_imu_faults |= quality_flags & 0x72U;
    s_imu_quality = quality_flags;
    PlatformCritical_Exit(lock);
}

uint8_t SystemNavigationHealth_ChangesGet(uint64_t evaluation_us)
{
    SystemNavigationGroupHealth snapshot;
    uint8_t mask = 0U, group;
    for (group = 0U; group < SYSTEM_NAVIGATION_GROUP_COUNT; group++)
    {
        if ((SystemNavigationHealth_GroupGet(group, evaluation_us, &snapshot) == SYSTEM_DEVICE_OK) &&
            ((uint8_t)snapshot.state != s_previous_state[group]))
        {
            mask |= (uint8_t)(1U << group);
            s_previous_state[group] = (uint8_t)snapshot.state;
        }
    }
    return mask;
}

SystemNavigationHealth SystemNavigationHealth_OverallGet(uint64_t evaluation_us,
    uint8_t required_mask, uint32_t imu_quality_flags)
{
    SystemNavigationGroupHealth snapshot;
    PlatformCriticalState lock;
    uint32_t imu_faults, imu_quality;
    uint8_t model_mismatch;
    uint8_t group, stale = 0U, seen = 0U, warmup = 0U, quality_degraded = 0U;
    SILVERSTAR_ASSERT(required_mask < (1U << SYSTEM_NAVIGATION_GROUP_COUNT),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    lock = PlatformCritical_Enter();
    model_mismatch = s_model_mismatch; imu_faults = s_imu_faults; imu_quality = s_imu_quality;
    PlatformCritical_Exit(lock);
    SILVERSTAR_ASSERT(model_mismatch <= 1U && (imu_faults & ~0x72U) == 0U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((model_mismatch != 0U) || ((imu_faults | (imu_quality_flags & 0x72U)) != 0U))
    { return SYSTEM_NAVIGATION_HEALTH_INVALID; }
    if (required_mask == 0U) { return SYSTEM_NAVIGATION_HEALTH_DEAD_RECKONING; }
    for (group = 0U; group < SYSTEM_NAVIGATION_GROUP_COUNT; group++)
    {
        if ((required_mask & (1U << group)) == 0U) { continue; }
        seen++;
        if ((SystemNavigationHealth_GroupGet(group, evaluation_us, &snapshot) != SYSTEM_DEVICE_OK) ||
            (snapshot.state == SYSTEM_NAVIGATION_INVALID)) { return SYSTEM_NAVIGATION_HEALTH_INVALID; }
        if (snapshot.state == SYSTEM_NAVIGATION_DEAD_RECKONING) { stale++; }
        if (!snapshot.has_success) { warmup = 1U; }
        if ((snapshot.quality > 1U) || (snapshot.state == SYSTEM_NAVIGATION_SOFT_WEIGHTED))
        { quality_degraded = 1U; }
    }
    if (stale == seen) { return SYSTEM_NAVIGATION_HEALTH_DEAD_RECKONING; }
    if ((stale != 0U) || (quality_degraded != 0U) ||
        (((imu_quality_flags | imu_quality) & 0x05U) != 0U))
    { return SYSTEM_NAVIGATION_HEALTH_DEGRADED; }
    return warmup ? SYSTEM_NAVIGATION_HEALTH_WARMUP : SYSTEM_NAVIGATION_HEALTH_HEALTHY;
}
