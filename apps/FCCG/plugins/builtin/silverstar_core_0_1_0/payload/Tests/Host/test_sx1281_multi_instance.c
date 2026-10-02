#include <stdint.h>
#include <string.h>

#include "platform_critical.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "project_resources.h"
#include "sx1280.h"
#include "sx1281_bus.h"
#include "sx1281_device.h"
#include "test_common.h"

#define TEST_INSTANCE_COUNT 2U

typedef struct
{
    uint32_t send_count;
    uint8_t sent[16];
    uint8_t sent_length;
    uint16_t raw_irq;
    uint8_t receive[16];
    uint8_t receive_length;
} TestRadioContext;

static TestRadioContext s_radios[TEST_INSTANCE_COUNT];
static uint8_t s_gpio_irq[PLATFORM_GPIO_COUNT];
static uint32_t s_tick_ms;
static PlatformResult s_gpio_write_results[PLATFORM_GPIO_COUNT];
static uint32_t s_gpio_write_attempts[PLATFORM_GPIO_COUNT];
static uint8_t s_gpio_written_levels[PLATFORM_GPIO_COUNT];
static uint8_t s_gpio_levels[PLATFORM_GPIO_COUNT];

void SX1280Init(uint8_t instance) { (void)instance; }

RadioStatus_t SX1280GetStatus(uint8_t instance)
{
    RadioStatus_t status;

    (void)instance;
    status.Value = 0x40U; /* Semtech ChipMode2: standby. */
    return status;
}

uint16_t SX1280GetFirmwareVersion(uint8_t instance)
{ (void)instance; return 0x1234U; }
void SX1280SetRegulatorMode(uint8_t instance, RadioRegulatorModes_t mode)
{ (void)instance; (void)mode; }
void SX1280SetStandby(uint8_t instance, RadioStandbyModes_t mode)
{ (void)instance; (void)mode; }
void SX1280SetPacketType(uint8_t instance, RadioPacketTypes_t type)
{ (void)instance; (void)type; }
void SX1280SetModulationParams(uint8_t instance, ModulationParams_t *params)
{ (void)instance; (void)params; }
void SX1280SetPacketParams(uint8_t instance, PacketParams_t *params)
{ (void)instance; (void)params; }
void SX1280SetRfFrequency(uint8_t instance, uint32_t frequency)
{ (void)instance; (void)frequency; }
void SX1280SetBufferBaseAddresses(
    uint8_t instance, uint8_t tx, uint8_t rx)
{ (void)instance; (void)tx; (void)rx; }
void SX1280SetTxParams(
    uint8_t instance, int8_t power, RadioRampTimes_t ramp)
{ (void)instance; (void)power; (void)ramp; }
void SX1280SetDioIrqParams(
    uint8_t instance, uint16_t irq, uint16_t dio1,
    uint16_t dio2, uint16_t dio3)
{
    (void)instance;
    (void)irq;
    (void)dio1;
    (void)dio2;
    (void)dio3;
}
void SX1280SetRx(uint8_t instance, TickTime_t timeout)
{ (void)instance; (void)timeout; }

uint16_t SX1280GetIrqStatus(uint8_t instance)
{ return s_radios[instance].raw_irq; }

void SX1280ClearIrqStatus(uint8_t instance, uint16_t irq)
{
    (void)irq;
    s_radios[instance].raw_irq = 0U;
}

RadioPacketTypes_t SX1280GetPacketType(uint8_t instance)
{ (void)instance; return PACKET_TYPE_LORA; }
int8_t SX1280GetRssiInst(uint8_t instance)
{ (void)instance; return -60; }

uint8_t SX1280GetPayload(
    uint8_t instance, uint8_t *payload, uint8_t *size, uint8_t maximum)
{
    TestRadioContext *radio = &s_radios[instance];

    if ((payload == NULL) || (size == NULL) ||
        (radio->receive_length > maximum))
    { return 1U; }
    (void)memcpy(payload, radio->receive, radio->receive_length);
    *size = radio->receive_length;
    return 0U;
}

