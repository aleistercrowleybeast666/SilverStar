#include <math.h>
#include <stdint.h>
#include <string.h>

#include "system_alignment.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_magnetometer_if.h"
#include "system_inertial_types.h"
#include "system_lifecycle.h"
#include "system_startup.h"
#include "system_user_config.h"
#include "system_user_alignment_config.h"
#include "system_user_startup_config.h"
#include "test_common.h"

static SystemLifecycleState s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
static SystemAlignmentAttitudeStatus s_attitude;
static SystemAlignmentGnssStatus s_gnss;
static SystemAlignmentBarometerStatus s_barometer;
static SystemDeviceResult s_reset_result = SYSTEM_DEVICE_OK;
static uint32_t s_reset_count;
static uint32_t s_prepare_count;
static uint32_t s_freeze_count;
static uint32_t s_abort_count;
static uint64_t s_timestamp_us;
static uint64_t s_guard_timestamp_us = 1000000ULL;
static SystemAlignmentGuardSample s_guard_sample;
static SystemStartupReport s_startup_report;
static SystemHardwareQuaternionSample s_hardware_quaternion;

static SystemDeviceResult Test_AttitudeCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_HW_QUAT_CAP_OUTPUT;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_HardwareQuaternionGet(
    SystemHardwareQuaternionSample *sample)
{
    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *sample = s_hardware_quaternion;
    return (sample->valid != 0U) ? SYSTEM_DEVICE_OK :
                                   SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult Test_ImuCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_GNSS_CAP_POSITION;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerCapabilitiesGet(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_VALID_PRESSURE | SYSTEM_BARO_VALID_ALTITUDE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemImu_CapabilitiesGet(uint32_t *mask)
{ return Test_ImuCapabilitiesGet(mask); }
SystemDeviceResult SystemMagnetometer_CapabilitiesGet(uint32_t *mask)
{
    if (mask != NULL) { *mask = 0U; }
    return SYSTEM_DEVICE_NOT_READY;
}
SystemDeviceResult SystemHardwareQuaternion_CapabilitiesGet(uint32_t *mask)
{ return Test_AttitudeCapabilitiesGet(mask); }
SystemDeviceResult SystemHardwareQuaternion_LatestSampleGet(
    SystemHardwareQuaternionSample *sample)
{ return Test_HardwareQuaternionGet(sample); }
SystemDeviceResult SystemGnss_CapabilitiesGet(uint32_t *mask)
{ return Test_GnssCapabilitiesGet(mask); }
SystemDeviceResult SystemBarometer_CapabilitiesGet(uint32_t *mask)
{ return Test_BarometerCapabilitiesGet(mask); }

const SystemStartupReport *SystemStartup_GetReport(void)
{
    return &s_startup_report;
}

SystemLifecycleState SystemLifecycle_GetState(void)
{
    return s_lifecycle_state;
}

SystemDeviceResult SystemLifecycle_EnterPreflight(void)
{
    if ((s_lifecycle_state != SYSTEM_STATE_SELF_TEST) &&
        (s_lifecycle_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_Reset(void)
{
    s_reset_count++;
    if (s_reset_result != SYSTEM_DEVICE_OK) { return s_reset_result; }
    (void)memset(&s_attitude, 0, sizeof(s_attitude));
    (void)memset(&s_gnss, 0, sizeof(s_gnss));
    (void)memset(&s_barometer, 0, sizeof(s_barometer));
    s_attitude.state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    s_gnss.state = SYSTEM_ALIGNMENT_COMPONENT_NOT_READY;
    s_gnss.supported = 1U;
    s_barometer.state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    s_barometer.supported = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_PrepareAttitude(void)
{
    s_prepare_count++;
    return (s_attitude.attitude_ready != 0U) ?
        SYSTEM_DEVICE_OK : SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult Test_FreezeOrigins(void)
{
    s_freeze_count++;
    if (s_gnss.ready != 0U)
    {
        s_gnss.origin_valid = 1U;
        s_gnss.origin_lat_e7 = 311234567;
        s_gnss.origin_lon_e7 = 1211234567;
        s_gnss.origin_height_mm = 12345;
    }
    if (s_barometer.ready != 0U)
    {
        s_barometer.origin_valid = 1U;
        s_barometer.origin_pressure_pa = 100100.0f;
        s_barometer.origin_altitude_m = 12.0f;
    }
    return SYSTEM_DEVICE_OK;
}

static void Test_Abort(void)
{
    s_abort_count++;
    s_gnss.origin_valid = 0U;
    s_barometer.origin_valid = 0U;
}

static SystemDeviceResult Test_GuardSampleGet(
    SystemAlignmentGuardSample *sample)
{
    if (sample == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    *sample = s_guard_sample;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_AttitudeStatusGet(
    SystemAlignmentSourceStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    status->detail.attitude = s_attitude;
    status->state = s_attitude.state;
    status->ready = s_attitude.attitude_ready;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_GnssStatusGet(
    SystemAlignmentSourceStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    status->detail.gnss = s_gnss;
    status->state = s_gnss.state;
    status->ready = s_gnss.ready;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Test_BarometerStatusGet(
    SystemAlignmentSourceStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    status->detail.barometer = s_barometer;
    status->state = s_barometer.state;
    status->ready = s_barometer.ready;
    return SYSTEM_DEVICE_OK;
}

static void Test_RequiredAlignmentReadySet(void)
{
    (void)memset(&s_guard_sample, 0, sizeof(s_guard_sample));
    s_guard_timestamp_us += 10000ULL;
    s_attitude.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_attitude.source =
        SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_KNOWN_YAW;
    s_attitude.algorithm = SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW;
    s_attitude.timestamp_us = s_guard_timestamp_us;
    s_attitude.receive_timestamp_us = s_guard_timestamp_us;
    s_attitude.sequence++;
    s_attitude.attitude_ready = 1U;
    s_attitude.quaternion_valid = 1U;
    s_attitude.final_quaternion_frozen = 1U;
    s_attitude.quaternion_wxyz[0] = 1.0f;
    s_attitude.quaternion_wxyz[1] = 0.0f;
    s_attitude.quaternion_wxyz[2] = 0.0f;
    s_attitude.quaternion_wxyz[3] = 0.0f;
    s_barometer.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_barometer.sample_count = 100U;
    s_barometer.ready = 1U;
    s_gnss.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_gnss.sample_count = 100U;
    s_gnss.horizontal_accuracy_m = 0.8f;
    s_gnss.vertical_accuracy_m = 1.2f;
    s_gnss.ready = 1U;
    s_guard_sample.observation_timestamp_us = s_guard_timestamp_us;
    s_guard_sample.inertial_sample_timestamp_us = s_guard_timestamp_us;
    s_guard_sample.inertial_receive_timestamp_us = s_guard_timestamp_us;
    s_guard_sample.inertial_sequence++;
    s_guard_sample.corrected_accel_b_mps2[1] =
        SYSTEM_LOCAL_GRAVITY_MPS2;
    s_guard_sample.valid_mask = SYSTEM_ALIGNMENT_GUARD_VALID_ACCEL |
                                SYSTEM_ALIGNMENT_GUARD_VALID_GYRO;
}

static void Test_GuardSampleAdvance(float gyro_x_radps,
                                    float accel_delta_mps2,
                                    float attitude_delta_rad)
{
    s_guard_timestamp_us += 10000ULL;
    s_guard_sample.observation_timestamp_us = s_guard_timestamp_us;
    s_guard_sample.inertial_sample_timestamp_us = s_guard_timestamp_us;
    s_guard_sample.inertial_receive_timestamp_us = s_guard_timestamp_us;
    s_guard_sample.inertial_sequence++;
    s_guard_sample.corrected_accel_b_mps2[0] = 0.0f;
    s_guard_sample.corrected_accel_b_mps2[1] =
        SYSTEM_LOCAL_GRAVITY_MPS2 + accel_delta_mps2;
    s_guard_sample.corrected_accel_b_mps2[2] = 0.0f;
    s_guard_sample.corrected_gyro_b_radps[0] = gyro_x_radps;
    s_guard_sample.corrected_gyro_b_radps[1] = 0.0f;
    s_guard_sample.corrected_gyro_b_radps[2] = 0.0f;
    s_guard_sample.valid_mask = SYSTEM_ALIGNMENT_GUARD_VALID_ACCEL |
                                SYSTEM_ALIGNMENT_GUARD_VALID_GYRO;

    s_attitude.timestamp_us = s_guard_timestamp_us;
    s_attitude.receive_timestamp_us = s_guard_timestamp_us;
    s_attitude.sequence++;
    s_attitude.quaternion_wxyz[0] = cosf(attitude_delta_rad * 0.5f);
    s_attitude.quaternion_wxyz[1] = sinf(attitude_delta_rad * 0.5f);
    s_attitude.quaternion_wxyz[2] = 0.0f;
    s_attitude.quaternion_wxyz[3] = 0.0f;
}

static void Test_GuardConditionConfirm(float gyro_x_radps,
                                       float accel_delta_mps2,
                                       float attitude_delta_rad)
{
    uint32_t index;
    const uint32_t sample_count = (uint32_t)(
        SYSTEM_USER_ALIGNMENT_GUARD_CONFIRM_DURATION_US / 10000ULL) + 2U;

    for (index = 0U; index < sample_count; index++)
    {
        Test_GuardSampleAdvance(gyro_x_radps, accel_delta_mps2,
                                attitude_delta_rad);
        TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    }
}

static void Test_OneFaceComplete(void)
{
    SystemInertialSample sample;
    float direction[3] = {0.0f, 0.0f, 0.0f};
    uint16_t index;

    direction[SYSTEM_IMU_STARTUP_GRAVITY_DIRECTION / 2U] =
        ((SYSTEM_IMU_STARTUP_GRAVITY_DIRECTION & 1U) == 0U) ? 1.0f : -1.0f;
    (void)memset(&sample, 0, sizeof(sample));
    sample.accel_b_mps2[0] = direction[0] * SYSTEM_LOCAL_GRAVITY_MPS2;
    sample.accel_b_mps2[1] = direction[1] * SYSTEM_LOCAL_GRAVITY_MPS2;
    sample.accel_b_mps2[2] = direction[2] * SYSTEM_LOCAL_GRAVITY_MPS2;
    sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL |
                        SYSTEM_INERTIAL_VALID_GYRO;
    for (index = 0U; index < 430U; index++)
    {
        s_timestamp_us += 5000ULL;
        sample.sample_timestamp_us = s_timestamp_us;
        sample.receive_timestamp_us = s_timestamp_us;
        sample.sequence++;
        SystemCalibration_ImuSampleProcess(&sample);
    }
    SystemCalibration_Process();
}

static void Test_SixFaceComplete(void)
{
    static const SystemCalibrationFace order[6] = {
        SYSTEM_CALIBRATION_FACE_Y_NEGATIVE,
        SYSTEM_CALIBRATION_FACE_Z_POSITIVE,
        SYSTEM_CALIBRATION_FACE_X_POSITIVE,
        SYSTEM_CALIBRATION_FACE_Z_NEGATIVE,
        SYSTEM_CALIBRATION_FACE_X_NEGATIVE,
        SYSTEM_CALIBRATION_FACE_Y_POSITIVE
    };
    SystemInertialSample sample;
    uint8_t face_index;
    uint16_t sample_index;

    TEST_CHECK(SystemCalibration_Start(
        SYSTEM_CALIBRATION_MODE_SIX_FACE) == SYSTEM_DEVICE_OK);
    for (face_index = 0U; face_index < 6U; face_index++)
    {
        uint8_t axis = (uint8_t)order[face_index] / 2U;
        float sign = (((uint8_t)order[face_index] & 1U) == 0U) ?
            1.0f : -1.0f;

        (void)memset(&sample, 0, sizeof(sample));
        sample.accel_b_mps2[axis] = sign * SYSTEM_LOCAL_GRAVITY_MPS2;
        sample.valid_mask = SYSTEM_INERTIAL_VALID_ACCEL |
                            SYSTEM_INERTIAL_VALID_GYRO;
        s_timestamp_us += 5000ULL;
        sample.sample_timestamp_us = s_timestamp_us;
        sample.receive_timestamp_us = s_timestamp_us;
        sample.sequence++;
        SystemCalibration_ImuSampleProcess(&sample);
        TEST_CHECK(SystemCalibration_FaceCollect(order[face_index]) ==
                   SYSTEM_DEVICE_OK);
        for (sample_index = 0U; sample_index < 430U; sample_index++)
        {
            s_timestamp_us += 5000ULL;
            sample.sample_timestamp_us = s_timestamp_us;
            sample.receive_timestamp_us = s_timestamp_us;
            sample.sequence++;
            SystemCalibration_ImuSampleProcess(&sample);
        }
        SystemCalibration_Process();
    }
    SystemCalibration_Process();
}

static void Test_StartupDeviceResultsSet(SystemDeviceResult init_result,
                                         SystemDeviceResult start_result)
{
    uint8_t index;

    (void)memset(&s_startup_report, 0, sizeof(s_startup_report));
    s_startup_report.completed = 1U;
    for (index = 0U; index < SYSTEM_STARTUP_DEVICE_COUNT; index++)
    {
        s_startup_report.devices[index].present = 1U;
        s_startup_report.devices[index].init_result = init_result;
        s_startup_report.devices[index].start_result = start_result;
    }
}

static uint8_t Test_StartReadyGet(void)
{
    SystemAlignmentStatus status;

    if ((SystemCalibration_IsReady() == 0U) ||
        (SystemAlignment_StatusGet(&status) != SYSTEM_DEVICE_OK))
    {
        return 0U;
    }
    return status.ready;
}

static void Test_PreflightQuaternionAuthority(void)
{
    SystemAlignmentPreflightAttitudeSource source;
    SystemAlignmentSummary summary;
    SystemAlignmentStatus status;
    float quaternion[4];

    (void)memset(&s_hardware_quaternion, 0,
                 sizeof(s_hardware_quaternion));
    s_hardware_quaternion.quaternion_wxyz[0] = 0.9238795f;
    s_hardware_quaternion.quaternion_wxyz[3] = 0.3826834f;
    s_hardware_quaternion.valid = 1U;
    s_hardware_quaternion.normalized = 1U;

    TEST_CHECK(SystemAlignment_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(
        quaternion, &source) == SYSTEM_DEVICE_OK);
    TEST_CHECK(source == SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE);
    TEST_CHECK_NEAR(quaternion[0], 0.9238795f, 1.0e-5f);
    TEST_CHECK_NEAR(quaternion[3], 0.3826834f, 1.0e-5f);

    Test_RequiredAlignmentReadySet();
    s_barometer.state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    s_barometer.ready = 0U;
    s_attitude.quaternion_wxyz[0] = 0.70710678f;
    s_attitude.quaternion_wxyz[3] = 0.70710678f;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_SummaryGet(&summary) == SYSTEM_DEVICE_OK);
    TEST_CHECK(summary.ready == 0U);
    TEST_CHECK(summary.preflight_attitude_source ==
        SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT);
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(
        quaternion, &source) == SYSTEM_DEVICE_OK);
    TEST_CHECK(source == SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT);
    TEST_CHECK_NEAR(quaternion[0], 0.70710678f, 1.0e-5f);
    TEST_CHECK_NEAR(quaternion[3], 0.70710678f, 1.0e-5f);

    s_barometer.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_barometer.ready = 1U;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_IsReady() != 0U);
    Test_GuardConditionConfirm(
        SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS + 0.01f,
        0.0f, 0.0f);
    /* The production attitude adapter keeps its frozen final result while
       the guard observes corrected inertial motion.  Restore that adapter
       contract after the generic guard test helper updates its mock q. */
    s_attitude.quaternion_wxyz[0] = 0.70710678f;
    s_attitude.quaternion_wxyz[1] = 0.0f;
    s_attitude.quaternion_wxyz[2] = 0.0f;
    s_attitude.quaternion_wxyz[3] = 0.70710678f;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_STALE);
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.final_quaternion_frozen != 0U);
    TEST_CHECK_NEAR(status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude.quaternion_wxyz[3], 0.70710678f, 1.0e-5f);
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(
        quaternion, &source) == SYSTEM_DEVICE_OK);
    TEST_CHECK(source == SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE);
    TEST_CHECK_NEAR(quaternion[0], 0.9238795f, 1.0e-5f);

    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    s_attitude.quaternion_wxyz[0] = 0.0f;
    s_attitude.quaternion_wxyz[1] = 0.0f;
    s_attitude.quaternion_wxyz[2] = 0.0f;
    s_attitude.quaternion_wxyz[3] = 1.0f;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(
        quaternion, &source) == SYSTEM_DEVICE_OK);
    TEST_CHECK(source == SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT);
    TEST_CHECK_NEAR(quaternion[3], 1.0f, 1.0e-6f);

    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(
        quaternion, &source) == SYSTEM_DEVICE_BAD_STATE);
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
    TEST_CHECK(SystemAlignment_SummaryGet(NULL) ==
        SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(NULL, &source) ==
        SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemAlignment_PreflightQuaternionGet(quaternion, NULL) ==
        SYSTEM_DEVICE_INVALID_ARGUMENT);
}

static void Test_ValidityGuard(void)
{
    SystemAlignmentStatus status;
    uint32_t index;

    TEST_CHECK(SystemAlignment_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);

    for (index = 0U; index < 20U; index++)
    {
        Test_GuardSampleAdvance(0.0f, 0.0f, 0.0f);
        TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    }
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);

    Test_GuardSampleAdvance(
        SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS + 0.01f,
        0.0f, 0.0f);
    s_guard_sample.observation_timestamp_us +=
        SYSTEM_USER_ALIGNMENT_GUARD_SAMPLE_FRESHNESS_US + 1ULL;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);

    Test_GuardSampleAdvance(
        SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS + 0.01f,
        0.0f, 0.0f);
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    Test_GuardSampleAdvance(0.0f, 0.0f, 0.0f);
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);

    s_lifecycle_state = SYSTEM_STATE_READY;
    Test_GuardConditionConfirm(
        SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS + 0.01f,
        0.0f, 0.0f);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_STALE);
    TEST_CHECK(status.stale_reason == SYSTEM_ALIGNMENT_STALE_REASON_MOTION);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(status.ready_mask ==
        (SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
         SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN |
         SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN));
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE].ready != 0U);
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].ready != 0U);
    TEST_CHECK(s_lifecycle_state == SYSTEM_STATE_PREFLIGHT);

    Test_GuardConditionConfirm(0.0f, 0.0f, 0.0f);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_STALE);
    TEST_CHECK(status.ready == 0U);

    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_COLLECTING);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);

    Test_GuardConditionConfirm(0.0f,
        SYSTEM_USER_ALIGNMENT_GUARD_ACCEL_TOLERANCE_MPS2 + 0.10f,
        0.0f);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_STALE);

    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    Test_GuardConditionConfirm(0.0f, 0.0f,
        SYSTEM_USER_ALIGNMENT_GUARD_ATTITUDE_DELTA_RAD + 0.02f);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);
    Test_GuardConditionConfirm(
        SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS + 0.01f,
        0.0f, 0.0f);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_STALE);

    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_PrepareMission() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_OriginsFreeze() == SYSTEM_DEVICE_OK);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    Test_GuardConditionConfirm(
        SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS + 1.0f,
        SYSTEM_USER_ALIGNMENT_GUARD_ACCEL_TOLERANCE_MPS2 + 2.0f,
        SYSTEM_USER_ALIGNMENT_GUARD_ATTITUDE_DELTA_RAD + 0.5f);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);
    TEST_CHECK(status.ready != 0U);
    s_lifecycle_state = SYSTEM_STATE_PREFLIGHT;
}

