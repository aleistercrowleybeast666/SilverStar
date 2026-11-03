#include "mag_rotation.h"
#include "common_format.h"
#include "system_mag_rotation_if.h"
#include "system_installation_active_if.h"
#include "system_descriptor_if.h"
#include "system_calibration.h"
#include "system_mag_calibration.h"
#include "system_source_selector.h"
#include "logger_bus.h"
#include "platform_critical.h"
#include "platform_memory.h"
#include "platform_time.h"
#include <math.h>
#include <string.h>

#define ROTATION_HISTORY_COUNT 8U
#define ROTATION_FRESH_US 150000ULL
#define ROTATION_MAX_CONVERSION_US 18000ULL
#define ROTATION_MAX_EDGE_GAP_US 4500ULL

typedef struct
{
    uint32_t low_us;
    float angle[3];
} RotationHistory;
typedef struct
{
    MagRotationFit fit;
    RotationHistory history[ROTATION_HISTORY_COUNT];
    float angle[3], last_rate[3];
    uint64_t edge_us, mag_us, mag_mid_us;
    uint32_t edge, imu_seq, epoch, imu_generation, mag_generation, mag_crc;
    uint32_t mag_sequence, base, estimate, adopted, revision, config, log_failures, quality;
    uint64_t fallback_us, retry_us;
    uint32_t fallback_base, fallback_quality, fallback_revision;
    uint8_t pending_fixed, pending_quality;
    uint16_t imu_physical, mag_physical;
    uint8_t head, count, valid, initialized, qualified, base_known, reset_requested;
} RotationRuntime;
static PLATFORM_CPU_FAST_BSS RotationRuntime s_rotation;

static uint8_t Rotation_Log(uint64_t time_us, FlightLogEventId event, uint32_t value,
                            uint32_t revision)
{
    if (LoggerBus_RotationEventPush(time_us, event, value, revision) == LOGGER_BUS_RESULT_OK)
    {
        return 1U;
    }
    PlatformCriticalState lock = PlatformCritical_Enter();
    if (s_rotation.log_failures < UINT32_MAX)
    {
        s_rotation.log_failures++;
    }
    PlatformCritical_Exit(lock);
    return 0U;
}

/* Only the DeviceTask mutates the deferred transition. Preserve its original
 * measurement time and revision across a temporarily full logger. */
static void Rotation_FallbackFlush(uint64_t now)
{
    if ((!s_rotation.pending_fixed && !s_rotation.pending_quality) || now < s_rotation.retry_us)
    {
        return;
    }
    s_rotation.retry_us = now + 100000ULL;
    if (s_rotation.pending_fixed &&
        Rotation_Log(s_rotation.fallback_us, FLIGHT_LOG_EVENT_MAG_ROTATION_FIXED,
                     s_rotation.fallback_base, s_rotation.fallback_revision))
    {
        s_rotation.pending_fixed = 0U;
    }
    if (!s_rotation.pending_fixed && s_rotation.pending_quality &&
        Rotation_Log(s_rotation.fallback_us, FLIGHT_LOG_EVENT_MAG_ROTATION_QUALITY,
                     s_rotation.fallback_quality, s_rotation.fallback_revision))
    {
        s_rotation.pending_quality = 0U;
    }
}

static void Rotation_FixedSelect(uint32_t quality, uint64_t now)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t was_valid = s_rotation.valid;
    s_rotation.valid = 0U;
    s_rotation.quality = quality;
    if (was_valid)
    {
        if (s_rotation.revision < UINT32_MAX)
        {
            s_rotation.revision++;
        }
        s_rotation.fallback_us = now;
        s_rotation.fallback_quality = quality;
        s_rotation.fallback_revision = s_rotation.revision;
        s_rotation.fallback_base = s_rotation.base;
        s_rotation.retry_us = now;
        s_rotation.pending_fixed = 1U;
        s_rotation.pending_quality = 1U;
    }
    PlatformCritical_Exit(lock);
    Rotation_FallbackFlush(now);
}

static void Rotation_Invalidate(MagRotationResult reason, uint64_t now)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_rotation.qualified = 0U;
    s_rotation.mag_us = 0ULL;
    s_rotation.mag_sequence = 0U;
    PlatformCritical_Exit(lock);
    Rotation_FixedSelect((uint32_t)reason | 0x00ffff00UL, now);
    MagRotation_Reset(&s_rotation.fit);
    s_rotation.mag_mid_us = 0ULL;
}

