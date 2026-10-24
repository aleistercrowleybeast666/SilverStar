#include "capture_internal.h"
#include <stddef.h>
#include <string.h>

static CaptureStorage s_capture __attribute__((section(".capture_ccm"),aligned(8)));
_Static_assert(sizeof(InstallationCaptureSample)==88U,"source ABI changed");
_Static_assert(sizeof(CapturePair)==316U,"pair ABI changed");
_Static_assert(sizeof(CaptureFrozen)<=640U,"complete snapshot exceeds reservation");
_Static_assert(sizeof(CaptureTransaction)<=256U,"transaction exceeds reservation");
_Static_assert(sizeof(CaptureSha)<=128U,"SHA exceeds reservation");
_Static_assert(sizeof(CaptureStorage)==1960U,"capture allocation changed");

static void Capture_ObjectCheck(void)
{
    CaptureTransaction *t=&s_capture.transaction.fields;uint8_t i,bad=0U;
    if(t->state>InstallationCaptureState_Failed||t->queue_head>=2U||t->queue_count>2U||
        t->consumer_active>1U||t->active_part>1U||t->pending[0]>1U||t->pending[1]>1U||
        (t->consumer_active&&t->queue_count==0U)){bad=1U;}
    if(s_capture.control.fields.resource_owner>10U||
        ((s_capture.control.fields.resource_owner==0U)!=(s_capture.control.fields.resource_token==0U))){bad=1U;}
    if(!bad){for(i=0U;i<t->queue_count;i++){if(s_capture.pairs[(t->queue_head+i)%2U].committed>1U){bad=1U;}}}
    if(s_capture.control.fields.configured){
        for(i=0U;i<2U;i++){
            const InstallationCaptureSource *source=&s_capture.frozen.fields.snapshot.sources[i];
            if(source->profile>=4U||(source->profile&1U)!=i||source->stride==0U||source->stride>65535U||
                t->native_modulo[i]>=source->stride){bad=1U;}
        }
    }
    if(bad){
        t->state=InstallationCaptureState_Failed;t->reason=InstallationCaptureResult_Failed;
        t->queue_head=0U;t->queue_count=0U;t->consumer_active=0U;t->active_part=0U;
        t->pending[0]=0U;t->pending[1]=0U;t->native_modulo[0]=0U;t->native_modulo[1]=0U;
        t->cleanup_complete=0U;s_capture.control.fields.configured=0U;s_capture.control.fields.snapshot_failed=1U;
    }
}

static uint8_t Capture_Enter(void)
{
#if defined(__arm__) || defined(__thumb__)
    uint32_t saved;
    /* The existing single-core PlatformCritical save/restore pattern, scoped
     * only to acquiring one byte. No exclusives on CCM or spin/wait loop. */
    __asm__ volatile("mrs %0, primask\n\tcpsid i":"=r"(saved)::"memory");
    if(s_capture.control.fields.gate!=0U){
        __asm__ volatile("msr primask, %0"::"r"(saved):"memory");
        return 0U;
    }
    s_capture.control.fields.gate=1U;
    __asm__ volatile("msr primask, %0"::"r"(saved):"memory");
#else
    uint8_t expected=0U;
    if(!__atomic_compare_exchange_n(&s_capture.control.fields.gate,
        &expected,1U,1,__ATOMIC_ACQUIRE,__ATOMIC_RELAXED)){return 0U;}
#endif
    Capture_ObjectCheck();return 1U;
}
static void Capture_Leave(void)
{
#if defined(__arm__) || defined(__thumb__)
    __asm__ volatile("dmb":::"memory");s_capture.control.fields.gate=0U;
    __asm__ volatile("":::"memory");
#else
    __atomic_store_n(&s_capture.control.fields.gate,0U,__ATOMIC_RELEASE);
#endif
}

static uint8_t Capture_Finite(double value)
{ union {double f;uint64_t u;} bits;bits.f=value;return (uint8_t)(((bits.u>>52)&2047U)!=2047U); }

