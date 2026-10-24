#include "navigation_replay.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

static uint8_t Replay_Terminal(NavigationSessionResult result)
{
    return (uint8_t)(result==NavigationSessionResult_Ok ||
        result==NavigationSessionResult_RejectedNis ||
        result==NavigationSessionResult_RejectedCorrection ||
        result==NavigationSessionResult_FieldRejected);
}

static uint8_t Replay_IdentityEqual(const NavigationInputIdentity *first,const NavigationInputIdentity *second)
{
    return (uint8_t)(first->epoch==second->epoch && first->source==second->source && first->calibration==second->calibration);
}

/* Called only after the caller verifies both timeline capacities and tags. */
static uint8_t Replay_LedgersValid(const NavigationReplay *replay)
{
    for(uint32_t group=0U;group<3U;group++) {
        const NavigationInputLedger *anchor=&replay->anchor.observation[group],*current=&replay->current.observation[group];
        uint64_t sample=anchor->last_sample_us;uint32_t sequence=anchor->last_sequence;uint8_t seen=anchor->seen;
        if(!Replay_IdentityEqual(&anchor->identity,&current->identity) || seen>1U || current->seen>1U ||
           (seen && sample>replay->anchor.state_us)) { return 0U; }
        for(uint32_t i=0U;i<replay->observation_count;i++) {
            if(replay->observations[i].kind==group) {
                const NavigationInputEvent *event=&replay->observations[i].event;
                uint32_t advance=event->sequence-sequence;
                if(seen && (event->sample_us<=sample || advance==0U || advance>=UINT32_C(0x80000000))) { return 0U; }
                sample=event->sample_us;sequence=event->sequence;seen=1U;
            }
        }
        if(current->seen!=seen || current->last_sample_us!=sample || current->last_sequence!=sequence) { return 0U; }
    }
    return 1U;
}

static uint8_t Replay_Valid(const NavigationReplay *replay)
{
    if(!(replay!=NULL && replay->body_count<=NAVIGATION_REPLAY_BODY_CAPACITY &&
        replay->observation_count<=NAVIGATION_REPLAY_OBSERVATION_CAPACITY &&
        replay->anchor.initialized==1U && replay->current.initialized==1U &&
        replay->anchor.origin_us==replay->current.origin_us &&
        replay->anchor.origin_us<=replay->anchor.state_us && replay->anchor.state_us<=replay->current.state_us &&
        replay->anchor.navigation.model==replay->current.navigation.model &&
        replay->current.navigation.model>=NavigationEskf20 && replay->current.navigation.model<=NavigationInEkf20 &&
        replay->maximum_delay_us>0U && replay->maximum_delay_us<=1000000U)) { return 0U; }
    if(replay->current.navigation.time_s!=(double)(replay->current.state_us-replay->current.origin_us)/1000000.0 ||
       replay->anchor.navigation.time_s!=(double)(replay->anchor.state_us-replay->anchor.origin_us)/1000000.0) { return 0U; }
    if(!Replay_IdentityEqual(&replay->anchor.imu_identity,&replay->current.imu_identity)) { return 0U; }
    uint64_t previous=replay->anchor.state_us;
    for(uint32_t i=0U;i<replay->body_count;i++) {
        const NavigationReplayBody *body=&replay->bodies[i];
        if(body->start_us!=previous || body->end_us<=previous || body->end_us-previous>20000U) { return 0U; }
        previous=body->end_us;
    }
    if(previous!=replay->current.state_us) { return 0U; }
    previous=replay->anchor.state_us;
    for(uint32_t i=0U;i<replay->observation_count;i++) {
        const NavigationReplayObservation *observation=&replay->observations[i];
        if(observation->kind>2U || observation->event.sample_us<=replay->anchor.state_us ||
           observation->event.sample_us<previous || observation->event.sample_us>replay->current.state_us ||
           observation->admission!=0U || observation->event.timestamp_trusted!=1U ||
           observation->event.sample_us>observation->event.receive_us || observation->event.receive_us>replay->current.state_us ||
           !Replay_IdentityEqual(&observation->event.identity,&replay->anchor.observation[observation->kind].identity) ||
           !Replay_Terminal(replay->outcomes[i].result)) { return 0U; }
        previous=observation->event.sample_us;
    }
    return Replay_LedgersValid(replay);
}

