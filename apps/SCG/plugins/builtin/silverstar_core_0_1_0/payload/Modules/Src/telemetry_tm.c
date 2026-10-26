#include "telemetry_tm.h"

#include <limits.h>
#include <math.h>
#include <string.h>
#include "project_device_instances.h"
#include "silverstar_assert.h"
#include "system_gnss_if.h"
#include "system_power_if.h"
#include "system_imu_if.h"
#include "system_storage_if.h"
#include "system_log_sink_if.h"
#include "system_startup.h"
#include "system_calibration.h"
#include "system_lifecycle.h"
#include "system_user_config.h"
#include "estimator_task.h"

#define TELEMETRY_TM_AGE_UNKNOWN UINT32_MAX
#define TELEMETRY_TM_AGE_SATURATED (UINT32_MAX - 1U)
#define TELEMETRY_TM_UNKNOWN_U16 UINT16_MAX
#define TELEMETRY_TM_SATURATED_U16 (UINT16_MAX - 1U)
#define TELEMETRY_TM_CURRENT_FIX_MAX_AGE_US 2000000ULL
#define TELEMETRY_TM_INSTANCE_BOUND 32U
#define TELEMETRY_TM_ESTIMATOR_MAX_AGE_US 1000000ULL

typedef struct
{
    SystemGnssSample fix;
    uint64_t timestamp_us;
    uint64_t battery_timestamp_us;
    uint16_t battery_mv;
    uint8_t valid;
    uint8_t height_valid;
    uint8_t measurement_time;
    uint8_t time_valid;
    uint8_t current_usable;
    uint8_t battery_valid;
    uint8_t battery_time_valid;
} TelemetryTmObservations;

static TelemetryTmObservations s_observations;

void TelemetryTm_Init(void)
{
    (void)memset(&s_observations, 0, sizeof(s_observations));
}

static uint32_t TelemetryTm_AgeMs(uint64_t now_us, uint64_t sample_us, uint8_t valid)
{
    uint64_t age_ms;
    if ((valid == 0U) || (sample_us > now_us)) { return TELEMETRY_TM_AGE_UNKNOWN; }
    age_ms = (now_us - sample_us) / 1000ULL;
    return (age_ms >= TELEMETRY_TM_AGE_SATURATED) ? TELEMETRY_TM_AGE_SATURATED : (uint32_t)age_ms;
}

static void TelemetryTm_GnssObserve(uint64_t now_us)
{
    SystemGnssSample sample;
    uint32_t capabilities = 0U;
    uint64_t timestamp;
    s_observations.current_usable = 0U;
    if (SystemGnss_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK) { return; }
    if ((sample.position_usable == 0U) || (sample.online == 0U) ||
        ((sample.valid_fields & SYSTEM_GNSS_FIELD_POSITION) == 0U) ||
        (sample.latitude_e7 < -900000000L) || (sample.latitude_e7 > 900000000L) ||
        (sample.longitude_e7 < -1800000000L) || (sample.longitude_e7 > 1800000000L)) { return; }
    uint8_t measurement_time = (uint8_t)((sample.measurement_timestamp_trusted != 0U) &&
        (sample.sample_timestamp_us != 0U) && (sample.sample_timestamp_us <= now_us));
    timestamp = (measurement_time != 0U) ? sample.sample_timestamp_us : sample.receive_timestamp_us;
    uint8_t time_valid = (uint8_t)((timestamp != 0U) && (timestamp <= now_us));
    if ((s_observations.time_valid != 0U) &&
        ((time_valid == 0U) || (timestamp < s_observations.timestamp_us))) { return; }
    /* Retain even a newly discovered old point, with its original timestamp.
     * Calling the getter again never refreshes sample age. */
    s_observations.fix = sample;
    s_observations.valid = 1U;
    s_observations.measurement_time = measurement_time;
    s_observations.time_valid = time_valid;
    s_observations.current_usable = (uint8_t)((time_valid != 0U) &&
        ((now_us - timestamp) <= TELEMETRY_TM_CURRENT_FIX_MAX_AGE_US));
    s_observations.timestamp_us = timestamp;
    s_observations.height_valid = 0U;
    if ((SystemGnss_CapabilitiesGet(&capabilities) == SYSTEM_DEVICE_OK) &&
        ((capabilities & SYSTEM_GNSS_CAP_ELLIPSOID_HEIGHT) != 0U) &&
        ((sample.valid_fields & SYSTEM_GNSS_FIELD_HEIGHT) != 0U) &&
        (sample.ellipsoid_height_mm != INT32_MIN)) { s_observations.height_valid = 1U; }
}