static uint8_t Capture_Token(const char text[32])
{
    uint8_t i;
    for (i=0U;i<32U;i++) {
        char c=text[i];
        if (c=='\0') {return (uint8_t)(i!=0U);}
        if (!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'||c=='.')) {return 0U;}
    }
    return 0U;
}

static uint8_t Capture_AxisValid(const int8_t axis[3])
{
    int a[3]={axis[0],axis[1],axis[2]}, sign=1, inversions=0;uint8_t i,j;
    for (i=0U;i<3U;i++) {if(a[i]<0){sign=-sign;a[i]=-a[i];}if(a[i]<1||a[i]>3){return 0U;}}
    for (i=0U;i<3U;i++) {for(j=(uint8_t)(i+1U);j<3U;j++){if(a[i]==a[j]){return 0U;}if(a[i]>a[j]){inversions++;}}}
    return (uint8_t)(sign*((inversions&1)!=0?-1:1)==1);
}

static uint8_t Capture_SourceValid(const InstallationCaptureSnapshot *snapshot,uint8_t role)
{
    const InstallationCaptureSource *source=&snapshot->sources[role];
    if ((source->profile>=4U)||((source->profile&1U)!=role)||(source->descriptor==0U)||
        (source->physical==0U)||(source->stride==0U)||(source->stride>65535U)||
        (source->phase>=source->stride)||
        (source->reserved_driver!=0U)||(source->reserved_model!=0U)||
        (source->proof_flags>7U)||!Capture_AxisValid(source->axis_map)) {return 0U;}
    if (source->profile<2U) {
        return (uint8_t)((snapshot->offline==1U)&&(source->intrinsic_generation!=0U)&&(source->time_basis==2U)&&
            (source->proof_flags==7U)&&(source->uncertainty_us<=snapshot->maximum_uncertainty_us));
    }
    return (uint8_t)((source->time_basis<=1U)&&(source->proof_flags==0U)&&
        (source->epoch==0U)&&(source->uncertainty_us==UINT32_MAX));
}

static uint8_t Capture_SnapshotValid(const InstallationCaptureSnapshot *snapshot)
{
    uint8_t i;
    if ((snapshot==NULL)||(snapshot->reserved!=0U)||(snapshot->boot_known>1U)||
        (snapshot->R_GA_known>1U)||(snapshot->offline>1U)||
        (snapshot->train_pairs<3U)||(snapshot->train_pairs>64U)||
        (snapshot->holdout_pairs<3U)||(snapshot->holdout_pairs>64U)||
        (snapshot->maximum_skew_us==0U)||(snapshot->maximum_uncertainty_us==0U)||
        (snapshot->native_health_timeout_us==0U)||(snapshot->source_timeout_us==0U)||
        (snapshot->face_timeout_us<=snapshot->source_timeout_us)||
        (snapshot->selected_interval_max_us==0U)||(snapshot->nominal_output_millihz==0U)) {return 0U;}
    if (!Capture_SourceValid(snapshot,0U)||!Capture_SourceValid(snapshot,1U)||
        !Capture_Token(snapshot->intrinsic_id[0])||!Capture_Token(snapshot->intrinsic_id[1])) {return 0U;}
    for(i=0U;i<3U;i++){if(!Capture_Finite(snapshot->accel_bias[i])||!Capture_Finite(snapshot->mag_bias[i])){return 0U;}}
    for(i=0U;i<9U;i++){if(!Capture_Finite(snapshot->accel_matrix[i])||!Capture_Finite(snapshot->mag_matrix[i])||!Capture_Finite(snapshot->R_GA[i])){return 0U;}}
    for(i=0U;i<2U;i++){
        if(snapshot->sources[i].intrinsic_generation==0U){
            const double *bias=i==0U?snapshot->accel_bias:snapshot->mag_bias;
            const double *matrix=i==0U?snapshot->accel_matrix:snapshot->mag_matrix;
            uint8_t j;
            if(strcmp(snapshot->intrinsic_id[i],"UNKNOWN")!=0){return 0U;}
            for(j=0U;j<3U;j++){if(bias[j]!=0.){return 0U;}}
            for(j=0U;j<9U;j++){if(matrix[j]!=0.){return 0U;}}
        }
    }
    return 1U;
}

static InstallationCaptureResult Capture_Fail(InstallationCaptureResult reason)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    t->state=InstallationCaptureState_Failed;t->reason=(uint8_t)reason;
    return reason;
}

static uint8_t Capture_SidMatches(const uint8_t sid[16])
{return (uint8_t)(sid!=NULL&&memcmp(sid,s_capture.transaction.fields.sid,16U)==0);}

static uint8_t Capture_Expire(uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    if(s_capture.control.fields.resource_owner==1U&&now_us>=t->last_command_us&&
        t->state!=InstallationCaptureState_Cancelling&&t->state!=InstallationCaptureState_Cancelled&&
        now_us-t->last_command_us>=30000000U){
        t->state=InstallationCaptureState_Cancelling;t->reason=InstallationCaptureResult_Timeout;
        t->cleanup_complete=0U;return 1U;
    }
    return 0U;
}

