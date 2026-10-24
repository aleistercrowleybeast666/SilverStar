#include "system_installation_capture.h"
#include "common_format.h"
#include "system_console_if.h"
#include <stddef.h>
#include <string.h>
#include "system_calibration.h"
#include "system_mag_calibration.h"
#include "system_descriptor_if.h"

typedef struct {
    uint8_t sid[16];
    uint32_t rid;
    uint16_t train_pairs,holdout_pairs;
    uint8_t configured,offline,active,cancelled;
} InstallationWire;
typedef struct { char *part[5]; } InstallationWireTokens;
static InstallationWire s_wire __attribute__((section(".ccmram_bss.installation_wire"),aligned(8)));

static void InstallationWire_Hex(char *out,const uint8_t *value,uint16_t count)
{
    static const char alphabet[]="0123456789abcdef";uint16_t i;
    for(i=0U;i<count;i++){out[2U*i]=alphabet[value[i]>>4];out[2U*i+1U]=alphabet[value[i]&15U];}
    out[2U*count]='\0';
}

static uint8_t InstallationWire_Unhex(const char *text,uint8_t *out,uint8_t count)
{
    uint8_t i,nonzero=0U;
    for(i=0U;i<count;i++){
        uint8_t j,value=0U;
        for(j=0U;j<2U;j++){
            char c=text[2U*i+j];uint8_t n;
            if(c>='0'&&c<='9'){n=(uint8_t)(c-'0');}
            else if(c>='a'&&c<='f'){n=(uint8_t)(c-'a'+10);}
            else{return 0U;}
            value=(uint8_t)(value*16U+n);
        }
        out[i]=value;nonzero|=value;
    }
    return (uint8_t)(text[2U*count]=='\0'&&nonzero!=0U);
}

static uint8_t InstallationWire_U32(const char *text,uint32_t *out)
{
    uint8_t i;uint32_t value=0U;
    if(text[0]=='\0'||(text[0]=='0'&&text[1]!='\0')){return 0U;}
    for(i=0U;i<11U;i++){
        uint8_t digit;
        if(text[i]=='\0'){*out=value;return 1U;}
        if(text[i]<'0'||text[i]>'9'){return 0U;}
        digit=(uint8_t)(text[i]-'0');
        if(value>(UINT32_MAX-digit)/10U){return 0U;}
        value=value*10U+digit;
    }
    return 0U;
}

static uint8_t InstallationWire_Split(char *text,InstallationWireTokens *parts,uint8_t maximum,char delimiter)
{
    uint16_t i;uint8_t count=0U,in=0U;
    for(i=0U;i<192U;i++){
        char c=text[i];
        if(c=='\0'){return (delimiter==':'&&in==0U)?0U:count;}
        if(c==delimiter||(delimiter==' '&&c=='\t')){
            if(delimiter==':'&&in==0U){return 0U;}
            text[i]='\0';in=0U;
        }
        else if(c<33||c>126){return 0U;}
        else if(in==0U){if(count>=maximum){return 0U;}parts->part[count++]=&text[i];in=1U;}
    }
    return 0U;
}

InstallationCaptureResult SystemInstallationCapture_Configure(const InstallationCaptureSnapshot *snapshot)
{
    InstallationCaptureResult result;
    if(snapshot==NULL){return InstallationCaptureResult_Invalid;}
    result=InstallationCapture_Enable(1U);
    if(result!=InstallationCaptureResult_Ok){return result;}
    result=InstallationCapture_Configure(snapshot);
    if(result==InstallationCaptureResult_Ok){
        (void)memset(&s_wire,0,sizeof(s_wire));
        s_wire.configured=1U;s_wire.offline=snapshot->offline;
        s_wire.train_pairs=snapshot->train_pairs;s_wire.holdout_pairs=snapshot->holdout_pairs;
    }
    return result;
}

