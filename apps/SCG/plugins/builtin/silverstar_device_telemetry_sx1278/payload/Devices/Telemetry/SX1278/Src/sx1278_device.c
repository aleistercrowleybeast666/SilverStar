#include "sx1278_device.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "project_resources.h"
#include "silverstar_assert.h"
#include <stddef.h>
#include <string.h>

#define SX1278_QUEUE_CAPACITY 2U
#define SX1278_RECEIPT_CAPACITY 4U
#define SX1278_TX_TIMEOUT_MS 250U
#define SX1278_QUEUE_TIMEOUT_MS 1000U
/* Fixed-profile maximum packet airtime is 121.088 ms; allow a complete reply. */
#define SX1278_RX_YIELD_MS 150U
#define SX1278_RECOVERY_MS 1000U
/* One extra millisecond covers quantization of the platform tick: these
 * guards guarantee at least 1 ms low and 5 ms after reset release. */
#define SX1278_RESET_LOW_GUARD_MS 2U
#define SX1278_RESET_RELEASE_GUARD_MS 6U

typedef enum
{
    Sx1278State_Stopped = 0, Sx1278State_ResetLow, Sx1278State_ResetWait,
    Sx1278State_Rx, Sx1278State_Tx, Sx1278State_Recovery
} Sx1278State;

typedef struct
{
    uint8_t data[SX1278_PACKET_CAPACITY];
    uint16_t length;
    uint32_t id, queued_ms;
} Sx1278Frame;

typedef struct
{
    Sx1278Frame frames[SX1278_QUEUE_CAPACITY];
    uint8_t head, count;
} Sx1278Queue;

typedef struct
{
    uint32_t id, queued_ms;
    Sx1278Result result;
} Sx1278Receipt;

typedef struct
{
    ProjectSx1278Resources resources;
    Sx1278ChipBus chip;
    Sx1278Queue control, data, rx;
    Sx1278Frame tx;
    Sx1278Receipt receipts[SX1278_RECEIPT_CAPACITY];
    Sx1278Stats stats;
    Sx1278Result stop_result;
    uint32_t since_ms, next_id;
    uint8_t receipt_next, initialized, wanted, stop_pending, tx_expired;
    Sx1278State state;
} Sx1278Context;

typedef struct
{
    uint8_t wanted, stop_pending;
} Sx1278Requests;

_Static_assert((PROJECT_SX1278_INSTANCE_COUNT == 1U) &&
    (PROJECT_SX1278_INSTANCE_COUNT_MAX == 1U),
    "Initial SX1278 profile has one explicit owner");
static Sx1278Context s_context;
static Sx1278Stats s_published;