static InstallationCaptureResult Capture_ClaimLocked(uint8_t owner,uint32_t *token)
{
    CaptureControl *control=&s_capture.control.fields;
    if(!control->enabled){return InstallationCaptureResult_Disabled;}
    if(control->resource_owner!=0U){return InstallationCaptureResult_Busy;}
    if(control->resource_generation==UINT32_MAX){return InstallationCaptureResult_Capacity;}
    control->resource_generation++;control->resource_token=control->resource_generation;
    control->resource_owner=owner;*token=control->resource_token;return InstallationCaptureResult_Ok;
}

InstallationCaptureResult InstallationCapture_ResourceClaim(uint8_t owner,uint32_t *token)
{
    InstallationCaptureResult result;
    if(owner<1U||owner>10U||token==NULL){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    result=Capture_ClaimLocked(owner,token);Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_ResourceRelease(uint8_t owner,uint32_t token)
{
    CaptureControl *control=&s_capture.control.fields;InstallationCaptureResult result=InstallationCaptureResult_Stale;
    if(owner<1U||owner>10U||token==0U){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(control->resource_owner==owner&&control->resource_token==token){
        if(owner==1U&&s_capture.transaction.fields.state>InstallationCaptureState_Configured){result=InstallationCaptureResult_Busy;}
        else {control->resource_owner=0U;control->resource_token=0U;result=InstallationCaptureResult_Ok;}
    }
    Capture_Leave();return result;
}

static void Capture_Cleanup(void)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    if ((t->state==InstallationCaptureState_Cancelling)&&(t->producer_stopped!=0U)&&(t->consumer_active==0U)) {
        t->queue_count=0U;t->pending[0]=0U;t->pending[1]=0U;
        t->state=InstallationCaptureState_Cancelled;t->cleanup_complete=1U;
    }
}

InstallationCaptureResult InstallationCapture_Enable(uint8_t enabled)
{
    InstallationCaptureResult result=InstallationCaptureResult_Ok;
    if(enabled>1U){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(s_capture.control.fields.resource_owner!=0U){result=InstallationCaptureResult_Busy;}
    else if((s_capture.transaction.fields.state>InstallationCaptureState_Configured)&&
        (s_capture.transaction.fields.state!=InstallationCaptureState_Cancelled)) {result=InstallationCaptureResult_Busy;}
    else {s_capture.control.fields.enabled=enabled;if(enabled==0U){s_capture.transaction.fields.state=InstallationCaptureState_Disabled;}}
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_Configure(const InstallationCaptureSnapshot *snapshot)
{
    CaptureSink sink={0};InstallationCaptureResult result=InstallationCaptureResult_Ok;
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(s_capture.control.fields.enabled==0U){result=InstallationCaptureResult_Disabled;}
    else if(s_capture.transaction.fields.state>InstallationCaptureState_Configured||s_capture.control.fields.resource_owner!=0U){result=InstallationCaptureResult_Busy;}
    else if(!Capture_SnapshotValid(snapshot)){result=InstallationCaptureResult_Invalid;}
    else {
        (void)memcpy(&s_capture.frozen.fields.snapshot,snapshot,sizeof(*snapshot));
        CaptureSha_Init(&s_capture.sha.fields);sink.hash=&s_capture.sha.fields;
        CaptureInfo_Output(&sink,&s_capture.frozen.fields,0U);
        CaptureSha_Finish(&s_capture.sha.fields,s_capture.frozen.fields.binding);
        if(sink.failed!=0U){result=Capture_Fail(InstallationCaptureResult_Capacity);}
        else {
            (void)memset(&sink,0,sizeof(sink));CaptureSha_Init(&s_capture.sha.fields);sink.hash=&s_capture.sha.fields;
            CaptureInfo_Output(&sink,&s_capture.frozen.fields,1U);CaptureSha_Finish(&s_capture.sha.fields,s_capture.info_digest);
            if(sink.failed!=0U){result=Capture_Fail(InstallationCaptureResult_Capacity);}
            else {s_capture.control.fields.info_bytes=sink.position;s_capture.control.fields.configured=1U;
                s_capture.control.fields.snapshot_failed=0U;s_capture.transaction.fields.state=InstallationCaptureState_Configured;}
        }
    }
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_InfoRead(uint16_t cursor,uint8_t output[48],uint16_t *length,uint16_t *next,uint8_t *end)
{
    CaptureSink sink={0};InstallationCaptureResult result=InstallationCaptureResult_Ok;
    if((output==NULL)||(length==NULL)||(next==NULL)||(end==NULL)){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(s_capture.control.fields.configured==0U){result=InstallationCaptureResult_Disabled;}
    else if((cursor>=s_capture.control.fields.info_bytes)||((cursor%48U)!=0U)){result=InstallationCaptureResult_Invalid;}
    else {
        sink.from=cursor;sink.output=output;sink.capacity=48U;
        CaptureInfo_Output(&sink,&s_capture.frozen.fields,1U);
        if(sink.failed!=0U||sink.position!=s_capture.control.fields.info_bytes){result=Capture_Fail(InstallationCaptureResult_Failed);}
        else {*length=sink.length;*next=(uint16_t)(cursor+sink.length);*end=(uint8_t)(*next==sink.position);}
    }
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_Status(InstallationCaptureStatus *status)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    if(status==NULL){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    status->state_bytes=sizeof(s_capture);status->frozen_bytes=sizeof(CaptureFrozen);
    status->transaction_bytes=sizeof(CaptureTransaction);status->queue_slots=2U;
    status->info_bytes=s_capture.control.fields.info_bytes;status->next_pair=t->next_pair;
    status->train_count=t->train_count;status->holdout_count=t->holdout_count;
    status->state=t->state;status->reason=t->reason;status->cleanup_complete=t->cleanup_complete;status->consumer_active=t->consumer_active;
    (void)memcpy(status->binding,s_capture.frozen.fields.binding,32U);(void)memcpy(status->info_sha256,s_capture.info_digest,32U);
    status->resource_owner=s_capture.control.fields.resource_owner;status->resource_token=s_capture.control.fields.resource_token;
    status->resource_generation=s_capture.control.fields.resource_generation;
    Capture_Leave();return InstallationCaptureResult_Ok;
}

InstallationCaptureResult InstallationCapture_Begin(const uint8_t sid[16],uint32_t rid,const uint8_t binding[15],uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;InstallationCaptureResult result=InstallationCaptureResult_Ok;
    uint8_t i,any=0U;
    if(sid==NULL||binding==NULL||rid==0U||rid>=UINT32_MAX-1U){return InstallationCaptureResult_Invalid;}
    for(i=0U;i<16U;i++){any|=sid[i];}if(any==0U){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(!s_capture.control.fields.enabled||!s_capture.control.fields.configured){result=InstallationCaptureResult_Disabled;}
    else if(memcmp(binding,s_capture.frozen.fields.binding,15U)!=0){result=InstallationCaptureResult_Conflict;}
    else if(Capture_Expire(now_us)){result=InstallationCaptureResult_Timeout;}
    else if(t->state!=InstallationCaptureState_Configured){
        result=(Capture_SidMatches(sid)&&t->rid==rid&&t->state==InstallationCaptureState_WaitFace)?InstallationCaptureResult_Ok:InstallationCaptureResult_Busy;
    } else if(Capture_SidMatches(sid)){result=InstallationCaptureResult_Stale;}
    else if(s_capture.control.fields.resource_owner!=0U){result=InstallationCaptureResult_Busy;}
    else {
        uint32_t token;
        result=Capture_ClaimLocked(1U,&token);
        if(result==InstallationCaptureResult_Ok){
            (void)memset(t,0,sizeof(*t));(void)memcpy(t->sid,sid,16U);
            t->rid=rid;t->now=now_us;t->last_command_us=now_us;t->next_pair=1U;t->state=InstallationCaptureState_WaitFace;
        }
    }
    Capture_Leave();return result;
}

static void Capture_FaceKey(uint8_t key[16],uint8_t mode,uint8_t stage,uint8_t face,uint16_t attempt)
{
    (void)memset(key,0,16U);key[0]=mode;key[1]=stage;key[2]=face;key[3]=(uint8_t)attempt;key[4]=(uint8_t)(attempt>>8);
}

InstallationCaptureResult InstallationCapture_Face(const uint8_t sid[16],uint32_t rid,uint8_t mode,uint8_t stage,uint8_t face,uint16_t attempt,uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;InstallationCaptureResult result=InstallationCaptureResult_Pending;
    uint8_t key[16],i;
    if(mode>1U||stage<1U||stage>2U||face>5U||attempt==0U||rid==0U||rid>=UINT32_MAX-1U){return InstallationCaptureResult_Invalid;}
    Capture_FaceKey(key,mode,stage,face,attempt);
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(!Capture_SidMatches(sid)){result=InstallationCaptureResult_Stale;}
    else if(Capture_Expire(now_us)){result=InstallationCaptureResult_Timeout;}
    else if(rid<t->rid){result=InstallationCaptureResult_Stale;}
    else if(rid==t->face_rid){result=memcmp(key,t->face_key,16U)!=0?InstallationCaptureResult_Conflict:t->state==InstallationCaptureState_Complete?InstallationCaptureResult_Complete:t->state==InstallationCaptureState_Failed?InstallationCaptureResult_Failed:InstallationCaptureResult_Pending;}
    else if(rid<=t->rid){result=InstallationCaptureResult_Stale;}
    else if(t->state!=InstallationCaptureState_WaitFace&&t->state!=InstallationCaptureState_Complete){result=InstallationCaptureResult_Busy;}
    else if(t->faces_started>=64U){result=InstallationCaptureResult_Capacity;}
    else if(now_us<t->now){result=Capture_Fail(InstallationCaptureResult_SourceTime);}
    else {
        t->rid=rid;t->face_rid=rid;(void)memcpy(t->face_key,key,16U);t->now=now_us;t->started=now_us;t->last_command_us=now_us;
        t->mode=mode;t->stage=stage;t->face=face;t->attempt=attempt;t->role=mode;t->train_count=0U;t->holdout_count=0U;
        t->faces_started++;
        t->queue_head=0U;t->queue_count=0U;t->reason=0U;t->consumer_active=0U;t->cleanup_complete=0U;t->producer_stopped=0U;
        for(i=0U;i<2U;i++){t->native_last[i]=now_us;t->selected_last[i]=now_us;t->native_seen[i]=0U;t->pending[i]=0U;t->native_modulo[i]=0U;}
        t->state=InstallationCaptureState_Collecting;
    }
    Capture_Leave();return result;
}

static InstallationCaptureResult Capture_PollLocked(uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    const InstallationCaptureSnapshot *f=&s_capture.frozen.fields.snapshot;uint8_t role;
    if(now_us<t->now){return Capture_Fail(InstallationCaptureResult_SourceTime);}t->now=now_us;
    (void)Capture_Expire(now_us);
    if(t->state==InstallationCaptureState_Collecting){
        if(now_us-t->started>=f->face_timeout_us){return Capture_Fail(InstallationCaptureResult_Timeout);}
        for(role=0U;role<2U;role++){
            if(now_us-t->native_last[role]>=f->native_health_timeout_us||now_us-t->selected_last[role]>f->selected_interval_max_us){return Capture_Fail(InstallationCaptureResult_Timeout);}
        }
    }
    Capture_Cleanup();
    if(t->state==InstallationCaptureState_Complete){return InstallationCaptureResult_Complete;}
    if(t->state==InstallationCaptureState_Cancelled){return InstallationCaptureResult_Cancelled;}
    if(t->state==InstallationCaptureState_Failed){return InstallationCaptureResult_Failed;}
    return InstallationCaptureResult_Pending;
}

InstallationCaptureResult InstallationCapture_Poll(uint64_t now_us)
{
    InstallationCaptureResult result;if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    result=Capture_PollLocked(now_us);Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_RequestTouch(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;InstallationCaptureResult result=InstallationCaptureResult_Ok;
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(!Capture_SidMatches(sid)||rid!=t->rid||s_capture.control.fields.resource_owner!=1U){result=InstallationCaptureResult_Stale;}
    else if(Capture_Expire(now_us)){result=InstallationCaptureResult_Timeout;}
    else if(now_us<t->now){result=Capture_Fail(InstallationCaptureResult_SourceTime);}
    else {t->last_command_us=now_us;}
    Capture_Leave();return result;
}

static void Body_U32(uint8_t *out,uint32_t value)
{uint8_t i;for(i=0U;i<4U;i++){out[i]=(uint8_t)(value>>(8U*i));}}
static void Body_U64(uint8_t *out,uint64_t value)
{uint8_t i;for(i=0U;i<8U;i++){out[i]=(uint8_t)(value>>(8U*i));}}
static void Body_F64(uint8_t *out,double value)
{union{double f;uint64_t u;}v;v.f=value;Body_U64(out,v.u);}

static void Body_Tag(uint8_t *out,uint32_t rid,uint8_t pose,uint8_t role)
{
    static const char hex[]="0123456789ABCDEF";uint8_t i,offset=pose!=0U?1U:0U;
    (void)memset(out,0,16U);if(pose!=0U){out[0]='P';}
    for(i=0U;i<8U;i++){out[offset+i]=(uint8_t)hex[(rid>>(28U-i*4U))&15U];}
    if(pose==0U){out[8]=role==0U?'T':'V';}
}

static void Body_Create(uint8_t out[154],uint8_t role)
{
    const InstallationCaptureSample *sample=&s_capture.pending[role];
    const CaptureTransaction *t=&s_capture.transaction.fields;uint8_t i;
    (void)memset(out,0,154U);Body_U32(out,sample->sequence);Body_U32(&out[4],sample->epoch);
    Body_U64(&out[8],sample->sample_us);Body_U64(&out[16],sample->receive_us);
    Body_U32(&out[32],sample->uncertainty_us);out[36]=(uint8_t)sample->flags;
    for(i=0U;i<(role==0U?6U:3U);i++){
        Body_F64(&out[37U+8U*i],(double)sample->physical[i]);
        if((sample->flags&16U)!=0U){Body_U32(&out[93U+4U*i],(uint32_t)sample->raw[i]);}
    }
    if((sample->flags&8U)!=0U){Body_F64(&out[85],(double)sample->temperature);}
    Body_Tag(&out[117],t->face_rid,0U,t->role);Body_Tag(&out[133],t->face_rid,1U,t->role);
    out[149]=t->stage;out[150]=t->face;out[151]=t->role;out[152]=(uint8_t)t->attempt;out[153]=(uint8_t)(t->attempt>>8);
}

static InstallationCaptureResult Capture_Pair(void)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    const InstallationCaptureSnapshot *f=&s_capture.frozen.fields.snapshot;
    CapturePair *slot;uint8_t i;uint64_t skew;
    if(t->pending[0]==0U||t->pending[1]==0U){return InstallationCaptureResult_Ok;}
    if(t->queue_count>=2U||t->next_pair==UINT32_MAX){return Capture_Fail(InstallationCaptureResult_Capacity);}
    if(f->sources[0].profile<2U&&f->sources[1].profile<2U){
        uint64_t a=s_capture.pending[0].sample_us,m=s_capture.pending[1].sample_us;
        skew=a>=m?a-m:m-a;
        uint64_t uncertainty=(uint64_t)s_capture.pending[0].uncertainty_us+s_capture.pending[1].uncertainty_us;
        if(skew>f->maximum_skew_us||uncertainty>f->maximum_uncertainty_us||
            uncertainty>(uint64_t)f->maximum_skew_us-skew){return Capture_Fail(InstallationCaptureResult_SourceTime);}
    }
    slot=&s_capture.pairs[(t->queue_head+t->queue_count)%2U];
    Body_Create(slot->body[0],0U);Body_Create(slot->body[1],1U);slot->pair=t->next_pair++;slot->committed=0U;t->queue_count++;
    for(i=0U;i<2U;i++){
        if(t->role==0U){t->train_last_sequence[i]=s_capture.pending[i].sequence;t->train_end_us[i]=s_capture.pending[i].sample_us;}
        else if(t->holdout_count==0U){t->holdout_first_sequence[i]=s_capture.pending[i].sequence;t->holdout_start_us[i]=s_capture.pending[i].sample_us;}
        t->pending[i]=0U;
    }
    if(t->role==0U){t->train_count++;if(t->train_count==f->train_pairs){t->role=1U;}}
    else {t->holdout_count++;if(t->holdout_count==f->holdout_pairs){t->state=InstallationCaptureState_Draining;}}
    return InstallationCaptureResult_Ok;
}

static InstallationCaptureResult Capture_SourceLocked(uint8_t role,const InstallationCaptureSample *sample,uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;
    const InstallationCaptureSource *source=&s_capture.frozen.fields.snapshot.sources[role];uint8_t i;
    if(t->state!=InstallationCaptureState_Collecting){return InstallationCaptureResult_Stale;}
    if(Capture_PollLocked(now_us)!=InstallationCaptureResult_Pending){return InstallationCaptureResult_Failed;}
    if(sample->epoch!=source->epoch||sample->receive_us>now_us||sample->receive_us<t->started||
        sample->sample_us>sample->receive_us||(source->time_basis==2U&&sample->sample_us<t->started)||
        (sample->flags&~31U)!=0U||(sample->flags&7U)!=0U){return Capture_Fail(InstallationCaptureResult_SourceTime);}
    if(t->native_seen[role]&&(sample->sequence-t->last_native_sequence[role]!=1U)){return Capture_Fail(InstallationCaptureResult_SourceGap);}
    if(t->native_seen[role]&&(sample->sample_us<t->native_sample_us[role]||
        (source->time_basis==2U&&sample->sample_us==t->native_sample_us[role]))){return Capture_Fail(InstallationCaptureResult_SourceTime);}
    if(source->time_basis==2U&&(sample->uncertainty_us<source->uncertainty_us||
        sample->uncertainty_us>s_capture.frozen.fields.snapshot.maximum_uncertainty_us)){return Capture_Fail(InstallationCaptureResult_SourceTime);}
    if(source->profile>=2U&&(sample->uncertainty_us!=UINT32_MAX||
        (source->time_basis==1U&&sample->sample_us!=sample->receive_us))){return Capture_Fail(InstallationCaptureResult_SourceTime);}
    for(i=0U;i<(role==0U?6U:3U);i++){if(!Capture_Finite((double)sample->physical[i])){return Capture_Fail(InstallationCaptureResult_SourceTime);}}
    if((sample->flags&8U)!=0U&&!Capture_Finite((double)sample->temperature)){return Capture_Fail(InstallationCaptureResult_SourceTime);}
    t->native_seen[role]=1U;t->last_native_sequence[role]=sample->sequence;t->native_last[role]=now_us;
    t->native_sample_us[role]=sample->sample_us;
    i=(uint8_t)(t->native_modulo[role]==source->phase);t->native_modulo[role]=(uint16_t)((t->native_modulo[role]+1U)%source->stride);
    if(i==0U){return InstallationCaptureResult_Ok;}
    if(t->pending[role]!=0U){return Capture_Fail(InstallationCaptureResult_Capacity);}
    (void)memcpy(&s_capture.pending[role],sample,sizeof(*sample));t->pending[role]=1U;t->selected_last[role]=now_us;
    return Capture_Pair();
}

InstallationCaptureResult InstallationCapture_SourcePush(uint8_t role,const InstallationCaptureSample *sample,uint64_t now_us)
{
    InstallationCaptureResult result;
    if(role>1U||sample==NULL){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    result=Capture_SourceLocked(role,sample,now_us);Capture_Leave();return result;
}

static uint32_t Capture_Crc(const uint8_t *data)
{
    uint32_t crc=UINT32_MAX;uint16_t i;uint8_t bit;
    for(i=0U;i<154U;i++){crc^=data[i];for(bit=0U;bit<8U;bit++){crc=(crc>>1)^((crc&1U)!=0U?0xEDB88320U:0U);}}
    return ~crc;
}

static uint16_t Event_Text(char *out,uint16_t at,const char *text)
{uint16_t i;for(i=0U;i<64U;i++){if(text[i]=='\0'){return at;}out[at++]=text[i];}return at;}
static uint16_t Event_Hex(char *out,uint16_t at,const uint8_t *value,uint16_t count,uint8_t lower)
{
    const char *alphabet=lower?"0123456789abcdef":"0123456789ABCDEF";uint16_t i;
    for(i=0U;i<count;i++){out[at++]=alphabet[value[i]>>4];out[at++]=alphabet[value[i]&15U];}return at;
}
static uint16_t Event_Number(char *out,uint16_t at,uint32_t value)
{
    uint32_t div=1000000000U;uint8_t i,started=0U;
    for(i=0U;i<10U;i++){uint32_t digit=value/div;if(digit||started||div==1U){out[at++]=(char)('0'+digit);started=1U;}value%=div;div=div>1U?div/10U:1U;}return at;
}

InstallationCaptureResult InstallationCapture_EventPeek(char *scratch,uint16_t capacity,uint16_t *length)
{
    CaptureTransaction *t=&s_capture.transaction.fields;CapturePair *slot;uint16_t n=0U;uint32_t crc;uint8_t i;
    InstallationCaptureResult result=InstallationCaptureResult_Ok;
    if(scratch==NULL||length==NULL||capacity<439U){return InstallationCaptureResult_Invalid;}
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    *length=0U;
    if(t->consumer_active||t->queue_count==0U||
        (t->state!=InstallationCaptureState_Collecting&&t->state!=InstallationCaptureState_Draining)){result=InstallationCaptureResult_Pending;}
    else {
        slot=&s_capture.pairs[t->queue_head];t->active_part=slot->committed;
        if(t->active_part>1U){result=Capture_Fail(InstallationCaptureResult_Failed);}
        else {
            n=Event_Text(scratch,n,t->active_part==0U?"EVENT INSTALL IMU sid=":"EVENT INSTALL MAG sid=");
            n=Event_Hex(scratch,n,t->sid,16U,1U);n=Event_Text(scratch,n," pair=");n=Event_Number(scratch,n,slot->pair);
            n=Event_Text(scratch,n," ctx=B-");n=Event_Hex(scratch,n,s_capture.frozen.fields.binding,15U,1U);
            n=Event_Text(scratch,n," data=");n=Event_Hex(scratch,n,slot->body[t->active_part],154U,0U);
            n=Event_Text(scratch,n," crc32=");crc=Capture_Crc(slot->body[t->active_part]);
            for(i=0U;i<8U;i++){scratch[n++]="0123456789ABCDEF"[(crc>>(28U-4U*i))&15U];}
            scratch[n++]='\r';scratch[n++]='\n';scratch[n]='\0';*length=n;t->consumer_active=1U;
        }
    }
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_EventCommit(uint8_t accepted)
{
    CaptureTransaction *t=&s_capture.transaction.fields;InstallationCaptureResult result=InstallationCaptureResult_Ok;
    if(accepted>1U){return InstallationCaptureResult_Invalid;}if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(!t->consumer_active){result=InstallationCaptureResult_Stale;}
    else {
        t->consumer_active=0U;
        if(accepted!=0U){s_capture.pairs[t->queue_head].committed++;
            if(s_capture.pairs[t->queue_head].committed==2U){t->queue_head=(uint8_t)((t->queue_head+1U)%2U);t->queue_count--;}}
        Capture_Cleanup();
        if(t->state==InstallationCaptureState_Draining&&t->queue_count==0U){t->state=InstallationCaptureState_Complete;}
    }
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_Cancel(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    CaptureTransaction *t=&s_capture.transaction.fields;InstallationCaptureResult result=InstallationCaptureResult_Pending;
    if(rid==0U){return InstallationCaptureResult_Invalid;}if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(!Capture_SidMatches(sid)){result=InstallationCaptureResult_Stale;}
    else if(rid==t->cancel_rid){Capture_Cleanup();result=t->cleanup_complete?InstallationCaptureResult_Cancelled:InstallationCaptureResult_Pending;}
    else if(s_capture.control.fields.resource_owner!=1U){result=InstallationCaptureResult_Stale;}
    else if(rid<=t->rid||now_us<t->now){result=InstallationCaptureResult_Stale;}
    else {t->rid=rid;t->cancel_rid=rid;t->now=now_us;t->last_command_us=now_us;t->state=InstallationCaptureState_Cancelling;t->cleanup_complete=0U;}
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_ProducerStopped(void)
{
    InstallationCaptureResult result=InstallationCaptureResult_Pending;if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    if(s_capture.transaction.fields.state!=InstallationCaptureState_Cancelling){result=InstallationCaptureResult_Stale;}
    else {s_capture.transaction.fields.producer_stopped=1U;Capture_Cleanup();if(s_capture.transaction.fields.cleanup_complete){result=InstallationCaptureResult_Cancelled;}}
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_Release(void)
{
    InstallationCaptureResult result=InstallationCaptureResult_Busy;if(!Capture_Enter()){return result;}
    if(s_capture.transaction.fields.cleanup_complete&&s_capture.transaction.fields.state==InstallationCaptureState_Cancelled){
        s_capture.transaction.fields.state=InstallationCaptureState_Configured;
        s_capture.control.fields.resource_owner=0U;s_capture.control.fields.resource_token=0U;
        if(s_capture.control.fields.snapshot_failed){s_capture.control.fields.configured=0U;s_capture.transaction.fields.state=InstallationCaptureState_Disabled;}
        result=InstallationCaptureResult_Ok;
    }
    Capture_Leave();return result;
}

InstallationCaptureResult InstallationCapture_Revoke(void)
{
    if(!Capture_Enter()){return InstallationCaptureResult_Busy;}
    s_capture.control.fields.snapshot_failed=1U;
    if(s_capture.control.fields.resource_owner!=1U){
        s_capture.control.fields.configured=0U;s_capture.transaction.fields.state=InstallationCaptureState_Disabled;
        Capture_Leave();return InstallationCaptureResult_Ok;
    }
    s_capture.transaction.fields.state=InstallationCaptureState_Cancelling;
    s_capture.transaction.fields.cleanup_complete=0U;s_capture.transaction.fields.reason=InstallationCaptureResult_Stale;
    Capture_Leave();return InstallationCaptureResult_Pending;
}

InstallationCaptureResult InstallationCapture_Number(double value,char output[32],uint16_t *length)
{return CaptureNumber_Write(value,output,length);}
InstallationCaptureResult InstallationCapture_Hash(const uint8_t *data,uint16_t length,uint8_t output[32])
{
    CaptureSha ctx;uint16_t i;if(data==NULL||output==NULL){return InstallationCaptureResult_Invalid;}
    CaptureSha_Init(&ctx);for(i=0U;i<length;i++){CaptureSha_Byte(&ctx,data[i]);}CaptureSha_Finish(&ctx,output);return InstallationCaptureResult_Ok;
}
#ifdef INSTALLATION_CAPTURE_HOST_TEST
void InstallationCapture_TestReset(void)
{ (void)memset(&s_capture,0,sizeof(s_capture)); }
void InstallationCapture_TestCorruptQueue(void)
{ s_capture.transaction.fields.queue_head=3U;s_capture.transaction.fields.consumer_active=1U; }
InstallationCaptureResult InstallationCapture_TestGuard(uint8_t held)
{
    if(held>1U){return InstallationCaptureResult_Invalid;}
    if(held!=0U){return Capture_Enter()?InstallationCaptureResult_Ok:InstallationCaptureResult_Busy;}
    Capture_Leave();return InstallationCaptureResult_Ok;
}
#endif
