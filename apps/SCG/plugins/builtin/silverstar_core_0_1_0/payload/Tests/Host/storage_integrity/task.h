#ifndef __TASK_H
#define __TASK_H
#include "FreeRTOS.h"
TickType_t xTaskGetTickCount(void);
BaseType_t xTaskGetSchedulerState(void);
void vTaskDelay(TickType_t ticks);
void Fixture_CriticalEnter(void);
void Fixture_CriticalExit(void);
#define taskENTER_CRITICAL() Fixture_CriticalEnter()
#define taskEXIT_CRITICAL() Fixture_CriticalExit()
#endif
