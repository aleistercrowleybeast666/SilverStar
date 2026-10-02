/* Real generated service, SX transport and radio driver. Only hardware ports
 * and unrelated flight subsystems are supplied by existing host fixtures. */
#include <stdio.h>
#include <string.h>
#define main Test_TelemetryPreviousMain
#define SystemTelemetry_SendControl Test_PreviousSystemSendControl
#define SystemTelemetry_TxResultGet Test_PreviousSystemTxResultGet
#define SystemTelemetry_Send Test_PreviousSystemSend
#define SystemTelemetry_Receive Test_PreviousSystemReceive
#define SystemTelemetry_Process Test_PreviousSystemProcess
#define s_tx_count s_mock_tx_count
#include "test_telemetry.c"
#undef main
#undef SystemTelemetry_SendControl
#undef SystemTelemetry_TxResultGet
#undef SystemTelemetry_Send
#undef SystemTelemetry_Receive
#undef SystemTelemetry_Process
#undef s_tx_count
#define TEST_SX1281_PORTS_ONLY 1
#define SX1280SendPayload Test_PreviousRadioSend
#define SX1280GetStatus Test_PreviousRadioStatus
#define Sx1281Bus_StatusGet Test_PreviousRadioBusStatus
#define Sx1281Bus_Init Test_PreviousRadioBusInit
#include "test_sx1281_device.c"
#undef SX1280SendPayload
#undef SX1280GetStatus
#undef Sx1281Bus_StatusGet
#undef Sx1281Bus_Init
static uint8_t s_radio_bus_failure;
static Sx1281BusStatus s_radio_bus_status;
void Sx1281Bus_Init(uint8_t instance)
{ (void)instance; memset(&s_radio_bus_status, 0, sizeof(s_radio_bus_status)); }
void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{ (void)instance; *status = s_radio_bus_status; }
RadioStatus_t SX1280GetStatus(uint8_t instance)
{
    (void)instance; RadioStatus_t status; status.Value = 0x40U;
    if (s_radio_bus_failure != 0U)
    { s_radio_bus_status.spi_error_count++; s_radio_bus_status.last_result = SX1281_BUS_SPI_ERROR; }
    else { s_radio_bus_status.last_result = SX1281_BUS_OK; }
    return status;
}
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout);
#include "sx1281_device.c"
#undef s_tx_count
#undef s_tx_head
#undef s_tx_tail
#undef s_rx_count
#undef s_rx_head
#undef s_rx_tail
#include "sx1281_instance.h"
static TestFrame s_over_air[128];
static uint8_t s_over_air_count;
void SX1280SendPayload(uint8_t instance, uint8_t *data, uint8_t length, TickTime_t timeout)
{
    (void)instance; (void)timeout;
    TEST_CHECK(length <= AIR_MAX_FRAME_LEN);
    TEST_CHECK(s_over_air_count < 128U);
    if ((length <= AIR_MAX_FRAME_LEN) && (s_over_air_count < 128U))
    { memcpy(s_over_air[s_over_air_count].data, data, length);
      s_over_air[s_over_air_count++].length = length; }
}
SystemDeviceResult SystemTelemetry_Send(const uint8_t *data, uint16_t length)
{ return Sx1281TelemetryInstance_Send(0U, data, length); }
SystemDeviceResult SystemTelemetry_Receive(uint8_t *data, uint16_t capacity, uint16_t *length)
{ return Sx1281TelemetryInstance_Receive(0U, data, capacity, length); }
void SystemTelemetry_Process(void) { (void)Sx1281TelemetryInstance_Process(0U); }
#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
SystemDeviceResult SystemTelemetry_SendControl(const uint8_t *data, uint16_t length, uint32_t *id)
{ return Sx1281TelemetryInstance_SendControl(0U, data, length, id); }
SystemDeviceResult SystemTelemetry_TxResultGet(uint32_t id, uint32_t *age_ms)
{ return Sx1281TelemetryInstance_TxResultGet(0U, id, age_ms); }
#endif
#include "telemetry_service.c"
#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
#define s_capability_sequence s_capability_tx.latest_sequence
#endif
static void Radio_Clock(uint32_t ms)
{ s_tick_ms = ms; s_now_us = (uint64_t)ms * 1000ULL; }
static void Radio_Command(uint8_t seq, uint8_t command, uint8_t param0, uint8_t param1)
{
    Test_CommandQueue(seq, command, 0U, param0, param1);
    TEST_CHECK(Lora_RxQueuePush(0U, s_rx[s_rx_tail].data,
        (uint8_t)s_rx[s_rx_tail].length, -60, 3) != 0U);
    s_rx_tail = Test_Next(s_rx_tail, TEST_RX_DEPTH);
}
static void Radio_Init(void)
{
    Test_Reset(); s_radio_bus_failure = 0U; Radio_Clock(0U);
    TEST_CHECK(Sx1281TelemetryInstance_Init(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(Sx1281TelemetryInstance_Start(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(s_contexts[0].mod_params.Params.LoRa.SpreadingFactor == LORA_SF10);
    TEST_CHECK(s_contexts[0].mod_params.Params.LoRa.Bandwidth == LORA_BW_0800);
    TEST_CHECK(s_contexts[0].mod_params.Params.LoRa.CodingRate == LORA_CR_4_5);
    TEST_CHECK(s_contexts[0].pkt_params.Params.LoRa.PreambleLength == 0x18U);
    TEST_CHECK(s_contexts[0].pkt_params.Params.LoRa.CrcMode == LORA_CRC_ON);
    TEST_CHECK(LORA_RF_FREQUENCY_HZ == 2473000000UL);
}
static void Radio_Complete(uint32_t ms)
{
    Radio_Clock(ms); s_raw_irq = IRQ_TX_DONE; s_dio1_pending = 1U;
    Lora_Process(0U);
}
static void Test_AckBacklog(void)
{
    uint8_t frame[AIR_PREFLIGHT_STATE_LEN] = {AIR_TYPE_PREFLIGHT_STATE};
    uint8_t index;
    Radio_Init();
    for (index = 0U; index < 8U; index++)
    { frame[1] = index; (void)SystemTelemetry_Send(frame, sizeof(frame)); }
    Radio_Clock(122U); Lora_Process(0U); /* ceil117.524ms maximum packet plus4ms margin. */
    Radio_Clock(123U);
    Radio_Command(200U, AIR_CMD_PING, 0U, 0U);
    TelemetryService_Process();
    Radio_Complete(194U);
    Radio_Clock(316U); TelemetryService_Process();
    TEST_CHECK(s_over_air_count >= 2U);
    printf("ACK_BACKLOG first=%02x second=%02x queue_count=%u\n",
        s_over_air[0].data[0], s_over_air[1].data[0], s_contexts[0].tx_count);
    /* A saturated normal lane cannot put the response behind normal backlog. */
    TEST_CHECK(s_over_air[1].data[0] == AIR_TYPE_ACK);
    TEST_CHECK(s_over_air[1].data[2] == 200U);
}
static void Test_CapabilityQueuedSupersedes(void)
{
    uint8_t first;
    uint8_t found = 0U;
    Radio_Init();
    /* Finite startup statuses precede the initial Capability. */
    for (unsigned int i = 0U; i < 5U; i++) { TelemetryService_Process(); }
    for (uint32_t now = 122U; now < 1000U; now += 196U)
    { Radio_Clock(now); TelemetryService_Process(); Radio_Complete(now + 74U); }
    first = 0U;
    for (uint8_t i = 0U; i < s_over_air_count; i++)
    { if (s_over_air[i].data[0] == AIR_TYPE_CAPABILITY) { first = s_over_air[i].data[1]; found = 1U; } }
    TEST_CHECK(found != 0U);
    TEST_CHECK(s_capability_sent != 0U);
    Radio_Clock(1100U);
    s_next_capability_us = 0ULL;
    (void)TelemetryService_CapabilitySend();
    printf("CAP_QUEUED advertised=%u current=%u queued=%u\n", first,
        s_capability_sequence, s_contexts[0].tx_count);
    Radio_Command(201U, AIR_CMD_CAPABILITY_ACK, first, AIR_PROFILE_ID_CURRENT);
    TelemetryService_Process();
    printf("CAP_REPLY state=%u (expected ACKED=%u)\n", s_capability_state,
        TELEMETRY_CAPABILITY_ACKED);
    TEST_CHECK(s_capability_state == TELEMETRY_CAPABILITY_ACKED);
}

#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
static void Test_QueueBoundaries(void)
{
    uint8_t data[65] = {0U};
    uint32_t id = 99U;
    uint32_t age;
    LoraTxPacket packet;
    static const uint8_t order[8] = {10U,11U,20U,12U,13U,21U,14U,15U};
    Radio_Init();
    TEST_CHECK(SystemTelemetry_SendControl(NULL, 1U, NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemTelemetry_SendControl(data, 65U, NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(Sx1281TelemetryInstance_SendControl(255U, data, 1U, NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemTelemetry_TxResultGet(0U, &age) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemTelemetry_TxResultGet(id, NULL) == SYSTEM_DEVICE_INVALID_ARGUMENT);
    TEST_CHECK(SystemTelemetry_TxResultGet(id, &age) == SYSTEM_DEVICE_NOT_PRESENT);
    for (uint8_t cycle = 0U; cycle < 32U; cycle++)
    {
        data[0] = 20U; TEST_CHECK(SystemTelemetry_Send(data, 64U) == SYSTEM_DEVICE_OK);
        data[0] = 21U; TEST_CHECK(SystemTelemetry_Send(data, 1U) == SYSTEM_DEVICE_OK);
        TEST_CHECK(SystemTelemetry_Send(data, 1U) == SYSTEM_DEVICE_NOT_READY);
        for (uint8_t index = 0U; index < 6U; index++)
        {
            data[0] = (uint8_t)(10U + index);
            /* NULL is the legal untracked ACK/status operation. */
            TEST_CHECK(SystemTelemetry_SendControl(data, 1U, NULL) == SYSTEM_DEVICE_OK);
        }
        TEST_CHECK(SystemTelemetry_SendControl(data, 1U, &id) == SYSTEM_DEVICE_NOT_READY);
        TEST_CHECK(id == 0U); /* Failure cannot publish a valid token. */
        for (uint8_t index = 0U; index < 8U; index++)
        {
            TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
            TEST_CHECK(packet.data[0] == order[index]);
            TEST_CHECK(s_contexts[0].active_tx_id == 0U);
        }
        TEST_CHECK(Lora_TxQueuePop(0U, &packet) == 0U);
    }
    TEST_CHECK(Sx1281TelemetryInstance_Stop(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_SendControl(data, 1U, NULL) == SYSTEM_DEVICE_NOT_READY);
}
static void Test_AckFullRetry(void)
{
    uint8_t data = 99U;
    LoraTxPacket packet;
    uint8_t ack_tail;
    Radio_Init();
    for (uint8_t i = 0U; i < 6U; i++)
    { TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, NULL) == SYSTEM_DEVICE_OK); }
    Radio_Command(200U, AIR_CMD_PING, 0U, 0U);
    TelemetryService_ReceiveProcess();
    ack_tail = s_ack_tail;
    TEST_CHECK(TelemetryService_AckSend() != 0U);
    TEST_CHECK(s_ack_tail == ack_tail);
    TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
    TEST_CHECK(TelemetryService_AckSend() != 0U);
    TEST_CHECK(s_ack_tail != ack_tail);
    for (uint8_t i = 0U; i < 5U; i++) { TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U); }
    /* Send through the actual hardware port, rather than merely inspecting a queue. */
    Radio_Clock(122U); Lora_Process(0U);
    TEST_CHECK(s_over_air_count == 1U);
    TEST_CHECK(s_over_air[0].data[0] == AIR_TYPE_ACK);
    TEST_CHECK(s_over_air[0].data[2] == 200U);
}
static void Test_RxContinuousFairness(void)
{
    uint8_t data = 1U;
    Radio_Init(); s_host_receive_enabled = 1U;
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, NULL) == SYSTEM_DEVICE_OK);
    for (uint32_t ms = 30U; ms < 120U; ms += 30U)
    { Radio_Clock(ms); s_raw_irq = IRQ_RX_DONE; s_dio1_pending = 1U; Lora_Process(0U); TEST_CHECK(s_over_air_count == 0U); }
    Radio_Clock(119U); s_raw_irq = IRQ_CRC_ERROR; s_dio1_pending = 1U; Lora_Process(0U);
    TEST_CHECK(s_over_air_count == 0U);
    Radio_Clock(122U); s_raw_irq = IRQ_HEADER_ERROR; s_dio1_pending = 1U; Lora_Process(0U);
    TEST_CHECK(s_over_air_count == 1U);
    TEST_CHECK(s_contexts[0].stats.rx_ok == 3U);
    Radio_Complete(194U);
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, NULL) == SYSTEM_DEVICE_OK);
    Radio_Clock(313U); Lora_Process(0U); TEST_CHECK(s_over_air_count == 1U);
    Radio_Clock(316U); Lora_Process(0U); TEST_CHECK(s_over_air_count == 2U);
    s_host_receive_enabled = 0U;
}
static void Test_TokenWrap(void)
{
    uint8_t data = 1U;
    uint32_t first, second, third, age;
    LoraTxPacket packet;
    Radio_Init();
    s_contexts[0].next_tx_id = 0x00FFFFFEUL;
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, &first) == SYSTEM_DEVICE_OK);
    TEST_CHECK(first == 0x00FFFFFFUL);
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, &second) == SYSTEM_DEVICE_OK);
    TEST_CHECK(second == 1U);
    /* Counter wrap must avoid a token still queued. */
    s_contexts[0].next_tx_id = 0x00FFFFFFUL;
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, &third) == SYSTEM_DEVICE_OK);
    TEST_CHECK(third == 2U);
    TEST_CHECK(SystemTelemetry_TxResultGet(second, &age) == SYSTEM_DEVICE_BUSY);
    TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
    TEST_CHECK(s_contexts[0].active_tx_id == first);
    Radio_Clock(UINT32_MAX - 5U); Lora_TxReceiptRecord(0U, LoraTxQueryResult_Complete);
    Radio_Clock(5U);
    TEST_CHECK(SystemTelemetry_TxResultGet(first, &age) == SYSTEM_DEVICE_OK);
    TEST_CHECK(age == 11U);
    TEST_CHECK(Lora_TxQueuePop(0U, &packet) != 0U);
    Lora_TxReceiptRecord(0U, LoraTxQueryResult_TimedOut);
    TEST_CHECK(SystemTelemetry_TxResultGet(second, &age) == SYSTEM_DEVICE_TIMEOUT);
    TEST_CHECK(SystemTelemetry_TxResultGet(first, &age) == SYSTEM_DEVICE_NOT_PRESENT);
    /* Reusing a completed token cannot inherit its completion. */
    s_contexts[0].next_tx_id = 0x00FFFFFFUL;
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, &first) == SYSTEM_DEVICE_OK);
    TEST_CHECK(first == 1U);
    TEST_CHECK(SystemTelemetry_TxResultGet(first, &age) == SYSTEM_DEVICE_BUSY);
    /* Separately inject full uint32 arithmetic overflow, then skip live 1/2. */
    s_contexts[0].next_tx_id = UINT32_MAX;
    TEST_CHECK(SystemTelemetry_SendControl(&data, 1U, &third) == SYSTEM_DEVICE_OK);
    TEST_CHECK(third == 3U);
    TEST_CHECK(SystemTelemetry_TxResultGet(third, &age) == SYSTEM_DEVICE_BUSY);
}
static void Radio_CapStart(uint8_t sequence, uint32_t ms)
{
    Radio_Clock(ms); s_tx_sequence = sequence;
    s_capability_send_pending = 1U;
    TEST_CHECK(TelemetryService_CapabilitySend() != 0U);
    TEST_CHECK(s_capability_tx.pending_id != 0U);
}
static void Test_CapSequenceWrap(void)
{
    uint64_t sent_us;
    Radio_Init();
    Radio_CapStart(255U, 0U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(255U, &sent_us) == 0U);
    Radio_Clock(122U); Lora_Process(0U); Radio_Complete(194U); TelemetryService_CapabilityTxPoll();
    TEST_CHECK(TelemetryService_CapabilityAdvertised(255U, &sent_us) != 0U);
    TEST_CHECK(sent_us == 194000ULL);
    Radio_CapStart(0U, 300U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(0U, &sent_us) == 0U);
    Radio_Clock(420U); Lora_Process(0U); Radio_Complete(494U); TelemetryService_CapabilityTxPoll();
    TEST_CHECK(TelemetryService_CapabilityAdvertised(0U, &sent_us) != 0U);
    /* Reusing a live 255 skips both live CAP values and queues 1. */
    Radio_CapStart(255U, 600U);
    TEST_CHECK(s_capability_tx.pending_sequence == 1U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(1U, &sent_us) == 0U);
    Radio_Command(100U, AIR_CMD_CAPABILITY_ACK, 1U, AIR_PROFILE_ID_CURRENT);
    TelemetryService_ReceiveProcess();
    TEST_CHECK(s_capability_state == TELEMETRY_CAPABILITY_NOT_ACKED);
    Radio_Clock(4194U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(255U, &sent_us) == 0U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(0U, &sent_us) != 0U);
    Radio_Command(101U, AIR_CMD_CAPABILITY_ACK, 255U, AIR_PROFILE_ID_CURRENT);
    TelemetryService_ReceiveProcess();
    TEST_CHECK(s_capability_state == TELEMETRY_CAPABILITY_NOT_ACKED);
    /* Pending token timeout never promotes an uncompleted advertisement. */
    Radio_Clock(4600U); TelemetryService_CapabilityTxPoll();
    TEST_CHECK(s_capability_tx.pending_id == 0U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(1U, &sent_us) == 0U);
    /* Reuse an expired wire value: the queued replacement is still not advertised. */
    Radio_CapStart(255U, 4601U);
    TEST_CHECK(s_capability_tx.pending_sequence == 255U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(255U, &sent_us) == 0U);
    Radio_Command(102U, AIR_CMD_CAPABILITY_ACK, 255U, AIR_PROFILE_ID_CURRENT);
    TelemetryService_ReceiveProcess();
    TEST_CHECK(s_capability_state == TELEMETRY_CAPABILITY_NOT_ACKED);
    Radio_Clock(4800U); Lora_Process(0U); Radio_Complete(4874U); TelemetryService_CapabilityTxPoll();
    TEST_CHECK(TelemetryService_CapabilityAdvertised(255U, &sent_us) == 0U);
    Radio_Clock(4996U); Lora_Process(0U); Radio_Complete(5070U); TelemetryService_CapabilityTxPoll();
    TEST_CHECK(TelemetryService_CapabilityAdvertised(255U, &sent_us) != 0U);
    TEST_CHECK(sent_us == 5070000ULL);
}
static void Test_CapTxTimeout(void)
{
    uint32_t id, age;
    uint64_t sent_us;
    Radio_Init(); Radio_CapStart(42U, 0U); id = s_capability_tx.pending_id;
    Radio_Clock(122U); Lora_Process(0U);
    TEST_CHECK(SystemTelemetry_TxResultGet(id, &age) == SYSTEM_DEVICE_BUSY);
    Radio_Clock(922U); s_raw_irq = IRQ_RX_TX_TIMEOUT; s_dio1_pending = 1U; Lora_Process(0U);
    TEST_CHECK(SystemTelemetry_TxResultGet(id, &age) == SYSTEM_DEVICE_TIMEOUT);
    TelemetryService_CapabilityTxPoll();
    TEST_CHECK(s_capability_tx.pending_id == 0U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(42U, &sent_us) == 0U);
    TEST_CHECK(s_capability_sent == 0U);
}
static void Test_MixedTokenFairness(void)
{
    uint8_t data = 90U;
    uint32_t ids[6];
    static const uint8_t order[8] = {0U,1U,255U,2U,3U,255U,4U,5U};
    Radio_Init();
    TEST_CHECK(SystemTelemetry_Send(&data, 1U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemTelemetry_Send(&data, 1U) == SYSTEM_DEVICE_OK);
    for (uint8_t i = 0U; i < 6U; i++)
    { TEST_CHECK(SystemTelemetry_SendControl(&i, 1U, &ids[i]) == SYSTEM_DEVICE_OK); }
    for (uint8_t i = 0U; i < 8U; i++)
    {
        Radio_Clock(122U + (uint32_t)i * 194U); Lora_Process(0U);
        TEST_CHECK(s_over_air_count == (uint8_t)(i + 1U));
        if (order[i] == 255U)
        { TEST_CHECK(s_over_air[i].data[0] == 90U); TEST_CHECK(s_contexts[0].active_tx_id == 0U); }
        else
        { TEST_CHECK(s_over_air[i].data[0] == order[i]); TEST_CHECK(s_contexts[0].active_tx_id == ids[order[i]]); }
        Radio_Complete(194U + (uint32_t)i * 194U);
    }
}
static void Test_CapLongExpiry(void)
{
    uint64_t sent_us;
    Radio_Init(); Radio_CapStart(250U, 0U);
    Radio_Clock(122U); Lora_Process(0U); Radio_Complete(194U); TelemetryService_CapabilityTxPoll();
    Radio_Clock(194U); s_now_us = (0x100000000ULL + 194ULL) * 1000ULL;
    TEST_CHECK(TelemetryService_CapabilityAdvertised(250U, &sent_us) == 0U);
}
static void Test_CapPendingLongExpiry(void)
{
    uint64_t sent_us;
    uint32_t id, age;
    Radio_Init(); Radio_CapStart(42U, 0U); id = s_capability_tx.pending_id;
    Radio_Clock(122U); Lora_Process(0U); Radio_Complete(194U);
    Radio_Clock(194U); s_now_us = (0x100000000ULL + 194ULL) * 1000ULL;
    /* Its 32-bit receipt age aliases to zero; the 64-bit pending lifetime wins. */
    TEST_CHECK(SystemTelemetry_TxResultGet(id, &age) == SYSTEM_DEVICE_OK);
    TEST_CHECK(age == 0U);
    TelemetryService_CapabilityTxPoll();
    TEST_CHECK(s_capability_tx.pending_id == 0U);
    TEST_CHECK(s_capability_sent == 0U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(42U, &sent_us) == 0U);
}
static void Test_CapClockWrap(void)
{
    uint64_t sent_us;
    Radio_Init(); Radio_CapStart(250U, UINT32_MAX - 200U);
    Lora_Process(0U); Radio_Complete(UINT32_MAX - 126U); TelemetryService_CapabilityTxPoll();
    Radio_Clock(100U); s_now_us = (0x100000000ULL + 100ULL) * 1000ULL;
    TEST_CHECK(TelemetryService_CapabilityAdvertised(250U, &sent_us) != 0U);
    TEST_CHECK(sent_us == (uint64_t)(UINT32_MAX - 126U) * 1000ULL);
    Radio_Clock(3873U); s_now_us = (0x100000000ULL + 3873ULL) * 1000ULL;
    TEST_CHECK(TelemetryService_CapabilityAdvertised(250U, &sent_us) == 0U);
}
static void Test_CapReconnectAndCache(void)
{
    uint64_t sent_us;
    AirCmdPayload command = {0};
    Radio_Init(); Radio_CapStart(10U, 0U);
    Radio_Clock(122U); Lora_Process(0U); Radio_Complete(194U); TelemetryService_CapabilityTxPoll();
    command.seq = 100U; command.cmd_id = AIR_CMD_CAPABILITY_ACK;
    command.param0 = 10U; command.param1 = AIR_PROFILE_ID_CURRENT;
    TelemetryService_CapabilityCommand(&command);
    TEST_CHECK(s_capability_state == TELEMETRY_CAPABILITY_ACKED);
    command.cmd_id = AIR_CMD_CAL_START; command.token = AIR_TOKEN_CALIBRATION;
    command.param0 = AIR_CALIBRATION_MODE_NONE; command.param1 = 0U;
    TelemetryService_CommandDispatch(&command);
    TEST_CHECK(s_calibration_start_count == 1U);
    TelemetryService_CommandDispatch(&command); TEST_CHECK(s_calibration_start_count == 1U);
    command.token = 0U; TEST_CHECK(TelemetryService_CachedAckQueue(&command) == 0U);
    TEST_CHECK(s_calibration_start_count == 1U); /* conflicting payload cannot reuse a cached ACK */
    command.token = AIR_TOKEN_CALIBRATION;
    /* A new completed CAP and handshake clear the prior-session business cache. */
    Radio_CapStart(20U, 300U);
    Radio_Clock(420U); Lora_Process(0U); Radio_Complete(494U); TelemetryService_CapabilityTxPoll();
    AirCmdPayload handshake = {0}; handshake.seq = 101U;
    handshake.cmd_id = AIR_CMD_CAPABILITY_ACK; handshake.param0 = 20U;
    handshake.param1 = AIR_PROFILE_ID_CURRENT;
    TelemetryService_CapabilityCommand(&handshake);
    TelemetryService_CommandDispatch(&command); TEST_CHECK(s_calibration_start_count == 2U);
    handshake.param0 = 10U; TelemetryService_CapabilityCommand(&handshake);
    TelemetryService_CommandDispatch(&command); TEST_CHECK(s_calibration_start_count == 2U);
    TEST_CHECK(s_capability_tx.ack_advertised_us == 494000ULL);
    Radio_Clock(4494U);
    TEST_CHECK(TelemetryService_CapabilityAdvertised(20U, &sent_us) == 0U);
    TelemetryService_CapabilityCommand(&handshake);
    TEST_CHECK(s_capability_tx.ack_advertised_us == 494000ULL);
    s_lifecycle_state = SYSTEM_STATE_FLIGHT;
    TelemetryService_CapabilityCommand(&handshake);
    TEST_CHECK(s_capability_tx.ack_advertised_us == 494000ULL);
}
#endif
#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
static void Test_SpiFaultHealth(void)
{
    Radio_Init(); Radio_CapStart(42U, 0U); s_radio_bus_failure = 1U;
    for (uint32_t ms = 1U; ms <= 300U; ms++)
    { Radio_Clock(ms); SystemTelemetry_Process(); TelemetryService_CapabilityTxPoll(); }
    SystemTelemetryHealth health;
    TEST_CHECK(Sx1281TelemetryInstance_HealthGet(0U, &health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(health.healthy == 0U && health.online == 0U);
    TEST_CHECK(health.initialized == 0U && health.started == 0U);
    TEST_CHECK(s_contexts[0].inited == 0U && s_contexts[0].chip_status.verified == 0U);
    TEST_CHECK(s_over_air_count == 0U);
    uint64_t sent_us = 0U;
    TEST_CHECK(TelemetryService_CapabilityAdvertised(42U, &sent_us) == 0U);
    TEST_CHECK(Sx1281TelemetryInstance_Start(0U) == SYSTEM_DEVICE_NOT_READY);
    s_radio_bus_failure = 0U; Radio_Clock(400U); SystemTelemetry_Process();
    TEST_CHECK(s_contexts[0].inited == 0U && s_over_air_count == 0U);
    TEST_CHECK(Sx1281TelemetryInstance_Init(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(Sx1281TelemetryInstance_Start(0U) == SYSTEM_DEVICE_OK);
    TEST_CHECK(Sx1281TelemetryInstance_HealthGet(0U, &health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(health.initialized != 0U && health.started != 0U && health.healthy != 0U);
}
#endif

int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    if (strcmp(argv[1], "ack_backlog") == 0) { Test_AckBacklog(); }
    else if (strcmp(argv[1], "cap_queued") == 0) { Test_CapabilityQueuedSupersedes(); }
#ifdef SYSTEM_TELEMETRY_TX_CONTROL_SUPPORTED
    else if (strcmp(argv[1], "spi_fault_health") == 0) { Test_SpiFaultHealth(); }
    else if (strcmp(argv[1], "queue_boundaries") == 0) { Test_QueueBoundaries(); }
    else if (strcmp(argv[1], "ack_full") == 0) { Test_AckFullRetry(); }
    else if (strcmp(argv[1], "rx_fairness") == 0) { Test_RxContinuousFairness(); }
    else if (strcmp(argv[1], "token_wrap") == 0) { Test_TokenWrap(); }
    else if (strcmp(argv[1], "cap_sequence_wrap") == 0) { Test_CapSequenceWrap(); }
    else if (strcmp(argv[1], "cap_tx_timeout") == 0) { Test_CapTxTimeout(); }
    else if (strcmp(argv[1], "mixed_tokens") == 0) { Test_MixedTokenFairness(); }
    else if (strcmp(argv[1], "cap_pending_long_expiry") == 0) { Test_CapPendingLongExpiry(); }
    else if (strcmp(argv[1], "cap_long_expiry") == 0) { Test_CapLongExpiry(); }
    else if (strcmp(argv[1], "cap_clock_wrap") == 0) { Test_CapClockWrap(); }
    else if (strcmp(argv[1], "cap_reconnect_cache") == 0) { Test_CapReconnectAndCache(); }
#endif
    else { return 2; }
    return Test_Finish(argv[1]);
}
