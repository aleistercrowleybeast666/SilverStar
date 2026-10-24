#ifndef __NAVIGATION_INPUT_H
#define __NAVIGATION_INPUT_H

#include <stdint.h>

/* Isolated integration candidate, not a wire ABI or a selectable estimator. */
typedef enum
{
    NavigationInputResult_Ok = 0,
    NavigationInputResult_InvalidInput,
    NavigationInputResult_IdentityMismatch,
    NavigationInputResult_UntrustedTime,
    NavigationInputResult_Future,
    NavigationInputResult_DelayedUnsupported,
    NavigationInputResult_Duplicate,
    NavigationInputResult_OutOfOrder,
    NavigationInputResult_NumericError,
    NavigationInputResult_WrongCorrectionStage,
    NavigationInputResult_FieldRejected
} NavigationInputResult;

typedef struct
{
    uint32_t epoch;
    uint32_t source;
    uint32_t calibration;
} NavigationInputIdentity;

typedef struct
{
    NavigationInputIdentity identity;
    uint64_t sample_us;
    uint64_t receive_us;
    uint32_t sequence;
    /* Admitted MCU-domain time under the caller's versioned contract; this
     * alone does not imply a native hardware clock (JY quality journal v2). */
    uint8_t timestamp_trusted;
} NavigationInputEvent;

/* One single-owner ledger per source AND measurement group. No hidden clock. */
typedef struct
{
    NavigationInputIdentity identity;
    uint64_t last_sample_us;
    uint32_t last_sequence;
    uint8_t seen;
} NavigationInputLedger;

typedef enum
{
    NavigationMagStage_SensorPhysical = 1,
    NavigationMagStage_SensorHardSoftCorrected = 2,
    NavigationMagStage_BodyCorrected = 3
} NavigationMagStage;

typedef struct
{
    float bias_uT[3];
    float soft_iron[9];
    float reference_uT;
    float minimum_norm_ratio;
    float maximum_norm_ratio;
} NavigationMagCorrection;

typedef struct
{
    float sensor_uT[3];
    float covariance_uT2[9];
    NavigationMagStage stage;
} NavigationMagPrepared;

NavigationInputResult NavigationInput_Initialize(NavigationInputLedger *ledger,
    const NavigationInputIdentity *identity);
NavigationInputResult NavigationInput_Check(const NavigationInputLedger *ledger,
    const NavigationInputEvent *event, uint64_t state_us);
/* Consume once after envelope and numerical payload validation, before a valid
 * update attempt; NIS rejection also consumes the sample. No retry by sequence. */
NavigationInputResult NavigationInput_Consume(NavigationInputLedger *ledger,
    const NavigationInputEvent *event, uint64_t state_us);
NavigationInputResult NavigationInput_Interval(uint64_t previous_us,
    uint64_t start_us, uint64_t end_us, float *dt_s);
/* No coarse installation rotation here: A0 belongs to the filter nominal A.
 * Input covariance is in physical sensor axes; output is S R S^T, in uT^2.
 * Output is committed only on success. Caller supplies disjoint objects. */
NavigationInputResult NavigationMag_Prepare(const float sensor_uT[3],
    const float covariance_uT2[9], NavigationMagStage stage,
    const NavigationMagCorrection *correction, NavigationMagPrepared *output);

#endif /* __NAVIGATION_INPUT_H */
