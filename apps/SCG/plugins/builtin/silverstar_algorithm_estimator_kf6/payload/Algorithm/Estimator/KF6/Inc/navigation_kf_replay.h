#ifndef __NAVIGATION_KF_REPLAY_H
#define __NAVIGATION_KF_REPLAY_H

#include "navigation_kf.h"
#include "system_fusion_timing.h"

/* Static budget: 600 ms at 200 Hz plus checkpoint/scheduling margin. */
#define NAV_REPLAY_WINDOW_US 600000ULL
#define NAV_REPLAY_IMU_CAPACITY 144U
#define NAV_REPLAY_GNSS_CAPACITY 48U
#define NAV_REPLAY_BARO_CAPACITY 160U
#define NAV_REPLAY_EVENT_CAPACITY (NAV_REPLAY_GNSS_CAPACITY + NAV_REPLAY_BARO_CAPACITY)
#define NAV_REPLAY_CHECKPOINT_CAPACITY 8U
#define NAV_REPLAY_CHECKPOINT_STRIDE 18U
#define NAV_REPLAY_MAX_STEPS (NAV_REPLAY_IMU_CAPACITY + 2U * NAV_REPLAY_EVENT_CAPACITY)
#define NAV_REPLAY_POSITION 1U
#define NAV_REPLAY_VELOCITY 2U
#define NAV_REPLAY_BAROMETER 4U

typedef enum
{
    NAV_REPLAY_OK = 0,
    NAV_REPLAY_INVALID,
    NAV_REPLAY_HISTORY_MISS,
    NAV_REPLAY_OVERFLOW,
    NAV_REPLAY_EPOCH_MISMATCH,
    NAV_REPLAY_DISCONTINUITY,
    NAV_REPLAY_NUMERIC_ERROR,
    NAV_REPLAY_WORK_LIMIT
} NavigationReplayResult;

typedef struct
{
    uint64_t availability_timestamp_us;
    uint64_t consistency_start_us;
    uint32_t generation;
    uint32_t consistent_count;
    uint8_t outage;
    uint8_t loss_latched;
    uint8_t recovery_valid;
} NavigationReplayGroupEvidence;

typedef struct
{
    uint64_t measurement_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t epoch;
    uint32_t sequence;
    uint32_t source;
    uint32_t calibration_generation; /* Current identity; ignored by legacy replay. */
    uint8_t kind;
    uint8_t valid_group_mask;
    uint8_t consistency_mask;
    uint8_t vertical_valid;
    uint8_t integrity_admission_valid;
    uint8_t integrity_admitted_group_mask;
    float position[3];
    float position_variance[3];
    float velocity[3];
    float velocity_variance[3];
    float altitude;
    float altitude_variance;
    NavigationReplayGroupEvidence evidence[NAV_KF_GNSS_GROUP_COUNT];
} NavigationReplayEvent;

typedef struct
{
    NavigationKfUpdateResult position;
    NavigationKfUpdateResult velocity;
    NavigationKfUpdateResult barometer;
    NavigationKfGnssSeparatedUpdateResult position_groups;
    NavigationKfGnssSeparatedUpdateResult velocity_groups;
    float group_nis[4];
    float baro_nis;
    float position_innovation[3];
    float velocity_innovation[3];
    float baro_innovation;
} NavigationReplayOutcome;

typedef struct
{
    uint64_t start_us;
    uint64_t end_us;
    float delta_velocity[3];
    float dt_s;
} NavigationReplayImu;

typedef struct
{
    uint64_t timestamp_us;
    NavigationKfContext state;
} NavigationReplayCheckpoint;

typedef struct
{
    uint32_t replay_count;
    uint32_t last_steps;
    uint32_t max_steps;
    uint32_t history_miss_count;
    uint32_t overflow_count;
    uint32_t rejection_count;
    uint32_t last_runtime_us;
    uint32_t max_runtime_us;
    uint32_t max_rewind_age_us;
    uint32_t event_high_water;
    NavigationReplayResult last_result;
} NavigationReplayDiagnostics;

/* One owner (EstimatorTask). No heap, callbacks, IO, clock or mission state. */
typedef struct
{
    NavigationReplayImu imu[NAV_REPLAY_IMU_CAPACITY];
    NavigationReplayCheckpoint checkpoints[NAV_REPLAY_CHECKPOINT_CAPACITY];
} NavigationReplayStorage;