static InstallationCaptureResult InstallationWire_SnapshotBuild(void)
{
    InstallationCaptureSnapshot snapshot;
    SystemDeviceDescriptor descriptor;
    SystemCalibrationImuCorrection imu;
    SystemMagCalibrationSnapshot mag;
    uint32_t before=SystemCalibration_GenerationGet();uint8_t role,i;
    (void)memset(&snapshot,0,sizeof(snapshot));
    snapshot.configuration=SystemDescriptor_ConfigDigestGet();
    snapshot.maximum_skew_us=2000U;snapshot.maximum_uncertainty_us=1000U;
    snapshot.native_health_timeout_us=250000U;snapshot.source_timeout_us=250000U;
    snapshot.face_timeout_us=10000000U;snapshot.selected_interval_max_us=210000U;
    snapshot.nominal_output_millihz=5000U;snapshot.train_pairs=3U;snapshot.holdout_pairs=3U;
    for(role=0U;role<2U;role++){
        InstallationCaptureSource *source=&snapshot.sources[role];
        if(SystemDescriptor_DeviceFind(role==0U?SYSTEM_DEVICE_CLASS_IMU:SYSTEM_DEVICE_CLASS_MAGNETOMETER,
                0U,&descriptor)!=SYSTEM_DEVICE_OK){return InstallationCaptureResult_Disabled;}
        source->configuration=snapshot.configuration;source->descriptor=descriptor.descriptor_id;
        source->physical=descriptor.physical_device_id;source->instance=descriptor.instance_id;
        if(descriptor.configured_rate_hz<5U||descriptor.configured_rate_hz%5U!=0U){return InstallationCaptureResult_Disabled;}
        source->profile=(uint16_t)(2U+role);source->stride=descriptor.configured_rate_hz/5U;
        source->uncertainty_us=UINT32_MAX;
        for(i=0U;i<3U;i++){source->axis_map[i]=(int8_t)(i+1U);}
        (void)memcpy(snapshot.intrinsic_id[role],"UNKNOWN",8U);
    }
    if(SystemCalibration_ImuCorrectionGet(&imu)==SYSTEM_DEVICE_OK&&imu.ready!=0U&&
            imu.mode!=SYSTEM_CALIBRATION_MODE_NONE&&before!=0U){
        snapshot.sources[0].intrinsic_generation=before;
        (void)CommonFormat_Print(snapshot.intrinsic_id[0],32U,"imu-%lu",(unsigned long)before);
        snapshot.gyro_known=1U;snapshot.gyro_mode=(uint8_t)imu.mode;
        for(i=0U;i<3U;i++){
            snapshot.accel_bias[i]=imu.accel_bias_mps2[i];snapshot.accel_matrix[4U*i]=imu.accel_scale[i];
            snapshot.gyro_bias[i]=imu.gyro_bias_radps[i];snapshot.gyro_scale[i]=imu.gyro_scale[i];
        }
    }
    if(SystemMagCalibration_SnapshotGet(0U,&mag)==SystemMagCalibrationResult_Ok){
        if(mag.status.generation==0U||mag.status.saved==0U||mag.status.save_pending!=0U||
            mag.status.save_failed!=0U||mag.status.configuration_digest!=snapshot.configuration){
            return InstallationCaptureResult_Conflict;
        }
        snapshot.sources[1].intrinsic_generation=mag.status.generation;
        (void)CommonFormat_Print(snapshot.intrinsic_id[1],32U,"mag-%lu-%08lx",
            (unsigned long)mag.status.generation,(unsigned long)mag.status.intrinsic_crc);
        for(i=0U;i<3U;i++){
            uint8_t j;snapshot.mag_bias[i]=mag.bias[i];
            for(j=0U;j<3U;j++){snapshot.mag_matrix[3U*i+j]=mag.matrix[i][j];}
        }
    }
    if(before!=SystemCalibration_GenerationGet()){return InstallationCaptureResult_Conflict;}
    /* Boot identity, sensor epochs, physical measurement time, native raw-frame
     * proof and R_GA are unavailable. Keep UNKNOWN/null; BEGIN stays closed. */
    return SystemInstallationCapture_Configure(&snapshot);
}

