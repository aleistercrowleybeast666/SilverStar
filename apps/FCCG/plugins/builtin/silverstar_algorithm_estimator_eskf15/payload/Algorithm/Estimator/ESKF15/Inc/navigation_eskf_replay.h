#ifndef __NAVIGATION_ESKF_REPLAY_H
#define __NAVIGATION_ESKF_REPLAY_H

#include "navigation_eskf.h"

#define NAV_ESKF_HISTORY_CAPACITY 192U
#define NAV_ESKF_EVENT_CAPACITY 208U
#define NAV_ESKF_HISTORY_WINDOW_US 600000ULL
#define NAV_ESKF_REPLAY_MAX_STEPS (NAV_ESKF_HISTORY_CAPACITY + 2U * NAV_ESKF_EVENT_CAPACITY)

typedef enum
{
    NAV_ESKF_REPLAY_OK = 0,
    NAV_ESKF_REPLAY_INVALID,
    NAV_ESKF_REPLAY_HISTORY_MISS,
    NAV_ESKF_REPLAY_OVERFLOW,
    NAV_ESKF_REPLAY_DUPLICATE,
    NAV_ESKF_REPLAY_NUMERIC_ERROR
} NavigationEskfReplayResult;

typedef struct
{
    uint64_t measurement_us;
    uint64_t receive_us;
    uint32_t sequence;
    uint32_t source;
    uint32_t generation;
    NavigationEskfMeasurement measurement;
} NavigationEskfReplayEvent;

typedef struct
{
    /* Continuity makes start/epoch/source redundant. Keep both actual body
       half means, the supplied dt and the integer end epoch without loss. */
    uint64_t end_us;
    float gyro_radps[2][3];
    float accel_mps2[2][3];
    float dt_s;
    uint32_t quality_flags;
} NavigationEskfHistoryInput;

_Static_assert(sizeof(NavigationEskfHistoryInput) == 64U, "ESKF history storage budget");

typedef struct
{
    NavigationEskfState anchor;
    NavigationEskfState working;
    NavigationEskfHistoryInput *body; /* Caller-owned 192-element CPU buffer. */
    NavigationEskfReplayEvent event[NAV_ESKF_EVENT_CAPACITY];
    uint16_t body_count;
    uint16_t event_count;
    uint32_t replay_count;
    uint32_t history_misses;
    uint32_t overflows;
    uint32_t maximum_steps;
    uint32_t last_steps;
} NavigationEskfReplay;

NavigationEskfReplayResult NavigationEskfReplay_Reset(
    NavigationEskfReplay *history, const NavigationEskfState *state,
    NavigationEskfHistoryInput body_storage[NAV_ESKF_HISTORY_CAPACITY]);
NavigationEskfReplayResult NavigationEskfReplay_Predict(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input);
NavigationEskfReplayResult NavigationEskfReplay_Insert(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfReplayEvent *event, NavigationEskfOutcome *outcome);

#endif /* __NAVIGATION_ESKF_REPLAY_H */
