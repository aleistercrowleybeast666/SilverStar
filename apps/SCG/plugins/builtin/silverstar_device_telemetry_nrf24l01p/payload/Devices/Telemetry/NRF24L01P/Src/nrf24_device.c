#include "nrf24_device.h"

#include <limits.h>
#include <stddef.h>
#include <string.h>
#include "air_link_config.h"
#include "platform_critical.h"
#include "platform_gpio.h"
#include "platform_spi.h"
#include "platform_time.h"
#include "project_resources.h"
#include "silverstar_assert.h"

#define NRF24_QUEUE_CAPACITY 2U
#define NRF24_RECEIPT_CAPACITY 4U
#define NRF24_SPI_TIMEOUT_MS 2U
#define NRF24_RECOVERY_US 1000000ULL

typedef enum
{
    Nrf24State_Stopped = 0, Nrf24State_Por, Nrf24State_Config,
    Nrf24State_PowerWait, Nrf24State_RxSettle, Nrf24State_Rx,
    Nrf24State_TxPulse, Nrf24State_TxWait, Nrf24State_Recovery
} Nrf24State;

typedef struct
{
    uint8_t data[NRF24_LOGICAL_MTU];
    uint8_t length;
    uint32_t id;
    uint32_t queued_ms;
} Nrf24Frame;

typedef struct
{
    Nrf24Frame frames[NRF24_QUEUE_CAPACITY];
    uint8_t head;
    uint8_t count;
} Nrf24Queue;

typedef struct
{
    uint32_t id;
    uint32_t queued_ms;
    Nrf24Result result;
} Nrf24Receipt;

typedef struct
{
    ProjectNrf24Resources resources;
    Nrf24Queue control;
    Nrf24Queue data;
    Nrf24Frame tx;
    Nrf24FragmentRx rx;
    Nrf24Receipt receipts[NRF24_RECEIPT_CAPACITY];
    Nrf24Stats stats;
    uint64_t since_us;
    uint64_t tx_timeout_us;
    uint32_t next_id;
    uint16_t session;
    uint16_t sequence;
    uint8_t fragment;
    uint8_t tx_active;
    uint8_t receipt_next;
    uint8_t wanted;
    uint8_t configured;
    Nrf24State state;
} Nrf24Context;

_Static_assert((AIR_LINK_PACKET_MTU >= 50U) && (AIR_LINK_PACKET_MTU <= NRF24_LOGICAL_MTU),
    "NRF24 logical MTU must preserve AIR M0 and fit static storage");

_Static_assert((AIR_LINK_NRF24_DATA_RATE_KBPS == 250U) ||
    (AIR_LINK_NRF24_DATA_RATE_KBPS == 1000U) || (AIR_LINK_NRF24_DATA_RATE_KBPS == 2000U),
    "NRF24 timeout requires a supported nonzero physical rate");
_Static_assert(AIR_LINK_NRF24_RETRY_SETUP <= 255U,
    "NRF24 retry setup must fit the validated hardware register");

static Nrf24Context s_contexts[PROJECT_NRF24_INSTANCE_COUNT];
static Nrf24Stats s_published[PROJECT_NRF24_INSTANCE_COUNT];

_Static_assert((PROJECT_NRF24_INSTANCE_COUNT == 1U) &&
    (PROJECT_NRF24_INSTANCE_COUNT == PROJECT_NRF24_INSTANCE_COUNT_MAX),
    "NRF24 runtime supports one configured pair only");

/* This polling backend owns SPI/CE in Process; no EXTI handler calls the radio.
 * STATUS/FIFO polling also handles missing edges and IRQ-low races. */
