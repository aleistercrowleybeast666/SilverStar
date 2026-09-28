#include "system_alignment.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "platform_critical.h"
#include "silverstar_assert.h"
#include "system_alignment_backend.h"
#include "system_barometer_if.h"
#include "system_calibration.h"
#include "system_gnss_if.h"
#include "system_hardware_quaternion_if.h"
#include "system_imu_if.h"
#include "system_lifecycle.h"
#include "system_magnetometer_if.h"
#include "system_source_selector.h"
#include "system_startup.h"
#include "system_user_alignment_config.h"
#include "system_user_config.h"

typedef struct
{
    uint64_t first_timestamp_us;
    uint8_t active;
} SystemAlignmentGuardDebounce;

typedef struct
{
    float reference_quaternion_wxyz[4];
    uint64_t last_inertial_timestamp_us;
    uint64_t last_attitude_timestamp_us;
    uint32_t last_inertial_sequence;
    uint32_t last_attitude_sequence;
    SystemAlignmentGuardDebounce gyro;
    SystemAlignmentGuardDebounce accel;
    SystemAlignmentGuardDebounce attitude;
    uint8_t reference_valid;
    uint8_t stale_latched;
} SystemAlignmentGuardRuntime;

static SystemAlignmentStatus s_status;
static SystemAlignmentGuardRuntime s_guard;
static uint8_t s_initialized;
static volatile uint8_t s_collecting;
static volatile uint8_t s_frozen;
static volatile uint8_t s_action_active;

static void SystemAlignment_GuardReset(void)
{
    (void)memset(&s_guard, 0, sizeof(s_guard));
}

