#ifndef __SYSTEM_STORAGE_IF_H
#define __SYSTEM_STORAGE_IF_H

#include "system_device_types.h"

#define SYSTEM_STORAGE_INVALID_SLOT UINT16_MAX

typedef enum
{
    SYSTEM_STORAGE_OPEN_CREATE_TRUNCATE = 0,
    SYSTEM_STORAGE_OPEN_CREATE_NEW,
    SYSTEM_STORAGE_OPEN_APPEND
} SystemStorageOpenMode;

typedef struct
{
    uint16_t slot;
    uint16_t generation;
} SystemStorageFileHandle;

typedef struct
{
    uint64_t last_write_timestamp_us;
    uint64_t last_sync_timestamp_us;
    uint64_t capacity_bytes;
    uint64_t free_bytes;
    uint32_t write_count;
    uint32_t sync_count;
    uint32_t error_count;
    uint64_t bytes_written;
    uint64_t max_write_latency_us;
    uint64_t max_sync_latency_us;
    uint8_t initialized;
    uint8_t mounted;
    uint8_t file_open;
    uint8_t healthy;
} SystemStorageHealth;

const char *SystemStorage_NameGet(void);
SystemDeviceResult SystemStorage_Init(void);
SystemDeviceResult SystemStorage_Mount(void);
SystemDeviceResult SystemStorage_Open(const char *path,
                                      SystemStorageOpenMode mode,
                                      SystemStorageFileHandle *handle);
SystemDeviceResult SystemStorage_Write(SystemStorageFileHandle *handle,
                                       const uint8_t *data,
                                       uint32_t length,
                                       uint32_t *written_length);
SystemDeviceResult SystemStorage_Sync(SystemStorageFileHandle *handle);
SystemDeviceResult SystemStorage_Close(SystemStorageFileHandle *handle);
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health);

#endif /* __SYSTEM_STORAGE_IF_H */
