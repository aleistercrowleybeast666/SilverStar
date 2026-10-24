#ifndef __TEST_MAG_TF_H
#define __TEST_MAG_TF_H

/* In-memory slot fault injection, linked to the REAL persistence codec and
 * maintenance service. No FatFs/card/MCU recovery claim. */
#include "persistent_storage.h"
#include "system_mag_calibration_storage_if.h"
#if defined(SILVERSTAR_MAG_TF_SERIAL)
#include <setjmp.h>
#include "serial_task.h"
#include "system_console.h"
#include "system_console_if.h"
#include "task.h"
#endif

static uint8_t s_tf_slots[2][PERSISTENT_STORAGE_OBJECT_MAX_BYTES + 18U];
static uint16_t s_tf_lengths[2];
static uint8_t s_tf_present = 1U;
static uint8_t s_tf_initialized;
static uint8_t s_tf_write_fault;
static uint8_t s_tf_verify_fault;
static uint8_t s_tf_last_slot;
static uint32_t s_tf_writes;
static uint8_t s_tf_read_fault_mode;
static uint8_t s_tf_read_fault_countdown;

uint8_t ProjectMagnetometerInstance_CountGet(void) { return s_count; }

SystemDeviceResult SystemStorage_Init(void)
{
    TEST_CHECK(s_critical_depth == 0U);
    s_tf_initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_Mount(void)
{
    TEST_CHECK(s_critical_depth == 0U);
    return ((s_tf_present != 0U) && (s_tf_initialized != 0U)) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemStorage_ObjectSlotRead(uint8_t kind, uint8_t instance,
    uint8_t slot, uint8_t *data, uint16_t capacity, uint16_t *length)
{
    TEST_CHECK(s_critical_depth == 0U);
    TEST_CHECK(kind == PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION && instance == 0U && slot < 2U);
    if (s_tf_present == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if ((s_tf_read_fault_countdown != 0U) && (--s_tf_read_fault_countdown == 0U))
    {
        if (s_tf_read_fault_mode == 1U) { return SYSTEM_DEVICE_IO_ERROR; }
        if (s_tf_read_fault_mode == 3U) { return SYSTEM_DEVICE_NOT_PRESENT; }
        s_tf_slots[slot][20] ^= 1U;
    }
    if ((s_tf_verify_fault != 0U) && (slot == s_tf_last_slot))
    { s_tf_verify_fault = 0U; return SYSTEM_DEVICE_IO_ERROR; }
    if (s_tf_lengths[slot] == 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    TEST_CHECK(capacity >= s_tf_lengths[slot]);
    (void)memcpy(data, s_tf_slots[slot], s_tf_lengths[slot]);
    *length = s_tf_lengths[slot];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_ObjectSlotWrite(uint8_t kind, uint8_t instance,
    uint8_t slot, const uint8_t *data, uint16_t length)
{
    TEST_CHECK(s_critical_depth == 0U);
    TEST_CHECK(kind == PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION && instance == 0U && slot < 2U);
    if (s_tf_present == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    s_tf_writes++;
    s_tf_last_slot = slot;
    s_tf_lengths[slot] = (s_tf_write_fault == 1U) ? 9U : length;
    (void)memcpy(s_tf_slots[slot], data, s_tf_lengths[slot]);
    if (s_tf_write_fault == 1U) { return SYSTEM_DEVICE_IO_ERROR; }
    if (s_tf_write_fault == 2U) { s_tf_slots[slot][20] ^= 1U; }
    if (s_tf_write_fault == 3U) { s_tf_verify_fault = 1U; }
    /* Corrupt the generated-descriptor contract, not the physical card. */
    if (s_tf_write_fault == 4U) { s_count = 0U; }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemStorage_Open(const char *path, SystemStorageOpenMode mode,
    SystemStorageFileHandle *handle)
{ (void)path; (void)mode; (void)handle; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemStorage_Write(SystemStorageFileHandle *handle,
    const uint8_t *data, uint32_t length, uint32_t *written_length)
{ (void)handle; (void)data; (void)length; (void)written_length; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemStorage_Sync(SystemStorageFileHandle *handle)
{ (void)handle; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemStorage_Close(SystemStorageFileHandle *handle)
{ (void)handle; return SYSTEM_DEVICE_NOT_READY; }

static void TestTf_Seal(uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES], char *hex)
{
    static const char digits[] = "0123456789ABCDEF";
    uint32_t crc = 0xFFFFFFFFUL;
    uint16_t index;
    for (index = 0U; index < 80U; index++)
    {
        uint8_t bit;
        crc ^= packet[index];
        for (bit = 0U; bit < 8U; bit++)
        { crc = (crc >> 1U) ^ (((crc & 1U) != 0U) ? 0xEDB88320UL : 0U); }
    }
    Test_U32Write(&packet[80], ~crc);
    for (index = 0U; index < SYSTEM_MAG_CAL_PACKET_BYTES; index++)
    {
        hex[index * 2U] = digits[packet[index] >> 4U];
        hex[index * 2U + 1U] = digits[packet[index] & 15U];
    }
    hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS] = '\0';
}

static void TestTf_Candidate(float bias, uint8_t qualified)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    Test_PacketBuild(0U, 11U, packet, hex);
    Test_F32Write(&packet[6], bias);
    if (qualified == 0U) { Test_F32Write(&packet[58], 40.0f); }
    TestTf_Seal(packet, hex);
    TEST_CHECK(SystemMagCalibration_PacketApply(0U, hex) ==
        ((qualified != 0U) ? SystemMagCalibrationResult_Ok : SystemMagCalibrationResult_InvalidObject));
}

static void TestTf_LoadFinish(void)
{
    uint8_t index;
    for (index = 0U; index < 3U; index++)
    { SystemMagCalibrationStorage_Service(); }
    TEST_CHECK(SystemMagCalibrationStorage_LoadCompleteGet() == 1U);
}

static void TestTf_Save(float bias)
{
    SystemMagCalibrationStatus status;
    TestTf_Candidate(bias, 1U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.save_pending == 1U && status.saved == 0U);
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.saved == 1U && status.save_pending == 0U && status.save_failed == 0U);
}

static uint32_t TestTf_Read(uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES])
{
    uint16_t length = 0U;
    uint32_t generation = 0U;
    TEST_CHECK(PersistentStorage_ObjectRead(PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        0U, record, SYSTEM_MAG_CAL_RECORD_BYTES, &length, &generation) == PERSISTENT_STORAGE_OK);
    TEST_CHECK(length == SYSTEM_MAG_CAL_RECORD_BYTES);
    return generation;
}

static void TestTf_RebootCheck(float expected_x, uint32_t expected_generation)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint32_t generation = TestTf_Read(record);
    SystemMagnetometerSample sample = Test_SampleGet(0U);
    TEST_CHECK(generation == expected_generation);
    SystemMagCalibration_Init();
    TEST_CHECK(SystemMagCalibration_RecordLoad(0U, record, sizeof(record), generation) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(sample.magnetic_field_b_uT[0] == expected_x);
}

static void TestTf_Replacement(void)
{
    uint8_t slot;
    uint32_t writes;
    SystemMagCalibrationStatus status;
    TestTf_LoadFinish();
    TestTf_Save(12.0f);
    slot = s_tf_last_slot;
    TestTf_Save(2.0f);
    TEST_CHECK(slot != s_tf_last_slot && s_tf_writes == 2U);
    TestTf_RebootCheck(11.0f, 2U);
    writes = s_tf_writes;
    TestTf_Candidate(100.0f, 0U);
    TEST_CHECK(s_tf_writes == writes);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.saved == 1U && status.generation == 2U);
    /* Third generation reuses the first slot, never creates a history chain. */
    TestTf_Save(3.0f);
    TEST_CHECK(slot == s_tf_last_slot && s_tf_writes == 3U);
    TestTf_RebootCheck(10.0f, 3U);
}

static void TestTf_Failure(uint8_t mode)
{
    uint8_t old[sizeof(s_tf_slots[0])];
    uint8_t slot;
    SystemMagCalibrationStatus status;
    SystemMagnetometerSample sample;
    TestTf_LoadFinish(); TestTf_Save(12.0f);
    slot = s_tf_last_slot;
    (void)memcpy(old, s_tf_slots[slot], sizeof(old));
    s_tf_write_fault = mode;
    TestTf_Candidate(2.0f, 1U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.saved == 1U && status.generation == 1U && status.save_failed == 1U && status.save_pending == 0U);
    TEST_CHECK(memcmp(old, s_tf_slots[slot], sizeof(old)) == 0);
    sample = Test_SampleGet(0U);
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(sample.magnetic_field_b_uT[0] == 1.0f);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 0U);
    s_tf_write_fault = 0U;
    if (mode == 3U)
    {
        /* A completed write with lost readback acknowledgement is uncertain;
         * boot may safely select the complete NEW record, never a partial one. */
        TestTf_RebootCheck(11.0f, 2U);
    }
    else
    {
        uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
        TEST_CHECK(TestTf_Read(record) == 1U);
        /* Retry uses the retained NEW candidate, not the restored old value. */
        TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
        SystemMagCalibrationStorage_Service();
        TestTf_RebootCheck(11.0f, 2U);
    }
}

static void TestTf_BeforeSave(void)
{
    TestTf_LoadFinish(); TestTf_Save(12.0f);
    TestTf_Candidate(2.0f, 1U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    /* Reset before LoggerTask services SAVE: only the last durable value loads. */
    TestTf_RebootCheck(1.0f, 1U);
    TEST_CHECK(s_tf_writes == 1U);
}

static void TestTf_ClearFailure(void)
{
    SystemMagCalibrationStatus status;
    TestTf_LoadFinish(); TestTf_Save(12.0f);
    s_tf_write_fault = 1U;
    TEST_CHECK(SystemMagCalibration_ClearRequest(0U) == SystemMagCalibrationResult_Ok);
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 1U && status.saved == 1U && status.generation == 1U && status.save_failed == 1U);
    s_tf_write_fault = 0U;
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 0U && status.saved == 0U && status.generation == 2U && status.save_failed == 0U);
}

static void TestTf_Corrupt(void)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint16_t length = 0U;
    uint32_t generation = 0U;
    TestTf_LoadFinish(); TestTf_Save(12.0f);
    s_tf_slots[0][0] ^= 1U;
    TEST_CHECK(PersistentStorage_ObjectRead(PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        0U, record, sizeof(record), &length, &generation) == PERSISTENT_STORAGE_VERIFY_FAILED);
    TEST_CHECK(length == 0U && generation == 0U);
}

static void TestTf_SelectedReadFailure(uint8_t mode)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint8_t unchanged[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint16_t length = 99U;
    uint32_t generation = 99U;
    TestTf_LoadFinish(); TestTf_Save(12.0f); TestTf_Save(2.0f);
    (void)memset(record, 0xA5, sizeof(record));
    (void)memcpy(unchanged, record, sizeof(record));
    /* Two metadata reads, then the bounded selected-slot reload. Never
     * publish payload or success if this last read fails or changes bytes. */
    s_tf_read_fault_mode = mode;
    s_tf_read_fault_countdown = 3U;
    TEST_CHECK(PersistentStorage_ObjectRead(PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        0U, record, sizeof(record), &length, &generation) ==
        ((mode == 1U) ? PERSISTENT_STORAGE_IO_ERROR : PERSISTENT_STORAGE_VERIFY_FAILED));
    TEST_CHECK(length == 0U && generation == 0U);
    TEST_CHECK(memcmp(record, unchanged, sizeof(record)) == 0);
    /* An I/O failure preserves the newest generation; corruption falls back
     * to the older independently committed slot on the next normal read. */
    TestTf_RebootCheck((mode == 2U) ? 1.0f : 11.0f, (mode == 2U) ? 1U : 2U);
}

static void TestTf_Envelope(void)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint8_t original[SYSTEM_MAG_CAL_RECORD_BYTES];
    static const uint8_t offsets[] = {0U, 4U, 5U, 6U, 7U, 13U, 14U, 15U, 28U};
    uint8_t index;
    uint32_t generation;
    TestTf_LoadFinish(); TestTf_Save(12.0f);
    generation = TestTf_Read(original);
    SystemMagCalibration_Init();
    for (index = 0U; index < sizeof(offsets); index++)
    {
        (void)memcpy(record, original, sizeof(record)); record[offsets[index]] ^= 0x40U;
        TEST_CHECK(SystemMagCalibration_RecordLoad(0U, record, sizeof(record), generation) == SystemMagCalibrationResult_InvalidObject);
    }
    (void)memcpy(record, original, sizeof(record)); record[32] = 0U;
    TEST_CHECK(SystemMagCalibration_RecordLoad(0U, record, sizeof(record), generation) == SystemMagCalibrationResult_InvalidObject);
}

