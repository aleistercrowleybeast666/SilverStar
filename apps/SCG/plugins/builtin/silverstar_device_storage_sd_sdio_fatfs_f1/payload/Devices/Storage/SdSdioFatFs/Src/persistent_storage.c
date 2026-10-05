#include "persistent_storage.h"

#include <stddef.h>
#include <string.h>

#include "silverstar_assert.h"

#define PERSISTENT_STORAGE_HEADER_BYTES 18U
#define PERSISTENT_STORAGE_RECORD_BYTES \
    (PERSISTENT_STORAGE_HEADER_BYTES + PERSISTENT_STORAGE_OBJECT_MAX_BYTES)

typedef struct
{
    uint32_t generation;
    uint16_t length;
    uint8_t slot;
} PersistentStorageObjectLatest;

/* LoggerTask is the single FatFs owner. These buffers never enter DMA. */
static uint8_t s_record[PERSISTENT_STORAGE_RECORD_BYTES];
static uint8_t s_latest_payload[PERSISTENT_STORAGE_OBJECT_MAX_BYTES];

static uint32_t PersistentStorage_U32Read(const uint8_t *data)
{
    return (uint32_t)data[0] | ((uint32_t)data[1] << 8U) |
        ((uint32_t)data[2] << 16U) | ((uint32_t)data[3] << 24U);
}

static void PersistentStorage_U32Write(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
    data[2] = (uint8_t)(value >> 16U);
    data[3] = (uint8_t)(value >> 24U);
}

static uint32_t PersistentStorage_CrcUpdate(
    uint32_t crc, const uint8_t *data, uint16_t length)
{
    uint16_t index;
    uint8_t bit;
    for (index = 0U; index < length; index++)
    {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; bit++)
        { crc = (crc >> 1U) ^ ((crc & 1U) ? 0xEDB88320UL : 0UL); }
    }
    return crc;
}

static uint32_t PersistentStorage_RecordCrcGet(
    const uint8_t *record, uint16_t payload_length)
{
    uint32_t crc = PersistentStorage_CrcUpdate(0xFFFFFFFFUL,
        record, 14U);
    crc = PersistentStorage_CrcUpdate(crc,
        &record[PERSISTENT_STORAGE_HEADER_BYTES], payload_length);
    return ~crc;
}

static uint8_t PersistentStorage_KeyValid(
    PersistentStorageObjectKind kind, uint8_t instance)
{
    return (uint8_t)((kind >= PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION) &&
        (kind <= PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT) &&
        (instance < 32U));
}

