#ifndef __NAVIGATION_ESKF_HORIZON_H
#define __NAVIGATION_ESKF_HORIZON_H

#include "navigation_eskf_replay.h"

/* Contract: contracts/navigation_fusion_horizon_v1.json. EstimatorTask owns
 * one context, workspace and output. All arrays are CPU-only and fixed-size. */
#define NAV_ESKF_HORIZON_BODY_CAPACITY 160U
#define NAV_ESKF_HORIZON_EVENT_CAPACITY 64U
#define NAV_ESKF_HORIZON_SOURCE_COUNT 4U
#define NAV_ESKF_HORIZON_MAX_WORK (4U * NAV_ESKF_HORIZON_BODY_CAPACITY + 3U * NAV_ESKF_HORIZON_EVENT_CAPACITY)

typedef enum
{
    NAV_ESKF_HORIZON_OK = 0,
    NAV_ESKF_HORIZON_QUEUED,
    NAV_ESKF_HORIZON_WARMUP,
    NAV_ESKF_HORIZON_INVALID,
    NAV_ESKF_HORIZON_STALE,
    NAV_ESKF_HORIZON_LATE,
    NAV_ESKF_HORIZON_CAPACITY,
    NAV_ESKF_HORIZON_DUPLICATE,
    NAV_ESKF_HORIZON_EPOCH_MISMATCH,
    NAV_ESKF_HORIZON_DISCONTINUITY,
    NAV_ESKF_HORIZON_NUMERIC_ERROR,
    NAV_ESKF_HORIZON_MODEL_MISMATCH,
    NAV_ESKF_HORIZON_NOT_READY,
    NAV_ESKF_HORIZON_BUSY,
    NAV_ESKF_HORIZON_EMPTY
} NavigationEskfHorizonResult;

typedef struct
{
    uint32_t sequence;
    uint8_t groups;
} NavigationEskfHorizonReceipt;

/* Immutable received observation plus audit metadata. Outcome is scratch
 * until Advance commits the whole primary/output transaction. */
typedef struct
{
    NavigationEskfReplayEvent event;
    uint64_t sample_us;
    uint32_t operation_sequence;
    float base_variance[2];
    float quality_scale;
    float consistency_scale;
    uint8_t timing_flags;
    NavigationEskfOutcome outcome;
} NavigationEskfHorizonEvent;

typedef struct
{
    NavigationEskfState primary;
    NavigationEskfState candidate;
    NavigationEskfState output_candidate;
    NavigationEskfConfig config;
    NavigationEskfHistoryInput body[NAV_ESKF_HORIZON_BODY_CAPACITY];
    NavigationEskfHorizonEvent event[NAV_ESKF_HORIZON_EVENT_CAPACITY];
    NavigationEskfHorizonReceipt gnss[NAV_ESKF_HORIZON_SOURCE_COUNT];
    NavigationEskfHorizonReceipt barometer;
    uint64_t initial_us;
    uint64_t present_us;
    uint64_t body_start_us;
    uint64_t horizon_us;
    uint16_t body_head;
    uint16_t body_count;
    uint16_t event_count;
    uint16_t completion_count;
    uint16_t completion_read;
    uint32_t last_work;
    uint32_t maximum_work;
    uint32_t late_count;
    uint32_t capacity_count;
    uint32_t failure_operation;
    float primary_endpoint_rate[3];
    float output_acceleration[3]; /* Prior output predicted with raw input only. */
    uint8_t endpoint_valid;
    uint8_t body_seen;
    uint8_t initialized;
    uint8_t faulted;
    uint8_t warmup;
    uint8_t failure_operation_valid;
} NavigationEskfHorizon;

/* Mutable context/workspace and output must not overlap each other or inputs.
 * Config is immutable for this lifecycle. No call is reentrant. */
NavigationEskfHorizonResult NavigationEskfHorizon_Reset(
    NavigationEskfHorizon *horizon, const NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    uint64_t horizon_us);
NavigationEskfHorizonResult NavigationEskfHorizon_BodyReceive(
    NavigationEskfHorizon *horizon, const NavigationEskfBodyInput *input);
NavigationEskfHorizonResult NavigationEskfHorizon_Insert(
    NavigationEskfHorizon *horizon, const NavigationEskfHorizonEvent *event);
NavigationEskfHorizonResult NavigationEskfHorizon_Advance(
    NavigationEskfHorizon *horizon, NavigationEskfState *output,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config);
NavigationEskfHorizonResult NavigationEskfHorizon_CompletionPop(
    NavigationEskfHorizon *horizon, NavigationEskfHorizonEvent *event);

#endif /* __NAVIGATION_ESKF_HORIZON_H */
