#ifndef __SYSTEM_LIFECYCLE_BACKEND_H
#define __SYSTEM_LIFECYCLE_BACKEND_H

#include "system_device_types.h"

/* Build-time integration symbols supplied by the selected APP target. */
SystemDeviceResult SystemLifecycleBackend_PrepareStart(void);
SystemDeviceResult SystemLifecycleBackend_FreezeOrigins(void);
SystemDeviceResult SystemLifecycleBackend_InitializeNavigation(void);
SystemDeviceResult SystemLifecycleBackend_ResetFlightQueues(void);
void SystemLifecycleBackend_AbortStart(void);

#endif /* __SYSTEM_LIFECYCLE_BACKEND_H */
