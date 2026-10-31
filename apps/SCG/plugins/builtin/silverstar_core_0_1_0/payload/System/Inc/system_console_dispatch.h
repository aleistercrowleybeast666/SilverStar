#ifndef __SYSTEM_CONSOLE_DISPATCH_H
#define __SYSTEM_CONSOLE_DISPATCH_H

#include "system_console.h"

/* Internal console boundary. The diagnostic parser owns its large temporary
 * views; installation and file-transfer commands never enter that frame. */
SystemConsoleExecuteResult SystemConsole_CommandsExecute(
    const char *line, char *response, uint16_t capacity);

#endif
