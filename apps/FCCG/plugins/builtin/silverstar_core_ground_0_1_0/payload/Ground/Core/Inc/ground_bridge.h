#ifndef __GROUND_BRIDGE_H
#define __GROUND_BRIDGE_H

#include <stdint.h>

typedef enum
{
    GROUND_BRIDGE_OK = 0U,
    GROUND_BRIDGE_RADIO_ERROR,
    GROUND_BRIDGE_PC_ERROR
} GroundBridgeResult;

typedef struct
{
    uint32_t pc_write_busy_count;
    uint32_t pc_write_error_count;
    uint32_t pc_rx_overflow_count;
    uint8_t pc_queued_frames;
} GroundBridgeDiagnostics;

GroundBridgeResult GroundBridge_Init(void);
GroundBridgeResult GroundBridge_Process(uint32_t now_ms);
GroundBridgeResult GroundBridge_DiagnosticsGet(
    GroundBridgeDiagnostics *diagnostics);

#endif /* __GROUND_BRIDGE_H */
