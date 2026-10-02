/* Actual generated Alignment, lifecycle transaction, origin collector and
 * selected estimator kernel. Sensor/attitude and storage inputs are fixtures;
 * neither readiness, FreezeOrigins nor START is replaced. Actual selected
 * INS/alignment, health, logging-enabled storage admission and task interfaces
 * execute; raw storage projections are inputs, not new SD qualification. */
#include "../../APP/Src/estimator_task.c"
#include "test_common.h"
#include "host_platform_mock.h"
#include "system_health.h"
#include "system_startup.h"
#include "system_alignment_backend.h"
#include "system_gnss_quality.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_storage_if.h"
#include "system_log_sink_if.h"
#include "system_console_if.h"
#include "system_telemetry_transport_if.h"
#include "system_power_if.h"
#include "system_mag_calibration.h"
#include "system_mag_calibration_storage_if.h"
#include "system_log_policy.h"
#include "optional_start_inputs.h"
#include "system_profile.h"
#include "system_output_if.h"
#include "system_lifecycle_backend.h"
#include "imu_sample_bus.h"

static uint64_t s_test_now = 1000000ULL;
static SystemGnssSample s_test_gnss;
static EstimatorPressureSnapshot s_test_pressure;
static uint8_t s_storage_ready = 1U;

void vTaskDelay(TickType_t ticks)
{ s_test_now += (uint64_t)ticks * 1000ULL; HostPlatformMock_TimeSetUs(s_test_now); }
SystemDeviceResult SystemOutput_SafeSet(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *mask)
{ *mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemMagnetometer_CapabilitiesGet(uint32_t *mask)
{ *mask = 0U; return SYSTEM_DEVICE_UNSUPPORTED; }
SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(uint32_t *mask)
{ *mask = SYSTEM_HW_QUAT_CAP_OUTPUT; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(SystemHardwareQuaternionSample *sample)
{ memset(sample, 0, sizeof(*sample)); return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *mask)
{ *mask = SYSTEM_GNSS_CAP_POSITION; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *mask)
{ *mask = SYSTEM_BARO_VALID_PRESSURE | SYSTEM_BARO_VALID_ALTITUDE; return SYSTEM_DEVICE_OK; }
const char *SystemGnss_NameGet(void) { return "HostM9N"; }
const char *SystemBarometer_NameGet(void) { return "HostJY901BBaro"; }
const char *SystemHardwareQuaternion_NameGet(void) { return "HostRawQuaternion"; }
SystemDeviceResult SystemMagnetometer_LatestSampleGet(SystemMagnetometerSample *sample)
{ memset(sample, 0, sizeof(*sample)); return SYSTEM_DEVICE_NOT_READY; }

SystemDeviceResult SystemGnss_TimeGet(SystemGnssTime *time)
{ memset(time, 0, sizeof(*time)); return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ *sample = s_test_gnss; return SystemGnssQuality_Evaluate(sample, s_test_now); }
SystemDeviceResult SystemSourceSelector_ImuSelectAndLock(void) { return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{ *instance = 0U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemSourceSelector_GnssActiveInstanceGet(uint8_t *instance)
{ *instance = 0U; return SYSTEM_DEVICE_OK; }

static SystemStartupReport s_startup_report;
const SystemStartupReport *SystemStartup_GetReport(void) { return &s_startup_report; }
static SystemDeviceResult Test_DeviceHealth(SystemDeviceHealth *health)
{ memset(health, 0, sizeof(*health)); health->initialized = 1U; health->online = 1U; health->healthy = 1U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemImu_HealthGet(SystemDeviceHealth *health) { return Test_DeviceHealth(health); }
SystemDeviceResult SystemGnss_HealthGet(SystemDeviceHealth *health) { return Test_DeviceHealth(health); }
SystemDeviceResult SystemBarometer_HealthGet(SystemDeviceHealth *health) { return Test_DeviceHealth(health); }
SystemDeviceResult SystemMagnetometer_HealthGet(SystemDeviceHealth *health) { return Test_DeviceHealth(health); }
SystemDeviceResult SystemHardwareQuaternion_HealthGet(SystemDeviceHealth *health) { return Test_DeviceHealth(health); }
SystemDeviceResult SystemPower_HealthGet(SystemDeviceHealth *health) { return Test_DeviceHealth(health); }
SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{ memset(health, 0, sizeof(*health)); health->initialized = 1U; health->healthy = 1U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemConsoleDevice_HealthGet(SystemConsoleHealth *health)
{ memset(health, 0, sizeof(*health)); health->initialized = 1U; health->healthy = 1U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemOutput_StatusGet(uint8_t channel, SystemOutputStatus *status)
{ memset(status, 0, sizeof(*status)); status->channel = channel; status->state = SYSTEM_OUTPUT_SAFE; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemStorage_HealthGet(SystemStorageHealth *health)
{ memset(health, 0, sizeof(*health)); health->initialized = 1U; health->mounted = s_storage_ready; health->healthy = s_storage_ready; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemStorage_MissionIdGet(uint32_t *mission_id) { *mission_id = 1U; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemLogSink_HealthGet(SystemLogSinkHealth *health)
{ memset(health, 0, sizeof(*health)); health->initialized = 1U; health->session_active = 1U; health->healthy = s_storage_ready; return SYSTEM_DEVICE_OK; }
SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{ memset(sample, 0, sizeof(*sample)); sample->sample_timestamp_us = s_test_now; sample->receive_timestamp_us = s_test_now; sample->sequence = (uint32_t)(s_test_now / 50000ULL); sample->accel_b_mps2[2] = SYSTEM_LOCAL_GRAVITY_MPS2; sample->valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO; return SYSTEM_DEVICE_OK; }

static void Test_Collect(uint8_t gnss_available)
{
    uint16_t index;
    (void)memset(&s_test_gnss, 0, sizeof(s_test_gnss));
    (void)memset(&s_test_pressure, 0, sizeof(s_test_pressure));
    s_test_gnss.position_usable = gnss_available;
    s_test_gnss.online = 1U;
    s_test_gnss.fix_type = gnss_available ? 3U : 0U;
    s_test_gnss.fix_ok = gnss_available;
    s_test_gnss.supported_fields = 0x3FFU;
    s_test_gnss.valid_fields = s_test_gnss.supported_fields;
    s_test_gnss.satellite_count = 8U;
    s_test_gnss.speed_accuracy_mps = 0.2f;
    s_test_gnss.latitude_e7 = 300000000;
    s_test_gnss.longitude_e7 = 1200000000;
    s_test_gnss.horizontal_accuracy_m = 1.0f;
    s_test_gnss.vertical_accuracy_m = 2.0f;
    s_test_gnss.velocity_valid_mask = 7U;
    s_test_gnss.velocity_variance_m2ps2[0] = 0.04f;
    s_test_gnss.velocity_variance_m2ps2[1] = 0.04f;
    s_test_gnss.velocity_variance_m2ps2[2] = 0.04f;
    s_test_pressure.altitude_m = 10.0f;
    s_test_pressure.pressure_pa = 101325.0f;
    s_test_pressure.valid = 1U;
    s_test_pressure.supported_fields = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
    s_test_pressure.valid_fields = s_test_pressure.supported_fields;
    for (index = 0U; index < SYSTEM_ESTIMATOR_GNSS_ORIGIN_WINDOW_SAMPLES; index++)
    {
        s_test_now += 50000ULL;
        HostPlatformMock_TimeSetUs(s_test_now);
        s_test_gnss.sequence++;
        s_test_pressure.sequence++;
        s_test_gnss.sample_timestamp_us = s_test_now;
        s_test_gnss.receive_timestamp_us = s_test_now;
        s_test_pressure.timestamp_us = s_test_now;
        s_test_pressure.receive_timestamp_us = s_test_now;
        TEST_CHECK(EstimatorBus_PressurePublish(&s_test_pressure) == ESTIMATOR_BUS_RESULT_OK);
        Test_InsInputFeed(s_test_now, (uint32_t)index + 1U);
        Estimator_OriginWindowCollect();
    }
}


static void Test_Reset(uint8_t fix, uint8_t barometer)
{
    InsTask_AbortMission();
    EstimatorTask_AbortMission();
    HostPlatformMock_TimeSetUs(s_test_now);
    TEST_CHECK(SystemTime_Init() == SYSTEM_DEVICE_OK);
    SystemProfile_UnfreezeForRollback();
    SystemNavigationProfile_UnfreezeForRollback();
    SystemEstimatorProfile_UnfreezeForRollback();
    SystemLifecycle_Init();
    TEST_CHECK(SystemLifecycle_EnterSelfTest() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterPreflight() == SYSTEM_DEVICE_OK);
    s_storage_ready = 1U;
    memset(&s_startup_report, 0, sizeof(s_startup_report));
    s_startup_report.completed = 1U; s_startup_report.mission_capable = 1U;
    s_startup_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    for (uint8_t index = 0U; index < SYSTEM_STARTUP_DEVICE_COUNT; index++)
    {
        s_startup_report.devices[index].device_id = (SystemStartupDeviceId)index;
        s_startup_report.devices[index].present = 1U;
        s_startup_report.devices[index].init_result = SYSTEM_DEVICE_OK;
        s_startup_report.devices[index].start_result = SYSTEM_DEVICE_OK;
    }
    SystemHealth_Init();
    SystemCalibration_Init();
    SystemAlignment_Init();
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    SystemLogPolicy_Init();
    Test_MagStorageInputsLoad();
    Test_StorageProjectionSet();
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_Collect(fix);
    if (!barometer) { memset(&s_estimator.baro_window, 0, sizeof(s_estimator.baro_window)); }
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    SystemHealth_Process();
    FlightLogRecord drained;
    for (uint16_t index = 0U; index < 512U; index++)
    { if (LoggerBus_NextPop(&drained) != LOGGER_BUS_RESULT_OK) { break; } }
    TEST_CHECK(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
}

static void Test_StartNoFix(void)
{
    EstimatorOutputSnapshot output = {0};
    SystemAlignmentSummary alignment = {0};
    uint8_t required = (uint8_t)((SYSTEM_USER_ALIGNMENT_REQUIRED_MASK & SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U);
    Test_Reset(0U, 1U);
    TEST_CHECK(SystemAlignment_SummaryGet(&alignment) == SYSTEM_DEVICE_OK);
    TEST_CHECK(alignment.required_mask == SYSTEM_USER_ALIGNMENT_REQUIRED_MASK);
    TEST_CHECK(alignment.ready == (uint8_t)!required);
    if (required)
    {
        TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_NOT_READY);
        /* Even a caller bypassing Alignment cannot freeze a required missing origin. */
        TEST_CHECK(EstimatorTask_FreezeOrigins() == SYSTEM_DEVICE_NOT_READY);
        TEST_CHECK(s_estimator.origin_collection_frozen == 0U);
        return;
    }
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycleBackend_StorageReadyGet() == 1U);
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_OK);
    TEST_CHECK(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(Estimator_GetLatestSnapshot(&output) != 0U);
    TEST_CHECK(output.mission_running == 1U && output.gnss_origin_valid == 0U && output.baro_origin_valid == 1U);
    TEST_CHECK(s_estimator.gnss_fusion_enabled == 0U && s_estimator.origin_collection_frozen == 1U);
    TEST_CHECK(s_estimator.gnss_frame.valid == 0U && s_estimator.frozen_gnss.position_usable == 0U);
    Test_Collect(1U); /* Late stationary or moving fixes must not establish a new origin. */
#if (SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U)
    EstimatorGnssUpdateWork work = {0};
    TEST_CHECK(Estimator_GnssSamplePrepare(s_test_now, &work) == ESTIMATOR_GNSS_PREPARE_STOP);
#endif
    if (SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE)
    {
        SystemInertialIncrement prediction = {0};
        prediction.timestamp_us = s_test_now;
        prediction.dt_s = 0.01f;
        prediction.delta_velocity_b_sculling_corrected[2] = SYSTEM_INS_GRAVITY_MPS2 * prediction.dt_s;
        Estimator_PredictionProcess(&prediction);
        TEST_CHECK(Estimator_GetLatestSnapshot(&output) != 0U);
        TEST_CHECK(output.predict_count > 0U && output.gnss_origin_valid == 0U);
        TEST_CHECK(output.gnss_position_update_count == 0U && output.gnss_velocity_update_count == 0U);
        TEST_CHECK((output.health_flags & ESTIMATOR_HEALTH_GNSS_ORIGIN_UNAVAILABLE) != 0U);
    }
    TEST_CHECK(s_estimator.gnss_origin_valid == 0U && s_estimator.gnss_fusion_enabled == 0U);
    Estimator_DiagnosticsPublish(s_test_now);
    TEST_CHECK(s_estimator.gnss_diagnostics.origin_valid == 0U && s_estimator.gnss_diagnostics.fusion_enabled == 0U);
}

static void Test_RequiredFailures(void)
{
    Test_Reset(1U, 1U);
    TEST_CHECK(InsTask_AlignmentReset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_NOT_READY);
    Test_Reset(1U, 0U);
    TEST_CHECK(SystemAlignment_IsReady() == 0U);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(EstimatorTask_FreezeOrigins() == SYSTEM_DEVICE_NOT_READY);
    Test_Reset(1U, 1U);
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    s_storage_ready = 0U;
    TEST_CHECK(SystemLifecycleBackend_StorageReadyGet() == 0U);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_NOT_READY);
    TEST_CHECK(SystemLifecycle_GetState() != SYSTEM_STATE_FLIGHT);
}

static void Test_StartWithOrigin(void)
{
    EstimatorOutputSnapshot output = {0};
    Test_Reset(1U, 1U);
    TEST_CHECK(SystemAlignment_IsReady() == 1U);
    TEST_CHECK(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycleBackend_StorageReadyGet() == 1U);
    TEST_CHECK(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_OK);
    TEST_CHECK(Estimator_GetLatestSnapshot(&output) != 0U);
    TEST_CHECK(output.gnss_origin_valid == 1U && output.mission_running == 1U);
    TEST_CHECK(s_estimator.gnss_fusion_enabled == (uint8_t)(SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE));
    EstimatorTask_AbortMission();
    /* Lost freshness after a successful preflight preparation must clear its
     * frozen sample before the optional no-origin START initializes a backend. */
    SystemProfile_UnfreezeForRollback();
    SystemNavigationProfile_UnfreezeForRollback();
    SystemEstimatorProfile_UnfreezeForRollback();
    SystemLifecycle_Init();
    TEST_CHECK(SystemLifecycle_EnterSelfTest() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemLifecycle_EnterPreflight() == SYSTEM_DEVICE_OK);
    memset(&s_estimator.gnss_window, 0, sizeof(s_estimator.gnss_window));
    Test_Collect(0U);
    (void)EstimatorTask_FreezeOrigins();
    TEST_CHECK(s_estimator.frozen_gnss.position_usable == 0U && s_estimator.gnss_frame.valid == 0U);
}

int main(void)
{
    HostPlatformMock_Reset();
    TEST_CHECK(ImuSampleBus_Init() == IMU_SAMPLE_BUS_RESULT_OK);
    TEST_CHECK(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    Test_StartNoFix(); Test_RequiredFailures(); Test_StartWithOrigin();
    return Test_Finish("optional_gnss_start_actual");
}
