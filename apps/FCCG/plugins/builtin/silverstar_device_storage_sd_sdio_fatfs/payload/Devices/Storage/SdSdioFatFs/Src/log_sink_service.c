#include "system_log_sink_if.h"

#include <stddef.h>
#include <string.h>

#include "platform_time.h"
#include "silverstar_assert.h"
#include "system_user_config.h"
#include "system_storage_if.h"

#define TF_LOG_PATH_SIZE 16U

typedef struct
{
    SystemStorageFileHandle file;
    char path[TF_LOG_PATH_SIZE];
    SystemLogSinkHealth health;
    uint8_t file_selected;
} SilverStarLogSinkServiceRuntime;

static SilverStarLogSinkServiceRuntime s_sink;

static void SilverStarLogSinkService_PathBuild(uint16_t index, char path[TF_LOG_PATH_SIZE])
{
    static const char prefix[] = "0:/SS";
    static const char suffix[] = ".BIN";

    (void)memset(path, 0, TF_LOG_PATH_SIZE);
    (void)memcpy(path, prefix, sizeof(prefix) - 1U);
    path[5] = (char)('0' + ((index / 1000U) % 10U));
    path[6] = (char)('0' + ((index / 100U) % 10U));
    path[7] = (char)('0' + ((index / 10U) % 10U));
    path[8] = (char)('0' + (index % 10U));
    (void)memcpy(&path[9], suffix, sizeof(suffix));
}

static SystemDeviceResult SilverStarLogSinkService_Init(void)
{
    SystemDeviceResult result;

    if (s_sink.health.initialized != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    (void)memset(&s_sink, 0, sizeof(s_sink));
    s_sink.file.slot = SYSTEM_STORAGE_INVALID_SLOT;
    result = SystemStorage_Init();
    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        s_sink.health.error_count++;
        return result;
    }
    s_sink.health.initialized = 1U;
    s_sink.health.healthy = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarLogSinkService_OpenSelected(void)
{
    SystemDeviceResult result;

    result = SystemStorage_Mount();
    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        return result;
    }
    if (s_sink.file_selected != 0U)
    {
        return SystemStorage_Open(s_sink.path,
                                  SYSTEM_STORAGE_OPEN_APPEND,
                                  &s_sink.file);
    }
    return SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult SilverStarLogSinkService_NewFileOpen(void)
{
    uint16_t index;
    SystemDeviceResult result;

    SILVERSTAR_ASSERT(s_sink.file_selected == 0U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_sink.health.session_active == 0U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    result = SystemStorage_Mount();
    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_ALREADY_MATCHED))
    {
        s_sink.health.error_count++;
        s_sink.health.healthy = 0U;
        return result;
    }
    for (index = 0U; index <= SYSTEM_LOG_FILE_INDEX_MAX; index++)
    {
        SilverStarLogSinkService_PathBuild(index, s_sink.path);
        result = SystemStorage_Open(s_sink.path,
                                    SYSTEM_STORAGE_OPEN_CREATE_NEW,
                                    &s_sink.file);
        if (result == SYSTEM_DEVICE_ALREADY_MATCHED) { continue; }
        if (result != SYSTEM_DEVICE_OK)
        {
            s_sink.health.error_count++;
            s_sink.health.healthy = 0U;
            return result;
        }
        s_sink.file_selected = 1U;
        s_sink.health.session_active = 1U;
        s_sink.health.healthy = 1U;
        return SYSTEM_DEVICE_OK;
    }
    s_sink.health.error_count++;
    s_sink.health.healthy = 0U;
    return SYSTEM_DEVICE_INTERNAL_ERROR;
}

