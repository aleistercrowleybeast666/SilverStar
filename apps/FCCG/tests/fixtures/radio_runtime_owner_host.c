/* Actual generated startup, SX driver and adapter; only physical ports and
 * unrelated startup devices are stubs. The hook models task preemption. */
#include <stdio.h>
#include <stdlib.h>
#include "silverstar_assert.h"
#include <string.h>
#define main Previous_StartupMain
#define SystemTelemetry_Init Previous_TelemetryInit
#define SystemTelemetry_Start Previous_TelemetryStart
#define SystemTelemetry_Process Previous_TelemetryProcess
#define SystemTelemetry_HealthGet Previous_TelemetryHealth
#include "test_system_startup.c"
#undef main
#undef SystemTelemetry_Init
#undef SystemTelemetry_Start
#undef SystemTelemetry_Process
#undef SystemTelemetry_HealthGet
#define TEST_SX1281_PORTS_ONLY 1
#define SX1280GetIrqStatus Previous_IrqRead
#define SX1280GetStatus Previous_ModeRead
#define SX1280SetRx Previous_SetRx
#define Sx1281Bus_Init Previous_BusInit
#define Sx1281Bus_StatusGet Previous_BusStatus
#include "test_sx1281_device.c"
#undef SX1280GetIrqStatus
#undef SX1280GetStatus
#undef SX1280SetRx
#undef Sx1281Bus_Init
#undef Sx1281Bus_StatusGet
#include "sx1281_instance.h"
static Sx1281BusStatus s_runtime_bus;
static uint8_t s_runtime_fault, s_preempt_armed, s_fault_on_rx_start;
static unsigned int s_process_depth, s_max_process_depth, s_preempt_count;
void Sx1281Bus_Init(uint8_t instance)
{ (void)instance; memset(&s_runtime_bus, 0, sizeof(s_runtime_bus)); }
void Sx1281Bus_StatusGet(uint8_t instance, Sx1281BusStatus *status)
{ (void)instance; *status = s_runtime_bus; }
static void Runtime_BusResult(void)
{
    s_runtime_bus.last_result = SX1281_BUS_OK;
    if (s_runtime_fault == 1U)
    { s_runtime_bus.spi_error_count++; s_runtime_bus.last_result = SX1281_BUS_SPI_ERROR; }
    else if (s_runtime_fault == 2U)
    { s_runtime_bus.spi_timeout_count++; s_runtime_bus.last_result = SX1281_BUS_SPI_TIMEOUT; }
    else if (s_runtime_fault == 3U)
    { s_runtime_bus.busy_timeout_count++; s_runtime_bus.last_result = SX1281_BUS_BUSY_TIMEOUT; }
    if ((s_runtime_fault != 0U) && (s_runtime_bus.first_failure_valid == 0U))
    {
        s_runtime_bus.first_failure_valid = 1U;
        s_runtime_bus.first_failure_result = s_runtime_bus.last_result;
        s_runtime_bus.first_failure_at_ms = s_tick_ms;
    }
}
void SX1280SetRx(uint8_t instance, TickTime_t timeout)
{
    Previous_SetRx(instance, timeout);
    if (s_fault_on_rx_start != 0U)
    {
        s_fault_on_rx_start = 0U;
        s_runtime_bus.spi_timeout_count++;
        s_runtime_bus.last_result = SX1281_BUS_SPI_TIMEOUT;
    }
}
RadioStatus_t SX1280GetStatus(uint8_t instance)
{ (void)instance; Runtime_BusResult(); RadioStatus_t status; status.Value = 0x40U; return status; }
uint16_t SX1280GetIrqStatus(uint8_t instance)
{
    (void)instance;
    if (s_preempt_armed != 0U)
    {
        s_preempt_armed = 0U; s_preempt_count++;
        /* DeviceTask preempts TelemetryTask inside the physical read. It
         * executes the real startup WaitConfig entry, including its real
         * transport Process call on the unfixed source. */
        SystemStartup_ProcessDevices();
        LoraDebugSnapshot snapshot; Lora_GetDebugSnapshot(0U, &snapshot);
        fprintf(stderr, "PREEMPT_RETURN init=%u state=%u rx_error=%lu depth=%u\n",
            snapshot.initialized, (unsigned int)snapshot.stats.radio_state,
            (unsigned long)snapshot.stats.rx_error, s_max_process_depth);
    }
    Runtime_BusResult(); return 0U;
}
SystemDeviceResult SystemTelemetry_Init(void) { return Sx1281TelemetryInstance_Init(0U); }
SystemDeviceResult SystemTelemetry_Start(void) { return Sx1281TelemetryInstance_Start(0U); }
SystemDeviceResult SystemTelemetry_HealthGet(SystemTelemetryHealth *health)
{ return Sx1281TelemetryInstance_HealthGet(0U, health); }
void SystemTelemetry_Process(void)
{
    s_process_depth++; if (s_process_depth > s_max_process_depth) { s_max_process_depth = s_process_depth; }
    (void)Sx1281TelemetryInstance_Process(0U); s_process_depth--;
}
/* Only the terminal trap is intercepted on Host, after the real assertion
 * implementation has latched its record. This is not MCU recovery. */
