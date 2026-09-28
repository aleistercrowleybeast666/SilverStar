#include "system_sensor_status.h"

#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "system_alignment.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#include "system_navigation_profile.h"
#include "system_user_alignment_config.h"

typedef enum
{
    SYSTEM_SENSOR_SOURCE_IMU = 0,
    SYSTEM_SENSOR_SOURCE_GNSS,
    SYSTEM_SENSOR_SOURCE_BAROMETER,
    SYSTEM_SENSOR_SOURCE_MAGNETOMETER,
    SYSTEM_SENSOR_SOURCE_HARDWARE_ATTITUDE
} SystemSensorSource;

typedef struct
{
    uint8_t sensor_id;
    uint8_t instance_id;
    SystemDeviceClass device_class;
    SystemSensorSource source;
} SystemSensorDescriptor;

static SystemSensorDescriptor
    s_descriptors[SYSTEM_SENSOR_STATUS_MAX_ENTRIES];
static SystemSensorStatus
    s_snapshot[SYSTEM_SENSOR_STATUS_MAX_ENTRIES];
static SystemSensorStatus
    s_capture_working[SYSTEM_SENSOR_STATUS_MAX_ENTRIES];
static SystemSensorStatusSnapshotInfo s_snapshot_info;
static uint8_t s_descriptor_count;
static uint8_t s_capture_active;

static uint32_t SystemSensorStatus_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemSensorStatus_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static uint8_t SystemSensorStatus_OrderRank(uint8_t sensor_id)
{
    if (sensor_id == SILVERSTAR_SENSOR_ID_IMU) { return 0U; }
    if (sensor_id == SILVERSTAR_SENSOR_ID_GNSS) { return 1U; }
    return 2U;
}

static uint8_t SystemSensorStatus_DescriptorLess(
    const SystemSensorDescriptor *lhs,
    const SystemSensorDescriptor *rhs)
{
    uint8_t lhs_rank = SystemSensorStatus_OrderRank(lhs->sensor_id);
    uint8_t rhs_rank = SystemSensorStatus_OrderRank(rhs->sensor_id);

    if (lhs_rank != rhs_rank) { return (uint8_t)(lhs_rank < rhs_rank); }
    if (lhs->sensor_id != rhs->sensor_id)
    {
        return (uint8_t)(lhs->sensor_id < rhs->sensor_id);
    }
    return (uint8_t)(lhs->instance_id < rhs->instance_id);
}