static SystemDeviceResult SilverStarLogSinkService_BeginSession(
    const SystemLogSessionInfo *session)
{
    SystemDeviceResult result;

    if (session == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(session, SystemLogSessionInfo,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    if (s_sink.health.initialized == 0U)
    {
        result = SilverStarLogSinkService_Init();
        if ((result != SYSTEM_DEVICE_OK) &&
            (result != SYSTEM_DEVICE_ALREADY_MATCHED))
        {
            return result;
        }
    }
    if (s_sink.health.session_active != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    if (s_sink.file_selected != 0U)
    {
        result = SilverStarLogSinkService_OpenSelected();
        if (result == SYSTEM_DEVICE_OK)
        {
            s_sink.health.session_active = 1U;
            s_sink.health.healthy = 1U;
        }
        return result;
    }
    return SilverStarLogSinkService_NewFileOpen();
}

static SystemDeviceResult SilverStarLogSinkService_Write(const uint8_t *data,
                                               uint32_t length,
                                               uint32_t *written_length)
{
    SystemDeviceResult result;
    uint64_t now_us;

    if (written_length != NULL) { *written_length = 0U; }
    if ((data == NULL) || (written_length == NULL) || (length == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(data, uint8_t, SILVERSTAR_ASSERT_MODULE_BOARD);
    if (s_sink.health.session_active == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemStorage_Write(&s_sink.file, data, length, written_length);
    now_us = PlatformTime_Us();
    s_sink.health.last_write_timestamp_us = now_us;
    s_sink.health.write_count++;
    s_sink.health.bytes_written += *written_length;
    if ((result != SYSTEM_DEVICE_OK) || (*written_length != length))
    {
        s_sink.health.error_count++;
        s_sink.health.healthy = 0U;
    }
    return result;
}

static SystemDeviceResult SilverStarLogSinkService_Flush(void)
{
    SystemDeviceResult result;

    if (s_sink.health.session_active == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemStorage_Sync(&s_sink.file);
    s_sink.health.last_flush_timestamp_us = PlatformTime_Us();
    s_sink.health.flush_count++;
    if (result != SYSTEM_DEVICE_OK)
    {
        s_sink.health.error_count++;
        s_sink.health.healthy = 0U;
    }
    return result;
}

static SystemDeviceResult SilverStarLogSinkService_EndSession(void)
{
    SystemDeviceResult sync_result = SYSTEM_DEVICE_OK;
    SystemDeviceResult close_result = SYSTEM_DEVICE_OK;

    if (s_sink.health.session_active != 0U)
    {
        sync_result = SystemStorage_Sync(&s_sink.file);
        close_result = SystemStorage_Close(&s_sink.file);
    }
    s_sink.health.session_active = 0U;
    s_sink.file.slot = SYSTEM_STORAGE_INVALID_SLOT;
    if ((sync_result != SYSTEM_DEVICE_OK) || (close_result != SYSTEM_DEVICE_OK))
    {
        s_sink.health.error_count++;
        s_sink.health.healthy = 0U;
        return SYSTEM_DEVICE_IO_ERROR;
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarLogSinkService_GetHealth(SystemLogSinkHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_sink.health;
    return SYSTEM_DEVICE_OK;
}

const char *SystemLogSink_NameGet(void) { return "TF/SDIO file log sink"; }
SystemDeviceResult SystemLogSink_Init(void) { return SilverStarLogSinkService_Init(); }
SystemDeviceResult SystemLogSink_SessionBegin(
    const SystemLogSessionInfo *session)
{ return SilverStarLogSinkService_BeginSession(session); }
SystemDeviceResult SystemLogSink_Write(const uint8_t *data,
                                       uint32_t length,
                                       uint32_t *written_length)
{ return SilverStarLogSinkService_Write(data, length, written_length); }
SystemDeviceResult SystemLogSink_Flush(void) { return SilverStarLogSinkService_Flush(); }
SystemDeviceResult SystemLogSink_SessionEnd(void)
{ return SilverStarLogSinkService_EndSession(); }
SystemDeviceResult SystemLogSink_HealthGet(SystemLogSinkHealth *health)
{ return SilverStarLogSinkService_GetHealth(health); }
