#ifndef __FREERTOS_H
#define __FREERTOS_H
#include <stdint.h>
typedef uint32_t TickType_t;
typedef uint32_t UBaseType_t;
typedef int BaseType_t;
#define pdFALSE 0
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))
#define portYIELD_FROM_ISR(value) ((void)(value))
#define taskSCHEDULER_RUNNING 2
#endif
