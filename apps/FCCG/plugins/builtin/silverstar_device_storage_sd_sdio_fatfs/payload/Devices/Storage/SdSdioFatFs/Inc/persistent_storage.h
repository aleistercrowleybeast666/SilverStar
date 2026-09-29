#ifndef __PERSISTENT_STORAGE_H
#define __PERSISTENT_STORAGE_H

#include <stdint.h>

#include "system_storage_if.h"

#define PERSISTENT_STORAGE_OBJECT_MAX_BYTES 512U

typedef enum
{
    PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION = 1U,
    PERSISTENT_STORAGE_OBJECT_DEVICE_CONFIG,
    PERSISTENT_STORAGE_OBJECT_PREFERENCES,
    PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT
} PersistentStorageObjectKind;

typedef enum
{
    PERSISTENT_STORAGE_OK = 0U,
    PERSISTENT_STORAGE_NOT_FOUND,
    PERSISTENT_STORAGE_INVALID_ARGUMENT,
    PERSISTENT_STORAGE_TOO_LARGE,
    PERSISTENT_STORAGE_NOT_READY,
    PERSISTENT_STORAGE_IO_ERROR,
    PERSISTENT_STORAGE_VERIFY_FAILED,
    PERSISTENT_STORAGE_GENERATION_EXHAUSTED
} PersistentStorageResult;

PersistentStorageResult PersistentStorage_ObjectRead(
    PersistentStorageObjectKind kind, uint8_t instance,
    uint8_t *data, uint16_t capacity, uint16_t *length,
    uint32_t *generation);
PersistentStorageResult PersistentStorage_ObjectWriteAtomic(
    PersistentStorageObjectKind kind, uint8_t instance,
    const uint8_t *data, uint16_t length, uint32_t *generation);

PersistentStorageResult PersistentStorage_StreamOpen(
    const char *path, SystemStorageOpenMode mode,
    SystemStorageFileHandle *handle);
PersistentStorageResult PersistentStorage_StreamWrite(
    SystemStorageFileHandle *handle, const uint8_t *data,
    uint32_t length, uint32_t *written_length);
PersistentStorageResult PersistentStorage_StreamSync(
    SystemStorageFileHandle *handle);
PersistentStorageResult PersistentStorage_StreamClose(
    SystemStorageFileHandle *handle);

#endif /* __PERSISTENT_STORAGE_H */