static Nrf24Result Nrf24_Command(Nrf24Context *context, uint8_t opcode,
    const uint8_t *data, uint8_t *output, uint8_t length)
{
    uint8_t tx[NRF24_PHYSICAL_MTU + 1U] = {0};
    uint8_t rx[NRF24_PHYSICAL_MTU + 1U] = {0};
    PlatformResult result;
    PlatformResult release;
    if (length > NRF24_PHYSICAL_MTU) { return Nrf24Result_Invalid; }
    tx[0] = opcode;
    if (data != NULL) { (void)memcpy(&tx[1], data, length); }
    result = PlatformGpio_Write(context->resources.csn, 0U);
    if (result == PLATFORM_OK)
    {
        result = PlatformSpi_Transfer(context->resources.spi, tx, rx,
            (uint16_t)(length + 1U), NRF24_SPI_TIMEOUT_MS);
    }
    release = PlatformGpio_Write(context->resources.csn, 1U);
    if ((result != PLATFORM_OK) || (release != PLATFORM_OK))
    {
        context->stats.spi_error++;
        if (result == PLATFORM_TIMEOUT) { context->stats.spi_timeout++; }
        return (result == PLATFORM_TIMEOUT) ? Nrf24Result_Timeout : Nrf24Result_Io;
    }
    if (output != NULL) { (void)memcpy(output, &rx[1], length); }
    return Nrf24Result_Ok;
}

static Nrf24Result Nrf24_RegisterWrite(Nrf24Context *context,
    uint8_t reg, uint8_t value)
{
    return Nrf24_Command(context, (uint8_t)(0x20U | reg), &value, NULL, 1U);
}

static Nrf24Result Nrf24_Verify(Nrf24Context *context,
    uint8_t reg, const uint8_t *value, uint8_t length)
{
    uint8_t actual[5] = {0};
    if ((length == 0U) || (length > sizeof(actual))) { return Nrf24Result_Invalid; }
    if ((Nrf24_Command(context, (uint8_t)(0x20U | reg), value, NULL, length) != Nrf24Result_Ok) ||
        (Nrf24_Command(context, reg, NULL, actual, length) != Nrf24Result_Ok))
    { return Nrf24Result_Io; }
    return (memcmp(actual, value, length) == 0) ? Nrf24Result_Ok : Nrf24Result_Io;
}

static Nrf24Result Nrf24_Configure(Nrf24Context *context)
{
    static const uint8_t address[5] = AIR_LINK_NRF24_ADDRESS_BYTES;
    static const uint8_t registers[8] = {0x00U, 0x01U, 0x02U, 0x03U, 0x04U, 0x05U, 0x06U, 0x1CU};
    static const uint8_t values[8] = {0x0CU, 0x01U, 0x01U, 0x03U,
        AIR_LINK_NRF24_RETRY_SETUP, AIR_LINK_NRF24_CHANNEL,
        AIR_LINK_NRF24_RF_SETUP, 0x01U};
    uint8_t index;
    uint8_t feature = 0x04U;
    uint8_t activate = 0x73U;
    if (PlatformGpio_Write(context->resources.ce, 0U) != PLATFORM_OK) { return Nrf24Result_Io; }
    for (index = 0U; index < 8U; index++)
    {
        if (Nrf24_Verify(context, registers[index], &values[index], 1U) != Nrf24Result_Ok)
        { return Nrf24Result_Io; }
    }
    /* Genuine plus chips expose FEATURE directly; a locked FEATURE requires
     * ACTIVATE once, followed by readback. Never accept an absent/all-FF bus. */
    if (Nrf24_Verify(context, 0x1DU, &feature, 1U) != Nrf24Result_Ok)
    {
        if ((Nrf24_Command(context, 0x50U, &activate, NULL, 1U) != Nrf24Result_Ok) ||
            (Nrf24_Verify(context, 0x1DU, &feature, 1U) != Nrf24Result_Ok))
        { return Nrf24Result_Io; }
    }
    if ((Nrf24_Verify(context, 0x0AU, address, 5U) != Nrf24Result_Ok) ||
        (Nrf24_Verify(context, 0x10U, address, 5U) != Nrf24Result_Ok) ||
        (Nrf24_Command(context, 0xE1U, NULL, NULL, 0U) != Nrf24Result_Ok) ||
        (Nrf24_Command(context, 0xE2U, NULL, NULL, 0U) != Nrf24Result_Ok) ||
        (Nrf24_RegisterWrite(context, 0x07U, 0x70U) != Nrf24Result_Ok))
    { return Nrf24Result_Io; }
    return Nrf24_Verify(context, 0x00U, (const uint8_t[]){0x0FU}, 1U);
}

