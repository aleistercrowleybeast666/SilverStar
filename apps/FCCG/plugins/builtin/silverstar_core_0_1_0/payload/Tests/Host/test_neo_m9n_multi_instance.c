#include <stdint.h>
#include <string.h>

#include "neo_m9n_device.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "project_resources.h"
#include "test_common.h"

#define TEST_UART_BUFFER_CAPACITY 256U
#define TEST_PVT_PAYLOAD_LENGTH   92U

typedef struct
{
    uint8_t data[TEST_UART_BUFFER_CAPACITY];
    uint16_t head;
    uint16_t tail;
    uint16_t count;
    uint32_t baudrate;
    PlatformUartDiagnostics diagnostics;
} TestUartContext;

static TestUartContext s_uarts[PLATFORM_UART_COUNT];
static uint32_t s_tick_ms = 100U;

static void Test_U16Write(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
}

static void Test_U32Write(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
    data[2] = (uint8_t)(value >> 16U);
    data[3] = (uint8_t)(value >> 24U);
}

static uint16_t Test_PvtFrameBuild(
    int32_t longitude, int32_t latitude, uint8_t fix_type,
    uint8_t fix_ok, uint8_t *frame)
{
    uint8_t payload[TEST_PVT_PAYLOAD_LENGTH];
    uint8_t ck_a = 0U;
    uint8_t ck_b = 0U;
    uint16_t index;

    (void)memset(payload, 0, sizeof(payload));
    payload[20] = fix_type;
    payload[21] = (uint8_t)(fix_ok != 0U);
    payload[23] = 12U;
    Test_U32Write(&payload[24], (uint32_t)longitude);
    Test_U32Write(&payload[28], (uint32_t)latitude);
    Test_U32Write(&payload[40], 1000U);
    Test_U32Write(&payload[44], 1200U);
    Test_U32Write(&payload[60], 4000U);
    Test_U32Write(&payload[68], 500U);
    Test_U32Write(&payload[72], 1000U);
    frame[0] = 0xB5U;
    frame[1] = 0x62U;
    frame[2] = 0x01U;
    frame[3] = 0x07U;
    Test_U16Write(&frame[4], sizeof(payload));
    (void)memcpy(&frame[6], payload, sizeof(payload));
    for (index = 2U; index < (uint16_t)(6U + sizeof(payload)); index++)
    {
        ck_a = (uint8_t)(ck_a + frame[index]);
        ck_b = (uint8_t)(ck_b + ck_a);
    }
    frame[6U + sizeof(payload)] = ck_a;
    frame[7U + sizeof(payload)] = ck_b;
    return (uint16_t)(sizeof(payload) + 8U);
}

static void Test_UartInject(
    PlatformUartId uart, const uint8_t *data, uint16_t length)
{
    TestUartContext *context = &s_uarts[uart];
    uint16_t index;

    TEST_CHECK((uint32_t)context->count + length <=
               TEST_UART_BUFFER_CAPACITY);
    for (index = 0U; index < length; index++)
    {
        context->data[context->head] = data[index];
        context->head = (uint16_t)((context->head + 1U) %
                                   TEST_UART_BUFFER_CAPACITY);
        context->count++;
    }
    context->diagnostics.rx_bytes += length;
    context->diagnostics.rx_event_count++;
    context->diagnostics.rx_active = 1U;
}

PlatformResult PlatformUart_Init(PlatformUartId id)
{
    if (id >= PLATFORM_UART_COUNT) { return PLATFORM_INVALID_ARGUMENT; }
    s_uarts[id].diagnostics.rx_active = 1U;
    if (s_uarts[id].baudrate == 0U) { s_uarts[id].baudrate = 115200U; }
    return PLATFORM_OK;
}

