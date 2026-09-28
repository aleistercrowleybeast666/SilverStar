#ifndef __GROUND_BRIDGE_H
#define __GROUND_BRIDGE_H

#include <stdint.h>

typedef enum
{
    GROUND_BRIDGE_OK = 0U,
    GROUND_BRIDGE_RADIO_ERROR,
    GROUND_BRIDGE_PC_ERROR
} GroundBridgeResult;

GroundBridgeResult GroundBridge_Init(void);
GroundBridgeResult GroundBridge_Process(uint32_t now_ms);

#endif /* __GROUND_BRIDGE_H */
