#ifndef __SYSTEM_LOG_FILE_H
#define __SYSTEM_LOG_FILE_H

#include <stdint.h>
#include "system_console.h"

#define SYSTEM_LOG_FILE_CHUNK_SIZE 64U
#define SYSTEM_LOG_FILE_HASH_QUANTUM 512U
#define SYSTEM_LOG_FILE_RESPONSE_SIZE 512U
#define SYSTEM_LOG_FILE_ID_MAX 999999UL

typedef enum
{
    SystemLogFileResult_Ok = 0,
    SystemLogFileResult_Pending,
    SystemLogFileResult_BadArgument,
    SystemLogFileResult_Busy,
    SystemLogFileResult_Locked,
    SystemLogFileResult_NotReady,
    SystemLogFileResult_NotFound,
    SystemLogFileResult_Stale,
    SystemLogFileResult_IoError,
    SystemLogFileResult_Cancelled,
    SystemLogFileResult_Timeout,
    SystemLogFileResult_Unsupported
} SystemLogFileResult;

/* SerialTask only: bounded parse/submit/poll; never accesses FatFs. */
SystemConsoleExecuteResult SystemLogFile_ExecuteLine(
    const char *line, char *response, uint16_t capacity);
/* LoggerTask only: one storage quantum per iteration. */
void SystemLogFile_Process(void);

/* Storage adapter functions below are exclusively called by LoggerTask.
 * Reset closes any private read/enumeration handle; it never touches writer. */
SystemLogFileResult SystemLogFileStorage_Reset(void);
SystemLogFileResult SystemLogFileStorage_Check(uint32_t file_id, uint8_t deleting);
SystemLogFileResult SystemLogFileStorage_List(
    uint32_t cursor, uint32_t *next_cursor, uint32_t *file_id, uint32_t *size);
SystemLogFileResult SystemLogFileStorage_HashBegin(uint32_t file_id, uint32_t *size);
SystemLogFileResult SystemLogFileStorage_HashRead(
    uint8_t data[SYSTEM_LOG_FILE_HASH_QUANTUM], uint16_t *length);
SystemLogFileResult SystemLogFileStorage_Read(
    uint32_t file_id, uint32_t size, uint32_t offset,
    uint8_t data[SYSTEM_LOG_FILE_CHUNK_SIZE], uint16_t *length);

#endif /* __SYSTEM_LOG_FILE_H */
