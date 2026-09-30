#include "system_mag_calibration.h"

#include <math.h>
#include <string.h>

#include "platform_critical.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"

#define SYSTEM_MAG_CAL_BODY_BYTES 80U
#define SYSTEM_MAG_CAL_FLOAT_COUNT 16U
#define SYSTEM_MAG_CAL_CRC_POLYNOMIAL 0xEDB88320UL

typedef struct
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    float bias[3];
    float matrix[3][3];
    uint32_t request_id;
    SystemMagCalibrationStatus status;
} SystemMagCalibrationEntry;

static SystemMagCalibrationEntry
    s_mag_calibration[PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX];
static uint32_t s_mag_calibration_next_request_id;

static uint32_t SystemMagCalibration_U32Read(const uint8_t *data)
{
    return (uint32_t)data[0] | ((uint32_t)data[1] << 8U) |
        ((uint32_t)data[2] << 16U) | ((uint32_t)data[3] << 24U);
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
    (void)memcpy(entry->packet, packet, SYSTEM_MAG_CAL_PACKET_BYTES);
    for (row = 0U; row < 3U; row++)
    {
        entry->bias[row] = values[row];
        for (column = 0U; column < 3U; column++)
        { entry->matrix[row][column] = values[3U + row * 3U + column]; }
    }
    entry->status.generation = generation;
    entry->status.physical_device_id =
        (uint16_t)packet[2] | ((uint16_t)packet[3] << 8U);
    entry->status.instance_id = instance_id;
    entry->status.active = 1U;
    entry->status.saved = (uint8_t)(generation != 0U);
    entry->status.save_failed = 0U;
    entry->status.load_error = SystemMagCalibrationResult_Ok;
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

SystemMagCalibrationResult SystemMagCalibration_PacketApply(
    uint8_t instance_id, const char *packet_hex)
{
    uint8_t packet[SYSTEM_MAG_CAL_PACKET_BYTES];
    float values[16];
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationResult result;
    PlatformCriticalState state;
    result = SystemMagCalibration_DescriptorGet(instance_id, &descriptor);
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
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_SaveRequest(uint8_t instance_id)
{
    PlatformCriticalState state;
    SystemMagCalibrationEntry *entry;
    if (instance_id >= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX)
    { return SystemMagCalibrationResult_InvalidArgument; }
    state = PlatformCritical_Enter();
    entry = &s_mag_calibration[instance_id];
    SILVERSTAR_ASSERT(entry->status.active <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(entry->status.save_pending <= 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (entry->status.active == 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_NotReady; }
    if (entry->status.save_pending != 0U)
    { PlatformCritical_Exit(state); return SystemMagCalibrationResult_Busy; }
    s_mag_calibration_next_request_id++;
    if (s_mag_calibration_next_request_id == 0U)
    { s_mag_calibration_next_request_id = 1U; }
    entry->request_id = s_mag_calibration_next_request_id;
    entry->status.save_pending = 1U;
    entry->status.saved = 0U;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_ClearRequest(uint8_t instance_id)
{
    PlatformCriticalState state;
    SystemMagCalibrationEntry *entry;
    if (instance_id >= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX)
    { return SystemMagCalibrationResult_InvalidArgument; }
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
    (void)memset(entry->packet, 0, sizeof(entry->packet));
    entry->status.active = 0U;
    entry->status.saved = 0U;
    entry->status.generation = 0U;
    entry->status.load_error = SystemMagCalibrationResult_Ok;
    s_mag_calibration_next_request_id++;
    if (s_mag_calibration_next_request_id == 0U)
    { s_mag_calibration_next_request_id = 1U; }
    entry->request_id = s_mag_calibration_next_request_id;
    entry->status.save_pending = 1U;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
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
        *instance_id = index;
        *request_id = s_mag_calibration[index].request_id;
        (void)memcpy(packet, s_mag_calibration[index].packet,
            SYSTEM_MAG_CAL_PACKET_BYTES);
        PlatformCritical_Exit(state);
        return SystemMagCalibrationResult_Ok;
    }
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_NotReady;
}

SystemMagCalibrationResult SystemMagCalibration_SaveComplete(
    uint8_t instance_id, uint32_t request_id, uint8_t success,
    uint32_t generation)
{
    PlatformCriticalState state;
    SystemMagCalibrationEntry *entry;
    if (instance_id >= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX)
    { return SystemMagCalibrationResult_InvalidArgument; }
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
    entry->status.save_pending = 0U;
    entry->status.save_failed = (uint8_t)(success == 0U);
    if (success != 0U)
    {
        entry->status.generation = generation;
        entry->status.saved = entry->status.active;
    }
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_StoredLoad(
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
    result = SystemMagCalibration_DescriptorGet(instance_id, &descriptor);
    if (result != SystemMagCalibrationResult_Ok) { return result; }
    SILVERSTAR_ASSERT_OBJECT(&descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (calibration_present != 0U)
    {
        result = SystemMagCalibration_PacketValidate(
            instance_id, descriptor.physical_device_id, packet, values);
        if (result != SystemMagCalibrationResult_Ok) { return result; }
    }
    else
    {
        uint16_t index;
        for (index = 1U; index < SYSTEM_MAG_CAL_PACKET_BYTES; index++)
        {
            if (packet[index] != 0U)
            { return SystemMagCalibrationResult_InvalidObject; }
        }
    }
    state = PlatformCritical_Enter();
    if ((s_mag_calibration[instance_id].status.active != 0U) ||
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
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_LoadFaultSet(
    uint8_t instance_id, SystemMagCalibrationResult reason)
{
    PlatformCriticalState state;
    if ((instance_id >= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX) ||
        (reason == SystemMagCalibrationResult_Ok))
    { return SystemMagCalibrationResult_InvalidArgument; }
    state = PlatformCritical_Enter();
    s_mag_calibration[instance_id].status.load_error = reason;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_StatusGet(
    uint8_t instance_id, SystemMagCalibrationStatus *status)
{
    PlatformCriticalState state;
    if ((instance_id >= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX) ||
        (status == NULL))
    { return SystemMagCalibrationResult_InvalidArgument; }
    state = PlatformCritical_Enter();
    *status = s_mag_calibration[instance_id].status;
    PlatformCritical_Exit(state);
    return SystemMagCalibrationResult_Ok;
}

SystemMagCalibrationResult SystemMagCalibration_SampleApply(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    SystemDeviceDescriptor descriptor;
    SystemMagCalibrationEntry calibration;
    PlatformCriticalState state;
    float uncalibrated[3];
    uint8_t row;
    if ((sample == NULL) ||
        (SystemMagCalibration_DescriptorGet(instance_id, &descriptor) !=
         SystemMagCalibrationResult_Ok))
    { return SystemMagCalibrationResult_InvalidArgument; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemMagnetometerSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(&descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((sample->valid_mask & SYSTEM_MAG_VALID_PHYSICAL_UNIT) == 0U)
    { return SystemMagCalibrationResult_NotReady; }
    state = PlatformCritical_Enter();
    calibration = s_mag_calibration[instance_id];
    PlatformCritical_Exit(state);
    if (calibration.status.active == 0U)
    { return SystemMagCalibrationResult_NotReady; }
    if (calibration.status.physical_device_id != descriptor.physical_device_id)
    { return SystemMagCalibrationResult_WrongDevice; }
    (void)memcpy(uncalibrated, sample->magnetic_field_b_uT,
        sizeof(uncalibrated));
    for (row = 0U; row < 3U; row++)
    {
        float corrected = 0.0f;
        uint8_t column;
        for (column = 0U; column < 3U; column++)
        {
            corrected += calibration.matrix[row][column] *
                (uncalibrated[column] - calibration.bias[column]);
        }
        if (!isfinite(corrected))
        { return SystemMagCalibrationResult_InvalidObject; }
        sample->magnetic_field_b_uT[row] = corrected;
    }
    sample->calibration_valid = 1U;
    sample->valid_mask |= SYSTEM_MAG_VALID_CALIBRATED;
    sample->physical_device_id = descriptor.physical_device_id;
    sample->instance_id = instance_id;
    return SystemMagCalibrationResult_Ok;
}
