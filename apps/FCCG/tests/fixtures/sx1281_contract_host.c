/* Real driver/assertion code, fake radio/critical/time ports. The only assertion
 * substitution is the terminal trap: longjmp lets the harness inspect the real
 * latched fault and verify no subsequent queue write or radio command occurred.
 * It is not firmware recovery and is never built into a target. */
#include <setjmp.h>
#include <stdlib.h>

#define main Test_PreviousMain
#define TEST_SX1281_PORTS_ONLY 1
#define SX1280GetFirmwareVersion Test_PreviousFirmwareVersion
#define SX1280SendPayload Test_PreviousSendPayload
#define Sx1281Bus_StatusGet Test_PreviousBusStatusGet
#include "test_sx1281_device.c"
#undef main
#undef SX1280GetFirmwareVersion
#undef SX1280SendPayload
#undef Sx1281Bus_StatusGet
#undef Lora_Init
#undef Lora_StartRx
#undef Lora_Process
#undef Lora_GetDiagSnapshot
#undef Lora_ChipStatusGet
#undef Lora_GetStats
#undef Lora_ControlSubmit
#undef Lora_ControlResultGet
#undef Lora_IrqClear

static jmp_buf s_trap_return;
static uint8_t s_missing_chip;
static uint8_t s_failed_port;
static uint32_t s_send_count;

uint16_t SX1280GetFirmwareVersion(uint8_t instance)
{
    return (s_missing_chip != 0U) ? 0U : Test_PreviousFirmwareVersion(instance);
}

void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{
    Test_PreviousBusStatusGet(instance, status);
    if (status != NULL) { status->spi_error_count = s_failed_port; }
}

void SX1280SendPayload(uint8_t instance, uint8_t *payload, uint8_t size,
                       TickTime_t timeout)
{
    s_send_count++;
    Test_PreviousSendPayload(instance, payload, size, timeout);
}

static _Noreturn void Test_Trap(void) { longjmp(s_trap_return, 1); }
#define __builtin_trap() Test_Trap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "sx1281_device.c"

static void Test_ReinitializationFailure(void)
{
    uint8_t data = 7U;
    LoraDebugSnapshot snapshot;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    s_missing_chip = 1U;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_CHIP_NOT_FOUND);
    Lora_GetDebugSnapshot(0U, &snapshot);
    TEST_CHECK(snapshot.initialized == 0U);
    TEST_CHECK(snapshot.stats.radio_state == LORA_RADIO_STATE_NOT_INIT);
    TEST_CHECK(Lora_TxEnqueue(0U, &data, 1U) == LORA_TX_ENQUEUE_NOT_INIT);
    Lora_Process(0U);
    TEST_CHECK(s_send_count == 0U);
    TEST_CHECK(s_set_rx_count == 0U);
    s_missing_chip = 0U;
    s_failed_port = 1U;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_PORT_ERROR);
    Lora_GetDebugSnapshot(0U, &snapshot);
    TEST_CHECK(snapshot.initialized == 0U);
    TEST_CHECK(Lora_TxEnqueue(0U, &data, 1U) == LORA_TX_ENQUEUE_NOT_INIT);
    s_failed_port = 0U;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    TEST_CHECK(Lora_TxEnqueue(0U, &data, 1U) == LORA_TX_ENQUEUE_OK);
    Lora_Process(0U);
    TEST_CHECK(s_send_count == 0U);
    s_tick_ms += 122U; /* Maximum64-byte airtime ceil118ms plus4ms margin. */
    Lora_Process(0U);
    TEST_CHECK(s_send_count == 1U);
}

