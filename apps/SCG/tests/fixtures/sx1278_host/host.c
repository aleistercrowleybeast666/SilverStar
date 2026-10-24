#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sx1278_device.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "project_resources.h"
#include "silverstar_assert.h"
#include "sx1278_instance.h"
#include "ground_radio.h"

static uint8_t registers[128], fifo[256], gpio[96];
static uint32_t now_ms, spi_calls, gpio_calls, fail_spi;
static uint8_t fail_gpio = 255U, fail_timeout, bad_readback;
static uint8_t absent, resource_invalid, critical_depth;
static uint8_t race_bad_packet;
static uint8_t advance_irq_ms;
static uint8_t ignore_mode, advance_reset_low_ms, advance_reset_high_ms, advance_rx_mode_ms;
static uint32_t stop_start_spi;
static uint64_t time_epoch_us;
static uint32_t trap_count;
#define CHECK(x) do { if (!(x)) { (void)printf("FAIL %u: %s\n", (unsigned)__LINE__, #x); exit(1); } } while (0)

/* Test-only direct inclusion enables stored-state corruption injection. */
#include "sx1278_device.c"

static void Chip_Reset(void)
{
    (void)memset(registers, 0, sizeof(registers));
    registers[0x42] = (absent != 0U) ? 0xFFU : 0x12U;
    registers[0x01] = 0x01U;
    registers[0x31] = 0xC3U;
}

void SilverStarAssert_Check(uint8_t condition, SilverStarAssertModuleId module,
    const char *file, uint32_t line, SilverStarAssertReasonId reason)
{
    (void)module; (void)file; (void)line; (void)reason;
    if (condition == 0U)
    { CHECK(s_published.ready==0U); trap_count++; (void)puts("EXPECTED_INTERNAL_TRAP"); exit(90); }
}

PlatformCriticalState PlatformCritical_Enter(void) { critical_depth++; return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state)
{ (void)state; CHECK(critical_depth != 0U); critical_depth--; }
uint32_t PlatformTime_Ms(void) { return now_ms; }
uint64_t PlatformTime_Us(void) { return time_epoch_us + (uint64_t)now_ms * 1000ULL; }
uint8_t PlatformGpio_IrqConsume(PlatformGpioId id) { (void)id; return 0U; }

SystemDeviceResult ProjectSx1278Resources_Get(uint8_t instance, ProjectSx1278Resources *r)
{
    if (instance != 0U) { return SYSTEM_DEVICE_NOT_PRESENT; }
    *r = (ProjectSx1278Resources){PLATFORM_SPI_1, PLATFORM_GPIO_0, PLATFORM_GPIO_1,
        PLATFORM_GPIO_2, PLATFORM_TIME_1, PLATFORM_GPIO_3, PLATFORM_GPIO_4};
    if (resource_invalid != 0U) { r->tx_en = r->rx_en; }
    return SYSTEM_DEVICE_OK;
}

PlatformResult PlatformGpio_Write(PlatformGpioId id, uint8_t high)
{
    CHECK(critical_depth == 0U); CHECK(id < PLATFORM_GPIO_COUNT); gpio_calls++;
    if (id == fail_gpio) { fail_gpio = 255U; return PLATFORM_IO_ERROR; }
    if (id == PLATFORM_GPIO_1)
    {
        now_ms += (high == 0U) ? advance_reset_low_ms : advance_reset_high_ms;
        if (high == 0U) { advance_reset_low_ms=0U; } else { advance_reset_high_ms=0U; }
    }
    gpio[id] = high;
    if ((id == PLATFORM_GPIO_1) && (high == 0U)) { Chip_Reset(); }
    CHECK((gpio[3] == 0U) || (gpio[4] == 0U));
    return PLATFORM_OK;
}

