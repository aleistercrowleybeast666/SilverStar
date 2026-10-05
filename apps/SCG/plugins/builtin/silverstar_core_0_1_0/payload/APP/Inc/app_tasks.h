#ifndef __APP_TASKS_H
#define __APP_TASKS_H

#include "system_task_stack.h"

typedef enum
{
    AppTasksInitResult_Ok = 0,
    AppTasksInitResult_CalibrationInitFailed,
    AppTasksInitResult_BusInitFailed,
    AppTasksInitResult_TaskCreateFailed
} AppTasksInitResult;

AppTasksInitResult AppTasks_Init(void);

void AppTask_Serial(void *argument);
void AppTask_Device(void *argument);
void AppTask_Ins(void *argument);
void AppTask_Estimator(void *argument);
void AppTask_Flight(void *argument);
void AppTask_Telemetry(void *argument);
void AppTask_Logger(void *argument);

#endif /* __APP_TASKS_H */
