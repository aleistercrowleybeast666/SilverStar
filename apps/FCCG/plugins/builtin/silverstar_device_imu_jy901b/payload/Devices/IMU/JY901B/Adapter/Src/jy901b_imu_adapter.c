#include "system_version.h"
#include "jy901b_sensor_adapter.h"

#include <stddef.h>
#include <string.h>

#include "project_resources.h"
#include "jy901b_config.h"
#include "jy901b_imu_build_capabilities.h"
#include "jy901b_instance.h"
#include "jy901b_sample_quality.h"
#include "jy901b_startup.h"
#include "debug_log.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "silverstar_assert.h"
#include "system_user_config.h"

typedef struct
{
    volatile uint8_t initialized;
    volatile uint8_t started;
    volatile uint8_t runtime_owner_active;
    SystemDeviceHealth health;
    SystemImuConfig effective_config;
    IMUData published_data;
    uint32_t imu_logical_sequence;
    uint64_t quality_previous_epoch_us;
    uint32_t quality_last_flags;
    uint32_t config_generation;
    IMUAlgorithm staged_algorithm;
    uint8_t startup_active;
    uint8_t startup_reported;
} Jy901bImuAdapterContext;

static Jy901bImuAdapterContext
    s_contexts[PROJECT_JY901B_INSTANCE_COUNT];

_Static_assert(PROJECT_JY901B_INSTANCE_COUNT <=
               PROJECT_JY901B_INSTANCE_COUNT_MAX,
               "JY901B adapter count exceeds generated resource bound");

#define s_initialized          (s_contexts[instance].initialized)
#define s_started              (s_contexts[instance].started)
#define s_runtime_owner_active (s_contexts[instance].runtime_owner_active)
#define s_health               (s_contexts[instance].health)
#define s_effective_config     (s_contexts[instance].effective_config)
#define s_published_data       (s_contexts[instance].published_data)
#define s_imu_logical_sequence (s_contexts[instance].imu_logical_sequence)
#define s_staged_algorithm     (s_contexts[instance].staged_algorithm)

