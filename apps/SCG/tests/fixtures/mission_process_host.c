#include "system_mission_process.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static SystemMissionProcessInput Input(uint64_t time, uint32_t sequence, float force)
{
    SystemMissionProcessInput input;
    (void)memset(&input, 0, sizeof(input));
    input.now_us = time;
    input.acceleration_timestamp_us = time;
    input.acceleration_sequence = sequence;
    input.acceleration_source = 1U;
    input.acceleration_epoch = 1U;
    input.acceleration_g = force;
    input.valid_mask = SYSTEM_MISSION_PROCESS_VALID_ACCEL;
    input.mission_started = 1U;
    input.events = 3U;
    return input;
}

int main(void)
{
    SystemMissionProcessInput input;
    SystemMissionProcessEvent event;
    SystemMissionProcess_Init();
    assert(SystemMissionProcess_TelemetryActiveGet() == 0U);
    assert(SystemMissionProcess_LoggingActiveGet() == 1U);
    assert(SystemMissionProcess_InsStoppedGet() == 0U);
    assert(SystemMissionProcess_EstimatorStoppedGet() == 0U);
    assert(SystemMissionProcess_Step(NULL) == SystemMissionProcessResult_Invalid);
    input = Input(1000U, 1U, 1.0f);
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    input = Input(2000U, 2U, 1.0f);
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    assert(SystemMissionProcess_EventGet(0U, &event) == SystemMissionProcessResult_Entered);
    assert(event.sequence == 1U && event.timestamp_us == 1000U && event.event_code == 256U);
    assert(SystemMissionProcess_EventGet(1U, &event) == SystemMissionProcessResult_Entered);
    assert(event.sequence == 2U && event.timestamp_us == 2000U && event.event_code == 257U);
    assert(SystemMissionProcess_EventGet(3U, &event) == SystemMissionProcessResult_Unavailable);
    input = Input(10000U, 3U, 2.1f);
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input.now_us = 60000U; /* Polling an unchanged sample never advances the hold. */
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(110000U, 4U, NAN);
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(120000U, 5U, 2.1f);
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(220000U, 6U, 2.1f);
    input.acceleration_epoch = 2U; /* Source/epoch switch resets the pending hold. */
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(320000U, 7U, 2.1f); input.acceleration_epoch = 2U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Invalid);
    assert(SystemMissionProcess_TelemetryActiveGet() == 1U);
    input = Input(330000U, 8U, 1.0f); input.acceleration_epoch = 2U;
    input.valid_mask = 0U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(450000U, 9U, 1.0f); input.acceleration_timestamp_us = 340000U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(460000U, 10U, 1.0f); input.acceleration_epoch = 2U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Waiting);
    input = Input(560000U, 11U, 1.0f); input.acceleration_epoch = 2U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Entered);
    assert(SystemMissionProcess_EventGet(6U, &event) == SystemMissionProcessResult_Entered);
    assert(event.timestamp_us == 560000U && event.stage_index == 3U);
    assert(SystemMissionProcess_InsStoppedGet() == 1U);
    assert(SystemMissionProcess_EstimatorStoppedGet() == 1U);
    assert(SystemMissionProcess_TelemetryActiveGet() == 1U);
    assert(SystemMissionProcess_EventGet(7U, &event) == SystemMissionProcessResult_Unavailable);
    input = Input(570000U, 12U, 1.0f); input.terminated = 1U;
    assert(SystemMissionProcess_Step(&input) == SystemMissionProcessResult_Complete);
    assert(SystemMissionProcess_EventGet(7U, &event) == SystemMissionProcessResult_Entered);
    assert(event.timestamp_us == 570000U && event.event_code == 257U);
    assert(SystemMissionProcess_TelemetryActiveGet() == 0U);
    assert(SystemMissionProcess_LoggingActiveGet() == 0U);
    assert(SystemMissionProcess_EventGet(UINT32_MAX, &event) == SystemMissionProcessResult_Unavailable);
    SystemMissionProcess_Init(); /* A new boot, never an automatic stage restart. */
    assert(SystemMissionProcess_InsStoppedGet() == 0U);
    assert(SystemMissionProcess_EstimatorStoppedGet() == 0U);
    puts("mission-process: fresh samples, epoch, NaN, invalid, timestamps, immutable history PASS");
    return 0;
}