PlatformResult PlatformSpi_Transfer(PlatformSpiId id, const uint8_t *tx,
    uint8_t *rx, uint16_t length, uint32_t timeout)
{
    uint16_t i;
    uint8_t address = (uint8_t)(tx[0] & 0x7FU);
    CHECK(critical_depth == 0U); CHECK(id == PLATFORM_SPI_1);
    CHECK(gpio[0] == 0U); CHECK(timeout == 2U);
    CHECK((length >= 2U) && (length <= 62U)); spi_calls++;
    if (spi_calls == stop_start_spi)
    { CHECK(Sx1278_Stop(0U)==Sx1278Result_Ok); CHECK(Sx1278_Start(0U)==Sx1278Result_Ok); stop_start_spi=0U; }
    if (tx[0] == 0x12U) { now_ms += advance_irq_ms; advance_irq_ms = 0U; }
    if (spi_calls == fail_spi) { return (fail_timeout != 0U) ? PLATFORM_TIMEOUT : PLATFORM_IO_ERROR; }
    rx[0] = 0U;
    for (i = 1U; i < length; i++)
    {
        uint8_t reg = (uint8_t)(address + i - 1U);
        if (address == 0U)
        {
            uint8_t ptr = registers[0x0D]++;
            if ((tx[0] & 0x80U) != 0U) { fifo[ptr] = tx[i]; }
            else { rx[i] = fifo[ptr]; }
        }
        else if ((tx[0] & 0x80U) != 0U)
        {
            if (reg == 0x12U) { registers[reg] &= (uint8_t)~tx[i]; }
            else
            {
                if ((reg == 1U) && (ignore_mode != 0U) && (tx[i] == ignore_mode)) { ignore_mode=0U; continue; }
                if ((reg == 1U) && (tx[i] == 0x8DU))
                { now_ms += advance_rx_mode_ms; advance_rx_mode_ms=0U; }
                if ((reg == 1U) && (registers[reg] == 0x8DU) &&
                    (tx[i] == 0x89U) && (race_bad_packet != 0U))
                { registers[0x12] |= 0x20U; race_bad_packet = 0U; }
                if ((reg == 0x01U) && (((registers[reg] ^ tx[i]) & 0x80U) != 0U))
                { CHECK((registers[reg] & 7U) == 0U); }
                registers[reg] = tx[i];
            }
        }
        else { rx[i] = (uint8_t)(registers[reg] ^ ((bad_readback == reg) ? 1U : 0U)); }
    }
    return PLATFORM_OK;
}

static void ProcessAt(uint32_t time)
{ now_ms = time; CHECK(Sx1278_Process(0U) == Sx1278Result_Ok); }

static void Boot(void)
{
    Sx1278Stats stats;
    Chip_Reset(); CHECK(Sx1278_Init(0U) == Sx1278Result_Ok);
    CHECK(Sx1278_Start(0U) == Sx1278Result_Ok);
    CHECK(spi_calls == 0U && gpio_calls == 0U);
    ProcessAt(0U); CHECK(gpio[1] == 0U);
    ProcessAt(2U); CHECK(gpio[1] == 1U);
    ProcessAt(7U); CHECK(spi_calls == 0U);
    ProcessAt(8U);
    CHECK(Sx1278_StatsGet(0U, &stats) == Sx1278Result_Ok && stats.ready != 0U);
    CHECK(registers[0x01] == 0x8DU && registers[0x06] == 0x6CU && registers[0x07] == 0x40U);
    CHECK(registers[0x09] == 0x8FU && registers[0x4D] == 0x84U);
    CHECK(registers[0x1D] == 0x72U && registers[0x1E] == 0x74U);
    CHECK(registers[0x26] == 4U && registers[0x40] == 0U);
    CHECK(registers[0x31] == 0x43U);
    CHECK(gpio[3] == 1U && gpio[4] == 0U && gpio[0] == 1U);
}

static void RxInject(uint8_t flags, uint8_t length, uint8_t crc)
{
    uint8_t i;
    registers[0x12] = flags; registers[0x13] = length;
    registers[0x10] = 192U; registers[0x1C] = crc;
    for (i = 0U; i < length; i++) { fifo[(uint8_t)(192U + i)] = i; }
}

static void ScenarioTx(void)
{
    uint8_t data[61] = {0x10U, 0x42U};
    uint32_t id, age;
    Boot(); CHECK(Sx1278_Send(0U, data, 61U, 1U, &id) == Sx1278Result_Ok);
    CHECK(Sx1278_ReceiptGet(0U, id, &age) == Sx1278Result_Busy);
    ProcessAt(157U); CHECK((registers[1] & 7U) == 5U);
    ProcessAt(158U); CHECK((registers[1] & 7U) == 3U);
    CHECK(gpio[3] == 0U && gpio[4] == 1U && registers[0x40] == 0x40U);
    CHECK(registers[0x22] == 61U && fifo[0] == 0x10U);
    registers[0x12] = 8U; ProcessAt(159U);
    CHECK(Sx1278_ReceiptGet(0U, id, &age) == Sx1278Result_Ok && age == 151U);
    CHECK(gpio[3] == 1U && gpio[4] == 0U);
}

