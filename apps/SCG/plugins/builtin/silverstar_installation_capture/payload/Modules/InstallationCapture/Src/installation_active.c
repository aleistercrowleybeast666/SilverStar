#include "system_installation_active_if.h"
#include "system_calibration.h"
#include "system_mag_calibration.h"
#include "system_descriptor_if.h"
#include "system_lifecycle.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "capture_internal.h"
#include "silverstar_assert.h"
#include <math.h>
#include <string.h>

_Static_assert(sizeof(CapturePair)>=SYSTEM_INSTALLATION_ACTIVE_BYTES,
    "Stopped capture pair must hold the complete active upload");

/* Persistent active state is CPU-only. Upload bytes borrow the stopped
 * capture queue while the Calibration lease excludes every other writer. */
static PLATFORM_CPU_FAST_BSS uint8_t s_active_record[SYSTEM_INSTALLATION_ACTIVE_BYTES];
static uint8_t s_sid[16],s_expected_sha[32];
static uint32_t s_rid;
static uint32_t s_expected_crc;
static uint16_t s_offset;
static uint8_t s_upload;
static uint64_t s_last_command_us;
static SystemInstallationActiveStatus s_status;
static uint32_t s_dependency_revision;
static uint8_t s_dependency_invalid;
static uint32_t s_active_lease;
static uint8_t s_release_pending;

/* Owner 10 has no generic continuation slot. Only this transaction possesses
 * its exact token; ordinary CAL/ALIGN/START and candidate-store cannot adopt it. */
