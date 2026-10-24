#ifndef __INSTALLATION_CAPTURE_H
#define __INSTALLATION_CAPTURE_H

#include <stdint.h>

/* Isolated template candidate. No driver, scheduler, storage or result apply.
 * Stateful calls use one nonblocking guard. Source owners report every native
 * frame; LatestSampleGet is not a substitute. No rate/configuration writes. */
typedef enum {
    InstallationCaptureResult_Ok = 0, InstallationCaptureResult_Disabled,
    InstallationCaptureResult_Invalid, InstallationCaptureResult_Busy,
    InstallationCaptureResult_Stale, InstallationCaptureResult_Conflict,
    InstallationCaptureResult_Capacity, InstallationCaptureResult_SourceGap,
    InstallationCaptureResult_SourceTime, InstallationCaptureResult_Timeout,
    InstallationCaptureResult_Pending, InstallationCaptureResult_Complete,
    InstallationCaptureResult_Cancelled, InstallationCaptureResult_Failed
} InstallationCaptureResult;

typedef enum {
    InstallationCaptureState_Disabled = 0, InstallationCaptureState_Configured,
    InstallationCaptureState_WaitFace, InstallationCaptureState_Collecting,
    InstallationCaptureState_Draining, InstallationCaptureState_Complete,
    InstallationCaptureState_Cancelling, InstallationCaptureState_Cancelled,
    InstallationCaptureState_Failed
} InstallationCaptureState;

/* Profiles 0/1 are explicitly synthetic IMU/MAG. Profiles 2/3 declare the
 * generated physical endpoints, receive/decode proxy, unknown uncertainty and
 * unknown source epoch/continuity: they can never advertise qualified sync. */
typedef struct {
    uint32_t configuration, reserved_driver, reserved_model, epoch;
    uint32_t stride, intrinsic_generation, uncertainty_us;
    uint16_t descriptor, physical, profile;
    uint8_t instance, time_basis;
    int8_t axis_map[3];
    uint8_t proof_flags;
    uint16_t phase;
} InstallationCaptureSource;

typedef struct {
    InstallationCaptureSource sources[2];
    double accel_bias[3], accel_matrix[9], mag_bias[3], mag_matrix[9], R_GA[9];
    double gyro_bias[3], gyro_scale[3];
    char intrinsic_id[2][32];
    uint8_t boot[16];
    uint32_t configuration, base_generation, maximum_skew_us, maximum_uncertainty_us;
    uint32_t native_health_timeout_us, source_timeout_us, face_timeout_us;
    uint32_t selected_interval_max_us, nominal_output_millihz;
    uint16_t train_pairs, holdout_pairs;
    uint8_t boot_known, R_GA_known, offline, reserved;
    uint8_t gyro_known, gyro_mode;
} InstallationCaptureSnapshot;
/* A real profile with unavailable parent coefficients uses generation 0,
 * intrinsic_id UNKNOWN and canonical zero numeric padding. INFO emits null
 * bias/matrix and cannot pass GSHC's fitting binding gate. Never label default
 * identity coefficients as a recorded calibration. */

typedef struct {
    uint64_t sample_us, receive_us;
    uint32_t sequence, epoch, uncertainty_us, flags;
    float physical[6];
    int32_t raw[6];
    float temperature;
} InstallationCaptureSample;

typedef struct {
    uint32_t state_bytes, frozen_bytes, transaction_bytes, queue_slots;
    uint32_t info_bytes, next_pair, train_count, holdout_count;
    uint32_t state, reason, cleanup_complete, consumer_active;
    uint8_t binding[32], info_sha256[32];
    uint32_t resource_owner, resource_token, resource_generation;
} InstallationCaptureStatus;

/* 1 INSTALL, 2 LOGFILE, 3 MAG_WRITE, 4 CAL, 5 ALIGN, 6 START,
 * 7 CONFIG, 8 CONSOLE, 9 IDLE_STATUS, 10 DIAGNOSTIC.
 * Production callers must be integrated explicitly; this is not an auto hook. */
InstallationCaptureResult InstallationCapture_ResourceClaim(uint8_t owner,uint32_t *token);
InstallationCaptureResult InstallationCapture_ResourceRelease(uint8_t owner,uint32_t token);
/* Typed production coordinator. Roles 2..7 and 11 own reserved token slots.
 * Continuation is only used under the owning controller's existing action
 * lock. Async completion must validate its request/generation before End. */
InstallationCaptureResult InstallationCapture_OperationBegin(uint8_t owner,uint8_t continuation);
InstallationCaptureResult InstallationCapture_OperationEnd(uint8_t owner);
uint8_t InstallationCapture_OperationHeld(uint8_t owner);

InstallationCaptureResult InstallationCapture_Enable(uint8_t enabled);
InstallationCaptureResult InstallationCapture_Configure(const InstallationCaptureSnapshot *snapshot);
InstallationCaptureResult InstallationCapture_InfoRead(uint16_t cursor, uint8_t output[48],
    uint16_t *length, uint16_t *next, uint8_t *end);
InstallationCaptureResult InstallationCapture_Status(InstallationCaptureStatus *status);
InstallationCaptureResult InstallationCapture_Begin(const uint8_t sid[16], uint32_t rid,
    const uint8_t binding[15], uint64_t now_us);
InstallationCaptureResult InstallationCapture_Face(const uint8_t sid[16], uint32_t rid,
    uint8_t mode, uint8_t stage, uint8_t face, uint16_t attempt, uint64_t now_us);
InstallationCaptureResult InstallationCapture_SourcePush(uint8_t role,
    const InstallationCaptureSample *sample, uint64_t now_us);
/* A producer that cannot deliver a frame/proof invalidates publication before
 * the next consumer operation, including when the state guard was busy. */
void InstallationCapture_SourceLost(void);
void InstallationCapture_DependenciesChanged(void);
InstallationCaptureResult InstallationCapture_Poll(uint64_t now_us);
/* Wire POLL/STATUS dispatch validates its sid/rid through this operation.
 * Periodic Poll ticks never refresh a disconnected client's 30 s lease. */
InstallationCaptureResult InstallationCapture_RequestTouch(const uint8_t sid[16],uint32_t rid,uint64_t now_us);
/* Peek reserves one consumer lease. Commit accepts/rejects that exact part;
 * accepted data is already copied by the caller's complete-line TX operation.
 * A successful commit is enqueue acceptance, never hardware delivery proof. */
InstallationCaptureResult InstallationCapture_EventPeek(char *scratch, uint16_t capacity,
    uint16_t *length);
InstallationCaptureResult InstallationCapture_EventCommit(uint8_t accepted);
InstallationCaptureResult InstallationCapture_Cancel(const uint8_t sid[16], uint32_t rid,
    uint64_t now_us);
InstallationCaptureResult InstallationCapture_ProducerStopped(void);
InstallationCaptureResult InstallationCapture_Release(void);
InstallationCaptureResult InstallationCapture_Revoke(void);
/* Scalar conversion and SHA entry points support cross-language golden tests.
 * No allocation, locale, printf or strtod is used by the linked target path. */
InstallationCaptureResult InstallationCapture_Number(double value, char output[32], uint16_t *length);
InstallationCaptureResult InstallationCapture_Hash(const uint8_t *data, uint16_t length, uint8_t output[32]);


#endif
