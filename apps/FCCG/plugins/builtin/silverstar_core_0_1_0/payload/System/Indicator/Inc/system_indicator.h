#ifndef __SYSTEM_INDICATOR_H
#define __SYSTEM_INDICATOR_H

#include <stdint.h>

#include "system_device_types.h"
#include "system_indicator_if.h"
#include "system_alignment.h"
#include "system_calibration.h"
#include "system_lifecycle.h"

typedef enum
{
    SYSTEM_INDICATOR_SYSTEM = 0U,
    SYSTEM_INDICATOR_GNSS,
    SYSTEM_INDICATOR_SAFETY,
    SYSTEM_INDICATOR_COUNT
} SystemIndicatorRole;

typedef enum
{
    SYSTEM_INDICATOR_MODE_OFF = 0U,
    SYSTEM_INDICATOR_MODE_ON,
    SYSTEM_INDICATOR_MODE_BLINK_SLOW,
    SYSTEM_INDICATOR_MODE_BLINK_FAST
} SystemIndicatorMode;

void SystemIndicator_Init(void);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemIndicator_ModeSet(
    SystemIndicatorRole role,
    SystemIndicatorMode mode);
SYSTEM_WARN_UNUSED_RESULT SystemDeviceResult SystemIndicator_Notify(
    SystemIndicatorRole role,
    SystemIndicatorMode mode,
    uint64_t duration_us);
void SystemIndicator_Process(void);

/* Pure policy helper kept public for Host tests and future UI/status reuse. */
SystemIndicatorMode SystemIndicator_SystemModeResolve(
    SystemCalibrationState calibration_state,
    uint8_t calibration_ready,
    uint8_t alignment_ready,
    uint8_t system_ready,
    SystemLifecycleState lifecycle_state);
SystemIndicatorMode SystemIndicator_GnssModeResolve(
    SystemDeviceResult health_result,
    uint8_t initialized,
    uint8_t online,
    SystemDeviceResult sample_result,
    uint8_t position_usable);

#endif /* __SYSTEM_INDICATOR_H */
