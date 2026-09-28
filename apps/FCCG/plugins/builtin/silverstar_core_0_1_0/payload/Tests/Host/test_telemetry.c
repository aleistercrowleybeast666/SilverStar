#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "air_protocol.h"
#include "estimator_task.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "system_alignment.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_flight_recovery.h"
#include "system_health.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_inertial.h"
#include "system_lifecycle.h"
#include "system_navigation_health.h"
#include "system_sensor_status.h"
#include "system_startup.h"
#include "system_telemetry_transport_if.h"
#include "telemetry_service.h"
#include "test_common.h"

#define TEST_RX_DEPTH 16U
#define TEST_TX_DEPTH 128U

typedef struct
{
    uint8_t data[AIR_MAX_FRAME_LEN];
    uint16_t length;
} TestFrame;

static TestFrame s_rx[TEST_RX_DEPTH];
static uint8_t s_rx_head;
static uint8_t s_rx_tail;
static TestFrame s_tx[TEST_TX_DEPTH];
static uint8_t s_tx_count;
static uint64_t s_now_us;
static SystemLifecycleState s_lifecycle_state;
static SystemGnssSample s_gnss_sample;
static SystemImuSample s_imu_sample;
static SystemStartupReport s_startup_report;
static SystemCalibrationStatus s_calibration_status;
static SystemAlignmentStatus s_alignment_status;
static SystemFlightRecoveryStatus s_flight_recovery_status;
static SystemCalibrationImuCorrection s_calibration_correction;
static SystemHealthSnapshot s_health_snapshot;
static SystemDeviceResult s_calibration_status_result;
static SystemDeviceResult s_calibration_correction_result;
static SystemDeviceResult s_alignment_status_result;
static SystemDeviceResult s_alignment_start_result;
static SystemDeviceResult s_start_submit_result;
static SystemLifecycleStartResult s_start_readiness_result;
static SystemLifecycleStartReason s_start_readiness_reason;
static SystemLifecycleStartResponse s_start_response;
static uint8_t s_start_response_pending;
static uint8_t s_start_complete_during_submit;
static uint8_t s_quaternion_available;
static uint32_t s_calibration_start_count;
static uint32_t s_calibration_reset_count;
static uint32_t s_alignment_start_count;
static uint32_t s_start_submit_count;
static uint32_t s_start_response_pop_count;
static uint8_t s_sensor_summary_flags;
static SystemSensorStatus s_sensor_snapshot[4];
static SystemSensorStatusSnapshotInfo s_sensor_snapshot_info;
static uint32_t s_sensor_snapshot_capture_count;
static SystemDeviceResult s_transport_send_result;
static EstimatorPreparationSnapshot s_navigation_preparation;
static SystemNavigationGroupHealth s_navigation_health[SYSTEM_NAVIGATION_GROUP_COUNT];