static void ScenarioRx(void)
{
    uint8_t data[61]; uint16_t length;
    Boot(); RxInject(0x40U, 61U, 0x40U); ProcessAt(9U);
    CHECK(Sx1278_Receive(0U, data, 60U, &length) == Sx1278Result_Invalid && length == 0U);
    CHECK(Sx1278_Receive(0U, data, 61U, &length) == Sx1278Result_Ok && length == 61U);
    CHECK(data[0] == 0U && data[60] == 60U);
    CHECK(Sx1278_Receive(0U, data, 61U, &length) == Sx1278Result_Empty);
    RxInject(0x60U, 10U, 0x40U); ProcessAt(10U);
    RxInject(0x40U, 10U, 0U); ProcessAt(11U);
    RxInject(0x40U, 62U, 0x40U); ProcessAt(12U);
    CHECK(s_published.rx_crc_error == 2U && s_published.rx_dropped == 3U);
    CHECK(Sx1278_Receive(0U, data, 61U, &length) == Sx1278Result_Empty);
}

static void ScenarioTimeout(void)
{
    uint8_t data[2] = {1U, 2U}; uint32_t id, queued, age;
    Boot(); CHECK(Sx1278_Send(0U,data,2U,1U,&id) == Sx1278Result_Ok); ProcessAt(158U);
    CHECK(Sx1278_Send(0U,data,2U,1U,&queued) == Sx1278Result_Ok);
    now_ms=408U; registers[0x12]=8U; CHECK(Sx1278_Process(0U) == Sx1278Result_Timeout);
    CHECK(s_published.ready == 0U && gpio[1] == 0U && gpio[3] == 0U && gpio[4] == 0U);
    CHECK(Sx1278_ReceiptGet(0U,id,&age) == Sx1278Result_Timeout);
    CHECK(Sx1278_ReceiptGet(0U,queued,&age) == Sx1278Result_NotPresent);
    ProcessAt(1407U); CHECK(s_published.ready == 0U);
    ProcessAt(1408U); ProcessAt(1410U); ProcessAt(1416U);
    CHECK(s_published.ready == 1U && s_context.control.count == 0U);
    ProcessAt(1602U); CHECK((registers[1] & 7U) == 5U);
}

static void ScenarioFault(uint32_t nth, uint8_t timeout)
{
    Sx1278Result result;
    Boot(); fail_spi=spi_calls+nth; fail_timeout=timeout;
    now_ms=9U; RxInject(0x40U,10U,0x40U); result=Sx1278_Process(0U);
    CHECK(result != Sx1278Result_Ok); CHECK(gpio[0] == 1U);
    CHECK(s_published.ready == 0U && s_context.rx.count == 0U);
    CHECK(gpio[1] == 0U && gpio[3] == 0U && gpio[4] == 0U);
    ProcessAt(1009U); ProcessAt(1011U); ProcessAt(1017U); CHECK(s_published.ready != 0U);
}

