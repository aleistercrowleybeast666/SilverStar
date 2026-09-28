#include "system_alignment.h"

#include <stddef.h>
#include "common_format.h"
#include "silverstar_assert.h"

static const SystemAlignmentSourceDescriptor s_source_descriptors[] =
{
    { SYSTEM_ALIGNMENT_SOURCE_ATTITUDE, "attitude",
      SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE },
    { SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN, "gnss",
      SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN },
    { SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN, "baro",
      SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN },
    { SYSTEM_ALIGNMENT_SOURCE_MAGNETIC, "mag",
      SYSTEM_ALIGNMENT_SOURCE_MASK_MAGNETIC },
    { SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING, "dual_gnss_heading",
      SYSTEM_ALIGNMENT_SOURCE_MASK_DUAL_GNSS_HEADING },
    { SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE, "external_attitude",
      SYSTEM_ALIGNMENT_SOURCE_MASK_EXTERNAL_ATTITUDE }
};

_Static_assert((sizeof(s_source_descriptors) /
                sizeof(s_source_descriptors[0])) ==
               SYSTEM_ALIGNMENT_SOURCE_COUNT,
               "Alignment descriptor count mismatch");

static unsigned long SystemAlignment_TimestampDisplay(uint64_t timestamp_us)
{
    return (unsigned long)((timestamp_us > UINT32_MAX) ?
        UINT32_MAX : (uint32_t)timestamp_us);
}

const SystemAlignmentSourceDescriptor *SystemAlignment_SourceDescriptorGet(
    SystemAlignmentSourceId source_id)
{
    if ((uint32_t)source_id >= SYSTEM_ALIGNMENT_SOURCE_COUNT)
    {
        return NULL;
    }
    return &s_source_descriptors[(uint32_t)source_id];
}

const SystemAlignmentSourceStatus *SystemAlignment_SourceStatusGet(
    const SystemAlignmentStatus *status,
    SystemAlignmentSourceId source_id)
{
    if ((status == NULL) ||
        ((uint32_t)source_id >= SYSTEM_ALIGNMENT_SOURCE_COUNT))
    {
        return NULL;
    }
    return &status->component[(uint32_t)source_id];
}

static void SystemAlignment_AttitudeDetailFormat(
    const SystemAlignmentSourceDescriptor *descriptor,
    const SystemAlignmentSourceStatus *source,
    char *text,
    uint16_t capacity)
{
    const SystemAlignmentAttitudeStatus *detail = &source->detail.attitude;

    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemAlignmentSourceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(text, capacity,
        "ALIGN SOURCE name=%s state=%s supported=%u required=%u ready=%u source=%s quaternion_valid=%u timestamp_us=%lu device=%s algorithm=%u samples=%lu rejects=%lu window_start_us=%lu window_end_us=%lu final_yaw_deg=%.3f known_yaw_deg=%.3f declination_deg=%.3f final_q_frozen=%u",
        descriptor->key, SystemAlignment_ComponentStateText(source->state),
        (unsigned int)source->supported,
        (unsigned int)source->required,
        (unsigned int)source->ready,
        SystemAlignment_AttitudeSourceText(detail->source),
        (unsigned int)detail->quaternion_valid,
        SystemAlignment_TimestampDisplay(detail->timestamp_us),
        (detail->device_name != NULL) ? detail->device_name : "NONE",
        (unsigned int)detail->algorithm,
        (unsigned long)detail->sample_count,
        (unsigned long)detail->reject_count,
        SystemAlignment_TimestampDisplay(detail->window_start_timestamp_us),
        SystemAlignment_TimestampDisplay(detail->window_end_timestamp_us),
        (double)detail->final_yaw_deg,
        (double)detail->known_yaw_deg,
        (double)detail->magnetic_declination_deg,
        (unsigned int)detail->final_quaternion_frozen);
}

static void SystemAlignment_GnssDetailFormat(
    const SystemAlignmentSourceDescriptor *descriptor,
    const SystemAlignmentSourceStatus *source,
    char *text,
    uint16_t capacity)
{
    const SystemAlignmentGnssStatus *detail = &source->detail.gnss;

    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemAlignmentSourceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(text, capacity,
        "ALIGN SOURCE name=%s state=%s supported=%u required=%u ready=%u origin_valid=%u lat=%ld lon=%ld height=%ld samples=%lu accuracy_h_m=%.3f accuracy_v_m=%.3f device=%s",
        descriptor->key, SystemAlignment_ComponentStateText(source->state),
        (unsigned int)source->supported,
        (unsigned int)source->required,
        (unsigned int)source->ready,
        (unsigned int)detail->origin_valid,
        (long)detail->origin_lat_e7,
        (long)detail->origin_lon_e7,
        (long)detail->origin_height_mm,
        (unsigned long)detail->sample_count,
        (double)detail->horizontal_accuracy_m,
        (double)detail->vertical_accuracy_m,
        (detail->device_name != NULL) ? detail->device_name : "NONE");
}

