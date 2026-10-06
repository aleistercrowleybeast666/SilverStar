#ifndef __NRF24_INSTANCE_H
#define __NRF24_INSTANCE_H
#include "system_telemetry_transport_if.h"

const char *Nrf24TelemetryInstance_NameGet(uint8_t instance);
SystemDeviceResult Nrf24TelemetryInstance_Init(uint8_t instance);
SystemDeviceResult Nrf24TelemetryInstance_Start(uint8_t instance);
SystemDeviceResult Nrf24TelemetryInstance_Stop(uint8_t instance);
SystemDeviceResult Nrf24TelemetryInstance_Send(
    uint8_t instance, const uint8_t *data, uint16_t length);
SystemDeviceResult Nrf24TelemetryInstance_SendControl(uint8_t instance,
    const uint8_t *data, uint16_t length, uint32_t *transaction_id);
SystemDeviceResult Nrf24TelemetryInstance_TxResultGet(uint8_t instance,
    uint32_t transaction_id, uint32_t *age_ms);
SystemDeviceResult Nrf24TelemetryInstance_Receive(
    uint8_t instance, uint8_t *data, uint16_t capacity, uint16_t *length);
SystemDeviceResult Nrf24TelemetryInstance_Process(uint8_t instance);
SystemDeviceResult Nrf24TelemetryInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info);
SystemDeviceResult Nrf24TelemetryInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *mask);
SystemDeviceResult Nrf24TelemetryInstance_HealthGet(
    uint8_t instance, SystemTelemetryHealth *health);
SystemDeviceResult Nrf24TelemetryInstance_IoDiagnosticsGet(
    uint8_t instance, SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult Nrf24TelemetryInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result);
SystemDeviceResult Nrf24TelemetryInstance_MtuGet(
    uint8_t instance, uint16_t *mtu);

#endif /* __NRF24_INSTANCE_H */
