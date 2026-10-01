#include <stdint.h>
#include <string.h>

#include "host_platform_mock.h"
#include "jy901b_config.h"
#include "jy901b_device.h"
#include "platform_uart.h"
#include "test_common.h"

#define TEST_LOCAL_GRAVITY_MPS2 9.80665f

static uint8_t s_advance_on_read;
static uint8_t s_clamp_rsw;
static uint16_t s_readback_rsw;
static uint8_t s_stop_fail;
static uint8_t s_restart_fail;
static uint8_t s_write_fail_at;
static uint32_t s_write_calls;
static uint32_t s_restart_calls;
static uint32_t s_baud_calls;

static PlatformResult Test_UartRead(PlatformUartId id, uint8_t *data,
    uint16_t capacity, uint16_t *length)
{
    PlatformResult result = PlatformUart_Read(id, data, capacity, length);
    if ((result == PLATFORM_OK) && (*length != 0U) && (s_advance_on_read != 0U))
    { HostPlatformMock_TimeAdvanceUs(1000ULL); }
    return result;
}

static PlatformResult Test_UartWrite(PlatformUartId id, const uint8_t *data,
    uint16_t length, uint32_t timeout_ms)
{
    PlatformResult result;
    s_write_calls++;
    if (s_write_calls == s_write_fail_at) { return PLATFORM_IO_ERROR; }
    result = PlatformUart_Write(id, data, length, timeout_ms);
    if ((result == PLATFORM_OK) && (length == IMU_CFG_FRAME_LEN) &&
        (data[2] == IMU_REG_RSW) && (s_clamp_rsw != 0U))
    { HostPlatformMock_Jy901bRegisterSet(id, IMU_REG_RSW, s_readback_rsw); }
    return result;
}

static PlatformResult Test_UartRxStop(PlatformUartId id)
{
    PlatformResult result = PlatformUart_RxStop(id);
    return (s_stop_fail != 0U) ? PLATFORM_IO_ERROR : result;
}

static PlatformResult Test_UartRxRestart(PlatformUartId id)
{
    s_restart_calls++;
    if (s_restart_fail != 0U) { return PLATFORM_IO_ERROR; }
    return PlatformUart_RxRestart(id);
}

static PlatformResult Test_UartBaudSet(PlatformUartId id, uint32_t baudrate)
{
    PlatformResult result;
    s_baud_calls++;
    result = PlatformUart_BaudSet(id, baudrate);
    if (result != PLATFORM_OK) { return result; }
    /* The actual F4 backend returns RxRestart's result on its success path. */
    return Test_UartRxRestart(id);
}

#define PlatformUart_Read Test_UartRead
#define PlatformUart_Write Test_UartWrite
#define PlatformUart_RxStop Test_UartRxStop
#define PlatformUart_RxRestart Test_UartRxRestart
#define PlatformUart_BaudSet Test_UartBaudSet
#include "jy901b_device.c"
#undef PlatformUart_Read
#undef PlatformUart_Write
#undef PlatformUart_RxStop
#undef PlatformUart_RxRestart
#undef PlatformUart_BaudSet