static void TelemetryTm_PowerObserve(uint64_t now_us)
{
    SystemPowerSample sample;
    float millivolts;
    if (SYSTEM_BUILD_POWER_IMPLEMENTATION_AVAILABLE == 0U) { return; }
    if ((SystemPower_LatestSampleGet(&sample) != SYSTEM_DEVICE_OK) ||
        ((sample.valid_mask & SYSTEM_POWER_VALID_VOLTAGE) == 0U) || !isfinite(sample.voltage_v)) { return; }
    millivolts = sample.voltage_v * 1000.0f;
    if ((millivolts < 0.0f) || (millivolts > 65534.0f)) { return; }
    s_observations.battery_mv = (uint16_t)floorf(millivolts + 0.5f);
    s_observations.battery_valid = 1U;
    s_observations.battery_timestamp_us = sample.sample_timestamp_us;
    s_observations.battery_time_valid = (uint8_t)((sample.sample_timestamp_us != 0U) && (sample.sample_timestamp_us <= now_us));
    if ((s_observations.battery_time_valid == 0U) &&
        (sample.receive_timestamp_us != 0U) && (sample.receive_timestamp_us <= now_us))
    { s_observations.battery_timestamp_us = sample.receive_timestamp_us; s_observations.battery_time_valid = 1U; }
}

void TelemetryTm_Observe(uint64_t now_us)
{
    TelemetryTm_GnssObserve(now_us);
    TelemetryTm_PowerObserve(now_us);
}

AirBuildResult TelemetryTm_PositionBuild(uint64_t now_us, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    int32_t latitude = INT32_MIN, longitude = INT32_MIN, height = INT32_MIN;
    uint8_t flags = 0U, satellites = UINT8_MAX;
    uint16_t accuracy = TELEMETRY_TM_UNKNOWN_U16;
    uint32_t age = TELEMETRY_TM_AGE_UNKNOWN;
    if (s_observations.valid != 0U)
    {
        const SystemGnssSample *sample = &s_observations.fix;
        flags = 1U; latitude = sample->latitude_e7; longitude = sample->longitude_e7;
        if (s_observations.height_valid != 0U) { flags |= 2U; height = sample->ellipsoid_height_mm; }
        flags |= (s_observations.current_usable != 0U) ? 4U : 16U;
        if (s_observations.measurement_time != 0U) { flags |= 8U; }
        if (sample->quality_degraded != 0U) { flags |= 32U; }
        age = TelemetryTm_AgeMs(now_us, s_observations.timestamp_us, s_observations.time_valid);
        if ((sample->valid_fields & SYSTEM_GNSS_FIELD_SATELLITE_COUNT) != 0U) { satellites = sample->satellite_count; }
        if (((sample->valid_fields & SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY) != 0U) &&
            isfinite(sample->horizontal_accuracy_m) && (sample->horizontal_accuracy_m >= 0.0f))
        {
            float cm = sample->horizontal_accuracy_m * 100.0f;
            accuracy = (cm >= 65534.0f) ? TELEMETRY_TM_SATURATED_U16 : (uint16_t)ceilf(cm);
        }
    }
    return SsTm_PositionBuild(latitude, longitude, height, age, accuracy, flags, satellites, out, capacity, length);
}

