#include <stdint.h>

#include "host_platform_mock.h"
#include "jy901b_config.h"
#include "jy901b_startup.h"
#include "platform_time.h"
#include "test_common.h"

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
    return Test_Finish("jy901b_startup");
}
