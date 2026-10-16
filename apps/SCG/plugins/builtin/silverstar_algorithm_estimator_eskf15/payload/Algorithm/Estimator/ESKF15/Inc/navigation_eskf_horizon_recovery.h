#ifndef __NAVIGATION_ESKF_HORIZON_RECOVERY_H
#define __NAVIGATION_ESKF_HORIZON_RECOVERY_H

#include "navigation_eskf_horizon.h"
#include "navigation_eskf_recovery.h"

/* Optional static companion, owned by the same EstimatorTask as the horizon.
 * Reset both contexts together; consistently use these Insert/Advance/Pop APIs.
 * Receipt qualification is outside this object and never rewinds. Candidate
 * policy commits only after primary updates AND complete output propagation. */
typedef struct
{
    NavigationEskfRecoveryConfig config;
    NavigationEskfRecoveryReplayState primary;
    NavigationEskfRecoveryReplayState candidate;
    NavigationEskfRecoveryTransaction transaction;
    NavigationEskfRecoveryEvidence evidence[NAV_ESKF_HORIZON_EVENT_CAPACITY];
    NavigationEskfRecoveryAction action[NAV_ESKF_HORIZON_EVENT_CAPACITY];
    uint8_t initialized;
} NavigationEskfHorizonRecovery;

NavigationEskfHorizonResult NavigationEskfHorizonRecovery_Reset(
    NavigationEskfHorizonRecovery *recovery, const NavigationEskfState *state,
    const NavigationEskfRecoveryReplayState *policy, const NavigationEskfRecoveryConfig *config);
NavigationEskfHorizonResult NavigationEskfHorizonRecovery_Insert(
    NavigationEskfHorizon *horizon, const NavigationEskfHorizonEvent *event,
    NavigationEskfHorizonRecovery *recovery, const NavigationEskfRecoveryEvidence *evidence);
NavigationEskfHorizonResult NavigationEskfHorizonRecovery_Advance(
    NavigationEskfHorizon *horizon, NavigationEskfState *output,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config,
    NavigationEskfHorizonRecovery *recovery);
NavigationEskfHorizonResult NavigationEskfHorizonRecovery_CompletionPop(
    NavigationEskfHorizon *horizon, NavigationEskfHorizonEvent *event,
    NavigationEskfHorizonRecovery *recovery, NavigationEskfRecoveryAction *action);

#endif /* __NAVIGATION_ESKF_HORIZON_RECOVERY_H */
