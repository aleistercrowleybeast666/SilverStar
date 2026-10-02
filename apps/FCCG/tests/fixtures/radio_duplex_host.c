/* Actual generated Flight/Ground drivers and Ground adapter. The physical
 * ports below model Semtech timed RX, preamble/header/completion, and airtime.
 * This is software scheduling evidence, never hardware qualification. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#define TEST_SX1281_PORTS_ONLY 1
#define SX1280SendPayload Previous_Send
#define SX1280SetRx Previous_SetRx
#define SX1280SetStandby Previous_SetStandby
#define SX1280GetStatus Previous_Status
#define SX1280GetIrqStatus Previous_Irq
#define SX1280ClearIrqStatus Previous_Clear
#define SX1280GetPayload Previous_Payload
#include "test_sx1281_device.c"
#undef SX1280SendPayload
#undef SX1280SetRx
#undef SX1280SetStandby
#undef SX1280GetStatus
#undef SX1280GetIrqStatus
#undef SX1280ClearIrqStatus
#undef SX1280GetPayload
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout);
void SX1280SetRx(uint8_t instance, TickTime_t timeout);
void SX1280SetStandby(uint8_t instance, RadioStandbyModes_t mode);
RadioStatus_t SX1280GetStatus(uint8_t instance);
uint16_t SX1280GetIrqStatus(uint8_t instance);
void SX1280ClearIrqStatus(uint8_t instance, uint16_t irq);
uint8_t SX1280GetPayload(uint8_t instance, uint8_t *data, uint8_t *length, uint8_t maximum);
#include "sx1281_device.c"
#undef s_tx_count
#undef s_rx_count
#include "ground_radio.h"
LoraScheduleRoleResult Ground_Lora_ScheduleRoleSet(uint8_t instance, LoraScheduleRole role);
LoraRxDequeueResult Ground_Lora_RxDequeue(uint8_t instance, uint8_t *data, uint8_t *len, int8_t *rssi, int8_t *snr);

typedef struct
{
    uint8_t rx_mode, tx_mode, receiving, detected, valid;
    uint8_t payload[64], length;
    uint16_t irq, suppress;
    uint64_t rx_deadline, rx_start, rx_end, tx_start, tx_end;
    unsigned int sent, received, software_abort, collisions;
    uint8_t send_sequence[128];
} PhysicalRadio;
static PhysicalRadio s_hw[2];
static unsigned int s_endpoint;
static uint64_t s_ms;
static uint32_t s_clock_base;
static unsigned int s_command_received, s_ack_received, s_enqueue_errors;
static uint8_t s_trace;

/* Independent datasheet calculation for the frozen SF10/BW812500/CR4/5 PHY. */
static uint32_t Physical_Airtime(uint8_t length)
{
    double symbols = 16.0 + 4.25 + 8.0 + ceil((8.0 * length + 4.0) / 40.0) * 5.0;
    return (uint32_t)ceil(symbols * 1024.0 / 812.5);
}
static void Physical_Receive(unsigned int endpoint, const uint8_t *data, uint8_t length,
                             uint64_t start, uint64_t end)
{
    PhysicalRadio *radio = &s_hw[endpoint];
    if ((radio->rx_mode == 0U) || (radio->tx_mode != 0U)) { return; }
    radio->receiving = 1U; radio->detected = 0U; radio->valid = 1U;
    radio->rx_start = start; radio->rx_end = end; radio->length = length;
    memcpy(radio->payload, data, length);
}
static void Physical_Events(void)
{
    for (unsigned int endpoint = 0U; endpoint < 2U; endpoint++)
    {
        PhysicalRadio *radio = &s_hw[endpoint];
        if ((radio->tx_mode != 0U) && (s_ms >= radio->tx_end))
        { radio->tx_mode = 0U; radio->irq |= (uint16_t)(IRQ_TX_DONE & ~radio->suppress); }
        if ((radio->receiving != 0U) && (radio->detected == 0U) && (s_ms >= radio->rx_start + 8U))
        {
            radio->detected = 1U;
            radio->irq |= (uint16_t)(IRQ_PREAMBLE_DETECTED & ~radio->suppress);
        }
        if ((radio->receiving != 0U) && (s_ms == radio->rx_start + 36U))
        { radio->irq |= (uint16_t)(IRQ_HEADER_VALID & ~radio->suppress); }
        if ((radio->receiving != 0U) && (s_ms >= radio->rx_end))
        {
            radio->receiving = 0U; radio->rx_mode = 0U;
            radio->irq |= (uint16_t)((radio->valid != 0U ? IRQ_RX_DONE : IRQ_CRC_ERROR) & ~radio->suppress);
        }
        if ((radio->rx_mode != 0U) && (radio->detected == 0U) && (s_ms >= radio->rx_deadline))
        {
            /* Native timed RX expires before detection; this is not software
             * switching TX while an admitted packet is still demodulating. */
            radio->rx_mode = 0U; radio->receiving = 0U;
            radio->irq |= (uint16_t)(IRQ_RX_TX_TIMEOUT & ~radio->suppress);
        }
    }
}
void SX1280SetStandby(uint8_t instance, RadioStandbyModes_t mode)
{
    (void)instance; (void)mode;
    PhysicalRadio *radio = &s_hw[s_endpoint];
    if ((radio->receiving != 0U) && (radio->valid != 0U) && (s_ms < radio->rx_end))
    { radio->software_abort++; }
    radio->rx_mode = 0U; radio->tx_mode = 0U; radio->receiving = 0U; radio->detected = 0U;
}
void SX1280SetRx(uint8_t instance, TickTime_t timeout)
{
    (void)instance;
    PhysicalRadio *radio = &s_hw[s_endpoint];
    TEST_CHECK(radio->receiving == 0U);
    radio->rx_mode = 1U; radio->detected = 0U;
    radio->rx_deadline = timeout.NbSteps == UINT16_MAX ? UINT64_MAX :
        s_ms + (uint64_t)timeout.NbSteps * (timeout.Step == RADIO_TICK_SIZE_4000_US ? 4U : 1U);
    /* Allow joining a transmission while its configured preamble remains. */
    PhysicalRadio *peer = &s_hw[1U - s_endpoint];
    if ((peer->tx_mode != 0U) && (s_ms <= peer->tx_start + 12U))
    { Physical_Receive(s_endpoint, peer->payload, peer->length, s_ms, peer->tx_end); }
}
RadioStatus_t SX1280GetStatus(uint8_t instance)
{
    (void)instance; RadioStatus_t status;
    status.Value = s_hw[s_endpoint].tx_mode != 0U ? 0xC0U :
        (s_hw[s_endpoint].rx_mode != 0U ? 0xA0U : 0x40U);
    return status;
}
uint16_t SX1280GetIrqStatus(uint8_t instance)
{ (void)instance; return s_hw[s_endpoint].irq; }
void SX1280ClearIrqStatus(uint8_t instance, uint16_t irq)
{ (void)instance; s_hw[s_endpoint].irq &= (uint16_t)~irq; }
uint8_t SX1280GetPayload(uint8_t instance, uint8_t *data, uint8_t *length, uint8_t maximum)
{
    (void)instance; PhysicalRadio *radio = &s_hw[s_endpoint];
    if ((radio->valid == 0U) || (radio->length > maximum)) { return 1U; }
    memcpy(data, radio->payload, radio->length); *length = radio->length;
    radio->received++; return 0U;
}
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout)
{
    (void)instance; (void)timeout;
    PhysicalRadio *radio = &s_hw[s_endpoint];
    if (s_trace != 0U) { printf("SEND ms=%llu endpoint=%u len=%u type=%02x peer_tx=%u ownrx=%u\n",
        (unsigned long long)s_ms, s_endpoint, length, data[0], s_hw[1U-s_endpoint].tx_mode, radio->receiving); }
    TEST_CHECK((radio->receiving == 0U) || (radio->valid == 0U) || (s_ms >= radio->rx_end));
    if (radio->sent < 128U) { radio->send_sequence[radio->sent] = data[1]; }
    radio->sent++; radio->rx_mode = 0U; radio->tx_mode = 1U;
    radio->tx_start = s_ms; radio->tx_end = s_ms + Physical_Airtime(length);
    memcpy(radio->payload, data, length); radio->length = length;
    PhysicalRadio *peer = &s_hw[1U - s_endpoint];
    if (peer->tx_mode != 0U)
    { radio->collisions++; peer->collisions++; peer->valid = 0U; }
    else { Physical_Receive(1U - s_endpoint, data, length, s_ms, radio->tx_end); }
}
static void Duplex_Init(uint32_t clock_base, uint8_t with_flight)
{
    memset(s_hw, 0, sizeof(s_hw)); s_ms = 0U; s_clock_base = clock_base;
    s_tick_ms = clock_base; s_command_received = 0U; s_ack_received = 0U; s_enqueue_errors = 0U;
    s_endpoint = 1U; TEST_CHECK(GroundRadio_Init() == GROUND_RADIO_OK);
    if (with_flight != 0U)
    { s_endpoint = 0U; TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK); Lora_StartRx(0U); }
}
static void Duplex_QueueFlight(void)
{
    uint8_t normal[26] = {0x11U};
    s_endpoint = 0U;
    (void)Lora_TxEnqueue(0U, normal, sizeof(normal));
}
static void Duplex_Step(uint64_t ms, uint8_t flight, uint8_t refill)
{
    s_ms = ms; s_tick_ms = s_clock_base + (uint32_t)ms;
    Physical_Events();
    if (flight != 0U)
    {
        s_endpoint = 0U; Lora_Process(0U);
        uint8_t data[64], length = 0U;
        if (Lora_RxDequeue(0U, data, &length, NULL, NULL) == LORA_RX_DEQUEUE_OK)
        {
            if (data[0] == 0x20U)
            {
                s_command_received++; uint8_t ack[9] = {0x40U}; ack[1] = data[1];
                if (Lora_TxEnqueuePriority(0U, ack, sizeof(ack)) != LORA_TX_ENQUEUE_OK) { s_enqueue_errors++; }
            }
        }
        if (refill != 0U) { Duplex_QueueFlight(); }
    }
    s_endpoint = 1U; GroundRadio_Process();
    uint8_t data[64], length = 0U;
    if (Ground_Lora_RxDequeue(0U, data, &length, NULL, NULL) == LORA_RX_DEQUEUE_OK)
    { if (data[0] == 0x40U) { s_ack_received++; } }
}
static void Test_PhaseScan(void)
{
    unsigned int worst_ack_ms = 0U, total_collisions = 0U;
    for (unsigned int phase = 0U; phase < (s_trace != 0U ? 1U : 800U); phase++)
    {
        Duplex_Init(phase % 2U == 0U ? 0U : UINT32_MAX - 1000U, 1U);
        Duplex_QueueFlight(); Duplex_QueueFlight();
        uint8_t command[9] = {0x20U, 17U};
        unsigned int completed = 0U;
        for (unsigned int ms = 0U; ms < 3000U; ms++)
        {
            if ((ms >= phase) && (((ms - phase) % 800U) == 0U))
            { s_endpoint = 1U; TEST_CHECK(GroundRadio_TxEnqueue(command, sizeof(command)) == GROUND_RADIO_OK); }
            Duplex_Step(ms, 1U, 1U);
            if (s_ack_received != 0U) { completed = ms - phase; break; }
        }
        TEST_CHECK(s_ack_received != 0U); TEST_CHECK(s_enqueue_errors == 0U);
        TEST_CHECK(s_hw[0].software_abort == 0U && s_hw[1].software_abort == 0U);
        TEST_CHECK(s_hw[0].collisions == 0U && s_hw[1].collisions == 0U);
        if (completed > worst_ack_ms) { worst_ack_ms = completed; }
        total_collisions += s_hw[0].collisions;
    }
    printf("PHASE_SCAN phases800 worst_ack_ms=%u collisions=%u\n", worst_ack_ms, total_collisions);
}
static void Test_Boundary(void)
{
    for (unsigned int suppressed = 0U; suppressed < 4U; suppressed++)
    {
        for (unsigned int start = 0U; start < 122U; start++)
        {
            Duplex_Init(UINT32_MAX - 100U, 1U); Duplex_QueueFlight();
            s_hw[0].suppress = suppressed == 0U ? 0U : suppressed == 1U ? IRQ_PREAMBLE_DETECTED :
                suppressed == 2U ? (IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID) : IRQ_RADIO_ALL;
            uint8_t command[9] = {0x20U, 9U};
            for (unsigned int ms = 0U; ms < 700U; ms++)
            {
                s_ms = ms;
                if (ms == start) { Physical_Receive(0U, command, sizeof(command), ms, ms + 49U); }
                Duplex_Step(ms, 1U, 0U);
            }
            TEST_CHECK(s_hw[0].software_abort == 0U); TEST_CHECK(s_hw[0].sent != 0U);
        }
    }
    printf("BOUNDARY122 phases x4 IRQ suppression modes: no software RX preemption\n");
}
static void Test_QueueAndNoPeer(void)
{
    Duplex_Init(UINT32_MAX - 100U, 0U);
    s_endpoint = 1U;
#ifndef DUPLEX_LEGACY_GROUND
    TEST_CHECK(Ground_Lora_ScheduleRoleSet(0U, LoraScheduleRole_Flight) == LoraScheduleRoleResult_NotReady);
#endif
    uint8_t command[64] = {0x20U};
    for (uint8_t index = 0U; index < 8U; index++)
    { command[1] = index; TEST_CHECK(GroundRadio_TxEnqueue(command, sizeof(command)) == GROUND_RADIO_OK); }
    TEST_CHECK(GroundRadio_TxEnqueue(command, sizeof(command)) == GROUND_RADIO_BUSY);
    for (unsigned int ms = 0U; ms < 4000U; ms++) { Duplex_Step(ms, 0U, 0U); }
    TEST_CHECK(s_hw[1].sent == 8U);
    for (uint8_t index = 0U; index < 8U; index++) { TEST_CHECK(s_hw[1].send_sequence[index] == index); }
    printf("NO_PEER full8 FIFO drained within4000ms through wrap\n");
}
static void Test_StartupAndFullStream(void)
{
    unsigned int worst = 0U, startup_collisions = 0U;
    for (unsigned int boot = 0U; boot < 500U; boot++)
    {
        Duplex_Init(UINT32_MAX - 250U, 0U);
        uint8_t command[9] = {0x20U, 12U};
        s_endpoint = 1U; TEST_CHECK(GroundRadio_TxEnqueue(command, sizeof(command)) == GROUND_RADIO_OK);
        unsigned int finished = 0U;
        for (unsigned int ms = 0U; ms < 3000U; ms++)
        {
            if (ms == boot)
            {
                s_ms = ms; s_tick_ms = s_clock_base + ms; s_endpoint = 0U;
                TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK); Lora_StartRx(0U);
            }
            if (ms != 0U && (ms % 800U) == 0U)
            { s_endpoint = 1U; TEST_CHECK(GroundRadio_TxEnqueue(command, sizeof(command)) == GROUND_RADIO_OK); }
            Duplex_Step(ms, ms >= boot ? 1U : 0U, 1U);
            if (s_ack_received != 0U) { finished = ms - boot; break; }
        }
        TEST_CHECK(s_ack_received != 0U); TEST_CHECK(s_enqueue_errors == 0U);
        TEST_CHECK(s_hw[0].software_abort == 0U && s_hw[1].software_abort == 0U);
        if (finished > worst) { worst = finished; }
        startup_collisions += s_hw[0].collisions;
    }
    printf("STARTUP_SCAN boot offsets500 bounded recovery worst_after_boot_ms=%u initial_collisions=%u\n",
        worst, startup_collisions);
    Duplex_Init(0U, 1U); Duplex_QueueFlight(); Duplex_QueueFlight();
    uint8_t command[64] = {0x20U};
    for (uint8_t index = 0U; index < 8U; index++)
    { s_endpoint = 1U; command[1] = index; TEST_CHECK(GroundRadio_TxEnqueue(command, sizeof(command)) == GROUND_RADIO_OK); }
    for (unsigned int ms = 0U; ms < 4000U; ms++) { Duplex_Step(ms, 1U, 1U); }
    TEST_CHECK(s_command_received == 8U); TEST_CHECK(s_ack_received == 8U);
    TEST_CHECK(s_hw[1].sent == 8U); TEST_CHECK(s_enqueue_errors == 0U);
    TEST_CHECK(s_hw[0].software_abort == 0U && s_hw[1].software_abort == 0U);
    TEST_CHECK(s_hw[0].collisions == 0U && s_hw[1].collisions == 0U);
    for (uint8_t index = 0U; index < 8U; index++) { TEST_CHECK(s_hw[1].send_sequence[index] == index); }
    printf("FULL_STREAM eight maximum64-byte uplinks preserve FIFO and all replies under continuous downlink\n");
}
static void Test_RxErrors(void)
{
    static const uint16_t errors[3] = {IRQ_CRC_ERROR, IRQ_HEADER_ERROR, IRQ_RX_TX_TIMEOUT};
    for (unsigned int error = 0U; error < 3U; error++)
    {
        Duplex_Init(0U, 1U); Duplex_QueueFlight();
        uint8_t command[9] = {0x20U, 9U};
        for (unsigned int ms = 0U; ms < 500U; ms++)
        {
            s_ms = ms;
            if (ms == 100U) { Physical_Receive(0U, command, sizeof(command), ms, ms + 49U); }
            if (ms == 119U)
            {
                s_hw[0].valid = 0U; s_hw[0].receiving = 0U; s_hw[0].rx_mode = 0U;
                s_hw[0].irq |= errors[error];
            }
            Duplex_Step(ms, 1U, 0U);
        }
        TEST_CHECK(s_command_received == 0U); TEST_CHECK(s_hw[0].sent == 1U);
        TEST_CHECK(s_contexts[0].rx_packet_active == 0U); TEST_CHECK(s_hw[0].software_abort == 0U);
    }
    printf("RX_ERRORS CRC/header/timeout release protection without publishing commands\n");
}
static void Test_AirtimeProfiles(void)
{
    static const RadioLoRaBandwidths_t bandwidths[4] = {LORA_BW_0200, LORA_BW_0400, LORA_BW_0800, LORA_BW_1600};
    static const double bandwidth_hz[4] = {203125.0, 406250.0, 812500.0, 1625000.0};
    Duplex_Init(0U, 1U);
    for (unsigned int sf = 5U; sf <= 12U; sf++)
    {
        for (unsigned int bw = 0U; bw < 4U; bw++)
        {
            for (unsigned int cr = 1U; cr <= 4U; cr++)
            {
                s_contexts[0].mod_params.Params.LoRa.SpreadingFactor = (RadioLoRaSpreadingFactors_t)(sf << 4U);
                s_contexts[0].mod_params.Params.LoRa.Bandwidth = bandwidths[bw];
                s_contexts[0].mod_params.Params.LoRa.CodingRate = (RadioLoRaCodingRates_t)cr;
                for (unsigned int length = 1U; length <= 64U; length++)
                {
                    double bits = 8.0 * length + 16.0 - 4.0 * sf + 20.0 + (sf >= 7U ? 8.0 : 0.0);
                    double blocks = ceil(fmax(0.0, bits) / (4.0 * (sf > 10U ? sf - 2U : sf)));
                    double symbols = 16.0 + 8.0 + (sf < 7U ? 6.25 : 4.25) + blocks * (cr + 4U);
                    uint32_t expected = (uint32_t)ceil(symbols * pow(2.0, sf) * 1000.0 / bandwidth_hz[bw]);
                    TEST_CHECK(Lora_PacketAirtimeMs(0U, (uint8_t)length) == expected);
                    TEST_CHECK(Lora_RxGrantMs(0U) >= expected + LORA_RX_TURN_MARGIN_MS);
                }
            }
        }
    }
    printf("AIRTIME8192 SF/BW/CR/length combinations match independent Semtech formula\n");
}
static void Test_NoiseAndLostTx(void)
{
    for (unsigned int endpoint = 0U; endpoint < 2U; endpoint++)
    {
        Duplex_Init(0U, 1U); uint8_t data[26] = {0x11U, 1U};
        if (endpoint == 0U) { Duplex_QueueFlight(); }
        else { s_endpoint = 1U; TEST_CHECK(GroundRadio_TxEnqueue(data, sizeof(data)) == GROUND_RADIO_OK); }
        for (unsigned int ms = 0U; ms < 600U; ms++)
        {
            if (ms >= 100U && s_hw[endpoint].rx_mode != 0U)
            {
                s_hw[endpoint].irq |= IRQ_PREAMBLE_DETECTED | IRQ_HEADER_VALID;
                s_hw[endpoint].detected = 1U; /* Noise prevents native timeout. */
            }
            Duplex_Step(ms, endpoint == 0U ? 1U : 0U, 0U);
        }
        TEST_CHECK(s_hw[endpoint].sent != 0U); TEST_CHECK(s_hw[endpoint].software_abort == 0U);
    }
    Duplex_Init(0U, 1U); Duplex_QueueFlight();
    uint8_t data[9] = {0x40U, 12U}; uint32_t id, age;
    s_endpoint = 0U; TEST_CHECK(Lora_TxEnqueueTracked(0U, data, sizeof(data), &id) == LORA_TX_ENQUEUE_OK);
    s_hw[0].suppress = IRQ_TX_DONE | IRQ_RX_TX_TIMEOUT;
    for (unsigned int ms = 0U; ms < 2200U; ms++) { Duplex_Step(ms, 1U, 0U); }
    TEST_CHECK(s_hw[0].sent >= 2U); TEST_CHECK(s_contexts[0].stats.tx_timeout >= 2U);
    TEST_CHECK(Lora_TxResultGet(0U, id, &age) == LoraTxQueryResult_TimedOut);
    printf("NOISE repeated indications cannot renew hold; lostTX IRQ recovers as timeout\n");
}
int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    if (strcmp(argv[1], "phase_scan") == 0) { Test_PhaseScan(); }
    else if (strcmp(argv[1], "phase_trace") == 0) { s_trace = 1U; Test_PhaseScan(); }
    else if (strcmp(argv[1], "boundary") == 0) { Test_Boundary(); }
    else if (strcmp(argv[1], "queue_no_peer") == 0) { Test_QueueAndNoPeer(); }
    else if (strcmp(argv[1], "noise_lost_tx") == 0) { Test_NoiseAndLostTx(); }
    else if (strcmp(argv[1], "startup_full_stream") == 0) { Test_StartupAndFullStream(); }
    else if (strcmp(argv[1], "rx_errors") == 0) { Test_RxErrors(); }
    else if (strcmp(argv[1], "airtime_profiles") == 0) { Test_AirtimeProfiles(); }
    else { return 2; }
    return Test_Finish(argv[1]);
}
