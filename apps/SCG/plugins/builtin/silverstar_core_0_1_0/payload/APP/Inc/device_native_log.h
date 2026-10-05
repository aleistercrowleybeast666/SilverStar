#ifndef __DEVICE_NATIVE_LOG_H
#define __DEVICE_NATIVE_LOG_H

#include <stdint.h>

#include "system_log_policy.h"

void DeviceNativeLog_Process(void);
void DeviceNativeLog_PowerProcess(
    uint64_t now_us, const SystemLogStreamConfig *config);

#endif /* __DEVICE_NATIVE_LOG_H */
