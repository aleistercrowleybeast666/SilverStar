#include <stdint.h>
#include <string.h>

#include "project_resources.h"
#include "host_platform_mock.h"
#include "jy901b_config.h"
#include "jy901b_device.h"
#include "system_user_config.h"
#include "test_common.h"

#define TEST_TX_BUFFER_CAPACITY 512U
#ifndef PROJECT_RESOURCE_IMU_UART
#define PROJECT_RESOURCE_IMU_UART PLATFORM_UART_1
#endif

/* Exercise the first generated instance in the existing single-device cases. */
#define IMU_LocalGravitySet(gravity) IMU_LocalGravitySet(0U, (gravity))
#define IMU_Init() IMU_Init(0U)
#define IMU_ApplyDefaultConfig(rate, algorithm) \
    IMU_ApplyDefaultConfig(0U, (rate), (algorithm))
#define IMU_Poll() IMU_Poll(0U)
#define IMU_StreamDiagnosticsGet(diagnostics) \
    IMU_StreamDiagnosticsGet(0U, (diagnostics))
#define IMU_IsOnline() IMU_IsOnline(0U)
#define IMU_GetData() IMU_GetData(0U)
#define Jy901bImu_SampleGetNext(sample) \
    Jy901bImu_SampleGetNext(0U, (sample))
#define IMU_ConfigCacheGet(config) IMU_ConfigCacheGet(0U, (config))

static uint8_t Test_ChecksumGet(const uint8_t *frame)
{
    uint8_t checksum = 0U;
    uint8_t index;

    for (index = 0U; index < (IMU_FRAME_LEN - 1U); index++)
    {
        checksum = (uint8_t)(checksum + frame[index]);
    }
    return checksum;
}

static void Test_S16Write(uint8_t *data, int16_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)((uint16_t)value >> 8U);
}

static void Test_FrameBuild(uint8_t type, int16_t x, int16_t y,
                            int16_t z, int16_t temperature,
                            uint8_t *frame)
{
    (void)memset(frame, 0, IMU_FRAME_LEN);
    frame[0] = IMU_FRAME_HEADER;
    frame[1] = type;
    Test_S16Write(&frame[2], x);
    Test_S16Write(&frame[4], y);
    Test_S16Write(&frame[6], z);
    Test_S16Write(&frame[8], temperature);
    frame[10] = Test_ChecksumGet(frame);
}

static uint8_t Test_RegisterWriteCount(const uint8_t *data,
                                       uint16_t length,
                                       uint8_t reg)
{
    uint8_t count = 0U;
    uint16_t offset;

    for (offset = 0U; (uint16_t)(offset + IMU_CFG_FRAME_LEN) <= length;
         offset = (uint16_t)(offset + IMU_CFG_FRAME_LEN))
    {
        if (data[offset + 2U] == reg) { count++; }
    }
    return count;
}

static uint16_t Test_RegisterLastValue(const uint8_t *data,
                                       uint16_t length,
                                       uint8_t reg)
{
    uint16_t offset = length;

    while (offset >= IMU_CFG_FRAME_LEN)
    {
        offset = (uint16_t)(offset - IMU_CFG_FRAME_LEN);
        if (data[offset + 2U] == reg)
        {
            return (uint16_t)((uint16_t)data[offset + 3U] |
                              ((uint16_t)data[offset + 4U] << 8U));
        }
    }
    return 0xFFFFU;
}

static void Test_ReturnContentComposition(void)
{
    TEST_CHECK((FC_IMU_RETURN_CONTENT_DEFAULT & JY901B_RSW_ACCEL_MASK) != 0U);
    TEST_CHECK((FC_IMU_RETURN_CONTENT_DEFAULT & JY901B_RSW_GYRO_MASK) != 0U);
    TEST_CHECK((FC_IMU_RETURN_CONTENT_DEFAULT &
                JY901B_RSW_PRESSURE_MASK) != 0U);
    TEST_CHECK((FC_IMU_RETURN_CONTENT_DEFAULT &
                JY901B_RSW_QUATERNION_MASK) != 0U);
#if JY901B_MAGNETOMETER_ADAPTER_ENABLE
    TEST_CHECK((FC_IMU_RETURN_CONTENT_DEFAULT & JY901B_RSW_MAG_MASK) != 0U);
#else
    TEST_CHECK((FC_IMU_RETURN_CONTENT_DEFAULT & JY901B_RSW_MAG_MASK) == 0U);
#endif
}

