#ifndef __FREERTOSCONFIG_H
#define __FREERTOSCONFIG_H

#include <stdint.h>

#include "freertos_target_config.h"

#define configUSE_PREEMPTION                     1
#define configUSE_TIME_SLICING                    1
#define configSUPPORT_STATIC_ALLOCATION           1
#define configSUPPORT_DYNAMIC_ALLOCATION          0
#define configUSE_IDLE_HOOK                       0
#define configUSE_TICK_HOOK                       0
#define configTICK_RATE_HZ                        ((TickType_t)1000U)
#define configMAX_PRIORITIES                      8U
#define configMINIMAL_STACK_SIZE                  ((configSTACK_DEPTH_TYPE)128U)
#define configMAX_TASK_NAME_LEN                   16U
#define configUSE_TRACE_FACILITY                  0
#define configUSE_16_BIT_TICKS                    0
#define configUSE_MUTEXES                         0
#define configQUEUE_REGISTRY_SIZE                 0U
#define configUSE_RECURSIVE_MUTEXES               0
#define configUSE_COUNTING_SEMAPHORES             0
#define configUSE_PORT_OPTIMISED_TASK_SELECTION   0
#define configUSE_CO_ROUTINES                     0
#define configMAX_CO_ROUTINE_PRIORITIES           1U
#define configUSE_TIMERS                          0
#define configCHECK_FOR_STACK_OVERFLOW            2
#define configUSE_MALLOC_FAILED_HOOK              0

#define INCLUDE_vTaskPrioritySet                  0
#define INCLUDE_uxTaskPriorityGet                 0
#define INCLUDE_vTaskDelete                       0
#define INCLUDE_vTaskSuspend                      0
#define INCLUDE_vTaskDelayUntil                   1
#define INCLUDE_vTaskDelay                        1
#define INCLUDE_xTaskGetSchedulerState            1
#define INCLUDE_uxTaskGetStackHighWaterMark       1
#define INCLUDE_xTaskGetCurrentTaskHandle         0
#define INCLUDE_eTaskGetState                     0

#define configASSERT(expression_) do { \
    if ((expression_) == 0) { \
        taskDISABLE_INTERRUPTS(); \
        for (;;) { } \
    } \
} while (0)

#endif /* __FREERTOSCONFIG_H */

