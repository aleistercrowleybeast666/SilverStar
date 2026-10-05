#include "system_calibration.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_alignment.h"
#include "system_source_selector.h"
#include "system_lifecycle.h"
#include "system_user_config.h"
#include "system_user_startup_config.h"

typedef enum
{
    SYSTEM_CALIBRATION_COLLECTOR_WAIT_STREAM = 0U,
    SYSTEM_CALIBRATION_COLLECTOR_SETTLING,
    SYSTEM_CALIBRATION_COLLECTOR_WINDOW
} SystemCalibrationCollectorState;

static SystemCalibrationStatus s_status;
static SystemInertialSample s_latest_sample;
static float s_accel_sum[3];
static float s_gyro_sum[3];
static float s_accel_square_sum[3];
static float s_gyro_square_sum[3];
static float s_pending_accel_mean[3];
static float s_pending_gyro_mean[3];
static uint64_t s_state_start_us;
static uint64_t s_last_sample_us;
static SystemCalibrationCollectorState s_collector_state;
static volatile uint8_t s_initialized;
static volatile uint8_t s_sampling_active;
static volatile uint8_t s_compute_pending;
static volatile uint8_t s_latest_sample_valid;
static volatile uint8_t s_action_active;

static PlatformCriticalState SystemCalibration_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemCalibration_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

static uint8_t SystemCalibration_ModificationAllowed(void)
{
    SystemLifecycleState state = SystemLifecycle_GetState();

    return (uint8_t)((state == SYSTEM_STATE_BOOT) ||
                     (state == SYSTEM_STATE_SELF_TEST) ||
                     (state == SYSTEM_STATE_PREFLIGHT) ||
                     (state == SYSTEM_STATE_READY));
}

static uint8_t SystemCalibration_ActionBegin(void)
{
    uint8_t result = 0U;
    uint32_t primask = SystemCalibration_IrqLock();

    if ((s_initialized != 0U) && (s_action_active == 0U))
    {
        s_action_active = 1U;
        result = 1U;
    }
    SystemCalibration_IrqUnlock(primask);
    return result;
}

static void SystemCalibration_ActionEnd(void)
{
    uint32_t primask = SystemCalibration_IrqLock();

    s_action_active = 0U;
    SystemCalibration_IrqUnlock(primask);
}

static void SystemCalibration_StateSet(SystemCalibrationState state)
{
    if (s_status.state != state)
    {
        s_status.state = state;
        s_status.state_sequence++;
    }
}

static void SystemCalibration_IdentitySet(SystemCalibrationMode mode,
                                          uint8_t ready)
{
    uint8_t index;

    (void)memset(&s_status.correction, 0,
                 sizeof(s_status.correction));
    s_status.correction.mode = mode;
    s_status.correction.ready = ready;
    for (index = 0U; index < 3U; index++)
    {
        s_status.correction.accel_scale[index] = 1.0f;
        s_status.correction.gyro_scale[index] = 1.0f;
    }
    s_status.ready = ready;
}

static void SystemCalibration_WindowReset(uint64_t timestamp_us)
{
    (void)memset(s_accel_sum, 0, sizeof(s_accel_sum));
    (void)memset(s_gyro_sum, 0, sizeof(s_gyro_sum));
    (void)memset(s_accel_square_sum, 0, sizeof(s_accel_square_sum));
    (void)memset(s_gyro_square_sum, 0, sizeof(s_gyro_square_sum));
    s_status.samples = 0U;
    s_state_start_us = timestamp_us;
}

static SystemCalibrationFace SystemCalibration_DiagnosticFaceGet(void)
{
    if ((s_status.mode == SYSTEM_CALIBRATION_MODE_SIX_FACE) &&
        (s_status.current_face <= SYSTEM_CALIBRATION_FACE_Z_NEGATIVE))
    {
        return s_status.current_face;
    }
    return SYSTEM_CALIBRATION_FACE_NONE;
}

static void SystemCalibration_DiagnosticSet(
    SystemCalibrationFace face,
    SystemCalibrationWaitReason reason)
{
    s_status.wait_reason = reason;
    if ((s_status.diagnostic_face == face) &&
        (s_status.diagnostic_reason == reason))
    {
        return;
    }
    s_status.diagnostic_face = face;
    s_status.diagnostic_reason = reason;
    s_status.diagnostic_sequence++;
}

