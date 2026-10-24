/* Tests link the owning calibration unit; only its platform/device ports are
 * mocked. This fixture neither communicates with devices nor proves recovery. */
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "platform_critical.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "system_mag_calibration.h"

static uint8_t s_count;
static uint32_t s_critical_depth;
static uint32_t s_capabilities;
static SystemDeviceResult s_capability_result;
static SystemDeviceDescriptor s_descriptors[2];
static uint32_t s_config_digest;
static uint8_t s_expected_terminal_assert;
static SilverStarAssertReasonId s_expected_assert_reason;

uint32_t SystemDescriptor_ConfigDigestGet(void)
{
    return s_config_digest;
}

static void Test_Check(uint8_t condition, uint32_t line)
{
    if (condition == 0U)
    {
#if defined(SILVERSTAR_MAG_CAL_ARM_LINK_ONLY)
        /* Link-only fixture: no board startup and never flashed/executed. */
        (void)line;
        __builtin_trap();
#else
        (void)fprintf(stderr, "CHECK_FAIL|%lu\n", (unsigned long)line);
        exit(1);
#endif
    }
}

#define TEST_CHECK(condition_) Test_Check((uint8_t)((condition_) != 0), __LINE__)

PlatformCriticalState PlatformCritical_Enter(void)
{
    PlatformCriticalState previous = s_critical_depth;
    s_critical_depth++;
    return previous;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    TEST_CHECK(s_critical_depth == state + 1U);
    s_critical_depth = state;
}

void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module_id,
    const char *file_name, uint32_t line, SilverStarAssertReasonId reason_id)
{
    if ((condition == 0U) && (s_expected_terminal_assert != 0U))
    {
        Test_Check((uint8_t)((module_id == SILVERSTAR_ASSERT_MODULE_DEVICE) &&
            (reason_id == s_expected_assert_reason) &&
            (strstr(file_name, "mag_calibration_storage.c") != NULL)), line);
#if defined(SILVERSTAR_MAG_CAL_ARM_LINK_ONLY)
        __builtin_trap();
#else
        (void)printf("EXPECTED_TERMINAL_ASSERT|module=%u|reason=%u|line=%lu\n",
            (unsigned int)module_id, (unsigned int)reason_id, (unsigned long)line);
        exit(0);
#endif
    }
    (void)module_id;
    (void)file_name;
    (void)reason_id;
    Test_Check(condition, line);
}

void SilverStarAssert_ObjectCheck(const volatile void *object, uint32_t alignment,
    SilverStarAssertModuleId module_id, const char *file_name, uint32_t line)
{
    (void)module_id;
    (void)file_name;
    Test_Check((uint8_t)((object != NULL) && (alignment != 0U) &&
        (((uintptr_t)object % alignment) == 0U)), line);
}

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    TEST_CHECK(s_critical_depth == 0U);
    if ((descriptor == NULL) ||
        (device_class != SYSTEM_DEVICE_CLASS_MAGNETOMETER))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance_id >= s_count) { return SYSTEM_DEVICE_NOT_PRESENT; }
    *descriptor = s_descriptors[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectMagnetometerInstance_CapabilitiesGet(
    uint8_t instance_id, uint32_t *mask)
{
    TEST_CHECK(s_critical_depth == 0U);
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance_id >= s_count) { return SYSTEM_DEVICE_NOT_PRESENT; }
    if (s_capability_result == SYSTEM_DEVICE_OK) { *mask = s_capabilities; }
    return s_capability_result;
}

