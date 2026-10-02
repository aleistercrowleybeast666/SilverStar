/* Adapter/LED tests with bounded port models. Real retirement/queue behavior
 * is checked separately by sx1281_contract_host.c. No MCU recovery claim. */
#include <assert.h>
#include <string.h>
#include "ground_radio.h"
#include "ground_radio_activity.h"
#include "ground_radio_config.h"
#include "project_resources.h"
#include "sx1281_device.h"
#include "platform_gpio.h"
#include "platform_time.h"

static uint32_t now_ms;
static LoraStats states[4];
static uint8_t online[4], bad_init[4], bad_config[4], bad_role[4];
static unsigned init_count[4], retire_count[4], process_count[4];
static unsigned tx_count[4], rx_count[4], time_reads;
static unsigned gpio_count[96];
static uint8_t gpio_level[96];
static PlatformResult gpio_result = PLATFORM_OK;
static LoraDeactivateResult retire_result = LoraDeactivateResult_Ok;
static LoraTxEnqueueResult tx_result = LORA_TX_ENQUEUE_OK;
static LoraRxDequeueResult rx_result = LORA_RX_DEQUEUE_EMPTY;
static char calls[128];
static unsigned call_count;
static void Call(char name) { assert(call_count < sizeof(calls)); calls[call_count++] = name; }
uint32_t PlatformTime_Ms(void) { time_reads++; return now_ms; }
PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    assert(id < PLATFORM_GPIO_COUNT && high <= 1U);
    gpio_count[id]++; if (gpio_result == PLATFORM_OK) { gpio_level[id] = high; }
    return gpio_result;
}
LoraInitResult Lora_Init(uint8_t i)
{
    assert(i < PROJECT_SX1281_INSTANCE_COUNT); init_count[i]++; Call('I');
    online[i] = (uint8_t)(bad_init[i] == 0U);
    return bad_init[i] ? LORA_INIT_PORT_ERROR : LORA_INIT_OK;
}
LoraConfigResult Lora_ApplyDefaultConfig(uint8_t i)
{ Call('C'); return bad_config[i] ? LORA_CONFIG_PORT_ERROR : LORA_CONFIG_OK; }
LoraScheduleRoleResult Lora_ScheduleRoleSet(uint8_t i, LoraScheduleRole role)
{ assert(role == LoraScheduleRole_Ground); Call('R'); return bad_role[i] ? LoraScheduleRoleResult_NotReady : LoraScheduleRoleResult_Ok; }
void Lora_StartRx(uint8_t i) { assert(i < PROJECT_SX1281_INSTANCE_COUNT); Call('S'); }
void Lora_Process(uint8_t i) { assert(i < PROJECT_SX1281_INSTANCE_COUNT); process_count[i]++; }
LoraDeactivateResult Lora_Deactivate(uint8_t i)
{ assert(i < PROJECT_SX1281_INSTANCE_COUNT); retire_count[i]++; online[i] = 0U; return retire_result; }
void Lora_GetDebugSnapshot(uint8_t i, LoraDebugSnapshot *out)
{ memset(out, 0, sizeof(*out)); out->initialized = online[i]; out->stats = states[i]; }
void Lora_GetStats(uint8_t i, LoraStats *out) { *out = states[i]; }
LoraTxEnqueueResult Lora_TxEnqueue(uint8_t i, const uint8_t *data, uint8_t len)
{ assert(data != NULL && len == 1U); tx_count[i]++; return tx_result; }
LoraRxDequeueResult Lora_RxDequeue(uint8_t i, uint8_t *data, uint8_t *len, int8_t *rssi, int8_t *snr)
{ (void)data; (void)len; (void)rssi; (void)snr; rx_count[i]++; return rx_result; }

