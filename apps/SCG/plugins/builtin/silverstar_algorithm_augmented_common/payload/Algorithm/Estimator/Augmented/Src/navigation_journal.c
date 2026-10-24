#include "navigation_journal.h"
#include "logger_bus.h"
#include <float.h>
#include <stddef.h>
#include <string.h>
_Static_assert(sizeof(double)==8U && DBL_MANT_DIG==53,"Journal needs IEEE754 binary64");
_Static_assert(sizeof(float)==4U && FLT_MANT_DIG==24,"Journal needs IEEE754 binary32");

static void Journal_UnsignedPut(NavigationJournal *journal,uint64_t value,uint32_t width)
{
    if(width>8U || journal->size>sizeof(journal->buffer) || width>sizeof(journal->buffer)-journal->size)
    { journal->valid=0U;return; }
    for(uint32_t i=0U;i<width;i++) { journal->buffer[journal->size++]=(uint8_t)(value>>(8U*i)); }
}
static void Journal_DoublesPut(NavigationJournal *journal,const double *values,uint32_t count)
{
    if(count>400U) { journal->valid=0U;return; }
    for(uint32_t i=0U;i<count;i++) {
        uint64_t bits;memcpy(&bits,&values[i],sizeof(bits));Journal_UnsignedPut(journal,bits,8U);
    }
}
static void Journal_FloatsPut(NavigationJournal *journal,const float *values,uint32_t count)
{
    if(count>15U) { journal->valid=0U;return; }
    for(uint32_t i=0U;i<count;i++) {
        uint32_t bits;memcpy(&bits,&values[i],sizeof(bits));Journal_UnsignedPut(journal,bits,4U);
    }
}
static void Journal_IdentityPut(NavigationJournal *journal,const NavigationInputIdentity *identity)
{
    Journal_UnsignedPut(journal,identity->epoch,4U);Journal_UnsignedPut(journal,identity->source,4U);
    Journal_UnsignedPut(journal,identity->calibration,4U);
}
static uint32_t Journal_Crc32(const NavigationJournal *journal)
{
    uint32_t crc=UINT32_MAX;
    for(uint32_t i=0U;i<journal->size && i<4096U;i++) {
        crc^=journal->buffer[i];
        for(uint32_t bit=0U;bit<8U;bit++) { crc=(crc>>1U)^((crc&1U)?UINT32_C(0xEDB88320):0U); }
    }
    return ~crc;
}
static NavigationJournalResult Journal_Flush(NavigationJournal *journal,uint64_t timestamp_us,uint8_t kind)
{
    FlightLogNavigationOperationPartRecord part;
    if(!journal->healthy || !journal->valid || journal->size==0U || journal->size>4096U || journal->operation==UINT32_MAX)
    { journal->healthy=0U;return NavigationJournalResult_InvalidState; }
    memset(&part,0,sizeof(part));part.epoch=journal->epoch;part.operation=journal->operation;
    part.total_size=journal->size;part.transaction_crc32=Journal_Crc32(journal);
    part.kind=kind;part.algorithm_id=journal->algorithm_id;part.revision=NAVIGATION_JOURNAL_REVISION;
    part.part_count=(uint8_t)((journal->size+159U)/160U);
    for(uint32_t i=0U;i<26U && i<part.part_count;i++) {
        uint32_t offset=i*160U,count=journal->size-offset;
        if(count>160U) { count=160U; }
        memset(part.data,0,sizeof(part.data));memcpy(part.data,&journal->buffer[offset],count);part.part_index=(uint8_t)i;
        if(LoggerBus_NavigationOperationPush(timestamp_us,&part)!=LOGGER_BUS_RESULT_OK) {
            journal->healthy=0U;journal->failures++;return NavigationJournalResult_StorageUnavailable;
        }
    }
    journal->operation++;return NavigationJournalResult_Ok;
}
static void Journal_StatePut(NavigationJournal *journal,const NavigationState *state)
{
    uint32_t dimension=state->model==NavigationInEkf15?15U:20U;
    Journal_DoublesPut(journal,state->rotation,9U);Journal_DoublesPut(journal,state->position,3U);
    Journal_DoublesPut(journal,state->velocity,3U);Journal_DoublesPut(journal,state->gyro_bias,3U);
    Journal_DoublesPut(journal,state->accel_bias,3U);Journal_DoublesPut(journal,state->installation,9U);
    Journal_DoublesPut(journal,&state->inclination,1U);Journal_DoublesPut(journal,&state->declination,1U);
    for(uint32_t i=0U;i<dimension;i++) { Journal_DoublesPut(journal,&state->covariance[i*20U],dimension); }
}
NavigationJournalResult NavigationJournal_Initial(NavigationJournal *journal,const NavigationReplay *replay,
    const int32_t origin_geodetic[3],uint16_t magnetic_physical,uint16_t magnetic_descriptor,uint8_t magnetic_bound)
{
    if(journal==NULL || replay==NULL || origin_geodetic==NULL || magnetic_bound>1U || replay->current.initialized!=1U || replay->body_count!=0U ||
       replay->observation_count!=0U || replay->current.navigation.time_s!=0.0 ||
       replay->current.navigation.model<NavigationEskf20 || replay->current.navigation.model>NavigationInEkf20)
    { return NavigationJournalResult_InvalidInput; }
    memset(journal,0,sizeof(*journal));journal->healthy=1U;journal->active=1U;journal->valid=1U;
    journal->epoch=replay->current.imu_identity.epoch;
    journal->algorithm_id=(uint8_t)replay->current.navigation.model+3U;
    Journal_UnsignedPut(journal,(uint32_t)replay->current.navigation.model,4U);
    Journal_UnsignedPut(journal,replay->current.origin_us,8U);Journal_IdentityPut(journal,&replay->current.imu_identity);
    for(uint32_t i=0U;i<3U;i++) { Journal_IdentityPut(journal,&replay->current.observation[i].identity); }
    Journal_UnsignedPut(journal,replay->maximum_delay_us,8U);
    for(uint32_t i=0U;i<3U;i++) { Journal_UnsignedPut(journal,(uint32_t)origin_geodetic[i],4U); }
    Journal_UnsignedPut(journal,magnetic_physical,2U);Journal_UnsignedPut(journal,magnetic_descriptor,2U);
    Journal_UnsignedPut(journal,magnetic_bound,4U);
    Journal_DoublesPut(journal,replay->gravity,3U);Journal_DoublesPut(journal,replay->density,12U);
    Journal_StatePut(journal,&replay->current.navigation);
    return Journal_Flush(journal,replay->current.state_us,0U);
}
NavigationJournalResult NavigationJournal_Predict(NavigationJournal *journal,
    const NavigationInputIdentity *imu,uint64_t start_us,uint64_t end_us,
    const double gyro[6],const double force[6],NavigationSessionResult result)
{
    if(journal==NULL || imu==NULL || gyro==NULL || force==NULL || !journal->active)
    { return NavigationJournalResult_InvalidInput; }
    journal->size=0U;journal->valid=1U;
    Journal_UnsignedPut(journal,start_us,8U);Journal_UnsignedPut(journal,end_us,8U);
    Journal_IdentityPut(journal,imu);Journal_DoublesPut(journal,gyro,6U);Journal_DoublesPut(journal,force,6U);
    Journal_UnsignedPut(journal,(uint32_t)result,4U);
    return Journal_Flush(journal,end_us,1U);
}
static void Journal_ObservationPut(NavigationJournal *journal,const NavigationReplayObservation *observation)
{
    const NavigationInputEvent *event=&observation->event;
    Journal_UnsignedPut(journal,observation->kind,4U);Journal_UnsignedPut(journal,observation->admission,4U);
    Journal_IdentityPut(journal,&event->identity);
    Journal_UnsignedPut(journal,event->sample_us,8U);Journal_UnsignedPut(journal,event->receive_us,8U);
    Journal_UnsignedPut(journal,event->sequence,4U);Journal_UnsignedPut(journal,event->timestamp_trusted,4U);
    Journal_DoublesPut(journal,&observation->gate,1U);
    if(observation->kind==2U) {
        Journal_FloatsPut(journal,observation->sensor_uT,3U);Journal_FloatsPut(journal,observation->covariance_uT2,9U);
        Journal_FloatsPut(journal,observation->correction.bias_uT,3U);Journal_FloatsPut(journal,observation->correction.soft_iron,9U);
        Journal_FloatsPut(journal,&observation->correction.reference_uT,1U);
        Journal_FloatsPut(journal,&observation->correction.minimum_norm_ratio,1U);
        Journal_FloatsPut(journal,&observation->correction.maximum_norm_ratio,1U);
        Journal_UnsignedPut(journal,(uint32_t)observation->stage,4U);
    } else { Journal_DoublesPut(journal,observation->measured,3U);Journal_DoublesPut(journal,observation->covariance,9U); }
}
NavigationJournalResult NavigationJournal_Observe(NavigationJournal *journal,uint64_t evaluation_us,
    const NavigationReplayObservation *observation,const NavigationReplayOutcome *outcome)
{
    if(journal==NULL || observation==NULL || outcome==NULL || observation->kind>2U || !journal->active)
    { return NavigationJournalResult_InvalidInput; }
    journal->size=0U;journal->valid=1U;Journal_ObservationPut(journal,observation);
    Journal_UnsignedPut(journal,(uint32_t)outcome->result,4U);Journal_DoublesPut(journal,&outcome->nis,1U);
    Journal_UnsignedPut(journal,evaluation_us,8U);
    return Journal_Flush(journal,evaluation_us,2U);
}
NavigationJournalResult NavigationJournal_Quality(NavigationJournal *journal,uint64_t evaluation_us,
    const NavigationInputIdentity *identity,uint32_t mode,uint32_t native_clock_trusted,
    NavigationMagQualityResult result,const NavigationMagQualityConfig *c,
    const NavigationMagQualityInput *x,const NavigationMagQualityOutput *y)
{
    if(journal==NULL || identity==NULL || c==NULL || x==NULL || y==NULL ||
       !journal->active || (mode!=1U && mode!=2U) || native_clock_trusted>1U) { return NavigationJournalResult_InvalidInput; }
    journal->size=0U;journal->valid=1U;
    Journal_UnsignedPut(journal,NAVIGATION_MAG_QUALITY_REVISION,4U);Journal_UnsignedPut(journal,mode,4U);
    Journal_UnsignedPut(journal,evaluation_us,8U);
    Journal_IdentityPut(journal,identity);Journal_UnsignedPut(journal,native_clock_trusted,4U);
    Journal_UnsignedPut(journal,x->imu_valid,4U);Journal_UnsignedPut(journal,x->transport_valid,4U);
    Journal_UnsignedPut(journal,x->queue_bytes,4U);Journal_UnsignedPut(journal,x->transport_epoch,4U);
    Journal_UnsignedPut(journal,x->calibration_generation,4U);Journal_UnsignedPut(journal,x->sequence,4U);
    Journal_UnsignedPut(journal,x->decode_span_us,4U);
    Journal_UnsignedPut(journal,x->decode_us,8U);Journal_UnsignedPut(journal,x->now_us,8U);
    Journal_UnsignedPut(journal,x->accel_decode_us,8U);Journal_UnsignedPut(journal,x->gyro_decode_us,8U);
    Journal_FloatsPut(journal,x->sensor_uT,3U);Journal_FloatsPut(journal,x->corrected_uT,3U);
    Journal_FloatsPut(journal,x->accel_mps2,3U);Journal_FloatsPut(journal,x->gyro_radps,3U);
    Journal_UnsignedPut(journal,c->minimum_samples,4U);Journal_UnsignedPut(journal,c->minimum_duration_us,4U);
    Journal_UnsignedPut(journal,c->maximum_gap_us,4U);Journal_UnsignedPut(journal,c->maximum_sequence_step,4U);
    const float scalars[10]={c->variance_floor_uT2,c->maximum_std_uT,c->maximum_span_uT,c->gyro_max_radps,
        c->accel_tolerance_mps2,c->accel_span_mps2,c->gravity_mps2,c->field_reference_uT,c->field_min_ratio,c->field_max_ratio};
    Journal_FloatsPut(journal,scalars,10U);
    Journal_UnsignedPut(journal,c->delay_us,4U);Journal_UnsignedPut(journal,c->uncertainty_us,4U);
    Journal_UnsignedPut(journal,c->maximum_time_uncertainty_us,4U);Journal_UnsignedPut(journal,c->maximum_queue_bytes,4U);
    Journal_UnsignedPut(journal,c->delay_bound_verified,4U);Journal_UnsignedPut(journal,y->sample_us,8U);
    Journal_UnsignedPut(journal,y->flags,4U);Journal_UnsignedPut(journal,y->uncertainty_us,4U);
    Journal_UnsignedPut(journal,y->sample_count,4U);Journal_UnsignedPut(journal,y->calibration_generation,4U);
    Journal_UnsignedPut(journal,y->covariance_valid,4U);Journal_UnsignedPut(journal,y->time_admitted,4U);
    Journal_FloatsPut(journal,y->covariance_sensor_uT2,9U);Journal_UnsignedPut(journal,(uint32_t)result,4U);
    return Journal_Flush(journal,evaluation_us,4U);
}

NavigationJournalResult NavigationJournal_End(NavigationJournal *journal,uint64_t state_us,uint32_t reason)
{
    if(journal==NULL || !journal->active) { return NavigationJournalResult_InvalidInput; }
    journal->size=0U;journal->valid=1U;
    Journal_UnsignedPut(journal,state_us,8U);Journal_UnsignedPut(journal,reason,4U);
    Journal_UnsignedPut(journal,journal->operation,4U);
    NavigationJournalResult result=Journal_Flush(journal,state_us,3U);journal->active=0U;
    return result;
}
