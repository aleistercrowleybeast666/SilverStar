#ifndef __SYSTEM_MISSION_PROCESS_H
#define __SYSTEM_MISSION_PROCESS_H

#include <stdint.h>

#define SYSTEM_MISSION_PROCESS_MAX_STAGES 32U
#define SYSTEM_MISSION_PROCESS_EVENT_ENTER 256U
#define SYSTEM_MISSION_PROCESS_EVENT_EXIT 257U
#define SYSTEM_MISSION_PROCESS_VALID_ACCEL 1U
#define SYSTEM_MISSION_PROCESS_VALID_NAV 2U

typedef enum
{
    SystemMissionProcessResult_Waiting = 0,
    SystemMissionProcessResult_Entered,
    SystemMissionProcessResult_Complete,
    SystemMissionProcessResult_Invalid,
    SystemMissionProcessResult_Unavailable
} SystemMissionProcessResult;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    uint32_t stage_id_hash;
    uint16_t event_code;
    uint8_t stage_index;
} SystemMissionProcessEvent;

typedef struct
{
    uint64_t now_us;
    uint64_t acceleration_timestamp_us;
    uint64_t navigation_timestamp_us;
    uint64_t ready_timestamp_us[2]; /* INS then estimator; never poll timestamps. */
    uint32_t navigation_sequence;
    uint32_t acceleration_sequence;
    uint32_t acceleration_source;
    uint32_t acceleration_epoch;
    uint32_t events;
    float acceleration_g;
    float altitude_agl_m;
    float vertical_velocity_mps;
    uint8_t valid_mask;
    uint8_t mission_started;
    uint8_t terminated;
    uint8_t ready_function_mask; /* Fresh valid output from fixed INS/estimator owners. */
} SystemMissionProcessInput;

typedef struct
{
    uint32_t stage_id_hash;
    uint32_t hold_ms;
    uint32_t event_mask;
    float threshold;
    uint8_t signal; /* 0 event, 1 elapsed, 2 altitude, 3 velocity, 4 specific force. */
    uint8_t less_equal;
} SystemMissionStageConfig;

typedef struct
{
    uint8_t start_kind;
    uint8_t start_index;
    uint8_t stop_kind;
    uint8_t stop_index;
    uint8_t dependency_mask; /* Fixed owner indices: INS bit 2, estimator bit 3. */
} SystemMissionFunctionConfig;

void SystemMissionProcess_Init(void);
SystemMissionProcessResult SystemMissionProcess_Step(const SystemMissionProcessInput *input);
SystemMissionProcessResult SystemMissionProcess_EventGet(uint32_t after_sequence,
    SystemMissionProcessEvent *event);
void SystemMissionProcess_RuntimeProcess(void);
uint8_t SystemMissionProcess_TelemetryActiveGet(void);
uint8_t SystemMissionProcess_LoggingActiveGet(void);
/* Navigation initialization remains owned by accepted START. These monotonic
 * stop permissions are false before START; they never request reinitialization. */
uint8_t SystemMissionProcess_InsStoppedGet(void);
uint8_t SystemMissionProcess_EstimatorStoppedGet(void);
uint8_t ProjectMissionStage_CountGet(void);
SystemMissionProcessResult ProjectMissionStage_ConfigGet(uint8_t index, SystemMissionStageConfig *config);
SystemMissionProcessResult ProjectMissionFunction_ConfigGet(uint8_t index, SystemMissionFunctionConfig *config);

#endif /* __SYSTEM_MISSION_PROCESS_H */
