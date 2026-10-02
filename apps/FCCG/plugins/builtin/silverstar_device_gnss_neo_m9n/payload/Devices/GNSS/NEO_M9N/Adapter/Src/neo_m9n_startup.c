#include "neo_m9n_startup.h"

#include <stddef.h>
#include <string.h>

#include "neo_m9n_config.h"
#include "neo_m9n_config_keys.h"
#include "neo_m9n_device.h"
#include "platform_memory.h"
#include "platform_time.h"
#include "silverstar_assert.h"

#define NEO_M9N_STARTUP_ITEM_COUNT 23U
#define NEO_M9N_STARTUP_PROBE_TIMEOUT_MS 5000U
#define NEO_M9N_STARTUP_STAGE_TIMEOUT_MS 45000U
#define NEO_M9N_STARTUP_SAMPLE_TIMEOUT_MS 3000U

typedef struct
{
    SystemDeviceStartup controller;
    SystemGnssConfig target;
    uint64_t actual[NEO_M9N_STARTUP_ITEM_COUNT];
    uint8_t instance;
    uint8_t read_index;
    uint8_t read_active;
    uint8_t apply_index;
    uint8_t apply_active;
    uint8_t verify_index;
    uint8_t verify_active;
    uint8_t reconnect_phase;
    uint32_t reconnect_started_ms;
    uint32_t sample_baseline;
    uint32_t signal_settle_started_ms;
    uint16_t signal_settle_ms;
    uint8_t signal_settle_active;
} NeoM9nStartupContext;

/* CPU-only startup state and decoded configuration values. No UART/DMA
 * backend retains this object: writes build a separate local UBX frame and
 * PlatformUart_WriteFrameAsync copies it into its DMA-accessible TX ring.
 * The target owns section/alignment/startup zeroing; targets without a
 * CPU-fast section and Host retain the platform API ordinary-BSS default. */
static PLATFORM_CPU_FAST_BSS NeoM9nStartupContext
    s_contexts[PROJECT_NEO_M9N_INSTANCE_COUNT];

/* The supported UART baud set is finite. The controller deduplicates target
 * and factory baud before walking these remaining declared candidates. */
static const SystemDeviceStartupCandidate s_supported_candidates[] =
{
    {GNSS_UART_BAUD_4800, 1U},
    {GNSS_UART_BAUD_9600, 1U},
    {GNSS_UART_BAUD_19200, 1U},
    {GNSS_UART_BAUD_38400, 1U},
    {GNSS_UART_BAUD_57600, 1U},
    {GNSS_UART_BAUD_115200, 1U},
    {GNSS_UART_BAUD_230400, 1U},
    {GNSS_UART_BAUD_460800, 1U},
    {GNSS_UART_BAUD_576000, 1U},
    {GNSS_UART_BAUD_921600, 1U}
};

static const uint32_t s_item_keys[NEO_M9N_STARTUP_ITEM_COUNT] =
{
    GNSS_CFG_UART1_BAUDRATE, /* Apply communication changes last. */
    GNSS_CFG_UART1INPROT_UBX, GNSS_CFG_UART1INPROT_NMEA,
    GNSS_CFG_UART1INPROT_RTCM3X, GNSS_CFG_UART1OUTPROT_UBX,
    GNSS_CFG_UART1OUTPROT_NMEA, GNSS_CFG_MSGOUT_NAV_PVT_UART1,
    GNSS_CFG_RATE_MEAS, GNSS_CFG_RATE_NAV, GNSS_CFG_RATE_TIMEREF,
    GNSS_CFG_NAVSPG_DYNMODEL,
    GNSS_CFG_SIGNAL_GPS_ENA, GNSS_CFG_SIGNAL_GPS_L1CA_ENA,
    GNSS_CFG_SIGNAL_SBAS_ENA, GNSS_CFG_SIGNAL_SBAS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GAL_ENA, GNSS_CFG_SIGNAL_GAL_E1_ENA,
    GNSS_CFG_SIGNAL_BDS_ENA, GNSS_CFG_SIGNAL_BDS_B1_ENA,
    GNSS_CFG_SIGNAL_QZSS_ENA, GNSS_CFG_SIGNAL_QZSS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GLO_ENA, GNSS_CFG_SIGNAL_GLO_L1_ENA
};