static void Nrf24_ReceiptFinish(Nrf24Context *context, Nrf24Result result)
{
    uint32_t lock = PlatformCritical_Enter();
    SILVERSTAR_ASSERT(context->receipt_next < NRF24_RECEIPT_CAPACITY,
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_INDEX_RANGE);
    if (context->tx.id != 0U)
    {
        Nrf24Receipt *receipt = &context->receipts[context->receipt_next];
        receipt->id = context->tx.id; receipt->queued_ms = context->tx.queued_ms;
        receipt->result = result;
        context->receipt_next = (uint8_t)((context->receipt_next + 1U) % NRF24_RECEIPT_CAPACITY);
    }
    context->tx_active = 0U;
    PlatformCritical_Exit(lock);
}

static void Nrf24_Fault(Nrf24Context *context, uint64_t now_us)
{
    uint32_t lock;
    PlatformResult ce_result = PlatformGpio_Write(context->resources.ce, 0U);
    if (ce_result != PLATFORM_OK) { context->stats.spi_error++; }
    if (context->tx_active != 0U)
    { context->stats.tx_dropped++; Nrf24_ReceiptFinish(context, Nrf24Result_Io); }
    lock = PlatformCritical_Enter();
    /* Unstarted control receipts become NOT_PRESENT. Never replay queues on recovery. */
    context->control.count = 0U; context->data.count = 0U;
    context->configured = 0U; context->stats.ready = 0U;
    s_published[0].ready = 0U; /* Same critical publication boundary as queue discard. */
    context->rx.active = 0U; context->rx.ready = 0U; context->rx.mask = 0U;
    context->since_us = now_us; context->state = Nrf24State_Recovery;
    PlatformCritical_Exit(lock);
}

Nrf24Result Nrf24_Init(uint8_t instance)
{
    Nrf24Context *context;
    if (instance >= PROJECT_NRF24_INSTANCE_COUNT) { return Nrf24Result_Invalid; }
    context = &s_contexts[instance];
    if (context->state != Nrf24State_Stopped) { return Nrf24Result_Busy; }
    if (ProjectNrf24Resources_Get(instance, &context->resources) != SYSTEM_DEVICE_OK)
    { return Nrf24Result_Invalid; }
    context->session = 1U;
    if ((PlatformGpio_Write(context->resources.ce, 0U) != PLATFORM_OK) ||
        (PlatformGpio_Write(context->resources.csn, 1U) != PLATFORM_OK))
    {
        Nrf24_Fault(context, PlatformTime_Us());
        return Nrf24Result_Ok; /* Static context accepted; owner retries asynchronously. */
    }
    context->session = 1U; /* Volatile tag; not a persistent boot identity. */
    context->since_us = PlatformTime_Us(); context->state = Nrf24State_Por;
    return Nrf24Result_Ok;
}

Nrf24Result Nrf24_Start(uint8_t instance)
{
    if (instance >= PROJECT_NRF24_INSTANCE_COUNT) { return Nrf24Result_Invalid; }
    if (s_contexts[instance].state == Nrf24State_Stopped) { return Nrf24Result_Offline; }
    s_contexts[instance].wanted = 1U;
    return Nrf24Result_Ok;
}

Nrf24Result Nrf24_Stop(uint8_t instance)
{
    Nrf24Context *context;
    if (instance >= PROJECT_NRF24_INSTANCE_COUNT) { return Nrf24Result_Invalid; }
    context = &s_contexts[instance];
    Nrf24_Fault(context, PlatformTime_Us());
    context->wanted = 0U; context->state = Nrf24State_Stopped;
    {
        uint32_t lock = PlatformCritical_Enter();
        s_published[instance].ready = 0U;
        PlatformCritical_Exit(lock);
    }
    return (PlatformGpio_Write(context->resources.ce, 0U) == PLATFORM_OK) ?
        Nrf24Result_Ok : Nrf24Result_Io;
}

