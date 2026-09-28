#include "device_native_log.h"

#include <string.h>

#include "logger_bus.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "system_lifecycle.h"
#include "system_user_config.h"

typedef struct
{
    uint32_t gnss_sequence[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint32_t barometer_sequence[PROJECT_BAROMETER_INSTANCE_COUNT_MAX];
    uint32_t magnetometer_sequence[PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX];
    uint32_t power_sequence[PROJECT_POWER_INSTANCE_COUNT_MAX];
    uint64_t power_log_timestamp_us[PROJECT_POWER_INSTANCE_COUNT_MAX];
    uint8_t gnss_sequence_valid[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint8_t barometer_sequence_valid[PROJECT_BAROMETER_INSTANCE_COUNT_MAX];
    uint8_t magnetometer_sequence_valid[
        PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX];
    uint8_t power_sequence_valid[PROJECT_POWER_INSTANCE_COUNT_MAX];
} DeviceNativeLogState;

static DeviceNativeLogState s_native_log;

static uint8_t DeviceNativeLog_Allowed(void)
{
    SystemLifecycleState state = SystemLifecycle_GetState();

    SILVERSTAR_ASSERT(state <= SYSTEM_STATE_FAULT,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (SYSTEM_LOG_PREFLIGHT_NATIVE_ENABLE != 0U) { return 1U; }
    return (uint8_t)((state == SYSTEM_STATE_FLIGHT) ||
                     (state == SYSTEM_STATE_RECOVERY));
}

static uint8_t DeviceNativeLog_SequenceAccept(
    uint32_t sequence, uint32_t *last_sequence, uint8_t *valid)
{
    if ((last_sequence == NULL) || (valid == NULL)) { return 0U; }
    if ((*valid != 0U) && (*last_sequence == sequence)) { return 0U; }
    *last_sequence = sequence;
    *valid = 1U;
    return 1U;
}

static void DeviceNativeLog_GnssRecordBuild(
    const SystemGnssSample *sample, const SystemDeviceDescriptor *descriptor,
    FlightLogGnssNativeRecord *record)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemGnssSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogGnssNativeRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->source_descriptor_id = descriptor->descriptor_id;
    record->instance_id = descriptor->instance_id;
    record->sample_timestamp_us = sample->sample_timestamp_us;
    record->receive_timestamp_us = sample->receive_timestamp_us;
    record->sequence = sample->sequence;
    record->latitude_e7 = sample->latitude_e7;
    record->longitude_e7 = sample->longitude_e7;
    record->ellipsoid_height_mm = sample->ellipsoid_height_mm;
    record->msl_height_mm = sample->msl_height_mm;
    (void)memcpy(record->velocity_enu_mps, sample->velocity_enu_mps,
        sizeof(record->velocity_enu_mps));
    (void)memcpy(record->velocity_variance_m2ps2,
        sample->velocity_variance_m2ps2,
        sizeof(record->velocity_variance_m2ps2));
    record->horizontal_accuracy_m = sample->horizontal_accuracy_m;
    record->vertical_accuracy_m = sample->vertical_accuracy_m;
    record->speed_accuracy_mps = sample->speed_accuracy_mps;
    record->velocity_valid_mask = sample->velocity_valid_mask;
    record->fix_type = sample->fix_type;
    record->position_usable = sample->position_usable;
    record->course_usable = sample->course_usable;
    record->online = sample->online;
    record->fix_ok = sample->fix_ok;
    record->satellite_count = sample->satellite_count;
    record->valid_group_mask = sample->valid_group_mask;
    record->measurement_timestamp_trusted = sample->measurement_timestamp_trusted;
    record->supported_fields = sample->supported_fields;
    record->valid_fields = sample->valid_fields;
    (void)memcpy(record->group_reject_mask, sample->group_reject_mask,
        sizeof(record->group_reject_mask));
}

static void DeviceNativeLog_GnssInstanceProcess(uint8_t instance_id)
{
    SystemDeviceDescriptor descriptor;
    SystemGnssSample sample;
    FlightLogGnssNativeRecord record;

    if ((ProjectGnssInstance_LatestSampleGet(instance_id, &sample) !=
         SYSTEM_DEVICE_OK) ||
        (ProjectDeviceInstance_DescriptorGet(SYSTEM_DEVICE_CLASS_GNSS,
         instance_id, &descriptor) != SYSTEM_DEVICE_OK) ||
        (DeviceNativeLog_SequenceAccept(sample.sequence,
         &s_native_log.gnss_sequence[instance_id],
         &s_native_log.gnss_sequence_valid[instance_id]) == 0U))
    { return; }
    DeviceNativeLog_GnssRecordBuild(&sample, &descriptor, &record);
    (void)LoggerBus_GnssNativePush(sample.sample_timestamp_us, 0U, &record);
}

static void DeviceNativeLog_GnssAllProcess(void)
{
    uint8_t count = ProjectGnssInstance_CountGet();
    uint8_t instance_id;

    SILVERSTAR_ASSERT(count <= PROJECT_GNSS_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U; instance_id < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        if (instance_id >= count) { break; }
        DeviceNativeLog_GnssInstanceProcess(instance_id);
    }
}

static void DeviceNativeLog_BarometerRecordBuild(
    const SystemBarometerSample *sample,
    const SystemDeviceDescriptor *descriptor,
    FlightLogBaroNativeRecord *record)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemBarometerSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogBaroNativeRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->source_descriptor_id = descriptor->descriptor_id;
    record->instance_id = descriptor->instance_id;
    record->sample_timestamp_us = sample->sample_timestamp_us;
    record->receive_timestamp_us = sample->receive_timestamp_us;
    record->sequence = sample->sequence;
    record->pressure_pa = sample->pressure_pa;
    record->altitude_m = sample->altitude_m;
    record->altitude_variance_m2 = sample->altitude_variance_m2;
    record->valid_mask = sample->valid_mask;
    record->supported_fields = sample->supported_fields;
    record->valid_fields = sample->valid_fields;
    record->measurement_timestamp_trusted = sample->measurement_timestamp_trusted;
}

static void DeviceNativeLog_BarometerInstanceProcess(uint8_t instance_id)
{
    SystemDeviceDescriptor descriptor;
    SystemDeviceHealth health;
    SystemBarometerSample sample;
    FlightLogBaroNativeRecord record;

    if ((ProjectBarometerInstance_LatestSampleGet(instance_id, &sample) !=
         SYSTEM_DEVICE_OK) ||
        (ProjectDeviceInstance_DescriptorGet(SYSTEM_DEVICE_CLASS_BAROMETER,
         instance_id, &descriptor) != SYSTEM_DEVICE_OK) ||
        (DeviceNativeLog_SequenceAccept(sample.sequence,
         &s_native_log.barometer_sequence[instance_id],
         &s_native_log.barometer_sequence_valid[instance_id]) == 0U))
    { return; }
    DeviceNativeLog_BarometerRecordBuild(&sample, &descriptor, &record);
    record.healthy = (uint8_t)((ProjectBarometerInstance_HealthGet(instance_id,
        &health) == SYSTEM_DEVICE_OK) && (health.healthy != 0U));
    (void)LoggerBus_BaroNativePush(sample.sample_timestamp_us,
        sample.valid_mask, &record);
}

static void DeviceNativeLog_BarometerAllProcess(void)
{
    uint8_t count = ProjectBarometerInstance_CountGet();
    uint8_t instance_id;

    SILVERSTAR_ASSERT(count <= PROJECT_BAROMETER_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U;
         instance_id < PROJECT_BAROMETER_INSTANCE_COUNT_MAX; instance_id++)
    {
        if (instance_id >= count) { break; }
        DeviceNativeLog_BarometerInstanceProcess(instance_id);
    }
}

static void DeviceNativeLog_MagnetometerRecordBuild(
    const SystemMagnetometerSample *sample,
    const SystemDeviceDescriptor *descriptor,
    FlightLogMagNativeRecord *record)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemMagnetometerSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogMagNativeRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->source_descriptor_id = descriptor->descriptor_id;
    record->instance_id = descriptor->instance_id;
    record->sample_timestamp_us = sample->sample_timestamp_us;
    record->receive_timestamp_us = sample->receive_timestamp_us;
    record->sequence = sample->sequence;
    (void)memcpy(record->raw, sample->raw, sizeof(record->raw));
    (void)memcpy(record->magnetic_field_b_uT, sample->magnetic_field_b_uT,
        sizeof(record->magnetic_field_b_uT));
    record->temperature_c = sample->temperature_c;
    record->valid_mask = sample->valid_mask;
    record->calibration_valid = sample->calibration_valid;
}