void SystemMagRotation_SourceLost(void)
{
    /* A maintenance Stop may run outside DeviceTask. Revoke immediately;
     * DeviceTask alone owns the mutable fit and integration history. */
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_rotation.qualified = 0U;
    s_rotation.reset_requested = 1U;
    PlatformCritical_Exit(lock);
}

static void Rotation_ResetOwner(void)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_rotation.edge_us = 0ULL;
    s_rotation.reset_requested = 0U;
    PlatformCritical_Exit(lock);
    Rotation_Invalidate(MagRotationResult_Stale, PlatformTime_Us());
    s_rotation.count = 0U;
    (void)memset(s_rotation.angle, 0, sizeof(s_rotation.angle));
}

static uint8_t Rotation_GyroGet(uint32_t source, const float input[3], uint32_t *generation,
                                uint16_t *physical, float gyro[3])
{
    SystemCalibrationImuCorrection correction;
    SystemDeviceDescriptor descriptor;
    uint8_t selected;
    if (input == NULL || source > UINT8_MAX ||
        SystemSourceSelector_ImuActiveInstanceGet(&selected) != SYSTEM_DEVICE_OK ||
        selected != source ||
        SystemDescriptor_DeviceFind(SYSTEM_DEVICE_CLASS_IMU, selected, &descriptor) !=
            SYSTEM_DEVICE_OK ||
        descriptor.physical_device_id == 0U)
    {
        return 0U;
    }
    *generation = SystemCalibration_GenerationGet();
    if (SystemCalibration_ImuCorrectionGet(&correction) != SYSTEM_DEVICE_OK ||
        correction.ready == 0U || *generation != SystemCalibration_GenerationGet())
    {
        return 0U;
    }
    *physical = descriptor.physical_device_id;
    for (uint8_t i = 0U; i < 3U; i++)
    {
        gyro[i] = (input[i] - correction.gyro_bias_radps[i]) * correction.gyro_scale[i];
        if (!isfinite(gyro[i]) || fabsf(gyro[i]) > 3.0f)
        {
            return 0U;
        }
    }
    return 1U;
}

void SystemMagRotation_ImuObserve(uint32_t source, uint32_t epoch, uint32_t sequence, uint32_t edge,
                                  uint64_t ready_us, const float input[3], uint8_t frame_ok)
{
    float gyro[3];
    uint32_t generation;
    uint16_t physical;
    PlatformCriticalState start_lock = PlatformCritical_Enter();
    uint8_t reset = s_rotation.reset_requested;
    PlatformCritical_Exit(start_lock);
    if (reset != 0U)
    {
        Rotation_ResetOwner();
    }
    if (frame_ok != 1U || epoch == 0U || sequence == 0U || ready_us == 0ULL ||
        !Rotation_GyroGet(source, input, &generation, &physical, gyro))
    {
        Rotation_ResetOwner();
        return;
    }
    if (s_rotation.edge_us != 0ULL &&
        (epoch != s_rotation.epoch || generation != s_rotation.imu_generation ||
         physical != s_rotation.imu_physical || edge != s_rotation.edge + 1U ||
         sequence != s_rotation.imu_seq + 1U || ready_us <= s_rotation.edge_us ||
         ready_us - s_rotation.edge_us > ROTATION_MAX_EDGE_GAP_US))
    {
        Rotation_ResetOwner();
    }
    if (s_rotation.edge_us != 0ULL)
    {
        float half_dt = (float)(ready_us - s_rotation.edge_us) * 0.0000005f;
        for (uint8_t i = 0U; i < 3U; i++)
        {
            s_rotation.angle[i] += half_dt * (gyro[i] + s_rotation.last_rate[i]);
        }
    }
    RotationHistory *item = &s_rotation.history[s_rotation.head];
    item->low_us = (uint32_t)ready_us;
    (void)memcpy(item->angle, s_rotation.angle, sizeof(item->angle));
    s_rotation.head = (uint8_t)((s_rotation.head + 1U) % ROTATION_HISTORY_COUNT);
    if (s_rotation.count < ROTATION_HISTORY_COUNT)
    {
        s_rotation.count++;
    }
    (void)memcpy(s_rotation.last_rate, gyro, sizeof(gyro));
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_rotation.edge_us = ready_us;
    s_rotation.epoch = epoch;
    s_rotation.edge = edge;
    s_rotation.imu_seq = sequence;
    s_rotation.imu_generation = generation;
    s_rotation.imu_physical = physical;
    PlatformCritical_Exit(lock);
}