static void Test_Setup(void)
{
    HostPlatformMock_Reset();
    HostPlatformMock_TimeSetUs(100000ULL);
    TEST_CHECK(IMU_LocalGravitySet(0U, TEST_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    s_write_calls = 0U;
    s_restart_calls = 0U;
    s_baud_calls = 0U;
}

static void Test_FrameInject(void)
{
    uint8_t frame[IMU_FRAME_LEN] = {IMU_FRAME_HEADER, IMUFrameQuaternion, 0U};
    uint8_t i;
    uint8_t checksum = 0U;
    frame[3] = 0x40U;
    for (i = 0U; i < (IMU_FRAME_LEN - 1U); i++)
    { checksum = (uint8_t)(checksum + frame[i]); }
    frame[IMU_FRAME_LEN - 1U] = checksum;
    TEST_CHECK(HostPlatformMock_UartRxInject(PLATFORM_UART_1,
        frame, sizeof(frame)) == sizeof(frame));
}

static void Test_Time(const char *scenario)
{
    uint32_t expected_tick = 100U;
    Test_Setup();
    if (strcmp(scenario, "no_frame") == 0)
    {
        IMU_Poll(0U);
        TEST_CHECK(IMU_GetData(0U)->Online == 0U);
        TEST_CHECK(IMU_IsOnline(0U) == 0U);
        return;
    }
    if ((strcmp(scenario, "cross_ms") == 0) ||
        (strcmp(scenario, "wrap_to_zero") == 0))
    { s_advance_on_read = 1U; expected_tick = 101U; }
    if (strcmp(scenario, "wrap_to_zero") == 0)
    { HostPlatformMock_TimeSetUs((uint64_t)UINT32_MAX * 1000ULL); expected_tick = 0U; }
    Test_FrameInject();
    IMU_Poll(0U);
    TEST_CHECK(IMU_GetData(0U)->LastUpdateTickMs == expected_tick);
    TEST_CHECK(IMU_GetData(0U)->Online == 1U);
    TEST_CHECK(IMU_IsOnline(0U) == 1U);
    if (strcmp(scenario, "timeout") == 0)
    {
        HostPlatformMock_TimeAdvanceUs((uint64_t)IMU_ONLINE_TIMEOUT_MS * 1000ULL);
        IMU_Poll(0U);
        TEST_CHECK(IMU_GetData(0U)->Online == 1U);
        HostPlatformMock_TimeAdvanceUs(1000ULL);
        IMU_Poll(0U);
        TEST_CHECK(IMU_GetData(0U)->Online == 0U);
        TEST_CHECK(IMU_IsOnline(0U) == 0U);
    }
    if (strcmp(scenario, "wrap_elapsed") == 0)
    {
        HostPlatformMock_TimeSetUs(((uint64_t)UINT32_MAX - 2ULL) * 1000ULL);
        Test_FrameInject();
        IMU_Poll(0U);
        HostPlatformMock_TimeAdvanceUs(5000ULL);
        IMU_Poll(0U);
        TEST_CHECK(IMU_GetData(0U)->Online == 1U);
        TEST_CHECK(IMU_IsOnline(0U) == 1U);
        HostPlatformMock_TimeAdvanceUs((uint64_t)IMU_ONLINE_TIMEOUT_MS * 1000ULL);
        IMU_Poll(0U);
        TEST_CHECK(IMU_GetData(0U)->Online == 0U);
        TEST_CHECK(IMU_IsOnline(0U) == 0U);
    }
}

static void Test_Readback(const char *scenario)
{
    IMUState expected = IMU_RESP_INVALID;
    Test_Setup();
    HostPlatformMock_Jy901bEnable(PLATFORM_UART_1, 1U, 0U);
    s_clamp_rsw = 1U;
    s_readback_rsw = FC_IMU_RETURN_CONTENT_DEFAULT;
    if (strcmp(scenario, "only_quat") == 0) { s_readback_rsw = FC_IMU_RETURN_CONTENT_QUAT_MASK; }
    if (strcmp(scenario, "missing_acc") == 0) { s_readback_rsw &= (uint16_t)~JY901B_RSW_ACCEL_MASK; }
    if (strcmp(scenario, "missing_gyro") == 0) { s_readback_rsw &= (uint16_t)~JY901B_RSW_GYRO_MASK; }
    if (strcmp(scenario, "missing_pressure") == 0) { s_readback_rsw &= (uint16_t)~JY901B_RSW_PRESSURE_MASK; }
    if (strcmp(scenario, "missing_quat") == 0) { s_readback_rsw &= (uint16_t)~FC_IMU_RETURN_CONTENT_QUAT_MASK; }
    if (strcmp(scenario, "complete") == 0) { expected = IMU_OK; }
    if (strcmp(scenario, "complete_extra") == 0) { s_readback_rsw |= 0x8000U; expected = IMU_OK; }
    if (strcmp(scenario, "already_complete") == 0)
    { HostPlatformMock_Jy901bRegisterSet(PLATFORM_UART_1, IMU_REG_RSW, FC_IMU_RETURN_CONTENT_DEFAULT); expected = IMU_OK; }
    TEST_CHECK(IMU_EnsureQuaternionOutput(0U) == expected);
    if (strcmp(scenario, "already_complete") == 0) { TEST_CHECK(s_write_calls == 1U); }
    else { TEST_CHECK(s_write_calls == 4U); }
    TEST_CHECK(HostPlatformMock_Jy901bRegisterGet(PLATFORM_UART_1, IMU_REG_SAVE) == 0U);
}

static void Test_Receive(const char *scenario)
{
    PlatformUartDiagnostics diagnostics;
    IMUState expected = IMU_OK;
    uint8_t baud_case = (uint8_t)(strncmp(scenario, "baud_", 5U) == 0);
    Test_Setup();
    if (strstr(scenario, "stop_fail") != NULL) { s_stop_fail = 1U; expected = IMU_UART_RX_ERROR; }
    if (strstr(scenario, "restart_fail") != NULL)
    { s_restart_fail = 1U; expected = (baud_case != 0U) ? IMU_UART_INIT_ERROR : IMU_UART_RX_ERROR; }
    if (strstr(scenario, "tx_fail") != NULL)
    { s_write_fail_at = 1U; expected = (s_restart_fail != 0U) ? IMU_UART_RX_ERROR : IMU_UART_TX_ERROR; }
    if (baud_case != 0U) { TEST_CHECK(IMU_SetBaudrate(0U, Baudrate_115200) == expected); }
    else { TEST_CHECK(IMU_SetOutputRate(0U, OutputRate_200Hz) == expected); }
    TEST_CHECK(PlatformUart_DiagnosticsGet(PLATFORM_UART_1, &diagnostics) == PLATFORM_OK);
    TEST_CHECK(diagnostics.rx_active == ((s_restart_fail != 0U) ? 0U : 1U));
    TEST_CHECK(s_restart_calls == 1U);
    if (s_stop_fail != 0U) { TEST_CHECK(s_write_calls == 0U && s_baud_calls == 0U); }
}

static void Test_Save(const char *scenario)
{
    IMUState expected = IMU_OK;
    uint32_t writes = 2U;
    Test_Setup();
    if (strstr(scenario, "stop_fail") != NULL)
    { s_stop_fail = 1U; expected = IMU_UART_RX_ERROR; writes = 0U; }
    if (strstr(scenario, "unlock_fail") != NULL)
    { s_write_fail_at = 1U; expected = IMU_UART_TX_ERROR; writes = 1U; }
    if (strstr(scenario, "save_fail") != NULL)
    { s_write_fail_at = 2U; expected = IMU_UART_TX_ERROR; }
    if (strstr(scenario, "restart_fail") != NULL)
    { s_restart_fail = 1U; expected = IMU_UART_RX_ERROR; }
    TEST_CHECK(IMU_SaveConfig(0U) == expected);
    TEST_CHECK(s_write_calls == writes);
    TEST_CHECK(s_restart_calls == 1U);
}

int main(int argc, char **argv)
{
    if (argc != 3) { return 2; }
    if (strcmp(argv[1], "time") == 0) { Test_Time(argv[2]); }
    else if (strcmp(argv[1], "readback") == 0) { Test_Readback(argv[2]); }
    else if (strcmp(argv[1], "receive") == 0) { Test_Receive(argv[2]); }
    else if (strcmp(argv[1], "save") == 0) { Test_Save(argv[2]); }
    else { return 2; }
    return Test_Finish("jy901b_boundary");
}