/* 0 unknown, 1 checked normal, 2 current fault. Historical counters are not masks. */
static uint8_t TelemetryTm_DeviceState(SystemDeviceClass device_class)
{
    uint8_t count = ProjectDeviceInstance_CountGet(device_class);
    uint8_t unknown = 0U, fault = 0U;
    SILVERSTAR_ASSERT(count <= TELEMETRY_TM_INSTANCE_BOUND,
        SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (count == 0U) { return 0U; }
    for (uint8_t index = 0U; index < TELEMETRY_TM_INSTANCE_BOUND; index++)
    {
        SystemDeviceHealth health;
        if (index >= count) { break; }
        if (ProjectDeviceInstance_HealthGet(device_class, index, &health) != SYSTEM_DEVICE_OK) { unknown = 1U; continue; }
        if (health.initialized == 0U) { unknown = 1U; continue; }
        if ((health.online == 0U) || (health.healthy == 0U)) { fault = 1U; }
    }
    return (uint8_t)((fault != 0U) ? 2U : (unknown != 0U) ? 0U : 1U);
}

static uint8_t TelemetryTm_PrimaryImuState(void)
{
    SystemDeviceHealth health;
    if ((SystemImu_HealthGet(&health) != SYSTEM_DEVICE_OK) || (health.initialized == 0U)) { return 0U; }
    return (uint8_t)(((health.online != 0U) && (health.healthy != 0U)) ? 1U : 2U);
}

static void TelemetryTm_HealthBit(uint8_t bit, uint8_t state, uint16_t *known, uint16_t *fault)
{
    uint16_t mask;
    SILVERSTAR_ASSERT(bit <= 10U, SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(state <= 2U, SILVERSTAR_ASSERT_MODULE_MODULES, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    mask = (uint16_t)(1U << bit);
    if (state != 0U) { *known |= mask; }
    if (state == 2U) { *fault |= mask; }
}

static void TelemetryTm_ServiceHealth(uint64_t now_us, uint16_t *known, uint16_t *fault)
{
    EstimatorOutputSnapshot estimator;
    SystemStorageHealth storage;
    SystemTelemetryHealth telemetry;
    SystemCalibrationStatus calibration;
    if ((Estimator_GetLatestSnapshot(&estimator) != 0U) && (estimator.mission_running != 0U))
    {
        uint8_t normal = (uint8_t)((estimator.initialized != 0U) && (estimator.timestamp_us <= now_us) &&
            ((now_us - estimator.timestamp_us) <= TELEMETRY_TM_ESTIMATOR_MAX_AGE_US) &&
            isfinite(estimator.q_nb[0]) && isfinite(estimator.q_nb[1]) &&
            isfinite(estimator.q_nb[2]) && isfinite(estimator.q_nb[3]) &&
            isfinite(estimator.position_enu_m[0]) && isfinite(estimator.position_enu_m[1]) &&
            isfinite(estimator.position_enu_m[2]) && isfinite(estimator.velocity_enu_mps[0]) &&
            isfinite(estimator.velocity_enu_mps[1]) && isfinite(estimator.velocity_enu_mps[2]));
        TelemetryTm_HealthBit(5U, (normal != 0U) ? 1U : 2U, known, fault);
    }
    if ((SystemStorage_HealthGet(&storage) == SYSTEM_DEVICE_OK) && (storage.initialized != 0U))
    { TelemetryTm_HealthBit(6U, (storage.healthy != 0U) ? 1U : 2U, known, fault); }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    {
        SystemLogSinkHealth sink;
        if ((SystemLogSink_HealthGet(&sink) == SYSTEM_DEVICE_OK) && (sink.initialized != 0U))
        { TelemetryTm_HealthBit(7U, (sink.healthy != 0U) ? 1U : 2U, known, fault); }
    }
#endif
    if ((SystemTelemetry_HealthGet(&telemetry) == SYSTEM_DEVICE_OK) && (telemetry.initialized != 0U))
    { TelemetryTm_HealthBit(8U, (telemetry.healthy != 0U) ? 1U : 2U, known, fault); }
    /* No whole-scheduler liveness provider exists: bit9 deliberately remains unknown. */
    if (SystemCalibration_StatusGet(&calibration) == SYSTEM_DEVICE_OK)
    {
        if (calibration.state == SYSTEM_CALIBRATION_STATE_FAILED)
        { TelemetryTm_HealthBit(10U, 2U, known, fault); }
        else if (calibration.ready != 0U) { TelemetryTm_HealthBit(10U, 1U, known, fault); }
    }
}

AirBuildResult TelemetryTm_HealthBuild(uint64_t now_us, uint8_t *out, uint8_t capacity, uint8_t *length)
{
    uint16_t known = 0U, fault = 0U;
    uint16_t battery = TELEMETRY_TM_UNKNOWN_U16, battery_age = TELEMETRY_TM_UNKNOWN_U16;
    uint32_t age;
    TelemetryTm_HealthBit(0U, TelemetryTm_DeviceState(SYSTEM_DEVICE_CLASS_POWER), &known, &fault);
    TelemetryTm_HealthBit(1U, TelemetryTm_PrimaryImuState(), &known, &fault);
    TelemetryTm_HealthBit(2U, TelemetryTm_DeviceState(SYSTEM_DEVICE_CLASS_GNSS), &known, &fault);
    TelemetryTm_HealthBit(3U, TelemetryTm_DeviceState(SYSTEM_DEVICE_CLASS_BAROMETER), &known, &fault);
    TelemetryTm_HealthBit(4U, TelemetryTm_DeviceState(SYSTEM_DEVICE_CLASS_MAGNETOMETER), &known, &fault);
    TelemetryTm_ServiceHealth(now_us, &known, &fault);
    if (s_observations.battery_valid != 0U)
    {
        battery = s_observations.battery_mv;
        age = TelemetryTm_AgeMs(now_us, s_observations.battery_timestamp_us, s_observations.battery_time_valid);
        if (age != TELEMETRY_TM_AGE_UNKNOWN)
        { battery_age = (age / 100U >= TELEMETRY_TM_SATURATED_U16) ? TELEMETRY_TM_SATURATED_U16 : (uint16_t)(age / 100U); }
    }
    return SsTm_HealthBuild(battery, battery_age, known, fault, out, capacity, length);
}