static void Test_Reset(uint8_t count)
{
    uint8_t index;
    s_count = count;
    s_critical_depth = 0U;
    s_capabilities = SYSTEM_MAG_CAP_RAW_OUTPUT | SYSTEM_MAG_CAP_PHYSICAL_UNIT;
    s_capability_result = SYSTEM_DEVICE_OK;
    s_config_digest = 0x13572468UL;
    (void)memset(s_descriptors, 0, sizeof(s_descriptors));
    for (index = 0U; index < 2U; index++)
    {
        s_descriptors[index].device_class = SYSTEM_DEVICE_CLASS_MAGNETOMETER;
        s_descriptors[index].instance_id = index;
        s_descriptors[index].physical_device_id = (uint16_t)(11U + index);
        s_descriptors[index].descriptor_id = (uint16_t)(30U + index);
        s_descriptors[index].flags = SYSTEM_DESCRIPTOR_FLAG_ENABLED;
        s_descriptors[index].driver_name_hash = 0x1234U;
        s_descriptors[index].model_name_hash = 0x5678U;
    }
    SystemMagCalibration_Init();
}

static void Test_U32Write(uint8_t *data, uint32_t value)
{
    uint8_t index;
    for (index = 0U; index < 4U; index++)
    { data[index] = (uint8_t)(value >> (8U * index)); }
}

static void Test_F32Write(uint8_t *data, float value)
{
    uint32_t bits;
    (void)memcpy(&bits, &value, sizeof(bits));
    Test_U32Write(data, bits);
}

static void Test_PacketBuild(uint8_t instance, uint16_t physical,
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U])
{
    static const char digits[] = "0123456789ABCDEF";
    uint32_t crc = 0xFFFFFFFFUL;
    uint16_t index;
    (void)memset(packet, 0, SYSTEM_MAG_CAL_PACKET_BYTES);
    packet[0] = 1U;
    packet[1] = 1U;
    packet[2] = (uint8_t)physical;
    packet[3] = (uint8_t)(physical >> 8U);
    packet[4] = instance;
    Test_F32Write(&packet[6], 12.0f);
    Test_F32Write(&packet[10], -8.0f);
    Test_F32Write(&packet[14], 3.0f);
    Test_F32Write(&packet[18], 1.0f);
    Test_F32Write(&packet[34], 2.0f);
    Test_F32Write(&packet[50], 1.0f);
    Test_F32Write(&packet[54], 50.0f);
    Test_F32Write(&packet[58], 0.2f);
    Test_F32Write(&packet[62], 0.8f);
    Test_F32Write(&packet[66], 2.0f);
    for (index = 70U; index < 78U; index++) { packet[index] = 75U; }
    packet[78] = 0x58U;
    packet[79] = 0x02U;
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

static void Test_Apply(uint8_t instance)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    Test_PacketBuild(instance, s_descriptors[instance].physical_device_id,
        packet, hex);
    TEST_CHECK(SystemMagCalibration_PacketApply(instance, hex) ==
        SystemMagCalibrationResult_Ok);
}

static SystemMagCalibrationResult Test_RecordLoad(uint8_t instance,
    const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES], uint32_t generation)
{
    uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES] = {0U};
    const SystemDeviceDescriptor *descriptor = &s_descriptors[instance];
    (void)memcpy(record, "SSIC", 4U);
    record[4] = 1U; record[5] = 1U; record[6] = 1U; record[7] = 1U;
    record[8] = (uint8_t)descriptor->descriptor_id;
    record[9] = (uint8_t)(descriptor->descriptor_id >> 8U);
    record[10] = (uint8_t)descriptor->physical_device_id;
    record[11] = (uint8_t)(descriptor->physical_device_id >> 8U);
    record[12] = instance;
    Test_U32Write(&record[16], s_config_digest);
    Test_U32Write(&record[20], descriptor->driver_name_hash);
    Test_U32Write(&record[24], descriptor->model_name_hash);
    (void)memcpy(&record[32], packet, SYSTEM_MAG_CAL_PACKET_BYTES);
    return SystemMagCalibration_RecordLoad(instance, record, sizeof(record), generation);
}