static uint8_t NeoM9nStartup_DynamicModelGet(
    SystemGnssDynamicModel model)
{
    switch (model)
    {
        case SYSTEM_GNSS_DYNAMIC_MODEL_STATIONARY:
            return GNSS_DYNMODEL_STATIONARY;
        case SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_1G:
            return GNSS_DYNMODEL_AIRBORNE_1G;
        case SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_2G:
            return GNSS_DYNMODEL_AIRBORNE_2G;
        case SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G:
            return GNSS_DYNMODEL_AIRBORNE_4G;
        case SYSTEM_GNSS_DYNAMIC_MODEL_PORTABLE:
        default:
            return GNSS_DYNMODEL_PORTABLE;
    }
}

static uint64_t NeoM9nStartup_ConstellationValueGet(
    uint8_t index, uint32_t mask)
{
    uint32_t constellation = 0U;

    switch (index)
    {
        case 11U:
        case 12U: constellation = SYSTEM_GNSS_CONSTELLATION_GPS; break;
        case 15U:
        case 16U: constellation = SYSTEM_GNSS_CONSTELLATION_GALILEO; break;
        case 17U:
        case 18U: constellation = SYSTEM_GNSS_CONSTELLATION_BDS; break;
        case 21U:
        case 22U: constellation = SYSTEM_GNSS_CONSTELLATION_GLONASS; break;
        default: break;
    }
    return (uint64_t)((mask & constellation) != 0U);
}

static GnssNeoM9nConfigItem NeoM9nStartup_ItemGet(
    const NeoM9nStartupContext *context, uint8_t index)
{
    GnssNeoM9nConfigItem item = {0U};
    uint8_t out_ubx;
    uint8_t out_nmea;

    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(index < NEO_M9N_STARTUP_ITEM_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    out_ubx = (uint8_t)(
        context->target.output_protocol != SYSTEM_GNSS_OUTPUT_PROTOCOL_NMEA);
    out_nmea = (uint8_t)(
        context->target.output_protocol != SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX);

    item.key = s_item_keys[index];
    item.value_len = (uint8_t)((item.key >> 28U) == 4U ? 4U :
        ((item.key >> 28U) == 3U ? 2U : 1U));
    switch (index)
    {
        case 0U: item.value = GNSS_DEFAULT_BAUDRATE; break;
        case 1U:
        case 2U:
        case 3U: item.value = 1U; break;
        case 4U: item.value = out_ubx; break;
        case 5U: item.value = out_nmea; break;
        case 6U:
            item.value = (uint64_t)(
                (context->target.enabled_message_mask &
                 SYSTEM_GNSS_MESSAGE_NAV_PVT) != 0U);
            break;
        case 7U:
            item.value = 1000U / context->target.navigation_rate_hz;
            break;
        case 8U:
        case 9U: item.value = 1U; break;
        case 10U:
            item.value = NeoM9nStartup_DynamicModelGet(
                context->target.dynamic_model);
            break;
        default:
            item.value = NeoM9nStartup_ConstellationValueGet(index,
                context->target.constellation_mask);
            break;
    }
    return item;
}

static SystemDeviceStartupStepResult NeoM9nStartup_ProbeStart(
    void *owner, const SystemDeviceStartupCandidate *candidate)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    GnssNeoM9nProbeStartResult result = GnssNeoM9n_ProbeStart(
        context->instance, candidate->baudrate);

    if (result == GnssNeoM9nProbeStartResult_Busy)
    { return SystemDeviceStartupStep_Pending; }
    return (result == GnssNeoM9nProbeStartResult_Ok) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Failed;
}

static SystemDeviceStartupStepResult NeoM9nStartup_ProbePoll(void *owner)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    GnssNeoM9nProbePollResult result = GnssNeoM9n_ProbePoll(
        context->instance);

    if (result == GnssNeoM9nProbePollResult_Pending)
    { return SystemDeviceStartupStep_Pending; }
    return (result == GnssNeoM9nProbePollResult_Identified) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Failed;
}

