#ifndef __SYSTEM_TELEMETRY_TRANSPORT_IF_H
#define __SYSTEM_TELEMETRY_TRANSPORT_IF_H

#include "system_device_types.h"

#define SYSTEM_TELEM_CAP_TX              (1UL << 0)
#define SYSTEM_TELEM_CAP_RX              (1UL << 1)
#define SYSTEM_TELEM_CAP_PACKET_BOUNDARY (1UL << 2)
#define SYSTEM_TELEM_CAP_LINK_CRC        (1UL << 3)
#define SYSTEM_TELEM_CAP_RSSI            (1UL << 4)
#define SYSTEM_TELEM_CAP_SNR             (1UL << 5)

typedef struct
{
    uint64_t last_transmit_timestamp_us;
    uint64_t last_receive_timestamp_us;
    uint32_t transmit_packet_count;
    uint32_t receive_packet_count;
    uint32_t transmit_timeout_count;
    uint32_t transmit_error_count;
    uint32_t receive_error_count;
    uint32_t integrity_error_count;
    int16_t last_rssi_dbm;
    int8_t last_snr_q4;
    uint8_t initialized;
    uint8_t started;
    uint8_t online;
    uint8_t healthy;
} SystemTelemetryHealth;

const char *SystemTelemetry_NameGet(void);
SystemDeviceResult SystemTelemetry_Init(void);
SystemDeviceResult SystemTelemetry_Start(void);
SystemDeviceResult SystemTelemetry_Stop(void);
SystemDeviceResult SystemTelemetry_Send(const uint8_t *data, uint16_t length);
SystemDeviceResult SystemTelemetry_Receive(uint8_t *data,
                                           uint16_t capacity,
                                           uint16_t *length);
void SystemTelemetry_Process(void);
SystemDeviceResult SystemTelemetry_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemTelemetry_CapabilitiesGet(uint32_t *capability_mask);
SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health);
SystemDeviceResult SystemTelemetry_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemTelemetry_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemTelemetry_MtuGet(uint16_t *mtu);

#endif /* __SYSTEM_TELEMETRY_TRANSPORT_IF_H */
