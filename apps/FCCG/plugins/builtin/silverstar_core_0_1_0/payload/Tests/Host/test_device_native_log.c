#include <string.h>

#include "device_native_log.h"
#include "logger_bus.h"
#include "project_device_instances.h"
#include "sslog_protocol.h"
#include "system_lifecycle.h"
#include "test_common.h"

#define TEST_INSTANCE_COUNT 2U

static SystemGnssSample s_gnss[TEST_INSTANCE_COUNT];
static SystemBarometerSample s_barometer[TEST_INSTANCE_COUNT];
static SystemMagnetometerSample s_magnetometer[TEST_INSTANCE_COUNT];
static SystemPowerSample s_power[TEST_INSTANCE_COUNT];
static FlightLogGnssNativeRecord s_gnss_record[4];
static FlightLogBaroNativeRecord s_barometer_record[4];
static FlightLogMagNativeRecord s_magnetometer_record[4];
static FlightLogPowerRecord s_power_record[4];
static uint8_t s_gnss_push_count;
static uint8_t s_barometer_push_count;
static uint8_t s_magnetometer_push_count;
static uint8_t s_power_push_count;

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return SYSTEM_STATE_FLIGHT;
}

uint8_t ProjectGnssInstance_CountGet(void) { return TEST_INSTANCE_COUNT; }
uint8_t ProjectBarometerInstance_CountGet(void) { return TEST_INSTANCE_COUNT; }
uint8_t ProjectMagnetometerInstance_CountGet(void)
{ return TEST_INSTANCE_COUNT; }
uint8_t ProjectPowerInstance_CountGet(void) { return TEST_INSTANCE_COUNT; }

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    if ((descriptor == NULL) || (instance_id >= TEST_INSTANCE_COUNT))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    (void)memset(descriptor, 0, sizeof(*descriptor));
    descriptor->descriptor_id = (uint16_t)(
        0x100U + ((uint16_t)device_class * 4U) + instance_id);
    descriptor->physical_device_id = (uint16_t)(
        0x20U + ((uint16_t)device_class * 2U) + instance_id);
    descriptor->device_class = device_class;
    descriptor->instance_id = instance_id;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectGnssInstance_LatestSampleGet(
    uint8_t instance_id, SystemGnssSample *sample)
{
    if ((sample == NULL) || (instance_id >= TEST_INSTANCE_COUNT))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_gnss[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectBarometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemBarometerSample *sample)
{
    if ((sample == NULL) || (instance_id >= TEST_INSTANCE_COUNT))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_barometer[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectBarometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if ((health == NULL) || (instance_id >= TEST_INSTANCE_COUNT))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    (void)memset(health, 0, sizeof(*health));
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectMagnetometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    if ((sample == NULL) || (instance_id >= TEST_INSTANCE_COUNT))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_magnetometer[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectPowerInstance_LatestSampleGet(
    uint8_t instance_id, SystemPowerSample *sample)
{
    if ((sample == NULL) || (instance_id >= TEST_INSTANCE_COUNT))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_power[instance_id];
    return SYSTEM_DEVICE_OK;
}

LoggerBusResult LoggerBus_GnssNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogGnssNativeRecord *record)
{
    (void)timestamp_us;
    (void)valid_flags;
    s_gnss_record[s_gnss_push_count++] = *record;
    return LOGGER_BUS_RESULT_OK;
}

LoggerBusResult LoggerBus_BaroNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogBaroNativeRecord *record)
{
    (void)timestamp_us;
    (void)valid_flags;
    s_barometer_record[s_barometer_push_count++] = *record;
    return LOGGER_BUS_RESULT_OK;
}

LoggerBusResult LoggerBus_MagNativePush(
    uint64_t timestamp_us, uint32_t valid_flags,
    const FlightLogMagNativeRecord *record)
{
    (void)timestamp_us;
    (void)valid_flags;
    s_magnetometer_record[s_magnetometer_push_count++] = *record;
    return LOGGER_BUS_RESULT_OK;
}

LoggerBusResult LoggerBus_PowerPush(
    uint64_t timestamp_us, const FlightLogPowerRecord *record)
{
    (void)timestamp_us;
    s_power_record[s_power_push_count++] = *record;
    return LOGGER_BUS_RESULT_OK;
}

static void Test_SamplesInitialize(void)
{
    uint8_t instance_id;

    for (instance_id = 0U; instance_id < TEST_INSTANCE_COUNT; instance_id++)
    {
        s_gnss[instance_id].sequence = (uint32_t)(20U + instance_id);
        s_barometer[instance_id].sequence = (uint32_t)(30U + instance_id);
        s_magnetometer[instance_id].sequence = (uint32_t)(40U + instance_id);
        s_power[instance_id].sequence = (uint32_t)(60U + instance_id);
        s_gnss[instance_id].sample_timestamp_us = 2000ULL + instance_id;
        s_barometer[instance_id].sample_timestamp_us = 3000ULL + instance_id;
        s_magnetometer[instance_id].sample_timestamp_us = 4000ULL + instance_id;
        s_power[instance_id].sample_timestamp_us = 6000ULL + instance_id;
        s_gnss[instance_id].latitude_e7 = (int32_t)(200 + instance_id);
        s_barometer[instance_id].pressure_raw_pa =
            (int32_t)(300 + instance_id);
        s_magnetometer[instance_id].raw[0] = (int32_t)(400 + instance_id);
        s_power[instance_id].voltage_v = 12.0f + (float)instance_id;
    }
}

static void Test_AllNativeInstances(void)
{
    Test_SamplesInitialize();
    DeviceNativeLog_Process();
    TEST_CHECK(s_gnss_push_count == 2U);
    TEST_CHECK(s_barometer_push_count == 2U);
    TEST_CHECK(s_magnetometer_push_count == 2U);
    TEST_CHECK(s_gnss_record[0].instance_id == 0U);
    TEST_CHECK(s_gnss_record[1].instance_id == 1U);
    TEST_CHECK(s_gnss_record[0].source_descriptor_id != s_gnss_record[1].source_descriptor_id);
    TEST_CHECK(s_gnss_record[1].latitude_e7 == 201);
    TEST_CHECK(s_barometer_record[1].healthy == 1U);
    TEST_CHECK(s_magnetometer_record[1].raw[0] == 401);
    DeviceNativeLog_Process();
    TEST_CHECK(s_gnss_push_count == 2U);
    s_gnss[1].sequence++;
    DeviceNativeLog_Process();
    TEST_CHECK(s_gnss_push_count == 3U);
    TEST_CHECK(s_gnss_record[2].instance_id == 1U);
}

static void Test_PowerInstancesAndRoundTrip(void)
{
    SystemLogStreamConfig config = {
        FLIGHT_LOG_RECORD_POWER, 1U, 1U, 1000UL,
        SSLOG_STREAM_POLICY_PERIODIC
    };
    FlightLogRecord source;
    FlightLogRecord decoded;
    uint8_t buffer[FLIGHT_LOG_MAX_PAYLOAD_SIZE];
    uint16_t size;

    DeviceNativeLog_PowerProcess(1000ULL, &config);
    TEST_CHECK(s_power_push_count == 2U);
    TEST_CHECK(s_power_record[0].instance_id == 0U);
    TEST_CHECK(s_power_record[1].instance_id == 1U);
    DeviceNativeLog_PowerProcess(2000ULL, &config);
    TEST_CHECK(s_power_push_count == 2U);
    s_power[1].sequence++;
    DeviceNativeLog_PowerProcess(3000ULL, &config);
    TEST_CHECK(s_power_push_count == 3U);
    TEST_CHECK(s_power_record[2].instance_id == 1U);
    (void)memset(&source, 0, sizeof(source));
    source.record_type = FLIGHT_LOG_RECORD_GNSS_NATIVE;
    source.payload.gnss_native = s_gnss_record[2];
    size = SslogRecords_PayloadSerialize(&source, buffer, sizeof(buffer));
    (void)memset(&decoded, 0, sizeof(decoded));
    decoded.record_type = FLIGHT_LOG_RECORD_GNSS_NATIVE;
    TEST_CHECK(SslogRecords_PayloadDeserialize(&decoded, buffer, size) ==
               FLIGHT_LOG_GNSS_NATIVE_PAYLOAD_SIZE);
    TEST_CHECK(decoded.payload.gnss_native.instance_id == 1U);
    TEST_CHECK(decoded.payload.gnss_native.source_descriptor_id ==
               s_gnss_record[2].source_descriptor_id);
}

int main(void)
{
    Test_AllNativeInstances();
    Test_PowerInstancesAndRoundTrip();
    return Test_Finish("device_native_log");
}
