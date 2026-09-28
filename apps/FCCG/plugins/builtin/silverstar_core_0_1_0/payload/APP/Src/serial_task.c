#include "serial_task.h"

#include "FreeRTOS.h"
#include "task.h"
#include "system_console.h"
#include "system_console_if.h"

void AppTask_Serial(void *argument)
{
    (void)argument;

    for (;;)
    {
        SystemConsoleDevice_Process();
        SystemConsole_Process();
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
}
