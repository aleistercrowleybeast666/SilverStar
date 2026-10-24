#ifndef __SYSTEM_LOG_FILE_H
#define __SYSTEM_LOG_FILE_H

#include <stdint.h>
#include "system_console.h"

#define SYSTEM_LOG_FILE_CHUNK_SIZE 64U
#define SYSTEM_LOG_FILE_BLOCK_SIZE 512U
#define SYSTEM_LOG_FILE_BATCH_COUNT 4U
#define SYSTEM_LOG_FILE_BLOCK_WIRE_SIZE 565U
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

typedef struct
{
    uint64_t timestamp_us;
    uint32_t sequence;
    uint64_t last_completed_write_us;
    uint32_t completed_writes;
    uint8_t lifecycle;
    uint8_t storage_valid;
    uint8_t mounted;
    uint8_t healthy;
    uint8_t writer_open;
    uint8_t log_fault;
    uint8_t finalization;
    uint8_t valid;
} SystemLogFileSnapshot;

/* LoggerTask publishes only RAM observations; SerialTask never queries disk. */
void SystemLogFile_StatusPublish(const SystemLogFileSnapshot *snapshot);
uint8_t SystemLogFile_StatusGet(SystemLogFileSnapshot *snapshot);

/* SerialTask only: bounded parse/submit/poll; never accesses FatFs. */
SystemConsoleExecuteResult SystemLogFile_ExecuteLine(
    const char *line, char *response, uint16_t capacity);
/* SerialTask only, immediately after ExecuteLine. Ok yields one framed binary
 * POLL response; NotReady means use the normal text response. Never touches TF. */
SystemLogFileResult SystemLogFile_BinaryResponseGet(
    uint8_t *data, uint16_t capacity, uint16_t *length);
/* SerialTask only: negotiated BATCH emits at most four512-byte records.
 * Report complete-frame TX-ring admission immediately after Get, before any
 * other console command. A rejected write retains the immutable record. */
SystemLogFileResult SystemLogFile_BatchResponseGet(
    uint8_t *data, uint16_t capacity, uint16_t *length);
void SystemLogFile_BatchResponseSent(uint8_t accepted);
/* LoggerTask only: at most eight META quanta and a 2000-us elapsed budget.
 * One blocking storage quantum may finish after that budget; this is not WCET. */
/* LoggerTask alone grants permission after finalization, closed sink, no I/O
 * or final-status failure and no boot-disabled logging. A mere close is not
 * permission. Adapter also requires the explicit lifecycle maintenance lease. */
void SystemLogFile_Process(uint8_t read_permitted);
/* LoggerTask only, after Process: active file work/cache needs a short yield. */
uint8_t SystemLogFile_IsActive(void);

/* Storage adapter functions below are exclusively called by LoggerTask.
 * Reset closes any private read/enumeration handle; it never touches writer.
 * Data buffers may reside in CPU-only memory: providers must copy through
 * their owned DMA-accessible bounce sector, never DMA directly to the caller. */
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
SystemLogFileResult SystemLogFileStorage_BlockRead(
    uint32_t file_id, uint32_t size, uint32_t offset,
    uint8_t data[SYSTEM_LOG_FILE_BLOCK_SIZE], uint16_t *length);

#endif /* __SYSTEM_LOG_FILE_H */
