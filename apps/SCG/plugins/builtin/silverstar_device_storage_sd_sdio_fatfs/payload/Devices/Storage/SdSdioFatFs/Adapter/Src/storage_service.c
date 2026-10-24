#include "system_storage_if.h"

#include <stddef.h>
#include <limits.h>
#include <string.h>

#include "project_storage_binding.h"
#include "persistent_storage.h"
#include "system_installation_store_if.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "silverstar_assert.h"

#define TF_SDIO_STORAGE_SLOT 0U
#define TF_SDIO_MISSION_ID_MAX 999999UL
#define TF_SDIO_MISSION_DIRECTORY_SIZE 24U
#define TF_SDIO_MANIFEST_SIZE 20U

static FIL s_file;
static FIL s_object_file;
static uint16_t s_generation = 1U;
static uint8_t s_initialized;
static uint8_t s_mounted;
static uint8_t s_file_open;
static SystemStorageHealth s_health;
static uint32_t s_mission_id;
static uint8_t s_manifest_ready;
/* DAP-only first mount result; UINT32_MAX means f_mount was never called. */
static volatile uint32_t s_first_mount_fresult = UINT32_MAX;
static void SilverStarStorageService_ObjectFaultRecord(void);

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
    s_mission_id = 0U;
    s_manifest_ready = 0U;
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
    if (s_health.initial_medium_unavailable != 0U)
    { return SYSTEM_DEVICE_NOT_READY; }
    result = f_mount(&PROJECT_STORAGE_FATFS_OBJECT, PROJECT_STORAGE_FATFS_PATH, 1U);
    primask = SilverStarStorageService_IrqLock();
    if (s_health.initial_probe_complete == 0U)
    {
        s_first_mount_fresult = (uint32_t)result;
        s_health.initial_probe_complete = 1U;
        s_health.initial_medium_unavailable = (uint8_t)(
            (result == FR_NOT_READY) || (result == FR_NO_FILESYSTEM));
    }
    SilverStarStorageService_IrqUnlock(primask);
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

typedef struct
{
    char path[48];
    char directory_buffer[TF_SDIO_MISSION_DIRECTORY_SIZE];
    const char *directory;
} SilverStarStorageObjectPath;