NavigationSessionResult NavigationReplay_Initialize(NavigationReplay *replay,
    NavigationReplayWorkspace *work,const NavigationState *initial,uint64_t origin_us,
    const NavigationInputIdentity *imu,const NavigationInputIdentity observations[3],
    const double gravity[3],const double density[12],uint64_t maximum_delay_us)
{
    NavigationSessionResult result;
    if(replay==NULL || work==NULL || initial==NULL || imu==NULL || observations==NULL || gravity==NULL || density==NULL ||
       maximum_delay_us==0U || maximum_delay_us>1000000U) { return NavigationSessionResult_InvalidInput; }
    for(uint32_t i=0U;i<3U;i++) { if(!isfinite(gravity[i])) { return NavigationSessionResult_InvalidInput; } }
    for(uint32_t i=0U;i<3U;i++) { if(observations[i].epoch!=imu->epoch) { return NavigationSessionResult_IdentityMismatch; } }
    for(uint32_t i=0U;i<12U;i++) { if(!isfinite(density[i]) || density[i]<0.0) { return NavigationSessionResult_InvalidInput; } }
    result=NavigationSession_Initialize(&work->trial,&work->session,initial,origin_us,imu,observations);
    if(result!=NavigationSessionResult_Ok) { return result; }
    memset(replay,0,sizeof(*replay));replay->anchor=work->trial;replay->current=work->trial;
    memcpy(replay->gravity,gravity,sizeof(replay->gravity));
    memcpy(replay->density,density,sizeof(replay->density));replay->maximum_delay_us=maximum_delay_us;
    return NavigationSessionResult_Ok;
}

static NavigationSessionResult Replay_Apply(NavigationSession *session,
    NavigationReplayWorkspace *work,const NavigationReplayObservation *observation,
    NavigationReplayOutcome *outcome)
{
    NavigationSessionResult result;
    if(observation->kind<2U) {
        result=NavigationSession_UpdateVector(session,&work->session,&observation->event,
            observation->kind==0U?NavigationPosition:NavigationVelocity,
            observation->measured,observation->covariance,observation->gate);
    } else if(observation->kind==2U) {
        result=NavigationSession_UpdateMagnetic(session,&work->session,&observation->event,
            observation->sensor_uT,observation->covariance_uT2,observation->stage,
            &observation->correction,observation->gate);
    } else { return NavigationSessionResult_InvalidInput; }
    outcome->result=result;
    outcome->nis=(result==NavigationSessionResult_Ok || result==NavigationSessionResult_RejectedNis ||
        result==NavigationSessionResult_RejectedCorrection)?work->session.core.nis:(double)NAN;
    work->operations++;
    return result;
}

/* Advance inside an ORIGINAL pair using its piecewise-constant half means.
 * Twice-relative integer ticks preserve odd-us half boundaries without doubling
 * an absolute uint64 timestamp. No interpolation of unrecorded IMU samples. */
static NavigationSessionResult Replay_Advance(NavigationSession *session,
    NavigationReplayWorkspace *work,const NavigationReplay *replay,
    const NavigationReplayBody *body,uint64_t target_us)
{
    return NavigationSession_PredictPart(session,&work->session,&session->imu_identity,
        body->start_us,body->end_us,target_us,body->gyro,body->force,replay->gravity,replay->density);
}

static const NavigationReplayObservation *Replay_Next(const NavigationReplay *replay,
    const NavigationReplayObservation *extra,uint32_t insertion,uint32_t index)
{
    if(extra==NULL) { return &replay->observations[index]; }
    if(index==insertion) { return extra; }
    return &replay->observations[index-(uint32_t)(index>insertion)];
}

static NavigationSessionResult Replay_Run(const NavigationReplay *replay,
    NavigationReplayWorkspace *work,NavigationSession *target,uint32_t body_limit,
    const NavigationReplayObservation *extra,uint32_t insertion)
{
    uint32_t cursor=0U,count=replay->observation_count+(uint32_t)(extra!=NULL);
    NavigationSessionResult result=NavigationSessionResult_Ok;
    *target=replay->anchor;work->operations=0U;
    for(uint32_t i=0U;i<body_limit;i++) {
        const NavigationReplayBody *body=&replay->bodies[i];
        if(body->start_us!=target->state_us || body->end_us<=body->start_us) { return NavigationSessionResult_InvalidState; }
        for(uint32_t j=cursor;j<count;j++) {
            const NavigationReplayObservation *observation=Replay_Next(replay,extra,insertion,j);
            if(observation->event.sample_us>body->end_us) { break; }
            if(observation->event.sample_us<target->state_us) { return NavigationSessionResult_InvalidState; }
            if(observation->event.sample_us>target->state_us) {
                result=Replay_Advance(target,work,replay,body,observation->event.sample_us);
                if(result!=NavigationSessionResult_Ok) { return result==NavigationSessionResult_NumericError?result:NavigationSessionResult_InvalidState; }
            }
            result=Replay_Apply(target,work,observation,&work->outcomes[j]);
            if(!Replay_Terminal(result)) {
                return (observation==extra || result==NavigationSessionResult_NumericError)?result:NavigationSessionResult_InvalidState;
            }
            cursor++;
        }
        if(target->state_us<body->end_us) {
            result=Replay_Advance(target,work,replay,body,body->end_us);
            if(result!=NavigationSessionResult_Ok) { return result==NavigationSessionResult_NumericError?result:NavigationSessionResult_InvalidState; }
        }
    }
    return NavigationSessionResult_Ok;
}