SystemDeviceResult EstimatorTask_PreparationGet(EstimatorPreparationSnapshot *snapshot)
{
    if (snapshot == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *snapshot = s_navigation_preparation;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemNavigationHealth_GroupGet(uint8_t group,
    uint64_t evaluation_us, SystemNavigationGroupHealth *snapshot)
{
    if ((group >= SYSTEM_NAVIGATION_GROUP_COUNT) || (snapshot == NULL) || (evaluation_us == 0ULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *snapshot = s_navigation_health[group];
    return SYSTEM_DEVICE_OK;
}

static uint8_t Test_Next(uint8_t index, uint8_t depth)
{
    index++;
    return (index >= depth) ? 0U : index;
}

static void Test_PutU32Le(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
    data[2] = (uint8_t)(value >> 16U);
    data[3] = (uint8_t)(value >> 24U);
}

static uint32_t Test_GetU32Le(const uint8_t *data)
{
    return (uint32_t)data[0] |
           ((uint32_t)data[1] << 8U) |
           ((uint32_t)data[2] << 16U) |
           ((uint32_t)data[3] << 24U);
}

static int16_t Test_GetI16Le(const uint8_t *data)
{
    return (int16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8U));
}

static void Test_CommandQueue(uint8_t sequence,
                              uint8_t command_id,
                              uint32_t token,
                              uint8_t param0,
                              uint8_t param1)
{
    uint8_t next = Test_Next(s_rx_head, TEST_RX_DEPTH);

    TEST_CHECK(next != s_rx_tail);
    if (next == s_rx_tail) { return; }
    (void)memset(&s_rx[s_rx_head], 0, sizeof(s_rx[s_rx_head]));
    s_rx[s_rx_head].data[0] = AIR_TYPE_CMD;
    s_rx[s_rx_head].data[1] = sequence;
    s_rx[s_rx_head].data[2] = command_id;
    Test_PutU32Le(&s_rx[s_rx_head].data[3], token);
    s_rx[s_rx_head].data[7] = param0;
    s_rx[s_rx_head].data[8] = param1;
    s_rx[s_rx_head].length = AIR_CMD_LEN;
    s_rx_head = next;
}

static uint8_t Test_TypeCount(uint8_t type)
{
    uint8_t index;
    uint8_t count = 0U;

    for (index = 0U; index < s_tx_count; index++)
    {
        if (s_tx[index].data[0] == type) { count++; }
    }
    return count;
}

static uint8_t Test_StatusIdCount(uint8_t status_id)
{
    uint8_t index;
    uint8_t count = 0U;

    for (index = 0U; index < s_tx_count; index++)
    {
        if ((s_tx[index].data[0] == AIR_TYPE_STATUS) &&
            (s_tx[index].data[2] == status_id))
        {
            count++;
        }
    }
    return count;
}

static const TestFrame *Test_LastTypeGet(uint8_t type)
{
    uint8_t index = s_tx_count;

    while (index > 0U)
    {
        index--;
        if (s_tx[index].data[0] == type) { return &s_tx[index]; }
    }
    return NULL;
}

static const TestFrame *Test_LastStatusGet(uint8_t status_id)
{
    uint8_t index = s_tx_count;

    while (index > 0U)
    {
        index--;
        if ((s_tx[index].data[0] == AIR_TYPE_STATUS) &&
            (s_tx[index].data[2] == status_id))
        {
            return &s_tx[index];
        }
    }
    return NULL;
}

static void Test_SensorSnapshotTransactionCheck(uint8_t snapshot_id,
                                                uint8_t terminal_state)
{
    static const uint8_t expected_ids[4] =
    {
        SILVERSTAR_SENSOR_ID_IMU,
        SILVERSTAR_SENSOR_ID_GNSS,
        SILVERSTAR_SENSOR_ID_BAROMETER,
        SILVERSTAR_SENSOR_ID_VISION
    };
    uint8_t first = 0xFFU;
    uint8_t terminal = 0xFFU;
    uint8_t sensor_count = 0U;
    uint8_t index;

    for (index = 0U; index < s_tx_count; index++)
    {
        if ((s_tx[index].data[0] == AIR_TYPE_SENSOR_STATUS) &&
            (s_tx[index].data[2] == snapshot_id))
        {
            if (first == 0xFFU) { first = index; }
            TEST_CHECK(s_tx[index].length == AIR_SENSOR_STATUS_LEN);
            TEST_CHECK(s_tx[index].data[3] == expected_ids[sensor_count]);
            TEST_CHECK(s_tx[index].data[7] == sensor_count);
            TEST_CHECK(s_tx[index].data[8] == 4U);
            sensor_count++;
        }
        if ((s_tx[index].data[0] == AIR_TYPE_STATUS) &&
            (s_tx[index].data[2] == AIR_STATUS_ALIGNMENT) &&
            (s_tx[index].data[7] == terminal_state) &&
            (s_tx[index].data[8] == snapshot_id))
        {
            terminal = index;
        }
    }
    TEST_CHECK(sensor_count == 4U);
    TEST_CHECK(first != 0xFFU);
    TEST_CHECK(terminal == (uint8_t)(first + sensor_count));
}

static const TestFrame *Test_AckGet(uint8_t command_sequence,
                                    uint8_t command_id)
{
    uint8_t index = s_tx_count;

    while (index > 0U)
    {
        index--;
        if ((s_tx[index].data[0] == AIR_TYPE_ACK) &&
            (s_tx[index].data[2] == command_sequence) &&
            (s_tx[index].data[3] == command_id))
        {
            return &s_tx[index];
        }
    }
    return NULL;
}

static uint8_t Test_AckCount(uint8_t command_sequence,
                             uint8_t command_id)
{
    uint8_t index;
    uint8_t count = 0U;

    for (index = 0U; index < s_tx_count; index++)
    {
        if ((s_tx[index].data[0] == AIR_TYPE_ACK) &&
            (s_tx[index].data[2] == command_sequence) &&
            (s_tx[index].data[3] == command_id))
        {
            count++;
        }
    }
    return count;
}

static SystemDeviceResult Mock_TransportInit(void) { return SYSTEM_DEVICE_OK; }
static SystemDeviceResult Mock_TransportStart(void) { return SYSTEM_DEVICE_OK; }
static SystemDeviceResult Mock_TransportStop(void) { return SYSTEM_DEVICE_OK; }
static void Mock_TransportProcess(void) { }

static SystemDeviceResult Mock_TransportSend(const uint8_t *data,
                                              uint16_t length)
{
    if ((data == NULL) || (length == 0U) || (s_tx_count >= TEST_TX_DEPTH))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_transport_send_result != SYSTEM_DEVICE_OK)
    {
        return s_transport_send_result;
    }
    (void)memcpy(s_tx[s_tx_count].data, data, length);
    s_tx[s_tx_count].length = length;
    s_tx_count++;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_TransportReceive(uint8_t *data,
                                                 uint16_t capacity,
                                                 uint16_t *length)
{
    if ((data == NULL) || (length == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (s_rx_tail == s_rx_head) { return SYSTEM_DEVICE_NOT_READY; }
    if (capacity < s_rx[s_rx_tail].length)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *length = s_rx[s_rx_tail].length;
    (void)memcpy(data, s_rx[s_rx_tail].data, *length);
    s_rx_tail = Test_Next(s_rx_tail, TEST_RX_DEPTH);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_TransportInfo(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_TransportCapabilities(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_TELEM_CAP_TX | SYSTEM_TELEM_CAP_RX |
            SYSTEM_TELEM_CAP_LINK_CRC;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_TransportHealth(SystemTelemetryHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_TransportSelfTest(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_TransportMtu(uint16_t *mtu)
{
    if (mtu == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mtu = 64U;
    return SYSTEM_DEVICE_OK;
}

const char *SystemTelemetry_NameGet(void) { return "Mock Transport"; }
SystemDeviceResult SystemTelemetry_Init(void) { return Mock_TransportInit(); }
SystemDeviceResult SystemTelemetry_Start(void) { return Mock_TransportStart(); }
SystemDeviceResult SystemTelemetry_Stop(void) { return Mock_TransportStop(); }
SystemDeviceResult SystemTelemetry_Send(
    const uint8_t *data, uint16_t length)
{ return Mock_TransportSend(data, length); }
SystemDeviceResult SystemTelemetry_Receive(
    uint8_t *data, uint16_t capacity, uint16_t *length)
{ return Mock_TransportReceive(data, capacity, length); }
void SystemTelemetry_Process(void) { Mock_TransportProcess(); }
SystemDeviceResult SystemTelemetry_InfoGet(SystemDeviceInfo *info)
{ return Mock_TransportInfo(info); }
SystemDeviceResult SystemTelemetry_CapabilitiesGet(uint32_t *mask)
{ return Mock_TransportCapabilities(mask); }
SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{ return Mock_TransportHealth(health); }
SystemDeviceResult SystemTelemetry_SelfTestRun(
    SystemDeviceSelfTestResult *result)
{ return Mock_TransportSelfTest(result); }
SystemDeviceResult SystemTelemetry_MtuGet(uint16_t *mtu)
{ return Mock_TransportMtu(mtu); }

static SystemDeviceResult Mock_GnssSample(SystemGnssSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_gnss_sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemGnss_LatestSampleGet(SystemGnssSample *sample)
{ return Mock_GnssSample(sample); }

static SystemDeviceResult Mock_ImuSample(SystemImuSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_imu_sample;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemImu_LatestSampleGet(SystemImuSample *sample)
{ return Mock_ImuSample(sample); }
SystemDeviceResult SystemImu_IoDetailGet(SystemImuIoDetail *detail)
{
    (void)memset(detail, 0, sizeof(*detail));
    detail->config_generation = 5U;
    detail->config_generation_valid = 1U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemImu_EffectiveConfigGet(SystemImuConfig *config)
{
    (void)memset(config, 0, sizeof(*config));
    config->requested_mask = SYSTEM_IMU_CFG_GYRO_RANGE | SYSTEM_IMU_CFG_ACCEL_RANGE;
    config->gyro_range_dps = 2000.0f;
    config->accel_range_g = 16.0f;
    return SYSTEM_DEVICE_OK;
}
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
LoggerBusResult LoggerBus_DiagnosticsGet(LoggerBusDiagnostics *diagnostics)
{
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->overflow_count = 70000U;
    diagnostics->normal_high_water = 17U;
    return LOGGER_BUS_RESULT_OK;
}
#endif
SystemDeviceResult SystemImu_NextSampleGet(SystemImuSample *sample)
{ return Mock_ImuSample(sample); }

static SystemDeviceResult Mock_QuaternionSample(
    SystemHardwareQuaternionSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_quaternion_available == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->quaternion_wxyz[0] = 1.0f;
    sample->sequence = 1U;
    sample->mode = SYSTEM_HW_QUAT_MODE_9AXIS;
    sample->mode_verified = 1U;
    sample->algorithm_healthy = 1U;
    sample->normalized = 1U;
    sample->valid = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample)
{ return Mock_QuaternionSample(sample); }

static SystemDeviceResult Mock_BarometerInfo(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(info, 0, sizeof(*info));
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_BarometerCapabilities(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_FIELD_PRESSURE | SYSTEM_BARO_FIELD_ALTITUDE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_BarometerHealth(SystemDeviceHealth *health)
{
    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(health, 0, sizeof(*health));
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Mock_BarometerSample(SystemBarometerSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    return SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult Mock_BarometerSelfTest(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_BarometerConfigApply(
    const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report)
{
    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(report, 0, sizeof(*report));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_BarometerConfigGet(
    SystemBarometerConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(config, 0, sizeof(*config));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Mock_BarometerNoiseGet(
    SystemBarometerNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult SystemBarometer_InfoGet(SystemDeviceInfo *info)
{ return Mock_BarometerInfo(info); }
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *mask)
{ return Mock_BarometerCapabilities(mask); }
SystemDeviceResult SystemBarometer_HealthGet(SystemDeviceHealth *health)
{ return Mock_BarometerHealth(health); }
SystemDeviceResult SystemBarometer_LatestSampleGet(
    SystemBarometerSample *sample)
{ return Mock_BarometerSample(sample); }
SystemDeviceResult SystemBarometer_SelfTestRun(
    SystemDeviceSelfTestResult *result)
{ return Mock_BarometerSelfTest(result); }
SystemDeviceResult SystemBarometer_ConfigApply(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{ return Mock_BarometerConfigApply(config, report); }
SystemDeviceResult SystemBarometer_ConfigVerify(
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{ return Mock_BarometerConfigApply(config, report); }
SystemDeviceResult SystemBarometer_EffectiveConfigGet(
    SystemBarometerConfig *config)
{ return Mock_BarometerConfigGet(config); }
SystemDeviceResult SystemBarometer_NoiseCharacteristicsGet(
    SystemBarometerNoiseCharacteristics *noise)
{ return Mock_BarometerNoiseGet(noise); }

SystemDeviceResult SystemInertial_LatestGet(SystemInertialSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = s_imu_sample.sample_timestamp_us;
    sample->receive_timestamp_us = s_imu_sample.receive_timestamp_us;
    sample->sequence = s_imu_sample.sequence;
    (void)memcpy(sample->accel_raw, s_imu_sample.accel_raw,
                 sizeof(sample->accel_raw));
    (void)memcpy(sample->gyro_raw, s_imu_sample.gyro_raw,
                 sizeof(sample->gyro_raw));
    (void)memcpy(sample->accel_b_mps2, s_imu_sample.accel_b_mps2,
                 sizeof(sample->accel_b_mps2));
    (void)memcpy(sample->gyro_b_radps, s_imu_sample.gyro_b_radps,
                 sizeof(sample->gyro_b_radps));
    sample->temperature_c = s_imu_sample.temperature_c;
    sample->valid_mask = s_imu_sample.valid_mask;
    return SYSTEM_DEVICE_OK;
}

SystemAlignmentSourceMask SystemAlignment_CapabilityMaskGet(void)
{
    return SYSTEM_ALIGNMENT_AIR_PROFILE_0_SOURCE_MASK;
}

uint8_t SystemSensorStatus_SummaryFlagsGet(void)
{
    return s_sensor_summary_flags;
}

SystemDeviceResult SystemSensorStatus_SnapshotCapture(uint8_t alignment_state)
{
    s_sensor_snapshot_capture_count++;
    s_sensor_snapshot_info.sequence++;
    s_sensor_snapshot_info.snapshot_id++;
    s_sensor_snapshot_info.total = 4U;
    s_sensor_snapshot_info.alignment_state = alignment_state;
    s_sensor_snapshot_info.valid = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemSensorStatus_SnapshotInfoGet(
    SystemSensorStatusSnapshotInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *info = s_sensor_snapshot_info;
    return (info->valid != 0U) ? SYSTEM_DEVICE_OK :
                                SYSTEM_DEVICE_NOT_READY;
}

SystemDeviceResult SystemSensorStatus_SnapshotGet(
    uint8_t index,
    SystemSensorStatus *status)
{
    if ((status == NULL) || (index >= s_sensor_snapshot_info.total))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *status = s_sensor_snapshot[index];
    return SYSTEM_DEVICE_OK;
}

uint64_t SystemTime_GetMonotonicUs(void) { return s_now_us; }
uint8_t SystemTime_IsMissionStarted(void)
{ return (uint8_t)(s_lifecycle_state >= SYSTEM_STATE_FLIGHT); }
uint64_t SystemTime_GetMissionUs(void) { return s_now_us; }
SystemLifecycleState SystemLifecycle_GetState(void)
{ return s_lifecycle_state; }

SystemDeviceResult SystemFlightRecovery_StatusGet(
    SystemFlightRecoveryStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *status = s_flight_recovery_status;
    return SYSTEM_DEVICE_OK;
}

SystemLifecycleStartResult SystemLifecycle_StartReadinessGet(
    SystemLifecycleStartReason *reason)
{
    if (reason != NULL) { *reason = s_start_readiness_reason; }
    return s_start_readiness_result;
}

const SystemStartupReport *SystemStartup_GetReport(void)
{ return &s_startup_report; }

SystemDeviceResult SystemCalibration_StatusGet(SystemCalibrationStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_calibration_status_result != SYSTEM_DEVICE_OK)
    { return s_calibration_status_result; }
    *status = s_calibration_status;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionGet(
    SystemCalibrationImuCorrection *correction)
{
    if (correction == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_calibration_correction_result != SYSTEM_DEVICE_OK)
    { return s_calibration_correction_result; }
    *correction = s_calibration_correction;
    return SYSTEM_DEVICE_OK;
}

void SystemHealth_GetSnapshot(SystemHealthSnapshot *snapshot)
{
    if (snapshot != NULL) { *snapshot = s_health_snapshot; }
}

SystemDeviceResult SystemCalibration_Start(SystemCalibrationMode mode)
{
    s_calibration_start_count++;
    (void)memset(&s_calibration_status, 0,
                 sizeof(s_calibration_status));
    s_calibration_status.mode = mode;
    s_calibration_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.state = (mode == SYSTEM_CALIBRATION_MODE_NONE) ?
        SYSTEM_CALIBRATION_STATE_READY :
        ((mode == SYSTEM_CALIBRATION_MODE_SIX_FACE) ?
            SYSTEM_CALIBRATION_STATE_WAIT_FACE :
            SYSTEM_CALIBRATION_STATE_COLLECTING);
    s_calibration_status.ready = (uint8_t)(mode == SYSTEM_CALIBRATION_MODE_NONE);
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_alignment_status.ready = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_FaceCollect(SystemCalibrationFace face)
{
    s_calibration_status.current_face = face;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_COLLECTING;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Stop(void)
{
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_IDLE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Reset(void)
{
    s_calibration_reset_count++;
    (void)memset(&s_calibration_status, 0,
                 sizeof(s_calibration_status));
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_IDLE;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_alignment_status.ready = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_StatusGet(SystemAlignmentStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_alignment_status_result != SYSTEM_DEVICE_OK)
    { return s_alignment_status_result; }
    *status = s_alignment_status;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_SummaryGet(SystemAlignmentSummary *summary)
{
    const SystemAlignmentSourceStatus *attitude;

    if (summary == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_alignment_status_result != SYSTEM_DEVICE_OK)
    { return s_alignment_status_result; }
    (void)memset(summary, 0, sizeof(*summary));
    summary->start_sequence = s_alignment_status.start_sequence;
    summary->selected_mask = s_alignment_status.selected_mask;
    summary->required_mask = s_alignment_status.required_mask;
    summary->ready_mask = s_alignment_status.ready_mask;
    summary->state = s_alignment_status.state;
    summary->stale_reason = s_alignment_status.stale_reason;
    summary->ready = s_alignment_status.ready;
    attitude = &s_alignment_status.component[
        SYSTEM_ALIGNMENT_SOURCE_ATTITUDE];
    summary->preflight_attitude_source =
        ((s_alignment_status.state != SYSTEM_ALIGNMENT_STATE_STALE) &&
         (attitude->ready != 0U) &&
         (attitude->detail.attitude.attitude_ready != 0U) &&
         (attitude->detail.attitude.quaternion_valid != 0U) &&
         (attitude->detail.attitude.final_quaternion_frozen != 0U)) ?
            SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT :
            SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_PreflightQuaternionGet(
    float quaternion_wxyz[4],
    SystemAlignmentPreflightAttitudeSource *source)
{
    SystemAlignmentSummary summary;
    SystemHardwareQuaternionSample sample;

    if ((quaternion_wxyz == NULL) || (source == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if ((s_lifecycle_state != SYSTEM_STATE_PREFLIGHT) &&
        (s_lifecycle_state != SYSTEM_STATE_READY))
    { return SYSTEM_DEVICE_BAD_STATE; }
    if (SystemAlignment_SummaryGet(&summary) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_READY; }
    if (summary.preflight_attitude_source ==
        SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT)
    {
        (void)memcpy(quaternion_wxyz,
            s_alignment_status.component[
                SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
                .detail.attitude.quaternion_wxyz,
            sizeof(float) * 4U);
        *source = SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT;
        return SYSTEM_DEVICE_OK;
    }
    if (Mock_QuaternionSample(&sample) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_NOT_READY; }
    (void)memcpy(quaternion_wxyz, sample.quaternion_wxyz,
                 sizeof(float) * 4U);
    *source = SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Start(void)
{
    s_alignment_start_count++;
    if (s_alignment_start_result != SYSTEM_DEVICE_OK)
    { return s_alignment_start_result; }
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
    s_alignment_status.ready = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Stop(void)
{
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    s_alignment_status.ready = 0U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Reset(void)
{
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    (void)memset(&s_flight_recovery_status, 0,
                 sizeof(s_flight_recovery_status));
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemLifecycle_SubmitStart(
    const SystemLifecycleStartRequest *request)
{
    if (request == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    s_start_submit_count++;
    if (s_start_submit_result != SYSTEM_DEVICE_OK)
    { return s_start_submit_result; }
    s_start_response.source = request->source;
    s_start_response.request_id = request->request_id;
    s_start_response.timestamp_us = s_now_us;
    s_start_response_pending = 1U;
    if ((s_start_complete_during_submit != 0U) &&
        (s_start_response.result == SYSTEM_LIFECYCLE_START_OK))
    {
        s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    }
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemLifecycle_TryGetStartResponse(
    SystemLifecycleStartResponse *response)
{
    if ((response == NULL) || (s_start_response_pending == 0U)) { return 0U; }
    *response = s_start_response;
    s_start_response_pending = 0U;
    s_start_response_pop_count++;
    if (response->result == SYSTEM_LIFECYCLE_START_OK)
    { s_lifecycle_state = SYSTEM_STATE_FLIGHT; }
    return 1U;
}

uint8_t Estimator_GetLatestSnapshot(EstimatorOutputSnapshot *snapshot)
{
    if (snapshot == NULL) { return 0U; }
    (void)memset(snapshot, 0, sizeof(*snapshot));
    snapshot->q_nb[0] = 1.0f;
    snapshot->velocity_enu_mps[0] = 1.25f;
    snapshot->position_enu_m[2] = -3.5f;
    return 1U;
}

static void Test_Reset(void)
{
    (void)memset(&s_navigation_preparation, 0, sizeof(s_navigation_preparation));
    (void)memset(s_navigation_health, 0, sizeof(s_navigation_health));
    (void)memset(s_rx, 0, sizeof(s_rx));
    (void)memset(s_tx, 0, sizeof(s_tx));
    (void)memset(&s_gnss_sample, 0, sizeof(s_gnss_sample));
    (void)memset(&s_imu_sample, 0, sizeof(s_imu_sample));
    (void)memset(&s_startup_report, 0, sizeof(s_startup_report));
    (void)memset(&s_calibration_status, 0, sizeof(s_calibration_status));
    (void)memset(&s_alignment_status, 0, sizeof(s_alignment_status));
    (void)memset(&s_calibration_correction, 0,
                 sizeof(s_calibration_correction));
    (void)memset(&s_health_snapshot, 0, sizeof(s_health_snapshot));
    (void)memset(&s_start_response, 0, sizeof(s_start_response));
    (void)memset(s_sensor_snapshot, 0, sizeof(s_sensor_snapshot));
    (void)memset(&s_sensor_snapshot_info, 0,
                 sizeof(s_sensor_snapshot_info));
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_tx_count = 0U;
    s_now_us = 1000ULL;
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    s_calibration_status_result = SYSTEM_DEVICE_NOT_READY;
    s_calibration_correction_result = SYSTEM_DEVICE_NOT_READY;
    s_alignment_status_result = SYSTEM_DEVICE_NOT_READY;
    s_alignment_start_result = SYSTEM_DEVICE_OK;
    s_start_submit_result = SYSTEM_DEVICE_OK;
    s_start_readiness_result = SYSTEM_LIFECYCLE_START_OK;
    s_start_readiness_reason = SYSTEM_START_REASON_NONE;
    s_start_response.result = SYSTEM_LIFECYCLE_START_OK;
    s_start_response.reason = SYSTEM_START_REASON_NONE;
    s_start_response_pending = 0U;
    s_start_complete_during_submit = 0U;
    s_quaternion_available = 0U;
    s_calibration_start_count = 0U;
    s_calibration_reset_count = 0U;
    s_alignment_start_count = 0U;
    s_start_submit_count = 0U;
    s_start_response_pop_count = 0U;
    s_sensor_summary_flags = AIR_SENSOR_SUMMARY_IMU_PRESENT |
        AIR_SENSOR_SUMMARY_GNSS_PRESENT |
        AIR_SENSOR_SUMMARY_AUX_SENSOR_PRESENT |
        AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED;
    s_sensor_snapshot_capture_count = 0U;
    s_sensor_snapshot[0].sensor_id = SILVERSTAR_SENSOR_ID_IMU;
    s_sensor_snapshot[0].status_flags = SYSTEM_SENSOR_STATUS_REGISTERED;
    s_sensor_snapshot[1].sensor_id = SILVERSTAR_SENSOR_ID_GNSS;
    s_sensor_snapshot[1].status_flags = SYSTEM_SENSOR_STATUS_REGISTERED;
    s_sensor_snapshot[2].sensor_id = SILVERSTAR_SENSOR_ID_BAROMETER;
    s_sensor_snapshot[2].status_flags = SYSTEM_SENSOR_STATUS_REGISTERED;
    s_sensor_snapshot[3].sensor_id = SILVERSTAR_SENSOR_ID_VISION;
    s_sensor_snapshot[3].instance_id = 1U;
    s_sensor_snapshot[3].status_flags = SYSTEM_SENSOR_STATUS_REGISTERED;
    s_transport_send_result = SYSTEM_DEVICE_OK;
    s_imu_sample.valid_mask = SYSTEM_IMU_VALID_ACCEL | SYSTEM_IMU_VALID_GYRO;
    s_imu_sample.accel_b_mps2[0] = AIR_STANDARD_GRAVITY_MPS2;
    s_calibration_correction.mode = SYSTEM_CALIBRATION_MODE_NONE;
    s_calibration_correction.ready = 1U;
    s_calibration_correction.accel_scale[0] = 1.0f;
    s_calibration_correction.accel_scale[1] = 1.0f;
    s_calibration_correction.accel_scale[2] = 1.0f;
    s_calibration_correction.gyro_scale[0] = 1.0f;
    s_calibration_correction.gyro_scale[1] = 1.0f;
    s_calibration_correction.gyro_scale[2] = 1.0f;
    TEST_CHECK(TelemetryService_Init() == SYSTEM_DEVICE_OK);
}

static uint8_t Test_InitialCapabilitySend(void)
{
    const TestFrame *frame = NULL;
    uint8_t index;

    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        frame = Test_LastTypeGet(AIR_TYPE_CAPABILITY);
        if (frame != NULL) { break; }
    }
    TEST_CHECK(frame != NULL);
    if (frame == NULL) { return 0U; }
    TEST_CHECK(frame->length == AIR_CAPABILITY_LEN);
    TEST_CHECK(frame->data[2] == AIR_PROFILE_COMPACT_V0);
    TEST_CHECK(frame->data[3] == AIR_COMMAND_POLICY_PREFLIGHT_ONLY);
    TEST_CHECK(frame->data[4] == (SYSTEM_CALIBRATION_CAPABILITY_NONE |
        SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK));
    TEST_CHECK(frame->data[6] == AIR_ACCEL_FULL_SCALE_G);
    TEST_CHECK(frame->data[7] == 0xD0U && frame->data[8] == 0x07U);
    return frame->data[1];
}

static void Test_CapabilityAck(uint8_t command_sequence,
                               uint8_t capability_sequence)
{
    const TestFrame *ack;

    Test_CommandQueue(command_sequence, AIR_CMD_CAPABILITY_ACK, 0U,
                      capability_sequence, AIR_PROFILE_COMPACT_V0);
    TelemetryService_Process();
    ack = Test_LastTypeGet(AIR_TYPE_ACK);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[2] == command_sequence);
    TEST_CHECK(ack->data[3] == AIR_CMD_CAPABILITY_ACK);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_OK);
}

static void Test_Authorize(void)
{
    uint8_t capability_sequence = Test_InitialCapabilitySend();

    Test_CapabilityAck(2U, capability_sequence);
    Test_CommandQueue(3U, AIR_CMD_UNLOCK, AIR_TOKEN_UNLOCK, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] == AIR_ACK_RESULT_OK);
}

static void Test_CapabilityHandshake(void)
{
    TelemetryServiceDiagnostics diagnostics;
    const TestFrame *capability;
    uint8_t first_sequence;
    uint8_t latest_sequence;

    Test_Reset();
    first_sequence = Test_InitialCapabilitySend();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_CAPABILITY)->data[5] ==
               AIR_SENSOR_SUMMARY_MASK_ALL);
    s_now_us += SYSTEM_TELEMETRY_CAPABILITY_PERIOD_US - 1ULL;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_CAPABILITY) == 1U);
    s_now_us++;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_CAPABILITY) == 2U);
    capability = Test_LastTypeGet(AIR_TYPE_CAPABILITY);
    latest_sequence = capability->data[1];

    Test_CommandQueue(10U, AIR_CMD_CAPABILITY_ACK, 0U,
                      first_sequence, AIR_PROFILE_COMPACT_V0);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_BAD_PARAM);
    Test_CommandQueue(11U, AIR_CMD_CAPABILITY_ACK, 0U,
                      latest_sequence, 1U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_BAD_PARAM);
    Test_CapabilityAck(12U, latest_sequence);
    s_now_us += 2ULL * SYSTEM_TELEMETRY_CAPABILITY_PERIOD_US;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_CAPABILITY) == 2U);

    Test_CommandQueue(13U, AIR_CMD_CAPABILITY_ACK, 0U,
                      latest_sequence, AIR_PROFILE_COMPACT_V0);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_BAD_STATE);

    TelemetryService_DiagnosticsGet(&diagnostics);
    TEST_CHECK(diagnostics.capability_state == TELEMETRY_CAPABILITY_ACKED);
    TEST_CHECK(diagnostics.capability_acked == 1U);
    TEST_CHECK(diagnostics.capability_tx_count == 2U);
}

static void Test_DynamicCapabilityMask(void)
{
    const TestFrame *capability;

    Test_Reset();
    s_sensor_summary_flags = AIR_SENSOR_SUMMARY_IMU_PRESENT |
        AIR_SENSOR_SUMMARY_AUX_SENSOR_PRESENT |
        AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED;
    s_startup_report.completed = 1U;
    s_startup_report.device_count = SYSTEM_STARTUP_DEVICE_COUNT;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION].
        device_id = SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION].
        present = 1U;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION].
        init_result = SYSTEM_DEVICE_OK;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION].
        start_result = SYSTEM_DEVICE_OK;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER].device_id =
        SYSTEM_STARTUP_DEVICE_BAROMETER;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER].present = 1U;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER].init_result =
        SYSTEM_DEVICE_OK;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER].start_result =
        SYSTEM_DEVICE_OK;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].device_id =
        SYSTEM_STARTUP_DEVICE_GNSS;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].present = 1U;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].init_result =
        SYSTEM_DEVICE_OK;
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].start_result =
        SYSTEM_DEVICE_NOT_READY;
    (void)Test_InitialCapabilitySend();
    capability = Test_LastTypeGet(AIR_TYPE_CAPABILITY);
    TEST_CHECK(capability->data[5] ==
        (AIR_SENSOR_SUMMARY_IMU_PRESENT |
         AIR_SENSOR_SUMMARY_AUX_SENSOR_PRESENT |
         AIR_SENSOR_SUMMARY_SNAPSHOT_SUPPORTED));
}

static void Test_UnackedPermission(void)
{
    uint8_t capability_sequence;

    Test_Reset();
    capability_sequence = Test_InitialCapabilitySend();
    Test_CommandQueue(20U, AIR_CMD_CAL_START, AIR_TOKEN_CALIBRATION,
                      AIR_CALIBRATION_MODE_NONE, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_CAPABILITY_REQUIRED);
    TEST_CHECK(s_calibration_start_count == 0U);
    Test_CommandQueue(21U, AIR_CMD_PING, 0U, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] == AIR_ACK_RESULT_OK);
    Test_CapabilityAck(22U, capability_sequence);
}

static void Test_PreflightState(void)
{
    TelemetryServiceDiagnostics diagnostics;
    const TestFrame *state;
    uint8_t count;
    uint8_t index;

    Test_Reset();
    Test_CapabilityAck(30U, Test_InitialCapabilitySend());
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_quaternion_available = 1U;
    s_imu_sample.accel_b_mps2[0] = AIR_STANDARD_GRAVITY_MPS2;
    s_imu_sample.accel_b_mps2[2] = -AIR_STANDARD_GRAVITY_MPS2;
    s_imu_sample.gyro_b_radps[1] = 17.4532925f;
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        if (Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE) != NULL) { break; }
    }
    state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK(state != NULL);
    TEST_CHECK(state->length == AIR_PREFLIGHT_STATE_LEN);
    TEST_CHECK(Test_GetI16Le(&state->data[6]) == 2048);
    TEST_CHECK(Test_GetI16Le(&state->data[10]) == -2048);
    TEST_CHECK(Test_GetI16Le(&state->data[14]) == 16384);
    TEST_CHECK(Test_GetI16Le(&state->data[18]) == INT16_MAX);
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE);
    s_now_us += SYSTEM_TELEMETRY_PREFLIGHT_STATE_PERIOD_US - 1ULL;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) == count);
    s_now_us++;
    s_imu_sample.accel_b_mps2[0] = 20.0f * AIR_STANDARD_GRAVITY_MPS2;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) ==
               (uint8_t)(count + 1U));
    TEST_CHECK(Test_GetI16Le(&Test_LastTypeGet(
        AIR_TYPE_PREFLIGHT_STATE)->data[6]) == INT16_MAX);
    TelemetryService_DiagnosticsGet(&diagnostics);
    TEST_CHECK(diagnostics.quantization_saturation_count != 0U);

    /* READY must replace the live hardware quaternion with the frozen final
       alignment quaternion without changing the existing wire layout. */
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_valid = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.final_quaternion_frozen = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.attitude_ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[0] = 0.70710678f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[3] = 0.70710678f;
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) != count) { break; }
    }
    state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) ==
               (uint8_t)(count + 1U));
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[18]), 23170.0f, 1.0f);
    TEST_CHECK(Test_GetI16Le(&state->data[20]) == 0);
    TEST_CHECK(Test_GetI16Le(&state->data[22]) == 0);
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[24]), 23170.0f, 1.0f);

    s_quaternion_available = 0U;
    s_now_us += SYSTEM_TELEMETRY_PREFLIGHT_STATE_PERIOD_US;
    TelemetryService_Process();
    state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[18]), 23170.0f, 1.0f);
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[24]), 23170.0f, 1.0f);

    /* STALE preserves the historical final q but immediately returns the
       preflight display authority to the live hardware quaternion. */
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_STALE;
    s_alignment_status.ready = 0U;
    s_quaternion_available = 1U;
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) != count) { break; }
    }
    state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) ==
               (uint8_t)(count + 1U));
    TEST_CHECK(Test_GetI16Le(&state->data[18]) == INT16_MAX);
    TEST_CHECK(Test_GetI16Le(&state->data[20]) == 0);
    TEST_CHECK(Test_GetI16Le(&state->data[22]) == 0);
    TEST_CHECK(Test_GetI16Le(&state->data[24]) == 0);

    /* A valid attitude result is authoritative even while another required
       source keeps the overall Alignment state in COLLECTING. */
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
    s_alignment_status.ready = 0U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[0] = 0.5f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[1] = 0.5f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[2] = 0.5f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[3] = 0.5f;
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) != count) { break; }
    }
    state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) ==
               (uint8_t)(count + 1U));
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[18]), 16384.0f, 1.0f);
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[20]), 16384.0f, 1.0f);
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[22]), 16384.0f, 1.0f);
    TEST_CHECK_NEAR(Test_GetI16Le(&state->data[24]), 16384.0f, 1.0f);

    /* A subsequent realignment switches immediately to the new frozen q. */
    s_alignment_status.start_sequence++;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[0] = 0.0f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[1] = 1.0f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[2] = 0.0f;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[3] = 0.0f;
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) != count) { break; }
    }
    state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) ==
               (uint8_t)(count + 1U));
    TEST_CHECK(Test_GetI16Le(&state->data[18]) == 0);
    TEST_CHECK(Test_GetI16Le(&state->data[20]) == INT16_MAX);
}

