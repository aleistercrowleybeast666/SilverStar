#ifndef __APP_TASK_CONFIG_H
#define __APP_TASK_CONFIG_H

#include "FreeRTOS.h"
#include "system_user_config.h"

/* Allocations are inputs to stack-report, not proof of a sufficient margin.
 * Augmented FP64 estimators need 1 KiB beyond the legacy estimator allocation:
 * H743 Release ESKF20/InEKF20 used 3760 B before exception context (2026-10-25).
 * Debug, callback closure, MSP/ISRs and hardware HWM need separate evidence. */
#define APP_TASK_STACK_DEVICE_WORDS       640U
#define APP_TASK_STACK_INS_WORDS          768U
#define APP_TASK_STACK_ESTIMATOR_WORDS \
    (1024U + 256U * SYSTEM_BUILD_AUGMENTED_ENABLED)
#define APP_TASK_STACK_FLIGHT_WORDS      1024U
#define APP_TASK_STACK_LOGGER_WORDS       768U
#define APP_TASK_STACK_SERIAL_WORDS      1536U
#define APP_TASK_STACK_TELEMETRY_WORDS   1024U

#define APP_PRIORITY_DEVICE       ((UBaseType_t)7U)
#define APP_PRIORITY_INS          ((UBaseType_t)7U)
#define APP_PRIORITY_ESTIMATOR    ((UBaseType_t)6U)
#define APP_PRIORITY_FLIGHT       ((UBaseType_t)5U)
#define APP_PRIORITY_SERIAL       ((UBaseType_t)4U)
#define APP_PRIORITY_LOGGER       ((UBaseType_t)3U)
#define APP_PRIORITY_TELEMETRY    ((UBaseType_t)3U)

#endif /* __APP_TASK_CONFIG_H */
