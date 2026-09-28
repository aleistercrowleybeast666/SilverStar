#include "system_health.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_alignment.h"
#include "system_calibration.h"
#include "system_profile.h"
#include "system_navigation_profile.h"
#include "system_output_if.h"
#include "system_startup.h"
#include "system_time.h"

static SystemHealthSnapshot s_health;
static uint8_t s_attitude_ready;
static SystemHealthAttitudeStatus s_attitude_status;

static uint32_t SystemHealth_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemHealth_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static uint8_t SystemHealth_OutputSafe(uint8_t channel_count)
{
    SystemOutputStatus status;
    uint16_t channel;

    SILVERSTAR_ASSERT_OBJECT(&s_health, SystemHealthSnapshot,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (channel_count == 0U)
    {
        return 0U;
    }
    for (channel = 1U; channel <= channel_count; channel++)
    {
        if ((SystemOutput_StatusGet((uint8_t)channel, &status) !=
             SYSTEM_DEVICE_OK) ||
            (status.state != SYSTEM_OUTPUT_SAFE) ||
            (status.physical_active != 0U) ||
            (status.fault != 0U))
        {
            return 0U;
        }
    }
    return 1U;
}

void SystemHealth_Init(void)
{
    uint32_t primask = SystemHealth_IrqLock();

    (void)memset(&s_health, 0, sizeof(s_health));
    s_attitude_ready = 0U;
    s_attitude_status = SYSTEM_HEALTH_ATTITUDE_UNKNOWN;
    SystemHealth_IrqUnlock(primask);
}

void SystemHealth_SetAttitudeReady(uint8_t ready)
{
    SystemHealth_SetAttitudeState(
        ready,
        (ready != 0U) ? SYSTEM_HEALTH_ATTITUDE_READY :
                        SYSTEM_HEALTH_ATTITUDE_UNKNOWN);
}

void SystemHealth_SetAttitudeState(uint8_t ready,
                                   SystemHealthAttitudeStatus status)
{
    uint32_t primask = SystemHealth_IrqLock();

    s_attitude_ready = (ready != 0U) ? 1U : 0U;
    s_attitude_status = status;
    SystemHealth_IrqUnlock(primask);
}

static uint32_t SystemHealth_ProfileBlockingMaskGet(
    const SystemHealthSnapshot *snapshot,
    const SystemProfile *profile,
    SystemDeviceResult capability_result)
{
    uint32_t available_mask;

    SILVERSTAR_ASSERT_OBJECT(snapshot, SystemHealthSnapshot,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((profile == NULL) || (capability_result != SYSTEM_DEVICE_OK))
    {
        return SYSTEM_HEALTH_BLOCK_PROFILE_INVALID;
    }
    available_mask = snapshot->capabilities.present_mask &
                     snapshot->capabilities.healthy_mask;
    if ((available_mask & profile->required_capabilities) !=
        profile->required_capabilities)
    {
        return SYSTEM_HEALTH_BLOCK_REQUIRED_DEVICE;
    }
    return 0U;
}

static uint32_t SystemHealth_StartupBlockingMaskGet(
    SystemHealthSnapshot *snapshot,
    const SystemStartupReport *startup_report)
{
    SILVERSTAR_ASSERT_OBJECT(snapshot, SystemHealthSnapshot,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((startup_report == NULL) || (startup_report->completed == 0U))
    {
        return SYSTEM_HEALTH_BLOCK_STARTUP_INCOMPLETE;
    }
    snapshot->warning_mask = startup_report->warning_mask;
    return (startup_report->mission_capable == 0U) ?
        SYSTEM_HEALTH_BLOCK_STARTUP_FAILED : 0U;
}

static uint32_t SystemHealth_SensorBlockingMaskGet(
    const SystemHealthSnapshot *snapshot,
    const SystemNavigationProfile *navigation,
    uint8_t attitude_ready)
{
    uint32_t blocking_mask = 0U;

    SILVERSTAR_ASSERT_OBJECT(snapshot, SystemHealthSnapshot,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (((snapshot->capabilities.present_mask & SYSTEM_CAPABILITY_IMU) == 0U) ||
        ((snapshot->capabilities.healthy_mask & SYSTEM_CAPABILITY_IMU) == 0U))
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_PRIMARY_IMU;
    }
    if (SystemCalibration_IsReady() == 0U)
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_CALIBRATION_NOT_READY;
    }
    if (SystemAlignment_IsReady() == 0U)
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_ALIGNMENT_NOT_READY;
    }
    if ((navigation != NULL) &&
        (navigation->alignment_algorithm == SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD) &&
        (((snapshot->capabilities.present_mask &
           SYSTEM_CAPABILITY_MAGNETOMETER) == 0U) ||
         ((snapshot->capabilities.healthy_mask &
           SYSTEM_CAPABILITY_MAGNETOMETER) == 0U)))
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_REQUIRED_DEVICE;
    }
    if (attitude_ready == 0U)
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_ATTITUDE_UNAVAILABLE;
    }
    return blocking_mask;
}

