#ifndef __NAVIGATION_INTEGRITY_H
#define __NAVIGATION_INTEGRITY_H

#include <stdint.h>

typedef enum
{
    NAV_INTEGRITY_NORMAL = 0,
    NAV_INTEGRITY_SUSPECT,
    NAV_INTEGRITY_REJECTED
} NavigationIntegrityState;

typedef enum
{
    NAV_INTEGRITY_REASON_HEALTHY = 0,
    NAV_INTEGRITY_REASON_ANCHOR,
    NAV_INTEGRITY_REASON_POSITION_INVALID,
    NAV_INTEGRITY_REASON_VELOCITY_INVALID,
    NAV_INTEGRITY_REASON_TIME_GAP,
    NAV_INTEGRITY_REASON_SEQUENCE_JUMP,
    NAV_INTEGRITY_REASON_SOURCE_CHANGE,
    NAV_INTEGRITY_REASON_QUALITY,
    NAV_INTEGRITY_REASON_CLOSURE_ABNORMAL
} NavigationIntegrityReason;

typedef enum
{
    NAV_INTEGRITY_PROCESS_OK = 0,
    NAV_INTEGRITY_PROCESS_INVALID,
    NAV_INTEGRITY_PROCESS_DUPLICATE
} NavigationIntegrityProcessResult;

typedef struct
{
    uint8_t enabled;
    uint32_t max_gap_us;
    uint32_t suspect_duration_us;
    uint32_t reject_duration_us;
    uint32_t recovery_duration_us;
    float error_threshold_m;
    float recovery_threshold_m;
    float position_r_scale;
    float hacc_max_m;
    float sacc_max_mps;
} NavigationIntegrityConfig;

typedef struct
{
    uint64_t timestamp_us;
    uint32_t epoch;
    uint32_t sequence;
    uint8_t source;
    uint8_t valid_group_mask;
    float position_en[2];
    float velocity_en[2];
    float hacc_m;
    float sacc_mps;
} NavigationIntegrityInput;

typedef struct
{
    uint64_t decision_us;
    uint8_t admitted_group_mask;
    uint8_t evidence_valid;
    uint8_t chain_reset;
    uint8_t state_changed;
    NavigationIntegrityState previous_state;
    NavigationIntegrityState state;
    NavigationIntegrityReason reason;
    float position_r_scale;
    float position_displacement_en[2];
    float integrated_velocity_en[2];
    float closure_en[2];
    float closure_norm_m;
} NavigationIntegrityDecision;

typedef struct
{
    NavigationIntegrityConfig config;
    uint64_t last_timestamp_us;
    uint64_t anchor_timestamp_us;
    uint32_t last_epoch;
    uint32_t last_sequence;
    uint32_t abnormal_duration_us;
    uint32_t reject_duration_us;
    uint32_t healthy_duration_us;
    float last_velocity_en[2];
    float integrated_velocity_en[2];
    float anchor_position_en[2];
    uint8_t last_source;
    uint8_t velocity_chain_valid;
    uint8_t anchor_valid;
    uint8_t anchor_trusted;
    NavigationIntegrityState state;
} NavigationIntegrityContext;

NavigationIntegrityProcessResult NavigationIntegrity_ConfigValidate(
    const NavigationIntegrityConfig *config);
NavigationIntegrityProcessResult NavigationIntegrity_Reset(
    NavigationIntegrityContext *context, const NavigationIntegrityConfig *config);
NavigationIntegrityProcessResult NavigationIntegrity_Receive(
    NavigationIntegrityContext *context, const NavigationIntegrityInput *input,
    NavigationIntegrityDecision *decision);

#endif /* __NAVIGATION_INTEGRITY_H */
