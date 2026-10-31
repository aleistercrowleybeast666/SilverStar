#include "system_console_dispatch.h"
#include "system_installation_capture_if.h"
#include "system_log_file.h"
#include "system_time.h"
#include "common_format.h"
#include <stddef.h>
#include <string.h>

SystemConsoleExecuteResult SystemConsole_ExecuteLine(
    const char *line, char *response, uint16_t capacity)
{
    if ((line == NULL) || (response == NULL) || (capacity == 0U))
    { return SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT; }
    if ((SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U) &&
        (strncmp(line, "INSTALL ", 8U) == 0))
    {
        SystemInstallationCapture_ExecuteLine(line, response, capacity,
            SystemTime_GetMonotonicUs());
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    if ((SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U) &&
        (SystemInstallationCapture_CommandBlocked() != 0U))
    {
        (void)CommonFormat_Print(response, capacity,
            "ERR SYSTEM INSTALL code=BUSY reason=INSTALLATION_OWNER");
        return SYSTEM_CONSOLE_EXECUTE_OK;
    }
    if (strncmp(line, "LOGFILE ", 8U) == 0)
    { return SystemLogFile_ExecuteLine(line, response, capacity); }
    return SystemConsole_CommandsExecute(line, response, capacity);
}
