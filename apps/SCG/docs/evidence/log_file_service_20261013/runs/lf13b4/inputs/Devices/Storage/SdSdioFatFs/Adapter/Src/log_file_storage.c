#include "system_log_file.h"

#include <stddef.h>
#include <string.h>
#include "project_storage_binding.h"
#include "system_storage_if.h"
#include "system_lifecycle.h"
#include "silverstar_assert.h"

#define LOG_FILE_PATH_SIZE 40U
#define LOG_FILE_DIRECTORY_LIMIT 1000000UL

static FIL s_reader;
static DIR s_directory;
static uint8_t s_reader_open;
static uint8_t s_failed;
static uint8_t s_directory_open;
static uint32_t s_cursor;
static uint32_t s_reader_size;

static SystemLogFileResult LogFileStorage_ResultMap(FRESULT result)
{
    if (result == FR_OK) { return SystemLogFileResult_Ok; }
    if ((result == FR_NO_FILE) || (result == FR_NO_PATH))
    { return SystemLogFileResult_NotFound; }
    if ((result == FR_NOT_READY) || (result == FR_NO_FILESYSTEM))
    { return SystemLogFileResult_NotReady; }
    return SystemLogFileResult_IoError;
}

static void LogFileStorage_PathBuild(uint32_t file_id, char path[LOG_FILE_PATH_SIZE])
{
    uint8_t digit;
    static const char pattern[] = "0:/missions/000000/flight.sslog";
    (void)memcpy(path, pattern, sizeof(pattern));
    for (digit = 0U; digit < 6U; digit++)
    { path[17U - digit] = (char)('0' + file_id % 10U); file_id /= 10U; }
}

SystemLogFileResult SystemLogFileStorage_Check(uint32_t file_id, uint8_t deleting)
{
    SystemLifecycleState lifecycle = SystemLifecycle_GetState();
    SystemStorageHealth health;
    uint32_t current = 0U;
    SystemDeviceResult current_result;
    if (s_failed != 0U) { return SystemLogFileResult_IoError; }
    if (deleting != 0U) { return SystemLogFileResult_Unsupported; }
    if ((lifecycle != SYSTEM_STATE_PREFLIGHT) && (lifecycle != SYSTEM_STATE_READY) &&
        (lifecycle != SYSTEM_STATE_POSTFLIGHT)) { return SystemLogFileResult_Locked; }
    if ((SystemStorage_HealthGet(&health) != SYSTEM_DEVICE_OK) ||
        (health.mounted == 0U) || (health.healthy == 0U))
    { return SystemLogFileResult_NotReady; }
    current_result = SystemStorage_MissionIdGet(&current);
    /* During a failed manifest reservation, current ID is still returned.
     * Never expose the current mission even if its writer is temporarily shut. */
    if ((current_result != SYSTEM_DEVICE_OK) &&
        (current_result != SYSTEM_DEVICE_NOT_READY)) { return SystemLogFileResult_NotReady; }
    if ((file_id != 0U) && (file_id == current)) { return SystemLogFileResult_Locked; }
    return SystemLogFileResult_Ok;
}

SystemLogFileResult SystemLogFileStorage_Reset(void)
{
    FRESULT reader_result = FR_OK;
    FRESULT directory_result = FR_OK;
    if (s_reader_open != 0U) { reader_result = f_close(&s_reader); }
    if (s_directory_open != 0U) { directory_result = f_closedir(&s_directory); }
    s_reader_open = 0U;
    s_directory_open = 0U;
    s_cursor = 0U;
    s_reader_size = 0U;
    if ((reader_result != FR_OK) || (directory_result != FR_OK)) { s_failed = 1U; }
    if (reader_result != FR_OK) { return LogFileStorage_ResultMap(reader_result); }
    return LogFileStorage_ResultMap(directory_result);
}

static uint32_t LogFileStorage_IdParse(const char *name)
{
    uint8_t index;
    uint32_t id = 0U;
    for (index = 0U; index < 6U; index++)
    {
        if ((name[index] < '0') || (name[index] > '9')) { return 0U; }
        id = id * 10U + (uint32_t)(name[index] - '0');
    }
    return (name[6] == '\0') ? id : 0U;
}

static SystemLogFileResult LogFileStorage_ListOpen(uint32_t cursor)
{
    FRESULT result;
    SystemLogFileResult reset;
    if (cursor == 0U)
    {
        reset = SystemLogFileStorage_Reset();
        if (reset != SystemLogFileResult_Ok) { return reset; }
        result = f_opendir(&s_directory, "0:/missions");
        if (result != FR_OK) { return LogFileStorage_ResultMap(result); }
        s_directory_open = 1U;
    }
    if ((s_directory_open == 0U) || (cursor != s_cursor))
    { return SystemLogFileResult_Stale; }
    if (s_cursor >= LOG_FILE_DIRECTORY_LIMIT) { return SystemLogFileResult_IoError; }
    return SystemLogFileResult_Ok;
}

