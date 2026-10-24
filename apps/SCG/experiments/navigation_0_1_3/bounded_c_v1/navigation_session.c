#include "navigation_session.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

static NavigationSessionResult Session_CoreResult(NavigationResult result)
{
    switch (result) {
        case NavigationOk: return NavigationSessionResult_Ok;
        case NavigationInvalidInput: return NavigationSessionResult_InvalidInput;
        case NavigationRejectedNis: return NavigationSessionResult_RejectedNis;
        case NavigationRejectedCorrection: return NavigationSessionResult_RejectedCorrection;
        case NavigationNoObservation: return NavigationSessionResult_Unsupported;
        case NavigationNumericError: return NavigationSessionResult_NumericError;
        default: return NavigationSessionResult_NumericError;
    }
}

static NavigationSessionResult Session_Validate(const NavigationSession *session,
    NavigationSessionWorkspace *work)
{
    if ((session == NULL) || (work == NULL)) { return NavigationSessionResult_InvalidInput; }
    if ((session->initialized != 1U) || (session->state_us < session->origin_us) ||
        (session->navigation.time_s != (double)(session->state_us - session->origin_us) / 1000000.0))
    { return NavigationSessionResult_InvalidState; }
    if (Navigation_Validate(&session->navigation, &work->core) != NavigationOk)
    { return NavigationSessionResult_InvalidState; }
    return NavigationSessionResult_Ok;
}

NavigationSessionResult NavigationSession_Initialize(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationState *initial, uint64_t origin_us,
    const NavigationInputIdentity *imu, const NavigationInputIdentity observations[3])
{
    if ((session == NULL) || (work == NULL) || (initial == NULL) ||
        (imu == NULL) || (observations == NULL)) { return NavigationSessionResult_InvalidInput; }
    if ((initial->time_s != 0.0) || (Navigation_Validate(initial, &work->core) != NavigationOk))
    { return NavigationSessionResult_InvalidState; }
    session->navigation = *initial;
    session->imu_identity = *imu;
    for (uint32_t i=0U; i<3U; i++) {
        /* Both pointer objects are checked above; Initialize has no other failure. */
        if (NavigationInput_Initialize(&session->observation[i], &observations[i]) != NavigationInputResult_Ok)
        { session->initialized=0U; return NavigationSessionResult_InvalidState; }
    }
    session->origin_us=origin_us; session->state_us=origin_us; session->initialized=1U;
    return NavigationSessionResult_Ok;
}

static uint8_t Session_ImuMatches(const NavigationSession *session, const NavigationInputIdentity *imu)
{
    return (uint8_t)((session->imu_identity.epoch == imu->epoch) &&
        (session->imu_identity.source == imu->source) &&
        (session->imu_identity.calibration == imu->calibration));
}

NavigationSessionResult NavigationSession_PredictPair(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputIdentity *imu,
    uint64_t start_us, uint64_t end_us, const double gyro_pair[6],
    const double force_pair[6], const double gravity[3], const double density[12])
{
    NavigationSessionResult result=Session_Validate(session,work);
    double half_dt;
    if (result != NavigationSessionResult_Ok) { return result; }
    if ((imu == NULL) || (gyro_pair == NULL) || (force_pair == NULL) ||
        (gravity == NULL) || (density == NULL)) { return NavigationSessionResult_InvalidInput; }
    if (Session_ImuMatches(session,imu) == 0U) { return NavigationSessionResult_IdentityMismatch; }
    if ((start_us != session->state_us) || (end_us <= start_us) || (end_us-start_us > 20000ULL))
    { return NavigationSessionResult_InvalidInput; }
    for (uint32_t i=0U; i<12U; i++) {
        if (!isfinite(density[i]) || (density[i] < 0.0)) { return NavigationSessionResult_InvalidInput; }
        work->density[i]=density[i];
    }
    if (session->navigation.model == NavigationEskf20) {
        for (uint32_t i=0U; i<3U; i++) { work->density[i]=density[i+3U]; work->density[i+3U]=density[i]; }
    }
    half_dt=(double)(end_us-start_us)/2000000.0;
    work->staged=session->navigation;
    for (uint32_t half=0U; half<2U; half++) {
        result=Session_CoreResult(Navigation_Predict(&work->staged,&work->core,
            &gyro_pair[half*3U],&force_pair[half*3U],gravity,work->density,half_dt));
        if (result != NavigationSessionResult_Ok) { return result; }
    }
    work->staged.time_s=(double)(end_us-session->origin_us)/1000000.0;
    session->navigation=work->staged; session->state_us=end_us;
    return NavigationSessionResult_Ok;
}

