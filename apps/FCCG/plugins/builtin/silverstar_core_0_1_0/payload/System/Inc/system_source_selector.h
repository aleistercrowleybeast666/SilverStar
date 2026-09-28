#ifndef __SYSTEM_SOURCE_SELECTOR_H
#define __SYSTEM_SOURCE_SELECTOR_H

#include <stdint.h>

#include "system_device_types.h"

#define SYSTEM_SOURCE_SELECTOR_IMU_FRESH_TIMEOUT_US 250000ULL
#define SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT 10U

typedef enum
{
    SYSTEM_SOURCE_CHANGE_REASON_PRESTART_PRIMARY_UNAVAILABLE = 5U,
    SYSTEM_SOURCE_CHANGE_REASON_GNSS_LIVENESS_TIMEOUT = 6U,
    SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_CONSECUTIVE_TX_TIMEOUT = 7U,
    SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_INIT_FAILURE = 8U
} SystemSourceChangeReason;

SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void);
void SystemSourceSelector_PendingEventsFlush(void);
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(
    uint8_t *instance_id);
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(
    uint8_t *instance_id);
SystemDeviceResult SystemSourceSelector_TelemetryActiveInstanceGet(
    uint8_t *instance_id);
uint16_t SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet(void);

#endif /* __SYSTEM_SOURCE_SELECTOR_H */