static void Test_CalibratedImuTelemetry(void)
{
    const TestFrame *state;
    SystemCalibrationMode mode;
    uint8_t index;

    for (mode = SYSTEM_CALIBRATION_MODE_ONE_FACE;
         mode <= SYSTEM_CALIBRATION_MODE_SIX_FACE;
         mode = (SystemCalibrationMode)((uint8_t)mode + 1U))
    {
        Test_Reset();
        Test_CapabilityAck(31U, Test_InitialCapabilitySend());
        s_alignment_status_result = SYSTEM_DEVICE_OK;
        s_quaternion_available = 1U;
        s_calibration_correction_result = SYSTEM_DEVICE_OK;
        s_calibration_correction.mode = mode;
        s_calibration_correction.accel_bias_mps2[0] =
            AIR_STANDARD_GRAVITY_MPS2;
        s_calibration_correction.accel_scale[0] = 0.5f;
        s_calibration_correction.gyro_scale[1] = 0.5f;
        s_imu_sample.accel_b_mps2[0] =
            2.0f * AIR_STANDARD_GRAVITY_MPS2;
        s_imu_sample.gyro_b_radps[1] = 17.4532925f;
        for (index = 0U; index < 8U; index++)
        {
            TelemetryService_Process();
            if (Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE) != NULL) { break; }
        }
        state = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATE);
        TEST_CHECK(state != NULL);
        TEST_CHECK(Test_GetI16Le(&state->data[6]) == 1024);
        TEST_CHECK(Test_GetI16Le(&state->data[14]) == 8192);
    }
}