static void TestTf_Identity(const char *mode)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint32_t generation;
    TestTf_LoadFinish(); TestTf_Save(12.0f);
    generation = TestTf_Read(record);
    SystemMagCalibration_Init();
    if (strcmp(mode, "tf_config") == 0) { s_config_digest++; }
    else if (strcmp(mode, "tf_sensor") == 0) { s_descriptors[0].physical_device_id++; }
    else if (strcmp(mode, "tf_endpoint") == 0) { s_descriptors[0].descriptor_id++; }
    else if (strcmp(mode, "tf_driver") == 0) { s_descriptors[0].driver_name_hash++; }
    else { s_descriptors[0].model_name_hash++; }
    TEST_CHECK(SystemMagCalibration_RecordLoad(0U, record, sizeof(record), generation) == SystemMagCalibrationResult_WrongDevice);
    TEST_CHECK(s_tf_writes == 1U);
}

static void TestTf_Legacy(void)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    uint32_t generation;
    SystemMagCalibrationStatus status;
    Test_PacketBuild(0U, 11U, packet, hex);
    TEST_CHECK(SystemStorage_Init() == SYSTEM_DEVICE_OK && SystemStorage_Mount() == SYSTEM_DEVICE_OK);
    TEST_CHECK(PersistentStorage_ObjectWriteAtomic(PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        0U, packet, sizeof(packet), &generation) == PERSISTENT_STORAGE_OK);
    TestTf_LoadFinish();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 0U && status.load_error == SystemMagCalibrationResult_InvalidObject);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 0U);
    /* Explicitly reviewed maintenance APPLY+SAVE is the migration boundary. */
    TestTf_Save(12.0f);
    TestTf_RebootCheck(1.0f, 2U);
}