static uint8_t InstallationWire_ProofValid(const SystemInstallationCaptureProof *proof)
{
    return (uint8_t)(proof!=NULL&&proof->every_native_frame==1U&&proof->measurement_time_known==1U&&
        proof->raw_definition_known==1U&&proof->physical_body_units_known==1U&&proof->uncertainty_us!=UINT32_MAX);
}

void SystemInstallationCapture_ImuObserve(const SystemImuSample *sample,const SystemInstallationCaptureProof *proof,uint64_t now_us)
{
    InstallationCaptureSample value;InstallationCaptureResult result;uint8_t i;
    if(sample==NULL||!InstallationWire_ProofValid(proof)||
        (sample->valid_mask&3U)!=3U||sample->quality_flags!=0U){InstallationCapture_SourceLost();return;}
    (void)memset(&value,0,sizeof(value));value.sequence=sample->sequence;value.epoch=proof->epoch;
    value.sample_us=sample->sample_timestamp_us;value.receive_us=sample->receive_timestamp_us;
    value.uncertainty_us=proof->uncertainty_us;value.flags=16U;
    for(i=0U;i<3U;i++){
        value.physical[i]=sample->accel_b_mps2[i];value.physical[i+3U]=sample->gyro_b_radps[i];
        value.raw[i]=sample->accel_raw[i];value.raw[i+3U]=sample->gyro_raw[i];
    }
    result=InstallationCapture_SourcePush(0U,&value,now_us);
    if(result!=InstallationCaptureResult_Ok&&result!=InstallationCaptureResult_Stale){InstallationCapture_SourceLost();}
}

void SystemInstallationCapture_MagObserve(const SystemMagnetometerSample *sample,const SystemInstallationCaptureProof *proof,uint64_t now_us)
{
    InstallationCaptureSample value;InstallationCaptureResult result;uint8_t i;
    if(sample==NULL||!InstallationWire_ProofValid(proof)||(sample->valid_mask&3U)!=3U||
        (sample->valid_mask&SYSTEM_MAG_VALID_CALIBRATED)!=0U){InstallationCapture_SourceLost();return;}
    (void)memset(&value,0,sizeof(value));value.sequence=sample->sequence;value.epoch=proof->epoch;
    value.sample_us=sample->sample_timestamp_us;value.receive_us=sample->receive_timestamp_us;
    value.uncertainty_us=proof->uncertainty_us;value.flags=16U;
    for(i=0U;i<3U;i++){value.physical[i]=sample->magnetic_field_b_uT[i];value.raw[i]=sample->raw[i];}
    result=InstallationCapture_SourcePush(1U,&value,now_us);
    if(result!=InstallationCaptureResult_Ok&&result!=InstallationCaptureResult_Stale){InstallationCapture_SourceLost();}
}

uint8_t SystemInstallationCapture_CommandBlocked(void)
{
    InstallationCaptureStatus status;
    return (uint8_t)(InstallationCapture_Status(&status)!=InstallationCaptureResult_Ok||
        status.resource_owner==1U||status.resource_owner==11U);
}

static void InstallationWire_Info(uint32_t cursor,char *out,uint16_t capacity)
{
    InstallationCaptureStatus status;uint8_t data[48],end;uint16_t length,next;
    char hex[97],binding[65],sha[65];InstallationCaptureResult result;
    if(cursor==0U&&s_wire.active==0U&&s_wire.offline==0U){s_wire.configured=0U;
        if(InstallationWire_SnapshotBuild()!=InstallationCaptureResult_Ok){
            (void)CommonFormat_Print(out,capacity,"ERR INSTALL INFO code=NOT_READY reason=PARENT_UNSTABLE_OR_ENDPOINT_UNAVAILABLE");return;}}
    if(cursor>65535U||s_wire.configured==0U){return;}
    result=InstallationCapture_InfoRead((uint16_t)cursor,data,&length,&next,&end);
    if(result!=InstallationCaptureResult_Ok||InstallationCapture_Status(&status)!=InstallationCaptureResult_Ok){return;}
    InstallationWire_Hex(hex,data,length);InstallationWire_Hex(binding,status.binding,15U);
    InstallationWire_Hex(sha,status.info_sha256,32U);
    (void)CommonFormat_Print(out,capacity,"OK INSTALL INFO binding=B-%s cursor=%lu next=%u end=%u length=%lu sha256=%s data=%s",
        binding,(unsigned long)cursor,(unsigned int)next,(unsigned int)end,(unsigned long)status.info_bytes,sha,hex);
}