SystemLogFileResult SystemLogFileStorage_List(
    uint32_t cursor, uint32_t *next_cursor, uint32_t *file_id, uint32_t *size)
{
    FILINFO info;
    char path[LOG_FILE_PATH_SIZE];
    FRESULT result;
    SystemLogFileResult ready;
    if ((next_cursor == NULL) || (file_id == NULL) || (size == NULL))
    { return SystemLogFileResult_BadArgument; }
    *file_id = 0U;
    *size = 0U;
    *next_cursor = cursor;
    ready = SystemLogFileStorage_Check(0U, 0U);
    if (ready != SystemLogFileResult_Ok) { return ready; }
    ready = LogFileStorage_ListOpen(cursor);
    if (ready == SystemLogFileResult_NotFound)
    { *next_cursor = 0U; return SystemLogFileResult_Ok; }
    if (ready != SystemLogFileResult_Ok) { return ready; }
    (void)memset(&info, 0, sizeof(info));
    result = f_readdir(&s_directory, &info);
    if (result != FR_OK) { return LogFileStorage_ResultMap(result); }
    if (info.fname[0] == '\0')
    { *next_cursor = 0U; return SystemLogFileStorage_Reset(); }
    s_cursor++;
    *next_cursor = s_cursor;
    if ((info.fattrib & AM_DIR) == 0U) { return SystemLogFileResult_Pending; }
    *file_id = LogFileStorage_IdParse(info.fname);
    if (*file_id == 0U) { return SystemLogFileResult_Pending; }
    ready = SystemLogFileStorage_Check(*file_id, 0U);
    if (ready == SystemLogFileResult_Locked) { return SystemLogFileResult_Pending; }
    if (ready != SystemLogFileResult_Ok) { return ready; }
    LogFileStorage_PathBuild(*file_id, path);
    result = f_stat(path, &info);
    if ((result == FR_NO_FILE) || (result == FR_NO_PATH))
    { return SystemLogFileResult_Pending; }
    if (result != FR_OK) { return LogFileStorage_ResultMap(result); }
    if ((info.fattrib & AM_DIR) != 0U) { return SystemLogFileResult_Pending; }
    *size = (uint32_t)info.fsize;
    return SystemLogFileResult_Ok;
}

SystemLogFileResult SystemLogFileStorage_HashBegin(uint32_t file_id, uint32_t *size)
{
    char path[LOG_FILE_PATH_SIZE];
    FRESULT result;
    SystemLogFileResult ready;
    if ((size == NULL) || (file_id == 0U) || (file_id > SYSTEM_LOG_FILE_ID_MAX))
    { return SystemLogFileResult_BadArgument; }
    if (s_reader_open != 0U) { return SystemLogFileResult_Busy; }
    ready = SystemLogFileStorage_Check(file_id, 0U);
    if (ready != SystemLogFileResult_Ok) { return ready; }
    LogFileStorage_PathBuild(file_id, path);
    result = f_open(&s_reader, path, FA_READ);
    if (result != FR_OK) { return LogFileStorage_ResultMap(result); }
    s_reader_open = 1U;
    s_reader_size = (uint32_t)f_size(&s_reader);
    *size = s_reader_size;
    return SystemLogFileResult_Ok;
}

SystemLogFileResult SystemLogFileStorage_HashRead(
    uint8_t data[SYSTEM_LOG_FILE_HASH_QUANTUM], uint16_t *length)
{
    UINT count = 0U;
    FRESULT result;
    if ((data == NULL) || (length == NULL)) { return SystemLogFileResult_BadArgument; }
    *length = 0U;
    if (s_reader_open == 0U) { return SystemLogFileResult_NotReady; }
    if ((uint32_t)f_size(&s_reader) != s_reader_size) { return SystemLogFileResult_Stale; }
    result = f_read(&s_reader, data, SYSTEM_LOG_FILE_HASH_QUANTUM, &count);
    if (result != FR_OK) { return LogFileStorage_ResultMap(result); }
    SILVERSTAR_ASSERT(count <= SYSTEM_LOG_FILE_HASH_QUANTUM,
        SILVERSTAR_ASSERT_MODULE_BOARD, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    *length = (uint16_t)count;
    return SystemLogFileResult_Ok;
}

SystemLogFileResult SystemLogFileStorage_Read(
    uint32_t file_id, uint32_t size, uint32_t offset,
    uint8_t data[SYSTEM_LOG_FILE_CHUNK_SIZE], uint16_t *length)
{
    uint32_t actual_size = 0U;
    UINT count = 0U;
    UINT expected;
    FRESULT io_result;
    SystemLogFileResult result;
    SystemLogFileResult close_result;
    if ((data == NULL) || (length == NULL) || (offset > size))
    { return SystemLogFileResult_BadArgument; }
    *length = 0U;
    result = SystemLogFileStorage_HashBegin(file_id, &actual_size);
    if (result != SystemLogFileResult_Ok) { return result; }
    if (actual_size != size)
    {
        close_result = SystemLogFileStorage_Reset();
        return (close_result == SystemLogFileResult_Ok) ? SystemLogFileResult_Stale : close_result;
    }
    expected = (size - offset > SYSTEM_LOG_FILE_CHUNK_SIZE) ?
        SYSTEM_LOG_FILE_CHUNK_SIZE : (UINT)(size - offset);
    io_result = f_lseek(&s_reader, offset);
    if (io_result == FR_OK) { io_result = f_read(&s_reader, data, expected, &count); }
    close_result = SystemLogFileStorage_Reset();
    if (io_result != FR_OK) { return LogFileStorage_ResultMap(io_result); }
    if (close_result != SystemLogFileResult_Ok) { return close_result; }
    if (count != expected) { return SystemLogFileResult_Stale; }
    *length = (uint16_t)count;
    return SystemLogFileResult_Ok;
}