static Nrf24Result Nrf24_QueueTake(Nrf24Context *context)
{
    uint32_t lock = PlatformCritical_Enter();
    Nrf24Queue *queue = (context->control.count != 0U) ? &context->control : &context->data;
    SILVERSTAR_ASSERT((queue->count <= NRF24_QUEUE_CAPACITY) &&
        (queue->head < NRF24_QUEUE_CAPACITY), SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (queue->count == 0U) { PlatformCritical_Exit(lock); return Nrf24Result_Empty; }
    context->tx = queue->frames[queue->head]; queue->count--;
    queue->head = (uint8_t)((queue->head + 1U) % NRF24_QUEUE_CAPACITY);
    context->tx_active = 1U; context->fragment = 0U;
    /* Increment session on sequence wrap. Identity reuse after 2^32 frames is
     * not allowed: fail-stop through the existing assertion contract. */
    context->sequence++;
    if (context->sequence == 0U)
    {
        SILVERSTAR_ASSERT(context->session != UINT16_MAX,
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
        context->session++;
    }
    PlatformCritical_Exit(lock);
    return Nrf24Result_Ok;
}

Nrf24Result Nrf24_Send(uint8_t instance, const uint8_t *data,
    uint16_t length, uint8_t control, uint32_t *transaction_id)
{
    Nrf24Context *context;
    Nrf24Queue *queue;
    Nrf24Frame *frame;
    uint32_t lock;
    if ((instance >= PROJECT_NRF24_INSTANCE_COUNT) || (data == NULL) ||
        (length == 0U) || (length > AIR_LINK_PACKET_MTU) || (length > NRF24_LOGICAL_MTU) || (control > 1U))
    { return Nrf24Result_Invalid; }
    context = &s_contexts[instance];
    lock = PlatformCritical_Enter();
    if (s_published[instance].ready == 0U) { PlatformCritical_Exit(lock); return Nrf24Result_Offline; }
    queue = (control != 0U) ? &context->control : &context->data;
    SILVERSTAR_ASSERT((queue->count <= NRF24_QUEUE_CAPACITY) && (queue->head < NRF24_QUEUE_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    if (queue->count == NRF24_QUEUE_CAPACITY) { PlatformCritical_Exit(lock); return Nrf24Result_Busy; }
    if ((transaction_id != NULL) && (context->next_id == UINT32_MAX))
    { PlatformCritical_Exit(lock); return Nrf24Result_Invalid; }
    frame = &queue->frames[(queue->head + queue->count) % NRF24_QUEUE_CAPACITY];
    (void)memcpy(frame->data, data, length); frame->length = (uint8_t)length;
    frame->queued_ms = PlatformTime_Ms(); frame->id = 0U;
    if (transaction_id != NULL) { context->next_id++; frame->id = context->next_id; *transaction_id = frame->id; }
    queue->count++;
    PlatformCritical_Exit(lock);
    return Nrf24Result_Ok;
}

static Nrf24Result Nrf24_RxDrain(Nrf24Context *context)
{
    uint8_t fifo = 0U;
    uint8_t length = 0U;
    uint8_t packet[NRF24_PHYSICAL_MTU];
    uint8_t index;
    Nrf24FragmentResult result;
    for (index = 0U; index < 3U; index++)
    {
        if (Nrf24_Command(context, 0x17U, NULL, &fifo, 1U) != Nrf24Result_Ok) { return Nrf24Result_Io; }
        if ((fifo & 1U) != 0U) { break; }
        if (Nrf24_Command(context, 0x60U, NULL, &length, 1U) != Nrf24Result_Ok) { return Nrf24Result_Io; }
        if ((length == 0U) || (length > NRF24_PHYSICAL_MTU))
        {
            context->stats.integrity_error++;
            context->rx.active = 0U; context->rx.mask = 0U;
            return Nrf24_Command(context, 0xE2U, NULL, NULL, 0U);
        }
        if (Nrf24_Command(context, 0x61U, NULL, packet, length) != Nrf24Result_Ok) { return Nrf24Result_Io; }
        result = Nrf24Fragment_Accept(&context->rx, packet, length, PlatformTime_Ms());
        if (result == Nrf24FragmentResult_Ok) { context->stats.rx_ok++; context->stats.last_rx_ms = PlatformTime_Ms(); }
        else if ((result == Nrf24FragmentResult_Invalid) || (result == Nrf24FragmentResult_Integrity) ||
                 (result == Nrf24FragmentResult_Conflict)) { context->stats.integrity_error++; }
        else if (result == Nrf24FragmentResult_Busy) { context->stats.rx_dropped++; }
        if (result == Nrf24FragmentResult_Integrity) { context->stats.rx_crc_error++; }
    }
    /* Clear only RX_DR; poll FIFO next round even if this races a new packet. */
    return Nrf24_RegisterWrite(context, 0x07U, 0x40U);
}

static uint64_t Nrf24_TxTimeoutUs_Get(uint8_t payload_length)
{
    /* ESB packet: preamble 8 + address 40 + control 9 + CRC16 = 73 bits.
     * ARD runs from one packet end to the next packet start (Nordic PS p34).
     * Include an ACK turnaround/empty packet on every attempt, even though
     * those windows overlap ARD, plus the first standby-to-TX 130 us. This
     * conservative radio deadline does not assume a bounded owner latency;
     * sticky terminal status is always consumed before checking elapsed time. */
    uint64_t rate = AIR_LINK_NRF24_DATA_RATE_KBPS;
    uint64_t packet_us = ((73ULL + 8ULL * payload_length) * 1000ULL + rate - 1ULL) / rate;
    uint64_t ack_us = 130ULL + (73000ULL + rate - 1ULL) / rate;
    uint64_t retries = AIR_LINK_NRF24_RETRY_SETUP & 0x0FU;
    uint64_t delay_us = ((AIR_LINK_NRF24_RETRY_SETUP >> 4U) + 1ULL) * 250ULL;
    return 130ULL + (retries + 1ULL) * (packet_us + ack_us) + retries * delay_us;
}

static Nrf24Result Nrf24_TxBegin(Nrf24Context *context)
{
    uint8_t packet[NRF24_PHYSICAL_MTU];
    uint8_t length = 0U;
    SILVERSTAR_ASSERT((context->tx.length > 0U) && (context->tx.length <= NRF24_LOGICAL_MTU) &&
        (context->fragment < NRF24_FRAGMENT_COUNT_MAX), SILVERSTAR_ASSERT_MODULE_DEVICE,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (Nrf24Fragment_Encode(context->tx.data, context->tx.length,
        context->session, context->sequence, context->fragment, packet, &length) != Nrf24FragmentResult_Ok)
    { return Nrf24Result_Invalid; }
    context->tx_timeout_us = Nrf24_TxTimeoutUs_Get(length);
    if ((PlatformGpio_Write(context->resources.ce, 0U) != PLATFORM_OK) ||
        (Nrf24_RegisterWrite(context, 0x00U, 0x0EU) != Nrf24Result_Ok) ||
        (Nrf24_RegisterWrite(context, 0x07U, 0x30U) != Nrf24Result_Ok) ||
        (Nrf24_Command(context, 0xA0U, packet, NULL, length) != Nrf24Result_Ok) ||
        (PlatformGpio_Write(context->resources.ce, 1U) != PLATFORM_OK))
    { return Nrf24Result_Io; }
    context->since_us = PlatformTime_Us(); context->state = Nrf24State_TxPulse;
    return Nrf24Result_Ok;
}

static Nrf24Result Nrf24_ReturnRx(Nrf24Context *context)
{
    if ((Nrf24_RegisterWrite(context, 0x00U, 0x0FU) != Nrf24Result_Ok) ||
        (PlatformGpio_Write(context->resources.ce, 1U) != PLATFORM_OK))
    { return Nrf24Result_Io; }
    context->state = Nrf24State_RxSettle; context->since_us = PlatformTime_Us();
    return Nrf24Result_Ok;
}

static Nrf24Result Nrf24_TxPoll(Nrf24Context *context, uint64_t now_us)
{
    uint8_t status = 0U;
    if (Nrf24_Command(context, 0x07U, NULL, &status, 1U) != Nrf24Result_Ok) { return Nrf24Result_Io; }
    if ((status & 0x30U) == 0x30U)
    { context->stats.integrity_error++; return Nrf24Result_Io; }
    /* Hardware terminal events are sticky. A late owner cannot turn an
     * already completed transmission into a timeout. Conflicting events are
     * an ordinary device fault, not evidence of success. */
    if (((status & 0x20U) == 0U) && (((status & 0x10U) != 0U) ||
        ((now_us - context->since_us) >= context->tx_timeout_us)))
    {
        /* MAX_RT retains FIFO payload: lower CE, flush, clear IRQ before RX.
         * No driver-level resend of this logical command. */
        if ((Nrf24_Command(context, 0xE1U, NULL, NULL, 0U) != Nrf24Result_Ok) ||
            (Nrf24_RegisterWrite(context, 0x07U, 0x30U) != Nrf24Result_Ok)) { return Nrf24Result_Io; }
        context->stats.tx_timeout++; Nrf24_ReceiptFinish(context, Nrf24Result_Timeout);
        return Nrf24_ReturnRx(context);
    }
    if ((status & 0x20U) == 0U) { return Nrf24Result_Ok; }
    if (Nrf24_RegisterWrite(context, 0x07U, 0x20U) != Nrf24Result_Ok) { return Nrf24Result_Io; }
    context->fragment++;
    if ((uint16_t)context->fragment * NRF24_FRAGMENT_DATA >= context->tx.length)
    {
        context->stats.tx_ok++; context->stats.last_tx_ms = PlatformTime_Ms();
        Nrf24_ReceiptFinish(context, Nrf24Result_Ok);
        return Nrf24_ReturnRx(context);
    }
    return Nrf24_TxBegin(context);
}

static Nrf24Result Nrf24_StateProcess(Nrf24Context *context, uint64_t now_us)
{
    uint64_t elapsed = now_us - context->since_us;
    switch (context->state)
    {
        case Nrf24State_Por:
            if (elapsed >= 100000ULL) { context->state = Nrf24State_Config; }
            break;
        case Nrf24State_Config:
            if (Nrf24_Configure(context) != Nrf24Result_Ok) { return Nrf24Result_Io; }
            context->since_us = PlatformTime_Us(); context->state = Nrf24State_PowerWait;
            break;
        case Nrf24State_PowerWait:
            /* 5 ms covers the specification's external-crystal startup table. */
            if ((elapsed >= 5000ULL) && (context->wanted != 0U))
            { return Nrf24_ReturnRx(context); }
            break;
        case Nrf24State_RxSettle:
            if (elapsed >= 130ULL)
            { context->state = Nrf24State_Rx; context->configured = 1U; context->stats.ready = 1U; }
            break;
        case Nrf24State_Rx:
            if (Nrf24_RxDrain(context) != Nrf24Result_Ok) { return Nrf24Result_Io; }
            if (Nrf24_QueueTake(context) == Nrf24Result_Ok) { return Nrf24_TxBegin(context); }
            break;
        case Nrf24State_TxPulse:
            if (elapsed >= 15ULL)
            {
                if (PlatformGpio_Write(context->resources.ce, 0U) != PLATFORM_OK) { return Nrf24Result_Io; }
                context->state = Nrf24State_TxWait;
            }
            break;
        case Nrf24State_TxWait: return Nrf24_TxPoll(context, now_us);
        case Nrf24State_Recovery:
            if (elapsed >= NRF24_RECOVERY_US)
            {
                context->stats.recovery_attempts++;
                /* Failed physical recovery must not consume logical identity.
                 * Keep the last allocated sequence and drop, never resend, TX.
                 * This permits indefinitely many bounded recovery rounds. */
                context->state = Nrf24State_Config;
            }
            break;
        case Nrf24State_Stopped: break;
        default:
            return Nrf24Result_Invalid;
    }
    return Nrf24Result_Ok;
}

void Nrf24_Process(uint8_t instance)
{
    Nrf24Context *context;
    uint64_t now_us;
    uint32_t lock;
    if (instance >= PROJECT_NRF24_INSTANCE_COUNT) { return; }
    context = &s_contexts[instance]; now_us = PlatformTime_Us();
    SILVERSTAR_ASSERT((context->state >= Nrf24State_Stopped) && (context->state <= Nrf24State_Recovery),
        SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    Nrf24Fragment_Expire(&context->rx, PlatformTime_Ms());
    if (Nrf24_StateProcess(context, now_us) != Nrf24Result_Ok) { Nrf24_Fault(context, now_us); }
    context->stats.state = (uint8_t)context->state;
    lock = PlatformCritical_Enter(); s_published[instance] = context->stats; PlatformCritical_Exit(lock);
}

Nrf24Result Nrf24_ReceiptGet(uint8_t instance, uint32_t transaction_id,
    uint32_t *age_ms)
{
    Nrf24Context *context;
    uint32_t lock;
    uint8_t index;
    uint8_t lane;
    Nrf24Result result = Nrf24Result_NotPresent;
    if ((instance >= PROJECT_NRF24_INSTANCE_COUNT) || (transaction_id == 0U) || (age_ms == NULL))
    { return Nrf24Result_Invalid; }
    context = &s_contexts[instance]; *age_ms = 0U; lock = PlatformCritical_Enter();
    for (index = 0U; index < NRF24_RECEIPT_CAPACITY; index++)
    {
        if (context->receipts[index].id == transaction_id)
        { *age_ms = PlatformTime_Ms() - context->receipts[index].queued_ms; result = context->receipts[index].result; }
    }
    if ((context->tx_active != 0U) && (context->tx.id == transaction_id))
    { *age_ms = PlatformTime_Ms() - context->tx.queued_ms; result = Nrf24Result_Busy; }
    for (lane = 0U; lane < 2U; lane++)
    {
        const Nrf24Queue *queue = (lane == 0U) ? &context->control : &context->data;
        SILVERSTAR_ASSERT((queue->count <= NRF24_QUEUE_CAPACITY) && (queue->head < NRF24_QUEUE_CAPACITY),
            SILVERSTAR_ASSERT_MODULE_DEVICE, SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
        for (index = 0U; index < NRF24_QUEUE_CAPACITY; index++)
        {
            const Nrf24Frame *frame = &queue->frames[(queue->head + index) % NRF24_QUEUE_CAPACITY];
            if ((index < queue->count) && (frame->id == transaction_id))
            { *age_ms = PlatformTime_Ms() - frame->queued_ms; result = Nrf24Result_Busy; }
        }
    }
    PlatformCritical_Exit(lock); return result;
}

Nrf24Result Nrf24_Receive(uint8_t instance, uint8_t *data,
    uint16_t capacity, uint16_t *length)
{
    Nrf24FragmentResult result;
    if (instance >= PROJECT_NRF24_INSTANCE_COUNT) { return Nrf24Result_Invalid; }
    result = Nrf24Fragment_Read(&s_contexts[instance].rx, data, capacity, length);
    if (result == Nrf24FragmentResult_Ok) { return Nrf24Result_Ok; }
    return (result == Nrf24FragmentResult_Empty) ? Nrf24Result_Empty : Nrf24Result_Invalid;
}

Nrf24Result Nrf24_StatsGet(uint8_t instance, Nrf24Stats *stats)
{
    uint32_t lock;
    if ((instance >= PROJECT_NRF24_INSTANCE_COUNT) || (stats == NULL)) { return Nrf24Result_Invalid; }
    lock = PlatformCritical_Enter(); *stats = s_published[instance]; PlatformCritical_Exit(lock);
    return Nrf24Result_Ok;
}
