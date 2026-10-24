/* Host-only actual UART/ring/Console/formatter model. No physical I/O. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stm32f4xx_hal.h"
#include "platform_critical.h"
#include "platform_stm32f4_resources.h"
#include "project_resources.h"
#include "system_console_if.h"
#include "console_uart_device.h"
#include "debug_log.h"
#include "test_common.h"

static UART_HandleTypeDef s_handles[6];
static DMA_HandleTypeDef s_dma[6];
static unsigned s_depth, s_cases;
static unsigned s_receive_init_calls;
/* This frame test controls the configuration boundary; the generated guard's
 * actual HAL-field checks are exercised by test_host_configuration_fixtures. */
static ProjectMaintenanceUartResult s_maintenance_result = ProjectMaintenanceUartResult_Mismatch;
ProjectMaintenanceUartResult ProjectMaintenanceUart_Validate(void)
{ return s_maintenance_result; }
static HAL_StatusTypeDef s_tx_result = HAL_OK;
static uint8_t *s_pending;
static uint8_t s_pending_copy[128], s_wire[8192];
static uint16_t s_pending_length;
static size_t s_wire_length;

#define REQUIRE(c) do { int required_ = !!(c); TEST_CHECK(required_); if (!required_) { exit(2); } } while (0)
void *PlatformStm32f4Resource_UartHandleGet(PlatformUartId id)
{ return (unsigned)id < 6U ? &s_handles[id] : NULL; }
PlatformCriticalState PlatformCritical_Enter(void) { return s_depth++; }
void PlatformCritical_Exit(PlatformCriticalState previous)
{ REQUIRE(s_depth == previous + 1U); s_depth = previous; }
uint8_t PlatformMemory_IsDmaAccessible(const void *data, size_t length)
{ return (uint8_t)(data != NULL && length != 0U); }
HAL_StatusTypeDef HAL_UART_AbortReceive(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_DeInit(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef *h) { (void)h; return HAL_OK; }
HAL_StatusTypeDef HAL_UARTEx_ReceiveToIdle_DMA(UART_HandleTypeDef *h,uint8_t *data,uint16_t n)
{ REQUIRE(h != NULL && data != NULL && n != 0U); s_receive_init_calls++; return HAL_OK; }
HAL_StatusTypeDef HAL_UART_Transmit_DMA(UART_HandleTypeDef *h,uint8_t *data,uint16_t n)
{
    REQUIRE(h == &s_handles[2] && data != NULL && n != 0U && n <= sizeof(s_pending_copy));
    if (s_tx_result != HAL_OK) { return s_tx_result; }
    REQUIRE(s_pending == NULL);
    s_pending=data;s_pending_length=n;memcpy(s_pending_copy,data,n);return HAL_OK;
}
HAL_StatusTypeDef HAL_UART_Transmit(UART_HandleTypeDef *h,uint8_t *data,uint16_t n,uint32_t timeout)
{ (void)timeout; return HAL_UART_Transmit_DMA(h,data,n); }
HAL_UART_RxEventTypeTypeDef HAL_UARTEx_GetRxEventType(UART_HandleTypeDef *h)
{ (void)h; return HAL_UART_RXEVENT_IDLE; }

#include "platform_uart_stm32f4.c"

static void Fixture_Drain(void)
{
    for (unsigned iteration=0U;iteration<128U;iteration++)
    {
        if (s_pending==NULL) { return; }
        REQUIRE(s_depth==0U && memcmp(s_pending,s_pending_copy,s_pending_length)==0);
        REQUIRE(s_wire_length+s_pending_length<=sizeof(s_wire));
        memcpy(s_wire+s_wire_length,s_pending,s_pending_length);s_wire_length+=s_pending_length;
        s_pending=NULL;s_pending_length=0U;HAL_UART_TxCpltCallback(&s_handles[2]);
    }
    REQUIRE(0);
}
static void Fixture_Reset(uint16_t offset)
{
    REQUIRE(s_pending==NULL && s_depth==0U && offset<s_uart[2].tx_ring_size);
    RingBuf_Reset(&s_uart[2].tx_ring);RingBuf_Reset(&s_uart[2].tx_priority_ring);
    s_uart[2].tx_ring.head=offset;s_uart[2].tx_ring.tail=offset;
    s_uart[2].tx_active=0U;s_uart[2].tx_dma_length=0U;
    memset(&s_uart[2].diagnostics,0,sizeof(s_uart[2].diagnostics));
    s_wire_length=0U;s_tx_result=HAL_OK;s_cases++;
}
static void Test_Formatter(void)
{
    static const unsigned lengths[]={0U,300U,301U,302U,303U,304U,308U,318U,500U,1000U};
    char text[1001];
    for (unsigned i=0U;i<sizeof(lengths)/sizeof(lengths[0]);i++)
    {
        Fixture_Reset(0U);memset(text,'A',lengths[i]);text[lengths[i]]='\0';
        DebugLog_Print("%s",text);Fixture_Drain();
        TEST_CHECK(s_wire_length>=2U && s_wire_length<=319U);
        TEST_CHECK(s_wire_length>=2U && s_wire[s_wire_length-2U]=='\r' && s_wire[s_wire_length-1U]=='\n');
    }
    Fixture_Reset(0U);DebugLog_Print(NULL);Fixture_Drain();TEST_CHECK(s_wire_length==0U);
    /* CommonFormat deliberately preserves unknown conversions verbatim. */
    Fixture_Reset(0U);DebugLog_Print("%q");Fixture_Drain();
    static const char unknown[]="LOG INFO SYSTEM %q\r\n";
    TEST_CHECK(s_wire_length==sizeof(unknown)-1U &&
               memcmp(s_wire,unknown,sizeof(unknown)-1U)==0);
    Fixture_Reset(0U);DebugLog_Print("already complete\r\n");Fixture_Drain();
    TEST_CHECK(s_wire_length>=2U && s_wire[s_wire_length-2U]=='\r' && s_wire[s_wire_length-1U]=='\n');
    TEST_CHECK(s_wire_length<4U || s_wire[s_wire_length-3U]!='\n');
}
static void Test_Capacity(uint16_t offset)
{
    uint8_t filler[PROJECT_PLATFORM_UART_3_TX_RING_SIZE-1U-64U];
    char text[301];PlatformUartDiagnostics before,after;
    Fixture_Reset(offset);memset(filler,'F',sizeof(filler));memset(text,'A',300U);text[300]='\0';
    s_tx_result=HAL_BUSY;
    REQUIRE(SystemConsoleDevice_Write(filler,sizeof(filler))==SYSTEM_DEVICE_OK);
    ConsoleUart_DiagnosticsGet(&before);DebugLog_Print("%s",text);ConsoleUart_DiagnosticsGet(&after);
    TEST_CHECK(RingBuf_GetUsed(&s_uart[2].tx_ring)==sizeof(filler));
    TEST_CHECK(after.tx_discarded_bytes-before.tx_discarded_bytes==318U);
    s_tx_result=HAL_OK;PlatformUart_Process(PLATFORM_UART_3);Fixture_Drain();
    TEST_CHECK(s_wire_length==sizeof(filler) && memcmp(s_wire,filler,sizeof(filler))==0);
}
static void Test_LegacyAndBusy(void)
{
    uint8_t legacy[3071];memset(legacy,'L',sizeof(legacy));legacy[3069]='\r';legacy[3070]='\n';
    Fixture_Reset(17U);uint16_t accepted=ConsoleUart_Write(legacy,sizeof(legacy));
    TEST_CHECK(accepted==sizeof(legacy));Fixture_Drain();
    TEST_CHECK(s_wire_length==sizeof(legacy) && memcmp(s_wire,legacy,sizeof(legacy))==0);
    Fixture_Reset(0U);s_tx_result=HAL_BUSY;
    TEST_CHECK(ConsoleUart_Write(legacy,sizeof(legacy))==sizeof(legacy) && s_pending==NULL);
    s_tx_result=HAL_OK;ConsoleUart_Process();Fixture_Drain();TEST_CHECK(s_wire_length==sizeof(legacy));
    Fixture_Reset(0U);TEST_CHECK(ConsoleUart_Write(NULL,1U)==0U);TEST_CHECK(ConsoleUart_Write(legacy,0U)==0U);
    TEST_CHECK(RingBuf_GetUsed(&s_uart[2].tx_ring)==0U);
}
static void Test_RejectionSaturation(void)
{
    static uint8_t oversized[65535];PlatformUartDiagnostics diagnostics;
    Fixture_Reset(0U);
    for (unsigned i=0U;i<65539U;i++) { TEST_CHECK(ConsoleUart_Write(oversized,sizeof(oversized))==0U); }
    ConsoleUart_DiagnosticsGet(&diagnostics);TEST_CHECK(diagnostics.tx_discarded_bytes==UINT32_MAX);
    TEST_CHECK(RingBuf_GetUsed(&s_uart[2].tx_ring)==0U);
    /* Transport errors must not wrap the already saturated public health. */
    s_tx_result=HAL_BUSY;
    TEST_CHECK(ConsoleUart_Write((const uint8_t *)"ok\r\n",4U)==4U);
    SystemConsoleHealth health;
    TEST_CHECK(SystemConsoleDevice_HealthGet(&health)==SYSTEM_DEVICE_OK);
    TEST_CHECK(health.transmit_error_count==UINT32_MAX);
    s_tx_result=HAL_OK;ConsoleUart_Process();Fixture_Drain();
}
int main(void)
{
    s_handles[2].hdmatx=&s_dma[2];
    REQUIRE(ConsoleUart_Init()==CONSOLE_UART_INIT_IO_ERROR);
    REQUIRE(s_receive_init_calls==0U);
    s_maintenance_result=ProjectMaintenanceUartResult_Ok;
    REQUIRE(SystemConsoleDevice_Init()==SYSTEM_DEVICE_OK);REQUIRE(SystemConsoleDevice_Start()==SYSTEM_DEVICE_OK);
    REQUIRE(s_receive_init_calls==1U);
    Test_Formatter();
    for (uint16_t offset=0U;offset<PROJECT_PLATFORM_UART_3_TX_RING_SIZE;offset++) { Test_Capacity(offset); }
    Test_LegacyAndBusy();Test_RejectionSaturation();
    printf("console_frames_actual modeled_cases=%u physical_io=0\n",s_cases);
    return Test_Finish("console_frames_actual");
}
