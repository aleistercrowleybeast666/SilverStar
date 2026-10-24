/* Existing console/lifecycle tests have no filesystem. The dedicated log-file
 * Host fixture compiles the real adapter and exercises its failure boundaries. */
#include "system_log_file.h"
SystemLogFileResult SystemLogFileStorage_Reset(void)
{ return SystemLogFileResult_Ok; }
SystemLogFileResult SystemLogFileStorage_Check(uint32_t file_id, uint8_t deleting)
{ (void)file_id; (void)deleting; return SystemLogFileResult_NotReady; }
SystemLogFileResult SystemLogFileStorage_List(uint32_t cursor, uint32_t *next,
    uint32_t *file_id, uint32_t *size)
{ (void)cursor; (void)next; (void)file_id; (void)size; return SystemLogFileResult_NotReady; }
SystemLogFileResult SystemLogFileStorage_HashBegin(uint32_t id, uint32_t *size)
{ (void)id; (void)size; return SystemLogFileResult_NotReady; }
SystemLogFileResult SystemLogFileStorage_HashRead(
    uint8_t data[SYSTEM_LOG_FILE_HASH_QUANTUM], uint16_t *length)
{ (void)data; (void)length; return SystemLogFileResult_NotReady; }
SystemLogFileResult SystemLogFileStorage_Read(uint32_t id, uint32_t size, uint32_t offset,
    uint8_t data[SYSTEM_LOG_FILE_CHUNK_SIZE], uint16_t *length)
{ (void)id; (void)size; (void)offset; (void)data; (void)length; return SystemLogFileResult_NotReady; }
SystemLogFileResult SystemLogFileStorage_BlockRead(uint32_t id, uint32_t size, uint32_t offset,
    uint8_t data[SYSTEM_LOG_FILE_BLOCK_SIZE], uint16_t *length)
{ (void)id; (void)size; (void)offset; (void)data; (void)length; return SystemLogFileResult_NotReady; }