static void TestTf_NoCard(void)
{
    SystemMagCalibrationStatus status;
    s_tf_present = 0U;
    TestTf_LoadFinish();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 0U && status.saved == 0U && status.load_error == SystemMagCalibrationResult_StorageError);
    TestTf_Candidate(12.0f, 1U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 0U && status.saved == 0U && status.save_failed == 1U && status.save_pending == 0U);
    TEST_CHECK(s_tf_writes == 0U && SystemMagCalibration_ReadyForMissionGet() == 0U);
}

static void TestTf_PendingIdentity(void)
{
    SystemMagCalibrationStatus status;
    TestTf_LoadFinish(); TestTf_Candidate(12.0f, 1U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    s_descriptors[0].physical_device_id++;
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.saved == 0U && status.save_pending == 0U && status.save_failed == 1U);
    TEST_CHECK(s_tf_writes == 0U);
}

static void TestTf_BootLoad(void)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES];
    uint8_t instance;
    uint32_t request;
    uint32_t generation;
    SystemMagCalibrationStatus status;
    SystemMagnetometerSample sample;
    /* Seed a complete record from a prior boot without running this boot's
     * storage service; then exercise the actual OneLoad lifecycle. */
    TestTf_Candidate(2.0f, 1U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_PendingRecordGet(&instance, record, &request) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemStorage_Init() == SYSTEM_DEVICE_OK && SystemStorage_Mount() == SYSTEM_DEVICE_OK);
    TEST_CHECK(PersistentStorage_ObjectWriteAtomic(PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION,
        0U, record, sizeof(record), &generation) == PERSISTENT_STORAGE_OK);
    SystemMagCalibration_Init();
    TestTf_LoadFinish();
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 1U && status.saved == 1U && status.generation == generation);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 1U);
    sample = Test_SampleGet(0U);
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(sample.magnetic_field_b_uT[0] == 11.0f);
}

