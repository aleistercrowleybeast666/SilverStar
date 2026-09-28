#include "system_version.h"
#include "system_hardware_quaternion_if.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "jy901b_instance.h"
#include "jy901b_sensor_adapter.h"
#include "silverstar_assert.h"

static SystemHardwareQuaternionConfig
    s_effective_configs[PROJECT_JY901B_INSTANCE_COUNT];

#define s_effective_config (s_effective_configs[instance])

static SystemDeviceResult Jy901bQuaternionAdapter_GetHealth(uint8_t instance,
    SystemDeviceHealth *health)
{
    (void)instance;
    return Jy901bAdapter_FrameHealthGet(instance, IMUFrameQuaternion, health);
}

static SystemDeviceResult Jy901bQuaternionAdapter_Init(uint8_t instance)
{
    (void)instance;
    return Jy901bAdapter_SharedInit(instance);
}

static SystemDeviceResult Jy901bQuaternionAdapter_Start(uint8_t instance)
{
    (void)instance;
    SystemDeviceResult result = Jy901bAdapter_SharedStart(instance);

    return (result == SYSTEM_DEVICE_ALREADY_MATCHED) ? SYSTEM_DEVICE_OK : result;
}

static SystemDeviceResult Jy901bQuaternionAdapter_Stop(uint8_t instance)
{
    (void)instance;
    return SYSTEM_DEVICE_OK;
}

static void Jy901bQuaternionAdapter_Process(uint8_t instance)
{
    (void)instance;
}

