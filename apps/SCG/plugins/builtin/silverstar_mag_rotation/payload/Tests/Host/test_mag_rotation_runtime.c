/* Real estimator and runtime, with a simulated stationary ambient magnetic
 * field, timestamped 400 Hz gyro and actual calibration/log port contracts. */
#include "mag_rotation.h"
#include "system_mag_rotation_if.h"
#include "system_installation_active_if.h"
#include "system_descriptor_if.h"
#include "system_calibration.h"
#include "system_mag_calibration.h"
#include "system_source_selector.h"
#include "logger_bus.h"
#include "common_format.h"
#include <stdarg.h>
#include "platform_critical.h"
#include "platform_time.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint64_t s_now;
static uint32_t s_epoch = 1U, s_cal_generation = 9U, s_last_packed, s_log_revision;
static unsigned s_adopted, s_fallback, s_locked;
static unsigned s_denied_adoptions;
static uint8_t s_deny_log, s_selected, s_deny_adoption;
static const float s_bias[3] = {3.0f, -2.0f, 1.0f};
static const float s_scale[3] = {1.1f, 0.9f, 1.05f};

int32_t CommonFormat_Print(char *text, size_t capacity, const char *format, ...)
{
    va_list arguments;
    va_start(arguments, format);
    int result = vsnprintf(text, capacity, format, arguments);
    va_end(arguments);
    return (int32_t)result;
}
uint64_t PlatformTime_Us(void)
{
    return s_now;
}
PlatformCriticalState PlatformCritical_Enter(void)
{
    return s_locked++;
}
void PlatformCritical_Exit(PlatformCriticalState state)
{
    assert(s_locked == state + 1U);
    s_locked = state;
}
uint32_t SystemCalibration_GenerationGet(void)
{
    return s_cal_generation;
}
uint32_t SystemDescriptor_ConfigDigestGet(void)
{
    return 22U;
}
SystemDeviceResult SystemSourceSelector_ImuActiveInstanceGet(uint8_t *instance)
{
    *instance = s_selected;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemDescriptor_DeviceFind(SystemDeviceClass kind, uint8_t instance,
                                               SystemDeviceDescriptor *d)
{
    assert((kind == SYSTEM_DEVICE_CLASS_IMU || kind == SYSTEM_DEVICE_CLASS_MAGNETOMETER) &&
           instance == 0U);
    (void)memset(d, 0, sizeof(*d));
    d->physical_device_id = kind == SYSTEM_DEVICE_CLASS_IMU ? 11U : 42U;
    d->descriptor_id = 23U;
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult SystemCalibration_ImuCorrectionGet(SystemCalibrationImuCorrection *c)
{
    (void)memset(c, 0, sizeof(*c));
    c->ready = 1U;
    for (unsigned i = 0U; i < 3U; i++)
    {
        c->gyro_scale[i] = 1.0f;
    }
    return SYSTEM_DEVICE_OK;
}
SystemMagCalibrationResult SystemMagCalibration_SnapshotGet(uint8_t instance,
                                                            SystemMagCalibrationSnapshot *s)
{
    assert(instance == 0U);
    (void)memset(s, 0, sizeof(*s));
    s->status.active = 1U;
    s->status.saved = 1U;
    s->status.generation = 7U;
    s->status.intrinsic_crc = 19U;
    s->status.physical_device_id = 42U;
    s->status.configuration_digest = 22U;
    for (unsigned i = 0U; i < 3U; i++)
    {
        s->bias[i] = s_bias[i];
        s->matrix[i][i] = s_scale[i];
    }
    return SystemMagCalibrationResult_Ok;
}
LoggerBusResult LoggerBus_RotationEventPush(uint64_t time, FlightLogEventId event, uint32_t arg0,
                                            uint32_t arg1)
{
    assert(time <= s_now);
    if (s_deny_log)
    {
        return LOGGER_BUS_RESULT_FULL;
    }
    if (event == FLIGHT_LOG_EVENT_MAG_ROTATION_ADOPTED)
    {
        if (s_deny_adoption != 0U)
        {
            s_denied_adoptions++;
            return LOGGER_BUS_RESULT_FULL;
        }
        s_last_packed = arg0;
        s_adopted++;
        s_log_revision = arg1;
    }
    if (event == FLIGHT_LOG_EVENT_MAG_ROTATION_FIXED)
    {
        s_fallback++;
        s_last_packed = arg0;
    }
    return LOGGER_BUS_RESULT_OK;
}
#if (SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U)
SystemInstallationActiveResult
SystemInstallationActive_MagBaseGet(uint8_t instance, uint32_t generation, uint32_t crc, float m[9])
{
    assert(instance == 0U && generation == 7U && crc == 19U);
    const float fixed[9] = {0.0f, -1.0f, 0.0f, 1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f};
    (void)memcpy(m, fixed, sizeof(fixed));
    return SystemInstallationActiveResult_Ok;
}
#endif
static void Rotate(const float w[3], float dt, float field[3])
{
    float n = sqrtf(w[0] * w[0] + w[1] * w[1] + w[2] * w[2]);
    float q[4] = {cosf(dt * n * 0.5f), 0.0f, 0.0f, 0.0f};
    if (n > 0.0f)
    {
        for (unsigned i = 0U; i < 3U; i++)
        {
            q[i + 1U] = sinf(dt * n * 0.5f) * w[i] / n;
        }
    }
    MagRotation_VectorRotate(q, field, field);
}
static void Frame(unsigned i, const float history[3], SystemMagnetometerSample *sample,
                  float intrinsic[3])
{
    const float delta[3] = {0.0f, -0.37f, 0.0f};
    (void)memcpy(intrinsic, history, 3U * sizeof(float));
    Rotate(delta, 1.0f, intrinsic);
#if (SYSTEM_INSTALLATION_CAPTURE_ENABLED != 0U)
    const float fixed_inverse[3] = {0.0f, 0.0f, -1.5707963268f};
    Rotate(fixed_inverse, 1.0f, intrinsic);
#endif
    (void)memset(sample, 0, sizeof(*sample));
    sample->sequence = i / 20U;
    sample->instance_id = 0U;
    sample->sample_timestamp_us = s_now - 2500ULL;
    sample->valid_mask = SYSTEM_MAG_VALID_RAW | SYSTEM_MAG_VALID_PHYSICAL_UNIT;
    for (unsigned k = 0U; k < 3U; k++)
    {
        sample->magnetic_field_b_uT[k] = intrinsic[k] / s_scale[k] + s_bias[k];
        sample->raw[k] = (int32_t)lroundf(sample->magnetic_field_b_uT[k] * (16384.0f / 100.0f));
    }
}
int main(int argc, char *argv[])
{
    float field[3] = {24.0f, -17.0f, 37.0f}, history[3][3] = {{0}}, intrinsic[3], axes[9];
    SystemMagnetometerSample sample;
    unsigned applied = 0U;
    s_deny_adoption = (uint8_t)(argc == 2 && strcmp(argv[1], "adoption-full") == 0);
    for (unsigned i = 1U; i <= 16000U; i++)
    {
        s_now = 1000000ULL + 2500ULL * i;
        float t = (float)i * 0.0025f;
        float w[3] = {1.3f * sinf(t * 2.1f), 1.0f * cosf(t * 2.9f), 1.4f * cosf(t * 1.3f)};
        Rotate(w, -0.0025f, field);
        (void)memcpy(history[i % 3U], field, sizeof(field));
        SystemMagRotation_ImuObserve(0U, s_epoch, i, i, s_now, w, 1U);
        if (i % 20U != 0U)
        {
            continue;
        }
        Frame(i, history[(i - 2U) % 3U], &sample, intrinsic);
        SystemMagRotation_MagObserve(&sample, s_now - 7500ULL, s_now);
        if (SystemMagRotation_TryApply(0U, 7U, 19U, sample.sequence, sample.sample_timestamp_us,
                                       intrinsic))
        {
            float expected[3];
            Frame(i, history[(i - 2U) % 3U], &sample, expected);
            float q[4];
            MagRotation_Decode(s_last_packed, q);
            MagRotation_VectorRotate(q, expected, expected);
            for (unsigned k = 0U; k < 3U; k++)
            {
                assert(fabsf(intrinsic[k] - expected[k]) < 0.0002f);
                assert(fabsf(intrinsic[k] - history[(i - 2U) % 3U][k]) < 0.5f);
            }
            applied++;
        }
        assert(!SystemMagRotation_TryApply(0U, 7U, 20U, sample.sequence, sample.sample_timestamp_us,
                                           intrinsic));
    }
    if (s_deny_adoption != 0U)
    {
        assert(s_denied_adoptions > 0U && s_adopted == 0U && applied == 0U);
        assert(!SystemMagRotation_TryApply(0U, 7U, 19U, sample.sequence,
                                           sample.sample_timestamp_us, intrinsic));
        puts("PASS full adoption queue never publishes an unrecorded rotation");
        return 0;
    }
    assert(s_adopted > 0U && applied > 0U && s_log_revision > 0U &&
           SystemMagRotation_ProviderQualified(axes));
    if (argc == 2 && strcmp(argv[1], "stop") == 0)
    {
        float unchanged[3];
        (void)memcpy(unchanged, intrinsic, sizeof(unchanged));
        SystemMagRotation_SourceLost();
        assert(!SystemMagRotation_ProviderQualified(axes));
        assert(!SystemMagRotation_TryApply(0U, 7U, 19U, sample.sequence,
                                           sample.sample_timestamp_us, intrinsic));
        assert(memcmp(unchanged, intrinsic, sizeof(unchanged)) == 0 && s_locked == 0U);
        puts("PASS maintenance Stop revokes before DeviceTask service without output mutation");
    }
    /* Loss of logging cannot hold the old accepted rotation active. On
     * recovery the queued FIXED/QUALITY retain the time and revision. */
    s_deny_log = 1U;
    s_now += 200000ULL;
    SystemMagRotation_Service(s_now);
    assert(!SystemMagRotation_TryApply(0U, 7U, 19U, sample.sequence, sample.sample_timestamp_us,
                                       intrinsic));
    assert(!SystemMagRotation_ProviderQualified(axes));
    unsigned previous_fallback = s_fallback;
    s_deny_log = 0U;
    s_now += 100001ULL;
    SystemMagRotation_Service(s_now);
    assert(s_fallback == previous_fallback + 1U);
    s_selected = 1U;
    SystemMagRotation_ImuObserve(0U, 1U, 16001U, 16001U, s_now, intrinsic, 1U);
    assert(!SystemMagRotation_ProviderQualified(axes));
    s_selected = 0U;
    s_deny_log = 1U;
    char status[192];
    SystemMagRotation_StatusWrite(status, sizeof(status));
    assert(strstr(status, "valid=0") != NULL);
    printf("time series gyro/mag, calibrated input, recorded=used, interruption, wrong source PASS "
           "adopted=%u applied=%u\n",
           s_adopted, applied);
    return 0;
}
