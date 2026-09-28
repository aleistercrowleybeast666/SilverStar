#include "system_estimator_diagnostics.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"

static SystemEstimatorBaroDiagnostics s_barometer_diagnostics;
static uint8_t s_barometer_diagnostics_valid;
static SystemEstimatorStatusDiagnostics s_estimator_status_diagnostics;
static SystemEstimatorGnssDiagnostics s_estimator_gnss_diagnostics;
static SystemKfDiagnostics s_kf_diagnostics;
static SystemInsDiagnostics s_ins_diagnostics;
static uint8_t s_estimator_status_diagnostics_valid;
static uint8_t s_estimator_gnss_diagnostics_valid;
static uint8_t s_kf_diagnostics_valid;
static uint8_t s_ins_diagnostics_valid;

#define SYSTEM_BARO_EVENT_WAIT_LIMIT_US 1000000ULL

uint8_t SystemEstimatorBaroDiagnostics_EventPending(
    SystemEstimatorBaroDiagnostics *diagnostics)
{
    SystemEstimatorBaroUpdateState state;
    uint8_t anomaly;
    if (diagnostics == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemEstimatorBaroDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    state = diagnostics->last_update_state;
    if (state == SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP)
    {
        if ((diagnostics->wait_start_timestamp_us == 0U) ||
            (diagnostics->last_update_timestamp_us < diagnostics->wait_start_timestamp_us))
        { diagnostics->wait_start_timestamp_us = diagnostics->last_update_timestamp_us; }
        if (diagnostics->last_update_timestamp_us - diagnostics->wait_start_timestamp_us <
            SYSTEM_BARO_EVENT_WAIT_LIMIT_US)
        { return 0U; }
    }
    else { diagnostics->wait_start_timestamp_us = 0U; }
    anomaly = (uint8_t)((state != SYSTEM_ESTIMATOR_BARO_UPDATE_NONE) &&
        (state != SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED) &&
        (state != SYSTEM_ESTIMATOR_BARO_UPDATE_SOFTENED));
    if ((anomaly == 0U) && (diagnostics->event_anomaly_active == 0U))
    { return 0U; }
    if ((anomaly != 0U) && (diagnostics->event_anomaly_active != 0U) &&
        (diagnostics->event_state == state) &&
        (diagnostics->event_reason == diagnostics->last_skip_reason))
    { return 0U; }
    diagnostics->event_state = state;
    diagnostics->event_reason = diagnostics->last_skip_reason;
    diagnostics->event_anomaly_active = anomaly;
    return 1U;
}

static PlatformCriticalState SystemEstimatorBaroDiagnostics_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemEstimatorBaroDiagnostics_IrqUnlock(
    PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

static uint32_t SystemEstimatorBaroDiagnostics_AgeMsGet(
    uint64_t timestamp_us,
    uint64_t now_us)
{
    uint64_t age_ms;

    if ((timestamp_us == 0U) || (timestamp_us > now_us))
    {
        return UINT32_MAX;
    }
    age_ms = (now_us - timestamp_us) / 1000ULL;
    return (age_ms > UINT32_MAX) ? UINT32_MAX : (uint32_t)age_ms;
}

void SystemEstimatorBaroDiagnostics_Reset(void)
{
    uint32_t primask = SystemEstimatorBaroDiagnostics_IrqLock();

    (void)memset(&s_barometer_diagnostics, 0,
                 sizeof(s_barometer_diagnostics));
    s_barometer_diagnostics_valid = 0U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

void SystemEstimatorBaroDiagnostics_UpdateRecord(
    SystemEstimatorBaroDiagnostics *diagnostics,
    SystemEstimatorBaroUpdateState state,
    SystemEstimatorBaroSkipReason reason,
    uint64_t timestamp_us,
    uint8_t count_event)
{
    if (diagnostics == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemEstimatorBaroDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    diagnostics->last_update_state = state;
    diagnostics->last_skip_reason = reason;
    diagnostics->last_update_timestamp_us = timestamp_us;
    if (count_event == 0U)
    {
        return;
    }
    switch (state)
    {
        case SYSTEM_ESTIMATOR_BARO_UPDATE_ACCEPTED:
            diagnostics->accepted_count++;
            break;
        case SYSTEM_ESTIMATOR_BARO_UPDATE_SOFTENED:
            diagnostics->softened_count++;
            break;
        case SYSTEM_ESTIMATOR_BARO_UPDATE_REJECTED:
            diagnostics->rejected_count++;
            break;
        case SYSTEM_ESTIMATOR_BARO_UPDATE_NONE:
            break;
        case SYSTEM_ESTIMATOR_BARO_UPDATE_NO_SAMPLE:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_UNSUPPORTED:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_NOT_READY:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_STALE:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_ORIGIN_NOT_READY:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_INVALID:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_DISABLED:
        case SYSTEM_ESTIMATOR_BARO_UPDATE_WAIT_STATE_CATCHUP:
        default:
            diagnostics->skipped_count++;
            break;
    }
}

void SystemEstimatorBaroDiagnostics_Publish(
    const SystemEstimatorBaroDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    s_barometer_diagnostics = *diagnostics;
    s_barometer_diagnostics_valid = 1U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

uint8_t SystemEstimatorBaroDiagnostics_Get(
    SystemEstimatorBaroDiagnostics *diagnostics,
    uint64_t now_us)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemEstimatorBaroDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    if (s_barometer_diagnostics_valid == 0U)
    {
        SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
        return 0U;
    }
    *diagnostics = s_barometer_diagnostics;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
    diagnostics->sample_age_ms =
        SystemEstimatorBaroDiagnostics_AgeMsGet(
            diagnostics->sample_timestamp_us, now_us);
    diagnostics->last_update_age_ms =
        SystemEstimatorBaroDiagnostics_AgeMsGet(
            diagnostics->last_update_timestamp_us, now_us);
    return 1U;
}

void SystemEstimatorStatusDiagnostics_Reset(void)
{
    uint32_t primask = SystemEstimatorBaroDiagnostics_IrqLock();

    (void)memset(&s_estimator_status_diagnostics, 0,
                 sizeof(s_estimator_status_diagnostics));
    s_estimator_status_diagnostics_valid = 0U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

void SystemEstimatorStatusDiagnostics_Publish(
    const SystemEstimatorStatusDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    s_estimator_status_diagnostics = *diagnostics;
    s_estimator_status_diagnostics_valid = 1U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

uint8_t SystemEstimatorStatusDiagnostics_Get(
    SystemEstimatorStatusDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return 0U;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    if (s_estimator_status_diagnostics_valid == 0U)
    {
        SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
        return 0U;
    }
    *diagnostics = s_estimator_status_diagnostics;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
    return 1U;
}

void SystemEstimatorGnssDiagnostics_Reset(void)
{
    uint32_t primask = SystemEstimatorBaroDiagnostics_IrqLock();

    (void)memset(&s_estimator_gnss_diagnostics, 0,
                 sizeof(s_estimator_gnss_diagnostics));
    s_estimator_gnss_diagnostics_valid = 0U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

void SystemEstimatorGnssDiagnostics_Publish(
    const SystemEstimatorGnssDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    s_estimator_gnss_diagnostics = *diagnostics;
    s_estimator_gnss_diagnostics_valid = 1U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

uint8_t SystemEstimatorGnssDiagnostics_Get(
    SystemEstimatorGnssDiagnostics *diagnostics,
    uint64_t now_us)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemEstimatorGnssDiagnostics,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    if (s_estimator_gnss_diagnostics_valid == 0U)
    {
        SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
        return 0U;
    }
    *diagnostics = s_estimator_gnss_diagnostics;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
    diagnostics->measurement_age_ms =
        SystemEstimatorBaroDiagnostics_AgeMsGet(
            diagnostics->last_measurement_timestamp_us, now_us);
    return 1U;
}

void SystemKfDiagnostics_Reset(void)
{
    uint32_t primask = SystemEstimatorBaroDiagnostics_IrqLock();

    (void)memset(&s_kf_diagnostics, 0, sizeof(s_kf_diagnostics));
    s_kf_diagnostics_valid = 0U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

void SystemKfDiagnostics_Publish(const SystemKfDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    s_kf_diagnostics = *diagnostics;
    s_kf_diagnostics_valid = 1U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

uint8_t SystemKfDiagnostics_Get(SystemKfDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return 0U;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    if (s_kf_diagnostics_valid == 0U)
    {
        SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
        return 0U;
    }
    *diagnostics = s_kf_diagnostics;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
    return 1U;
}

void SystemInsDiagnostics_Reset(void)
{
    uint32_t primask = SystemEstimatorBaroDiagnostics_IrqLock();

    (void)memset(&s_ins_diagnostics, 0, sizeof(s_ins_diagnostics));
    s_ins_diagnostics_valid = 0U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

void SystemInsDiagnostics_Publish(const SystemInsDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    s_ins_diagnostics = *diagnostics;
    s_ins_diagnostics_valid = 1U;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
}

uint8_t SystemInsDiagnostics_Get(SystemInsDiagnostics *diagnostics)
{
    uint32_t primask;

    if (diagnostics == NULL)
    {
        return 0U;
    }
    primask = SystemEstimatorBaroDiagnostics_IrqLock();
    if (s_ins_diagnostics_valid == 0U)
    {
        SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
        return 0U;
    }
    *diagnostics = s_ins_diagnostics;
    SystemEstimatorBaroDiagnostics_IrqUnlock(primask);
    return 1U;
}