static InstallationCaptureResult InstallationWire_Face(char *text,uint32_t rid,uint64_t now_us)
{
    static const char * const faces[6]={"XP","XN","YP","YN","ZP","ZN"};
    InstallationWireTokens fields;uint32_t attempt;uint8_t mode,stage,face;
    if(InstallationWire_Split(text,&fields,4U,':')!=4U||!InstallationWire_U32(fields.part[3],&attempt)||attempt==0U||attempt>65535U){return InstallationCaptureResult_Invalid;}
    if(strcmp(fields.part[0],"FIT_CHECK")==0){mode=0U;}else if(strcmp(fields.part[0],"CHECK_ONLY")==0){mode=1U;}else{return InstallationCaptureResult_Invalid;}
    if(strcmp(fields.part[1],"SIX_FACE")==0){stage=1U;}else if(strcmp(fields.part[1],"SUPPLEMENT")==0){stage=2U;}else{return InstallationCaptureResult_Invalid;}
    for(face=0U;face<6U;face++){if(strcmp(fields.part[2],faces[face])==0){break;}}
    if(face==6U){return InstallationCaptureResult_Invalid;}
    return InstallationCapture_Face(s_wire.sid,rid,mode,stage,face,(uint16_t)attempt,now_us);
}

static InstallationCaptureResult InstallationWire_Begin(const uint8_t sid[16],
    uint32_t rid,const char *binding,uint64_t now_us)
{
    uint8_t bytes[15];InstallationCaptureResult result;
    if(s_wire.active!=0U&&memcmp(sid,s_wire.sid,16U)!=0){return InstallationCaptureResult_Conflict;}
    if(strncmp(binding,"B-",2U)!=0||!InstallationWire_Unhex(binding+2U,bytes,15U)){return InstallationCaptureResult_Invalid;}
    if(s_wire.offline==0U){return InstallationCaptureResult_Disabled;}
    result=InstallationCapture_Begin(sid,rid,bytes,now_us);
    if(result==InstallationCaptureResult_Ok){
        (void)memcpy(s_wire.sid,sid,16U);s_wire.active=1U;s_wire.cancelled=0U;
    }
    return result;
}

static InstallationCaptureResult InstallationWire_Cancel(const uint8_t sid[16],uint32_t rid,uint64_t now_us)
{
    InstallationCaptureResult result;
    if(s_wire.cancelled==1U&&s_wire.rid==rid){return InstallationCaptureResult_Cancelled;}
    result=InstallationCapture_Cancel(sid,rid,now_us);
    if(result!=InstallationCaptureResult_Pending&&result!=InstallationCaptureResult_Cancelled){return result;}
    /* No DMA/FIFO/async producer lease is owned by the synchronous Observe
     * calls. The acquired guard proves their copy returned before this ACK. */
    s_wire.rid=rid;s_wire.cancelled=2U;
    if(result==InstallationCaptureResult_Pending){result=InstallationCapture_ProducerStopped();}
    if(result==InstallationCaptureResult_Cancelled){
        if(InstallationCapture_Release()!=InstallationCaptureResult_Ok){return InstallationCaptureResult_Pending;}
        s_wire.active=0U;s_wire.cancelled=1U;
    }
    return result;
}