static void SystemAlignment_BarometerDetailFormat(
    const SystemAlignmentSourceDescriptor *descriptor,
    const SystemAlignmentSourceStatus *source,
    char *text,
    uint16_t capacity)
{
    const SystemAlignmentBarometerStatus *detail = &source->detail.barometer;

    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemAlignmentSourceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(text, capacity,
        "ALIGN SOURCE name=%s state=%s supported=%u required=%u ready=%u origin_valid=%u samples=%lu pressure_pa=%.3f altitude_m=%.3f device=%s",
        descriptor->key, SystemAlignment_ComponentStateText(source->state),
        (unsigned int)source->supported,
        (unsigned int)source->required,
        (unsigned int)source->ready,
        (unsigned int)detail->origin_valid,
        (unsigned long)detail->sample_count,
        (double)detail->origin_pressure_pa,
        (double)detail->origin_altitude_m,
        (detail->device_name != NULL) ? detail->device_name : "NONE");
}

static void SystemAlignment_GenericDetailFormat(
    const SystemAlignmentSourceDescriptor *descriptor,
    const SystemAlignmentSourceStatus *source,
    char *text,
    uint16_t capacity)
{
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemAlignmentSourceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)CommonFormat_Print(text, capacity,
        "ALIGN SOURCE name=%s state=%s supported=%u required=%u ready=%u",
        descriptor->key, SystemAlignment_ComponentStateText(source->state),
        (unsigned int)source->supported,
        (unsigned int)source->required,
        (unsigned int)source->ready);
}

SystemDeviceResult SystemAlignment_SourceDetailFormat(
    const SystemAlignmentStatus *status,
    SystemAlignmentSourceId source_id,
    char *text,
    uint16_t capacity)
{
    const SystemAlignmentSourceDescriptor *descriptor;
    const SystemAlignmentSourceStatus *source;

    if ((status == NULL) || (text == NULL) || (capacity == 0U))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    descriptor = SystemAlignment_SourceDescriptorGet(source_id);
    source = SystemAlignment_SourceStatusGet(status, source_id);
    if ((descriptor == NULL) || (source == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }

    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (source_id)
    {
        case SYSTEM_ALIGNMENT_SOURCE_ATTITUDE:
            SystemAlignment_AttitudeDetailFormat(descriptor, source, text,
                capacity);
            break;
        case SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN:
            SystemAlignment_GnssDetailFormat(descriptor, source, text,
                capacity);
            break;
        case SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN:
            SystemAlignment_BarometerDetailFormat(descriptor, source, text,
                capacity);
            break;
        case SYSTEM_ALIGNMENT_SOURCE_MAGNETIC:
        case SYSTEM_ALIGNMENT_SOURCE_DUAL_GNSS_HEADING:
        case SYSTEM_ALIGNMENT_SOURCE_EXTERNAL_ATTITUDE:
        default:
            SystemAlignment_GenericDetailFormat(descriptor, source, text,
                capacity);
            break;
    }
    return SYSTEM_DEVICE_OK;
}

const char *SystemAlignment_StateText(SystemAlignmentState state)
{
    switch (state)
    {
        case SYSTEM_ALIGNMENT_STATE_IDLE: return "IDLE";
        case SYSTEM_ALIGNMENT_STATE_COLLECTING: return "COLLECTING";
        case SYSTEM_ALIGNMENT_STATE_CHECKING: return "CHECKING";
        case SYSTEM_ALIGNMENT_STATE_READY: return "READY";
        case SYSTEM_ALIGNMENT_STATE_FAILED: return "FAILED";
        case SYSTEM_ALIGNMENT_STATE_STALE: return "STALE";
        default: return "FAILED";
    }
}

const char *SystemAlignment_StaleReasonText(
    SystemAlignmentStaleReason reason)
{
    return (reason == SYSTEM_ALIGNMENT_STALE_REASON_MOTION) ?
        "MOTION" : "NONE";
}

const char *SystemAlignment_ComponentStateText(
    SystemAlignmentComponentState state)
{
    switch (state)
    {
        case SYSTEM_ALIGNMENT_COMPONENT_NOT_READY: return "NOT_READY";
        case SYSTEM_ALIGNMENT_COMPONENT_COLLECTING: return "COLLECTING";
        case SYSTEM_ALIGNMENT_COMPONENT_READY: return "READY";
        case SYSTEM_ALIGNMENT_COMPONENT_FAILED: return "FAILED";
        case SYSTEM_ALIGNMENT_COMPONENT_DISABLED:
        default: return "DISABLED";
    }
}

const char *SystemAlignment_ConfigResultText(
    SystemAlignmentConfigResult result)
{
    switch (result)
    {
        case SYSTEM_ALIGNMENT_CONFIG_OK: return "OK";
        case SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED:
            return "REQUIRED_NOT_SELECTED";
        case SYSTEM_ALIGNMENT_CONFIG_REQUIRED_UNAVAILABLE:
            return "REQUIRED_UNAVAILABLE";
        case SYSTEM_ALIGNMENT_CONFIG_ADAPTER_UNAVAILABLE:
        default: return "ADAPTER_UNAVAILABLE";
    }
}

const char *SystemAlignment_AttitudeSourceText(
    SystemAlignmentAttitudeSource source)
{
    switch (source)
    {
        case SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION:
            return "HARDWARE_QUATERNION";
        case SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_KNOWN_YAW:
            return "GRAVITY_KNOWN_YAW";
        case SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_MAG_TRIAD:
            return "GRAVITY_MAG_TRIAD";
        case SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_NONE:
        default:
            return "NONE";
    }
}
