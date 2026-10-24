#ifndef __NAVIGATION_SESSION_H
#define __NAVIGATION_SESSION_H
#include "navigation_bounded.h"
#include "navigation_input.h"

/* Offline integration candidate. Caller exclusively owns session and workspace;
 * allocate both statically, not on a task stack. Pointer objects are disjoint.
 * This interface does not claim the production backend/clock/calibration adapter.
 */
typedef enum {
    NavigationSessionResult_Ok=0, NavigationSessionResult_InvalidInput=1,
    NavigationSessionResult_IdentityMismatch=2, NavigationSessionResult_UntrustedTime=3,
    NavigationSessionResult_Future=4, NavigationSessionResult_DelayedUnsupported=5,
    NavigationSessionResult_Duplicate=6, NavigationSessionResult_OutOfOrder=7,
    NavigationSessionResult_NumericError=8, NavigationSessionResult_WrongStage=9,
    NavigationSessionResult_FieldRejected=10, NavigationSessionResult_InvalidState=11,
    NavigationSessionResult_RejectedNis=12, NavigationSessionResult_RejectedCorrection=13,
    NavigationSessionResult_Unsupported=14,
    NavigationSessionResult_HistoryMiss=15, NavigationSessionResult_Capacity=16
} NavigationSessionResult;

typedef struct {
    NavigationState navigation;
    NavigationInputIdentity imu_identity;
    NavigationInputLedger observation[3]; /* position, velocity, magnetic */
    uint64_t origin_us, state_us;
    uint8_t initialized;
} NavigationSession;

typedef struct {
    NavigationWorkspace core;
    NavigationState staged;
    double density[12];
} NavigationSessionWorkspace;

NavigationSessionResult NavigationSession_Initialize(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationState *initial, uint64_t origin_us,
    const NavigationInputIdentity *imu, const NavigationInputIdentity observations[3]);
/* Input is calibrated body angular-rate and specific-force half means, not
 * coning/sculling delta inputs and not raw IMU measurements. No extra calibration.
 * density order: gyro, accel, gyro-bias RW, accel-bias RW (three axes per block).
 * Models remain fixed for the entire explicitly initialized session.
 */
NavigationSessionResult NavigationSession_PredictPair(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputIdentity *imu,
    uint64_t start_us, uint64_t end_us, const double gyro_pair[6],
    const double force_pair[6], const double gravity[3], const double density[12]);
/* Replay only: advance from the current integer time inside an original pair.
 * The pair's two constant half means retain their original exact half boundary. */
NavigationSessionResult NavigationSession_PredictPart(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputIdentity *imu,
    uint64_t pair_start_us, uint64_t pair_end_us, uint64_t target_us,
    const double gyro_pair[6], const double force_pair[6],
    const double gravity[3], const double density[12]);
NavigationSessionResult NavigationSession_UpdateVector(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputEvent *event,
    NavigationVectorKind kind, const double measured[3], const double covariance[9], double gate);
NavigationSessionResult NavigationSession_UpdateMagnetic(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputEvent *event,
    const float sensor_uT[3], const float covariance_uT2[9], NavigationMagStage stage,
    const NavigationMagCorrection *correction, double gate);
#endif
