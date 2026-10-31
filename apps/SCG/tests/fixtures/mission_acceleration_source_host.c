/* Actual runtime collector and correction consumer; provider I/O is injected. */
#include "system_mission_process_runtime.c"
#include <assert.h>
#include <stdio.h>

static SystemInertialSample s_sample;
static SystemCalibrationImuCorrection s_correction;
static SystemDeviceResult s_sample_result = SYSTEM_DEVICE_OK;
static SystemDeviceResult s_correction_result = SYSTEM_DEVICE_OK;
static EstimatorOutputSnapshot s_estimator;
static InsOutputSnapshot s_ins;
static uint8_t s_navigation_ready;

SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{ *sample = s_sample; return s_sample_result; }

SystemDeviceResult SystemCalibration_ImuCorrectionGet(SystemCalibrationImuCorrection *correction)
{ *correction = s_correction; return s_correction_result; }

uint64_t SystemTime_GetMonotonicUs(void) { return 0U; }
uint8_t SystemTime_IsMissionStarted(void) { return 0U; }
SystemLifecycleState SystemLifecycle_GetState(void) { return SYSTEM_STATE_READY; }
void SystemLifecycle_EnterFault(uint32_t reason) { (void)reason; assert(0); }
uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{ *snapshot = s_estimator; return s_navigation_ready; }
uint8_t Ins_GetLatestSnapshot(InsOutputSnapshot *snapshot)
{ *snapshot = s_ins; return s_navigation_ready; }
SystemDeviceResult SystemFlightRecovery_StatusGet(SystemFlightRecoveryStatus *status)
{ (void)status; return SYSTEM_DEVICE_NOT_READY; }
SystemDeviceResult SystemFlightRecovery_StageRecoveryRequest(uint32_t identity)
{ (void)identity; return SYSTEM_DEVICE_NOT_READY; }
LoggerBusResult LoggerBus_EventPush(uint64_t timestamp, FlightLogEventId event,
    uint32_t arg0, uint32_t arg1)
{ (void)timestamp; (void)event; (void)arg0; (void)arg1; return LOGGER_BUS_RESULT_OK; }

static SystemMissionProcessInput Read(void)
{
    SystemMissionProcessInput input;
    (void)memset(&input, 0, sizeof(input));
    SystemMissionProcess_AccelerationRead(&input);
    return input;
}

int main(void)
{
    SystemMissionProcessInput input;
    s_sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL;
    s_sample.sample_timestamp_us = 123456U;
    s_sample.sequence = 17U;
    s_sample.accel_b_mps2[2] = 19.6133f;
    s_correction.ready = 1U;
    for (uint8_t index = 0; index < 3U; index++)
    { s_correction.accel_scale[index] = 1.0f; s_correction.gyro_scale[index] = 1.0f; }
    input = Read();
    assert(input.valid_mask == SYSTEM_MISSION_PROCESS_VALID_ACCEL);
    assert(fabsf(input.acceleration_g - 2.0f) < 0.00001f);
    assert(input.acceleration_timestamp_us == 123456U && input.acceleration_sequence == 17U);
    s_correction.accel_bias_mps2[2] = 9.80665f;
    input = Read();
    assert(fabsf(input.acceleration_g - 1.0f) < 0.00001f);
    s_sample.accel_b_mps2[2] = NAN;
    assert(Read().valid_mask == 0U);
    s_sample.accel_b_mps2[2] = 19.6133f; s_correction.ready = 0U;
    assert(Read().valid_mask == 0U);
    s_correction.ready = 1U; s_sample.valid_mask = 0U;
    assert(Read().valid_mask == 0U);
    s_sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL; s_sample_result = SYSTEM_DEVICE_NOT_READY;
    assert(Read().valid_mask == 0U);
    s_sample_result = SYSTEM_DEVICE_OK; s_correction_result = SYSTEM_DEVICE_NOT_READY;
    assert(Read().valid_mask == 0U);
    (void)memset(&input, 0, sizeof(input)); input.now_us = 200000U;
    s_navigation_ready = 1U;
    s_estimator.initialized = 1U; s_estimator.mission_running = 1U;
    s_estimator.timestamp_us = 150000U;
    SystemMissionProcess_NavigationRead(&input);
    assert(input.ready_function_mask == 8U);
    input.ready_function_mask = 0U; s_estimator.timestamp_us = 50000U;
    SystemMissionProcess_NavigationRead(&input);
    assert(input.ready_function_mask == 0U); /* Old output cannot open a dependency. */
    s_estimator.timestamp_us = 200001U;
    SystemMissionProcess_NavigationRead(&input);
    assert(input.ready_function_mask == 0U);
    s_estimator.timestamp_us = 150000U; s_estimator.mission_running = 0U;
    SystemMissionProcess_NavigationRead(&input);
    assert(input.ready_function_mask == 0U);
    s_ins.timestamp_us = 150000U; s_ins.ins_valid = 1U;
    s_ins.alignment_valid = 1U; s_ins.mission_running = 1U;
    SystemMissionProcess_InsRead(&input);
    assert(input.ready_function_mask == 4U);
    input.ready_function_mask = 0U; s_ins.ins_valid = 0U;
    SystemMissionProcess_InsRead(&input);
    assert(input.ready_function_mask == 0U);
    puts("actual collector: m/s2 to g, calibration, timestamp, unavailable and NaN PASS");
    return 0;
}