static void Replay_TrimCommit(NavigationReplay *replay,const NavigationSession *anchor)
{
    uint32_t removed=0U;
    for(uint32_t i=0U;i<replay->observation_count;i++) {
        if(replay->observations[i].event.sample_us>anchor->state_us) { break; }
        uint32_t kind=replay->observations[i].kind;
        if(replay->outcomes[i].result==NavigationSessionResult_Ok) {
            replay->retired_accepted[kind]++;replay->retired_last_accepted_us[kind]=replay->observations[i].event.sample_us;
        }
        else { replay->retired_rejected[kind]++; }
        removed++;
    }
    for(uint32_t i=removed;i<replay->observation_count;i++) {
        replay->observations[i-removed]=replay->observations[i];replay->outcomes[i-removed]=replay->outcomes[i];
    }
    replay->observation_count-=removed;
    for(uint32_t i=1U;i<replay->body_count;i++) { replay->bodies[i-1U]=replay->bodies[i]; }
    replay->body_count--;replay->anchor=*anchor;
}

NavigationSessionResult NavigationReplay_Predict(NavigationReplay *replay,
    NavigationReplayWorkspace *work,const NavigationInputIdentity *imu,
    uint64_t start_us,uint64_t end_us,const double gyro[6],const double force[6])
{
    NavigationSessionResult result;
    if(replay==NULL || work==NULL) { return NavigationSessionResult_InvalidInput; }
    if(!Replay_Valid(replay)) { return NavigationSessionResult_InvalidState; }
    work->trial=replay->current;
    result=NavigationSession_PredictPair(&work->trial,&work->session,imu,start_us,end_us,
        gyro,force,replay->gravity,replay->density);
    if(result!=NavigationSessionResult_Ok) { return result; }
    if(replay->body_count==NAVIGATION_REPLAY_BODY_CAPACITY) {
        result=Replay_Run(replay,work,&work->next_anchor,1U,NULL,0U);
        if(result!=NavigationSessionResult_Ok) { return result; }
        Replay_TrimCommit(replay,&work->next_anchor);
    }
    NavigationReplayBody *body=&replay->bodies[replay->body_count];
    body->start_us=start_us;body->end_us=end_us;
    memcpy(body->gyro,gyro,sizeof(body->gyro));memcpy(body->force,force,sizeof(body->force));
    replay->body_count++;replay->current=work->trial;
    return NavigationSessionResult_Ok;
}

static NavigationSessionResult Replay_Envelope(const NavigationReplay *replay,
    const NavigationReplayObservation *observation,uint32_t *insertion)
{
    const NavigationInputEvent *event=&observation->event;
    if(observation->kind>2U || event->timestamp_trusted>1U || !isfinite(observation->gate) || observation->gate<=0.0)
    { return NavigationSessionResult_InvalidInput; }
    if(observation->admission!=0U) {
        if(observation->admission==1U || observation->admission==2U || observation->admission==9U)
        { return (NavigationSessionResult)observation->admission; }
        return NavigationSessionResult_InvalidInput;
    }
    const NavigationInputIdentity *expected=&replay->current.observation[observation->kind].identity;
    if(event->identity.epoch!=expected->epoch || event->identity.source!=expected->source || event->identity.calibration!=expected->calibration)
    { return NavigationSessionResult_IdentityMismatch; }
    if(event->timestamp_trusted!=1U) { return NavigationSessionResult_UntrustedTime; }
    if(event->sample_us>event->receive_us) { return NavigationSessionResult_InvalidInput; }
    if(event->sample_us>replay->current.state_us || event->receive_us>replay->current.state_us) { return NavigationSessionResult_Future; }
    if(event->sample_us<=replay->anchor.state_us || replay->current.state_us-event->sample_us>replay->maximum_delay_us)
    { return NavigationSessionResult_HistoryMiss; }
    *insertion=0U;
    for(uint32_t i=0U;i<replay->observation_count;i++) {
        const NavigationReplayObservation *prior=&replay->observations[i];
        if(prior->kind==observation->kind && prior->event.sequence==event->sequence) { return NavigationSessionResult_Duplicate; }
        if(prior->event.sample_us<=event->sample_us) { *insertion=i+1U; }
    }
    /* A candidate must fit BETWEEN consumed sequences in measurement-time
     * order. Reject its external contradiction before replaying stored events;
     * never misclassify an induced successor failure as stored corruption. */
    const NavigationInputLedger *anchor=&replay->anchor.observation[observation->kind];
    uint32_t previous_sequence=anchor->last_sequence;uint8_t previous_seen=anchor->seen;
    for(uint32_t i=0U;i<replay->observation_count;i++) {
        const NavigationReplayObservation *prior=&replay->observations[i];
        if(prior->kind!=observation->kind) { continue; }
        if(prior->event.sample_us==event->sample_us) { return NavigationSessionResult_OutOfOrder; }
        if(prior->event.sample_us<event->sample_us) {
            previous_sequence=prior->event.sequence;previous_seen=1U;
        } else {
            uint32_t advance=prior->event.sequence-event->sequence;
            if(advance==0U || advance>=UINT32_C(0x80000000)) { return NavigationSessionResult_OutOfOrder; }
            break;
        }
    }
    if(previous_seen) {
        uint32_t advance=event->sequence-previous_sequence;
        if(advance==0U) { return NavigationSessionResult_Duplicate; }
        if(advance>=UINT32_C(0x80000000)) { return NavigationSessionResult_OutOfOrder; }
    }
    return NavigationSessionResult_Ok;
}

