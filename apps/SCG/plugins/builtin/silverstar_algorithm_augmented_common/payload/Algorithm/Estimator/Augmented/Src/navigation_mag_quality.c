#include "navigation_mag_quality.h"
#include <math.h>
#include <stddef.h>
#include <string.h>

void NavigationMagQuality_Reset(NavigationMagQuality *state)
{
    if(state!=NULL) { (void)memset(state,0,sizeof(*state)); }
}

static uint8_t Quality_ConfigValid(const NavigationMagQualityConfig *c)
{
    const float values[10]={c->variance_floor_uT2,c->maximum_std_uT,c->maximum_span_uT,
        c->gyro_max_radps,c->accel_tolerance_mps2,c->accel_span_mps2,c->gravity_mps2,
        c->field_reference_uT,c->field_min_ratio,c->field_max_ratio};
    for(uint32_t i=0U;i<10U;i++) { if(!isfinite(values[i]) || values[i]<=0.0f) { return 0U; } }
    return (uint8_t)(c->minimum_samples>=16U && c->minimum_samples<=NAVIGATION_MAG_QUALITY_SAMPLES_MAX &&
        c->minimum_duration_us>=1000U && c->minimum_duration_us<=5000000U &&
        c->maximum_gap_us>0U && c->maximum_gap_us<=1000000U &&
        c->maximum_sequence_step>0U && c->maximum_sequence_step<=256U &&
        c->field_max_ratio>c->field_min_ratio && c->delay_us<=1000000U &&
        c->uncertainty_us<=1000000U && c->maximum_time_uncertainty_us<=1000000U &&
        c->maximum_queue_bytes<=4096U && c->delay_bound_verified<=1U);
}

static void Quality_WindowReset(NavigationMagQuality *s)
{
    s->count=0U;s->frozen=0U;s->window_start_us=0U;
    (void)memset(s->mean,0,sizeof(s->mean));(void)memset(s->scatter,0,sizeof(s->scatter));
    (void)memset(s->covariance,0,sizeof(s->covariance));
}

static uint8_t Quality_InputFinite(const NavigationMagQualityInput *x)
{
    for(uint32_t i=0U;i<3U;i++) {
        if(!isfinite(x->sensor_uT[i]) || !isfinite(x->corrected_uT[i]) ||
           !isfinite(x->accel_mps2[i]) || !isfinite(x->gyro_radps[i])) { return 0U; }
    }
    return (uint8_t)(x->transport_valid<=1U && x->imu_valid<=1U);
}

static double Quality_NormSquared(const float vector[3])
{
    double sum=0.0;
    for(uint32_t i=0U;i<3U;i++) { sum+=(double)vector[i]*(double)vector[i]; }
    return sum;
}

static uint8_t Quality_PositiveDefinite(const float covariance[9])
{
    double l[9]={0.0};
    for(uint32_t i=0U;i<3U;i++) {
        for(uint32_t j=0U;j<3U;j++) {
            if(!isfinite(covariance[i*3U+j]) || covariance[i*3U+j]!=covariance[j*3U+i]) { return 0U; }
        }
    }
    for(uint32_t i=0U;i<3U;i++) {
        for(uint32_t j=0U;j<=i;j++) {
            double value=(double)covariance[i*3U+j];
            for(uint32_t k=0U;k<j;k++) { value-=l[i*3U+k]*l[j*3U+k]; }
            if(i==j) { if(!isfinite(value) || value<=0.0) { return 0U; } l[i*3U+j]=sqrt(value); }
            else { l[i*3U+j]=value/l[j*3U+j]; }
        }
    }
    return 1U;
}

static uint8_t Quality_Freeze(NavigationMagQuality *s,const NavigationMagQualityConfig *c)
{
    for(uint32_t i=0U;i<3U;i++) {
        for(uint32_t j=0U;j<3U;j++) {
            double value=(s->scatter[i*3U+j]+s->scatter[j*3U+i])/(2.0*(double)(s->count-1U));
            if(i==j) {
                if(value<0.0 || value>(double)c->maximum_std_uT*(double)c->maximum_std_uT) { return 0U; }
                value+=(double)c->variance_floor_uT2;
            }
            s->covariance[i*3U+j]=(float)value;
            if(!isfinite(s->covariance[i*3U+j])) { return 0U; }
        }
    }
    s->frozen=Quality_PositiveDefinite(s->covariance);
    return (uint8_t)s->frozen;
}

