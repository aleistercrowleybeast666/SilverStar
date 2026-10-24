#include "system_mag_calibration.h"

#include <math.h>
#include <string.h>

#include "platform_critical.h"
#include "platform_memory.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "system_installation_capture_if.h"

#define SYSTEM_MAG_CAL_BODY_BYTES 80U
#define SYSTEM_MAG_CAL_FLOAT_COUNT 16U
#define SYSTEM_MAG_CAL_CRC_POLYNOMIAL 0xEDB88320UL

typedef struct
{
    float bias[3];
    float matrix[3][3];
} SystemMagCalibrationCorrection;

typedef struct
{
    uint8_t candidate[SYSTEM_MAG_CAL_PACKET_BYTES];
    uint8_t committed[SYSTEM_MAG_CAL_PACKET_BYTES];
    SystemMagCalibrationCorrection correction;
    uint32_t request_id;
    uint32_t committed_generation;
    uint32_t driver_hash;
    uint32_t model_hash;
    uint16_t descriptor_id;
    uint8_t candidate_valid;
    SystemMagCalibrationStatus status;
} SystemMagCalibrationEntry;

/* CPU-owned state: runtime readers/writers retain their critical sections.
 * No entry address is passed to storage, transport or DMA. */
static PLATFORM_CPU_FAST_BSS SystemMagCalibrationEntry
    s_mag_calibration[PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX];
static uint32_t s_mag_calibration_next_request_id;

static uint32_t SystemMagCalibration_U32Read(const uint8_t *data)
{
    return (uint32_t)data[0] | ((uint32_t)data[1] << 8U) |
        ((uint32_t)data[2] << 16U) | ((uint32_t)data[3] << 24U);
}

static void SystemMagCalibration_U32Write(uint8_t *data, uint32_t value)
{
    uint8_t index;
    for (index = 0U; index < 4U; index++)
    { data[index] = (uint8_t)(value >> (8U * index)); }
}

static float SystemMagCalibration_F32Read(const uint8_t *data)
{
    uint32_t bits = SystemMagCalibration_U32Read(data);
    float value;
    (void)memcpy(&value, &bits, sizeof(value));
    return value;
}

static uint8_t SystemMagCalibration_HexNibbleGet(char character)
{
    if ((character >= '0') && (character <= '9'))
    { return (uint8_t)(character - '0'); }
    if ((character >= 'A') && (character <= 'F'))
    { return (uint8_t)(character - 'A' + 10); }
    if ((character >= 'a') && (character <= 'f'))
    { return (uint8_t)(character - 'a' + 10); }
    return UINT8_MAX;
}

