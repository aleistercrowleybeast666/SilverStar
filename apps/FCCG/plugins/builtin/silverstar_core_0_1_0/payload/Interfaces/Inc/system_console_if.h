#ifndef __SYSTEM_CONSOLE_IF_H
#define __SYSTEM_CONSOLE_IF_H

#include "system_device_types.h"

#define SYSTEM_CONSOLE_CAP_RX     (1UL << 0)
#define SYSTEM_CONSOLE_CAP_TX     (1UL << 1)
#define SYSTEM_CONSOLE_CAP_STREAM (1UL << 2)

typedef struct
{
    uint64_t last_receive_timestamp_us;
    uint64_t last_transmit_timestamp_us;
    uint32_t received_byte_count;
    uint32_t transmitted_byte_count;
    uint32_t receive_overrun_count;
    uint32_t transmit_error_count;
    uint8_t initialized;
    uint8_t started;
    uint8_t online;
    uint8_t healthy;
} SystemConsoleHealth;

const char *SystemConsoleDevice_NameGet(void);
SystemDeviceResult SystemConsoleDevice_Init(void);
SystemDeviceResult SystemConsoleDevice_Start(void);
SystemDeviceResult SystemConsoleDevice_Stop(void);
void SystemConsoleDevice_Process(void);
SystemDeviceResult SystemConsoleDevice_InfoGet(SystemDeviceInfo *info);
SystemDeviceResult SystemConsoleDevice_CapabilitiesGet(
    uint32_t *capability_mask);
SystemDeviceResult SystemConsoleDevice_HealthGet(SystemConsoleHealth *health);
SystemDeviceResult SystemConsoleDevice_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics);
SystemDeviceResult SystemConsoleDevice_SelfTestRun(
    SystemDeviceSelfTestResult *result);
SystemDeviceResult SystemConsoleDevice_Read(uint8_t *data,
                                            uint16_t capacity,
                                            uint16_t *length);
SystemDeviceResult SystemConsoleDevice_Write(const uint8_t *data,
                                             uint16_t length);

#endif /* __SYSTEM_CONSOLE_IF_H */
