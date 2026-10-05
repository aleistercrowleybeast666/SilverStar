#ifndef __TASK_H
#define __TASK_H

#include "FreeRTOS.h"

TaskHandle_t xTaskCreateStatic(TaskFunction_t entry, const char *name,
    uint32_t words, void *argument, UBaseType_t priority,
    StackType_t *stack, StaticTask_t *control);
UBaseType_t uxTaskGetStackHighWaterMark(TaskHandle_t task);

void vTaskDelay(TickType_t ticks);

#endif /* __TASK_H */
