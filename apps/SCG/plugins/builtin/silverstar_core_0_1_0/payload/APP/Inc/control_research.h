#ifndef __CONTROL_RESEARCH_H
#define __CONTROL_RESEARCH_H

#include <stdint.h>
#include "system_navigation_provenance.h"
#include "system_mission_process.h"

#define CONTROL_RESEARCH_PERIOD_US 10000ULL
#define CONTROL_RESEARCH_LATENESS_US 2000ULL
#define CONTROL_RESEARCH_INPUT_AGE_US 20000ULL
#define CONTROL_RESEARCH_INPUT_SKEW_US 10000ULL
/* Explicit task mapping; the generic mathematical cores keep abstract outputs. */
#define CONTROL_RESEARCH_TORQUE_REFERENCE_NM 1.0f

typedef enum
{
    ControlResearchResult_Ok = 0,
    ControlResearchResult_Disabled,
    ControlResearchResult_Waiting,
    ControlResearchResult_Stopped,
    ControlResearchResult_Unavailable,
    ControlResearchResult_InvalidInput,
    ControlResearchResult_Stale,
    ControlResearchResult_Timing,
    ControlResearchResult_SourceChanged,
    ControlResearchResult_BackendError,
    ControlResearchResult_InvalidState
} ControlResearchResult;

typedef enum
{
    ControlResearchState_Waiting = 0,
    ControlResearchState_Starting,
    ControlResearchState_Running,
    ControlResearchState_Stopped,
    ControlResearchState_Failed,
    ControlResearchState_Disabled
} ControlResearchState;

typedef struct
{
    uint64_t navigation_us;
    uint64_t imu_us;
    uint32_t navigation_sequence;
    uint32_t imu_sequence;
    float q_nb[4];
    float rate_radps;
    SystemNavigationProvenance navigation_provenance;
    SystemNavigationProvenance imu_provenance;
} ControlResearchInput;

typedef struct
{
    uint64_t published_us;
    uint64_t scheduled_us;
    uint64_t navigation_us;
    uint64_t imu_us;
    uint32_t sequence;
    float requested_body_y_torque_nm; /* Research request, never an electrical command. */
    float angle_rad;
    float rate_radps;
    ControlResearchState state;
    ControlResearchResult result;
    uint8_t ready; /* Research snapshot only. Never electrical/deployment READY. */
} ControlResearchSnapshot;

/* Init and Process have exactly one owner: FlightTask. No additional task. */
void ControlResearch_Init(void);
ControlResearchResult ControlResearch_Process(uint64_t now_us,
    SystemMissionControlWindowResult window, ControlResearchResult input_result,
    const ControlResearchInput *input);
ControlResearchResult ControlResearch_InputRead(ControlResearchInput *input);
ControlResearchResult ControlResearch_RuntimeProcess(void);
ControlResearchResult ControlResearch_SnapshotGet(ControlResearchSnapshot *snapshot);
/* Called under the publication lock; revalidate historical producer proof. */
ControlResearchResult ControlResearch_PublicationCheck(const SystemNavigationProvenance *provenance,
    uint64_t navigation_us, uint32_t navigation_sequence);

/* Generated direct calls bind exactly one implementation; no callback table.
 * Limit and output are body-Y torque in N*m, at 1 N*m per core-output unit. */
ControlResearchResult ControlResearchBackend_Start(float *limit);
ControlResearchResult ControlResearchBackend_Stop(void);
ControlResearchResult ControlResearchBackend_Step(float angle_rad, float rate_radps, float *output);

#endif /* __CONTROL_RESEARCH_H */
