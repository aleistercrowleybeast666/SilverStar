#include "system_version.h"
#include "system_magnetometer_if.h"

#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "jy901b_instance.h"
#include "jy901b_sensor_adapter.h"
#include "jy901b_magnetometer_config.h"
#include "silverstar_assert.h"
#include "system_user_config.h"

#define JY901B_MAG_MGAUSS_PER_LSB 0.0667f
#define JY901B_MAG_UT_PER_LSB     0.00667f

static SystemMagnetometerConfig
    s_effective_configs[PROJECT_JY901B_INSTANCE_COUNT];

#define s_effective_config (s_effective_configs[instance])

static SystemDeviceResult Jy901bMagnetometerAdapter_GetHealth(uint8_t instance,
    SystemDeviceHealth *health)
{
    (void)instance;
    return Jy901bAdapter_FrameHealthGet(instance, IMUFrameMag, health);
}

static SystemDeviceResult Jy901bMagnetometerAdapter_Init(uint8_t instance)
{
    (void)instance;
    return Jy901bAdapter_SharedInit(instance);
}

static SystemDeviceResult Jy901bMagnetometerAdapter_Start(uint8_t instance)
{
    (void)instance;
    SystemDeviceResult result = Jy901bAdapter_SharedStart(instance);

    return (result == SYSTEM_DEVICE_ALREADY_MATCHED) ? SYSTEM_DEVICE_OK : result;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_Stop(uint8_t instance)
{
    (void)instance;
    return SYSTEM_DEVICE_OK;
}

static void Jy901bMagnetometerAdapter_Process(uint8_t instance)
{
    (void)instance;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_GetInfo(uint8_t instance,
    SystemDeviceInfo *info)
{
    (void)instance;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "JY901B Magnetometer Adapter";
    info->model_name = "JY901B";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_MAG_CAP_RAW_OUTPUT |
                             SYSTEM_MAG_CAP_PHYSICAL_UNIT |
                             SYSTEM_MAG_CAP_TEMPERATURE |
                             SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE;
    info->configuration_mask = SYSTEM_MAG_CFG_OUTPUT_RATE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_GetCapabilities(uint8_t instance,
    uint32_t *mask)
{
    (void)instance;
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_MAG_CAP_RAW_OUTPUT |
            SYSTEM_MAG_CAP_PHYSICAL_UNIT |
            SYSTEM_MAG_CAP_TEMPERATURE |
            SYSTEM_MAG_CAP_CONFIG_OUTPUT_RATE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_GetSample(uint8_t instance,
    SystemMagnetometerSample *sample)
{
    (void)instance;
    IMUData data;
    SystemDeviceResult result;
    uint8_t index;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemMagnetometerSample,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Jy901bAdapter_SharedSnapshotGet(instance, &data);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if ((data.ValidMask & (1U << 3)) == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = data.MagTimestampUs;
    sample->receive_timestamp_us = data.MagTimestampUs;
    sample->sequence = data.MagFrameCount;
    for (index = 0U; index < 3U; index++)
    {
        sample->raw[index] = data.MagRaw[index];
        sample->magnetic_field_b_uT[index] =
            (float)data.MagRaw[index] * JY901B_MAG_UT_PER_LSB;
    }
    sample->temperature_c = data.TemperatureC;
    sample->valid_mask = SYSTEM_MAG_VALID_RAW |
                         SYSTEM_MAG_VALID_PHYSICAL_UNIT |
                         SYSTEM_MAG_VALID_TEMPERATURE;
    sample->calibration_valid =
        (uint8_t)(JY901B_MAGNETOMETER_CALIBRATION_VALID != 0U);
    if (sample->calibration_valid != 0U)
    {
        sample->valid_mask |= SYSTEM_MAG_VALID_CALIBRATED;
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_SelfTest(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance;
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_ConfigCheck(uint8_t instance,
    const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemMagnetometerConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = SYSTEM_MAG_CFG_OUTPUT_RATE;
    report->unsupported_required_mask = config->required_mask &
                                        ~SYSTEM_MAG_CFG_OUTPUT_RATE;
    report->unsupported_optional_mask = (config->requested_mask &
                                         ~SYSTEM_MAG_CFG_OUTPUT_RATE) &
                                        ~config->required_mask;
    if ((report->unsupported_required_mask != 0U) ||
        (((config->requested_mask & SYSTEM_MAG_CFG_OUTPUT_RATE) != 0U) &&
         (config->output_rate_hz != SYSTEM_IMU_OUTPUT_RATE_HZ)))
    {
        report->verify_failed_mask = config->requested_mask;
        report->failed_mask = config->requested_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->matched_mask = config->requested_mask & SYSTEM_MAG_CFG_OUTPUT_RATE;
    report->success = 1U;
    return (report->unsupported_optional_mask != 0U) ?
        SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_ApplyConfig(uint8_t instance,
    const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    SystemDeviceResult result =
        Jy901bMagnetometerAdapter_ConfigCheck(instance, config, report);

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    {
        return result;
    }
    s_effective_config = *config;
    report->delegated_mask = report->matched_mask;
    report->applied_mask = 0U;
    report->matched_mask = 0U;
    return (report->delegated_mask != 0U) ?
        SYSTEM_DEVICE_CONFIG_DELEGATED : result;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_VerifyConfig(uint8_t instance,
    const SystemMagnetometerConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    uint16_t value;
    IMUOutputRate expected_rate;
    IMUState state;
    SystemDeviceResult result =
        Jy901bMagnetometerAdapter_ConfigCheck(instance, config, report);

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    { return result; }
    SILVERSTAR_ASSERT_OBJECT(config, SystemMagnetometerConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((config->requested_mask & SYSTEM_MAG_CFG_OUTPUT_RATE) == 0U)
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
        report->verify_failed_mask = SYSTEM_MAG_CFG_OUTPUT_RATE;
        report->failed_mask = report->verify_failed_mask;
        report->detail_code = (state != IMU_OK) ? (uint32_t)state : value;
        report->success = 0U;
        return (state == IMU_RESP_TIMEOUT) ? SYSTEM_DEVICE_TIMEOUT :
                                             SYSTEM_DEVICE_VERIFY_FAILED;
    }
    return result;
}

static SystemDeviceResult Jy901bMagnetometerAdapter_GetConfig(uint8_t instance,
    SystemMagnetometerConfig *config)
{
    (void)instance;
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *config = s_effective_config;
    return SYSTEM_DEVICE_OK;
}

const char *Jy901bMagnetometerInstance_NameGet(uint8_t instance) {
    (void)instance; return "JY901B Magnetometer"; }
SystemDeviceResult Jy901bMagnetometerInstance_Init(uint8_t instance)
{
    (void)instance; return Jy901bMagnetometerAdapter_Init(instance); }
SystemDeviceResult Jy901bMagnetometerInstance_Start(uint8_t instance)
{
    (void)instance; return Jy901bMagnetometerAdapter_Start(instance); }
SystemDeviceResult Jy901bMagnetometerInstance_Stop(uint8_t instance)
{
    (void)instance; return Jy901bMagnetometerAdapter_Stop(instance); }
void Jy901bMagnetometerInstance_Process(uint8_t instance) {
    (void)instance; Jy901bMagnetometerAdapter_Process(instance); }
SystemDeviceResult Jy901bMagnetometerInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance; return Jy901bMagnetometerAdapter_GetInfo(instance, info); }
SystemDeviceResult Jy901bMagnetometerInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    (void)instance; return Jy901bMagnetometerAdapter_GetCapabilities(instance, mask); }
SystemDeviceResult Jy901bMagnetometerInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    (void)instance; return Jy901bMagnetometerAdapter_GetHealth(instance, health); }
SystemDeviceResult Jy901bMagnetometerInstance_LatestSampleGet(uint8_t instance,
    SystemMagnetometerSample *sample)
{
    (void)instance; return Jy901bMagnetometerAdapter_GetSample(instance, sample); }
SystemDeviceResult Jy901bMagnetometerInstance_SelfTestRun(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance; return Jy901bMagnetometerAdapter_SelfTest(instance, result); }
SystemDeviceResult Jy901bMagnetometerInstance_ConfigApply(uint8_t instance,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    (void)instance; return Jy901bMagnetometerAdapter_ApplyConfig(instance, config, report); }
SystemDeviceResult Jy901bMagnetometerInstance_ConfigVerify(uint8_t instance,
    const SystemMagnetometerConfig *config, SystemDeviceConfigReport *report)
{
    (void)instance; return Jy901bMagnetometerAdapter_VerifyConfig(instance, config, report); }
SystemDeviceResult Jy901bMagnetometerInstance_EffectiveConfigGet(uint8_t instance,
    SystemMagnetometerConfig *config)
{
    (void)instance; return Jy901bMagnetometerAdapter_GetConfig(instance, config); }
