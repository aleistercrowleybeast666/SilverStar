#include "system_time.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "platform_time.h"
#include "silverstar_assert.h"

static uint8_t s_time_source_ready;
static uint64_t s_mission_start_us;
static uint64_t s_mission_stop_us;
static uint8_t s_mission_started;
static uint8_t s_mission_stopped;
static SystemUtcSnapshot s_utc_mapping;

static PlatformCriticalState SystemTime_Lock(void)
{
    return PlatformCritical_Enter();
}

static void SystemTime_Unlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

SystemDeviceResult SystemTime_Init(void)
{
    PlatformCriticalState state;
    uint64_t first_timestamp_us;
    uint64_t second_timestamp_us;

    SILVERSTAR_ASSERT(s_time_source_ready <= 1U,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((s_mission_started <= 1U) &&
                      (s_mission_stopped <= 1U),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    s_time_source_ready = 0U;
    if (PlatformTime_Init() != PLATFORM_OK)
    {
        s_mission_start_us = 0ULL;
        s_mission_stop_us = 0ULL;
        s_mission_started = 0U;
        s_mission_stopped = 0U;
        (void)memset(&s_utc_mapping, 0, sizeof(s_utc_mapping));
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }

    state = SystemTime_Lock();
    s_mission_start_us = 0ULL;
    s_mission_stop_us = 0ULL;
    s_mission_started = 0U;
    s_mission_stopped = 0U;
    (void)memset(&s_utc_mapping, 0, sizeof(s_utc_mapping));
    first_timestamp_us = PlatformTime_Us();
    second_timestamp_us = PlatformTime_Us();
    SystemTime_Unlock(state);
    if (second_timestamp_us < first_timestamp_us)
    {
        s_time_source_ready = 0U;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    s_time_source_ready = 1U;
    return SYSTEM_DEVICE_OK;
}

uint64_t SystemTime_GetMonotonicUs(void)
{
    if (s_time_source_ready == 0U)
    {
        return 0ULL;
    }

    return PlatformTime_Us();
}

uint64_t SystemTime_GetMonotonicUsFromIsr(void)
{
    return SystemTime_GetMonotonicUs();
}

void SystemTime_MissionStart(uint64_t timestamp_us)
{
    PlatformCriticalState state;

    if (s_time_source_ready == 0U)
    {
        return;
    }

    state = SystemTime_Lock();
    if (s_mission_started == 0U)
    {
        s_mission_start_us = timestamp_us;
        s_mission_stop_us = 0ULL;
        s_mission_started = 1U;
        s_mission_stopped = 0U;
    }
    SystemTime_Unlock(state);
}

void SystemTime_MissionStop(uint64_t timestamp_us)
{
    PlatformCriticalState state;

    if (s_time_source_ready == 0U)
    {
        return;
    }

    state = SystemTime_Lock();
    if ((s_mission_started != 0U) && (s_mission_stopped == 0U))
    {
        s_mission_stop_us = (timestamp_us >= s_mission_start_us) ?
            timestamp_us : s_mission_start_us;
        s_mission_stopped = 1U;
    }
    SystemTime_Unlock(state);
}

void SystemTime_MissionReset(void)
{
    PlatformCriticalState state;

    if (s_time_source_ready == 0U)
    {
        return;
    }

    state = SystemTime_Lock();
    s_mission_start_us = 0ULL;
    s_mission_stop_us = 0ULL;
    s_mission_started = 0U;
    s_mission_stopped = 0U;
    SystemTime_Unlock(state);
}

uint8_t SystemTime_IsMissionStarted(void)
{
    uint8_t mission_started;
    PlatformCriticalState state;

    if (s_time_source_ready == 0U)
    {
        return 0U;
    }

    state = SystemTime_Lock();
    mission_started = s_mission_started;
    SystemTime_Unlock(state);
    return mission_started;
}

uint8_t SystemTime_GetMissionUsAt(uint64_t monotonic_us,
                                  uint64_t *mission_us)
{
    uint64_t mission_start_us;
    uint64_t mission_stop_us;
    uint8_t mission_started;
    uint8_t mission_stopped;
    PlatformCriticalState state;

    if ((mission_us == NULL) || (s_time_source_ready == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(mission_us, uint64_t,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);

    state = SystemTime_Lock();
    mission_start_us = s_mission_start_us;
    mission_stop_us = s_mission_stop_us;
    mission_started = s_mission_started;
    mission_stopped = s_mission_stopped;
    SystemTime_Unlock(state);

    if ((mission_started == 0U) || (monotonic_us < mission_start_us))
    {
        return 0U;
    }

    if ((mission_stopped != 0U) && (monotonic_us > mission_stop_us))
    {
        monotonic_us = mission_stop_us;
    }
    *mission_us = monotonic_us - mission_start_us;
    return 1U;
}

uint64_t SystemTime_GetMissionUs(void)
{
    uint64_t mission_us = 0ULL;

    (void)SystemTime_GetMissionUsAt(SystemTime_GetMonotonicUs(), &mission_us);
    return mission_us;
}

SystemDeviceResult SystemTime_UpdateUtcMapping(
    const SystemUtcMeasurement *measurement)
{
    PlatformCriticalState state;

    if ((measurement == NULL) ||
        (measurement->source == SYSTEM_UTC_SOURCE_NONE))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(measurement, SystemUtcMeasurement,
                             SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (s_time_source_ready == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }

    state = SystemTime_Lock();
    s_utc_mapping.monotonic_timestamp_us = measurement->monotonic_timestamp_us;
    s_utc_mapping.utc_time_us = measurement->utc_time_us;
    s_utc_mapping.uncertainty_us = measurement->uncertainty_us;
    s_utc_mapping.source = measurement->source;
    s_utc_mapping.valid = 1U;
    SystemTime_Unlock(state);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemTime_GetUtc(SystemUtcSnapshot *snapshot)
{
    PlatformCriticalState state;

    if (snapshot == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_time_source_ready == 0U)
    {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        return SYSTEM_DEVICE_NOT_READY;
    }

    state = SystemTime_Lock();
    *snapshot = s_utc_mapping;
    SystemTime_Unlock(state);
    return (snapshot->valid != 0U) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemMeasurementTimeResult SystemTime_MeasurementTimestampResolve(
    uint64_t receive_us, uint64_t native_mcu_us, uint8_t native_trusted,
    uint32_t configured_delay_ms, uint64_t *measurement_us)
{
    uint64_t delay_us = (uint64_t)configured_delay_ms * 1000ULL;
    if ((measurement_us == NULL) || (receive_us == 0U) || (native_trusted > 1U))
    { return SYSTEM_MEASUREMENT_TIME_INVALID; }
    if (native_trusted != 0U)
    {
        if ((native_mcu_us == 0U) || (native_mcu_us > receive_us))
        { return SYSTEM_MEASUREMENT_TIME_INVALID; }
        *measurement_us = native_mcu_us;
    }
    else
    {
        if (receive_us < delay_us) { return SYSTEM_MEASUREMENT_TIME_INVALID; }
        *measurement_us = receive_us - delay_us;
    }
    return SYSTEM_MEASUREMENT_TIME_OK;
}