static NavigationSessionResult Session_ObservationFinish(NavigationSession *session,
    NavigationInputLedger *ledger, const NavigationInputEvent *event, NavigationResult result)
{
    if ((result == NavigationOk) || (result == NavigationRejectedNis) ||
        (result == NavigationRejectedCorrection)) {
        if (NavigationInput_Consume(ledger,event,session->state_us) != NavigationInputResult_Ok)
        { return NavigationSessionResult_InvalidState; }
    }
    return Session_CoreResult(result);
}

NavigationSessionResult NavigationSession_UpdateVector(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputEvent *event,
    NavigationVectorKind kind, const double measured[3], const double covariance[9], double gate)
{
    NavigationSessionResult result=Session_Validate(session,work);
    NavigationInputResult admission;
    NavigationResult core_result;
    uint32_t group;
    if (result != NavigationSessionResult_Ok) { return result; }
    if (!isfinite(gate) || (gate <= 0.0) || (measured == NULL) || (covariance == NULL) ||
        ((kind != NavigationPosition) && (kind != NavigationVelocity)))
    { return NavigationSessionResult_InvalidInput; }
    group=(kind == NavigationPosition) ? 0U : 1U;
    admission=NavigationInput_Check(&session->observation[group],event,session->state_us);
    if (admission != NavigationInputResult_Ok) { return (NavigationSessionResult)admission; }
    work->staged=session->navigation;
    core_result=Navigation_UpdateVector(&work->staged,&work->core,measured,covariance,kind,
        session->navigation.time_s,gate);
    result=Session_ObservationFinish(session,&session->observation[group],event,core_result);
    if (result == NavigationSessionResult_Ok) { session->navigation=work->staged; }
    return result;
}

NavigationSessionResult NavigationSession_UpdateMagnetic(NavigationSession *session,
    NavigationSessionWorkspace *work, const NavigationInputEvent *event,
    const float sensor_uT[3], const float covariance_uT2[9], NavigationMagStage stage,
    const NavigationMagCorrection *correction, double gate)
{
    NavigationSessionResult result=Session_Validate(session,work);
    NavigationInputResult admission;
    NavigationMagPrepared prepared;
    NavigationMagneticSample sample;
    NavigationResult core_result;
    if (result != NavigationSessionResult_Ok) { return result; }
    if (session->navigation.model == NavigationInEkf15) { return NavigationSessionResult_Unsupported; }
    if (!isfinite(gate) || (gate <= 0.0)) { return NavigationSessionResult_InvalidInput; }
    admission=NavigationInput_Check(&session->observation[2],event,session->state_us);
    if (admission != NavigationInputResult_Ok) { return (NavigationSessionResult)admission; }
    admission=NavigationMag_Prepare(sensor_uT,covariance_uT2,stage,correction,&prepared);
    if (admission == NavigationInputResult_FieldRejected) {
        if (NavigationInput_Consume(&session->observation[2],event,session->state_us) != NavigationInputResult_Ok)
        { return NavigationSessionResult_InvalidState; }
    }
    if (admission != NavigationInputResult_Ok) { return (NavigationSessionResult)admission; }
    for (uint32_t i=0U; i<3U; i++) { sample.corrected_sensor_uT[i]=(double)prepared.sensor_uT[i]; }
    for (uint32_t i=0U; i<9U; i++) { sample.covariance_sensor_uT2[i]=(double)prepared.covariance_uT2[i]; }
    sample.reference_strength_uT=(double)correction->reference_uT;
    sample.time_s=session->navigation.time_s; sample.sensor_frame=1U; sample.calibration=1U;
    work->staged=session->navigation;
    core_result=Navigation_UpdateMagnetic(&work->staged,&work->core,&sample,gate);
    result=Session_ObservationFinish(session,&session->observation[2],event,core_result);
    if (result == NavigationSessionResult_Ok) { session->navigation=work->staged; }
    return result;
}
