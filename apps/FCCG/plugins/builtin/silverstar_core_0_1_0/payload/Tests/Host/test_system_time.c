#include <stdint.h>

#include "platform_critical.h"
#include "platform_time.h"
#include "system_time.h"
#include "test_common.h"

static uint64_t s_fake_now_us;
static uint32_t s_lock_depth;
static uint32_t s_lock_count;
static uint32_t s_unlock_count;

PlatformResult PlatformTime_Init(void)
{
    s_lock_depth = 0U;
    s_lock_count = 0U;
    s_unlock_count = 0U;
    return PLATFORM_OK;
}

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState previous = s_lock_depth;

    s_lock_depth++;
    s_lock_count++;
    return previous;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    TEST_CHECK(s_lock_depth > 0U);
    s_lock_depth = state;
    s_unlock_count++;
}

uint64_t PlatformTime_Us(void)
{
    return s_fake_now_us;
}

uint32_t PlatformTime_Ms(void)
{
    return (uint32_t)(s_fake_now_us / 1000ULL);
}

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    s_fake_now_us += (uint64_t)delay_ms * 1000ULL;
}

static void Test_MonotonicAndMissionTime(void)
{
    uint64_t mission_us = 0ULL;

    s_fake_now_us = 1000ULL;
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTime_GetMonotonicUs() == 1000ULL);

    s_fake_now_us = 1100ULL;
    TEST_CHECK(SystemTime_GetMonotonicUsFromIsr() == 1100ULL);
    TEST_CHECK(SystemTime_IsMissionStarted() == 0U);
    TEST_CHECK(SystemTime_GetMissionUsAt(1100ULL, &mission_us) == 0U);
    TEST_CHECK(SystemTime_GetMissionUsAt(1100ULL, NULL) == 0U);

    SystemTime_MissionStart(1200ULL);
    TEST_CHECK(SystemTime_IsMissionStarted() != 0U);
    SystemTime_MissionStart(1300ULL); /* Idempotent: first START wins. */

    s_fake_now_us = 1700ULL;
    TEST_CHECK(SystemTime_GetMissionUs() == 500ULL);
    TEST_CHECK(SystemTime_GetMissionUsAt(1199ULL, &mission_us) == 0U);
    TEST_CHECK(SystemTime_GetMissionUsAt(1600ULL, &mission_us) != 0U);
    TEST_CHECK(mission_us == 400ULL);

    SystemTime_MissionStop(1800ULL);
    s_fake_now_us = 2400ULL;
    TEST_CHECK(SystemTime_GetMissionUs() == 600ULL);
    SystemTime_MissionStop(2600ULL); /* Idempotent: first STOP wins. */
    TEST_CHECK(SystemTime_GetMissionUs() == 600ULL);

    SystemTime_MissionReset();
    TEST_CHECK(SystemTime_IsMissionStarted() == 0U);
    TEST_CHECK(SystemTime_GetMissionUs() == 0ULL);
}

static void Test_UtcMapping(void)
{
    SystemUtcMeasurement measurement;
    SystemUtcSnapshot snapshot;

    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTime_GetUtc(NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemTime_GetUtc(&snapshot) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(SystemTime_UpdateUtcMapping(NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);

    measurement.monotonic_timestamp_us = 5000000ULL;
    measurement.utc_time_us = 1900000000000000LL;
    measurement.uncertainty_us = 250U;
    measurement.source = SYSTEM_UTC_SOURCE_NONE;
    TEST_CHECK(SystemTime_UpdateUtcMapping(&measurement) ==
               SYSTEM_DEVICE_INVALID_ARGUMENT);

    measurement.source = SYSTEM_UTC_SOURCE_GNSS;
    TEST_CHECK(SystemTime_UpdateUtcMapping(&measurement) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTime_GetUtc(&snapshot) == SYSTEM_DEVICE_OK);
    TEST_CHECK(snapshot.valid != 0U);
    TEST_CHECK(snapshot.monotonic_timestamp_us == measurement.monotonic_timestamp_us);
    TEST_CHECK(snapshot.utc_time_us == measurement.utc_time_us);
    TEST_CHECK(snapshot.uncertainty_us == measurement.uncertainty_us);
    TEST_CHECK(snapshot.source == SYSTEM_UTC_SOURCE_GNSS);
}

int main(void)
{
    Test_MonotonicAndMissionTime();
    Test_UtcMapping();
    TEST_CHECK(s_lock_depth == 0U);
    TEST_CHECK(s_lock_count == s_unlock_count);
    return Test_Finish("system_time");
}
