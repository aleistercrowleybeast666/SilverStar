#ifndef __NAVIGATION_KF_HORIZON_H
#define __NAVIGATION_KF_HORIZON_H

#include "navigation_kf_replay.h"

/* Sole EstimatorTask owner, fixed CPU-only storage, no callbacks or allocation.
 * Each event owns exactly one group and immutable once-per-receipt evidence. */
#define NAV_KF_HORIZON_BODY_CAPACITY 160U
#define NAV_KF_HORIZON_EVENT_CAPACITY 64U
#define NAV_KF_HORIZON_SOURCE_COUNT 4U
#define NAV_KF_HORIZON_MAX_WORK (2U * NAV_KF_HORIZON_BODY_CAPACITY + 3U * NAV_KF_HORIZON_EVENT_CAPACITY)

typedef enum
{
    NAV_KF_HORIZON_OK = 0,
    NAV_KF_HORIZON_QUEUED,
    NAV_KF_HORIZON_WARMUP,
    NAV_KF_HORIZON_INVALID,
    NAV_KF_HORIZON_STALE,
    NAV_KF_HORIZON_LATE,
    NAV_KF_HORIZON_CAPACITY,
    NAV_KF_HORIZON_DUPLICATE,
    NAV_KF_HORIZON_EPOCH_MISMATCH,
    NAV_KF_HORIZON_DISCONTINUITY,
    NAV_KF_HORIZON_NUMERIC_ERROR,
    NAV_KF_HORIZON_MODEL_MISMATCH,
    NAV_KF_HORIZON_NOT_READY,
    NAV_KF_HORIZON_BUSY,
    NAV_KF_HORIZON_EMPTY
} NavigationKfHorizonResult;

typedef struct
{
    uint64_t sample_us;
    uint64_t source_us;
    uint64_t receive_us;
    NavigationReplayGroupEvidence evidence;
    uint32_t operation_sequence;
    uint32_t epoch;
    uint32_t source;
    uint32_t generation;
    uint32_t sequence;
    float observation[2];
    float variance[2];
    float base_variance[2];
    float quality_scale;
    float consistency_scale;
    NavigationKfUpdateResult result;
    float nis;
    float innovation[2];
    float effective_variance[2];
    float robust_scale;
    /* Group naturally aligned fields to avoid per-event padding. Wire codecs
     * serialize fields explicitly; this private staging layout is not a wire. */
    uint8_t group;
    uint8_t physically_valid;
    uint8_t consistency_valid;
    uint8_t timing_flags;
    uint8_t effective_update;
} NavigationKfHorizonEvent;

typedef struct
{
    NavigationKfContext primary;
    NavigationKfContext candidate;
    NavigationKfContext predictor;
    NavigationKfContext receive_tracker[NAV_KF_HORIZON_SOURCE_COUNT];
    NavigationReplayImu body[NAV_KF_HORIZON_BODY_CAPACITY];
    NavigationKfHorizonEvent event[NAV_KF_HORIZON_EVENT_CAPACITY];
    SystemFusionReceipt receipt[NAV_KF_HORIZON_SOURCE_COUNT];
    SystemFusionReceipt barometer;
    uint64_t initial_us;
    uint64_t present_us;
    uint64_t primary_us;
    uint64_t output_us;
    uint64_t horizon_us;
    uint64_t last_receive_us[NAV_KF_HORIZON_SOURCE_COUNT];
    uint32_t epoch;
    uint32_t source;
    uint32_t generation;
    uint32_t applied_source[4];
    uint32_t candidate_source[4];
    uint32_t last_work;
    uint32_t maximum_work;
    uint32_t late_count;
    uint32_t capacity_count;
    uint32_t failure_operation;
    float output_acceleration[3];
    uint16_t body_head;
    uint16_t body_count;
    uint16_t event_count;
    uint16_t completion_count;
    uint16_t completion_read;
    uint8_t failure_operation_valid;
    uint8_t initialized;
    uint8_t faulted;
    uint8_t warmup;
} NavigationKfHorizon;

NavigationKfHorizonResult NavigationKfHorizon_Reset(NavigationKfHorizon *horizon,
    const NavigationKfContext *state, uint64_t timestamp_us, uint32_t epoch,
    uint32_t source, uint32_t generation, uint64_t horizon_us);
NavigationKfHorizonResult NavigationKfHorizon_BodyReceive(NavigationKfHorizon *horizon,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s,
    uint32_t source, uint32_t generation);
/* Call exactly once per GNSS producer receipt, before per-group insertion.
 * event receives all four immutable recovery certificates, never a fusion. */
NavigationKfHorizonResult NavigationKfHorizon_ReceiveTrack(NavigationKfHorizon *horizon,
    const NavigationKfGnssEpoch *receive_epoch, NavigationReplayEvent *event);
NavigationKfHorizonResult NavigationKfHorizon_Insert(NavigationKfHorizon *horizon,
    const NavigationKfHorizonEvent *event);
NavigationKfHorizonResult NavigationKfHorizon_Advance(NavigationKfHorizon *horizon,
    NavigationKfContext *output);
NavigationKfHorizonResult NavigationKfHorizon_CompletionPop(NavigationKfHorizon *horizon,
    NavigationKfHorizonEvent *event);

#endif /* __NAVIGATION_KF_HORIZON_H */