PlatformResult PlatformUart_Write(
    PlatformUartId id, const uint8_t *data, uint16_t length,
    uint32_t timeout_ms)
{
    (void)timeout_ms;
    if ((id >= PLATFORM_UART_COUNT) || (data == NULL) || (length == 0U))
    { return PLATFORM_INVALID_ARGUMENT; }
    s_uarts[id].diagnostics.tx_bytes += length;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_Read(
    PlatformUartId id, uint8_t *data, uint16_t capacity,
    uint16_t *read_length)
{
    TestUartContext *context;
    uint16_t count = 0U;

    if ((id >= PLATFORM_UART_COUNT) || (data == NULL) ||
        (read_length == NULL))
    { return PLATFORM_INVALID_ARGUMENT; }
    context = &s_uarts[id];
    while ((count < capacity) && (context->count > 0U))
    {
        data[count] = context->data[context->tail];
        context->tail = (uint16_t)((context->tail + 1U) %
                                   TEST_UART_BUFFER_CAPACITY);
        context->count--;
        count++;
    }
    *read_length = count;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baudrate)
{
    if ((id >= PLATFORM_UART_COUNT) || (baudrate == 0U))
    { return PLATFORM_INVALID_ARGUMENT; }
    s_uarts[id].baudrate = baudrate;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_BaudGet(
    PlatformUartId id, uint32_t *baudrate)
{
    if ((id >= PLATFORM_UART_COUNT) || (baudrate == NULL))
    { return PLATFORM_INVALID_ARGUMENT; }
    *baudrate = (s_uarts[id].baudrate != 0U) ?
        s_uarts[id].baudrate : 115200U;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_DiagnosticsGet(
    PlatformUartId id, PlatformUartDiagnostics *diagnostics)
{
    if ((id >= PLATFORM_UART_COUNT) || (diagnostics == NULL))
    { return PLATFORM_INVALID_ARGUMENT; }
    *diagnostics = s_uarts[id].diagnostics;
    return PLATFORM_OK;
}

uint32_t PlatformTime_Ms(void) { return s_tick_ms; }
uint64_t PlatformTime_Us(void) { return (uint64_t)s_tick_ms * 1000ULL; }
void PlatformTime_DelayMs(uint32_t delay_ms) { s_tick_ms += delay_ms; }
PlatformCriticalState PlatformCritical_Enter(void) { return 0U; }
void PlatformCritical_Exit(PlatformCriticalState state) { (void)state; }

static void Test_ParserAndLivenessIsolation(void)
{
    ProjectNeoM9nResources resources0;
    ProjectNeoM9nResources resources1;
    GnssNeoM9nData data0;
    GnssNeoM9nData data1;
    GnssNeoM9nStatusSnapshot status0;
    GnssNeoM9nStatusSnapshot status1;
    uint8_t frame0[TEST_PVT_PAYLOAD_LENGTH + 8U];
    uint8_t frame1[TEST_PVT_PAYLOAD_LENGTH + 8U];
    uint16_t length0;
    uint16_t length1;

    (void)memset(s_uarts, 0, sizeof(s_uarts));
    TEST_CHECK(ProjectNeoM9nResources_Get(0U, &resources0) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(ProjectNeoM9nResources_Get(1U, &resources1) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(resources0.uart != resources1.uart);
    TEST_CHECK(GnssNeoM9n_Init(0U) == GnssNeoM9n_InitOk);
    TEST_CHECK(GnssNeoM9n_Init(1U) == GnssNeoM9n_InitOk);

    length0 = Test_PvtFrameBuild(111111111, 222222222, 3U, 1U, frame0);
    length1 = Test_PvtFrameBuild(-333333333, -444444444, 1U, 0U, frame1);
    Test_UartInject(resources0.uart, frame0, length0);
    Test_UartInject(resources1.uart, frame1, length1);
    TEST_CHECK(GnssNeoM9n_Process(0U, s_tick_ms) ==
               GnssNeoM9n_UpdateOk);
    TEST_CHECK(GnssNeoM9n_Process(1U, s_tick_ms) ==
               GnssNeoM9n_UpdateOk);
    TEST_CHECK(GnssNeoM9n_GetData(0U, &data0) != 0U);
    TEST_CHECK(GnssNeoM9n_GetData(1U, &data1) != 0U);
    TEST_CHECK(data0.lon == 111111111 && data0.lat == 222222222);
    TEST_CHECK(data1.lon == -333333333 && data1.lat == -444444444);
    TEST_CHECK(data0.hasValidFix != 0U);
    TEST_CHECK(data1.hasValidFix == 0U);
    TEST_CHECK(data1.online != 0U);
    GnssNeoM9n_GetStatusSnapshot(0U, &status0);
    GnssNeoM9n_GetStatusSnapshot(1U, &status1);
    TEST_CHECK(status0.ubx_pvt_count == 1U);
    TEST_CHECK(status1.ubx_pvt_count == 1U);

    frame0[length0 - 1U] ^= 0x01U;
    Test_UartInject(resources0.uart, frame0, length0);
    (void)GnssNeoM9n_Process(0U, s_tick_ms);
    GnssNeoM9n_GetStatusSnapshot(0U, &status0);
    GnssNeoM9n_GetStatusSnapshot(1U, &status1);
    TEST_CHECK(status0.ubx_checksum_error_count == 1U);
    TEST_CHECK(status1.ubx_checksum_error_count == 0U);

    s_tick_ms = 1701U;
    length1 = Test_PvtFrameBuild(-555555555, -666666666, 1U, 0U, frame1);
    Test_UartInject(resources1.uart, frame1, length1);
    (void)GnssNeoM9n_Process(0U, s_tick_ms);
    (void)GnssNeoM9n_Process(1U, s_tick_ms);
    TEST_CHECK(GnssNeoM9n_GetData(0U, &data0) == 0U);
    TEST_CHECK(GnssNeoM9n_GetData(1U, &data1) != 0U);
    TEST_CHECK(data1.lon == -555555555);
    TEST_CHECK(data1.hasValidFix == 0U);

    GnssNeoM9n_GetStatusSnapshot(1U, &status1);
    TEST_CHECK(GnssNeoM9n_Init(0U) == GnssNeoM9n_InitOk);
    GnssNeoM9n_GetStatusSnapshot(1U, &status0);
    TEST_CHECK(status0.ubx_pvt_count == status1.ubx_pvt_count);
    TEST_CHECK(status0.ubx_checksum_error_count ==
               status1.ubx_checksum_error_count);
}

int main(void)
{
    _Static_assert(PROJECT_NEO_M9N_INSTANCE_COUNT == 2U,
        "multi-instance NEO-M9N Host fixture must expose two contexts");
    Test_ParserAndLivenessIsolation();
    return Test_Finish("neo_m9n_multi_instance");
}
