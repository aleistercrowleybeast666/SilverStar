#include "ins_task.h"

#include <stddef.h>
#include <string.h>

#include "app_tasks.h"
#include "alignment_strategy_binding.h"
#include "attitude_frame.h"
#include "attitude_preflight.h"
#include "FreeRTOS.h"
#include "task.h"
#include "estimator_bus.h"
#include "estimator_task.h"
#include "imu_sample_bus.h"
#include "ins_mechanization.h"
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
#include "logger_bus.h"
#endif
#include "platform_critical.h"
#include "platform_memory.h"
#include "silverstar_assert.h"
#include "system_alignment.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_estimator_diagnostics.h"
#include "system_health.h"
#include "system_navigation_health.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_navigation_backend.h"
#include "system_lifecycle.h"
#include "system_magnetometer_if.h"
#include "system_navigation_profile.h"
#include "system_time.h"

#define INS_MAX_SAMPLES_PER_CYCLE 64U

typedef struct
{
    uint8_t final_ready;
    uint8_t source_available;
    uint8_t calibration_ready;
} InsTaskAlignmentFlags;

static union
{
    InsInertialContext inertial;
    InsMechanizationContext pure_ins;
} s_navigation_input;
static AttitudePreflightContext s_preflight_attitude;
static PLATFORM_CPU_FAST_BSS AlignmentStrategyContext s_alignment_strategy;
static InsAlignmentSnapshot s_alignment_snapshot;
static InsOutputSnapshot s_output;
static InsOutputSnapshot s_published_output;
static uint32_t s_increment_sequence;
static SystemAlignmentAttitudeSource s_alignment_source;
static uint8_t s_alignment_invalid_sample_seen;
static uint8_t s_attitude_source_available;
static uint8_t s_alignment_final_ready;
static volatile uint8_t s_calibration_ready;
static volatile uint8_t s_mission_attitude_frozen;
static volatile uint8_t s_mission_running;

static PlatformCriticalState InsTask_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void InsTask_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