static uint8_t SystemAlignment_QuaternionNormalize(
    const float input_wxyz[4],
    float normalized_wxyz[4])
{
    float norm_squared = 0.0f;
    float reciprocal_norm;
    uint8_t index;

    if ((input_wxyz == NULL) || (normalized_wxyz == NULL))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT(input_wxyz != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(normalized_wxyz != NULL,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    for (index = 0U; index < 4U; index++)
    {
        if (!isfinite(input_wxyz[index])) { return 0U; }
        norm_squared += input_wxyz[index] * input_wxyz[index];
    }
    if ((!isfinite(norm_squared)) || (norm_squared <= 1.0e-12f))
    {
        return 0U;
    }
    reciprocal_norm = 1.0f / sqrtf(norm_squared);
    for (index = 0U; index < 4U; index++)
    {
        normalized_wxyz[index] = input_wxyz[index] * reciprocal_norm;
    }
    return 1U;
}

static void SystemAlignment_GuardDebounceReset(
    SystemAlignmentGuardDebounce *debounce)
{
    if (debounce == NULL) { return; }
    debounce->first_timestamp_us = 0ULL;
    debounce->active = 0U;
}

static uint8_t SystemAlignment_GuardDebounceUpdate(
    SystemAlignmentGuardDebounce *debounce,
    uint8_t condition,
    uint64_t timestamp_us)
{
    if (debounce == NULL) { return 0U; }
    SILVERSTAR_ASSERT_OBJECT(debounce, SystemAlignmentGuardDebounce,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (condition == 0U)
    {
        SystemAlignment_GuardDebounceReset(debounce);
        return 0U;
    }
    if ((debounce->active == 0U) ||
        (timestamp_us < debounce->first_timestamp_us))
    {
        debounce->first_timestamp_us = timestamp_us;
        debounce->active = 1U;
        return (uint8_t)(
            SYSTEM_USER_ALIGNMENT_GUARD_CONFIRM_DURATION_US == 0ULL);
    }
    return (uint8_t)(
        (timestamp_us - debounce->first_timestamp_us) >=
        SYSTEM_USER_ALIGNMENT_GUARD_CONFIRM_DURATION_US);
}

static uint8_t SystemAlignment_GuardGyroProcess(
    const SystemAlignmentGuardSample *sample)
{
    float gyro_norm;

    SILVERSTAR_ASSERT_OBJECT(sample, SystemAlignmentGuardSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((sample->valid_mask & SYSTEM_ALIGNMENT_GUARD_VALID_GYRO) == 0U)
    {
        SystemAlignment_GuardDebounceReset(&s_guard.gyro);
        return 0U;
    }
    gyro_norm = sqrtf(
        (sample->corrected_gyro_b_radps[0] *
         sample->corrected_gyro_b_radps[0]) +
        (sample->corrected_gyro_b_radps[1] *
         sample->corrected_gyro_b_radps[1]) +
        (sample->corrected_gyro_b_radps[2] *
         sample->corrected_gyro_b_radps[2]));
    return SystemAlignment_GuardDebounceUpdate(&s_guard.gyro,
        (uint8_t)(isfinite(gyro_norm) &&
            (gyro_norm > SYSTEM_USER_ALIGNMENT_GUARD_GYRO_THRESHOLD_RADPS)),
        sample->inertial_sample_timestamp_us);
}

static uint8_t SystemAlignment_GuardAccelProcess(
    const SystemAlignmentGuardSample *sample)
{
    float accel_norm;

    SILVERSTAR_ASSERT_OBJECT(sample, SystemAlignmentGuardSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((sample->valid_mask & SYSTEM_ALIGNMENT_GUARD_VALID_ACCEL) == 0U)
    {
        SystemAlignment_GuardDebounceReset(&s_guard.accel);
        return 0U;
    }
    accel_norm = sqrtf(
        (sample->corrected_accel_b_mps2[0] *
         sample->corrected_accel_b_mps2[0]) +
        (sample->corrected_accel_b_mps2[1] *
         sample->corrected_accel_b_mps2[1]) +
        (sample->corrected_accel_b_mps2[2] *
         sample->corrected_accel_b_mps2[2]));
    return SystemAlignment_GuardDebounceUpdate(&s_guard.accel,
        (uint8_t)(isfinite(accel_norm) &&
            (fabsf(accel_norm - SYSTEM_LOCAL_GRAVITY_MPS2) >
             SYSTEM_USER_ALIGNMENT_GUARD_ACCEL_TOLERANCE_MPS2)),
        sample->inertial_sample_timestamp_us);
}

static uint8_t SystemAlignment_GuardTimestampFresh(
    uint64_t observation_timestamp_us,
    uint64_t sample_timestamp_us)
{
    return (uint8_t)(
        (sample_timestamp_us != 0ULL) &&
        (observation_timestamp_us >= sample_timestamp_us) &&
        ((observation_timestamp_us - sample_timestamp_us) <=
         SYSTEM_USER_ALIGNMENT_GUARD_SAMPLE_FRESHNESS_US));
}

static uint8_t SystemAlignment_GuardReferenceCapture(
    const SystemAlignmentStatus *status)
{
    const SystemAlignmentAttitudeStatus *attitude;

    if (status == NULL) { return 0U; }
    attitude = &status->component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude;
    if ((attitude->quaternion_valid == 0U) ||
        (SystemAlignment_QuaternionNormalize(attitude->quaternion_wxyz,
            s_guard.reference_quaternion_wxyz) == 0U))
    {
        return 0U;
    }
    s_guard.last_attitude_sequence = attitude->sequence;
    s_guard.last_attitude_timestamp_us = attitude->timestamp_us;
    s_guard.reference_valid = 1U;
    return 1U;
}

static uint8_t SystemAlignment_FinalAttitudeAuthoritative(
    const SystemAlignmentStatus *status,
    uint8_t stale_latched)
{
    const SystemAlignmentSourceStatus *component;
    const SystemAlignmentAttitudeStatus *attitude;

    if ((status == NULL) || (stale_latched != 0U) ||
        (status->state == SYSTEM_ALIGNMENT_STATE_STALE))
    {
        return 0U;
    }
    component = &status->component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE];
    attitude = &component->detail.attitude;
    return (uint8_t)((component->ready != 0U) &&
        (attitude->attitude_ready != 0U) &&
        (attitude->quaternion_valid != 0U) &&
        (attitude->final_quaternion_frozen != 0U));
}

static uint8_t SystemAlignment_GuardInertialProcess(
    const SystemAlignmentGuardSample *sample)
{
    uint8_t confirmed = 0U;

    if ((sample == NULL) ||
        (sample->inertial_sequence == s_guard.last_inertial_sequence))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemAlignmentGuardSample,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((s_guard.last_inertial_timestamp_us != 0ULL) &&
        ((sample->inertial_sample_timestamp_us <=
          s_guard.last_inertial_timestamp_us) ||
         ((sample->inertial_sample_timestamp_us -
           s_guard.last_inertial_timestamp_us) >
          SYSTEM_USER_ALIGNMENT_GUARD_SAMPLE_FRESHNESS_US)))
    {
        SystemAlignment_GuardDebounceReset(&s_guard.gyro);
        SystemAlignment_GuardDebounceReset(&s_guard.accel);
    }
    s_guard.last_inertial_sequence = sample->inertial_sequence;
    s_guard.last_inertial_timestamp_us =
        sample->inertial_sample_timestamp_us;
    if (SystemAlignment_GuardTimestampFresh(
            sample->observation_timestamp_us,
            sample->inertial_sample_timestamp_us) == 0U)
    {
        SystemAlignment_GuardDebounceReset(&s_guard.gyro);
        SystemAlignment_GuardDebounceReset(&s_guard.accel);
        return 0U;
    }
    confirmed |= SystemAlignment_GuardGyroProcess(sample);
    confirmed |= SystemAlignment_GuardAccelProcess(sample);
    return confirmed;
}

static uint8_t SystemAlignment_GuardAttitudeProcess(
    const SystemAlignmentStatus *status,
    uint64_t observation_timestamp_us)
{
    const SystemAlignmentAttitudeStatus *attitude;
    float current_quaternion[4];
    float dot = 0.0f;
    float minimum_dot;
    uint8_t index;

    if ((status == NULL) || (s_guard.reference_valid == 0U) ||
        (SYSTEM_ALIGNMENT_BUILD_GUARD_HARDWARE_QUATERNION == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    attitude = &status->component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
        .detail.attitude;
    if (attitude->sequence == s_guard.last_attitude_sequence)
    {
        return 0U;
    }
    if ((s_guard.last_attitude_timestamp_us != 0ULL) &&
        ((attitude->timestamp_us <= s_guard.last_attitude_timestamp_us) ||
         ((attitude->timestamp_us - s_guard.last_attitude_timestamp_us) >
          SYSTEM_USER_ALIGNMENT_GUARD_SAMPLE_FRESHNESS_US)))
    {
        SystemAlignment_GuardDebounceReset(&s_guard.attitude);
    }
    s_guard.last_attitude_sequence = attitude->sequence;
    s_guard.last_attitude_timestamp_us = attitude->timestamp_us;
    if ((attitude->quaternion_valid == 0U) ||
        (SystemAlignment_GuardTimestampFresh(observation_timestamp_us,
            attitude->timestamp_us) == 0U) ||
        (SystemAlignment_QuaternionNormalize(attitude->quaternion_wxyz,
            current_quaternion) == 0U))
    {
        SystemAlignment_GuardDebounceReset(&s_guard.attitude);
        return 0U;
    }
    for (index = 0U; index < 4U; index++)
    {
        dot += current_quaternion[index] *
            s_guard.reference_quaternion_wxyz[index];
    }
    dot = fabsf(dot);
    if (dot > 1.0f) { dot = 1.0f; }
    minimum_dot = cosf(
        SYSTEM_USER_ALIGNMENT_GUARD_ATTITUDE_DELTA_RAD * 0.5f);
    return SystemAlignment_GuardDebounceUpdate(
        &s_guard.attitude,
        (uint8_t)(isfinite(dot) && (dot < minimum_dot)),
        attitude->timestamp_us);
}

static uint8_t SystemAlignment_GuardProcess(
    const SystemAlignmentStatus *status,
    uint8_t frozen)
{
    SystemAlignmentGuardSample sample;
    uint64_t attitude_observation_timestamp_us;
    uint8_t confirmed = 0U;

    if ((SYSTEM_USER_ALIGNMENT_GUARD_ENABLE == 0U) ||
        (status == NULL) || (frozen != 0U) ||
        (s_guard.reference_valid == 0U) ||
        (s_guard.stale_latched != 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(&sample, 0, sizeof(sample));
    if (SystemAlignmentBackend_GuardSampleGet(&sample) != SYSTEM_DEVICE_OK)
    {
        SystemAlignment_GuardDebounceReset(&s_guard.gyro);
        SystemAlignment_GuardDebounceReset(&s_guard.accel);
        attitude_observation_timestamp_us =
            status->component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
                .detail.attitude.receive_timestamp_us;
    }
    else
    {
        confirmed = SystemAlignment_GuardInertialProcess(&sample);
        attitude_observation_timestamp_us =
            sample.observation_timestamp_us;
    }
    confirmed |= SystemAlignment_GuardAttitudeProcess(
        status, attitude_observation_timestamp_us);
    return confirmed;
}

static uint32_t SystemAlignment_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SystemAlignment_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static uint8_t SystemAlignment_StartupDeviceAvailable(
    SystemStartupDeviceId device_id)
{
    const SystemStartupReport *report = SystemStartup_GetReport();

    if ((report == NULL) || (report->completed == 0U))
    {
        return 1U;
    }
    if ((uint32_t)device_id >= SYSTEM_STARTUP_DEVICE_COUNT)
    {
        return 0U;
    }
    return SystemStartup_DeviceReportIsAvailable(
        &report->devices[(uint32_t)device_id]);
}

static uint8_t SystemAlignment_ImuCapabilityReady(void)
{
    uint32_t capability = 0U;

    if (SYSTEM_ALIGNMENT_BUILD_CAPABILITY_IMU == 0U)
    {
        return 1U;
    }
    return (uint8_t)(
        (SystemAlignment_StartupDeviceAvailable(
            SYSTEM_STARTUP_DEVICE_IMU) != 0U) &&
        (SystemImu_CapabilitiesGet(&capability) == SYSTEM_DEVICE_OK) &&
        ((capability & (SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO)) ==
         (SYSTEM_IMU_CAP_ACCEL | SYSTEM_IMU_CAP_GYRO)));
}

static uint8_t SystemAlignment_MagnetometerCapabilityReady(void)
{
    uint32_t capability = 0U;

    if (SYSTEM_ALIGNMENT_BUILD_CAPABILITY_MAGNETOMETER == 0U)
    {
        return 1U;
    }
    return (uint8_t)(
        (SystemAlignment_StartupDeviceAvailable(
            SYSTEM_STARTUP_DEVICE_MAGNETOMETER) != 0U) &&
        (SystemMagnetometer_CapabilitiesGet(&capability) ==
         SYSTEM_DEVICE_OK) &&
        ((capability & SYSTEM_MAG_CAP_PHYSICAL_UNIT) != 0U));
}

static uint8_t SystemAlignment_HardwareQuaternionCapabilityReady(void)
{
    uint32_t capability = 0U;

    if (SYSTEM_ALIGNMENT_BUILD_CAPABILITY_HARDWARE_QUATERNION == 0U)
    {
        return 1U;
    }
    return (uint8_t)(
        (SystemAlignment_StartupDeviceAvailable(
            SYSTEM_STARTUP_DEVICE_HARDWARE_QUATERNION) != 0U) &&
        (SystemHardwareQuaternion_CapabilitiesGet(&capability) ==
         SYSTEM_DEVICE_OK) &&
        ((capability & SYSTEM_HW_QUAT_CAP_OUTPUT) != 0U));
}

static uint8_t SystemAlignment_AttitudeCapabilityReady(void)
{
    return (uint8_t)(
        (SystemAlignment_ImuCapabilityReady() != 0U) &&
        (SystemAlignment_MagnetometerCapabilityReady() != 0U) &&
        (SystemAlignment_HardwareQuaternionCapabilityReady() != 0U));
}

static SystemAlignmentSourceMask SystemAlignment_CapabilityDetect(void)
{
    SystemAlignmentSourceMask mask = 0U;
    uint32_t capability = 0U;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemAlignment_AttitudeCapabilityReady() != 0U)
    {
        mask |= SYSTEM_ALIGNMENT_SOURCE_MASK_ATTITUDE;
    }

    capability = 0U;
    if ((SystemAlignment_StartupDeviceAvailable(
            SYSTEM_STARTUP_DEVICE_GNSS) != 0U) &&
        (SystemGnss_CapabilitiesGet(&capability) == SYSTEM_DEVICE_OK) &&
        ((capability & SYSTEM_GNSS_CAP_POSITION) != 0U))
    {
        mask |= SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN;
    }

    capability = 0U;
    if ((SystemAlignment_StartupDeviceAvailable(
            SYSTEM_STARTUP_DEVICE_BAROMETER) != 0U) &&
        (SystemBarometer_CapabilitiesGet(&capability) == SYSTEM_DEVICE_OK) &&
        ((capability & (SYSTEM_BARO_VALID_PRESSURE |
                        SYSTEM_BARO_VALID_ALTITUDE)) != 0U))
    {
        mask |= SYSTEM_ALIGNMENT_SOURCE_MASK_BARO_ORIGIN;
    }
    return mask;
}

SystemAlignmentConfigResult SystemAlignment_MasksValidate(
    SystemAlignmentSourceMask capability_mask,
    SystemAlignmentSourceMask selected_mask,
    SystemAlignmentSourceMask required_mask,
    SystemAlignmentSourceMask *unavailable_mask)
{
    SystemAlignmentSourceMask unavailable =
        selected_mask & ~capability_mask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (unavailable_mask != NULL)
    {
        *unavailable_mask = unavailable;
    }
    if ((required_mask & ~selected_mask) != 0U)
    {
        return SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED;
    }
    if ((required_mask & unavailable) != 0U)
    {
        return SYSTEM_ALIGNMENT_CONFIG_REQUIRED_UNAVAILABLE;
    }
    /* Optional selected sources may be unavailable for this boot.  Preserve
       that fact in unavailable_mask, but keep the mission configuration valid
       so the source can degrade cleanly instead of forcing FAULT. */
    return SYSTEM_ALIGNMENT_CONFIG_OK;
}

static void SystemAlignment_ComponentInitialize(
    SystemAlignmentSourceStatus *component,
    SystemAlignmentSourceId source_id,
    SystemAlignmentState state)
{
    SystemAlignmentSourceMask bit = SYSTEM_ALIGNMENT_SOURCE_BIT(source_id);

    SILVERSTAR_ASSERT_OBJECT(component, SystemAlignmentSourceStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(component, 0, sizeof(*component));
    component->supported = (uint8_t)((s_status.capability_mask & bit) != 0U);
    component->selected = (uint8_t)((s_status.selected_mask & bit) != 0U);
    component->required = (uint8_t)((s_status.required_mask & bit) != 0U);
    if ((component->selected == 0U) || (component->supported == 0U) ||
        ((s_status.missing_adapter_mask & bit) != 0U))
    {
        component->state = SYSTEM_ALIGNMENT_COMPONENT_DISABLED;
    }
    else if (state == SYSTEM_ALIGNMENT_STATE_COLLECTING)
    {
        component->state = SYSTEM_ALIGNMENT_COMPONENT_COLLECTING;
    }
    else if (state == SYSTEM_ALIGNMENT_STATE_FAILED)
    {
        component->state = SYSTEM_ALIGNMENT_COMPONENT_FAILED;
    }
    else
    {
        component->state = SYSTEM_ALIGNMENT_COMPONENT_NOT_READY;
    }
}

static void SystemAlignment_StatusReset(SystemAlignmentState state)
{
    SystemAlignmentSourceMask capability_mask = s_status.capability_mask;
    SystemAlignmentSourceMask selected_mask = s_status.selected_mask;
    SystemAlignmentSourceMask required_mask = s_status.required_mask;
    SystemAlignmentSourceMask unavailable_mask = s_status.unavailable_mask;
    SystemAlignmentSourceMask missing_adapter_mask =
        s_status.missing_adapter_mask;
    SystemAlignmentConfigResult config_result = s_status.config_result;
    uint32_t start_sequence = s_status.start_sequence;
    uint32_t source;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    (void)memset(&s_status, 0, sizeof(s_status));
    s_status.start_sequence = start_sequence;
    s_status.capability_mask = capability_mask;
    s_status.selected_mask = selected_mask;
    s_status.required_mask = required_mask;
    s_status.unavailable_mask = unavailable_mask;
    s_status.missing_adapter_mask = missing_adapter_mask;
    s_status.config_result = config_result;
    s_status.state = state;
    for (source = 0U; source < SYSTEM_ALIGNMENT_SOURCE_COUNT; source++)
    {
        SystemAlignment_ComponentInitialize(&s_status.component[source],
            (SystemAlignmentSourceId)source, state);
    }
}

static uint8_t SystemAlignment_ModificationAllowed(void)
{
    SystemLifecycleState state = SystemLifecycle_GetState();

    return (uint8_t)((state == SYSTEM_STATE_BOOT) ||
                     (state == SYSTEM_STATE_SELF_TEST) ||
                     (state == SYSTEM_STATE_PREFLIGHT) ||
                     (state == SYSTEM_STATE_READY));
}

static SystemDeviceResult SystemAlignment_ActionBegin(void)
{
    uint32_t primask;

    primask = SystemAlignment_IrqLock();
    if (s_initialized == 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_action_active != 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    s_action_active = 1U;
    SystemAlignment_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static void SystemAlignment_ActionEnd(void)
{
    uint32_t primask = SystemAlignment_IrqLock();

    s_action_active = 0U;
    SystemAlignment_IrqUnlock(primask);
}

static void SystemAlignment_PreflightStateRestore(void)
{
    if (SystemLifecycle_GetState() == SYSTEM_STATE_READY)
    {
        (void)SystemLifecycle_EnterPreflight();
    }
}

void SystemAlignment_Init(void)
{
    uint32_t primask = SystemAlignment_IrqLock();
    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus, SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(s_initialized <= 1U, SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);

    (void)memset(&s_status, 0, sizeof(s_status));
    SystemAlignment_GuardReset();
    s_status.capability_mask = SystemAlignment_CapabilityDetect();
    s_status.selected_mask = SYSTEM_USER_ALIGNMENT_SELECTED_MASK;
    s_status.required_mask = SYSTEM_USER_ALIGNMENT_REQUIRED_MASK;
    /* GNSS-dependent navigation cannot make READY on attitude/barometer alone. */
    if ((SYSTEM_FUSION_ALGORITHM != SYSTEM_FUSION_NONE) &&
        (SYSTEM_ESTIMATOR_GNSS_FUSION_REQUIRES_PREFLIGHT_ORIGIN != 0U))
    {
        s_status.required_mask |= SYSTEM_ALIGNMENT_SOURCE_MASK_GNSS_ORIGIN;
    }
    s_status.config_result = SystemAlignment_MasksValidate(
        s_status.capability_mask, s_status.selected_mask,
        s_status.required_mask, &s_status.unavailable_mask);
    SystemAlignment_StatusReset((s_status.config_result ==
        SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED) ?
            SYSTEM_ALIGNMENT_STATE_FAILED : SYSTEM_ALIGNMENT_STATE_IDLE);
    s_initialized = 1U;
    s_collecting = 0U;
    s_frozen = 0U;
    s_action_active = 0U;
    SystemAlignment_IrqUnlock(primask);
}

static SystemDeviceResult SystemAlignment_CalibrationUnavailableReset(void)
{
    uint32_t primask = SystemAlignment_IrqLock();

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (s_initialized == 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_action_active != 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    s_collecting = 0U;
    s_frozen = 0U;
    SystemAlignment_GuardReset();
    SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_IDLE);
    SystemAlignment_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static uint8_t SystemAlignment_SourceRefresh(
    SystemAlignmentStatus *status,
    uint32_t source)
{
    SystemAlignmentSourceMask bit = SYSTEM_ALIGNMENT_SOURCE_BIT(source);
    SystemAlignmentSourceStatus next;

    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((status->selected_mask & bit) == 0U)
    {
        return 0U;
    }
    if (((status->capability_mask & bit) == 0U) ||
        ((status->missing_adapter_mask & bit) != 0U))
    {
        status->component[source].state =
            SYSTEM_ALIGNMENT_COMPONENT_DISABLED;
        status->component[source].ready = 0U;
        return (uint8_t)((status->required_mask & bit) != 0U);
    }
    (void)memset(&next, 0, sizeof(next));
    if (SystemAlignmentBackend_SourceStatusGet(
            (SystemAlignmentSourceId)source, &next) != SYSTEM_DEVICE_OK)
    {
        next.state = SYSTEM_ALIGNMENT_COMPONENT_FAILED;
    }
    next.supported = 1U;
    next.selected = 1U;
    next.required = (uint8_t)((status->required_mask & bit) != 0U);
    next.ready = (uint8_t)((next.ready != 0U) ||
        (next.state == SYSTEM_ALIGNMENT_COMPONENT_READY));
    status->component[source] = next;
    if (next.ready != 0U)
    {
        status->ready_mask |= bit;
    }
    return (uint8_t)((next.required != 0U) &&
        ((next.state == SYSTEM_ALIGNMENT_COMPONENT_FAILED) ||
         (next.state == SYSTEM_ALIGNMENT_COMPONENT_DISABLED)));
}

static uint8_t SystemAlignment_SourcesRefresh(SystemAlignmentStatus *status)
{
    uint8_t required_failed = 0U;
    uint32_t source;

    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    status->ready_mask = 0U;
    for (source = 0U; source < SYSTEM_ALIGNMENT_SOURCE_COUNT; source++)
    {
        required_failed |= SystemAlignment_SourceRefresh(status, source);
    }
    return required_failed;
}

static void SystemAlignment_StateResolve(SystemAlignmentStatus *status,
                                         uint8_t required_failed)
{
    SILVERSTAR_ASSERT_OBJECT(status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    status->ready = (uint8_t)(
        (status->ready_mask & status->required_mask) == status->required_mask);
    if (s_guard.stale_latched != 0U)
    {
        status->state = SYSTEM_ALIGNMENT_STATE_STALE;
        status->stale_reason = SYSTEM_ALIGNMENT_STALE_REASON_MOTION;
        status->ready = 0U;
    }
    else if ((status->config_result ==
              SYSTEM_ALIGNMENT_CONFIG_REQUIRED_NOT_SELECTED) ||
             (status->config_result ==
              SYSTEM_ALIGNMENT_CONFIG_ADAPTER_UNAVAILABLE) ||
             (required_failed != 0U))
    {
        status->state = SYSTEM_ALIGNMENT_STATE_FAILED;
        status->ready = 0U;
    }
    else if (status->ready == 0U)
    {
        status->state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
    }
    else
    {
        status->state = SYSTEM_ALIGNMENT_STATE_READY;
        if ((SYSTEM_USER_ALIGNMENT_GUARD_ENABLE != 0U) &&
            (s_guard.reference_valid == 0U) &&
            (SystemAlignment_GuardReferenceCapture(status) == 0U))
        {
            status->state = SYSTEM_ALIGNMENT_STATE_COLLECTING;
            status->ready = 0U;
        }
    }
}

static uint8_t SystemAlignment_StaleGuardApply(
    SystemAlignmentStatus *status,
    uint8_t frozen)
{
    if ((status->state != SYSTEM_ALIGNMENT_STATE_READY) ||
        (SystemAlignment_GuardProcess(status, frozen) == 0U))
    {
        return 0U;
    }
    s_guard.stale_latched = 1U;
    status->state = SYSTEM_ALIGNMENT_STATE_STALE;
    status->stale_reason = SYSTEM_ALIGNMENT_STALE_REASON_MOTION;
    status->ready = 0U;
    return 1U;
}

SystemDeviceResult SystemAlignment_Process(void)
{
    SystemAlignmentStatus status;
    SystemDeviceResult action_result;
    uint8_t collecting;
    uint8_t frozen;
    uint8_t required_failed;
    uint8_t stale_entered;
    uint32_t primask;

    if (SystemCalibration_IsReady() == 0U)
    {
        return SystemAlignment_CalibrationUnavailableReset();
    }

    action_result = SystemAlignment_ActionBegin();
    if (action_result != SYSTEM_DEVICE_OK)
    {
        return action_result;
    }
    primask = SystemAlignment_IrqLock();
    collecting = s_collecting;
    frozen = s_frozen;
    status = s_status;
    SystemAlignment_IrqUnlock(primask);
    SILVERSTAR_ASSERT_OBJECT(&status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((collecting == 0U) && (frozen == 0U))
    {
        SystemAlignment_ActionEnd();
        return SYSTEM_DEVICE_OK;
    }

    required_failed = SystemAlignment_SourcesRefresh(&status);
    SystemAlignment_StateResolve(&status, required_failed);
    stale_entered = SystemAlignment_StaleGuardApply(&status, frozen);

    primask = SystemAlignment_IrqLock();
    s_status = status;
    SystemAlignment_IrqUnlock(primask);
    SystemAlignment_ActionEnd();
    if (stale_entered != 0U)
    {
        SystemAlignment_PreflightStateRestore();
    }
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_StatusGet(SystemAlignmentStatus *status)
{
    uint32_t primask;

    if (status == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    primask = SystemAlignment_IrqLock();
    if (s_initialized == 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    *status = s_status;
    SystemAlignment_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_DetailGet(SystemAlignmentStatus *detail)
{
    return SystemAlignment_StatusGet(detail);
}

SystemDeviceResult SystemAlignment_SummaryGet(SystemAlignmentSummary *summary)
{
    uint32_t primask;

    if (summary == NULL)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(summary, SystemAlignmentSummary,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    primask = SystemAlignment_IrqLock();
    if (s_initialized == 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    summary->start_sequence = s_status.start_sequence;
    summary->selected_mask = s_status.selected_mask;
    summary->required_mask = s_status.required_mask;
    summary->ready_mask = s_status.ready_mask;
    summary->state = s_status.state;
    summary->stale_reason = s_status.stale_reason;
    summary->preflight_attitude_source =
        (SystemAlignment_FinalAttitudeAuthoritative(
            &s_status, s_guard.stale_latched) != 0U) ?
            SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT :
            SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE;
    summary->ready = s_status.ready;
    SystemAlignment_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

uint8_t SystemAlignment_IsReady(void)
{
    uint8_t ready;
    uint32_t primask = SystemAlignment_IrqLock();

    ready = (s_initialized != 0U) ? s_status.ready : 0U;
    SystemAlignment_IrqUnlock(primask);
    return ready;
}

static SystemDeviceResult SystemAlignment_HardwareQuaternionGet(
    float quaternion_wxyz[4],
    SystemAlignmentPreflightAttitudeSource *source)
{
    SystemHardwareQuaternionSample hardware_sample;

    SILVERSTAR_ASSERT(quaternion_wxyz != NULL,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(source != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    (void)memset(&hardware_sample, 0, sizeof(hardware_sample));
    if ((SystemHardwareQuaternion_LatestSampleGet(&hardware_sample) !=
         SYSTEM_DEVICE_OK) ||
        (hardware_sample.valid == 0U) ||
        (hardware_sample.normalized == 0U) ||
        (SystemAlignment_QuaternionNormalize(
            hardware_sample.quaternion_wxyz, quaternion_wxyz) == 0U))
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    *source = SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_HARDWARE;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_PreflightQuaternionGet(
    float quaternion_wxyz[4],
    SystemAlignmentPreflightAttitudeSource *source)
{
    SystemLifecycleState lifecycle_state;
    float alignment_quaternion[4];
    uint8_t alignment_authoritative;
    uint32_t primask;

    if ((quaternion_wxyz == NULL) || (source == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT(quaternion_wxyz != NULL,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    SILVERSTAR_ASSERT(source != NULL, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_NULL_POINTER);
    lifecycle_state = SystemLifecycle_GetState();
    if ((lifecycle_state != SYSTEM_STATE_PREFLIGHT) &&
        (lifecycle_state != SYSTEM_STATE_READY))
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }

    primask = SystemAlignment_IrqLock();
    if (s_initialized == 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    alignment_authoritative = SystemAlignment_FinalAttitudeAuthoritative(
        &s_status, s_guard.stale_latched);
    if (alignment_authoritative != 0U)
    {
        (void)memcpy(alignment_quaternion,
            s_status.component[SYSTEM_ALIGNMENT_SOURCE_ATTITUDE]
                .detail.attitude.quaternion_wxyz,
            sizeof(alignment_quaternion));
    }
    SystemAlignment_IrqUnlock(primask);

    if (alignment_authoritative != 0U)
    {
        if (SystemAlignment_QuaternionNormalize(alignment_quaternion,
                quaternion_wxyz) == 0U)
        {
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
        *source = SYSTEM_ALIGNMENT_PREFLIGHT_ATTITUDE_ALIGNMENT;
        return SYSTEM_DEVICE_OK;
    }

    return SystemAlignment_HardwareQuaternionGet(quaternion_wxyz, source);
}

SystemDeviceResult SystemAlignment_Start(void)
{
    SystemDeviceResult result;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemAlignment_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    if (SystemCalibration_IsReady() == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_status.config_result != SYSTEM_ALIGNMENT_CONFIG_OK)
    {
        return SYSTEM_DEVICE_UNSUPPORTED;
    }
    result = SystemSourceSelector_ImuSelectAndLock();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    result = SystemAlignment_ActionBegin();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    primask = SystemAlignment_IrqLock();
    s_collecting = 0U;
    s_frozen = 0U;
    SystemAlignment_GuardReset();
    SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_CHECKING);
    SystemAlignment_IrqUnlock(primask);
    result = SystemAlignmentBackend_Reset();
    primask = SystemAlignment_IrqLock();
    if (result == SYSTEM_DEVICE_OK)
    {
        s_status.start_sequence++;
        s_collecting = 1U;
        SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_COLLECTING);
    }
    else
    {
        SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_FAILED);
    }
    SystemAlignment_IrqUnlock(primask);
    SystemAlignment_ActionEnd();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    SystemAlignment_PreflightStateRestore();
    /* FlightTask owns status refresh and motion-guard work. The ACK reports
     * accepted initialization, not completion of alignment. */
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Stop(void)
{
    SystemDeviceResult result;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemAlignment_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    result = SystemAlignment_ActionBegin();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    primask = SystemAlignment_IrqLock();
    s_collecting = 0U;
    s_frozen = 0U;
    SystemAlignment_GuardReset();
    SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_IDLE);
    SystemAlignment_IrqUnlock(primask);
    SystemAlignment_ActionEnd();
    SystemAlignment_PreflightStateRestore();
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult SystemAlignment_Reset(void)
{
    SystemDeviceResult result;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemAlignment_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    result = SystemAlignment_ActionBegin();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    primask = SystemAlignment_IrqLock();
    s_collecting = 0U;
    s_frozen = 0U;
    SystemAlignment_GuardReset();
    SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_CHECKING);
    SystemAlignment_IrqUnlock(primask);
    result = SystemAlignmentBackend_Reset();
    primask = SystemAlignment_IrqLock();
    SystemAlignment_StatusReset((result == SYSTEM_DEVICE_OK) ?
        SYSTEM_ALIGNMENT_STATE_IDLE : SYSTEM_ALIGNMENT_STATE_FAILED);
    SystemAlignment_IrqUnlock(primask);
    SystemAlignment_ActionEnd();
    if (result == SYSTEM_DEVICE_OK)
    {
        SystemAlignment_PreflightStateRestore();
    }
    return result;
}

SystemDeviceResult SystemAlignment_CalibrationInvalidate(void)
{
    SystemDeviceResult result = SYSTEM_DEVICE_OK;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemAlignment_ModificationAllowed() == 0U)
    {
        return SYSTEM_DEVICE_BAD_STATE;
    }
    primask = SystemAlignment_IrqLock();
    if (s_initialized == 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_action_active != 0U)
    {
        SystemAlignment_IrqUnlock(primask);
        return SYSTEM_DEVICE_BUSY;
    }
    s_action_active = 1U;
    s_collecting = 0U;
    s_frozen = 0U;
    SystemAlignment_GuardReset();
    SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_IDLE);
    SystemAlignment_IrqUnlock(primask);
    result = SystemAlignmentBackend_Reset();
    if (result != SYSTEM_DEVICE_OK)
    {
        primask = SystemAlignment_IrqLock();
        SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_FAILED);
        SystemAlignment_IrqUnlock(primask);
    }
    SystemAlignment_ActionEnd();
    SystemAlignment_PreflightStateRestore();
    return result;
}

SystemDeviceResult SystemAlignment_PrepareMission(void)
{
    SystemDeviceResult result;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (SystemCalibration_IsReady() == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemAlignment_Process();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    /*
     * Do not copy the full SystemAlignmentStatus onto the FlightTask stack
     * here.  START calls this function synchronously and it in turn calls
     * SystemAlignment_Process(), which already has a sizeable stack frame.
     * Reading the authoritative ready bit under the same IRQ lock keeps the
     * readiness check atomic while avoiding a large nested stack frame.
     */
    if (SystemAlignment_IsReady() == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    result = SystemAlignment_ActionBegin();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    primask = SystemAlignment_IrqLock();
    s_status.state = SYSTEM_ALIGNMENT_STATE_CHECKING;
    SystemAlignment_IrqUnlock(primask);
    result = SystemAlignmentBackend_PrepareMission();
    SystemAlignment_ActionEnd();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    return SystemAlignment_Process();
}

SystemDeviceResult SystemAlignment_OriginsFreeze(void)
{
    SystemDeviceResult result = SystemAlignment_ActionBegin();
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_status, SystemAlignmentStatus,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    result = SystemAlignmentBackend_FreezeSources();
    if (result == SYSTEM_DEVICE_OK)
    {
        primask = SystemAlignment_IrqLock();
        s_collecting = 0U;
        s_frozen = 1U;
        SystemAlignment_IrqUnlock(primask);
    }
    SystemAlignment_ActionEnd();
    if (result != SYSTEM_DEVICE_OK)
    {
        return result;
    }
    return SystemAlignment_Process();
}

void SystemAlignment_MissionPreparationAbort(void)
{
    SystemDeviceResult process_result;
    uint32_t primask;

    if (SystemAlignment_ActionBegin() != SYSTEM_DEVICE_OK)
    {
        return;
    }
    SystemAlignmentBackend_MissionPreparationAbort();
    primask = SystemAlignment_IrqLock();
    s_collecting = 1U;
    s_frozen = 0U;
    SystemAlignment_StatusReset(SYSTEM_ALIGNMENT_STATE_COLLECTING);
    SystemAlignment_IrqUnlock(primask);
    SystemAlignment_ActionEnd();
    process_result = SystemAlignment_Process();
    if (process_result != SYSTEM_DEVICE_OK)
    {
        /* The owning task retries the read-only refresh next cycle. */
    }
}

uint8_t SystemAlignment_IsCollecting(void)
{
    uint8_t collecting;
    uint32_t primask = SystemAlignment_IrqLock();

    collecting = (uint8_t)((s_collecting != 0U) && (s_frozen == 0U));
    SystemAlignment_IrqUnlock(primask);
    return collecting;
}

SystemAlignmentSourceMask SystemAlignment_CapabilityMaskGet(void)
{
    SystemAlignmentSourceMask mask;
    uint32_t primask = SystemAlignment_IrqLock();

    mask = s_status.capability_mask;
    SystemAlignment_IrqUnlock(primask);
    return mask;
}
