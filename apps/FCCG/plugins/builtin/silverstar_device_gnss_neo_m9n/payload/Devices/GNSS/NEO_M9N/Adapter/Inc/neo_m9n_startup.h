#ifndef __NEO_M9N_STARTUP_H
#define __NEO_M9N_STARTUP_H

#include <stdint.h>

#include "system_device_startup.h"
#include "system_gnss_if.h"

typedef enum
{
    NeoM9nStartupResult_Ok = 0,
    NeoM9nStartupResult_InvalidArgument,
    NeoM9nStartupResult_ControllerError
} NeoM9nStartupResult;

NeoM9nStartupResult NeoM9nStartup_Init(
    uint8_t instance, const SystemGnssConfig *target);
void NeoM9nStartup_Tick(uint8_t instance, uint32_t now_ms);

typedef enum
{
    NeoM9nStartupRecoveryState_None = 0,
    NeoM9nStartupRecoveryState_Backoff,
    NeoM9nStartupRecoveryState_Probing,
    NeoM9nStartupRecoveryState_Exhausted,
    NeoM9nStartupRecoveryState_Rejected,
    NeoM9nStartupRecoveryState_RestoreFailed,
    NeoM9nStartupRecoveryState_NoStream,
    NeoM9nStartupRecoveryState_Ready
} NeoM9nStartupRecoveryState;

/* Native, device-task-owned diagnostics; no AIR/SSLOG layout changes.
 * A restored communication baud does not imply verified identity or READY. */
typedef struct
{
    NeoM9nStartupRecoveryState state;
    uint8_t attempt_count;
    uint8_t last_probe_result;
    uint32_t last_confirmed_baudrate;
    uint32_t backoff_started_ms;
    uint32_t backoff_ms;
} NeoM9nStartupRecoveryDiagnostics;

uint8_t NeoM9nStartup_RecoveryPending(uint8_t instance);
/* Call from the owning device task, or an isolated Host harness. */
NeoM9nStartupResult NeoM9nStartup_RecoveryDiagnosticsGet(
    uint8_t instance, NeoM9nStartupRecoveryDiagnostics *out);
SystemDeviceStartupState NeoM9nStartup_StateGet(uint8_t instance);
SystemDeviceStartupFailure NeoM9nStartup_FailureGet(uint8_t instance);

#endif /* __NEO_M9N_STARTUP_H */
