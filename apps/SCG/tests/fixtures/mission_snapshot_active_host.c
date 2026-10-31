/* Actual generated snapshot serializer, synthetic committed-record provider.
 * No physical source qualification or active firmware transaction is modeled. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "mission_snapshot.c"
static SystemInstallationActiveResult s_result;
static uint32_t s_saved_generation;
static uint8_t s_packet[228], s_written[512];
static uint16_t s_written_length;
static unsigned s_write_count;
static PersistentStorageResult s_storage_result;
SystemInstallationActiveResult SystemInstallationActive_SnapshotGet(uint8_t record[228],uint32_t *generation)
{ memcpy(record,s_packet,228);*generation=s_saved_generation;return s_result; }
SystemDeviceResult SystemCalibration_ImuCorrectionGet(SystemCalibrationImuCorrection *value)
{ memset(value,0,sizeof(*value));value->ready=1U;for(unsigned i=0;i<3;i++){value->accel_scale[i]=1.f;value->gyro_scale[i]=1.f;}return SYSTEM_DEVICE_OK; }
uint32_t SystemCalibration_GenerationGet(void) { return 42U; }
uint8_t ProjectMagnetometerInstance_CountGet(void) { return 0U; }
uint32_t SystemMagCalibration_GenerationHashGet(void) { return 0U; }
SystemDeviceResult ProjectDeviceInstance_DescriptorGet(SystemDeviceClass cls,uint8_t instance,SystemDeviceDescriptor *d)
{ (void)cls;(void)instance;(void)d;return SYSTEM_DEVICE_NOT_READY; }
PersistentStorageResult PersistentStorage_ObjectRead(PersistentStorageObjectKind kind,uint8_t instance,uint8_t *data,uint16_t capacity,uint16_t *length,uint32_t *generation)
{ (void)kind;(void)instance;(void)data;(void)capacity;*length=0;*generation=0;return PERSISTENT_STORAGE_NOT_FOUND; }
PersistentStorageResult PersistentStorage_ObjectWriteAtomic(PersistentStorageObjectKind kind,uint8_t instance,const uint8_t *data,uint16_t length,uint32_t *generation)
{ assert(kind==PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT && instance==6U);s_write_count++;memcpy(s_written,data,length);s_written_length=length;*generation=19U;return s_storage_result; }
int main(void)
{
    SystemMissionSnapshotStatus status={0};uint32_t generation=0,hash=0;
    for(unsigned i=0;i<228;i++){s_packet[i]=(uint8_t)i;}
    s_storage_result=PERSISTENT_STORAGE_OK;
    s_result=SystemInstallationActiveResult_NotPresent;
    assert(MissionSnapshot_CalibrationWrite(0,&generation,&hash,&status)==SystemMissionSnapshotResult_Ok);
    assert(s_write_count==1 && s_written_length==76 && s_written[4]==4 && s_written[75]==0);
    s_result=SystemInstallationActiveResult_NotReady;
    assert(MissionSnapshot_CalibrationWrite(0,&generation,&hash,&status)==SystemMissionSnapshotResult_NotReady);
    assert(s_write_count==1);
    s_result=SystemInstallationActiveResult_Ok;
    assert(MissionSnapshot_CalibrationWrite(0,&generation,&hash,&status)==SystemMissionSnapshotResult_NotReady);
    assert(s_write_count==1);
    s_saved_generation=7;
    assert(MissionSnapshot_CalibrationWrite(0,&generation,&hash,&status)==SystemMissionSnapshotResult_Ok);
    assert(s_write_count==2 && s_written_length==312 && s_written[75]==1);
    assert(s_written[76]==7 && s_written[77]==0 && s_written[78]==0 && s_written[79]==0);
    assert(memcmp(&s_written[80],&s_packet[224],4)==0 && memcmp(&s_written[84],s_packet,228)==0);
    assert(hash==MissionSnapshot_HashGet(s_written,s_written_length) && generation==19 && status.calibration_generation==42);
    s_storage_result=PERSISTENT_STORAGE_IO_ERROR;
    assert(MissionSnapshot_CalibrationWrite(0,&generation,&hash,&status)==SystemMissionSnapshotResult_StorageError);
    puts("schema4 exact active bytes; missing, unsaved, zero generation and storage failure preserved");return 0;
}
