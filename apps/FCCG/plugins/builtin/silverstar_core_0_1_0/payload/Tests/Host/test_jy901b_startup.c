#include <stdint.h>
#include <string.h>

#include "host_platform_mock.h"
#include "jy901b_config.h"
#include "jy901b_startup.h"
#ifdef JY_BOOT_PROBE_ADAPTER_VERIFY
#include "jy901b_instance.h"
#include "debug_log.h"
#endif
#include "platform_time.h"
#include "test_common.h"

#ifdef JY_BOOT_PROBE_ADAPTER_VERIFY
void DebugLog_Print(const char *fmt, ...) { (void)fmt; }
#endif

static void Test_FrameBuild(uint8_t type, uint8_t frame[IMU_FRAME_LEN])
{
    uint8_t index;

    for (index = 0U; index < IMU_FRAME_LEN; index++) { frame[index] = 0U; }
    frame[0] = IMU_FRAME_HEADER;
    frame[1] = type;
    for (index = 0U; index < (IMU_FRAME_LEN - 1U); index++)
    { frame[10] = (uint8_t)(frame[10] + frame[index]); }
}

static void Test_SamplesInject(void)
{
    uint8_t accel[IMU_FRAME_LEN];
    uint8_t gyro[IMU_FRAME_LEN];

    Test_FrameBuild(0x51U, accel);
    Test_FrameBuild(0x52U, gyro);
    (void)HostPlatformMock_UartRxInject(PLATFORM_UART_1,
        accel, sizeof(accel));
    (void)HostPlatformMock_UartRxInject(PLATFORM_UART_1,
        gyro, sizeof(gyro));
}

static void Test_RegisterDefaultsSet(void)
{
    uint8_t index;

    for (index = 0U; index < JY901B_STARTUP_REGISTER_COUNT; index++)
    {
        uint8_t reg;
        uint16_t expected;
        TEST_CHECK(IMU_StartupRegisterGet(index, OutputRate_200Hz,
            Algorithm_6Axis, &reg, &expected) ==
            Jy901bStartupRegisterResult_Ok);
        HostPlatformMock_Jy901bRegisterSet(PLATFORM_UART_1,
            reg, expected);
    }
}

static void Test_Run(uint32_t physical_baud, uint8_t inject_samples)
{
    uint32_t tick;

    for (tick = 0U; tick < 1000U; tick++)
    {
        SystemDeviceStartupState state = Jy901bStartup_StateGet(0U);
        uint32_t host_baud = 0U;
        (void)PlatformUart_BaudGet(PLATFORM_UART_1, &host_baud);
        if ((state == SystemDeviceStartupState_Probing) &&
            (host_baud == physical_baud))
        { Test_SamplesInject(); Test_SamplesInject(); }
        if ((state == SystemDeviceStartupState_WaitingSample) &&
            (inject_samples != 0U))
        { Test_SamplesInject(); }
        Jy901bStartup_Tick(0U, PlatformTime_Ms());
        state = Jy901bStartup_StateGet(0U);
        if ((state == SystemDeviceStartupState_Ready) ||
            (state == SystemDeviceStartupState_Failed))
        { return; }
        HostPlatformMock_TimeAdvanceUs(10000ULL);
    }
}

static uint8_t Test_ConfigWritesCount(uint8_t *last_reg)
{
    uint8_t tx[2048];
    uint16_t count = HostPlatformMock_UartTxTake(
        PLATFORM_UART_1, tx, sizeof(tx));
    uint16_t offset;
    uint8_t writes = 0U;

    *last_reg = 0U;
    for (offset = 0U; (uint16_t)(offset + IMU_CFG_FRAME_LEN) <= count;
         offset = (uint16_t)(offset + IMU_CFG_FRAME_LEN))
    {
        if ((tx[offset] != 0xFFU) || (tx[offset + 1U] != 0xAAU) ||
            (tx[offset + 2U] == IMU_REG_READADDR) ||
            (tx[offset + 2U] == IMU_REG_KEY))
        { continue; }
        writes++;
        *last_reg = tx[offset + 2U];
    }
    return writes;
}

