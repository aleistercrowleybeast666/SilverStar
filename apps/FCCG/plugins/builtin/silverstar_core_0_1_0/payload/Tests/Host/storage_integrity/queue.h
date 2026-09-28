#ifndef __QUEUE_H
#define __QUEUE_H
#include "FreeRTOS.h"
typedef struct { uint16_t data[16]; unsigned count; unsigned size; unsigned capacity; } StaticQueue_t;
typedef StaticQueue_t *QueueHandle_t;
QueueHandle_t xQueueCreateStatic(UBaseType_t count, UBaseType_t size, uint8_t *storage, StaticQueue_t *control);
BaseType_t xQueueReceive(QueueHandle_t queue, void *data, TickType_t ticks);
BaseType_t xQueueSendFromISR(QueueHandle_t queue, const void *data, BaseType_t *woken);
BaseType_t xQueueReset(QueueHandle_t queue);
#endif
