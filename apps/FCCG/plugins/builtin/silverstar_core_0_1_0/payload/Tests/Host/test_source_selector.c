#include <math.h>
#include <stdint.h>
#include <string.h>

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "platform_critical.h"
#include "project_device_instances.h"
#include "system_gnss_if.h"
#include "system_imu_if.h"
#include "system_mag_calibration.h"
#include "system_source_selector.h"
#include "system_telemetry_transport_if.h"
#include "system_time.h"
#include "test_common.h"

#define TEST_INSTANCE_COUNT 3U
#define TEST_EVENT_COUNT_MAX 32U

SystemMagCalibrationResult SystemMagCalibration_SampleApply(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    (void)instance_id;
    (void)sample;
    return SystemMagCalibrationResult_NotReady;
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
typedef struct
{
    FlightLogEventId event_id;
    uint32_t arg0;
    uint32_t arg1;
} TestEvent;
#endif

static uint8_t s_imu_count = TEST_INSTANCE_COUNT;
static uint8_t s_gnss_count = TEST_INSTANCE_COUNT;
static uint8_t s_telemetry_count = TEST_INSTANCE_COUNT;
static uint8_t s_magnetometer_count = 1U;
static uint8_t s_primary_imu;
static uint8_t s_primary_gnss;
static uint8_t s_primary_telemetry;
static uint64_t s_now_us = 1000000ULL;

static SystemDeviceResult s_imu_init_result[TEST_INSTANCE_COUNT];
static SystemDeviceResult s_imu_start_result[TEST_INSTANCE_COUNT];
static SystemDeviceHealth s_imu_health[TEST_INSTANCE_COUNT];
static SystemImuSample s_imu_sample[TEST_INSTANCE_COUNT];
static uint32_t s_imu_init_count[TEST_INSTANCE_COUNT];
static uint32_t s_imu_start_count[TEST_INSTANCE_COUNT];
static uint32_t s_imu_process_count[TEST_INSTANCE_COUNT];

static SystemDeviceResult s_gnss_init_result[TEST_INSTANCE_COUNT];
static SystemDeviceResult s_gnss_start_result[TEST_INSTANCE_COUNT];
static SystemDeviceHealth s_gnss_health[TEST_INSTANCE_COUNT];
static SystemGnssSample s_gnss_sample[TEST_INSTANCE_COUNT];
static uint32_t s_gnss_init_count[TEST_INSTANCE_COUNT];
static uint32_t s_gnss_start_count[TEST_INSTANCE_COUNT];
static uint32_t s_gnss_process_count[TEST_INSTANCE_COUNT];
static uint32_t s_gnss_capabilities[TEST_INSTANCE_COUNT];
static uint32_t s_gnss_apply_count[TEST_INSTANCE_COUNT];
static uint32_t s_gnss_verify_count[TEST_INSTANCE_COUNT];

static SystemDeviceResult s_telemetry_init_result[TEST_INSTANCE_COUNT];
static SystemDeviceResult s_telemetry_start_result[TEST_INSTANCE_COUNT];
static SystemDeviceResult s_telemetry_send_result[TEST_INSTANCE_COUNT];
static SystemTelemetryHealth s_telemetry_health[TEST_INSTANCE_COUNT];
static uint32_t s_telemetry_init_count[TEST_INSTANCE_COUNT];
static uint32_t s_telemetry_start_count[TEST_INSTANCE_COUNT];
static uint32_t s_telemetry_stop_count[TEST_INSTANCE_COUNT];
static uint32_t s_telemetry_send_count[TEST_INSTANCE_COUNT];
static uint32_t s_telemetry_receive_count[TEST_INSTANCE_COUNT];
static uint32_t s_telemetry_process_count[TEST_INSTANCE_COUNT];
static SystemMagnetometerSample s_magnetometer_sample;

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static TestEvent s_events[TEST_EVENT_COUNT_MAX];
#endif
static uint8_t s_event_count;

static void Test_StateReset(void)
{
    uint8_t instance;

    s_imu_count = TEST_INSTANCE_COUNT;
    s_gnss_count = TEST_INSTANCE_COUNT;
    s_telemetry_count = TEST_INSTANCE_COUNT;
    s_magnetometer_count = 1U;
    s_primary_imu = 0U;
    s_primary_gnss = 0U;
    s_primary_telemetry = 0U;
    s_now_us = 1000000ULL;
    (void)memset(s_imu_health, 0, sizeof(s_imu_health));
    (void)memset(s_imu_sample, 0, sizeof(s_imu_sample));
    (void)memset(s_imu_init_count, 0, sizeof(s_imu_init_count));
    (void)memset(s_imu_start_count, 0, sizeof(s_imu_start_count));
    (void)memset(s_imu_process_count, 0, sizeof(s_imu_process_count));
    (void)memset(s_gnss_health, 0, sizeof(s_gnss_health));
    (void)memset(s_gnss_sample, 0, sizeof(s_gnss_sample));
    (void)memset(s_gnss_init_count, 0, sizeof(s_gnss_init_count));
    (void)memset(s_gnss_start_count, 0, sizeof(s_gnss_start_count));
    (void)memset(s_gnss_process_count, 0, sizeof(s_gnss_process_count));
    (void)memset(s_gnss_capabilities, 0, sizeof(s_gnss_capabilities));
    (void)memset(s_gnss_apply_count, 0, sizeof(s_gnss_apply_count));
    (void)memset(s_gnss_verify_count, 0, sizeof(s_gnss_verify_count));
    (void)memset(s_telemetry_health, 0, sizeof(s_telemetry_health));
    (void)memset(&s_magnetometer_sample, 0, sizeof(s_magnetometer_sample));
    (void)memset(s_telemetry_init_count, 0,
                 sizeof(s_telemetry_init_count));
    (void)memset(s_telemetry_start_count, 0,
                 sizeof(s_telemetry_start_count));
    (void)memset(s_telemetry_stop_count, 0,
                 sizeof(s_telemetry_stop_count));
    (void)memset(s_telemetry_send_count, 0,
                 sizeof(s_telemetry_send_count));
    (void)memset(s_telemetry_receive_count, 0,
                 sizeof(s_telemetry_receive_count));
    (void)memset(s_telemetry_process_count, 0,
                 sizeof(s_telemetry_process_count));
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    (void)memset(s_events, 0, sizeof(s_events));
#endif
    s_event_count = 0U;
    for (instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    {
        uint8_t axis;

        s_imu_init_result[instance] = SYSTEM_DEVICE_OK;
        s_imu_start_result[instance] = SYSTEM_DEVICE_OK;
        s_imu_health[instance].initialized = 1U;
        s_imu_health[instance].started = 1U;
        s_imu_health[instance].online = 1U;
        s_imu_health[instance].healthy = 1U;
        s_imu_sample[instance].receive_timestamp_us = s_now_us;
        s_imu_sample[instance].valid_mask =
            SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO;
        for (axis = 0U; axis < 3U; axis++)
        {
            s_imu_sample[instance].accel_b_mps2[axis] =
                (float)(instance + 1U);
            s_imu_sample[instance].gyro_b_radps[axis] =
                (float)(instance + 1U) * 0.1f;
        }

        s_gnss_init_result[instance] = SYSTEM_DEVICE_OK;
        s_gnss_start_result[instance] = SYSTEM_DEVICE_OK;
        s_gnss_health[instance].initialized = 1U;
        s_gnss_health[instance].started = 1U;
        s_gnss_health[instance].online = 1U;
        s_gnss_health[instance].healthy = 1U;
        s_gnss_sample[instance].online = 1U;
        s_gnss_sample[instance].fix_ok = 1U;
        s_gnss_sample[instance].fix_type = 3U;

        s_telemetry_init_result[instance] = SYSTEM_DEVICE_OK;
        s_telemetry_start_result[instance] = SYSTEM_DEVICE_OK;
        s_telemetry_send_result[instance] = SYSTEM_DEVICE_OK;
        s_telemetry_health[instance].initialized = 1U;
        s_telemetry_health[instance].healthy = 1U;
    }
}

static uint8_t Test_PrimaryGet(SystemDeviceClass device_class)
{
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU: return s_primary_imu;
        case SYSTEM_DEVICE_CLASS_GNSS: return s_primary_gnss;
        case SYSTEM_DEVICE_CLASS_TELEMETRY: return s_primary_telemetry;
        default: return 0U;
    }
}

uint8_t ProjectDeviceInstance_CountGet(SystemDeviceClass device_class)
{
    switch (device_class)
    {
        case SYSTEM_DEVICE_CLASS_IMU: return s_imu_count;
        case SYSTEM_DEVICE_CLASS_GNSS: return s_gnss_count;
        case SYSTEM_DEVICE_CLASS_TELEMETRY: return s_telemetry_count;
        case SYSTEM_DEVICE_CLASS_MAGNETOMETER:
            return s_magnetometer_count;
        default: return 0U;
    }
}

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    uint8_t count = ProjectDeviceInstance_CountGet(device_class);

    if (descriptor == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (instance_id >= count) { return SYSTEM_DEVICE_NOT_PRESENT; }
    (void)memset(descriptor, 0, sizeof(*descriptor));
    descriptor->descriptor_id = (uint16_t)(
        ((uint16_t)device_class * 16U) + instance_id + 1U);
    descriptor->physical_device_id = (uint16_t)(
        ((uint16_t)device_class * 16U) + instance_id + 1U);
    descriptor->device_class = device_class;
    descriptor->instance_id = instance_id;
    descriptor->flags = SYSTEM_DESCRIPTOR_FLAG_ENABLED;
    if (instance_id == Test_PrimaryGet(device_class))
    { descriptor->flags |= SYSTEM_DESCRIPTOR_FLAG_PRIMARY; }
    return SYSTEM_DEVICE_OK;
}

uint8_t ProjectImuInstance_CountGet(void) { return s_imu_count; }
SystemDeviceResult ProjectImuInstance_Init(uint8_t instance_id)
{
    s_imu_init_count[instance_id]++;
    return s_imu_init_result[instance_id];
}
SystemDeviceResult ProjectImuInstance_Start(uint8_t instance_id)
{
    s_imu_start_count[instance_id]++;
    return s_imu_start_result[instance_id];
}
SystemDeviceResult ProjectImuInstance_Process(uint8_t instance_id)
{
    s_imu_process_count[instance_id]++;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectImuInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if ((instance_id >= s_imu_count) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_imu_health[instance_id];
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectImuInstance_LatestSampleGet(
    uint8_t instance_id, SystemImuSample *sample)
{
    if ((instance_id >= s_imu_count) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_imu_sample[instance_id];
    return SYSTEM_DEVICE_OK;
}

#define TEST_STUB_NO_OUTPUT(name) \
    SystemDeviceResult name(uint8_t instance_id) \
    { (void)instance_id; return SYSTEM_DEVICE_NOT_PRESENT; }
#define TEST_STUB_OUTPUT(name, value_type) \
    SystemDeviceResult name(uint8_t instance_id, value_type *value) \
    { \
        (void)instance_id; \
        (void)value; \
        return SYSTEM_DEVICE_NOT_PRESENT; \
    }
#define TEST_STUB_CONFIG(name, config_type) \
    SystemDeviceResult name( \
        uint8_t instance_id, const config_type *config, \
        SystemDeviceConfigReport *report) \
    { \
        (void)instance_id; \
        (void)config; \
        (void)report; \
        return SYSTEM_DEVICE_NOT_PRESENT; \
    }

TEST_STUB_NO_OUTPUT(ProjectImuInstance_Stop)
TEST_STUB_NO_OUTPUT(ProjectImuInstance_RuntimeOwnerActivate)
TEST_STUB_OUTPUT(ProjectImuInstance_InfoGet, SystemDeviceInfo)
TEST_STUB_OUTPUT(ProjectImuInstance_CapabilitiesGet, uint32_t)
TEST_STUB_OUTPUT(ProjectImuInstance_IoDiagnosticsGet,
                 SystemDeviceIoDiagnostics)
TEST_STUB_OUTPUT(ProjectImuInstance_IoDetailGet, SystemImuIoDetail)
TEST_STUB_OUTPUT(ProjectImuInstance_NextSampleGet, SystemImuSample)
TEST_STUB_OUTPUT(ProjectImuInstance_SelfTestRun,
                 SystemDeviceSelfTestResult)
TEST_STUB_CONFIG(ProjectImuInstance_ConfigApply, SystemImuConfig)
TEST_STUB_CONFIG(ProjectImuInstance_ConfigVerify, SystemImuConfig)
TEST_STUB_OUTPUT(ProjectImuInstance_EffectiveConfigGet, SystemImuConfig)
TEST_STUB_OUTPUT(ProjectImuInstance_NoiseCharacteristicsGet,
                 SystemImuNoiseCharacteristics)

uint8_t ProjectGnssInstance_CountGet(void) { return s_gnss_count; }
SystemDeviceResult ProjectGnssInstance_Init(uint8_t instance_id)
{
    s_gnss_init_count[instance_id]++;
    return s_gnss_init_result[instance_id];
}
SystemDeviceResult ProjectGnssInstance_Start(uint8_t instance_id)
{
    s_gnss_start_count[instance_id]++;
    return s_gnss_start_result[instance_id];
}
SystemDeviceResult ProjectGnssInstance_Process(uint8_t instance_id)
{
    s_gnss_process_count[instance_id]++;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectGnssInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if ((instance_id >= s_gnss_count) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_gnss_health[instance_id];
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectGnssInstance_LatestSampleGet(
    uint8_t instance_id, SystemGnssSample *sample)
{
    if ((instance_id >= s_gnss_count) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_gnss_sample[instance_id];
    return SYSTEM_DEVICE_OK;
}

TEST_STUB_NO_OUTPUT(ProjectGnssInstance_Stop)
TEST_STUB_NO_OUTPUT(ProjectGnssInstance_RuntimeOwnerActivate)
TEST_STUB_OUTPUT(ProjectGnssInstance_InfoGet, SystemDeviceInfo)
SystemDeviceResult ProjectGnssInstance_CapabilitiesGet(uint8_t instance_id,
    uint32_t *capability_mask)
{
    if ((instance_id >= s_gnss_count) || (capability_mask == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *capability_mask = s_gnss_capabilities[instance_id];
    return SYSTEM_DEVICE_OK;
}
TEST_STUB_OUTPUT(ProjectGnssInstance_IoDiagnosticsGet,
                 SystemDeviceIoDiagnostics)
TEST_STUB_OUTPUT(ProjectGnssInstance_IoDetailGet, SystemGnssIoDetail)
TEST_STUB_OUTPUT(ProjectGnssInstance_TimeGet, SystemGnssTime)
TEST_STUB_OUTPUT(ProjectGnssInstance_SelfTestRun,
                 SystemDeviceSelfTestResult)
SystemDeviceResult ProjectGnssInstance_ConfigApply(uint8_t instance_id,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if ((instance_id >= s_gnss_count) || (config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_gnss_apply_count[instance_id]++;
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->supported_mask = config->requested_mask;
    report->applied_mask = config->requested_mask;
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectGnssInstance_ConfigVerify(uint8_t instance_id,
    const SystemGnssConfig *config, SystemDeviceConfigReport *report)
{
    if ((instance_id >= s_gnss_count) || (config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_gnss_verify_count[instance_id]++;
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->supported_mask = config->requested_mask;
    report->matched_mask = config->requested_mask;
    report->success = 1U;
    return SYSTEM_DEVICE_OK;
}
TEST_STUB_OUTPUT(ProjectGnssInstance_EffectiveConfigGet, SystemGnssConfig)
TEST_STUB_OUTPUT(ProjectGnssInstance_NoiseCharacteristicsGet,
                 SystemGnssNoiseCharacteristics)
TEST_STUB_OUTPUT(ProjectGnssInstance_HardwareConfigRead,
                 SystemGnssHardwareConfig)
TEST_STUB_OUTPUT(ProjectGnssInstance_LastConfigReportGet,
                 SystemGnssConfigTransactionReport)
TEST_STUB_OUTPUT(ProjectGnssInstance_SatelliteDiagnosticsRead,
                 SystemGnssSatelliteDiagnostics)
TEST_STUB_OUTPUT(ProjectGnssInstance_LatestSatelliteDiagnosticsGet,
                 SystemGnssSatelliteDiagnostics)
TEST_STUB_OUTPUT(ProjectGnssInstance_RfDiagnosticsRead,
                 SystemGnssRfDiagnostics)
TEST_STUB_OUTPUT(ProjectGnssInstance_LatestRfDiagnosticsGet,
                 SystemGnssRfDiagnostics)

uint8_t ProjectTelemetryInstance_CountGet(void)
{ return s_telemetry_count; }
SystemDeviceResult ProjectTelemetryInstance_Init(uint8_t instance_id)
{
    s_telemetry_init_count[instance_id]++;
    if (s_telemetry_init_result[instance_id] == SYSTEM_DEVICE_OK)
    { s_telemetry_health[instance_id].initialized = 1U; }
    return s_telemetry_init_result[instance_id];
}
SystemDeviceResult ProjectTelemetryInstance_Start(uint8_t instance_id)
{
    s_telemetry_start_count[instance_id]++;
    if (s_telemetry_start_result[instance_id] == SYSTEM_DEVICE_OK)
    { s_telemetry_health[instance_id].started = 1U; }
    return s_telemetry_start_result[instance_id];
}
SystemDeviceResult ProjectTelemetryInstance_Stop(uint8_t instance_id)
{
    s_telemetry_stop_count[instance_id]++;
    s_telemetry_health[instance_id].started = 0U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectTelemetryInstance_Send(
    uint8_t instance_id, const uint8_t *data, uint16_t length)
{
    SystemDeviceResult result;

    if ((data == NULL) || (length == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_telemetry_send_count[instance_id]++;
    result = s_telemetry_send_result[instance_id];
    if (result == SYSTEM_DEVICE_OK)
    { s_telemetry_health[instance_id].transmit_packet_count++; }
    else if (result == SYSTEM_DEVICE_TIMEOUT)
    { s_telemetry_health[instance_id].transmit_timeout_count++; }
    return result;
}
SystemDeviceResult ProjectTelemetryInstance_Receive(
    uint8_t instance_id, uint8_t *data, uint16_t capacity,
    uint16_t *length)
{
    if ((data == NULL) || (length == NULL) || (capacity == 0U))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_telemetry_receive_count[instance_id]++;
    *length = 0U;
    return SYSTEM_DEVICE_NOT_READY;
}
SystemDeviceResult ProjectTelemetryInstance_Process(uint8_t instance_id)
{
    s_telemetry_process_count[instance_id]++;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult ProjectTelemetryInstance_HealthGet(
    uint8_t instance_id, SystemTelemetryHealth *health)
{
    if ((instance_id >= s_telemetry_count) || (health == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *health = s_telemetry_health[instance_id];
    return SYSTEM_DEVICE_OK;
}

TEST_STUB_OUTPUT(ProjectTelemetryInstance_InfoGet, SystemDeviceInfo)
TEST_STUB_OUTPUT(ProjectTelemetryInstance_CapabilitiesGet, uint32_t)
TEST_STUB_OUTPUT(ProjectTelemetryInstance_IoDiagnosticsGet,
                 SystemDeviceIoDiagnostics)
TEST_STUB_OUTPUT(ProjectTelemetryInstance_SelfTestRun,
                 SystemDeviceSelfTestResult)
TEST_STUB_OUTPUT(ProjectTelemetryInstance_MtuGet, uint16_t)

#define TEST_PASSIVE_STUBS(prefix, sample_type, config_type) \
    TEST_STUB_NO_OUTPUT(prefix ## _Init) \
    TEST_STUB_NO_OUTPUT(prefix ## _Start) \
    TEST_STUB_NO_OUTPUT(prefix ## _Stop) \
    TEST_STUB_OUTPUT(prefix ## _InfoGet, SystemDeviceInfo) \
    TEST_STUB_OUTPUT(prefix ## _CapabilitiesGet, uint32_t) \
    TEST_STUB_OUTPUT(prefix ## _HealthGet, SystemDeviceHealth) \
    TEST_STUB_OUTPUT(prefix ## _SelfTestRun, SystemDeviceSelfTestResult) \
    TEST_STUB_CONFIG(prefix ## _ConfigApply, config_type) \
    TEST_STUB_CONFIG(prefix ## _ConfigVerify, config_type) \
    TEST_STUB_OUTPUT(prefix ## _EffectiveConfigGet, config_type)

TEST_PASSIVE_STUBS(ProjectBarometerInstance, SystemBarometerSample,
                   SystemBarometerConfig)
TEST_STUB_OUTPUT(ProjectBarometerInstance_LatestSampleGet,
                 SystemBarometerSample)
TEST_STUB_NO_OUTPUT(ProjectBarometerInstance_Process)
TEST_STUB_OUTPUT(ProjectBarometerInstance_NoiseCharacteristicsGet,
                 SystemBarometerNoiseCharacteristics)
TEST_PASSIVE_STUBS(ProjectMagnetometerInstance, SystemMagnetometerSample,
                   SystemMagnetometerConfig)
SystemDeviceResult ProjectMagnetometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    if ((instance_id >= s_magnetometer_count) || (sample == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_magnetometer_sample;
    return SYSTEM_DEVICE_OK;
}
TEST_STUB_NO_OUTPUT(ProjectMagnetometerInstance_Process)
TEST_PASSIVE_STUBS(ProjectAttitudeInstance,
                   SystemHardwareQuaternionSample,
                   SystemHardwareQuaternionConfig)
TEST_STUB_OUTPUT(ProjectAttitudeInstance_LatestSampleGet,
                 SystemHardwareQuaternionSample)

#undef TEST_PASSIVE_STUBS
#undef TEST_STUB_CONFIG
#undef TEST_STUB_OUTPUT
#undef TEST_STUB_NO_OUTPUT

uint64_t SystemTime_GetMonotonicUs(void) { return s_now_us; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
LoggerBusResult LoggerBus_EventPush(
    uint64_t timestamp_us, FlightLogEventId event_id,
    uint32_t arg0, uint32_t arg1)
{
    (void)timestamp_us;
    if (s_event_count >= TEST_EVENT_COUNT_MAX)
    { return LOGGER_BUS_RESULT_FULL; }
    s_events[s_event_count].event_id = event_id;
    s_events[s_event_count].arg0 = arg0;
    s_events[s_event_count].arg1 = arg1;
    s_event_count++;
    return LOGGER_BUS_RESULT_OK;
}

static uint8_t Test_EventReasonGet(uint8_t index)
{ return (uint8_t)(s_events[index].arg0 >> 24U); }
#endif

static void Test_EventCountAssert(uint8_t enabled_count)
{
    /* Disabled logging must leave the event sink absent. The source-selection
     * and timeout assertions below execute unchanged in both configurations. */
    TEST_CHECK(s_event_count == ((SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U) ? enabled_count : 0U));
}

static uint8_t Test_ActiveGet(
    SystemDeviceResult (*getter)(uint8_t *))
{
    uint8_t active = 0xFFU;

    TEST_CHECK(getter(&active) == SYSTEM_DEVICE_OK);
    return active;
}

static void Test_ImuSelectionAndLock(void)
{
    uint8_t instance;

    Test_StateReset();
    TEST_CHECK(SystemImu_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemImu_Start() == SYSTEM_DEVICE_OK);
    for (instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    {
        TEST_CHECK(s_imu_init_count[instance] == 1U);
        TEST_CHECK(s_imu_start_count[instance] == 1U);
    }
    TEST_CHECK(SystemSourceSelector_ImuSelectAndLock() ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_ImuActiveInstanceGet) == 0U);
    TEST_CHECK(s_event_count == 0U);

    Test_StateReset();
    s_imu_sample[0].receive_timestamp_us =
        s_now_us - SYSTEM_SOURCE_SELECTOR_IMU_FRESH_TIMEOUT_US - 1ULL;
    s_imu_sample[1].accel_b_mps2[0] = NAN;
    TEST_CHECK(SystemImu_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemImu_Start() == SYSTEM_DEVICE_OK);
    SystemImu_Process();
    TEST_CHECK(SystemSourceSelector_ImuSelectAndLock() ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_ImuActiveInstanceGet) == 2U);
    Test_EventCountAssert(1U);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    TEST_CHECK(s_events[0].event_id ==
               FLIGHT_LOG_EVENT_SENSOR_SOURCE_CHANGE);
    TEST_CHECK(Test_EventReasonGet(0U) ==
               SYSTEM_SOURCE_CHANGE_REASON_PRESTART_PRIMARY_UNAVAILABLE);
#endif
    for (instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    { TEST_CHECK(s_imu_process_count[instance] == 1U); }

    s_imu_sample[0].receive_timestamp_us = s_now_us;
    s_imu_health[2].online = 0U;
    SystemImu_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_ImuActiveInstanceGet) == 2U);
    Test_EventCountAssert(1U);
}

static void Test_GnssOneWayLiveness(void)
{
    SystemGnssSample sample;
    uint8_t instance;

    Test_StateReset();
    s_gnss_sample[0].fix_ok = 0U;
    s_gnss_sample[0].fix_type = 1U;
    TEST_CHECK(SystemGnss_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnss_Start() == SYSTEM_DEVICE_OK);
    SystemGnss_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_GnssActiveInstanceGet) == 0U);
    TEST_CHECK(SystemGnss_LatestSampleGet(&sample) == SYSTEM_DEVICE_OK);
    TEST_CHECK(sample.online != 0U && sample.fix_ok == 0U);
    TEST_CHECK(s_event_count == 0U);

    s_gnss_health[0].online = 0U;
    SystemGnss_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_GnssActiveInstanceGet) == 1U);
    Test_EventCountAssert(1U);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    TEST_CHECK(Test_EventReasonGet(0U) ==
               SYSTEM_SOURCE_CHANGE_REASON_GNSS_LIVENESS_TIMEOUT);
#endif
    s_gnss_health[0].online = 1U;
    SystemGnss_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_GnssActiveInstanceGet) == 1U);
    s_gnss_health[1].online = 0U;
    SystemGnss_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_GnssActiveInstanceGet) == 2U);
    Test_EventCountAssert(2U);
    s_gnss_health[2].online = 0U;
    SystemGnss_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_GnssActiveInstanceGet) == 2U);
    Test_EventCountAssert(2U);
    for (instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    {
        TEST_CHECK(s_gnss_init_count[instance] == 1U);
        TEST_CHECK(s_gnss_start_count[instance] == 1U);
        TEST_CHECK(s_gnss_process_count[instance] == 5U);
    }

    Test_StateReset();
    s_gnss_count = 1U;
    TEST_CHECK(SystemGnss_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnss_Start() == SYSTEM_DEVICE_OK);
    s_gnss_health[0].online = 0U;
    SystemGnss_Process();
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_GnssActiveInstanceGet) == 0U);
    TEST_CHECK(s_event_count == 0U);
}

static void Test_GnssReadOnlyConfigFanout(void)
{
    SystemGnssConfig config;
    SystemDeviceConfigReport report;
    Test_StateReset();
    s_gnss_capabilities[0] = SYSTEM_GNSS_CAP_READ_ONLY;
    TEST_CHECK(SystemGnss_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnss_Start() == SYSTEM_DEVICE_OK);
    (void)memset(&config, 0, sizeof(config));
    config.requested_mask = SYSTEM_GNSS_CFG_NAVIGATION_RATE;
    config.required_mask = config.requested_mask;
    TEST_CHECK(SystemGnss_ConfigApply(&config, &report) ==
        SYSTEM_DEVICE_CONFIG_NO_ACTION);
    TEST_CHECK(SystemGnss_ConfigVerify(&config, &report) ==
        SYSTEM_DEVICE_CONFIG_NO_ACTION);
    TEST_CHECK(s_gnss_apply_count[0] == 0U);
    TEST_CHECK(s_gnss_verify_count[0] == 0U);
    TEST_CHECK(s_gnss_apply_count[1] == 1U && s_gnss_apply_count[2] == 1U);
    TEST_CHECK(s_gnss_verify_count[1] == 1U && s_gnss_verify_count[2] == 1U);
    TEST_CHECK(report.requested_mask == 0U);
}

static void Test_TelemetryAttempt(
    uint8_t instance, SystemDeviceResult result, uint16_t count)
{
    static const uint8_t data[] = {0x55U};
    uint16_t attempt;

    s_telemetry_send_result[instance] = result;
    for (attempt = 0U; attempt < count; attempt++)
    {
        TEST_CHECK(SystemTelemetry_Send(data, sizeof(data)) == result);
        SystemTelemetry_Process();
    }
}

static void Test_TelemetryThresholdAndReset(void)
{
    uint8_t instance;

    Test_StateReset();
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Start() == SYSTEM_DEVICE_OK);
    for (instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    { TEST_CHECK(s_telemetry_init_count[instance] == 1U); }
    TEST_CHECK(s_telemetry_start_count[0] == 1U);
    TEST_CHECK(s_telemetry_start_count[1] == 0U);
    TEST_CHECK(s_telemetry_start_count[2] == 0U);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_TIMEOUT, 9U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 0U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               9U);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_TIMEOUT, 1U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 1U);
    TEST_CHECK(s_telemetry_start_count[1] == 1U);
    TEST_CHECK(s_telemetry_stop_count[0] == 1U);
    TEST_CHECK(s_telemetry_send_count[0] == 10U);
    TEST_CHECK(s_telemetry_send_count[1] == 0U);
    Test_EventCountAssert(1U);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    TEST_CHECK(Test_EventReasonGet(0U) ==
        SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_CONSECUTIVE_TX_TIMEOUT);
#endif
    Test_TelemetryAttempt(1U, SYSTEM_DEVICE_OK, 1U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               0U);

    Test_StateReset();
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Start() == SYSTEM_DEVICE_OK);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_TIMEOUT, 5U);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_OK, 1U);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_TIMEOUT, 5U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 0U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               5U);
    TEST_CHECK(s_event_count == 0U);

    Test_StateReset();
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Start() == SYSTEM_DEVICE_OK);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_BUSY, 20U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 0U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               0U);
    TEST_CHECK(s_event_count == 0U);
}

static void Test_TelemetryChainAndLastCandidate(void)
{
    uint8_t receive_data[4];
    uint16_t receive_length;

    Test_StateReset();
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Start() == SYSTEM_DEVICE_OK);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_TIMEOUT, 10U);
    Test_TelemetryAttempt(1U, SYSTEM_DEVICE_TIMEOUT, 10U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 2U);
    Test_EventCountAssert(2U);
    Test_TelemetryAttempt(2U, SYSTEM_DEVICE_TIMEOUT, 20U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 2U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT);
    TEST_CHECK(s_telemetry_send_count[0] == 10U);
    TEST_CHECK(s_telemetry_send_count[1] == 10U);
    TEST_CHECK(s_telemetry_send_count[2] == 20U);
    Test_EventCountAssert(2U);
    Test_TelemetryAttempt(2U, SYSTEM_DEVICE_OK, 1U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               0U);
    receive_length = 0U;
    TEST_CHECK(SystemTelemetry_Receive(
        receive_data, sizeof(receive_data), &receive_length) ==
        SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(s_telemetry_receive_count[0] == 0U);
    TEST_CHECK(s_telemetry_receive_count[1] == 0U);
    TEST_CHECK(s_telemetry_receive_count[2] == 1U);

    Test_StateReset();
    s_telemetry_count = 1U;
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Start() == SYSTEM_DEVICE_OK);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_TIMEOUT, 12U);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 0U);
    TEST_CHECK(s_telemetry_send_count[0] == 12U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               SYSTEM_TELEMETRY_FAILOVER_CONSECUTIVE_TIMEOUT_LIMIT);
    Test_TelemetryAttempt(0U, SYSTEM_DEVICE_OK, 1U);
    TEST_CHECK(SystemSourceSelector_TelemetryConsecutiveTimeoutCountGet() ==
               0U);
    TEST_CHECK(s_event_count == 0U);
}

static void Test_TelemetryInitFailureSkipsCandidate(void)
{
    Test_StateReset();
    s_telemetry_init_result[0] = SYSTEM_DEVICE_IO_ERROR;
    TEST_CHECK(SystemTelemetry_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(Test_ActiveGet(
        SystemSourceSelector_TelemetryActiveInstanceGet) == 1U);
    Test_EventCountAssert(1U);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    TEST_CHECK(Test_EventReasonGet(0U) ==
               SYSTEM_SOURCE_CHANGE_REASON_TELEMETRY_INIT_FAILURE);
#endif
    TEST_CHECK(SystemTelemetry_Start() == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_telemetry_start_count[0] == 0U);
    TEST_CHECK(s_telemetry_start_count[1] == 1U);
    TEST_CHECK(s_telemetry_start_count[2] == 0U);
}

int main(void)
{
    SystemMagnetometerSample magnetometer;
    Test_StateReset();
    s_magnetometer_sample.sequence = 7U;
    TEST_CHECK(SystemMagnetometer_LatestSampleGet(&magnetometer) ==
        SYSTEM_DEVICE_OK);
    TEST_CHECK(magnetometer.sequence == 7U);
    TEST_CHECK(magnetometer.instance_id == 0U);
    TEST_CHECK(magnetometer.descriptor_id ==
        (uint16_t)(SYSTEM_DEVICE_CLASS_MAGNETOMETER * 16U + 1U));
    TEST_CHECK(magnetometer.physical_device_id == magnetometer.descriptor_id);
    Test_ImuSelectionAndLock();
    Test_GnssOneWayLiveness();
    Test_GnssReadOnlyConfigFanout();
    Test_TelemetryThresholdAndReset();
    Test_TelemetryChainAndLastCandidate();
    Test_TelemetryInitFailureSkipsCandidate();
    return Test_Finish("source_selector");
}