static void SystemCalibration_DiagnosticReset(SystemCalibrationFace face)
{
    s_status.wait_reason = SYSTEM_CALIBRATION_WAIT_NONE;
    if (s_status.diagnostic_reason != SYSTEM_CALIBRATION_WAIT_NONE)
    {
        s_status.diagnostic_sequence++;
    }
    s_status.diagnostic_face = face;
    s_status.diagnostic_reason = SYSTEM_CALIBRATION_WAIT_NONE;
}

static void SystemCalibration_CollectorReset(uint8_t publish_diagnostic)
{
    SystemCalibration_WindowReset(0ULL);
    (void)memset(s_pending_accel_mean, 0,
                 sizeof(s_pending_accel_mean));
    (void)memset(s_pending_gyro_mean, 0,
                 sizeof(s_pending_gyro_mean));
    s_last_sample_us = 0ULL;
    s_collector_state = SYSTEM_CALIBRATION_COLLECTOR_WAIT_STREAM;
    if (publish_diagnostic != 0U)
    {
        SystemCalibration_DiagnosticSet(
            SystemCalibration_DiagnosticFaceGet(),
            SYSTEM_CALIBRATION_WAIT_NO_STREAM);
    }
    else
    {
        s_status.wait_reason = SYSTEM_CALIBRATION_WAIT_NO_STREAM;
    }
}

static void SystemCalibration_StatusReset(void)
{
    uint32_t start_sequence = s_status.start_sequence;
    uint32_t state_sequence = s_status.state_sequence;
    uint32_t face_event_sequence = s_status.face_event_sequence;
    uint32_t diagnostic_sequence = s_status.diagnostic_sequence;
    uint8_t diagnostic_clear = (uint8_t)(
        s_status.diagnostic_reason != SYSTEM_CALIBRATION_WAIT_NONE);

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(&s_status, 0, sizeof(s_status));
    s_status.start_sequence = start_sequence;
    s_status.state_sequence = state_sequence;
    s_status.face_event_sequence = face_event_sequence;
    s_status.diagnostic_sequence = diagnostic_sequence + diagnostic_clear;
    s_status.mode = SYSTEM_CALIBRATION_MODE_NOT_SELECTED;
    s_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_status.last_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_status.diagnostic_face = SYSTEM_CALIBRATION_FACE_NONE;
    s_status.diagnostic_reason = SYSTEM_CALIBRATION_WAIT_NONE;
    s_status.state = SYSTEM_CALIBRATION_STATE_IDLE;
    SystemCalibration_IdentitySet(
        SYSTEM_CALIBRATION_MODE_NOT_SELECTED, 0U);
    SystemCalibration_CollectorReset(0U);
}

static void SystemCalibration_DirectionGet(SystemCalibrationFace face,
                                           float direction[3])
{
    direction[0] = 0.0f;
    direction[1] = 0.0f;
    direction[2] = 0.0f;
    switch (face)
    {
        case SYSTEM_CALIBRATION_FACE_X_POSITIVE: direction[0] = 1.0f; break;
        case SYSTEM_CALIBRATION_FACE_X_NEGATIVE: direction[0] = -1.0f; break;
        case SYSTEM_CALIBRATION_FACE_Y_POSITIVE: direction[1] = 1.0f; break;
        case SYSTEM_CALIBRATION_FACE_Y_NEGATIVE: direction[1] = -1.0f; break;
        case SYSTEM_CALIBRATION_FACE_Z_POSITIVE: direction[2] = 1.0f; break;
        case SYSTEM_CALIBRATION_FACE_Z_NEGATIVE: direction[2] = -1.0f; break;
        case SYSTEM_CALIBRATION_FACE_NONE:
        default: break;
    }
}

static SystemCalibrationFace SystemCalibration_StartupFaceGet(void)
{
    return (SystemCalibrationFace)SYSTEM_IMU_STARTUP_GRAVITY_DIRECTION;
}

