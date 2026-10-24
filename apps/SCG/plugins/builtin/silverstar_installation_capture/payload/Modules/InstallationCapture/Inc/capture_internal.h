#ifndef __CAPTURE_INTERNAL_H
#define __CAPTURE_INTERNAL_H
#include "installation_capture.h"

typedef struct {
    uint32_t h[8];
    uint64_t bytes;
    uint8_t block[64];
    uint32_t used;
} CaptureSha;
void CaptureSha_Init(CaptureSha *ctx);
void CaptureSha_Byte(CaptureSha *ctx, uint8_t value);
void CaptureSha_Finish(CaptureSha *ctx, uint8_t output[32]);
InstallationCaptureResult CaptureNumber_Write(double value, char output[32], uint16_t *length);

typedef struct {
    InstallationCaptureSnapshot snapshot;
    uint8_t binding[32];
} CaptureFrozen;
typedef struct {
    CaptureFrozen fields;
    uint8_t store_chunk[64];
    uint32_t store_token;
    volatile uint32_t release_token;
    volatile uint32_t dependency_generation;
    uint32_t body_crc;
} CaptureFrozenSpace;

typedef struct {
    uint32_t request_id, expected_generation, total_bytes, offset, crc;
    uint8_t object_sha256[32];
    uint16_t chunk_length;
    uint8_t phase, flags;
} CaptureStoreContext;

typedef enum {
    StoreIdle=0,StoreOpenQueued,StoreOpenIo,StoreStaging,StoreWriteQueued,StoreWriteIo,
    StoreVerifyTemp,StoreReadTempIo,StorePublishQueued,StorePublishIo,
    StoreVerifyFinal,StoreReadFinalIo,StoreCommitQueued,StoreCommitIo,
    StoreComplete,StoreCancelled,StoreFailed,StoreUncertain
} CaptureStorePhase;

typedef struct {
    volatile uint32_t operation_tokens[6];
    CaptureStoreContext store;
} CaptureCoordinator;
typedef struct {
    uint8_t sid[16], face_key[16];
    uint64_t now, started, last_command_us, native_last[2], selected_last[2];
    uint64_t native_sample_us[2];
    uint64_t train_end_us[2], holdout_start_us[2];
    uint32_t rid, face_rid, cancel_rid, next_pair, last_native_sequence[2];
    uint32_t train_last_sequence[2], holdout_first_sequence[2];
    uint16_t train_count, holdout_count, native_modulo[2], attempt, faces_started;
    uint8_t state, reason, mode, stage, face, role;
    uint8_t queue_head, queue_count, active_part, consumer_active;
    uint8_t pending[2], native_seen[2], producer_stopped, cleanup_complete;
} CaptureTransaction;
typedef union { CaptureTransaction fields; uint8_t bytes[256]; } CaptureTransactionSpace;
typedef struct { uint8_t body[2][154]; uint32_t pair; uint8_t committed; } CapturePair;
typedef union { CaptureSha fields; uint8_t bytes[128]; } CaptureShaSpace;
typedef struct {
    volatile uint8_t gate;
    uint8_t enabled, configured, snapshot_failed;
    uint16_t info_bytes;
    uint8_t resource_owner;
    volatile uint8_t producer_lost;
    uint32_t resource_generation, resource_token;
    CaptureCoordinator coordinator;
} CaptureControl;
typedef union { CaptureControl fields; uint8_t bytes[96]; } CaptureControlSpace;
typedef struct {
    CapturePair pairs[2];
    InstallationCaptureSample pending[2];
    CaptureFrozenSpace frozen;
    CaptureTransactionSpace transaction;
    CaptureShaSpace sha;
    uint8_t info_digest[32];
    CaptureControlSpace control;
} CaptureStorage;

/* Private implementation boundary, never exposed to APP/transport/storage.
 * Get is only used while Enter owns the nonblocking guard. No I/O under it. */
uint8_t CaptureState_Enter(void);
void CaptureState_Leave(void);
CaptureStorage *CaptureState_Get(void);
InstallationCaptureResult CaptureState_Claim(uint8_t owner,uint32_t *token);

typedef struct {
    uint16_t position, from, length, capacity;
    uint8_t *output;
    CaptureSha *hash;
    uint8_t failed;
} CaptureSink;

void CaptureInfo_Output(CaptureSink *sink, const CaptureFrozen *frozen, uint8_t include_binding);
void CaptureSink_Byte(CaptureSink *sink, uint8_t value);

#endif