void SX1280GetPacketStatus(uint8_t instance, PacketStatus_t *status)
{
    (void)instance;
    if (status != NULL)
    {
        (void)memset(status, 0, sizeof(*status));
        status->Params.LoRa.RssiPkt = -70;
        status->Params.LoRa.SnrPkt = 8;
    }
}

void SX1280SendPayload(
    uint8_t instance, uint8_t *payload, uint8_t size,
    TickTime_t timeout)
{
    TestRadioContext *radio = &s_radios[instance];

    (void)timeout;
    TEST_CHECK(size <= sizeof(radio->sent));
    (void)memcpy(radio->sent, payload, size);
    radio->sent_length = size;
    radio->send_count++;
}

void Sx1281Bus_Init(uint8_t instance) { (void)instance; }
void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{
    (void)instance;
    if (status != NULL) { (void)memset(status, 0, sizeof(*status)); }
}

static PlatformGpioId Test_ResourceGpioGet(
    uint8_t instance, uint8_t member)
{
    ProjectSx1281Resources resources;

    if (ProjectSx1281Resources_Get(instance, &resources) !=
        SYSTEM_DEVICE_OK)
    { return PLATFORM_GPIO_COUNT; }
    switch (member)
    {
        case 0U: return resources.nss;
        case 1U: return resources.reset;
        case 2U: return resources.busy;
        case 3U: return resources.dio1;
        default: return PLATFORM_GPIO_COUNT;
    }
}

PlatformGpioId Sx1281Bus_NssGet(uint8_t instance)
{ return Test_ResourceGpioGet(instance, 0U); }
PlatformGpioId Sx1281Bus_ResetGet(uint8_t instance)
{ return Test_ResourceGpioGet(instance, 1U); }
PlatformGpioId Sx1281Bus_BusyGet(uint8_t instance)
{ return Test_ResourceGpioGet(instance, 2U); }
PlatformGpioId Sx1281Bus_Dio1Get(uint8_t instance)
{ return Test_ResourceGpioGet(instance, 3U); }

uint32_t PlatformTime_Ms(void) { return s_tick_ms; }
uint64_t PlatformTime_Us(void) { return (uint64_t)s_tick_ms * 1000ULL; }
void PlatformTime_DelayMs(uint32_t delay_ms) { s_tick_ms += delay_ms; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t logical_high)
{
    if ((id >= PLATFORM_GPIO_COUNT) || (logical_high > 1U))
    { return PLATFORM_INVALID_ARGUMENT; }
    s_gpio_write_attempts[id]++;
    s_gpio_written_levels[id] = logical_high;
    if (s_gpio_write_results[id] == PLATFORM_OK)
    { s_gpio_levels[id] = logical_high; }
    return s_gpio_write_results[id];
}

PlatformResult PlatformGpio_Read(
    PlatformGpioId id, uint8_t *logical_high)
{
    if ((id >= PLATFORM_GPIO_COUNT) || (logical_high == NULL))
    { return PLATFORM_INVALID_ARGUMENT; }
    *logical_high = 0U;
    return PLATFORM_OK;
}

uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t pending;

    if (id >= PLATFORM_GPIO_COUNT) { return 0U; }
    pending = s_gpio_irq[id];
    s_gpio_irq[id] = 0U;
    return pending;
}

static void Test_IrqRaise(uint8_t instance, uint16_t irq)
{
    PlatformGpioId dio1 = Sx1281Bus_Dio1Get(instance);

    s_radios[instance].raw_irq = irq;
    s_gpio_irq[dio1] = 1U;
}

