#include "system_log_file.h"

#include <stddef.h>
#include <string.h>

#include "common_format.h"

/* Selected by the declarative source graph. Ordinary TF logging is separate. */
void SystemLogFile_StatusPublish(const SystemLogFileSnapshot *snapshot)
{
    (void)snapshot; /* Disabled export retains no diagnostic snapshot. */
}

uint8_t SystemLogFile_StatusGet(SystemLogFileSnapshot *snapshot)
{
    (void)snapshot; /* Unavailable reads leave caller storage unchanged. */
    return 0U;
}

SystemConsoleExecuteResult SystemLogFile_ExecuteLine(
    const char *line, char *response, uint16_t capacity)
{
    if ((line == NULL) || (response == NULL) ||
        (capacity < SYSTEM_LOG_FILE_RESPONSE_SIZE))
    { return SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT; }
    if (strcmp(line, "LOGFILE CAPS") == 0)
    {
        (void)CommonFormat_Print(response, capacity,
            "OK LOGFILE CAPS file_service_version=1 supported=0 max_chunk=64 "
            "delete_supported=0 telemetry_bulk=0");
    }
    else
    {
        (void)CommonFormat_Print(response, capacity,
            "ERR LOGFILE PARSE request=0 code=UNSUPPORTED");
    }
    /* Fixed responses fit the required capacity; CommonFormat is bounded. */
    return SYSTEM_CONSOLE_EXECUTE_OK;
}

SystemLogFileResult SystemLogFile_BinaryResponseGet(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    { return SystemLogFileResult_BadArgument; }
    return SystemLogFileResult_NotReady;
}

void SystemLogFile_Process(uint8_t read_permitted)
{
    (void)read_permitted; /* No request, storage operation or lease to process. */
}

uint8_t SystemLogFile_IsActive(void)
{
    return 0U;
}

SystemLogFileResult SystemLogFile_BatchResponseGet(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    { return SystemLogFileResult_BadArgument; }
    *length = 0U;
    return SystemLogFileResult_NotReady;
}

void SystemLogFile_BatchResponseSent(uint8_t accepted)
{
    (void)accepted; /* Disabled export owns no pending record. */
}
