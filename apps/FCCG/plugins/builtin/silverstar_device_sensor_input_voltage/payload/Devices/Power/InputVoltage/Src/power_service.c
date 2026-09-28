#include "system_version.h"
#include "system_power_if.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "adc_power_config.h"
#include "project_resources.h"
#include "platform_adc.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "silverstar_assert.h"

static volatile uint8_t s_initialized;
static volatile uint8_t s_started;
static uint64_t s_last_attempt_us;
static SystemPowerSample s_sample;
static SystemDeviceHealth s_health;
static SystemPowerConfig s_effective_config =
{
    .requested_mask = SYSTEM_POWER_CFG_VOLTAGE_SCALE |
                      SYSTEM_POWER_CFG_VOLTAGE_OFFSET,
    .required_mask = SYSTEM_POWER_CFG_VOLTAGE_SCALE,
    .voltage_scale = ADC_POWER_DEFAULT_SCALE,
    .voltage_offset_v = ADC_POWER_DEFAULT_OFFSET_V,
    .current_scale = 0.0f,
    .current_offset_a = 0.0f
};

static uint32_t SilverStarPowerService_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void SilverStarPowerService_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

static SystemDeviceResult SilverStarPowerService_ConfigCheck(
    const SystemPowerConfig *config,
    SystemDeviceConfigReport *report,
    uint8_t apply)
{
    const uint32_t supported_mask = SYSTEM_POWER_CFG_VOLTAGE_SCALE |
                                    SYSTEM_POWER_CFG_VOLTAGE_OFFSET;
    SystemPowerConfig effective_config;
    uint32_t primask;
    uint32_t unsupported_mask;

    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemPowerConfig,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = supported_mask;
    unsupported_mask = config->requested_mask & ~supported_mask;
    report->unsupported_required_mask = unsupported_mask &
                                        config->required_mask;
    report->unsupported_optional_mask = unsupported_mask &
                                        ~config->required_mask;
    if ((report->unsupported_required_mask != 0U) ||
        (((config->requested_mask & SYSTEM_POWER_CFG_VOLTAGE_SCALE) != 0U) &&
         ((!isfinite(config->voltage_scale)) ||
          (config->voltage_scale <= 0.0f))) ||
        (((config->requested_mask & SYSTEM_POWER_CFG_VOLTAGE_OFFSET) != 0U) &&
         (!isfinite(config->voltage_offset_v))))
    {
        report->verify_failed_mask = config->requested_mask & supported_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }

    report->applied_mask = config->requested_mask & supported_mask;
    report->matched_mask = report->applied_mask;
    report->success = 1U;
    if (apply != 0U)
    {
        primask = SilverStarPowerService_IrqLock();
        effective_config = s_effective_config;
        SilverStarPowerService_IrqUnlock(primask);
        if ((config->requested_mask & SYSTEM_POWER_CFG_VOLTAGE_SCALE) != 0U)
        {
            effective_config.voltage_scale = config->voltage_scale;
        }
        if ((config->requested_mask & SYSTEM_POWER_CFG_VOLTAGE_OFFSET) != 0U)
        {
            effective_config.voltage_offset_v = config->voltage_offset_v;
        }
        effective_config.requested_mask = report->applied_mask;
        effective_config.required_mask = config->required_mask & supported_mask;
        primask = SilverStarPowerService_IrqLock();
        s_effective_config = effective_config;
        SilverStarPowerService_IrqUnlock(primask);
    }
    return (report->unsupported_optional_mask != 0U) ?
        SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK;
}

static void SilverStarPowerService_ErrorRecord(SystemDeviceResult result)
{
    uint32_t primask = SilverStarPowerService_IrqLock();

    s_health.error_count++;
    if (result == SYSTEM_DEVICE_TIMEOUT)
    {
        s_health.timeout_count++;
    }
    s_health.online = 0U;
    s_health.healthy = 0U;
    SilverStarPowerService_IrqUnlock(primask);
}

