/* Real owning active wire/SHA/CAL consumer with explicit synthetic native,
 * descriptor, parent MAG and storage completion facades. Not hardware proof. */
#define ACTIVE_INTEGRATION
#include "installation_baseline_fixture.h"
#include "capture_internal.h"
#include "system_installation_active_if.h"
#include "system_mag_calibration.h"
#include "installation_capture.c"
static SystemCalibrationBaselineResult Harness_BaselineApplyOwned(
    const SystemCalibrationBaselineIdentity *identity,const SystemCalibrationImuCorrection *correction,
    uint32_t expected,uint32_t *applied,uint32_t token);
#define SystemCalibration_BaselineApplyOwned Harness_BaselineApplyOwned
#include "installation_active.c"
#undef SystemCalibration_BaselineApplyOwned
#include "installation_active_wire.c"
#include "mag_calibration_storage.c"

static uint8_t s_qualified=1U,s_change_on_check;
static SystemMaintenanceState s_maintenance_state=SystemMaintenanceState_Ready;
static SystemCalibrationBaselineResult Harness_BaselineApplyOwned(
    const SystemCalibrationBaselineIdentity *identity,const SystemCalibrationImuCorrection *correction,
    uint32_t expected,uint32_t *applied,uint32_t token)
{
    SystemCalibrationBaselineResult result=SystemCalibration_BaselineApplyOwned(identity,correction,expected,applied,token);
    if(result==SystemCalibrationBaselineResult_Ok){
        TEST_CHECK(s_capture.control.fields.resource_owner==10U);
        TEST_CHECK(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_Calibration,1U)==SYSTEM_DEVICE_BUSY);
        TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE)==SYSTEM_DEVICE_BUSY);
        TEST_CHECK(s_capture.control.fields.resource_owner==10U);
        if(s_change_on_apply){s_change_on_apply=0U;SystemInstallationActive_DependenciesChanged();}
    }
    return result;
}

static uint8_t s_persisted[228],s_store_fault;
static uint32_t s_persisted_generation;
SystemDeviceResult SystemStorage_Init(void){return SYSTEM_DEVICE_OK;}
SystemDeviceResult SystemStorage_Mount(void){return SYSTEM_DEVICE_OK;}
uint8_t ProjectMagnetometerInstance_CountGet(void){return 0U;}
SystemMagCalibrationResult SystemMagCalibration_LoadFaultSet(uint8_t instance,SystemMagCalibrationResult result)
{(void)instance;(void)result;return SystemMagCalibrationResult_Ok;}
SystemMagCalibrationResult SystemMagCalibration_SaveComplete(uint8_t instance,uint32_t request,uint8_t success,uint32_t generation)
{(void)instance;(void)request;(void)success;(void)generation;return SystemMagCalibrationResult_Ok;}
SystemMagCalibrationResult SystemMagCalibration_RecordLoadOwned(uint8_t instance,const uint8_t *record,uint16_t length,uint32_t generation)
{(void)instance;(void)record;(void)length;(void)generation;return SystemMagCalibrationResult_NotPresent;}
SystemMagCalibrationResult SystemMagCalibration_PendingRecordGet(uint8_t *instance,uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES],uint32_t *request)
{(void)record;(void)request;*instance=UINT8_MAX;return SystemMagCalibrationResult_NotReady;}
PersistentStorageResult PersistentStorage_ObjectWriteAtomic(PersistentStorageObjectKind kind,uint8_t instance,const uint8_t *data,uint16_t length,uint32_t *generation)
{
    TEST_CHECK(kind==PERSISTENT_STORAGE_OBJECT_INSTALLATION_ACTIVE&&instance==0U&&length==228U);
    if(s_store_fault==1U){return PERSISTENT_STORAGE_IO_ERROR;}
    (void)memcpy(s_persisted,data,228U);*generation=++s_persisted_generation;return PERSISTENT_STORAGE_OK;
}
PersistentStorageResult PersistentStorage_ObjectRead(PersistentStorageObjectKind kind,uint8_t instance,uint8_t *data,uint16_t capacity,uint16_t *length,uint32_t *generation)
{
    TEST_CHECK(kind==PERSISTENT_STORAGE_OBJECT_INSTALLATION_ACTIVE&&instance==0U&&capacity>=228U);
    if(!s_persisted_generation){return PERSISTENT_STORAGE_NOT_FOUND;}
    (void)memcpy(data,s_persisted,228U);*length=228U;*generation=s_persisted_generation;
    if(s_store_fault==2U){data[100]^=1U;}return PERSISTENT_STORAGE_OK;
}

