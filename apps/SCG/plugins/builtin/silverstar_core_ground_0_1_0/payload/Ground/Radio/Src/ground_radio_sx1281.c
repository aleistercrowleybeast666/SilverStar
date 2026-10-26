#include "ground_radio.h"

#include <string.h>
#include <stddef.h>

#include "ground_radio_config.h"
#include "ground_radio_activity.h"
#include "project_resources.h"
#include "platform_time.h"
#include "silverstar_assert.h"
#include "sx1281_device.h"

/* Single instance folds to the legacy literal zero. One bare-metal owner,
 * no aggregation, no old queue copied to a replacement, no backwards switch. */
#define GROUND_RADIO_INSTANCE ((uint8_t)((PROJECT_SX1281_INSTANCE_COUNT == 1U) ? 0U : s_active))
static uint8_t s_active = GROUND_RADIO_INITIAL_INSTANCE;
static uint8_t s_offline_seen;
static uint8_t s_exhausted;
static uint32_t s_offline_ms;

_Static_assert((PROJECT_SX1281_INSTANCE_COUNT >= 1U) &&
    (GROUND_RADIO_INITIAL_INSTANCE < PROJECT_SX1281_INSTANCE_COUNT),
    "Ground initial module must exist");

#define GROUND_TM_RETIRED_BOUND 16U
static uint32_t s_tm_session;
static uint32_t s_tm_retired[GROUND_TM_RETIRED_BOUND];
static uint8_t s_tm_retired_next;
static uint64_t s_tm_phase_floor_us;
/* Until a current preflight CAP is received, a late joining GS is passive. */
static uint8_t s_tm_passive = 1U;