#if defined(SILVERSTAR_MAG_TF_SERIAL)
#if !defined(SILVERSTAR_MAG_CAL_ARM_LINK_ONLY)
static jmp_buf s_tf_serial_exit;
#endif
static uint8_t s_tf_serial_queued;
static uint8_t s_tf_serial_steps;

void SystemConsoleDevice_Process(void) { }
void SystemConsole_Process(void)
{
    if ((SystemMagCalibrationStorage_LoadCompleteGet() != 0U) && (s_tf_serial_queued == 0U))
    {
        TestTf_Candidate(2.0f, 1U);
        TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
        s_tf_serial_queued = 1U;
    }
}
void vTaskDelay(TickType_t ticks)
{
    SystemMagCalibrationStatus status;
    TEST_CHECK(ticks == 1U && ++s_tf_serial_steps < 10U);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    if (status.saved != 0U)
    {
#if defined(SILVERSTAR_MAG_CAL_ARM_LINK_ONLY)
        __builtin_trap();
#else
        longjmp(s_tf_serial_exit, 1);
#endif
    }
}
static void TestTf_Serial(void)
{
#if defined(SILVERSTAR_MAG_CAL_ARM_LINK_ONLY)
    AppTask_Serial(NULL);
#else
    if (setjmp(s_tf_serial_exit) == 0) { AppTask_Serial(NULL); }
#endif
    TEST_CHECK(s_tf_serial_queued == 1U && s_tf_writes == 1U);
    TestTf_RebootCheck(11.0f, 1U);
}
#endif

