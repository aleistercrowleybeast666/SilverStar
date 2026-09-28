#include "system_version.h"
#include "system_barometer_if.h"

#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "jy901b_barometer_build_capabilities.h"
#include "jy901b_instance.h"
#include "jy901b_sensor_adapter.h"
#include "silverstar_assert.h"
#include "system_user_config.h"

static SystemBarometerConfig
    s_effective_configs[PROJECT_JY901B_INSTANCE_COUNT];

#define s_effective_config (s_effective_configs[instance])

static SystemDeviceResult Jy901bBarometerAdapter_GetHealth(uint8_t instance,
    SystemDeviceHealth *health)
{
    (void)instance;
    return Jy901bAdapter_FrameHealthGet(instance, IMUFramePressureHeight, health);
}

static SystemDeviceResult Jy901bBarometerAdapter_Init(uint8_t instance)
{
    (void)instance;
    return Jy901bAdapter_SharedInit(instance);
}

static SystemDeviceResult Jy901bBarometerAdapter_Start(uint8_t instance)
{
    (void)instance;
    SystemDeviceResult result = Jy901bAdapter_SharedStart(instance);

    return (result == SYSTEM_DEVICE_ALREADY_MATCHED) ? SYSTEM_DEVICE_OK : result;
}

static SystemDeviceResult Jy901bBarometerAdapter_Stop(uint8_t instance)
{
    (void)instance;
    return SYSTEM_DEVICE_OK;
}

static void Jy901bBarometerAdapter_Process(uint8_t instance)
{
    (void)instance;
}

