#include "serial_task.h"

#include "FreeRTOS.h"
#include "task.h"
#include "system_console.h"
#include "system_console_if.h"
#include "system_user_config.h"

#include "system_mag_calibration_storage_if.h"

void AppTask_Serial(void *argument)
{
    (void)argument;

    for (;;)
    {
        SystemConsoleDevice_Process();
        SystemConsole_Process();
        /* No LoggerTask exists in this build. Serial is the exclusive
         * calibration filesystem owner; one bounded request per iteration. */
        if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED == 0U)
        { SystemMagCalibrationStorage_Service(); }
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
}