/* Interpolate only between two actually observed edge samples. The short
 * uint32 clock is compared by age relative to a fresh, full-width last edge. */
static uint8_t Rotation_AngleGet(uint64_t midpoint, float angle[3])
{
    if (midpoint > s_rotation.edge_us || s_rotation.edge_us - midpoint > 30000ULL)
    {
        return 0U;
    }
    uint32_t age = (uint32_t)(s_rotation.edge_us - midpoint);
    for (uint8_t i = 1U; i < s_rotation.count; i++)
    {
        uint8_t right =
            (uint8_t)((s_rotation.head + ROTATION_HISTORY_COUNT - i) % ROTATION_HISTORY_COUNT);
        uint8_t left = (uint8_t)((right + ROTATION_HISTORY_COUNT - 1U) % ROTATION_HISTORY_COUNT);
        uint32_t a = (uint32_t)s_rotation.edge_us - s_rotation.history[left].low_us;
        uint32_t b = (uint32_t)s_rotation.edge_us - s_rotation.history[right].low_us;
        if (a >= age && age >= b && a > b && a - b <= ROTATION_MAX_EDGE_GAP_US)
        {
            float f = (float)(a - age) / (float)(a - b);
            for (uint8_t k = 0U; k < 3U; k++)
            {
                angle[k] =
                    s_rotation.history[left].angle[k] +
                    f * (s_rotation.history[right].angle[k] - s_rotation.history[left].angle[k]);
            }
            return 1U;
        }
    }
    return 0U;
}

static void Rotation_BaseQuaternion(const float m[9], float q[4])
{
    float k[4] = {1.0f + m[0] + m[4] + m[8], 1.0f + m[0] - m[4] - m[8], 1.0f - m[0] + m[4] - m[8],
                  1.0f - m[0] - m[4] + m[8]};
    uint8_t best = 0U;
    for (uint8_t i = 1U; i < 4U; i++)
    {
        if (k[i] > k[best])
        {
            best = i;
        }
    }
    float a = 0.5f * sqrtf(k[best]), f = 0.25f / a;
    if (best == 0U)
    {
        q[0] = a;
        q[1] = (m[7] - m[5]) * f;
        q[2] = (m[2] - m[6]) * f;
        q[3] = (m[3] - m[1]) * f;
    }
    else if (best == 1U)
    {
        q[1] = a;
        q[0] = (m[7] - m[5]) * f;
        q[2] = (m[1] + m[3]) * f;
        q[3] = (m[2] + m[6]) * f;
    }
    else if (best == 2U)
    {
        q[2] = a;
        q[0] = (m[2] - m[6]) * f;
        q[1] = (m[1] + m[3]) * f;
        q[3] = (m[5] + m[7]) * f;
    }
    else
    {
        q[3] = a;
        q[0] = (m[3] - m[1]) * f;
        q[1] = (m[2] + m[6]) * f;
        q[2] = (m[5] + m[7]) * f;
    }
}

static uint32_t Rotation_Compose(const float a[4], const float b[4])
{
    float q[4] = {a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3],
                  a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2],
                  a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1],
                  a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0]};
    return MagRotation_Encode(q);
}

