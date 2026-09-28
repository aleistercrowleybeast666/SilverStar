#ifndef __SYSTEM_DEVICE_STARTUP_H
#define __SYSTEM_DEVICE_STARTUP_H

#include <stdint.h>

#define SYSTEM_DEVICE_STARTUP_MAX_CANDIDATES 8U

typedef enum
{
    SystemDeviceStartupState_Uninitialized = 0,
    SystemDeviceStartupState_Probing,
    SystemDeviceStartupState_Identified,
    SystemDeviceStartupState_ReadingConfig,
    SystemDeviceStartupState_ApplyingConfig,
    SystemDeviceStartupState_Reconnecting,
    SystemDeviceStartupState_VerifyingConfig,
    SystemDeviceStartupState_WaitingSample,
    SystemDeviceStartupState_Ready,
    SystemDeviceStartupState_Failed
} SystemDeviceStartupState;

typedef enum
{
    SystemDeviceStartupPersistence_None = 0,
    SystemDeviceStartupPersistence_Persistent
} SystemDeviceStartupPersistence;

typedef enum
{
    SystemDeviceStartupStep_Pending = 0,
    SystemDeviceStartupStep_Ok,
    SystemDeviceStartupStep_Failed
} SystemDeviceStartupStepResult;

typedef enum
{
    SystemDeviceStartupResult_Ok = 0,
    SystemDeviceStartupResult_InvalidArgument,
    SystemDeviceStartupResult_CandidateLimit
} SystemDeviceStartupResult;

typedef enum
{
    SystemDeviceStartupFailure_None = 0,
    SystemDeviceStartupFailure_NotPresent,
    SystemDeviceStartupFailure_ConfigRead,
    SystemDeviceStartupFailure_ConfigApply,
    SystemDeviceStartupFailure_Reconnect,
    SystemDeviceStartupFailure_ConfigVerify,
    SystemDeviceStartupFailure_SampleTimeout
} SystemDeviceStartupFailure;

typedef struct
{
    uint32_t baudrate;
    uint32_t protocol;
} SystemDeviceStartupCandidate;

typedef struct
{
    SystemDeviceStartupStepResult (*probe_start)(void *owner,
        const SystemDeviceStartupCandidate *candidate);
    SystemDeviceStartupStepResult (*probe_poll)(void *owner);
    SystemDeviceStartupStepResult (*config_read)(void *owner,
        uint32_t *difference_mask);
    SystemDeviceStartupStepResult (*config_apply)(void *owner,
        uint32_t difference_mask, uint8_t *reconnect_required);
    SystemDeviceStartupStepResult (*reconnect)(void *owner);
    SystemDeviceStartupStepResult (*config_verify)(void *owner);
    SystemDeviceStartupStepResult (*sample_poll)(void *owner);
} SystemDeviceStartupOperations;

typedef struct
{
    SystemDeviceStartupPersistence persistence;
    SystemDeviceStartupCandidate target;
    SystemDeviceStartupCandidate factory;
    const SystemDeviceStartupCandidate *supported_candidates;
    uint8_t supported_candidate_count;
    uint32_t probe_timeout_ms;
    uint32_t stage_timeout_ms;
    uint32_t sample_timeout_ms;
    const SystemDeviceStartupOperations *operations;
    void *owner;
} SystemDeviceStartupConfig;

typedef struct
{
    SystemDeviceStartupState state;
    SystemDeviceStartupFailure failure;
    SystemDeviceStartupCandidate candidates[SYSTEM_DEVICE_STARTUP_MAX_CANDIDATES];
    uint8_t candidate_count;
    uint8_t candidate_index;
    uint8_t probe_started;
    uint8_t reconnect_required;
    uint32_t state_entered_ms;
    uint32_t difference_mask;
    SystemDeviceStartupConfig config;
} SystemDeviceStartup;

SystemDeviceStartupResult SystemDeviceStartup_Init(
    SystemDeviceStartup *startup, const SystemDeviceStartupConfig *config);
void SystemDeviceStartup_Tick(SystemDeviceStartup *startup, uint32_t now_ms);

#endif /* __SYSTEM_DEVICE_STARTUP_H */