static void DeviceNativeLog_MagnetometerInstanceProcess(uint8_t instance_id)
{
    SystemDeviceDescriptor descriptor;
    SystemMagnetometerSample sample;
    FlightLogMagNativeRecord record;

    if ((ProjectMagnetometerInstance_LatestSampleGet(instance_id, &sample) !=
         SYSTEM_DEVICE_OK) ||
        (ProjectDeviceInstance_DescriptorGet(SYSTEM_DEVICE_CLASS_MAGNETOMETER,
         instance_id, &descriptor) != SYSTEM_DEVICE_OK) ||
        (DeviceNativeLog_SequenceAccept(sample.sequence,
         &s_native_log.magnetometer_sequence[instance_id],
         &s_native_log.magnetometer_sequence_valid[instance_id]) == 0U))
    { return; }
    DeviceNativeLog_MagnetometerRecordBuild(&sample, &descriptor, &record);
    (void)LoggerBus_MagNativePush(sample.sample_timestamp_us,
        sample.valid_mask, &record);
}

static void DeviceNativeLog_MagnetometerAllProcess(void)
{
    uint8_t count = ProjectMagnetometerInstance_CountGet();
    uint8_t instance_id;

    SILVERSTAR_ASSERT(count <= PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U;
         instance_id < PROJECT_MAGNETOMETER_INSTANCE_COUNT_MAX; instance_id++)
    {
        if (instance_id >= count) { break; }
        DeviceNativeLog_MagnetometerInstanceProcess(instance_id);
    }
}