static void Rotation_Publish(MagRotationResult result, const float base_q[4], uint64_t when)
{
    if (s_rotation.pending_fixed || s_rotation.pending_quality ||
        result == MagRotationResult_Training || result == MagRotationResult_Waiting)
    {
        return;
    }
    if (s_rotation.revision == UINT32_MAX)
    {
        Rotation_Invalidate(MagRotationResult_Stale, when);
        return;
    }
    s_rotation.revision++;
    float rms = s_rotation.fit.relative_rms;
    uint32_t residual = isfinite(rms) ? (uint32_t)fminf(65534.0f, rms * 10000.0f) : 65535U;
    uint32_t quality =
        (uint32_t)result | (residual << 8U) | ((uint32_t)s_rotation.fit.last_window_pairs << 24U);
    s_rotation.quality = quality;
    if (!Rotation_Log(when, FLIGHT_LOG_EVENT_MAG_ROTATION_QUALITY, quality, s_rotation.revision))
    {
        Rotation_Invalidate(MagRotationResult_Stale, when);
        return;
    }
    if (result != MagRotationResult_Candidate && result != MagRotationResult_Accepted)
    {
        /* Revoke the output immediately. A full observable holdout may be
         * inaccurate while a bounded candidate is still being learned. */
        Rotation_FixedSelect(quality, when);
        return;
    }
    s_rotation.estimate = MagRotation_Encode(s_rotation.fit.q);
    if (!Rotation_Log(when, FLIGHT_LOG_EVENT_MAG_ROTATION_ESTIMATE, s_rotation.estimate,
                      s_rotation.revision))
    {
        Rotation_Invalidate(MagRotationResult_Stale, when);
        return;
    }
    if (result == MagRotationResult_Accepted)
    {
        uint32_t packed = Rotation_Compose(s_rotation.fit.q, base_q);
        /* A concurrent maintenance Stop must never enqueue a new adoption
         * after revocation. LoggerBus uses bounded, nonblocking queue writes. */
        PlatformCriticalState lock = PlatformCritical_Enter();
        if (s_rotation.reset_requested || !s_rotation.qualified ||
            !Rotation_Log(when, FLIGHT_LOG_EVENT_MAG_ROTATION_ADOPTED, packed, s_rotation.revision))
        {
            PlatformCritical_Exit(lock);
            Rotation_Invalidate(MagRotationResult_Stale, when);
            return;
        }
        s_rotation.adopted = packed;
        s_rotation.valid = 1U;
        PlatformCritical_Exit(lock);
    }
}

/* MMC5983MA supplies native signed 18-bit counts and a fixed uT/count.
 * A saturated endpoint or a mismatched raw/physical pair cannot support a fit. */
static uint8_t Rotation_RawFieldValid(const SystemMagnetometerSample *sample)
{
    const uint32_t required = SYSTEM_MAG_VALID_RAW | SYSTEM_MAG_VALID_PHYSICAL_UNIT;
    if (sample == NULL || sample->instance_id != 0U || sample->sequence == 0U ||
        (sample->valid_mask & required) != required || sample->calibration_valid != 0U ||
        (sample->valid_mask & SYSTEM_MAG_VALID_CALIBRATED) != 0U)
    {
        return 0U;
    }
    for (uint8_t i = 0U; i < 3U; i++)
    {
        float expected = (float)sample->raw[i] * (100.0f / 16384.0f);
        if (sample->raw[i] <= -131072 || sample->raw[i] >= 131071 ||
            !isfinite(sample->magnetic_field_b_uT[i]) ||
            fabsf(sample->magnetic_field_b_uT[i] - expected) > (50.01f / 16384.0f))
        {
            return 0U;
        }
    }
    return 1U;
}

static uint8_t Rotation_FieldGet(const SystemMagnetometerSample *sample,
                                 SystemMagCalibrationStatus *status, float field[3],
                                 float base_q[4])
{
    SystemMagCalibrationSnapshot snap;
    SystemDeviceDescriptor descriptor;
    float intrinsic[3], m[9] = {1.0f, 0.0f, 0.0f, 0.0f, 1.0f, 0.0f, 0.0f, 0.0f, 1.0f};
    if (SystemMagCalibration_SnapshotGet(sample->instance_id, &snap) !=
            SystemMagCalibrationResult_Ok ||
        !snap.status.active || !snap.status.saved || snap.status.save_pending ||
        snap.status.save_failed || snap.status.instance_id != sample->instance_id ||
        SystemDescriptor_DeviceFind(SYSTEM_DEVICE_CLASS_MAGNETOMETER, sample->instance_id,
                                    &descriptor) != SYSTEM_DEVICE_OK ||
        descriptor.physical_device_id == 0U ||
        snap.status.physical_device_id != descriptor.physical_device_id ||
        (sample->physical_device_id != 0U &&
         sample->physical_device_id != descriptor.physical_device_id) ||
        (sample->descriptor_id != 0U && sample->descriptor_id != descriptor.descriptor_id) ||
        snap.status.generation == 0U ||
        snap.status.configuration_digest != SystemDescriptor_ConfigDigestGet())
    {
        return 0U;
    }
    SystemInstallationActiveResult r = SystemInstallationActive_MagBaseGet(
        sample->instance_id, snap.status.generation, snap.status.intrinsic_crc, m);
    if (r != SystemInstallationActiveResult_NotPresent && r != SystemInstallationActiveResult_Ok)
    {
        return 0U;
    }
    for (uint8_t i = 0U; i < 3U; i++)
    {
        intrinsic[i] = 0.0f;
        for (uint8_t j = 0U; j < 3U; j++)
        {
            intrinsic[i] += snap.matrix[i][j] * (sample->magnetic_field_b_uT[j] - snap.bias[j]);
        }
    }
    for (uint8_t i = 0U; i < 3U; i++)
    {
        field[i] = m[3U * i] * intrinsic[0] + m[3U * i + 1U] * intrinsic[1] +
                   m[3U * i + 2U] * intrinsic[2];
    }
    *status = snap.status;
    Rotation_BaseQuaternion(m, base_q);
    return 1U;
}