SystemDeviceResult SystemAlignmentBackend_Reset(void)
{ return Test_Reset(); }
SystemDeviceResult SystemAlignmentBackend_PrepareMission(void)
{ return Test_PrepareAttitude(); }
SystemDeviceResult SystemAlignmentBackend_FreezeSources(void)
{ return Test_FreezeOrigins(); }
SystemDeviceResult SystemAlignmentBackend_GuardSampleGet(
    SystemAlignmentGuardSample *sample)
{ return Test_GuardSampleGet(sample); }
void SystemAlignmentBackend_MissionPreparationAbort(void)
{ Test_Abort(); }
SystemDeviceResult SystemAlignmentBackend_SourceStatusGet(
    SystemAlignmentSourceId source_id, SystemAlignmentSourceStatus *status)
{
    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(status, 0, sizeof(*status));
    switch (source_id)
    {
        case SYSTEM_ALIGNMENT_SOURCE_ATTITUDE:
            return Test_AttitudeStatusGet(status);
        case SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN:
            return Test_GnssStatusGet(status);
        case SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN:
            return Test_BarometerStatusGet(status);
        default:
            status->state = SYSTEM_ALIGNMENT_COMPONENT_DISABLED;
            return SYSTEM_DEVICE_UNSUPPORTED;
    }
}