NavigationSessionResult NavigationReplay_Observe(NavigationReplay *replay,
    NavigationReplayWorkspace *work,const NavigationReplayObservation *observation,
    NavigationReplayOutcome *outcome)
{
    uint32_t insertion=0U;NavigationSessionResult result;
    if(replay==NULL || work==NULL || observation==NULL || outcome==NULL) { return NavigationSessionResult_InvalidInput; }
    if(!Replay_Valid(replay)) { outcome->result=NavigationSessionResult_InvalidState;outcome->nis=(double)NAN;return outcome->result; }
    outcome->result=NavigationSessionResult_InvalidInput;outcome->nis=NAN;
    if(observation->kind==2U && replay->current.navigation.model==NavigationInEkf15) {
        outcome->result=NavigationSessionResult_Unsupported;return outcome->result;
    }
    result=Replay_Envelope(replay,observation,&insertion);
    if(result!=NavigationSessionResult_Ok) { outcome->result=result;return result; }
    if(replay->observation_count==NAVIGATION_REPLAY_OBSERVATION_CAPACITY) {
        outcome->result=NavigationSessionResult_Capacity;return outcome->result;
    }
    result=Replay_Run(replay,work,&work->trial,replay->body_count,observation,insertion);
    if(result!=NavigationSessionResult_Ok) { outcome->result=result;return result; }
    *outcome=work->outcomes[insertion];
    for(uint32_t i=replay->observation_count;i>insertion;i--) { replay->observations[i]=replay->observations[i-1U]; }
    replay->observations[insertion]=*observation;replay->observation_count++;
    memcpy(replay->outcomes,work->outcomes,replay->observation_count*sizeof(replay->outcomes[0]));
    replay->current=work->trial;return outcome->result;
}

NavigationSessionResult NavigationReplay_CountsGet(const NavigationReplay *replay,
    uint32_t accepted[3],uint32_t rejected[3])
{
    if(!Replay_Valid(replay) || accepted==NULL || rejected==NULL) { return NavigationSessionResult_InvalidInput; }
    memcpy(accepted,replay->retired_accepted,sizeof(replay->retired_accepted));
    memcpy(rejected,replay->retired_rejected,sizeof(replay->retired_rejected));
    for(uint32_t i=0U;i<replay->observation_count;i++) {
        uint32_t kind=replay->observations[i].kind;
        if(kind>2U || !Replay_Terminal(replay->outcomes[i].result)) { return NavigationSessionResult_InvalidState; }
        if(replay->outcomes[i].result==NavigationSessionResult_Ok) { accepted[kind]++; }
        else { rejected[kind]++; }
    }
    return NavigationSessionResult_Ok;
}

NavigationSessionResult NavigationReplay_LastAcceptedGet(const NavigationReplay *replay,uint64_t sample_us[3])
{
    if(!Replay_Valid(replay) || sample_us==NULL) { return NavigationSessionResult_InvalidInput; }
    memcpy(sample_us,replay->retired_last_accepted_us,sizeof(replay->retired_last_accepted_us));
    for(uint32_t i=0U;i<replay->observation_count;i++) {
        uint32_t kind=replay->observations[i].kind;
        if(kind>2U) { return NavigationSessionResult_InvalidState; }
        if(replay->outcomes[i].result==NavigationSessionResult_Ok) { sample_us[kind]=replay->observations[i].event.sample_us; }
    }
    return NavigationSessionResult_Ok;
}
