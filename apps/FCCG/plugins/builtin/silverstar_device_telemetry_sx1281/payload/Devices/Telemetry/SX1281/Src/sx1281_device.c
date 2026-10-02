#include "sx1281_device.h"

#include <string.h>

#include "project_resources.h"
#include "silverstar_assert.h"
#include "platform_critical.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "sx1280.h"
#include "sx1281_bus.h"

typedef struct
{
    uint8_t len;
    uint8_t data[LORA_MAX_PAYLOAD_LEN];
} LoraTxPacket;

typedef struct
{
    uint8_t len;
    int8_t rssi;
    int8_t snr;
    uint8_t data[LORA_MAX_PAYLOAD_LEN];
} LoraRxPacket;

typedef enum
{
    LoraControlStateIdle = 0U,
    LoraControlStateSubmitted,
    LoraControlStateActive,
    LoraControlStateComplete
} LoraControlState;

typedef struct
{
    LoraControlState state;
    LoraControlOperation operation;
    uint32_t transaction_id;
    uint32_t next_transaction_id;
    uint32_t submitted_ms;
    uint32_t timeout_ms;
    uint8_t auto_release;
    LoraControlResult result;
} LoraControlTransaction;

#define LORA_DIAG_REFRESH_PERIOD_MS 100U
#define LORA_CONTROL_DEFAULT_TIMEOUT_MS 250U

typedef struct
{
    volatile uint8_t tx_done_flag;
    volatile uint8_t rx_done_flag;
    volatile uint8_t tx_timeout_flag;
    volatile uint8_t rx_timeout_flag;
    volatile uint8_t rx_error_flag;
    volatile IrqErrorCode_t rx_error_code;
    volatile uint8_t inited;
    volatile uint8_t tx_busy;
    volatile uint8_t radio_in_rx;
    uint32_t rx_started_ms;
    uint8_t rx_tmp_buf[LORA_MAX_PAYLOAD_LEN];
    PacketStatus_t pkt_status;
    ModulationParams_t mod_params;
    PacketParams_t pkt_params;
    LoraStats stats;
    LoraDiagSnapshot diag;
    uint16_t diag_counted_raw_irq;
    LoraChipStatus chip_status;
    LoraControlTransaction control_transaction;
    uint32_t diag_last_refresh_ms;
    uint8_t cached_busy_gpio;
    uint8_t cached_dio1_gpio;
    LoraTxPacket tx_queue[LORA_TX_QUEUE_DEPTH];
    uint8_t tx_head;
    uint8_t tx_tail;
    uint8_t tx_count;
    uint8_t tx_control_count;
    uint8_t tx_control_burst;
    uint8_t rx_window_active;
    uint8_t schedule_role;
    uint8_t rx_packet_active;
    uint32_t rx_packet_started_ms;
    uint32_t tx_ids[LORA_TX_QUEUE_DEPTH];
    uint32_t next_tx_id;
    uint32_t active_tx_id;
    uint32_t completed_tx_id;
    uint32_t completed_tx_ms;
    LoraTxQueryResult completed_tx_result;
    LoraRxPacket rx_queue[LORA_RX_QUEUE_DEPTH];
    uint8_t rx_head;
    uint8_t rx_tail;
    uint8_t rx_count;
} Sx1281Context;

_Static_assert((LORA_TX_NORMAL_QUEUE_DEPTH + LORA_TX_CONTROL_QUEUE_DEPTH) == LORA_TX_QUEUE_DEPTH,
    "TX lane capacities must fill the existing bounded queue");
_Static_assert(LORA_TX_CONTROL_BURST_MAX > 0U, "control fairness burst must be positive");
_Static_assert(LORA_TX_TIMEOUT_STEP == RADIO_TICK_SIZE_1000_US, "TX watchdog requires a1ms timeout step");
static Sx1281Context s_contexts[PROJECT_SX1281_INSTANCE_COUNT];

_Static_assert(PROJECT_SX1281_INSTANCE_COUNT <=
               PROJECT_SX1281_INSTANCE_COUNT_MAX,
               "SX1281 context count exceeds generated resource bound");
_Static_assert((LORA_TX_QUEUE_DEPTH > 0U) && (LORA_TX_QUEUE_DEPTH <= UINT8_MAX),
               "TX queue counters must represent the configured capacity");
_Static_assert((LORA_RX_QUEUE_DEPTH > 0U) && (LORA_RX_QUEUE_DEPTH <= UINT8_MAX),
               "RX queue counters must represent the configured capacity");

#define s_tx_done_flag        (s_contexts[instance].tx_done_flag)
#define s_rx_done_flag        (s_contexts[instance].rx_done_flag)
#define s_tx_timeout_flag     (s_contexts[instance].tx_timeout_flag)
#define s_rx_timeout_flag     (s_contexts[instance].rx_timeout_flag)
#define s_rx_error_flag       (s_contexts[instance].rx_error_flag)
#define s_rx_error_code       (s_contexts[instance].rx_error_code)
#define s_inited              (s_contexts[instance].inited)
#define s_tx_busy             (s_contexts[instance].tx_busy)
#define s_radio_in_rx         (s_contexts[instance].radio_in_rx)
#define s_rx_started_ms       (s_contexts[instance].rx_started_ms)
#define s_rx_tmp_buf          (s_contexts[instance].rx_tmp_buf)
#define s_pkt_status          (s_contexts[instance].pkt_status)
#define s_mod_params          (s_contexts[instance].mod_params)
#define s_pkt_params          (s_contexts[instance].pkt_params)
#define s_stats               (s_contexts[instance].stats)
#define s_diag                (s_contexts[instance].diag)
#define s_diag_counted_raw_irq (s_contexts[instance].diag_counted_raw_irq)
#define s_chip_status         (s_contexts[instance].chip_status)
#define s_control_transaction (s_contexts[instance].control_transaction)
#define s_diag_last_refresh_ms (s_contexts[instance].diag_last_refresh_ms)
#define s_cached_busy_gpio    (s_contexts[instance].cached_busy_gpio)
#define s_cached_dio1_gpio    (s_contexts[instance].cached_dio1_gpio)
#define s_tx_queue            (s_contexts[instance].tx_queue)
#define s_tx_head             (s_contexts[instance].tx_head)
#define s_tx_tail             (s_contexts[instance].tx_tail)
#define s_tx_count            (s_contexts[instance].tx_count)
#define s_tx_control_count    (s_contexts[instance].tx_control_count)
#define s_tx_control_burst    (s_contexts[instance].tx_control_burst)
#define s_rx_queue            (s_contexts[instance].rx_queue)
#define s_rx_head             (s_contexts[instance].rx_head)
#define s_rx_tail             (s_contexts[instance].rx_tail)
#define s_rx_count            (s_contexts[instance].rx_count)

static void Lora_OnTxDone(uint8_t instance);
static void Lora_OnRxDone(uint8_t instance);
static void Lora_OnTxTimeout(uint8_t instance);
static void Lora_OnRxTimeout(uint8_t instance);
static void Lora_OnRxError(uint8_t instance, IrqErrorCode_t errCode);
static void Lora_DiagRecordIrq(uint8_t instance, uint16_t raw_irq);
static void Lora_DiagSetDioIrqParams(uint8_t instance, uint16_t irq_mask,
                                     uint16_t dio1_mask,
                                     uint16_t dio2_mask,
                                     uint16_t dio3_mask);
static void Lora_ControlProcess(uint8_t instance);
static void Lora_IrqProcess(uint8_t instance, uint16_t raw_irq);
static LoraControlSubmitResult Lora_ControlSubmitInternal(uint8_t instance,
    LoraControlOperation operation,
    uint32_t timeout_ms,
    uint8_t auto_release,
    uint32_t *transaction_id);
static LoraDiagResult Lora_ForceRxContinuousDirect(uint8_t instance);

static PlatformCriticalState Lora_IrqLock(void)
{
    return PlatformCritical_Enter();
}

static void Lora_IrqUnlock(PlatformCriticalState state)
{
    PlatformCritical_Exit(state);
}