static void InstallationWire_Status(const char *sid_text,char *out,uint16_t capacity)
{
    uint8_t sid[16];InstallationCaptureStatus status;
    if(InstallationWire_Unhex(sid_text,sid,16U)&&memcmp(sid,s_wire.sid,16U)==0&&
        InstallationCapture_Status(&status)==InstallationCaptureResult_Ok){
        (void)CommonFormat_Print(out,capacity,"OK INSTALL STATUS sid=%s state=%lu reason=%lu cleanup_complete=%lu",
            sid_text,(unsigned long)status.state,(unsigned long)status.reason,(unsigned long)status.cleanup_complete);
    }
}

static uint8_t InstallationWire_Inspection(const InstallationWireTokens *tokens,
    uint8_t count,char *out,uint16_t capacity)
{
    uint32_t cursor;
    if(strcmp(tokens->part[1],"CAPS")==0){
        if(count==2U){
            (void)CommonFormat_Print(out,capacity,"OK INSTALL CAPS maintenance=0.1 supported=1 install_contract=1 face_auto=1 check_only=1 sample_format=1 max_request=191 max_line=511 train_pairs=%u holdout_pairs=%u pair_capacity=4096 offline=%u",
                s_wire.configured?(unsigned int)s_wire.train_pairs:3U,
                s_wire.configured?(unsigned int)s_wire.holdout_pairs:3U,(unsigned int)s_wire.offline);
        }
        return 1U;
    }
    if(strcmp(tokens->part[1],"INFO")==0){
        if(count==4U&&strcmp(tokens->part[2],"0:0")==0&&InstallationWire_U32(tokens->part[3],&cursor)){
            InstallationWire_Info(cursor,out,capacity);
        }
        return 1U;
    }
    return 0U;
}

