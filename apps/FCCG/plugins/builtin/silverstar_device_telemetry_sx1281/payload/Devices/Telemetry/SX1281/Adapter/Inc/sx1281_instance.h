#ifndef __SX1281_INSTANCE_H
#define __SX1281_INSTANCE_H

#include <stdint.h>

#include "system_telemetry_transport_if.h"

const char *Sx1281TelemetryInstance_NameGet(uint8_t instance);
SystemDeviceResult Sx1281TelemetryInstance_Init(uint8_t instance);
SystemDeviceResult Sx1281TelemetryInstance_Start(uint8_t instance);
SystemDeviceResult Sx1281TelemetryInstance_Stop(uint8_t instance);
SystemDeviceResult Sx1281TelemetryInstance_Send(
    uint8_t instance, const uint8_t *data, uint16_t length);
SystemDeviceResult Sx1281TelemetryInstance_Receive(
    uint8_t instance, uint8_t *data, uint16_t capacity, uint16_t *length);
SystemDeviceResult Sx1281TelemetryInstance_Process(uint8_t instance);
SystemDeviceResult Sx1281TelemetryInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Sx1281TelemetryInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *mask);
SystemDeviceResult Sx1281TelemetryInstance_HealthGet(
    uint8_t instance, SystemTelemetryHealth *health);
SystemDeviceResult Sx1281TelemetryInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Sx1281TelemetryInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Sx1281TelemetryInstance_MtuGet(
    uint8_t instance, uint16_t *mtu);

#endif /* __SX1281_INSTANCE_H */