static void Rotation_AverageRateGet(uint64_t center, const float at_mid[3], float rate[3])
{
    if (s_rotation.mag_mid_us != 0ULL && center > s_rotation.mag_mid_us)
    {
        float dt = (float)(center - s_rotation.mag_mid_us) * 0.000001f;
        for (uint8_t i = 0U; i < 3U; i++)
        {
            rate[i] = at_mid[i] / dt;
        }
    }
    /* Rebase integral at each accepted magnetic observation to limit float error. */
    for (uint8_t i = 0U; i < 3U; i++)
    {
        s_rotation.angle[i] -= at_mid[i];
        for (uint8_t k = 0U; k < ROTATION_HISTORY_COUNT; k++)
        {
            s_rotation.history[k].angle[i] -= at_mid[i];
        }
    }
}

static void Rotation_ObservationBind(uint64_t center, const SystemMagnetometerSample *sample,
                                     const SystemMagCalibrationStatus *status)
{
    PlatformCriticalState lock = PlatformCritical_Enter();
    s_rotation.mag_mid_us = center;
    s_rotation.mag_us = sample->sample_timestamp_us;
    s_rotation.mag_sequence = sample->sequence;
    s_rotation.mag_crc = status->intrinsic_crc;
    s_rotation.mag_generation = status->generation;
    s_rotation.config = status->configuration_digest;
    s_rotation.mag_physical = status->physical_device_id;
    s_rotation.qualified = 1U;
    s_rotation.initialized = 1U;
    PlatformCritical_Exit(lock);
}

void SystemMagRotation_MagObserve(const SystemMagnetometerSample *sample, uint64_t trigger,
                                  uint64_t available)
{
    SystemMagCalibrationStatus status;
    float field[3], base_q[4], at_mid[3], rate[3] = {0.0f, 0.0f, 0.0f};
    if (!Rotation_RawFieldValid(sample) || trigger == 0ULL ||
        sample->sample_timestamp_us <= trigger ||
        sample->sample_timestamp_us - trigger > ROTATION_MAX_CONVERSION_US ||
        available < sample->sample_timestamp_us ||
        available - sample->sample_timestamp_us > 30000ULL ||
        !Rotation_FieldGet(sample, &status, field, base_q))
    {
        Rotation_Invalidate(MagRotationResult_WrongSource, available);
        return;
    }
    uint64_t center = trigger + (sample->sample_timestamp_us - trigger) / 2ULL;
    uint32_t base = MagRotation_Encode(base_q);
    if (!Rotation_AngleGet(center, at_mid))
    {
        Rotation_Invalidate(MagRotationResult_Stale, available);
        return;
    }
    if (!s_rotation.initialized || s_rotation.mag_generation != status.generation ||
        s_rotation.mag_crc != status.intrinsic_crc ||
        s_rotation.config != status.configuration_digest ||
        s_rotation.mag_physical != status.physical_device_id ||
        (s_rotation.mag_sequence != 0U && sample->sequence != s_rotation.mag_sequence + 1U) ||
        s_rotation.base != base)
    {
        Rotation_Invalidate(MagRotationResult_WrongSource, available);
        s_rotation.base_known = 0U;
    }
    if (!s_rotation.base_known)
    {
        if (!Rotation_Log(available, FLIGHT_LOG_EVENT_MAG_ROTATION_BASE, base, s_rotation.revision))
        {
            return;
        }
        s_rotation.base_known = 1U;
        s_rotation.base = base;
    }
    Rotation_AverageRateGet(center, at_mid, rate);
    Rotation_ObservationBind(center, sample, &status);
    MagRotationResult result = MagRotation_Step(&s_rotation.fit, center, field, rate);
    Rotation_Publish(result, base_q, available);
}

