#include "system_source_selector.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "project_device_build_capabilities.h"
#include "system_barometer_if.h"
#include "system_barometer_cold.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#include "system_mag_calibration.h"
#include "system_telemetry_transport_if.h"
#include "system_time.h"

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#include "sslog_protocol.h"
#endif

#define SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE 0xFFU
#define SYSTEM_SOURCE_SELECTOR_PENDING_EVENT_COUNT_MAX 4U
#define SYSTEM_GNSS_RECOVERY_DELAY_MS 1000UL
#define SYSTEM_GNSS_RECOVERY_BACKOFF_MAX 5U
#define SYSTEM_TELEMETRY_RECOVERY_DELAY_MS 1000UL
#define SYSTEM_TELEMETRY_RECOVERY_BACKOFF_MAX 5U
#define SYSTEM_TELEMETRY_CLEANUP_BACKOFF_MAX 6U
#define SYSTEM_TELEMETRY_SWITCH_COOLDOWN_MS 32000UL

typedef struct
{
    SystemDeviceClass device_class;
    uint8_t old_instance;
    uint8_t new_instance;
    SystemSourceChangeReason reason;
} SystemSourceSelectorPendingEvent;

typedef struct
{
    uint8_t order[PROJECT_IMU_INSTANCE_COUNT_MAX];
    uint8_t initialized[PROJECT_IMU_INSTANCE_COUNT_MAX];
    uint8_t started[PROJECT_IMU_INSTANCE_COUNT_MAX];
    uint8_t count;
    uint8_t configured_primary;
    uint8_t active;
    uint8_t active_position;
    uint8_t locked;
} SystemSourceSelectorImuState;

