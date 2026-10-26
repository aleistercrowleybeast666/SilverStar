#ifndef __TELEMETRY_TM_H
#define __TELEMETRY_TM_H

#include <stdint.h>
#include "project_telemetry_protocol.h"

void TelemetryTm_Init(void);
void TelemetryTm_Observe(uint64_t now_us);
AirBuildResult TelemetryTm_PositionBuild(uint64_t now_us, uint8_t *out, uint8_t capacity, uint8_t *length);
AirBuildResult TelemetryTm_HealthBuild(uint64_t now_us, uint8_t *out, uint8_t capacity, uint8_t *length);

#endif /* __TELEMETRY_TM_H */