int main(int argc, char **argv)
{
    uint8_t data[61]={1U}; uint32_t id,age; uint16_t length;
    CHECK(argc >= 2); (void)memset(gpio,0,sizeof(gpio));
    if (strcmp(argv[1],"tx")==0) { ScenarioTx(); }
    else if (strcmp(argv[1],"rx")==0) { ScenarioRx(); }
    else if (strcmp(argv[1],"crc_race")==0)
    {
        Boot(); RxInject(0x40U,10U,0x40U); race_bad_packet=1U; ProcessAt(9U);
        CHECK(s_published.rx_crc_error==1U && s_published.rx_ok==0U);
        CHECK(Sx1278_Receive(0U,data,61U,&length)==Sx1278Result_Empty);
    }
    else if (strcmp(argv[1],"timeout")==0) { ScenarioTimeout(); }
    else if (strcmp(argv[1],"deadline_during_spi")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok); ProcessAt(158U);
        registers[0x12]=8U; advance_irq_ms=2U; now_ms=407U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Timeout);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Timeout && s_published.tx_ok==0U);
    }
    else if (strcmp(argv[1],"stop_restart")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        RxInject(0x40U,1U,0x40U); ProcessAt(9U);
        CHECK(Sx1278_Stop(0U)==Sx1278Result_Ok && Sx1278_Start(0U)==Sx1278Result_Ok);
        ProcessAt(10U); CHECK(s_context.state==Sx1278State_Stopped && s_published.ready==0U);
        CHECK(s_context.control.count==0U && s_context.rx.count==0U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_NotPresent);
        ProcessAt(11U); ProcessAt(13U); ProcessAt(19U); CHECK(s_published.ready==1U);
    }
    else if (strcmp(argv[1],"stop_during_config")==0)
    {
        CHECK(Sx1278_Init(0U)==Sx1278Result_Ok && Sx1278_Start(0U)==Sx1278Result_Ok);
        ProcessAt(0U); ProcessAt(2U); stop_start_spi=5U; ProcessAt(8U);
        CHECK(s_published.ready==0U && gpio[1]==0U && s_context.state==Sx1278State_Stopped);
    }
    else if (strcmp(argv[1],"stop_during_tx_done")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok); ProcessAt(158U);
        registers[0x12]=8U; stop_start_spi=spi_calls+1U; ProcessAt(159U);
        CHECK(s_published.ready==0U && s_published.tx_ok==0U && s_context.state==Sx1278State_Stopped);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Offline);
    }
    else if (strcmp(argv[1],"stop_receive")==0)
    {
        Boot(); RxInject(0x40U,1U,0x40U); ProcessAt(9U); CHECK(Sx1278_Stop(0U)==Sx1278Result_Ok);
        CHECK(Sx1278_Receive(0U,data,61U,&length)==Sx1278Result_Offline && length==0U);
    }
    else if (strcmp(argv[1],"stop_gpio_error")==0)
    {
        SystemDeviceIoDiagnostics diagnostics;
        Boot(); CHECK(Sx1278_Stop(0U)==Sx1278Result_Ok); fail_gpio=PLATFORM_GPIO_1;
        now_ms=9U; CHECK(Sx1278_Process(0U)==Sx1278Result_Io && s_published.ready==0U);
        CHECK(Sx1278TelemetryInstance_IoDiagnosticsGet(0U,&diagnostics)==SYSTEM_DEVICE_OK);
        CHECK((diagnostics.supported_mask & SYSTEM_DEVICE_IO_VALID_SPI_ERRORS)==0U);
        CHECK((diagnostics.valid_mask & SYSTEM_DEVICE_IO_VALID_TRANSPORT_ERRORS)!=0U && diagnostics.transport_error_count>0U);
    }
    else if (strcmp(argv[1],"adapter_stop_pending")==0)
    {
        Boot(); CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_BUSY);
        now_ms=9U; CHECK(Sx1278_Process(0U)==Sx1278Result_Offline);
        CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_OK);
        CHECK(gpio[1]==0U && gpio[3]==0U && gpio[4]==0U);
    }
    else if (strcmp(argv[1],"adapter_stop_before_start")==0)
    {
        CHECK(Sx1278_Init(0U)==Sx1278Result_Ok);
        CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_BUSY);
        CHECK(Sx1278_Process(0U)==Sx1278Result_Offline);
        CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_OK && gpio[1]==0U);
    }
    else if (strcmp(argv[1],"stop_status_error")==0)
    {
        Boot(); CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_BUSY);
        fail_gpio=PLATFORM_GPIO_1; now_ms=9U; CHECK(Sx1278_Process(0U)==Sx1278Result_Io);
        CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_IO_ERROR);
        now_ms=10U; CHECK(Sx1278_Process(0U)==Sx1278Result_Offline);
        CHECK(Sx1278TelemetryInstance_Stop(0U)==SYSTEM_DEVICE_OK);
    }
    else if (strcmp(argv[1],"ignored_standby")==0)
    {
        Boot(); RxInject(0x40U,1U,0x40U); ignore_mode=0x89U; now_ms=9U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Io && s_published.rx_ok==0U && s_published.ready==0U);
    }
    else if (strcmp(argv[1],"unexpected_reset_rx")==0)
    {
        Boot(); Chip_Reset(); now_ms=9U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Io && s_published.ready==0U);
    }
    else if (strcmp(argv[1],"unexpected_mode_tx")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok); ProcessAt(158U);
        registers[0x01]=0x89U; now_ms=159U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Io && s_published.ready==0U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Io);
    }
    else if (strcmp(argv[1],"autonomous_tx_done")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok); ProcessAt(158U);
        registers[0x01]=0x89U; registers[0x12]=8U; ProcessAt(159U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Ok && s_published.tx_ok==1U);
    }
    else if (strcmp(argv[1],"health_time_epoch")==0)
    {
        SystemTelemetryHealth health; Boot(); time_epoch_us=4294967296000ULL;
        RxInject(0x40U,1U,0x40U); ProcessAt(10U);
        CHECK(Sx1278TelemetryInstance_HealthGet(0U,&health)==SYSTEM_DEVICE_OK);
        CHECK(health.last_receive_timestamp_us==PlatformTime_Us());
    }
    else if (strcmp(argv[1],"ignored_rx_entry")==0)
    {
        CHECK(Sx1278_Init(0U)==Sx1278Result_Ok && Sx1278_Start(0U)==Sx1278Result_Ok);
        ProcessAt(0U); ProcessAt(2U); ignore_mode=0x8DU; now_ms=8U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Io && s_published.ready==0U);
    }
    else if (strcmp(argv[1],"ignored_tx_entry")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        ignore_mode=0x8BU; now_ms=158U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Io && s_published.ready==0U);
    }
    else if (strcmp(argv[1],"reset_timing")==0)
    {
        CHECK(Sx1278_Init(0U)==Sx1278Result_Ok && Sx1278_Start(0U)==Sx1278Result_Ok);
        advance_reset_low_ms=4U; ProcessAt(0U); ProcessAt(5U); CHECK(gpio[1]==0U);
        advance_reset_high_ms=4U; ProcessAt(6U); CHECK(now_ms==10U && gpio[1]==1U);
        ProcessAt(15U); CHECK(spi_calls==0U); ProcessAt(16U); CHECK(s_published.ready==1U);
    }
    else if (strcmp(argv[1],"rx_window_clock")==0)
    {
        advance_rx_mode_ms=20U; Boot(); CHECK(now_ms==28U);
        CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        ProcessAt(158U); CHECK(s_context.state==Sx1278State_Rx);
        ProcessAt(178U); CHECK(s_context.state==Sx1278State_Tx);
    }
    else if (strcmp(argv[1],"queue_nonterminal_irq")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        registers[0x12]=0x10U; now_ms=1008U;
        CHECK(Sx1278_Process(0U)==Sx1278Result_Timeout && s_published.ready==0U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Timeout);
    }
    else if (strcmp(argv[1],"wanted_corrupt")==0)
    { Boot(); s_context.wanted=2U; (void)Sx1278_Process(0U); CHECK(0); }
    else if (strcmp(argv[1],"lifecycle_corrupt")==0)
    { Boot(); s_context.tx.id=55U; (void)Sx1278_Process(0U); CHECK(0); }
    else if (strcmp(argv[1],"negative_state_corrupt")==0)
    { Boot(); s_context.state=(Sx1278State)-1; (void)Sx1278_Process(0U); CHECK(0); }
    else if (strcmp(argv[1],"receipt_corrupt")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok); ProcessAt(158U);
        s_context.receipt_next=4U; registers[0x12]=8U; now_ms=159U;
        (void)Sx1278_Process(0U); CHECK(0);
    }
    else if (strcmp(argv[1],"rx_length_corrupt")==0)
    {
        Boot(); RxInject(0x40U,1U,0x40U); ProcessAt(9U);
        s_context.rx.frames[s_context.rx.head].length=62U;
        (void)Sx1278_Receive(0U,data,61U,&length); CHECK(0);
    }
    else if (strcmp(argv[1],"tx_length_corrupt")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,0U,&id)==Sx1278Result_Ok);
        s_context.data.frames[s_context.data.head].length=62U;
        now_ms=158U; (void)Sx1278_Process(0U); CHECK(0);
    }
    else if (strcmp(argv[1],"spi_fault")==0) { CHECK(argc==4); ScenarioFault((uint32_t)atoi(argv[2]),(uint8_t)atoi(argv[3])); }
    else if (strcmp(argv[1],"absent")==0 || strcmp(argv[1],"readback")==0)
    {
        absent=(uint8_t)(strcmp(argv[1],"absent")==0); bad_readback=(absent!=0U)?0U:0x1DU;
        CHECK(Sx1278_Init(0U)==Sx1278Result_Ok && Sx1278_Start(0U)==Sx1278Result_Ok);
        ProcessAt(0U); ProcessAt(2U); now_ms=8U; CHECK(Sx1278_Process(0U)!=Sx1278Result_Ok);
        CHECK(s_published.ready==0U && gpio[1]==0U);
    }
    else if (strcmp(argv[1],"boundaries")==0)
    {
        Boot(); CHECK(Sx1278_Send(1U,data,1U,0U,&id)==Sx1278Result_Invalid);
        CHECK(Sx1278_Send(0U,data,62U,0U,&id)==Sx1278Result_Invalid);
        CHECK(Sx1278_Send(0U,NULL,1U,0U,&id)==Sx1278Result_Invalid);
        CHECK(Sx1278_Send(0U,data,1U,2U,&id)==Sx1278Result_Invalid);
        CHECK(Sx1278_Receive(0U,data,61U,NULL)==Sx1278Result_Invalid);
        CHECK(Sx1278_ReceiptGet(0U,0U,&age)==Sx1278Result_Invalid);
        CHECK(Sx1278_Send(0U,data,1U,0U,&id)==Sx1278Result_Ok);
        CHECK(Sx1278_Send(0U,data,1U,0U,&id)==Sx1278Result_Ok);
        CHECK(Sx1278_Send(0U,data,1U,0U,&id)==Sx1278Result_Busy);
        CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        CHECK(Sx1278_Stop(0U)==Sx1278Result_Ok); CHECK(s_published.ready==0U);
        CHECK(Sx1278_Send(0U,data,1U,0U,&id)==Sx1278Result_Offline);
        CHECK(Sx1278_Process(0U)==Sx1278Result_Offline && gpio[1]==0U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_NotPresent);
    }
    else if (strcmp(argv[1],"gpio_fault")==0)
    {
        Boot(); fail_gpio=0U; now_ms=9U; CHECK(Sx1278_Process(0U)==Sx1278Result_Io);
        CHECK(s_published.ready==0U && gpio[0]==1U);
    }
    else if (strcmp(argv[1],"queue_expiry")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,0U,&id)==Sx1278Result_Ok);
        CHECK(Sx1278_Send(0U,data,1U,1U,NULL)==Sx1278Result_Ok);
        now_ms=1008U; CHECK(Sx1278_Process(0U)==Sx1278Result_Timeout);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Timeout);
        CHECK(s_published.tx_timeout==1U && s_published.bus_timeout==0U);
    }
    else if (strcmp(argv[1],"continuous_rx")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        RxInject(0x40U,1U,0x40U); ProcessAt(102U);
        RxInject(0x40U,1U,0x40U); ProcessAt(158U);
        CHECK(s_context.state==Sx1278State_Tx && gpio[4]==1U);
    }
    else if (strcmp(argv[1],"tx_spi_fault")==0)
    {
        CHECK(argc==4); Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        fail_spi=spi_calls+(uint32_t)atoi(argv[2]); fail_timeout=(uint8_t)atoi(argv[3]);
        now_ms=158U; CHECK(Sx1278_Process(0U)!=Sx1278Result_Ok);
        CHECK(s_published.ready==0U && gpio[1]==0U && gpio[0]==1U && gpio[4]==0U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)!=Sx1278Result_Ok);
    }
    else if (strcmp(argv[1],"rx_tx_spi_fault")==0)
    {
        CHECK(argc==3); Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok);
        RxInject(0x40U,1U,0x40U); fail_spi=spi_calls+(uint32_t)atoi(argv[2]);
        now_ms=158U; CHECK(Sx1278_Process(0U)!=Sx1278Result_Ok);
        CHECK(s_published.ready==0U && gpio[1]==0U && gpio[4]==0U);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)!=Sx1278Result_Ok);
    }
    else if (strcmp(argv[1],"init_spi_fault")==0)
    {
        CHECK(argc==3); CHECK(Sx1278_Init(0U)==Sx1278Result_Ok);
        CHECK(Sx1278_Start(0U)==Sx1278Result_Ok); ProcessAt(0U); ProcessAt(2U);
        fail_spi=(uint32_t)atoi(argv[2]); now_ms=8U;
        CHECK(Sx1278_Process(0U)!=Sx1278Result_Ok);
        CHECK(s_published.ready==0U && gpio[1]==0U && gpio[0]==1U && gpio[4]==0U);
    }
    else if (strcmp(argv[1],"conflicting_irq")==0)
    {
        Boot(); CHECK(Sx1278_Send(0U,data,1U,1U,&id)==Sx1278Result_Ok); ProcessAt(158U);
        registers[0x12]=0x48U; now_ms=159U; CHECK(Sx1278_Process(0U)==Sx1278Result_Io);
        CHECK(Sx1278_ReceiptGet(0U,id,&age)==Sx1278Result_Io && s_published.tx_ok==0U);
    }
    else if (strcmp(argv[1],"chip_bounds")==0)
    {
        Sx1278ChipBus bus={PLATFORM_SPI_1,PLATFORM_GPIO_0};
        CHECK(Sx1278Chip_Read(&bus,0x7FU,data,2U)==Sx1278Result_Invalid);
        CHECK(Sx1278Chip_Read(&bus,0U,data,62U)==Sx1278Result_Invalid);
        CHECK(Sx1278Chip_Write(&bus,0x80U,data,1U)==Sx1278Result_Invalid);
        CHECK(spi_calls==0U && gpio_calls==0U);
    }
    else if (strcmp(argv[1],"resources")==0)
    { resource_invalid=1U; CHECK(Sx1278_Init(0U)==Sx1278Result_Invalid && gpio_calls==0U); }
    else if (strcmp(argv[1],"wrap")==0)
    { Boot(); s_context.state=Sx1278State_Recovery; s_context.since_ms=UINT32_MAX-500U;
      s_context.stats.ready=0U; ProcessAt(498U); CHECK(s_context.state==Sx1278State_Recovery);
      ProcessAt(499U); CHECK(s_context.state==Sx1278State_ResetLow); }
    else if (strcmp(argv[1],"queue_corrupt")==0)
    { Boot(); s_context.data.count=3U; (void)Sx1278_Send(0U,data,1U,0U,&id); CHECK(0); }
    else if (strcmp(argv[1],"state_corrupt")==0)
    { Boot(); s_context.state=(Sx1278State)99; (void)Sx1278_Process(0U); CHECK(0); }
    else if (strcmp(argv[1],"adapter")==0)
    {
        SystemTelemetryHealth health; uint32_t mask; Boot();
        CHECK(Sx1278TelemetryInstance_CapabilitiesGet(0U,&mask)==SYSTEM_DEVICE_OK);
        CHECK((mask & (SYSTEM_TELEM_CAP_RSSI|SYSTEM_TELEM_CAP_SNR))==0U);
        CHECK(Sx1278TelemetryInstance_HealthGet(0U,&health)==SYSTEM_DEVICE_OK && health.online==0U);
        CHECK(Sx1278TelemetryInstance_Receive(0U,data,61U,&length)==SYSTEM_DEVICE_NOT_READY);
    }
    else if (strcmp(argv[1],"ground_adapter")==0)
    {
        GroundRadioStats stats; Boot(); CHECK(GroundRadio_Init()==GROUND_RADIO_OK);
        CHECK(GroundRadio_MetricsSupportedGet()==0U);
        CHECK(GroundRadio_TxEnqueue(data,61U)==GROUND_RADIO_OK);
        ProcessAt(158U); registers[0x12]=8U; GroundRadio_Process();
        GroundRadio_StatsGet(&stats); CHECK(stats.tx_ok==1U);
    }
    else { CHECK(0); }
    CHECK(trap_count==0U); CHECK(critical_depth==0U); (void)puts("PASS"); return 0;
}