static void Test_InitUsesPlatformUart(void)
{
    HostPlatformMock_Reset();
    TEST_CHECK(IMU_LocalGravitySet(0.0f) == IMU_RESP_INVALID);
    TEST_CHECK(IMU_LocalGravitySet(SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    HostPlatformMock_UartInitResultSet(PROJECT_RESOURCE_IMU_UART,
                                       PLATFORM_IO_ERROR);
    TEST_CHECK(IMU_Init() == IMU_UART_INIT_ERROR);
    HostPlatformMock_UartInitResultSet(PROJECT_RESOURCE_IMU_UART, PLATFORM_OK);
    TEST_CHECK(IMU_Init() == IMU_OK);
}

static void Test_ParserAndNativeSample(void)
{
    uint8_t frames[2U * IMU_FRAME_LEN];
    Jy901bImuSample sample;
    IMUStreamDiagnostics diagnostics;
    const IMUData *data;

    HostPlatformMock_Reset();
    HostPlatformMock_TimeSetUs(100000ULL);
    TEST_CHECK(IMU_LocalGravitySet(SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init() == IMU_OK);
    Test_FrameBuild(IMUFrameAcc, 0, 0, 2048, 2500, &frames[0]);
    Test_FrameBuild(IMUFrameGyro, 100, -200, 300, 2500,
                    &frames[IMU_FRAME_LEN]);
    TEST_CHECK(HostPlatformMock_UartRxInject(
        PROJECT_RESOURCE_IMU_UART, frames, sizeof(frames)) == sizeof(frames));
    IMU_Poll();
    data = IMU_GetData();
    TEST_CHECK(data->AccRaw[2] == 2048);
    TEST_CHECK(data->GyroRaw[0] == 100);
    TEST_CHECK_NEAR(data->Acc[2], SYSTEM_LOCAL_GRAVITY_MPS2, 1.0e-4f);
    TEST_CHECK_NEAR(data->TemperatureC, 25.0f, 1.0e-5f);
    TEST_CHECK(data->FrameCount == 2U);
    TEST_CHECK(IMU_IsOnline() != 0U);
    TEST_CHECK(Jy901bImu_SampleGetNext(&sample) ==
               JY901B_IMU_SAMPLE_GET_OK);
    TEST_CHECK(sample.accel_raw[2] == 2048);
    TEST_CHECK(sample.gyro_raw[1] == -200);
    TEST_CHECK_NEAR(sample.accel_mps2[2], SYSTEM_LOCAL_GRAVITY_MPS2,
                    1.0e-4f);
    IMU_StreamDiagnosticsGet(&diagnostics);
    TEST_CHECK(diagnostics.valid_frame_count == 2U);
    TEST_CHECK(diagnostics.checksum_error_count == 0U);
}

static void Test_ApplyUsesOneSave(void)
{
    uint8_t tx[TEST_TX_BUFFER_CAPACITY];
    uint16_t tx_length;
    IMUConfig config;

    HostPlatformMock_Reset();
    HostPlatformMock_Jy901bEnable(PROJECT_RESOURCE_IMU_UART, 1U, 0U);
    TEST_CHECK(IMU_LocalGravitySet(SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init() == IMU_OK);
    TEST_CHECK(IMU_ApplyDefaultConfig(OutputRate_200Hz,
                                      Algorithm_6Axis) == IMU_OK);
    tx_length = HostPlatformMock_UartTxTake(
        PROJECT_RESOURCE_IMU_UART, tx, sizeof(tx));
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_SAVE) == 0U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_BAUD) == 1U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_ORIENT) == 1U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_AXIS6) == 1U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_RRATE) == 1U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_RSW) == 1U);
    TEST_CHECK(Test_RegisterLastValue(tx, tx_length, IMU_REG_AXIS6) ==
               IMU_ALGORITHM_6_AXIS_VALUE);
    TEST_CHECK(Test_RegisterLastValue(tx, tx_length, IMU_REG_RRATE) ==
               IMU_RRATE_200HZ_VALUE);
    TEST_CHECK(Test_RegisterLastValue(tx, tx_length, IMU_REG_RSW) ==
               FC_IMU_RETURN_CONTENT_DEFAULT);
    IMU_ConfigCacheGet(&config);
    TEST_CHECK(config.AlgorithmValue == IMU_ALGORITHM_6_AXIS_VALUE);
    TEST_CHECK(config.OutputRateValue == IMU_RRATE_200HZ_VALUE);
    TEST_CHECK(config.ReturnContentValue == FC_IMU_RETURN_CONTENT_DEFAULT);
    TEST_CHECK(IMU_ApplyDefaultConfig(OutputRate_200Hz, Algorithm_6Axis) == IMU_OK);
    tx_length = HostPlatformMock_UartTxTake(PROJECT_RESOURCE_IMU_UART, tx, sizeof(tx));
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_SAVE) == 0U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_BAUD) == 0U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_RRATE) == 0U);
}

static void Test_ReadbackMismatchDoesNotSave(void)
{
    uint8_t tx[TEST_TX_BUFFER_CAPACITY];
    uint16_t length;
    HostPlatformMock_Reset();
    HostPlatformMock_Jy901bEnable(PROJECT_RESOURCE_IMU_UART, 1U, 1U);
    TEST_CHECK(IMU_Init() == IMU_OK);
    TEST_CHECK(IMU_ApplyDefaultConfig(OutputRate_200Hz, Algorithm_6Axis) == IMU_RESP_INVALID);
    length = HostPlatformMock_UartTxTake(PROJECT_RESOURCE_IMU_UART, tx, sizeof(tx));
    TEST_CHECK(Test_RegisterWriteCount(tx, length, IMU_REG_SAVE) == 0U);
}