static SystemDeviceResult SilverStarPowerService_Init(void)
{
    uint32_t primask;

    if (s_initialized != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    primask = SilverStarPowerService_IrqLock();
    (void)memset(&s_sample, 0, sizeof(s_sample));
    (void)memset(&s_health, 0, sizeof(s_health));
    s_initialized = 1U;
    s_health.initialized = 1U;
    s_health.healthy = 1U;
    SilverStarPowerService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarPowerService_Start(void)
{
    uint32_t primask;

    if (s_initialized == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (s_started != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    primask = SilverStarPowerService_IrqLock();
    s_started = 1U;
    s_health.started = 1U;
    SilverStarPowerService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarPowerService_Stop(void)
{
    uint32_t primask = SilverStarPowerService_IrqLock();

    s_started = 0U;
    s_health.started = 0U;
    SilverStarPowerService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static void SilverStarPowerService_SampleBuild(
    const SystemPowerConfig *effective_config,
    SystemPowerSample *sample,
    SystemDeviceHealth *health,
    uint32_t adc_count,
    uint64_t now_us)
{
    float pin_voltage_v;

    SILVERSTAR_ASSERT_OBJECT(effective_config, SystemPowerConfig,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    SILVERSTAR_ASSERT_OBJECT(sample, SystemPowerSample,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    SILVERSTAR_ASSERT_OBJECT(health, SystemDeviceHealth,
                             SILVERSTAR_ASSERT_MODULE_BOARD);
    pin_voltage_v = ((float)adc_count *
                     ((float)ADC_POWER_NOMINAL_VREF_MV / 1000.0f)) /
                    (float)ADC_POWER_FULL_SCALE_COUNT;
    sample->sample_timestamp_us = now_us;
    sample->receive_timestamp_us = now_us;
    sample->sequence++;
    sample->voltage_v =
        (pin_voltage_v * effective_config->voltage_scale) +
        effective_config->voltage_offset_v;
    sample->current_a = 0.0f;
    sample->power_w = 0.0f;
    sample->state_of_charge_percent = 0.0f;
    sample->temperature_c = 0.0f;
    sample->valid_mask = SYSTEM_POWER_VALID_VOLTAGE;
    health->last_sample_timestamp_us = now_us;
    health->last_receive_timestamp_us = now_us;
    health->sample_count++;
    health->online = 1U;
    health->healthy = 1U;
}

static void SilverStarPowerService_Process(void)
{
    PlatformResult platform_result;
    SystemPowerConfig effective_config;
    SystemPowerSample sample;
    SystemDeviceHealth health;
    uint32_t adc_count;
    uint32_t primask;
    uint64_t now_us;

    SILVERSTAR_ASSERT(s_initialized <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_started <= 1U,
                      SILVERSTAR_ASSERT_MODULE_BOARD,
                      SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_started == 0U)
    {
        return;
    }
    now_us = PlatformTime_Us();
    if ((now_us - s_last_attempt_us) < ADC_POWER_SAMPLE_PERIOD_US)
    {
        return;
    }
    s_last_attempt_us = now_us;

    if (PROJECT_FEATURE_INPUT_VOLTAGE_MONITOR == 0U)
    {
        return;
    }
    platform_result = PlatformAdc_Read(PROJECT_RESOURCE_INPUT_VOLTAGE_ADC,
                                       ADC_POWER_POLL_TIMEOUT_MS,
                                       &adc_count);
    if (platform_result != PLATFORM_OK)
    {
        SilverStarPowerService_ErrorRecord((platform_result == PLATFORM_TIMEOUT) ?
            SYSTEM_DEVICE_TIMEOUT : SYSTEM_DEVICE_IO_ERROR);
        return;
    }

    primask = SilverStarPowerService_IrqLock();
    effective_config = s_effective_config;
    sample = s_sample;
    health = s_health;
    SilverStarPowerService_IrqUnlock(primask);
    SilverStarPowerService_SampleBuild(
        &effective_config, &sample, &health, adc_count, now_us);
    primask = SilverStarPowerService_IrqLock();
    s_sample = sample;
    s_health = health;
    SilverStarPowerService_IrqUnlock(primask);
}

static SystemDeviceResult SilverStarPowerService_GetInfo(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "SilverStar Power Service";
    info->model_name = "SS0.5 Voltage Input";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_POWER_VALID_VOLTAGE;
    info->configuration_mask = SYSTEM_POWER_CFG_VOLTAGE_SCALE |
                               SYSTEM_POWER_CFG_VOLTAGE_OFFSET;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarPowerService_GetCapabilities(uint32_t *mask)
{
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_POWER_VALID_VOLTAGE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarPowerService_GetHealth(SystemDeviceHealth *health)
{
    uint32_t primask;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SilverStarPowerService_IrqLock();
    *health = s_health;
    SilverStarPowerService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarPowerService_GetLatestSample(SystemPowerSample *sample)
{
    SystemPowerSample snapshot;
    uint32_t primask;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SilverStarPowerService_IrqLock();
    snapshot = s_sample;
    SilverStarPowerService_IrqUnlock(primask);
    if (snapshot.sequence == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    *sample = snapshot;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult SilverStarPowerService_RunSelfTest(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult SilverStarPowerService_ApplyConfig(
    const SystemPowerConfig *config,
    SystemDeviceConfigReport *report)
{
    return SilverStarPowerService_ConfigCheck(config, report, 1U);
}

static SystemDeviceResult SilverStarPowerService_VerifyConfig(
    const SystemPowerConfig *config,
    SystemDeviceConfigReport *report)
{
    return SilverStarPowerService_ConfigCheck(config, report, 0U);
}

static SystemDeviceResult SilverStarPowerService_GetEffectiveConfig(
    SystemPowerConfig *config)
{
    uint32_t primask;

    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = SilverStarPowerService_IrqLock();
    *config = s_effective_config;
    SilverStarPowerService_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

const char *SystemPower_NameGet(void) { return "ADC Power"; }
SystemDeviceResult SystemPower_Init(void) { return SilverStarPowerService_Init(); }
SystemDeviceResult SystemPower_Start(void) { return SilverStarPowerService_Start(); }
SystemDeviceResult SystemPower_Stop(void) { return SilverStarPowerService_Stop(); }
void SystemPower_Process(void) { SilverStarPowerService_Process(); }
SystemDeviceResult SystemPower_InfoGet(SystemDeviceInfo *info)
{ return SilverStarPowerService_GetInfo(info); }
SystemDeviceResult SystemPower_CapabilitiesGet(uint32_t *mask)
{ return SilverStarPowerService_GetCapabilities(mask); }
SystemDeviceResult SystemPower_HealthGet(SystemDeviceHealth *health)
{ return SilverStarPowerService_GetHealth(health); }
SystemDeviceResult SystemPower_LatestSampleGet(SystemPowerSample *sample)
{ return SilverStarPowerService_GetLatestSample(sample); }
SystemDeviceResult SystemPower_SelfTestRun(SystemDeviceSelfTestResult *result)
{ return SilverStarPowerService_RunSelfTest(result); }
SystemDeviceResult SystemPower_ConfigApply(
    const SystemPowerConfig *config, SystemDeviceConfigReport *report)
{ return SilverStarPowerService_ApplyConfig(config, report); }
SystemDeviceResult SystemPower_ConfigVerify(
    const SystemPowerConfig *config, SystemDeviceConfigReport *report)
{ return SilverStarPowerService_VerifyConfig(config, report); }
SystemDeviceResult SystemPower_EffectiveConfigGet(SystemPowerConfig *config)
{ return SilverStarPowerService_GetEffectiveConfig(config); }