static void DeviceNativeLog_PowerRecordBuild(
    const SystemPowerSample *sample, const SystemDeviceDescriptor *descriptor,
    FlightLogPowerRecord *record)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemPowerSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(record, FlightLogPowerRecord,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(record, 0, sizeof(*record));
    record->source_descriptor_id = descriptor->descriptor_id;
    record->instance_id = descriptor->instance_id;
    record->sample_timestamp_us = sample->sample_timestamp_us;
    record->receive_timestamp_us = sample->receive_timestamp_us;
    record->sequence = sample->sequence;
    record->voltage_v = sample->voltage_v;
    record->current_a = sample->current_a;
    record->power_w = sample->power_w;
    record->state_of_charge_percent = sample->state_of_charge_percent;
    record->temperature_c = sample->temperature_c;
    record->valid_mask = sample->valid_mask;
}

static void DeviceNativeLog_PowerInstanceProcess(
    uint8_t instance_id, uint64_t now_us,
    const SystemLogStreamConfig *config)
{
    SystemDeviceDescriptor descriptor;
    SystemPowerSample sample;
    FlightLogPowerRecord record;

    SILVERSTAR_ASSERT_OBJECT(config, SystemLogStreamConfig,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(instance_id < PROJECT_POWER_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (((now_us - s_native_log.power_log_timestamp_us[instance_id]) <
         config->period_us) ||
        (ProjectPowerInstance_LatestSampleGet(instance_id, &sample) !=
         SYSTEM_DEVICE_OK) ||
        (ProjectDeviceInstance_DescriptorGet(SYSTEM_DEVICE_CLASS_POWER,
         instance_id, &descriptor) != SYSTEM_DEVICE_OK) ||
        (DeviceNativeLog_SequenceAccept(sample.sequence,
         &s_native_log.power_sequence[instance_id],
         &s_native_log.power_sequence_valid[instance_id]) == 0U))
    { return; }
    DeviceNativeLog_PowerRecordBuild(&sample, &descriptor, &record);
    s_native_log.power_log_timestamp_us[instance_id] = now_us;
    (void)LoggerBus_PowerPush(sample.sample_timestamp_us, &record);
}

void DeviceNativeLog_Process(void)
{
    if (DeviceNativeLog_Allowed() == 0U) { return; }
    DeviceNativeLog_GnssAllProcess();
    DeviceNativeLog_BarometerAllProcess();
    DeviceNativeLog_MagnetometerAllProcess();
}

void DeviceNativeLog_PowerProcess(
    uint64_t now_us, const SystemLogStreamConfig *config)
{
    uint8_t count;
    uint8_t instance_id;

    if ((config == NULL) || (config->enabled == 0U)) { return; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemLogStreamConfig,
        SILVERSTAR_ASSERT_MODULE_APP);
    count = ProjectPowerInstance_CountGet();
    SILVERSTAR_ASSERT(count <= PROJECT_POWER_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U; instance_id < PROJECT_POWER_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        if (instance_id >= count) { break; }
        DeviceNativeLog_PowerInstanceProcess(instance_id, now_us, config);
    }
}
