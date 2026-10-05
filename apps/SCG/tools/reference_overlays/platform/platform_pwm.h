#ifndef __PLATFORM_PWM_H
#define __PLATFORM_PWM_H

#include <stdint.h>

#include "platform_types.h"

#define PLATFORM_PWM_DUTY_PERMILLE_MAX 1000U

typedef enum
{
    PLATFORM_PWM_1 = 0,
    PLATFORM_PWM_2,
    PLATFORM_PWM_3,
    PLATFORM_PWM_4,
    PLATFORM_PWM_5,
    PLATFORM_PWM_6,
    PLATFORM_PWM_7,
    PLATFORM_PWM_8,
    PLATFORM_PWM_COUNT = 64
} PlatformPwmId;

typedef enum
{
    PLATFORM_PWM_MODE_1 = 0,
    PLATFORM_PWM_MODE_2
} PlatformPwmMode;

typedef struct
{
    uint32_t frequency_hz;
    uint16_t resolution_bits;
    uint8_t active_high;
    uint8_t started;
    uint16_t duty_permille;
} PlatformPwmDiagnostics;

PlatformResult PlatformPwm_Start(PlatformPwmId id);
PlatformResult PlatformPwm_Stop(PlatformPwmId id);
PlatformResult PlatformPwm_DutyPermilleSet(
    PlatformPwmId id,
    uint16_t duty_permille);
PlatformResult PlatformPwm_SafeInactiveSet(PlatformPwmId id);
PlatformResult PlatformPwm_DiagnosticsGet(
    PlatformPwmId id,
    PlatformPwmDiagnostics *diagnostics);

#endif /* __PLATFORM_PWM_H */