static uint8_t Quality_Stationary(const NavigationMagQuality *s,const NavigationMagQualityConfig *c,
    const NavigationMagQualityInput *x)
{
    if(x->imu_valid!=1U || x->accel_decode_us==0U || x->gyro_decode_us==0U ||
       x->accel_decode_us>x->decode_us || x->gyro_decode_us>x->decode_us ||
       x->decode_us-x->accel_decode_us>c->maximum_gap_us || x->decode_us-x->gyro_decode_us>c->maximum_gap_us ||
       Quality_NormSquared(x->gyro_radps)>(double)c->gyro_max_radps*(double)c->gyro_max_radps ||
       fabs(sqrt(Quality_NormSquared(x->accel_mps2))-(double)c->gravity_mps2)>(double)c->accel_tolerance_mps2) { return 0U; }
    for(uint32_t i=0U;i<3U;i++) {
        if(s->count>0U && fabs((double)x->accel_mps2[i]-(double)s->accel_anchor[i])>(double)c->accel_span_mps2) { return 0U; }
    }
    return 1U;
}

static uint8_t Quality_Collect(NavigationMagQuality *s,const NavigationMagQualityConfig *c,
    const NavigationMagQualityInput *x)
{
    double delta[3];
    if(s->count>=NAVIGATION_MAG_QUALITY_SAMPLES_MAX) { return 0U; }
    if(s->count==0U) {
        s->window_start_us=x->decode_us;
        for(uint32_t i=0U;i<3U;i++) { s->minimum[i]=x->sensor_uT[i];s->maximum[i]=x->sensor_uT[i];s->accel_anchor[i]=x->accel_mps2[i]; }
    }
    s->count++;
    for(uint32_t i=0U;i<3U;i++) {
        if(x->sensor_uT[i]<s->minimum[i]) { s->minimum[i]=x->sensor_uT[i]; }
        if(x->sensor_uT[i]>s->maximum[i]) { s->maximum[i]=x->sensor_uT[i]; }
        if((double)s->maximum[i]-(double)s->minimum[i]>(double)c->maximum_span_uT) { return 0U; }
        delta[i]=(double)x->sensor_uT[i]-s->mean[i];s->mean[i]+=delta[i]/(double)s->count;
    }
    for(uint32_t i=0U;i<3U;i++) {
        for(uint32_t j=0U;j<3U;j++) { s->scatter[i*3U+j]+=delta[i]*((double)x->sensor_uT[j]-s->mean[j]); }
    }
    if(s->count>=c->minimum_samples && x->decode_us-s->window_start_us>=c->minimum_duration_us) { return Quality_Freeze(s,c); }
    return 1U;
}

static void Quality_TimeResolve(const NavigationMagQualityConfig *c,const NavigationMagQualityInput *x,
    NavigationMagQualityOutput *y)
{
    y->flags|=NAVIGATION_MAG_Q_PROXY;y->uncertainty_us=UINT32_MAX;y->sample_us=x->decode_us;
    if(x->decode_us<c->delay_us || x->decode_us==0U || x->now_us<x->decode_us ||
       x->now_us-x->decode_us>c->maximum_gap_us || x->transport_valid!=1U || x->queue_bytes>c->maximum_queue_bytes) {
        y->flags|=NAVIGATION_MAG_Q_TIME;return;
    }
    y->sample_us=x->decode_us-c->delay_us;y->flags|=NAVIGATION_MAG_Q_COMPENSATED;
    if(c->delay_bound_verified!=1U || c->uncertainty_us==0U || c->maximum_time_uncertainty_us==0U) {
        y->flags|=NAVIGATION_MAG_Q_UNVERIFIED;return;
    }
    uint64_t bound=(uint64_t)c->uncertainty_us+x->decode_span_us;
    if(bound>UINT32_MAX) { y->flags|=NAVIGATION_MAG_Q_TIME;return; }
    y->uncertainty_us=(uint32_t)bound;
    if(bound>c->maximum_time_uncertainty_us) { y->flags|=NAVIGATION_MAG_Q_TIME;return; }
    y->time_admitted=1U;
}

