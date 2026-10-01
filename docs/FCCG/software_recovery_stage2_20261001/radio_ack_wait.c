/* Software scheduling evidence only: real driver/protocol, fake IRQ/clock/SPI.
 * Continuous TX completion is injected; no MCU timing/RF reliability claim. */
#define TEST_SX1281_PORTS_ONLY 1
#define SX1280SendPayload Test_OriginalSendPayload
#include "test_sx1281_device.c"
#undef SX1280SendPayload
#include "air_protocol.h"
static uint8_t s_last_type;
static uint8_t s_last_command_sequence;
void SX1280SendPayload(uint8_t instance, uint8_t *payload, uint8_t size, TickTime_t timeout)
{
    s_last_type = payload[0];
    s_last_command_sequence = (size >= 3U) ? payload[2] : 0U;
    Test_OriginalSendPayload(instance, payload, size, timeout);
}
#include "sx1281_device.c"
int main(void)
{
    uint8_t telemetry[9] = {0x13U};
    uint8_t command[64];
    uint8_t ack[9];
    uint8_t length = 0U;
    uint8_t ack_length = 0U;
    uint32_t cycle;
    uint32_t accepted_ms = 0U;
    uint32_t wait_ms = 0U;
    s_tick_ms = UINT32_MAX - 60U;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    for (cycle = 0U; cycle < LORA_TX_QUEUE_DEPTH; cycle++)
    { TEST_CHECK(Lora_TxEnqueue(0U, telemetry, sizeof(telemetry)) == LORA_TX_ENQUEUE_OK); }
    Lora_StartRx(0U);
    s_tick_ms += 120U;
    Lora_Process(0U);
    s_host_receive_enabled = 1U;
    for (cycle = 0U; cycle < 16U; cycle++)
    {
        uint32_t sends = s_host_send_count;
        s_raw_irq = IRQ_TX_DONE; s_dio1_pending = 1U;
        Lora_Process(0U);
        TEST_CHECK(s_host_send_count == sends);
        s_tick_ms += 60U;
        s_raw_irq = IRQ_RX_DONE; s_dio1_pending = 1U;
        Lora_Process(0U);
        TEST_CHECK(Lora_RxDequeue(0U, command, &length, NULL, NULL) == LORA_RX_DEQUEUE_OK);
        TEST_CHECK(length == 9U && command[1] == 255U);
        if (cycle == 0U)
        {
            accepted_ms = s_tick_ms;
            TEST_CHECK(Air_AckBuild(1U, command[1], command[2], AIR_ACK_RESULT_OK,
                s_tick_ms, ack, sizeof(ack), &ack_length) == AIR_BUILD_OK);
            TEST_CHECK(Lora_TxEnqueue(0U, ack, ack_length) == LORA_TX_ENQUEUE_OK);
        }
        else
        { TEST_CHECK(Lora_TxEnqueue(0U, telemetry, sizeof(telemetry)) == LORA_TX_ENQUEUE_OK); }
        s_tick_ms += 120U;
        Lora_Process(0U);
        if (cycle == 7U)
        {
            TEST_CHECK(s_last_type == AIR_TYPE_ACK && s_last_command_sequence == 255U);
            wait_ms = (uint32_t)(s_tick_ms - accepted_ms);
            TEST_CHECK(wait_ms <= 1440U);
        }
    }
    (void)printf("Mock ACK admitted behind seven telemetry packets: %lu ms to TX start; injected completion, no RF deadline proof\n", (unsigned long)wait_ms);
    return Test_Finish("continuous_load_ack_wait");
}
