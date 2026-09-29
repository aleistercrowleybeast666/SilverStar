#ifndef __PLATFORM_CRITICAL_H
#define __PLATFORM_CRITICAL_H

#include <stdint.h>

typedef uint32_t PlatformCriticalState;

PlatformCriticalState PlatformCritical_Enter(void);
void PlatformCritical_Exit(PlatformCriticalState state);

#endif /* __PLATFORM_CRITICAL_H */