NavigationMagQualityResult NavigationMagQuality_Process(NavigationMagQuality *s,
    const NavigationMagQualityConfig *c,const NavigationMagQualityInput *x,NavigationMagQualityOutput *y)
{
    if(s==NULL || c==NULL || x==NULL || y==NULL) { return NavigationMagQualityResult_InvalidInput; }
    (void)memset(y,0,sizeof(*y));y->uncertainty_us=UINT32_MAX;y->calibration_generation=x->calibration_generation;
    if(!Quality_ConfigValid(c)) { Quality_WindowReset(s);y->flags=NAVIGATION_MAG_Q_CONFIG;return NavigationMagQualityResult_Unconfigured; }
    if(s->count>NAVIGATION_MAG_QUALITY_SAMPLES_MAX || s->seen>1U || s->frozen>1U) {
        NavigationMagQuality_Reset(s);y->flags=NAVIGATION_MAG_Q_NUMERIC;return NavigationMagQualityResult_InvalidState;
    }
    if(s->frozen && (!Quality_PositiveDefinite(s->covariance) || s->count<c->minimum_samples)) {
        NavigationMagQuality_Reset(s);y->flags=NAVIGATION_MAG_Q_NUMERIC;return NavigationMagQualityResult_InvalidState;
    }
    if(!Quality_InputFinite(x)) {
        NavigationMagQuality_Reset(s);y->flags=NAVIGATION_MAG_Q_INPUT;return NavigationMagQualityResult_InvalidInput;
    }
    Quality_TimeResolve(c,x,y);
    if(s->seen && (s->calibration_generation!=x->calibration_generation || s->transport_epoch!=x->transport_epoch)) {
        y->flags|=(s->calibration_generation!=x->calibration_generation)?NAVIGATION_MAG_Q_CALIBRATION:NAVIGATION_MAG_Q_TRANSPORT;
        Quality_WindowReset(s);s->seen=0U;
    }
    if(s->seen && x->sequence==s->previous_sequence && x->decode_us==s->previous_us) {
        y->flags|=NAVIGATION_MAG_Q_DUPLICATE;y->sample_count=s->count;
        return NavigationMagQualityResult_Duplicate;
    }
    uint32_t step=x->sequence-s->previous_sequence;
    if(s->seen && (step==0U || step>c->maximum_sequence_step || x->decode_us<=s->previous_us || x->decode_us-s->previous_us>c->maximum_gap_us)) {
        Quality_WindowReset(s);y->flags|=NAVIGATION_MAG_Q_SEQUENCE|NAVIGATION_MAG_Q_TIME;y->time_admitted=0U;
    } else if(s->seen && step>1U) { y->flags|=NAVIGATION_MAG_Q_SKIPPED; }
    s->seen=1U;s->previous_sequence=x->sequence;s->previous_us=x->decode_us;
    s->transport_epoch=x->transport_epoch;s->calibration_generation=x->calibration_generation;
    double norm=sqrt(Quality_NormSquared(x->corrected_uT));
    if(x->transport_valid!=1U || x->queue_bytes>c->maximum_queue_bytes || x->decode_span_us>c->maximum_gap_us || x->decode_us==0U ||
       x->now_us<x->decode_us || x->now_us-x->decode_us>c->maximum_gap_us ||
       norm<(double)c->field_reference_uT*(double)c->field_min_ratio || norm>(double)c->field_reference_uT*(double)c->field_max_ratio) {
        Quality_WindowReset(s);y->flags|=NAVIGATION_MAG_Q_TRANSPORT|NAVIGATION_MAG_Q_FIELD;y->time_admitted=0U;
        return NavigationMagQualityResult_Ok;
    }
    if((y->flags&NAVIGATION_MAG_Q_SEQUENCE)!=0U) { return NavigationMagQualityResult_Ok; }
    if(!Quality_Stationary(s,c,x)) {
        y->flags|=NAVIGATION_MAG_Q_MOTION;
        if(!s->frozen) { Quality_WindowReset(s); }
    } else if(!s->frozen && !Quality_Collect(s,c,x)) {
        Quality_WindowReset(s);y->flags|=NAVIGATION_MAG_Q_FIELD|NAVIGATION_MAG_Q_NUMERIC;
    }
    y->sample_count=s->count;
    if(s->frozen) {
        y->flags|=NAVIGATION_MAG_Q_COVARIANCE;y->covariance_valid=1U;
        (void)memcpy(y->covariance_sensor_uT2,s->covariance,sizeof(s->covariance));
    } else { y->flags|=NAVIGATION_MAG_Q_WARMUP; }
    return NavigationMagQualityResult_Ok;
}
