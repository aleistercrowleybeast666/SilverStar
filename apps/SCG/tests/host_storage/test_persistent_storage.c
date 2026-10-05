#include "persistent_storage.h"

#include <assert.h>
#include <string.h>

#define TEST_RECORD_CAPACITY (PERSISTENT_STORAGE_OBJECT_MAX_BYTES + 18U)

static uint8_t s_slots[2][TEST_RECORD_CAPACITY];
static uint16_t s_lengths[2];
static uint8_t s_corrupt_next_write;

SystemDeviceResult SystemStorage_ObjectSlotRead(
    uint8_t kind, uint8_t instance, uint8_t slot,
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    assert(kind == PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION);
    assert(instance == 0U && slot < 2U);
    if (s_lengths[slot] == 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    assert(capacity >= s_lengths[slot]);
    (void)memcpy(data, s_slots[slot], s_lengths[slot]);
    *length = s_lengths[slot];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_ObjectSlotWrite(
    uint8_t kind, uint8_t instance, uint8_t slot,
    const uint8_t *data, uint16_t length)
{
    assert(kind == PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION);
    assert(instance == 0U && slot < 2U && length <= TEST_RECORD_CAPACITY);
    (void)memcpy(s_slots[slot], data, length);
    s_lengths[slot] = length;
    if (s_corrupt_next_write != 0U)
    {
        s_slots[slot][length - 1U] ^= 0x5AU;
        s_corrupt_next_write = 0U;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_Open(const char *path,
    SystemStorageOpenMode mode, SystemStorageFileHandle *handle)
{ (void)path; (void)mode; (void)handle; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemStorage_Write(SystemStorageFileHandle *handle,
    const uint8_t *data, uint32_t length, uint32_t *written_length)
{ (void)handle; (void)data; (void)length; (void)written_length;
  return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemStorage_Sync(SystemStorageFileHandle *handle)
{ (void)handle; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemStorage_Close(SystemStorageFileHandle *handle)
{ (void)handle; return SYSTEM_DEVICE_NOT_READY; }

int main(void)
{
    static const uint8_t first[] = {1U, 2U, 3U, 4U};
    static const uint8_t second[] = {5U, 6U, 7U};
    static const uint8_t third[] = {8U, 9U};
    uint8_t output[8];
    uint16_t length = 0U;
    uint32_t generation = 0U;
    assert(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        output, sizeof(output), &length, &generation) ==
        PERSISTENT_STORAGE_NOT_FOUND);
    assert(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        first, sizeof(first), &generation) == PERSISTENT_STORAGE_OK);
    assert(generation == 1U && s_lengths[0] == sizeof(first) + 18U);
    assert(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        second, sizeof(second), &generation) == PERSISTENT_STORAGE_OK);
    assert(generation == 2U && s_lengths[1] == sizeof(second) + 18U);
    assert(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        output, sizeof(output), &length, &generation) == PERSISTENT_STORAGE_OK);
    assert(generation == 2U && length == sizeof(second));
    assert(memcmp(output, second, sizeof(second)) == 0);
    s_corrupt_next_write = 1U;
    assert(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        third, sizeof(third), &generation) == PERSISTENT_STORAGE_VERIFY_FAILED);
    assert(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        output, sizeof(output), &length, &generation) == PERSISTENT_STORAGE_OK);
    assert(generation == 2U && length == sizeof(second));
    assert(memcmp(output, second, sizeof(second)) == 0);
    assert(PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        output, 1U, &length, &generation) == PERSISTENT_STORAGE_TOO_LARGE);
    assert(PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 32U,
        third, sizeof(third), &generation) == PERSISTENT_STORAGE_INVALID_ARGUMENT);
    return 0;
}