static void Test_LateStream(uint32_t physical_baud, uint32_t initial_ms)
{
    uint32_t tick;
    uint32_t started_ms;
    uint32_t identified_ms = 0U;
    uint8_t identified = 0U;
    /* The generated-platform integration target also checks the real adapter. */
#ifdef JY_BOOT_PROBE_ADAPTER_VERIFY
    SystemDeviceResult init_result;
    SystemImuConfig verify_config;
    SystemDeviceConfigReport verify_report;
    (void)memset(&verify_config, 0, sizeof(verify_config));
    verify_config.requested_mask = SYSTEM_IMU_CFG_OUTPUT_RATE;
    verify_config.output_rate_hz = 200U;
#endif

    HostPlatformMock_Reset();
    HostPlatformMock_TimeAdvanceUs((uint64_t)initial_ms * 1000ULL);
    HostPlatformMock_Jy901bEnable(PLATFORM_UART_1, 1U, 0U);
#ifdef JY_BOOT_PROBE_ADAPTER_VERIFY
    init_result = Jy901bImuInstance_Init(0U);
    TEST_CHECK((init_result == SYSTEM_DEVICE_OK) ||
        (init_result == SYSTEM_DEVICE_ALREADY_MATCHED));
    /* Reset the driver after each independent host UART/time fixture reset. */
#endif
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    if (physical_baud == JY901B_UART_BOOT_BAUD) { Test_RegisterDefaultsSet(); }
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz,
        Algorithm_6Axis) == Jy901bStartupResult_Ok);
    started_ms = PlatformTime_Ms();
    for (tick = 0U; tick < 1000U; tick++)
    {
        uint32_t elapsed = (uint32_t)(PlatformTime_Ms() - started_ms);
        uint32_t host_baud = 0U;
        SystemDeviceStartupState state = Jy901bStartup_StateGet(0U);
        (void)PlatformUart_BaudGet(PLATFORM_UART_1, &host_baud);
        /* Both first-pass target/factory slots have ended at 600 ms.
         * Valid physical streaming is available at 700 ms, before pass two. */
        if ((elapsed >= 700U) &&
            (state == SystemDeviceStartupState_Probing) &&
            (host_baud == physical_baud))
        { Test_SamplesInject(); Test_SamplesInject(); }
        if (state == SystemDeviceStartupState_WaitingSample)
        { Test_SamplesInject(); }
        Jy901bStartup_Tick(0U, PlatformTime_Ms());
        state = Jy901bStartup_StateGet(0U);
        TEST_CHECK(state != SystemDeviceStartupState_Failed);
#ifdef JY_BOOT_PROBE_ADAPTER_VERIFY
        TEST_CHECK(Jy901bImuInstance_ConfigVerify(0U, &verify_config, &verify_report) ==
            ((state == SystemDeviceStartupState_Ready) ? SYSTEM_DEVICE_OK : SYSTEM_DEVICE_BUSY));
#endif
        TEST_CHECK(Jy901bStartup_FailureGet(0U) == SystemDeviceStartupFailure_None);
        if ((state == SystemDeviceStartupState_Identified) && (identified == 0U))
        { identified = 1U; identified_ms = elapsed; }
        if (state == SystemDeviceStartupState_Ready) { break; }
        HostPlatformMock_TimeAdvanceUs(10000ULL);
    }
    TEST_CHECK(Jy901bStartup_StateGet(0U) == SystemDeviceStartupState_Ready);
    TEST_CHECK(identified != 0U);
    TEST_CHECK(identified_ms >= 2100U && identified_ms < 2700U);
}

static void Test_AbsentProbeBudget(uint32_t initial_ms)
{
    HostPlatformMock_Reset();
    HostPlatformMock_TimeAdvanceUs((uint64_t)initial_ms * 1000ULL);
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz,
        Algorithm_6Axis) == Jy901bStartupResult_Ok);
    Test_Run(0U, 0U);
    TEST_CHECK(Jy901bStartup_StateGet(0U) == SystemDeviceStartupState_Failed);
    TEST_CHECK(Jy901bStartup_FailureGet(0U) == SystemDeviceStartupFailure_NotPresent);
    TEST_CHECK((uint32_t)(PlatformTime_Ms() - initial_ms) == 4200U);
}

int main(void)
{
    uint8_t last_reg;

    HostPlatformMock_Reset();
    HostPlatformMock_Jy901bEnable(PLATFORM_UART_1, 1U, 0U);
    TEST_CHECK(IMU_LocalGravitySet(0U, 9.80665f) == IMU_OK);
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    Test_RegisterDefaultsSet();
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz,
        Algorithm_6Axis) == Jy901bStartupResult_Ok);
    Test_Run(JY901B_UART_BOOT_BAUD, 1U);
    TEST_CHECK(Jy901bStartup_StateGet(0U) == SystemDeviceStartupState_Ready);
    TEST_CHECK(Test_ConfigWritesCount(&last_reg) == 0U);

    HostPlatformMock_Reset();
    HostPlatformMock_Jy901bEnable(PLATFORM_UART_1, 1U, 0U);
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz,
        Algorithm_6Axis) == Jy901bStartupResult_Ok);
    Test_Run(JY901B_FACTORY_BAUD, 1U);
    TEST_CHECK(Jy901bStartup_StateGet(0U) == SystemDeviceStartupState_Ready);
    TEST_CHECK(HostPlatformMock_Jy901bRegisterGet(
        PLATFORM_UART_1, IMU_REG_BAUD) == IMU_DEFAULT_BAUD_VALUE);
    TEST_CHECK(Test_ConfigWritesCount(&last_reg) > 0U);
    TEST_CHECK(last_reg == IMU_REG_BAUD);

    HostPlatformMock_Reset();
    HostPlatformMock_Jy901bEnable(PLATFORM_UART_1, 1U, 1U);
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz,
        Algorithm_6Axis) == Jy901bStartupResult_Ok);
    Test_Run(JY901B_UART_BOOT_BAUD, 1U);
    TEST_CHECK(Jy901bStartup_StateGet(0U) == SystemDeviceStartupState_Failed);
    TEST_CHECK(Jy901bStartup_FailureGet(0U) ==
        SystemDeviceStartupFailure_ConfigVerify);

    HostPlatformMock_Reset();
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz,
        Algorithm_6Axis) == Jy901bStartupResult_Ok);
    Test_Run(0U, 0U);
    TEST_CHECK(Jy901bStartup_StateGet(0U) == SystemDeviceStartupState_Failed);
    TEST_CHECK(Jy901bStartup_FailureGet(0U) ==
        SystemDeviceStartupFailure_NotPresent);
    Test_LateStream(JY901B_UART_BOOT_BAUD, 0U);
    Test_LateStream(JY901B_FACTORY_BAUD, 0U);
    Test_LateStream(JY901B_UART_BOOT_BAUD, UINT32_MAX - 1000U);
    Test_LateStream(JY901B_FACTORY_BAUD, UINT32_MAX - 1000U);
    Test_AbsentProbeBudget(0U);
    Test_AbsentProbeBudget(UINT32_MAX - 1000U);
    return Test_Finish("jy901b_startup");
}
