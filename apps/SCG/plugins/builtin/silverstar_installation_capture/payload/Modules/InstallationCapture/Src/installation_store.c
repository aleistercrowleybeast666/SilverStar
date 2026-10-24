#include "capture_internal.h"
#include "capture_port.h"
#include "system_installation_store_if.h"
#include "system_installation_calibration_if.h"
#include "silverstar_assert.h"
#include "system_lifecycle.h"
#include "system_time.h"
#include <stddef.h>
#include <string.h>

#define STORE_CANCEL_FLAG 1U
#define STORE_FINAL_FLAG 2U
#define STORE_IDLE_US 30000000ULL

static CaptureStoreContext *Store_Context(CaptureStorage *state)
{return &state->control.fields.coordinator.store;}

static uint32_t Store_U32(const uint8_t *data)
{return (uint32_t)data[0]|((uint32_t)data[1]<<8U)|((uint32_t)data[2]<<16U)|((uint32_t)data[3]<<24U);}

static uint32_t Store_Crc(uint32_t crc,const uint8_t *data,uint16_t length)
{
    uint16_t index;uint8_t bit;
    for(index=0U;index<length;index++){
        crc^=data[index];
        for(bit=0U;bit<8U;bit++){crc=(crc>>1U)^((crc&1U)?0xEDB88320UL:0U);}
    }
    return crc;
}

static SystemInstallationStoreResult Store_Result(const CaptureStoreContext *ctx)
{
    if(ctx->phase==StoreComplete){return SystemInstallationStoreResult_CandidateOnly;}
    if(ctx->phase==StoreCancelled){return SystemInstallationStoreResult_Cancelled;}
    if(ctx->phase==StoreFailed||ctx->phase==StoreUncertain)
    {return (SystemInstallationStoreResult)(ctx->flags>>2U);}
    return (ctx->phase==StoreStaging)?SystemInstallationStoreResult_Ok:SystemInstallationStoreResult_Pending;
}