static void Test_NormalQueuesAndTimeout(void)
{
    uint8_t input[64];
    LoraTxPacket tx;
    LoraRxPacket rx;
    LoraControlResult result;
    uint32_t id;
    uint32_t cycle;
    uint32_t index;
    memset(input, 0xA5, sizeof(input));
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    TEST_CHECK(Lora_Init(1U) == LORA_INIT_OK);
    for (cycle = 0U; cycle < 4U; cycle++)
    {
        for (index = 0U; index < LORA_TX_NORMAL_QUEUE_DEPTH; index++)
        { TEST_CHECK(Lora_TxEnqueue(0U, input, sizeof(input)) == LORA_TX_ENQUEUE_OK); }
        TEST_CHECK(Lora_TxEnqueue(0U, input, 1U) == LORA_TX_ENQUEUE_QUEUE_FULL);
        for (index = 0U; index < LORA_TX_NORMAL_QUEUE_DEPTH; index++)
        {
            TEST_CHECK(Lora_TxQueuePop(0U, &tx) == 1U);
            TEST_CHECK(tx.len == sizeof(input));
            TEST_CHECK(memcmp(tx.data, input, sizeof(input)) == 0);
        }
        TEST_CHECK(Lora_TxQueuePop(1U, &tx) == 0U);
        TEST_CHECK(Lora_TxEnqueuePriority(0U, input, 1U) == LORA_TX_ENQUEUE_OK);
        TEST_CHECK(Lora_TxQueuePop(0U, &tx) == 1U);
        for (index = 0U; index < LORA_RX_QUEUE_DEPTH; index++)
        { TEST_CHECK(Lora_RxQueuePush(0U, input, sizeof(input), -60, 3) == 1U); }
        TEST_CHECK(Lora_RxQueuePush(0U, input, 1U, -60, 3) == 0U);
        for (index = 0U; index < LORA_RX_QUEUE_DEPTH; index++)
        {
            TEST_CHECK(Lora_RxQueuePop(0U, &rx) == 1U);
            TEST_CHECK(rx.len == sizeof(input));
            TEST_CHECK(memcmp(rx.data, input, sizeof(input)) == 0);
        }
        TEST_CHECK(Lora_RxQueuePop(1U, &rx) == 0U);
    }
    TEST_CHECK(Lora_TxEnqueue(0U, NULL, 1U) == LORA_TX_ENQUEUE_BAD_PARAM);
    TEST_CHECK(Lora_TxEnqueue(0U, input, 65U) == LORA_TX_ENQUEUE_BAD_PARAM);
    s_tick_ms = UINT32_MAX - 5U;
    TEST_CHECK(Lora_ControlSubmit(0U, LORA_CONTROL_IRQ_CLEAR, 10U, &id) == LORA_CONTROL_SUBMIT_OK);
    s_tick_ms = 5U;
    TEST_CHECK(Lora_ControlResultGet(0U, id, &result) == LORA_CONTROL_GET_COMPLETE);
    TEST_CHECK(result.result == LORA_DIAG_RESULT_TIMEOUT);
    TEST_CHECK(s_irq_clear_count == 0U);
    /* Radio CRC/header errors and timeout IRQs remain expected events. */
    Lora_IrqProcess(0U, IRQ_CRC_ERROR);
    Lora_RxErrorProcess(0U);
    Lora_IrqProcess(0U, IRQ_HEADER_ERROR);
    Lora_RxErrorProcess(0U);
    Lora_IrqProcess(0U, IRQ_RX_TX_TIMEOUT);
    Lora_RxErrorProcess(0U);
    TEST_CHECK(s_contexts[0].stats.rx_error == 2U);
    TEST_CHECK(s_contexts[0].stats.rx_crc_error == 1U);
    TEST_CHECK(s_contexts[0].stats.rx_timeout == 1U);
    TEST_CHECK(SilverStarAssert_FaultedGet() == 0U);
}