uint8_t SystemMagRotation_ProviderQualified(float r[9])
{
    if (r == NULL)
    {
        return 0U;
    }
    uint64_t now = PlatformTime_Us();
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t valid =
        (uint8_t)(s_rotation.qualified != 0U && !s_rotation.reset_requested &&
                  s_rotation.imu_physical != 0U && s_rotation.mag_physical != 0U &&
                  now >= s_rotation.edge_us &&
                  now - s_rotation.edge_us <= ROTATION_MAX_EDGE_GAP_US &&
                  now >= s_rotation.mag_us && now - s_rotation.mag_us <= ROTATION_FRESH_US);
    PlatformCritical_Exit(lock);
    if (valid)
    {
        for (uint8_t i = 0U; i < 9U; i++)
        {
            r[i] = (i % 4U) == 0U ? 1.0f : 0.0f;
        }
    }
    return valid;
}

uint8_t SystemMagRotation_TryApply(uint8_t instance, uint32_t generation, uint32_t crc,
                                   uint32_t sequence, uint64_t sample_us, float field[3])
{
    if (field == NULL || instance != 0U)
    {
        return 0U;
    }
    uint64_t now = PlatformTime_Us();
    uint32_t current_generation = SystemCalibration_GenerationGet();
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint32_t packed = s_rotation.adopted;
    uint8_t valid =
        (uint8_t)(s_rotation.valid && s_rotation.qualified && !s_rotation.reset_requested &&
                  generation == s_rotation.mag_generation && crc == s_rotation.mag_crc &&
                  current_generation == s_rotation.imu_generation &&
                  sequence == s_rotation.mag_sequence && sample_us == s_rotation.mag_us &&
                  now >= sample_us && now - sample_us <= ROTATION_FRESH_US &&
                  now >= s_rotation.edge_us &&
                  now - s_rotation.edge_us <= ROTATION_MAX_EDGE_GAP_US);
    PlatformCritical_Exit(lock);
    if (valid)
    {
        float q[4];
        MagRotation_Decode(packed, q);
        MagRotation_VectorRotate(q, field, field);
    }
    return valid;
}

void SystemMagRotation_Service(uint64_t now_us)
{
    Rotation_FallbackFlush(now_us);
    PlatformCriticalState lock = PlatformCritical_Enter();
    uint8_t reset = s_rotation.reset_requested;
    uint8_t stale =
        (uint8_t)(s_rotation.qualified &&
                  (now_us < s_rotation.edge_us ||
                   now_us - s_rotation.edge_us > ROTATION_MAX_EDGE_GAP_US ||
                   now_us < s_rotation.mag_us || now_us - s_rotation.mag_us > ROTATION_FRESH_US));
    PlatformCritical_Exit(lock);
    if (reset || stale)
    {
        Rotation_ResetOwner();
    }
}

void SystemMagRotation_StatusWrite(char *response, uint16_t capacity)
{
    uint32_t base, estimate, adopted, revision, quality, failures, epoch, generation;
    uint8_t valid, qualified;
    if (response == NULL || capacity == 0U)
    {
        return;
    }
    PlatformCriticalState lock = PlatformCritical_Enter();
    base = s_rotation.base;
    estimate = s_rotation.estimate;
    valid = s_rotation.valid;
    qualified = (uint8_t)(s_rotation.qualified && !s_rotation.reset_requested);
    adopted = valid && qualified ? s_rotation.adopted : base;
    revision = s_rotation.revision;
    quality = s_rotation.quality;
    failures = s_rotation.log_failures;
    epoch = s_rotation.epoch;
    generation = s_rotation.mag_generation;
    PlatformCritical_Exit(lock);
    (void)CommonFormat_Print(
        response, capacity,
        "OK MAG 0 ROT enabled=1 qualified=%u valid=%u rev=%lu quality=%lu base=%lu estimate=%lu "
        "used=%lu imu_epoch=%lu mag_gen=%lu log_fail=%lu",
        (unsigned int)qualified, (unsigned int)(valid && qualified), (unsigned long)revision,
        (unsigned long)quality, (unsigned long)base, (unsigned long)estimate,
        (unsigned long)adopted, (unsigned long)epoch, (unsigned long)generation,
        (unsigned long)failures);
}
