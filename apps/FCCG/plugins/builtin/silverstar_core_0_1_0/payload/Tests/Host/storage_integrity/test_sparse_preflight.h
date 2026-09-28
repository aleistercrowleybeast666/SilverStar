/* Host source facades; the native/corrected producers and storage are real. */
#ifndef __TEST_SPARSE_PREFLIGHT_H
#define __TEST_SPARSE_PREFLIGHT_H
#include "device_native_log.h"
#include "imu_sample_bus.h"
#include "project_device_instances.h"
#include "system_calibration.h"
#include "system_lifecycle.h"
static SystemImuSample s_imu[1];
static SystemGnssSample s_gnss[1];
static SystemBarometerSample s_barometer[1];
static SystemMagnetometerSample s_magnetometer[1];
static SystemHardwareQuaternionSample s_attitude[1];
static SystemPowerSample s_power[1];
static SystemInertialSample s_source_sample;
static uint8_t s_source_sample_pending;
static uint32_t s_calibration_steps;
static SystemLifecycleState s_lifecycle = SYSTEM_STATE_PREFLIGHT;
SystemLifecycleState SystemLifecycle_GetState(void) { return s_lifecycle; }
uint8_t ProjectImuInstance_CountGet(void) { return 1U; }
uint8_t ProjectGnssInstance_CountGet(void) { return 1U; }
uint8_t ProjectBarometerInstance_CountGet(void) { return 1U; }
uint8_t ProjectMagnetometerInstance_CountGet(void)
{ return 0U; }
uint8_t ProjectAttitudeInstance_CountGet(void) { return 1U; }
uint8_t ProjectPowerInstance_CountGet(void) { return 1U; }

