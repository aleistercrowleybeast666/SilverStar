#ifndef __NAVIGATION_BOUNDED_H
#define __NAVIGATION_BOUNDED_H

/* Offline candidate. Matrix storage is row-major with stride 20, including
 * InEKF15. Caller owns exclusive state/workspace; never place workspace on a
 * task stack. No allocator, device adapter or runtime model switching exists. */
typedef enum { NavigationEskf20 = 1, NavigationInEkf15 = 2,
               NavigationInEkf20 = 3 } NavigationModel;
typedef enum { NavigationOk = 0, NavigationNoObservation,
    NavigationInvalidInput, NavigationNumericError, NavigationRejectedNis,
    NavigationRejectedCorrection } NavigationResult;
typedef enum { NavigationPosition = 1, NavigationVelocity = 2 } NavigationVectorKind;
typedef struct {
    NavigationModel model;
    double rotation[9], position[3], velocity[3], gyro_bias[3], accel_bias[3];
    double installation[9], inclination, declination, time_s;
    double covariance[400];
} NavigationState;
typedef struct {
    NavigationState candidate;
    double matrix[8][400];
    double observation[60], gain[60], correction[20];
    double residual[3], noise[9], innovation[9], nis;
} NavigationWorkspace;
typedef struct {
    double corrected_sensor_uT[3], covariance_sensor_uT2[9];
    double reference_strength_uT, time_s;
    /* Explicit boundary labels; only these exact enum-like values accepted. */
    unsigned sensor_frame; /* 1 = magnetometer_sensor */
    unsigned calibration;  /* 1 = hard_soft_iron_only */
} NavigationMagneticSample;

/* State initialization is caller-explicit: no hidden tuning or covariance.
 * State and every input buffer must be disjoint from workspace; overlap is
 * rejected before workspace mutation. All input pointers must otherwise refer
 * to readable objects of the declared length (ordinary C caller contract).
 * All operations reject invalid state before a no-observation result.
 * gate==0 disables gating; otherwise finite positive. On failure state bytes
 * are unchanged. Workspace is scratch and changes on any call. */
NavigationResult Navigation_Validate(const NavigationState *state, NavigationWorkspace *work);
/* Density is amplitude/sqrt(Hz), squared once. Deliberately preserves each
 * reference's order: ESKF20 [accel3,gyro3,bgRW3,baRW3], InEKF15/20
 * [gyro3,accel3,bgRW3,baRW3]. A canonical gyro-first adapter MUST swap the
 * first two triplets for ESKF20. IMU values are bias-uncorrected body-frame
 * angular rate and specific force held over this one interval. Two-half
 * increment adapters must call twice with their distinct means and half dt.
 * Bounded numerical domain: 0<dt<=.02 and L1((gyro-bg)*dt)<=64 radians.
 * Domain violations return InvalidInput. Acceleration/translation has no
 * arbitrary magnitude cutoff; unrepresentable arithmetic/SPD failure rejects. */
NavigationResult Navigation_Predict(NavigationState *state, NavigationWorkspace *work,
    const double gyro[3], const double accel[3], const double gravity[3],
    const double density[12], double dt);
NavigationResult Navigation_UpdateVector(NavigationState *state, NavigationWorkspace *work,
    const double measured[3], const double covariance[9], NavigationVectorKind kind,
    double time_s, double gate);
NavigationResult Navigation_UpdateMagnetic(NavigationState *state, NavigationWorkspace *work,
    const NavigationMagneticSample *sample, double gate);
/* Mathematical retraction/reset diagnostic; also enforces operational bounds. */
NavigationResult Navigation_Inject(NavigationState *state, NavigationWorkspace *work,
    const double correction[20]);
#endif
