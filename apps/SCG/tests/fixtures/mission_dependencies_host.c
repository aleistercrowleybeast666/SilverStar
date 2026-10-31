#include "system_mission_process.h"
#include <assert.h>
#include <string.h>
static uint64_t s_now = 10U;
uint64_t SystemTime_GetMonotonicUs(void) { return s_now; }

int main(void)
{
    SystemMissionProcessInput input;
    (void)memset(&input, 0, sizeof(input));
    SystemMissionProcess_Init();
    input.events = 3U;
    input.mission_started = 1U;
    input.now_us = 1U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    input.now_us = 2U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    /* The selected interval is active, but an unavailable upstream output
     * must stop data publication. Recording has no dependency in this model. */
    assert(SystemMissionProcess_TelemetryActiveGet() == 0U);
    assert(SystemMissionProcess_LoggingActiveGet() == 1U);
    input.now_us = 3U; input.ready_function_mask = 8U;
    input.ready_timestamp_us[1] = 3U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Complete);
    assert(SystemMissionProcess_TelemetryActiveGet() == 1U);
    input.now_us = 4U; input.ready_function_mask = 0U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Complete);
    assert(SystemMissionProcess_TelemetryActiveGet() == 0U);
    input.now_us = 5U; input.ready_function_mask = 8U;
    input.ready_timestamp_us[1] = 5U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Complete);
    assert(SystemMissionProcess_TelemetryActiveGet() == 1U);
    s_now = 100006U; /* FlightTask stops updating: cached readiness must expire. */
    assert(SystemMissionProcess_TelemetryActiveGet() == 0U);
    input.now_us = 100007U; input.ready_timestamp_us[1] = 100007U; s_now = 100007U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Complete);
    assert(SystemMissionProcess_TelemetryActiveGet() == 1U);
    input.now_us = 100008U; input.terminated = 1U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Complete);
    assert(SystemMissionProcess_TelemetryActiveGet() == 0U);
    return 0;
}