SystemDeviceResult ProjectDeviceInstance_DescriptorGet(
    SystemDeviceClass device_class, uint8_t instance_id,
    SystemDeviceDescriptor *descriptor)
{
    if ((descriptor == NULL) || (instance_id >= 1U))
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

SystemDeviceResult ProjectImuInstance_LatestSampleGet(
    uint8_t instance_id, SystemImuSample *sample)
{
    if ((sample == NULL) || (instance_id >= 1U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_imu[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectGnssInstance_LatestSampleGet(
    uint8_t instance_id, SystemGnssSample *sample)
{
    if ((sample == NULL) || (instance_id >= 1U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_gnss[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectBarometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemBarometerSample *sample)
{
    if ((sample == NULL) || (instance_id >= 1U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_barometer[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectBarometerInstance_HealthGet(
    uint8_t instance_id, SystemDeviceHealth *health)
{
    if ((health == NULL) || (instance_id != 0U)) { return SYSTEM_DEVICE_NOT_PRESENT; }
    memset(health, 0, sizeof(*health));
    health->healthy = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectMagnetometerInstance_LatestSampleGet(
    uint8_t instance_id, SystemMagnetometerSample *sample)
{
    if ((sample == NULL) || (instance_id >= 1U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_magnetometer[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectAttitudeInstance_LatestSampleGet(
    uint8_t instance_id, SystemHardwareQuaternionSample *sample)
{
    if ((sample == NULL) || (instance_id >= 1U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_attitude[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult ProjectPowerInstance_LatestSampleGet(
    uint8_t instance_id, SystemPowerSample *sample)
{
    if ((sample == NULL) || (instance_id >= 1U))
    { return SYSTEM_DEVICE_NOT_PRESENT; }
    *sample = s_power[instance_id];
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemInertial_NextGet(SystemInertialSample *sample)
{
    if ((sample == NULL) || (s_source_sample_pending == 0U))
    {
        return (sample == NULL) ? SYSTEM_DEVICE_INVALID_ARGUMENT :
                                  SYSTEM_DEVICE_NOT_READY;
    }
    *sample = s_source_sample;
    s_source_sample_pending = 0U;
    return SYSTEM_DEVICE_OK;
}

void SystemCalibration_ImuSampleProcess(
    const SystemInertialSample *sample)
{
    (void)sample;
    s_calibration_steps++;
}

SystemDeviceResult SystemCalibration_StatusGet(
    SystemCalibrationStatus *status)
{
    uint8_t axis;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    (void)memset(status, 0, sizeof(*status));
    status->mode = SYSTEM_CALIBRATION_MODE_NONE;
    status->state = SYSTEM_CALIBRATION_STATE_READY;
    status->ready = 1U;
    status->correction.mode = SYSTEM_CALIBRATION_MODE_NONE;
    status->correction.ready = 1U;
    for (axis = 0U; axis < 3U; axis++)
    {
        status->correction.accel_scale[axis] = 1.0f;
        status->correction.gyro_scale[axis] = 1.0f;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionGet(
    SystemCalibrationImuCorrection *correction)
{
    SystemCalibrationStatus status;
    SystemDeviceResult result;

    if (correction == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    result = SystemCalibration_StatusGet(&status);
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    *correction = status.correction;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Reset(void) { return SYSTEM_DEVICE_OK; }

static void Fixture_SparseFrame(uint32_t frame, uint64_t now)
{
    FlightLogRecord r = {0};
    InsImuSample consumed;
    ImuSampleBusStats stats;
    s_device_steps++;
    s_flight_steps++;
    if (frame == 1U) { Fixture_ResultCheck(LoggerBus_CalibrationResultPush(now, &r.payload.calibration_result)); }
    if (frame == 100U) { Fixture_ResultCheck(LoggerBus_AlignmentResultPush(now, &r.payload.alignment_result)); }
    if (frame == s_preflight_frames)
    {
        s_lifecycle = SYSTEM_STATE_FLIGHT;
        Fixture_ResultCheck(LoggerBus_MissionConfigPush(now));
        Fixture_ResultCheck(LoggerBus_SystemConfigPush(now));
        r.payload.initial_state.q_nb[0] = 1.0f;
        Fixture_ResultCheck(LoggerBus_InitialStatePush(now, &r.payload.initial_state));
        Fixture_ResultCheck(LoggerBus_EventPush(now, FLIGHT_LOG_EVENT_MISSION_START, 0U, 0U));
    }
    if (frame == s_preflight_frames + 2000U)
    {
        s_lifecycle = SYSTEM_STATE_LANDED;
        s_landing_us = now;
        Fixture_ResultCheck(LoggerBus_EventPush(now, FLIGHT_LOG_EVENT_LANDING, 0U, 0U));
        if (LoggerBus_FinalizationArm(now) != LOGGER_BUS_RESULT_OK) { abort(); }
        s_final_armed = 1U;
    }
    s_imu[0].sequence = frame + 1U;
    s_imu[0].sample_timestamp_us = now;
    s_imu[0].receive_timestamp_us = now;
    s_imu[0].valid_mask = 3U;
    s_imu[0].accel_b_mps2[2] = 9.80665f;
    s_barometer[0].sequence = frame / 4U + 1U;
    s_barometer[0].sample_timestamp_us = now;
    s_gnss[0].sequence = frame / 8U + 1U;
    s_gnss[0].sample_timestamp_us = now;
    s_attitude[0].sequence = frame + 1U;
    s_attitude[0].sample_timestamp_us = now;
    s_magnetometer[0].sequence = frame + 1U;
    s_magnetometer[0].sample_timestamp_us = now;
    s_source_sample.sequence = frame + 1U;
    s_source_sample.sample_timestamp_us = now;
    s_source_sample.receive_timestamp_us = now;
    s_source_sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO;
    s_source_sample.accel_b_mps2[2] = 9.80665f;
    s_source_sample_pending = 1U;
    DeviceNativeLog_Process();
    ImuSampleBus_Process();
    /* A consumer receives every sample even throughout the sparse preflight. */
    if (ImuSampleBus_Pop(&consumed) != IMU_SAMPLE_BUS_RESULT_OK || consumed.sequence != frame + 1U) { abort(); }
    ImuSampleBus_StatsGet(&stats);
    if (stats.overflow_count || stats.source_gap_count) { abort(); }
    if (frame % 100U == 0U)
    {
        Fixture_ResultCheck(LoggerBus_PowerPush(now, &r.payload.power));
        Fixture_ResultCheck(LoggerBus_HealthPush(now, &r.payload.health));
        Fixture_ResultCheck(LoggerBus_StatsPush(now, &r.payload.stats));
    }
    if (frame < s_preflight_frames || frame >= s_preflight_frames + 2000U) { return; }
    if (frame % 2U == 0U)
    {
        Fixture_ResultCheck(LoggerBus_InertialIncrementPush(now, frame, &r.payload.inertial_increment));
        Fixture_ResultCheck(LoggerBus_PureInsPush(now, frame, &r.payload.pure_ins));
        Fixture_ResultCheck(LoggerBus_EstimatorPush(now, frame, &r.payload.estimator));
        Fixture_ResultCheck(LoggerBus_Kf6DiagnosticPush(now, frame, &r.payload.kf6_diagnostic));
        Fixture_ResultCheck(LoggerBus_Kf6FullPPush(now, &r.payload.kf6_full_p));
        Fixture_ResultCheck(LoggerBus_BaroMeasurementPush(now, frame, &r.payload.baro_measurement));
    }
    if (frame % 8U == 0U) { Fixture_ResultCheck(LoggerBus_GnssMeasurementPush(now, frame, &r.payload.gnss_measurement)); }
}
#endif