static SystemMagnetometerSample Test_SampleGet(uint8_t instance)
{
    SystemMagnetometerSample sample;
    (void)memset(&sample, 0, sizeof(sample));
    sample.valid_mask = SYSTEM_MAG_VALID_RAW | SYSTEM_MAG_VALID_PHYSICAL_UNIT;
    sample.physical_device_id = s_descriptors[instance].physical_device_id;
    sample.descriptor_id = s_descriptors[instance].descriptor_id;
    sample.instance_id = instance;
    sample.raw[0] = 123;
    sample.sequence = 17U;
    sample.sample_timestamp_us = 123456789ULL;
    sample.magnetic_field_b_uT[0] = 13.0f;
    sample.magnetic_field_b_uT[1] = -6.0f;
    sample.magnetic_field_b_uT[2] = 6.0f;
    return sample;
}

static void Test_EmptyUnchanged(uint32_t hash)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    uint8_t instance = UINT8_MAX;
    uint32_t request = UINT32_MAX;
    TEST_CHECK(SystemMagCalibration_GenerationHashGet() == hash);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 1U);
    TEST_CHECK(SystemMagCalibration_PendingGet(&instance, packet, &request) ==
        SystemMagCalibrationResult_NotReady);
    TEST_CHECK(instance == UINT8_MAX && request == UINT32_MAX);
    TEST_CHECK(s_critical_depth == 0U);
}

static void Test_Absent(const char *operation)
{
    uint32_t hash;
    Test_Reset(0U);
    hash = SystemMagCalibration_GenerationHashGet();
    if (strcmp(operation, "absent_clear") == 0)
    { TEST_CHECK(SystemMagCalibration_ClearRequest(0U) == SystemMagCalibrationResult_NotPresent); }
    else if (strcmp(operation, "absent_save") == 0)
    { TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_NotPresent); }
    else if (strcmp(operation, "absent_status") == 0)
    {
        SystemMagCalibrationStatus status;
        SystemMagCalibrationStatus before;
        (void)memset(&status, 0x5A, sizeof(status));
        (void)memcpy(&before, &status, sizeof(before));
        TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_NotPresent);
        TEST_CHECK(memcmp(&status, &before, sizeof(status)) == 0);
    }
    else if (strcmp(operation, "absent_complete") == 0)
    { TEST_CHECK(SystemMagCalibration_SaveComplete(0U, 1U, 1U, 2U) == SystemMagCalibrationResult_NotPresent); }
    else if (strcmp(operation, "absent_fault") == 0)
    { TEST_CHECK(SystemMagCalibration_LoadFaultSet(0U, SystemMagCalibrationResult_StorageError) == SystemMagCalibrationResult_NotPresent); }
    else
    {
        uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
        char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
        SystemMagnetometerSample sample = Test_SampleGet(0U);
        Test_PacketBuild(0U, 11U, packet, hex);
        TEST_CHECK(SystemMagCalibration_PacketApply(0U, hex) == SystemMagCalibrationResult_NotPresent);
        TEST_CHECK(Test_RecordLoad(0U, packet, 1U) == SystemMagCalibrationResult_NotPresent);
        TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_NotPresent);
    }
    Test_EmptyUnchanged(hash);
}

static void Test_Provider(const char *scenario)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    SystemMagCalibrationResult expected = SystemMagCalibrationResult_NotReady;
    uint32_t hash;
    Test_Reset(1U);
    hash = SystemMagCalibration_GenerationHashGet();
    Test_PacketBuild(0U, 11U, packet, hex);
    if (strcmp(scenario, "disabled") == 0)
    { s_descriptors[0].flags = 0U; expected = SystemMagCalibrationResult_NotPresent; }
    else if (strcmp(scenario, "wrong_class") == 0)
    { s_descriptors[0].device_class = SYSTEM_DEVICE_CLASS_IMU; expected = SystemMagCalibrationResult_WrongDevice; }
    else if (strcmp(scenario, "wrong_instance") == 0)
    { s_descriptors[0].instance_id = 1U; expected = SystemMagCalibrationResult_WrongDevice; }
    else if (strcmp(scenario, "zero_identity") == 0)
    { s_descriptors[0].physical_device_id = 0U; expected = SystemMagCalibrationResult_WrongDevice; }
    else if (strcmp(scenario, "raw_only") == 0)
    { s_capabilities = SYSTEM_MAG_CAP_RAW_OUTPUT; }
    else if (strcmp(scenario, "unsupported") == 0)
    { s_capability_result = SYSTEM_DEVICE_UNSUPPORTED; }
    else if (strcmp(scenario, "timeout") == 0)
    { s_capability_result = SYSTEM_DEVICE_TIMEOUT; }
    else
    { s_capability_result = SYSTEM_DEVICE_NOT_PRESENT; expected = SystemMagCalibrationResult_NotPresent; }
    TEST_CHECK(SystemMagCalibration_PacketApply(0U, hex) == expected);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == expected);
    TEST_CHECK(SystemMagCalibration_ClearRequest(0U) == expected);
    TEST_CHECK(Test_RecordLoad(0U, packet, 1U) == expected);
    Test_EmptyUnchanged(hash);
}