static SystemCalibrationWaitReason SystemCalibration_StaticSampleCheck(
    const SystemInertialSample *sample,
    SystemCalibrationFace face,
    uint8_t check_gap)
{
    float gyro_norm;
    float accel_norm;
    float expected_direction[3];
    float direction_dot;

    if ((sample == NULL) ||
        ((sample->valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL |
                                SYSTEM_INERTIAL_VALID_GYRO)) !=
         (SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO)))
    {
        return SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemInertialSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((check_gap != 0U) && (s_last_sample_us != 0ULL) &&
        ((sample->sample_timestamp_us <= s_last_sample_us) ||
         ((sample->sample_timestamp_us - s_last_sample_us) >
          SYSTEM_IMU_BIAS_MAX_SAMPLE_GAP_US)))
    {
        return SYSTEM_CALIBRATION_WAIT_SAMPLE_GAP;
    }
    gyro_norm = sqrtf(
        (sample->gyro_b_radps[0] * sample->gyro_b_radps[0]) +
        (sample->gyro_b_radps[1] * sample->gyro_b_radps[1]) +
        (sample->gyro_b_radps[2] * sample->gyro_b_radps[2]));
    accel_norm = sqrtf(
        (sample->accel_b_mps2[0] * sample->accel_b_mps2[0]) +
        (sample->accel_b_mps2[1] * sample->accel_b_mps2[1]) +
        (sample->accel_b_mps2[2] * sample->accel_b_mps2[2]));
    if ((!isfinite(gyro_norm)) || (!isfinite(accel_norm)) ||
        (accel_norm <= 1.0e-6f))
    {
        return SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE;
    }
    if (gyro_norm > SYSTEM_IMU_BIAS_MAX_GYRO_RADPS)
    {
        return SYSTEM_CALIBRATION_WAIT_GYRO_MOVING;
    }
    if (fabsf(accel_norm - SYSTEM_LOCAL_GRAVITY_MPS2) >
        SYSTEM_IMU_BIAS_ACCEL_TOLERANCE_MPS2)
    {
        return SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE;
    }
    SystemCalibration_DirectionGet(face, expected_direction);
    direction_dot =
        ((sample->accel_b_mps2[0] / accel_norm) * expected_direction[0]) +
        ((sample->accel_b_mps2[1] / accel_norm) * expected_direction[1]) +
        ((sample->accel_b_mps2[2] / accel_norm) * expected_direction[2]);
    if ((!isfinite(direction_dot)) ||
        (direction_dot < SYSTEM_IMU_GRAVITY_DIRECTION_COS_MIN))
    {
        return SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION;
    }
    return SYSTEM_CALIBRATION_WAIT_NONE;
}

static uint8_t SystemCalibration_VarianceValid(void)
{
    float count = (float)s_status.samples;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < 3U; index++)
    {
        float accel_mean = s_accel_sum[index] / count;
        float gyro_mean = s_gyro_sum[index] / count;
        float accel_variance = (s_accel_square_sum[index] / count) -
                               (accel_mean * accel_mean);
        float gyro_variance = (s_gyro_square_sum[index] / count) -
                              (gyro_mean * gyro_mean);

        if ((!isfinite(accel_variance)) || (!isfinite(gyro_variance)) ||
            (accel_variance > SYSTEM_IMU_BIAS_ACCEL_VARIANCE_MAX_M2PS4) ||
            (gyro_variance > SYSTEM_IMU_BIAS_GYRO_VARIANCE_MAX_RAD2PS2))
        {
            return 0U;
        }
    }
    return 1U;
}

static void SystemCalibration_FaceEventSet(
    SystemCalibrationFace face,
    SystemCalibrationFaceResult result)
{
    s_status.last_face = face;
    s_status.last_face_result = result;
    s_status.face_event_sequence++;
}

static void SystemCalibration_WindowComplete(void)
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < 3U; index++)
    {
        s_pending_accel_mean[index] =
            s_accel_sum[index] / (float)s_status.samples;
        s_pending_gyro_mean[index] =
            s_gyro_sum[index] / (float)s_status.samples;
    }
    if (s_status.mode == SYSTEM_CALIBRATION_MODE_SIX_FACE)
    {
        uint8_t face = (uint8_t)s_status.current_face;

        (void)memcpy(
            s_status.six_face_measurements.accel_mean_mps2[face],
            s_pending_accel_mean, sizeof(s_pending_accel_mean));
        (void)memcpy(
            s_status.six_face_measurements.gyro_mean_radps[face],
            s_pending_gyro_mean, sizeof(s_pending_gyro_mean));
        s_status.completed_face_mask |= (uint8_t)(1U << face);
        SystemCalibration_FaceEventSet(
            s_status.current_face,
            SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE);
        s_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
        s_sampling_active = 0U;
        if (s_status.completed_face_mask == SYSTEM_CALIBRATION_FACE_MASK_ALL)
        {
            s_compute_pending = 1U;
            SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_CHECKING);
        }
        else
        {
            SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_WAIT_FACE);
        }
    }
    else
    {
        s_sampling_active = 0U;
        s_compute_pending = 1U;
        SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_CHECKING);
    }
}