SystemMaintenanceState SystemLifecycle_MaintenanceGet(void){return s_maintenance_state;}
uint8_t SystemInstallationCapture_ActiveQualifiedGet(float matrix[9])
{uint8_t i;for(i=0U;i<9U;i++){matrix[i]=(i%4U==0U)?1.0f:0.0f;}return s_qualified;}
SystemMagCalibrationResult SystemMagCalibration_SnapshotGet(uint8_t instance,SystemMagCalibrationSnapshot *snapshot)
{
    (void)instance;(void)memset(snapshot,0,sizeof(*snapshot));snapshot->status.active=1U;
    snapshot->status.saved=1U;snapshot->status.generation=3U;snapshot->status.intrinsic_crc=99U;
    if(s_change_on_check){s_change_on_check=0U;SystemInstallationActive_DependenciesChanged();}
    return SystemMagCalibrationResult_Ok;
}
static void Test_U32(uint8_t *p,uint32_t value)
{uint8_t i;for(i=0U;i<4U;i++){p[i]=(uint8_t)(value>>(8U*i));}}
static void Test_F32(uint8_t *p,float value){uint32_t bits;(void)memcpy(&bits,&value,4U);Test_U32(p,bits);}
static void Test_Record(uint8_t record[228])
{
    uint8_t i;CaptureSha hash;static const uint8_t domain[]="SSIC-ACTIVE-STABLE-v1";
    (void)memset(record,0,228U);(void)memcpy(record,"SSIC",4U);
    record[4]=1U;record[5]=3U;record[6]=1U;record[7]=3U;record[8]=101U;record[10]=9U;
    record[13]=1U;record[14]=1U;Test_U32(&record[16],77U);Test_U32(&record[20],22U);Test_U32(&record[24],33U);
    Test_U32(&record[28],99U);record[32]=101U;record[34]=9U;Test_U32(&record[40],22U);Test_U32(&record[44],33U);
    Test_U32(&record[48],3U);(void)memset(&record[52],0x42,32U);
    for(i=0U;i<3U;i++){Test_F32(&record[116U+4U*i],0.1f);Test_F32(&record[128U+4U*i],1.02f);Test_F32(&record[140U+4U*i],0.01f);}
    for(i=0U;i<9U;i++){Test_F32(&record[152U+4U*i],(i%4U==0U)?1.0f:0.0f);}
    /* +90 degrees about Z in M -> A, so a duplicate application is visible. */
    Test_F32(&record[192],-1.0f);Test_F32(&record[200],1.0f);Test_F32(&record[220],1.0f);
    CaptureSha_Init(&hash);for(i=0U;i<sizeof(domain);i++){CaptureSha_Byte(&hash,domain[i]);}
    for(i=0U;i<52U;i++){CaptureSha_Byte(&hash,record[i]);}for(i=152U;i<188U;i++){CaptureSha_Byte(&hash,record[i]);}
    CaptureSha_Finish(&hash,&record[84]);Test_U32(&record[224],Active_Crc(record,224U));
}
static void Test_Reset(void)
{
    (void)memset(&s_status,0,sizeof(s_status));s_upload=0U;s_rid=0U;s_dependency_revision=0U;s_dependency_invalid=0U;
    s_maintenance_state=SystemMaintenanceState_Ready;s_change_on_apply=0U;s_change_on_check=0U;s_qualified=1U;s_offset=0U;s_configuration=77U;
    (void)memset(&s_capture,0,sizeof(s_capture));s_active_lease=0U;s_release_pending=0U;
    (void)memset(s_sid,0,sizeof(s_sid));(void)memset(s_read_sid,0,sizeof(s_read_sid));
    s_capture.transaction.fields.producer_stopped=0U;SystemCalibration_Init();
    s_mag_calibration_load_complete=0U;s_mag_calibration_load_instance=0U;s_installation_active_load_complete=0U;
}
static uint32_t Test_Upload(const uint8_t record[228],const uint8_t sid[16])
{
    uint8_t sha[32];uint16_t offset;uint32_t rid=1U;
    TEST_CHECK(InstallationCapture_Hash(record,228U,sha)==InstallationCaptureResult_Ok);
    TEST_CHECK(SystemInstallationActive_UploadBegin(sid,rid,Active_Crc(record,228U),sha,100U)==SystemInstallationActiveResult_Ok);
    TEST_CHECK(SystemInstallationActive_UploadBegin(sid,rid,Active_Crc(record,228U),sha,100U)==SystemInstallationActiveResult_Ok);
    for(offset=0U;offset<228U;offset=(uint16_t)(offset+48U)){
        uint16_t length=(uint16_t)(228U-offset);if(length>48U){length=48U;}rid++;
        TEST_CHECK(SystemInstallationActive_UploadWrite(sid,rid,offset,&record[offset],length,100U)==SystemInstallationActiveResult_Ok);
        TEST_CHECK(SystemInstallationActive_UploadWrite(sid,rid,offset,&record[offset],length,100U)==SystemInstallationActiveResult_Ok);
    }
    return rid+1U;
}
static void Test_StartOwnership(void)
{
    uint32_t token=0U,newer=0U,alignment;
    Test_Reset();
    TEST_CHECK(InstallationCapture_OperationBegin(5U,0U)==InstallationCaptureResult_Ok);
    alignment=s_capture.control.fields.resource_token;
    TEST_CHECK(InstallationCapture_StartClaim(1U,&token)==InstallationCaptureResult_Ok&&token>alignment);
    TEST_CHECK(InstallationCapture_OperationHeld(5U)==0U&&InstallationCapture_OperationHeld(6U)==1U);
    TEST_CHECK(InstallationCapture_OperationEnd(5U)==InstallationCaptureResult_Stale);
    TEST_CHECK(InstallationCapture_OperationBegin(4U,1U)==InstallationCaptureResult_Busy);
    TEST_CHECK(InstallationCapture_StartClaim(1U,&newer)==InstallationCaptureResult_Stale);
    /* Completion must not spin on the Device inspector's capture gate. */
    s_capture.control.fields.gate=1U;
    TEST_CHECK(InstallationCapture_StartRelease(token,1U)==InstallationCaptureResult_Ok);
    TEST_CHECK(s_capture.frozen.release_token==0U&&s_capture.transaction.fields.start_restore_token==token);
    TEST_CHECK(InstallationCapture_StartRelease(token,0U)==InstallationCaptureResult_Stale);
    s_capture.control.fields.gate=0U;
    TEST_CHECK(InstallationCapture_OperationHeld(5U)==1U&&s_capture.control.fields.resource_token==token);
    TEST_CHECK(InstallationCapture_OperationBegin(4U,1U)==InstallationCaptureResult_Busy);
    InstallationCapture_DependenciesChanged();
    TEST_CHECK(InstallationCapture_StartClaim(1U,&newer)==InstallationCaptureResult_Ok&&newer>token);
    TEST_CHECK(InstallationCapture_StartRelease(token,1U)==InstallationCaptureResult_Stale);
    TEST_CHECK(InstallationCapture_OperationHeld(6U)==1U&&s_capture.control.fields.resource_token==newer);
    TEST_CHECK(InstallationCapture_StartRelease(newer,0U)==InstallationCaptureResult_Ok);
    TEST_CHECK(InstallationCapture_OperationHeld(5U)==0U&&InstallationCapture_OperationHeld(6U)==0U);
    TEST_CHECK(InstallationCapture_StartClaim(0U,&newer)==InstallationCaptureResult_Ok&&newer>token);
    TEST_CHECK(InstallationCapture_StartRelease(token,1U)==InstallationCaptureResult_Stale);
    TEST_CHECK(InstallationCapture_OperationHeld(6U)==1U&&s_capture.control.fields.resource_token==newer);
    TEST_CHECK(InstallationCapture_StartRelease(newer,0U)==InstallationCaptureResult_Ok);
    TEST_CHECK(InstallationCapture_OperationBegin(4U,0U)==InstallationCaptureResult_Ok);
    TEST_CHECK(InstallationCapture_StartClaim(0U,&newer)==InstallationCaptureResult_Busy);
    TEST_CHECK(InstallationCapture_OperationEnd(4U)==InstallationCaptureResult_Ok);
    TEST_CHECK(InstallationCapture_OperationHeld(4U)==0U);
    TEST_CHECK(InstallationCapture_OperationBegin(5U,0U)==InstallationCaptureResult_Ok);
    alignment=s_capture.control.fields.resource_token;s_capture.control.fields.resource_generation=UINT32_MAX;
    TEST_CHECK(InstallationCapture_StartClaim(1U,&newer)==InstallationCaptureResult_Capacity);
    TEST_CHECK(InstallationCapture_OperationHeld(5U)==1U&&s_capture.control.fields.resource_token==alignment);
}

