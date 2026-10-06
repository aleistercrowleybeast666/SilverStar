/* Actual MPU driver/selector, ONE_FACE, INS dual-vector window, barometric
 * collector/freeze, health and lifecycle. Reuse existing deterministic sensor
 * and storage projections; legacy optional-GNSS scenarios are not executed. */
#include <assert.h>
#include <stdlib.h>
#include "system_inertial.h"
#include "system_source_selector.h"
#include "platform_i2c.h"
#include "platform_time.h"
#include "project_resources.h"
#include "system_barometer_cold.h"
#define main Test_LegacyOptionalMain
#define SystemImu_CapabilitiesGet Test_LegacyImuCapabilities
#define SystemImu_HealthGet Test_LegacyImuHealth
#define SystemInertial_LatestGet Test_LegacyInertialLatest
#define SystemSourceSelector_ImuSelectAndLock Test_LegacySelect
#define SystemSourceSelector_ImuActiveInstanceGet Test_LegacyImuActive
#define SystemSourceSelector_GnssActiveInstanceGet Test_LegacyGnssActive
#include "test_optional_gnss_start.c"
#undef main
#undef SystemImu_CapabilitiesGet
#undef SystemImu_HealthGet
#undef SystemInertial_LatestGet
#undef SystemSourceSelector_ImuSelectAndLock
#undef SystemSourceSelector_ImuActiveInstanceGet
#undef SystemSourceSelector_GnssActiveInstanceGet

static uint8_t s_registers[256];
static uint8_t s_read_failure;
static unsigned s_inject_stage;
static uint8_t s_inject_lifecycle_fault;
void Test_InsQueuedQualityCheck(uint8_t clipped);

SystemDeviceResult ProjectMpu6050Resources_Get(uint8_t instance,
    ProjectMpu6050Resources *resources)
{
    if (instance != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    resources->i2c = PLATFORM_I2C_1; resources->time = PLATFORM_TIME_1;
    resources->axis_map[0] = -2; resources->axis_map[1] = 1; resources->axis_map[2] = 3;
    return SYSTEM_DEVICE_OK;
}
/* Raw non-IMU admission inputs; the real capability and START checks consume
 * these projections. No SD/BMP280/telemetry hardware qualification is claimed. */
void Test_MagStorageInputsLoad(void) { }
uint8_t SystemMagCalibrationStorage_LoadCompleteGet(void) { return 1U; }
SystemDeviceResult SystemBarometerCold_HealthGet(SystemDeviceHealth *health)
{ return Test_DeviceHealth(health); }
uint8_t SystemBarometerCold_ActiveGet(void) { return 0U; }
PlatformResult PlatformI2c_MemoryRead(PlatformI2cId id, uint16_t address,
    uint16_t reg, PlatformI2cMemoryAddressSize size, uint8_t *data,
    uint16_t length, uint32_t timeout)
{
    assert(id == PLATFORM_I2C_1 && address == 0x68U && timeout == 2U);
    assert(size == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT && reg + length <= 256U);
    if (s_read_failure != 0U) { return PLATFORM_IO_ERROR; }
    memcpy(data, &s_registers[reg], length); return PLATFORM_OK;
}
PlatformResult PlatformI2c_MemoryWrite(PlatformI2cId id, uint16_t address,
    uint16_t reg, PlatformI2cMemoryAddressSize size, const uint8_t *data,
    uint16_t length, uint32_t timeout)
{
    assert(id == PLATFORM_I2C_1 && address == 0x68U && timeout == 2U);
    assert(size == PLATFORM_I2C_MEMORY_ADDRESS_8_BIT && reg + length <= 256U);
    memcpy(&s_registers[reg], data, length);
    if ((reg == 107U) && (data[0] == 128U)) { s_registers[reg] = 0U; }
    return PLATFORM_OK;
}

static void Test_Tick(void)
{
    s_test_now += 10000ULL; HostPlatformMock_TimeSetUs(s_test_now);
    SystemImu_Process();
}
static void Test_PhysicalReady(void)
{
    SystemImuSample sample;
    for (uint32_t index = 0U; index < 4000U; index++)
    {
        Test_Tick();
        if (SystemImu_LatestSampleGet(&sample) == SYSTEM_DEVICE_OK) { return; }
    }
    assert(!"physical MPU never recovered within bounded fixture budget");
}
static void Test_Fault(void)
{
    s_read_failure = 1U; Test_Tick(); s_read_failure = 0U;
    assert(SystemCalibration_IsReady() == 0U ||
        SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED == 0U);
}
void Test_InjectStartStage(unsigned stage)
{
    if (s_inject_stage == stage)
    {
        Test_Fault();
        if (s_inject_lifecycle_fault != 0U) { SystemLifecycle_EnterFault(1U); }
        s_inject_stage = 0U;
    }
}

static void Test_Calibrate(void)
{
#if defined(TEST_CAL_NONE)
    assert(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) == SYSTEM_DEVICE_OK);
#else
    assert(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_OK);
    for (uint32_t index = 0U; index < 2000U; index++)
    {
        Test_Tick(); ImuSampleBus_Process(); SystemCalibration_Process();
        if (SystemCalibration_IsReady() != 0U) { break; }
    }
#endif
    if (SystemCalibration_IsReady() == 0U)
    {
        SystemCalibrationStatus status;
        assert(SystemCalibration_StatusGet(&status) == SYSTEM_DEVICE_OK);
        printf("CAL state=%u wait=%u samples=%lu rejects=%lu min_samples=%u settle=%llu duration=%llu\n",
            (unsigned)status.state, (unsigned)status.wait_reason,
            (unsigned long)status.samples, (unsigned long)status.reject_count,
            (unsigned)SYSTEM_IMU_BIAS_MIN_VALID_SAMPLES,
            (unsigned long long)SYSTEM_IMU_BIAS_SETTLE_TIME_US,
            (unsigned long long)SYSTEM_IMU_BIAS_MIN_DURATION_US);
    }
    assert(SystemCalibration_IsReady() != 0U);
}