static void Test_PreflightStatus(void)
{
    AirPreflightStatusPayload parsed;
    const TestFrame *status;
    uint8_t capability_sequence;
    uint8_t count;
    uint8_t index;

    Test_Reset();
    capability_sequence = Test_InitialCapabilitySend();
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_ONE_FACE;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_READY;
    s_calibration_status.current_face = SYSTEM_CALIBRATION_FACE_Y_POSITIVE;
    s_calibration_status.completed_face_mask = 0x04U;
    s_calibration_status.ready = 1U;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    s_alignment_status.ready_mask =
        SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
        SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN;
    s_health_snapshot.ready = 1U;
    s_startup_report.completed = 1U;
    s_startup_report.mission_capable = 1U;
    s_gnss_sample.online = 1U;
    s_gnss_sample.position_usable = 1U;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) == 0U);
    TEST_CHECK(s_sensor_snapshot_capture_count == 1U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_SENSOR_STATUS) == 0U);
    Test_CapabilityAck(32U, capability_sequence);
    Test_CommandQueue(33U, AIR_CMD_UNLOCK, AIR_TOKEN_UNLOCK, 0U, 0U);
    TelemetryService_Process();
    for (count = 0U; count < 32U; count++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) != 0U) { break; }
    }
    status = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATUS);
    TEST_CHECK(status != NULL);
    if (status == NULL) { return; }
    TEST_CHECK(status->length == AIR_PREFLIGHT_STATUS_LEN);
    TEST_CHECK(Air_PreflightStatusParse(status->data,
        (uint8_t)status->length, &parsed) == AIR_PARSE_OK);
    TEST_CHECK(parsed.lifecycle_state == AIR_LIFECYCLE_PREFLIGHT);
    TEST_CHECK(parsed.calibration_state == AIR_CALIBRATION_STATE_READY);
    TEST_CHECK(parsed.calibration_mode == AIR_CALIBRATION_MODE_ONE_FACE);
    TEST_CHECK(parsed.completed_face_mask == 0x04U);
    TEST_CHECK(parsed.current_face == AIR_CALIBRATION_FACE_Y_POSITIVE);
    TEST_CHECK(parsed.alignment_state == AIR_ALIGNMENT_STATE_READY);
    TEST_CHECK((status->data[6] & 0xF0U) == 0U);
    TEST_CHECK(parsed.flags == AIR_PREFLIGHT_FLAG_MASK_ALL);
    TEST_CHECK(parsed.start_block_reason == AIR_ACK_RESULT_OK);
    Test_SensorSnapshotTransactionCheck(
        s_sensor_snapshot_info.snapshot_id, AIR_ALIGNMENT_STATE_READY);

    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS);
    s_now_us += SYSTEM_TELEMETRY_PREFLIGHT_STATUS_PERIOD_US - 1ULL;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) == count);
    s_now_us++;
    TelemetryService_Process();
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) ==
               (uint8_t)(count + 1U));

    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
    s_alignment_status.ready = 0U;
    s_health_snapshot.ready = 0U;
    s_start_readiness_result = SYSTEM_LIFECYCLE_START_NOT_READY;
    s_start_readiness_reason = SYSTEM_START_REASON_ALIGNMENT_REQUIRED;
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) != count) { break; }
    }
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) ==
               (uint8_t)(count + 1U));
    status = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATUS);
    TEST_CHECK(Air_PreflightStatusParse(status->data,
        (uint8_t)status->length, &parsed) == AIR_PARSE_OK);
    TEST_CHECK(parsed.alignment_state == AIR_ALIGNMENT_STATE_COLLECTING);
    TEST_CHECK((parsed.flags & AIR_PREFLIGHT_FLAG_ALIGNMENT_READY) == 0U);
    TEST_CHECK((parsed.flags & AIR_PREFLIGHT_FLAG_SYSTEM_READY) == 0U);
    TEST_CHECK(parsed.start_block_reason ==
               AIR_ACK_RESULT_ALIGNMENT_REQUIRED);

    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_STALE;
    s_alignment_status.ready = 0U;
    count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS);
    for (index = 0U; index < 12U; index++)
    {
        TelemetryService_Process();
        status = Test_LastStatusGet(AIR_STATUS_ALIGNMENT);
        if ((status != NULL) &&
            (status->data[7] == AIR_ALIGNMENT_STATE_STALE) &&
            (Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) != count))
        {
            break;
        }
    }
    status = Test_LastStatusGet(AIR_STATUS_ALIGNMENT);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->data[7] == AIR_ALIGNMENT_STATE_STALE);
    TEST_CHECK(status->data[8] == 0xFFU);
    status = Test_LastTypeGet(AIR_TYPE_PREFLIGHT_STATUS);
    TEST_CHECK(Air_PreflightStatusParse(status->data,
        (uint8_t)status->length, &parsed) == AIR_PARSE_OK);
    TEST_CHECK(parsed.alignment_state == AIR_ALIGNMENT_STATE_STALE);
    TEST_CHECK((status->data[6] & 0xF0U) == 0U);
    TEST_CHECK((parsed.flags & AIR_PREFLIGHT_FLAG_ALIGNMENT_READY) == 0U);
    TEST_CHECK(parsed.start_block_reason ==
               AIR_ACK_RESULT_ALIGNMENT_REQUIRED);

    count = Test_StatusIdCount(AIR_STATUS_ALIGNMENT);
    s_alignment_status.ready_mask =
        SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE;
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
    }
    TEST_CHECK(Test_StatusIdCount(AIR_STATUS_ALIGNMENT) == count);
}