static void Routing(uint8_t owner)
{
    uint8_t data = 7U, len = 1U; int8_t rssi = 0, snr = 0; unsigned i;
    GroundRadioStats out;
    assert(GroundRadio_ActiveInstanceGet() == owner);
    assert(GroundRadio_TxEnqueue(&data, 1U) == GROUND_RADIO_OK);
    tx_result = LORA_TX_ENQUEUE_QUEUE_FULL;
    assert(GroundRadio_TxEnqueue(&data, 1U) == GROUND_RADIO_BUSY);
    tx_result = LORA_TX_ENQUEUE_NOT_INIT;
    assert(GroundRadio_TxEnqueue(&data, 1U) == GROUND_RADIO_ERROR);
    assert(GroundRadio_RxDequeue(&data, &len, &rssi, &snr) == GROUND_RADIO_EMPTY);
    rx_result = LORA_RX_DEQUEUE_OK;
    assert(GroundRadio_RxDequeue(&data, &len, &rssi, &snr) == GROUND_RADIO_OK);
    states[owner].rx_crc_error = 19U;
    GroundRadio_StatsGet(&out); assert(out.rx_crc_error == 19U);
    GroundRadio_StatsGet(NULL);
    for (i = 0U; i < PROJECT_SX1281_INSTANCE_COUNT; i++)
    { assert(tx_count[i] == (i == owner ? 3U : 0U)); assert(rx_count[i] == (i == owner ? 2U : 0U)); }
}
static void Tick(uint32_t tick) { now_ms = tick; GroundRadio_Process(); }
static void FaultHold(uint8_t owner, uint32_t start)
{
    unsigned before = retire_count[owner];
    online[owner] = 0U;
    Tick(start); Tick(start + 249U); assert(retire_count[owner] == before);
    Tick(start + 250U); assert(retire_count[owner] == before + 1U);
}
int main(int argc, char **argv)
{
    const uint8_t initial = GROUND_RADIO_INITIAL_INSTANCE;
    assert(argc == 2);
    if (strcmp(argv[1], "cold_start_error") == 0)
    {
        unsigned i;
        retire_result = LoraDeactivateResult_PortError;
        assert(GroundRadio_Init() == GROUND_RADIO_ERROR);
        for (i = 0U; i < PROJECT_SX1281_INSTANCE_COUNT; i++) { assert(init_count[i] == 0U); }
        return 0;
    }
    if (strcmp(argv[1], "init_error") == 0)
    {
        bad_init[initial] = 1U;
        assert(GroundRadio_Init() == (PROJECT_SX1281_INSTANCE_COUNT == 1U ? GROUND_RADIO_ERROR : GROUND_RADIO_OK));
        assert(retire_count[initial] == (PROJECT_SX1281_INSTANCE_COUNT == 1U ? 0U : 2U));
        return 0;
    }
    if (strcmp(argv[1], "config_error") == 0)
    {
        bad_config[initial] = 1U; assert(GroundRadio_Init() == GROUND_RADIO_ERROR);
        assert(call_count == 2U && memcmp(calls, "IC", 2U) == 0); return 0;
    }
    if (strcmp(argv[1], "role_error") == 0)
    {
        bad_role[initial] = 1U; assert(GroundRadio_Init() == GROUND_RADIO_ERROR);
        assert(call_count == 3U && memcmp(calls, "ICR", 3U) == 0); return 0;
    }
    assert(GroundRadio_Init() == GROUND_RADIO_OK);
    assert(call_count == 4U && memcmp(calls, "ICRS", 4U) == 0);
    if (PROJECT_SX1281_INSTANCE_COUNT > 1U)
    {
        unsigned i;
        for (i = 0U; i < PROJECT_SX1281_INSTANCE_COUNT; i++)
        { assert(retire_count[i] == 1U); assert(online[i] == (i == initial ? 1U : 0U)); }
    }
    if (strcmp(argv[1], "routing") == 0) { Routing(initial); return 0; }
    if (strcmp(argv[1], "quiet") == 0)
    {
        unsigned i; for (i = 0U; i < 100U; i++) { Tick(i * 10000U); }
        assert(init_count[initial] == 1U);
        assert(retire_count[initial] == (PROJECT_SX1281_INSTANCE_COUNT == 1U ? 0U : 1U));
        assert(process_count[initial] == 100U);
        if (PROJECT_SX1281_INSTANCE_COUNT == 1U && GROUND_ACTIVITY_ENABLED == 0U)
        { assert(time_reads == 0U); }
        return 0;
    }
    if (strcmp(argv[1], "transient") == 0)
    {
        online[initial] = 0U; Tick(0U); Tick(249U);
        online[initial] = 1U; Tick(250U); Tick(10000U);
        assert(retire_count[initial] == 1U); return 0;
    }
    if (strcmp(argv[1], "retire_error") == 0)
    {
        retire_result = LoraDeactivateResult_PortError; FaultHold(initial, 1U);
        Tick(100000U); assert(retire_count[initial] == 2U);
        assert(init_count[initial + 1U] == 0U); return 0;
    }
    if (strcmp(argv[1], "forward") == 0 || strcmp(argv[1], "wrap") == 0)
    {
        uint8_t next = (uint8_t)(initial + 1U);
        FaultHold(initial, strcmp(argv[1], "wrap") == 0 ? UINT32_MAX - 100U : 1U);
        assert(init_count[next] == 1U); Routing(next);
        FaultHold(next, 10000U); Tick(100000U);
        assert(init_count[initial] == 1U && init_count[next] == 1U);
        assert(retire_count[next] == 2U); return 0;
    }
    if (strcmp(argv[1], "led") == 0)
    {
        unsigned tx = (unsigned)GROUND_ACTIVITY_TX_GPIO;
        unsigned rx = (unsigned)GROUND_ACTIVITY_RX_GPIO;
        assert(tx < 96U && rx < 96U);
        assert(gpio_count[tx] == 1U); /* Shared pin is initialized once. */
        Tick(10U); assert(gpio_count[tx] == 1U);
        states[initial].tx_timeout++; states[initial].rx_crc_error++;
        Tick(11U); assert(gpio_count[tx] == 1U);
        states[initial].tx_ok++; Tick(12U);
        assert(gpio_level[tx] == GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        states[initial].tx_ok++; Tick(51U); assert(gpio_count[tx] == 2U);
        states[initial].rx_ok++; Tick(52U);
        assert(gpio_level[tx] == 1U - GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        if (tx != rx) { assert(gpio_level[rx] == GROUND_ACTIVITY_RX_ACTIVE_HIGH); }
        states[initial].tx_ok++; Tick(53U); assert(gpio_level[tx] == GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        Tick(93U); assert(gpio_level[tx] == 1U - GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        gpio_result = PLATFORM_IO_ERROR; states[initial].tx_ok++; Tick(94U);
        assert(GroundRadioActivity_ErrorCountGet() != 0U);
        gpio_result = PLATFORM_OK;
        GroundRadioActivity_Init(0U, 0U);
        GroundRadioActivity_Process(UINT32_MAX - 10U, 1U, 0U);
        GroundRadioActivity_Process(29U, 1U, 0U);
        assert(gpio_level[tx] == 1U - GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        GroundRadioActivity_Process(30U, 2U, 0U);
        gpio_result = PLATFORM_IO_ERROR;
        GroundRadioActivity_Process(70U, 2U, 0U);
        assert(gpio_level[tx] == GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        gpio_result = PLATFORM_OK;
        GroundRadioActivity_Process(71U, 3U, 0U);
        assert(gpio_level[tx] == 1U - GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        GroundRadioActivity_Process(72U, 4U, 0U);
        assert(gpio_level[tx] == GROUND_ACTIVITY_TX_ACTIVE_HIGH);
        return 0;
    }
    assert(0 && "unknown scenario"); return 1;
}