void SystemHealth_Process(void)
{
    const SystemProfile *profile = SystemProfile_Get();
    const SystemNavigationProfile *navigation = SystemNavigationProfile_Get();
    SystemHealthSnapshot next;
    uint32_t blocking_mask = 0U;
    uint32_t primask;
    uint8_t attitude_ready;
    SystemDeviceResult capability_result;
    const SystemStartupReport *startup_report = SystemStartup_GetReport();

    SystemHealth_GetSnapshot(&next);
    SILVERSTAR_ASSERT_OBJECT(&next, SystemHealthSnapshot,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    capability_result = SystemCapabilities_Refresh();
    SystemCapabilities_Get(&next.capabilities);
    primask = SystemHealth_IrqLock();
    attitude_ready = s_attitude_ready;
    next.attitude_status = s_attitude_status;
    SystemHealth_IrqUnlock(primask);

    blocking_mask |= SystemHealth_ProfileBlockingMaskGet(&next, profile,
        capability_result);
    blocking_mask |= SystemHealth_StartupBlockingMaskGet(&next,
        startup_report);
    blocking_mask |= SystemHealth_SensorBlockingMaskGet(&next, navigation,
        attitude_ready);
    if ((profile == NULL) ||
        (SystemHealth_OutputSafe(profile->output_channel_count) == 0U))
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_OUTPUT_NOT_SAFE;
    }
    if (SilverStarAssert_FaultedGet() != 0U)
    {
        blocking_mask |= SYSTEM_HEALTH_BLOCK_ASSERTION_FAULT;
    }

    next.timestamp_us = SystemTime_GetMonotonicUs();
    next.start_blocking_mask = blocking_mask;
    next.ready = (blocking_mask == 0U) ? 1U : 0U;
    next.sequence++;
    primask = SystemHealth_IrqLock();
    s_health = next;
    SystemHealth_IrqUnlock(primask);
}

void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot)
{
    uint32_t primask;

    if (snapshot != NULL)
    {
        primask = SystemHealth_IrqLock();
        *snapshot = s_health;
        SystemHealth_IrqUnlock(primask);
    }
}

uint8_t SystemHealth_IsReady(void)
{
    uint32_t primask = SystemHealth_IrqLock();
    uint8_t ready = s_health.ready;

    SystemHealth_IrqUnlock(primask);
    return ready;
}

const char *SystemHealth_AttitudeStatusText(SystemHealthAttitudeStatus status)
{
    switch (status)
    {
        case SYSTEM_HEALTH_ATTITUDE_READY: return "READY";
        case SYSTEM_HEALTH_ATTITUDE_CALIBRATION_NOT_READY:
            return "CALIBRATION_NOT_READY";
        case SYSTEM_HEALTH_ATTITUDE_SOURCE_UNAVAILABLE:
            return "SOURCE_UNAVAILABLE";
        case SYSTEM_HEALTH_ATTITUDE_NO_SAMPLE: return "ATTITUDE_NOT_READY";
        case SYSTEM_HEALTH_ATTITUDE_INVALID: return "ATTITUDE_INVALID";
        case SYSTEM_HEALTH_ATTITUDE_STALE: return "ATTITUDE_STALE";
        case SYSTEM_HEALTH_ATTITUDE_UNKNOWN:
        default: return "UNKNOWN";
    }
}