static void Test_WriteFailureDoesNotSave(void)
{
    uint8_t tx[TEST_TX_BUFFER_CAPACITY];
    uint16_t tx_length;

    HostPlatformMock_Reset();
    TEST_CHECK(IMU_LocalGravitySet(SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init() == IMU_OK);
    HostPlatformMock_UartWriteResultSet(PROJECT_RESOURCE_IMU_UART,
                                        PLATFORM_IO_ERROR);
    TEST_CHECK(IMU_ApplyDefaultConfig(OutputRate_200Hz,
                                      Algorithm_9Axis) ==
               IMU_UART_TX_ERROR);
    tx_length = HostPlatformMock_UartTxTake(
        PROJECT_RESOURCE_IMU_UART, tx, sizeof(tx));
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_SAVE) == 0U);
}

static void Test_RegisterReadAsync(void)
{
    uint8_t response[IMU_FRAME_LEN];
    uint16_t value = 0U;

    HostPlatformMock_Reset();
    TEST_CHECK(IMU_LocalGravitySet(SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init() == IMU_OK);
    TEST_CHECK(IMU_RegisterReadAsyncStart(0U, IMU_REG_RRATE) ==
               Jy901bRegisterReadStartResult_Ok);
    TEST_CHECK(IMU_RegisterReadAsyncStart(0U, IMU_REG_RRATE) ==
               Jy901bRegisterReadStartResult_Busy);
    TEST_CHECK(IMU_RegisterReadAsyncPoll(0U, &value) ==
               Jy901bRegisterReadPollResult_Pending);
    Test_FrameBuild(IMU_REG_READ_RESPONSE, 0x1234, 0, 0, 0, response);
    TEST_CHECK(HostPlatformMock_UartRxInject(PROJECT_RESOURCE_IMU_UART,
                   response, sizeof(response)) == sizeof(response));
    IMU_Poll();
    TEST_CHECK(IMU_RegisterReadAsyncPoll(0U, &value) ==
               Jy901bRegisterReadPollResult_Complete);
    TEST_CHECK(value == 0x1234U);
    TEST_CHECK(IMU_RegisterReadAsyncStart(0U, IMU_REG_RRATE) ==
               Jy901bRegisterReadStartResult_Ok);
    HostPlatformMock_TimeAdvanceUs(
        ((uint64_t)IMU_CONFIG_READ_TIMEOUT_MS + 1ULL) * 1000ULL);
    TEST_CHECK(IMU_RegisterReadAsyncPoll(0U, &value) ==
               Jy901bRegisterReadPollResult_Timeout);
}

static void Test_RegisterWriteAsync(void)
{
    uint8_t tx[TEST_TX_BUFFER_CAPACITY];
    uint16_t tx_length;

    HostPlatformMock_Reset();
    TEST_CHECK(IMU_LocalGravitySet(SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init() == IMU_OK);
    TEST_CHECK(IMU_RegisterWriteAsyncStart(0U, IMU_REG_RRATE,
                   OutputRate_200Hz) == Jy901bRegisterWriteStartResult_Ok);
    TEST_CHECK(IMU_RegisterReadAsyncStart(0U, IMU_REG_RRATE) ==
               Jy901bRegisterReadStartResult_Busy);
    TEST_CHECK(IMU_RegisterWriteAsyncPoll(0U) ==
               Jy901bRegisterWritePollResult_Pending);
    HostPlatformMock_TimeAdvanceUs(
        ((uint64_t)IMU_CFG_UNLOCK_DELAY_MS) * 1000ULL);
    TEST_CHECK(IMU_RegisterWriteAsyncPoll(0U) ==
               Jy901bRegisterWritePollResult_Pending);
    HostPlatformMock_TimeAdvanceUs(
        ((uint64_t)IMU_CFG_WRITE_DELAY_MS) * 1000ULL);
    TEST_CHECK(IMU_RegisterWriteAsyncPoll(0U) ==
               Jy901bRegisterWritePollResult_Complete);
    tx_length = HostPlatformMock_UartTxTake(PROJECT_RESOURCE_IMU_UART,
        tx, sizeof(tx));
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_KEY) == 1U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_RRATE) == 1U);
    TEST_CHECK(Test_RegisterWriteCount(tx, tx_length, IMU_REG_SAVE) == 0U);
}

int main(void)
{
    Test_ReturnContentComposition();
    Test_InitUsesPlatformUart();
    Test_ParserAndNativeSample();
    Test_ApplyUsesOneSave();
    Test_WriteFailureDoesNotSave();
    Test_ReadbackMismatchDoesNotSave();
    Test_RegisterReadAsync();
    Test_RegisterWriteAsync();
    return Test_Finish("jy901b_device");
}