static _Noreturn void Runtime_Trap(void)
{
    SilverStarAssertFaultRecord record;
    if (SilverStarAssert_FaultRecordGet(&record) == 0U) { exit(91); }
    fprintf(stderr, "ASSERT file=%s line=%lu module=%u reason=%u active=%u\n",
        record.file_name, (unsigned long)record.line, (unsigned int)record.module_id,
        (unsigned int)record.reason_id, record.active);
    exit(90);
}
#define __builtin_trap() Runtime_Trap()
#include "silverstar_assert.c"
#undef __builtin_trap
#include "sx1281_device.c"
#undef s_tx_count
#undef s_rx_count
#include "system_startup.c"
int main(int argc, char **argv)
{
    uint8_t history_success;
    uint8_t history_timeout;
    uint32_t old_tx_id = 0U;
    uint32_t new_tx_id = 0U;
    uint32_t receipt_age_ms = 0U;
    const uint8_t receipt_data[1] = {0x42U};
    SystemTelemetryHealth history_initial_health = {0};
    SystemTelemetryHealth history_fault_health = {0};
    if (argc != 2) { return 2; }
    history_success = (uint8_t)(strcmp(argv[1], "history_success") == 0);
    history_timeout = (uint8_t)(strcmp(argv[1], "history_timeout") == 0);
    s_runtime_fault = 0U; s_preempt_armed = 0U; s_fault_on_rx_start = 0U;
    Test_Reset(); s_async_config = 1U; s_async_busy_ticks = 900U; s_precise_time = 1U;
    s_tick_ms = 0U; s_now_us = 0ULL;
    TEST_CHECK(SystemStartup_Run() == SYSTEM_STARTUP_OK);
    for (unsigned int step = 0U; step < 6U; step++) { SystemStartup_ProcessDevices(); }
    TEST_CHECK(s_startup_phase == SystemStartupPhase_WaitConfig);
    TEST_CHECK(s_contexts[0].inited == 1U);
    if ((history_success != 0U) || (history_timeout != 0U))
    {
        s_contexts[0].stats.tx_ok = history_success != 0U ? 299U : 0U;
        s_contexts[0].stats.tx_timeout = history_timeout != 0U ? 1U : 0U;
        s_tick_ms = 250U; s_now_us = 250000ULL;
        SystemTelemetry_Process();
        SystemTelemetryHealth before_fault;
        TEST_CHECK(SystemTelemetry_HealthGet(&before_fault) == SYSTEM_DEVICE_OK);
        TEST_CHECK(before_fault.transmit_packet_count == s_contexts[0].stats.tx_ok);
        TEST_CHECK(before_fault.transmit_timeout_count == s_contexts[0].stats.tx_timeout);
        history_initial_health = before_fault;
        TEST_CHECK(Lora_TxEnqueueTracked(0U, receipt_data,
            sizeof(receipt_data), &old_tx_id) == LORA_TX_ENQUEUE_OK);
        TEST_CHECK(old_tx_id != 0U);
    }
    s_tick_ms = 300U; s_now_us = 300000ULL;
    if ((history_success != 0U) || (history_timeout != 0U))
    {
        s_runtime_bus.spi_timeout_count++;
        s_runtime_bus.last_result = SX1281_BUS_SPI_TIMEOUT;
        s_runtime_bus.first_failure_valid = 1U;
        s_runtime_bus.first_failure_result = SX1281_BUS_SPI_TIMEOUT;
        s_runtime_bus.first_failure_at_ms = s_tick_ms;
        Lora_RadioFault(0U, 1U);
    }
    else
    {
        s_runtime_fault = strcmp(argv[1], "busy") == 0 ? 3U :
            strcmp(argv[1], "timeout") == 0 ? 2U : 1U;
        s_preempt_armed = 1U;
    }
    SystemTelemetry_Process();
    TEST_CHECK(SilverStarAssert_FaultedGet() == 0U);
    TEST_CHECK(s_preempt_count == ((history_success != 0U) ||
        (history_timeout != 0U) ? 0U : 1U));
    TEST_CHECK(s_max_process_depth == 1U);
    TEST_CHECK(s_contexts[0].inited == 0U);
    TEST_CHECK(s_contexts[0].stats.radio_state == LORA_RADIO_STATE_NOT_INIT);
    TEST_CHECK(s_contexts[0].stats.rx_error == 1U);
    SystemTelemetryHealth health;
    TEST_CHECK(SystemTelemetry_HealthGet(&health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(health.initialized == 0U && health.started == 0U && health.healthy == 0U && health.online == 0U);
    if ((history_success != 0U) || (history_timeout != 0U))
    {
        history_fault_health = health;
        TEST_CHECK(health.transmit_packet_count == (history_success != 0U ? 299U : 0U));
        TEST_CHECK(health.transmit_timeout_count >= (history_timeout != 0U ? 1U : 0U));
        TEST_CHECK(Lora_TxResultGet(0U, old_tx_id, &receipt_age_ms) ==
            LoraTxQueryResult_TimedOut);
    }
    Sx1281BusStatus before = s_runtime_bus;
    for (unsigned int step = 0U; step < 8U; step++) { SystemTelemetry_Process(); SystemStartup_ProcessDevices(); }
    TEST_CHECK(memcmp(&before, &s_runtime_bus, sizeof(before)) == 0);
    if (strcmp(argv[1], "exhaust") == 0)
    {
        for (unsigned int attempt = 1U; attempt <= 3U; attempt++)
        {
            s_tick_ms = 300U + 1000U * attempt;
            s_now_us = (unsigned long long)s_tick_ms * 1000ULL;
            SystemTelemetry_Process();
            TEST_CHECK(SystemTelemetry_HealthGet(&health) == SYSTEM_DEVICE_OK);
            TEST_CHECK(health.started == 0U && health.healthy == 0U);
        }
        s_runtime_fault = 0U;
        s_tick_ms = 5300U; s_now_us = 5300000ULL;
        SystemTelemetry_Process();
        TEST_CHECK(SystemTelemetry_HealthGet(&health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.started == 0U && health.healthy == 0U);
        Sx1281RecoveryDiagnostics recovery;
        TEST_CHECK(Sx1281TelemetryInstance_RecoveryDiagnosticsGet(0U, &recovery) == SYSTEM_DEVICE_OK);
        TEST_CHECK(recovery.attempts == 3U && recovery.limit == 3U);
        TEST_CHECK(recovery.pending == 0U && recovery.limit_exhausted == 1U);
        TEST_CHECK(recovery.fault_bus_status.first_failure_valid == 1U);
        TEST_CHECK(recovery.fault_bus_status.first_failure_at_ms == 300U);
        TEST_CHECK(recovery.fault_captured == 1U);
    }
    else
    {
        s_runtime_fault = 0U;
        if (strcmp(argv[1], "start_fail") == 0) { s_fault_on_rx_start = 1U; }
        s_tick_ms = 1299U; s_now_us = 1299000ULL;
        SystemTelemetry_Process();
        TEST_CHECK(SystemTelemetry_HealthGet(&health) == SYSTEM_DEVICE_OK);
        TEST_CHECK(health.started == 0U);
        s_tick_ms = 1300U; s_now_us = 1300000ULL;
        SystemTelemetry_Process();
        TEST_CHECK(SystemTelemetry_HealthGet(&health) == SYSTEM_DEVICE_OK);
        if (strcmp(argv[1], "start_fail") == 0)
        {
            TEST_CHECK(health.started == 0U && health.healthy == 0U);
            s_tick_ms = 2300U; s_now_us = 2300000ULL;
            SystemTelemetry_Process();
            TEST_CHECK(SystemTelemetry_HealthGet(&health) == SYSTEM_DEVICE_OK);
        }
        TEST_CHECK(health.initialized == 1U && health.started == 1U && health.healthy == 1U);
        if ((history_success != 0U) || (history_timeout != 0U))
        {
            TEST_CHECK(health.transmit_packet_count == (history_success != 0U ? 299U : 0U));
            TEST_CHECK(health.transmit_timeout_count >= (history_timeout != 0U ? 1U : 0U));
            TEST_CHECK(Lora_TxEnqueueTracked(0U, receipt_data,
                sizeof(receipt_data), &new_tx_id) == LORA_TX_ENQUEUE_OK);
            TEST_CHECK(new_tx_id != 0U && new_tx_id != old_tx_id);
            TEST_CHECK(Lora_TxResultGet(0U, old_tx_id, &receipt_age_ms) ==
                LoraTxQueryResult_NotFound);
            printf("RADIO_HEALTH_TRACE %lu %lu %lu %lu %lu %lu\n",
                (unsigned long)history_initial_health.transmit_packet_count,
                (unsigned long)history_initial_health.transmit_timeout_count,
                (unsigned long)history_fault_health.transmit_packet_count,
                (unsigned long)history_fault_health.transmit_timeout_count,
                (unsigned long)health.transmit_packet_count,
                (unsigned long)health.transmit_timeout_count);
        }
        Sx1281RecoveryDiagnostics recovery;
        TEST_CHECK(Sx1281TelemetryInstance_RecoveryDiagnosticsGet(0U, &recovery) == SYSTEM_DEVICE_OK);
        TEST_CHECK(recovery.attempts == (strcmp(argv[1], "start_fail") == 0 ? 2U : 1U));
        TEST_CHECK(recovery.limit_exhausted == 0U);
        TEST_CHECK(recovery.fault_bus_status.first_failure_valid == 1U);
        TEST_CHECK(recovery.fault_bus_status.first_failure_at_ms == 300U);
        TEST_CHECK(recovery.fault_captured == 1U);
    }
    printf("RUNTIME_OWNER preemptions=%u max_depth=%u bounded owner recovery verified\n", s_preempt_count, s_max_process_depth);
    return Test_Finish(argv[1]);
}
