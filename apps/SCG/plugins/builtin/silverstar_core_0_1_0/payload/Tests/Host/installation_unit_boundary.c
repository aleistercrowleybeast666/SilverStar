/* Explicit boundary for existing isolated Host units: no active installation
 * record and no qualified native producer. The generated suite also compiles
 * test_installation_active.c with actual owner/wire/CAL/Logger implementation.
 * This file is test-only; it must never enter any target SourceGraph. */
#include "system_installation_active_if.h"
#include "system_installation_store_if.h"
#include <string.h>
void SystemInstallationCapture_ImuObserve(const SystemImuSample *sample,const SystemInstallationCaptureProof *proof,uint64_t now)
{(void)sample;(void)proof;(void)now;}
void SystemInstallationCapture_MagObserve(const SystemMagnetometerSample *sample,const SystemInstallationCaptureProof *proof,uint64_t now)
{(void)sample;(void)proof;(void)now;}
void SystemInstallationCapture_ProviderImu(uint32_t source,uint32_t epoch,uint32_t sequence,
    uint32_t edge,uint64_t time_us,uint8_t valid)
{(void)source;(void)epoch;(void)sequence;(void)edge;(void)time_us;(void)valid;}
void SystemInstallationCapture_ProviderMag(const SystemMagnetometerSample *sample,
    uint64_t trigger,uint64_t available)
{(void)sample;(void)trigger;(void)available;}
void SystemInstallationCapture_Process(uint64_t now){(void)now;}
uint8_t SystemInstallationCapture_CommandBlocked(void){return 0U;}
void SystemInstallationCapture_ExecuteLine(const char *line,char *response,uint16_t capacity,uint64_t now)
{(void)line;(void)now;if(capacity>0U){response[0]='\0';}}
uint8_t SystemInstallationActive_ApplyOwnerHeld(uint32_t token){(void)token;return 0U;}
uint8_t SystemInstallationActive_ReadyForMissionGet(void){return 1U;}
uint8_t SystemInstallationActive_RuntimeReady(uint32_t generation){(void)generation;return 0U;}
void SystemInstallationActive_LoadFaultSet(SystemInstallationActiveResult result){(void)result;}
void SystemInstallationActive_DependenciesChanged(void){}
void SystemInstallationActive_Service(uint64_t now){(void)now;}
SystemInstallationActiveResult SystemInstallationActive_SnapshotGet(uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *generation)
{(void)record;(void)generation;return SystemInstallationActiveResult_NotPresent;}
SystemInstallationActiveResult SystemInstallationActive_PendingGet(uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *request)
{(void)record;(void)request;return SystemInstallationActiveResult_NotReady;}
SystemInstallationActiveResult SystemInstallationActive_StoredLoad(const uint8_t *record,uint16_t length,uint32_t generation)
{(void)record;(void)length;(void)generation;return SystemInstallationActiveResult_Unsupported;}
SystemInstallationActiveResult SystemInstallationActive_SaveComplete(uint32_t request,uint8_t success,uint32_t generation,const uint8_t *record,uint16_t length)
{(void)request;(void)success;(void)generation;(void)record;(void)length;return SystemInstallationActiveResult_Unsupported;}
SystemInstallationActiveResult SystemInstallationActive_MagTransform(uint8_t instance,uint32_t generation,uint32_t crc,const float input[3],float output[3])
{
    (void)instance;(void)generation;(void)crc;
    if(input==NULL||output==NULL){return SystemInstallationActiveResult_Invalid;}
    (void)memcpy(output,input,sizeof(float)*3U);return SystemInstallationActiveResult_Ok;
}

/* This unit fixture has no candidate upload or queued object writes. */
void SystemInstallationStore_Service(void){}
