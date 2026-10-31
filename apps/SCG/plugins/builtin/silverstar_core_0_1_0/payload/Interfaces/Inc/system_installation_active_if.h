#ifndef __SYSTEM_INSTALLATION_ACTIVE_IF_H
#define __SYSTEM_INSTALLATION_ACTIVE_IF_H
#include <stdint.h>
#include "system_installation_capture_if.h"

#define SYSTEM_INSTALLATION_ACTIVE_BYTES 228U
typedef enum {
    SystemInstallationActiveResult_Ok=0U,
    SystemInstallationActiveResult_Invalid,
    SystemInstallationActiveResult_Unsupported,
    SystemInstallationActiveResult_Busy,
    SystemInstallationActiveResult_Stale,
    SystemInstallationActiveResult_DependencyChanged,
    SystemInstallationActiveResult_NotReady,
    SystemInstallationActiveResult_Pending,
    SystemInstallationActiveResult_StorageError,
    SystemInstallationActiveResult_NotPresent
} SystemInstallationActiveResult;
typedef struct {
    uint32_t applied_generation, saved_generation, record_crc, request_id;
    /* active means a record exists; valid also requires current dependencies. */
    uint8_t active, saved, loaded, pending, valid;
    SystemInstallationActiveResult result;
} SystemInstallationActiveStatus;

#if (SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U)
/* Qualification is supplied by the native provider integration. The current
 * generated providers return unavailable; target software cannot turn an
 * uploaded flag into source/frame qualification. */
uint8_t SystemInstallationCapture_ActiveQualifiedGet(float R_GA[9]);
uint8_t SystemInstallationActive_ApplyOwnerHeld(uint32_t token);
uint8_t SystemInstallationActive_ReadyForMissionGet(void);
void SystemInstallationActive_LoadFaultSet(SystemInstallationActiveResult result);
SystemInstallationActiveResult SystemInstallationActive_UploadBegin(
    const uint8_t sid[16],uint32_t rid,uint32_t crc,const uint8_t sha256[32],uint64_t now_us);
SystemInstallationActiveResult SystemInstallationActive_UploadWrite(
    const uint8_t sid[16],uint32_t rid,uint16_t offset,const uint8_t *bytes,
    uint16_t length,uint64_t now_us);
SystemInstallationActiveResult SystemInstallationActive_Apply(
    const uint8_t sid[16],uint32_t rid,uint64_t now_us);
SystemInstallationActiveResult SystemInstallationActive_Save(
    const uint8_t sid[16],uint32_t rid,uint64_t now_us);
SystemInstallationActiveResult SystemInstallationActive_Cancel(const uint8_t sid[16],uint32_t rid);
SystemInstallationActiveResult SystemInstallationActive_StatusGet(SystemInstallationActiveStatus *status);
SystemInstallationActiveResult SystemInstallationActive_RecordGet(uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES]);
SystemInstallationActiveResult SystemInstallationActive_SnapshotGet(
    uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *committed_generation);
uint8_t SystemInstallationActive_ExecuteLine(const char *line,char *response,uint16_t capacity,uint64_t now_us);
SystemInstallationActiveResult SystemInstallationActive_PendingGet(
    uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *request_id);
SystemInstallationActiveResult SystemInstallationActive_SaveComplete(uint32_t request_id,
    uint8_t success,uint32_t committed_generation,const uint8_t *readback,uint16_t length);
SystemInstallationActiveResult SystemInstallationActive_StoredLoad(
    const uint8_t *record,uint16_t length,uint32_t committed_generation);
SystemInstallationActiveResult SystemInstallationActive_MagTransform(uint8_t instance,
    uint32_t parent_generation,uint32_t parent_crc,const float input[3],float output[3]);
uint8_t SystemInstallationActive_RuntimeReady(uint32_t generation);
void SystemInstallationActive_Service(uint64_t now_us);
void SystemInstallationActive_DependenciesChanged(void);
#else
static inline uint8_t SystemInstallationActive_ApplyOwnerHeld(uint32_t token) {(void)token;return 0U;}
static inline uint8_t SystemInstallationActive_ReadyForMissionGet(void) {return 1U;}
static inline void SystemInstallationActive_LoadFaultSet(SystemInstallationActiveResult result) {(void)result;}
static inline SystemInstallationActiveResult SystemInstallationActive_PendingGet(uint8_t *record,uint32_t *request_id)
{(void)record;(void)request_id;return SystemInstallationActiveResult_NotReady;}
static inline SystemInstallationActiveResult SystemInstallationActive_StoredLoad(const uint8_t *record,uint16_t length,uint32_t generation)
{(void)record;(void)length;(void)generation;return SystemInstallationActiveResult_Unsupported;}
static inline SystemInstallationActiveResult SystemInstallationActive_SaveComplete(uint32_t request_id,
    uint8_t success,uint32_t generation,const uint8_t *readback,uint16_t length)
{(void)request_id;(void)success;(void)generation;(void)readback;(void)length;return SystemInstallationActiveResult_Unsupported;}
static inline SystemInstallationActiveResult SystemInstallationActive_SnapshotGet(
    uint8_t record[SYSTEM_INSTALLATION_ACTIVE_BYTES],uint32_t *generation)
{ (void)record;(void)generation;return SystemInstallationActiveResult_NotPresent; }
static inline SystemInstallationActiveResult SystemInstallationActive_MagTransform(uint8_t instance,
    uint32_t generation,uint32_t crc,const float input[3],float output[3])
{(void)instance;(void)generation;(void)crc;(void)input;(void)output;return SystemInstallationActiveResult_Unsupported;}
static inline uint8_t SystemInstallationActive_RuntimeReady(uint32_t generation)
{ (void)generation; return 0U; }
static inline void SystemInstallationActive_Service(uint64_t now_us) { (void)now_us; }
static inline void SystemInstallationActive_DependenciesChanged(void) {}
#endif
#endif