static void Test_WrongPacket(void)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    uint32_t hash;
    Test_Reset(1U);
    hash = SystemMagCalibration_GenerationHashGet();
    Test_PacketBuild(0U, 42U, packet, hex);
    TEST_CHECK(SystemMagCalibration_PacketApply(0U, hex) == SystemMagCalibrationResult_WrongDevice);
    TEST_CHECK(Test_RecordLoad(0U, packet, 1U) == SystemMagCalibrationResult_WrongDevice);
    Test_PacketBuild(1U, 11U, packet, hex);
    TEST_CHECK(SystemMagCalibration_PacketApply(0U, hex) == SystemMagCalibrationResult_WrongDevice);
    Test_PacketBuild(0U, 11U, packet, hex);
    hex[10] = (hex[10] == '0') ? '1' : '0';
    TEST_CHECK(SystemMagCalibration_PacketApply(0U, hex) == SystemMagCalibrationResult_InvalidObject);
    Test_EmptyUnchanged(hash);
}

static void Test_Sample(const char *scenario)
{
    SystemMagnetometerSample sample;
    SystemMagnetometerSample before;
    SystemMagCalibrationResult expected;
    Test_Reset(1U);
    Test_Apply(0U);
    sample = Test_SampleGet(0U);
    expected = SystemMagCalibrationResult_WrongDevice;
    if (strcmp(scenario, "wrong_sample") == 0) { sample.physical_device_id = 42U; }
    else if (strcmp(scenario, "wrong_sample_descriptor") == 0) { sample.descriptor_id = 41U; }
    else if (strcmp(scenario, "wrong_sample_instance") == 0) { sample.instance_id = 1U; }
    else
    {
        expected = SystemMagCalibrationResult_InvalidObject;
        sample.magnetic_field_b_uT[1] = FLT_MAX;
    }
    (void)memcpy(&before, &sample, sizeof(before));
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == expected);
    TEST_CHECK(memcmp(&sample, &before, sizeof(sample)) == 0);
}

static void Test_Normal(void)
{
    SystemMagnetometerSample sample;
    SystemMagCalibrationStatus status;
    Test_Reset(1U);
    /* Host calibration consumes physical units, not a chip calibration opcode. */
    s_capabilities = SYSTEM_MAG_CAP_PHYSICAL_UNIT;
    Test_Apply(0U);
    sample = Test_SampleGet(0U);
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(sample.magnetic_field_b_uT[0] == 1.0f);
    TEST_CHECK(sample.magnetic_field_b_uT[1] == 4.0f);
    TEST_CHECK(sample.magnetic_field_b_uT[2] == 3.0f);
    TEST_CHECK(sample.raw[0] == 123 && sample.sequence == 17U);
    TEST_CHECK(sample.sample_timestamp_us == 123456789ULL);
    TEST_CHECK(sample.calibration_valid == 1U);
    TEST_CHECK((sample.valid_mask & SYSTEM_MAG_VALID_CALIBRATED) != 0U);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 1U && status.saved == 0U);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 0U);
}