void SystemInstallationCapture_ExecuteLine(const char *line,char *out,uint16_t capacity,uint64_t now_us)
{
    static const char * const reasons[14]={"OK","DISABLED","BAD_ARGUMENT","BUSY","STALE","CONFLICT","CAPACITY",
        "SOURCE_GAP","SOURCE_TIME","TIMEOUT","PENDING","COMPLETE","CANCELLED","INTERNAL_STATE"};
    char text[192],sid[33],binding[33];InstallationWireTokens tokens;uint16_t i;uint8_t count,parsed_sid[16];
    uint32_t rid=0U;InstallationCaptureResult result=InstallationCaptureResult_Invalid;InstallationCaptureStatus status;
    if(out==NULL||capacity<511U){return;}
    /* All fixed formats below fit 511 bytes. CommonFormat results are unused
     * because admission guarantees that capacity; full-frame TX is checked. */
    (void)CommonFormat_Print(out,capacity,"ERR INSTALL CAPS code=BAD_FORMAT reason=REQUEST");
    if(line==NULL){return;}
    for(i=0U;i<192U;i++){text[i]=line[i];if(line[i]=='\0'){break;}}
    if(i==192U){return;}
    count=InstallationWire_Split(text,&tokens,5U,' ');
    if(count<2U||strcmp(tokens.part[0],"INSTALL")!=0){return;}
    (void)CommonFormat_Print(out,capacity,"ERR INSTALL %s code=BAD_FORMAT reason=REQUEST",tokens.part[1]);
    if(InstallationWire_Inspection(&tokens,count,out,capacity)!=0U){return;}
    if(count==4U&&strcmp(tokens.part[1],"STATUS")==0&&strcmp(tokens.part[3],"STATE:0")==0){
        InstallationWire_Status(tokens.part[2],out,capacity);
        return;
    }
    if(count<4U||!InstallationWire_Unhex(tokens.part[2],parsed_sid,16U)||!InstallationWire_U32(tokens.part[3],&rid)||rid==0U){return;}
    InstallationWire_Hex(sid,parsed_sid,16U);
    if(strcmp(tokens.part[1],"BEGIN")==0&&count==5U){
        result=InstallationWire_Begin(parsed_sid,rid,tokens.part[4],now_us);
        if(result==InstallationCaptureResult_Disabled){
            (void)CommonFormat_Print(out,capacity,"ERR INSTALL BEGIN sid=%s rid=%lu code=UNSUPPORTED reason=SOURCE_QUALIFICATION",sid,(unsigned long)rid);return;
        }
        if(result==InstallationCaptureResult_Ok){(void)CommonFormat_Print(out,capacity,"OK INSTALL BEGIN sid=%s rid=%lu state=FACE_WAIT",sid,(unsigned long)rid);return;}
    }else if(memcmp(parsed_sid,s_wire.sid,16U)!=0){result=InstallationCaptureResult_Stale;
    }else if(strcmp(tokens.part[1],"DO")==0&&count==5U&&strcmp(tokens.part[4],"CANCEL")==0){
        result=InstallationWire_Cancel(parsed_sid,rid,now_us);
        if(result==InstallationCaptureResult_Cancelled){(void)CommonFormat_Print(out,capacity,"OK INSTALL DO sid=%s rid=%lu cleanup_complete=1",sid,(unsigned long)rid);return;}
        if(result==InstallationCaptureResult_Pending){(void)CommonFormat_Print(out,capacity,"PENDING INSTALL DO sid=%s rid=%lu cleanup_complete=0",sid,(unsigned long)rid);return;}
    }else if(strcmp(tokens.part[1],"FACE")==0&&count==5U&&s_wire.active){
        result=InstallationWire_Face(tokens.part[4],rid,now_us);if(result==InstallationCaptureResult_Pending){s_wire.rid=rid;}
    }else if(strcmp(tokens.part[1],"POLL")==0&&count==4U){
        if(s_wire.cancelled!=0U&&s_wire.rid==rid){
            result=InstallationWire_Cancel(parsed_sid,rid,now_us);
            (void)CommonFormat_Print(out,capacity,"%s INSTALL DO sid=%s rid=%lu cleanup_complete=%u",
                result==InstallationCaptureResult_Cancelled?"OK":"PENDING",sid,(unsigned long)rid,
                result==InstallationCaptureResult_Cancelled?1U:0U);return;
        }
        result=InstallationCapture_RequestTouch(parsed_sid,rid,now_us);
        if(result==InstallationCaptureResult_Ok){result=InstallationCapture_Poll(now_us);}
    }
    if((result==InstallationCaptureResult_Pending||result==InstallationCaptureResult_Complete)&&
            InstallationCapture_Status(&status)==InstallationCaptureResult_Ok){
        InstallationWire_Hex(binding,status.binding,15U);
        (void)CommonFormat_Print(out,capacity,"%s INSTALL FACE sid=%s rid=%lu binding=B-%s state=%s train_count=%lu holdout_count=%lu",
            status.state==InstallationCaptureState_Complete?"OK":"PENDING",sid,(unsigned long)rid,binding,
            status.state==InstallationCaptureState_Complete?"COMPLETE":"COLLECTING",(unsigned long)status.train_count,(unsigned long)status.holdout_count);return;
    }
    (void)CommonFormat_Print(out,capacity,"ERR INSTALL %s sid=%s rid=%lu code=%s reason=%s",tokens.part[1],sid,(unsigned long)rid,
        result==InstallationCaptureResult_Busy?"BUSY":result==InstallationCaptureResult_Stale?"STALE":"FAILED",
        (unsigned int)result<14U?reasons[result]:"INTERNAL_STATE");
}

void SystemInstallationCapture_Process(uint64_t now_us)
{
    char line[439];uint16_t length;InstallationCaptureResult result,committed;
    result=InstallationCapture_Poll(now_us);
    if(result!=InstallationCaptureResult_Pending&&result!=InstallationCaptureResult_Complete){return;}
    result=InstallationCapture_EventPeek(line,sizeof(line),&length);
    if(result!=InstallationCaptureResult_Ok){return;}
    committed=InstallationCapture_EventCommit((uint8_t)(SystemConsoleDevice_Write((const uint8_t *)line,length)==SYSTEM_DEVICE_OK));
    if(committed!=InstallationCaptureResult_Ok){InstallationCapture_SourceLost();}
}