static void Test_CalibrationDiagnosticEdges(void)
{
    const TestFrame *diagnostic;
    uint8_t count;
    uint8_t index;

    Test_Reset();
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_ONE_FACE;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_COLLECTING;
    s_calibration_status.diagnostic_sequence = 1U;
    s_calibration_status.diagnostic_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_calibration_status.diagnostic_reason =
        SYSTEM_CALIBRATION_WAIT_GYRO_MOVING;
    for (index = 0U; index < 12U; index++)
    {
        TelemetryService_Process();
        if (Test_StatusIdCount(
                AIR_STATUS_CALIBRATION_DIAGNOSTIC) == 1U)
        {
            break;
        }
    }
    diagnostic = Test_LastStatusGet(AIR_STATUS_CALIBRATION_DIAGNOSTIC);
    TEST_CHECK(diagnostic != NULL);
    TEST_CHECK(diagnostic->length == AIR_STATUS_LEN);
    TEST_CHECK(diagnostic->data[7] == AIR_CALIBRATION_FACE_NOT_SELECTED);
    TEST_CHECK(diagnostic->data[8] ==
               AIR_CALIBRATION_DIAGNOSTIC_GYRO_MOVING);

    count = Test_StatusIdCount(AIR_STATUS_CALIBRATION_DIAGNOSTIC);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
    }
    TEST_CHECK(Test_StatusIdCount(
        AIR_STATUS_CALIBRATION_DIAGNOSTIC) == count);

    s_calibration_status.diagnostic_sequence++;
    s_calibration_status.diagnostic_reason =
        SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE;
    for (index = 0U; index < 12U; index++)
    {
        TelemetryService_Process();
        if (Test_StatusIdCount(
                AIR_STATUS_CALIBRATION_DIAGNOSTIC) > count)
        {
            break;
        }
    }
    diagnostic = Test_LastStatusGet(AIR_STATUS_CALIBRATION_DIAGNOSTIC);
    TEST_CHECK(diagnostic->data[8] ==
               AIR_CALIBRATION_DIAGNOSTIC_ACCEL_MAGNITUDE);
    count = Test_StatusIdCount(AIR_STATUS_CALIBRATION_DIAGNOSTIC);

    s_calibration_status.diagnostic_sequence++;
    s_calibration_status.diagnostic_reason = SYSTEM_CALIBRATION_WAIT_NONE;
    for (index = 0U; index < 12U; index++)
    {
        TelemetryService_Process();
        if (Test_StatusIdCount(
                AIR_STATUS_CALIBRATION_DIAGNOSTIC) > count)
        {
            break;
        }
    }
    diagnostic = Test_LastStatusGet(AIR_STATUS_CALIBRATION_DIAGNOSTIC);
    TEST_CHECK(diagnostic->data[8] == AIR_CALIBRATION_DIAGNOSTIC_NONE);
    count = Test_StatusIdCount(AIR_STATUS_CALIBRATION_DIAGNOSTIC);

    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_SIX_FACE;
    s_calibration_status.diagnostic_sequence++;
    s_calibration_status.diagnostic_face =
        SYSTEM_CALIBRATION_FACE_X_POSITIVE;
    s_calibration_status.diagnostic_reason =
        SYSTEM_CALIBRATION_WAIT_NO_STREAM;
    for (index = 0U; index < 12U; index++)
    {
        TelemetryService_Process();
        if (Test_StatusIdCount(
                AIR_STATUS_CALIBRATION_DIAGNOSTIC) > count)
        {
            break;
        }
    }
    diagnostic = Test_LastStatusGet(AIR_STATUS_CALIBRATION_DIAGNOSTIC);
    TEST_CHECK(diagnostic->data[7] == AIR_CALIBRATION_FACE_X_POSITIVE);
    TEST_CHECK(diagnostic->data[8] ==
               AIR_CALIBRATION_DIAGNOSTIC_NO_STREAM);
}