static void TestTf_ServiceContract(uint8_t completion)
{
    if (completion != 0U)
    {
        TestTf_LoadFinish();
        TestTf_Candidate(2.0f, 1U);
        TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
        s_tf_write_fault = 4U;
        s_expected_assert_reason = SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT;
    }
    else
    {
        s_tf_present = 0U;
        s_descriptors[0].flags = 0U;
        s_expected_assert_reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT;
    }
    s_expected_terminal_assert = 1U;
    SystemMagCalibrationStorage_Service();
    TEST_CHECK(0U); /* The corrupted internal contract must not return. */
}

static void TestTf_Run(const char *mode)
{
    Test_Reset(1U);
#if defined(SILVERSTAR_MAG_TF_SERIAL)
    if (strcmp(mode, "tf_serial") == 0) { TestTf_Serial(); return; }
#endif
    if (strcmp(mode, "tf_replacement") == 0) { TestTf_Replacement(); }
    else if (strcmp(mode, "tf_torn") == 0) { TestTf_Failure(1U); }
    else if (strcmp(mode, "tf_crc") == 0) { TestTf_Failure(2U); }
    else if (strcmp(mode, "tf_verify") == 0) { TestTf_Failure(3U); }
    else if (strcmp(mode, "tf_legacy") == 0) { TestTf_Legacy(); }
    else if (strcmp(mode, "tf_no_card") == 0) { TestTf_NoCard(); }
    else if (strcmp(mode, "tf_before_save") == 0) { TestTf_BeforeSave(); }
    else if (strcmp(mode, "tf_clear_failure") == 0) { TestTf_ClearFailure(); }
    else if (strcmp(mode, "tf_corrupt") == 0) { TestTf_Corrupt(); }
    else if (strcmp(mode, "tf_selected_read_io") == 0) { TestTf_SelectedReadFailure(1U); }
    else if (strcmp(mode, "tf_selected_read_crc") == 0) { TestTf_SelectedReadFailure(2U); }
    else if (strcmp(mode, "tf_selected_read_missing") == 0) { TestTf_SelectedReadFailure(3U); }
    else if (strcmp(mode, "tf_envelope") == 0) { TestTf_Envelope(); }
    else if (strcmp(mode, "tf_pending_identity") == 0) { TestTf_PendingIdentity(); }
    else if (strcmp(mode, "tf_boot_load") == 0) { TestTf_BootLoad(); }
    else if (strcmp(mode, "tf_load_fault_contract") == 0) { TestTf_ServiceContract(0U); }
    else if (strcmp(mode, "tf_completion_contract") == 0) { TestTf_ServiceContract(1U); }
    else { TestTf_Identity(mode); }
}

#endif /* __TEST_MAG_TF_H */
