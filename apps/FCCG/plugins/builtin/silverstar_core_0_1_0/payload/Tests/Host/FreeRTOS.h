#ifndef __FREERTOS_H
#define __FREERTOS_H

#include <stdint.h>

typedef uint32_t TickType_t;
typedef uint32_t StackType_t;
typedef uint32_t UBaseType_t;
typedef struct { uint32_t unused; } StaticTask_t;
typedef StaticTask_t *TaskHandle_t;
typedef void (*TaskFunction_t)(void *argument);

#define pdMS_TO_TICKS(milliseconds_) ((TickType_t)(milliseconds_))

#endif /* __FREERTOS_H */