typedef struct
{
    uint8_t order[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint8_t initialized[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint8_t started[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint8_t cleanup_pending[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint8_t count;
    uint8_t configured_primary;
    uint8_t active;
    uint8_t active_position;
    uint8_t recovery_position;
    uint8_t runtime_enabled;
    uint8_t runtime_owner_active;
    uint8_t recovery_failures[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint32_t recovery_scheduled_ms[PROJECT_GNSS_INSTANCE_COUNT_MAX];
    uint64_t active_after_us;
} SystemSourceSelectorGnssState;

typedef struct
{
    uint8_t order[PROJECT_TELEMETRY_INSTANCE_COUNT_MAX];
    uint8_t initialized[PROJECT_TELEMETRY_INSTANCE_COUNT_MAX];
    uint8_t started[PROJECT_TELEMETRY_INSTANCE_COUNT_MAX];
    uint8_t cleanup_pending[PROJECT_TELEMETRY_INSTANCE_COUNT_MAX];
    uint8_t count;
    uint8_t configured_primary;
    uint8_t active;
    uint8_t active_position;
    uint16_t consecutive_timeout_count;
    uint32_t observed_transmit_count;
    uint32_t observed_timeout_count;
    uint32_t recovery_scheduled_ms;
    uint8_t recovery_failures;
    uint8_t active_offline;
    uint8_t start_requested;
    uint8_t cooldown_active[PROJECT_TELEMETRY_INSTANCE_COUNT_MAX];
    uint32_t cooldown_scheduled_ms[PROJECT_TELEMETRY_INSTANCE_COUNT_MAX];
} SystemSourceSelectorTelemetryState;

static SystemSourceSelectorImuState s_imu;
static SystemSourceSelectorGnssState s_gnss;
static SystemSourceSelectorTelemetryState s_telemetry;
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static SystemSourceSelectorPendingEvent
    s_pending_events[SYSTEM_SOURCE_SELECTOR_PENDING_EVENT_COUNT_MAX];
static uint8_t s_pending_event_count;
static uint8_t s_pending_event_flush_active;
#endif

_Static_assert(PROJECT_IMU_INSTANCE_COUNT_MAX <= 4U,
    "IMU selector bound exceeds the SilverStar 0.1.0 contract");
_Static_assert(PROJECT_GNSS_INSTANCE_COUNT_MAX <= 4U,
    "GNSS selector bound exceeds the SilverStar 0.1.0 contract");
_Static_assert(PROJECT_TELEMETRY_INSTANCE_COUNT_MAX <= 4U,
    "telemetry selector bound exceeds the SilverStar 0.1.0 contract");
_Static_assert(SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT > 0U,
    "telemetry timeout failover limit must be positive");

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
_Static_assert(
    (int)SYSTEM_SOURCE_CHANGE_REASON_RECOVERY ==
        (int)FLIGHT_LOG_SENSOR_SOURCE_CHANGE_RECOVERY,
    "source-change reason catalog mismatch");
_Static_assert(
    (int)SYSTEM_SOURCE_CHANGE_REASON_PRESTART_PRIMARY_UNAVAILABLE ==
        (int)FLIGHT_LOG_SENSOR_SOURCE_CHANGE_PRESTART_PRIMARY_UNAVAILABLE,
    "source-change reason catalog mismatch");
_Static_assert(
    (int)SYSTEM_SOURCE_CHANGE_REASON_GNSS_LIVENESS_TIMEOUT ==
        (int)FLIGHT_LOG_SENSOR_SOURCE_CHANGE_GNSS_LIVENESS_TIMEOUT,
    "source-change reason catalog mismatch");
_Static_assert(
    (int)SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_CONSECUTIVE_TX_TIMEOUT ==
        (int)FLIGHT_LOG_SENSOR_SOURCE_CHANGE_TELEMETRY_CONSECUTIVE_TX_TIMEOUT,
    "source-change reason catalog mismatch");
_Static_assert(
    (int)SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_INIT_FAILURE ==
        (int)FLIGHT_LOG_SENSOR_SOURCE_CHANGE_TELEMETRY_INIT_FAILURE,
    "source-change reason catalog mismatch");
#endif

static uint8_t SystemSourceSelector_ResultSuccessful(
    SystemDeviceResult result)
{
    return (uint8_t)((result == SYSTEM_DEVICE_OK) ||
                     (result == SYSTEM_DEVICE_ALREADY_MATCHED) ||
                     (result == SYSTEM_DEVICE_VALUE_ADJUSTED) ||
                     (result == SYSTEM_DEVICE_CONFIG_NO_ACTION) ||
                     (result == SYSTEM_DEVICE_CONFIG_DELEGATED));
}

static uint8_t SystemSourceSelector_OrderBuild(
    SystemDeviceClass device_class, uint8_t count, uint8_t bound,
    uint8_t *order)
{
    uint8_t primary = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    uint8_t instance_id;
    uint8_t output_index = 0U;

    if ((order == NULL) || (count > bound)) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(order, uint8_t,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (instance_id = 0U; instance_id < bound; instance_id++)
    {
        SystemDeviceDescriptor descriptor;

        if (instance_id >= count) { break; }
        if ((ProjectDeviceInstance_DescriptorGet(
                 device_class, instance_id, &descriptor) == SYSTEM_DEVICE_OK) &&
            ((descriptor.flags & SYSTEM_DESCRIPTOR_FLAG_PRIMARY) != 0U))
        {
            primary = instance_id;
            break;
        }
    }
    if ((primary == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) && (count > 0U))
    {
        primary = 0U;
    }
    if (primary != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    {
        order[output_index] = primary;
        output_index++;
    }
    for (instance_id = 0U; instance_id < bound; instance_id++)
    {
        if (instance_id >= count) { break; }
        if (instance_id == primary) { continue; }
        order[output_index] = instance_id;
        output_index++;
    }
    return output_index;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static LoggerBusResult SystemSourceSelector_EventWrite(
    const SystemSourceSelectorPendingEvent *event)
{
    SystemDeviceDescriptor old_descriptor;
    SystemDeviceDescriptor new_descriptor;

    if (event == NULL) { return LOGGER_BUS_RESULT_BAD_PARAM; }
    (void)memset(&old_descriptor, 0, sizeof(old_descriptor));
    (void)memset(&new_descriptor, 0, sizeof(new_descriptor));
    if (((event->old_instance != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
         (ProjectDeviceInstance_DescriptorGet(event->device_class,
             event->old_instance, &old_descriptor) != SYSTEM_DEVICE_OK)) ||
        ((event->new_instance != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
         (ProjectDeviceInstance_DescriptorGet(event->device_class,
             event->new_instance, &new_descriptor) != SYSTEM_DEVICE_OK)))
    {
        return LOGGER_BUS_RESULT_BAD_PARAM;
    }
    return LoggerBus_EventPush(SystemTime_GetMonotonicUs(),
        FLIGHT_LOG_EVENT_SENSOR_SOURCE_CHANGE,
        FLIGHT_LOG_SENSOR_SOURCE_CHANGE_ARG0(event->device_class,
            event->old_instance, event->new_instance, event->reason),
        FLIGHT_LOG_SENSOR_SOURCE_CHANGE_ARG1(old_descriptor.descriptor_id,
            new_descriptor.descriptor_id));
}
#endif

static void SystemSourceSelector_EventRecord(
    SystemDeviceClass device_class, uint8_t old_instance,
    uint8_t new_instance, SystemSourceChangeReason reason)
{
    SILVERSTAR_ASSERT((device_class >= SYSTEM_DEVICE_CLASS_IMU) &&
                      (device_class <= SYSTEM_DEVICE_CLASS_TIME),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(
        (reason >= SYSTEM_SOURCE_CHANGE_REASON_RECOVERY) &&
        (reason <= SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_INIT_FAILURE),
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    SystemSourceSelectorPendingEvent event;

    if ((old_instance == new_instance) &&
        (reason != SYSTEM_SOURCE_CHANGE_REASON_RECOVERY)) { return; }
    event.device_class = device_class;
    event.old_instance = old_instance;
    event.new_instance = new_instance;
    event.reason = reason;
    if (SystemSourceSelector_EventWrite(&event) == LOGGER_BUS_RESULT_OK)
    {
        return;
    }
    {
        PlatformCriticalState state = PlatformCritical_Enter();

        if (s_pending_event_count <
            SYSTEM_SOURCE_SELECTOR_PENDING_EVENT_COUNT_MAX)
        {
            s_pending_events[s_pending_event_count] = event;
            s_pending_event_count++;
        }
        PlatformCritical_Exit(state);
    }
#else
    (void)device_class;
    (void)old_instance;
    (void)new_instance;
    (void)reason;
#endif
}

void SystemSourceSelector_PendingEventsFlush(void)
{
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    uint8_t attempt;

    SILVERSTAR_ASSERT(s_pending_event_count <=
                      SYSTEM_SOURCE_SELECTOR_PENDING_EVENT_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT(s_pending_event_flush_active <= 1U,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (attempt = 0U;
         attempt < SYSTEM_SOURCE_SELECTOR_PENDING_EVENT_COUNT_MAX;
         attempt++)
    {
        SystemSourceSelectorPendingEvent event;
        PlatformCriticalState state;
        LoggerBusResult result;
        uint8_t index;

        state = PlatformCritical_Enter();
        if ((s_pending_event_count == 0U) ||
            (s_pending_event_flush_active != 0U))
        {
            PlatformCritical_Exit(state);
            break;
        }
        event = s_pending_events[0];
        s_pending_event_flush_active = 1U;
        PlatformCritical_Exit(state);

        result = SystemSourceSelector_EventWrite(&event);

        state = PlatformCritical_Enter();
        if (result == LOGGER_BUS_RESULT_OK)
        {
            for (index = 1U;
                 index < SYSTEM_SOURCE_SELECTOR_PENDING_EVENT_COUNT_MAX;
                 index++)
            {
                if (index >= s_pending_event_count) { break; }
                s_pending_events[index - 1U] = s_pending_events[index];
            }
            s_pending_event_count--;
        }
        s_pending_event_flush_active = 0U;
        PlatformCritical_Exit(state);
        if (result != LOGGER_BUS_RESULT_OK) { break; }
    }
#endif
}

static uint8_t SystemSourceSelector_PrimaryInstanceGet(
    SystemDeviceClass device_class)
{
    uint8_t count;
    uint8_t instance_id;
    uint8_t primary = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;

    SILVERSTAR_ASSERT((device_class >= SYSTEM_DEVICE_CLASS_IMU) &&
                      (device_class <= SYSTEM_DEVICE_CLASS_TIME),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    count = ProjectDeviceInstance_CountGet(device_class);
    SILVERSTAR_ASSERT(count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U;
         instance_id < PROJECT_IMU_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        SystemDeviceDescriptor descriptor;

        if (instance_id >= count) { break; }
        if ((ProjectDeviceInstance_DescriptorGet(device_class,
                 instance_id, &descriptor) == SYSTEM_DEVICE_OK) &&
            ((descriptor.flags & SYSTEM_DESCRIPTOR_FLAG_PRIMARY) != 0U))
        {
            primary = instance_id;
            break;
        }
    }
    if ((primary == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) && (count > 0U))
    {
        primary = 0U;
    }
    return primary;
}

static uint8_t SystemSourceSelector_CompanionActiveGet(
    SystemDeviceClass device_class)
{
    if ((SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U) &&
        (device_class == SYSTEM_DEVICE_CLASS_BAROMETER))
    { return SystemBarometerCold_ActiveGet(); }
    /* Companion capabilities keep their own configured canonical source. */
    return SystemSourceSelector_PrimaryInstanceGet(device_class);
}

static uint8_t SystemSourceSelector_ImuSampleUsable(uint8_t instance_id)
{
    SystemDeviceHealth health;
    SystemImuSample sample;
    uint64_t now_us;
    uint8_t axis;

    SILVERSTAR_ASSERT(instance_id < s_imu.count,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_imu.count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    (void)memset(&health, 0, sizeof(health));
    (void)memset(&sample, 0, sizeof(sample));
    if ((ProjectImuInstance_HealthGet(instance_id, &health) !=
         SYSTEM_DEVICE_OK) ||
        (health.initialized == 0U) || (health.started == 0U) ||
        (health.online == 0U) ||
        (ProjectImuInstance_LatestSampleGet(instance_id, &sample) !=
         SYSTEM_DEVICE_OK) ||
        ((sample.valid_mask & (SYSTEM_IMU_VALID_ACCEL |
                              SYSTEM_IMU_VALID_GYRO)) !=
         (SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO)))
    {
        return 0U;
    }
    now_us = SystemTime_GetMonotonicUs();
    if ((sample.receive_timestamp_us == 0ULL) ||
        (now_us < sample.receive_timestamp_us) ||
        ((now_us - sample.receive_timestamp_us) >
         SYSTEM_SOURCE_SELECTOR_IMU_FRESH_TIMEOUT_US))
    {
        return 0U;
    }
    for (axis = 0U; axis < 3U; axis++)
    {
        if ((!isfinite(sample.accel_b_mps2[axis])) ||
            (!isfinite(sample.gyro_b_radps[axis])))
        {
            return 0U;
        }
    }
    return 1U;
}

static uint8_t SystemSourceSelector_ImuFreshSelect(void)
{
    uint8_t position;

    SILVERSTAR_ASSERT(s_imu.count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(s_imu.locked <= 1U,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        if ((s_imu.initialized[instance_id] != 0U) &&
            (s_imu.started[instance_id] != 0U) &&
            (SystemSourceSelector_ImuSampleUsable(instance_id) != 0U))
        {
            s_imu.active = instance_id;
            s_imu.active_position = position;
            return instance_id;
        }
    }
    return SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
}

SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void)
{
    uint8_t selected;

    SILVERSTAR_ASSERT(s_imu.count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    SILVERSTAR_ASSERT(s_imu.locked <= 1U,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_imu.locked != 0U)
    {
        return (s_imu.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ?
            SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
    }
    selected = SystemSourceSelector_ImuFreshSelect();
    if (selected == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    s_imu.locked = 1U;
    if ((s_imu.configured_primary != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (selected != s_imu.configured_primary))
    {
        SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_IMU,
            s_imu.configured_primary, selected,
            SYSTEM_SOURCE_CHANGE_REASON_PRESTART_PRIMARY_UNAVAILABLE);
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(
    uint8_t *instance_id)
{
    if (instance_id == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    *instance_id = s_imu.active;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(
    uint8_t *instance_id)
{
    if (instance_id == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    *instance_id = s_gnss.active;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemSourceSelector_TelemetryActiveInstanceGet(
    uint8_t *instance_id)
{
    if (instance_id == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    *instance_id = s_telemetry.active;
    return SYSTEM_DEVICE_OK;
}

uint16_t SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet(void)
{
    return s_telemetry.consecutive_timeout_count;
}

const char *SystemImu_NameGet(void)
{
    SystemDeviceInfo info;

    if ((s_imu.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectImuInstance_InfoGet(s_imu.active, &info) == SYSTEM_DEVICE_OK) &&
        (info.device_name != NULL))
    {
        return info.device_name;
    }
    return "IMU";
}

/* Prepared is owned by the instance, not duplicated selector state.
 * The ordinary constant branch never calls the compact provider query. */
static uint8_t SystemSourceSelector_ImuPreparedGet(uint8_t instance_id)
{
    uint8_t prepared = 0U;
    if (SILVERSTAR_BUILD_COMPACT_ENABLED == 0U) { return 0U; }
    return (uint8_t)((ProjectImuInstance_RecoveryPreparedGet(instance_id, &prepared) == SYSTEM_DEVICE_OK) &&
        (prepared != 0U));
}

SystemDeviceResult SystemImu_Init(void)
{
    SystemDeviceResult first_failure = SYSTEM_DEVICE_NOT_PRESENT;
    uint8_t position;
    uint8_t success_count = 0U;

    (void)memset(&s_imu, 0, sizeof(s_imu));
    s_imu.active = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_imu.active_position = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_imu.configured_primary = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_imu.count = ProjectImuInstance_CountGet();
    if (s_imu.count > PROJECT_IMU_INSTANCE_COUNT_MAX)
    {
        s_imu.count = 0U;
        return SYSTEM_DEVICE_INTERNAL_ERROR;
    }
    s_imu.count = SystemSourceSelector_OrderBuild(SYSTEM_DEVICE_CLASS_IMU,
        s_imu.count, PROJECT_IMU_INSTANCE_COUNT_MAX, s_imu.order);
    if (s_imu.count > 0U) { s_imu.configured_primary = s_imu.order[0]; }
    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceResult result;
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        SILVERSTAR_ASSERT(instance_id < s_imu.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        result = ProjectImuInstance_Init(instance_id);
        SILVERSTAR_ASSERT((uint32_t)result <= (uint32_t)SYSTEM_DEVICE_NOT_PRESENT,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
        if (SystemSourceSelector_ImuPreparedGet(instance_id) != 0U)
        {
            s_imu.active = instance_id;
            s_imu.active_position = position;
            /* Preserve real first probe/reset result; do not mark initialized. */
            first_failure = result;
            continue;
        }
        if (SystemSourceSelector_ResultSuccessful(result) != 0U)
        {
            s_imu.initialized[instance_id] = 1U;
            success_count++;
            if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
            {
                s_imu.active = instance_id;
                s_imu.active_position = position;
            }
        }
        else if (first_failure == SYSTEM_DEVICE_NOT_PRESENT)
        {
            first_failure = result;
        }
    }
    return (success_count > 0U) ? SYSTEM_DEVICE_OK : first_failure;
}

SystemDeviceResult SystemImu_Start(void)
{
    SystemDeviceResult first_failure = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;
    uint8_t success_count = 0U;

    SILVERSTAR_ASSERT(s_imu.count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceResult result;
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        SILVERSTAR_ASSERT(instance_id < s_imu.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        if (s_imu.initialized[instance_id] == 0U)
        {
            if (SystemSourceSelector_ImuPreparedGet(instance_id) == 0U) { continue; }
        }
        s_imu.started[instance_id] = 0U;
        result = ProjectImuInstance_Start(instance_id);
        SILVERSTAR_ASSERT((uint32_t)result <= (uint32_t)SYSTEM_DEVICE_NOT_PRESENT,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
        if (SystemSourceSelector_ResultSuccessful(result) != 0U)
        {
            s_imu.started[instance_id] = 1U;
            success_count++;
        }
        else if (first_failure == SYSTEM_DEVICE_NOT_READY)
        {
            first_failure = result;
        }
    }
    if ((success_count > 0U) && (SystemSourceSelector_ImuPreparedGet(0U) != 0U) &&
        (s_imu.initialized[0] == 0U))
    { return SYSTEM_DEVICE_CONFIG_DELEGATED; }
    return (success_count > 0U) ? SYSTEM_DEVICE_OK : first_failure;
}

SystemDeviceResult SystemImu_Stop(void)
{
    SystemDeviceResult result = SYSTEM_DEVICE_OK;
    uint8_t position;

    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        if (s_imu.started[instance_id] == 0U) { continue; }
        if (ProjectImuInstance_Stop(instance_id) != SYSTEM_DEVICE_OK)
        {
            result = SYSTEM_DEVICE_IO_ERROR;
        }
        s_imu.started[instance_id] = 0U;
    }
    return result;
}

SystemDeviceResult SystemImu_RuntimeOwnerActivate(void)
{
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;

    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t instance_id;
        SystemDeviceResult candidate_result;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        if (s_imu.initialized[instance_id] == 0U)
        {
            if (SystemSourceSelector_ImuPreparedGet(instance_id) == 0U) { continue; }
        }
        candidate_result = ProjectImuInstance_RuntimeOwnerActivate(instance_id);
        if (instance_id == s_imu.active) { result = candidate_result; }
    }
    return result;
}

void SystemImu_Process(void)
{
    uint8_t position;

    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        if ((SILVERSTAR_BUILD_COMPACT_ENABLED != 0U) &&
            (instance_id >= PROJECT_IMU_INSTANCE_COUNT_MAX))
        {
            SILVERSTAR_ASSERT(instance_id < PROJECT_IMU_INSTANCE_COUNT_MAX,
                SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
            return;
        }
        if (s_imu.started[instance_id] != 0U)
        {
            (void)ProjectImuInstance_Process(instance_id);
            if (SystemSourceSelector_ImuPreparedGet(instance_id) != 0U)
            {
                SystemDeviceHealth health;
                s_imu.initialized[instance_id] =
                    (uint8_t)((ProjectImuInstance_HealthGet(instance_id, &health) == SYSTEM_DEVICE_OK) &&
                    (health.initialized != 0U));
            }
        }
    }
    if (s_imu.locked == 0U) { (void)SystemSourceSelector_ImuFreshSelect(); }
    SystemSourceSelector_PendingEventsFlush();
}

SystemDeviceResult SystemImu_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_InfoGet(s_imu.active, info);
}

SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_CapabilitiesGet(
        s_imu.active, capability_mask);
}

SystemDeviceResult SystemImu_HealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_HealthGet(s_imu.active, health);
}

SystemDeviceResult SystemImu_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_IoDiagnosticsGet(s_imu.active, diagnostics);
}

SystemDeviceResult SystemImu_IoDetailGet(SystemImuIoDetail *detail)
{
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_IoDetailGet(s_imu.active, detail);
}

SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.locked == 0U) { (void)SystemSourceSelector_ImuFreshSelect(); }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_LatestSampleGet(s_imu.active, sample);
}

SystemDeviceResult SystemImu_NextSampleGet(SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_NextSampleGet(s_imu.active, sample);
}

SystemDeviceResult SystemImu_SelfTestRun(SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_SelfTestRun(s_imu.active, result);
}

SystemDeviceResult SystemImu_ConfigApply(const SystemImuConfig *config,
                                          SystemDeviceConfigReport *report)
{
    SystemDeviceResult active_result = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemImuConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceConfigReport candidate_report;
        SystemDeviceResult candidate_result;
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        if ((s_imu.initialized[instance_id] == 0U) &&
            (SystemSourceSelector_ImuPreparedGet(instance_id) == 0U))
        { continue; }
        (void)memset(&candidate_report, 0, sizeof(candidate_report));
        candidate_result = ProjectImuInstance_ConfigApply(instance_id,
            config, &candidate_report);
        if (instance_id == s_imu.active)
        {
            *report = candidate_report;
            active_result = candidate_result;
        }
    }
    return active_result;
}

SystemDeviceResult SystemImu_ConfigVerify(const SystemImuConfig *config,
                                           SystemDeviceConfigReport *report)
{
    SystemDeviceResult active_result = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemImuConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (position = 0U;
         position < PROJECT_IMU_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceConfigReport candidate_report;
        SystemDeviceResult candidate_result;
        uint8_t instance_id;

        if (position >= s_imu.count) { break; }
        instance_id = s_imu.order[position];
        if ((s_imu.initialized[instance_id] == 0U) &&
            (SystemSourceSelector_ImuPreparedGet(instance_id) == 0U))
        { continue; }
        (void)memset(&candidate_report, 0, sizeof(candidate_report));
        candidate_result = ProjectImuInstance_ConfigVerify(instance_id,
            config, &candidate_report);
        if (instance_id == s_imu.active)
        {
            *report = candidate_report;
            active_result = candidate_result;
        }
    }
    return active_result;
}

SystemDeviceResult SystemImu_EffectiveConfigGet(SystemImuConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_EffectiveConfigGet(s_imu.active, config);
}

SystemDeviceResult SystemImu_NoiseCharacteristicsGet(
    SystemImuNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_imu.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectImuInstance_NoiseCharacteristicsGet(s_imu.active, noise);
}

static void SystemSourceSelector_GnssSwitchEvaluate(void)
{
    SystemDeviceHealth health;
    uint8_t position;

    SILVERSTAR_ASSERT(s_gnss.count <= PROJECT_GNSS_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) { return; }
    SILVERSTAR_ASSERT(s_gnss.active < s_gnss.count,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_gnss.active_position < s_gnss.count) &&
        (s_gnss.order[s_gnss.active_position] == s_gnss.active),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    (void)memset(&health, 0, sizeof(health));
    if ((ProjectGnssInstance_HealthGet(s_gnss.active, &health) ==
         SYSTEM_DEVICE_OK) &&
        (health.initialized != 0U) && (health.started != 0U) &&
        (health.online != 0U))
    {
        return;
    }
    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceHealth candidate_health;
        uint8_t candidate;

        if (position >= s_gnss.count) { break; }
        if (position == s_gnss.active_position) { continue; }
        candidate = s_gnss.order[position];
        SILVERSTAR_ASSERT(candidate < s_gnss.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        if ((s_gnss.initialized[candidate] == 0U) ||
            (s_gnss.started[candidate] == 0U))
        {
            continue;
        }
        (void)memset(&candidate_health, 0, sizeof(candidate_health));
        if ((ProjectGnssInstance_HealthGet(candidate, &candidate_health) ==
             SYSTEM_DEVICE_OK) &&
            (candidate_health.initialized != 0U) &&
            (candidate_health.started != 0U) &&
            (candidate_health.online != 0U))
        {
            uint8_t previous = s_gnss.active;

            s_gnss.active = candidate;
            s_gnss.active_position = position;
            s_gnss.active_after_us = SystemTime_GetMonotonicUs();
            SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_GNSS,
                previous, candidate,
                SYSTEM_SOURCE_CHANGE_REASON_GNSS_LIVENESS_TIMEOUT);
            break;
        }
    }
}

static void SystemSourceSelector_GnssFailureCount(uint8_t candidate)
{
    if (s_gnss.recovery_failures[candidate] < SYSTEM_GNSS_RECOVERY_BACKOFF_MAX)
    { s_gnss.recovery_failures[candidate]++; }
}

static void SystemSourceSelector_GnssRecoveryAttempt(
    uint8_t candidate, uint8_t position)
{
    SystemDeviceResult result;
    if ((s_gnss.started[candidate] != 0U) ||
        (s_gnss.cleanup_pending[candidate] != 0U))
    {
        result = ProjectGnssInstance_Stop(candidate);
        if (SystemSourceSelector_ResultSuccessful(result) == 0U)
        { SystemSourceSelector_GnssFailureCount(candidate); return; }
        s_gnss.started[candidate] = 0U;
        s_gnss.cleanup_pending[candidate] = 0U;
    }
    if (s_gnss.initialized[candidate] == 0U)
    {
        result = ProjectGnssInstance_Init(candidate);
        if (SystemSourceSelector_ResultSuccessful(result) == 0U)
        { SystemSourceSelector_GnssFailureCount(candidate); return; }
        s_gnss.initialized[candidate] = 1U;
    }
    s_gnss.cleanup_pending[candidate] = 1U;
    result = ProjectGnssInstance_Start(candidate);
    SystemSourceSelector_GnssFailureCount(candidate);
    if (SystemSourceSelector_ResultSuccessful(result) == 0U) { return; }
    s_gnss.started[candidate] = 1U;
    s_gnss.cleanup_pending[candidate] = 0U;
    if (s_gnss.runtime_owner_active != 0U)
    {
        result = ProjectGnssInstance_RuntimeOwnerActivate(candidate);
        if (SystemSourceSelector_ResultSuccessful(result) == 0U)
        { s_gnss.started[candidate] = 0U;
          s_gnss.cleanup_pending[candidate] = 1U; return; }
    }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    {
        s_gnss.active = candidate;
        s_gnss.active_position = position;
        SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_GNSS,
            SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE, candidate,
            SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
    }
    if (candidate == s_gnss.active)
    { s_gnss.active_after_us = SystemTime_GetMonotonicUs(); }
}

/* A cold backup is considered before restarting anything. Recovery visits at
 * most one offline instance per Process call and never restarts a healthy one. */
static void SystemSourceSelector_GnssRecoveryProcess(void)
{
    uint8_t step;
    uint64_t now_us = SystemTime_GetMonotonicUs();
    uint32_t now_ms = (uint32_t)(now_us / 1000ULL);
    SystemDeviceHealth health;
    if ((s_gnss.runtime_enabled == 0U) || (s_gnss.count == 0U)) { return; }
    if ((s_gnss.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectGnssInstance_HealthGet(s_gnss.active, &health) == SYSTEM_DEVICE_OK) &&
        (health.initialized != 0U) && (health.started != 0U) &&
        (health.online != 0U))
    {
        if (s_gnss.recovery_failures[s_gnss.active] != 0U)
        {
            SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_GNSS,
                s_gnss.active, s_gnss.active,
                SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
        }
        s_gnss.recovery_failures[s_gnss.active] = 0U;
        return;
    }
    if (s_gnss.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { s_gnss.active_after_us = now_us; }
    for (step = 0U; step < PROJECT_GNSS_INSTANCE_COUNT_MAX; step++)
    {
        uint8_t position;
        uint8_t candidate;
        if (step >= s_gnss.count) { break; }
        position = (uint8_t)((s_gnss.recovery_position + step) % s_gnss.count);
        candidate = s_gnss.order[position];
        if (s_gnss.started[candidate] != 0U)
        {
            uint8_t busy = 0U;
            SystemDeviceResult busy_result =
                ProjectGnssInstance_RecoveryBusyGet(candidate, &busy);
            if ((busy_result != SYSTEM_DEVICE_OK) &&
                (busy_result != SYSTEM_DEVICE_UNSUPPORTED)) { continue; }
            if (busy != 0U) { continue; }
            SystemDeviceResult health_result =
                ProjectGnssInstance_HealthGet(candidate, &health);
            if ((health_result == SYSTEM_DEVICE_OK) && (health.online != 0U))
            { continue; }
        }
        if ((uint32_t)(now_ms - s_gnss.recovery_scheduled_ms[candidate]) <
            (SYSTEM_GNSS_RECOVERY_DELAY_MS << s_gnss.recovery_failures[candidate]))
        { continue; }
        s_gnss.recovery_position = (uint8_t)((position + 1U) % s_gnss.count);
        s_gnss.recovery_scheduled_ms[candidate] = now_ms;
        SystemSourceSelector_GnssRecoveryAttempt(candidate, position);
        break;
    }
}

const char *SystemGnss_NameGet(void)
{
    SystemDeviceInfo info;

    if ((s_gnss.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectGnssInstance_InfoGet(s_gnss.active, &info) ==
         SYSTEM_DEVICE_OK) &&
        (info.device_name != NULL))
    {
        return info.device_name;
    }
    return "GNSS";
}

SystemDeviceResult SystemGnss_Init(void)
{
    SystemDeviceResult first_failure = SYSTEM_DEVICE_NOT_PRESENT;
    uint8_t position;
    uint8_t success_count = 0U;

    (void)memset(&s_gnss, 0, sizeof(s_gnss));
    s_gnss.active = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_gnss.active_position = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_gnss.configured_primary = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_gnss.count = ProjectGnssInstance_CountGet();
    if (s_gnss.count > PROJECT_GNSS_INSTANCE_COUNT_MAX)
    { s_gnss.count = 0U; return SYSTEM_DEVICE_INTERNAL_ERROR; }
    s_gnss.count = SystemSourceSelector_OrderBuild(SYSTEM_DEVICE_CLASS_GNSS,
        s_gnss.count, PROJECT_GNSS_INSTANCE_COUNT_MAX, s_gnss.order);
    if (s_gnss.count > 0U) { s_gnss.configured_primary = s_gnss.order[0]; }
    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceResult result;
        uint8_t instance_id;

        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        SILVERSTAR_ASSERT(instance_id < s_gnss.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        result = ProjectGnssInstance_Init(instance_id);
        SILVERSTAR_ASSERT((uint32_t)result <= (uint32_t)SYSTEM_DEVICE_NOT_PRESENT,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
        if (SystemSourceSelector_ResultSuccessful(result) != 0U)
        {
            s_gnss.initialized[instance_id] = 1U;
            success_count++;
            if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
            {
                s_gnss.active = instance_id;
                s_gnss.active_position = position;
            }
        }
        else if (first_failure == SYSTEM_DEVICE_NOT_PRESENT)
        {
            first_failure = result;
        }
    }
    if ((s_gnss.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (s_gnss.active != s_gnss.configured_primary))
    {
        SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_GNSS,
            s_gnss.configured_primary, s_gnss.active,
            SYSTEM_SOURCE_CHANGE_REASON_PRESTART_PRIMARY_UNAVAILABLE);
    }
    return (success_count > 0U) ? SYSTEM_DEVICE_OK : first_failure;
}

static SystemDeviceResult SystemSourceSelector_GnssStartOne(uint8_t instance_id)
{
    SystemDeviceResult result;
    s_gnss.started[instance_id] = 0U;
    s_gnss.cleanup_pending[instance_id] = 1U;
    result = ProjectGnssInstance_Start(instance_id);
    SILVERSTAR_ASSERT((uint32_t)result <= (uint32_t)SYSTEM_DEVICE_NOT_PRESENT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (SystemSourceSelector_ResultSuccessful(result) != 0U)
    { s_gnss.started[instance_id] = 1U; s_gnss.cleanup_pending[instance_id] = 0U; }
    return result;
}

SystemDeviceResult SystemGnss_Start(void)
{
    SystemDeviceResult first_failure = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;
    uint8_t success_count = 0U;
    uint8_t selected_position = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;

    SILVERSTAR_ASSERT(s_gnss.count <= PROJECT_GNSS_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    s_gnss.runtime_enabled = 1U;
    SILVERSTAR_ASSERT((s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        (s_gnss.active < s_gnss.count), SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        ((s_gnss.active_position < s_gnss.count) &&
         (s_gnss.order[s_gnss.active_position] == s_gnss.active)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceResult result;
        uint8_t instance_id;

        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        SILVERSTAR_ASSERT(instance_id < s_gnss.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        if (s_gnss.initialized[instance_id] == 0U) { continue; }
        result = SystemSourceSelector_GnssStartOne(instance_id);
        if (SystemSourceSelector_ResultSuccessful(result) != 0U)
        {
            success_count++;
            if ((position >= s_gnss.active_position) &&
                (selected_position == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE))
            { selected_position = position; }
        }
        else if (first_failure == SYSTEM_DEVICE_NOT_READY)
        {
            first_failure = result;
        }
    }
    if ((s_gnss.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (selected_position != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE))
    {
        uint8_t previous = s_gnss.active;

        s_gnss.active = s_gnss.order[selected_position];
        s_gnss.active_position = selected_position;
        if (previous != s_gnss.active)
        {
            SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_GNSS,
                previous, s_gnss.active,
                SYSTEM_SOURCE_CHANGE_REASON_PRESTART_PRIMARY_UNAVAILABLE);
        }
    }
    return (success_count > 0U) ? SYSTEM_DEVICE_OK : first_failure;
}

SystemDeviceResult SystemGnss_Stop(void)
{
    SystemDeviceResult result = SYSTEM_DEVICE_OK;
    uint8_t position;
    s_gnss.runtime_enabled = 0U;
    s_gnss.runtime_owner_active = 0U;

    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t instance_id;
        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        if ((s_gnss.started[instance_id] == 0U) &&
            (s_gnss.cleanup_pending[instance_id] == 0U)) { continue; }
        if (ProjectGnssInstance_Stop(instance_id) != SYSTEM_DEVICE_OK)
        { result = SYSTEM_DEVICE_IO_ERROR; }
        else
        { s_gnss.started[instance_id] = 0U; s_gnss.cleanup_pending[instance_id] = 0U; }
    }
    return result;
}

SystemDeviceResult SystemGnss_RuntimeOwnerActivate(void)
{
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;
    s_gnss.runtime_owner_active = 1U;

    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceResult candidate_result;
        uint8_t instance_id;

        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        if (s_gnss.initialized[instance_id] == 0U) { continue; }
        candidate_result = ProjectGnssInstance_RuntimeOwnerActivate(instance_id);
        if (instance_id == s_gnss.active) { result = candidate_result; }
    }
    return result;
}

void SystemGnss_Process(void)
{
    uint8_t position;

    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t instance_id;
        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        if (s_gnss.started[instance_id] != 0U)
        { (void)ProjectGnssInstance_Process(instance_id); }
    }
    SystemSourceSelector_GnssSwitchEvaluate();
    SystemSourceSelector_GnssRecoveryProcess();
    SystemSourceSelector_PendingEventsFlush();
}

SystemDeviceResult SystemGnss_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_InfoGet(s_gnss.active, info);
}

SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_CapabilitiesGet(
        s_gnss.active, capability_mask);
}

SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_HealthGet(s_gnss.active, health);
}

SystemDeviceResult SystemGnss_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_IoDiagnosticsGet(s_gnss.active, diagnostics);
}

SystemDeviceResult SystemGnss_IoDetailGet(SystemGnssIoDetail *detail)
{
    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_IoDetailGet(s_gnss.active, detail);
}

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{
    SystemDeviceResult result;
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    result = ProjectGnssInstance_LatestSampleGet(s_gnss.active, sample);
    if ((result == SYSTEM_DEVICE_OK) && (s_gnss.active_after_us != 0U) &&
        (sample->receive_timestamp_us <= s_gnss.active_after_us))
    { return SYSTEM_DEVICE_NOT_READY; }
    return result;
}

SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{
    if (time == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_TimeGet(s_gnss.active, time);
}

SystemDeviceResult SystemGnss_SelfTestRun(SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_SelfTestRun(s_gnss.active, result);
}

SystemDeviceResult SystemGnss_ConfigApply(const SystemGnssConfig *config,
                                           SystemDeviceConfigReport *report)
{
    SystemDeviceResult active_result = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceConfigReport candidate_report;
        SystemDeviceResult candidate_result;
        uint32_t capabilities = 0U;
        uint8_t instance_id;

        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        if (s_gnss.initialized[instance_id] == 0U) { continue; }
        (void)memset(&candidate_report, 0, sizeof(candidate_report));
        if ((ProjectGnssInstance_CapabilitiesGet(instance_id,
                &capabilities) == SYSTEM_DEVICE_OK) &&
            ((capabilities & SYSTEM_GNSS_CAP_READ_ONLY) != 0U))
        { candidate_result = SYSTEM_DEVICE_CONFIG_NO_ACTION; }
        else
        { candidate_result = ProjectGnssInstance_ConfigApply(instance_id,
            config, &candidate_report); }
        if (instance_id == s_gnss.active)
        {
            *report = candidate_report;
            active_result = candidate_result;
        }
    }
    return active_result;
}

SystemDeviceResult SystemGnss_ConfigVerify(const SystemGnssConfig *config,
                                            SystemDeviceConfigReport *report)
{
    SystemDeviceResult active_result = SYSTEM_DEVICE_NOT_READY;
    uint8_t position;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (position = 0U;
         position < PROJECT_GNSS_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceConfigReport candidate_report;
        SystemDeviceResult candidate_result;
        uint32_t capabilities = 0U;
        uint8_t instance_id;

        if (position >= s_gnss.count) { break; }
        instance_id = s_gnss.order[position];
        if (s_gnss.initialized[instance_id] == 0U) { continue; }
        (void)memset(&candidate_report, 0, sizeof(candidate_report));
        if ((ProjectGnssInstance_CapabilitiesGet(instance_id,
                &capabilities) == SYSTEM_DEVICE_OK) &&
            ((capabilities & SYSTEM_GNSS_CAP_READ_ONLY) != 0U))
        { candidate_result = SYSTEM_DEVICE_CONFIG_NO_ACTION; }
        else
        { candidate_result = ProjectGnssInstance_ConfigVerify(instance_id,
            config, &candidate_report); }
        if (instance_id == s_gnss.active)
        {
            *report = candidate_report;
            active_result = candidate_result;
        }
    }
    return active_result;
}

SystemDeviceResult SystemGnss_EffectiveConfigGet(SystemGnssConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_EffectiveConfigGet(s_gnss.active, config);
}

SystemDeviceResult SystemGnss_NoiseCharacteristicsGet(
    SystemGnssNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_NoiseCharacteristicsGet(s_gnss.active, noise);
}

SystemDeviceResult SystemGnss_HardwareConfigRead(
    SystemGnssHardwareConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_HardwareConfigRead(s_gnss.active, config);
}

SystemDeviceResult SystemGnss_LastConfigReportGet(
    SystemGnssConfigTransactionReport *report)
{
    if (report == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_LastConfigReportGet(s_gnss.active, report);
}

SystemDeviceResult SystemGnss_SatelliteDiagnosticsRead(
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_SatelliteDiagnosticsRead(
        s_gnss.active, diagnostics);
}

SystemDeviceResult SystemGnss_LatestSatelliteDiagnosticsGet(
    SystemGnssSatelliteDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_LatestSatelliteDiagnosticsGet(
        s_gnss.active, diagnostics);
}

SystemDeviceResult SystemGnss_RfDiagnosticsRead(
    SystemGnssRfDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_RfDiagnosticsRead(
        s_gnss.active, diagnostics);
}

SystemDeviceResult SystemGnss_LatestRfDiagnosticsGet(
    SystemGnssRfDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_gnss.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectGnssInstance_LatestRfDiagnosticsGet(
        s_gnss.active, diagnostics);
}

static void SystemSourceSelector_TelemetryBaselineSet(void)
{
    SystemTelemetryHealth health;

    s_telemetry.observed_transmit_count = 0U;
    s_telemetry.observed_timeout_count = 0U;
    if ((s_telemetry.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectTelemetryInstance_HealthGet(
             s_telemetry.active, &health) == SYSTEM_DEVICE_OK))
    {
        s_telemetry.observed_transmit_count = health.transmit_packet_count;
        s_telemetry.observed_timeout_count = health.transmit_timeout_count;
    }
}

typedef enum
{
    SystemSourceSelectorTelemetryCandidate_Failed = 0,
    SystemSourceSelectorTelemetryCandidate_Ready,
    SystemSourceSelectorTelemetryCandidate_Blocked
} SystemSourceSelectorTelemetryCandidateResult;

static SystemSourceSelectorTelemetryCandidateResult
SystemSourceSelector_TelemetryCandidateStart(uint8_t candidate)
{
    SystemDeviceResult result;
    if ((s_telemetry.started[candidate] != 0U) ||
        (s_telemetry.cleanup_pending[candidate] != 0U))
    {
        result = ProjectTelemetryInstance_Stop(candidate);
        if (SystemSourceSelector_ResultSuccessful(result) == 0U)
        { s_telemetry.cleanup_pending[candidate] = 1U;
          return SystemSourceSelectorTelemetryCandidate_Blocked; }
        s_telemetry.started[candidate] = 0U;
        s_telemetry.cleanup_pending[candidate] = 0U;
        s_telemetry.initialized[candidate] = 0U;
    }
    if (s_telemetry.initialized[candidate] == 0U)
    {
        result = ProjectTelemetryInstance_Init(candidate);
        if (SystemSourceSelector_ResultSuccessful(result) == 0U)
        { return SystemSourceSelectorTelemetryCandidate_Failed; }
        s_telemetry.initialized[candidate] = 1U;
    }
    result = ProjectTelemetryInstance_Start(candidate);
    SILVERSTAR_ASSERT((uint32_t)result <= (uint32_t)SYSTEM_DEVICE_NOT_PRESENT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (SystemSourceSelector_ResultSuccessful(result) == 0U)
    {
        s_telemetry.cleanup_pending[candidate] = 1U;
        if (SystemSourceSelector_ResultSuccessful(
                ProjectTelemetryInstance_Stop(candidate)) == 0U)
        { return SystemSourceSelectorTelemetryCandidate_Blocked; }
        s_telemetry.cleanup_pending[candidate] = 0U;
        s_telemetry.initialized[candidate] = 0U;
        return SystemSourceSelectorTelemetryCandidate_Failed;
    }
    s_telemetry.started[candidate] = 1U;
    return SystemSourceSelectorTelemetryCandidate_Ready;
}

static uint8_t SystemSourceSelector_TelemetryNextStart(uint8_t include_inactive_active)
{
    uint8_t step;

    SILVERSTAR_ASSERT(s_telemetry.count <= PROJECT_TELEMETRY_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        ((s_telemetry.active_position < s_telemetry.count) &&
         (s_telemetry.order[s_telemetry.active_position] == s_telemetry.active)),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (step = 0U; step < PROJECT_TELEMETRY_INSTANCE_COUNT_MAX; step++)
    {
        uint8_t position;
        uint8_t candidate;
        SystemSourceSelectorTelemetryCandidateResult result;
        if (step >= s_telemetry.count) { break; }
        position = s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE ?
            step : (uint8_t)((s_telemetry.active_position + step + 1U) % s_telemetry.count);
        candidate = s_telemetry.order[position];
        if (candidate >= PROJECT_TELEMETRY_INSTANCE_COUNT_MAX)
        {
            SILVERSTAR_ASSERT(candidate < PROJECT_TELEMETRY_INSTANCE_COUNT_MAX,
                SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
            return 0U;
        }
        SILVERSTAR_ASSERT(candidate < s_telemetry.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        if ((candidate == s_telemetry.active) &&
            (include_inactive_active == 0U)) { continue; }
        if ((s_telemetry.cooldown_active[candidate] != 0U) &&
            ((uint32_t)((uint32_t)(SystemTime_GetMonotonicUs() / 1000ULL) -
              s_telemetry.cooldown_scheduled_ms[candidate]) <
             SYSTEM_TELEMETRY_SWITCH_COOLDOWN_MS)) { continue; }
        result = SystemSourceSelector_TelemetryCandidateStart(candidate);
        if (result == SystemSourceSelectorTelemetryCandidate_Blocked)
        { return 0U; }
        if (result != SystemSourceSelectorTelemetryCandidate_Ready)
        { continue; }
        s_telemetry.active = candidate;
        s_telemetry.active_position = position;
        s_telemetry.active_offline = 0U;
        s_telemetry.consecutive_timeout_count = 0U;
        SystemSourceSelector_TelemetryBaselineSet();
        return 1U;
    }
    return 0U;
}

static void SystemSourceSelector_TelemetryQuarantine(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < s_telemetry.count,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    s_telemetry.cooldown_active[instance] = 1U;
    s_telemetry.cooldown_scheduled_ms[instance] =
        (uint32_t)(SystemTime_GetMonotonicUs() / 1000ULL);
}

static uint8_t SystemSourceSelector_TelemetryCleanupPending(void)
{
    uint8_t candidate;
    for (candidate = 0U; candidate < PROJECT_TELEMETRY_INSTANCE_COUNT_MAX;
         candidate++)
    {
        if (candidate >= s_telemetry.count) { break; }
        if (s_telemetry.cleanup_pending[candidate] != 0U) { return 1U; }
    }
    return 0U;
}

static void SystemSourceSelector_TelemetryCleanupFirstFailure(void)
{
    s_telemetry.recovery_scheduled_ms =
        (uint32_t)(SystemTime_GetMonotonicUs() / 1000ULL);
    s_telemetry.recovery_failures = 1U;
}

static void SystemSourceSelector_TelemetryCleanupTry(void)
{
    uint8_t position;
    for (position = 0U; position < PROJECT_TELEMETRY_INSTANCE_COUNT_MAX;
         position++)
    {
        uint8_t candidate;
        if (position >= s_telemetry.count) { break; }
        candidate = s_telemetry.order[position];
        if (candidate >= PROJECT_TELEMETRY_INSTANCE_COUNT_MAX)
        {
            SILVERSTAR_ASSERT(candidate < PROJECT_TELEMETRY_INSTANCE_COUNT_MAX,
                SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
            return;
        }
        SILVERSTAR_ASSERT(candidate < s_telemetry.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        if (s_telemetry.cleanup_pending[candidate] == 0U) { continue; }
        if (SystemSourceSelector_ResultSuccessful(
                ProjectTelemetryInstance_Stop(candidate)) == 0U)
        {
            if (s_telemetry.recovery_failures <
                SYSTEM_TELEMETRY_CLEANUP_BACKOFF_MAX)
            { s_telemetry.recovery_failures++; }
            return;
        }
        s_telemetry.cleanup_pending[candidate] = 0U;
        s_telemetry.started[candidate] = 0U;
        s_telemetry.initialized[candidate] = 0U;
        if (SystemSourceSelector_TelemetryCleanupPending() == 0U)
        {
            s_telemetry.recovery_failures = 0U;
            s_telemetry.recovery_scheduled_ms = 0U;
        }
        if ((candidate != s_telemetry.active) &&
            (s_telemetry.active_offline != 0U))
        {
            SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_TELEMETRY,
                candidate, s_telemetry.active,
                SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
            s_telemetry.active_offline = 0U;
        }
        return;
    }
}

static uint8_t SystemSourceSelector_TelemetryRecoveryTry(
    uint8_t include_inactive_active)
{
    uint32_t now_ms = (uint32_t)(SystemTime_GetMonotonicUs() / 1000ULL);
    uint8_t cleanup_pending = SystemSourceSelector_TelemetryCleanupPending();
    uint8_t backoff_shift = s_telemetry.recovery_failures;
    SILVERSTAR_ASSERT(backoff_shift <= SYSTEM_TELEMETRY_CLEANUP_BACKOFF_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((cleanup_pending != 0U) && (backoff_shift > 0U))
    { backoff_shift--; }
    if ((uint32_t)(now_ms - s_telemetry.recovery_scheduled_ms) <
        (SYSTEM_TELEMETRY_RECOVERY_DELAY_MS << backoff_shift))
    { return 0U; }
    s_telemetry.recovery_scheduled_ms = now_ms;
    if (cleanup_pending != 0U)
    {
        SystemSourceSelector_TelemetryCleanupTry();
        return 0U;
    }
    if (SystemSourceSelector_TelemetryNextStart(include_inactive_active) != 0U)
    {
        s_telemetry.recovery_failures = 0U;
        s_telemetry.recovery_scheduled_ms = 0U;
        return 1U;
    }
    if (s_telemetry.recovery_failures < SYSTEM_TELEMETRY_RECOVERY_BACKOFF_MAX)
    { s_telemetry.recovery_failures++; }
    return 0U;
}

static void SystemSourceSelector_TelemetrySwitchIfAvailable(
    SystemSourceChangeReason reason)
{
    uint8_t previous = s_telemetry.active;
    if (SystemSourceSelector_TelemetryRecoveryTry(0U) == 0U) { return; }
    if (SystemSourceSelector_ResultSuccessful(
            ProjectTelemetryInstance_Stop(previous)) == 0U)
    {
        s_telemetry.started[previous] = 0U;
        s_telemetry.cleanup_pending[previous] = 1U;
        s_telemetry.active_offline = 1U;
        SystemSourceSelector_TelemetryCleanupFirstFailure();
        return;
    }
    s_telemetry.started[previous] = 0U;
    SystemSourceSelector_TelemetryQuarantine(previous);
    SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_TELEMETRY,
        previous, s_telemetry.active, reason);
}

static void SystemSourceSelector_TelemetryTimeoutAccumulate(uint32_t timeout_delta)
{
    if (timeout_delta >=
        ((uint32_t)SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT -
         (uint32_t)s_telemetry.consecutive_timeout_count))
    {
        s_telemetry.consecutive_timeout_count =
            SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT;
    }
    else
    {
        s_telemetry.consecutive_timeout_count = (uint16_t)(
            (uint32_t)s_telemetry.consecutive_timeout_count + timeout_delta);
    }
}

static void SystemSourceSelector_TelemetryHealthProcess(void)
{
    SystemTelemetryHealth health;
    uint32_t success_delta;
    uint32_t timeout_delta;

    SILVERSTAR_ASSERT(s_telemetry.count <= PROJECT_TELEMETRY_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) { return; }
    SILVERSTAR_ASSERT(s_telemetry.active < s_telemetry.count,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_telemetry.consecutive_timeout_count <=
        SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((ProjectTelemetryInstance_HealthGet(
            s_telemetry.active, &health) != SYSTEM_DEVICE_OK) ||
        (health.initialized == 0U) || (health.started == 0U))
    {
        s_telemetry.active_offline = 1U;
        SystemSourceSelector_TelemetrySwitchIfAvailable(
            SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
        return;
    }
    if (s_telemetry.active_offline != 0U)
    {
        SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_TELEMETRY,
            s_telemetry.active, s_telemetry.active,
            SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
        s_telemetry.active_offline = 0U;
    }
    success_delta = health.transmit_packet_count -
                    s_telemetry.observed_transmit_count;
    timeout_delta = health.transmit_timeout_count -
                    s_telemetry.observed_timeout_count;
    s_telemetry.observed_transmit_count = health.transmit_packet_count;
    s_telemetry.observed_timeout_count = health.transmit_timeout_count;
    if (success_delta > 0U)
    {
        s_telemetry.consecutive_timeout_count = 0U;
        s_telemetry.recovery_failures = 0U;
        s_telemetry.recovery_scheduled_ms = 0U;
        s_telemetry.cooldown_active[s_telemetry.active] = 0U;
        return;
    }
    if (timeout_delta == 0U) { return; }
    SystemSourceSelector_TelemetryTimeoutAccumulate(timeout_delta);
    if (s_telemetry.consecutive_timeout_count >=
        SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT)
    { SystemSourceSelector_TelemetrySwitchIfAvailable(
        SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_CONSECUTIVE_TX_TIMEOUT); }
}

const char *SystemTelemetry_NameGet(void)
{
    SystemDeviceInfo info;

    if ((s_telemetry.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectTelemetryInstance_InfoGet(s_telemetry.active, &info) ==
         SYSTEM_DEVICE_OK) &&
        (info.device_name != NULL))
    {
        return info.device_name;
    }
    return "Telemetry";
}

SystemDeviceResult SystemTelemetry_Init(void)
{
    SystemDeviceResult first_failure = SYSTEM_DEVICE_NOT_PRESENT;
    uint8_t position;
    uint8_t success_count = 0U;

    if (SystemSourceSelector_TelemetryCleanupPending() != 0U)
    { return SYSTEM_DEVICE_BUSY; }
    (void)memset(&s_telemetry, 0, sizeof(s_telemetry));
    s_telemetry.active = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_telemetry.active_position = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_telemetry.configured_primary = SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE;
    s_telemetry.count = ProjectTelemetryInstance_CountGet();
    if (s_telemetry.count > PROJECT_TELEMETRY_INSTANCE_COUNT_MAX)
    { s_telemetry.count = 0U; return SYSTEM_DEVICE_INTERNAL_ERROR; }
    s_telemetry.count = SystemSourceSelector_OrderBuild(
        SYSTEM_DEVICE_CLASS_TELEMETRY, s_telemetry.count,
        PROJECT_TELEMETRY_INSTANCE_COUNT_MAX, s_telemetry.order);
    if (s_telemetry.count > 0U)
    { s_telemetry.configured_primary = s_telemetry.order[0]; }
    for (position = 0U;
         position < PROJECT_TELEMETRY_INSTANCE_COUNT_MAX;
         position++)
    {
        SystemDeviceResult result;
        uint8_t instance_id;

        if (position >= s_telemetry.count) { break; }
        instance_id = s_telemetry.order[position];
        SILVERSTAR_ASSERT(instance_id < s_telemetry.count,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
        result = ProjectTelemetryInstance_Init(instance_id);
        SILVERSTAR_ASSERT((uint32_t)result <= (uint32_t)SYSTEM_DEVICE_NOT_PRESENT,
            SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
        if (SystemSourceSelector_ResultSuccessful(result) != 0U)
        {
            s_telemetry.initialized[instance_id] = 1U;
            success_count++;
            if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
            {
                s_telemetry.active = instance_id;
                s_telemetry.active_position = position;
            }
        }
        else if (first_failure == SYSTEM_DEVICE_NOT_PRESENT)
        {
            first_failure = result;
        }
    }
    if ((s_telemetry.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (s_telemetry.active != s_telemetry.configured_primary))
    {
        SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_TELEMETRY,
            s_telemetry.configured_primary, s_telemetry.active,
            SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_INIT_FAILURE);
    }
    return (success_count > 0U) ? SYSTEM_DEVICE_OK : first_failure;
}

SystemDeviceResult SystemTelemetry_Start(void)
{
    uint8_t previous;
    SystemSourceSelectorTelemetryCandidateResult result;

    SILVERSTAR_ASSERT(s_telemetry.count <= PROJECT_TELEMETRY_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    s_telemetry.start_requested = 1U;
    if (SystemSourceSelector_TelemetryCleanupPending() != 0U)
    { return SYSTEM_DEVICE_BUSY; }
    if ((s_telemetry.count == 0U) || (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE))
    { return SYSTEM_DEVICE_NOT_READY; }
    SILVERSTAR_ASSERT(s_telemetry.active < s_telemetry.count,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    previous = s_telemetry.active;
    result = SystemSourceSelector_TelemetryCandidateStart(previous);
    if (result == SystemSourceSelectorTelemetryCandidate_Ready)
    {
        s_telemetry.consecutive_timeout_count = 0U;
        SystemSourceSelector_TelemetryBaselineSet();
        return SYSTEM_DEVICE_OK;
    }
    if (result == SystemSourceSelectorTelemetryCandidate_Blocked)
    { return SYSTEM_DEVICE_IO_ERROR; }
    if (SystemSourceSelector_TelemetryNextStart(0U) != 0U)
    {
        SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_TELEMETRY,
            previous, s_telemetry.active,
            SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_INIT_FAILURE);
        return SYSTEM_DEVICE_OK;
    }
    return SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemTelemetry_Stop(void)
{
    SystemDeviceResult result;
    uint8_t cleanup_was_pending =
        SystemSourceSelector_TelemetryCleanupPending();
    s_telemetry.start_requested = 0U;

    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    result = ProjectTelemetryInstance_Stop(s_telemetry.active);
    s_telemetry.started[s_telemetry.active] = 0U;
    s_telemetry.cleanup_pending[s_telemetry.active] =
        (uint8_t)(SystemSourceSelector_ResultSuccessful(result) == 0U);
    if ((s_telemetry.cleanup_pending[s_telemetry.active] != 0U) &&
        (cleanup_was_pending == 0U))
    { SystemSourceSelector_TelemetryCleanupFirstFailure(); }
    return result;
}

SystemDeviceResult SystemTelemetry_Send(
    const uint8_t *data, uint16_t length)
{
    if ((data == NULL) || (length == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        (s_telemetry.started[s_telemetry.active] == 0U) ||
        (SystemSourceSelector_TelemetryCleanupPending() != 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_Send(s_telemetry.active, data, length);
}

SystemDeviceResult SystemTelemetry_SendControl(
    const uint8_t *data, uint16_t length, uint32_t *transaction_id)
{
    if (transaction_id != NULL) { *transaction_id = 0U; }
    if ((data == NULL) || (length == 0U)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        (s_telemetry.started[s_telemetry.active] == 0U) ||
        (SystemSourceSelector_TelemetryCleanupPending() != 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_SendControl(s_telemetry.active, data, length, transaction_id);
}

SystemDeviceResult SystemTelemetry_TxResultGet(uint32_t transaction_id, uint32_t *age_ms)
{
    if ((transaction_id == 0U) || (age_ms == NULL)) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        (s_telemetry.started[s_telemetry.active] == 0U) ||
        (SystemSourceSelector_TelemetryCleanupPending() != 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_TxResultGet(s_telemetry.active, transaction_id, age_ms);
}

SystemDeviceResult SystemTelemetry_Receive(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{
    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        (s_telemetry.started[s_telemetry.active] == 0U) ||
        (SystemSourceSelector_TelemetryCleanupPending() != 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_Receive(
        s_telemetry.active, data, capacity, length);
}

void SystemTelemetry_Process(void)
{
    if (SystemSourceSelector_TelemetryCleanupPending() != 0U)
    {
        (void)SystemSourceSelector_TelemetryRecoveryTry(0U);
        SystemSourceSelector_PendingEventsFlush();
        return;
    }
    if ((s_telemetry.start_requested != 0U) &&
        ((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
         (s_telemetry.started[s_telemetry.active] == 0U)))
    {
        uint8_t previous = s_telemetry.active;
        if (SystemSourceSelector_TelemetryRecoveryTry(1U) != 0U)
        {
            SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_TELEMETRY,
                previous, s_telemetry.active,
                SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
        }
    }
    if ((s_telemetry.active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (s_telemetry.started[s_telemetry.active] != 0U) &&
        (s_telemetry.cleanup_pending[s_telemetry.active] == 0U))
    {
        (void)ProjectTelemetryInstance_Process(s_telemetry.active);
        SystemSourceSelector_TelemetryHealthProcess();
    }
    SystemSourceSelector_PendingEventsFlush();
}

SystemDeviceResult SystemTelemetry_InfoGet(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_InfoGet(s_telemetry.active, info);
}

SystemDeviceResult SystemTelemetry_CapabilitiesGet(uint32_t *capability_mask)
{
    if (capability_mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_CapabilitiesGet(
        s_telemetry.active, capability_mask);
}

SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) ||
        (SystemSourceSelector_TelemetryCleanupPending() != 0U))
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_HealthGet(s_telemetry.active, health);
}

SystemDeviceResult SystemTelemetry_IoDiagnosticsGet(
    SystemDeviceIoDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_IoDiagnosticsGet(
        s_telemetry.active, diagnostics);
}

SystemDeviceResult SystemTelemetry_SelfTestRun(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_SelfTestRun(s_telemetry.active, result);
}

SystemDeviceResult SystemTelemetry_MtuGet(uint16_t *mtu)
{
    if (mtu == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_telemetry.active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectTelemetryInstance_MtuGet(s_telemetry.active, mtu);
}

static SystemDeviceResult SystemSourceSelector_PassiveInit(
    SystemDeviceClass device_class)
{
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_PRESENT;
    uint8_t count = ProjectDeviceInstance_CountGet(device_class);
    uint8_t instance_id;
    uint8_t success_count = 0U;

    SILVERSTAR_ASSERT((device_class == SYSTEM_DEVICE_CLASS_BAROMETER) ||
                      (device_class == SYSTEM_DEVICE_CLASS_MAGNETOMETER) ||
                      (device_class ==
                       SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U;
         instance_id < PROJECT_IMU_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        SystemDeviceResult candidate_result = SYSTEM_DEVICE_UNSUPPORTED;

        if (instance_id >= count) { break; }
        switch (device_class)
        {
            case SYSTEM_DEVICE_CLASS_BAROMETER:
                candidate_result = ProjectBarometerInstance_Init(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
                candidate_result = ProjectMagnetometerInstance_Init(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
                candidate_result = ProjectAttitudeInstance_Init(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_IMU:
            case SYSTEM_DEVICE_CLASS_GNSS:
            case SYSTEM_DEVICE_CLASS_TELEMETRY:
            case SYSTEM_DEVICE_CLASS_CONSOLE:
            case SYSTEM_DEVICE_CLASS_POWER:
            case SYSTEM_DEVICE_CLASS_STORAGE:
            case SYSTEM_DEVICE_CLASS_LOG_SINK:
            case SYSTEM_DEVICE_CLASS_OUTPUT:
            case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
            case SYSTEM_DEVICE_CLASS_TIME:
            default:
                break;
        }
        if (SystemSourceSelector_ResultSuccessful(candidate_result) != 0U)
        {
            success_count++;
            result = SYSTEM_DEVICE_OK;
        }
        else if (success_count == 0U)
        {
            result = candidate_result;
        }
    }
    return result;
}

static SystemDeviceResult SystemSourceSelector_PassiveStart(
    SystemDeviceClass device_class)
{
    SystemDeviceResult result = SYSTEM_DEVICE_NOT_PRESENT;
    uint8_t count = ProjectDeviceInstance_CountGet(device_class);
    uint8_t instance_id;
    uint8_t success_count = 0U;

    SILVERSTAR_ASSERT((device_class == SYSTEM_DEVICE_CLASS_BAROMETER) ||
                      (device_class == SYSTEM_DEVICE_CLASS_MAGNETOMETER) ||
                      (device_class ==
                       SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U;
         instance_id < PROJECT_IMU_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        SystemDeviceResult candidate_result = SYSTEM_DEVICE_UNSUPPORTED;

        if (instance_id >= count) { break; }
        switch (device_class)
        {
            case SYSTEM_DEVICE_CLASS_BAROMETER:
                candidate_result = ProjectBarometerInstance_Start(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
                candidate_result = ProjectMagnetometerInstance_Start(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
                candidate_result = ProjectAttitudeInstance_Start(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_IMU:
            case SYSTEM_DEVICE_CLASS_GNSS:
            case SYSTEM_DEVICE_CLASS_TELEMETRY:
            case SYSTEM_DEVICE_CLASS_CONSOLE:
            case SYSTEM_DEVICE_CLASS_POWER:
            case SYSTEM_DEVICE_CLASS_STORAGE:
            case SYSTEM_DEVICE_CLASS_LOG_SINK:
            case SYSTEM_DEVICE_CLASS_OUTPUT:
            case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
            case SYSTEM_DEVICE_CLASS_TIME:
            default:
                break;
        }
        if (SystemSourceSelector_ResultSuccessful(candidate_result) != 0U)
        {
            success_count++;
            result = SYSTEM_DEVICE_OK;
        }
        else if (success_count == 0U)
        {
            result = candidate_result;
        }
    }
    return result;
}

static SystemDeviceResult SystemSourceSelector_PassiveStop(
    SystemDeviceClass device_class)
{
    SystemDeviceResult result = SYSTEM_DEVICE_OK;
    uint8_t count = ProjectDeviceInstance_CountGet(device_class);
    uint8_t instance_id;

    SILVERSTAR_ASSERT((device_class == SYSTEM_DEVICE_CLASS_BAROMETER) ||
                      (device_class == SYSTEM_DEVICE_CLASS_MAGNETOMETER) ||
                      (device_class ==
                       SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION),
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
                      SILVERSTAR_ASSERT_MODULE_SYSTEM,
                      SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U;
         instance_id < PROJECT_IMU_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        SystemDeviceResult candidate_result = SYSTEM_DEVICE_UNSUPPORTED;

        if (instance_id >= count) { break; }
        switch (device_class)
        {
            case SYSTEM_DEVICE_CLASS_BAROMETER:
                candidate_result = ProjectBarometerInstance_Stop(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
                candidate_result = ProjectMagnetometerInstance_Stop(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION:
                candidate_result = ProjectAttitudeInstance_Stop(instance_id);
                break;
            case SYSTEM_DEVICE_CLASS_IMU:
            case SYSTEM_DEVICE_CLASS_GNSS:
            case SYSTEM_DEVICE_CLASS_TELEMETRY:
            case SYSTEM_DEVICE_CLASS_CONSOLE:
            case SYSTEM_DEVICE_CLASS_POWER:
            case SYSTEM_DEVICE_CLASS_STORAGE:
            case SYSTEM_DEVICE_CLASS_LOG_SINK:
            case SYSTEM_DEVICE_CLASS_OUTPUT:
            case SYSTEM_DEVICE_CLASS_MISSION_ACTION:
            case SYSTEM_DEVICE_CLASS_TIME:
            default:
                break;
        }
        if ((candidate_result != SYSTEM_DEVICE_OK) &&
            (candidate_result != SYSTEM_DEVICE_NOT_READY))
        {
            result = candidate_result;
        }
    }
    return result;
}

static void SystemSourceSelector_PassiveProcess(SystemDeviceClass device_class)
{
    uint8_t count = ProjectDeviceInstance_CountGet(device_class);
    uint8_t instance_id;
    SILVERSTAR_ASSERT(count <= PROJECT_IMU_INSTANCE_COUNT_MAX,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (instance_id = 0U; instance_id < PROJECT_IMU_INSTANCE_COUNT_MAX;
         instance_id++)
    {
        if (instance_id >= count) { break; }
        if (device_class == SYSTEM_DEVICE_CLASS_BAROMETER)
        { (void)ProjectBarometerInstance_Process(instance_id); }
        else if (device_class == SYSTEM_DEVICE_CLASS_MAGNETOMETER)
        { (void)ProjectMagnetometerInstance_Process(instance_id); }
    }
}

const char *SystemBarometer_NameGet(void)
{
    SystemDeviceInfo info;
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if ((active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectBarometerInstance_InfoGet(active, &info) == SYSTEM_DEVICE_OK) &&
        (info.device_name != NULL)) { return info.device_name; }
    return "Barometer";
}

SystemDeviceResult SystemBarometer_Init(void)
{
    if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U) { return SystemBarometerCold_Init(); }
    return SystemSourceSelector_PassiveInit(SYSTEM_DEVICE_CLASS_BAROMETER);
}
SystemDeviceResult SystemBarometer_Start(void)
{
    if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U) { return SystemBarometerCold_Start(); }
    return SystemSourceSelector_PassiveStart(SYSTEM_DEVICE_CLASS_BAROMETER);
}
SystemDeviceResult SystemBarometer_Stop(void)
{
    if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U) { return SystemBarometerCold_Stop(); }
    return SystemSourceSelector_PassiveStop(SYSTEM_DEVICE_CLASS_BAROMETER);
}
SystemDeviceResult SystemBarometer_Process(void)
{
    if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U)
    {
        uint8_t previous = SystemBarometerCold_ActiveGet();
        SystemDeviceResult result = SystemBarometerCold_Process();
        uint8_t active = SystemBarometerCold_ActiveGet();
        if (active != previous)
        {
            SystemSourceSelector_EventRecord(SYSTEM_DEVICE_CLASS_BAROMETER,
                previous, active, SYSTEM_SOURCE_CHANGE_REASON_RECOVERY);
        }
        SystemSourceSelector_PendingEventsFlush();
        return result;
    }
    SystemSourceSelector_PassiveProcess(SYSTEM_DEVICE_CLASS_BAROMETER);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemBarometer_InfoGet(SystemDeviceInfo *info)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_InfoGet(active, info);
}

SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *mask)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_CapabilitiesGet(active, mask);
}

SystemDeviceResult SystemBarometer_HealthGet(SystemDeviceHealth *health)
{
    if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U) { return SystemBarometerCold_HealthGet(health); }
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_HealthGet(active, health);
}

SystemDeviceResult SystemBarometer_LatestSampleGet(SystemBarometerSample *sample)
{
    if (SYSTEM_BUILD_BAROMETER_COLD_ENABLED != 0U) { return SystemBarometerCold_SampleGet(sample); }
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_LatestSampleGet(active, sample);
}

SystemDeviceResult SystemBarometer_SelfTestRun(SystemDeviceSelfTestResult *result)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_SelfTestRun(active, result);
}

SystemDeviceResult SystemBarometer_ConfigApply(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_ConfigApply(active, config, report);
}

SystemDeviceResult SystemBarometer_ConfigVerify(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_ConfigVerify(active, config, report);
}

SystemDeviceResult SystemBarometer_EffectiveConfigGet(
    SystemBarometerConfig *config)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_EffectiveConfigGet(active, config);
}

SystemDeviceResult SystemBarometer_NoiseCharacteristicsGet(
    SystemBarometerNoiseCharacteristics *noise)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_BAROMETER);
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectBarometerInstance_NoiseCharacteristicsGet(active, noise);
}

const char *SystemMagnetometer_NameGet(void)
{
    SystemDeviceInfo info;
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if ((active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectMagnetometerInstance_InfoGet(active, &info) == SYSTEM_DEVICE_OK) &&
        (info.device_name != NULL)) { return info.device_name; }
    return "Magnetometer";
}

SystemDeviceResult SystemMagnetometer_Init(void)
{ return SystemSourceSelector_PassiveInit(SYSTEM_DEVICE_CLASS_MAGNETOMETER); }
SystemDeviceResult SystemMagnetometer_Start(void)
{ return SystemSourceSelector_PassiveStart(SYSTEM_DEVICE_CLASS_MAGNETOMETER); }
SystemDeviceResult SystemMagnetometer_Stop(void)
{ return SystemSourceSelector_PassiveStop(SYSTEM_DEVICE_CLASS_MAGNETOMETER); }
SystemDeviceResult SystemMagnetometer_Process(void)
{
    SystemSourceSelector_PassiveProcess(SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemMagnetometer_InfoGet(SystemDeviceInfo *info)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_InfoGet(active, info);
}

SystemDeviceResult SystemMagnetometer_CapabilitiesGet(uint32_t *mask)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_CapabilitiesGet(active, mask);
}

SystemDeviceResult SystemMagnetometer_HealthGet(SystemDeviceHealth *health)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_HealthGet(active, health);
}

SystemDeviceResult SystemMagnetometer_LatestSampleGet(
    SystemMagnetometerSample *sample)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    SystemDeviceDescriptor descriptor;
    SystemDeviceResult result;
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    result = ProjectMagnetometerInstance_LatestSampleGet(active, sample);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    result = ProjectDeviceInstance_DescriptorGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER, active, &descriptor);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemMagnetometerSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT_OBJECT(&descriptor, SystemDeviceDescriptor,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    sample->physical_device_id = descriptor.physical_device_id;
    sample->descriptor_id = descriptor.descriptor_id;
    sample->instance_id = active;
    {
        SystemMagCalibrationResult calibration_result =
            SystemMagCalibration_SampleApply(active, sample);
        if ((calibration_result != SystemMagCalibrationResult_Ok) &&
            (calibration_result != SystemMagCalibrationResult_NotReady))
        {
            sample->calibration_valid = 0U;
            sample->valid_mask &= ~SYSTEM_MAG_VALID_CALIBRATED;
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemMagnetometer_SelfTestRun(
    SystemDeviceSelfTestResult *result)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_SelfTestRun(active, result);
}

SystemDeviceResult SystemMagnetometer_ConfigApply(
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_ConfigApply(active, config, report);
}

SystemDeviceResult SystemMagnetometer_ConfigVerify(
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_ConfigVerify(active, config, report);
}

SystemDeviceResult SystemMagnetometer_EffectiveConfigGet(
    SystemMagnetometerConfig *config)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_MAGNETOMETER);
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectMagnetometerInstance_EffectiveConfigGet(active, config);
}

const char *SystemHardwareQuaternion_NameGet(void)
{
    SystemDeviceInfo info;
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if ((active != SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE) &&
        (ProjectAttitudeInstance_InfoGet(active, &info) == SYSTEM_DEVICE_OK) &&
        (info.device_name != NULL)) { return info.device_name; }
    return "Hardware Quaternion";
}

SystemDeviceResult SystemHardwareQuaternion_Init(void)
{
    return SystemSourceSelector_PassiveInit(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
}
SystemDeviceResult SystemHardwareQuaternion_Start(void)
{
    return SystemSourceSelector_PassiveStart(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
}
SystemDeviceResult SystemHardwareQuaternion_Stop(void)
{
    return SystemSourceSelector_PassiveStop(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
}
void SystemHardwareQuaternion_Process(void) { }

SystemDeviceResult SystemHardwareQuaternion_InfoGet(SystemDeviceInfo *info)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_InfoGet(active, info);
}

SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(uint32_t *mask)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_CapabilitiesGet(active, mask);
}

SystemDeviceResult SystemHardwareQuaternion_HealthGet(
    SystemDeviceHealth *health)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_HealthGet(active, health);
}

SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_LatestSampleGet(active, sample);
}

SystemDeviceResult SystemHardwareQuaternion_SelfTestRun(
    SystemDeviceSelfTestResult *result)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_SelfTestRun(active, result);
}

SystemDeviceResult SystemHardwareQuaternion_ConfigApply(
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_ConfigApply(active, config, report);
}

SystemDeviceResult SystemHardwareQuaternion_ConfigVerify(
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_ConfigVerify(active, config, report);
}

SystemDeviceResult SystemHardwareQuaternion_EffectiveConfigGet(
    SystemHardwareQuaternionConfig *config)
{
    uint8_t active = SystemSourceSelector_CompanionActiveGet(
        SYSTEM_DEVICE_CLASS_HARDWARE_QUATERNION);
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (active == SYSTEM_SOURCE_SELECTOR_INSTANCE_NONE)
    { return SYSTEM_DEVICE_NOT_READY; }
    return ProjectAttitudeInstance_EffectiveConfigGet(active, config);
}
