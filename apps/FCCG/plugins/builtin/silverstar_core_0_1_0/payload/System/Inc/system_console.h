#ifndef __SYSTEM_CONSOLE_H
#define __SYSTEM_CONSOLE_H

#include <stdint.h>

#include "system_device_types.h"

#define SYSTEM_ENABLE_DEVELOPER_CONSOLE 0U
#define SYSTEM_ENABLE_LEGACY_CONSOLE    0U

#ifndef SYSTEM_CONSOLE_LINE_CAPACITY
#define SYSTEM_CONSOLE_LINE_CAPACITY     192U
#endif
#ifndef SYSTEM_CONSOLE_RESPONSE_CAPACITY
#define SYSTEM_CONSOLE_RESPONSE_CAPACITY 3072U
#endif
#ifndef SYSTEM_CONSOLE_READ_CHUNK
#define SYSTEM_CONSOLE_READ_CHUNK        32U
#endif

typedef enum
{
    SYSTEM_CONSOLE_EXECUTE_OK = 0,
    SYSTEM_CONSOLE_EXECUTE_BAD_ARGUMENT,
    SYSTEM_CONSOLE_EXECUTE_BAD_MODULE,
    SYSTEM_CONSOLE_EXECUTE_BAD_COMMAND,
    SYSTEM_CONSOLE_EXECUTE_UNSUPPORTED,
    SYSTEM_CONSOLE_EXECUTE_LOCKED,
    SYSTEM_CONSOLE_EXECUTE_FAILED
} SystemConsoleExecuteResult;

SystemDeviceResult SystemConsole_Init(void);
void SystemConsole_Process(void);
SystemConsoleExecuteResult SystemConsole_ExecuteLine(const char *line,
                                                     char *response,
                                                     uint16_t capacity);

#endif /* __SYSTEM_CONSOLE_H */