static void SystemCalibration_NoneReadySet(void)
{
    s_status.start_sequence++;
    s_status.mode = SYSTEM_CALIBRATION_MODE_NONE;
    SystemCalibration_IdentitySet(SYSTEM_CALIBRATION_MODE_NONE, 1U);
    SystemCalibration_DiagnosticSet(SYSTEM_CALIBRATION_FACE_NONE,
        SYSTEM_CALIBRATION_WAIT_NONE);
    SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_READY);
}

void SystemCalibration_Init(void)
{
    uint32_t primask = SystemCalibration_IrqLock();

    (void)memset(&s_status, 0, sizeof(s_status));
    (void)memset(&s_latest_sample, 0, sizeof(s_latest_sample));
    s_initialized = 1U;
    s_sampling_active = 0U;
    s_compute_pending = 0U;
    s_latest_sample_valid = 0U;
    s_action_active = 0U;
    SystemCalibration_StatusReset();
    if (SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK == 0U)
    {
        /* Identity needs no sample or source lock during pre-scheduler boot.
         * ALIGN_START still selects and locks the physical IMU before use. */
        SystemCalibration_NoneReadySet();
    }
    SystemCalibration_IrqUnlock(primask);
}

static void SystemCalibration_OneFaceCorrectionApply(void)
{
    float direction[3];
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemCalibration_DirectionGet(SystemCalibration_StartupFaceGet(),
                                   direction);
    SystemCalibration_IdentitySet(SYSTEM_CALIBRATION_MODE_ONE_FACE, 1U);
    for (index = 0U; index < 3U; index++)
    {
        s_status.correction.accel_bias_mps2[index] =
            s_pending_accel_mean[index] -
            (direction[index] * SYSTEM_LOCAL_GRAVITY_MPS2);
        s_status.correction.gyro_bias_radps[index] =
            s_pending_gyro_mean[index];
    }
    s_compute_pending = 0U;
    SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_READY);
}

static void SystemCalibration_SixFaceCorrectionApply(void)
{
    ImuSixFaceCorrection correction;
    ImuSixFaceResult result;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    result = ImuSixFace_CorrectionCalculate(
        &s_status.six_face_measurements,
        SYSTEM_LOCAL_GRAVITY_MPS2,
        SYSTEM_IMU_CAL_ACCEL_SCALE_MIN,
        SYSTEM_IMU_CAL_ACCEL_SCALE_MAX,
        &correction);
    if (result == IMU_SIX_FACE_RESULT_OK)
    {
        s_status.correction.mode = SYSTEM_CALIBRATION_MODE_SIX_FACE;
        (void)memcpy(s_status.correction.accel_bias_mps2,
                     correction.accel_bias_mps2,
                     sizeof(s_status.correction.accel_bias_mps2));
        (void)memcpy(s_status.correction.accel_scale,
                     correction.accel_scale,
                     sizeof(s_status.correction.accel_scale));
        (void)memcpy(s_status.correction.gyro_bias_radps,
                     correction.gyro_bias_radps,
                     sizeof(s_status.correction.gyro_bias_radps));
        (void)memcpy(s_status.correction.gyro_scale,
                     correction.gyro_scale,
                     sizeof(s_status.correction.gyro_scale));
        s_status.correction.ready = 1U;
        s_status.ready = 1U;
        SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_READY);
    }
    else
    {
        SystemCalibration_IdentitySet(SYSTEM_CALIBRATION_MODE_SIX_FACE, 0U);
        SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_FAILED);
    }
    s_compute_pending = 0U;
}

void SystemCalibration_Process(void)
{
    if ((s_compute_pending == 0U) ||
        (SystemCalibration_ActionBegin() == 0U))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (s_status.mode == SYSTEM_CALIBRATION_MODE_ONE_FACE)
    {
        SystemCalibration_OneFaceCorrectionApply();
    }
    else if (s_status.mode == SYSTEM_CALIBRATION_MODE_SIX_FACE)
    {
        SystemCalibration_SixFaceCorrectionApply();
    }
    SystemCalibration_ActionEnd();
}

static void SystemCalibration_LatestSampleStore(
    const SystemInertialSample *sample)
{
    uint32_t primask = SystemCalibration_IrqLock();

    s_latest_sample = *sample;
    s_latest_sample_valid = (uint8_t)(
        ((sample->valid_mask & (SYSTEM_INERTIAL_VALID_ACCEL |
                                SYSTEM_INERTIAL_VALID_GYRO)) ==
         (SYSTEM_INERTIAL_VALID_ACCEL | SYSTEM_INERTIAL_VALID_GYRO)) ?
        1U : 0U);
    SystemCalibration_IrqUnlock(primask);
}

