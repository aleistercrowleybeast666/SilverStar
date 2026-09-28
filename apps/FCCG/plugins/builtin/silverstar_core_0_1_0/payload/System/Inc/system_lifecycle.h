#ifndef __SYSTEM_LIFECYCLE_H
#define __SYSTEM_LIFECYCLE_H

#include <stdint.h>

#include "system_device_types.h"
#include "system_user_config.h"

typedef enum
{
    SYSTEM_STATE_BOOT = 0,
    SYSTEM_STATE_SELF_TEST,
    SYSTEM_STATE_PREFLIGHT,
    SYSTEM_STATE_READY,
    SYSTEM_STATE_FLIGHT,
    SYSTEM_STATE_RECOVERY,
    SYSTEM_STATE_LANDED,
    SYSTEM_STATE_POSTFLIGHT,
    SYSTEM_STATE_FAULT
} SystemLifecycleState;

typedef enum
{
    SYSTEM_START_SOURCE_AIR = 0,
    SYSTEM_START_SOURCE_CONSOLE,
    SYSTEM_START_SOURCE_LOCAL
} SystemStartSource;

typedef enum
{
    SYSTEM_LIFECYCLE_START_OK = 0,
    SYSTEM_LIFECYCLE_START_BUSY,
    SYSTEM_LIFECYCLE_START_NOT_READY,
    SYSTEM_LIFECYCLE_START_LOCKED,
    SYSTEM_LIFECYCLE_START_PREPARE_FAILED,
    SYSTEM_LIFECYCLE_START_ORIGIN_FAILED,
    SYSTEM_LIFECYCLE_START_NAVIGATION_FAILED,
    SYSTEM_LIFECYCLE_START_QUEUE_FAILED,
    SYSTEM_LIFECYCLE_START_INTERNAL_ERROR
} SystemLifecycleStartResult;

typedef enum
{
    SYSTEM_START_REASON_NONE = 0,
    SYSTEM_START_REASON_REQUEST_PENDING,
    SYSTEM_START_REASON_CALIBRATION_REQUIRED,
    SYSTEM_START_REASON_ALIGNMENT_REQUIRED,
    SYSTEM_START_REASON_ATTITUDE_NOT_READY,
    SYSTEM_START_REASON_ATTITUDE_INVALID,
    SYSTEM_START_REASON_ATTITUDE_STALE,
    SYSTEM_START_REASON_SYSTEM_NOT_READY,
    SYSTEM_START_REASON_LOCKED,
    SYSTEM_START_REASON_HOOKS_UNAVAILABLE,
    SYSTEM_START_REASON_PREPARE_FAILED,
    SYSTEM_START_REASON_ORIGIN_FAILED,
    SYSTEM_START_REASON_NAVIGATION_FAILED,
    SYSTEM_START_REASON_QUEUE_FAILED
} SystemLifecycleStartReason;

typedef struct
{
    SystemStartSource source;
    uint32_t request_id;
} SystemLifecycleStartRequest;

typedef struct
{
    SystemStartSource source;
    uint32_t request_id;
    uint64_t timestamp_us;
    SystemLifecycleStartResult result;
    SystemLifecycleStartReason reason;
} SystemLifecycleStartResponse;

typedef struct
{
    SystemLifecycleStartResponse response;
    uint32_t sequence;
    uint8_t valid;
} SystemLifecycleStartDiagnostic;

void SystemLifecycle_Init(void);
SystemLifecycleState SystemLifecycle_GetState(void);
SystemDeviceResult SystemLifecycle_EnterSelfTest(void);
SystemDeviceResult SystemLifecycle_EnterPreflight(void);
SystemDeviceResult SystemLifecycle_EnterReady(void);
SystemDeviceResult SystemLifecycle_EnterRecovery(void);
SystemDeviceResult SystemLifecycle_EnterLanded(void);
SystemDeviceResult SystemLifecycle_EnterPostflight(void);
void SystemLifecycle_EnterFault(uint32_t reason_mask);
uint32_t SystemLifecycle_GetFaultReason(void);
SYSTEM_WARN_UNUSED_RESULT SystemLifecycleStartResult
SystemLifecycle_StartReadinessGet(SystemLifecycleStartReason *reason);
SYSTEM_WARN_UNUSED_RESULT SystemLifecycleStartResult SystemLifecycle_StartTransaction(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemLifecycle_SubmitStart(
    const SystemLifecycleStartRequest *request);
uint8_t SystemLifecycle_TryGetStartResponse(
    SystemLifecycleStartResponse *response);
uint8_t SystemLifecycle_GetLastStartDiagnostic(
    SystemStartSource source,
    SystemLifecycleStartDiagnostic *diagnostic);
const char *SystemLifecycle_StartResultText(SystemLifecycleStartResult result);
const char *SystemLifecycle_StartReasonText(SystemLifecycleStartReason reason);
void SystemLifecycle_Process(void);
uint8_t SystemLifecycle_IsConfigurationLocked(void);

#endif /* __SYSTEM_LIFECYCLE_H */