static void Test_BadCommandEcho(void)
{
    const TestFrame *ack;

    Test_Reset();
    Test_Authorize();
    Test_CommandQueue(34U, 0x55U, 0U, 0U, 0U);
    TelemetryService_Process();
    ack = Test_LastTypeGet(AIR_TYPE_ACK);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->length == AIR_ACK_LEN);
    TEST_CHECK(ack->data[2] == 34U);
    TEST_CHECK(ack->data[3] == 0x55U);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_BAD_CMD);
}

static void Test_PreflightCommandsAndEvents(void)
{
    const TestFrame *status;
    uint32_t start_count;
    uint8_t index;

    Test_Reset();
    Test_Authorize();
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_calibration_status.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
    s_calibration_status.state = SYSTEM_CALIBRATION_STATE_IDLE;
    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_IDLE;

    Test_CommandQueue(40U, AIR_CMD_CAL_START, AIR_TOKEN_CALIBRATION,
                      AIR_CALIBRATION_MODE_NONE, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_calibration_start_count == 1U);
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] == AIR_ACK_RESULT_OK);
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        status = Test_LastTypeGet(AIR_TYPE_STATUS);
        if ((status != NULL) &&
            (status->data[2] == AIR_STATUS_CALIBRATION) &&
            (status->data[7] == AIR_CALIBRATION_STATE_READY))
        {
            break;
        }
    }
    status = Test_LastTypeGet(AIR_TYPE_STATUS);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->data[2] == AIR_STATUS_CALIBRATION);
    TEST_CHECK(status->data[7] == AIR_CALIBRATION_STATE_READY);
    TEST_CHECK(status->data[8] == AIR_CALIBRATION_MODE_NONE);

    start_count = s_calibration_start_count;
    Test_CommandQueue(40U, AIR_CMD_CAL_START, AIR_TOKEN_CALIBRATION,
                      AIR_CALIBRATION_MODE_NONE, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_calibration_start_count == start_count);

    Test_CommandQueue(41U, AIR_CMD_ALIGN_START, AIR_TOKEN_ALIGNMENT, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_alignment_start_count == 1U);
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] == AIR_ACK_RESULT_OK);

    s_alignment_start_result = SYSTEM_DEVICE_NOT_READY;
    Test_CommandQueue(42U, AIR_CMD_ALIGN_START, AIR_TOKEN_ALIGNMENT, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_CALIBRATION_REQUIRED);

    s_alignment_status.state = SYSTEM_ALIGNMENT_STATE_READY;
    s_alignment_status.ready = 1U;
    s_alignment_status.ready_mask =
        SYSTEM_ALIGNMENT_AIR_PROFILE_0_SOURCE_MASK;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.origin_valid = 1U;
    s_alignment_status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.origin_valid = 1U;
    for (index = 0U; index < 8U; index++)
    {
        TelemetryService_Process();
        status = Test_LastTypeGet(AIR_TYPE_STATUS);
        if ((status != NULL) &&
            (status->data[2] == AIR_STATUS_ALIGNMENT) &&
            (status->data[7] == AIR_ALIGNMENT_STATE_READY))
        {
            break;
        }
    }
    status = Test_LastTypeGet(AIR_TYPE_STATUS);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->data[2] == AIR_STATUS_ALIGNMENT);
    TEST_CHECK(status->data[7] == AIR_ALIGNMENT_STATE_READY);
    TEST_CHECK(status->data[8] == s_sensor_snapshot_info.snapshot_id);
    TEST_CHECK(status->data[8] != 0xFFU);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_SENSOR_STATUS) == 4U);
    Test_SensorSnapshotTransactionCheck(
        s_sensor_snapshot_info.snapshot_id, AIR_ALIGNMENT_STATE_READY);

    s_calibration_status.last_face = SYSTEM_CALIBRATION_FACE_Z_POSITIVE;
    s_calibration_status.last_face_result =
        SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE;
    s_calibration_status.face_event_sequence++;
    TelemetryService_Process();
    TelemetryService_Process();
    status = Test_LastTypeGet(AIR_TYPE_STATUS);
    TEST_CHECK(status->data[2] == AIR_STATUS_CALIBRATION_FACE);
    TEST_CHECK(status->data[7] == AIR_CALIBRATION_FACE_Z_POSITIVE);
    TEST_CHECK(status->data[8] == AIR_CALIBRATION_FACE_PASSED);
}

static void Test_StartResponseCase(SystemLifecycleStartResult result,
                                   SystemLifecycleStartReason reason,
                                   AirAckResult expected)
{
    const TestFrame *ack;

    Test_Reset();
    Test_Authorize();
    s_start_response.result = result;
    s_start_response.reason = reason;
    Test_CommandQueue(50U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TelemetryService_Process();
    ack = Test_LastTypeGet(AIR_TYPE_ACK);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[3] == AIR_CMD_START_MISSION);
    TEST_CHECK(ack->data[4] == expected);
}

static void Test_StartResults(void)
{
    Test_Reset();
    (void)Test_InitialCapabilitySend();
    Test_CommandQueue(49U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_CAPABILITY_REQUIRED);

    Test_Reset();
    Test_CapabilityAck(48U, Test_InitialCapabilitySend());
    Test_CommandQueue(49U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_LOCKED_REQUIRED);

    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NOT_READY,
        SYSTEM_START_REASON_CALIBRATION_REQUIRED,
        AIR_ACK_RESULT_CALIBRATION_REQUIRED);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NOT_READY,
        SYSTEM_START_REASON_ALIGNMENT_REQUIRED,
        AIR_ACK_RESULT_ALIGNMENT_REQUIRED);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NOT_READY,
        SYSTEM_START_REASON_ATTITUDE_NOT_READY,
        AIR_ACK_RESULT_ATTITUDE_NOT_READY);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NOT_READY,
        SYSTEM_START_REASON_ATTITUDE_INVALID,
        AIR_ACK_RESULT_ATTITUDE_INVALID);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NOT_READY,
        SYSTEM_START_REASON_ATTITUDE_STALE,
        AIR_ACK_RESULT_ATTITUDE_STALE);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NOT_READY,
        SYSTEM_START_REASON_SYSTEM_NOT_READY,
        AIR_ACK_RESULT_SYSTEM_NOT_READY);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_ORIGIN_FAILED,
        SYSTEM_START_REASON_ORIGIN_FAILED,
        AIR_ACK_RESULT_ORIGIN_FAILED);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_NAVIGATION_FAILED,
        SYSTEM_START_REASON_NAVIGATION_FAILED,
        AIR_ACK_RESULT_NAVIGATION_FAILED);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_QUEUE_FAILED,
        SYSTEM_START_REASON_QUEUE_FAILED,
        AIR_ACK_RESULT_QUEUE_FAILED);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_INTERNAL_ERROR,
        SYSTEM_START_REASON_HOOKS_UNAVAILABLE,
        AIR_ACK_RESULT_HOOKS_UNAVAILABLE);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_PREPARE_FAILED,
        SYSTEM_START_REASON_PREPARE_FAILED,
        AIR_ACK_RESULT_PREPARE_FAILED);
    Test_StartResponseCase(SYSTEM_LIFECYCLE_START_BUSY,
        SYSTEM_START_REASON_REQUEST_PENDING,
        AIR_ACK_RESULT_BUSY);

    Test_Reset();
    Test_Authorize();
    s_start_submit_result = SYSTEM_DEVICE_BUSY;
    Test_CommandQueue(51U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] == AIR_ACK_RESULT_BUSY);

    Test_Reset();
    Test_Authorize();
    s_start_readiness_result = SYSTEM_LIFECYCLE_START_NOT_READY;
    s_start_readiness_reason = SYSTEM_START_REASON_HOOKS_UNAVAILABLE;
    Test_CommandQueue(52U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_start_submit_count == 0U);
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] ==
               AIR_ACK_RESULT_HOOKS_UNAVAILABLE);
}

