#ifndef __PLATFORM_CAN_H
#define __PLATFORM_CAN_H

#include <stdint.h>

#include "platform_types.h"

#define PLATFORM_CAN_DATA_MAX_LENGTH 8U
#define PLATFORM_CAN_SEND_TIMEOUT_MAX_MS 60000U

typedef enum
{
    PLATFORM_CAN_1 = 0,
    PLATFORM_CAN_2,
    PLATFORM_CAN_COUNT
} PlatformCanId;

typedef struct
{
    uint32_t identifier;
    uint8_t length;
    uint8_t extended_id;
    uint8_t data[PLATFORM_CAN_DATA_MAX_LENGTH];
} PlatformCanFrame;

typedef struct
{
    uint32_t driver_error;
    uint32_t tx_count;
    uint32_t rx_count;
    uint32_t rx_overrun_count;
    uint32_t bus_off_count;
    uint8_t started;
    uint8_t bus_off;
} PlatformCanDiagnostics;

PlatformResult PlatformCan_Start(PlatformCanId id);
PlatformResult PlatformCan_Stop(PlatformCanId id);
PlatformResult PlatformCan_Send(PlatformCanId id,
                                const PlatformCanFrame *frame,
                                uint32_t timeout_ms);
PlatformResult PlatformCan_ReceivePoll(PlatformCanId id,
                                       PlatformCanFrame *frame);
PlatformResult PlatformCan_DiagnosticsGet(
    PlatformCanId id,
    PlatformCanDiagnostics *diagnostics);

#endif /* __PLATFORM_CAN_H */