static void Test_InterruptedQualification(unsigned which)
{
    if (which == 20U)
    {
        SystemInertialSample old;
        assert(SystemInertial_LatestGet(&old) == SYSTEM_DEVICE_OK);
        assert(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_OK);
        for (unsigned index = 0U; index < 50U; index++)
        { Test_Tick(); ImuSampleBus_Process(); SystemCalibration_Process(); }
        assert(SystemCalibration_IsReady() == 0U);
        Test_Fault(); Test_PhysicalReady();
        SystemCalibration_ImuSampleProcess(&old);
        for (unsigned index = 0U; index < 2200U; index++)
        { Test_Tick(); ImuSampleBus_Process(); SystemCalibration_Process(); }
        assert(SystemCalibration_IsReady() == 0U);
    }
    else
    {
        assert(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
        for (unsigned index = 0U; index < 20U; index++)
        {
            s_test_now += 50000ULL; HostPlatformMock_TimeSetUs(s_test_now);
            s_test_pressure.sequence++; s_test_pressure.timestamp_us = s_test_now;
            s_test_pressure.receive_timestamp_us = s_test_now;
            assert(EstimatorBus_PressurePublish(&s_test_pressure) == ESTIMATOR_BUS_RESULT_OK);
            Test_InsInputFeed(s_test_now, index + 1U); Estimator_OriginWindowCollect();
        }
        assert(s_estimator.baro_window.count > 0U);
        assert(s_estimator.baro_window.count < SYSTEM_ESTIMATOR_BARO_ORIGIN_WINDOW_SAMPLES);
        assert(SystemAlignment_IsReady() == 0U);
        Test_Fault(); Test_PhysicalReady();
        /* Successful status refresh/reset is not a READY result. */
        assert(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
        assert(SystemAlignment_IsReady() == 0U);
    }
    assert(SystemLifecycle_StartTransaction() != SYSTEM_LIFECYCLE_START_OK);
    assert(SystemCalibration_IsReady() == 0U && SystemAlignment_IsReady() == 0U);
    Test_Calibrate();
    assert(s_estimator.baro_window.count == 0U);
}
static void Test_Align(void)
{
    assert(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    /* This calls actual INS strategy and estimator origin collection. */
    Test_Collect(0U);
    assert(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    assert(SystemAlignment_IsReady() != 0U);
    assert(s_estimator.baro_window.count == SYSTEM_ESTIMATOR_BARO_ORIGIN_WINDOW_SAMPLES);
    assert(EstimatorTask_PrepareNavigation() == SYSTEM_DEVICE_OK);
    SystemHealth_Process(); Test_StorageProjectionSet();
    FlightLogRecord drained;
    for (unsigned index = 0U; index < 512U; index++)
    { if (LoggerBus_NextPop(&drained) != LOGGER_BUS_RESULT_OK) { break; } }
    assert(LoggerBus_StreamingReady() == LOGGER_BUS_RESULT_OK);
    assert(SystemLifecycleBackend_StorageReadyGet() != 0U);
    assert(SystemLifecycle_EnterReady() == SYSTEM_DEVICE_OK);
}
static void Test_Boot(unsigned which)
{
    HostPlatformMock_Reset(); SystemLifecycle_Init();
    assert(SystemTime_Init() == SYSTEM_DEVICE_OK);
    assert(SystemLifecycle_EnterSelfTest() == SYSTEM_DEVICE_OK);
    assert(SystemLifecycle_EnterPreflight() == SYSTEM_DEVICE_OK);
    memset(&s_startup_report, 0, sizeof(s_startup_report));
    s_startup_report.completed = 1U; s_startup_report.mission_capable = 1U;
    s_startup_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    for (uint8_t index = 0U; index < SYSTEM_STARTUP_DEVICE_COUNT; index++)
    {
        s_startup_report.devices[index].present = 1U;
        s_startup_report.devices[index].init_result = SYSTEM_DEVICE_OK;
        s_startup_report.devices[index].start_result = SYSTEM_DEVICE_OK;
    }
    SystemHealth_Init(); SystemCalibration_Init(); SystemAlignment_Init();
    assert(ImuSampleBus_Init() == IMU_SAMPLE_BUS_RESULT_OK);
    assert(EstimatorBus_Init() == ESTIMATOR_BUS_RESULT_OK);
    assert(LoggerBus_Init() == LOGGER_BUS_RESULT_OK);
    SystemLogPolicy_Init(); Test_MagStorageInputsLoad();
    s_registers[117] = 104U; s_registers[58] = 1U;
    s_registers[63] = 8U; /* Z raw 2048, real +/-16g conversion. */
    assert(SystemImu_Init() == SYSTEM_DEVICE_CONFIG_DELEGATED);
    SystemDeviceResult start = SystemImu_Start();
    assert(start == SYSTEM_DEVICE_CONFIG_DELEGATED || start == SYSTEM_DEVICE_OK);
    assert(SystemInertial_Init() == SYSTEM_DEVICE_OK);
    if (which == 5U)
    {
        /* Failure before any CAL/source lock, then first physical recovery. */
        s_read_failure = 1U;
        for (unsigned index = 0U; index < 50U; index++) { Test_Tick(); }
        s_read_failure = 0U;
        s_startup_report.mission_capable = 0U;
        s_startup_report.required_failure_mask = 1UL << SYSTEM_STARTUP_DEVICE_IMU;
        s_startup_report.devices[SYSTEM_STARTUP_DEVICE_IMU].init_result = SYSTEM_DEVICE_VERIFY_FAILED;
    }
    Test_PhysicalReady(); Test_Calibrate(); Test_Align();
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    assert(argc == 2); unsigned which = (unsigned)strtoul(argv[1], NULL, 10);
    Test_Boot(which);
    if ((which == 20U) || (which == 21U))
    { Test_InterruptedQualification(which); Test_Align(); }
#if (SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U) && !defined(TEST_EPOCH_DRAFT)
    if (which == 30U)
    {
        /* Sequential ownership regression: no forced scheduling/probe. */
        assert(SystemLifecycle_ConfigurationBegin(SYSTEM_CONFIGURATION_ACTION_ALIGNMENT) == SYSTEM_DEVICE_OK);
        assert(SystemLifecycle_StartTransaction() == SYSTEM_LIFECYCLE_START_BUSY);
        SystemLifecycle_ConfigurationEnd(SYSTEM_CONFIGURATION_ACTION_ALIGNMENT);
        SystemLifecycleStartRequest request = { SYSTEM_START_SOURCE_AIR, 7U };
        assert(SystemLifecycle_SubmitStart(&request) == SYSTEM_DEVICE_OK);
        assert(SystemAlignment_Stop() == SYSTEM_DEVICE_BUSY);
        assert(SystemCalibration_Reset() == SYSTEM_DEVICE_BUSY);
        SystemLifecycle_Process();
        assert(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
        assert(SystemAlignment_Stop() == SYSTEM_DEVICE_BAD_STATE);
        assert(SystemCalibration_Reset() == SYSTEM_DEVICE_BAD_STATE);
        return Test_Finish("mpu_epoch_configuration_start_exclusion");
    }
#endif
    uint8_t source; assert(SystemSourceSelector_ImuActiveInstanceGet(&source) == SYSTEM_DEVICE_OK);
    assert(source == 0U);
    SystemImuSample before, after;
    assert(SystemImu_LatestSampleGet(&before) == SYSTEM_DEVICE_OK);
    if ((which >= 2U) && (which <= 4U))
    {
        Test_Fault();
        assert(SystemHealth_IsReady() == 0U);
        assert(SystemLifecycle_StartTransaction() != SYSTEM_LIFECYCLE_START_OK);
        InsImuSample stale; assert(ImuSampleBus_Pop(&stale) != IMU_SAMPLE_BUS_RESULT_OK);
        Test_PhysicalReady();
        assert(SystemImu_LatestSampleGet(&after) == SYSTEM_DEVICE_OK);
#if (SYSTEM_BUILD_IMU_EPOCH_QUALIFICATION_ENABLED != 0U)
        assert(after.source_id == before.source_id && after.config_epoch > before.config_epoch);
#endif
        assert(SystemCalibration_IsReady() == 0U);
        assert(SystemAlignment_IsReady() == 0U);
        assert(SystemSourceSelector_ImuActiveInstanceGet(&source) == SYSTEM_DEVICE_OK && source == 0U);
#if defined(TEST_CAL_NONE)
        assert(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
        assert(SystemCalibration_IsReady() == 0U);
        assert(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) == SYSTEM_DEVICE_NOT_READY);
        assert(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_UNSUPPORTED);
        assert(SystemLifecycle_StartTransaction() != SYSTEM_LIFECYCLE_START_OK);
        return Test_Finish("mpu_epoch_none_recovery_fail_closed");
#else
        Test_Calibrate();
        if (which >= 3U)
        {
            s_startup_report.mission_capable = 0U;
            s_startup_report.required_failure_mask = 1UL << SYSTEM_STARTUP_DEVICE_IMU;
            if (which == 4U) { s_startup_report.required_failure_mask |= 1UL << SYSTEM_STARTUP_DEVICE_BAROMETER; }
        }
        if (which == 4U)
        {
            assert(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
            Test_Collect(0U); assert(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
            SystemHealth_Process(); assert(SystemHealth_IsReady() == 0U);
            assert(SystemLifecycle_StartTransaction() != SYSTEM_LIFECYCLE_START_OK);
            return Test_Finish("mpu_epoch_other_required_failure_blocked");
        }
        Test_Align();
#endif
    }
    if ((which >= 10U) && (which <= 13U)) { s_inject_stage = which - 9U; }
    if (which == 14U) { s_inject_stage = 4U; s_inject_lifecycle_fault = 1U; }
    SystemLifecycleStartResult result = SystemLifecycle_StartTransaction();
    SystemLifecycleStartDiagnostic diagnostic;
    assert(SystemLifecycle_GetLastStartDiagnostic(SYSTEM_START_SOURCE_LOCAL,
        &diagnostic) != 0U);
    printf("START result=%u reason=%u state=%u\n", (unsigned)result,
        (unsigned)diagnostic.response.reason, (unsigned)SystemLifecycle_GetState());
    if ((which >= 10U) && (which <= 14U))
    {
        assert(s_inject_stage == 0U);
        assert(result != SYSTEM_LIFECYCLE_START_OK);
        assert(SystemLifecycle_GetState() != SYSTEM_STATE_FLIGHT);
        assert(SystemTime_IsMissionStarted() == 0U && s_estimator.mission_running == 0U);
        if (which == 14U) { assert(SystemLifecycle_GetState() == SYSTEM_STATE_FAULT); }
    }
    else
    {
        assert(result == SYSTEM_LIFECYCLE_START_OK);
        assert(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
        assert(s_estimator.baro_origin_valid != 0U && s_estimator.origin_collection_frozen != 0U);
        if (which == 40U)
        {
            s_registers[63] = 127U; s_registers[64] = 255U;
            Test_Tick(); ImuSampleBus_Process(); Test_InsQueuedQualityCheck(1U);
            s_registers[63] = 8U; s_registers[64] = 0U;
            Test_Tick(); ImuSampleBus_Process(); Test_InsQueuedQualityCheck(0U);
            assert(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
            return Test_Finish("mpu_epoch_same_identity_clipped_fault_latches");
        }
        Test_Fault(); Test_PhysicalReady();
        assert(SystemSourceSelector_ImuActiveInstanceGet(&source) == SYSTEM_DEVICE_OK && source == 0U);
        assert(SystemLifecycle_GetState() == SYSTEM_STATE_FLIGHT);
        assert(s_estimator.origin_collection_frozen != 0U);
        assert(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_BAD_STATE);
        assert(SystemAlignment_Start() == SYSTEM_DEVICE_BAD_STATE);
    }
    return Test_Finish("mpu_epoch_actual_start_flow");
}