int main(void)
{
    uint8_t packet[228],readback[228],sid[16]={1U},sha[32];uint32_t rid,generation,request;
    SystemInstallationActiveStatus status;SystemCalibrationImuCorrection correction;
    float input[3]={1.1f,2.1f,3.1f},gyro[3]={0.11f,0.21f,0.31f},a[3],g[3];char reply[512];
    Test_StartOwnership();
    Test_Reset();Test_Record(packet);
    {uint8_t empty_sid[16]={0U};
        TEST_CHECK(InstallationCapture_Hash(packet,228U,sha)==InstallationCaptureResult_Ok);
        TEST_CHECK(SystemInstallationActive_UploadBegin(empty_sid,1U,Active_Crc(packet,228U),sha,100U)==SystemInstallationActiveResult_Invalid);
    }
    rid=Test_Upload(packet,sid);
    TEST_CHECK(SystemInstallationActive_Apply(sid,rid,100U)==SystemInstallationActiveResult_Ok&&s_capture.control.fields.resource_owner==0U);
    TEST_CHECK(SystemInstallationActive_Apply(sid,rid,100U)==SystemInstallationActiveResult_Ok);
    TEST_CHECK(SystemCalibration_IsReady()==0U);
    s_maintenance_state=SystemMaintenanceState_Off;
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE)==SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_ImuCorrectionGet(&correction)==SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_ImuCorrectionApply(input,gyro,&correction,a,g)==SYSTEM_DEVICE_OK);
    TEST_CHECK_NEAR(a[0],1.02f,0.00001f);TEST_CHECK_NEAR(g[0],0.1f,0.00001f);
    s_maintenance_state=SystemMaintenanceState_Ready;
    TEST_CHECK(SystemInstallationActive_MagTransform(0U,3U,99U,input,a)==SystemInstallationActiveResult_Ok);
    TEST_CHECK_NEAR(a[0],-2.1f,0.00001f);TEST_CHECK_NEAR(a[1],1.1f,0.00001f);
    TEST_CHECK(SystemInstallationActive_SnapshotGet(readback,&generation)==SystemInstallationActiveResult_NotReady);
    TEST_CHECK(SystemInstallationActive_Save(sid,++rid,100U)==SystemInstallationActiveResult_Pending);
    TEST_CHECK(SystemInstallationActive_Cancel(sid,rid+1U)==SystemInstallationActiveResult_Pending&&s_capture.control.fields.resource_owner==10U);
    TEST_CHECK(SystemInstallationActive_PendingGet(readback,&request)==SystemInstallationActiveResult_Ok&&request==rid);
    readback[100]^=1U;
    TEST_CHECK(SystemInstallationActive_SaveComplete(rid,1U,7U,readback,228U)==SystemInstallationActiveResult_Ok&&s_capture.control.fields.resource_owner==0U);
    TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&!status.saved&&status.saved_generation==7U);
    TEST_CHECK(SystemInstallationActive_Save(sid,++rid,100U)==SystemInstallationActiveResult_Pending);
    TEST_CHECK(SystemInstallationActive_SaveComplete(rid,1U,8U,packet,228U)==SystemInstallationActiveResult_Ok);
    TEST_CHECK(SystemInstallationActive_SnapshotGet(readback,&generation)==SystemInstallationActiveResult_Ok&&generation==8U);
    /* Reboot facade resets only RAM; immutable persistent bytes survive. */
    Test_Reset();TEST_CHECK(SystemInstallationActive_StoredLoad(packet,228U,8U)==SystemInstallationActiveResult_Ok);
    TEST_CHECK(SystemCalibration_IsReady()==0U);
    TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&status.loaded&&status.saved&&status.valid);
    SystemInstallationActive_DependenciesChanged();
    TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&status.active&&!status.valid);
    TEST_CHECK(SystemInstallationActive_RecordGet(readback)==SystemInstallationActiveResult_NotReady);
    TEST_CHECK(!SystemInstallationActive_RuntimeReady(1U));
    TEST_CHECK(SystemInstallationActive_SnapshotGet(readback,&generation)==SystemInstallationActiveResult_NotReady);
    /* Deterministic fault: identity revision changes after baseline publication. */
    Test_Reset();rid=Test_Upload(packet,sid);s_change_on_apply=1U;
    TEST_CHECK(SystemInstallationActive_Apply(sid,rid,100U)==SystemInstallationActiveResult_DependencyChanged);
    TEST_CHECK(s_capture.control.fields.resource_owner==0U&&!SystemInstallationActive_RuntimeReady(1U));
    TEST_CHECK(SystemInstallationActive_SnapshotGet(readback,&generation)==SystemInstallationActiveResult_NotReady);
    Test_Reset();s_change_on_apply=1U;
    TEST_CHECK(SystemInstallationActive_StoredLoad(packet,228U,8U)==SystemInstallationActiveResult_DependencyChanged);
    TEST_CHECK(!SystemInstallationActive_RuntimeReady(1U));
    Test_Reset();rid=Test_Upload(packet,sid);TEST_CHECK(SystemInstallationActive_Apply(sid,rid,100U)==SystemInstallationActiveResult_Ok);
    s_change_on_check=1U;TEST_CHECK(SystemInstallationActive_Save(sid,++rid,100U)==SystemInstallationActiveResult_DependencyChanged);
    TEST_CHECK(!s_capture.control.fields.resource_owner);TEST_CHECK(SystemInstallationActive_PendingGet(readback,&request)==SystemInstallationActiveResult_NotReady);
    Test_Reset();s_qualified=0U;TEST_CHECK(InstallationCapture_Hash(packet,228U,sha)==InstallationCaptureResult_Ok);
    TEST_CHECK(SystemInstallationActive_UploadBegin(sid,1U,Active_Crc(packet,228U),sha,100U)==SystemInstallationActiveResult_Unsupported);
    TEST_CHECK(!s_capture.control.fields.resource_owner);
    TEST_CHECK(SystemInstallationActive_ExecuteLine("INSTALL DO 01000000000000000000000000000000 3 APPLY",reply,sizeof(reply),100U));
    TEST_CHECK(strstr(reply,"ERR INSTALL DO")!=NULL);
    /* Real Logger TF service owner, with explicit bounded media facade. */
    Test_Reset();SystemMagCalibrationStorage_Service();SystemMagCalibrationStorage_Service();
    rid=Test_Upload(packet,sid);TEST_CHECK(SystemInstallationActive_Apply(sid,rid,100U)==SystemInstallationActiveResult_Ok);
    s_store_fault=1U;TEST_CHECK(SystemInstallationActive_Save(sid,++rid,100U)==SystemInstallationActiveResult_Pending);
    SystemMagCalibrationStorage_Service();TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&!status.saved&&!status.pending&&!s_capture.control.fields.resource_owner);
    s_store_fault=2U;TEST_CHECK(SystemInstallationActive_Save(sid,++rid,100U)==SystemInstallationActiveResult_Pending);
    SystemMagCalibrationStorage_Service();TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&!status.saved&&status.saved_generation==1U);
    s_store_fault=0U;TEST_CHECK(SystemInstallationActive_Save(sid,++rid,100U)==SystemInstallationActiveResult_Pending);
    SystemMagCalibrationStorage_Service();TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&status.saved&&status.saved_generation==2U);
    Test_Reset();SystemMagCalibrationStorage_Service();SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemInstallationActive_StatusGet(&status)==SystemInstallationActiveResult_Ok&&status.loaded&&status.saved&&status.valid);
    TEST_CHECK(SystemCalibration_IsReady()==0U);
    return Test_Finish("installation_active_real_CAL_and_MAG_transform");
}