static void Test_SaveFailure(void)
{
    SystemMagCalibrationStatus status;
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    uint8_t instance;
    uint32_t request;
    uint32_t previous;
    uint32_t hash;
    Test_Reset(1U);
    Test_Apply(0U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_PendingGet(&instance, packet, &request) == SystemMagCalibrationResult_Ok);
    previous = request;
    hash = SystemMagCalibration_GenerationHashGet();
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U, request + 1U, 1U, 7U) == SystemMagCalibrationResult_Busy);
    TEST_CHECK(SystemMagCalibration_GenerationHashGet() == hash);
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U, request, 0U, 0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.save_failed == 1U && status.save_pending == 0U && status.saved == 0U);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 0U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_PendingGet(&instance, packet, &request) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(previous != request && instance == 0U);
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U, request, 1U, 7U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.generation == 7U && status.saved == 1U && status.save_failed == 0U);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 1U);
}

static void Test_StoredAndClear(void)
{
    SystemMagCalibrationStatus status;
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    uint8_t instance;
    uint32_t request;
    Test_Reset(2U);
    Test_PacketBuild(1U, 12U, packet, hex);
    TEST_CHECK(Test_RecordLoad(1U, packet, 4U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 0U);
    TEST_CHECK(SystemMagCalibration_StatusGet(1U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.saved == 1U && status.generation == 4U && status.physical_device_id == 12U);
    TEST_CHECK(SystemMagCalibration_ClearRequest(1U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_PendingGet(&instance, packet, &request) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(instance == 1U && packet[0] == 0U);
    TEST_CHECK(SystemMagCalibration_SaveComplete(1U, request, 1U, 5U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_ReadyForMissionGet() == 1U);
    Test_Reset(2U);
    TEST_CHECK(Test_RecordLoad(1U, packet, 5U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_StatusGet(1U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.active == 0U && status.generation == 5U);
}

static void Test_ProviderLoss(void)
{
    SystemMagCalibrationStatus before;
    SystemMagCalibrationStatus after;
    uint32_t hash;
    Test_Reset(1U);
    Test_Apply(0U);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &before) == SystemMagCalibrationResult_Ok);
    hash = SystemMagCalibration_GenerationHashGet();
    s_capability_result = SYSTEM_DEVICE_UNSUPPORTED;
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_NotReady);
    TEST_CHECK(SystemMagCalibration_ClearRequest(0U) == SystemMagCalibrationResult_NotReady);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &after) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(after.active == before.active && after.saved == before.saved &&
        after.save_pending == before.save_pending && after.generation == before.generation);
    TEST_CHECK(SystemMagCalibration_GenerationHashGet() == hash);
}

static void Test_ChangedIdentity(void)
{
    uint32_t hash;
    Test_Reset(1U);
    Test_Apply(0U);
    hash = SystemMagCalibration_GenerationHashGet();
    s_descriptors[0].physical_device_id = 42U;
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_WrongDevice);
    TEST_CHECK(SystemMagCalibration_ClearRequest(0U) == SystemMagCalibrationResult_WrongDevice);
    TEST_CHECK(SystemMagCalibration_GenerationHashGet() == hash);
}

static void Test_DoubleCorrection(void)
{
    SystemMagnetometerSample sample;
    SystemMagnetometerSample before;
    Test_Reset(1U);
    Test_Apply(0U);
    sample = Test_SampleGet(0U);
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_Ok);
    before = sample;
    TEST_CHECK(SystemMagCalibration_SampleApply(0U, &sample) == SystemMagCalibrationResult_NotReady);
    TEST_CHECK(memcmp(&sample, &before, sizeof(sample)) == 0);
}

static void Test_Snapshot(void)
{
    SystemMagCalibrationSnapshot snapshot;
    SystemMagCalibrationSnapshot unchanged;
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    uint8_t instance;
    uint32_t request;
    Test_Reset(1U);
    (void)memset(&snapshot,0xA5,sizeof(snapshot));unchanged=snapshot;
    TEST_CHECK(SystemMagCalibration_SnapshotGet(0U,&snapshot)==SystemMagCalibrationResult_NotReady);
    TEST_CHECK(memcmp(&snapshot,&unchanged,sizeof(snapshot))==0);
    Test_PacketBuild(0U,11U,packet,hex);
    TEST_CHECK(Test_RecordLoad(0U,packet,8U)==SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_SnapshotGet(0U,&snapshot)==SystemMagCalibrationResult_Ok);
    TEST_CHECK(snapshot.status.saved==1U&&snapshot.status.generation==8U);
    TEST_CHECK(snapshot.bias[0]==12.0f&&snapshot.bias[1]==-8.0f&&snapshot.matrix[1][1]==2.0f);
    Test_Apply(0U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U)==SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_PendingGet(&instance,packet,&request)==SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U,request,0U,0U)==SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_SnapshotGet(0U,&snapshot)==SystemMagCalibrationResult_Ok);
    TEST_CHECK(snapshot.status.generation==8U&&snapshot.status.save_failed==1U);
    TEST_CHECK(snapshot.bias[0]==12.0f&&snapshot.matrix[1][1]==2.0f);
    unchanged=snapshot;
    TEST_CHECK(SystemMagCalibration_SnapshotGet(1U,&snapshot)==SystemMagCalibrationResult_NotPresent);
    TEST_CHECK(memcmp(&snapshot,&unchanged,sizeof(snapshot))==0);
}