static uint8_t ActiveLease_Claim(void)
{
    InstallationCaptureResult result;CaptureStorage *state;
    if(s_active_lease!=0U||!CaptureState_Enter()){return 0U;}
    state=CaptureState_Get();state->control.fields.enabled=1U;
    result=CaptureState_Claim(10U,&s_active_lease);CaptureState_Leave();
    return (uint8_t)(result==InstallationCaptureResult_Ok);
}
static uint8_t ActiveLease_Release(void)
{
    InstallationCaptureResult result;
    if(s_active_lease==0U){return 1U;}
    result=InstallationCapture_ResourceRelease(10U,s_active_lease);
    if(result==InstallationCaptureResult_Busy){s_release_pending=1U;return 0U;}
    SILVERSTAR_ASSERT(result==InstallationCaptureResult_Ok,SILVERSTAR_ASSERT_MODULE_MODULES,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    s_active_lease=0U;s_release_pending=0U;return 1U;
}
uint8_t SystemInstallationActive_ApplyOwnerHeld(uint32_t token)
{
    CaptureStorage *state;uint8_t held;
    if(token==0U||token!=s_active_lease||!s_status.pending||s_status.request_id!=0U||!CaptureState_Enter()){return 0U;}
    state=CaptureState_Get();held=(uint8_t)(state->control.fields.resource_owner==10U&&state->control.fields.resource_token==token);
    CaptureState_Leave();return held;
}

static uint32_t Active_U32(const uint8_t *p)
{return (uint32_t)p[0]|((uint32_t)p[1]<<8U)|((uint32_t)p[2]<<16U)|((uint32_t)p[3]<<24U);}
static float Active_F32(const uint8_t *p)
{uint32_t bits=Active_U32(p);float value;(void)memcpy(&value,&bits,4U);return value;}
static uint32_t Active_Crc(const uint8_t *p,uint16_t length)
{
    uint32_t crc=UINT32_MAX;uint16_t i;uint8_t bit;
    for(i=0U;i<length;i++){crc^=p[i];for(bit=0U;bit<8U;bit++)
        {crc=(crc>>1U)^((crc&1U)?0xEDB88320UL:0U);}}
    return ~crc;
}
static uint8_t Active_Rotation(const uint8_t *p)
{
    uint8_t i,j,k;float m[9],det;
    for(i=0U;i<9U;i++){m[i]=Active_F32(&p[4U*i]);if(!isfinite(m[i])){return 0U;}}
    for(i=0U;i<3U;i++){for(j=0U;j<3U;j++){
        float dot=0.0f;for(k=0U;k<3U;k++){dot+=m[3U*i+k]*m[3U*j+k];}
        if(fabsf(dot-((i==j)?1.0f:0.0f))>0.0005f){return 0U;}
    }}
    det=m[0]*(m[4]*m[8]-m[5]*m[7])-m[1]*(m[3]*m[8]-m[5]*m[6])+m[2]*(m[3]*m[7]-m[4]*m[6]);
    return (uint8_t)(fabsf(det-1.0f)<0.0005f);
}
static void Active_IdentityRead(const uint8_t *record,SystemCalibrationBaselineIdentity *identity)
{
    identity->configuration_digest=Active_U32(&record[16]);
    identity->driver_hash=Active_U32(&record[20]);identity->model_hash=Active_U32(&record[24]);
    identity->descriptor_id=(uint16_t)(record[8]|((uint16_t)record[9]<<8U));
    identity->physical_device_id=(uint16_t)(record[10]|((uint16_t)record[11]<<8U));identity->instance_id=record[12];
}
static uint8_t Active_DependenciesMatch(const uint8_t *record)
{
    SystemDeviceDescriptor descriptor;SystemMagCalibrationSnapshot mag;float R_GA[9];uint8_t i;
    if(!SystemInstallationCapture_ActiveQualifiedGet(R_GA)){return 0U;}
    if(SystemDescriptor_ConfigDigestGet()!=Active_U32(&record[16])||
        SystemDescriptor_DeviceFind(SYSTEM_DEVICE_CLASS_MAGNETOMETER,record[36],&descriptor)!=SYSTEM_DEVICE_OK||
        SystemMagCalibration_SnapshotGet(record[36],&mag)!=SystemMagCalibrationResult_Ok){return 0U;}
    if(descriptor.descriptor_id!=(uint16_t)(record[32]|((uint16_t)record[33]<<8U))||
        descriptor.physical_device_id!=(uint16_t)(record[34]|((uint16_t)record[35]<<8U))||
        descriptor.driver_name_hash!=Active_U32(&record[40])||descriptor.model_name_hash!=Active_U32(&record[44])||
        mag.status.generation!=Active_U32(&record[48])||mag.status.intrinsic_crc!=Active_U32(&record[28])||
        !mag.status.active||!mag.status.saved||mag.status.save_pending||mag.status.save_failed){return 0U;}
    for(i=0U;i<9U;i++){
        /* This first runtime supports provider accel/gyro already expressed
         * in the same configured body frame. Unknown is never identity. */
        if(!isfinite(R_GA[i])||fabsf(R_GA[i]-Active_F32(&record[152U+4U*i]))>0.00001f||
            fabsf(R_GA[i]-((i%4U==0U)?1.0f:0.0f))>0.00001f){return 0U;}
    }
    return 1U;
}
static SystemInstallationActiveResult Active_Validate(const uint8_t *record,
    SystemCalibrationBaselineIdentity *identity,SystemCalibrationImuCorrection *correction)
{
    static const uint8_t domain[]="SSIC-ACTIVE-STABLE-v1";
    CaptureSha hash;uint8_t digest[32],i;uint32_t evidence=0U;
    if(memcmp(record,"SSIC",4U)!=0||record[4]!=1U||record[5]!=3U||record[6]!=1U||record[7]!=3U||
        record[13]!=1U||record[14]!=1U||record[15]!=0U||record[37]!=0U||record[38]!=0U||record[39]!=0U||
        Active_Crc(record,224U)!=Active_U32(&record[224])||!Active_Rotation(&record[152])||!Active_Rotation(&record[188]))
    {return SystemInstallationActiveResult_Invalid;}
    CaptureSha_Init(&hash);
    for(i=0U;i<sizeof(domain);i++){CaptureSha_Byte(&hash,domain[i]);}
    for(i=0U;i<52U;i++){CaptureSha_Byte(&hash,record[i]);}
    for(i=152U;i<188U;i++){CaptureSha_Byte(&hash,record[i]);}
    CaptureSha_Finish(&hash,digest);
    if(memcmp(digest,&record[84],32U)!=0){return SystemInstallationActiveResult_Invalid;}
    for(i=52U;i<84U;i++){evidence|=record[i];}
    if(evidence==0U){return SystemInstallationActiveResult_Invalid;}
    (void)memset(correction,0,sizeof(*correction));correction->ready=1U;
    for(i=0U;i<3U;i++){
        correction->accel_bias_mps2[i]=Active_F32(&record[116U+4U*i]);correction->accel_scale[i]=Active_F32(&record[128U+4U*i]);
        correction->gyro_bias_radps[i]=Active_F32(&record[140U+4U*i]);correction->gyro_scale[i]=1.0f;
    }
    Active_IdentityRead(record,identity);
    return Active_DependenciesMatch(record)?SystemInstallationActiveResult_Ok:SystemInstallationActiveResult_DependencyChanged;
}
static uint8_t Active_Context(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    return (uint8_t)(sid!=NULL&&memcmp(sid,s_sid,16U)==0&&rid>=s_rid&&rid<UINT32_MAX&&
        now_us>=s_last_command_us&&now_us-s_last_command_us<=30000000ULL);
}
SystemInstallationActiveResult SystemInstallationActive_UploadBegin(
    const uint8_t sid[16],uint32_t rid,uint32_t crc,const uint8_t sha256[32],uint64_t now_us)
{
    float R_GA[9];CaptureStorage *state;uint8_t index,nonzero=0U;
    if(sid==NULL||sha256==NULL||rid==0U||rid==UINT32_MAX){return SystemInstallationActiveResult_Invalid;}
    for(index=0U;index<16U;index++){nonzero|=sid[index];}
    if(nonzero==0U){return SystemInstallationActiveResult_Invalid;}
    if(!SystemInstallationCapture_ActiveQualifiedGet(R_GA)){return SystemInstallationActiveResult_Unsupported;}
    if(s_upload&&rid==s_rid&&s_offset==0U&&Active_Context(sid,rid,now_us)&&
        crc==s_expected_crc&&memcmp(sha256,s_expected_sha,32U)==0){return SystemInstallationActiveResult_Ok;}
    if(s_upload||s_status.pending||SystemLifecycle_MaintenanceGet()!=SystemMaintenanceState_Ready)
    {return SystemInstallationActiveResult_Busy;}
    if(!ActiveLease_Claim())
    {return SystemInstallationActiveResult_Busy;}
    if(!CaptureState_Enter()){
        (void)ActiveLease_Release();return SystemInstallationActiveResult_Busy;
    }
    state=CaptureState_Get();
    if(state->transaction.fields.consumer_active||state->transaction.fields.queue_count!=0U||
        (!state->transaction.fields.producer_stopped&&state->transaction.fields.state>InstallationCaptureState_Configured)){
        CaptureState_Leave();(void)ActiveLease_Release();
        return SystemInstallationActiveResult_Busy;
    }
    (void)memset(&state->pairs[0],0,sizeof(state->pairs[0]));CaptureState_Leave();
    (void)memcpy(s_sid,sid,16U);(void)memcpy(s_expected_sha,sha256,32U);
    s_rid=rid;s_offset=0U;s_upload=1U;s_last_command_us=now_us;s_expected_crc=crc;
    return SystemInstallationActiveResult_Ok;
}
SystemInstallationActiveResult SystemInstallationActive_UploadWrite(const uint8_t sid[16],uint32_t rid,
    uint16_t offset,const uint8_t *bytes,uint16_t length,uint64_t now_us)
{
    CaptureStorage *state;uint8_t *destination;
    if(bytes==NULL||length==0U||length>48U||offset>SYSTEM_INSTALLATION_ACTIVE_BYTES||
        length>SYSTEM_INSTALLATION_ACTIVE_BYTES-offset){return SystemInstallationActiveResult_Invalid;}
    if(!s_upload||!Active_Context(sid,rid,now_us)){return SystemInstallationActiveResult_Stale;}
    if(!CaptureState_Enter()){return SystemInstallationActiveResult_Busy;}
    state=CaptureState_Get();destination=(uint8_t *)&state->pairs[0];
    if(rid==s_rid&&offset+length==s_offset&&memcmp(&destination[offset],bytes,length)==0){
        CaptureState_Leave();return SystemInstallationActiveResult_Ok;
    }
    if(rid<=s_rid||offset!=s_offset){CaptureState_Leave();return SystemInstallationActiveResult_Stale;}
    (void)memcpy(&destination[offset],bytes,length);s_offset=(uint16_t)(offset+length);
    s_rid=rid;s_last_command_us=now_us;CaptureState_Leave();return SystemInstallationActiveResult_Ok;
}
SystemInstallationActiveResult SystemInstallationActive_Apply(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    uint8_t packet[SYSTEM_INSTALLATION_ACTIVE_BYTES],sha[32];CaptureStorage *state;
    SystemCalibrationBaselineIdentity identity;SystemCalibrationImuCorrection correction;
    SystemInstallationActiveResult result;uint32_t generation,lock,revision;SystemCalibrationBaselineResult applied;
    if(!Active_Context(sid,rid,now_us)){return SystemInstallationActiveResult_Stale;}
    if(!s_upload&&rid==s_rid&&s_status.active&&!s_dependency_invalid){return SystemInstallationActiveResult_Ok;}
    if(!s_upload||s_offset!=SYSTEM_INSTALLATION_ACTIVE_BYTES||rid<=s_rid){return SystemInstallationActiveResult_NotReady;}
    if(!CaptureState_Enter()){return SystemInstallationActiveResult_Busy;}
    state=CaptureState_Get();(void)memcpy(packet,&state->pairs[0],sizeof(packet));CaptureState_Leave();
    if(Active_Crc(packet,sizeof(packet))!=s_expected_crc||
        InstallationCapture_Hash(packet,sizeof(packet),sha)!=InstallationCaptureResult_Ok||memcmp(sha,s_expected_sha,32U)!=0)
    {return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();revision=s_dependency_revision;PlatformCritical_Exit(lock);
    if(revision==UINT32_MAX){return SystemInstallationActiveResult_NotReady;}
    result=Active_Validate(packet,&identity,&correction);if(result!=SystemInstallationActiveResult_Ok){return result;}
    lock=PlatformCritical_Enter();s_status.pending=1U;s_status.request_id=0U;
    s_status.result=SystemInstallationActiveResult_Busy;generation=s_status.applied_generation;PlatformCritical_Exit(lock);
    applied=SystemCalibration_BaselineApplyOwned(&identity,&correction,generation,&generation,s_active_lease);
    if(applied!=SystemCalibrationBaselineResult_Ok){
        lock=PlatformCritical_Enter();s_status.pending=0U;PlatformCritical_Exit(lock);
        return SystemInstallationActiveResult_Busy;
    }
    lock=PlatformCritical_Enter();
    /* A baseline has already been published. Preserve its identity even on
     * a dependency race so neither Snapshot nor MAG can fall back to absent. */
    (void)memcpy(s_active_record,packet,sizeof(packet));
    s_status.applied_generation=generation;s_status.record_crc=Active_U32(&packet[224]);
    s_status.active=1U;s_status.saved=0U;s_status.loaded=0U;s_status.pending=0U;
    s_upload=0U;s_rid=rid;s_last_command_us=now_us;
    if(revision!=s_dependency_revision){
        s_dependency_invalid=1U;
        s_status.result=SystemInstallationActiveResult_DependencyChanged;PlatformCritical_Exit(lock);
        (void)ActiveLease_Release();
        return SystemInstallationActiveResult_DependencyChanged;
    }
    s_status.result=SystemInstallationActiveResult_Ok;s_dependency_invalid=0U;PlatformCritical_Exit(lock);
    (void)ActiveLease_Release();return SystemInstallationActiveResult_Ok;
}
SystemInstallationActiveResult SystemInstallationActive_Cancel(const uint8_t sid[16],uint32_t rid)
{
    uint8_t release;PlatformCriticalState lock=PlatformCritical_Enter();
    if(sid==NULL||memcmp(sid,s_sid,16U)!=0||rid<s_rid){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Stale;}
    if(s_status.pending){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Pending;}
    release=s_upload;s_upload=0U;s_rid=rid;PlatformCritical_Exit(lock);
    if((release||s_release_pending)&&!ActiveLease_Release()){return SystemInstallationActiveResult_Pending;}
    return SystemInstallationActiveResult_Ok;
}
SystemInstallationActiveResult SystemInstallationActive_StatusGet(SystemInstallationActiveStatus *status)
{
    PlatformCriticalState lock;if(status==NULL){return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();*status=s_status;
    status->valid=(uint8_t)(s_status.active&&!s_status.pending&&!s_dependency_invalid);
    PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Ok;
}
SystemInstallationActiveResult SystemInstallationActive_RecordGet(uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES])
{
    PlatformCriticalState lock;if(record==NULL){return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();if(!s_status.active||s_status.pending||s_dependency_invalid){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_NotReady;}
    (void)memcpy(record,s_active_record,SYSTEM_INSTALLATION_ACTIVE_BYTES);PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Ok;
}
uint8_t SystemInstallationActive_RuntimeReady(uint32_t generation)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint8_t ready=(uint8_t)(s_status.active&&!s_status.pending&&!s_dependency_invalid&&generation==s_status.applied_generation);
    PlatformCritical_Exit(lock);return ready;
}
SystemInstallationActiveResult SystemInstallationActive_SnapshotGet(
    uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *committed_generation)
{
    PlatformCriticalState lock;
    if(record==NULL||committed_generation==NULL){return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();
    if(!s_status.active){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_NotPresent;}
    if(!s_status.saved||s_status.pending||s_dependency_invalid)
    {PlatformCritical_Exit(lock);return SystemInstallationActiveResult_NotReady;}
    (void)memcpy(record,s_active_record,SYSTEM_INSTALLATION_ACTIVE_BYTES);*committed_generation=s_status.saved_generation;
    PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Ok;
}
void SystemInstallationActive_Service(uint64_t now_us)
{
    uint8_t packet[SYSTEM_INSTALLATION_ACTIVE_BYTES],release;PlatformCriticalState lock;
    if(s_release_pending){(void)ActiveLease_Release();}
    if(SystemInstallationActive_RecordGet(packet)==SystemInstallationActiveResult_Ok&&!Active_DependenciesMatch(packet))
    {SystemInstallationActive_DependenciesChanged();}
    lock=PlatformCritical_Enter();
    release=(uint8_t)(s_upload&&!s_status.pending&&(now_us<s_last_command_us||now_us-s_last_command_us>30000000ULL));
    if(release){s_upload=0U;}PlatformCritical_Exit(lock);
    if(release){(void)ActiveLease_Release();}
}
void SystemInstallationActive_DependenciesChanged(void)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    if(s_dependency_revision!=UINT32_MAX){s_dependency_revision++;}
    s_dependency_invalid=1U;
    if(s_status.active){s_status.result=SystemInstallationActiveResult_DependencyChanged;}
    PlatformCritical_Exit(lock);
}

SystemInstallationActiveResult SystemInstallationActive_Save(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    PlatformCriticalState lock;uint32_t revision;
    if(!Active_Context(sid,rid,now_us)){return SystemInstallationActiveResult_Stale;}
    if(s_upload||!s_status.active||s_dependency_invalid||SystemLifecycle_MaintenanceGet()!=SystemMaintenanceState_Ready)
    {return SystemInstallationActiveResult_NotReady;}
    if(rid==s_rid&&s_status.pending){return SystemInstallationActiveResult_Pending;}
    if(s_status.pending){return SystemInstallationActiveResult_Busy;}
    if(s_status.saved){s_rid=rid;s_last_command_us=now_us;return SystemInstallationActiveResult_Ok;}
    if(rid<=s_rid){return SystemInstallationActiveResult_Stale;}
    if(!ActiveLease_Claim())
    {return SystemInstallationActiveResult_Busy;}
    lock=PlatformCritical_Enter();revision=s_dependency_revision;PlatformCritical_Exit(lock);
    if(!Active_DependenciesMatch(s_active_record)){
        (void)ActiveLease_Release();
        return SystemInstallationActiveResult_DependencyChanged;
    }
    lock=PlatformCritical_Enter();
    if(revision!=s_dependency_revision||s_dependency_invalid||s_status.pending||!s_status.active){
        PlatformCritical_Exit(lock);(void)ActiveLease_Release();
        return SystemInstallationActiveResult_DependencyChanged;
    }
    s_rid=rid;s_status.request_id=rid;s_status.pending=1U;
    s_status.result=SystemInstallationActiveResult_Pending;s_last_command_us=now_us;
    PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Pending;
}

SystemInstallationActiveResult SystemInstallationActive_PendingGet(
    uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *request_id)
{
    PlatformCriticalState lock;
    if(record==NULL||request_id==NULL){return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();
    if(!s_status.pending||s_status.request_id==0U||s_status.result!=SystemInstallationActiveResult_Pending)
    {PlatformCritical_Exit(lock);return SystemInstallationActiveResult_NotReady;}
    (void)memcpy(record,s_active_record,SYSTEM_INSTALLATION_ACTIVE_BYTES);*request_id=s_status.request_id;
    PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Ok;
}

SystemInstallationActiveResult SystemInstallationActive_SaveComplete(uint32_t request_id,
    uint8_t success,uint32_t committed_generation,const uint8_t *readback,uint16_t length)
{
    PlatformCriticalState lock;uint8_t confirmed;
    if(request_id==0U||success>1U){return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();
    if(!s_status.pending||request_id!=s_status.request_id){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Stale;}
    confirmed=(uint8_t)(success&&committed_generation!=0U&&readback!=NULL&&
        length==SYSTEM_INSTALLATION_ACTIVE_BYTES&&memcmp(readback,s_active_record,length)==0);
    s_status.saved=confirmed;s_status.saved_generation=committed_generation;s_status.pending=0U;
    s_status.result=confirmed?(s_dependency_invalid?SystemInstallationActiveResult_DependencyChanged:
        SystemInstallationActiveResult_Ok):SystemInstallationActiveResult_StorageError;
    PlatformCritical_Exit(lock);
    (void)ActiveLease_Release();
    return SystemInstallationActiveResult_Ok;
}

SystemInstallationActiveResult SystemInstallationActive_StoredLoad(
    const uint8_t *record,uint16_t length,uint32_t committed_generation)
{
    SystemCalibrationBaselineIdentity identity;SystemCalibrationImuCorrection correction;
    SystemCalibrationBaselineResult applied;SystemInstallationActiveResult result;
    PlatformCriticalState lock;uint32_t generation,revision;SystemLifecycleState lifecycle=SystemLifecycle_GetState();
    if(record==NULL||length!=SYSTEM_INSTALLATION_ACTIVE_BYTES||committed_generation==0U)
    {return SystemInstallationActiveResult_Invalid;}
    if(s_upload||s_status.pending||s_status.active||
        (lifecycle!=SYSTEM_STATE_BOOT&&lifecycle!=SYSTEM_STATE_SELF_TEST&&lifecycle!=SYSTEM_STATE_PREFLIGHT))
    {return SystemInstallationActiveResult_Busy;}
    lock=PlatformCritical_Enter();revision=s_dependency_revision;PlatformCritical_Exit(lock);
    if(revision==UINT32_MAX){return SystemInstallationActiveResult_NotReady;}
    result=Active_Validate(record,&identity,&correction);if(result!=SystemInstallationActiveResult_Ok){return result;}
    if(!ActiveLease_Claim()){return SystemInstallationActiveResult_Busy;}
    lock=PlatformCritical_Enter();s_status.pending=1U;s_status.request_id=0U;PlatformCritical_Exit(lock);
    applied=SystemCalibration_BaselineApplyOwned(&identity,&correction,0U,&generation,s_active_lease);
    if(applied!=SystemCalibrationBaselineResult_Ok){
        lock=PlatformCritical_Enter();s_status.pending=0U;PlatformCritical_Exit(lock);
        (void)ActiveLease_Release();return SystemInstallationActiveResult_NotReady;
    }
    lock=PlatformCritical_Enter();
    (void)memcpy(s_active_record,record,SYSTEM_INSTALLATION_ACTIVE_BYTES);
    s_status.applied_generation=generation;s_status.saved_generation=committed_generation;
    s_status.record_crc=Active_U32(&record[224]);s_status.active=1U;s_status.saved=1U;s_status.loaded=1U;s_status.pending=0U;
    if(revision!=s_dependency_revision){
        s_dependency_invalid=1U;s_status.result=SystemInstallationActiveResult_DependencyChanged;
        PlatformCritical_Exit(lock);(void)ActiveLease_Release();return SystemInstallationActiveResult_DependencyChanged;
    }
    s_status.result=SystemInstallationActiveResult_Ok;s_dependency_invalid=0U;PlatformCritical_Exit(lock);
    (void)ActiveLease_Release();
    /* BaselineApply invalidated old CAL/ALIGN. Loading never creates READY. */
    return SystemInstallationActiveResult_Ok;
}

uint8_t SystemInstallationActive_ReadyForMissionGet(void)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    uint8_t ready=(uint8_t)(!s_status.active||(s_status.saved&&!s_status.pending&&!s_dependency_invalid));
    PlatformCritical_Exit(lock);return ready;
}
void SystemInstallationActive_LoadFaultSet(SystemInstallationActiveResult result)
{
    PlatformCriticalState lock=PlatformCritical_Enter();
    s_status.active=1U;s_status.saved=0U;s_status.loaded=0U;s_status.result=result;s_dependency_invalid=1U;
    PlatformCritical_Exit(lock);
}

SystemInstallationActiveResult SystemInstallationActive_MagTransform(uint8_t instance,
    uint32_t parent_generation,uint32_t parent_crc,const float input[3],float output[3])
{
    float a[3],g[3];uint8_t i,j;PlatformCriticalState lock;
    if(input==NULL||output==NULL){return SystemInstallationActiveResult_Invalid;}
    lock=PlatformCritical_Enter();
    if(!s_status.active){
        for(i=0U;i<3U;i++){if(!isfinite(input[i])){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Invalid;}}
        (void)memcpy(output,input,sizeof(float)*3U);PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Ok;
    }
    if(s_status.pending||s_dependency_invalid||instance!=s_active_record[36]||parent_generation!=Active_U32(&s_active_record[48])||
        parent_crc!=Active_U32(&s_active_record[28]))
    {PlatformCritical_Exit(lock);return SystemInstallationActiveResult_DependencyChanged;}
    for(i=0U;i<3U;i++){
        a[i]=0.0f;for(j=0U;j<3U;j++){a[i]+=Active_F32(&s_active_record[188U+4U*(3U*i+j)])*input[j];}
    }
    for(i=0U;i<3U;i++){
        g[i]=0.0f;for(j=0U;j<3U;j++){g[i]+=Active_F32(&s_active_record[152U+4U*(3U*i+j)])*a[j];}
        if(!isfinite(g[i])){PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Invalid;}
    }
    (void)memcpy(output,g,sizeof(g));PlatformCritical_Exit(lock);return SystemInstallationActiveResult_Ok;
}
