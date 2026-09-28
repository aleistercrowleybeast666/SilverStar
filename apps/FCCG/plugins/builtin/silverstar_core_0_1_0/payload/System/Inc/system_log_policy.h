#ifndef __SYSTEM_LOG_POLICY_H
#define __SYSTEM_LOG_POLICY_H

#include <stdint.h>

#include "sslog_records.h"
#include "system_device_types.h"

typedef struct
{
    FlightLogRecordType record_type;
    uint8_t enabled;
    uint16_t decimation;
    uint32_t period_us;
    SslogStreamPolicy policy;
} SystemLogStreamConfig;

void SystemLogPolicy_Init(void);
uint16_t SystemLogPolicy_StreamCountGet(void);
SystemDeviceResult SystemLogPolicy_StreamByIndexGet(
    uint16_t index, SystemLogStreamConfig *config);
SystemDeviceResult SystemLogPolicy_StreamGet(
    FlightLogRecordType record_type, SystemLogStreamConfig *config);
SystemDeviceResult SystemLogPolicy_StreamConfigure(
    const SystemLogStreamConfig *config);
uint8_t SystemLogPolicy_IsEnabled(FlightLogRecordType record_type);
uint8_t SystemLogPolicy_ShouldEmit(FlightLogRecordType record_type);
uint8_t SystemLogPolicy_ShouldEmitAt(FlightLogRecordType record_type,
    uint64_t timestamp_us);
void SystemLogPolicy_EmissionTimeRecord(FlightLogRecordType record_type,
    uint64_t timestamp_us);
void SystemLogPolicy_EmissionReset(void);
uint8_t SystemLogPolicy_IsFrozen(void);
void SystemLogPolicy_Freeze(void);
void SystemLogPolicy_UnfreezeForRollback(void);

#endif /* __SYSTEM_LOG_POLICY_H */