/* Caller holds the IRQ lock: indices/count are one coherent ring snapshot. */
static void Lora_TxQueueAssert(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_tx_head < LORA_TX_QUEUE_DEPTH) &&
        (s_tx_tail < LORA_TX_QUEUE_DEPTH),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_tx_count <= LORA_TX_QUEUE_DEPTH,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    uint8_t normal_capacity = (s_contexts[instance].schedule_role == LoraScheduleRole_Ground) ?
        LORA_TX_QUEUE_DEPTH : LORA_TX_NORMAL_QUEUE_DEPTH;
    SILVERSTAR_ASSERT(s_contexts[instance].schedule_role <= LoraScheduleRole_Ground,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((s_tx_control_count <= LORA_TX_CONTROL_QUEUE_DEPTH) &&
        (s_tx_control_count <= s_tx_count) &&
        (((uint32_t)s_tx_count - (uint32_t)s_tx_control_count) <= normal_capacity) &&
        (s_tx_control_burst <= LORA_TX_CONTROL_BURST_MAX),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((s_contexts[instance].schedule_role != LoraScheduleRole_Ground) ||
        ((s_tx_control_count == 0U) && (s_tx_control_burst == 0U)),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT(s_tx_head == (((uint32_t)s_tx_tail + s_tx_count) % LORA_TX_QUEUE_DEPTH),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
}

/* Caller holds the IRQ lock: indices/count are one coherent ring snapshot. */
static void Lora_RxQueueAssert(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_rx_head < LORA_RX_QUEUE_DEPTH) &&
        (s_rx_tail < LORA_RX_QUEUE_DEPTH),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_rx_count <= LORA_RX_QUEUE_DEPTH,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT(s_rx_head == (((uint32_t)s_rx_tail + s_rx_count) % LORA_RX_QUEUE_DEPTH),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
}

/* Non-idle owner transactions carry an operation, nonzero ID and deadline. */
static void Lora_ControlAssert(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((uint32_t)s_control_transaction.state <= LoraControlStateComplete,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (s_control_transaction.state == LoraControlStateIdle) { return; }
    SILVERSTAR_ASSERT((s_control_transaction.operation == LORA_CONTROL_IRQ_CLEAR) ||
        (s_control_transaction.operation == LORA_CONTROL_FORCE_RX_CONTINUOUS),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(s_control_transaction.transaction_id != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT(s_control_transaction.timeout_ms != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    SILVERSTAR_ASSERT(s_control_transaction.auto_release <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

static void Lora_SetRadioState(uint8_t instance, LoraRadioState state)
{
    uint32_t primask;

    primask = Lora_IrqLock();
    s_stats.radio_state = state;
    Lora_IrqUnlock(primask);
}

/* SDK reads return buffers through void HAL operations. Reject plausible stale
 * bytes whenever any operation reported SPI/busy failure, even if a later
 * operation overwrote last_result with OK. Snapshots are owner-task coherent. */
static uint8_t Lora_BusReadSucceeded(uint8_t instance, Sx1281BusStatus before)
{
    Sx1281BusStatus after;
    Sx1281Bus_StatusGet(instance, &after);
    uint8_t good = (uint8_t)((after.last_result == SX1281_BUS_OK) &&
        (after.spi_error_count == before.spi_error_count) &&
        (after.spi_timeout_count == before.spi_timeout_count) &&
        (after.busy_timeout_count == before.busy_timeout_count));
    if (good == 0U)
    {
        uint32_t primask = Lora_IrqLock();
        s_chip_status.verified = 0U;
        s_stats.radio_state = LORA_RADIO_STATE_BUSY;
        Lora_IrqUnlock(primask);
    }
    return good;
}

static void Lora_LastRxRecord(uint8_t instance, uint8_t len, int8_t rssi, int8_t snr)
{
    uint32_t primask;

    primask = Lora_IrqLock();
    s_stats.last_rx_len = len;
    s_stats.last_rx_rssi = rssi;
    s_stats.last_rx_snr = snr;
    s_stats.last_rx_type = (len > 0U) ? s_rx_tmp_buf[0] : 0U;
    Lora_IrqUnlock(primask);
}

static void Lora_StatsIncrement(uint32_t *counter)
{
    uint32_t primask;

    if (counter == 0)
    {
        return;
    }

    primask = Lora_IrqLock();
    (*counter)++;
    Lora_IrqUnlock(primask);
}

static void Lora_DiagRecordSetRx(uint8_t instance)
{
    uint32_t primask;
    uint32_t tick_ms = PlatformTime_Ms();

    primask = Lora_IrqLock();
    s_diag.setrx_count++;
    s_diag.rx_start_count++;
    s_diag.last_setrx_ms = tick_ms;
    Lora_IrqUnlock(primask);
}

static void Lora_DiagRecordSetTx(uint8_t instance)
{
    uint32_t primask;
    uint32_t tick_ms = PlatformTime_Ms();

    primask = Lora_IrqLock();
    s_diag.settx_count++;
    s_diag.last_settx_ms = tick_ms;
    Lora_IrqUnlock(primask);
}

static void Lora_DiagRecordTxStart(uint8_t instance)
{
    uint32_t primask;

    primask = Lora_IrqLock();
    s_diag.tx_start_count++;
    Lora_IrqUnlock(primask);
}

static void Lora_DiagTimeoutRecord(uint8_t instance, uint16_t raw_irq,
                                   uint8_t *is_tx_irq,
                                   uint8_t *is_rx_irq)
{
    if ((raw_irq & IRQ_RX_TX_TIMEOUT) == 0U)
    {
        return;
    }
    if ((s_tx_busy != 0U) || (s_stats.radio_state == LORA_RADIO_STATE_TX))
    {
        s_diag.tx_timeout_count++;
        *is_tx_irq = 1U;
    }
    else
    {
        s_diag.rx_timeout_count++;
        *is_rx_irq = 1U;
    }
}

static void Lora_DiagRecordIrq(uint8_t instance, uint16_t raw_irq)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((uint32_t)s_stats.radio_state <= LORA_RADIO_STATE_BUSY,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    uint32_t primask;
    uint32_t tick_ms;
    uint8_t is_tx_irq = 0U;
    uint8_t is_rx_irq = 0U;

    if (raw_irq == 0U)
    {
        return;
    }


    tick_ms = PlatformTime_Ms();
    primask = Lora_IrqLock();

    s_diag.last_raw_irq = raw_irq;
    s_diag.last_irq_ms = tick_ms;
    s_diag.has_last_irq = 1U;

    if ((raw_irq & IRQ_TX_DONE) != 0U)
    {
        s_diag.tx_done_count++;
        is_tx_irq = 1U;
    }
    if ((raw_irq & IRQ_RX_DONE) != 0U)
    {
        s_diag.rx_done_count++;
        is_rx_irq = 1U;
    }
    if ((raw_irq & IRQ_CRC_ERROR) != 0U)
    {
        s_diag.rx_crc_count++;
        s_diag.rx_error_count++;
        is_rx_irq = 1U;
    }
    if ((raw_irq & IRQ_HEADER_ERROR) != 0U)
    {
        s_diag.rx_header_count++;
        s_diag.rx_error_count++;
        is_rx_irq = 1U;
    }
    Lora_DiagTimeoutRecord(instance, raw_irq, &is_tx_irq, &is_rx_irq);

    if (is_rx_irq != 0U)
    {
        s_diag.last_rx_irq_ms = tick_ms;
        s_diag.has_last_rx_irq = 1U;
    }
    if (is_tx_irq != 0U)
    {
        s_diag.last_tx_irq_ms = tick_ms;
        s_diag.has_last_tx_irq = 1U;
    }

    Lora_IrqUnlock(primask);
}

static void Lora_DiagSetDioIrqParams(uint8_t instance, uint16_t irq_mask,
                                     uint16_t dio1_mask,
                                     uint16_t dio2_mask,
                                     uint16_t dio3_mask)
{
    uint32_t primask;

    SX1280SetDioIrqParams(instance, irq_mask, dio1_mask, dio2_mask, dio3_mask);

    primask = Lora_IrqLock();
    s_diag.irq_mask = irq_mask;
    s_diag.dio1_mask = dio1_mask;
    s_diag.dio2_mask = dio2_mask;
    s_diag.dio3_mask = dio3_mask;
    Lora_IrqUnlock(primask);
}

static void Lora_LoadDefaultConfig(uint8_t instance)
{
    memset(&s_mod_params, 0, sizeof(s_mod_params));
    memset(&s_pkt_params, 0, sizeof(s_pkt_params));
    memset(&s_pkt_status, 0, sizeof(s_pkt_status));

    s_mod_params.PacketType = PACKET_TYPE_LORA;
    s_mod_params.Params.LoRa.SpreadingFactor = LORA_CFG_SF;
    s_mod_params.Params.LoRa.Bandwidth = LORA_CFG_BW;
    s_mod_params.Params.LoRa.CodingRate = LORA_CFG_CR;

    s_pkt_params.PacketType = PACKET_TYPE_LORA;
    s_pkt_params.Params.LoRa.PreambleLength = LORA_CFG_PREAMBLE_LEN;
    s_pkt_params.Params.LoRa.HeaderType = LORA_CFG_HEADER_TYPE;
    s_pkt_params.Params.LoRa.CrcMode = LORA_CFG_CRC_MODE;
    s_pkt_params.Params.LoRa.InvertIQ = LORA_CFG_IQ_MODE;
    s_pkt_params.Params.LoRa.PayloadLength = LORA_MAX_PAYLOAD_LEN;
}

static void Lora_ClearRuntimeState(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask = Lora_IrqLock();

    /* Reset the owned context together, including READY and future fields.
     * Default modulation/packet configuration is loaded after this reset. */
    memset(&s_contexts[instance], 0, sizeof(s_contexts[instance]));
    s_rx_error_code = IRQ_HEADER_ERROR_CODE;
    s_stats.radio_state = LORA_RADIO_STATE_NOT_INIT;
    Lora_IrqUnlock(primask);
}

/* Caller owns the IRQ lock. At most two normal packets move; controls keep FIFO. */
static void Lora_TxQueueInsert(uint8_t instance, const uint8_t *data,
    uint8_t len, uint8_t control, uint32_t transaction_id)
{
    uint8_t position = s_tx_head;
    uint8_t index;
    if (control != 0U)
    {
        for (index = 0U; index < LORA_TX_NORMAL_QUEUE_DEPTH; index++)
        {
            uint8_t normal = (uint8_t)(s_tx_count - s_tx_control_count);
            if (index < normal)
            {
                uint8_t previous = (uint8_t)((position + LORA_TX_QUEUE_DEPTH - 1U) % LORA_TX_QUEUE_DEPTH);
                s_tx_queue[position] = s_tx_queue[previous];
                s_contexts[instance].tx_ids[position] = s_contexts[instance].tx_ids[previous];
                position = previous;
            }
        }
        s_tx_control_count++;
    }
    s_tx_queue[position].len = len;
    (void)memcpy(s_tx_queue[position].data, data, len);
    s_contexts[instance].tx_ids[position] = transaction_id;
    s_tx_head = (uint8_t)((s_tx_head + 1U) % LORA_TX_QUEUE_DEPTH);
    s_tx_count++;
}

/* Caller owns IRQ lock and has validated queue geometry. */
static uint8_t Lora_TxIdPending(uint8_t instance, uint32_t id)
{
    uint8_t found = (uint8_t)(s_contexts[instance].active_tx_id == id);
    for (uint8_t index = 0U; index < LORA_TX_QUEUE_DEPTH; index++)
    {
        uint8_t slot = (uint8_t)((s_tx_tail + index) % LORA_TX_QUEUE_DEPTH);
        if ((index < s_tx_count) && (s_contexts[instance].tx_ids[slot] == id)) { found = 1U; }
    }
    return found;
}

static uint8_t Lora_TxQueuePushClass(uint8_t instance, const uint8_t *data,
    uint8_t len, uint8_t control, uint32_t *transaction_id)
{
    uint32_t primask;
    uint32_t id = 0U;
    if ((data == NULL) || (len == 0U) || (len > LORA_MAX_PAYLOAD_LEN)) { return 0U; }
    primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance);
    uint8_t normal_capacity = (s_contexts[instance].schedule_role == LoraScheduleRole_Ground) ?
        LORA_TX_QUEUE_DEPTH : LORA_TX_NORMAL_QUEUE_DEPTH;
    if (s_contexts[instance].schedule_role == LoraScheduleRole_Ground) { control = 0U; }
    if (((control != 0U) && (s_tx_control_count >= LORA_TX_CONTROL_QUEUE_DEPTH)) ||
        ((control == 0U) && (((uint32_t)s_tx_count - (uint32_t)s_tx_control_count) >= normal_capacity)))
    { Lora_IrqUnlock(primask); return 0U; }
    if (transaction_id != NULL)
    {
        /* At most eight queued tokens plus one active token can collide. */
        for (uint8_t attempt = 0U; attempt < (LORA_TX_QUEUE_DEPTH + 2U); attempt++)
        {
            s_contexts[instance].next_tx_id = (s_contexts[instance].next_tx_id + 1U) & 0x00FFFFFFUL;
            if (s_contexts[instance].next_tx_id == 0U) { s_contexts[instance].next_tx_id = 1U; }
            id = ((uint32_t)instance << 24U) | s_contexts[instance].next_tx_id;
            if (Lora_TxIdPending(instance, id) == 0U) { break; }
        }
        SILVERSTAR_ASSERT(Lora_TxIdPending(instance, id) == 0U,
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
        if (id == s_contexts[instance].completed_tx_id) { s_contexts[instance].completed_tx_id = 0U; }
    }
    Lora_TxQueueInsert(instance, data, len, control, id);
    if (transaction_id != NULL) { *transaction_id = id; }
    Lora_IrqUnlock(primask);
    return 1U;
}

static uint8_t Lora_TxQueuePush(uint8_t instance, const uint8_t *data, uint8_t len)
{ return Lora_TxQueuePushClass(instance, data, len, 0U, NULL); }

static uint8_t Lora_TxQueuePushFront(uint8_t instance, const uint8_t *data, uint8_t len)
{ return Lora_TxQueuePushClass(instance, data, len, 1U, NULL); }

static uint8_t Lora_TxQueuePop(uint8_t instance, LoraTxPacket *pkt)
{
    uint32_t primask;
    uint8_t position;
    uint8_t index;
    uint8_t normal;
    uint8_t normal_selected = 0U;
    if (pkt == NULL) { return 0U; }
    primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance);
    if (s_tx_count == 0U) { Lora_IrqUnlock(primask); return 0U; }
    normal = (uint8_t)(s_tx_count - s_tx_control_count);
    position = s_tx_tail;
    if ((normal != 0U) && ((s_tx_control_count == 0U) ||
        (s_tx_control_burst >= LORA_TX_CONTROL_BURST_MAX)))
    {
        position = (uint8_t)((s_tx_tail + s_tx_control_count) % LORA_TX_QUEUE_DEPTH);
        normal_selected = 1U;
    }
    SILVERSTAR_ASSERT((s_tx_queue[position].len > 0U) && (s_tx_queue[position].len <= LORA_MAX_PAYLOAD_LEN),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (normal_selected != 0U) { s_tx_control_burst = 0U; }
    else
    { s_tx_control_count--; if (s_tx_control_burst < LORA_TX_CONTROL_BURST_MAX) { s_tx_control_burst++; } }
    *pkt = s_tx_queue[position];
    s_contexts[instance].active_tx_id = s_contexts[instance].tx_ids[position];
    if (position == s_tx_tail) { s_tx_tail = (uint8_t)((s_tx_tail + 1U) % LORA_TX_QUEUE_DEPTH); }
    else
    {
        for (index = 1U; index < LORA_TX_NORMAL_QUEUE_DEPTH; index++)
        {
            if (index < normal)
            {
                uint8_t next = (uint8_t)((position + 1U) % LORA_TX_QUEUE_DEPTH);
                s_tx_queue[position] = s_tx_queue[next];
                s_contexts[instance].tx_ids[position] = s_contexts[instance].tx_ids[next];
                position = next;
            }
        }
        s_tx_head = (uint8_t)((s_tx_head + LORA_TX_QUEUE_DEPTH - 1U) % LORA_TX_QUEUE_DEPTH);
    }
    s_tx_count--;
    if (s_tx_count == 0U) { s_tx_control_burst = 0U; }
    Lora_IrqUnlock(primask);
    return 1U;
}

static uint8_t Lora_RxQueuePush(uint8_t instance, const uint8_t *data, uint8_t len, int8_t rssi, int8_t snr)
{
    uint32_t primask;

    if ((data == 0) || (len == 0) || (len > LORA_MAX_PAYLOAD_LEN))
    {
        return 0U;
    }

    SILVERSTAR_ASSERT_OBJECT(data, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    primask = Lora_IrqLock();
    Lora_RxQueueAssert(instance);

    if (s_rx_count >= LORA_RX_QUEUE_DEPTH)
    {
        Lora_IrqUnlock(primask);
        return 0U;
    }

    s_rx_queue[s_rx_head].len = len;
    s_rx_queue[s_rx_head].rssi = rssi;
    s_rx_queue[s_rx_head].snr = snr;
    memcpy(s_rx_queue[s_rx_head].data, data, len);

    s_rx_head++;
    if (s_rx_head >= LORA_RX_QUEUE_DEPTH)
    {
        s_rx_head = 0U;
    }

    s_rx_count++;
    Lora_IrqUnlock(primask);
    return 1U;
}

static uint8_t Lora_RxQueuePop(uint8_t instance, LoraRxPacket *pkt)
{
    uint32_t primask;

    if (pkt == 0)
    {
        return 0U;
    }

    SILVERSTAR_ASSERT_OBJECT(pkt, LoraRxPacket,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    primask = Lora_IrqLock();
    Lora_RxQueueAssert(instance);

    if (s_rx_count == 0)
    {
        Lora_IrqUnlock(primask);
        return 0U;
    }

    SILVERSTAR_ASSERT((s_rx_queue[s_rx_tail].len > 0U) &&
        (s_rx_queue[s_rx_tail].len <= LORA_MAX_PAYLOAD_LEN),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);

    *pkt = s_rx_queue[s_rx_tail];

    s_rx_tail++;
    if (s_rx_tail >= LORA_RX_QUEUE_DEPTH)
    {
        s_rx_tail = 0U;
    }

    s_rx_count--;
    Lora_IrqUnlock(primask);
    return 1U;
}

/* Semtech Rev3.2 sections7.4.4.1/11.9.1: legacy CR, SF5..12.
 * Quarter-symbol arithmetic keeps the 4.25/6.25 contribution exact. */
static uint32_t Lora_PacketAirtimeMs(uint8_t instance, uint8_t length)
{
    uint32_t bandwidth = 0U;
    uint32_t sf = (uint32_t)s_mod_params.Params.LoRa.SpreadingFactor >> 4U;
    uint32_t cr = (uint32_t)s_mod_params.Params.LoRa.CodingRate;
    uint32_t preamble = (uint32_t)(s_pkt_params.Params.LoRa.PreambleLength & 0x0FU) <<
        ((uint32_t)s_pkt_params.Params.LoRa.PreambleLength >> 4U);
    SILVERSTAR_ASSERT((sf >= 5U) && (sf <= 12U) &&
        ((uint32_t)s_mod_params.Params.LoRa.SpreadingFactor == (sf << 4U)) &&
        (cr >= 1U) && (cr <= 4U),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT((s_mod_params.PacketType == PACKET_TYPE_LORA) &&
        (s_pkt_params.PacketType == PACKET_TYPE_LORA) &&
        ((s_pkt_params.Params.LoRa.HeaderType == LORA_PACKET_VARIABLE_LENGTH) ||
         (s_pkt_params.Params.LoRa.HeaderType == LORA_PACKET_FIXED_LENGTH)) &&
        ((s_pkt_params.Params.LoRa.CrcMode == LORA_CRC_ON) || (s_pkt_params.Params.LoRa.CrcMode == LORA_CRC_OFF)) &&
        (preamble == LORA_CFG_PREAMBLE_SYMBOLS),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((length > 0U) && (length <= LORA_MAX_PAYLOAD_LEN),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    switch (s_mod_params.Params.LoRa.Bandwidth)
    {
        case LORA_BW_0200: bandwidth = 203125U; break;
        case LORA_BW_0400: bandwidth = 406250U; break;
        case LORA_BW_0800: bandwidth = 812500U; break;
        case LORA_BW_1600: bandwidth = 1625000U; break;
        default: break;
    }
    SILVERSTAR_ASSERT(bandwidth != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    int32_t bits = (int32_t)(8U * length) - (int32_t)(4U * sf);
    if (s_pkt_params.Params.LoRa.CrcMode == LORA_CRC_ON) { bits += 16; }
    if (s_pkt_params.Params.LoRa.HeaderType == LORA_PACKET_VARIABLE_LENGTH) { bits += 20; }
    if (sf >= 7U) { bits += 8; }
    uint32_t denominator = 4U * ((sf > 10U) ? (sf - 2U) : sf);
    uint32_t blocks = (bits > 0) ? ((uint32_t)bits + denominator - 1U) / denominator : 0U;
    uint32_t quarter_symbols = 4U * (preamble + 8U + blocks * (cr + 4U)) +
        ((sf < 7U) ? 25U : 17U);
    uint64_t numerator = (uint64_t)quarter_symbols * (1UL << sf) * 1000ULL;
    return (uint32_t)((numerator + (uint64_t)4U * bandwidth - 1U) / ((uint64_t)4U * bandwidth));
}

static uint32_t Lora_RxGrantMs(uint8_t instance)
{
    uint32_t minimum = Lora_PacketAirtimeMs(instance, LORA_MAX_PAYLOAD_LEN) + LORA_RX_TURN_MARGIN_MS;
    return (minimum > LORA_RX_DWELL_MS) ? minimum : LORA_RX_DWELL_MS;
}

static uint32_t Lora_RxListenMs(uint8_t instance)
{
    uint32_t grant = Lora_RxGrantMs(instance);
    if (s_contexts[instance].schedule_role == LoraScheduleRole_Ground)
    { grant += Lora_PacketAirtimeMs(instance, LORA_MAX_PAYLOAD_LEN) + LORA_RX_TURN_MARGIN_MS; }
    return grant;
}

/* No peer/late arrival recovery has a finite bound. A received packet grants
 * Ground an early slot; never begin a packet that overruns Flight's RX grant. */
static uint8_t Lora_TxTurnAvailable(uint8_t instance)
{
    if (s_contexts[instance].rx_window_active == 0U) { return 0U; }
    uint32_t elapsed = PlatformTime_Ms() - s_rx_started_ms;
    uint32_t grant = Lora_RxGrantMs(instance);
    if (s_contexts[instance].schedule_role == LoraScheduleRole_Flight)
    { return (uint8_t)(elapsed >= grant); }
    uint32_t recovery = Lora_RxListenMs(instance);
    if (elapsed >= recovery) { return 1U; }
    if (s_contexts[instance].rx_window_active != 2U) { return 0U; }
    uint32_t primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance);
    uint8_t length = (s_tx_count != 0U) ? s_tx_queue[s_tx_tail].len : 0U;
    Lora_IrqUnlock(primask);
    if (length == 0U) { return 0U; }
    return (uint8_t)((elapsed + Lora_PacketAirtimeMs(instance, length) + LORA_RX_TURN_MARGIN_MS) <= grant);
}

/* First detection owns the immutable deadline. Late/repeated indications
 * cannot prolong a lost-completion/noise hold. Expiry discards the stale RX
 * in the ordinary timeout path, before any queued payload is transmitted. */
/* Ordinary persistent I/O failure: fail bounded queued work, invalidate the
 * cached chip/READY state, and require explicit owner reinitialization.
 * No successful receipt is manufactured and no further radio command runs. */
static void Lora_RadioFault(uint8_t instance, uint8_t failed_tx)
{
    uint32_t primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance); Lora_RxQueueAssert(instance); Lora_ControlAssert(instance);
    if (failed_tx != 0U) { s_stats.tx_timeout++; }
    for (uint32_t index = 0U; index < (LORA_TX_QUEUE_DEPTH + 1U); index++)
    {
        uint32_t id = s_contexts[instance].active_tx_id;
        if (index < LORA_TX_QUEUE_DEPTH)
        {
            uint8_t slot = (uint8_t)((s_tx_tail + index) % LORA_TX_QUEUE_DEPTH);
            id = index < s_tx_count ? s_contexts[instance].tx_ids[slot] : 0U;
            s_contexts[instance].tx_ids[slot] = 0U;
        }
        if (id != 0U)
        {
            s_contexts[instance].completed_tx_id = id;
            s_contexts[instance].completed_tx_ms = PlatformTime_Ms();
            s_contexts[instance].completed_tx_result = LoraTxQueryResult_TimedOut;
        }
    }
    s_stats.tx_dropped += s_tx_count; s_stats.rx_dropped += s_rx_count; s_stats.rx_error++;
    s_tx_head = 0U; s_tx_tail = 0U; s_tx_count = 0U;
    s_tx_control_count = 0U; s_tx_control_burst = 0U;
    s_rx_head = 0U; s_rx_tail = 0U; s_rx_count = 0U;
    s_contexts[instance].active_tx_id = 0U;
    s_contexts[instance].rx_packet_active = 0U; s_contexts[instance].rx_window_active = 0U;
    s_tx_busy = 0U; s_radio_in_rx = 0U; s_inited = 0U; s_chip_status.verified = 0U;
    s_tx_done_flag = 0U; s_tx_timeout_flag = 0U; s_rx_done_flag = 0U;
    s_rx_timeout_flag = 0U; s_rx_error_flag = 0U;
    if ((s_control_transaction.state == LoraControlStateSubmitted) ||
        (s_control_transaction.state == LoraControlStateActive))
    {
        s_control_transaction.result.transaction_id = s_control_transaction.transaction_id;
        s_control_transaction.result.result = LORA_DIAG_RESULT_TIMEOUT;
        s_control_transaction.result.raw_irq_before = 0U;
        s_control_transaction.state = s_control_transaction.auto_release != 0U ?
            LoraControlStateIdle : LoraControlStateComplete;
    }
    s_stats.radio_state = LORA_RADIO_STATE_NOT_INIT;
    Lora_IrqUnlock(primask);
}

static uint8_t Lora_RadioRecover(uint8_t instance, uint8_t failed_tx)
{
    Sx1281BusStatus before;
    Sx1281Bus_StatusGet(instance, &before);
    SX1280SetStandby(instance, STDBY_RC);
    SX1280ClearIrqStatus(instance, IRQ_RADIO_ALL);
    RadioStatus_t status = SX1280GetStatus(instance);
    if ((Lora_BusReadSucceeded(instance, before) != 0U) &&
        ((status.Fields.ChipMode == 2U) || (status.Fields.ChipMode == 3U)))
    { s_radio_in_rx = 0U; s_contexts[instance].rx_packet_active = 0U; return 1U; }
    Lora_RadioFault(instance, failed_tx);
    return 0U;
}

static uint8_t Lora_RxPacketHeld(uint8_t instance)
{
    SILVERSTAR_ASSERT(s_contexts[instance].rx_packet_active <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_contexts[instance].rx_packet_active == 0U) { return 0U; }
    uint32_t bound = Lora_PacketAirtimeMs(instance, LORA_MAX_PAYLOAD_LEN) + LORA_RX_TURN_MARGIN_MS;
    if ((uint32_t)(PlatformTime_Ms() - s_contexts[instance].rx_packet_started_ms) < bound)
    { return 1U; }
    Lora_StatsIncrement(&s_stats.rx_timeout);
    return (uint8_t)(Lora_RadioRecover(instance, 0U) == 0U);
}

/* Hardware timed RX protects the pre-detection gap too. Only a completed
 * RX/timeout, verified standby, or the fixed lost-IRQ watchdog allows TX. */
static uint8_t Lora_RxIdleForTx(uint8_t instance)
{
    if (s_radio_in_rx == 0U) { return 1U; }
    Sx1281BusStatus before;
    Sx1281Bus_StatusGet(instance, &before);
    RadioStatus_t status = SX1280GetStatus(instance);
    if ((Lora_BusReadSucceeded(instance, before) != 0U) &&
        ((status.Fields.ChipMode == 2U) || (status.Fields.ChipMode == 3U)))
    { s_radio_in_rx = 0U; return 1U; }
    uint32_t bound = Lora_RxListenMs(instance) +
        Lora_PacketAirtimeMs(instance, LORA_MAX_PAYLOAD_LEN) + LORA_RX_TURN_MARGIN_MS;
    if ((uint32_t)(PlatformTime_Ms() - s_rx_started_ms) < bound) { return 0U; }
    Lora_StatsIncrement(&s_stats.rx_timeout);
    return Lora_RadioRecover(instance, 0U);
}

static void Lora_TryStartNextTx(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_inited <= 1U) && (s_tx_busy <= 1U),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    LoraTxPacket pkt;

    if ((s_inited == 0) || (s_tx_busy != 0))
    {
        return;
    }

    if (Lora_TxQueuePop(instance, &pkt) == 0)
    {
        return;
    }

    Sx1281BusStatus before;
    Sx1281Bus_StatusGet(instance, &before);
    s_pkt_params.Params.LoRa.PayloadLength = pkt.len;
    SX1280SetPacketParams(instance, &s_pkt_params);
    Lora_DiagSetDioIrqParams(instance, LORA_TX_IRQ_MASK, LORA_TX_IRQ_MASK, IRQ_RADIO_NONE, IRQ_RADIO_NONE);
    Lora_DiagRecordTxStart(instance);
    SX1280SendPayload(instance, pkt.data, pkt.len,
                      (TickTime_t){ LORA_TX_TIMEOUT_STEP,
                                    LORA_TX_TIMEOUT_COUNT });
    Lora_DiagRecordSetTx(instance);
    if (Lora_BusReadSucceeded(instance, before) == 0U)
    { Lora_RadioFault(instance, 1U); return; }

    s_tx_busy = 1U;
    s_radio_in_rx = 0U;
    s_contexts[instance].rx_window_active = 0U;
    Lora_SetRadioState(instance, LORA_RADIO_STATE_TX);
}

LoraConfigResult Lora_ApplyDefaultConfig(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    Sx1281BusStatus before;
    Sx1281BusStatus after;

    Sx1281Bus_StatusGet(instance, &before);
    SX1280SetPacketType(instance, PACKET_TYPE_LORA);
    SX1280SetModulationParams(instance, &s_mod_params);
    SX1280SetPacketParams(instance, &s_pkt_params);
    SX1280SetRfFrequency(instance, LORA_RF_FREQUENCY_HZ);
    SX1280SetBufferBaseAddresses(instance, 0x00, 0x00);
    SX1280SetTxParams(instance, LORA_TX_OUTPUT_POWER_DBM, RADIO_RAMP_02_US);
    Sx1281Bus_StatusGet(instance, &after);
    return ((after.spi_error_count != before.spi_error_count) ||
            (after.spi_timeout_count != before.spi_timeout_count) ||
            (after.last_result != SX1281_BUS_OK) ||
            (after.busy_timeout_count != before.busy_timeout_count)) ?
        LORA_CONFIG_PORT_ERROR : LORA_CONFIG_OK;
}

LoraScheduleRoleResult Lora_ScheduleRoleSet(uint8_t instance, LoraScheduleRole role)
{
    if ((instance >= PROJECT_SX1281_INSTANCE_COUNT) ||
        ((role != LoraScheduleRole_Flight) && (role != LoraScheduleRole_Ground)))
    { return LoraScheduleRoleResult_InvalidArgument; }
    uint32_t primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance);
    if ((s_inited == 0U) || (s_tx_busy != 0U) || (s_tx_count != 0U) || (s_radio_in_rx != 0U))
    { Lora_IrqUnlock(primask); return LoraScheduleRoleResult_NotReady; }
    s_contexts[instance].schedule_role = (uint8_t)role;
    Lora_IrqUnlock(primask);
    return LoraScheduleRoleResult_Ok;
}

LoraInitResult Lora_Init(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_control_transaction.state != LoraControlStateActive,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    RadioStatus_t radio_status;
    Sx1281BusStatus bus_status;

    Sx1281Bus_Init(instance);
    Lora_ClearRuntimeState(instance);
    Lora_LoadDefaultConfig(instance);

    SX1280Init(instance);
    SX1280SetRegulatorMode(instance, USE_LDO);
    SX1280SetStandby(instance, STDBY_RC);
    if (Lora_ApplyDefaultConfig(instance) != LORA_CONFIG_OK)
    {
        return LORA_INIT_PORT_ERROR;
    }

    s_chip_status.firmware_version = SX1280GetFirmwareVersion(instance);
    radio_status = SX1280GetStatus(instance);
    s_chip_status.status_value = radio_status.Value;
    Sx1281Bus_StatusGet(instance, &bus_status);
    if ((bus_status.spi_error_count != 0U) ||
        (bus_status.spi_timeout_count != 0U) ||
        (bus_status.last_result != SX1281_BUS_OK) ||
        (bus_status.busy_timeout_count != 0U))
    {
        return LORA_INIT_PORT_ERROR;
    }
    if ((s_chip_status.firmware_version == 0x0000U) ||
        (s_chip_status.firmware_version == 0xFFFFU) ||
        (s_chip_status.status_value == 0x00U) ||
        (s_chip_status.status_value == 0xFFU))
    {
        return LORA_INIT_CHIP_NOT_FOUND;
    }
    s_chip_status.verified = 1U;

    s_inited = 1U;
    Lora_SetRadioState(instance, LORA_RADIO_STATE_READY);

    return LORA_INIT_OK;
}

void Lora_StartRx(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (s_inited == 0)
    {
        return;
    }

    SILVERSTAR_ASSERT(s_pkt_params.PacketType == PACKET_TYPE_LORA,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);

    Sx1281BusStatus before;
    Sx1281Bus_StatusGet(instance, &before);
    uint32_t now = PlatformTime_Ms();
    if (s_contexts[instance].rx_window_active == 0U)
    { s_rx_started_ms = now; s_contexts[instance].rx_window_active = 1U; }
    uint32_t listen = Lora_RxListenMs(instance);
    uint32_t elapsed = now - s_rx_started_ms;
    if ((elapsed >= listen) && (s_tx_count == 0U))
    { s_rx_started_ms = now; elapsed = 0U; s_contexts[instance].rx_window_active = 1U; }
    uint32_t remaining = (elapsed < listen) ? (listen - elapsed) : 1U;
    SILVERSTAR_ASSERT(remaining < UINT16_MAX,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    s_pkt_params.Params.LoRa.PayloadLength = LORA_MAX_PAYLOAD_LEN;
    SX1280SetPacketParams(instance, &s_pkt_params);
    Lora_DiagSetDioIrqParams(instance, LORA_RX_IRQ_MASK, LORA_RX_IRQ_MASK, IRQ_RADIO_NONE, IRQ_RADIO_NONE);
    /* Hardware disables this timer when it detects a packet, finishing the
     * packet before RX_DONE. Software must observe RX completion or idle. */
    SX1280SetRx(instance, (TickTime_t){RADIO_TICK_SIZE_1000_US, (uint16_t)remaining});
    Lora_DiagRecordSetRx(instance);
    if (Lora_BusReadSucceeded(instance, before) == 0U)
    { Lora_RadioFault(instance, 0U); return; }

    s_radio_in_rx = 1U;
    if (s_tx_busy != 0)
    {
        Lora_SetRadioState(instance, LORA_RADIO_STATE_TX);
    }
    else
    {
        Lora_SetRadioState(instance, LORA_RADIO_STATE_RX);
    }
}

LoraTxEnqueueResult Lora_TxEnqueue(uint8_t instance, const uint8_t *data, uint8_t len)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (s_inited == 0)
    {
        return LORA_TX_ENQUEUE_NOT_INIT;
    }

    if ((data == 0) || (len == 0) || (len > LORA_MAX_PAYLOAD_LEN))
    {
        return LORA_TX_ENQUEUE_BAD_PARAM;
    }

    if (Lora_TxQueuePush(instance, data, len) == 0)
    {
        Lora_StatsIncrement(&s_stats.tx_dropped);
        return LORA_TX_ENQUEUE_QUEUE_FULL;
    }

    return LORA_TX_ENQUEUE_OK;
}

LoraTxEnqueueResult Lora_TxEnqueuePriority(uint8_t instance, const uint8_t *data, uint8_t len)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (s_inited == 0)
    {
        return LORA_TX_ENQUEUE_NOT_INIT;
    }

    if ((data == 0) || (len == 0) || (len > LORA_MAX_PAYLOAD_LEN))
    {
        return LORA_TX_ENQUEUE_BAD_PARAM;
    }

    if (Lora_TxQueuePushFront(instance, data, len) == 0)
    {
        Lora_StatsIncrement(&s_stats.tx_dropped);
        return LORA_TX_ENQUEUE_QUEUE_FULL;
    }

    return LORA_TX_ENQUEUE_OK;
}

LoraTxEnqueueResult Lora_TxEnqueueTracked(uint8_t instance,
    const uint8_t *data, uint8_t len, uint32_t *transaction_id)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (transaction_id == NULL) { return LORA_TX_ENQUEUE_BAD_PARAM; }
    *transaction_id = 0U;
    if (s_inited == 0U) { return LORA_TX_ENQUEUE_NOT_INIT; }
    if ((data == NULL) || (len == 0U) || (len > LORA_MAX_PAYLOAD_LEN)) { return LORA_TX_ENQUEUE_BAD_PARAM; }
    if (Lora_TxQueuePushClass(instance, data, len, 1U, transaction_id) == 0U)
    { Lora_StatsIncrement(&s_stats.tx_dropped); return LORA_TX_ENQUEUE_QUEUE_FULL; }
    return LORA_TX_ENQUEUE_OK;
}

LoraTxQueryResult Lora_TxResultGet(uint8_t instance,
    uint32_t transaction_id, uint32_t *age_ms)
{
    uint8_t index;
    uint32_t primask;
    LoraTxQueryResult result = LoraTxQueryResult_NotFound;
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if ((transaction_id == 0U) || (age_ms == NULL)) { return LoraTxQueryResult_InvalidArgument; }
    *age_ms = 0U;
    primask = Lora_IrqLock();
    Lora_TxQueueAssert(instance);
    if (s_contexts[instance].completed_tx_id == transaction_id)
    {
        SILVERSTAR_ASSERT((s_contexts[instance].completed_tx_result == LoraTxQueryResult_Complete) ||
            (s_contexts[instance].completed_tx_result == LoraTxQueryResult_TimedOut),
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
        result = s_contexts[instance].completed_tx_result;
        *age_ms = (uint32_t)(PlatformTime_Ms() - s_contexts[instance].completed_tx_ms);
    }
    else if (s_contexts[instance].active_tx_id == transaction_id) { result = LoraTxQueryResult_Pending; }
    else
    {
        for (index = 0U; index < LORA_TX_QUEUE_DEPTH; index++)
        {
            uint8_t position = (uint8_t)((s_tx_tail + index) % LORA_TX_QUEUE_DEPTH);
            if ((index < s_tx_count) && (s_contexts[instance].tx_ids[position] == transaction_id))
            { result = LoraTxQueryResult_Pending; }
        }
    }
    Lora_IrqUnlock(primask);
    return result;
}

static void Lora_IrqProcess(uint8_t instance, uint16_t raw_irq)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_tx_busy <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (((raw_irq & (IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID)) != 0U) &&
        (s_tx_busy == 0U) && (s_radio_in_rx != 0U) &&
        (s_contexts[instance].rx_packet_active == 0U))
    {
        s_contexts[instance].rx_packet_started_ms = PlatformTime_Ms();
        s_contexts[instance].rx_packet_active = 1U;
    }
    if ((raw_irq & IRQ_TX_DONE) != 0U)
    {
        Lora_OnTxDone(instance);
    }
    if ((raw_irq & IRQ_RX_DONE) != 0U)
    {
        if ((raw_irq & IRQ_CRC_ERROR) != 0U)
        {
            Lora_OnRxError(instance, IRQ_CRC_ERROR_CODE);
        }
        else if ((raw_irq & IRQ_HEADER_ERROR) != 0U)
        {
            Lora_OnRxError(instance, IRQ_HEADER_ERROR_CODE);
        }
        else
        {
            Lora_OnRxDone(instance);
        }
    }
    else if ((raw_irq & IRQ_CRC_ERROR) != 0U)
    {
        Lora_OnRxError(instance, IRQ_CRC_ERROR_CODE);
    }
    else if ((raw_irq & IRQ_HEADER_ERROR) != 0U)
    {
        Lora_OnRxError(instance, IRQ_HEADER_ERROR_CODE);
    }
    if ((raw_irq & IRQ_RX_TX_TIMEOUT) != 0U)
    {
        if (s_tx_busy != 0U)
        {
            Lora_OnTxTimeout(instance);
        }
        else
        {
            Lora_OnRxTimeout(instance);
        }
    }
}

static void Lora_RawIrqProcess(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_tx_busy <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    uint16_t raw_irq = 0U;
    uint32_t primask;
    Sx1281BusStatus before;

    if ((PlatformGpio_IrqConsume(Sx1281Bus_Dio1Get(instance)) != 0U) ||
        (s_tx_busy != 0U) || (s_radio_in_rx != 0U))
    {
        Sx1281Bus_StatusGet(instance, &before);
        raw_irq = SX1280GetIrqStatus(instance);
        if (Lora_BusReadSucceeded(instance, before) == 0U) { raw_irq = 0U; }
    }
    primask = Lora_IrqLock();
    s_diag.raw_irq = raw_irq;
    Lora_IrqUnlock(primask);
    if (raw_irq != 0U)
    {
        Lora_DiagRecordIrq(instance, raw_irq);
        Lora_IrqProcess(instance, raw_irq);
        SX1280ClearIrqStatus(instance, raw_irq);
        s_diag_counted_raw_irq = raw_irq;
    }
    else
    {
        s_diag_counted_raw_irq = 0U;
    }
}

static void Lora_DiagnosticsRefresh(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_inited == 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    RadioStatus_t radio_status;
    uint8_t busy_gpio = 0U;
    uint8_t dio1_gpio = 0U;
    uint8_t packet_runtime;
    int16_t rssi_inst;
    uint32_t primask;
    Sx1281BusStatus before;

    if ((PlatformTime_Ms() - s_diag_last_refresh_ms) <
        LORA_DIAG_REFRESH_PERIOD_MS)
    {
        return;
    }
    Sx1281Bus_StatusGet(instance, &before);
    radio_status = SX1280GetStatus(instance);
    packet_runtime = (uint8_t)SX1280GetPacketType(instance);
    rssi_inst = (int16_t)SX1280GetRssiInst(instance);
    (void)PlatformGpio_Read(Sx1281Bus_BusyGet(instance), &busy_gpio);
    (void)PlatformGpio_Read(Sx1281Bus_Dio1Get(instance), &dio1_gpio);
    uint8_t reads_good = Lora_BusReadSucceeded(instance, before);
    primask = Lora_IrqLock();
    s_chip_status.status_value = radio_status.Value;
    s_chip_status.verified = (uint8_t)((reads_good != 0U) && (radio_status.Value != 0x00U) &&
                                      (radio_status.Value != 0xFFU));
    s_diag.packet_runtime = packet_runtime;
    s_diag.rssi_inst = rssi_inst;
    s_diag.rssi_inst_valid = reads_good;
    s_cached_busy_gpio = busy_gpio;
    s_cached_dio1_gpio = dio1_gpio;
    s_diag_last_refresh_ms = PlatformTime_Ms();
    Lora_IrqUnlock(primask);
}

static void Lora_TxReceiptRecord(uint8_t instance, LoraTxQueryResult result)
{
    uint32_t primask;
    SILVERSTAR_ASSERT((result == LoraTxQueryResult_Complete) || (result == LoraTxQueryResult_TimedOut),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    primask = Lora_IrqLock();
    if (s_contexts[instance].active_tx_id != 0U)
    {
        s_contexts[instance].completed_tx_id = s_contexts[instance].active_tx_id;
        s_contexts[instance].completed_tx_ms = PlatformTime_Ms();
        s_contexts[instance].completed_tx_result = result;
        s_contexts[instance].active_tx_id = 0U;
    }
    Lora_IrqUnlock(primask);
}

static void Lora_TxCompletionProcess(uint8_t instance)
{
    if (s_tx_done_flag != 0U)
    {
        s_tx_done_flag = 0U;
        s_tx_busy = 0U;
        Lora_StatsIncrement(&s_stats.tx_ok);
        Lora_TxReceiptRecord(instance, LoraTxQueryResult_Complete);
        Lora_SetRadioState(instance, LORA_RADIO_STATE_READY);
    }
    if (s_tx_timeout_flag != 0U)
    {
        s_tx_timeout_flag = 0U;
        s_tx_busy = 0U;
        Lora_StatsIncrement(&s_stats.tx_timeout);
        Lora_TxReceiptRecord(instance, LoraTxQueryResult_TimedOut);
        Lora_SetRadioState(instance, LORA_RADIO_STATE_READY);
    }
}

static void Lora_RxCompletionProcess(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(s_rx_done_flag <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    uint8_t size = 0U;
    int8_t rssi;
    int8_t snr;

    if (s_rx_done_flag == 0U)
    {
        return;
    }
    s_rx_done_flag = 0U;
    Sx1281BusStatus before;
    Sx1281Bus_StatusGet(instance, &before);
    uint8_t payload_result = SX1280GetPayload(instance, s_rx_tmp_buf, &size, LORA_MAX_PAYLOAD_LEN);
    SX1280GetPacketStatus(instance, &s_pkt_status);
    uint8_t reads_good = Lora_BusReadSucceeded(instance, before);
    if ((payload_result == 0U) && (reads_good != 0U))
    {
        SILVERSTAR_ASSERT(size <= LORA_MAX_PAYLOAD_LEN,
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
        if (s_contexts[instance].schedule_role == LoraScheduleRole_Ground)
        {
            s_rx_started_ms = PlatformTime_Ms();
            s_contexts[instance].rx_window_active = 2U;
        }
        rssi = s_pkt_status.Params.LoRa.RssiPkt;
        snr = s_pkt_status.Params.LoRa.SnrPkt;
        Lora_LastRxRecord(instance, size, rssi, snr);
        if (Lora_RxQueuePush(instance, s_rx_tmp_buf, size, rssi, snr) != 0U)
        {
            Lora_StatsIncrement(&s_stats.rx_ok);
        }
        else
        {
            Lora_StatsIncrement(&s_stats.rx_dropped);
        }
    }
    else
    {
        Lora_StatsIncrement(&s_stats.rx_dropped);
    }
    if (reads_good != 0U) { Lora_SetRadioState(instance, LORA_RADIO_STATE_READY); }
}

static void Lora_RxErrorProcess(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_rx_timeout_flag <= 1U) && (s_rx_error_flag <= 1U),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT((s_rx_error_flag == 0U) ||
        (s_rx_error_code == IRQ_CRC_ERROR_CODE) ||
        (s_rx_error_code == IRQ_HEADER_ERROR_CODE),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (s_rx_timeout_flag != 0U)
    {
        s_rx_timeout_flag = 0U;
        Lora_StatsIncrement(&s_stats.rx_timeout);
        Lora_SetRadioState(instance, LORA_RADIO_STATE_READY);
    }
    if (s_rx_error_flag != 0U)
    {
        s_rx_error_flag = 0U;
        Lora_StatsIncrement(&s_stats.rx_error);
        if (s_rx_error_code == IRQ_CRC_ERROR_CODE)
        {
            Lora_StatsIncrement(&s_stats.rx_crc_error);
        }
        Lora_SetRadioState(instance, LORA_RADIO_STATE_READY);
    }
}

void Lora_Process(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT((s_inited <= 1U) && (s_contexts[instance].rx_window_active <= 2U) &&
        ((s_contexts[instance].rx_window_active != 2U) ||
         (s_contexts[instance].schedule_role == LoraScheduleRole_Ground)),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (s_inited == 0)
    {
        return;
    }

    Lora_ControlProcess(instance);
    Lora_RawIrqProcess(instance);
    if ((s_tx_busy != 0U) && (s_tx_done_flag == 0U) && (s_tx_timeout_flag == 0U) &&
        ((uint32_t)(PlatformTime_Ms() - s_diag.last_settx_ms) >=
         ((uint32_t)LORA_TX_TIMEOUT_COUNT + LORA_RX_TURN_MARGIN_MS)))
    {
        /* Timeout step is fixed at1ms; recover a lost completion IRQ without
         * publishing a successful tracked receipt. */
        if (Lora_RadioRecover(instance, 1U) == 0U) { return; }
        s_tx_timeout_flag = 1U;
    }
    Lora_DiagnosticsRefresh(instance);
    Lora_TxCompletionProcess(instance);
    Lora_RxCompletionProcess(instance);
    Lora_RxErrorProcess(instance);
    if (s_tx_busy == 0)
    {
        if (Lora_RxPacketHeld(instance) != 0U) { return; }
        uint32_t rx_bound = Lora_RxListenMs(instance) +
            Lora_PacketAirtimeMs(instance, LORA_MAX_PAYLOAD_LEN) + LORA_RX_TURN_MARGIN_MS;
        if ((s_radio_in_rx != 0U) &&
            ((uint32_t)(PlatformTime_Ms() - s_rx_started_ms) >= rx_bound) &&
            (Lora_RxIdleForTx(instance) == 0U)) { return; }
        if ((s_tx_count != 0U) && (Lora_TxTurnAvailable(instance) != 0U) &&
            (Lora_RxIdleForTx(instance) != 0U))
        { Lora_TryStartNextTx(instance); return; }
        if (s_inited == 0U) { return; }
        if (s_radio_in_rx == 0)
        {
            /* Peer just finished its packet and grants Ground the channel.
             * Stay in standby during the early uplink slot rather than
             * starting RX and forcibly cutting an unseen preamble. */
            if ((s_contexts[instance].schedule_role == LoraScheduleRole_Ground) &&
                (s_contexts[instance].rx_window_active == 2U) &&
                ((uint32_t)(PlatformTime_Ms() - s_rx_started_ms) <
                 (Lora_RxGrantMs(instance) - LORA_RX_TURN_MARGIN_MS)))
            { return; }
            Lora_StartRx(instance);
        }
    }
}

LoraRxDequeueResult Lora_RxDequeue(uint8_t instance, uint8_t *data, uint8_t *len, int8_t *rssi, int8_t *snr)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    LoraRxPacket pkt;

    if ((data == 0) || (len == 0))
    {
        return LORA_RX_DEQUEUE_BAD_PARAM;
    }

    SILVERSTAR_ASSERT_OBJECT(data, uint8_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);

    if (Lora_RxQueuePop(instance, &pkt) == 0)
    {
        return LORA_RX_DEQUEUE_EMPTY;
    }

    memcpy(data, pkt.data, pkt.len);
    *len = pkt.len;

    if (rssi != 0)
    {
        *rssi = pkt.rssi;
    }

    if (snr != 0)
    {
        *snr = pkt.snr;
    }

    return LORA_RX_DEQUEUE_OK;
}

void Lora_GetStats(uint8_t instance, LoraStats *stats)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;

    if (stats == 0)
    {
        return;
    }

    primask = Lora_IrqLock();
    *stats = s_stats;
    Lora_IrqUnlock(primask);
}

void Lora_GetDebugSnapshot(uint8_t instance, LoraDebugSnapshot *snapshot)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;

    if (snapshot == 0)
    {
        return;
    }

    primask = Lora_IrqLock();
    snapshot->initialized = s_inited;
    snapshot->tx_queue_count = s_tx_count;
    snapshot->rx_queue_count = s_rx_count;
    snapshot->stats = s_stats;
    snapshot->busy_gpio = s_cached_busy_gpio;
    snapshot->dio1_gpio = s_cached_dio1_gpio;
    Lora_IrqUnlock(primask);
}

void Lora_GetDiagSnapshot(uint8_t instance, LoraDiagSnapshot *snapshot)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;

    if (snapshot == 0)
    {
        return;
    }

    primask = Lora_IrqLock();
    *snapshot = s_diag;
    Lora_IrqUnlock(primask);
}

LoraDiagResult Lora_IrqClear(uint8_t instance, uint16_t *raw_before)
{
    uint32_t transaction_id;
    LoraControlSubmitResult result;

    if (raw_before != 0)
    {
        *raw_before = 0U;
    }
    result = Lora_ControlSubmitInternal(instance, LORA_CONTROL_IRQ_CLEAR,
                                        LORA_CONTROL_DEFAULT_TIMEOUT_MS,
                                        1U,
                                        &transaction_id);
    (void)transaction_id;
    if (result == LORA_CONTROL_SUBMIT_OK)
    {
        return LORA_DIAG_RESULT_QUEUED;
    }
    return (result == LORA_CONTROL_SUBMIT_BUSY) ? LORA_DIAG_RESULT_BUSY :
                                                  LORA_DIAG_RESULT_NOT_INIT;
}

static LoraDiagResult Lora_ForceRxContinuousDirect(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;

    if (s_inited == 0U)
    {
        return LORA_DIAG_RESULT_NOT_INIT;
    }

    SILVERSTAR_ASSERT(s_pkt_params.PacketType == PACKET_TYPE_LORA,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);

    SX1280SetStandby(instance, STDBY_RC);
    SX1280ClearIrqStatus(instance, IRQ_RADIO_ALL);
    s_diag_counted_raw_irq = 0U;

    primask = Lora_IrqLock();
    s_tx_done_flag = 0U;
    s_rx_done_flag = 0U;
    s_tx_timeout_flag = 0U;
    s_rx_timeout_flag = 0U;
    s_rx_error_flag = 0U;
    s_tx_busy = 0U;
    s_radio_in_rx = 0U;
    s_contexts[instance].rx_packet_active = 0U;
    s_contexts[instance].rx_window_active = 1U;
    Lora_IrqUnlock(primask);

    s_pkt_params.Params.LoRa.PayloadLength = LORA_MAX_PAYLOAD_LEN;
    SX1280SetPacketParams(instance, &s_pkt_params);
    Lora_DiagSetDioIrqParams(instance, LORA_RX_IRQ_MASK, LORA_RX_IRQ_MASK, IRQ_RADIO_NONE, IRQ_RADIO_NONE);
    SX1280SetRx(instance, RX_TX_CONTINUOUS);
    Lora_DiagRecordSetRx(instance);

    primask = Lora_IrqLock();
    s_radio_in_rx = 1U;
    s_rx_started_ms = PlatformTime_Ms();
    Lora_IrqUnlock(primask);
    Lora_SetRadioState(instance, LORA_RADIO_STATE_RX);

    return LORA_DIAG_RESULT_OK;
}

void Lora_ClearStats(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    LoraRadioState state;
    uint32_t primask;

    primask = Lora_IrqLock();
    state = s_stats.radio_state;
    memset(&s_stats, 0, sizeof(s_stats));
    s_stats.radio_state = state;
    Lora_IrqUnlock(primask);
}

LoraBusyState Lora_IsBusy(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint8_t busy;
    uint32_t primask;

    primask = Lora_IrqLock();
    busy = ((s_tx_busy != 0) || (s_tx_count > 0U)) ? 1U : 0U;
    Lora_IrqUnlock(primask);

    if (busy != 0)
    {
        return LORA_BUSY_ACTIVE;
    }

    return LORA_BUSY_IDLE;
}

LoraDiagResult Lora_ChipStatusGet(uint8_t instance, LoraChipStatus *status)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;

    SILVERSTAR_ASSERT_OBJECT(&s_stats, LoraStats,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if ((status == 0) || (s_inited == 0U))
    {
        return LORA_DIAG_RESULT_NOT_INIT;
    }
    primask = Lora_IrqLock();
    *status = s_chip_status;
    Lora_IrqUnlock(primask);
    return LORA_DIAG_RESULT_OK;
}

LoraDiagResult Lora_ForceRxContinuous(uint8_t instance)
{
    uint32_t transaction_id;
    LoraControlSubmitResult result = Lora_ControlSubmitInternal(instance,
        LORA_CONTROL_FORCE_RX_CONTINUOUS,
        LORA_CONTROL_DEFAULT_TIMEOUT_MS,
        1U,
        &transaction_id);

    (void)transaction_id;
    if (result == LORA_CONTROL_SUBMIT_OK)
    {
        return LORA_DIAG_RESULT_QUEUED;
    }
    return (result == LORA_CONTROL_SUBMIT_BUSY) ? LORA_DIAG_RESULT_BUSY :
                                                  LORA_DIAG_RESULT_NOT_INIT;
}

LoraControlSubmitResult Lora_ControlSubmit(uint8_t instance, LoraControlOperation operation,
                                           uint32_t timeout_ms,
                                           uint32_t *transaction_id)
{
    return Lora_ControlSubmitInternal(instance, operation, timeout_ms, 0U,
                                      transaction_id);
}

static LoraControlSubmitResult Lora_ControlSubmitInternal(uint8_t instance,
    LoraControlOperation operation,
    uint32_t timeout_ms,
    uint8_t auto_release,
    uint32_t *transaction_id)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;
    uint32_t now_ms;

    if ((transaction_id == 0) || (timeout_ms == 0U) ||
        ((operation != LORA_CONTROL_IRQ_CLEAR) &&
         (operation != LORA_CONTROL_FORCE_RX_CONTINUOUS)))
    {
        return LORA_CONTROL_SUBMIT_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(transaction_id, uint32_t,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    if (s_inited == 0U) { return LORA_CONTROL_SUBMIT_NOT_INIT; }
    now_ms = PlatformTime_Ms();
    primask = Lora_IrqLock();
    Lora_ControlAssert(instance);
    if (((s_control_transaction.state == LoraControlStateSubmitted) ||
         (s_control_transaction.state == LoraControlStateComplete)) &&
        ((now_ms - s_control_transaction.submitted_ms) >=
         s_control_transaction.timeout_ms))
    {
        s_control_transaction.state = LoraControlStateIdle;
    }
    if (s_control_transaction.state != LoraControlStateIdle)
    {
        Lora_IrqUnlock(primask);
        return LORA_CONTROL_SUBMIT_BUSY;
    }
    s_control_transaction.next_transaction_id++;
    if (s_control_transaction.next_transaction_id == 0U)
    {
        s_control_transaction.next_transaction_id = 1U;
    }
    s_control_transaction.transaction_id =
        s_control_transaction.next_transaction_id;
    s_control_transaction.operation = operation;
    s_control_transaction.submitted_ms = now_ms;
    s_control_transaction.timeout_ms = timeout_ms;
    s_control_transaction.auto_release = auto_release;
    s_control_transaction.state = LoraControlStateSubmitted;
    *transaction_id = s_control_transaction.transaction_id;
    Lora_IrqUnlock(primask);
    return LORA_CONTROL_SUBMIT_OK;
}

LoraControlGetResult Lora_ControlResultGet(uint8_t instance, uint32_t transaction_id,
                                           LoraControlResult *result)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    uint32_t primask;

    if ((transaction_id == 0U) || (result == 0))
    {
        return LORA_CONTROL_GET_BAD_PARAM;
    }
    SILVERSTAR_ASSERT_OBJECT(result, LoraControlResult,
        SILVERSTAR_ASSERT_MODULE_DEVICE);
    primask = Lora_IrqLock();
    Lora_ControlAssert(instance);
    if ((s_control_transaction.state == LoraControlStateIdle) ||
        (s_control_transaction.transaction_id != transaction_id))
    {
        Lora_IrqUnlock(primask);
        return LORA_CONTROL_GET_NOT_FOUND;
    }
    if ((s_control_transaction.state == LoraControlStateSubmitted) &&
        ((PlatformTime_Ms() - s_control_transaction.submitted_ms) >=
         s_control_transaction.timeout_ms))
    {
        s_control_transaction.result.transaction_id = transaction_id;
        s_control_transaction.result.result = LORA_DIAG_RESULT_TIMEOUT;
        s_control_transaction.result.raw_irq_before = 0U;
        s_control_transaction.state = LoraControlStateComplete;
    }
    if (s_control_transaction.state != LoraControlStateComplete)
    {
        Lora_IrqUnlock(primask);
        return LORA_CONTROL_GET_PENDING;
    }
    *result = s_control_transaction.result;
    s_control_transaction.state = LoraControlStateIdle;
    Lora_IrqUnlock(primask);
    return LORA_CONTROL_GET_COMPLETE;
}

static void Lora_ControlProcess(uint8_t instance)
{
    SILVERSTAR_ASSERT(instance < PROJECT_SX1281_INSTANCE_COUNT,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    LoraControlOperation operation;
    LoraControlResult result;
    uint32_t primask;

    primask = Lora_IrqLock();
    SILVERSTAR_ASSERT((uint32_t)s_control_transaction.state <= LoraControlStateComplete,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    if (s_control_transaction.state != LoraControlStateSubmitted)
    {
        Lora_IrqUnlock(primask);
        return;
    }
    SILVERSTAR_ASSERT((s_control_transaction.operation == LORA_CONTROL_IRQ_CLEAR) ||
        (s_control_transaction.operation == LORA_CONTROL_FORCE_RX_CONTINUOUS),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    SILVERSTAR_ASSERT(s_control_transaction.transaction_id != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT(s_control_transaction.timeout_ms != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_TIME_INVARIANT);
    SILVERSTAR_ASSERT(s_control_transaction.auto_release <= 1U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if ((PlatformTime_Ms() - s_control_transaction.submitted_ms) >=
        s_control_transaction.timeout_ms)
    {
        s_control_transaction.result.transaction_id =
            s_control_transaction.transaction_id;
        s_control_transaction.result.result = LORA_DIAG_RESULT_TIMEOUT;
        s_control_transaction.result.raw_irq_before = 0U;
        s_control_transaction.state =
            (s_control_transaction.auto_release != 0U) ?
                LoraControlStateIdle : LoraControlStateComplete;
        Lora_IrqUnlock(primask);
        return;
    }
    operation = s_control_transaction.operation;
    result.transaction_id = s_control_transaction.transaction_id;
    result.raw_irq_before = 0U;
    s_control_transaction.state = LoraControlStateActive;
    Lora_IrqUnlock(primask);

    if (operation == LORA_CONTROL_IRQ_CLEAR)
    {
        result.raw_irq_before = SX1280GetIrqStatus(instance);
        SX1280ClearIrqStatus(instance, IRQ_RADIO_ALL);
        s_diag_counted_raw_irq = 0U;
        result.result = LORA_DIAG_RESULT_OK;
    }
    else
    {
        result.result = Lora_ForceRxContinuousDirect(instance);
    }

    primask = Lora_IrqLock();
    s_control_transaction.result = result;
    s_control_transaction.state =
        (s_control_transaction.auto_release != 0U) ?
            LoraControlStateIdle : LoraControlStateComplete;
    Lora_IrqUnlock(primask);
}

static void Lora_OnTxDone(uint8_t instance)
{
    Lora_StatsIncrement(&s_stats.tx_irq_count);
    s_tx_done_flag = 1U;
    s_radio_in_rx = 0U;
}

static void Lora_OnRxDone(uint8_t instance)
{
    s_contexts[instance].rx_packet_active = 0U;
    Lora_StatsIncrement(&s_stats.rx_irq_count);
    s_rx_done_flag = 1U;
    s_radio_in_rx = 0U;
}

static void Lora_OnTxTimeout(uint8_t instance)
{
    Lora_StatsIncrement(&s_stats.tx_timeout_irq_count);
    s_tx_timeout_flag = 1U;
    s_radio_in_rx = 0U;
}

static void Lora_OnRxTimeout(uint8_t instance)
{
    s_contexts[instance].rx_packet_active = 0U;
    Lora_StatsIncrement(&s_stats.rx_timeout_irq_count);
    s_rx_timeout_flag = 1U;
    s_radio_in_rx = 0U;
}

static void Lora_OnRxError(uint8_t instance, IrqErrorCode_t errCode)
{
    s_contexts[instance].rx_packet_active = 0U;
    Lora_StatsIncrement(&s_stats.rx_error_irq_count);
    s_rx_error_code = errCode;
    s_rx_error_flag = 1U;
    s_radio_in_rx = 0U;
}
