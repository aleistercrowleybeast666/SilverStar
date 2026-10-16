#ifndef __NAVIGATION_ESKF_RECOVERY_QUALIFIER_H
#define __NAVIGATION_ESKF_RECOVERY_QUALIFIER_H

#include "system_gnss_receipt.h"

typedef enum
{
    NAV_ESKF_QUALIFIER_COMPLETE = 0,
    NAV_ESKF_QUALIFIER_BASELINE,
    NAV_ESKF_QUALIFIER_INELIGIBLE,
    NAV_ESKF_QUALIFIER_DUPLICATE,
    NAV_ESKF_QUALIFIER_DISCONTINUITY,
    NAV_ESKF_QUALIFIER_INVALID_ARGUMENT,
    NAV_ESKF_QUALIFIER_BAD_STATE
} NavigationEskfRecoveryQualifierResult;

#define NAV_ESKF_QUALIFIER_REASON_CLOCK 1UL
#define NAV_ESKF_QUALIFIER_REASON_BASELINE 2UL
#define NAV_ESKF_QUALIFIER_REASON_INTERVAL 4UL
#define NAV_ESKF_QUALIFIER_REASON_JITTER 8UL
#define NAV_ESKF_QUALIFIER_REASON_PHYSICAL 16UL
#define NAV_ESKF_QUALIFIER_REASON_STALE 32UL
#define NAV_ESKF_QUALIFIER_REASON_COHERENCE 64UL

/* Explicit experimental policy, no defaults or flight-approved values. The
 * interval cannot exceed existing500ms receive-age admission. Reported native
 * uncertainties are mandatory; model floors never stand in for recorded data. */
typedef struct
{
    uint64_t maximum_interval_us;
    uint64_t clock_jitter_us;
    float horizontal_acceleration_limit_mps2;
    float vertical_acceleration_limit_mps2;
    float closure_sigma;
} NavigationEskfRecoveryQualifierConfig;

typedef struct
{
    uint64_t native_us;
    uint32_t reasons;
    uint8_t clock_basis;
    uint8_t physical_mask;
    uint8_t coherent_mask;
    uint8_t time_proven;
} NavigationEskfRecoveryQualifierOutput;

/* EstimatorTask-owned, never replayed. previous is an original value copy;
 * week_us unwraps only this source's native iTOW and has no MCU-axis meaning. */
typedef struct
{
    SystemGnssReceiptSnapshot previous;
    float position_enu_m[3];
    uint64_t native_us;
    uint64_t week_us;
    uint8_t physical_mask;
    uint8_t eligible_mask;
    uint8_t clock_basis;
    uint8_t initialized;
} NavigationEskfRecoveryQualifier;

NavigationEskfRecoveryQualifierResult NavigationEskfRecoveryQualifier_ConfigValidate(
    const NavigationEskfRecoveryQualifierConfig *config);
NavigationEskfRecoveryQualifierResult NavigationEskfRecoveryQualifier_Reset(
    NavigationEskfRecoveryQualifier *qualifier);
/* Caller first admits the real source/sequence/MCU receive identity for its
 * lifecycle. present_us is actual MCU evaluation time. Invalid external data
 * stays ineligible; corrupt owned metadata returns BAD_STATE without writes.
 * Objects must be disjoint when either is writable. No source/device IO. */
NavigationEskfRecoveryQualifierResult NavigationEskfRecoveryQualifier_Receive(
    NavigationEskfRecoveryQualifier *qualifier,
    const NavigationEskfRecoveryQualifierConfig *config,
    const SystemGnssReceiptSnapshot *receipt, const float position_enu_m[3],
    uint64_t present_us, NavigationEskfRecoveryQualifierOutput *output);

#endif /* __NAVIGATION_ESKF_RECOVERY_QUALIFIER_H */