static uint64_t GroundRadio_TmUnsignedGet(const uint8_t *data, uint8_t width)
{
    uint64_t value = 0ULL;
    SILVERSTAR_ASSERT((data != NULL) && (width > 0U) && (width <= 8U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    for (uint8_t index = 0U; index < width; index++)
    { value |= (uint64_t)data[index] << (8U * index); }
    return value;
}

static void GroundRadio_TmObserve(const uint8_t *data, uint8_t length)
{
    uint32_t session;
    uint64_t occurred_us = 0ULL;
    uint8_t type;
    if ((length < 8U) || (data[0] != 1U) || ((data[1] & 0x80U) != 0U)) { return; }
    session = (uint32_t)GroundRadio_TmUnsignedGet(&data[4], 4U);
    if (session == 0U) { return; }
    type = data[1];
    /* Transport policy only, not a second decoder. Exact qualifying message
     * lengths/fields are explicit; opaque raw forwarding remains unchanged. */
    if (!(((type == 0x12U) && (length == 24U) && (data[8] == 0U) &&
           (data[9] == 1U) && ((data[10] & 0xF8U) == 0U) &&
           ((data[11] & 0xF0U) == 0U) && (data[12] != 0U) &&
           (GroundRadio_TmUnsignedGet(&data[13], 2U) != 0U) && (data[15] == 1U)) ||
          ((type == 0x10U) && (length == 56U)) ||
          ((type == 0x40U) && (length == 16U) && (data[10] == 1U) && (data[11] == 0U)) ||
          ((type == 0x20U) && (length == 32U) &&
           (GroundRadio_TmUnsignedGet(&data[8], 4U) != 0U)))) { return; }
    if (session != s_tm_session)
    {
        for (uint8_t index = 0U; index < GROUND_TM_RETIRED_BOUND; index++)
        { if (s_tm_retired[index] == session) { return; } }
        s_tm_retired[s_tm_retired_next] = s_tm_session;
        s_tm_retired_next = (uint8_t)((s_tm_retired_next + 1U) % GROUND_TM_RETIRED_BOUND);
        s_tm_session = session; s_tm_passive = 1U; s_tm_phase_floor_us = 0ULL;
    }
    if (type == 0x12U)
    {
        if (GroundRadio_TmUnsignedGet(&data[16], 8U) > s_tm_phase_floor_us)
        { s_tm_passive = 0U; }
        return;
    }
    if (type == 0x20U)
    {
        uint16_t code = (uint16_t)GroundRadio_TmUnsignedGet(&data[20], 2U);
        if ((code != 3U) && (code != 4U) && (code != 5U) && (code != 6U) &&
            (code != 0x100U) && (code != 0x101U)) { return; }
        occurred_us = GroundRadio_TmUnsignedGet(&data[12], 8U);
    }
    else { occurred_us = GroundRadio_TmUnsignedGet(&data[(type == 0x40U) ? 12U : 8U], 4U) * 1000ULL; }
    if (occurred_us > s_tm_phase_floor_us) { s_tm_phase_floor_us = occurred_us; }
    s_tm_passive = 1U;
}

static GroundRadioResult GroundRadio_TmModeApply(uint8_t instance)
{
    LoraModeSetResult result = Lora_OperatingModeSet(instance,
        (s_tm_passive != 0U) ? LoraOperatingMode_ReceiveOnly : LoraOperatingMode_HalfDuplex);
    if (result == LoraModeSetResult_Ok) { return GROUND_RADIO_OK; }
    return (result == LoraModeSetResult_Busy) ? GROUND_RADIO_BUSY : GROUND_RADIO_ERROR;
}

static GroundRadioResult GroundRadio_InstanceInit(uint8_t instance)
{
    if (Lora_Init(instance) != LORA_INIT_OK) { return GROUND_RADIO_ERROR; }
    if (Lora_ApplyDefaultConfig(instance) != LORA_CONFIG_OK) { return GROUND_RADIO_ERROR; }
    if (Lora_ScheduleRoleSet(instance, LoraScheduleRole_Ground) != LoraScheduleRoleResult_Ok)
    { return GROUND_RADIO_ERROR; }
    if (GROUND_TM_S_ENABLED != 0U)
    {
    if (GroundRadio_TmModeApply(instance) != GROUND_RADIO_OK) { return GROUND_RADIO_ERROR; }
    }
    Lora_StartRx(instance);
    return GROUND_RADIO_OK;
}

static GroundRadioResult GroundRadio_StartFrom(uint8_t start)
{
    uint8_t instance;
    SILVERSTAR_ASSERT(start <= PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    for (instance = start; instance < PROJECT_SX1281_INSTANCE_COUNT; instance++)
    {
        s_active = instance;
        if (GroundRadio_InstanceInit(instance) == GROUND_RADIO_OK)
        { s_offline_seen = 0U; return GROUND_RADIO_OK; }
        if (Lora_Deactivate(instance) != LoraDeactivateResult_Ok)
        { s_exhausted = 1U; return GROUND_RADIO_ERROR; }
    }
    s_exhausted = 1U;
    return GROUND_RADIO_ERROR;
}

static GroundRadioResult GroundRadio_ColdStart(void)
{
    uint8_t instance;
    /* MCU restart does not prove that another powered radio stopped. Hold
     * every module in reset before releasing the sole selected owner. */
    for (instance = 0U; instance < PROJECT_SX1281_INSTANCE_COUNT; instance++)
    {
        if (Lora_Deactivate(instance) != LoraDeactivateResult_Ok)
        { s_exhausted = 1U; return GROUND_RADIO_ERROR; }
    }
    return GroundRadio_StartFrom(GROUND_RADIO_INITIAL_INSTANCE);
}

uint8_t GroundRadio_MetricsSupportedGet(void) { return 1U; }

GroundRadioResult GroundRadio_Init(void)
{
    s_active = GROUND_RADIO_INITIAL_INSTANCE;
    s_offline_seen = 0U;
    s_exhausted = 0U;
    if (GROUND_ACTIVITY_ENABLED != 0U) { GroundRadioActivity_Init(0U, 0U); }
    if (PROJECT_SX1281_INSTANCE_COUNT != 1U)
    { return GroundRadio_ColdStart(); }
    if (Lora_Init(GROUND_RADIO_INSTANCE) != LORA_INIT_OK)
    {
        return GROUND_RADIO_ERROR;
    }
    if (Lora_ApplyDefaultConfig(GROUND_RADIO_INSTANCE) != LORA_CONFIG_OK)
    {
        return GROUND_RADIO_ERROR;
    }
    if (Lora_ScheduleRoleSet(GROUND_RADIO_INSTANCE, LoraScheduleRole_Ground) !=
        LoraScheduleRoleResult_Ok)
    {
        return GROUND_RADIO_ERROR;
    }
    if (GROUND_TM_S_ENABLED != 0U)
    {
    if (GroundRadio_TmModeApply(GROUND_RADIO_INSTANCE) != GROUND_RADIO_OK) { return GROUND_RADIO_ERROR; }
    }
    Lora_StartRx(GROUND_RADIO_INSTANCE);
    return GROUND_RADIO_OK;
}

static void GroundRadio_FailoverProcess(uint32_t now_ms)
{
    LoraDebugSnapshot snapshot;
    SILVERSTAR_ASSERT(s_active < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_offline_seen <= 1U) && (s_exhausted <= 1U),
        SILVERSTAR_ASSERT_MODULE_SYSTEM, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_exhausted != 0U) { return; }
    Lora_GetDebugSnapshot(s_active, &snapshot);
    /* Only the driver's NOT_INIT/offline result qualifies. Quiet RF, missing
     * ACK/CAPABILITY, RX rate and normal timed-RX expiry are not predicates. */
    if (snapshot.initialized != 0U) { s_offline_seen = 0U; return; }
    if (s_offline_seen == 0U)
    {
        s_offline_seen = 1U;
        s_offline_ms = now_ms;
        if (GROUND_ACTIVITY_ENABLED != 0U)
        { GroundRadioActivity_Init(snapshot.stats.tx_ok, snapshot.stats.rx_ok); }
        return;
    }
    if ((uint32_t)(now_ms - s_offline_ms) < GROUND_RADIO_FAILOVER_HOLD_MS) { return; }
    if (Lora_Deactivate(s_active) != LoraDeactivateResult_Ok)
    { s_exhausted = 1U; return; }
    if (GroundRadio_StartFrom((uint8_t)(s_active + 1U)) != GROUND_RADIO_OK)
    { s_exhausted = 1U; }
    if (GROUND_ACTIVITY_ENABLED != 0U) { GroundRadioActivity_Init(0U, 0U); }
}

void GroundRadio_Process(void)
{
    Lora_Process(GROUND_RADIO_INSTANCE);
    if (GROUND_TM_S_ENABLED != 0U)
    {
    /* Desired policy survives PC reconnect and failover. An in-flight uplink
     * may finish; further enqueue is already blocked while mode set is BUSY. */
    if (s_exhausted == 0U)
    {
        GroundRadioResult result = GroundRadio_TmModeApply(GROUND_RADIO_INSTANCE);
        if (result == GROUND_RADIO_ERROR) { s_offline_seen = 1U; }
    }
    }
    if (PROJECT_SX1281_INSTANCE_COUNT > 1U)
    { GroundRadio_FailoverProcess(PlatformTime_Ms()); }
    if (GROUND_ACTIVITY_ENABLED != 0U)
    {
        LoraStats stats;
        Lora_GetStats(GROUND_RADIO_INSTANCE, &stats);
        GroundRadioActivity_Process(PlatformTime_Ms(), stats.tx_ok, stats.rx_ok);
    }
}

uint8_t GroundRadio_ActiveInstanceGet(void) { return GROUND_RADIO_INSTANCE; }

GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length)
{
    LoraTxEnqueueResult result;
    if (GROUND_TM_S_ENABLED != 0U)
    {
    if (s_tm_passive != 0U) { return GROUND_RADIO_BUSY; }
    }
    result = Lora_TxEnqueue(GROUND_RADIO_INSTANCE, data, length);
    if (result == LORA_TX_ENQUEUE_OK)
    {
        return GROUND_RADIO_OK;
    }
    return (result == LORA_TX_ENQUEUE_QUEUE_FULL) ? GROUND_RADIO_BUSY : GROUND_RADIO_ERROR;
}

GroundRadioResult GroundRadio_RxDequeue(
    uint8_t *data, uint8_t *length, int8_t *rssi_dbm, int8_t *snr_db)
{
    LoraRxDequeueResult result = Lora_RxDequeue(
        GROUND_RADIO_INSTANCE, data, length, rssi_dbm, snr_db);
    if (result == LORA_RX_DEQUEUE_OK)
    {
    if (GROUND_TM_S_ENABLED != 0U)
    {
        GroundRadio_TmObserve(data, *length);
    }
        return GROUND_RADIO_OK;
    }
    return (result == LORA_RX_DEQUEUE_EMPTY) ? GROUND_RADIO_EMPTY : GROUND_RADIO_ERROR;
}

void GroundRadio_StatsGet(GroundRadioStats *stats)
{
    LoraStats source;
    if (stats == NULL)
    {
        return;
    }
    memset(&source, 0, sizeof(source));
    Lora_GetStats(GROUND_RADIO_INSTANCE, &source);
    stats->radio_state = (uint8_t)source.radio_state;
    stats->tx_ok = source.tx_ok;
    stats->rx_ok = source.rx_ok;
    stats->rx_crc_error = source.rx_crc_error;
    stats->tx_timeout = source.tx_timeout;
    stats->rx_timeout = source.rx_timeout;
    stats->tx_dropped = source.tx_dropped;
    stats->rx_dropped = source.rx_dropped;
}