static PlatformUartId Jy901bAdapter_UartGet(uint8_t instance)
{
    ProjectJy901bResources resources;

    if (ProjectJy901bResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    {
        return (PlatformUartId)PLATFORM_UART_COUNT;
    }
    return resources.uart;
}

static uint8_t Jy901bAdapter_ImuSampleBuild(const IMUData *data,
                                              SystemImuSample *sample)
{
    uint8_t index;

    if ((data == NULL) || (sample == NULL) ||
        ((data->ValidMask & 0x03U) != 0x03U) ||
        (data->AccFrameCount == 0U) || (data->GyroFrameCount == 0U))
    {
        return 0U;
    }
    SILVERSTAR_ASSERT_OBJECT(data, IMUData,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us =
        (data->AccTimestampUs > data->GyroTimestampUs) ?
            data->AccTimestampUs : data->GyroTimestampUs;
    sample->receive_timestamp_us = sample->sample_timestamp_us;
    for (index = 0U; index < 3U; index++)
    {
        sample->accel_raw[index] = data->AccRaw[index];
        sample->gyro_raw[index] = data->GyroRaw[index];
        sample->accel_b_mps2[index] = data->Acc[index];
        sample->gyro_b_radps[index] = data->Gyro[index];
    }
    sample->temperature_c = data->TemperatureC;
    sample->valid_mask = SYSTEM_IMU_VALID_ACCEL |
                         SYSTEM_IMU_VALID_GYRO |
                         SYSTEM_IMU_VALID_TEMPERATURE;
    return 1U;
}

static void Jy901bAdapter_NativeSampleConvert(const Jy901bImuSample *native,
                                               SystemImuSample *sample)
{
    uint8_t index;

    (void)memset(sample, 0, sizeof(*sample));
    sample->sample_timestamp_us = native->sample_timestamp_us;
    sample->receive_timestamp_us = native->sample_timestamp_us;
    for (index = 0U; index < 3U; index++)
    {
        sample->accel_raw[index] = native->accel_raw[index];
        sample->gyro_raw[index] = native->gyro_raw[index];
        sample->accel_b_mps2[index] = native->accel_mps2[index];
        sample->gyro_b_radps[index] = native->gyro_radps[index];
    }
    sample->temperature_c = native->temperature_c;
    sample->valid_mask = SYSTEM_IMU_VALID_ACCEL |
                         SYSTEM_IMU_VALID_GYRO |
                         SYSTEM_IMU_VALID_TEMPERATURE;
}

#if (JY901B_LEGACY_STARTUP_ENABLE != 0U)
static const uint32_t s_baud_candidates[] =
{
    IMU_UART_BAUD_230400,
    IMU_UART_BAUD_115200,
    IMU_UART_BAUD_57600,
    IMU_UART_BAUD_38400,
    IMU_UART_BAUD_19200,
    IMU_UART_BAUD_9600,
    IMU_UART_BAUD_4800
};

#define JY901B_LEGAL_FRAME_WAIT_MAX_POLLS 1024U
#endif

static void Jy901bAdapter_EffectiveRangeUpdate(uint8_t instance, const IMUConfig *config)
{
    static const float accel_ranges_g[] = {2.0f, 4.0f, 8.0f, 16.0f};
    static const float gyro_ranges_dps[] = {200.0f, 500.0f, 1000.0f, 2000.0f};

    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (((config->ValidMask & IMU_CONFIG_VALID_ACCEL_RANGE) != 0U) &&
        (config->AccelRangeValue <
         (sizeof(accel_ranges_g) / sizeof(accel_ranges_g[0]))))
    {
        s_effective_config.accel_range_g =
            accel_ranges_g[config->AccelRangeValue];
        s_effective_config.requested_mask |= SYSTEM_IMU_CFG_ACCEL_RANGE;
    }
    if (((config->ValidMask & IMU_CONFIG_VALID_GYRO_RANGE) != 0U) &&
        (config->GyroRangeValue <
         (sizeof(gyro_ranges_dps) / sizeof(gyro_ranges_dps[0]))))
    {
        s_effective_config.gyro_range_dps =
            gyro_ranges_dps[config->GyroRangeValue];
        s_effective_config.requested_mask |= SYSTEM_IMU_CFG_GYRO_RANGE;
    }
}

static void Jy901bAdapter_EffectiveConfigUpdate(uint8_t instance,
    const IMUConfig *private_config)
{
    SystemImuConfig previous = s_effective_config;
    if (private_config == NULL) { return; }
    SILVERSTAR_ASSERT_OBJECT(private_config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((private_config->ValidMask & IMU_CONFIG_VALID_RATE) != 0U)
    {
        switch ((IMUOutputRate)private_config->OutputRateValue)
        {
            case OutputRate_0_2Hz:
            case OutputRate_0_5Hz:
            case OutputRate_Single0C:
            case OutputRate_None:
            case OutputRate_Single:
                s_effective_config.output_rate_hz = 0U;
                break;
            case OutputRate_1Hz: s_effective_config.output_rate_hz = 1U; break;
            case OutputRate_2Hz: s_effective_config.output_rate_hz = 2U; break;
            case OutputRate_5Hz: s_effective_config.output_rate_hz = 5U; break;
            case OutputRate_10Hz: s_effective_config.output_rate_hz = 10U; break;
            case OutputRate_20Hz: s_effective_config.output_rate_hz = 20U; break;
            case OutputRate_50Hz: s_effective_config.output_rate_hz = 50U; break;
            case OutputRate_100Hz: s_effective_config.output_rate_hz = 100U; break;
            case OutputRate_200Hz: s_effective_config.output_rate_hz = 200U; break;
            default: s_effective_config.output_rate_hz = 0U; break;
        }
        s_effective_config.requested_mask |= SYSTEM_IMU_CFG_OUTPUT_RATE;
    }
    if ((private_config->ValidMask & IMU_CONFIG_VALID_BANDWIDTH) != 0U)
    {
        switch ((IMUBandwidth)private_config->BandwidthValue)
        {
            case Bandwidth_256Hz: s_effective_config.accel_bandwidth_hz = 256.0f; break;
            case Bandwidth_188Hz: s_effective_config.accel_bandwidth_hz = 188.0f; break;
            case Bandwidth_98Hz: s_effective_config.accel_bandwidth_hz = 98.0f; break;
            case Bandwidth_42Hz: s_effective_config.accel_bandwidth_hz = 42.0f; break;
            case Bandwidth_20Hz: s_effective_config.accel_bandwidth_hz = 20.0f; break;
            case Bandwidth_10Hz: s_effective_config.accel_bandwidth_hz = 10.0f; break;
            case Bandwidth_5Hz: s_effective_config.accel_bandwidth_hz = 5.0f; break;
            default: s_effective_config.accel_bandwidth_hz = 0.0f; break;
        }
        s_effective_config.gyro_bandwidth_hz =
            s_effective_config.accel_bandwidth_hz;
        s_effective_config.requested_mask |=
            SYSTEM_IMU_CFG_ACCEL_BANDWIDTH |
            SYSTEM_IMU_CFG_GYRO_BANDWIDTH;
    }
    Jy901bAdapter_EffectiveRangeUpdate(instance, private_config);
    if ((s_contexts[instance].config_generation == 0U) ||
        (memcmp(&previous, &s_effective_config, sizeof(previous)) != 0))
    {
        s_contexts[instance].config_generation++;
        s_contexts[instance].quality_previous_epoch_us = 0U;
    }
}

#if (JY901B_LEGACY_STARTUP_ENABLE != 0U)
static uint8_t Jy901bAdapter_LegalFramesWait(uint8_t instance, uint32_t timeout_ms)
{
    uint32_t start_tick = PlatformTime_Ms();
    uint32_t poll;

    for (poll = 0U; poll < JY901B_LEGAL_FRAME_WAIT_MAX_POLLS; poll++)
    {
        IMU_Poll(instance);
        if (IMU_GetConsecutiveLegalFrameCount(instance) >=
            JY901B_BAUD_VERIFY_FRAME_COUNT)
        {
            return 1U;
        }
        PlatformTime_DelayMs(1U);
        if ((PlatformTime_Ms() - start_tick) >= timeout_ms)
        {
            break;
        }
    }

    return 0U;
}

static uint8_t Jy901bAdapter_BaudCandidateTry(uint8_t instance, uint32_t baudrate)
{
    if (PlatformUart_BaudSet(Jy901bAdapter_UartGet(instance), baudrate) != PLATFORM_OK)
    {
        return 0U;
    }
    IMU_StreamReset(instance);
    (void)PlatformUart_RxFlush(Jy901bAdapter_UartGet(instance));
    return Jy901bAdapter_LegalFramesWait(instance, JY901B_BAUD_SCAN_DWELL_MS);
}

static uint8_t Jy901bAdapter_BaudRescueRun(uint8_t instance)
{
    IMUConfig private_config;
    uint32_t elapsed_ms;
    uint32_t detected_baudrate = 0U;
    uint8_t pass;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(&s_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (JY901B_BAUD_RESCUE_ENABLE == 0U)
    {
        return 1U;
    }

    for (pass = 0U; pass < JY901B_BAUD_SCAN_PASS_COUNT; pass++)
    {
        for (index = 0U;
             index < (uint8_t)(sizeof(s_baud_candidates) /
                               sizeof(s_baud_candidates[0]));
             index++)
        {
            if (Jy901bAdapter_BaudCandidateTry(instance, s_baud_candidates[index]) != 0U)
            {
                detected_baudrate = s_baud_candidates[index];
                break;
            }
        }
        if (detected_baudrate == 0U)
        {
            continue;
        }

        (void)IMU_ReadCurrentConfigPartial(instance, &private_config, &elapsed_ms);
        Jy901bAdapter_EffectiveConfigUpdate(instance, &private_config);
        if ((JY901B_BAUD_NORMALIZE_ENABLE != 0U) &&
            (detected_baudrate != IMU_DEFAULT_BAUDRATE))
        {
            if (IMU_SetBaudrate(instance, Baudrate_230400) != IMU_OK)
            {
                detected_baudrate = 0U;
                continue;
            }
            detected_baudrate = IMU_DEFAULT_BAUDRATE;
        }

        IMU_StreamReset(instance);
        (void)PlatformUart_RxFlush(Jy901bAdapter_UartGet(instance));
        if (Jy901bAdapter_LegalFramesWait(instance,
                JY901B_BAUD_SCAN_DWELL_MS) != 0U)
        {
            return 1U;
        }
        detected_baudrate = 0U;
    }

    (void)PlatformUart_BaudSet(Jy901bAdapter_UartGet(instance), JY901B_UART_BOOT_BAUD);
    IMU_StreamReset(instance);
    (void)PlatformUart_RxFlush(Jy901bAdapter_UartGet(instance));
    return 0U;
}
#endif

static uint32_t Jy901bAdapter_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void Jy901bAdapter_IrqUnlock(uint32_t primask)
{
    PlatformCritical_Exit(primask);
}

SystemDeviceResult Jy901bAdapter_SharedInit(uint8_t instance)
{
    IMUState state;

    SILVERSTAR_ASSERT_OBJECT(&s_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_initialized != 0U)
    {
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    (void)memset(&s_health, 0, sizeof(s_health));
    (void)memset(&s_effective_config, 0, sizeof(s_effective_config));
    (void)memset(&s_published_data, 0, sizeof(s_published_data));
    s_imu_logical_sequence = 0U;
    s_contexts[instance].quality_previous_epoch_us = 0U;
    s_contexts[instance].quality_last_flags = SYSTEM_IMU_QUALITY_RANGE_UNVERIFIED |
        SYSTEM_IMU_QUALITY_TIME_UNCERTAIN;
    s_runtime_owner_active = 0U;
    s_staged_algorithm = Algorithm_6Axis;
    s_contexts[instance].startup_active = 0U;
    s_contexts[instance].startup_reported = 0xFFU;
    state = IMU_LocalGravitySet(instance, SYSTEM_LOCAL_GRAVITY_MPS2);
    if (state == IMU_OK)
    {
        state = IMU_Init(instance);
    }
    if (state != IMU_OK)
    {
        s_health.error_count++;
        return (state == IMU_RESP_TIMEOUT) ? SYSTEM_DEVICE_TIMEOUT :
                                             SYSTEM_DEVICE_IO_ERROR;
    }
#if (JY901B_LEGACY_STARTUP_ENABLE != 0U)
    if (Jy901bAdapter_BaudRescueRun(instance) == 0U)
    {
        s_health.timeout_count++;
        return SYSTEM_DEVICE_TIMEOUT;
    }
#endif
    s_initialized = 1U;
    s_health.initialized = 1U;
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Jy901bAdapter_AlgorithmStage(uint8_t instance, IMUAlgorithm algorithm)
{
    if ((algorithm != Algorithm_6Axis) && (algorithm != Algorithm_9Axis))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    s_staged_algorithm = algorithm;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
}

SystemDeviceResult Jy901bAdapter_SharedStart(uint8_t instance)
{
    uint32_t primask;

    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    if (s_started != 0U) { return SYSTEM_DEVICE_ALREADY_MATCHED; }
    primask = Jy901bAdapter_IrqLock();
    s_started = 1U;
    s_health.started = 1U;
    Jy901bAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Jy901bAdapter_SharedStop(uint8_t instance)
{
    uint32_t primask = Jy901bAdapter_IrqLock();

    s_started = 0U;
    s_health.started = 0U;
    Jy901bAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

void Jy901bAdapter_SharedProcess(uint8_t instance)
{
    const IMUData *data;
    IMUData snapshot;
    PlatformUartDiagnostics io_diagnostics;
    SystemDeviceHealth health;
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_started == 0U) { return; }
    IMU_Poll(instance);
#if (JY901B_LEGACY_STARTUP_ENABLE == 0U)
    if (s_contexts[instance].startup_active != 0U)
    {
        SystemDeviceStartupState state;
        Jy901bStartup_Tick(instance, PlatformTime_Ms());
        state = Jy901bStartup_StateGet(instance);
        if (s_contexts[instance].startup_reported != (uint8_t)state)
        {
            DebugLog_Print("JY901B startup state=%u failure=%u",
                (unsigned int)state,
                (unsigned int)Jy901bStartup_FailureGet(instance));
            s_contexts[instance].startup_reported = (uint8_t)state;
        }
        if (state == SystemDeviceStartupState_Ready)
        {
            IMUConfig readback;
            IMU_ConfigCacheGet(instance, &readback);
            Jy901bAdapter_EffectiveConfigUpdate(instance, &readback);
            s_contexts[instance].startup_active = 0U;
        }
        else if (state == SystemDeviceStartupState_Failed)
        {
            s_health.error_count++;
            s_contexts[instance].startup_active = 0U;
            return;
        }
        else { return; }
    }
#endif
    (void)PlatformUart_DiagnosticsGet(Jy901bAdapter_UartGet(instance), &io_diagnostics);
    data = IMU_GetData(instance);
    snapshot = *data;
    primask = Jy901bAdapter_IrqLock();
    health = s_health;
    Jy901bAdapter_IrqUnlock(primask);
    health.last_sample_timestamp_us =
        (snapshot.GyroTimestampUs > snapshot.AccTimestampUs) ?
            snapshot.GyroTimestampUs : snapshot.AccTimestampUs;
    health.last_receive_timestamp_us = health.last_sample_timestamp_us;
    health.sample_count = s_imu_logical_sequence;
    health.health_flags = s_contexts[instance].quality_last_flags;
    health.error_count += Jy901bImu_OverflowCountTake(instance);
    health.online = IMU_IsOnline(instance);
    health.healthy = (uint8_t)((health.online != 0U) &&
        ((snapshot.ValidMask & 0x03U) == 0x03U) &&
        (io_diagnostics.rx_active != 0U) &&
        ((health.health_flags & (SYSTEM_IMU_QUALITY_CLIPPED |
            SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY | SYSTEM_IMU_QUALITY_RANGE_UNVERIFIED |
            SYSTEM_IMU_QUALITY_PAIR_SKEW)) == 0U));
    primask = Jy901bAdapter_IrqLock();
    s_published_data = snapshot;
    s_health = health;
    Jy901bAdapter_IrqUnlock(primask);
}

SystemDeviceResult Jy901bAdapter_SharedHealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    uint32_t primask;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    primask = Jy901bAdapter_IrqLock();
    *health = s_health;
    Jy901bAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Jy901bAdapter_SharedSnapshotGet(uint8_t instance, IMUData *snapshot)
{
    uint32_t primask;

    if (snapshot == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (s_initialized == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    primask = Jy901bAdapter_IrqLock();
    *snapshot = s_published_data;
    Jy901bAdapter_IrqUnlock(primask);
    return (snapshot->FrameCount != 0U) ? SYSTEM_DEVICE_OK :
                                         SYSTEM_DEVICE_NOT_READY;
}

static SystemDeviceResult Jy901bImuAdapter_Init(uint8_t instance)
{
    return Jy901bAdapter_SharedInit(instance);
}

static SystemDeviceResult Jy901bImuAdapter_Start(uint8_t instance)
{
    return Jy901bAdapter_SharedStart(instance);
}

static SystemDeviceResult Jy901bImuAdapter_Stop(uint8_t instance)
{
    return Jy901bAdapter_SharedStop(instance);
}

static SystemDeviceResult Jy901bImuAdapter_RuntimeOwnerActivate(uint8_t instance)
{
    uint32_t primask;

    if (s_started == 0U) { return SYSTEM_DEVICE_NOT_READY; }
    primask = Jy901bAdapter_IrqLock();
    if (s_runtime_owner_active != 0U)
    {
        Jy901bAdapter_IrqUnlock(primask);
        return SYSTEM_DEVICE_ALREADY_MATCHED;
    }
    s_runtime_owner_active = 1U;
    Jy901bAdapter_IrqUnlock(primask);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Jy901bAdapter_ConfigAccessCheck(uint8_t instance)
{
    return (s_runtime_owner_active != 0U) ? SYSTEM_DEVICE_BUSY :
                                            SYSTEM_DEVICE_OK;
}

static void Jy901bImuAdapter_Process(uint8_t instance)
{
    Jy901bAdapter_SharedProcess(instance);
}

static SystemDeviceResult Jy901bImuAdapter_GetInfo(SystemDeviceInfo *info)
{
    if (info == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    info->device_name = "JY901B IMU Adapter";
    info->model_name = "JY901B";
    info->driver_version = SILVERSTAR_PRODUCT_STRING;
    info->capability_mask = SYSTEM_IMU_CAP_ACCEL |
                            SYSTEM_IMU_CAP_GYRO |
                            SYSTEM_IMU_CAP_TEMPERATURE |
                            SYSTEM_IMU_CAP_CONFIG_OUTPUT_RATE |
                            SYSTEM_IMU_CAP_CONFIG_BANDWIDTH |
                            SYSTEM_IMU_CAP_CONFIG_RANGE;
    info->configuration_mask = SYSTEM_IMU_CFG_OUTPUT_RATE |
                               SYSTEM_IMU_CFG_ACCEL_BANDWIDTH |
                               SYSTEM_IMU_CFG_GYRO_BANDWIDTH |
                               SYSTEM_IMU_CFG_ACCEL_RANGE |
                               SYSTEM_IMU_CFG_GYRO_RANGE;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_GetCapabilities(uint32_t *mask)
{
    SystemDeviceInfo info;

    if (mask == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)Jy901bImuAdapter_GetInfo(&info);
    *mask = info.capability_mask;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_GetLatestSample(uint8_t instance,
    SystemImuSample *sample)
{
    IMUData data;
    uint8_t index;
    SystemDeviceResult result;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemImuSample, SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Jy901bAdapter_SharedSnapshotGet(instance, &data);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    (void)index;
    if (Jy901bAdapter_ImuSampleBuild(&data, sample) == 0U)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    sample->sequence = s_imu_logical_sequence;
    {
        uint64_t skew = (data.AccTimestampUs > data.GyroTimestampUs) ?
            data.AccTimestampUs - data.GyroTimestampUs : data.GyroTimestampUs - data.AccTimestampUs;
        uint64_t previous = (sample->sample_timestamp_us > 0U) ? sample->sample_timestamp_us - 1U : 0U;
        if (Jy901bSample_QualityEvaluate(sample, &s_effective_config, previous, skew) != SYSTEM_DEVICE_OK)
        {
            return SYSTEM_DEVICE_VERIFY_FAILED;
        }
        sample->quality_flags |= s_contexts[instance].quality_last_flags &
            (SYSTEM_IMU_QUALITY_TIME_DISCONTINUITY | SYSTEM_IMU_QUALITY_HISTORY_RESET);
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_GetNextSample(uint8_t instance,
    SystemImuSample *sample)
{
    Jy901bImuSample native;
    Jy901bImuSampleGetResult result;

    if (sample == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(sample, SystemImuSample, SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Jy901bImu_SampleGetNext(instance, &native);
    if (result == JY901B_IMU_SAMPLE_GET_EMPTY)
    {
        return SYSTEM_DEVICE_NOT_READY;
    }
    if (result != JY901B_IMU_SAMPLE_GET_OK)
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    Jy901bAdapter_NativeSampleConvert(&native, sample);
    if (Jy901bSample_QualityEvaluate(sample, &s_effective_config,
        s_contexts[instance].quality_previous_epoch_us, 0U) != SYSTEM_DEVICE_OK)
    {
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    s_contexts[instance].quality_previous_epoch_us = sample->sample_timestamp_us;
    s_contexts[instance].quality_last_flags = sample->quality_flags;
    sample->sequence = ++s_imu_logical_sequence;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_RunSelfTest(
    SystemDeviceSelfTestResult *result)
{
    if (result == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(result, 0, sizeof(*result));
    result->unsupported_mask = 1U;
    return SYSTEM_DEVICE_UNSUPPORTED;
}

SystemDeviceResult Jy901bAdapter_OutputRateValueGet(uint16_t rate_hz,
                                                     IMUOutputRate *value)
{
    if (value == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    switch (rate_hz)
    {
        case 1U: *value = OutputRate_1Hz; break;
        case 2U: *value = OutputRate_2Hz; break;
        case 5U: *value = OutputRate_5Hz; break;
        case 10U: *value = OutputRate_10Hz; break;
        case 20U: *value = OutputRate_20Hz; break;
        case 50U: *value = OutputRate_50Hz; break;
        case 100U: *value = OutputRate_100Hz; break;
        case 200U: *value = OutputRate_200Hz; break;
        default: return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_ConfigValidate(
    const SystemImuConfig *config,
    SystemDeviceConfigReport *report)
{
    IMUOutputRate rate;
    const uint32_t supported = SYSTEM_IMU_CFG_OUTPUT_RATE |
                               SYSTEM_IMU_CFG_ACCEL_BANDWIDTH |
                               SYSTEM_IMU_CFG_GYRO_BANDWIDTH |
                               SYSTEM_IMU_CFG_ACCEL_RANGE |
                               SYSTEM_IMU_CFG_GYRO_RANGE;

    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemImuConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(report, 0, sizeof(*report));
    report->requested_mask = config->requested_mask;
    report->required_mask = config->required_mask;
    report->supported_mask = supported;
    report->unsupported_required_mask = config->required_mask & ~supported;
    report->unsupported_optional_mask = (config->requested_mask & ~supported) &
                                        ~config->required_mask;
    if ((report->unsupported_required_mask != 0U) ||
        (((config->requested_mask & SYSTEM_IMU_CFG_OUTPUT_RATE) != 0U) &&
         (Jy901bAdapter_OutputRateValueGet(config->output_rate_hz, &rate) !=
          SYSTEM_DEVICE_OK)) ||
        (((config->requested_mask & SYSTEM_IMU_CFG_ACCEL_BANDWIDTH) != 0U) &&
         (config->accel_bandwidth_hz != 256.0f)) ||
        (((config->requested_mask & SYSTEM_IMU_CFG_GYRO_BANDWIDTH) != 0U) &&
         (config->gyro_bandwidth_hz != 256.0f)) ||
        (((config->requested_mask & (SYSTEM_IMU_CFG_ACCEL_BANDWIDTH |
                                     SYSTEM_IMU_CFG_GYRO_BANDWIDTH)) ==
          (SYSTEM_IMU_CFG_ACCEL_BANDWIDTH |
           SYSTEM_IMU_CFG_GYRO_BANDWIDTH)) &&
         (config->accel_bandwidth_hz != config->gyro_bandwidth_hz)) ||
        (((config->requested_mask & SYSTEM_IMU_CFG_ACCEL_RANGE) != 0U) &&
         (config->accel_range_g != 16.0f)) ||
        (((config->requested_mask & SYSTEM_IMU_CFG_GYRO_RANGE) != 0U) &&
         (config->gyro_range_dps != 2000.0f)))
    {
        report->verify_failed_mask = config->requested_mask & supported;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->matched_mask = config->requested_mask & supported;
    report->success = 1U;
    return (report->unsupported_optional_mask != 0U) ?
        SYSTEM_DEVICE_UNSUPPORTED : SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_ApplyConfig(uint8_t instance,
    const SystemImuConfig *config,
    SystemDeviceConfigReport *report)
{
#if (JY901B_LEGACY_STARTUP_ENABLE == 0U)
    IMUOutputRate rate = OutputRate_200Hz;
    SystemDeviceResult result;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    if (Jy901bAdapter_ConfigAccessCheck(instance) != SYSTEM_DEVICE_OK)
    { return SYSTEM_DEVICE_BUSY; }
    result = Jy901bImuAdapter_ConfigValidate(config, report);
    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    { return result; }
    if ((config->requested_mask & SYSTEM_IMU_CFG_OUTPUT_RATE) != 0U)
    { (void)Jy901bAdapter_OutputRateValueGet(config->output_rate_hz, &rate); }
    if (Jy901bStartup_Init(instance, rate, s_staged_algorithm) !=
        Jy901bStartupResult_Ok)
    { return SYSTEM_DEVICE_IO_ERROR; }
    s_contexts[instance].startup_active = 1U;
    s_contexts[instance].startup_reported = 0xFFU;
    report->delegated_mask = report->matched_mask;
    report->applied_mask = 0U;
    report->persisted = 0U;
    return SYSTEM_DEVICE_CONFIG_DELEGATED;
#else
    IMUOutputRate rate;
    IMUState state;
    IMUConfig readback;
    SystemDeviceResult result;

    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemImuConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (Jy901bAdapter_ConfigAccessCheck(instance) != SYSTEM_DEVICE_OK)
    {
        (void)memset(report, 0, sizeof(*report));
        return SYSTEM_DEVICE_BUSY;
    }
    result = Jy901bImuAdapter_ConfigValidate(config, report);

    if ((result != SYSTEM_DEVICE_OK) && (result != SYSTEM_DEVICE_UNSUPPORTED))
    {
        return result;
    }
    rate = OutputRate_200Hz;
    if ((config->requested_mask & SYSTEM_IMU_CFG_OUTPUT_RATE) != 0U)
    {
        (void)Jy901bAdapter_OutputRateValueGet(config->output_rate_hz, &rate);
    }
    state = IMU_ApplyDefaultConfig(instance, rate, s_staged_algorithm);
    if (state != IMU_OK)
    {
        report->verify_failed_mask = config->requested_mask;
        report->failed_mask = report->matched_mask;
        report->detail_code = (uint32_t)state;
        report->success = 0U;
        return (state == IMU_RESP_TIMEOUT) ? SYSTEM_DEVICE_TIMEOUT :
                                             SYSTEM_DEVICE_IO_ERROR;
    }
    report->applied_mask = report->matched_mask;
    state = IMU_ReadCurrentConfig(instance, &readback);
    if (state != IMU_OK)
    {
        report->success = 0U;
        report->verify_failed_mask = report->applied_mask;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    Jy901bAdapter_EffectiveConfigUpdate(instance, &readback);
    /* JY901B does not expose a separately readable persistent layer. */
    report->persisted = 0U;
    report->success = 1U;
    return result;
#endif
}

static uint32_t Jy901bImuAdapter_ConfigMismatchMaskGet(uint8_t instance,
    const IMUConfig *config,
    IMUOutputRate expected_rate)
{
    uint32_t mismatch_mask = 0U;

    SILVERSTAR_ASSERT_OBJECT(config, IMUConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (config->BaudrateValue != IMU_DEFAULT_BAUD_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_BAUD; }
    if (config->OutputRateValue != (uint16_t)expected_rate)
    { mismatch_mask |= IMU_CONFIG_VALID_RATE; }
    if (config->BandwidthValue != IMU_DEFAULT_BANDWIDTH_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_BANDWIDTH; }
    if (config->AlgorithmValue != (uint16_t)s_staged_algorithm)
    { mismatch_mask |= IMU_CONFIG_VALID_ALGORITHM; }
    if (config->OrientationValue != IMU_DEFAULT_ORIENT_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_ORIENTATION; }
    if (config->GyroRangeValue != IMU_DEFAULT_GYRO_RANGE_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_GYRO_RANGE; }
    if (config->AccelRangeValue != IMU_DEFAULT_ACCEL_RANGE_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_ACCEL_RANGE; }
    if (config->FusionFilterValue != IMU_DEFAULT_FUSION_FILTER_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_FUSION_FILTER; }
    if (config->AccelerationFilterValue != IMU_DEFAULT_ACCEL_FILTER_VALUE)
    { mismatch_mask |= IMU_CONFIG_VALID_ACCEL_FILTER; }
    if (config->ReturnContentValue != FC_IMU_RETURN_CONTENT_DEFAULT)
    { mismatch_mask |= IMU_CONFIG_VALID_RETURN_CONTENT; }
    return mismatch_mask;
}

static SystemDeviceResult Jy901bImuAdapter_VerifyConfig(uint8_t instance,
    const SystemImuConfig *config,
    SystemDeviceConfigReport *report)
{
#if (JY901B_LEGACY_STARTUP_ENABLE == 0U)
    IMUConfig private_config;
    IMUOutputRate expected_rate = OutputRate_200Hz;
    SystemDeviceStartupState state;
    SystemDeviceResult validation;
    uint32_t mismatch_mask;

    if ((config == NULL) || (report == NULL))
    { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    validation = Jy901bImuAdapter_ConfigValidate(config, report);
    if ((validation != SYSTEM_DEVICE_OK) &&
        (validation != SYSTEM_DEVICE_UNSUPPORTED))
    { return validation; }
    state = Jy901bStartup_StateGet(instance);
    if (state == SystemDeviceStartupState_Failed)
    {
        report->failed_mask = config->requested_mask;
        report->detail_code = (uint32_t)Jy901bStartup_FailureGet(instance);
        report->success = 0U;
        return SYSTEM_DEVICE_TIMEOUT;
    }
    if (state != SystemDeviceStartupState_Ready)
    { return SYSTEM_DEVICE_BUSY; }
    if ((config->requested_mask & SYSTEM_IMU_CFG_OUTPUT_RATE) != 0U)
    { (void)Jy901bAdapter_OutputRateValueGet(config->output_rate_hz,
          &expected_rate); }
    IMU_ConfigCacheGet(instance, &private_config);
    mismatch_mask = Jy901bImuAdapter_ConfigMismatchMaskGet(instance,
        &private_config, expected_rate);
    report->detail_code = mismatch_mask;
    if (mismatch_mask != 0U)
    {
        report->failed_mask = config->requested_mask;
        report->verify_failed_mask = config->requested_mask;
        report->success = 0U;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->applied_mask = report->matched_mask;
    report->success = 1U;
    return validation;
#else
    IMUConfig private_config;
    IMUOutputRate expected_rate = OutputRate_200Hz;
    IMUState state;
    uint32_t mismatch_mask = 0U;
    SystemDeviceResult validation;

    if ((config == NULL) || (report == NULL))
    {
        return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    SILVERSTAR_ASSERT_OBJECT(config, SystemImuConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (Jy901bAdapter_ConfigAccessCheck(instance) != SYSTEM_DEVICE_OK)
    {
        (void)memset(report, 0, sizeof(*report));
        return SYSTEM_DEVICE_BUSY;
    }
    validation = Jy901bImuAdapter_ConfigValidate(config, report);

    if ((validation != SYSTEM_DEVICE_OK) &&
        (validation != SYSTEM_DEVICE_UNSUPPORTED))
    {
        return validation;
    }
    if ((config->requested_mask & SYSTEM_IMU_CFG_OUTPUT_RATE) != 0U)
    {
        (void)Jy901bAdapter_OutputRateValueGet(config->output_rate_hz,
                                                 &expected_rate);
    }
    state = IMU_ReadCurrentConfig(instance, &private_config);
    if (state != IMU_OK)
    {
        report->matched_mask = 0U;
        report->verify_failed_mask = config->requested_mask;
        report->failed_mask = report->verify_failed_mask;
        report->detail_code = (uint32_t)state;
        report->success = 0U;
        return (state == IMU_RESP_TIMEOUT) ? SYSTEM_DEVICE_TIMEOUT :
                                             SYSTEM_DEVICE_IO_ERROR;
    }
    mismatch_mask = Jy901bImuAdapter_ConfigMismatchMaskGet(instance, &private_config,
        expected_rate);
    report->detail_code = mismatch_mask;
    if (mismatch_mask != 0U)
    {
        report->matched_mask = 0U;
        report->verify_failed_mask = config->requested_mask;
        report->failed_mask = report->verify_failed_mask;
        report->success = 0U;
        return SYSTEM_DEVICE_VERIFY_FAILED;
    }
    report->success = 1U;
    return validation;
#endif
}

static SystemDeviceResult Jy901bImuAdapter_GetIoDiagnostics(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    PlatformUartDiagnostics source;

    if (diagnostics == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(diagnostics, SystemDeviceIoDiagnostics,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)PlatformUart_DiagnosticsGet(Jy901bAdapter_UartGet(instance), &source);
    (void)memset(diagnostics, 0, sizeof(*diagnostics));
    diagnostics->supported_mask = SYSTEM_DEVICE_IO_VALID_TRANSPORT |
        SYSTEM_DEVICE_IO_VALID_RX_BYTES |
        SYSTEM_DEVICE_IO_VALID_RX_EVENTS |
        SYSTEM_DEVICE_IO_VALID_RX_IDLE_EVENTS |
        SYSTEM_DEVICE_IO_VALID_RX_TC_EVENTS |
        SYSTEM_DEVICE_IO_VALID_RX_DISCARDED |
        SYSTEM_DEVICE_IO_VALID_UART_OVERRUN |
        SYSTEM_DEVICE_IO_VALID_UART_FRAMING |
        SYSTEM_DEVICE_IO_VALID_UART_NOISE |
        SYSTEM_DEVICE_IO_VALID_UART_PARITY |
        SYSTEM_DEVICE_IO_VALID_DMA_ERRORS |
        SYSTEM_DEVICE_IO_VALID_RX_RESTARTS |
        SYSTEM_DEVICE_IO_VALID_RX_RESTART_FAILS |
        SYSTEM_DEVICE_IO_VALID_DISCONTINUITIES |
        SYSTEM_DEVICE_IO_VALID_RX_ACTIVE;
    diagnostics->valid_mask = diagnostics->supported_mask;
    diagnostics->transport_type = SYSTEM_DEVICE_TRANSPORT_UART;
    diagnostics->owner = SYSTEM_DEVICE_IO_OWNER_SELF;
    diagnostics->rx_bytes = source.rx_bytes;
    diagnostics->rx_event_count = source.rx_event_count;
    diagnostics->rx_idle_event_count = source.rx_idle_event_count;
    diagnostics->rx_transfer_complete_count =
        source.rx_transfer_complete_count;
    diagnostics->rx_discarded_bytes = source.rx_discarded_bytes;
    diagnostics->uart_overrun_error_count =
        source.uart_overrun_error_count;
    diagnostics->uart_framing_error_count =
        source.uart_framing_error_count;
    diagnostics->uart_noise_error_count = source.uart_noise_error_count;
    diagnostics->uart_parity_error_count = source.uart_parity_error_count;
    diagnostics->dma_error_count = source.dma_error_count;
    diagnostics->rx_restart_count = source.rx_restart_count;
    diagnostics->rx_restart_failure_count = source.rx_restart_failure_count;
    diagnostics->rx_discontinuity_count = source.rx_discontinuity_count;
    diagnostics->rx_active = source.rx_active;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_GetIoDetail(uint8_t instance,
    SystemImuIoDetail *detail)
{
    IMUStreamDiagnostics source;

    if (detail == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    IMU_StreamDiagnosticsGet(instance, &source);
    (void)memset(detail, 0, sizeof(*detail));
    detail->valid_frame_count = source.valid_frame_count;
    detail->checksum_error_count = source.checksum_error_count;
    detail->parser_resync_count = source.parser_resync_count;
    detail->config_generation = s_contexts[instance].config_generation;
    detail->config_generation_valid = (detail->config_generation != 0U);
    return SYSTEM_DEVICE_OK;
}

SystemDeviceResult Jy901bAdapter_FrameHealthGet(uint8_t instance, IMUFrameType frame_type,
                                                 SystemDeviceHealth *health)
{
    IMUData snapshot;
    uint64_t timestamp_us = 0U;
    uint64_t now_us;
    uint32_t count = 0U;
    uint32_t valid_mask = 0U;
    uint8_t recent;
    SystemDeviceResult result;

    if (health == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    SILVERSTAR_ASSERT_OBJECT(health, SystemDeviceHealth,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    result = Jy901bAdapter_SharedHealthGet(instance, health);
    if (result != SYSTEM_DEVICE_OK) { return result; }
    (void)memset(&snapshot, 0, sizeof(snapshot));
    result = Jy901bAdapter_SharedSnapshotGet(instance, &snapshot);
    if ((result != SYSTEM_DEVICE_OK) &&
        (result != SYSTEM_DEVICE_NOT_READY))
    {
        return result;
    }
    switch (frame_type)
    {
        case IMUFrameNone:
        case IMUFrameAcc:
        case IMUFrameGyro:
        case IMUFrameEuler:
            return SYSTEM_DEVICE_INVALID_ARGUMENT;
        case IMUFrameMag:
            timestamp_us = snapshot.MagTimestampUs;
            count = snapshot.MagFrameCount;
            valid_mask = (1U << 3);
            break;
        case IMUFramePressureHeight:
            timestamp_us = snapshot.PressureTimestampUs;
            count = snapshot.PressureFrameCount;
            valid_mask = (1U << 4);
            break;
        case IMUFrameQuaternion:
            timestamp_us = snapshot.QuaternionTimestampUs;
            count = snapshot.QuaternionFrameCount;
            valid_mask = (1U << 5);
            break;
        default:
            return SYSTEM_DEVICE_INVALID_ARGUMENT;
    }
    now_us = PlatformTime_Us();
    recent = (uint8_t)((timestamp_us != 0U) && (now_us >= timestamp_us) &&
        ((now_us - timestamp_us) <= ((uint64_t)IMU_ONLINE_TIMEOUT_MS * 1000ULL)));
    health->last_sample_timestamp_us = timestamp_us;
    health->last_receive_timestamp_us = timestamp_us;
    health->sample_count = count;
    health->online = (uint8_t)((health->initialized != 0U) &&
                               (health->started != 0U) &&
                               (recent != 0U));
    health->healthy = (uint8_t)((health->online != 0U) &&
                                ((snapshot.ValidMask & valid_mask) != 0U));
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_GetEffectiveConfig(uint8_t instance,
    SystemImuConfig *config)
{
    if (config == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    *config = s_effective_config;
    return SYSTEM_DEVICE_OK;
}

static SystemDeviceResult Jy901bImuAdapter_GetNoise(
    SystemImuNoiseCharacteristics *noise)
{
    if (noise == NULL) { return SYSTEM_DEVICE_INVALID_ARGUMENT; }
    (void)memset(noise, 0, sizeof(*noise));
    noise->recommended_process_accel_std_mps2[0] =
        JY901B_IMU_RECOMMENDED_PROCESS_ACCEL_E_STD_MPS2;
    noise->recommended_process_accel_std_mps2[1] =
        JY901B_IMU_RECOMMENDED_PROCESS_ACCEL_N_STD_MPS2;
    noise->recommended_process_accel_std_mps2[2] =
        JY901B_IMU_RECOMMENDED_PROCESS_ACCEL_U_STD_MPS2;
    noise->valid_mask = SYSTEM_IMU_NOISE_VALID_PROCESS_ACCEL_STD;
    return SYSTEM_DEVICE_OK;
}

const char *Jy901bImuInstance_NameGet(uint8_t instance)
{
    (void)instance;
    return "JY901B IMU";
}
SystemDeviceResult Jy901bImuInstance_Init(uint8_t instance) { return Jy901bImuAdapter_Init(instance); }
SystemDeviceResult Jy901bImuInstance_Start(uint8_t instance) { return Jy901bImuAdapter_Start(instance); }
SystemDeviceResult Jy901bImuInstance_Stop(uint8_t instance) { return Jy901bImuAdapter_Stop(instance); }
SystemDeviceResult Jy901bImuInstance_RuntimeOwnerActivate(uint8_t instance)
{
    return Jy901bImuAdapter_RuntimeOwnerActivate(instance);
}
SystemDeviceResult Jy901bImuInstance_Process(uint8_t instance)
{
    Jy901bImuAdapter_Process(instance);
    return SYSTEM_DEVICE_OK;
}
SystemDeviceResult Jy901bImuInstance_InfoGet(
    uint8_t instance, SystemDeviceInfo *info)
{
    (void)instance;
    return Jy901bImuAdapter_GetInfo(info);
}
SystemDeviceResult Jy901bImuInstance_CapabilitiesGet(
    uint8_t instance, uint32_t *capability_mask)
{
    (void)instance;
    return Jy901bImuAdapter_GetCapabilities(capability_mask);
}
SystemDeviceResult Jy901bImuInstance_HealthGet(uint8_t instance, SystemDeviceHealth *health)
{
    return Jy901bAdapter_SharedHealthGet(instance, health);
}
SystemDeviceResult Jy901bImuInstance_IoDiagnosticsGet(uint8_t instance,
    SystemDeviceIoDiagnostics *diagnostics)
{
    return Jy901bImuAdapter_GetIoDiagnostics(instance, diagnostics);
}
SystemDeviceResult Jy901bImuInstance_IoDetailGet(uint8_t instance, SystemImuIoDetail *detail)
{
    return Jy901bImuAdapter_GetIoDetail(instance, detail);
}
SystemDeviceResult Jy901bImuInstance_LatestSampleGet(uint8_t instance, SystemImuSample *sample)
{
    return Jy901bImuAdapter_GetLatestSample(instance, sample);
}
SystemDeviceResult Jy901bImuInstance_NextSampleGet(uint8_t instance, SystemImuSample *sample)
{
    return Jy901bImuAdapter_GetNextSample(instance, sample);
}
SystemDeviceResult Jy901bImuInstance_SelfTestRun(
    uint8_t instance, SystemDeviceSelfTestResult *result)
{
    (void)instance;
    return Jy901bImuAdapter_RunSelfTest(result);
}
SystemDeviceResult Jy901bImuInstance_ConfigApply(uint8_t instance, const SystemImuConfig *config,
                                         SystemDeviceConfigReport *report)
{
    return Jy901bImuAdapter_ApplyConfig(instance, config, report);
}
SystemDeviceResult Jy901bImuInstance_ConfigVerify(uint8_t instance, const SystemImuConfig *config,
                                          SystemDeviceConfigReport *report)
{
    return Jy901bImuAdapter_VerifyConfig(instance, config, report);
}
SystemDeviceResult Jy901bImuInstance_EffectiveConfigGet(uint8_t instance, SystemImuConfig *config)
{
    return Jy901bImuAdapter_GetEffectiveConfig(instance, config);
}
SystemDeviceResult Jy901bImuInstance_NoiseCharacteristicsGet(
    uint8_t instance, SystemImuNoiseCharacteristics *noise)
{
    (void)instance;
    return Jy901bImuAdapter_GetNoise(noise);
}
