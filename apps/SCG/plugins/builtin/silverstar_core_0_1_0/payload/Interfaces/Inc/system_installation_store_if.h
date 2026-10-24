#ifndef __SYSTEM_INSTALLATION_STORE_IF_H
#define __SYSTEM_INSTALLATION_STORE_IF_H
#include "system_installation_capture_if.h"

#define SYSTEM_INSTALLATION_STORE_MAX_BYTES 16384U
#define SYSTEM_INSTALLATION_STORE_CHUNK_BYTES 64U

typedef enum {
    SystemInstallationStoreResult_Ok=0, SystemInstallationStoreResult_Pending,
    SystemInstallationStoreResult_Busy, SystemInstallationStoreResult_InvalidArgument,
    SystemInstallationStoreResult_Stale, SystemInstallationStoreResult_DependencyChanged,
    SystemInstallationStoreResult_IntegrityError, SystemInstallationStoreResult_StorageError,
    SystemInstallationStoreResult_CleanupUnconfirmed, SystemInstallationStoreResult_Cancelled,
    SystemInstallationStoreResult_CandidateOnly, SystemInstallationStoreResult_Unsupported,
    SystemInstallationStoreResult_GenerationExhausted
} SystemInstallationStoreResult;

typedef enum {
    SystemInstallationStoreAction_Open=1, SystemInstallationStoreAction_Write,
    SystemInstallationStoreAction_Read, SystemInstallationStoreAction_Publish,
    SystemInstallationStoreAction_Commit
} SystemInstallationStoreAction;

typedef struct {
    SystemInstallationStoreAction action;
    uint32_t request_id,token,expected_generation,total_bytes,offset;
    uint8_t object_sha256[32],binding_sha256[32],data[64];
    uint16_t length;
    uint8_t final_blob;
} SystemInstallationStoreWork;

typedef struct {
    uint32_t request_id,completed_bytes,total_bytes,generation;
    SystemInstallationStoreResult result;
    uint8_t cleanup_complete,candidate_only;
} SystemInstallationStoreStatus;

#if (SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U)
/* Typed software-candidate path. No wire UPLOAD/APPLY/SAVE is enabled. The
 * target's real snapshot is offline=0, which Begin rejects as Unsupported. */
SystemInstallationStoreResult SystemInstallationStore_Begin(const uint8_t sid[16],uint32_t rid,
    uint32_t expected_generation,uint32_t length,const uint8_t sha256[32],const uint8_t binding[32],uint64_t now_us);
SystemInstallationStoreResult SystemInstallationStore_Write(const uint8_t sid[16],uint32_t rid,
    uint32_t offset,const uint8_t *data,uint16_t length,uint64_t now_us);
SystemInstallationStoreResult SystemInstallationStore_Verify(const uint8_t sid[16],uint32_t rid,uint64_t now_us);
SystemInstallationStoreResult SystemInstallationStore_Cancel(const uint8_t sid[16],uint32_t rid,uint64_t now_us);
SystemInstallationStoreResult SystemInstallationStore_Status(const uint8_t sid[16],uint32_t rid,
    uint64_t now_us,SystemInstallationStoreStatus *status);
void SystemInstallationStore_Service(void);

/* Private bridge between the coordinator and the one Logger/TF executor.
 * Work is a bounded copy; its token/rid/phase must still match on completion. */
SystemInstallationStoreResult SystemInstallationStore_WorkTake(uint64_t now_us,SystemInstallationStoreWork *work);
SystemInstallationStoreResult SystemInstallationStore_WorkComplete(const SystemInstallationStoreWork *work,
    SystemInstallationStoreResult result,uint32_t progress,uint32_t generation,uint64_t now_us);
void SystemInstallationStore_CompletionLost(void);
#else
static inline void SystemInstallationStore_Service(void){}
#endif
SystemInstallationStoreResult SystemInstallationStoreStorage_Execute(
    SystemInstallationStoreWork *work,uint32_t *progress,uint32_t *generation);
const char *SystemInstallationStore_ResultText(SystemInstallationStoreResult result);
#endif /* __SYSTEM_INSTALLATION_STORE_IF_H */