static SystemDeviceStartupStepResult NeoM9nStartup_ItemReadStep(
    NeoM9nStartupContext *context, uint8_t *index, uint8_t *active,
    uint64_t *values, uint8_t compare_target)
{
    GnssNeoM9nConfigItem actual;
    GnssNeoM9nConfigItem expected;
    GnssNeoM9nItemStartResult start_result;
    GnssNeoM9nItemPollResult poll_result;

    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(index, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(active, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(values, uint64_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    if (*index >= NEO_M9N_STARTUP_ITEM_COUNT)
    { return SystemDeviceStartupStep_Ok; }
    expected = NeoM9nStartup_ItemGet(context, *index);
    if (*active == 0U)
    {
        start_result = GnssNeoM9n_ItemReadStart(context->instance,
            expected.key);
        if (start_result == GnssNeoM9nItemStartResult_Busy)
        { return SystemDeviceStartupStep_Pending; }
        if (start_result != GnssNeoM9nItemStartResult_Ok)
        { return SystemDeviceStartupStep_Failed; }
        *active = 1U;
        return SystemDeviceStartupStep_Pending;
    }
    poll_result = GnssNeoM9n_ItemReadPoll(context->instance, &actual);
    if (poll_result == GnssNeoM9nItemPollResult_Pending)
    { return SystemDeviceStartupStep_Pending; }
    *active = 0U;
    if ((poll_result != GnssNeoM9nItemPollResult_Complete) ||
        (actual.key != expected.key) ||
        (actual.value_len != expected.value_len) ||
        ((compare_target != 0U) && (actual.value != expected.value)))
    { return SystemDeviceStartupStep_Failed; }
    values[*index] = actual.value;
    (*index)++;
    return (*index == NEO_M9N_STARTUP_ITEM_COUNT) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult NeoM9nStartup_ConfigRead(
    void *owner, uint32_t *difference_mask)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    SystemDeviceStartupStepResult result = NeoM9nStartup_ItemReadStep(
        context, &context->read_index, &context->read_active,
        context->actual, 0U);
    uint8_t index;

    if (result != SystemDeviceStartupStep_Ok) { return result; }
    *difference_mask = 0U;
    for (index = 0U; index < NEO_M9N_STARTUP_ITEM_COUNT; index++)
    {
        GnssNeoM9nConfigItem expected = NeoM9nStartup_ItemGet(
            context, index);
        if (context->actual[index] != expected.value)
        { *difference_mask |= 1UL << index; }
    }
    return SystemDeviceStartupStep_Ok;
}

static uint8_t NeoM9nStartup_SignalSettling(NeoM9nStartupContext *context)
{
    if (context->signal_settle_active == 0U) { return 0U; }
    if ((uint32_t)(PlatformTime_Ms() - context->signal_settle_started_ms) <
        context->signal_settle_ms) { return 1U; }
    context->signal_settle_active = 0U;
    return 0U;
}

static void NeoM9nStartup_SignalSettleStart(NeoM9nStartupContext *context,
    uint32_t key)
{
    GnssNeoM9nIdentityDiagnostics identity;
    if ((key & 0x0FFF0000UL) != 0x00310000UL) { return; }
    if (GnssNeoM9n_IdentityDiagnosticsGet(context->instance, &identity) !=
        GnssNeoM9nIdentityOk) { return; }
    context->signal_settle_ms = identity.signal_settle_ms;
    context->signal_settle_started_ms = PlatformTime_Ms();
    context->signal_settle_active = (uint8_t)(identity.signal_settle_ms != 0U);
}

static SystemDeviceStartupStepResult NeoM9nStartup_ConfigApply(
    void *owner, uint32_t difference_mask, uint8_t *reconnect_required)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    GnssNeoM9nConfigItem item;
    GnssNeoM9nItemStartResult start_result;
    GnssNeoM9nItemPollResult poll_result;
    uint8_t index;

    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(reconnect_required, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->apply_index <= NEO_M9N_STARTUP_ITEM_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);

    if (NeoM9nStartup_SignalSettling(context) != 0U)
    { return SystemDeviceStartupStep_Pending; }
    if (context->apply_index >= NEO_M9N_STARTUP_ITEM_COUNT)
    {
        *reconnect_required = (uint8_t)((difference_mask & 1UL) != 0U);
        return SystemDeviceStartupStep_Ok;
    }
    index = (context->apply_index ==
        (NEO_M9N_STARTUP_ITEM_COUNT - 1U)) ?
        0U : (uint8_t)(context->apply_index + 1U);
    if ((difference_mask & (1UL << index)) == 0U)
    {
        context->apply_index++;
        return SystemDeviceStartupStep_Pending;
    }
    item = NeoM9nStartup_ItemGet(context, index);
    if (context->apply_active == 0U)
    {
        start_result = GnssNeoM9n_ItemWriteStart(context->instance, &item);
        if (start_result == GnssNeoM9nItemStartResult_Busy)
        { return SystemDeviceStartupStep_Pending; }
        if (start_result != GnssNeoM9nItemStartResult_Ok)
        { return SystemDeviceStartupStep_Failed; }
        context->apply_active = 1U;
        return SystemDeviceStartupStep_Pending;
    }
    poll_result = GnssNeoM9n_ItemWritePoll(context->instance);
    if (poll_result == GnssNeoM9nItemPollResult_Pending)
    { return SystemDeviceStartupStep_Pending; }
    context->apply_active = 0U;
    if ((poll_result != GnssNeoM9nItemPollResult_Complete) &&
        !((index == 0U) &&
          ((poll_result == GnssNeoM9nItemPollResult_Timeout) ||
           (poll_result == GnssNeoM9nItemPollResult_IoError))))
    { return SystemDeviceStartupStep_Failed; }
    if (poll_result == GnssNeoM9nItemPollResult_Complete)
    { NeoM9nStartup_SignalSettleStart(context, item.key); }
    context->apply_index++;
    return SystemDeviceStartupStep_Pending;
}

static SystemDeviceStartupStepResult NeoM9nStartup_Reconnect(void *owner)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    GnssNeoM9nProbeStartResult start_result;
    GnssNeoM9nProbePollResult poll_result;

    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT(context->reconnect_phase <= 2U,
        SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);

    if (context->reconnect_phase == 0U)
    {
        context->reconnect_started_ms = PlatformTime_Ms();
        context->reconnect_phase = 1U;
        return SystemDeviceStartupStep_Pending;
    }
    if (context->reconnect_phase == 1U)
    {
        if ((uint32_t)(PlatformTime_Ms() -
                context->reconnect_started_ms) <
            GNSS_UART_CONFIG_SETTLE_MS)
        { return SystemDeviceStartupStep_Pending; }
        start_result = GnssNeoM9n_ProbeStart(context->instance,
            GNSS_DEFAULT_BAUDRATE);
        if (start_result == GnssNeoM9nProbeStartResult_Busy)
        { return SystemDeviceStartupStep_Pending; }
        if (start_result != GnssNeoM9nProbeStartResult_Ok)
        { return SystemDeviceStartupStep_Failed; }
        context->reconnect_phase = 2U;
        return SystemDeviceStartupStep_Pending;
    }
    poll_result = GnssNeoM9n_ProbePoll(context->instance);
    if (poll_result == GnssNeoM9nProbePollResult_Pending)
    { return SystemDeviceStartupStep_Pending; }
    return (poll_result == GnssNeoM9nProbePollResult_Identified) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Failed;
}

static SystemDeviceStartupStepResult NeoM9nStartup_ConfigVerify(void *owner)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    GnssNeoM9nData data;
    SystemDeviceStartupStepResult result = NeoM9nStartup_ItemReadStep(
        context, &context->verify_index, &context->verify_active,
        context->actual, 1U);

    if (result != SystemDeviceStartupStep_Ok) { return result; }
    (void)GnssNeoM9n_GetData(context->instance, &data);
    context->sample_baseline = data.pvtSequence;
    return SystemDeviceStartupStep_Ok;
}