/* High-rate barometer events do not carry unused GNSS vectors/evidence. */
typedef struct
{
    uint64_t measurement_timestamp_us;
    uint64_t receive_timestamp_us;
    uint32_t epoch;
    uint32_t sequence;
    uint32_t source;
    float altitude;
    float altitude_variance;
    uint8_t occupied;
} NavigationReplayBarometerEvent;

typedef struct
{
    NavigationReplayStorage *storage;
    NavigationReplayEvent events[NAV_REPLAY_GNSS_CAPACITY];
    NavigationReplayBarometerEvent barometer[NAV_REPLAY_BARO_CAPACITY];
    uint16_t event_order[NAV_REPLAY_EVENT_CAPACITY];
    NavigationReplayEvent event_work;
    NavigationKfContext receive_tracker;
    NavigationKfContext working;
    NavigationReplayDiagnostics diagnostics;
    uint64_t present_us;
    uint64_t epoch_start_us;
    uint32_t epoch;
    uint32_t prediction_count;
    uint16_t imu_head;
    uint16_t imu_count;
    uint16_t event_count;
    uint8_t checkpoint_count;
    uint8_t faulted;
} NavigationReplayContext;

void NavigationReplay_Reset(NavigationReplayContext *history,
                            NavigationReplayStorage *storage,
                            const NavigationKfContext *state,
                            uint64_t timestamp_us, uint32_t epoch);
NavigationReplayResult NavigationReplay_Predict(
    NavigationReplayContext *history, NavigationKfContext *state,
    uint64_t timestamp_us, const float delta_velocity[3], float dt_s);
/* Call once per received packet, before splitting position/velocity delays. */
NavigationReplayResult NavigationReplay_ReceiveTrack(
    NavigationReplayContext *history, const NavigationKfGnssEpoch *receive_epoch,
    NavigationReplayEvent *event);
NavigationReplayResult NavigationReplay_Insert(
    NavigationReplayContext *history, NavigationKfContext *state,
    const NavigationReplayEvent *event, NavigationReplayOutcome *outcome);
void NavigationReplay_RuntimeRecord(NavigationReplayContext *history,
                                    uint64_t elapsed_us);

typedef enum
{
    NAV_CURRENT_OK = SYSTEM_FUSION_EXEC_COMPLETE,
    NAV_CURRENT_INVALID = SYSTEM_FUSION_EXEC_INVALID,
    NAV_CURRENT_STALE = SYSTEM_FUSION_EXEC_STALE,
    NAV_CURRENT_DUPLICATE = SYSTEM_FUSION_EXEC_DUPLICATE,
    NAV_CURRENT_EPOCH_MISMATCH = SYSTEM_FUSION_EXEC_EPOCH_MISMATCH,
    NAV_CURRENT_DISCONTINUITY = SYSTEM_FUSION_EXEC_DISCONTINUITY,
    NAV_CURRENT_NUMERIC_ERROR = SYSTEM_FUSION_EXEC_NUMERIC_ERROR,
    NAV_CURRENT_NOT_READY = SYSTEM_FUSION_EXEC_NOT_READY
} NavigationCurrentResult;

typedef struct
{
    NavigationKfContext receive_tracker;
    NavigationKfContext working;
    NavigationReplayDiagnostics diagnostics; /* Replay counters remain zero. */
    SystemFusionReceipt gnss[SYSTEM_FUSION_SOURCE_COUNT];
    SystemFusionReceipt barometer;
    uint64_t present_us;
    uint64_t epoch_start_us;
    uint32_t epoch;
    uint32_t calibration_generation;
    uint8_t initialized;
    uint8_t faulted;
} NavigationCurrentContext;

NavigationCurrentResult NavigationCurrent_Reset(NavigationCurrentContext *current,
    const NavigationKfContext *state, uint64_t timestamp_us, uint32_t epoch,
    uint32_t calibration_generation);
NavigationCurrentResult NavigationCurrent_Predict(NavigationCurrentContext *current,
    NavigationKfContext *state, uint64_t timestamp_us,
    const float delta_velocity[3], float dt_s);
NavigationCurrentResult NavigationCurrent_ReceiveTrack(NavigationCurrentContext *current,
    const NavigationKfGnssEpoch *receive_epoch, NavigationReplayEvent *event);
NavigationCurrentResult NavigationCurrent_Insert(NavigationCurrentContext *current,
    NavigationKfContext *state, const NavigationReplayEvent *event,
    NavigationReplayOutcome *outcome);

#endif /* __NAVIGATION_KF_REPLAY_H */
