#ifndef __NAVIGATION_ESKF_RECOVERY_H
#define __NAVIGATION_ESKF_RECOVERY_H

#include "navigation_eskf.h"

#define NAV_ESKF_RECOVERY_GROUPS 4U
#define NAV_ESKF_RECOVERY_SOURCES 4U

typedef enum
{
    NAV_ESKF_RECOVERY_COMPLETE = 0,
    NAV_ESKF_RECOVERY_DUPLICATE,
    NAV_ESKF_RECOVERY_DISCONTINUITY,
    NAV_ESKF_RECOVERY_INELIGIBLE,
    NAV_ESKF_RECOVERY_EXHAUSTED,
    NAV_ESKF_RECOVERY_INVALID_ARGUMENT,
    NAV_ESKF_RECOVERY_NUMERIC_ERROR,
    NAV_ESKF_RECOVERY_MODEL_MISMATCH,
    NAV_ESKF_RECOVERY_MEASUREMENT_INVALID
} NavigationEskfRecoveryResult;

typedef enum
{
    NAV_ESKF_RECOVERY_ACTION_NONE = 0,
    NAV_ESKF_RECOVERY_ACTION_PENDING,
    NAV_ESKF_RECOVERY_ACTION_SCALED,
    NAV_ESKF_RECOVERY_ACTION_LIMITED
} NavigationEskfRecoveryAction;

/* No defaults. Caller owns validation, immutable configuration and recording.
 * scale[] must be uniform, finite and >1..2; caps are finite positive variances.
 * Counts and times are explicit policy parameters, not approved flight settings. */
typedef struct
{
    uint64_t loss_gap_us;
    uint64_t stable_span_us;
    uint64_t maximum_interval_us;
    uint64_t cooldown_us;
    uint32_t identity;
    uint8_t stable_count;
    uint8_t reject_count;
    uint8_t confirmation_count;
    uint8_t maximum_attempts;
    float scale[NAV_ESKF_DIM];
    float variance_cap[NAV_ESKF_DIM];
} NavigationEskfRecoveryConfig;

typedef struct
{
    uint64_t receive_us;
    uint32_t sequence;
    uint8_t valid;
} NavigationEskfRecoveryReceipt;

typedef struct
{
    uint64_t last_physical_us;
    uint64_t stable_start_us;
    uint64_t last_qualified_us;
    uint32_t loss_token;
    uint32_t chain;
    uint8_t stable_count;
    uint8_t in_outage;
} NavigationEskfRecoveryQualification;

typedef struct
{
    NavigationEskfRecoveryReceipt source[NAV_ESKF_RECOVERY_SOURCES];
    NavigationEskfRecoveryQualification group[NAV_ESKF_RECOVERY_GROUPS];
    uint64_t epoch_start_us;
    uint64_t horizon_us;
    uint64_t native_us;
    uint32_t mission;
    uint32_t calibration;
    uint32_t configuration;
    uint32_t ordinal;
    uint8_t selected_source;
    uint8_t selected_valid;
    uint8_t initialized;
    uint8_t exhausted;
} NavigationEskfRecoveryReceiveState;

/* Caller admits receive_us against its actual MCU present/age/epoch policy first.
 * native_us is a separate strictly ordered clock, such as unwrapped iTOW. It
 * shares neither origin nor magnitude with receive_us. Caller proves its clock
 * identity, continuity and physical coherence; numerical order alone is no proof.
 * Physical/coherent masks are explicitly verified by the caller for this exact
 * source/sequence/native epoch. Missing proof is zero, never a guessed default.
 * Coherence screens and native-source snapshot ownership are adapter obligations.
 * Consume valid receipt identity before checking these proof fields. */
typedef struct
{
    uint64_t receive_us;
    uint64_t native_us;
    uint32_t source;
    uint32_t sequence;
    uint32_t mission;
    uint32_t calibration;
    uint8_t physical_mask;
    uint8_t coherent_mask;
    uint8_t time_proven;
} NavigationEskfRecoveryPacket;

typedef struct
{
    /* An all-zero evidence value explicitly requests ordinary Update only. */
    uint32_t ordinal;
    uint32_t chain;
    uint32_t loss_tokens[NAV_ESKF_RECOVERY_GROUPS];
    uint8_t qualified;
    uint8_t reserved[3];
} NavigationEskfRecoveryEvidence;

typedef struct
{
    uint32_t loss_token;
    uint32_t chain;
    uint32_t ordinal;
    uint8_t rejects;
    uint8_t confirmations;
} NavigationEskfRecoveryGroup;

/* Replay this object with P; never replay ReceiveState or refill its watermarks.
 * Attempts count surviving reconstructed actions, not repeated CPU invocations. */
