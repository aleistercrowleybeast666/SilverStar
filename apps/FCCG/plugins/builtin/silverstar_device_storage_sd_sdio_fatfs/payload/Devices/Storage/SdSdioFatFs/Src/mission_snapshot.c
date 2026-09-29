#include "system_mission_snapshot_if.h"

#include <stddef.h>
#include <string.h>

#include "air_link_config.h"
#include "persistent_storage.h"
#include "silverstar_assert.h"
#include "system_calibration.h"
#include "system_descriptor_if.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_lifecycle.h"
#include "system_profile.h"
#include "system_project_parameters_if.h"
#include "system_source_selector.h"
#include "system_storage_if.h"
#include "system_user_config.h"

#define MISSION_SNAPSHOT_SCHEMA 1U
#define MISSION_SNAPSHOT_DEVICE_CHUNK_COUNT 16U
#define MISSION_SNAPSHOT_PARAMETER_CHUNK_COUNT 48U
#define MISSION_SNAPSHOT_OBJECT_COUNT 6U
#define MISSION_SNAPSHOT_BANK_SPAN 8U
#define MISSION_SNAPSHOT_MAG_OBJECT_CAPACITY 512U

typedef struct
{
    uint16_t length;
    uint8_t overflow;
} MissionSnapshotWriter;

/* LoggerTask is the sole FatFs owner; the buffer never enters DMA. */
static uint8_t s_payload[PERSISTENT_STORAGE_OBJECT_MAX_BYTES];
static uint8_t s_mag_data[MISSION_SNAPSHOT_MAG_OBJECT_CAPACITY];
static uint32_t s_active_mission_id;
static uint32_t s_commit_sequence;
static uint8_t s_active_bank = 0xFFU;