static SystemDeviceResult Jy901bBarometerAdapter_GetInfo(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "JY901B Barometer Adapter";
    info->model_name = "JY901B";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_BARO_VALID_PRESSURE |
                            SYSTEM_BARO_VALID_ALTITUDE;
    info->configuration_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bBarometerAdapter_GetCapabilities(uint8_t instance, uint32_t *mask)
{
    (void)instance;
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_BARO_VALID_PRESSURE |
            SYSTEM_BARO_VALID_ALTITUDE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bBarometerAdapter_GetSample(uint8_t instance,
    SystemBarometerSample *sample)
{
    (void)instance;
    IMUData data;
    SystemDeviceResult result;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemBarometerSample,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Jy901bAdapter_SharedSnapshotGet(instance, &data);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if ((data.ValidMask & (1U << 4)) == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = data.PressureTimestampUs;
    sample->receive_timestamp_us = data.PressureTimestampUs;
    sample->sequence = data.PressureFrameCount;
    sample->pressure_raw_pa = data.PressureRawPa;
    sample->altitude_raw_cm = data.HeightRawCm;
    sample->pressure_pa = data.PressurePa;
    sample->altitude_m = data.HeightCm * 0.01f;
    /* The packet has no native uncertainty estimate. Recommendation is advisory. */
    sample->altitude_variance_m2 = 0.0f;
    sample->supported_fields = SYSTEM_BARO_FIELD_PRESSURE |
                               SYSTEM_BARO_FIELD_ALTITUDE;
    sample->valid_fields = sample->supported_fields;
    sample->valid_mask = sample->valid_fields;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bBarometerAdapter_SelfTest(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance;
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Jy901bBarometerAdapter_ConfigCheck(uint8_t instance,
    const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemBarometerConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->unsupported_required_mask = config->required_mask &
                                        ~SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->unsupported_optional_mask = (config->requested_mask &
                                         ~SYSTEM_BARO_CFG_OUTPUT_RATE) &
                                        ~config->required_mask;
    if ((report->unsupported_required_mask != 0U) ||
        (((config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE) != 0U) &&
         (config->output_rate_hz != SYSTEM_IMU_OUTPUT_RATE_HZ)))
    {
        report->verify_failed_mask = config->requested_mask;
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->matched_mask = config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE;
    report->success = 1U;
    return (report->unsupported_optional_mask != 0U) ?
        SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bBarometerAdapter_ApplyConfig(uint8_t instance,
    const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    SystemDeviceResult result = Jy901bBarometerAdapter_ConfigCheck(instance, config, report);

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    { return result; }
    s_effective_config = *config;
    report->delegated_mask = report->matched_mask;
    report->applied_mask = 0U;
    report->matched_mask = 0U;
    return (report->delegated_mask != 0U) ?
        SYSTEM_DEVICE_CONFIG_DELEGATED : result;
}

static SystemDeviceResult Jy901bBarometerAdapter_VerifyConfig(uint8_t instance,
    const SystemBarometerConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    uint16_t value;
    IMUOutputRate expected_rate;
    IMUState state;
    SystemDeviceResult result =
        Jy901bBarometerAdapter_ConfigCheck(instance, config, report);

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    { return result; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemBarometerConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((config->requested_mask & SYSTEM_BARO_CFG_OUTPUT_RATE) == 0U)
    { return result; }
    if (Jy901bAdapter_ConfigAccessCheck(instance) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_BUSY; }
    if (Jy901bAdapter_OutputRateValueGet(config->output_rate_hz,
                                          &expected_rate) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    state = IMU_ReadOutputRate(instance, &value);
    if ((state != IMU_OK) || (value != (uint16_t)expected_rate))
    {
        report->matched_mask = 0U;
        report->verify_failed_mask = SYSTEM_BARO_CFG_OUTPUT_RATE;
        report->failed_mask = report->verify_failed_mask;
        report->detail_code = (state != IMU_OK) ? (uint32_t)state : value;
        report->success = 0U;
        return (state == IMU_RESP_TIMEOUT) ? SYSTEM_DEVICE_TIMEOUT :
                                             SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return result;
}

static SystemDeviceResult Jy901bBarometerAdapter_GetConfig(uint8_t instance,
    SystemBarometerConfig *config)
{
    (void)instance;
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *config = s_effective_config;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bBarometerAdapter_GetNoise(uint8_t instance,
    SystemBarometerNoiseCharacteristics *noise)
{
    (void)instance;
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    noise->recommended_altitude_std_m =
        JY901B_BAROMETER_RECOMMENDED_ALTITUDE_STD_M;
    noise->pressure_noise_std_pa = 0.0f;
    noise->valid_mask = SYSTEM_BAROMETER_NOISE_VALID_ALTITUDE_STD;
    return SYSTEM_DEVICE_OK;
}

const char *Jy901bBarometerInstance_NameGet(uint8_t instance) {
    (void)instance; return "JY901B Barometer"; }
SystemDeviceResult Jy901bBarometerInstance_Init(uint8_t instance)
{
    (void)instance; return Jy901bBarometerAdapter_Init(instance); }
SystemDeviceResult Jy901bBarometerInstance_Start(uint8_t instance)
{
    (void)instance; return Jy901bBarometerAdapter_Start(instance); }
SystemDeviceResult Jy901bBarometerInstance_Stop(uint8_t instance)
{
    (void)instance; return Jy901bBarometerAdapter_Stop(instance); }
void Jy901bBarometerInstance_Process(uint8_t instance) {
    (void)instance; Jy901bBarometerAdapter_Process(instance); }
SystemDeviceResult Jy901bBarometerInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance; return Jy901bBarometerAdapter_GetInfo(instance, info); }
SystemDeviceResult Jy901bBarometerInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    (void)instance; return Jy901bBarometerAdapter_GetCapabilities(instance, mask); }
SystemDeviceResult Jy901bBarometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    (void)instance; return Jy901bBarometerAdapter_GetHealth(instance, health); }
SystemDeviceResult Jy901bBarometerInstance_LatestSampleGet(uint8_t instance,
    SystemBarometerSample *sample)
{
    (void)instance; return Jy901bBarometerAdapter_GetSample(instance, sample); }
SystemDeviceResult Jy901bBarometerInstance_SelfTestRun(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance; return Jy901bBarometerAdapter_SelfTest(instance, result); }
SystemDeviceResult Jy901bBarometerInstance_ConfigApply(uint8_t instance,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    (void)instance; return Jy901bBarometerAdapter_ApplyConfig(instance, config, report); }
SystemDeviceResult Jy901bBarometerInstance_ConfigVerify(uint8_t instance,
    const SystemBarometerConfig *config, SystemDeviceConfigReport *report)
{
    (void)instance; return Jy901bBarometerAdapter_VerifyConfig(instance, config, report); }
SystemDeviceResult Jy901bBarometerInstance_EffectiveConfigGet(uint8_t instance,
    SystemBarometerConfig *config)
{
    (void)instance; return Jy901bBarometerAdapter_GetConfig(instance, config); }
SystemDeviceResult Jy901bBarometerInstance_NoiseCharacteristicsGet(uint8_t instance,
    SystemBarometerNoiseCharacteristics *noise)
{
    (void)instance; return Jy901bBarometerAdapter_GetNoise(instance, noise); }