static void InsTask_NavigationDiagnosticsApply(SystemInsDiagnostics *diagnostics)
{
    EstimatorOutputSnapshot navigation;

    if (diagnostics == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemInsDiagnostics,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (Estimator_GetLatestSnapshot(&navigation) == 0U) { return; }
    diagnostics->last_update_timestamp_us = navigation.timestamp_us;
    diagnostics->quaternion_valid = navigation.initialized;
    diagnostics->velocity_valid = navigation.initialized;
    diagnostics->position_valid = navigation.initialized;
    diagnostics->software_attitude_propagation = (uint8_t)(
        (navigation.mission_running != 0U) && (navigation.predict_count != 0U));
}

static void InsTask_DiagnosticsPublish(void)
{
    SystemCalibrationStatus calibration;
    InsOutputSnapshot output;
    SystemInsDiagnostics diagnostics;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_output, InsOutputSnapshot,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (SystemCalibration_StatusGet(&calibration) != SYSTEM_DEVICE_OK)
    {
        (void)memset(&calibration, 0, sizeof(calibration));
    }
    primask = InsTask_IrqLock();
    output = s_output;
    InsTask_IrqUnlock(primask);
    (void)memset(&diagnostics, 0, sizeof(diagnostics));
    diagnostics.last_update_timestamp_us = output.timestamp_us;
    diagnostics.bias_samples = calibration.samples;
    diagnostics.initialized = 1U;
    diagnostics.started = s_mission_running;
    diagnostics.attitude_ready = output.alignment_valid;
    diagnostics.quaternion_valid = (uint8_t)(
        (output.alignment_valid != 0U) || (output.ins_valid != 0U));
    diagnostics.velocity_valid = output.ins_valid;
    diagnostics.position_valid = output.ins_valid;
    diagnostics.software_attitude_propagation = (uint8_t)(
        (s_mission_running != 0U) && (output.update_seq != 0U) &&
        (output.ins_valid != 0U));
    diagnostics.bias_ready = calibration.ready;
    if ((SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE) && (s_mission_running != 0U))
    {
        InsTask_NavigationDiagnosticsApply(&diagnostics);
    }
    SystemInsDiagnostics_Publish(&diagnostics);
}

static void InsTask_OutputPublish(void)
{
    uint32_t primask = InsTask_IrqLock();

    s_published_output = s_output;
    InsTask_IrqUnlock(primask);
    InsTask_DiagnosticsPublish();
}

static uint8_t InsTask_SampleCorrect(const InsImuSample *source,
                                     InsAlgorithmSample *destination)
{
    SystemCalibrationImuCorrection correction;

    if ((source == NULL) || (destination == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(source, InsImuSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(destination, InsAlgorithmSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(destination, 0, sizeof(*destination));
    if (SystemCalibration_ImuCorrectionGet(&correction) !=
        SYSTEM_DEVICE_OK)
    {
        return 0U;
    }
    destination->timestamp_us = source->sample_timestamp_us;
    destination->quality_flags = source->quality_flags;
    if (SystemCalibration_ImuCorrectionApply(
            source->accel_b_mps2,
            source->gyro_b_radps,
            &correction,
            destination->accel_b_mps2,
            destination->gyro_b_radps) != SYSTEM_DEVICE_OK)
    {
        return 0U;
    }
    destination->valid_flags = INS_ALGORITHM_VALID_ACCEL |
                               INS_ALGORITHM_VALID_GYRO;
    return 1U;
}

static SystemHealthAttitudeStatus InsTask_AttitudeStatusEvaluateLocked(
    uint64_t now_us)
{
    (void)now_us;

    if (s_calibration_ready == 0U)
    {
        return SYSTEM_HEALTH_ATTITUDE_CALIBRATION_NOT_READY;
    }
    if (s_alignment_final_ready != 0U)
    {
        return SYSTEM_HEALTH_ATTITUDE_READY;
    }
    if (s_attitude_source_available == 0U)
    {
        return SYSTEM_HEALTH_ATTITUDE_SOURCE_UNAVAILABLE;
    }
    return (s_alignment_invalid_sample_seen != 0U) ?
        SYSTEM_HEALTH_ATTITUDE_INVALID :
        SYSTEM_HEALTH_ATTITUDE_NO_SAMPLE;
}

static SystemHealthAttitudeStatus InsTask_AttitudeReadinessRefresh(
    uint64_t now_us)
{
    SystemHealthAttitudeStatus status;
    uint32_t primask = InsTask_IrqLock();

    status = InsTask_AttitudeStatusEvaluateLocked(now_us);
    s_output.alignment_valid =
        (status == SYSTEM_HEALTH_ATTITUDE_READY) ? 1U : 0U;
    s_published_output = s_output;
    InsTask_IrqUnlock(primask);
    InsTask_DiagnosticsPublish();
    SystemHealth_SetAttitudeState(
        (status == SYSTEM_HEALTH_ATTITUDE_READY) ? 1U : 0U, status);
    return status;
}

static void InsTask_AlignmentConfigGet(
    const SystemNavigationProfile *profile,
    AlignmentStrategyConfig *config)
{
    static const AlignmentConstraintSpec constraints[] =
        SYSTEM_ALIGNMENT_CONSTRAINTS_INITIALIZER;
    _Static_assert((sizeof(constraints) / sizeof(constraints[0])) ==
        SYSTEM_ALIGNMENT_CONSTRAINT_COUNT, "Alignment count mismatch");
    _Static_assert(SYSTEM_ALIGNMENT_CONSTRAINT_COUNT <=
        ALIGNMENT_STRATEGY_MAX_CONSTRAINTS, "Alignment exceeds fixed capacity");
    if ((profile == NULL) || (config == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(profile, SystemNavigationProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(config, AlignmentStrategyConfig,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(config, 0, sizeof(*config));
    config->minimum_samples = profile->alignment_minimum_samples;
    config->maximum_samples = profile->alignment_maximum_samples;
    config->minimum_duration_us = profile->alignment_minimum_duration_us;
    config->maximum_gap_us = profile->alignment_maximum_gap_us;
    config->gravity_mps2 = SYSTEM_LOCAL_GRAVITY_MPS2;
    config->acceleration_tolerance_mps2 =
        profile->alignment_acceleration_tolerance_mps2;
    config->maximum_gyro_radps =
        profile->alignment_maximum_gyro_radps;
    config->maximum_quaternion_deviation_rad =
        profile->alignment_maximum_quaternion_deviation_rad;
    config->maximum_tilt_error_rad =
        profile->alignment_maximum_tilt_error_rad;
    config->known_yaw_deg = profile->known_yaw_deg;
    config->known_yaw_body_axis = profile->known_yaw_body_axis;
    config->magnetic_declination_deg = profile->magnetic_declination_deg;
    config->magnetic_magnitude_min_uT = SYSTEM_ALIGNMENT_MAG_MIN_UT;
    config->magnetic_magnitude_max_uT = SYSTEM_ALIGNMENT_MAG_MAX_UT;
    config->magnetic_magnitude_max_deviation_ratio =
        SYSTEM_ALIGNMENT_MAG_MAX_MAGNITUDE_DEVIATION_RATIO;
    config->magnetic_direction_min_dot =
        SYSTEM_ALIGNMENT_MAG_DIRECTION_MIN_DOT;
    config->magnetic_horizontal_min_ratio =
        SYSTEM_ALIGNMENT_MAG_HORIZONTAL_MIN_RATIO;
    SILVERSTAR_ASSERT(SYSTEM_ALIGNMENT_CONSTRAINT_COUNT <=
        ALIGNMENT_STRATEGY_MAX_CONSTRAINTS, SILVERSTAR_ASSERT_MODULE_APP,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    config->constraint_count = SYSTEM_ALIGNMENT_CONSTRAINT_COUNT;
    config->external_yaw_authoritative =
        SYSTEM_ALIGNMENT_EXTERNAL_YAW_AUTHORITATIVE;
    (void)memcpy(config->constraints, constraints, sizeof(constraints));
}

static void InsTask_AlignmentOptionalSamplesGet(
    AlignmentStrategySample *sample)
{
    SystemMagnetometerSample magnetometer;
    SystemHardwareQuaternionSample quaternion;

    if (sample == NULL)
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, AlignmentStrategySample,
        SILVERSTAR_ASSERT_MODULE_APP);
    if ((AlignmentStrategy_MagnetometerRequired() != 0U) &&
        (SystemMagnetometer_LatestSampleGet(&magnetometer) ==
         SYSTEM_DEVICE_OK))
    {
        sample->magnetometer_timestamp_us =
            magnetometer.sample_timestamp_us;
        sample->magnetometer_sequence = magnetometer.sequence;
        sample->magnetometer_physical_device_id =
            magnetometer.physical_device_id;
        sample->magnetometer_instance_id = magnetometer.instance_id;
        (void)memcpy(sample->magnetic_field_b_uT,
                     magnetometer.magnetic_field_b_uT,
                     sizeof(sample->magnetic_field_b_uT));
        sample->magnetometer_available = 1U;
        sample->magnetometer_calibrated = (uint8_t)(
            (magnetometer.calibration_valid != 0U) &&
            ((magnetometer.valid_mask &
              SYSTEM_MAG_VALID_PHYSICAL_UNIT) != 0U));
    }
    if ((AlignmentStrategy_HardwareQuaternionRequired() != 0U) &&
        (SystemHardwareQuaternion_LatestSampleGet(&quaternion) ==
         SYSTEM_DEVICE_OK) && (quaternion.valid != 0U))
    {
        sample->quaternion_timestamp_us = quaternion.sample_timestamp_us;
        sample->quaternion_sequence = quaternion.sequence;
        (void)memcpy(sample->quaternion_wxyz, quaternion.quaternion_wxyz,
                     sizeof(sample->quaternion_wxyz));
        sample->quaternion_available = 1U;
        sample->quaternion_mode = (uint8_t)quaternion.mode;
        sample->quaternion_mode_verified = quaternion.mode_verified;
    }
}

static void InsTask_AlignmentProgressUpdate(
    const SystemNavigationProfile *profile,
    const AlignmentStrategyOutput *output)
{
    uint32_t primask;

    if ((profile == NULL) || (output == NULL))
    {
        return;
    }
    primask = InsTask_IrqLock();
    s_alignment_snapshot.algorithm = profile->alignment_algorithm;
    s_alignment_snapshot.first_timestamp_us = output->first_timestamp_us;
    s_alignment_snapshot.last_timestamp_us = output->last_timestamp_us;
    s_alignment_snapshot.sample_count = output->sample_count;
    s_alignment_snapshot.reject_count = output->reject_count;
    InsTask_IrqUnlock(primask);
}

static void InsTask_AlignmentSourceSet(
    SystemAlignmentAttitudeSource source,
    uint8_t source_available)
{
    uint32_t primask = InsTask_IrqLock();

    s_alignment_source = source;
    s_attitude_source_available = source_available;
    InsTask_IrqUnlock(primask);
}

static void InsTask_AlignmentSnapshotCommit(
    const SystemNavigationProfile *profile,
    const AttitudePreflightSample *sample,
    const AlignmentStrategyOutput *quality,
    const float acceleration_mean_b_mps2[3],
    const float gyro_mean_b_radps[3],
    const float magnetic_field_mean_b_uT[3],
    SystemHardwareQuaternionMode hardware_mode,
    uint8_t mode_verified)
{
    if ((profile == NULL) || (sample == NULL) || (quality == NULL) ||
        (acceleration_mean_b_mps2 == NULL) ||
        (gyro_mean_b_radps == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(profile, SystemNavigationProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(sample, AttitudePreflightSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(quality, AlignmentStrategyOutput,
        SILVERSTAR_ASSERT_MODULE_APP);
    s_alignment_snapshot.algorithm = profile->alignment_algorithm;
    s_alignment_snapshot.hardware_mode = hardware_mode;
    s_alignment_snapshot.mode_verified = mode_verified;
    s_alignment_snapshot.constraint_count = quality->constraint_count;
    s_alignment_snapshot.valid_pair_count = quality->valid_pair_count;
    s_alignment_snapshot.magnetometer_physical_device_id =
        quality->magnetometer_physical_device_id;
    s_alignment_snapshot.magnetometer_instance_id =
        quality->magnetometer_instance_id;
    s_alignment_snapshot.minimum_pair_sine = quality->minimum_pair_sine;
    s_alignment_snapshot.rms_mismatch_rad = quality->rms_mismatch_rad;
    s_alignment_snapshot.max_mismatch_rad = quality->max_mismatch_rad;
    s_alignment_snapshot.valid = 1U;
    (void)memcpy(s_alignment_snapshot.q_nb,
                 s_preflight_attitude.latest.quaternion_wxyz,
                 sizeof(s_alignment_snapshot.q_nb));
    (void)memcpy(s_alignment_snapshot.acceleration_mean_b_mps2,
                 acceleration_mean_b_mps2,
                 sizeof(s_alignment_snapshot.acceleration_mean_b_mps2));
    (void)memcpy(s_alignment_snapshot.gyro_mean_b_radps,
                 gyro_mean_b_radps,
                 sizeof(s_alignment_snapshot.gyro_mean_b_radps));
    if (magnetic_field_mean_b_uT != NULL)
    {
        (void)memcpy(s_alignment_snapshot.magnetic_field_mean_b_uT,
                     magnetic_field_mean_b_uT,
                     sizeof(s_alignment_snapshot.magnetic_field_mean_b_uT));
    }
    s_alignment_invalid_sample_seen = 0U;
    s_alignment_final_ready = 1U;
    s_output.timestamp_us = sample->sample_timestamp_us;
    (void)memcpy(s_output.q_nb,
                 s_preflight_attitude.latest.quaternion_wxyz,
                 sizeof(s_output.q_nb));
    s_output.alignment_valid = 1U;
    s_published_output = s_output;
}

static uint8_t InsTask_AlignmentFinalize(
    const SystemNavigationProfile *profile,
    const InsImuSample *imu_sample,
    const AlignmentStrategyOutput *quality,
    const float q_nb[4],
    const float acceleration_mean_b_mps2[3],
    const float gyro_mean_b_radps[3],
    const float magnetic_field_mean_b_uT[3],
    SystemHardwareQuaternionMode hardware_mode,
    uint8_t mode_verified)
{
    AttitudePreflightSample sample;
    AttitudePreflightResult result;
    uint32_t primask;

    if ((profile == NULL) || (imu_sample == NULL) ||
        (quality == NULL) || (q_nb == NULL) ||
        (acceleration_mean_b_mps2 == NULL) ||
        (gyro_mean_b_radps == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(profile, SystemNavigationProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(imu_sample, InsImuSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(&sample, 0, sizeof(sample));
    (void)memcpy(sample.quaternion_wxyz, q_nb,
                 sizeof(sample.quaternion_wxyz));
    sample.sample_timestamp_us = s_alignment_snapshot.last_timestamp_us;
    sample.receive_timestamp_us = imu_sample->receive_timestamp_us;
    sample.sequence = imu_sample->sequence;
    sample.valid = 1U;

    primask = InsTask_IrqLock();
    if (s_alignment_final_ready != 0U)
    {
        InsTask_IrqUnlock(primask);
        return 1U;
    }
    result = AttitudePreflight_LatestUpdate(&s_preflight_attitude, &sample);
    if (result == ATTITUDE_PREFLIGHT_RESULT_OK)
    {
        InsTask_AlignmentSnapshotCommit(
            profile, &sample, quality, acceleration_mean_b_mps2,
            gyro_mean_b_radps, magnetic_field_mean_b_uT,
            hardware_mode, mode_verified);
    }
    InsTask_IrqUnlock(primask);
    return (result == ATTITUDE_PREFLIGHT_RESULT_OK) ? 1U : 0U;
}

static void InsTask_AlignmentResultStateUpdate(
    AlignmentStrategyProcessResult result)
{
    uint32_t primask;

    if (result == ALIGNMENT_STRATEGY_PROCESS_WAITING)
    {
        return;
    }
    primask = InsTask_IrqLock();
    s_alignment_invalid_sample_seen = (uint8_t)(
        (result == ALIGNMENT_STRATEGY_PROCESS_REJECTED) ||
        (result == ALIGNMENT_STRATEGY_PROCESS_INVALID));
    InsTask_IrqUnlock(primask);
}

static void InsTask_AlignmentSampleBuild(
    const InsAlgorithmSample *corrected,
    AlignmentStrategySample *sample)
{
    if ((corrected == NULL) || (sample == NULL))
    {
        return;
    }
    (void)memset(sample, 0, sizeof(*sample));
    sample->timestamp_us = corrected->timestamp_us;
    (void)memcpy(sample->acceleration_b_mps2,
                 corrected->accel_b_mps2,
                 sizeof(sample->acceleration_b_mps2));
    (void)memcpy(sample->gyro_b_radps,
                 corrected->gyro_b_radps,
                 sizeof(sample->gyro_b_radps));
    InsTask_AlignmentOptionalSamplesGet(sample);
}

static void InsTask_AlignmentReadyFinalize(
    const SystemNavigationProfile *profile,
    const InsImuSample *imu_sample,
    AlignmentStrategyProcessResult result,
    const AlignmentStrategyOutput *output)
{
    const float *magnetic_field = NULL;

    if ((profile == NULL) || (imu_sample == NULL) || (output == NULL) ||
        (result != ALIGNMENT_STRATEGY_PROCESS_READY))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(output, AlignmentStrategyOutput,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (output->magnetic_field_valid != 0U)
    {
        magnetic_field = output->magnetic_field_mean_b_uT;
    }
    (void)InsTask_AlignmentFinalize(
        profile, imu_sample, output, output->q_nb,
        output->acceleration_mean_b_mps2,
        output->gyro_mean_b_radps, magnetic_field,
        (SystemHardwareQuaternionMode)output->hardware_mode,
        output->hardware_mode_verified);
}

static void InsTask_AlignmentProcess(const InsImuSample *imu_sample)
{
    const SystemNavigationProfile *profile;
    AlignmentStrategyConfig config;
    AlignmentStrategySample sample;
    AlignmentStrategyOutput output;
    InsAlgorithmSample corrected_sample;
    AlignmentStrategyProcessResult result;
    uint64_t now_us;
    uint32_t primask;

    if ((imu_sample == NULL) ||
        (SystemAlignment_IsCollecting() == 0U))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(imu_sample, InsImuSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    now_us = SystemTime_GetMonotonicUs();
    primask = InsTask_IrqLock();
    s_calibration_ready = SystemCalibration_IsReady();
    if ((s_calibration_ready == 0U) || (s_alignment_final_ready != 0U))
    {
        InsTask_IrqUnlock(primask);
        (void)InsTask_AttitudeReadinessRefresh(now_us);
        return;
    }
    InsTask_IrqUnlock(primask);
    profile = SystemNavigationProfile_Get();
    if ((profile == NULL) ||
        (InsTask_SampleCorrect(imu_sample, &corrected_sample) == 0U))
    {
        primask = InsTask_IrqLock();
        s_alignment_invalid_sample_seen = 1U;
        InsTask_IrqUnlock(primask);
        (void)InsTask_AttitudeReadinessRefresh(now_us);
        return;
    }
    InsTask_AlignmentConfigGet(profile, &config);
    InsTask_AlignmentSampleBuild(&corrected_sample, &sample);
    InsTask_AlignmentSourceSet(
        (SystemAlignmentAttitudeSource)SYSTEM_ALIGNMENT_BUILD_SOURCE, 1U);
    result = AlignmentStrategy_SampleProcess(
        &s_alignment_strategy, &config, &sample, &output);
    InsTask_AlignmentProgressUpdate(profile, &output);
    InsTask_AlignmentResultStateUpdate(result);
    InsTask_AlignmentReadyFinalize(profile, imu_sample, result, &output);
    (void)InsTask_AttitudeReadinessRefresh(now_us);
}

static void InsTask_PureOutputPublish(const InsState *state)
{
    if (state == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(state, InsState, SILVERSTAR_ASSERT_MODULE_APP);
    s_output.timestamp_us = state->timestamp_us;
    s_output.update_seq = state->update_count;
    (void)memcpy(s_output.q_nb, state->q_nb, sizeof(s_output.q_nb));
    (void)memcpy(s_output.velocity_n_mps, state->velocity_n_mps,
                 sizeof(s_output.velocity_n_mps));
    (void)memcpy(s_output.position_n_m, state->position_n_m,
                 sizeof(s_output.position_n_m));
    (void)memcpy(s_output.accel_n_mps2, state->accel_n_mps2,
                 sizeof(s_output.accel_n_mps2));
    s_output.dt_s = state->dt_s;
    s_output.health_flags = state->health_flags;
    s_output.alignment_valid = s_mission_attitude_frozen;
    s_output.ins_valid = state->valid;
    s_output.mission_running = s_mission_running;
    InsTask_OutputPublish();
}

static float s_eskf_gyro_pair[2][3];
static float s_eskf_accel_pair[2][3];
static uint32_t s_eskf_quality_flags;

/* Integrate the actual adjacent sample segments onto two equal physical halves.
 * This preserves nonuniform timestamp spacing without duplicating coning. */
static float InsTask_HalfMean(float first, float middle, float last,
    uint64_t middle_us, uint64_t end_us, uint8_t half)
{
    const float values[3] = {first, middle, last};
    const uint64_t times[3] = {0U, middle_us, end_us};
    uint64_t begin = (half == 0U) ? 0U : end_us / 2U;
    uint64_t end = (half == 0U) ? end_us / 2U : end_us;
    float integral = 0.0f;
    SILVERSTAR_ASSERT((middle_us > 0U) && (end_us > middle_us),
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(half < 2U, SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    for (uint8_t segment = 0U; segment < 2U; segment++)
    {
        uint64_t left = (begin > times[segment]) ? begin : times[segment];
        uint64_t right = (end < times[segment + 1U]) ? end : times[segment + 1U];
        if (right > left)
        {
            float span = (float)(times[segment + 1U] - times[segment]);
            float fraction = ((float)(left - times[segment]) + (float)(right - times[segment])) / span;
            float mean = values[segment] + 0.5f * fraction * (values[segment + 1U] - values[segment]);
            integral += mean * (float)(right - left);
        }
    }
    return integral / (float)(end - begin);
}

static void InsTask_BodyPairBuildOne(
    const InsAlgorithmSample *first, const InsAlgorithmSample *last)
{
    SILVERSTAR_ASSERT_OBJECT(first, InsAlgorithmSample, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(last, InsAlgorithmSample, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(s_navigation_input.inertial.sample_count == 1U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    s_eskf_quality_flags = first->quality_flags | last->quality_flags;
    if (last->timestamp_us <= first->timestamp_us)
    { s_eskf_quality_flags |= SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY; return; }
    for (uint8_t axis = 0U; axis < 3U; axis++)
    {
        /* Two half-interval means from the same real endpoint samples. */
        s_eskf_gyro_pair[0][axis] =
            (3.0f * first->gyro_b_radps[axis] + last->gyro_b_radps[axis]) * 0.25f;
        s_eskf_gyro_pair[1][axis] =
            (first->gyro_b_radps[axis] + 3.0f * last->gyro_b_radps[axis]) * 0.25f;
        s_eskf_accel_pair[0][axis] =
            (3.0f * first->accel_b_mps2[axis] + last->accel_b_mps2[axis]) * 0.25f;
        s_eskf_accel_pair[1][axis] =
            (first->accel_b_mps2[axis] + 3.0f * last->accel_b_mps2[axis]) * 0.25f;
    }
}

static void InsTask_BodyPairBuildTwo(
    const InsAlgorithmSample *first, const InsAlgorithmSample *middle,
    const InsAlgorithmSample *last)
{
    uint64_t middle_us;
    uint64_t end_us;
    SILVERSTAR_ASSERT_OBJECT(first, InsAlgorithmSample, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(middle, InsAlgorithmSample, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(last, InsAlgorithmSample, SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT(s_navigation_input.inertial.sample_count == 2U,
        SILVERSTAR_ASSERT_MODULE_APP, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    s_eskf_quality_flags = first->quality_flags | middle->quality_flags | last->quality_flags;
    if ((middle->timestamp_us <= first->timestamp_us) || (last->timestamp_us <= middle->timestamp_us))
    { s_eskf_quality_flags |= SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY; return; }
    middle_us = middle->timestamp_us - first->timestamp_us;
    end_us = last->timestamp_us - first->timestamp_us;
    for (uint8_t half = 0U; half < 2U; half++)
    {
        for (uint8_t axis = 0U; axis < 3U; axis++)
        {
            s_eskf_gyro_pair[half][axis] = InsTask_HalfMean(first->gyro_b_radps[axis],
                middle->gyro_b_radps[axis], last->gyro_b_radps[axis], middle_us, end_us, half);
            s_eskf_accel_pair[half][axis] = InsTask_HalfMean(first->accel_b_mps2[axis],
                middle->accel_b_mps2[axis], last->accel_b_mps2[axis], middle_us, end_us, half);
        }
    }
}

static void InsTask_BodyPairBuild(const InsAlgorithmSample *last)
{
    const InsAlgorithmSample *first =
        &s_navigation_input.inertial.sample_history[0];
    SILVERSTAR_ASSERT_OBJECT(last, InsAlgorithmSample, SILVERSTAR_ASSERT_MODULE_APP);
    if (SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT == 1U)
    { InsTask_BodyPairBuildOne(first, last); }
    else
    {
        InsTask_BodyPairBuildTwo(first,
            &s_navigation_input.inertial.sample_history[1], last);
    }
}

static void InsTask_InertialOutputsPublish(
    const InsImuSample *imu_sample,
    const InsState *state)
{
    SystemInertialIncrement increment;
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    FlightLogInertialIncrementRecord increment_record;
#endif

    if ((imu_sample == NULL) || (state == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(imu_sample, InsImuSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(state, InsState, SILVERSTAR_ASSERT_MODULE_APP);
    increment.timestamp_us = state->timestamp_us;
    increment.sequence = ++s_increment_sequence;
    increment.dt_s = state->dt_s;
    if (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_ESKF15)
    {
        SystemNavigationBackend_BodyInputFill(&increment, &s_eskf_gyro_pair[0][0],
            &s_eskf_accel_pair[0][0], s_eskf_quality_flags);
    }
    (void)memcpy(increment.delta_theta_b_corrected,
                 state->delta_theta_b_coning_corrected,
                 sizeof(increment.delta_theta_b_corrected));
    (void)memcpy(increment.delta_velocity_b_sculling_corrected,
                 state->delta_velocity_b_sculling_corrected,
                 sizeof(increment.delta_velocity_b_sculling_corrected));

    if (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_NONE)
    {
        InsTask_PureOutputPublish(state);
    }

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    (void)memset(&increment_record, 0, sizeof(increment_record));
    increment_record.interval_end_timestamp_us = state->timestamp_us;
    increment_record.interval_start_timestamp_us = state->interval_start_timestamp_us;
    increment_record.sequence = increment.sequence;
    increment_record.dt_s = increment.dt_s;
    (void)memcpy(increment_record.delta_theta_b_corrected,
                 state->delta_theta_b_coning_corrected,
                 sizeof(increment_record.delta_theta_b_corrected));
    (void)memcpy(increment_record.delta_velocity_b_sculling_corrected,
                 state->delta_velocity_b_sculling_corrected,
                 sizeof(increment_record.delta_velocity_b_sculling_corrected));
    increment_record.health_flags = state->health_flags;
    (void)LoggerBus_InertialIncrementPush(state->timestamp_us,
                                          imu_sample->valid_mask,
                                          &increment_record);
#endif
    (void)EstimatorBus_PredictionPush(&increment);
    if (SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE)
    {
        InsTask_DiagnosticsPublish();
    }
}

#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
static void InsTask_PureRecordWrite(const InsImuSample *imu_sample,
                                    const InsState *state)
{
    FlightLogPureInsRecord record;

    if ((imu_sample == NULL) || (state == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(state, InsState, SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(&record, 0, sizeof(record));
    record.update_sequence = state->update_count;
    (void)memcpy(record.q_nb, state->q_nb, sizeof(record.q_nb));
    (void)memcpy(record.velocity_enu_mps, state->velocity_n_mps,
                 sizeof(record.velocity_enu_mps));
    (void)memcpy(record.position_enu_m, state->position_n_m,
                 sizeof(record.position_enu_m));
    (void)memcpy(record.accel_enu_mps2, state->accel_n_mps2,
                 sizeof(record.accel_enu_mps2));
    record.dt_s = state->dt_s;
    record.health_flags = state->health_flags;
    record.alignment_valid = s_mission_attitude_frozen;
    record.ins_valid = state->valid;
    (void)LoggerBus_PureInsPush(state->timestamp_us, imu_sample->valid_mask,
                                &record);
}
#endif

static void InsTask_Propagate(const InsImuSample *imu_sample)
{
    InsAlgorithmSample algorithm_sample;
    InsState state;

    if (imu_sample == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(imu_sample, InsImuSample,
        SILVERSTAR_ASSERT_MODULE_APP);
    SystemNavigationHealth_ImuQualityRecord(imu_sample->quality_flags);
    if ((imu_sample->quality_flags & 0x72U) != 0U) { return; }
    if (InsTask_SampleCorrect(imu_sample, &algorithm_sample) == 0U) { return; }
    if (SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE)
    {
        if ((SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_ESKF15) &&
            (s_navigation_input.inertial.sample_count ==
             SYSTEM_MECHANIZATION_SUBSAMPLE_COUNT))
        {
            InsTask_BodyPairBuild(&algorithm_sample);
        }
        if (InsInertial_Update(&s_navigation_input.inertial,
                &algorithm_sample, &state) != INS_INERTIAL_UPDATE_READY)
        {
            return;
        }
    }
    else if (InsMechanization_Update(&s_navigation_input.pure_ins,
                 &algorithm_sample, &state) == 0U)
    {
        return;
    }
    InsTask_InertialOutputsPublish(imu_sample, &state);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    if (SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_NONE)
    {
        InsTask_PureRecordWrite(imu_sample, &state);
    }
#endif
}

void AppTask_Ins(void *argument)
{
    InsImuSample sample;
    SystemLifecycleState lifecycle_state;
    uint64_t mission_us;
    uint32_t sample_index;

    (void)argument;
    SILVERSTAR_ASSERT_OBJECT(&s_navigation_input.pure_ins, InsMechanizationContext,
        SILVERSTAR_ASSERT_MODULE_APP);
    InsMechanization_Init(&s_navigation_input.pure_ins, SYSTEM_INS_GRAVITY_MPS2);
    AttitudePreflight_Init(&s_preflight_attitude);
    AlignmentStrategy_Init(&s_alignment_strategy);
    (void)memset(&s_alignment_snapshot, 0, sizeof(s_alignment_snapshot));
    (void)memset(&s_output, 0, sizeof(s_output));
    (void)memset(&s_published_output, 0, sizeof(s_published_output));
    SystemInsDiagnostics_Reset();
    InsTask_DiagnosticsPublish();

    for (;;)
    {
        for (sample_index = 0U;
             sample_index < INS_MAX_SAMPLES_PER_CYCLE;
             sample_index++)
        {
            if (ImuSampleBus_Pop(&sample) != IMU_SAMPLE_BUS_RESULT_OK)
            {
                break;
            }
            lifecycle_state = SystemLifecycle_GetState();
            if ((s_mission_running != 0U) &&
                ((lifecycle_state == SYSTEM_STATE_FLIGHT) ||
                 (lifecycle_state == SYSTEM_STATE_RECOVERY)) &&
                (SystemTime_GetMissionUsAt(sample.sample_timestamp_us,
                                           &mission_us) != 0U))
            {
                InsTask_Propagate(&sample);
            }
            else if (s_mission_running == 0U)
            {
                InsTask_AlignmentProcess(&sample);
            }
        }
        if (sample_index == INS_MAX_SAMPLES_PER_CYCLE)
        {
            s_output.health_flags |= INS_HEALTH_CYCLE_DRAIN_LIMIT;
            InsTask_OutputPublish();
        }
        vTaskDelay(pdMS_TO_TICKS(1U));
    }
}

static SystemDeviceResult InsTask_StartFreezeFinalize(
    const SystemNavigationProfile *profile,
    uint64_t now_us,
    AttitudePreflightResult freeze_result)
{
    SystemHealthAttitudeStatus status;

    if (profile == NULL) { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    SILVERSTAR_ASSERT_OBJECT(profile, SystemNavigationProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    InsTask_DiagnosticsPublish();
    if (freeze_result != ATTITUDE_PREFLIGHT_RESULT_OK)
    {
        status = (freeze_result == ATTITUDE_PREFLIGHT_RESULT_STALE) ?
            SYSTEM_HEALTH_ATTITUDE_STALE :
            SYSTEM_HEALTH_ATTITUDE_INVALID;
        SystemHealth_SetAttitudeState(0U, status);
        return SYSTEM_DEVICE_NOT_READY;
    }
    SystemHealth_SetAttitudeState(1U, SYSTEM_HEALTH_ATTITUDE_READY);
#if (SILVERSTAR_PROTOCOL_LOGGING_ENABLED != 0U)
    (void)LoggerBus_EventPush(now_us,
                              FLIGHT_LOG_EVENT_ALIGNMENT_COMPLETE,
                              (uint32_t)profile->alignment_algorithm,
                              1U);
#else
    (void)now_us;
#endif
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult InsTask_PrepareStart(void)
{
    const SystemNavigationProfile *profile;
    AttitudePreflightSample mission_sample;
    AttitudePreflightResult freeze_result;
    SystemHealthAttitudeStatus status;
    uint32_t primask;
    uint64_t now_us;

    if (s_mission_attitude_frozen != 0U)
    {
        return SYSTEM_DEVICE_OK;
    }
    profile = SystemNavigationProfile_Get();
    if (profile == NULL)
    {
        return SYSTEM_DEVICE_INTERNAL_ERROR;
    }
    SILVERSTAR_ASSERT_OBJECT(profile, SystemNavigationProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    now_us = SystemTime_GetMonotonicUs();
    primask = InsTask_IrqLock();
    s_calibration_ready = SystemCalibration_IsReady();
    status = InsTask_AttitudeStatusEvaluateLocked(now_us);
    if (status != SYSTEM_HEALTH_ATTITUDE_READY)
    {
        s_output.alignment_valid = 0U;
        s_published_output = s_output;
        InsTask_IrqUnlock(primask);
        InsTask_DiagnosticsPublish();
        SystemHealth_SetAttitudeState(0U, status);
        return SYSTEM_DEVICE_NOT_READY;
    }
    freeze_result = AttitudePreflight_MissionFreeze(
        &s_preflight_attitude, now_us, UINT64_MAX);
    if ((freeze_result == ATTITUDE_PREFLIGHT_RESULT_OK) &&
        (AttitudePreflight_MissionGet(
             &s_preflight_attitude, &mission_sample) == 0U))
    {
        freeze_result = ATTITUDE_PREFLIGHT_RESULT_INVALID;
    }
    if (freeze_result == ATTITUDE_PREFLIGHT_RESULT_OK)
    {
        s_mission_attitude_frozen = 1U;
        (void)memcpy(s_output.q_nb,
                     mission_sample.quaternion_wxyz,
                     sizeof(s_output.q_nb));
        s_output.alignment_valid = 1U;
        s_published_output = s_output;
    }
    InsTask_IrqUnlock(primask);
    return InsTask_StartFreezeFinalize(profile, now_us, freeze_result);
}

SystemDeviceResult InsTask_PrepareNavigation(const float q_nb[4])
{
    uint32_t lock;
    uint8_t initialized;
    if (q_nb == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(q_nb, float, SILVERSTAR_ASSERT_MODULE_APP);
    if (s_mission_running != 0U) { return SYSTEM_DEVICE_BAD_STATE; }
    lock = InsTask_IrqLock();
    initialized = InsMechanization_ResetNavigationWithAttitude(&s_navigation_input.pure_ins, q_nb);
    InsTask_IrqUnlock(lock);
    return initialized ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_VERIFY_FAILED;
}

SystemDeviceResult InsTask_InitializeMission(void)
{
    float initial_q_nb[4];

    SILVERSTAR_ASSERT_OBJECT(&s_navigation_input.pure_ins, InsMechanizationContext,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (InsTask_PrepareStart() != SYSTEM_DEVICE_OK)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (Ins_GetInitialAttitude(initial_q_nb) == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    InsInertial_Reset(&s_navigation_input.inertial);
    if ((SYSTEM_FUSION_ALGORITHM == SYSTEM_FUSION_NONE) &&
        (InsMechanization_ResetNavigationWithAttitude(
            &s_navigation_input.pure_ins, initial_q_nb) == 0U))
    {
        return SYSTEM_DEVICE_INTERNAL_ERROR;
    }
    s_increment_sequence = 0U;
    s_mission_running = 1U;
    s_output.ins_valid = 0U;
    s_output.mission_running = 1U;
    InsTask_OutputPublish();
    return SYSTEM_DEVICE_OK;
}

void InsTask_AbortMission(void)
{
    uint64_t now_us = SystemTime_GetMonotonicUs();
    uint32_t primask;

    s_mission_running = 0U;
    primask = InsTask_IrqLock();
    AttitudePreflight_MissionUnfreeze(&s_preflight_attitude);
    s_mission_attitude_frozen = 0U;
    s_output.alignment_valid =
        (InsTask_AttitudeStatusEvaluateLocked(now_us) ==
         SYSTEM_HEALTH_ATTITUDE_READY) ? 1U : 0U;
    s_published_output = s_output;
    InsTask_IrqUnlock(primask);
    InsMechanization_ResetNavigation(&s_navigation_input.pure_ins);
    s_output.ins_valid = 0U;
    s_output.mission_running = 0U;
    InsTask_OutputPublish();
}

uint8_t Ins_IsMissionRunning(void)
{
    return s_mission_running;
}

uint8_t Ins_IsReadyForMission(void)
{
    uint64_t now_us;
    uint32_t primask;
    SystemHealthAttitudeStatus status;

    now_us = SystemTime_GetMonotonicUs();
    primask = InsTask_IrqLock();
    s_calibration_ready = SystemCalibration_IsReady();
    status = InsTask_AttitudeStatusEvaluateLocked(now_us);
    InsTask_IrqUnlock(primask);
    SystemHealth_SetAttitudeState(
        (status == SYSTEM_HEALTH_ATTITUDE_READY) ? 1U : 0U, status);
    return (status == SYSTEM_HEALTH_ATTITUDE_READY) ? 1U : 0U;
}

uint8_t Ins_GetInitialAttitude(float q_nb[4])
{
    AttitudePreflightSample sample;
    uint32_t primask;

    if (q_nb == NULL)
    {
        return 0U;
    }
    primask = InsTask_IrqLock();
    if (AttitudePreflight_MissionGet(
            &s_preflight_attitude, &sample) == 0U)
    {
        InsTask_IrqUnlock(primask);
        return 0U;
    }
    (void)memcpy(q_nb, sample.quaternion_wxyz,
                 sizeof(sample.quaternion_wxyz));
    InsTask_IrqUnlock(primask);
    return 1U;
}

uint8_t Ins_GetAlignmentSnapshot(InsAlignmentSnapshot *snapshot)
{
    uint32_t primask;

    if (snapshot == NULL)
    {
        return 0U;
    }
    primask = InsTask_IrqLock();
    *snapshot = s_alignment_snapshot;
    InsTask_IrqUnlock(primask);
    return snapshot->valid;
}

uint8_t Ins_GetLatestSnapshot(InsOutputSnapshot *snapshot)
{
    InsOutputSnapshot published;
    uint32_t primask;

    if (snapshot == NULL)
    {
        return 0U;
    }
    if ((SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE) && (s_mission_running != 0U))
    {
        (void)memset(snapshot, 0, sizeof(*snapshot));
        return 0U;
    }
    primask = InsTask_IrqLock();
    published = s_published_output;
    InsTask_IrqUnlock(primask);
    *snapshot = published;
    return (uint8_t)((published.alignment_valid != 0U) ||
                     (published.ins_valid != 0U));
}

SystemDeviceResult InsTask_AlignmentReset(void)
{
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_alignment_strategy, AlignmentStrategyContext,
        SILVERSTAR_ASSERT_MODULE_APP);
    if (s_mission_running != 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    primask = InsTask_IrqLock();
    AttitudePreflight_Init(&s_preflight_attitude);
    AlignmentStrategy_Init(&s_alignment_strategy);
    (void)memset(&s_alignment_snapshot, 0, sizeof(s_alignment_snapshot));
    s_alignment_invalid_sample_seen = 0U;
    s_attitude_source_available = 0U;
    s_alignment_final_ready = 0U;
    s_alignment_source = SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_NONE;
    s_mission_attitude_frozen = 0U;
    s_calibration_ready = SystemCalibration_IsReady();
    s_output.timestamp_us = 0ULL;
    s_output.q_nb[0] = 1.0f;
    s_output.q_nb[1] = 0.0f;
    s_output.q_nb[2] = 0.0f;
    s_output.q_nb[3] = 0.0f;
    s_output.alignment_valid = 0U;
    s_published_output = s_output;
    InsTask_IrqUnlock(primask);
    InsTask_DiagnosticsPublish();
    SystemHealth_SetAttitudeState(
        0U,
        (s_calibration_ready != 0U) ? SYSTEM_HEALTH_ATTITUDE_NO_SAMPLE :
                             SYSTEM_HEALTH_ATTITUDE_CALIBRATION_NOT_READY);
    return SYSTEM_DEVICE_OK;
}

static void InsTask_AttitudeStatusSnapshotGet(
    SystemAlignmentAttitudeStatus *status,
    InsTaskAlignmentFlags *flags)
{
    AttitudePreflightSample sample;
    uint32_t primask;

    if ((status == NULL) || (flags == NULL))
    {
        return;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentAttitudeStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(flags, InsTaskAlignmentFlags,
        SILVERSTAR_ASSERT_MODULE_APP);
    primask = InsTask_IrqLock();
    flags->final_ready = s_alignment_final_ready;
    flags->source_available = s_attitude_source_available;
    flags->calibration_ready = s_calibration_ready;
    status->quaternion_valid = AttitudePreflight_LatestGet(
        &s_preflight_attitude, &sample);
    if (status->quaternion_valid != 0U)
    {
        status->timestamp_us = sample.sample_timestamp_us;
        status->receive_timestamp_us = sample.receive_timestamp_us;
        status->sequence = sample.sequence;
        (void)memcpy(status->quaternion_wxyz,
                     sample.quaternion_wxyz,
                     sizeof(status->quaternion_wxyz));
    }
    status->source = s_alignment_source;
    status->window_start_timestamp_us =
        s_alignment_snapshot.first_timestamp_us;
    status->window_end_timestamp_us =
        s_alignment_snapshot.last_timestamp_us;
    status->sample_count = s_alignment_snapshot.sample_count;
    status->reject_count = s_alignment_snapshot.reject_count;
    (void)memcpy(status->acceleration_mean_b_mps2,
                 s_alignment_snapshot.acceleration_mean_b_mps2,
                 sizeof(status->acceleration_mean_b_mps2));
    (void)memcpy(status->gyro_mean_b_radps,
                 s_alignment_snapshot.gyro_mean_b_radps,
                 sizeof(status->gyro_mean_b_radps));
    (void)memcpy(status->magnetic_field_mean_b_uT,
                 s_alignment_snapshot.magnetic_field_mean_b_uT,
                  sizeof(status->magnetic_field_mean_b_uT));
    InsTask_IrqUnlock(primask);
}

static void InsTask_AttitudeSourceResolve(
    SystemAlignmentAttitudeStatus *status,
    SystemAlignmentAlgorithm algorithm,
    InsTaskAlignmentFlags *flags)
{
    if ((status == NULL) || (flags == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentAttitudeStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(flags, InsTaskAlignmentFlags,
        SILVERSTAR_ASSERT_MODULE_APP);
    flags->source_available = 1U;
    if (status->source != SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_NONE) { return; }
    if (algorithm == SYSTEM_ALIGNMENT_GRAVITY_KNOWN_YAW)
    {
        status->source = SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_KNOWN_YAW;
    }
    else if (algorithm == SYSTEM_ALIGNMENT_GRAVITY_MAG_TRIAD)
    {
        status->source = SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_MAG_TRIAD;
    }
    else if (algorithm == SYSTEM_ALIGNMENT_VECTOR_CONSTRAINTS)
    {
        status->source = SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_VECTOR_CONSTRAINTS;
    }
    else
    {
        status->source = SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION;
    }
}

static void InsTask_AttitudeStatusDetailsSet(
    SystemAlignmentAttitudeStatus *status,
    const SystemNavigationProfile *profile,
    const InsTaskAlignmentFlags *flags)
{
    float yaw_rad;

    if ((status == NULL) || (profile == NULL) || (flags == NULL)) { return; }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentAttitudeStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    SILVERSTAR_ASSERT_OBJECT(profile, SystemNavigationProfile,
        SILVERSTAR_ASSERT_MODULE_APP);
    status->known_yaw_deg = profile->known_yaw_deg;
    status->magnetic_declination_deg = profile->magnetic_declination_deg;
    if ((status->quaternion_valid != 0U) &&
        (Attitude_YawEnuFromQuaternion(status->quaternion_wxyz,
            &yaw_rad) == ATTITUDE_YAW_RESULT_OK))
    {
        status->final_yaw_deg = yaw_rad * 57.295779513082320876f;
    }
    status->final_quaternion_frozen = flags->final_ready;
    if (status->source ==
        SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_HARDWARE_QUATERNION)
    {
        status->device_name = SystemHardwareQuaternion_NameGet();
    }
    else if (status->source ==
             SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_MAG_TRIAD)
    {
        status->device_name = "CORRECTED_IMU+MAGNETOMETER";
    }
    else if (status->source ==
             SYSTEM_ALIGNMENT_ATTITUDE_SOURCE_GRAVITY_KNOWN_YAW)
    {
        status->device_name = "CORRECTED_IMU";
    }
    status->attitude_ready = (uint8_t)(
        (flags->calibration_ready != 0U) &&
        (flags->final_ready != 0U) &&
        (status->quaternion_valid != 0U));
    if (status->attitude_ready != 0U)
    {
        status->state = SYSTEM_ALIGNMENT_COMPONENT_READY;
    }
    else if (flags->source_available == 0U)
    {
        status->state = SYSTEM_ALIGNMENT_COMPONENT_DISABLED;
    }
    else
    {
        status->state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    }
}

SystemDeviceResult InsTask_AttitudeAlignmentStatusGet(
    SystemAlignmentAttitudeStatus *status)
{
    const SystemNavigationProfile *profile;
    InsTaskAlignmentFlags flags;

    if (status == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentAttitudeStatus,
        SILVERSTAR_ASSERT_MODULE_APP);
    (void)memset(status, 0, sizeof(*status));
    status->device_name = "NONE";
    profile = SystemNavigationProfile_Get();
    if (profile == NULL) { return SYSTEM_DEVICE_INTERNAL_ERROR; }
    InsTask_AttitudeStatusSnapshotGet(status, &flags);
    status->algorithm = profile->alignment_algorithm;
    InsTask_AttitudeSourceResolve(status, profile->alignment_algorithm,
                                  &flags);
    InsTask_AttitudeStatusDetailsSet(status, profile, &flags);
    return SYSTEM_DEVICE_OK;
}
