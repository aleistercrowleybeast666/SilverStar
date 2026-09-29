#include "jy901b_startup.h"

#include <stddef.h>
#include <string.h>

#include "jy901b_config.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "project_resources.h"
#include "silverstar_assert.h"

#define JY901B_STARTUP_STAGE_TIMEOUT_MS 10000U
#define JY901B_STARTUP_SAMPLE_TIMEOUT_MS 2000U

typedef struct
{
    SystemDeviceStartup controller;
    uint16_t actual[JY901B_STARTUP_REGISTER_COUNT];
    uint16_t verified[JY901B_STARTUP_REGISTER_COUNT];
    uint32_t sample_acc_baseline;
    uint32_t sample_gyro_baseline;
    uint32_t reconnect_started_ms;
    IMUOutputRate output_rate;
    IMUAlgorithm algorithm;
    uint8_t instance;
    uint8_t read_index;
    uint8_t read_active;
    uint8_t apply_index;
    uint8_t apply_active;
    uint8_t verify_index;
    uint8_t verify_active;
    uint8_t reconnect_started;
} Jy901bStartupContext;

static Jy901bStartupContext s_contexts[PROJECT_JY901B_INSTANCE_COUNT];

static const SystemDeviceStartupCandidate s_supported_candidates[] =
{
    {IMU_UART_BAUD_115200, 0U},
    {IMU_UART_BAUD_57600, 0U},
    {IMU_UART_BAUD_38400, 0U},
    {IMU_UART_BAUD_19200, 0U},
    {IMU_UART_BAUD_4800, 0U}
};

static PlatformUartId Jy901bStartup_UartGet(uint8_t instance)
{
    ProjectJy901bResources resources;

    if (ProjectJy901bResources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return (PlatformUartId)PLATFORM_UART_COUNT; }
    return resources.uart;
}