static void Test_Corruption(const char *name)
{
    uint8_t byte = 1U;
    static uint8_t output[64];
    static uint8_t len = 99U;
    uint32_t id;
    uint32_t send_before;
    uint32_t rx_before;
    Sx1281Context before;
    SilverStarAssertFaultRecord fault;
    volatile SilverStarAssertReasonId reason = SILVERSTAR_ASSERT_REASON_INDEX_RANGE;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    if (strcmp(name, "air_sf") == 0) { s_contexts[0].mod_params.Params.LoRa.SpreadingFactor = (RadioLoRaSpreadingFactors_t)0xA1U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "air_bw") == 0) { s_contexts[0].mod_params.Params.LoRa.Bandwidth = (RadioLoRaBandwidths_t)0x19U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "air_cr") == 0) { s_contexts[0].mod_params.Params.LoRa.CodingRate = LORA_CR_LI_4_5; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "air_crc") == 0) { s_contexts[0].pkt_params.Params.LoRa.CrcMode = (RadioLoRaCrcModes_t)0x10U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "air_header") == 0) { s_contexts[0].pkt_params.Params.LoRa.HeaderType = (RadioLoRaPacketLengthsModes_t)0x01U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "air_preamble") == 0) { s_contexts[0].pkt_params.Params.LoRa.PreambleLength = 0x19U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "rx_hold") == 0) { s_contexts[0].rx_packet_active = 2U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "schedule_role") == 0) { s_contexts[0].schedule_role = 2U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    if (strcmp(name, "tx_head") == 0) { s_contexts[0].tx_head = LORA_TX_QUEUE_DEPTH; }
    else if (strcmp(name, "tx_count") == 0) { s_contexts[0].tx_count = LORA_TX_QUEUE_DEPTH + 1U; reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY; }
    else if (strcmp(name, "tx_control_count") == 0) { s_contexts[0].tx_control_count = 1U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "tx_control_burst") == 0) { s_contexts[0].tx_control_burst = 3U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "rx_window") == 0) { s_contexts[0].rx_window_active = 2U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "tx_sequence") == 0) { s_contexts[0].tx_head = 1U; reason = SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT; }
    else if (strcmp(name, "rx_tail") == 0) { s_contexts[0].rx_tail = LORA_RX_QUEUE_DEPTH; }
    else if (strcmp(name, "rx_count") == 0) { s_contexts[0].rx_count = LORA_RX_QUEUE_DEPTH + 1U; reason = SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY; }
    else if (strcmp(name, "rx_sequence") == 0) { s_contexts[0].rx_head = 1U; reason = SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT; }
    else if ((strcmp(name, "tx_len") == 0) || (strcmp(name, "rx_len") == 0))
    {
        TEST_CHECK(Lora_TxQueuePush(0U, &byte, 1U) == 1U);
        TEST_CHECK(Lora_RxQueuePush(0U, &byte, 1U, -60, 3) == 1U);
        s_contexts[0].tx_queue[0].len = 65U;
        s_contexts[0].rx_queue[0].len = 65U;
        reason = SILVERSTAR_ASSERT_REASON_LENGTH_RANGE;
    }
    else if (strncmp(name, "control_", 8U) == 0)
    {
        TEST_CHECK(Lora_ControlSubmit(0U, LORA_CONTROL_IRQ_CLEAR, 10U, &id) == LORA_CONTROL_SUBMIT_OK);
        if (strcmp(name, "control_op") == 0) { s_contexts[0].control_transaction.operation = (LoraControlOperation)9U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
        if (strcmp(name, "control_id") == 0) { s_contexts[0].control_transaction.transaction_id = 0U; reason = SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT; }
        if (strcmp(name, "control_time") == 0) { s_contexts[0].control_transaction.timeout_ms = 0U; reason = SILVERSTAR_ASSERT_REASON_TIME_INVARIANT; }
        if (strcmp(name, "control_state") == 0) { s_contexts[0].control_transaction.state = (LoraControlState)9U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
        if (strcmp(name, "control_active_init") == 0) { s_contexts[0].control_transaction.state = LoraControlStateActive; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    }
    else if (strcmp(name, "flags") == 0) { s_contexts[0].inited = 2U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strstr(name, "busy") != NULL) { s_contexts[0].tx_busy = 2U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strstr(name, "packet_type") != NULL) { s_contexts[0].pkt_params.PacketType = PACKET_TYPE_GFSK; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "diag_uninitialized") == 0) { s_contexts[0].inited = 0U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "rx_done_flag") == 0) { s_contexts[0].rx_done_flag = 2U; reason = SILVERSTAR_ASSERT_REASON_STATE_INVARIANT; }
    else if (strcmp(name, "rx_error") == 0) { s_contexts[0].rx_error_flag = 1U; s_contexts[0].rx_error_code = (IrqErrorCode_t)9U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    else if (strcmp(name, "radio_state") == 0) { s_contexts[0].stats.radio_state = (LoraRadioState)9U; reason = SILVERSTAR_ASSERT_REASON_ENUM_RANGE; }
    before = s_contexts[0]; send_before = s_send_count; rx_before = s_set_rx_count;
    memset(output, 0xCC, sizeof(output));
    if (setjmp(s_trap_return) == 0)
    {
        if (strncmp(name, "air_", 4U) == 0) { (void)Lora_PacketAirtimeMs(0U, 64U); }
        else if (strcmp(name, "rx_hold") == 0) { (void)Lora_RxPacketHeld(0U); }
        else if (strcmp(name, "schedule_role") == 0) { (void)Lora_ScheduleRoleSet(0U, LoraScheduleRole_Ground); }
        else if (strcmp(name, "tx_len") == 0) { Lora_TryStartNextTx(0U); }
        else if (strncmp(name, "tx_", 3U) == 0) { (void)Lora_TxEnqueue(0U, &byte, 1U); }
        else if (strcmp(name, "rx_tail") == 0 || strcmp(name, "rx_len") == 0 || strcmp(name, "rx_count") == 0 || strcmp(name, "rx_sequence") == 0) { (void)Lora_RxDequeue(0U, output, &len, NULL, NULL); }
        else if (strcmp(name, "rx_done_flag") == 0) { Lora_RxCompletionProcess(0U); }
        else if (strcmp(name, "control_active_init") == 0) { (void)Lora_Init(0U); }
        else if (strncmp(name, "control_", 8U) == 0) { Lora_ControlProcess(0U); }
        else if (strcmp(name, "packet_type") == 0) { Lora_StartRx(0U); }
        else if (strcmp(name, "force_packet_type") == 0) { (void)Lora_ForceRxContinuousDirect(0U); }
        else if (strcmp(name, "try_busy") == 0) { Lora_TryStartNextTx(0U); }
        else if (strcmp(name, "raw_busy") == 0) { Lora_RawIrqProcess(0U); }
        else if (strcmp(name, "irq_busy") == 0) { Lora_IrqProcess(0U, IRQ_RX_TX_TIMEOUT); }
        else if (strcmp(name, "diag_uninitialized") == 0) { Lora_DiagnosticsRefresh(0U); }
        else if (strcmp(name, "rx_error") == 0) { Lora_RxErrorProcess(0U); }
        else if (strcmp(name, "radio_state") == 0) { Lora_DiagRecordIrq(0U, IRQ_RX_TX_TIMEOUT); }
        else { Lora_Process((strcmp(name, "instance") == 0) ? PROJECT_SX1281_INSTANCE_COUNT : 0U); }
        TEST_CHECK(0); /* The real fault latch/terminal boundary must be reached. */
    }
    TEST_CHECK(SilverStarAssert_FaultRecordGet(&fault) == 1U);
    TEST_CHECK(fault.module_id == SILVERSTAR_ASSERT_MODULE_DEVICE);
    TEST_CHECK(fault.reason_id == reason);
    TEST_CHECK(fault.line != 0U);
    TEST_CHECK(s_send_count == send_before);
    TEST_CHECK(s_set_rx_count == rx_before);
    TEST_CHECK(memcmp(&before, &s_contexts[0], sizeof(before)) == 0);
    TEST_CHECK(output[0] == 0xCCU);
    TEST_CHECK(len == 99U);
}

int main(int argc, char **argv)
{
    if (argc != 2) { return 2; }
    if (strcmp(argv[1], "reinit") == 0) { Test_ReinitializationFailure(); }
    else if (strcmp(argv[1], "normal") == 0) { Test_NormalQueuesAndTimeout(); }
    else { Test_Corruption(argv[1]); }
    return Test_Finish(argv[1]);
}