static void Test_StartFlightTransitionRace(void)
{
    const TestFrame *ack;
    uint8_t index;

    Test_Reset();
    Test_Authorize();
    s_quaternion_available = 1U;
    s_start_complete_during_submit = 1U;
    Test_CommandQueue(70U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(s_start_submit_count == 1U);
    TEST_CHECK(s_start_response_pop_count == 0U);
    TEST_CHECK(Test_AckGet(70U, AIR_CMD_START_MISSION) == NULL);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_FLIGHT_STATE) == 0U);

    TelemetryService_Process();
    ack = Test_AckGet(70U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->length == AIR_ACK_LEN);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_OK);
    TEST_CHECK(s_start_response_pop_count == 1U);
    TEST_CHECK(s_start_submit_count == 1U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_FLIGHT_STATE) == 0U);
    for (index = 0U; index < 12U; index++)
    {
        TelemetryService_Process();
        if (Test_TypeCount(AIR_TYPE_FLIGHT_STATE) != 0U) { break; }
    }
    TEST_CHECK(Test_StatusIdCount(AIR_STATUS_MISSION_START) != 0U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_FLIGHT_STATE) != 0U);

    Test_Reset();
    Test_Authorize();
    s_quaternion_available = 1U;
    Test_CommandQueue(71U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_PREFLIGHT);
    TEST_CHECK(s_start_submit_count == 1U);
    TelemetryService_Process();
    ack = Test_AckGet(71U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_OK);
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_FLIGHT);
    TEST_CHECK(s_start_response_pop_count == 1U);
    TEST_CHECK(s_start_submit_count == 1U);
}

static void Test_StartFailureRetryAndIdempotency(void)
{
    const TestFrame *ack;

    Test_Reset();
    Test_Authorize();
    s_start_response.result = SYSTEM_LIFECYCLE_START_NOT_READY;
    s_start_response.reason = SYSTEM_START_REASON_ALIGNMENT_REQUIRED;
    Test_CommandQueue(72U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TelemetryService_Process();
    ack = Test_AckGet(72U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_ALIGNMENT_REQUIRED);
    TEST_CHECK(s_start_submit_count == 1U);
    TEST_CHECK(s_start_response_pop_count == 1U);
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_PREFLIGHT);

    s_start_response.reason = SYSTEM_START_REASON_CALIBRATION_REQUIRED;
    Test_CommandQueue(73U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_start_submit_count == 2U);
    TelemetryService_Process();
    ack = Test_AckGet(73U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_CALIBRATION_REQUIRED);
    TEST_CHECK(s_start_response_pop_count == 2U);

    Test_Reset();
    Test_Authorize();
    s_start_response.result = SYSTEM_LIFECYCLE_START_NOT_READY;
    s_start_response.reason = SYSTEM_START_REASON_ALIGNMENT_REQUIRED;
    Test_CommandQueue(74U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    Test_CommandQueue(74U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_start_submit_count == 1U);
    TEST_CHECK(Test_AckGet(74U, AIR_CMD_START_MISSION) == NULL);
    TelemetryService_Process();
    TEST_CHECK(Test_AckCount(74U, AIR_CMD_START_MISSION) == 1U);
    TEST_CHECK(s_start_submit_count == 1U);
    Test_CommandQueue(74U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(Test_AckCount(74U, AIR_CMD_START_MISSION) == 2U);
    TEST_CHECK(s_start_submit_count == 1U);
    TEST_CHECK(s_start_response_pop_count == 1U);
}

static void Test_StartBusyOwnership(void)
{
    const TestFrame *ack;

    Test_Reset();
    Test_Authorize();
    s_start_response.result = SYSTEM_LIFECYCLE_START_NOT_READY;
    s_start_response.reason = SYSTEM_START_REASON_ALIGNMENT_REQUIRED;
    Test_CommandQueue(75U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    Test_CommandQueue(76U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TEST_CHECK(s_start_submit_count == 1U);
    ack = Test_AckGet(76U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_BUSY);
    TelemetryService_Process();
    ack = Test_AckGet(75U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_ALIGNMENT_REQUIRED);
    TEST_CHECK(s_start_submit_count == 1U);
    TEST_CHECK(s_start_response_pop_count == 1U);

    Test_Reset();
    Test_Authorize();
    s_start_readiness_result = SYSTEM_LIFECYCLE_START_BUSY;
    s_start_readiness_reason = SYSTEM_START_REASON_REQUEST_PENDING;
    Test_CommandQueue(77U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    ack = Test_AckGet(77U, AIR_CMD_START_MISSION);
    TEST_CHECK(ack != NULL);
    TEST_CHECK(ack->data[4] == AIR_ACK_RESULT_BUSY);
    TEST_CHECK(s_start_submit_count == 0U);
}

static void Test_FlightRxPolicy(void)
{
    TelemetryServiceDiagnostics diagnostics;
    uint8_t ack_count;
    uint8_t capability_count;
    uint8_t preflight_count;
    uint8_t preflight_status_count;
    uint8_t index;

    Test_Reset();
    Test_Authorize();
    s_quaternion_available = 1U;
    TelemetryService_Process();
    capability_count = Test_TypeCount(AIR_TYPE_CAPABILITY);
    s_start_response.result = SYSTEM_LIFECYCLE_START_OK;
    s_start_response.reason = SYSTEM_START_REASON_NONE;
    Test_CommandQueue(60U, AIR_CMD_START_MISSION,
                      AIR_TOKEN_START_MISSION, 0U, 0U);
    TelemetryService_Process();
    TelemetryService_Process();
    TEST_CHECK(Test_LastTypeGet(AIR_TYPE_ACK)->data[4] == AIR_ACK_RESULT_OK);
    ack_count = Test_TypeCount(AIR_TYPE_ACK);
    preflight_count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE);
    preflight_status_count = Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS);

    Test_CommandQueue(61U, AIR_CMD_CAL_RESET,
                      AIR_TOKEN_CALIBRATION, 0U, 0U);
    Test_CommandQueue(62U, AIR_CMD_PING, 0U, 0U, 0U);
    for (index = 0U; index < 8U; index++)
    {
        s_now_us += SYSTEM_TELEMETRY_STATUS_REPEAT_PERIOD_US;
        TelemetryService_Process();
    }
    TEST_CHECK(s_calibration_reset_count == 0U);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_ACK) == ack_count);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_CAPABILITY) == capability_count);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATE) == preflight_count);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_PREFLIGHT_STATUS) ==
               preflight_status_count);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_FLIGHT_STATE) != 0U);
    TelemetryService_DiagnosticsGet(&diagnostics);
    TEST_CHECK(diagnostics.capability_state ==
               TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT);
    TEST_CHECK(diagnostics.capability_acked == 0U);

    s_gnss_sample.online = 1U;
    s_gnss_sample.position_usable = 1U;
    for (index = 0U; index < 4U; index++)
    {
        TelemetryService_Process();
    }
    TEST_CHECK(Test_StatusIdCount(AIR_STATUS_GNSS_POSITION) == 1U);

    Test_Reset();
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TelemetryService_Process();
    TelemetryService_DiagnosticsGet(&diagnostics);
    TEST_CHECK(diagnostics.capability_state ==
               TELEMETRY_CAPABILITY_DISABLED_FOR_FLIGHT);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_CAPABILITY) == 0U);
}

static void Test_SelfTestAndGnssEdges(void)
{
    const TestFrame *status;

    Test_Reset();
    s_startup_report.completed = 1U;
    s_startup_report.mission_capable = 1U;
    TelemetryService_Process();
    status = Test_LastTypeGet(AIR_TYPE_STATUS);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->data[2] == AIR_STATUS_SELFTEST_COMPLETE);
    TEST_CHECK(status->data[7] == 1U);

    Test_Reset();
    s_gnss_sample.online = 1U;
    s_gnss_sample.position_usable = 1U;
    TelemetryService_Process();
    status = Test_LastTypeGet(AIR_TYPE_STATUS);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->data[2] == AIR_STATUS_GNSS_POSITION);
    TEST_CHECK(status->data[7] == 1U);
}

static void Test_FlightRecoveryEvents(void)
{
    const TestFrame *status;
    uint8_t deploy_count;
    uint8_t landing_count;

    Test_Reset();
    s_flight_recovery_status.deploy_event_sequence = 1U;
    s_flight_recovery_status.deploy_event_mission_time_ms = 0x01020304UL;
    s_transport_send_result = SYSTEM_DEVICE_IO_ERROR;
    TelemetryService_Process();
    TEST_CHECK(Test_StatusIdCount(AIR_STATUS_PARACHUTE_DEPLOY) == 0U);
    s_transport_send_result = SYSTEM_DEVICE_OK;
    TelemetryService_Process();
    status = Test_LastStatusGet(AIR_STATUS_PARACHUTE_DEPLOY);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->length == AIR_STATUS_LEN);
    TEST_CHECK(Test_GetU32Le(&status->data[3]) == 0x01020304UL);
    TEST_CHECK(status->data[7] == 0U);
    TEST_CHECK(status->data[8] == 0U);
    deploy_count = Test_StatusIdCount(AIR_STATUS_PARACHUTE_DEPLOY);
    TelemetryService_Process();
    TEST_CHECK(Test_StatusIdCount(AIR_STATUS_PARACHUTE_DEPLOY) ==
               deploy_count);

    s_flight_recovery_status.landing_event_sequence = 1U;
    s_flight_recovery_status.landing_event_mission_time_ms = 0x11223344UL;
    TelemetryService_Process();
    status = Test_LastStatusGet(AIR_STATUS_LANDING);
    TEST_CHECK(status != NULL);
    TEST_CHECK(status->length == AIR_STATUS_LEN);
    TEST_CHECK(Test_GetU32Le(&status->data[3]) == 0x11223344UL);
    TEST_CHECK(status->data[7] == 0U);
    TEST_CHECK(status->data[8] == 0U);
    landing_count = Test_StatusIdCount(AIR_STATUS_LANDING);
    TelemetryService_Process();
    TEST_CHECK(Test_StatusIdCount(AIR_STATUS_LANDING) == landing_count);
}

