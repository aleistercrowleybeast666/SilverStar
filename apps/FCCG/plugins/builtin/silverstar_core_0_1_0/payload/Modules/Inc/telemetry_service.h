#ifndef __TELEMETRY_SERVICE_H
#define __TELEMETRY_SERVICE_H

#include "system_device_types.h"

typedef enum
{
    TELEMETRY_CAPABILITY_NOT_ACKED = 0U,
    TELEMETRY_CAPABILITY_ACKED,
    TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT
} TelemetryCapabilityState;

typedef struct
{
    uint32_t status_event_drop_count;
    uint32_t ack_queue_failure_count;
    uint32_t start_response_limit_count;
    uint32_t receive_limit_count;
    uint32_t quantization_saturation_count;
    uint32_t capability_tx_count;
    TelemetryCapabilityState capability_state;
    uint8_t capability_acked;
} TelemetryServiceDiagnostics;

SystemDeviceResult TelemetryService_Init(void);
void TelemetryService_Process(void);
void TelemetryService_DiagnosticsGet(TelemetryServiceDiagnostics *diagnostics);

#endif /* __TELEMETRY_SERVICE_H */