static SystemDeviceStartupStepResult NeoM9nStartup_SamplePoll(void *owner)
{
    NeoM9nStartupContext *context = (NeoM9nStartupContext *)owner;
    GnssNeoM9nData data;

    (void)GnssNeoM9n_Process(context->instance, PlatformTime_Ms());
    (void)GnssNeoM9n_GetData(context->instance, &data);
    return (data.pvtSequence > context->sample_baseline) ?
        SystemDeviceStartupStep_Ok : SystemDeviceStartupStep_Pending;
}

static const SystemDeviceStartupOperations s_operations =
{
    NeoM9nStartup_ProbeStart,
    NeoM9nStartup_ProbePoll,
    NeoM9nStartup_ConfigRead,
    NeoM9nStartup_ConfigApply,
    NeoM9nStartup_Reconnect,
    NeoM9nStartup_ConfigVerify,
    NeoM9nStartup_SamplePoll
};

NeoM9nStartupResult NeoM9nStartup_Init(
    uint8_t instance, const SystemGnssConfig *target)
{
    NeoM9nStartupContext *context;
    SystemDeviceStartupConfig config;

    if ((instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) || (target == NULL) ||
        (target->navigation_rate_hz == 0U) ||
        (target->navigation_rate_hz > GNSS_MAX_RATE_HZ) ||
        ((1000U % target->navigation_rate_hz) != 0U) ||
        (target->constellation_mask == 0U) ||
        (target->output_protocol > SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX_AND_NMEA))
    { return NeoM9nStartupResult_InvalidArgument; }
    context = &s_contexts[instance];
    SILVERSTAR_ASSERT_OBJECT(context, NeoM9nStartupContext,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    SILVERSTAR_ASSERT_OBJECT(target, SystemGnssConfig,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    (void)memset(context, 0, sizeof(*context));
    context->instance = instance;
    context->target = *target;
    (void)memset(&config, 0, sizeof(config));
    config.persistence = SystemDeviceStartupPersistence_Persistent;
    config.target.baudrate = GNSS_DEFAULT_BAUDRATE;
    config.target.protocol = 1U;
    config.factory.baudrate = GNSS_FACTORY_BAUDRATE;
    config.factory.protocol = 1U;
    config.supported_candidates = s_supported_candidates;
    config.supported_candidate_count = (uint8_t)(
        sizeof(s_supported_candidates) / sizeof(s_supported_candidates[0]));
    config.probe_timeout_ms = NEO_M9N_STARTUP_PROBE_TIMEOUT_MS;
    config.stage_timeout_ms = NEO_M9N_STARTUP_STAGE_TIMEOUT_MS;
    config.sample_timeout_ms = NEO_M9N_STARTUP_SAMPLE_TIMEOUT_MS;
    config.operations = &s_operations;
    config.owner = context;
    return (SystemDeviceStartup_Init(&context->controller, &config) ==
        SystemDeviceStartupResult_Ok) ?
        NeoM9nStartupResult_Ok : NeoM9nStartupResult_ControllerError;
}

void NeoM9nStartup_Tick(uint8_t instance, uint32_t now_ms)
{
    if (instance >= PROJECT_NEO_M9N_INSTANCE_COUNT) { return; }
    SystemDeviceStartup_Tick(&s_contexts[instance].controller, now_ms);
}

SystemDeviceStartupState NeoM9nStartup_StateGet(uint8_t instance)
{
    return (instance < PROJECT_NEO_M9N_INSTANCE_COUNT) ?
        s_contexts[instance].controller.state :
        SystemDeviceStartupState_Failed;
}

SystemDeviceStartupFailure NeoM9nStartup_FailureGet(uint8_t instance)
{
    return (instance < PROJECT_NEO_M9N_INSTANCE_COUNT) ?
        s_contexts[instance].controller.failure :
        SystemDeviceStartupFailure_NotPresent;
}
