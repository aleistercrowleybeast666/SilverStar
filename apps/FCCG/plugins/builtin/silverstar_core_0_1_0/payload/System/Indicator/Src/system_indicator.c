#include "system_indicator.h"

#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"
#include "system_gnss_if.h"
#include "system_health.h"
#include "system_time.h"
#include "system_user_config.h"

typedef struct
{
    SystemIndicatorMode base_mode[SYSTEM_INDICATOR_COUNT];
    SystemIndicatorMode transient_mode[SYSTEM_INDICATOR_COUNT];
    uint64_t transient_until_us[SYSTEM_INDICATOR_COUNT];
    uint8_t transient_active[SYSTEM_INDICATOR_COUNT];
    uint8_t output_known[SYSTEM_INDICATOR_COUNT];
    uint8_t last_output[SYSTEM_INDICATOR_COUNT];
    uint32_t calibration_face_event_sequence;
    uint32_t alignment_start_sequence;
    SystemCalibrationState calibration_state;
    SystemAlignmentState alignment_state;
    uint8_t calibration_observed;
    uint8_t alignment_observed;
    uint8_t initialized;
} SystemIndicatorRuntime;

static SystemIndicatorRuntime s_indicator;

static uint8_t SystemIndicator_RoleEnabled(SystemIndicatorRole role)
{
    switch (role)
    {
        case SYSTEM_INDICATOR_SYSTEM:
            return (uint8_t)SYSTEM_INDICATOR_SYSTEM_ENABLE;
        case SYSTEM_INDICATOR_GNSS:
            return (uint8_t)SYSTEM_INDICATOR_GNSS_ENABLE;
        case SYSTEM_INDICATOR_SAFETY:
            return (uint8_t)SYSTEM_INDICATOR_SAFETY_ENABLE;
        case SYSTEM_INDICATOR_COUNT:
        default:
            return 0U;
    }
}

static uint8_t SystemIndicator_OutputResolve(SystemIndicatorMode mode,
                                             uint64_t now_us)
{
    switch (mode)
    {
        case SYSTEM_INDICATOR_MODE_ON:
            return 1U;
        case SYSTEM_INDICATOR_MODE_BLINK_FAST:
            return (uint8_t)(((now_us / SYSTEM_INDICATOR_FAST_HALF_PERIOD_US) &
                              1ULL) == 0ULL);
        case SYSTEM_INDICATOR_MODE_BLINK_SLOW:
            return (uint8_t)(((now_us / SYSTEM_INDICATOR_SLOW_HALF_PERIOD_US) &
                              1ULL) == 0ULL);
        case SYSTEM_INDICATOR_MODE_OFF:
        default:
            return 0U;
    }
}

static SystemIndicatorMode SystemIndicator_EffectiveModeGet(
    SystemIndicatorRole role,
    uint64_t now_us)
{
    if ((s_indicator.transient_active[role] != 0U) &&
        (now_us < s_indicator.transient_until_us[role]))
    {
        return s_indicator.transient_mode[role];
    }
    s_indicator.transient_active[role] = 0U;
    return s_indicator.base_mode[role];
}