static SystemDeviceResult SilverStarStorageService_MissionDirectoryBuild(
    uint32_t mission_id, char path[TF_SDIO_MISSION_DIRECTORY_SIZE])
{
    static const char prefix[] = "0:/missions/";
    uint8_t digit;
    if ((mission_id == 0U) || (mission_id > TF_SDIO_MISSION_ID_MAX) ||
        (path == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memcpy(path, prefix, sizeof(prefix) - 1U);
    for (digit = 0U; digit < 6U; digit++)
    {
        path[17U - digit] = (char)('0' + mission_id % 10U);
        mission_id /= 10U;
    }
    path[18] = '\0';
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarStorageService_ObjectPathBuild(
    uint8_t kind, uint8_t instance, uint8_t slot,
    SilverStarStorageObjectPath *object_path)
{
    const char *prefix = NULL;
    uint8_t length=0U;
    if ((instance >= 32U) || (slot > 1U) || (object_path == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(object_path, SilverStarStorageObjectPath,
        SILVERSTAR_ASSERT_MODULE_BOARD);
    switch (kind)
    {
        case PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION:
            object_path->directory = "0:/system/calibration";
            prefix = "0:/system/calibration/mag";
            break;
        case PERSISTENT_STORAGE_OBJECT_DEVICE_CONFIG:
            object_path->directory = "0:/system/device";
            prefix = "0:/system/device/dev";
            break;
        case PERSISTENT_STORAGE_OBJECT_PREFERENCES:
            object_path->directory = "0:/system/preferences";
            prefix = "0:/system/preferences/pre";
            break;
        case PERSISTENT_STORAGE_OBJECT_INSTALLATION_CANDIDATE:
            object_path->directory = "0:/system/install";
            prefix = "0:/system/install/head";
            break;
        case PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT:
            if (SilverStarStorageService_MissionDirectoryBuild(
                    s_mission_id, object_path->directory_buffer) !=
                SYSTEM_DEVICE_OK)
            { return SYSTEM_DEVICE_NOT_READY; }
            object_path->directory = object_path->directory_buffer;
            (void)memcpy(object_path->path,
                object_path->directory_buffer, 18U);
            (void)memcpy(&object_path->path[18], "/snap", 5U);
            length = 23U;
            break;
        default:
            return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (kind != PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT)
    {
        if (prefix == NULL) { return SYSTEM_DEVICE_INTERNAL_ERROR; }
        length = (uint8_t)strlen(prefix);
        (void)memcpy(object_path->path, prefix, length);
    }
    if ((uint32_t)length + 5U > sizeof(object_path->path))
    { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    object_path->path[length] = (char)('0' + instance / 10U);
    object_path->path[length + 1U] = (char)('0' + instance % 10U);
    object_path->path[length + 2U] = '.';
    object_path->path[length + 3U] = (char)('0' + slot);
    object_path->path[length + 4U] = '\0';
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_MissionDirectoryReserve(uint32_t mission_id)
{
    char path[TF_SDIO_MISSION_DIRECTORY_SIZE];
    FRESULT result;
    uint32_t primask;
    if (SilverStarStorageService_MissionDirectoryBuild(
            mission_id, path) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT(s_mounted <= 1U,
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_mission_id <= TF_SDIO_MISSION_ID_MAX,
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (s_mounted == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    result = f_mkdir("0:/missions");
    if ((result != FR_OK) && (result != FR_EXIST))
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SilverStarStorageService_ResultMap(result);
    }
    result = f_mkdir(path);
    if (result == FR_EXIST) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    if (result != FR_OK)
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SilverStarStorageService_ResultMap(result);
    }
    primask = SilverStarStorageService_IrqLock();
    s_mission_id = mission_id;
    s_manifest_ready = 0U;
    SilverStarStorageService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static uint32_t SilverStarStorageService_ManifestCrcGet(
    const uint8_t data[TF_SDIO_MANIFEST_SIZE])
{
    uint32_t crc = 0xFFFFFFFFUL;
    uint8_t index;
    uint8_t bit;
    for (index = 0U; index < TF_SDIO_MANIFEST_SIZE - 4U; index++)
    {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; bit++)
        { crc = (crc >> 1U) ^ ((crc & 1U) ? 0xEDB88320UL : 0UL); }
    }
    return ~crc;
}

static void SilverStarStorageService_ManifestU32Write(
    uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
    data[2] = (uint8_t)(value >> 16U);
    data[3] = (uint8_t)(value >> 24U);
}

static SystemDeviceResult SilverStarStorageService_ManifestWrite(
    const char *path, const uint8_t record[TF_SDIO_MANIFEST_SIZE])
{
    UINT count = 0U;
    FRESULT result = f_open(&s_object_file, path, FA_CREATE_NEW | FA_WRITE);
    FRESULT close_result;
    if (result != FR_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    result = f_write(&s_object_file, record, TF_SDIO_MANIFEST_SIZE, &count);
    if ((result == FR_OK) && (count == TF_SDIO_MANIFEST_SIZE))
    { result = f_sync(&s_object_file); }
    close_result = f_close(&s_object_file);
    return ((result == FR_OK) && (count == TF_SDIO_MANIFEST_SIZE) &&
        (close_result == FR_OK)) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}

static SystemDeviceResult SilverStarStorageService_ManifestVerify(
    const char *path, const uint8_t record[TF_SDIO_MANIFEST_SIZE])
{
    uint8_t readback[TF_SDIO_MANIFEST_SIZE] = {0U};
    UINT count = 0U;
    FRESULT result = f_open(&s_object_file, path, FA_READ);
    FRESULT close_result;
    if (result != FR_OK) { return SYSTEM_DEVICE_IO_ERROR; }
    result = f_read(&s_object_file, readback, sizeof(readback), &count);
    close_result = f_close(&s_object_file);
    return ((result == FR_OK) && (count == sizeof(readback)) &&
        (close_result == FR_OK) &&
        (memcmp(record, readback, sizeof(readback)) == 0)) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_IO_ERROR;
}

SystemDeviceResult SystemStorage_MissionManifestCreate(
    uint32_t profile_id, uint8_t version_major,
    uint8_t version_minor, uint8_t version_patch)
{
    static const char suffix[] = "/manifest";
    char path[TF_SDIO_MISSION_DIRECTORY_SIZE + sizeof(suffix)];
    uint8_t record[TF_SDIO_MANIFEST_SIZE] = {0U};
    uint32_t primask;
    SILVERSTAR_ASSERT(s_mounted <= 1U,
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_mission_id <= TF_SDIO_MISSION_ID_MAX,
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if ((s_mounted == 0U) || (s_mission_id == 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    if (s_manifest_ready != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    if (SilverStarStorageService_MissionDirectoryBuild(
            s_mission_id, path) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memcpy(&path[18], suffix, sizeof(suffix));
    (void)memcpy(record, "SSMF", 4U);
    record[4] = 1U;
    record[5] = version_major;
    record[6] = version_minor;
    record[7] = version_patch;
    SilverStarStorageService_ManifestU32Write(&record[8], s_mission_id);
    SilverStarStorageService_ManifestU32Write(&record[12], profile_id);
    SilverStarStorageService_ManifestU32Write(&record[16],
        SilverStarStorageService_ManifestCrcGet(record));
    if ((SilverStarStorageService_ManifestWrite(path, record) !=
            SYSTEM_DEVICE_OK) ||
        (SilverStarStorageService_ManifestVerify(path, record) !=
            SYSTEM_DEVICE_OK))
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SYSTEM_DEVICE_IO_ERROR;
    }
    primask = SilverStarStorageService_IrqLock();
    s_manifest_ready = 1U;
    SilverStarStorageService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_MissionIdGet(uint32_t *mission_id)
{
    uint32_t primask;
    uint8_t manifest_ready;
    if (mission_id == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SilverStarStorageService_IrqLock();
    *mission_id = s_mission_id;
    manifest_ready = s_manifest_ready;
    SilverStarStorageService_IrqUnlock(primask);
    return ((*mission_id == 0U) || (manifest_ready == 0U)) ?
        SYSTEM_DEVICE_NOT_READY : SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarStorageService_DirectoryEnsure(
    uint8_t kind, const char *directory)
{
    FRESULT result;
    const char *parent = "0:/system";
    if (kind == PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT)
    { parent = "0:/missions"; }
    result = f_mkdir(parent);
    if ((result != FR_OK) && (result != FR_EXIST))
    { return SilverStarStorageService_ResultMap(result); }
    result = f_mkdir(directory);
    if ((result != FR_OK) && (result != FR_EXIST))
    { return SilverStarStorageService_ResultMap(result); }
    return SYSTEM_DEVICE_OK;
}

static void SilverStarStorageService_ObjectFaultRecord(void)
{
    uint32_t primask = SilverStarStorageService_IrqLock();
    s_health.error_count++;
    s_health.healthy = 0U;
    SilverStarStorageService_IrqUnlock(primask);
}

SystemDeviceResult SystemStorage_ObjectSlotRead(
    uint8_t kind, uint8_t instance, uint8_t slot,
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    SilverStarStorageObjectPath object_path;
    FRESULT result;
    FRESULT close_result;
    UINT read_count = 0U;
    UINT extra_count = 0U;
    uint8_t extra;
    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(length, uint16_t,
        SILVERSTAR_ASSERT_MODULE_BOARD);
    SILVERSTAR_ASSERT(s_mounted <= 1U,
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    *length = 0U;
    {
        SystemDeviceResult path_result = SilverStarStorageService_ObjectPathBuild(
            kind, instance, slot, &object_path);
        if (path_result != SYSTEM_DEVICE_OK) { return path_result; }
    }
    if (s_mounted == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    result = f_open(&s_object_file, object_path.path, FA_READ);
    if ((result == FR_NO_FILE) || (result == FR_NO_PATH))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (result != FR_OK)
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SilverStarStorageService_ResultMap(result);
    }
    result = f_read(&s_object_file, data, capacity, &read_count);
    if (result == FR_OK)
    { result = f_read(&s_object_file, &extra, 1U, &extra_count); }
    close_result = f_close(&s_object_file);
    if ((result != FR_OK) || (close_result != FR_OK))
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SYSTEM_DEVICE_IO_ERROR;
    }
    if (extra_count != 0U) { return SYSTEM_DEVICE_OK; }
    *length = (uint16_t)read_count;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_ObjectSlotWrite(
    uint8_t kind, uint8_t instance, uint8_t slot,
    const uint8_t *data, uint16_t length)
{
    SilverStarStorageObjectPath object_path;
    FRESULT result;
    FRESULT close_result;
    UINT written = 0U;
    if ((data == NULL) || (length == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(data, uint8_t,
        SILVERSTAR_ASSERT_MODULE_BOARD);
    SILVERSTAR_ASSERT(s_mounted <= 1U,
        SILVERSTAR_ASSERT_MODULE_BOARD,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    {
        SystemDeviceResult path_result = SilverStarStorageService_ObjectPathBuild(
            kind, instance, slot, &object_path);
        if (path_result != SYSTEM_DEVICE_OK) { return path_result; }
    }
    if (s_mounted == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (SilverStarStorageService_DirectoryEnsure(
            kind, object_path.directory) != SYSTEM_DEVICE_OK)
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SYSTEM_DEVICE_IO_ERROR;
    }
    result = f_open(&s_object_file, object_path.path,
        FA_CREATE_ALWAYS | FA_WRITE);
    if (result != FR_OK)
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SilverStarStorageService_ResultMap(result);
    }
    result = f_write(&s_object_file, data, length, &written);
    if ((result == FR_OK) && (written == length))
    { result = f_sync(&s_object_file); }
    close_result = f_close(&s_object_file);
    if ((result != FR_OK) || (written != length) || (close_result != FR_OK))
    {
        SilverStarStorageService_ObjectFaultRecord();
        return SYSTEM_DEVICE_IO_ERROR;
    }
    return SYSTEM_DEVICE_OK;
}

/* SHA-256 is split into eight 8-character components: valid on short-name
 * FatFs, injective over the full hash, with no caller-supplied path text.
 * Logger owns this adapter and the existing s_object_file/s_record scratch. */
#define INSTALLATION_PATH_BYTES 96U
#define INSTALLATION_HEAD_BYTES 68U
_Static_assert(INSTALLATION_PATH_BYTES>=94U,"bounded SHA path exceeds capacity");

static void InstallationStorage_PathBuild(const uint8_t sha[32],
    uint8_t final_blob,char path[INSTALLATION_PATH_BYTES])
{
    static const char hex[]="0123456789abcdef";
    uint8_t group,index,position=17U;
    (void)memcpy(path,"0:/system/install",17U);
    for(group=0U;group<8U;group++){
        path[position++]='/';
        for(index=0U;index<4U;index++){
            uint8_t value=sha[(uint32_t)group*4U+index];
            path[position++]=hex[value>>4U];path[position++]=hex[value&15U];
        }
    }
    (void)memcpy(&path[position],final_blob?".sic":".tmp",5U);
}

static SystemInstallationStoreResult InstallationStorage_Close(FRESULT operation)
{
    FRESULT closed=f_close(&s_object_file);
    if(closed!=FR_OK){SilverStarStorageService_ObjectFaultRecord();return SystemInstallationStoreResult_CleanupUnconfirmed;}
    if(operation!=FR_OK){SilverStarStorageService_ObjectFaultRecord();return SystemInstallationStoreResult_StorageError;}
    return SystemInstallationStoreResult_Ok;
}

static FRESULT InstallationStorage_DirectoriesEnsure(char path[INSTALLATION_PATH_BYTES])
{
    FRESULT result;uint8_t group,position;char saved;
    result=f_mkdir("0:/system");
    if(result!=FR_OK&&result!=FR_EXIST){return result;}
    result=f_mkdir("0:/system/install");
    if(result!=FR_OK&&result!=FR_EXIST){return result;}
    for(group=0U;group<7U;group++){
        position=(uint8_t)(26U+9U*group);saved=path[position];path[position]='\0';
        result=f_mkdir(path);path[position]=saved;
        if(result!=FR_OK&&result!=FR_EXIST){return result;}
    }
    return FR_OK;
}

static SystemInstallationStoreResult InstallationStorage_Open(
    SystemInstallationStoreWork *work,uint32_t *progress)
{
    char path[INSTALLATION_PATH_BYTES];FILINFO information;FRESULT result;
    SystemInstallationStoreResult closed;
    InstallationStorage_PathBuild(work->object_sha256,1U,path);
    result=f_stat(path,&information);
    if(result==FR_OK){
        if((information.fattrib&AM_DIR)!=0U||information.fsize!=work->total_bytes)
        {return SystemInstallationStoreResult_IntegrityError;}
        *progress=(uint32_t)information.fsize;work->final_blob=1U;return SystemInstallationStoreResult_Ok;
    }
    if(result!=FR_NO_FILE&&result!=FR_NO_PATH){return SystemInstallationStoreResult_StorageError;}
    InstallationStorage_PathBuild(work->object_sha256,0U,path);
    result=InstallationStorage_DirectoriesEnsure(path);
    if(result!=FR_OK){return SystemInstallationStoreResult_StorageError;}
    result=f_open(&s_object_file,path,FA_OPEN_ALWAYS|FA_WRITE);
    if(result!=FR_OK){return SystemInstallationStoreResult_StorageError;}
    *progress=(uint32_t)f_size(&s_object_file);work->final_blob=0U;
    closed=InstallationStorage_Close(FR_OK);
    if(closed!=SystemInstallationStoreResult_Ok){return closed;}
    return (*progress<=work->total_bytes)?SystemInstallationStoreResult_Ok:SystemInstallationStoreResult_IntegrityError;
}

static SystemInstallationStoreResult InstallationStorage_Write(
    SystemInstallationStoreWork *work,uint32_t *progress)
{
    char path[INSTALLATION_PATH_BYTES];UINT written=0U;FRESULT result;
    SystemInstallationStoreResult closed;
    InstallationStorage_PathBuild(work->object_sha256,0U,path);
    result=f_open(&s_object_file,path,FA_WRITE);
    if(result!=FR_OK){return SystemInstallationStoreResult_StorageError;}
    if(f_size(&s_object_file)!=work->offset){
        closed=InstallationStorage_Close(FR_OK);
        return (closed==SystemInstallationStoreResult_Ok)?SystemInstallationStoreResult_IntegrityError:closed;
    }
    result=f_lseek(&s_object_file,work->offset);
    if(result==FR_OK){result=f_write(&s_object_file,work->data,work->length,&written);}
    if(result==FR_OK&&written==work->length){result=f_sync(&s_object_file);}
    closed=InstallationStorage_Close(result);
    if(closed!=SystemInstallationStoreResult_Ok){return closed;}
    if(written!=work->length){return SystemInstallationStoreResult_StorageError;}
    *progress=work->offset+work->length;return SystemInstallationStoreResult_Ok;
}

static SystemInstallationStoreResult InstallationStorage_Read(SystemInstallationStoreWork *work)
{
    char path[INSTALLATION_PATH_BYTES];UINT count=0U;FRESULT result;
    SystemInstallationStoreResult closed;
    InstallationStorage_PathBuild(work->object_sha256,work->final_blob,path);
    result=f_open(&s_object_file,path,FA_READ);
    if(result!=FR_OK){return SystemInstallationStoreResult_StorageError;}
    if(f_size(&s_object_file)!=work->total_bytes){
        closed=InstallationStorage_Close(FR_OK);
        return (closed==SystemInstallationStoreResult_Ok)?SystemInstallationStoreResult_IntegrityError:closed;
    }
    result=f_lseek(&s_object_file,work->offset);
    if(result==FR_OK){result=f_read(&s_object_file,work->data,work->length,&count);}
    closed=InstallationStorage_Close(result);
    if(closed!=SystemInstallationStoreResult_Ok){return closed;}
    return (count==work->length)?SystemInstallationStoreResult_Ok:SystemInstallationStoreResult_IntegrityError;
}

static SystemInstallationStoreResult InstallationStorage_Publish(const SystemInstallationStoreWork *work)
{
    char temporary[INSTALLATION_PATH_BYTES],final[INSTALLATION_PATH_BYTES];
    FILINFO information;FRESULT result;
    InstallationStorage_PathBuild(work->object_sha256,0U,temporary);
    InstallationStorage_PathBuild(work->object_sha256,1U,final);
    result=f_stat(final,&information);
    if(result==FR_OK){return (information.fsize==work->total_bytes&&
        (information.fattrib&AM_DIR)==0U)?SystemInstallationStoreResult_Ok:SystemInstallationStoreResult_IntegrityError;}
    if(result!=FR_NO_FILE&&result!=FR_NO_PATH){return SystemInstallationStoreResult_StorageError;}
    result=f_rename(temporary,final);
    /* The coordinator always verifies the published bytes before head CAS. */
    return (result==FR_OK)?SystemInstallationStoreResult_Ok:SystemInstallationStoreResult_StorageError;
}

static SystemInstallationStoreResult InstallationStorage_Commit(
    const SystemInstallationStoreWork *work,uint32_t *generation)
{
    uint8_t head[INSTALLATION_HEAD_BYTES];uint16_t length=0U;uint32_t current=0U;
    PersistentStorageResult result=PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_INSTALLATION_CANDIDATE,0U,head,sizeof(head),&length,&current);
    if(result!=PERSISTENT_STORAGE_OK&&result!=PERSISTENT_STORAGE_NOT_FOUND)
    {return SystemInstallationStoreResult_CleanupUnconfirmed;}
    if(result==PERSISTENT_STORAGE_OK&&length!=sizeof(head)){return SystemInstallationStoreResult_IntegrityError;}
    if(current!=work->expected_generation){
        if(current==work->expected_generation+1U&&length==sizeof(head)&&
            memcmp(head,work->object_sha256,32U)==0&&memcmp(&head[32],work->binding_sha256,32U)==0&&
            ((uint32_t)head[64]|((uint32_t)head[65]<<8U)|((uint32_t)head[66]<<16U)|((uint32_t)head[67]<<24U))==work->total_bytes)
        {*generation=current;return SystemInstallationStoreResult_Ok;}
        return SystemInstallationStoreResult_DependencyChanged;
    }
    (void)memcpy(head,work->object_sha256,32U);(void)memcpy(&head[32],work->binding_sha256,32U);
    head[64]=(uint8_t)work->total_bytes;head[65]=(uint8_t)(work->total_bytes>>8U);
    head[66]=(uint8_t)(work->total_bytes>>16U);head[67]=(uint8_t)(work->total_bytes>>24U);
    result=PersistentStorage_ObjectWriteAtomic(PERSISTENT_STORAGE_OBJECT_INSTALLATION_CANDIDATE,
        0U,head,sizeof(head),generation);
    if(result==PERSISTENT_STORAGE_GENERATION_EXHAUSTED){return SystemInstallationStoreResult_GenerationExhausted;}
    /* SSOB slot helpers cannot distinguish a close failure from other I/O.
     * Conservatively retain the installation lease on any failed head commit. */
    return (result==PERSISTENT_STORAGE_OK)?SystemInstallationStoreResult_Ok:SystemInstallationStoreResult_CleanupUnconfirmed;
}

SystemInstallationStoreResult SystemInstallationStoreStorage_Execute(
    SystemInstallationStoreWork *work,uint32_t *progress,uint32_t *generation)
{
    if(work==NULL||progress==NULL||generation==NULL||work->token==0U||work->request_id==0U||
        work->total_bytes<64U||work->total_bytes>SYSTEM_INSTALLATION_STORE_MAX_BYTES||
        work->expected_generation==UINT32_MAX||work->final_blob>1U||work->offset>work->total_bytes)
    {return SystemInstallationStoreResult_InvalidArgument;}
    *progress=0U;*generation=0U;
    if(s_mounted==0U||s_file_open!=0U||s_health.healthy==0U){return SystemInstallationStoreResult_StorageError;}
    if((work->action==SystemInstallationStoreAction_Read||work->action==SystemInstallationStoreAction_Write)&&
        (work->length==0U||work->length>64U||work->length>work->total_bytes-work->offset))
    {return SystemInstallationStoreResult_InvalidArgument;}
    switch(work->action){
        case SystemInstallationStoreAction_Open:return InstallationStorage_Open(work,progress);
        case SystemInstallationStoreAction_Write:return InstallationStorage_Write(work,progress);
        case SystemInstallationStoreAction_Read:return InstallationStorage_Read(work);
        case SystemInstallationStoreAction_Publish:return InstallationStorage_Publish(work);
        case SystemInstallationStoreAction_Commit:return InstallationStorage_Commit(work,generation);
        default:return SystemInstallationStoreResult_InvalidArgument;
    }
}