static void Test_NavigationSubscription(void)
{
    const TestFrame *frame;
    uint8_t index;

    Test_Reset();
    Test_CommandQueue(20U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
    TelemetryService_Process();
    frame = Test_AckGet(20U, AIR_CMD_NAV_SUBSCRIBE);
    TEST_CHECK(frame != NULL);
    TEST_CHECK(frame->data[4] == AIR_ACK_RESULT_CAPABILITY_REQUIRED);
    TEST_CHECK(Test_TypeCount(AIR_TYPE_NAV_CAPABILITY) == 0U);
    Test_Authorize();
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_calibration_status.ready = 1U;
    s_alignment_status.required_mask = SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
        SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN;
    s_alignment_status.ready_mask = SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE;
    s_navigation_preparation.generation = 7U;
    s_navigation_preparation.algorithm_id = 2U;
    Test_CommandQueue(21U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
    for (index = 0U; index < 32U; index++)
    {
        TelemetryService_Process();
        s_now_us += 20000ULL;
    }
    frame = Test_LastTypeGet(AIR_TYPE_NAV_CAPABILITY);
    TEST_CHECK(frame != NULL);
    if (frame == NULL) { return; }
    TEST_CHECK(frame->length == 9U && frame->data[2] == 0x34U && frame->data[3] == 0x12U);
    TEST_CHECK(frame->data[4] == 7U && frame->data[6] == 1U && frame->data[7] == 2U);
    frame = Test_LastTypeGet(AIR_TYPE_NAV_PREPARATION);
    TEST_CHECK(frame != NULL);
    if (frame == NULL) { return; }
    TEST_CHECK((frame->data[6] & 0x50U) == 0x50U);
    TEST_CHECK((frame->data[7] & 0x50U) == 0U);
    /* Same command sequence with a new nonce must start a new subscription. */
    s_navigation_preparation.generation++;
    s_navigation_preparation.initialized = 1U;
    s_alignment_status.ready_mask |= SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN;
    Test_CommandQueue(21U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561235UL, 1U, 0U);
    for (index = 0U; index < 32U; index++)
    {
        TelemetryService_Process();
        s_now_us += 20000ULL;
    }
    frame = Test_LastTypeGet(AIR_TYPE_NAV_PREPARATION);
    TEST_CHECK(frame != NULL);
    if (frame == NULL) { return; }
    TEST_CHECK(frame->data[2] == 0x35U && frame->data[4] == 8U);
    TEST_CHECK((frame->data[7] & 0x50U) == 0x50U);
}

static void Test_NavigationHealth(void)
{
    uint8_t index;
    uint8_t state_mask = 0U;
    uint8_t age_mask = 0U;

    Test_Reset();
    Test_Authorize();
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_navigation_preparation.algorithm_id = 1U;
    s_navigation_health[0].state = SYSTEM_NAVIGATION_REJECTED;
    s_navigation_health[0].quality = 1U;
    s_navigation_health[0].reason = 5U;
    Test_CommandQueue(22U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
    for (index = 0U; index < 200U; index++)
    {
        TelemetryService_Process();
        s_now_us += 20000ULL;
    }
    for (index = 0U; index < s_tx_count; index++)
    {
        const uint8_t *frame = s_tx[index].data;
        if (frame[0] != AIR_TYPE_NAV_HEALTH) { continue; }
        if (frame[6] < 5U)
        {
            state_mask |= (uint8_t)(1U << frame[6]);
            if (frame[6] == 0U) { TEST_CHECK(frame[7] == 0x13U && frame[8] == 5U); }
        }
        else if ((frame[6] >= 8U) && (frame[6] <= 12U))
        {
            age_mask |= (uint8_t)(1U << (frame[6] - 8U));
            TEST_CHECK(frame[7] == UINT8_MAX && frame[8] == UINT8_MAX);
        }
    }
    TEST_CHECK(state_mask == 31U && age_mask == 31U);
    TEST_CHECK(s_navigation_health[0].has_success == 0U);
}

static void Test_NavigationDetails(void)
{
    uint16_t cycle;
    uint64_t detail_mask = 0ULL;
    uint64_t last_primary[10] = {0ULL};
    uint8_t frame_index;
    Test_Reset();
    Test_Authorize();
    s_calibration_status_result = SYSTEM_DEVICE_OK;
    s_alignment_status_result = SYSTEM_DEVICE_OK;
    s_navigation_preparation.algorithm_id = 2U;
    s_gnss_sample.supported_fields = SYSTEM_GNSS_FIELD_SATELLITE_COUNT |
        SYSTEM_GNSS_FIELD_HORIZONTAL_ACCURACY | SYSTEM_GNSS_FIELD_VERTICAL_ACCURACY |
        SYSTEM_GNSS_FIELD_SPEED_ACCURACY | SYSTEM_GNSS_FIELD_FIX_TYPE | SYSTEM_GNSS_FIELD_FIX_OK;
    s_gnss_sample.valid_fields = s_gnss_sample.supported_fields;
    s_gnss_sample.satellite_count = 4U;
    s_gnss_sample.horizontal_accuracy_m = 1.25f;
    s_gnss_sample.vertical_accuracy_m = 2.5f;
    s_gnss_sample.speed_accuracy_mps = 0.5f;
    s_imu_sample.quality_flags = SYSTEM_IMU_QUALITY_CLIPPED | SYSTEM_IMU_QUALITY_TIME_UNCERTAIN;
    Test_CommandQueue(23U, AIR_CMD_NAV_SUBSCRIBE, 0x4E561234UL, 1U, 0U);
    for (cycle = 0U; cycle < 500U; cycle++)
    {
        s_gnss_sample.receive_timestamp_us = s_now_us;
        s_imu_sample.receive_timestamp_us = s_now_us;
        TelemetryService_Process();
        for (frame_index = 0U; frame_index < s_tx_count; frame_index++)
        {
            const uint8_t *frame = s_tx[frame_index].data;
            uint8_t group = frame[6] & 7U;
            uint8_t metric = frame[6] >> 3U;
            uint16_t value = (uint16_t)(frame[7] | ((uint16_t)frame[8] << 8U));
            if (frame[0] != AIR_TYPE_NAV_HEALTH) { continue; }
            if ((group < 5U) && (metric < 2U))
            {
                uint8_t primary = (uint8_t)(metric * 5U + group);
                if (last_primary[primary] != 0ULL)
                { TEST_CHECK((s_now_us - last_primary[primary]) < 3000000ULL); }
                last_primary[primary] = s_now_us;
            }
            else
            {
                uint8_t detail = (group == 7U) ? (uint8_t)(35U + metric) :
                    (uint8_t)((metric - 2U) * 5U + group);
                TEST_CHECK(detail < 52U);
                detail_mask |= 1ULL << detail;
                if (group != 7U) { continue; }
                if (metric == 0U) { TEST_CHECK(value == 4U); }
                if (metric == 1U) { TEST_CHECK(value == 125U); }
                if (metric == 2U) { TEST_CHECK(value == 250U); }
                if (metric == 3U) { TEST_CHECK(value == 50U); }
                if (metric == 6U) { TEST_CHECK(value == 6U); }
                if (metric == 8U) { TEST_CHECK(value == 5U); }
                if (metric == 9U) { TEST_CHECK(value == 2000U); }
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
                if (metric == 10U) { TEST_CHECK(value == UINT16_MAX - 1U); }
                if (metric == 11U) { TEST_CHECK(value == 17U); }
#else
                if (metric == 10U) { TEST_CHECK(value == UINT16_MAX); }
#endif
                if (metric == 16U) { TEST_CHECK(value == 1600U); }
            }
        }
        s_tx_count = 0U;
        s_now_us += 20000ULL;
    }
    TEST_CHECK(detail_mask == ((1ULL << 52U) - 1ULL));
}

int main(void)
{
    TEST_CHECK(AIR_MAX_FRAME_LEN <= 64U);
    TEST_CHECK(AIR_PROTOCOL_APPLICATION_CRC_SIZE == 0U);
    Test_CapabilityHandshake();
    Test_DynamicCapabilityMask();
    Test_UnackedPermission();
    Test_PreflightState();
    Test_CalibratedImuTelemetry();
    Test_PreflightStatus();
    Test_CalibrationDiagnosticEdges();
    Test_BadCommandEcho();
    Test_PreflightCommandsAndEvents();
    Test_StartResults();
    Test_StartFlightTransitionRace();
    Test_StartFailureRetryAndIdempotency();
    Test_StartBusyOwnership();
    Test_FlightRxPolicy();
    Test_SelfTestAndGnssEdges();
    Test_FlightRecoveryEvents();
    Test_NavigationSubscription();
    Test_NavigationHealth();
    Test_NavigationDetails();
    return Test_Finish("telemetry");
}