static void MissionSnapshot_WriterReset(MissionSnapshotWriter *writer,
    uint8_t section, uint8_t count)
{
    SILVERSTAR_ASSERT_OBJECT(writer, MissionSnapshotWriter,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(s_payload, 0, sizeof(s_payload));
    writer->length = 0U;
    writer->overflow = 0U;
    s_payload[writer->length++] = 'S';
    s_payload[writer->length++] = 'S';
    s_payload[writer->length++] = 'M';
    s_payload[writer->length++] = 'S';
    s_payload[writer->length++] = MISSION_SNAPSHOT_SCHEMA;
    s_payload[writer->length++] = section;
    s_payload[writer->length++] = count;
    s_payload[writer->length++] = 0U;
}

static void MissionSnapshot_U8Write(MissionSnapshotWriter *writer,
    uint8_t value)
{
    if (writer->length >= sizeof(s_payload))
    { writer->overflow = 1U; return; }
    s_payload[writer->length++] = value;
}

static void MissionSnapshot_U16Write(MissionSnapshotWriter *writer,
    uint16_t value)
{
    MissionSnapshot_U8Write(writer, (uint8_t)value);
    MissionSnapshot_U8Write(writer, (uint8_t)(value >> 8U));
}

static void MissionSnapshot_U32Write(MissionSnapshotWriter *writer,
    uint32_t value)
{
    MissionSnapshot_U16Write(writer, (uint16_t)value);
    MissionSnapshot_U16Write(writer, (uint16_t)(value >> 16U));
}

static void MissionSnapshot_FloatWrite(MissionSnapshotWriter *writer,
    float value)
{
    uint32_t bits;
    _Static_assert(sizeof(float) == sizeof(uint32_t),
        "Mission snapshot requires binary32 floats");
    (void)memcpy(&bits, &value, sizeof(bits));
    MissionSnapshot_U32Write(writer, bits);
}

static uint32_t MissionSnapshot_HashGet(const uint8_t *data,
    uint16_t length)
{
    uint32_t hash = 0x811C9DC5UL;
    uint16_t index;
    for (index = 0U; index < length; index++)
    { hash = (hash ^ data[index]) * 0x01000193UL; }
    return hash;
}

static SystemMissionSnapshotResult MissionSnapshot_SectionCommit(
    MissionSnapshotWriter *writer, uint8_t instance,
    uint32_t *generation, uint32_t *hash)
{
    PersistentStorageResult result;

    SILVERSTAR_ASSERT_OBJECT(writer, MissionSnapshotWriter,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (writer->overflow != 0U)
    { return SystemMissionSnapshotResult_TooLarge; }
    *hash = MissionSnapshot_HashGet(s_payload, writer->length);
    result = PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT,
        instance, s_payload, writer->length, generation);
    return (result == PERSISTENT_STORAGE_OK) ?
        SystemMissionSnapshotResult_Ok :
        SystemMissionSnapshotResult_StorageError;
}

static SystemMissionSnapshotResult MissionSnapshot_DevicesWrite(
    uint8_t base, uint8_t chunk, uint32_t *generation, uint32_t *hash)
{
    MissionSnapshotWriter writer;
    const uint16_t count = SystemDescriptor_DeviceCountGet();
    const uint16_t start = (uint16_t)chunk *
        MISSION_SNAPSHOT_DEVICE_CHUNK_COUNT;
    uint16_t index;
    uint16_t limit = count;

    SILVERSTAR_ASSERT(chunk < 2U, SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT_OBJECT(generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(hash, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (count > SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX)
    { return SystemMissionSnapshotResult_TooLarge; }
    if (limit > start + MISSION_SNAPSHOT_DEVICE_CHUNK_COUNT)
    { limit = start + MISSION_SNAPSHOT_DEVICE_CHUNK_COUNT; }
    MissionSnapshot_WriterReset(&writer, (uint8_t)(1U + chunk),
        (uint8_t)((limit > start) ? (uint16_t)(limit - start) : 0U));
    for (index = start; index < limit; index++)
    {
        SystemDeviceDescriptor descriptor;
        if (SystemDescriptor_DeviceGet(index, &descriptor) != SYSTEM_DEVICE_OK)
        { return SystemMissionSnapshotResult_DataError; }
        MissionSnapshot_U16Write(&writer, descriptor.descriptor_id);
        MissionSnapshot_U16Write(&writer, descriptor.physical_device_id);
        MissionSnapshot_U8Write(&writer, (uint8_t)descriptor.device_class);
        MissionSnapshot_U8Write(&writer, descriptor.instance_id);
        MissionSnapshot_U16Write(&writer, descriptor.driver_id);
        MissionSnapshot_U16Write(&writer, descriptor.flags);
        MissionSnapshot_U32Write(&writer, descriptor.capability_mask);
        MissionSnapshot_U32Write(&writer, descriptor.configured_rate_hz);
        MissionSnapshot_U32Write(&writer, descriptor.driver_name_hash);
        MissionSnapshot_U32Write(&writer, descriptor.model_name_hash);
    }
    return MissionSnapshot_SectionCommit(&writer, (uint8_t)(base + 1U + chunk),
        generation, hash);
}

static SystemMissionSnapshotResult MissionSnapshot_AlgorithmsWrite(
    uint8_t base, uint32_t *generation, uint32_t *hash)
{
    MissionSnapshotWriter writer;
    const uint16_t count = SystemDescriptor_AlgorithmCountGet();
    uint16_t index;

    SILVERSTAR_ASSERT_OBJECT(generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(hash, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (count > SYSTEM_DESCRIPTOR_ALGORITHM_COUNT_MAX)
    { return SystemMissionSnapshotResult_TooLarge; }
    MissionSnapshot_WriterReset(&writer, 3U, (uint8_t)count);
    for (index = 0U; index < count; index++)
    {
        SystemAlgorithmDescriptor descriptor;
        if (SystemDescriptor_AlgorithmGet(index, &descriptor) != SYSTEM_DEVICE_OK)
        { return SystemMissionSnapshotResult_DataError; }
        MissionSnapshot_U16Write(&writer, descriptor.descriptor_id);
        MissionSnapshot_U8Write(&writer, (uint8_t)descriptor.algorithm_class);
        MissionSnapshot_U8Write(&writer, descriptor.instance_id);
        MissionSnapshot_U16Write(&writer, descriptor.algorithm_id);
        MissionSnapshot_U16Write(&writer, descriptor.flags);
        MissionSnapshot_U32Write(&writer, descriptor.config_digest);
        MissionSnapshot_U32Write(&writer, descriptor.name_hash);
    }
    return MissionSnapshot_SectionCommit(&writer, (uint8_t)(base + 3U),
        generation, hash);
}

static SystemMissionSnapshotResult MissionSnapshot_ParametersWrite(
    uint8_t base, uint8_t chunk, uint32_t *generation, uint32_t *hash)
{
    MissionSnapshotWriter writer;
    const uint16_t count = SystemProjectParameter_CountGet();
    const uint16_t start = (uint16_t)chunk *
        MISSION_SNAPSHOT_PARAMETER_CHUNK_COUNT;
    uint16_t limit = count;
    uint16_t index;

    SILVERSTAR_ASSERT(chunk < 2U, SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT_OBJECT(generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(hash, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (count > 2U * MISSION_SNAPSHOT_PARAMETER_CHUNK_COUNT)
    { return SystemMissionSnapshotResult_TooLarge; }
    if (limit > start + MISSION_SNAPSHOT_PARAMETER_CHUNK_COUNT)
    { limit = start + MISSION_SNAPSHOT_PARAMETER_CHUNK_COUNT; }
    MissionSnapshot_WriterReset(&writer, (uint8_t)(4U + chunk),
        (uint8_t)((limit > start) ? (uint16_t)(limit - start) : 0U));
    for (index = start; index < limit; index++)
    {
        SystemProjectParameter parameter;
        if (SystemProjectParameter_Get(index, &parameter) !=
            SystemProjectParameterResult_Ok)
        { return SystemMissionSnapshotResult_DataError; }
        MissionSnapshot_U32Write(&writer, parameter.key_hash);
        MissionSnapshot_U32Write(&writer, parameter.value_bits);
        MissionSnapshot_U8Write(&writer, (uint8_t)parameter.kind);
    }
    return MissionSnapshot_SectionCommit(&writer, (uint8_t)(base + 4U + chunk),
        generation, hash);
}

static SystemMissionSnapshotResult MissionSnapshot_CalibrationWrite(
    uint8_t base, uint32_t *generation, uint32_t *hash,
    SystemMissionSnapshotStatus *status)
{
    MissionSnapshotWriter writer;
    SystemCalibrationImuCorrection correction;
    uint16_t mag_length = 0U;
    uint32_t mag_generation = 0U;
    PersistentStorageResult mag_result;
    uint8_t axis;

    SILVERSTAR_ASSERT_OBJECT(status, SystemMissionSnapshotStatus,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(hash, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK)
    { return SystemMissionSnapshotResult_NotReady; }
    if (correction.ready == 0U)
    { return SystemMissionSnapshotResult_NotReady; }
    MissionSnapshot_WriterReset(&writer, 6U, 1U);
    status->calibration_generation = SystemCalibration_GenerationGet();
    MissionSnapshot_U32Write(&writer, status->calibration_generation);
    MissionSnapshot_U8Write(&writer, (uint8_t)correction.mode);
    MissionSnapshot_U8Write(&writer, correction.ready);
    for (axis = 0U; axis < 3U; axis++)
    {
        MissionSnapshot_FloatWrite(&writer, correction.accel_bias_mps2[axis]);
        MissionSnapshot_FloatWrite(&writer, correction.accel_scale[axis]);
        MissionSnapshot_FloatWrite(&writer, correction.gyro_bias_radps[axis]);
        MissionSnapshot_FloatWrite(&writer, correction.gyro_scale[axis]);
    }
    status->imu_correction_hash = MissionSnapshot_HashGet(s_payload,
        writer.length);
    mag_result = PersistentStorage_ObjectRead(
        PERSISTENT_STORAGE_OBJECT_MAG_CALIBRATION, 0U,
        s_mag_data, sizeof(s_mag_data), &mag_length, &mag_generation);
    if ((mag_result != PERSISTENT_STORAGE_OK) &&
        (mag_result != PERSISTENT_STORAGE_NOT_FOUND))
    { return SystemMissionSnapshotResult_StorageError; }
    status->mag_calibration_generation = mag_generation;
    MissionSnapshot_U32Write(&writer, mag_generation);
    MissionSnapshot_U32Write(&writer,
        (mag_result == PERSISTENT_STORAGE_OK) ?
        MissionSnapshot_HashGet(s_mag_data, mag_length) : 0U);
    return MissionSnapshot_SectionCommit(&writer, (uint8_t)(base + 6U),
        generation, hash);
}

static void MissionSnapshot_AirProfileWrite(MissionSnapshotWriter *writer)
{
    MissionSnapshot_U32Write(writer, AIR_LINK_FREQUENCY_HZ);
    MissionSnapshot_U8Write(writer, AIR_LINK_SPREADING_FACTOR);
    MissionSnapshot_U32Write(writer, AIR_LINK_BANDWIDTH_HZ);
    MissionSnapshot_U8Write(writer, AIR_LINK_CODING_RATE_DENOMINATOR);
    MissionSnapshot_U16Write(writer, AIR_LINK_PREAMBLE_SYMBOLS);
    MissionSnapshot_U16Write(writer, AIR_LINK_PACKET_MTU);
    MissionSnapshot_U8Write(writer, (uint8_t)AIR_LINK_TX_POWER_DBM);
}

static SystemMissionSnapshotResult MissionSnapshot_HeaderWrite(
    uint8_t base,
    const SystemMissionSnapshotStatus *status,
    const uint32_t generations[MISSION_SNAPSHOT_OBJECT_COUNT],
    const uint32_t hashes[MISSION_SNAPSHOT_OBJECT_COUNT],
    uint32_t *commit_generation)
{
    MissionSnapshotWriter writer;
    const SystemProfile *profile = SystemProfile_Get();
    static const uint8_t build_tag[] = SILVERSTAR_LOG_BUILD_TAG;
    uint8_t index;

    _Static_assert(sizeof(build_tag) == 9U,
        "Mission snapshot build tag must contain eight bytes");
    SILVERSTAR_ASSERT_OBJECT(status, SystemMissionSnapshotStatus,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(generations, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(hashes, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(commit_generation, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (profile == NULL) { return SystemMissionSnapshotResult_DataError; }
    MissionSnapshot_WriterReset(&writer, 0U,
        MISSION_SNAPSHOT_OBJECT_COUNT);
    MissionSnapshot_U8Write(&writer, base);
    MissionSnapshot_U32Write(&writer, status->mission_id);
    MissionSnapshot_U32Write(&writer, status->snapshot_sequence);
    MissionSnapshot_U32Write(&writer, profile->profile_id);
    MissionSnapshot_U32Write(&writer, SystemDescriptor_ConfigDigestGet());
    MissionSnapshot_U8Write(&writer, SILVERSTAR_VERSION_MAJOR);
    MissionSnapshot_U8Write(&writer, SILVERSTAR_VERSION_MINOR);
    MissionSnapshot_U8Write(&writer, SILVERSTAR_VERSION_PATCH);
    MissionSnapshot_U8Write(&writer, SILVERSTAR_VERSION_BUILD);
    for (index = 0U; index < 8U; index++)
    { MissionSnapshot_U8Write(&writer, build_tag[index]); }
    MissionSnapshot_U8Write(&writer, 0U); /* No trajectory guidance plan. */
    MissionSnapshot_U32Write(&writer, SYSTEM_IMU_OUTPUT_RATE_HZ);
    MissionSnapshot_U16Write(&writer, SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT);
    MissionSnapshot_U32Write(&writer, SYSTEM_IMU_OUTPUT_RATE_HZ /
        SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT);
    MissionSnapshot_U8Write(&writer, status->imu_source_instance);
    MissionSnapshot_U8Write(&writer, status->gnss_source_instance);
    MissionSnapshot_U32Write(&writer, status->calibration_generation);
    MissionSnapshot_U32Write(&writer, status->imu_correction_hash);
    MissionSnapshot_U32Write(&writer, status->mag_calibration_generation);
    MissionSnapshot_AirProfileWrite(&writer);
    for (index = 0U; index < MISSION_SNAPSHOT_OBJECT_COUNT; index++)
    {
        MissionSnapshot_U32Write(&writer, generations[index]);
        MissionSnapshot_U32Write(&writer, hashes[index]);
    }
    if (writer.overflow != 0U)
    { return SystemMissionSnapshotResult_TooLarge; }
    return (PersistentStorage_ObjectWriteAtomic(
        PERSISTENT_STORAGE_OBJECT_MISSION_SNAPSHOT, base,
        s_payload, writer.length, commit_generation) ==
        PERSISTENT_STORAGE_OK) ? SystemMissionSnapshotResult_Ok :
        SystemMissionSnapshotResult_StorageError;
}

static SystemMissionSnapshotResult MissionSnapshot_SectionsWrite(
    uint8_t base, SystemMissionSnapshotStatus *status,
    uint32_t generations[MISSION_SNAPSHOT_OBJECT_COUNT],
    uint32_t hashes[MISSION_SNAPSHOT_OBJECT_COUNT])
{
    SystemMissionSnapshotResult result;
    SILVERSTAR_ASSERT_OBJECT(status, SystemMissionSnapshotStatus,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(generations, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(hashes, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = MissionSnapshot_DevicesWrite(base, 0U,
        &generations[0], &hashes[0]);
    if (result != SystemMissionSnapshotResult_Ok) { return result; }
    result = MissionSnapshot_DevicesWrite(base, 1U,
        &generations[1], &hashes[1]);
    if (result != SystemMissionSnapshotResult_Ok) { return result; }
    result = MissionSnapshot_AlgorithmsWrite(base,
        &generations[2], &hashes[2]);
    if (result != SystemMissionSnapshotResult_Ok) { return result; }
    result = MissionSnapshot_ParametersWrite(base, 0U,
        &generations[3], &hashes[3]);
    if (result != SystemMissionSnapshotResult_Ok) { return result; }
    result = MissionSnapshot_ParametersWrite(base, 1U,
        &generations[4], &hashes[4]);
    if (result != SystemMissionSnapshotResult_Ok) { return result; }
    return MissionSnapshot_CalibrationWrite(base, &generations[5],
        &hashes[5], status);
}

SystemMissionSnapshotResult SystemMissionSnapshot_Create(
    SystemMissionSnapshotStatus *status)
{
    uint32_t generations[MISSION_SNAPSHOT_OBJECT_COUNT] = {0U};
    uint32_t hashes[MISSION_SNAPSHOT_OBJECT_COUNT] = {0U};
    SystemMissionSnapshotResult result;
    uint8_t base;

    if (status == NULL) { return SystemMissionSnapshotResult_DataError; }
    SILVERSTAR_ASSERT_OBJECT(status, SystemMissionSnapshotStatus,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(MISSION_SNAPSHOT_OBJECT_COUNT <= 31U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    (void)memset(status, 0, sizeof(*status));
    if (SystemStorage_MissionIdGet(&status->mission_id) != SYSTEM_DEVICE_OK)
    { return SystemMissionSnapshotResult_NotReady; }
    if (SystemCalibration_IsReady() == 0U)
    { return SystemMissionSnapshotResult_NotReady; }
    if (SystemSourceSelector_ImuActiveInstanceGet(
            &status->imu_source_instance) != SYSTEM_DEVICE_OK)
    { return SystemMissionSnapshotResult_NotReady; }
    if (SystemSourceSelector_GnssActiveInstanceGet(
            &status->gnss_source_instance) != SYSTEM_DEVICE_OK)
    { status->gnss_source_instance = 0xFFU; }
    if (s_active_mission_id != status->mission_id)
    {
        s_active_mission_id = status->mission_id;
        s_active_bank = 0xFFU;
        s_commit_sequence = 0U;
    }
    base = (s_active_bank == 0U) ? MISSION_SNAPSHOT_BANK_SPAN : 0U;
    result = MissionSnapshot_SectionsWrite(base, status,
        generations, hashes);
    if (result != SystemMissionSnapshotResult_Ok) { return result; }
    if (s_commit_sequence == UINT32_MAX)
    { return SystemMissionSnapshotResult_DataError; }
    status->snapshot_sequence = s_commit_sequence + 1U;
    result = MissionSnapshot_HeaderWrite(base, status, generations, hashes,
        &status->commit_generation);
    if (result == SystemMissionSnapshotResult_Ok)
    {
        s_active_bank = base;
        s_commit_sequence = status->snapshot_sequence;
        status->snapshot_base_instance = base;
    }
    return result;
}

SystemMissionSnapshotResult SystemMissionSnapshot_FinalStatusWrite(
    uint64_t timestamp_us, uint8_t logger_fault)
{
    MissionSnapshotWriter writer;
    SystemFlightRecoveryStatus recovery;
    SystemHealthSnapshot health;
    SystemStorageHealth storage;
    uint32_t mission_id = 0U;
    uint32_t generation = 0U;
    uint32_t hash = 0U;
    uint8_t recovery_valid;
    uint8_t storage_valid;

    SILVERSTAR_ASSERT(logger_fault <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(timestamp_us != 0ULL,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (SystemStorage_MissionIdGet(&mission_id) != SYSTEM_DEVICE_OK)
    { return SystemMissionSnapshotResult_NotReady; }
    (void)memset(&recovery, 0, sizeof(recovery));
    recovery_valid = (uint8_t)(SystemFlightRecovery_StatusGet(&recovery) ==
        SYSTEM_DEVICE_OK);
    (void)memset(&health, 0, sizeof(health));
    SystemHealth_GetSnapshot(&health);
    (void)memset(&storage, 0, sizeof(storage));
    storage_valid = (uint8_t)(SystemStorage_HealthGet(&storage) ==
        SYSTEM_DEVICE_OK);
    MissionSnapshot_WriterReset(&writer, 7U, 1U);
    MissionSnapshot_U32Write(&writer, mission_id);
    MissionSnapshot_U32Write(&writer, (uint32_t)timestamp_us);
    MissionSnapshot_U32Write(&writer, (uint32_t)(timestamp_us >> 32U));
    MissionSnapshot_U8Write(&writer, (uint8_t)SystemLifecycle_GetState());
    MissionSnapshot_U8Write(&writer, recovery_valid);
    MissionSnapshot_U8Write(&writer, recovery.landing_detected);
    MissionSnapshot_U8Write(&writer, recovery.deploy_triggered);
    MissionSnapshot_U8Write(&writer, recovery.deploy_completed);
    MissionSnapshot_U8Write(&writer, logger_fault);
    MissionSnapshot_U8Write(&writer, storage_valid);
    MissionSnapshot_U8Write(&writer,
        (uint8_t)((storage.healthy == 0U) || (storage.mounted == 0U)));
    MissionSnapshot_U32Write(&writer, health.start_blocking_mask);
    MissionSnapshot_U32Write(&writer, health.warning_mask);
    MissionSnapshot_U32Write(&writer, health.sequence);
    MissionSnapshot_U32Write(&writer, (uint32_t)recovery.deploy_action_result);
    MissionSnapshot_U32Write(&writer,
        (uint32_t)recovery.landing_transition_result);
    return MissionSnapshot_SectionCommit(&writer, 7U, &generation, &hash);
}