static SystemDeviceStartupStepResult Jy901bStartup_ProbeStart(
    void *owner, const SystemDeviceStartupCandidate *candidate)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;
    PlatformUartId uart;

    if ((context == NULL) || (candidate == NULL))
    { return SystemDeviceStartupStep_Failed; }
    uart = Jy901bStartup_UartGet(context->instance);
    if (PlatformUart_BaudSet(uart, candidate->baudrate) != PLATFORM_OK)
    { return SystemDeviceStartupStep_Failed; }
    IMU_StreamReset(context->instance);
    (void)PlatformUart_RxFlush(uart);
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Jy901bStartup_ProbePoll(void *owner)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;

    IMU_Poll(context->instance);
    return (IMU_GetConsecutiveLegalFrameCount(context->instance) >=
            JY901B_BAUD_VERIFY_FRAME_COUNT) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult Jy901bStartup_RegisterReadStep(
    Jy901bStartupContext *context, uint8_t *position, uint8_t *active,
    uint16_t *values)
{
    uint8_t reg;
    uint16_t expected;
    uint16_t value;
    Jy901bRegisterReadStartResult start_result;
    Jy901bRegisterReadPollResult poll_result;

    SILVERSTAR_ASSERT_OBJECT(context, Jy901bStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(position, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(active, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(values, uint16_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(*position <= JY901B_STARTUP_REGISTER_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);

    if (*position >= JY901B_STARTUP_REGISTER_COUNT)
    { return SystemDeviceStartupStep_Ok; }
    if (IMU_StartupRegisterGet(*position, context->output_rate,
            context->algorithm, &reg, &expected) !=
        Jy901bStartupRegisterResult_Ok)
    { return SystemDeviceStartupStep_Failed; }
    if (*active == 0U)
    {
        start_result = IMU_RegisterReadAsyncStart(context->instance, reg);
        if (start_result == Jy901bRegisterReadStartResult_Busy)
        { return SystemDeviceStartupStep_Pending; }
        if (start_result != Jy901bRegisterReadStartResult_Ok)
        { return SystemDeviceStartupStep_Failed; }
        *active = 1U;
        return SystemDeviceStartupStep_Pending;
    }
    poll_result = IMU_RegisterReadAsyncPoll(context->instance, &value);
    if (poll_result == Jy901bRegisterReadPollResult_Pending)
    { return SystemDeviceStartupStep_Pending; }
    *active = 0U;
    if (poll_result != Jy901bRegisterReadPollResult_Complete)
    { return SystemDeviceStartupStep_Failed; }
    values[*position] = value;
    (*position)++;
    return (*position >= JY901B_STARTUP_REGISTER_COUNT) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult Jy901bStartup_ConfigRead(
    void *owner, uint32_t *difference_mask)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;
    SystemDeviceStartupStepResult result;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, Jy901bStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(difference_mask, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    result = Jy901bStartup_RegisterReadStep(context,
        &context->read_index, &context->read_active, context->actual);
    if (result != SystemDeviceStartupStep_Ok) { return result; }
    *difference_mask = 0U;
    for (index = 0U; index < JY901B_STARTUP_REGISTER_COUNT; index++)
    {
        uint8_t reg;
        uint16_t expected;
        (void)IMU_StartupRegisterGet(index, context->output_rate,
            context->algorithm, &reg, &expected);
        if (context->actual[index] != expected)
        { *difference_mask |= 1UL << index; }
    }
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Jy901bStartup_ConfigApply(
    void *owner, uint32_t difference_mask, uint8_t *reconnect_required)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;
    uint8_t index;
    uint8_t reg;
    uint16_t expected;

    SILVERSTAR_ASSERT_OBJECT(context, Jy901bStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(reconnect_required, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->apply_index <= JY901B_STARTUP_REGISTER_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);

    if (context->apply_index >= JY901B_STARTUP_REGISTER_COUNT)
    {
        *reconnect_required = (uint8_t)((difference_mask & 1UL) != 0U);
        return SystemDeviceStartupStep_Ok;
    }
    /* Communication changes are always the final register write. */
    index = (context->apply_index ==
             (JY901B_STARTUP_REGISTER_COUNT - 1U)) ?
        0U : (uint8_t)(context->apply_index + 1U);
    if ((difference_mask & (1UL << index)) == 0U)
    {
        context->apply_index++;
        return SystemDeviceStartupStep_Pending;
    }
    if (IMU_StartupRegisterGet(index, context->output_rate,
            context->algorithm, &reg, &expected) !=
        Jy901bStartupRegisterResult_Ok)
    { return SystemDeviceStartupStep_Failed; }
    if (context->apply_active == 0U)
    {
        Jy901bRegisterWriteStartResult start_result =
            IMU_RegisterWriteAsyncStart(context->instance, reg, expected);
        if (start_result == Jy901bRegisterWriteStartResult_Busy)
        { return SystemDeviceStartupStep_Pending; }
        if (start_result != Jy901bRegisterWriteStartResult_Ok)
        { return SystemDeviceStartupStep_Failed; }
        context->apply_active = 1U;
        return SystemDeviceStartupStep_Pending;
    }
    {
        Jy901bRegisterWritePollResult poll_result =
            IMU_RegisterWriteAsyncPoll(context->instance);
        if (poll_result == Jy901bRegisterWritePollResult_Pending)
        { return SystemDeviceStartupStep_Pending; }
        context->apply_active = 0U;
        if (poll_result != Jy901bRegisterWritePollResult_Complete)
        { return SystemDeviceStartupStep_Failed; }
    }
    context->apply_index++;
    return SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult Jy901bStartup_Reconnect(void *owner)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;
    PlatformUartId uart = Jy901bStartup_UartGet(context->instance);

    if (context->reconnect_started == 0U)
    {
        if (PlatformUart_BaudSet(uart, IMU_DEFAULT_BAUDRATE) != PLATFORM_OK)
        { return SystemDeviceStartupStep_Failed; }
        IMU_StreamReset(context->instance);
        (void)PlatformUart_RxFlush(uart);
        context->reconnect_started_ms = PlatformTime_Ms();
        context->reconnect_started = 1U;
        return SystemDeviceStartupStep_Pending;
    }
    return ((uint32_t)(PlatformTime_Ms() - context->reconnect_started_ms) >=
            IMU_CFG_BAUD_SWITCH_DELAY_MS) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static void Jy901bStartup_VerifiedConfigStore(Jy901bStartupContext *context)
{
    IMUConfig config;

    (void)memset(&config, 0, sizeof(config));
    config.BaudrateValue = context->verified[0];
    config.OrientationValue = context->verified[1];
    config.AlgorithmValue = context->verified[2];
    config.BandwidthValue = context->verified[3];
    config.OutputRateValue = context->verified[4];
    config.GyroRangeValue = context->verified[5];
    config.AccelRangeValue = context->verified[6];
    config.FusionFilterValue = context->verified[7];
    config.AccelerationFilterValue = context->verified[8];
    config.ReturnContentValue = context->verified[9];
    config.ValidMask = IMU_CONFIG_VALID_ALL;
    IMU_ConfigCacheSetAll(context->instance, &config);
}

static SystemDeviceStartupStepResult Jy901bStartup_ConfigVerify(void *owner)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;
    SystemDeviceStartupStepResult result;
    uint8_t index;
    const IMUData *data;

    SILVERSTAR_ASSERT_OBJECT(context, Jy901bStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->verify_index <= JY901B_STARTUP_REGISTER_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);

    result = Jy901bStartup_RegisterReadStep(context,
        &context->verify_index, &context->verify_active,
        context->verified);
    if (result != SystemDeviceStartupStep_Ok) { return result; }
    for (index = 0U; index < JY901B_STARTUP_REGISTER_COUNT; index++)
    {
        uint8_t reg;
        uint16_t expected;
        (void)IMU_StartupRegisterGet(index, context->output_rate,
            context->algorithm, &reg, &expected);
        if (context->verified[index] != expected)
        { return SystemDeviceStartupStep_Failed; }
    }
    Jy901bStartup_VerifiedConfigStore(context);
    data = IMU_GetData(context->instance);
    context->sample_acc_baseline = data->AccFrameCount;
    context->sample_gyro_baseline = data->GyroFrameCount;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult Jy901bStartup_SamplePoll(void *owner)
{
    Jy901bStartupContext *context = (Jy901bStartupContext *)owner;
    const IMUData *data;

    IMU_Poll(context->instance);
    data = IMU_GetData(context->instance);
    return (((data->ValidMask & 0x03U) == 0x03U) &&
            (data->AccFrameCount > context->sample_acc_baseline) &&
            (data->GyroFrameCount > context->sample_gyro_baseline)) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static const SystemDeviceStartupOperations s_operations =
{
    Jy901bStartup_ProbeStart,
    Jy901bStartup_ProbePoll,
    Jy901bStartup_ConfigRead,
    Jy901bStartup_ConfigApply,
    Jy901bStartup_Reconnect,
    Jy901bStartup_ConfigVerify,
    Jy901bStartup_SamplePoll
};

Jy901bStartupResult Jy901bStartup_Init(
    uint8_t instance, IMUOutputRate output_rate, IMUAlgorithm algorithm)
{
    SystemDeviceStartupConfig config;
    Jy901bStartupContext *context;

    if ((instance >= PROJECT_JY901B_INSTANCE_COUNT) ||
        ((algorithm != Algorithm_6Axis) &&
         (algorithm != Algorithm_9Axis)))
    { return Jy901bStartupResult_InvalidArgument; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT_OBJECT(context, Jy901bStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(context, 0, sizeof(*context));
    context->instance = instance;
    context->output_rate = output_rate;
    context->algorithm = algorithm;
    (void)memset(&config, 0, sizeof(config));
    config.persistence = SystemDeviceStartupPersistence_Persistent;
    config.target.baudrate = JY901B_UART_BOOT_BAUD;
    config.factory.baudrate = JY901B_FACTORY_BAUD;
    config.supported_candidates = s_supported_candidates;
    config.supported_candidate_count = (uint8_t)(
        sizeof(s_supported_candidates) / sizeof(s_supported_candidates[0]));
    SILVERSTAR_ASSERT(config.supported_candidate_count + 2U <=
                      SYSTEM_DEVICE_STARTUP_MAX_CANDIDATES,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    config.probe_timeout_ms = JY901B_BAUD_SCAN_DWELL_MS;
    config.stage_timeout_ms = JY901B_STARTUP_STAGE_TIMEOUT_MS;
    config.sample_timeout_ms = JY901B_STARTUP_SAMPLE_TIMEOUT_MS;
    config.operations = &s_operations;
    config.owner = context;
    return (SystemDeviceStartup_Init(&context->controller, &config) ==
            SystemDeviceStartupResult_Ok) ?
        Jy901bStartupResult_Ok : Jy901bStartupResult_ControllerError;
}

void Jy901bStartup_Tick(uint8_t instance, uint32_t now_ms)
{
    if (instance >= PROJECT_JY901B_INSTANCE_COUNT) { return; }
    SystemDeviceStartup_Tick(&s_contexts[instance].controller, now_ms);
}

SystemDeviceStartupState Jy901bStartup_StateGet(uint8_t instance)
{
    return (instance < PROJECT_JY901B_INSTANCE_COUNT) ?
        s_contexts[instance].controller.state :
        SystemDeviceStartupState_Failed;
}

SystemDeviceStartupFailure Jy901bStartup_FailureGet(uint8_t instance)
{
    return (instance < PROJECT_JY901B_INSTANCE_COUNT) ?
        s_contexts[instance].controller.failure :
        SystemDeviceStartupFailure_NotPresent;
}
