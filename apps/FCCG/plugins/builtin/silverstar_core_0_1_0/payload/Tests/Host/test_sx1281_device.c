#include <stdint.h>
#include <string.h>

#include "project_resources.h"
#include "platform_critical.h"
#include "platform_gpio.h"
#include "platform_time.h"
#include "sx1280.h"
#include "sx1281_bus.h"
#include "sx1281_device.h"
#include "test_common.h"

static uint32_t s_tick_ms;
static uint32_t s_irq_get_count;
static uint32_t s_packet_type_get_count;
static uint32_t s_rssi_get_count;
static uint32_t s_irq_clear_count;
static uint32_t s_set_rx_count;
static uint16_t s_raw_irq;
static uint8_t s_dio1_pending;

void SX1280Init(uint8_t instance) { (void)instance; }

RadioStatus_t SX1280GetStatus(uint8_t instance)
{
    RadioStatus_t status;

    (void)instance;
    status.Value = 0x20U;
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
{
    (void)instance;
    (void)tx;
    (void)rx;
}
void SX1280SetTxParams(
    uint8_t instance, int8_t power, RadioRampTimes_t ramp)
{
    (void)instance;
    (void)power;
    (void)ramp;
}
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
{
    (void)instance;
    (void)timeout;
    s_set_rx_count++;
}
uint16_t SX1280GetIrqStatus(uint8_t instance)
{
    (void)instance;
    s_irq_get_count++;
    return s_raw_irq;
}
void SX1280ClearIrqStatus(uint8_t instance, uint16_t irq)
{
    (void)instance;
    (void)irq;
    s_irq_clear_count++;
    s_raw_irq = 0U;
}
RadioPacketTypes_t SX1280GetPacketType(uint8_t instance)
{
    (void)instance;
    s_packet_type_get_count++;
    return PACKET_TYPE_LORA;
}
int8_t SX1280GetRssiInst(uint8_t instance)
{
    (void)instance;
    s_rssi_get_count++;
    return -60;
}
uint8_t SX1280GetPayload(
    uint8_t instance, uint8_t *payload, uint8_t *size, uint8_t maximum)
{
    (void)instance;
    (void)payload;
    (void)size;
    (void)maximum;
    return 1U;
}
void SX1280GetPacketStatus(uint8_t instance, PacketStatus_t *status)
{
    (void)instance;
    if (status != NULL) { (void)memset(status, 0, sizeof(*status)); }
}
void SX1280SendPayload(
    uint8_t instance, uint8_t *payload, uint8_t size, TickTime_t timeout)
{
    (void)instance;
    (void)payload;
    (void)size;
    (void)timeout;
}

void Sx1281Bus_Init(uint8_t instance) { (void)instance; }
void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{
    (void)instance;
    if (status != NULL) { (void)memset(status, 0, sizeof(*status)); }
}
PlatformGpioId Sx1281Bus_NssGet(uint8_t instance)
{
    ProjectSx1281Resources resources;
    return (ProjectSx1281Resources_Get(instance, &resources) ==
            SYSTEM_DEVICE_OK) ? resources.nss : PLATFORM_GPIO_COUNT;
}
PlatformGpioId Sx1281Bus_ResetGet(uint8_t instance)
{
    ProjectSx1281Resources resources;
    return (ProjectSx1281Resources_Get(instance, &resources) ==
            SYSTEM_DEVICE_OK) ? resources.reset : PLATFORM_GPIO_COUNT;
}
PlatformGpioId Sx1281Bus_BusyGet(uint8_t instance)
{
    ProjectSx1281Resources resources;
    return (ProjectSx1281Resources_Get(instance, &resources) ==
            SYSTEM_DEVICE_OK) ? resources.busy : PLATFORM_GPIO_COUNT;
}
PlatformGpioId Sx1281Bus_Dio1Get(uint8_t instance)
{
    ProjectSx1281Resources resources;
    return (ProjectSx1281Resources_Get(instance, &resources) ==
            SYSTEM_DEVICE_OK) ? resources.dio1 : PLATFORM_GPIO_COUNT;
}

uint32_t PlatformTime_Ms(void) { return s_tick_ms; }
uint64_t PlatformTime_Us(void) { return (uint64_t)s_tick_ms * 1000ULL; }
void PlatformTime_DelayMs(uint32_t delay_ms) { s_tick_ms += delay_ms; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }

PlatformResult PlatformGpio_Read(PlatformGpioId id, uint8_t *logical_high)
{
    if ((id >= PLATFORM_GPIO_COUNT) || (logical_high == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *logical_high = 0U;
    return PLATFORM_OK;
}

uint8_t PlatformGpio_IrqConsume(PlatformGpioId id)
{
    uint8_t pending;

    if (id != PLATFORM_GPIO_3) { return 0U; }
    pending = s_dio1_pending;
    s_dio1_pending = 0U;
    return pending;
}

#define Lora_Init() Lora_Init(0U)
#define Lora_StartRx() Lora_StartRx(0U)
#define Lora_Process() Lora_Process(0U)
#define Lora_GetDiagSnapshot(snapshot) Lora_GetDiagSnapshot(0U, (snapshot))
#define Lora_ChipStatusGet(status) Lora_ChipStatusGet(0U, (status))
#define Lora_GetStats(stats) Lora_GetStats(0U, (stats))
#define Lora_ControlSubmit(operation, timeout_ms, transaction_id) \
    Lora_ControlSubmit(0U, (operation), (timeout_ms), (transaction_id))
#define Lora_ControlResultGet(transaction_id, result) \
    Lora_ControlResultGet(0U, (transaction_id), (result))
#define Lora_IrqClear(raw_before) Lora_IrqClear(0U, (raw_before))

static void Test_CachedDiagnosticsDoNotReadSpi(void)
{
    LoraDiagSnapshot snapshot;
    LoraChipStatus chip;
    uint32_t irq_count;
    uint32_t packet_count;
    uint32_t rssi_count;

    TEST_CHECK(Lora_Init() == LORA_INIT_OK);
    Lora_StartRx();
    s_tick_ms = 100U;
    Lora_Process();
    irq_count = s_irq_get_count;
    packet_count = s_packet_type_get_count;
    rssi_count = s_rssi_get_count;
    Lora_GetDiagSnapshot(&snapshot);
    TEST_CHECK(Lora_ChipStatusGet(&chip) == LORA_DIAG_RESULT_OK);
    TEST_CHECK(s_irq_get_count == irq_count);
    TEST_CHECK(s_packet_type_get_count == packet_count);
    TEST_CHECK(s_rssi_get_count == rssi_count);
    TEST_CHECK(snapshot.rssi_inst_valid != 0U);
    TEST_CHECK(chip.verified != 0U);
}

static void Test_DioEventDrivesDirectIrqProcessing(void)
{
    LoraStats stats;
    uint32_t irq_count = s_irq_get_count;

    s_raw_irq = IRQ_RX_TX_TIMEOUT;
    s_dio1_pending = 1U;
    Lora_Process();
    Lora_GetStats(&stats);
    TEST_CHECK(s_irq_get_count == (irq_count + 1U));
    TEST_CHECK(s_irq_clear_count != 0U);
    TEST_CHECK(stats.rx_timeout_irq_count != 0U);
}

static void Test_OwnerControlTransaction(void)
{
    LoraControlResult result;
    uint32_t first_id;
    uint32_t second_id;
    uint32_t set_rx_before;

    TEST_CHECK(Lora_ControlSubmit(LORA_CONTROL_IRQ_CLEAR, 20U,
                                  &first_id) == LORA_CONTROL_SUBMIT_OK);
    TEST_CHECK(Lora_ControlSubmit(LORA_CONTROL_FORCE_RX_CONTINUOUS, 20U,
                                  &second_id) == LORA_CONTROL_SUBMIT_BUSY);
    s_raw_irq = IRQ_RX_DONE;
    Lora_Process();
    TEST_CHECK(Lora_ControlResultGet(first_id, &result) ==
               LORA_CONTROL_GET_COMPLETE);
    TEST_CHECK(result.result == LORA_DIAG_RESULT_OK);
    TEST_CHECK(result.raw_irq_before == IRQ_RX_DONE);
    TEST_CHECK(s_irq_clear_count != 0U);

    TEST_CHECK(Lora_IrqClear(NULL) == LORA_DIAG_RESULT_QUEUED);
    Lora_Process();
    TEST_CHECK(Lora_ControlSubmit(LORA_CONTROL_IRQ_CLEAR, 20U,
                                  &first_id) == LORA_CONTROL_SUBMIT_OK);
    Lora_Process();
    TEST_CHECK(Lora_ControlResultGet(first_id, &result) ==
               LORA_CONTROL_GET_COMPLETE);

    set_rx_before = s_set_rx_count;
    TEST_CHECK(Lora_ControlSubmit(LORA_CONTROL_FORCE_RX_CONTINUOUS, 10U,
                                  &first_id) == LORA_CONTROL_SUBMIT_OK);
    s_tick_ms += 11U;
    TEST_CHECK(Lora_ControlResultGet(first_id, &result) ==
               LORA_CONTROL_GET_COMPLETE);
    TEST_CHECK(result.result == LORA_DIAG_RESULT_TIMEOUT);
    TEST_CHECK(s_set_rx_count == set_rx_before);

    TEST_CHECK(Lora_ControlSubmit(LORA_CONTROL_FORCE_RX_CONTINUOUS, 20U,
                                  &second_id) == LORA_CONTROL_SUBMIT_OK);
    Lora_Process();
    TEST_CHECK(Lora_ControlResultGet(second_id, &result) ==
               LORA_CONTROL_GET_COMPLETE);
    TEST_CHECK(result.result == LORA_DIAG_RESULT_OK);
    TEST_CHECK(s_set_rx_count > set_rx_before);
}

int main(void)
{
    Test_CachedDiagnosticsDoNotReadSpi();
    Test_DioEventDrivesDirectIrqProcessing();
    Test_OwnerControlTransaction();
    return Test_Finish("sx1281_device");
}