typedef struct
{
    NavigationEskfRecoveryGroup group[NAV_ESKF_RECOVERY_GROUPS];
    uint64_t last_scale_receive_us;
    uint32_t mission;
    uint32_t calibration;
    uint32_t configuration;
    uint32_t pending_ordinal;
    uint32_t pending_chain;
    uint32_t pending_loss;
    uint32_t last_scale_ordinal;
    uint8_t pending_source;
    uint8_t pending_group;
    uint8_t pending_valid;
    uint8_t active_mask;
    uint8_t attempts;
    uint8_t limited;
    uint8_t initialized;
} NavigationEskfRecoveryReplayState;

typedef struct
{
    uint64_t receive_us;
    uint32_t source;
    uint32_t sequence;
    uint32_t mission;
    uint32_t calibration;
    NavigationEskfMeasurement measurement;
    NavigationEskfRecoveryEvidence evidence;
} NavigationEskfRecoveryEvent;

/* Caller-owned static scratch; never place this or kernel workspace on task stack.
 * All objects are serialized, non-reentrant. Scratch may change on failure. */
typedef struct
{
    NavigationEskfState state;
    NavigationEskfRecoveryReplayState policy;
} NavigationEskfRecoveryTransaction;

typedef struct
{
    NavigationEskfOutcome filter;
    NavigationEskfRecoveryAction action;
} NavigationEskfRecoveryOutput;

NavigationEskfRecoveryResult NavigationEskfRecovery_ConfigValidate(
    const NavigationEskfRecoveryConfig *config);
NavigationEskfRecoveryResult NavigationEskfRecovery_PolicyValidate(
    const NavigationEskfRecoveryReplayState *policy, const NavigationEskfRecoveryConfig *config);
NavigationEskfRecoveryResult NavigationEskfRecovery_Reset(
    NavigationEskfRecoveryReceiveState *receive, NavigationEskfRecoveryReplayState *policy,
    const NavigationEskfRecoveryConfig *config, uint32_t mission, uint32_t calibration,
    uint64_t epoch_start_us);
NavigationEskfRecoveryResult NavigationEskfRecovery_SourceSelect(
    NavigationEskfRecoveryReceiveState *receive, uint32_t source);
NavigationEskfRecoveryResult NavigationEskfRecovery_SourceUnavailable(
    NavigationEskfRecoveryReceiveState *receive);
/* Process received evidence before advancing this horizon. A subsequently supplied
 * older receipt is consumed but ineligible; this module never rewinds physical FSM. */
NavigationEskfRecoveryResult NavigationEskfRecovery_Tick(
    NavigationEskfRecoveryReceiveState *receive, const NavigationEskfRecoveryConfig *config,
    uint64_t present_us);
NavigationEskfRecoveryResult NavigationEskfRecovery_Receive(
    NavigationEskfRecoveryReceiveState *receive, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryPacket *packet,
    NavigationEskfRecoveryEvidence evidence[NAV_ESKF_RECOVERY_GROUPS]);
/* Separate numerical and policy transaction. COMPLETE includes ordinary NIS reject
 * or cap-limited operation; inspect output.filter without changing its meaning.
 * Numeric/model-mismatch/invalid failures preserve both authority objects bytewise.
 * MODEL_MISMATCH is separate so legacy may continue while current keeps its latch.
 * MEASUREMENT_INVALID preserves the ordinary filter INVALID_INPUT path; it is
 * distinct from invalid recovery configuration/state/call arguments. The original
 * filter outcome remains authoritative. All-zero evidence runs ordinary Update.
 * Input/output/authority/scratch objects must not overlap if either is writable.
 * One actual Update per call; Scale is only before a newer qualified observation.
 * This API does not admit sensor times, mutate receipt state or publish health. */
NavigationEskfRecoveryResult NavigationEskfRecovery_UpdateCandidate(
    NavigationEskfState *state, NavigationEskfRecoveryReplayState *policy,
    NavigationEskfWorkspace *workspace, NavigationEskfRecoveryTransaction *transaction,
    const NavigationEskfConfig *filter_config, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryEvent *event, NavigationEskfRecoveryOutput *output);
/* Same transaction using the Revision2 stable covariance reset.
 * The horizon path must use this operation; no legacy-kernel substitution. */
NavigationEskfRecoveryResult NavigationEskfRecovery_UpdateCandidateRevision2(
    NavigationEskfState *state, NavigationEskfRecoveryReplayState *policy,
    NavigationEskfWorkspace *workspace, NavigationEskfRecoveryTransaction *transaction,
    const NavigationEskfConfig *filter_config, const NavigationEskfRecoveryConfig *config,
    const NavigationEskfRecoveryEvent *event, NavigationEskfRecoveryOutput *output);

#endif /* __NAVIGATION_ESKF_RECOVERY_H */