static void Test_ContextQueueAndIrqIsolation(void)
{
    static const uint8_t payload0[] = {0x10U, 0x11U, 0x12U};
    static const uint8_t payload1[] = {0x20U, 0x21U};
    static const uint8_t receive0[] = {0xA0U, 0xA1U};
    static const uint8_t receive1[] = {0xB0U, 0xB1U, 0xB2U};
    ProjectSx1281Resources resources0;
    ProjectSx1281Resources resources1;
    LoraDebugSnapshot debug0;
    LoraDebugSnapshot debug1;
    LoraStats stats0;
    LoraStats stats1;
    uint8_t received[16];
    uint8_t received_length;

    (void)memset(s_radios, 0, sizeof(s_radios));
    (void)memset(s_gpio_irq, 0, sizeof(s_gpio_irq));
    TEST_CHECK(ProjectSx1281Resources_Get(0U, &resources0) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(ProjectSx1281Resources_Get(1U, &resources1) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(resources0.spi != resources1.spi);
    TEST_CHECK(resources0.dio1 != resources1.dio1);
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    TEST_CHECK(Lora_Init(1U) == LORA_INIT_OK);
    TEST_CHECK(Lora_TxEnqueue(0U, payload0, sizeof(payload0)) ==
               LORA_TX_ENQUEUE_OK);
    TEST_CHECK(Lora_TxEnqueue(1U, payload1, sizeof(payload1)) ==
               LORA_TX_ENQUEUE_OK);

    Lora_StartRx(0U);
    Lora_StartRx(1U);
    s_tick_ms += 122U; /* ceil117.524ms maximum packet plus4ms turn margin. */
    Lora_Process(0U);
    TEST_CHECK(s_radios[0].send_count == 1U);
    TEST_CHECK(s_radios[1].send_count == 0U);
    TEST_CHECK(s_radios[0].sent_length == sizeof(payload0));
    TEST_CHECK(memcmp(s_radios[0].sent, payload0, sizeof(payload0)) == 0);
    Lora_GetDebugSnapshot(0U, &debug0);
    Lora_GetDebugSnapshot(1U, &debug1);
    TEST_CHECK(debug0.tx_queue_count == 0U);
    TEST_CHECK(debug1.tx_queue_count == 1U);

    Lora_Process(1U);
    TEST_CHECK(s_radios[1].send_count == 1U);
    TEST_CHECK(memcmp(s_radios[1].sent, payload1, sizeof(payload1)) == 0);
    Test_IrqRaise(0U, IRQ_TX_DONE);
    Lora_Process(0U);
    Test_IrqRaise(1U, IRQ_RX_TX_TIMEOUT);
    Lora_Process(1U);
    Lora_GetStats(0U, &stats0);
    Lora_GetStats(1U, &stats1);
    TEST_CHECK(stats0.tx_ok == 1U && stats0.tx_timeout == 0U);
    TEST_CHECK(stats1.tx_ok == 0U && stats1.tx_timeout == 1U);

    (void)memcpy(s_radios[0].receive, receive0, sizeof(receive0));
    s_radios[0].receive_length = sizeof(receive0);
    (void)memcpy(s_radios[1].receive, receive1, sizeof(receive1));
    s_radios[1].receive_length = sizeof(receive1);
    Test_IrqRaise(0U, IRQ_RX_DONE);
    Lora_Process(0U);
    received_length = 0U;
    TEST_CHECK(Lora_RxDequeue(
        1U, received, &received_length, NULL, NULL) ==
        LORA_RX_DEQUEUE_EMPTY);
    TEST_CHECK(Lora_RxDequeue(
        0U, received, &received_length, NULL, NULL) ==
        LORA_RX_DEQUEUE_OK);
    TEST_CHECK(received_length == sizeof(receive0));
    TEST_CHECK(memcmp(received, receive0, sizeof(receive0)) == 0);

    Test_IrqRaise(1U, IRQ_RX_DONE);
    Lora_Process(1U);
    TEST_CHECK(Lora_RxDequeue(
        1U, received, &received_length, NULL, NULL) ==
        LORA_RX_DEQUEUE_OK);
    TEST_CHECK(received_length == sizeof(receive1));
    TEST_CHECK(memcmp(received, receive1, sizeof(receive1)) == 0);

    Lora_GetStats(1U, &stats1);
    Lora_ClearStats(0U);
    Lora_GetStats(1U, &stats0);
    TEST_CHECK(memcmp(&stats0, &stats1, sizeof(stats0)) == 0);
}

static void Test_ReceiveHoldIsolation(void)
{
    uint8_t payload[2] = {0x20U, 1U};
    (void)memset(s_radios, 0, sizeof(s_radios));
    s_tick_ms = 0U;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    TEST_CHECK(Lora_Init(1U) == LORA_INIT_OK);
    TEST_CHECK(Lora_TxEnqueue(0U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_OK);
    TEST_CHECK(Lora_TxEnqueue(1U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_OK);
    Lora_StartRx(0U); Lora_StartRx(1U);
    s_tick_ms = 100U; Test_IrqRaise(0U, IRQ_PREAMBLE_DETECTED); Lora_Process(0U);
    s_tick_ms = 122U; Lora_Process(1U); Lora_Process(0U);
    TEST_CHECK(s_radios[1].send_count == 1U);
    TEST_CHECK(s_radios[0].send_count == 0U);
    s_tick_ms = 200U; Test_IrqRaise(0U, IRQ_HEADER_VALID); Lora_Process(0U);
    s_tick_ms = 221U; Lora_Process(0U);
    TEST_CHECK(s_radios[0].send_count == 0U);
    s_tick_ms = 222U; Lora_Process(0U);
    TEST_CHECK(s_radios[0].send_count == 1U); /* Header did not renew first100ms deadline. */
    TEST_CHECK(s_radios[1].send_count == 1U);
}

static void Test_RoleCapacityIsolation(void)
{
    uint8_t payload[2] = {0x20U, 1U};
    (void)memset(s_radios, 0, sizeof(s_radios));
    s_tick_ms = 0U;
    TEST_CHECK(Lora_Init(0U) == LORA_INIT_OK);
    TEST_CHECK(Lora_Init(1U) == LORA_INIT_OK);
    TEST_CHECK(Lora_ScheduleRoleSet(2U, LoraScheduleRole_Ground) == LoraScheduleRoleResult_InvalidArgument);
    TEST_CHECK(Lora_ScheduleRoleSet(1U, (LoraScheduleRole)2U) == LoraScheduleRoleResult_InvalidArgument);
    TEST_CHECK(Lora_ScheduleRoleSet(1U, LoraScheduleRole_Ground) == LoraScheduleRoleResult_Ok);
    for (uint8_t index = 0U; index < 8U; index++)
    { TEST_CHECK(Lora_TxEnqueue(1U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_OK); }
    TEST_CHECK(Lora_TxEnqueue(1U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_QUEUE_FULL);
    TEST_CHECK(Lora_TxEnqueue(0U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_OK);
    TEST_CHECK(Lora_TxEnqueue(0U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_OK);
    TEST_CHECK(Lora_TxEnqueue(0U, payload, sizeof(payload)) == LORA_TX_ENQUEUE_QUEUE_FULL);
    Lora_StartRx(0U); Lora_StartRx(1U);
    s_tick_ms = 122U; Lora_Process(0U); Lora_Process(1U);
    TEST_CHECK(s_radios[0].send_count == 1U && s_radios[1].send_count == 0U);
    s_tick_ms = 244U; Lora_Process(1U);
    TEST_CHECK(s_radios[1].send_count == 1U);
}

static void Test_DeactivateIsolation(uint8_t retired, PlatformResult gpio_result)
{
    static const uint8_t payload[] = {0x30U, 0x31U};
    uint32_t completed[TEST_INSTANCE_COUNT];
    uint32_t pending[TEST_INSTANCE_COUNT];
    uint32_t control[TEST_INSTANCE_COUNT];
    uint32_t age_ms = 0U;
    uint8_t other = (uint8_t)(1U - retired);
    uint8_t received[16];
    uint8_t length = 0U;
    PlatformGpioId reset = Sx1281Bus_ResetGet(retired);
    PlatformGpioId other_reset = Sx1281Bus_ResetGet(other);
    LoraDebugSnapshot before = {0};
    LoraDebugSnapshot after = {0};
    LoraDebugSnapshot cleared = {0};
    LoraDiagSnapshot diag_before = {0};
    LoraDiagSnapshot diag_after = {0};
    LoraDiagSnapshot diag_cleared = {0};
    LoraControlResult control_result = {0};
    LoraChipStatus chip = {0};
    LoraDeactivateResult result;

    (void)memset(s_radios, 0, sizeof(s_radios));
    (void)memset(s_gpio_irq, 0, sizeof(s_gpio_irq));
    (void)memset(s_gpio_write_results, 0, sizeof(s_gpio_write_results));
    (void)memset(s_gpio_write_attempts, 0, sizeof(s_gpio_write_attempts));
    (void)memset(s_gpio_written_levels, 1, sizeof(s_gpio_written_levels));
    (void)memset(s_gpio_levels, 1, sizeof(s_gpio_levels));
    s_tick_ms = 0U;
    TEST_CHECK(reset != other_reset && reset < PLATFORM_GPIO_COUNT);
    for (uint8_t instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    {
        TEST_CHECK(Lora_Init(instance) == LORA_INIT_OK);
        TEST_CHECK(Lora_TxEnqueueTracked(instance, payload, sizeof(payload),
                                       &completed[instance]) == LORA_TX_ENQUEUE_OK);
        Lora_StartRx(instance);
    }
    s_tick_ms = 122U;
    for (uint8_t instance = 0U; instance < TEST_INSTANCE_COUNT; instance++)
    {
        Lora_Process(instance);
        TEST_CHECK(s_radios[instance].send_count == 1U);
        Test_IrqRaise(instance, IRQ_TX_DONE);
        Lora_Process(instance);
        TEST_CHECK(Lora_TxResultGet(instance, completed[instance], &age_ms) ==
                   LoraTxQueryResult_Complete);
        s_radios[instance].receive[0] = (uint8_t)(0xA0U + instance);
        s_radios[instance].receive_length = 1U;
        Test_IrqRaise(instance, IRQ_RX_DONE);
        Lora_Process(instance);
        TEST_CHECK(Lora_TxEnqueueTracked(instance, payload, sizeof(payload),
                                       &pending[instance]) == LORA_TX_ENQUEUE_OK);
        TEST_CHECK(Lora_ControlSubmit(instance, LORA_CONTROL_IRQ_CLEAR, 1000U,
                                     &control[instance]) == LORA_CONTROL_SUBMIT_OK);
        TEST_CHECK(Lora_ControlResultGet(instance, control[instance], &control_result) ==
                   LORA_CONTROL_GET_PENDING);
        Test_IrqRaise(instance, IRQ_RX_DONE); /* Leave both GPIO latches pending. */
    }
    Lora_GetDebugSnapshot(other, &before);
    Lora_GetDiagSnapshot(other, &diag_before);
    TEST_CHECK(before.initialized == 1U && before.tx_queue_count == 1U &&
               before.rx_queue_count == 1U);
    TEST_CHECK(before.stats.tx_ok == 1U && before.stats.rx_ok == 1U);
    s_gpio_write_results[reset] = gpio_result;
    result = Lora_Deactivate(retired);
    TEST_CHECK(result == ((gpio_result == PLATFORM_OK) ?
               LoraDeactivateResult_Ok : LoraDeactivateResult_PortError));
    TEST_CHECK(s_gpio_write_attempts[reset] == 1U);
    TEST_CHECK(s_gpio_written_levels[reset] == 0U);
    TEST_CHECK(s_gpio_levels[reset] == ((gpio_result == PLATFORM_OK) ? 0U : 1U));
    TEST_CHECK(s_gpio_write_attempts[other_reset] == 0U && s_gpio_levels[other_reset] == 1U);
    TEST_CHECK(s_gpio_irq[Sx1281Bus_Dio1Get(retired)] == 0U);
    TEST_CHECK(s_gpio_irq[Sx1281Bus_Dio1Get(other)] == 1U);
    Lora_GetDebugSnapshot(retired, &after);
    TEST_CHECK(memcmp(&after, &cleared, sizeof(after)) == 0);
    Lora_GetDiagSnapshot(retired, &diag_after);
    TEST_CHECK(memcmp(&diag_after, &diag_cleared, sizeof(diag_after)) == 0);
    TEST_CHECK(Lora_IsBusy(retired) == LORA_BUSY_IDLE);
    TEST_CHECK(Lora_TxResultGet(retired, completed[retired], &age_ms) == LoraTxQueryResult_NotFound);
    TEST_CHECK(Lora_TxResultGet(retired, pending[retired], &age_ms) == LoraTxQueryResult_NotFound);
    TEST_CHECK(Lora_ControlResultGet(retired, control[retired], &control_result) ==
               LORA_CONTROL_GET_NOT_FOUND);
    TEST_CHECK(Lora_ControlSubmit(retired, LORA_CONTROL_IRQ_CLEAR, 1000U, &age_ms) ==
               LORA_CONTROL_SUBMIT_NOT_INIT);
    TEST_CHECK(Lora_ChipStatusGet(retired, &chip) == LORA_DIAG_RESULT_NOT_INIT);
    TEST_CHECK(Lora_RxDequeue(retired, received, &length, NULL, NULL) == LORA_RX_DEQUEUE_EMPTY);
    TEST_CHECK(Lora_TxEnqueue(retired, payload, sizeof(payload)) == LORA_TX_ENQUEUE_NOT_INIT);
    (void)memset(&after, 0, sizeof(after));
    Lora_GetDebugSnapshot(other, &after);
    TEST_CHECK(memcmp(&before, &after, sizeof(before)) == 0);
    Lora_GetDiagSnapshot(other, &diag_after);
    TEST_CHECK(memcmp(&diag_before, &diag_after, sizeof(diag_before)) == 0);
    TEST_CHECK(Lora_TxResultGet(other, completed[other], &age_ms) == LoraTxQueryResult_Complete);
    TEST_CHECK(Lora_TxResultGet(other, pending[other], &age_ms) == LoraTxQueryResult_Pending);
    TEST_CHECK(Lora_ControlResultGet(other, control[other], &control_result) == LORA_CONTROL_GET_PENDING);
    TEST_CHECK(Lora_ChipStatusGet(other, &chip) == LORA_DIAG_RESULT_OK && chip.verified == 1U);
    TEST_CHECK(Lora_RxDequeue(other, received, &length, NULL, NULL) == LORA_RX_DEQUEUE_OK);
    TEST_CHECK(length == 1U && received[0] == (uint8_t)(0xA0U + other));
    s_gpio_write_results[reset] = PLATFORM_OK;
    TEST_CHECK(Lora_Init(retired) == LORA_INIT_OK);
    Lora_GetDebugSnapshot(retired, &after);
    TEST_CHECK(after.initialized == 1U && after.tx_queue_count == 0U && after.rx_queue_count == 0U);
    TEST_CHECK(Lora_ControlSubmit(retired, LORA_CONTROL_IRQ_CLEAR, 1000U, &age_ms) ==
               LORA_CONTROL_SUBMIT_OK);
}

int main(void)
{
    _Static_assert(PROJECT_SX1281_INSTANCE_COUNT == TEST_INSTANCE_COUNT,
        "multi-instance SX1281 Host fixture must expose two contexts");
    Test_ContextQueueAndIrqIsolation();
    Test_ReceiveHoldIsolation();
    Test_RoleCapacityIsolation();
    Test_DeactivateIsolation(0U, PLATFORM_OK);
    Test_DeactivateIsolation(1U, PLATFORM_OK);
    Test_DeactivateIsolation(0U, PLATFORM_IO_ERROR);
    Test_DeactivateIsolation(1U, PLATFORM_TIMEOUT);
    return Test_Finish("sx1281_multi_instance");
}
