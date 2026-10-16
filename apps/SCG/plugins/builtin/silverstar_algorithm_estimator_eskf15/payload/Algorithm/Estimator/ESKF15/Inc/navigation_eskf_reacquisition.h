#ifndef __NAVIGATION_ESKF_REACQUISITION_H
#define __NAVIGATION_ESKF_REACQUISITION_H

#include "navigation_eskf_recovery_configuration.h"
#include "navigation_eskf_replay_recovery.h"
#include "navigation_eskf_horizon_recovery.h"

typedef enum
{
    NAV_ESKF_REACQUISITION_COMPLETE = 0,
    NAV_ESKF_REACQUISITION_DISABLED,
    NAV_ESKF_REACQUISITION_SKIPPED,
    NAV_ESKF_REACQUISITION_LIMITED,
    NAV_ESKF_REACQUISITION_INVALID_ARGUMENT,
    NAV_ESKF_REACQUISITION_BAD_STATE
} NavigationEskfReacquisitionResult;

typedef struct
{
    NavigationEskfRecoveryQualifierOutput qualification;
    NavigationEskfRecoveryEvidence evidence[NAV_ESKF_RECOVERY_GROUPS];
    uint64_t receive_us;
    uint64_t evaluation_us;
    uint32_t source;
    uint32_t sequence;
    uint32_t mission;
    uint32_t calibration;
    uint32_t configuration;
    uint32_t ordinal;
    NavigationEskfRecoveryResult receive_result;
    NavigationEskfRecoveryQualifierResult qualifier_result;
    uint8_t valid;
} NavigationEskfReacquisitionReceipt;

/* Single EstimatorTask owner. Never call from an ISR, another task or recursively.
 * These availability/results do not credit fusion health or imply flight READY.
 * Reset/Initialize precede EpochStart; receive/source/Tick never rewind with P.
 * Read-only views are valid until the next owner operation and never writable. */
void NavigationEskfReacquisition_Reset(void);
NavigationEskfReacquisitionResult NavigationEskfReacquisition_Initialize(void);
NavigationEskfReacquisitionResult NavigationEskfReacquisition_EpochStart(
    const NavigationEskfState *state, uint32_t calibration, uint64_t epoch_us);
NavigationEskfReacquisitionResult NavigationEskfReacquisition_SourceSelect(uint8_t source, uint8_t available);
NavigationEskfReacquisitionResult NavigationEskfReacquisition_Receive(
    const SystemGnssReceiptSnapshot *receipt, const float position_enu_m[3], uint64_t present_us);
NavigationEskfReacquisitionResult NavigationEskfReacquisition_Tick(uint64_t present_us);
uint8_t NavigationEskfReacquisition_FaultedGet(void);
void NavigationEskfReacquisition_FaultMark(void);
const NavigationEskfReacquisitionReceipt *NavigationEskfReacquisition_ReceiptGet(void);
const NavigationEskfRecoveryReceiveState *NavigationEskfReacquisition_ReceiveStateGet(void);
const NavigationEskfRecoveryReplayState *NavigationEskfReacquisition_PolicyGet(void);

NavigationEskfReplayResult NavigationEskfReacquisition_ReplayPredict(
    NavigationEskfReplay *history, NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfBodyInput *input);
NavigationEskfReplayResult NavigationEskfReacquisition_ReplayInsert(
    NavigationEskfReplay *history, NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfReplayEvent *event,
    NavigationEskfOutcome *outcome, NavigationEskfRecoveryAction *action);
NavigationEskfResult NavigationEskfReacquisition_CurrentUpdate(
    NavigationEskfState *state, NavigationEskfWorkspace *workspace,
    const NavigationEskfConfig *config, const NavigationEskfReplayEvent *event,
    NavigationEskfOutcome *outcome, NavigationEskfRecoveryAction *action);
NavigationEskfHorizonResult NavigationEskfReacquisition_HorizonInsert(
    NavigationEskfHorizon *horizon, const NavigationEskfHorizonEvent *event);
NavigationEskfHorizonResult NavigationEskfReacquisition_HorizonAdvance(
    NavigationEskfHorizon *horizon, NavigationEskfState *output,
    NavigationEskfWorkspace *workspace, const NavigationEskfConfig *config);
NavigationEskfHorizonResult NavigationEskfReacquisition_HorizonPop(
    NavigationEskfHorizon *horizon, NavigationEskfHorizonEvent *event,
    NavigationEskfRecoveryAction *action);

#endif /* __NAVIGATION_ESKF_REACQUISITION_H */
