#ifndef __SYSTEM_TIME_H
#define __SYSTEM_TIME_H

#include <stdint.h>

#include "system_device_types.h"

typedef enum
{
    SYSTEM_UTC_SOURCE_NONE = 0,
    SYSTEM_UTC_SOURCE_GNSS,
    SYSTEM_UTC_SOURCE_EXTERNAL
} SystemUtcSource;

typedef struct
{
    uint64_t monotonic_timestamp_us;
    int64_t utc_time_us;
    uint32_t uncertainty_us;
    SystemUtcSource source;
} SystemUtcMeasurement;

typedef struct
{
    uint64_t monotonic_timestamp_us;
    int64_t utc_time_us;
    uint32_t uncertainty_us;
    SystemUtcSource source;
    uint8_t valid;
} SystemUtcSnapshot;

typedef enum
{
    SYSTEM_MEASUREMENT_TIME_OK = 0,
    SYSTEM_MEASUREMENT_TIME_INVALID
} SystemMeasurementTimeResult;

/* native_mcu_us is already converted by the provider's existing time sync.
 * A trusted epoch bypasses configured receive latency; never subtract twice. */
SystemMeasurementTimeResult SystemTime_MeasurementTimestampResolve(
    uint64_t receive_us, uint64_t native_mcu_us, uint8_t native_trusted,
    uint32_t configured_delay_ms, uint64_t *measurement_us);

SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemTime_Init(void);
uint64_t SystemTime_GetMonotonicUs(void);
uint64_t SystemTime_GetMonotonicUsFromIsr(void);
void SystemTime_MissionStart(uint64_t timestamp_us);
void SystemTime_MissionStop(uint64_t timestamp_us);
void SystemTime_MissionReset(void);
uint8_t SystemTime_IsMissionStarted(void);
uint64_t SystemTime_GetMissionUs(void);
uint8_t SystemTime_GetMissionUsAt(uint64_t monotonic_us,
                                  uint64_t *mission_us);
SystemDeviceResult SystemTime_UpdateUtcMapping(
    const SystemUtcMeasurement *measurement);
SystemDeviceResult SystemTime_GetUtc(SystemUtcSnapshot *snapshot);

#endif /* __SYSTEM_TIME_H */