static SystemDeviceResult Jy901bQuaternionAdapter_GetInfo(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance;
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "JY901B Hardware Quaternion Adapter";
    info->model_name = "JY901B";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_HW_QUAT_CAP_OUTPUT |
                            SYSTEM_HW_QUAT_CAP_6AXIS |
                            SYSTEM_HW_QUAT_CAP_9AXIS |
                            SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
    info->configuration_mask = SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bQuaternionAdapter_GetCapabilities(uint8_t instance, uint32_t *mask)
{
    (void)instance;
    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *mask = SYSTEM_HW_QUAT_CAP_OUTPUT |
            SYSTEM_HW_QUAT_CAP_6AXIS |
            SYSTEM_HW_QUAT_CAP_9AXIS |
            SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
    return SYSTEM_DEVICE_OK;
}

static void Jy901bQuaternionAdapter_ModeResolve(uint8_t instance,
    const IMUConfig *config,
    SystemHardwareQuaternionSample *sample)
{
    (void)instance;
    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(sample, SystemHardwareQuaternionSample,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    sample->mode = SYSTEM_HW_QUAT_MODE_UNKNOWN;
    if ((config->ValidMask & IMU_CONFIG_VALID_ALGORITHM) == 0U) { return; }
    if (config->AlgorithmValue == IMU_ALGORITHM_6_AXIS_VALUE)
    {
        sample->mode = SYSTEM_HW_QUAT_MODE_6AXIS;
        sample->mode_verified = 1U;
    }
    else if (config->AlgorithmValue == IMU_ALGORITHM_9_AXIS_VALUE)
    {
        sample->mode = SYSTEM_HW_QUAT_MODE_9AXIS;
        sample->mode_verified = 1U;
    }
}

static SystemDeviceResult Jy901bQuaternionAdapter_GetSample(uint8_t instance,
    SystemHardwareQuaternionSample *sample)
{
    (void)instance;
    IMUData data;
    IMUConfig config;
    float norm;
    uint8_t index;
    SystemDeviceResult result;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemHardwareQuaternionSample,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Jy901bAdapter_SharedSnapshotGet(instance, &data);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    if ((data.ValidMask & (1U << 5)) == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    IMU_ConfigCacheGet(instance, &config);
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = data.QuaternionTimestampUs;
    sample->receive_timestamp_us = data.QuaternionTimestampUs;
    sample->sequence = data.QuaternionFrameCount;
    for (index = 0U; index < 4U; index++)
    {
        sample->quaternion_wxyz[index] =
            (float)data.QuaternionRawQ15[index] / 32768.0f;
    }
    norm = sqrtf((sample->quaternion_wxyz[0] * sample->quaternion_wxyz[0]) +
                 (sample->quaternion_wxyz[1] * sample->quaternion_wxyz[1]) +
                 (sample->quaternion_wxyz[2] * sample->quaternion_wxyz[2]) +
                 (sample->quaternion_wxyz[3] * sample->quaternion_wxyz[3]));
    if ((!isfinite(norm)) || (norm < 1.0e-6f))
    {
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    for (index = 0U; index < 4U; index++)
    {
        sample->quaternion_wxyz[index] /= norm;
    }
    Jy901bQuaternionAdapter_ModeResolve(instance, &config, sample);
    /* This is runtime mode/config health, not SilverStar Alignment
     * qualification. Authoritative eligibility is build-time metadata. */
    sample->algorithm_healthy = sample->mode_verified;
    sample->normalized = 1U;
    sample->valid = 1U;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bQuaternionAdapter_SelfTest(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance;
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

static SystemDeviceResult Jy901bQuaternionAdapter_ConfigCheck(uint8_t instance,
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemHardwareQuaternionConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
    report->unsupported_required_mask = config->required_mask &
                                        ~SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
    report->unsupported_optional_mask = (config->requested_mask &
                                         ~SYSTEM_HW_QUAT_CAP_CONFIG_MODE) &
                                        ~config->required_mask;
    if ((report->unsupported_required_mask != 0U) ||
        ((config->requested_mask & SYSTEM_HW_QUAT_CAP_CONFIG_MODE) != 0U &&
         (config->mode != SYSTEM_HW_QUAT_MODE_6AXIS) &&
         (config->mode != SYSTEM_HW_QUAT_MODE_9AXIS)))
    {
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->matched_mask = config->requested_mask &
                           SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
    report->success = 1U;
    return (report->unsupported_optional_mask != 0U) ?
        SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bQuaternionAdapter_ApplyConfig(uint8_t instance,
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    SystemDeviceResult result =
        Jy901bQuaternionAdapter_ConfigCheck(instance, config, report);
    IMUAlgorithm algorithm;

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    {
        return result;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemHardwareQuaternionConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((config->requested_mask & SYSTEM_HW_QUAT_CAP_CONFIG_MODE) != 0U)
    {
        algorithm = (config->mode == SYSTEM_HW_QUAT_MODE_6AXIS) ?
            Algorithm_6Axis : Algorithm_9Axis;
        if (Jy901bAdapter_AlgorithmStage(instance, algorithm) !=
            SYSTEM_DEVICE_CONFIG_DELEGATED)
        {
            report->verify_failed_mask = SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
            report->success = 0U;
            return SYSTEM_DEVICE_INVALID_ARGUMENT;
        }
        report->delegated_mask = SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
        report->applied_mask = 0U;
        report->matched_mask = 0U;
    }
    s_effective_config = *config;
    return (report->delegated_mask != 0U) ?
        SYSTEM_DEVICE_CONFIG_DELEGATED : result;
}

static SystemDeviceResult Jy901bQuaternionAdapter_VerifyConfig(uint8_t instance,
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance;
    uint16_t actual_value;
    uint16_t expected_value;
    IMUState state;
    SystemDeviceResult result =
        Jy901bQuaternionAdapter_ConfigCheck(instance, config, report);

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    {
        return result;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemHardwareQuaternionConfig,
                             SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((config->requested_mask & SYSTEM_HW_QUAT_CAP_CONFIG_MODE) == 0U)
    {
        return result;
    }
    if (Jy901bAdapter_ConfigAccessCheck(instance) != SYSTEM_DEVICE_OK)
    {
        return SYSTEM_DEVICE_BUSY;
    }
    expected_value = (config->mode == SYSTEM_HW_QUAT_MODE_6AXIS) ?
        IMU_ALGORITHM_6_AXIS_VALUE : IMU_ALGORITHM_9_AXIS_VALUE;
    state = IMU_ReadAlgorithm(instance, &actual_value);
    if ((state != IMU_OK) || (actual_value != expected_value))
    {
        report->matched_mask = 0U;
        report->verify_failed_mask = SYSTEM_HW_QUAT_CAP_CONFIG_MODE;
        report->failed_mask = report->verify_failed_mask;
        report->detail_code = (state != IMU_OK) ? (uint32_t)state :
                                                    (uint32_t)actual_value;
        report->success = 0U;
        return (state == IMU_RESP_TIMEOUT) ? SYSTEM_DEVICE_TIMEOUT :
                                             SYSTEM_DEVICE_VERIFY_FAILED;
    }
    IMU_ConfigCacheSetField(instance, IMU_CONFIG_VALID_ALGORITHM, actual_value);
    return result;
}

static SystemDeviceResult Jy901bQuaternionAdapter_GetConfig(uint8_t instance,
    SystemHardwareQuaternionConfig *config)
{
    (void)instance;
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *config = s_effective_config;
    return SYSTEM_DEVICE_OK;
}

const char *Jy901bQuaternionInstance_NameGet(uint8_t instance)
{
    (void)instance; return "JY901B Hardware Quaternion"; }
SystemDeviceResult Jy901bQuaternionInstance_Init(uint8_t instance)
{
    (void)instance; return Jy901bQuaternionAdapter_Init(instance); }
SystemDeviceResult Jy901bQuaternionInstance_Start(uint8_t instance)
{
    (void)instance; return Jy901bQuaternionAdapter_Start(instance); }
SystemDeviceResult Jy901bQuaternionInstance_Stop(uint8_t instance)
{
    (void)instance; return Jy901bQuaternionAdapter_Stop(instance); }
void Jy901bQuaternionInstance_Process(uint8_t instance)
{
    (void)instance; Jy901bQuaternionAdapter_Process(instance); }
SystemDeviceResult Jy901bQuaternionInstance_InfoGet(uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance; return Jy901bQuaternionAdapter_GetInfo(instance, info); }
SystemDeviceResult Jy901bQuaternionInstance_CapabilitiesGet(uint8_t instance, uint32_t *mask)
{
    (void)instance; return Jy901bQuaternionAdapter_GetCapabilities(instance, mask); }
SystemDeviceResult Jy901bQuaternionInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    (void)instance; return Jy901bQuaternionAdapter_GetHealth(instance, health); }
SystemDeviceResult Jy901bQuaternionInstance_LatestSampleGet(uint8_t instance,
    SystemHardwareQuaternionSample *sample)
{
    (void)instance; return Jy901bQuaternionAdapter_GetSample(instance, sample); }
SystemDeviceResult Jy901bQuaternionInstance_SelfTestRun(uint8_t instance,
    SystemDeviceSelfTestResult *result)
{
    (void)instance; return Jy901bQuaternionAdapter_SelfTest(instance, result); }
SystemDeviceResult Jy901bQuaternionInstance_ConfigApply(uint8_t instance,
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance; return Jy901bQuaternionAdapter_ApplyConfig(instance, config, report); }
SystemDeviceResult Jy901bQuaternionInstance_ConfigVerify(uint8_t instance,
    const SystemHardwareQuaternionConfig *config,
    SystemDeviceConfigReport *report)
{
    (void)instance; return Jy901bQuaternionAdapter_VerifyConfig(instance, config, report); }
SystemDeviceResult Jy901bQuaternionInstance_EffectiveConfigGet(uint8_t instance,
    SystemHardwareQuaternionConfig *config)
{
    (void)instance; return Jy901bQuaternionAdapter_GetConfig(instance, config); }
