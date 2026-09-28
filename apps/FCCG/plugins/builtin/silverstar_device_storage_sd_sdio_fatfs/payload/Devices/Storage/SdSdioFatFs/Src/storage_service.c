#include "system_storage_if.h"

#include <stddef.h>
#include <limits.h>
#include <string.h>

#include "project_storage_binding.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "silverstar_assert.h"

#define TF_SDIO_STORAGE_SLOT 0U

static FIL s_file;
static uint16_t s_generation = 1U;
static uint8_t s_initialized;
static uint8_t s_mounted;
static uint8_t s_file_open;
static SystemStorageHealth s_health;

static uint32_t SilverStarStorageService_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SilverStarStorageService_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static SystemDeviceResult SilverStarStorageService_ResultMap(FRESULT result)
{
    if (result == FR_OK) { return SYSTEM_DEVICE_OK; }
    if (result == FR_EXIST) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    if ((result == FR_NOT_READY) || (result == FR_NO_FILESYSTEM))
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if ((result == FR_INVALID_OBJECT) || (result == FR_INVALID_PARAMETER))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    return SYSTEM_DEVICE_IO_ERROR;
}

static uint8_t SilverStarStorageService_HandleValid(
    const SystemStorageFileHandle *handle)
{
    return (uint8_t)((handle != NULL) && s_file_open &&
                     (handle->slot == TF_SDIO_STORAGE_SLOT) &&
                     (handle->generation == s_generation));
}

