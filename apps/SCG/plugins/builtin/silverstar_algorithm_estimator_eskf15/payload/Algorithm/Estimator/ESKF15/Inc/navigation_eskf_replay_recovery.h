#ifndef __NAVIGATION_ESKF_REPLAY_RECOVERY_H
#define __NAVIGATION_ESKF_REPLAY_RECOVERY_H

#include "navigation_eskf_recovery.h"
#include "navigation_eskf_replay.h"

/* Optional caller-owned static companion. Ordinary replay retains its original
 * event/context ABI and capacity. The receipt FSM is never stored or rewound.
 * Use the recovery variants consistently for the complete initialized lifecycle.
 * One owner, no aliases with history/state/workspace/config/inputs or outputs. */
typedef struct
{
    NavigationEskfRecoveryConfig config;
    NavigationEskfRecoveryReplayState anchor;
    NavigationEskfRecoveryReplayState current;
    NavigationEskfRecoveryReplayState working;
    NavigationEskfRecoveryTransaction transaction;
    NavigationEskfRecoveryEvidence evidence[NAV_ESKF_EVENT_CAPACITY];
    uint8_t initialized;
} NavigationEskfReplayRecovery;

NavigationEskfReplayResult NavigationEskfReplayRecovery_Reset(
    NavigationEskfReplayRecovery *recovery, const NavigationEskfState *state,
    const NavigationEskfRecoveryReplayState *policy, const NavigationEskfRecoveryConfig *config);
NavigationEskfReplayResult NavigationEskfReplayRecovery_Predict(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfBodyInput *input, NavigationEskfReplayRecovery *recovery);
NavigationEskfReplayResult NavigationEskfReplayRecovery_Insert(
    NavigationEskfReplay *history, NavigationEskfState *state,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    const NavigationEskfReplayEvent *event, NavigationEskfOutcome *outcome,
    NavigationEskfReplayRecovery *recovery, const NavigationEskfRecoveryEvidence *evidence,
    NavigationEskfRecoveryAction *action);

#endif /* __NAVIGATION_ESKF_REPLAY_RECOVERY_H */