int main(void)
{
    SystemAlignmentStatus status;
    SystemCalibrationStatus calibration;
    SystemAlignmentSourceMask unavailable;

    Test_StartupDeviceResultsSet(SYSTEM_DEVICE_ALREADY_MATCHED,
                                 SYSTEM_DEVICE_ALREADY_MATCHED);
    SystemCalibration_Init();
    SystemAlignment_Init();
    TEST_CHECK(SystemAlignment_MasksValidate(0x07U, 0x07U, 0x05U,
        &unavailable) == SYSTEM_ALIGNMENT_CONFIG_OK);
    TEST_CHECK(unavailable == 0U);
    TEST_CHECK(SystemAlignment_MasksValidate(0x07U, 0x01U, 0x05U,
        &unavailable) == SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED);
    TEST_CHECK(SystemAlignment_MasksValidate(0x05U, 0x07U, 0x05U,
        &unavailable) == SYSTEM_ALIGNMENT_CONFIG_OK);
    TEST_CHECK(unavailable == SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN);
    TEST_CHECK(SystemAlignment_MasksValidate(0x03U, 0x07U, 0x05U,
        &unavailable) == SYSTEM_ALIGNMENT_CONFIG_REQUIRED_UNAVAILABLE);
    TEST_CHECK((unavailable & SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN) != 0U);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_IDLE);
    TEST_CHECK(status.capability_mask == 0x07U);
    TEST_CHECK(status.unavailable_mask == 0U);
    TEST_CHECK(status.selected_mask == 0x07U);
    TEST_CHECK(status.required_mask == (0x05U |
        (((SYSTEM_BUILD_ESTIMATOR_ENABLED != 0U) &&
          (SYSTEM_ESTIMATOR_GNSS_FUSION_REQUIRES_PREFLIGHT_ORIGIN != 0U)) ? 0x02U : 0U)));
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_NOT_READY);

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_IsReady() == 1U);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_COLLECTING);
    s_attitude.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_attitude.attitude_ready = 1U;
    s_attitude.quaternion_valid = 1U;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_COLLECTING);
    TEST_CHECK(status.ready_mask == SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE);
    Test_RequiredAlignmentReadySet();
    /* SS0002: ACK/attitude/barometer complete while GNSS origin is still absent. */
    s_gnss.ready = 0U;
    s_gnss.state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    if ((status.required_mask & SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U)
    {
        TEST_CHECK(status.ready == 0U);
        TEST_CHECK(Test_StartReadyGet() == 0U);
        TEST_CHECK(SystemAlignment_PrepareMission() == SYSTEM_DEVICE_NOT_READY);
    }
    else
    {
        /* Explicit Pure INS configuration remains legal without a GNSS origin. */
        TEST_CHECK(status.ready == 1U);
        TEST_CHECK(Test_StartReadyGet() == 1U);
    }
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_READY);
    TEST_CHECK(status.ready == 1U);
    TEST_CHECK(status.ready_mask ==
        (SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
         SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN |
         SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN));
    TEST_CHECK(Test_StartReadyGet() == 1U);

    s_gnss.state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    s_gnss.sample_count = 100U;
    s_gnss.horizontal_accuracy_m = 0.8f;
    s_gnss.vertical_accuracy_m = 1.2f;
    s_gnss.ready = 1U;
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_PrepareMission() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_OriginsFreeze() == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_prepare_count == 1U && s_freeze_count == 1U);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN]
        .detail.gnss.origin_valid == 1U);
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN]
        .detail.barometer.origin_valid == 1U);
    SystemAlignment_MissionPreparationAbort();
    TEST_CHECK(s_abort_count == 1U);

    TEST_CHECK(SystemAlignment_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_StatusGet(&calibration) == SYSTEM_DEVICE_OK);
    TEST_CHECK(calibration.ready == 1U);
    TEST_CHECK(calibration.mode == SYSTEM_CALIBRATION_MODE_NONE);

    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_IDLE);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_NOT_READY);

    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_Start(
        SYSTEM_CALIBRATION_MODE_ONE_FACE) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_IDLE);
    Test_OneFaceComplete();
    TEST_CHECK(SystemCalibration_IsReady() == 1U);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(Test_StartReadyGet() == 1U);

    TEST_CHECK(SystemAlignment_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_IsReady() == 1U);

    Test_SixFaceComplete();
    TEST_CHECK(SystemCalibration_IsReady() == 1U);
    TEST_CHECK(Test_StartReadyGet() == 0U);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_OK);
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(Test_StartReadyGet() == 1U);

    Test_PreflightQuaternionAuthority();
    Test_ValidityGuard();

    /* Missing GNSS blocks a GNSS navigation configuration, while explicitly
       selected Pure INS still treats this physical device as optional. */
    Test_StartupDeviceResultsSet(SYSTEM_DEVICE_ALREADY_MATCHED,
                                 SYSTEM_DEVICE_ALREADY_MATCHED);
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_GNSS].init_result =
        SYSTEM_DEVICE_IO_ERROR;
    SystemAlignment_Init();
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.capability_mask ==
        (SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE |
         SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN));
    TEST_CHECK(status.config_result ==
        (((status.required_mask & SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U) ?
            SYSTEM_ALIGNMENT_CONFIG_REQUIRED_UNAVAILABLE : SYSTEM_ALIGNMENT_CONFIG_OK));
    TEST_CHECK(status.unavailable_mask ==
        SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN);
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].state ==
        SYSTEM_ALIGNMENT_COMPONENT_DISABLED);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_Start() ==
        (((status.required_mask & SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U) ?
            SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK));
    Test_RequiredAlignmentReadySet();
    TEST_CHECK(SystemAlignment_Process() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.ready ==
        (((status.required_mask & SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN) != 0U) ? 0U : 1U));
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_GNSS_ORIGIN].state ==
        SYSTEM_ALIGNMENT_COMPONENT_DISABLED);

    /* A required source can be unavailable because of a real hardware/startup
       failure. That must block Alignment/START while keeping the configuration
       machinery operational; the build-time backend remains available. */
    Test_StartupDeviceResultsSet(SYSTEM_DEVICE_ALREADY_MATCHED,
                                 SYSTEM_DEVICE_ALREADY_MATCHED);
    s_startup_report.devices[SYSTEM_STARTUP_DEVICE_BAROMETER].start_result =
        SYSTEM_DEVICE_IO_ERROR;
    SystemAlignment_Init();
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.config_result ==
        SYSTEM_ALIGNMENT_CONFIG_REQUIRED_UNAVAILABLE);
    TEST_CHECK((status.unavailable_mask &
        SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN) != 0U);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemCalibration_Start(SYSTEM_CALIBRATION_MODE_NONE) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_UNSUPPORTED);
    TEST_CHECK(SystemAlignment_StatusGet(&status) == SYSTEM_DEVICE_OK);
    TEST_CHECK(status.state == SYSTEM_ALIGNMENT_STATE_IDLE);
    TEST_CHECK(status.ready == 0U);
    TEST_CHECK(status.component[SYSTEM_ALIGNMENT_SOURCE_BARO_ORIGIN].state ==
        SYSTEM_ALIGNMENT_COMPONENT_DISABLED);

    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TEST_CHECK(SystemAlignment_Start() == SYSTEM_DEVICE_BAD_STATE);
    TEST_CHECK(SystemAlignment_Stop() == SYSTEM_DEVICE_BAD_STATE);
    TEST_CHECK(SystemAlignment_Reset() == SYSTEM_DEVICE_BAD_STATE);
    TEST_CHECK(SystemCalibration_Reset() == SYSTEM_DEVICE_BAD_STATE);

    TEST_CHECK(strcmp(SystemAlignment_StateText(
        SYSTEM_ALIGNMENT_STATE_CHECKING), "CHECKING") == 0);
    TEST_CHECK(strcmp(SystemAlignment_StateText(
        SYSTEM_ALIGNMENT_STATE_STALE), "STALE") == 0);
    TEST_CHECK(strcmp(SystemAlignment_StaleReasonText(
        SYSTEM_ALIGNMENT_STALE_REASON_MOTION), "MOTION") == 0);
    TEST_CHECK(strcmp(SystemAlignment_ComponentStateText(
        SYSTEM_ALIGNMENT_COMPONENT_DISABLED), "DISABLED") == 0);
    TEST_CHECK(strcmp(SystemAlignment_AttitudeSourceText(
        SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION),
        "HARDWARE_QUATERNION") == 0);
    TEST_CHECK(strcmp(SystemAlignment_AttitudeSourceText(
        SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_KNOWN_YAW),
        "GRAVITY_KNOWN_YAW") == 0);
    TEST_CHECK(strcmp(SystemAlignment_SourceDescriptorGet(
        SYSTEM_ALIGNMENT_SOURCE_MAGNETIC)->key, "mag") == 0);
    TEST_CHECK(s_reset_count >= 8U);
    return Test_Finish("system_alignment");
}