static SystemMagCalibrationResult SystemMagCalibration_HexDecode(
    const char *hex, uint8_t *packet)
{
    uint16_t index;
    if ((hex == NULL) || (packet == NULL))
    { return SystemMagCalibrationResult_InvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(hex, char, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(packet, uint8_t, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < SYSTEM_MAG_CAL_PACKET_BYTES; index++)
    {
        uint8_t high;
        uint8_t low;
        if ((hex[index * 2U] == '\0') ||
            (hex[index * 2U + 1U] == '\0'))
        { return SystemMagCalibrationResult_InvalidObject; }
        high = SystemMagCalibration_HexNibbleGet(hex[index * 2U]);
        if (high == UINT8_MAX)
        { return SystemMagCalibrationResult_InvalidObject; }
        low = SystemMagCalibration_HexNibbleGet(hex[index * 2U + 1U]);
        if (low == UINT8_MAX)
        { return SystemMagCalibrationResult_InvalidObject; }
        packet[index] = (uint8_t)((high << 4U) | low);
    }
    return (hex[SYSTEM_MAG_CAL_PACKET_HEX_CHARS] == '\0') ?
        SystemMagCalibrationResult_Ok :
        SystemMagCalibrationResult_InvalidObject;
}

static uint32_t SystemMagCalibration_CrcGet(const uint8_t *data)
{
    uint32_t crc = 0xFFFFFFFFUL;
    uint16_t index;
    uint8_t bit;
    for (index = 0U; index < SYSTEM_MAG_CAL_BODY_BYTES; index++)
    {
        crc ^= data[index];
        for (bit = 0U; bit < 8U; bit++)
        {
            crc = (crc >> 1U) ^
                (((crc & 1U) != 0U) ? SYSTEM_MAG_CAL_CRC_POLYNOMIAL : 0U);
        }
    }
    return ~crc;
}

static uint8_t SystemMagCalibration_MatrixValid(const float values[16])
{
    const float *matrix = &values[3];
    float minor;
    float determinant;
    uint8_t row;
    uint8_t column;
    SILVERSTAR_ASSERT_OBJECT(values, float, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(isfinite(matrix[0]) && isfinite(matrix[8]),
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (row = 0U; row < 3U; row++)
    {
        for (column = 0U; column < 3U; column++)
        {
            if ((fabsf(matrix[row * 3U + column]) > 10.0f) ||
                (fabsf(matrix[row * 3U + column] -
                       matrix[column * 3U + row]) > 0.02f))
            { return 0U; }
        }
    }
    minor = matrix[0] * matrix[4] - matrix[1] * matrix[3];
    determinant = matrix[0] * (matrix[4] * matrix[8] - matrix[5] * matrix[7]) -
        matrix[1] * (matrix[3] * matrix[8] - matrix[5] * matrix[6]) +
        matrix[2] * (matrix[3] * matrix[7] - matrix[4] * matrix[6]);
    return (uint8_t)((matrix[0] > 0.0001f) && (minor > 0.000001f) &&
        (determinant > 0.000001f));
}

static SystemMagCalibrationResult SystemMagCalibration_PacketValidate(
    uint8_t instance_id, uint16_t physical_device_id,
    const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES], float values[16])
{
    uint16_t index;
    uint16_t sample_count;
    SILVERSTAR_ASSERT_OBJECT(packet, uint8_t, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(values, float, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((packet[0] != 1U) || (packet[1] != 1U) || (packet[5] != 0U) ||
        (SystemMagCalibration_CrcGet(packet) !=
         SystemMagCalibration_U32Read(&packet[SYSTEM_MAG_CAL_BODY_BYTES])))
    { return SystemMagCalibrationResult_InvalidObject; }
    if ((((uint16_t)packet[2] | ((uint16_t)packet[3] << 8U)) !=
         physical_device_id) || (packet[4] != instance_id))
    { return SystemMagCalibrationResult_WrongDevice; }
    for (index = 0U; index < SYSTEM_MAG_CAL_FLOAT_COUNT; index++)
    {
        values[index] = SystemMagCalibration_F32Read(&packet[6U + index * 4U]);
        if (!isfinite(values[index]))
        { return SystemMagCalibrationResult_InvalidObject; }
    }
    if (SystemMagCalibration_MatrixValid(values) == 0U)
    { return SystemMagCalibrationResult_InvalidObject; }
    for (index = 0U; index < 3U; index++)
    {
        if (fabsf(values[index]) > 1000.0f)
        { return SystemMagCalibrationResult_InvalidObject; }
    }
    sample_count = (uint16_t)packet[78] | ((uint16_t)packet[79] << 8U);
    if ((values[12] < 10.0f) || (values[12] > 100.0f) ||
        (values[13] < 0.0f) || (values[13] > values[12] * 0.15f) ||
        (values[14] < values[13]) || (values[14] > values[12] * 0.50f) ||
        (values[15] < 1.0f) || (values[15] > 25.0f) ||
        (sample_count < 128U) || (sample_count > 4096U))
    { return SystemMagCalibrationResult_InvalidObject; }
    for (index = 70U; index < 78U; index++)
    {
        if (packet[index] < 4U)
        { return SystemMagCalibrationResult_InvalidObject; }
    }
    return SystemMagCalibrationResult_Ok;
}

static SystemMagCalibrationResult SystemMagCalibration_DescriptorGet(
    uint8_t instance_id, SystemDeviceDescriptor *descriptor)
{
    if ((instance_id >= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX) ||
        (descriptor == NULL))
    { return SystemMagCalibrationResult_InvalidArgument; }
    if (ProjectDeviceInstance_DescriptorGet(
            SYSTEM_DEVICE_CLASS_MAGNETOMETER, instance_id,
            descriptor) != SYSTEM_DEVICE_OK)
    { return SystemMagCalibrationResult_NotPresent; }
    if ((descriptor->flags & SYSTEM_DESCRIPTOR_FLAG_ENABLED) == 0U)
    { return SystemMagCalibrationResult_NotPresent; }
    if ((descriptor->device_class != SYSTEM_DEVICE_CLASS_MAGNETOMETER) ||
        (descriptor->instance_id != instance_id) ||
        (descriptor->physical_device_id == 0U) ||
        (descriptor->descriptor_id == 0U))
    { return SystemMagCalibrationResult_WrongDevice; }
    return SystemMagCalibrationResult_Ok;
}

static SystemMagCalibrationResult SystemMagCalibration_PacketDecode(
    uint8_t instance_id, uint16_t physical_device_id,
    const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES], float values[16])
{
    uint16_t index;
    if (packet[0] != 0U)
    { return SystemMagCalibration_PacketValidate(instance_id, physical_device_id, packet, values); }
    for (index = 1U; index < SYSTEM_MAG_CAL_PACKET_BYTES; index++)
    {
        if (packet[index] != 0U) { return SystemMagCalibrationResult_InvalidObject; }
    }
    return SystemMagCalibrationResult_Ok;
}

static SystemMagCalibrationResult SystemMagCalibration_ProviderGet(
    uint8_t instance_id, SystemDeviceDescriptor *descriptor)
{
    uint32_t capabilities = 0U;
    SystemDeviceResult device_result;
    SystemMagCalibrationResult result =
        SystemMagCalibration_DescriptorGet(instance_id, descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    /* This is host-fitted correction of physical vectors. A chip's own
     * calibration command capability is a separate, optional operation. */
    device_result = ProjectMagnetometerInstance_CapabilitiesGet(
        instance_id, &capabilities);
    if (device_result == SYSTEM_DEVICE_NOT_PRESENT)
    { return SystemMagCalibrationResult_NotPresent; }
    if ((device_result != SYSTEM_DEVICE_OK) ||
        ((capabilities & SYSTEM_MAG_CAP_PHYSICAL_UNIT) == 0U))
    { return SystemMagCalibrationResult_NotReady; }
    return SystemMagCalibrationResult_Ok;
}

static void SystemMagCalibration_EntrySet(
    uint8_t instance_id, const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    const float values[16], uint32_t generation)
{
    SystemMagCalibrationEntry *entry = &s_mag_calibration[instance_id];
    uint8_t row;
    uint8_t column;
    SILVERSTAR_ASSERT_OBJECT(packet, uint8_t, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(values, float, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (row = 0U; row < 3U; row++)
    {
        entry->correction.bias[row] = values[row];
        for (column = 0U; column < 3U; column++)
        { entry->correction.matrix[row][column] = values[3U + row * 3U + column]; }
    }
    entry->status.generation = generation;
    entry->status.configuration_digest = SystemDescriptor_ConfigDigestGet();
    entry->status.intrinsic_crc =
        SystemMagCalibration_U32Read(&packet[SYSTEM_MAG_CAL_BODY_BYTES]);
    entry->status.physical_device_id =
        (uint16_t)packet[2] | ((uint16_t)packet[3] << 8U);
    entry->status.instance_id = instance_id;
    entry->status.active = 1U;
    entry->status.saved = (uint8_t)(generation != 0U);
    entry->status.save_failed = 0U;
    entry->status.load_error = SystemMagCalibrationResult_Ok;
}

static void SystemMagCalibration_IdentitySet(
    SystemMagCalibrationEntry *entry, const SystemDeviceDescriptor *descriptor)
{
    entry->descriptor_id = descriptor->descriptor_id;
    entry->driver_hash = descriptor->driver_name_hash;
    entry->model_hash = descriptor->model_name_hash;
    entry->status.configuration_digest = SystemDescriptor_ConfigDigestGet();
    entry->status.physical_device_id = descriptor->physical_device_id;
    entry->status.instance_id = descriptor->instance_id;
}

static uint8_t SystemMagCalibration_IdentityMatches(
    const SystemMagCalibrationEntry *entry,
    const SystemDeviceDescriptor *descriptor)
{
    return (uint8_t)((entry->status.physical_device_id == descriptor->physical_device_id) &&
        (entry->descriptor_id == descriptor->descriptor_id) &&
        (entry->driver_hash == descriptor->driver_name_hash) &&
        (entry->model_hash == descriptor->model_name_hash) &&
        (entry->status.configuration_digest == SystemDescriptor_ConfigDigestGet()));
}

void SystemMagCalibration_Init(void)
{
    (void)memset(s_mag_calibration, 0, sizeof(s_mag_calibration));
    s_mag_calibration_next_request_id = 0U;
}

uint8_t SystemMagCalibration_ReadyForMissionGet(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    uint8_t index;
    for (index = 0U; index < PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX; index++)
    {
        const SystemMagCalibrationStatus *status =
            &s_mag_calibration[index].status;
        if ((status->save_pending != 0U) ||
            (status->save_failed != 0U) ||
            (status->load_error != SystemMagCalibrationResult_Ok) ||
            ((status->active != 0U) && (status->saved == 0U)))
        { PlatformCritical_Exit(state); return 0U; }
    }
    PlatformCritical_Exit(state);
    return 1U;
}

uint32_t SystemMagCalibration_GenerationHashGet(void)
{
    PlatformCriticalState state = PlatformCritical_Enter();
    uint32_t hash = 2166136261UL;
    uint8_t index;
    for (index = 0U; index < PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX; index++)
    {
        const SystemMagCalibrationStatus *status =
            &s_mag_calibration[index].status;
        hash = (hash ^ index) * 16777619UL;
        hash = (hash ^ status->generation) * 16777619UL;
        hash = (hash ^ status->physical_device_id) * 16777619UL;
        hash = (hash ^ status->active) * 16777619UL;
        hash = (hash ^ status->saved) * 16777619UL;
    }
    PlatformCritical_Exit(state);
    return hash;
}

static SystemMagCalibrationResult SystemMagCalibration_PacketApplyOwned(
    uint8_t instance_id, const char *packet_hex)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    float values[16];
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    PlatformCriticalState state;
    result = SystemMagCalibration_ProviderGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    result = SystemMagCalibration_HexDecode(packet_hex, packet);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    result = SystemMagCalibration_PacketValidate(
        instance_id, descriptor.physical_device_id, packet, values);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    SILVERSTAR_ASSERT_OBJECT(&descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(packet, uint8_t, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    state = PlatformCritical_Enter();
    if (s_mag_calibration[instance_id].status.save_pending != 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Busy; }
    SystemMagCalibration_EntrySet(instance_id, packet, values, 0U);
    SystemMagCalibration_IdentitySet(&s_mag_calibration[instance_id], &descriptor);
    (void)memcpy(s_mag_calibration[instance_id].candidate, packet, sizeof(packet));
    s_mag_calibration[instance_id].candidate_valid = 1U;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_PacketApply(
    uint8_t instance_id,const char *packet_hex)
{
    SystemMagCalibrationResult result;
    if(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_MagWrite,0U)!=SYSTEM_DEVICE_OK)
    {return SystemMagCalibrationResult_Busy;}
    result=SystemMagCalibration_PacketApplyOwned(instance_id,packet_hex);
    SystemInstallationCapture_OperationEnd(SystemInstallationOperation_MagWrite);
    return result;
}

static SystemMagCalibrationResult SystemMagCalibration_SaveRequestOwned(
    uint8_t instance_id,uint8_t *pending)
{
    PlatformCriticalState state;
    SystemMagCalibrationEntry *entry;
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result =
        SystemMagCalibration_ProviderGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    state = PlatformCritical_Enter();
    entry = &s_mag_calibration[instance_id];
    SILVERSTAR_ASSERT(entry->status.active <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(entry->status.save_pending <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((entry->status.active == 0U) && (entry->candidate_valid == 0U))
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_NotReady; }
    if (SystemMagCalibration_IdentityMatches(entry, &descriptor) == 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_WrongDevice; }
    if (entry->status.save_pending != 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Busy; }
    /* An already verified value needs no additional generation or slot write. */
    if (entry->candidate_valid == 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Ok; }
    s_mag_calibration_next_request_id++;
    if (s_mag_calibration_next_request_id == 0U)
    { s_mag_calibration_next_request_id = 1U; }
    entry->request_id = s_mag_calibration_next_request_id;
    entry->status.save_pending = 1U;
    entry->status.save_failed = 0U;
    *pending=1U;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_SaveRequest(uint8_t instance_id)
{
    uint8_t pending=0U;
    SystemMagCalibrationResult result;
    if(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_MagWrite,0U)!=SYSTEM_DEVICE_OK)
    {return SystemMagCalibrationResult_Busy;}
    result=SystemMagCalibration_SaveRequestOwned(instance_id,&pending);
    if(pending==0U){SystemInstallationCapture_OperationEnd(SystemInstallationOperation_MagWrite);}
    return result;
}

static SystemMagCalibrationResult SystemMagCalibration_ClearRequestOwned(
    uint8_t instance_id,uint8_t *pending)
{
    PlatformCriticalState state;
    SystemMagCalibrationEntry *entry;
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result =
        SystemMagCalibration_ProviderGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    state = PlatformCritical_Enter();
    entry = &s_mag_calibration[instance_id];
    SILVERSTAR_ASSERT(entry->status.active <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(entry->status.save_pending <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (entry->status.save_pending != 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Busy; }
    if (((entry->status.active != 0U) || (entry->candidate_valid != 0U)) &&
        (SystemMagCalibration_IdentityMatches(entry, &descriptor) == 0U))
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_WrongDevice; }
    (void)memset(entry->candidate, 0, sizeof(entry->candidate));
    entry->candidate_valid = 1U;
    SystemMagCalibration_IdentitySet(entry, &descriptor);
    entry->status.active = 0U;
    entry->status.saved = 0U;
    entry->status.generation = 0U;
    entry->status.intrinsic_crc = 0U;
    entry->status.save_failed = 0U;
    entry->status.load_error = SystemMagCalibrationResult_Ok;
    s_mag_calibration_next_request_id++;
    if (s_mag_calibration_next_request_id == 0U)
    { s_mag_calibration_next_request_id = 1U; }
    entry->request_id = s_mag_calibration_next_request_id;
    entry->status.save_pending = 1U;
    *pending=1U;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_ClearRequest(uint8_t instance_id)
{
    uint8_t pending=0U;
    SystemMagCalibrationResult result;
    if(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_MagWrite,0U)!=SYSTEM_DEVICE_OK)
    {return SystemMagCalibrationResult_Busy;}
    result=SystemMagCalibration_ClearRequestOwned(instance_id,&pending);
    if(pending==0U){SystemInstallationCapture_OperationEnd(SystemInstallationOperation_MagWrite);}
    return result;
}

SystemMagCalibrationResult SystemMagCalibration_PendingGet(
    uint8_t *instance_id, uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    uint32_t *request_id)
{
    PlatformCriticalState state;
    uint8_t index;
    if ((instance_id == NULL) || (packet == NULL) || (request_id == NULL))
    { return SystemMagCalibrationResult_InvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(instance_id, uint8_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(packet, uint8_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    state = PlatformCritical_Enter();
    for (index = 0U; index < PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX; index++)
    {
        if (s_mag_calibration[index].status.save_pending == 0U) { continue; }
        SILVERSTAR_ASSERT(s_mag_calibration[index].candidate_valid == 1U &&
            s_mag_calibration[index].request_id != 0U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
            SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
        *instance_id = index;
        *request_id = s_mag_calibration[index].request_id;
        (void)memcpy(packet, s_mag_calibration[index].candidate,
            SYSTEM_MAG_CAL_PACKET_BYTES);
        PlatformCritical_Exit(state);
        return SystemMagCalibrationResult_Ok;
    }
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_NotReady;
}

static SystemMagCalibrationResult SystemMagCalibration_SelectionSet(uint8_t instance_id,
    const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES], uint32_t generation)
{
    float values[16];
    SystemMagCalibrationEntry *entry = &s_mag_calibration[instance_id];
    SystemMagCalibrationResult result = SystemMagCalibration_PacketDecode(
        instance_id, entry->status.physical_device_id, packet, values);
    /* Only previously validated candidates/committed bytes enter this helper. */
    SILVERSTAR_ASSERT(result == SystemMagCalibrationResult_Ok,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    if (packet[0] != 0U)
    {
        SystemMagCalibration_EntrySet(instance_id, packet, values, generation);
    }
    else
    {
        entry->status.active = 0U;
        entry->status.saved = 0U;
        entry->status.generation = generation;
        entry->status.intrinsic_crc = 0U;
        entry->status.load_error = SystemMagCalibrationResult_Ok;
    }
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_SaveComplete(
    uint8_t instance_id, uint32_t request_id, uint8_t success,
    uint32_t generation)
{
    PlatformCriticalState state;
    SystemMagCalibrationEntry *entry;
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result =
        SystemMagCalibration_DescriptorGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    SILVERSTAR_ASSERT(success <= 1U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((success == 0U) || (generation > 0U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    state = PlatformCritical_Enter();
    entry = &s_mag_calibration[instance_id];
    if ((entry->status.save_pending == 0U) ||
        (entry->request_id != request_id))
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Busy; }
    if (SystemMagCalibration_IdentityMatches(entry, &descriptor) == 0U)
    { success = 0U; }
    result = SystemMagCalibration_SelectionSet(instance_id,
        (success != 0U) ? entry->candidate : entry->committed,
        (success != 0U) ? generation : entry->committed_generation);
    if (result != SystemMagCalibrationResult_Ok)
    { PlatformCritical_Exit(state); return result; }
    if (success != 0U)
    {
        (void)memcpy(entry->committed, entry->candidate, sizeof(entry->committed));
        entry->committed_generation = generation;
        entry->candidate_valid = 0U;
    }
    entry->status.save_pending = 0U;
    entry->status.save_failed = (uint8_t)(success == 0U);
    /* Request identity was checked above. Publication/rollback is complete
     * before the storage owner's lifetime reservation can be released. */
    SystemInstallationCapture_OperationEnd(SystemInstallationOperation_MagWrite);
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

static SystemMagCalibrationResult SystemMagCalibration_StoredLoad(
    uint8_t instance_id, const uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES],
    uint32_t generation)
{
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    float values[16];
    PlatformCriticalState state;
    uint8_t calibration_present;
    if ((packet == NULL) || (generation == 0U))
    { return SystemMagCalibrationResult_InvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(packet, uint8_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    calibration_present = (uint8_t)(packet[0] != 0U);
    result = SystemMagCalibration_ProviderGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    SILVERSTAR_ASSERT_OBJECT(&descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = SystemMagCalibration_PacketDecode(
        instance_id, descriptor.physical_device_id, packet, values);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    state = PlatformCritical_Enter();
    if ((s_mag_calibration[instance_id].candidate_valid != 0U) ||
        (s_mag_calibration[instance_id].status.active != 0U) ||
        (s_mag_calibration[instance_id].status.save_pending != 0U))
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Busy; }
    if (calibration_present != 0U)
    { SystemMagCalibration_EntrySet(instance_id, packet, values, generation); }
    else
    {
        s_mag_calibration[instance_id].status.generation = generation;
        s_mag_calibration[instance_id].status.load_error =
            SystemMagCalibrationResult_Ok;
    }
    SystemMagCalibration_IdentitySet(&s_mag_calibration[instance_id], &descriptor);
    (void)memcpy(s_mag_calibration[instance_id].committed, packet, SYSTEM_MAG_CAL_PACKET_BYTES);
    s_mag_calibration[instance_id].committed_generation = generation;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_PendingRecordGet(
    uint8_t *instance_id, uint8_t record[SYSTEM_MAG_CAL_RECORD_BYTES],
    uint32_t *request_id)
{
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    float values[16];
    PlatformCriticalState state;
    if (record == NULL) { return SystemMagCalibrationResult_InvalidArgument; }
    result = SystemMagCalibration_PendingGet(instance_id,
        &record[SYSTEM_INSTALLATION_CAL_HEADER_BYTES], request_id);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    result = SystemMagCalibration_ProviderGet(*instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    state = PlatformCritical_Enter();
    if (SystemMagCalibration_IdentityMatches(
            &s_mag_calibration[*instance_id], &descriptor) == 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_WrongDevice; }
    PlatformCritical_Exit(state);
    result = SystemMagCalibration_PacketDecode(*instance_id,
        descriptor.physical_device_id, &record[SYSTEM_INSTALLATION_CAL_HEADER_BYTES], values);
    SILVERSTAR_ASSERT(result == SystemMagCalibrationResult_Ok,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    (void)memset(record, 0, SYSTEM_INSTALLATION_CAL_HEADER_BYTES);
    (void)memcpy(record, "SSIC", 4U);
    record[4] = SYSTEM_INSTALLATION_CAL_SCHEMA;
    record[5] = (uint8_t)SystemInstallationCalibrationKind_MagEllipsoid;
    record[6] = SYSTEM_INSTALLATION_CAL_MAG_ALGORITHM;
    record[7] = SYSTEM_INSTALLATION_CAL_BODY_UT_COORDINATES;
    record[8] = (uint8_t)descriptor.descriptor_id;
    record[9] = (uint8_t)(descriptor.descriptor_id >> 8U);
    record[10] = (uint8_t)descriptor.physical_device_id;
    record[11] = (uint8_t)(descriptor.physical_device_id >> 8U);
    record[12] = *instance_id;
    SystemMagCalibration_U32Write(&record[16], SystemDescriptor_ConfigDigestGet());
    SystemMagCalibration_U32Write(&record[20], descriptor.driver_name_hash);
    SystemMagCalibration_U32Write(&record[24], descriptor.model_name_hash);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_RecordLoadOwned(
    uint8_t instance_id, const uint8_t *record, uint16_t length,
    uint32_t generation)
{
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    if (record == NULL) { return SystemMagCalibrationResult_InvalidArgument; }
    result = SystemMagCalibration_ProviderGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    if ((length != SYSTEM_MAG_CAL_RECORD_BYTES) ||
        (memcmp(record, "SSIC", 4U) != 0) ||
        (record[4] != SYSTEM_INSTALLATION_CAL_SCHEMA) ||
        (record[5] != (uint8_t)SystemInstallationCalibrationKind_MagEllipsoid) ||
        (record[6] != SYSTEM_INSTALLATION_CAL_MAG_ALGORITHM) ||
        (record[7] != SYSTEM_INSTALLATION_CAL_BODY_UT_COORDINATES) ||
        (record[13] != 0U) || (record[14] != 0U) || (record[15] != 0U) ||
        (SystemMagCalibration_U32Read(&record[28]) != 0U))
    { return SystemMagCalibrationResult_InvalidObject; }
    if ((((uint16_t)record[8] | ((uint16_t)record[9] << 8U)) != descriptor.descriptor_id) ||
        (((uint16_t)record[10] | ((uint16_t)record[11] << 8U)) != descriptor.physical_device_id) ||
        (record[12] != instance_id) ||
        (SystemMagCalibration_U32Read(&record[16]) != SystemDescriptor_ConfigDigestGet()) ||
        (SystemMagCalibration_U32Read(&record[20]) != descriptor.driver_name_hash) ||
        (SystemMagCalibration_U32Read(&record[24]) != descriptor.model_name_hash))
    { return SystemMagCalibrationResult_WrongDevice; }
    return SystemMagCalibration_StoredLoad(instance_id,
        &record[SYSTEM_INSTALLATION_CAL_HEADER_BYTES], generation);
}

SystemMagCalibrationResult SystemMagCalibration_RecordLoad(
    uint8_t instance_id,const uint8_t *record,uint16_t length,uint32_t generation)
{
    SystemMagCalibrationResult result;
    if(SystemInstallationCapture_OperationBegin(SystemInstallationOperation_MagWrite,0U)!=SYSTEM_DEVICE_OK)
    {return SystemMagCalibrationResult_Busy;}
    result=SystemMagCalibration_RecordLoadOwned(instance_id,record,length,generation);
    SystemInstallationCapture_OperationEnd(SystemInstallationOperation_MagWrite);
    return result;
}

SystemMagCalibrationResult SystemMagCalibration_LoadFaultSet(
    uint8_t instance_id, SystemMagCalibrationResult reason)
{
    PlatformCriticalState state;
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    if ((reason <= SystemMagCalibrationResult_Ok) ||
        (reason > SystemMagCalibrationResult_StorageError))
    { return SystemMagCalibrationResult_InvalidArgument; }
    result = SystemMagCalibration_DescriptorGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    state = PlatformCritical_Enter();
    s_mag_calibration[instance_id].status.load_error = reason;
    SystemInstallationCapture_DependenciesChanged();
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_StatusGet(
    uint8_t instance_id, SystemMagCalibrationStatus *status)
{
    PlatformCriticalState state;
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    if (status == NULL)
    { return SystemMagCalibrationResult_InvalidArgument; }
    result = SystemMagCalibration_DescriptorGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    state = PlatformCritical_Enter();
    *status = s_mag_calibration[instance_id].status;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_SnapshotGet(
    uint8_t instance_id, SystemMagCalibrationSnapshot *snapshot)
{
    PlatformCriticalState lock;
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationEntry *entry;
    SystemMagCalibrationResult result;
    if (snapshot == NULL)
    { return SystemMagCalibrationResult_InvalidArgument; }
    result = SystemMagCalibration_DescriptorGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    lock = PlatformCritical_Enter();
    entry = &s_mag_calibration[instance_id];
    if (entry->status.active == 0U)
    { PlatformCritical_Exit(lock); return SystemMagCalibrationResult_NotReady; }
    snapshot->status = entry->status;
    (void)memcpy(snapshot->bias, entry->correction.bias, sizeof(snapshot->bias));
    (void)memcpy(snapshot->matrix, entry->correction.matrix,
                 sizeof(snapshot->matrix));
    PlatformCritical_Exit(lock);
    return SystemMagCalibrationResult_Ok;
}

static SystemMagCalibrationResult SystemMagCalibration_VectorCorrect(
    const SystemMagCalibrationCorrection *calibration, const float input[3],
    float output[3])
{
    uint8_t row;
    for (row = 0U; row < 3U; row++)
    {
        float corrected = 0.0f;
        uint8_t column;
        for (column = 0U; column < 3U; column++)
        {
            corrected += calibration->matrix[row][column] *
                (input[column] - calibration->bias[column]);
        }
        if (!isfinite(corrected))
        { return SystemMagCalibrationResult_InvalidObject; }
        output[row] = corrected;
    }
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_SampleApply(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationCorrection calibration;
    SystemMagCalibrationResult result;
    PlatformCriticalState state;
    float corrected[3];
    if (sample == NULL)
    { return SystemMagCalibrationResult_InvalidArgument; }
    result = SystemMagCalibration_ProviderGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemMagnetometerSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(&descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((sample->valid_mask & SYSTEM_MAG_VALID_PHYSICAL_UNIT) == 0U)
    { return SystemMagCalibrationResult_NotReady; }
    if ((sample->calibration_valid != 0U) ||
        ((sample->valid_mask & SYSTEM_MAG_VALID_CALIBRATED) != 0U))
    { return SystemMagCalibrationResult_NotReady; }
    if (((sample->physical_device_id != 0U) &&
         (sample->physical_device_id != descriptor.physical_device_id)) ||
        ((sample->descriptor_id != 0U) &&
         (sample->descriptor_id != descriptor.descriptor_id)) ||
        (sample->instance_id != instance_id))
    { return SystemMagCalibrationResult_WrongDevice; }
    state = PlatformCritical_Enter();
    if (s_mag_calibration[instance_id].status.active == 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_NotReady; }
    if (SystemMagCalibration_IdentityMatches(&s_mag_calibration[instance_id], &descriptor) == 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_WrongDevice; }
    calibration = s_mag_calibration[instance_id].correction;
    PlatformCritical_Exit(state);
    result = SystemMagCalibration_VectorCorrect(&calibration,
        sample->magnetic_field_b_uT, corrected);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    /* Publish only after the complete vector passed numerical checks. The
     * sample is caller-owned; failures leave all its bytes unchanged. */
    (void)memcpy(sample->magnetic_field_b_uT, corrected, sizeof(corrected));
    sample->calibration_valid = 1U;
    sample->valid_mask |= SYSTEM_MAG_VALID_CALIBRATED;
    sample->physical_device_id = descriptor.physical_device_id;
    sample->descriptor_id = descriptor.descriptor_id;
    sample->instance_id = instance_id;
    return SystemMagCalibrationResult_Ok;
}