static SystemDeviceResult SilverStarStorageService_Init(void)
{
    uint32_t primask;

    if (s_initialized != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    (void)memset(&s_file, 0, sizeof(s_file));
    primask = SilverStarStorageService_IrqLock();
    (void)memset(&s_health, 0, sizeof(s_health));
    s_initialized = 1U;
    s_health.initialized = 1U;
    s_health.healthy = 1U;
    SilverStarStorageService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarStorageService_Mount(void)
{
    FRESULT result;
    uint32_t primask;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_mounted <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (s_mounted != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    result = f_mount(&PROJECT_STORAGE_FATFS_OBJECT, PROJECT_STORAGE_FATFS_PATH, 1U);
    if (result != FR_OK)
    {
        primask = SilverStarStorageService_IrqLock();
        s_health.error_count++;
        s_health.healthy = 0U;
        SilverStarStorageService_IrqUnlock(primask);
        return SilverStarStorageService_ResultMap(result);
    }
    primask = SilverStarStorageService_IrqLock();
    s_mounted = 1U;
    s_health.mounted = 1U;
    s_health.healthy = 1U;
    SilverStarStorageService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarStorageService_Open(
    const char *path,
    SystemStorageOpenMode mode,
    SystemStorageFileHandle *handle)
{
    BYTE flags;
    FRESULT result;
    uint32_t primask;

    if ((path == NULL) || (path[0] == '\0') || (handle == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(handle, SystemStorageFileHandle,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    handle->slot = SYSTEM_STORAGE_INVALID_SLOT;
    handle->generation = 0U;
    if (s_mounted == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (s_file_open != 0U) { return SYSTEM_DEVICE_BAD_STATE; }
    if (mode == SYSTEM_STORAGE_OPEN_CREATE_TRUNCATE)
    {
        flags = FA_CREATE_ALWAYS | FA_WRITE;
    }
    else if (mode == SYSTEM_STORAGE_OPEN_CREATE_NEW)
    {
        flags = FA_CREATE_NEW | FA_WRITE;
    }
    else if (mode == SYSTEM_STORAGE_OPEN_APPEND)
    {
        flags = FA_OPEN_APPEND | FA_WRITE;
    }
    else
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }

    result = f_open(&s_file, path, flags);
    if (result == FR_EXIST)
    {
        /* Expected while scanning for the next unique log filename. */
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    if (result != FR_OK)
    {
        primask = SilverStarStorageService_IrqLock();
        s_health.error_count++;
        SilverStarStorageService_IrqUnlock(primask);
        return SilverStarStorageService_ResultMap(result);
    }
    primask = SilverStarStorageService_IrqLock();
    s_file_open = 1U;
    s_health.file_open = 1U;
    SilverStarStorageService_IrqUnlock(primask);
    handle->slot = TF_SDIO_STORAGE_SLOT;
    handle->generation = s_generation;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarStorageService_Write(
    SystemStorageFileHandle *handle,
    const uint8_t *data,
    uint32_t length,
    uint32_t *written_length)
{
    UINT written = 0U;
    FRESULT result;
    uint64_t timestamp_us;
    uint64_t started_us;
    uint32_t primask;

    if (written_length != NULL) { *written_length = 0U; }
    if ((handle == NULL) || (data == NULL) ||
        (written_length == NULL) || (length == 0U) || (length > UINT_MAX))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *written_length = 0U;
    if (SilverStarStorageService_HandleValid(handle) == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    SILVERSTAR_ASSERT_OBJECT(handle, SystemStorageFileHandle,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    /* FatFs accepts arbitrary byte-addressed CPU RAM. The diskio backend
     * owns DMA alignment/accessibility, including partial file sectors. */
    started_us = PlatformTime_Us();
    result = f_write(&s_file, data, (UINT)length, &written);
    *written_length = written;
    timestamp_us = PlatformTime_Us();
    primask = SilverStarStorageService_IrqLock();
    if ((timestamp_us - started_us) > s_health.max_write_latency_us)
    { s_health.max_write_latency_us = timestamp_us - started_us; }
    s_health.bytes_written += written;
    s_health.last_write_timestamp_us = timestamp_us;
    s_health.write_count++;
    if ((result != FR_OK) || (written != length))
    {
        s_health.error_count++;
        s_health.healthy = 0U;
        s_mounted = 0U;
        s_health.mounted = 0U;
        SilverStarStorageService_IrqUnlock(primask);
        return SYSTEM_DEVICE_IO_ERROR;
    }
    SilverStarStorageService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarStorageService_Sync(SystemStorageFileHandle *handle)
{
    FRESULT result;
    uint64_t timestamp_us;
    uint64_t started_us;
    uint32_t primask;

    if (handle == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(handle, SystemStorageFileHandle,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    if (SilverStarStorageService_HandleValid(handle) == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    started_us = PlatformTime_Us();
    result = f_sync(&s_file);
    timestamp_us = PlatformTime_Us();
    primask = SilverStarStorageService_IrqLock();
    if ((timestamp_us - started_us) > s_health.max_sync_latency_us)
    { s_health.max_sync_latency_us = timestamp_us - started_us; }
    s_health.last_sync_timestamp_us = timestamp_us;
    s_health.sync_count++;
    if (result != FR_OK)
    {
        s_health.error_count++;
        s_health.healthy = 0U;
        s_mounted = 0U;
        s_health.mounted = 0U;
    }
    SilverStarStorageService_IrqUnlock(primask);
    return SilverStarStorageService_ResultMap(result);
}

static SystemDeviceResult SilverStarStorageService_Close(SystemStorageFileHandle *handle)
{
    FRESULT result;
    uint32_t primask;

    if (handle == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(handle, SystemStorageFileHandle,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    if (handle->slot == SYSTEM_STORAGE_INVALID_SLOT)
    {
        return SYSTEM_DEVICE_OK;
    }
    if (SilverStarStorageService_HandleValid(handle) == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    result = f_close(&s_file);
    primask = SilverStarStorageService_IrqLock();
    s_file_open = 0U;
    s_health.file_open = 0U;
    s_generation++;
    if (s_generation == 0U) { s_generation = 1U; }
    handle->slot = SYSTEM_STORAGE_INVALID_SLOT;
    handle->generation = 0U;
    if (result != FR_OK)
    {
        s_health.error_count++;
        s_health.healthy = 0U;
    }
    SilverStarStorageService_IrqUnlock(primask);
    return SilverStarStorageService_ResultMap(result);
}

static SystemDeviceResult SilverStarStorageService_GetHealth(SystemStorageHealth *health)
{
    uint32_t primask;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SilverStarStorageService_IrqLock();
    *health = s_health;
    SilverStarStorageService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

const char *SystemStorage_NameGet(void) { return "TF SDIO Storage"; }
SystemDeviceResult SystemStorage_Init(void) { return SilverStarStorageService_Init(); }
SystemDeviceResult SystemStorage_Mount(void) { return SilverStarStorageService_Mount(); }
SystemDeviceResult SystemStorage_Open(const char *path,
                                      SystemStorageOpenMode mode,
                                      SystemStorageFileHandle *handle)
{ return SilverStarStorageService_Open(path, mode, handle); }
SystemDeviceResult SystemStorage_Write(SystemStorageFileHandle *handle,
                                       const uint8_t *data,
                                       uint32_t length,
                                       uint32_t *written_length)
{ return SilverStarStorageService_Write(handle, data, length, written_length); }
SystemDeviceResult SystemStorage_Sync(SystemStorageFileHandle *handle)
{ return SilverStarStorageService_Sync(handle); }
SystemDeviceResult SystemStorage_Close(SystemStorageFileHandle *handle)
{ return SilverStarStorageService_Close(handle); }
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{ return SilverStarStorageService_GetHealth(health); }
