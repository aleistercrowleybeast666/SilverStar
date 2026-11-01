#ifndef __PLATFORM_BOOT_SESSION_H
#define __PLATFORM_BOOT_SESSION_H

#include "platform_types.h"

/* Startup/telemetry owner only. Cached within this boot. A random 32-bit
 * session separates retries, not authentication or global device identity.
 * Failure is explicit: callers must not substitute a constant or tick count. */
PlatformResult PlatformBootSession_Get(uint32_t *session);

#endif /* __PLATFORM_BOOT_SESSION_H */