static uint8_t SystemSensorStatus_DeviceClassResolve(
    SystemDeviceClass device_class, uint8_t *sensor_id,
    SystemSensorSource *source)
{
    if ((sensor_id == NULL) || (source == NULL)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(sensor_id, uint8_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU:
            *sensor_id = SILVERSTAR_SENSOR_ID_IMU;
            *source = SYSTEM_SENSOR_SOURCE_IMU;
            return 1U;
        case SYSTEM_DEVICE_CLASS_GNSS:
            *sensor_id = SILVERSTAR_SENSOR_ID_GNSS;
            *source = SYSTEM_SENSOR_SOURCE_GNSS;
            return 1U;
        case SYSTEM_DEVICE_CLASS_BAROMETER:
            *sensor_id = SILVERSTAR_SENSOR_ID_BAROMETER;
            *source = SYSTEM_SENSOR_SOURCE_BAROMETER;
            return 1U;
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
            *sensor_id = SILVERSTAR_SENSOR_ID_MAGNETOMETER;
            *source = SYSTEM_SENSOR_SOURCE_MAGNETOMETER;
            return 1U;
        case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
            *sensor_id = SILVERSTAR_SENSOR_ID_EXTERNAL_ATTITUDE;
            *source = SYSTEM_SENSOR_SOURCE_HARDWARE_ATTITUDE;
            return 1U;
        case SYSTEM_DEVICE_CLASS_TELEMETRY:
        case SYSTEM_DEVICE_CLASS_CONSOLE:
        case SYSTEM_DEVICE_CLASS_POWER:
        case SYSTEM_DEVICE_CLASS_STORAGE:
        case SYSTEM_DEVICE_CLASS_LOG_SINK:
        case SYSTEM_DEVICE_CLASS_OUTPUT:
        case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
        case SYSTEM_DEVICE_CLASS_TIME:
        default: return 0U;
    }
}

static void SystemSensorStatus_DescriptorAppend(
    const SystemDeviceDescriptor *project_descriptor)
{
    SystemSensorDescriptor *descriptor;
    uint8_t sensor_id;
    SystemSensorSource source;

    if ((project_descriptor == NULL) ||
        (s_descriptor_count >= SYSTEM_SENSOR_STATUS_MAX_ENTRIES) ||
        (SystemSensorStatus_DeviceClassResolve(
            project_descriptor->device_class, &sensor_id, &source) == 0U))
    {
        return;
    }
    descriptor = &s_descriptors[s_descriptor_count++];
    descriptor->sensor_id = sensor_id;
    descriptor->instance_id = project_descriptor->instance_id;
    descriptor->device_class = project_descriptor->device_class;
    descriptor->source = source;
}

static void SystemSensorStatus_DescriptorsRefresh(void)
{
    SystemDeviceDescriptor project_descriptor;
    SystemSensorDescriptor value;
    uint16_t project_count;
    uint16_t project_index;
    uint8_t index;
    uint8_t insert;
    uint8_t shift;
    uint32_t primask = SystemSensorStatus_IrqLock();

    SILVERSTAR_ASSERT_OBJECT(s_descriptors, SystemSensorDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    s_descriptor_count = 0U;
    project_count = SystemDescriptor_DeviceCountGet();
    for (project_index = 0U;
         project_index < SYSTEM_DESCRIPTOR_DEVICE_COUNT_MAX;
         project_index++)
    {
        if (project_index >= project_count) { break; }
        if (SystemDescriptor_DeviceGet(project_index, &project_descriptor) ==
            SYSTEM_DEVICE_OK)
        {
            SystemSensorStatus_DescriptorAppend(&project_descriptor);
        }
    }
    for (index = 1U; index < s_descriptor_count; index++)
    {
        value = s_descriptors[index];
        insert = index;
        for (shift = 0U;
             shift < SYSTEM_SENSOR_STATUS_MAX_ENTRIES;
             shift++)
        {
            if ((insert == 0U) ||
                (SystemSensorStatus_DescriptorLess(
                    &value, &s_descriptors[insert - 1U]) == 0U))
            {
                break;
            }
            s_descriptors[insert] = s_descriptors[insert - 1U];
            insert--;
        }
        s_descriptors[insert] = value;
    }
    SystemSensorStatus_IrqUnlock(primask);
}

static void SystemSensorStatus_AlignmentUsageResolve(
    uint8_t sensor_id,
    const SystemNavigationProfile *navigation,
    SystemAlignmentSourceMask selected_mask,
    SystemAlignmentSourceMask required_mask,
    uint8_t *used,
    uint8_t *required)
{
    SILVERSTAR_ASSERT(used != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(required != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    *used = 0U;
    *required = 0U;
    switch (sensor_id)
    {
        case SILVERSTAR_SENSOR_ID_IMU:
            *used = (uint8_t)((selected_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE) != 0U);
            *required = (uint8_t)((required_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE) != 0U);
            break;
        case SILVERSTAR_SENSOR_ID_GNSS:
            *used = (uint8_t)((selected_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U);
            *required = (uint8_t)((required_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U);
            break;
        case SILVERSTAR_SENSOR_ID_BAROMETER:
            *used = (uint8_t)((selected_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN) != 0U);
            *required = (uint8_t)((required_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN) != 0U);
            break;
        case SILVERSTAR_SENSOR_ID_MAGNETOMETER:
            *used = (uint8_t)((navigation != NULL) &&
                (navigation->alignment_algorithm ==
                 SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD));
            *required = (uint8_t)((*used != 0U) && ((required_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE) != 0U));
            break;
        case SILVERSTAR_SENSOR_ID_EXTERNAL_ATTITUDE:
            *used = (uint8_t)((navigation != NULL) &&
                ((navigation->alignment_algorithm ==
                  SYSTEM_ALIGNMENT_HW_QUAT_9AXIS) ||
                 (navigation->alignment_algorithm ==
                  SYSTEM_ALIGNMENT_HW_QUAT_6AXIS_KNOWN_YAW)));
            *required = (uint8_t)((*used != 0U) && ((required_mask &
                SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE) != 0U));
            break;
        default:
            break;
    }
}

static void SystemSensorStatus_AlignmentFlagsApply(
    SystemSensorStatus *status)
{
    const SystemNavigationProfile *navigation = SystemNavigationProfile_Get();
    SystemAlignmentSummary alignment;
    SystemAlignmentSourceMask selected_mask =
        SYSTEM_USER_ALIGNMENT_SELECTED_MASK;
    SystemAlignmentSourceMask required_mask =
        SYSTEM_USER_ALIGNMENT_REQUIRED_MASK;
    uint8_t used = 0U;
    uint8_t required = 0U;

    if (SystemAlignment_SummaryGet(&alignment) == SYSTEM_DEVICE_OK)
    {
        selected_mask = alignment.selected_mask;
        required_mask = alignment.required_mask;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemSensorStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemSensorStatus_AlignmentUsageResolve(status->sensor_id, navigation,
        selected_mask, required_mask, &used, &required);
    if (used != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_ALIGNMENT_USED;
    }
    if (required != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_REQUIRED_FOR_START;
    }
}

static void SystemSensorStatus_HealthApply(SystemSensorStatus *status,
                                           const SystemDeviceHealth *health,
                                           SystemDeviceResult result)
{
    if ((result != SYSTEM_DEVICE_OK) || (health == NULL)) { return; }
    if (health->initialized != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_INITIALIZED;
    }
    if (health->online != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_ONLINE;
    }
    if (health->healthy != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_HEALTHY;
    }
}

static void SystemSensorStatus_DetailResolve(SystemSensorStatus *status)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemSensorStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((status->status_flags & SYSTEM_SENSOR_STATUS_INITIALIZED) == 0U)
    {
        status->detail_code = SYSTEM_SENSOR_DETAIL_INIT_FAILED;
    }
    else if ((status->status_flags & SYSTEM_SENSOR_STATUS_ONLINE) == 0U)
    {
        status->detail_code = SYSTEM_SENSOR_DETAIL_OFFLINE;
    }
    else if ((status->status_flags & SYSTEM_SENSOR_STATUS_HEALTHY) == 0U)
    {
        status->detail_code = SYSTEM_SENSOR_DETAIL_UNHEALTHY;
    }
    else if ((status->status_flags & SYSTEM_SENSOR_STATUS_DATA_VALID) == 0U)
    {
        status->detail_code =
            ((status->status_flags & SYSTEM_SENSOR_STATUS_ALIGNMENT_USED) !=
             0U) ? SYSTEM_SENSOR_DETAIL_ALIGNMENT_INPUT_INVALID :
                   SYSTEM_SENSOR_DETAIL_NO_VALID_DATA;
    }
    else if ((status->status_flags &
              SYSTEM_SENSOR_STATUS_CALIBRATION_OK) == 0U)
    {
        status->detail_code = SYSTEM_SENSOR_DETAIL_CALIBRATION_REQUIRED;
    }
    else
    {
        status->detail_code = SYSTEM_SENSOR_DETAIL_NONE;
    }
}

static uint8_t SystemSensorStatus_ImuStatusApply(
    SystemSensorStatus *status,
    SystemDeviceHealth *health,
    uint8_t *calibration_ok,
    uint8_t instance_id)
{
    SystemImuSample sample;

    SystemSensorStatus_HealthApply(status, health,
        ProjectDeviceInstance_HealthGet(
            SYSTEM_DEVICE_CLASS_IMU, instance_id, health));
    (void)memset(&sample, 0, sizeof(sample));
    *calibration_ok = SystemCalibration_IsReady();
    return (uint8_t)((ProjectImuInstance_LatestSampleGet(
        instance_id, &sample) ==
        SYSTEM_DEVICE_OK) &&
        ((sample.valid_mask & (SYSTEM_IMU_VALID_ACCEL |
                               SYSTEM_IMU_VALID_GYRO)) ==
         (SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO)));
}

static uint8_t SystemSensorStatus_GnssStatusApply(
    SystemSensorStatus *status,
    SystemDeviceHealth *health,
    uint8_t instance_id)
{
    SystemGnssSample sample;

    SystemSensorStatus_HealthApply(status, health,
        ProjectDeviceInstance_HealthGet(
            SYSTEM_DEVICE_CLASS_GNSS, instance_id, health));
    (void)memset(&sample, 0, sizeof(sample));
    return (uint8_t)((ProjectGnssInstance_LatestSampleGet(
        instance_id, &sample) ==
        SYSTEM_DEVICE_OK) && (sample.position_usable != 0U));
}

static uint8_t SystemSensorStatus_BarometerStatusApply(
    SystemSensorStatus *status,
    SystemDeviceHealth *health,
    uint8_t instance_id)
{
    SystemBarometerSample sample;

    SystemSensorStatus_HealthApply(status, health,
        ProjectDeviceInstance_HealthGet(
            SYSTEM_DEVICE_CLASS_BAROMETER, instance_id, health));
    (void)memset(&sample, 0, sizeof(sample));
    return (uint8_t)((ProjectBarometerInstance_LatestSampleGet(
        instance_id, &sample) ==
        SYSTEM_DEVICE_OK) &&
        ((sample.valid_fields & (SYSTEM_BARO_FIELD_ALTITUDE |
                                 SYSTEM_BARO_FIELD_PRESSURE)) != 0U));
}

static uint8_t SystemSensorStatus_MagnetometerStatusApply(
    SystemSensorStatus *status,
    SystemDeviceHealth *health,
    uint8_t *calibration_ok,
    uint8_t instance_id)
{
    SystemMagnetometerSample sample;
    uint8_t data_valid;

    SILVERSTAR_ASSERT_OBJECT(status, SystemSensorStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemSensorStatus_HealthApply(status, health,
        ProjectDeviceInstance_HealthGet(
            SYSTEM_DEVICE_CLASS_MAGNETOMETER, instance_id, health));
    (void)memset(&sample, 0, sizeof(sample));
    data_valid = (uint8_t)((ProjectMagnetometerInstance_LatestSampleGet(
        instance_id, &sample) ==
        SYSTEM_DEVICE_OK) &&
        ((sample.valid_mask & SYSTEM_MAG_VALID_PHYSICAL_UNIT) != 0U));
    if ((status->status_flags & SYSTEM_SENSOR_STATUS_ALIGNMENT_USED) != 0U)
    {
        *calibration_ok = sample.calibration_valid;
    }
    return data_valid;
}

static uint8_t SystemSensorStatus_HardwareAttitudeStatusApply(
    SystemSensorStatus *status,
    SystemDeviceHealth *health,
    uint8_t instance_id)
{
    SystemHardwareQuaternionSample sample;

    SystemSensorStatus_HealthApply(status, health,
        ProjectDeviceInstance_HealthGet(
            SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION,
            instance_id, health));
    (void)memset(&sample, 0, sizeof(sample));
    return (uint8_t)((ProjectAttitudeInstance_LatestSampleGet(
        instance_id, &sample) ==
        SYSTEM_DEVICE_OK) && (sample.valid != 0U) &&
        (sample.normalized != 0U));
}

static SystemDeviceResult SystemSensorStatus_BuiltinGet(
    const SystemSensorDescriptor *descriptor,
    SystemSensorStatus *status)
{
    SystemDeviceHealth health;
    uint8_t data_valid = 0U;
    uint8_t calibration_ok = 1U;

    if ((descriptor == NULL) || (status == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(status, 0, sizeof(*status));
    (void)memset(&health, 0, sizeof(health));
    SILVERSTAR_ASSERT_OBJECT(descriptor, SystemSensorDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    status->sensor_id = descriptor->sensor_id;
    status->instance_id = descriptor->instance_id;
    status->status_flags = SYSTEM_SENSOR_STATUS_REGISTERED;
    SystemSensorStatus_AlignmentFlagsApply(status);
    switch (descriptor->source)
    {
        case SYSTEM_SENSOR_SOURCE_IMU:
            data_valid = SystemSensorStatus_ImuStatusApply(status, &health,
                &calibration_ok, descriptor->instance_id);
            break;
        case SYSTEM_SENSOR_SOURCE_GNSS:
            data_valid = SystemSensorStatus_GnssStatusApply(
                status, &health, descriptor->instance_id);
            break;
        case SYSTEM_SENSOR_SOURCE_BAROMETER:
            data_valid = SystemSensorStatus_BarometerStatusApply(status,
                &health, descriptor->instance_id);
            break;
        case SYSTEM_SENSOR_SOURCE_MAGNETOMETER:
            data_valid = SystemSensorStatus_MagnetometerStatusApply(status,
                &health, &calibration_ok, descriptor->instance_id);
            break;
        case SYSTEM_SENSOR_SOURCE_HARDWARE_ATTITUDE:
            data_valid = SystemSensorStatus_HardwareAttitudeStatusApply(
                status, &health, descriptor->instance_id);
            break;
        default:
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
    if (data_valid != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_DATA_VALID;
    }
    if (calibration_ok != 0U)
    {
        status->status_flags |= SYSTEM_SENSOR_STATUS_CALIBRATION_OK;
    }
    SystemSensorStatus_DetailResolve(status);
    return SYSTEM_DEVICE_OK;
}

void SystemSensorStatus_Reset(void)
{
    uint32_t primask = SystemSensorStatus_IrqLock();

    (void)memset(s_descriptors, 0, sizeof(s_descriptors));
    (void)memset(s_snapshot, 0, sizeof(s_snapshot));
    (void)memset(s_capture_working, 0, sizeof(s_capture_working));
    (void)memset(&s_snapshot_info, 0, sizeof(s_snapshot_info));
    s_descriptor_count = 0U;
    s_capture_active = 0U;
    SystemSensorStatus_IrqUnlock(primask);
}

uint8_t SystemSensorStatus_CountGet(void)
{
    uint8_t count;
    uint32_t primask;

    SystemSensorStatus_DescriptorsRefresh();
    primask = SystemSensorStatus_IrqLock();
    count = s_descriptor_count;
    SystemSensorStatus_IrqUnlock(primask);
    return count;
}

SystemDeviceResult SystemSensorStatus_Get(uint8_t index,
                                          SystemSensorStatus *status)
{
    SystemSensorDescriptor descriptor;
    uint32_t primask;

    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SystemSensorStatus_DescriptorsRefresh();
    primask = SystemSensorStatus_IrqLock();
    if (index >= s_descriptor_count)
    {
        SystemSensorStatus_IrqUnlock(primask);
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    descriptor = s_descriptors[index];
    SystemSensorStatus_IrqUnlock(primask);
    return SystemSensorStatus_BuiltinGet(&descriptor, status);
}

uint8_t SystemSensorStatus_SummaryFlagsGet(void)
{
    uint8_t flags = (1U << 3);
    uint8_t index;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(s_descriptors, SystemSensorDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemSensorStatus_DescriptorsRefresh();
    primask = SystemSensorStatus_IrqLock();
    for (index = 0U; index < s_descriptor_count; index++)
    {
        if (s_descriptors[index].sensor_id == SILVERSTAR_SENSOR_ID_IMU)
        {
            flags |= (1U << 0);
        }
        else if (s_descriptors[index].sensor_id == SILVERSTAR_SENSOR_ID_GNSS)
        {
            flags |= (1U << 1);
        }
        else
        {
            flags |= (1U << 2);
        }
    }
    SystemSensorStatus_IrqUnlock(primask);
    return flags;
}

SystemDeviceResult SystemSensorStatus_SnapshotCapture(uint8_t alignment_state)
{
    SystemSensorStatusSnapshotInfo info;
    SystemDeviceResult result = SYSTEM_DEVICE_OK;
    uint8_t count;
    uint8_t index;
    uint32_t primask;

    primask = SystemSensorStatus_IrqLock();
    if (s_capture_active != 0U)
    {
        SystemSensorStatus_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    s_capture_active = 1U;
    info = s_snapshot_info;
    SystemSensorStatus_IrqUnlock(primask);
    SILVERSTAR_ASSERT_OBJECT(&info, SystemSensorStatusSnapshotInfo,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    count = SystemSensorStatus_CountGet();
    for (index = 0U; index < count; index++)
    {
        result = SystemSensorStatus_Get(index, &s_capture_working[index]);
        if (result != SYSTEM_DEVICE_OK) { break; }
    }
    primask = SystemSensorStatus_IrqLock();
    if (result == SYSTEM_DEVICE_OK)
    {
        (void)memcpy(s_snapshot, s_capture_working,
                     (size_t)count * sizeof(s_snapshot[0]));
        info.sequence++;
        info.snapshot_id++;
        info.total = count;
        info.alignment_state = alignment_state;
        info.valid = 1U;
        s_snapshot_info = info;
    }
    s_capture_active = 0U;
    SystemSensorStatus_IrqUnlock(primask);
    return result;
}

SystemDeviceResult SystemSensorStatus_SnapshotInfoGet(
    SystemSensorStatusSnapshotInfo *info)
{
    uint32_t primask;

    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SystemSensorStatus_IrqLock();
    *info = s_snapshot_info;
    SystemSensorStatus_IrqUnlock(primask);
    return (info->valid != 0U) ? SYSTEM_DEVICE_OK :
                                SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemSensorStatus_SnapshotGet(
    uint8_t index,
    SystemSensorStatus *status)
{
    uint32_t primask;

    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SystemSensorStatus_IrqLock();
    if ((s_snapshot_info.valid == 0U) ||
        (index >= s_snapshot_info.total))
    {
        SystemSensorStatus_IrqUnlock(primask);
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *status = s_snapshot[index];
    SystemSensorStatus_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}