static void SystemIndicator_OutputRefresh(SystemIndicatorRole role,
                                          uint64_t now_us)
{
    SystemIndicatorMode effective_mode;
    uint8_t output;

    SILVERSTAR_ASSERT(role <= SYSTEM_INDICATOR_COUNT,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(s_indicator.initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((role >= SYSTEM_INDICATOR_COUNT) ||
        (SystemIndicator_RoleEnabled(role) == 0U))
    {
        return;
    }
    effective_mode = SystemIndicator_EffectiveModeGet(role, now_us);
    output = SystemIndicator_OutputResolve(effective_mode, now_us);
    if ((s_indicator.output_known[role] != 0U) &&
        (s_indicator.last_output[role] == output))
    {
        return;
    }
    if (SystemIndicatorDevice_Set((uint8_t)role, output) == SYSTEM_DEVICE_OK)
    {
        s_indicator.last_output[role] = output;
        s_indicator.output_known[role] = 1U;
    }
}

static void SystemIndicator_SystemConfirmNotify(void)
{
    SystemDeviceResult result = SystemIndicator_Notify(
        SYSTEM_INDICATOR_SYSTEM,
        SYSTEM_INDICATOR_MODE_ON,
        SYSTEM_INDICATOR_EVENT_CONFIRM_US);

    (void)result;
}

static void SystemIndicator_CalibrationEventsProcess(
    const SystemCalibrationStatus *calibration)
{
    if (calibration == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(calibration, SystemCalibrationStatus,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);

    if (s_indicator.calibration_observed == 0U)
    {
        s_indicator.calibration_face_event_sequence =
            calibration->face_event_sequence;
        s_indicator.calibration_state = calibration->state;
        s_indicator.calibration_observed = 1U;
        return;
    }
    if (calibration->face_event_sequence !=
        s_indicator.calibration_face_event_sequence)
    {
        s_indicator.calibration_face_event_sequence =
            calibration->face_event_sequence;
        if (calibration->last_face_result ==
            SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE)
        {
            SystemIndicator_SystemConfirmNotify();
        }
    }
    if (calibration->state != s_indicator.calibration_state)
    {
        if (calibration->state == SYSTEM_CALIBRATION_STATE_READY)
        {
            SystemIndicator_SystemConfirmNotify();
        }
        s_indicator.calibration_state = calibration->state;
    }
}

static void SystemIndicator_AlignmentEventsProcess(
    const SystemAlignmentSummary *alignment)
{
    if (alignment == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(alignment, SystemAlignmentSummary,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);

    if (s_indicator.alignment_observed == 0U)
    {
        s_indicator.alignment_start_sequence = alignment->start_sequence;
        s_indicator.alignment_state = alignment->state;
        s_indicator.alignment_observed = 1U;
        return;
    }
    if ((alignment->state != s_indicator.alignment_state) ||
        (alignment->start_sequence != s_indicator.alignment_start_sequence))
    {
        if ((alignment->start_sequence != 0U) &&
            (alignment->state == SYSTEM_ALIGNMENT_STATE_READY))
        {
            SystemIndicator_SystemConfirmNotify();
        }
        s_indicator.alignment_state = alignment->state;
        s_indicator.alignment_start_sequence = alignment->start_sequence;
    }
}

SystemIndicatorMode SystemIndicator_SystemModeResolve(
    SystemCalibrationState calibration_state,
    uint8_t calibration_ready,
    uint8_t alignment_ready,
    uint8_t system_ready,
    SystemLifecycleState lifecycle_state)
{
    SILVERSTAR_ASSERT((calibration_ready <= 1U) && (alignment_ready <= 1U) &&
                      (system_ready <= 1U),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(lifecycle_state <= SYSTEM_STATE_FAULT,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if ((lifecycle_state == SYSTEM_STATE_FLIGHT) ||
        (lifecycle_state == SYSTEM_STATE_RECOVERY) ||
        (lifecycle_state == SYSTEM_STATE_LANDED) ||
        (lifecycle_state == SYSTEM_STATE_POSTFLIGHT))
    {
        return SYSTEM_INDICATOR_MODE_ON;
    }
    if ((calibration_ready != 0U) &&
        (alignment_ready != 0U) &&
        (system_ready != 0U))
    {
        return SYSTEM_INDICATOR_MODE_ON;
    }
    if (calibration_ready != 0U)
    {
        return SYSTEM_INDICATOR_MODE_BLINK_SLOW;
    }
    if ((calibration_state == SYSTEM_CALIBRATION_STATE_WAIT_FACE) ||
        (calibration_state == SYSTEM_CALIBRATION_STATE_COLLECTING) ||
        (calibration_state == SYSTEM_CALIBRATION_STATE_CHECKING))
    {
        return SYSTEM_INDICATOR_MODE_BLINK_FAST;
    }
    return SYSTEM_INDICATOR_MODE_OFF;
}

SystemIndicatorMode SystemIndicator_GnssModeResolve(
    SystemDeviceResult health_result,
    uint8_t initialized,
    uint8_t online,
    SystemDeviceResult sample_result,
    uint8_t position_usable)
{
    SILVERSTAR_ASSERT((initialized <= 1U) && (online <= 1U) &&
                      (position_usable <= 1U),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((health_result <= SYSTEM_DEVICE_BUSY) &&
                      (sample_result <= SYSTEM_DEVICE_BUSY),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if ((health_result != SYSTEM_DEVICE_OK) || (initialized == 0U) ||
        (online == 0U) || (sample_result != SYSTEM_DEVICE_OK))
    {
        return SYSTEM_INDICATOR_MODE_OFF;
    }
    if (position_usable == 0U)
    {
        return SYSTEM_INDICATOR_MODE_BLINK_SLOW;
    }
    return SYSTEM_INDICATOR_MODE_ON;
}

static void SystemIndicator_GnssModeUpdate(void)
{
    SystemDeviceHealth health;
    SystemGnssSample sample;
    SystemDeviceResult health_result;
    SystemDeviceResult sample_result = SYSTEM_DEVICE_NOT_READY;

    (void)memset(&health, 0, sizeof(health));
    (void)memset(&sample, 0, sizeof(sample));
    health_result = SystemGnss_HealthGet(&health);
    if ((health_result == SYSTEM_DEVICE_OK) &&
        (health.initialized != 0U) && (health.online != 0U))
    {
        sample_result = SystemGnss_LatestSampleGet(&sample);
    }
    s_indicator.base_mode[SYSTEM_INDICATOR_GNSS] =
        SystemIndicator_GnssModeResolve(
            health_result, health.initialized, health.online,
            sample_result, sample.position_usable);
}

void SystemIndicator_Init(void)
{
    (void)memset(&s_indicator, 0, sizeof(s_indicator));
    s_indicator.initialized = 1U;
}

SystemDeviceResult SystemIndicator_ModeSet(SystemIndicatorRole role,
                                           SystemIndicatorMode mode)
{
    if ((role >= SYSTEM_INDICATOR_COUNT) ||
        (mode > SYSTEM_INDICATOR_MODE_BLINK_FAST))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(&s_indicator, SystemIndicatorRuntime,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (s_indicator.initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (SystemIndicator_RoleEnabled(role) == 0U)
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    s_indicator.base_mode[role] = mode;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemIndicator_Notify(SystemIndicatorRole role,
                                          SystemIndicatorMode mode,
                                          uint64_t duration_us)
{
    uint64_t now_us;

    if ((role >= SYSTEM_INDICATOR_COUNT) ||
        (mode > SYSTEM_INDICATOR_MODE_BLINK_FAST) ||
        (duration_us == 0ULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(&s_indicator, SystemIndicatorRuntime,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (s_indicator.initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (SystemIndicator_RoleEnabled(role) == 0U)
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    now_us = SystemTime_GetMonotonicUs();
    s_indicator.transient_mode[role] = mode;
    s_indicator.transient_until_us[role] = now_us + duration_us;
    s_indicator.transient_active[role] = 1U;
    s_indicator.output_known[role] = 0U;
    return SYSTEM_DEVICE_OK;
}

void SystemIndicator_Process(void)
{
    uint64_t now_us;
    SystemCalibrationStatus calibration;
    SystemAlignmentSummary alignment;
    SystemIndicatorMode system_mode;
    uint8_t alignment_ready = 0U;
    uint8_t system_ready;

    SILVERSTAR_ASSERT(s_indicator.initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((SYSTEM_INDICATOR_SYSTEM_ENABLE <= 1U) &&
                      (SYSTEM_INDICATOR_GNSS_ENABLE <= 1U) &&
                      (SYSTEM_INDICATOR_SAFETY_ENABLE <= 1U),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_indicator.initialized == 0U)
    {
        return;
    }
    now_us = SystemTime_GetMonotonicUs();
    if ((SYSTEM_INDICATOR_SYSTEM_ENABLE != 0U) &&
        (SystemCalibration_StatusGet(&calibration) == SYSTEM_DEVICE_OK))
    {
        if (SystemAlignment_SummaryGet(&alignment) == SYSTEM_DEVICE_OK)
        {
            alignment_ready = alignment.ready;
            SystemIndicator_AlignmentEventsProcess(&alignment);
        }
        system_ready = SystemHealth_IsReady();
        system_mode = SystemIndicator_SystemModeResolve(
            calibration.state,
            calibration.ready,
            alignment_ready,
            system_ready,
            SystemLifecycle_GetState());
        s_indicator.base_mode[SYSTEM_INDICATOR_SYSTEM] = system_mode;
        SystemIndicator_CalibrationEventsProcess(&calibration);
    }
    if (SYSTEM_INDICATOR_GNSS_ENABLE != 0U)
    {
        SystemIndicator_GnssModeUpdate();
    }
    SystemIndicator_OutputRefresh(SYSTEM_INDICATOR_SYSTEM, now_us);
    SystemIndicator_OutputRefresh(SYSTEM_INDICATOR_GNSS, now_us);
    SystemIndicator_OutputRefresh(SYSTEM_INDICATOR_SAFETY, now_us);
}