static void Sx1278Queue_Check(const Sx1278Queue *queue)
{
    if ((queue->head >= SX1278_QUEUE_CAPACITY) || (queue->count > SX1278_QUEUE_CAPACITY))
    { s_context.stats.ready = 0U; s_published.ready = 0U; }
    SILVERSTAR_ASSERT(queue->head < SX1278_QUEUE_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    SILVERSTAR_ASSERT(queue->count <= SX1278_QUEUE_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
}

static void Sx1278_Publish(void)
{
    uint32_t lock = PlatformCritical_Enter();
    s_context.stats.state = (uint8_t)s_context.state;
    s_context.stats.initialized = s_context.initialized;
    s_context.stats.started = (uint8_t)(s_context.wanted != 0U);
    if ((s_context.wanted == 0U) || (s_context.stop_pending != 0U)) { s_context.stats.ready = 0U; }
    s_published = s_context.stats;
    PlatformCritical_Exit(lock);
}

static Sx1278Result Sx1278Frontend_Set(uint8_t rx, uint8_t tx)
{
    PlatformResult rx_off = PlatformGpio_Write(s_context.resources.rx_en, 0U);
    PlatformResult tx_off = PlatformGpio_Write(s_context.resources.tx_en, 0U);
    if ((rx_off != PLATFORM_OK) || (tx_off != PLATFORM_OK)) { return Sx1278Result_Io; }
    if (rx != 0U)
    { return (PlatformGpio_Write(s_context.resources.rx_en, 1U) == PLATFORM_OK) ? Sx1278Result_Ok : Sx1278Result_Io; }
    if (tx != 0U)
    { return (PlatformGpio_Write(s_context.resources.tx_en, 1U) == PLATFORM_OK) ? Sx1278Result_Ok : Sx1278Result_Io; }
    return Sx1278Result_Ok;
}

static void Sx1278_ReceiptFinish(Sx1278Result result)
{
    uint32_t lock = PlatformCritical_Enter();
    if (s_context.receipt_next >= SX1278_RECEIPT_CAPACITY)
    { s_context.stats.ready = 0U; s_published.ready = 0U; }
    SILVERSTAR_ASSERT(s_context.receipt_next < SX1278_RECEIPT_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (result == Sx1278Result_Ok)
    {
        if ((s_context.wanted == 0U) || (s_context.stop_pending != 0U))
        { result = Sx1278Result_Offline; s_context.stats.tx_dropped++; }
        else
        {
            s_context.stats.tx_ok++; s_context.stats.last_tx_ms = PlatformTime_Ms();
            s_context.stats.last_tx_us = PlatformTime_Us();
        }
    }
    if (s_context.tx.id != 0U)
    {
        Sx1278Receipt *receipt = &s_context.receipts[s_context.receipt_next];
        receipt->id = s_context.tx.id; receipt->queued_ms = s_context.tx.queued_ms;
        receipt->result = result;
        s_context.receipt_next = (uint8_t)((s_context.receipt_next + 1U) % SX1278_RECEIPT_CAPACITY);
    }
    s_context.tx.id = 0U;
    PlatformCritical_Exit(lock);
}

static Sx1278Result Sx1278_Quiesce(void)
{
    Sx1278Result frontend = Sx1278Frontend_Set(0U, 0U);
    PlatformResult reset = PlatformGpio_Write(s_context.resources.reset, 0U);
    PlatformResult nss = PlatformGpio_Write(s_context.resources.nss, 1U);
    return ((frontend == Sx1278Result_Ok) && (reset == PLATFORM_OK) &&
        (nss == PLATFORM_OK)) ? Sx1278Result_Ok : Sx1278Result_Io;
}

static Sx1278Result Sx1278_Fault(Sx1278Result result)
{
    uint32_t lock = PlatformCritical_Enter();
    Sx1278Result quiesced;
    s_context.stats.ready = 0U; s_published.ready = 0U;
    Sx1278Queue_Check(&s_context.control); Sx1278Queue_Check(&s_context.data);
    Sx1278Queue_Check(&s_context.rx);
    s_context.stats.tx_dropped += s_context.control.count + s_context.data.count;
    s_context.stats.rx_dropped += s_context.rx.count;
    s_context.control.count = 0U; s_context.data.count = 0U; s_context.rx.count = 0U;
    s_context.state = Sx1278State_Recovery;
    PlatformCritical_Exit(lock);
    if (s_context.tx.id != 0U)
    {
        s_context.stats.tx_dropped++;
        if (s_context.tx_expired != 0U) { s_context.stats.tx_timeout++; }
        Sx1278_ReceiptFinish(result);
    }
    quiesced = Sx1278_Quiesce();
    if (quiesced != Sx1278Result_Ok) { s_context.stats.transport_error++; }
    s_context.since_ms = PlatformTime_Ms();
    return quiesced;
}

static Sx1278Requests Sx1278_RequestsGet(void)
{
    uint32_t lock = PlatformCritical_Enter();
    uint8_t valid = (uint8_t)((s_context.initialized == 1U) &&
        (s_context.wanted <= 1U) && (s_context.stop_pending <= 1U) &&
        ((s_context.stop_result == Sx1278Result_Ok) || (s_context.stop_result == Sx1278Result_Busy) ||
         (s_context.stop_result == Sx1278Result_Io)) &&
        ((uint32_t)s_context.state <= (uint32_t)Sx1278State_Recovery) &&
        ((s_context.state == Sx1278State_Tx) == (s_context.tx.id != 0U)));
    Sx1278Requests requests = {s_context.wanted, s_context.stop_pending};
    if (valid == 0U) { s_context.stats.ready = 0U; s_published.ready = 0U; }
    SILVERSTAR_ASSERT(valid != 0U,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    PlatformCritical_Exit(lock);
    return requests;
}

static Sx1278Result Sx1278_StopProcess(void)
{
    uint32_t lock = PlatformCritical_Enter();
    uint8_t restart = s_context.wanted;
    Sx1278Result result;
    /* A later Start cannot erase an earlier Stop. A new Stop during the
     * bounded quiesce remains pending for the next owner invocation. */
    s_context.stop_pending = 0U;
    PlatformCritical_Exit(lock);
    result = Sx1278_Fault(Sx1278Result_Offline);
    lock = PlatformCritical_Enter();
    if (result == Sx1278Result_Ok) { s_context.state = Sx1278State_Stopped; }
    s_context.stop_result = result;
    PlatformCritical_Exit(lock);
    return (result == Sx1278Result_Ok) ?
        ((restart != 0U) ? Sx1278Result_Ok : Sx1278Result_Offline) : result;
}

static Sx1278Result Sx1278_ResourcesValidate(const ProjectSx1278Resources *resources)
{
    uint8_t index, other;
    PlatformGpioId pins[5] = {resources->nss, resources->reset,
        resources->dio0, resources->rx_en, resources->tx_en};
    if ((resources->spi >= PLATFORM_SPI_COUNT) || (resources->time >= PLATFORM_TIME_COUNT))
    { return Sx1278Result_Invalid; }
    for (index = 0U; index < 5U; index++)
    {
        if (pins[index] >= PLATFORM_GPIO_COUNT) { return Sx1278Result_Invalid; }
        for (other = 0U; other < index; other++)
        { if (pins[index] == pins[other]) { return Sx1278Result_Invalid; } }
    }
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_Init(uint8_t instance)
{
    uint32_t lock;
    ProjectSx1278Resources resources;
    if (instance != 0U) { return Sx1278Result_Invalid; }
    if (ProjectSx1278Resources_Get(instance, &resources) != SYSTEM_DEVICE_OK)
    { return Sx1278Result_Invalid; }
    if (Sx1278_ResourcesValidate(&resources) != Sx1278Result_Ok) { return Sx1278Result_Invalid; }
    lock = PlatformCritical_Enter();
    if (s_context.initialized != 0U) { PlatformCritical_Exit(lock); return Sx1278Result_Busy; }
    s_context.resources = resources; s_context.chip.spi = resources.spi;
    s_context.chip.nss = resources.nss; s_context.initialized = 1U;
    s_context.stop_result = Sx1278Result_Busy;
    s_published.initialized = 1U;
    PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_Start(uint8_t instance)
{
    uint32_t lock = PlatformCritical_Enter();
    if ((instance != 0U) || (s_context.initialized == 0U))
    { PlatformCritical_Exit(lock); return Sx1278Result_Invalid; }
    s_context.wanted = 1U; s_context.stop_result = Sx1278Result_Busy;
    PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_Stop(uint8_t instance)
{
    uint32_t lock = PlatformCritical_Enter();
    if ((instance != 0U) || (s_context.initialized == 0U))
    { PlatformCritical_Exit(lock); return Sx1278Result_Invalid; }
    if (s_context.wanted != 0U) { s_context.stop_result = Sx1278Result_Busy; }
    if ((s_context.stop_result != Sx1278Result_Ok) || (s_context.state != Sx1278State_Stopped))
    { s_context.stop_pending = 1U; }
    s_context.wanted = 0U; s_context.stats.ready = 0U;
    s_published.ready = 0U; s_published.started = 0U;
    PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_StopStatusGet(uint8_t instance)
{
    uint32_t lock = PlatformCritical_Enter();
    Sx1278Result result;
    if ((instance != 0U) || (s_context.initialized == 0U))
    { PlatformCritical_Exit(lock); return Sx1278Result_Invalid; }
    result = (s_context.wanted != 0U) ? Sx1278Result_Busy : s_context.stop_result;
    PlatformCritical_Exit(lock);
    return result;
}

static Sx1278Result Sx1278_RxStart(void)
{
    Sx1278Result result = Sx1278Chip_ModeSet(&s_context.chip, 1U);
    if (result == Sx1278Result_Ok) { result = Sx1278Frontend_Set(1U, 0U); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x40U, 0U); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x12U, 0xFFU); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_ModeSet(&s_context.chip, 5U); }
    if (result == Sx1278Result_Ok)
    {
        uint32_t lock = PlatformCritical_Enter();
        s_context.state = Sx1278State_Rx; s_context.since_ms = PlatformTime_Ms();
        /* Stop may have arrived during a bounded bus call. */
        s_context.stats.ready = (uint8_t)((s_context.wanted != 0U) && (s_context.stop_pending == 0U));
        PlatformCritical_Exit(lock);
    }
    return result;
}

static Sx1278Result Sx1278_RxRead(void)
{
    Sx1278Frame frame = {0};
    uint8_t current, length, modem, flags;
    uint32_t lock;
    Sx1278Result result = Sx1278Chip_ModeSet(&s_context.chip, 1U);
    if (result != Sx1278Result_Ok) { return result; }
    /* RXCONT may finish another packet between the wake-up flag read and
     * standby. Re-read after freezing the modem, before trusting this FIFO. */
    result = Sx1278Chip_Read(&s_context.chip, 0x12U, &flags, 1U);
    if (result != Sx1278Result_Ok) { return result; }
    if (((flags & 0x40U) == 0U) || ((flags & 0x08U) != 0U)) { return Sx1278Result_Io; }
    /* Explicit LoRa header reports whether the sender enabled payload CRC. */
    result = Sx1278Chip_Read(&s_context.chip, 0x1CU, &modem, 1U);
    if (result != Sx1278Result_Ok) { return result; }
    if (((flags & 0x20U) != 0U) || ((modem & 0x40U) == 0U))
    { s_context.stats.rx_crc_error++; s_context.stats.rx_dropped++; return Sx1278Result_Ok; }
    result = Sx1278Chip_Read(&s_context.chip, 0x13U, &length, 1U);
    if (result != Sx1278Result_Ok) { return result; }
    if ((length == 0U) || (length > SX1278_PACKET_CAPACITY))
    { s_context.stats.rx_dropped++; return Sx1278Result_Ok; }
    result = Sx1278Chip_Read(&s_context.chip, 0x10U, &current, 1U);
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x0DU, current); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_Read(&s_context.chip, 0U, frame.data, length); }
    if (result != Sx1278Result_Ok) { return result; }
    frame.length = length; lock = PlatformCritical_Enter();
    Sx1278Queue_Check(&s_context.rx);
    if ((s_context.rx.count < SX1278_QUEUE_CAPACITY) &&
        (s_context.wanted != 0U) && (s_context.stop_pending == 0U))
    {
        uint8_t tail = (uint8_t)((s_context.rx.head + s_context.rx.count) % SX1278_QUEUE_CAPACITY);
        s_context.rx.frames[tail] = frame; s_context.rx.count++;
        s_context.stats.rx_ok++; s_context.stats.last_rx_ms = PlatformTime_Ms();
        s_context.stats.last_rx_us = PlatformTime_Us();
    }
    else { s_context.stats.rx_dropped++; }
    PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}

static uint8_t Sx1278_TxTake(void)
{
    uint32_t lock = PlatformCritical_Enter();
    Sx1278Queue *queue = &s_context.control;
    Sx1278Queue_Check(queue); Sx1278Queue_Check(&s_context.data);
    if (queue->count == 0U) { queue = &s_context.data; }
    /* Expired data cannot be hidden forever by the higher-priority lane. */
    if ((s_context.data.count != 0U) &&
        ((uint32_t)(PlatformTime_Ms() - s_context.data.frames[s_context.data.head].queued_ms) >= SX1278_QUEUE_TIMEOUT_MS))
    { queue = &s_context.data; }
    if ((queue->count == 0U) || (s_context.wanted == 0U) || (s_context.stop_pending != 0U))
    { PlatformCritical_Exit(lock); return 0U; }
    s_context.tx = queue->frames[queue->head];
    if ((s_context.tx.length == 0U) || (s_context.tx.length > SX1278_PACKET_CAPACITY) || (s_context.tx.id == 0U))
    { s_context.stats.ready = 0U; s_published.ready = 0U; }
    SILVERSTAR_ASSERT((s_context.tx.length > 0U) &&
        (s_context.tx.length <= SX1278_PACKET_CAPACITY) && (s_context.tx.id != 0U),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    queue->head = (uint8_t)((queue->head + 1U) % SX1278_QUEUE_CAPACITY); queue->count--;
    PlatformCritical_Exit(lock);
    return 1U;
}

static uint8_t Sx1278_QueueExpiredGet(uint32_t now)
{
    uint32_t lock = PlatformCritical_Enter();
    uint8_t expired;
    Sx1278Queue_Check(&s_context.control); Sx1278Queue_Check(&s_context.data);
    expired = (uint8_t)(((s_context.control.count != 0U) &&
        ((uint32_t)(now - s_context.control.frames[s_context.control.head].queued_ms) >= SX1278_QUEUE_TIMEOUT_MS)) ||
        ((s_context.data.count != 0U) &&
        ((uint32_t)(now - s_context.data.frames[s_context.data.head].queued_ms) >= SX1278_QUEUE_TIMEOUT_MS)));
    PlatformCritical_Exit(lock);
    return expired;
}

static Sx1278Result Sx1278_TxStart(uint32_t now)
{
    Sx1278Result result = Sx1278Chip_ModeSet(&s_context.chip, 1U);
    if (result == Sx1278Result_Ok) { result = Sx1278Frontend_Set(0U, 0U); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x0DU, 0U); }
    if (result == Sx1278Result_Ok)
    { result = Sx1278Chip_Write(&s_context.chip, 0U, s_context.tx.data, (uint8_t)s_context.tx.length); }
    if (result == Sx1278Result_Ok)
    { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x22U, (uint8_t)s_context.tx.length); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x40U, 0x40U); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_RegisterWrite(&s_context.chip, 0x12U, 0xFFU); }
    if (result == Sx1278Result_Ok) { result = Sx1278Frontend_Set(0U, 1U); }
    if (result == Sx1278Result_Ok) { result = Sx1278Chip_ModeSet(&s_context.chip, 3U); }
    if (result == Sx1278Result_Ok) { s_context.state = Sx1278State_Tx; s_context.since_ms = now; }
    return result;
}

static Sx1278Result Sx1278_TxScheduledStart(uint32_t now)
{
    if (((uint32_t)(now - s_context.since_ms) < SX1278_RX_YIELD_MS) || (Sx1278_TxTake() == 0U))
    { return Sx1278Result_Empty; }
    if ((uint32_t)(now - s_context.tx.queued_ms) >= SX1278_QUEUE_TIMEOUT_MS)
    { s_context.tx_expired = 1U; return Sx1278Result_Timeout; }
    return Sx1278_TxStart(now);
}

static Sx1278Result Sx1278_RunningProcess(uint32_t now)
{
    uint8_t flags, mode;
    Sx1278Result result;
    /* Consume only a hint. Polling flags handles lost/coalesced DIO0 edges. */
    (void)PlatformGpio_IrqConsume(s_context.resources.dio0);
    result = Sx1278Chip_Read(&s_context.chip, 0x01U, &mode, 1U);
    if (result != Sx1278Result_Ok) { return result; }
    /* Detect uncommanded reset/mode loss before interpreting the shared
     * register bank as LoRa. TX may autonomously return to standby at TxDone. */
    if (((s_context.state == Sx1278State_Rx) && (mode != 0x8DU)) ||
        ((s_context.state == Sx1278State_Tx) && (mode != 0x8BU) && (mode != 0x89U)))
    { return Sx1278Result_Io; }
    result = Sx1278Chip_Read(&s_context.chip, 0x12U, &flags, 1U);
    if (result != Sx1278Result_Ok) { return result; }
    /* Include the bounded SPI duration when applying the TX/queue deadline. */
    now = PlatformTime_Ms();
    if (s_context.state == Sx1278State_Tx)
    {
        /* Deadline wins over a late completion: never publish a late success. */
        if ((uint32_t)(now - s_context.since_ms) >= SX1278_TX_TIMEOUT_MS)
        { s_context.tx_expired = 1U; return Sx1278Result_Timeout; }
        if ((mode == 0x89U) && ((flags & 0x08U) == 0U)) { return Sx1278Result_Io; }
        if ((flags & 0xF7U) != 0U) { return Sx1278Result_Io; }
        if ((flags & 0x08U) == 0U) { return Sx1278Result_Ok; }
        Sx1278_ReceiptFinish(Sx1278Result_Ok);
        return Sx1278_RxStart();
    }
    if ((flags & 0x08U) != 0U) { return Sx1278Result_Io; }
    if ((flags & 0x40U) != 0U)
    {
        uint32_t window_started = s_context.since_ms;
        result = Sx1278_RxRead();
        if (result != Sx1278Result_Ok) { return result; }
        result = Sx1278_TxScheduledStart(now);
        if (result != Sx1278Result_Empty) { return result; }
        result = Sx1278_RxStart();
        s_context.since_ms = window_started;
        return result;
    }
    if (flags != 0U)
    { return Sx1278Chip_RegisterWrite(&s_context.chip, 0x12U, flags); }
    result = Sx1278_TxScheduledStart(now);
    return (result == Sx1278Result_Empty) ? Sx1278Result_Ok : result;
}

static Sx1278Result Sx1278_StateProcess(uint32_t now)
{
    Sx1278Result result;
    if ((s_context.state == Sx1278State_Stopped) ||
        ((s_context.state == Sx1278State_Recovery) &&
         ((uint32_t)(now - s_context.since_ms) >= SX1278_RECOVERY_MS)))
    {
        result = Sx1278_Quiesce();
        if (result == Sx1278Result_Ok)
        { s_context.state = Sx1278State_ResetLow; s_context.since_ms = PlatformTime_Ms(); s_context.stats.recovery_attempts++; }
        return result;
    }
    if ((s_context.state == Sx1278State_ResetLow) &&
        ((uint32_t)(now - s_context.since_ms) >= SX1278_RESET_LOW_GUARD_MS))
    {
        if (PlatformGpio_Write(s_context.resources.reset, 1U) != PLATFORM_OK) { return Sx1278Result_Io; }
        s_context.state = Sx1278State_ResetWait; s_context.since_ms = PlatformTime_Ms();
    }
    else if ((s_context.state == Sx1278State_ResetWait) &&
        ((uint32_t)(now - s_context.since_ms) >= SX1278_RESET_RELEASE_GUARD_MS))
    {
        result = Sx1278Chip_Configure(&s_context.chip);
        return (result == Sx1278Result_Ok) ? Sx1278_RxStart() : result;
    }
    else if ((s_context.state == Sx1278State_Rx) || (s_context.state == Sx1278State_Tx))
    { return Sx1278_RunningProcess(now); }
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_Process(uint8_t instance)
{
    uint32_t now;
    Sx1278Requests requests;
    Sx1278Result result, quiesced;
    if ((instance != 0U) || (s_context.initialized == 0U)) { return Sx1278Result_Invalid; }
    requests = Sx1278_RequestsGet();
    s_context.tx_expired = 0U;
    now = PlatformTime_Ms();
    if ((requests.wanted == 0U) || (requests.stop_pending != 0U))
    {
        result = Sx1278_StopProcess(); Sx1278_Publish(); return result;
    }
    if (((s_context.state == Sx1278State_Rx) || (s_context.state == Sx1278State_Tx)) &&
        (Sx1278_QueueExpiredGet(now) != 0U))
    {
        if ((s_context.tx.id == 0U) && (Sx1278_TxTake() == 0U)) { result = Sx1278Result_Offline; }
        else { s_context.tx_expired = 1U; result = Sx1278Result_Timeout; }
    }
    else { result = Sx1278_StateProcess(now); }
    if (result != Sx1278Result_Ok)
    {
        if (((result == Sx1278Result_Io) || (result == Sx1278Result_Timeout)) &&
            (s_context.tx_expired == 0U)) { s_context.stats.transport_error++; }
        if ((result == Sx1278Result_Timeout) && (s_context.tx_expired == 0U)) { s_context.stats.bus_timeout++; }
        quiesced = Sx1278_Fault(result);
        if (quiesced != Sx1278Result_Ok) { result = quiesced; }
    }
    requests = Sx1278_RequestsGet();
    if ((requests.wanted == 0U) || (requests.stop_pending != 0U))
    {
        quiesced = Sx1278_StopProcess();
        if ((result == Sx1278Result_Ok) || (quiesced == Sx1278Result_Io)) { result = quiesced; }
    }
    Sx1278_Publish();
    return result;
}

Sx1278Result Sx1278_Send(uint8_t instance, const uint8_t *data,
    uint16_t length, uint8_t control, uint32_t *transaction_id)
{
    uint32_t lock;
    Sx1278Queue *queue;
    Sx1278Frame *frame;
    if ((instance != 0U) || (data == NULL) || (length == 0U) ||
        (length > SX1278_PACKET_CAPACITY) || (control > 1U)) { return Sx1278Result_Invalid; }
    lock = PlatformCritical_Enter();
    if ((s_published.ready == 0U) || (s_context.wanted == 0U) || (s_context.stop_pending != 0U))
    { PlatformCritical_Exit(lock); return Sx1278Result_Offline; }
    queue = (control != 0U) ? &s_context.control : &s_context.data;
    Sx1278Queue_Check(queue);
    if (queue->count == SX1278_QUEUE_CAPACITY) { PlatformCritical_Exit(lock); return Sx1278Result_Busy; }
    /* Exhaustion requires restart, preventing an old receipt from aliasing. */
    if (s_context.next_id == UINT32_MAX) { PlatformCritical_Exit(lock); return Sx1278Result_Offline; }
    frame = &queue->frames[(queue->head + queue->count) % SX1278_QUEUE_CAPACITY];
    (void)memcpy(frame->data, data, length); frame->length = length;
    frame->queued_ms = PlatformTime_Ms(); frame->id = ++s_context.next_id;
    queue->count++;
    if (transaction_id != NULL) { *transaction_id = frame->id; }
    PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_ReceiptGet(uint8_t instance, uint32_t id, uint32_t *age_ms)
{
    uint8_t index, lane;
    uint32_t lock;
    if ((instance != 0U) || (id == 0U) || (age_ms == NULL)) { return Sx1278Result_Invalid; }
    lock = PlatformCritical_Enter();
    for (index = 0U; index < SX1278_RECEIPT_CAPACITY; index++)
    {
        if (s_context.receipts[index].id == id)
        {
            Sx1278Result result = s_context.receipts[index].result;
            *age_ms = PlatformTime_Ms() - s_context.receipts[index].queued_ms;
            PlatformCritical_Exit(lock); return result;
        }
    }
    for (lane = 0U; lane < 2U; lane++)
    {
        const Sx1278Queue *queue = (lane == 0U) ? &s_context.control : &s_context.data;
        Sx1278Queue_Check(queue);
        for (index = 0U; index < queue->count; index++)
        {
            const Sx1278Frame *frame = &queue->frames[(queue->head + index) % SX1278_QUEUE_CAPACITY];
            if (frame->id == id)
            { *age_ms = PlatformTime_Ms() - frame->queued_ms; PlatformCritical_Exit(lock); return Sx1278Result_Busy; }
        }
    }
    if (s_context.tx.id == id)
    { *age_ms = PlatformTime_Ms() - s_context.tx.queued_ms; PlatformCritical_Exit(lock); return Sx1278Result_Busy; }
    PlatformCritical_Exit(lock);
    return Sx1278Result_NotPresent;
}

Sx1278Result Sx1278_Receive(uint8_t instance, uint8_t *data, uint16_t capacity, uint16_t *length)
{
    uint32_t lock;
    const Sx1278Frame *frame;
    if ((instance != 0U) || (data == NULL) || (length == NULL)) { return Sx1278Result_Invalid; }
    *length = 0U; lock = PlatformCritical_Enter();
    if ((s_context.wanted == 0U) || (s_context.stop_pending != 0U) || (s_published.ready == 0U))
    { PlatformCritical_Exit(lock); return Sx1278Result_Offline; }
    Sx1278Queue_Check(&s_context.rx);
    if (s_context.rx.count == 0U) { PlatformCritical_Exit(lock); return Sx1278Result_Empty; }
    frame = &s_context.rx.frames[s_context.rx.head];
    if ((frame->length == 0U) || (frame->length > SX1278_PACKET_CAPACITY))
    { s_context.stats.ready = 0U; s_published.ready = 0U; }
    SILVERSTAR_ASSERT((frame->length > 0U) && (frame->length <= SX1278_PACKET_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (capacity < frame->length) { PlatformCritical_Exit(lock); return Sx1278Result_Invalid; }
    (void)memcpy(data, frame->data, frame->length); *length = frame->length;
    s_context.rx.head = (uint8_t)((s_context.rx.head + 1U) % SX1278_QUEUE_CAPACITY); s_context.rx.count--;
    PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}

Sx1278Result Sx1278_StatsGet(uint8_t instance, Sx1278Stats *stats)
{
    uint32_t lock;
    if ((instance != 0U) || (stats == NULL)) { return Sx1278Result_Invalid; }
    lock = PlatformCritical_Enter(); *stats = s_published; PlatformCritical_Exit(lock);
    return Sx1278Result_Ok;
}