static void Store_Finish(CaptureStorage *state,SystemInstallationStoreResult result)
{
    CaptureStoreContext *ctx=Store_Context(state);
    SILVERSTAR_ASSERT(result<=SystemInstallationStoreResult_GenerationExhausted&&
        result!=SystemInstallationStoreResult_Pending&&result!=SystemInstallationStoreResult_Busy,
        SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    ctx->flags=(uint8_t)((ctx->flags&3U)|((uint8_t)result<<2U));
    ctx->phase=(uint8_t)((result==SystemInstallationStoreResult_CandidateOnly)?StoreComplete:
        ((result==SystemInstallationStoreResult_Cancelled)?StoreCancelled:
        ((result==SystemInstallationStoreResult_CleanupUnconfirmed)?StoreUncertain:StoreFailed)));
    /* An uncertain media close/commit retains the exclusive lease. */
    if(ctx->phase!=StoreUncertain){SystemInstallationCapture_OperationEnd(SystemInstallationOperation_Store);}
}

static uint8_t Store_Session(CaptureStorage *state,const uint8_t sid[16])
{return (uint8_t)(sid!=NULL&&memcmp(sid,state->transaction.fields.sid,16U)==0);}

static uint8_t Store_Io(uint8_t phase)
{return (uint8_t)(phase==StoreOpenIo||phase==StoreWriteIo||phase==StoreReadTempIo||
    phase==StoreReadFinalIo||phase==StorePublishIo||phase==StoreCommitIo);}

static uint8_t Store_Touch(CaptureStorage *state,uint64_t now_us)
{
    if(now_us<state->transaction.fields.last_command_us){return 0U;}
    state->transaction.fields.last_command_us=now_us;return 1U;
}

SystemInstallationStoreResult SystemInstallationStore_Begin(const uint8_t sid[16],uint32_t rid,
    uint32_t expected_generation,uint32_t length,const uint8_t sha256[32],const uint8_t binding[32],uint64_t now_us)
{
    CaptureStorage *state;CaptureStoreContext *ctx;SystemInstallationStoreResult result;uint32_t token=0U;
    if(sid==NULL||sha256==NULL||binding==NULL||rid==0U||rid>=UINT32_MAX-1U||length<64U||
        length>SYSTEM_INSTALLATION_STORE_MAX_BYTES||expected_generation==UINT32_MAX){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    if(!state->control.fields.enabled||!state->control.fields.configured||!state->frozen.fields.snapshot.offline)
    {result=SystemInstallationStoreResult_Unsupported;}
    else if(state->transaction.fields.rid==0U||!Store_Session(state,sid)||
        now_us<state->transaction.fields.last_command_us){result=SystemInstallationStoreResult_Stale;}
    else if(CapturePort_WordRead(&state->frozen.dependency_generation)==UINT32_MAX||
        memcmp(binding,state->frozen.fields.binding,32U)!=0){result=SystemInstallationStoreResult_DependencyChanged;}
    else if(ctx->request_id==rid&&ctx->phase<=StoreStaging&&ctx->chunk_length==0U&&
        ctx->total_bytes==length&&ctx->expected_generation==expected_generation&&
        memcmp(ctx->object_sha256,sha256,32U)==0)
    {result=Store_Result(ctx);CaptureState_Leave();return result;}
    else if(ctx->request_id==rid){result=SystemInstallationStoreResult_InvalidArgument;}
    else if(state->control.fields.resource_owner!=0U){result=SystemInstallationStoreResult_Busy;}
    else if(rid<=ctx->request_id||rid<=state->transaction.fields.cancel_rid){result=SystemInstallationStoreResult_Stale;}
    else {result=SystemInstallationStoreResult_Ok;}
    if(result!=SystemInstallationStoreResult_Ok){CaptureState_Leave();return result;}
    if(CaptureState_Claim(11U,&token)!=InstallationCaptureResult_Ok)
    {CaptureState_Leave();return SystemInstallationStoreResult_GenerationExhausted;}
    {
        uint8_t published=CapturePort_WordPublish(&state->frozen.store_token,token);
        SILVERSTAR_ASSERT(published!=0U,SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    }
    (void)memset(ctx,0,sizeof(*ctx));ctx->request_id=rid;ctx->expected_generation=expected_generation;
    ctx->total_bytes=length;ctx->phase=StoreOpenQueued;(void)memcpy(ctx->object_sha256,sha256,32U);
    state->transaction.fields.cancel_rid=0U;(void)Store_Touch(state,now_us);
    CaptureState_Leave();return SystemInstallationStoreResult_Pending;
}

SystemInstallationStoreResult SystemInstallationStore_Write(const uint8_t sid[16],uint32_t rid,
    uint32_t offset,const uint8_t *data,uint16_t length,uint64_t now_us)
{
    CaptureStorage *state;CaptureStoreContext *ctx;SystemInstallationStoreResult result;
    if(data==NULL||length==0U||length>64U||offset>SYSTEM_INSTALLATION_STORE_MAX_BYTES||
        rid==0U||rid>=UINT32_MAX-1U){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    if(!Store_Session(state,sid)||!Store_Touch(state,now_us)){result=SystemInstallationStoreResult_Stale;}
    else if(rid==ctx->request_id&&length==ctx->chunk_length&&
        memcmp(data,state->frozen.store_chunk,length)==0&&
        (offset==ctx->offset||(ctx->phase==StoreStaging&&offset+length==ctx->offset)))
    {result=Store_Result(ctx);}
    else if(rid<=ctx->request_id){result=SystemInstallationStoreResult_Stale;}
    else if(ctx->phase!=StoreStaging){result=SystemInstallationStoreResult_Busy;}
    else if((ctx->flags&STORE_FINAL_FLAG)!=0U||offset!=ctx->offset||offset>ctx->total_bytes||
        length>ctx->total_bytes-offset){result=SystemInstallationStoreResult_InvalidArgument;}
    else {
        ctx->request_id=rid;ctx->chunk_length=length;ctx->phase=StoreWriteQueued;
        (void)memcpy(state->frozen.store_chunk,data,length);result=SystemInstallationStoreResult_Pending;
    }
    CaptureState_Leave();return result;
}

SystemInstallationStoreResult SystemInstallationStore_Verify(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    CaptureStorage *state;CaptureStoreContext *ctx;SystemInstallationStoreResult result;
    if(rid==0U||rid>=UINT32_MAX-1U){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    if(!Store_Session(state,sid)||!Store_Touch(state,now_us)||rid<ctx->request_id){result=SystemInstallationStoreResult_Stale;}
    else if(rid==ctx->request_id){result=(ctx->phase>=StoreVerifyTemp)?Store_Result(ctx):SystemInstallationStoreResult_InvalidArgument;}
    else if(ctx->phase!=StoreStaging||ctx->offset!=ctx->total_bytes){result=SystemInstallationStoreResult_Busy;}
    else {
        ctx->request_id=rid;ctx->offset=0U;ctx->crc=UINT32_MAX;
        ctx->phase=(uint8_t)((ctx->flags&STORE_FINAL_FLAG)?StoreVerifyFinal:StoreVerifyTemp);
        CaptureSha_Init(&state->sha.fields);result=SystemInstallationStoreResult_Pending;
    }
    CaptureState_Leave();return result;
}

SystemInstallationStoreResult SystemInstallationStore_Cancel(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    CaptureStorage *state;CaptureStoreContext *ctx;SystemInstallationStoreResult result;
    if(rid==0U||rid>=UINT32_MAX-1U){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    if(!Store_Session(state,sid)||rid<=ctx->request_id||!Store_Touch(state,now_us)||
        rid<state->transaction.fields.cancel_rid)
    {result=SystemInstallationStoreResult_Stale;}
    else if(ctx->phase>=StoreComplete){result=Store_Result(ctx);}
    else {
        state->transaction.fields.cancel_rid=rid;ctx->flags|=STORE_CANCEL_FLAG;
        if(!Store_Io(ctx->phase)){Store_Finish(state,SystemInstallationStoreResult_Cancelled);}
        result=(ctx->phase==StoreCancelled)?SystemInstallationStoreResult_Cancelled:SystemInstallationStoreResult_Pending;
    }
    CaptureState_Leave();return result;
}

SystemInstallationStoreResult SystemInstallationStore_Status(const uint8_t sid[16],uint32_t rid,
    uint64_t now_us,SystemInstallationStoreStatus *status)
{
    CaptureStorage *state;CaptureStoreContext *ctx;SystemInstallationStoreResult result;
    if(status==NULL){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    if(!Store_Session(state,sid)||(rid!=ctx->request_id&&rid!=state->transaction.fields.cancel_rid)||
        !Store_Touch(state,now_us)){result=SystemInstallationStoreResult_Stale;}
    else {
        result=Store_Result(ctx);status->request_id=rid;status->completed_bytes=ctx->offset;
        status->total_bytes=ctx->total_bytes;
        status->generation=ctx->expected_generation+(uint32_t)(ctx->phase==StoreComplete);
        status->result=result;status->candidate_only=1U;
        status->cleanup_complete=(uint8_t)(ctx->phase>=StoreComplete&&state->control.fields.resource_owner!=11U);
    }
    CaptureState_Leave();return result;
}

SystemInstallationStoreResult SystemInstallationStore_WorkTake(uint64_t now_us,SystemInstallationStoreWork *work)
{
    CaptureStorage *state;CaptureStoreContext *ctx;SystemInstallationStoreResult result=SystemInstallationStoreResult_Pending;
    if(work==NULL){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    SILVERSTAR_ASSERT(ctx->phase<=StoreUncertain,SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if(state->control.fields.resource_owner!=11U||ctx->phase>=StoreComplete||Store_Io(ctx->phase))
    {CaptureState_Leave();return SystemInstallationStoreResult_Busy;}
    if(now_us>=state->transaction.fields.last_command_us&&now_us-state->transaction.fields.last_command_us>=STORE_IDLE_US)
    {ctx->flags|=STORE_CANCEL_FLAG;}
    if((ctx->flags&STORE_CANCEL_FLAG)!=0U){Store_Finish(state,SystemInstallationStoreResult_Cancelled);result=Store_Result(ctx);}
    else if(CapturePort_WordRead(&state->frozen.dependency_generation)==UINT32_MAX)
    {Store_Finish(state,SystemInstallationStoreResult_DependencyChanged);result=Store_Result(ctx);}
    else {
        work->request_id=ctx->request_id;work->token=CapturePort_WordRead(&state->frozen.store_token);
        work->expected_generation=ctx->expected_generation;work->total_bytes=ctx->total_bytes;
        work->offset=ctx->offset;work->length=ctx->chunk_length;
        work->final_blob=(uint8_t)((ctx->flags&STORE_FINAL_FLAG)!=0U);
        (void)memcpy(work->object_sha256,ctx->object_sha256,32U);
        (void)memcpy(work->binding_sha256,state->frozen.fields.binding,32U);
        (void)memcpy(work->data,state->frozen.store_chunk,64U);
        switch(ctx->phase){
            case StoreOpenQueued:work->action=SystemInstallationStoreAction_Open;ctx->phase=StoreOpenIo;break;
            case StoreWriteQueued:work->action=SystemInstallationStoreAction_Write;ctx->phase=StoreWriteIo;break;
            case StoreVerifyTemp:case StoreVerifyFinal:
                work->action=SystemInstallationStoreAction_Read;work->length=(uint16_t)((ctx->total_bytes-ctx->offset>64U)?64U:ctx->total_bytes-ctx->offset);
                ctx->phase=(uint8_t)(work->final_blob?StoreReadFinalIo:StoreReadTempIo);break;
            case StorePublishQueued:work->action=SystemInstallationStoreAction_Publish;ctx->phase=StorePublishIo;break;
            case StoreCommitQueued:work->action=SystemInstallationStoreAction_Commit;ctx->phase=StoreCommitIo;break;
            default:result=SystemInstallationStoreResult_Busy;break;
        }
    }
    CaptureState_Leave();return result;
}

static uint8_t Store_Envelope(CaptureStorage *state,const uint8_t data[64])
{
    const InstallationCaptureSnapshot *snapshot=&state->frozen.fields.snapshot;
    uint16_t descriptor=(uint16_t)data[8]|((uint16_t)data[9]<<8U);
    uint16_t physical=(uint16_t)data[10]|((uint16_t)data[11]<<8U);
    if(memcmp(data,"SSIC",4U)!=0||data[4]!=SYSTEM_INSTALLATION_CAL_SCHEMA||data[5]!=2U||data[6]!=1U||
        data[7]!=SYSTEM_INSTALLATION_CAL_NAMED_SNAPSHOT_COORDINATES||data[13]!=0U||data[14]!=0U||data[15]!=0U||
        descriptor!=snapshot->sources[0].descriptor||physical!=snapshot->sources[0].physical||
        data[12]!=snapshot->sources[0].instance||Store_U32(&data[16])!=snapshot->configuration||
        Store_U32(&data[20])!=0U||Store_U32(&data[24])!=0U||Store_U32(&data[28])!=0U||
        Store_U32(&data[32])!=Store_Context(state)->total_bytes-40U){return 0U;}
    state->frozen.body_crc=Store_U32(&data[36]);return 1U;
}

static void Store_ReadComplete(CaptureStorage *state,const SystemInstallationStoreWork *work)
{
    CaptureStoreContext *ctx=Store_Context(state);uint16_t index;uint8_t digest[32];
    SILVERSTAR_ASSERT(ctx->offset<=ctx->total_bytes&&work->length<=64U&&work->length<=ctx->total_bytes-ctx->offset,
        SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if(ctx->offset==0U&&!Store_Envelope(state,work->data))
    {Store_Finish(state,SystemInstallationStoreResult_IntegrityError);return;}
    for(index=0U;index<work->length;index++){
        CaptureSha_Byte(&state->sha.fields,work->data[index]);
        if(ctx->offset+index>=40U){ctx->crc=Store_Crc(ctx->crc,&work->data[index],1U);}
    }
    ctx->offset+=work->length;
    if(ctx->offset<ctx->total_bytes){ctx->phase=(uint8_t)(work->final_blob?StoreVerifyFinal:StoreVerifyTemp);return;}
    CaptureSha_Finish(&state->sha.fields,digest);
    if(memcmp(digest,ctx->object_sha256,32U)!=0||~ctx->crc!=state->frozen.body_crc)
    {Store_Finish(state,SystemInstallationStoreResult_IntegrityError);return;}
    ctx->phase=(uint8_t)(work->final_blob?StoreCommitQueued:StorePublishQueued);
}

static uint8_t Store_WorkMatches(const CaptureStoreContext *ctx,const SystemInstallationStoreWork *work)
{
    switch(work->action){
        case SystemInstallationStoreAction_Open:return (uint8_t)(ctx->phase==StoreOpenIo);
        case SystemInstallationStoreAction_Write:return (uint8_t)(ctx->phase==StoreWriteIo&&ctx->offset==work->offset);
        case SystemInstallationStoreAction_Read:return (uint8_t)(ctx->offset==work->offset&&
            ctx->phase==(work->final_blob?StoreReadFinalIo:StoreReadTempIo));
        case SystemInstallationStoreAction_Publish:return (uint8_t)(ctx->phase==StorePublishIo);
        case SystemInstallationStoreAction_Commit:return (uint8_t)(ctx->phase==StoreCommitIo);
        default:return 0U;
    }
}

SystemInstallationStoreResult SystemInstallationStore_WorkComplete(const SystemInstallationStoreWork *work,
    SystemInstallationStoreResult result,uint32_t progress,uint32_t generation,uint64_t now_us)
{
    CaptureStorage *state;CaptureStoreContext *ctx;
    if(work==NULL){return SystemInstallationStoreResult_InvalidArgument;}
    if(!CaptureState_Enter()){return SystemInstallationStoreResult_Busy;}
    state=CaptureState_Get();ctx=Store_Context(state);
    if(work->request_id!=ctx->request_id||work->token!=CapturePort_WordRead(&state->frozen.store_token)||!Store_WorkMatches(ctx,work))
    {CaptureState_Leave();return SystemInstallationStoreResult_Stale;}
    if(now_us>=state->transaction.fields.last_command_us&&now_us-state->transaction.fields.last_command_us>=STORE_IDLE_US)
    {ctx->flags|=STORE_CANCEL_FLAG;}
    if(result!=SystemInstallationStoreResult_Ok){Store_Finish(state,result);}
    /* A successful head CAS has published and cannot be cancelled by a
     * command/lease expiry observed after I/O. Publish its actual generation;
     * this remains a stored candidate, never an applied runtime correction. */
    else if((ctx->flags&STORE_CANCEL_FLAG)!=0U&&work->action!=SystemInstallationStoreAction_Commit)
    {Store_Finish(state,SystemInstallationStoreResult_Cancelled);}
    else if(CapturePort_WordRead(&state->frozen.dependency_generation)==UINT32_MAX&&
        work->action!=SystemInstallationStoreAction_Commit)
    {Store_Finish(state,SystemInstallationStoreResult_DependencyChanged);}
    else {
        switch(work->action){
            case SystemInstallationStoreAction_Open:
                if(progress>ctx->total_bytes){Store_Finish(state,SystemInstallationStoreResult_IntegrityError);break;}
                ctx->offset=progress;ctx->flags|=(uint8_t)(work->final_blob?STORE_FINAL_FLAG:0U);ctx->phase=StoreStaging;break;
            case SystemInstallationStoreAction_Write:
                if(progress!=ctx->offset+ctx->chunk_length){Store_Finish(state,SystemInstallationStoreResult_IntegrityError);break;}
                ctx->offset=progress;ctx->phase=StoreStaging;break;
            case SystemInstallationStoreAction_Read:Store_ReadComplete(state,work);break;
            case SystemInstallationStoreAction_Publish:
                ctx->flags|=STORE_FINAL_FLAG;ctx->offset=0U;ctx->crc=UINT32_MAX;
                CaptureSha_Init(&state->sha.fields);ctx->phase=StoreVerifyFinal;break;
            case SystemInstallationStoreAction_Commit:
                Store_Finish(state,(generation==ctx->expected_generation+1U)?
                    SystemInstallationStoreResult_CandidateOnly:SystemInstallationStoreResult_DependencyChanged);break;
            default:Store_Finish(state,SystemInstallationStoreResult_InvalidArgument);break;
        }
    }
    CaptureState_Leave();return SystemInstallationStoreResult_Ok;
}

void SystemInstallationStore_CompletionLost(void)
{InstallationCapture_SourceLost();}

/* Logger is the sole caller. No filesystem work executes in the Serial task.
 * Four nonblocking completion attempts cover transient producer guard use;
 * an unacknowledged I/O completion is latched uncertain, never released. */
void SystemInstallationStore_Service(void)
{
    SystemInstallationStoreWork work;
    SystemInstallationStoreResult result,completion=SystemInstallationStoreResult_Busy;
    uint32_t progress=0U,generation=0U;uint8_t attempt;
    if(SystemInstallationStore_WorkTake(SystemTime_GetMonotonicUs(),&work)!=SystemInstallationStoreResult_Pending){return;}
    if(SystemLifecycle_MaintenanceGet()!=SystemMaintenanceState_Ready)
    {result=SystemInstallationStoreResult_StorageError;}
    else {result=SystemInstallationStoreStorage_Execute(&work,&progress,&generation);}
    for(attempt=0U;attempt<4U;attempt++){
        completion=SystemInstallationStore_WorkComplete(&work,result,progress,generation,SystemTime_GetMonotonicUs());
        if(completion!=SystemInstallationStoreResult_Busy){break;}
    }
    if(completion==SystemInstallationStoreResult_Busy){SystemInstallationStore_CompletionLost();}
    SILVERSTAR_ASSERT(completion==SystemInstallationStoreResult_Ok||completion==SystemInstallationStoreResult_Busy||
        completion==SystemInstallationStoreResult_Stale,SILVERSTAR_ASSERT_MODULE_MODULES,SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
}

const char *SystemInstallationStore_ResultText(SystemInstallationStoreResult result)
{
    switch(result){
        case SystemInstallationStoreResult_Ok:return "OK";
        case SystemInstallationStoreResult_Pending:return "PENDING";
        case SystemInstallationStoreResult_Busy:return "BUSY";
        case SystemInstallationStoreResult_InvalidArgument:return "INVALID_ARGUMENT";
        case SystemInstallationStoreResult_Stale:return "STALE_SESSION_OR_REQUEST";
        case SystemInstallationStoreResult_DependencyChanged:return "DEPENDENCY_CHANGED";
        case SystemInstallationStoreResult_IntegrityError:return "INTEGRITY_ERROR";
        case SystemInstallationStoreResult_StorageError:return "STORAGE_ERROR";
        case SystemInstallationStoreResult_CleanupUnconfirmed:return "CLEANUP_UNCONFIRMED_REBOOT_REQUIRED";
        case SystemInstallationStoreResult_Cancelled:return "CANCELLED";
        case SystemInstallationStoreResult_CandidateOnly:return "VERIFIED_BYTES_CANDIDATE_ONLY_NOT_APPLIED";
        case SystemInstallationStoreResult_Unsupported:return "REAL_STORE_DISABLED_SOURCE_QUALIFICATION";
        case SystemInstallationStoreResult_GenerationExhausted:return "GENERATION_EXHAUSTED";
        default:return "UNKNOWN";
    }
}