/* Python tests drive the same C line handler and owning storage service. CAPS
 * is a synthetic test facade, never linked into generated firmware. */
void Harness_Reset(void){s_persisted_generation=0U;s_store_fault=0U;Test_Reset();SystemMagCalibrationStorage_Service();SystemMagCalibrationStorage_Service();}
void Harness_Reboot(void){Test_Reset();SystemMagCalibrationStorage_Service();SystemMagCalibrationStorage_Service();}
void Harness_Packet(uint8_t record[228]){Test_Record(record);}
void Harness_Fault(uint8_t fault){s_store_fault=fault;}
uint8_t Harness_Execute(const char *line,char *out)
{
    if(strcmp(line,"INSTALL CAPS")==0){
        (void)CommonFormat_Print(out,512U,"OK INSTALL CAPS maintenance=0.1 supported=1 install_contract=1 face_auto=1 check_only=1 sample_format=1 max_request=191 max_line=511 train_pairs=3 holdout_pairs=3 pair_capacity=4096 offline=1 contract_supported=1 capture_available=1 apply_supported=1 save_supported=1 active_record=3 reason=SYNTHETIC_ONLY");return 1U;
    }
    SystemMagCalibrationStorage_Service();return SystemInstallationActive_ExecuteLine(line,out,512U,100U);
}