static uint8_t PersistentStorage_RecordParse(
    PersistentStorageObjectKind kind, uint8_t instance,
    const uint8_t *record, uint16_t record_length,
    PersistentStorageObjectLatest *latest)
{
    uint16_t payload_length;
    uint32_t generation;
    SILVERSTAR_ASSERT_OBJECT(record, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(latest, PersistentStorageObjectLatest,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((record_length < PERSISTENT_STORAGE_HEADER_BYTES) ||
        (memcmp(record, "SSOB", 4U) != 0) || (record[4] != 1U) ||
        (record[5] != (uint8_t)kind) || (record[6] != instance) ||
        (record[7] != 0U)) { return 0U; }
    generation = PersistentStorage_U32Read(&record[8]);
    payload_length = (uint16_t)record[12] | ((uint16_t)record[13] << 8U);
    if ((generation == 0U) || (payload_length == 0U) ||
        (payload_length > PERSISTENT_STORAGE_OBJECT_MAX_BYTES) ||
        (record_length != (uint16_t)(PERSISTENT_STORAGE_HEADER_BYTES +
            payload_length)) ||
        (PersistentStorage_RecordCrcGet(record, payload_length) !=
            PersistentStorage_U32Read(&record[14]))) { return 0U; }
    latest->generation = generation;
    latest->length = payload_length;
    return 1U;
}

static PersistentStorageResult PersistentStorage_ResultMap(
    SystemDeviceResult result)
{
    if ((result == SYSTEM_DEVICE_OK) ||
        (result == SYSTEM_DEVICE_ALREADY_MATCHED))
    { return PERSISTENT_STORAGE_OK; }
    if (result == SYSTEM_DEVICE_NOT_PRESENT)
    { return PERSISTENT_STORAGE_NOT_FOUND; }
    if (result == SYSTEM_DEVICE_NOT_READY)
    { return PERSISTENT_STORAGE_NOT_READY; }
    if (result == SYSTEM_DEVICE_INVALID_ARGUMENT)
    { return PERSISTENT_STORAGE_INVALID_ARGUMENT; }
    return PERSISTENT_STORAGE_IO_ERROR;
}

static PersistentStorageResult PersistentStorage_LatestGet(
    PersistentStorageObjectKind kind, uint8_t instance,
    PersistentStorageObjectLatest *latest)
{
    PersistentStorageResult status = PERSISTENT_STORAGE_NOT_FOUND;
    uint8_t slot;
    SILVERSTAR_ASSERT_OBJECT(latest, PersistentStorageObjectLatest,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(PersistentStorage_KeyValid(kind, instance) != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    for (slot = 0U; slot < 2U; slot++)
    {
        PersistentStorageObjectLatest candidate = {0U, 0U, slot};
        uint16_t record_length = 0U;
        SystemDeviceResult read_result = SystemStorage_ObjectSlotRead(
            (uint8_t)kind, instance, slot, s_record,
            sizeof(s_record), &record_length);
        if (read_result == SYSTEM_DEVICE_NOT_PRESENT) { continue; }
        if (read_result != SYSTEM_DEVICE_OK)
        { return PersistentStorage_ResultMap(read_result); }
        if (PersistentStorage_RecordParse(kind, instance, s_record,
                record_length, &candidate) == 0U) { continue; }
        if ((status == PERSISTENT_STORAGE_NOT_FOUND) ||
            (candidate.generation > latest->generation))
        {
            *latest = candidate;
            (void)memcpy(s_latest_payload,
                &s_record[PERSISTENT_STORAGE_HEADER_BYTES],
                candidate.length);
            status = PERSISTENT_STORAGE_OK;
        }
    }
    return status;
}

PersistentStorageResult PersistentStorage_ObjectRead(
    PersistentStorageObjectKind kind, uint8_t instance,
    uint8_t *data, uint16_t capacity, uint16_t *length,
    uint32_t *generation)
{
    PersistentStorageObjectLatest latest = {0U, 0U, 0U};
    PersistentStorageResult result;
    if ((PersistentStorage_KeyValid(kind, instance) == 0U) ||
        (data == NULL) || (length == NULL) || (generation == NULL))
    { return PERSISTENT_STORAGE_INVALID_ARGUMENT; }
    *length = 0U;
    *generation = 0U;
    result = PersistentStorage_LatestGet(kind, instance, &latest);
    if (result != PERSISTENT_STORAGE_OK) { return result; }
    if (latest.length > capacity) { return PERSISTENT_STORAGE_TOO_LARGE; }
    (void)memcpy(data, s_latest_payload, latest.length);
    *length = latest.length;
    *generation = latest.generation;
    return PERSISTENT_STORAGE_OK;
}

PersistentStorageResult PersistentStorage_ObjectWriteAtomic(
    PersistentStorageObjectKind kind, uint8_t instance,
    const uint8_t *data, uint16_t length, uint32_t *generation)
{
    PersistentStorageObjectLatest latest = {0U, 0U, 1U};
    PersistentStorageObjectLatest verified = {0U, 0U, 0U};
    PersistentStorageResult result;
    SystemDeviceResult device_result;
    uint32_t next_generation;
    uint16_t record_length;
    uint8_t target_slot;
    if ((PersistentStorage_KeyValid(kind, instance) == 0U) ||
        (data == NULL) || (generation == NULL) || (length == 0U))
    { return PERSISTENT_STORAGE_INVALID_ARGUMENT; }
    if (length > PERSISTENT_STORAGE_OBJECT_MAX_BYTES)
    { return PERSISTENT_STORAGE_TOO_LARGE; }
    SILVERSTAR_ASSERT_OBJECT(generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(sizeof(s_record) >=
        (PERSISTENT_STORAGE_HEADER_BYTES + length),
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    *generation = 0U;
    result = PersistentStorage_LatestGet(kind, instance, &latest);
    if ((result != PERSISTENT_STORAGE_OK) &&
        (result != PERSISTENT_STORAGE_NOT_FOUND)) { return result; }
    if (latest.generation == UINT32_MAX)
    { return PERSISTENT_STORAGE_GENERATION_EXHAUSTED; }
    next_generation = latest.generation + 1U;
    target_slot = (uint8_t)(latest.slot ^ 1U);
    (void)memcpy(s_record, "SSOB", 4U);
    s_record[4] = 1U;
    s_record[5] = (uint8_t)kind;
    s_record[6] = instance;
    s_record[7] = 0U;
    PersistentStorage_U32Write(&s_record[8], next_generation);
    s_record[12] = (uint8_t)length;
    s_record[13] = (uint8_t)(length >> 8U);
    (void)memcpy(&s_record[PERSISTENT_STORAGE_HEADER_BYTES], data, length);
    PersistentStorage_U32Write(&s_record[14],
        PersistentStorage_RecordCrcGet(s_record, length));
    record_length = (uint16_t)(PERSISTENT_STORAGE_HEADER_BYTES + length);
    device_result = SystemStorage_ObjectSlotWrite((uint8_t)kind,
        instance, target_slot, s_record, record_length);
    if (device_result != SYSTEM_DEVICE_OK)
    { return PersistentStorage_ResultMap(device_result); }
    device_result = SystemStorage_ObjectSlotRead((uint8_t)kind,
        instance, target_slot, s_record, sizeof(s_record), &record_length);
    if ((device_result != SYSTEM_DEVICE_OK) ||
        (PersistentStorage_RecordParse(kind, instance, s_record,
            record_length, &verified) == 0U) ||
        (verified.generation != next_generation) ||
        (verified.length != length) ||
        (memcmp(&s_record[PERSISTENT_STORAGE_HEADER_BYTES],
            data, length) != 0))
    { return PERSISTENT_STORAGE_VERIFY_FAILED; }
    *generation = next_generation;
    return PERSISTENT_STORAGE_OK;
}

PersistentStorageResult PersistentStorage_StreamOpen(
    const char *path, SystemStorageOpenMode mode,
    SystemStorageFileHandle *handle)
{ return PersistentStorage_ResultMap(SystemStorage_Open(path, mode, handle)); }

PersistentStorageResult PersistentStorage_StreamWrite(
    SystemStorageFileHandle *handle, const uint8_t *data,
    uint32_t length, uint32_t *written_length)
{ return PersistentStorage_ResultMap(SystemStorage_Write(
    handle, data, length, written_length)); }

PersistentStorageResult PersistentStorage_StreamSync(
    SystemStorageFileHandle *handle)
{ return PersistentStorage_ResultMap(SystemStorage_Sync(handle)); }

PersistentStorageResult PersistentStorage_StreamClose(
    SystemStorageFileHandle *handle)
{ return PersistentStorage_ResultMap(SystemStorage_Close(handle)); }