static void Test_ReplacementFailure(void)
{
    SystemMagCalibrationStatus status;
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    char hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS + 1U];
    uint8_t instance;
    uint32_t request;
    Test_Reset(1U);
    Test_PacketBuild(0U, 11U, packet, hex);
    TEST_CHECK(Test_RecordLoad(0U, packet, 8U) == SystemMagCalibrationResult_Ok);
    Test_Apply(0U);
    TEST_CHECK(SystemMagCalibration_SaveRequest(0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_PendingGet(&instance, packet, &request) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_SaveComplete(0U, request, 0U, 0U) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(SystemMagCalibration_StatusGet(0U, &status) == SystemMagCalibrationResult_Ok);
    TEST_CHECK(status.saved == 1U && status.generation == 8U && status.save_failed == 1U);
}

#if defined(SILVERSTAR_MAG_TF_TEST)
#include "test_mag_tf.h"
#endif

int main(int argc, char **argv)
{
    TEST_CHECK(argc == 2);
#if defined(SILVERSTAR_MAG_TF_TEST)
    if (strncmp(argv[1], "tf_", 3U) == 0) { TestTf_Run(argv[1]); }
    else
#endif
    if (strncmp(argv[1], "absent_", 7U) == 0) { Test_Absent(argv[1]); }
    else if (strncmp(argv[1], "provider_", 9U) == 0) { Test_Provider(argv[1] + 9); }
    else if (strcmp(argv[1], "wrong_packet") == 0) { Test_WrongPacket(); }
    else if ((strncmp(argv[1], "wrong_sample", 12U) == 0) ||
             (strcmp(argv[1], "sample_atomic") == 0)) { Test_Sample(argv[1]); }
    else if (strcmp(argv[1], "normal") == 0) { Test_Normal(); }
    else if (strcmp(argv[1], "save_failure") == 0) { Test_SaveFailure(); }
    else if (strcmp(argv[1], "stored_clear") == 0) { Test_StoredAndClear(); }
    else if (strcmp(argv[1], "capability_loss") == 0) { Test_ProviderLoss(); }
    else if (strcmp(argv[1], "changed_identity") == 0) { Test_ChangedIdentity(); }
    else if (strcmp(argv[1], "double_correction") == 0) { Test_DoubleCorrection(); }
    else if (strcmp(argv[1], "replacement_failure") == 0) { Test_ReplacementFailure(); }
    else if (strcmp(argv[1], "snapshot") == 0) { Test_Snapshot(); }
    else { TEST_CHECK(0U); }
    TEST_CHECK(s_critical_depth == 0U);
#if !defined(SILVERSTAR_MAG_CAL_ARM_LINK_ONLY)
    (void)printf("PASS|%s\n", argv[1]);
#endif
    return 0;
}