static uint8_t SystemCalibration_WaitStreamProcess(
    const SystemInertialSample *sample)
{
    if (s_collector_state != SYSTEM_CALIBRATION_COLLECTOR_WAIT_STREAM)
    {
        return 0U;
    }
    s_collector_state = SYSTEM_CALIBRATION_COLLECTOR_SETTLING;
    s_state_start_us = sample->sample_timestamp_us;
    s_last_sample_us = sample->sample_timestamp_us;
    SystemCalibration_DiagnosticSet(SystemCalibration_DiagnosticFaceGet(),
        SYSTEM_CALIBRATION_WAIT_NONE);
    return 1U;
}

static uint8_t SystemCalibration_SettlingProcess(
    const SystemInertialSample *sample,
    SystemCalibrationWaitReason reason)
{
    SILVERSTAR_ASSERT_OBJECT(sample, SystemInertialSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (s_collector_state != SYSTEM_CALIBRATION_COLLECTOR_SETTLING)
    {
        return 0U;
    }
    if (reason != SYSTEM_CALIBRATION_WAIT_NONE)
    {
        s_status.reject_count++;
        SystemCalibration_DiagnosticSet(
            SystemCalibration_DiagnosticFaceGet(), reason);
        s_state_start_us = sample->sample_timestamp_us;
        return 1U;
    }
    SystemCalibration_DiagnosticSet(SystemCalibration_DiagnosticFaceGet(),
        SYSTEM_CALIBRATION_WAIT_NONE);
    if ((sample->sample_timestamp_us - s_state_start_us) <
        SYSTEM_IMU_BIAS_SETTLE_TIME_US)
    {
        return 1U;
    }
    s_collector_state = SYSTEM_CALIBRATION_COLLECTOR_WINDOW;
    SystemCalibration_WindowReset(sample->sample_timestamp_us);
    return 0U;
}

static void SystemCalibration_WindowReject(
    const SystemInertialSample *sample,
    SystemCalibrationWaitReason reason)
{
    s_status.reject_count++;
    s_status.retry_count++;
    SystemCalibration_DiagnosticSet(SystemCalibration_DiagnosticFaceGet(),
        reason);
    s_collector_state = SYSTEM_CALIBRATION_COLLECTOR_SETTLING;
    SystemCalibration_WindowReset(sample->sample_timestamp_us);
}

static void SystemCalibration_WindowSampleAdd(
    const SystemInertialSample *sample)
{
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(sample, SystemInertialSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    for (index = 0U; index < 3U; index++)
    {
        s_accel_sum[index] += sample->accel_b_mps2[index];
        s_gyro_sum[index] += sample->gyro_b_radps[index];
        s_accel_square_sum[index] +=
            sample->accel_b_mps2[index] * sample->accel_b_mps2[index];
        s_gyro_square_sum[index] +=
            sample->gyro_b_radps[index] * sample->gyro_b_radps[index];
    }
    s_status.samples++;
    if ((s_status.samples < SYSTEM_IMU_BIAS_MIN_VALID_SAMPLES) ||
        ((sample->sample_timestamp_us - s_state_start_us) <
         SYSTEM_IMU_BIAS_MIN_DURATION_US))
    {
        return;
    }
    if (SystemCalibration_VarianceValid() == 0U)
    {
        s_status.retry_count++;
        SystemCalibration_DiagnosticSet(SystemCalibration_DiagnosticFaceGet(),
            SYSTEM_CALIBRATION_WAIT_VARIANCE);
        s_collector_state = SYSTEM_CALIBRATION_COLLECTOR_SETTLING;
        SystemCalibration_WindowReset(sample->sample_timestamp_us);
    }
    else
    {
        SystemCalibration_WindowComplete();
    }
}

void SystemCalibration_ImuSampleProcess(const SystemInertialSample *sample)
{
    SystemCalibrationWaitReason reason;

    if ((sample == NULL) || (s_initialized == 0U))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemInertialSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SystemCalibration_LatestSampleStore(sample);
    if ((s_sampling_active == 0U) ||
        (SystemCalibration_ActionBegin() == 0U))
    {
        return;
    }
    if (SystemCalibration_WaitStreamProcess(sample) != 0U)
    {
        SystemCalibration_ActionEnd();
        return;
    }
    reason = SystemCalibration_StaticSampleCheck(
        sample, s_status.current_face, 1U);
    s_last_sample_us = sample->sample_timestamp_us;
    if (SystemCalibration_SettlingProcess(sample, reason) != 0U)
    {
        SystemCalibration_ActionEnd();
        return;
    }
    if (reason != SYSTEM_CALIBRATION_WAIT_NONE)
    {
        SystemCalibration_WindowReject(sample, reason);
        SystemCalibration_ActionEnd();
        return;
    }
    SystemCalibration_DiagnosticSet(
        SystemCalibration_DiagnosticFaceGet(),
        SYSTEM_CALIBRATION_WAIT_NONE);
    SystemCalibration_WindowSampleAdd(sample);
    SystemCalibration_ActionEnd();
}

static SystemDeviceResult SystemCalibration_FaceSampleValidate(
    SystemCalibrationFace face,
    SystemInertialSample *latest_sample)
{
    SystemCalibrationWaitReason reason;
    uint32_t primask;
    uint8_t latest_sample_valid;

    (void)memset(latest_sample, 0, sizeof(*latest_sample));
    SILVERSTAR_ASSERT_OBJECT(latest_sample, SystemInertialSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    primask = SystemCalibration_IrqLock();
    *latest_sample = s_latest_sample;
    latest_sample_valid = s_latest_sample_valid;
    SystemCalibration_IrqUnlock(primask);
    if (latest_sample_valid == 0U)
    {
        SystemCalibration_DiagnosticSet(face,
            SYSTEM_CALIBRATION_WAIT_NO_STREAM);
        SystemCalibration_FaceEventSet(face,
            SYSTEM_CALIBRATION_FACE_RESULT_FAILED);
        return SYSTEM_DEVICE_NOT_READY;
    }
    reason = SystemCalibration_StaticSampleCheck(latest_sample, face, 0U);
    if (reason != SYSTEM_CALIBRATION_WAIT_NONE)
    {
        SystemCalibration_DiagnosticSet(face, reason);
        s_status.reject_count++;
        SystemCalibration_FaceEventSet(face,
            SYSTEM_CALIBRATION_FACE_RESULT_FAILED);
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SystemCalibration_FaceCorrectionInvalidate(
    uint8_t face_mask)
{
    SystemDeviceResult result;

    if (((s_status.completed_face_mask & face_mask) == 0U) &&
        (s_status.ready == 0U))
    {
        return SYSTEM_DEVICE_OK;
    }
    result = SystemAlignment_CalibrationInvalidate();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    s_status.completed_face_mask &= (uint8_t)(~face_mask);
    SystemCalibration_IdentitySet(SYSTEM_CALIBRATION_MODE_SIX_FACE, 0U);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SystemCalibration_ModeValidate(SystemCalibrationMode mode)
{
    if ((uint32_t)mode > (uint32_t)SYSTEM_CALIBRATION_MODE_SIX_FACE)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (((SYSTEM_CALIBRATION_CAPABILITY_NONE |
          SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK) &
         (1UL << (uint32_t)mode)) == 0U)
    {
        /* Reject before locking a source or invalidating either subsystem. */
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Start(SystemCalibrationMode mode)
{
    SystemDeviceResult invalidate_result;
    SystemDeviceResult selector_result;
    uint32_t primask;

    if (SystemCalibration_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    selector_result = SystemCalibration_ModeValidate(mode);
    if (selector_result != SYSTEM_DEVICE_OK) { return selector_result; }
    selector_result = SystemSourceSelector_ImuSelectAndLock();
    if (selector_result != SYSTEM_DEVICE_OK)
    {
        return selector_result;
    }
    if (SystemCalibration_ActionBegin() == 0U)
    {
        return SYSTEM_DEVICE_BUSY;
    }
    invalidate_result = SystemAlignment_CalibrationInvalidate();
    if (invalidate_result != SYSTEM_DEVICE_OK)
    {
        SystemCalibration_ActionEnd();
        return invalidate_result;
    }
    primask = SystemCalibration_IrqLock();
    SystemCalibration_StatusReset();
    s_status.start_sequence++;
    s_status.mode = mode;
    s_status.correction.mode = mode;
    s_sampling_active = 0U;
    s_compute_pending = 0U;
    if (mode == SYSTEM_CALIBRATION_MODE_NONE)
    {
        SystemCalibration_IdentitySet(mode, 1U);
        SystemCalibration_DiagnosticSet(
            SYSTEM_CALIBRATION_FACE_NONE,
            SYSTEM_CALIBRATION_WAIT_NONE);
        SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_READY);
    }
    else if (mode == SYSTEM_CALIBRATION_MODE_ONE_FACE)
    {
        s_status.current_face = SystemCalibration_StartupFaceGet();
        s_sampling_active = 1U;
        SystemCalibration_CollectorReset(1U);
        SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_COLLECTING);
    }
    else
    {
        SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_WAIT_FACE);
    }
    SystemCalibration_IrqUnlock(primask);
    SystemCalibration_ActionEnd();
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_FaceCollect(SystemCalibrationFace face)
{
    SystemDeviceResult result;
    SystemInertialSample latest_sample;
    uint8_t face_mask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemCalibration_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (face > SYSTEM_CALIBRATION_FACE_Z_NEGATIVE)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    if (SystemCalibration_ActionBegin() == 0U)
    {
        return SYSTEM_DEVICE_BUSY;
    }
    if ((s_status.mode != SYSTEM_CALIBRATION_MODE_SIX_FACE) ||
        ((s_status.state != SYSTEM_CALIBRATION_STATE_WAIT_FACE) &&
         (s_status.state != SYSTEM_CALIBRATION_STATE_READY)))
    {
        SystemCalibration_ActionEnd();
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (s_sampling_active != 0U)
    {
        SystemCalibration_ActionEnd();
        return SYSTEM_DEVICE_BUSY;
    }
    result = SystemCalibration_FaceSampleValidate(face, &latest_sample);
    if (result != SYSTEM_DEVICE_OK)
    {
        SystemCalibration_ActionEnd();
        return result;
    }
    face_mask = (uint8_t)(1U << (uint8_t)face);
    result = SystemCalibration_FaceCorrectionInvalidate(face_mask);
    if (result != SYSTEM_DEVICE_OK)
    {
        SystemCalibration_ActionEnd();
        return result;
    }
    s_status.current_face = face;
    SystemCalibration_DiagnosticReset(face);
    s_sampling_active = 1U;
    s_compute_pending = 0U;
    SystemCalibration_CollectorReset(1U);
    SystemCalibration_StateSet(SYSTEM_CALIBRATION_STATE_COLLECTING);
    SystemCalibration_ActionEnd();
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Stop(void)
{
    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemCalibration_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (SystemCalibration_ActionBegin() == 0U)
    {
        return SYSTEM_DEVICE_BUSY;
    }
    if (s_status.ready == 0U)
    {
        s_sampling_active = 0U;
        s_compute_pending = 0U;
        s_status.current_face = SYSTEM_CALIBRATION_FACE_NONE;
        SystemCalibration_DiagnosticSet(
            SYSTEM_CALIBRATION_FACE_NONE,
            SYSTEM_CALIBRATION_WAIT_NONE);
        SystemCalibration_StateSet(
            (s_status.mode == SYSTEM_CALIBRATION_MODE_SIX_FACE) ?
                SYSTEM_CALIBRATION_STATE_WAIT_FACE :
                SYSTEM_CALIBRATION_STATE_IDLE);
    }
    SystemCalibration_ActionEnd();
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_Reset(void)
{
    SystemDeviceResult invalidate_result;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemCalibration_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (SystemCalibration_ActionBegin() == 0U)
    {
        return SYSTEM_DEVICE_BUSY;
    }
    invalidate_result = SystemAlignment_CalibrationInvalidate();
    if (invalidate_result != SYSTEM_DEVICE_OK)
    {
        SystemCalibration_ActionEnd();
        return invalidate_result;
    }
    primask = SystemCalibration_IrqLock();
    s_sampling_active = 0U;
    s_compute_pending = 0U;
    SystemCalibration_StatusReset();
    if (SYSTEM_CALIBRATION_BUILD_PROCEDURE_MASK == 0U)
    {
        SystemCalibration_NoneReadySet();
    }
    SystemCalibration_IrqUnlock(primask);
    SystemCalibration_ActionEnd();
    return SYSTEM_DEVICE_OK;
}

uint32_t SystemCalibration_GenerationGet(void)
{
    PlatformCriticalState lock = SystemCalibration_IrqLock();
    uint32_t generation = s_status.start_sequence;
    SystemCalibration_IrqUnlock(lock);
    return generation;
}

SystemDeviceResult SystemCalibration_StatusGet(SystemCalibrationStatus *status)
{
    uint32_t primask;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemCalibrationStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    primask = SystemCalibration_IrqLock();
    if (s_initialized == 0U)
    {
        SystemCalibration_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_action_active != 0U)
    {
        SystemCalibration_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    *status = s_status;
    SystemCalibration_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemCalibration_ImuCorrectionGet(
    SystemCalibrationImuCorrection *correction)
{
    uint32_t primask;

    if (correction == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(correction, SystemCalibrationImuCorrection,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    primask = SystemCalibration_IrqLock();
    if ((s_initialized == 0U) || (s_status.correction.ready == 0U))
    {
        SystemCalibration_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_action_active != 0U)
    {
        SystemCalibration_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    *correction = s_status.correction;
    SystemCalibration_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemCalibration_IsReady(void)
{
    uint8_t ready;
    uint32_t primask = SystemCalibration_IrqLock();

    ready = (uint8_t)((s_initialized != 0U) &&
                      (s_action_active == 0U) &&
                      (s_status.ready != 0U));
    SystemCalibration_IrqUnlock(primask);
    return ready;
}

const char *SystemCalibration_ModeText(SystemCalibrationMode mode)
{
    switch (mode)
    {
        case SYSTEM_CALIBRATION_MODE_NONE: return "NONE";
        case SYSTEM_CALIBRATION_MODE_ONE_FACE: return "ONE_FACE";
        case SYSTEM_CALIBRATION_MODE_SIX_FACE: return "SIX_FACE";
        case SYSTEM_CALIBRATION_MODE_NOT_SELECTED:
        default: return "NOT_SELECTED";
    }
}

const char *SystemCalibration_StateText(SystemCalibrationState state)
{
    switch (state)
    {
        case SYSTEM_CALIBRATION_STATE_IDLE: return "IDLE";
        case SYSTEM_CALIBRATION_STATE_WAIT_FACE: return "WAIT_FACE";
        case SYSTEM_CALIBRATION_STATE_COLLECTING: return "COLLECTING";
        case SYSTEM_CALIBRATION_STATE_CHECKING: return "CHECKING";
        case SYSTEM_CALIBRATION_STATE_READY: return "READY";
        case SYSTEM_CALIBRATION_STATE_FAILED:
        default: return "FAILED";
    }
}

const char *SystemCalibration_FaceText(SystemCalibrationFace face)
{
    switch (face)
    {
        case SYSTEM_CALIBRATION_FACE_X_POSITIVE: return "X+";
        case SYSTEM_CALIBRATION_FACE_X_NEGATIVE: return "X-";
        case SYSTEM_CALIBRATION_FACE_Y_POSITIVE: return "Y+";
        case SYSTEM_CALIBRATION_FACE_Y_NEGATIVE: return "Y-";
        case SYSTEM_CALIBRATION_FACE_Z_POSITIVE: return "Z+";
        case SYSTEM_CALIBRATION_FACE_Z_NEGATIVE: return "Z-";
        case SYSTEM_CALIBRATION_FACE_NONE:
        default: return "NONE";
    }
}

const char *SystemCalibration_WaitReasonText(
    SystemCalibrationWaitReason reason)
{
    switch (reason)
    {
        case SYSTEM_CALIBRATION_WAIT_NONE: return "NONE";
        case SYSTEM_CALIBRATION_WAIT_NO_STREAM: return "NO_STREAM";
        case SYSTEM_CALIBRATION_WAIT_GYRO_MOVING: return "GYRO_MOVING";
        case SYSTEM_CALIBRATION_WAIT_ACCEL_MAGNITUDE:
            return "ACCEL_MAGNITUDE";
        case SYSTEM_CALIBRATION_WAIT_GRAVITY_DIRECTION:
            return "GRAVITY_DIRECTION";
        case SYSTEM_CALIBRATION_WAIT_VARIANCE: return "VARIANCE";
        case SYSTEM_CALIBRATION_WAIT_SAMPLE_GAP:
        default: return "SAMPLE_GAP";
    }
}

const char *SystemCalibration_FaceResultText(
    SystemCalibrationFaceResult result)
{
    switch (result)
    {
        case SYSTEM_CALIBRATION_FACE_RESULT_FAILED: return "FAILED";
        case SYSTEM_CALIBRATION_FACE_RESULT_COMPLETE: return "PASSED";
        case SYSTEM_CALIBRATION_FACE_RESULT_NONE:
        default: return "NONE";
    }
}
