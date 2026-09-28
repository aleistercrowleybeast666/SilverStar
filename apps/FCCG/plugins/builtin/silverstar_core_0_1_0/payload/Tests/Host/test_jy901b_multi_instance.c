#include <stdint.h>
#include <string.h>

#include "host_platform_mock.h"
#include "jy901b_device.h"
#include "project_resources.h"
#include "system_user_config.h"
#include "test_common.h"

static uint8_t Test_ChecksumGet(const uint8_t *frame)
{
    uint8_t checksum = 0U;
    uint8_t index;

    for (index = 0U; index < (IMU_FRAME_LEN - 1U); index++)
    { checksum = (uint8_t)(checksum + frame[index]); }
    return checksum;
}

static void Test_S16Write(uint8_t *data, int16_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)((uint16_t)value >> 8U);
}

static void Test_FrameBuild(
    uint8_t type, int16_t x, int16_t y, int16_t z, uint8_t *frame)
{
    (void)memset(frame, 0, IMU_FRAME_LEN);
    frame[0] = IMU_FRAME_HEADER;
    frame[1] = type;
    Test_S16Write(&frame[2], x);
    Test_S16Write(&frame[4], y);
    Test_S16Write(&frame[6], z);
    Test_S16Write(&frame[8], 2500);
    frame[10] = Test_ChecksumGet(frame);
}

static void Test_PairInject(
    PlatformUartId uart, int16_t accel_z, int16_t gyro_x)
{
    uint8_t frames[2U * IMU_FRAME_LEN];

    Test_FrameBuild(IMUFrameAcc, 0, 0, accel_z, &frames[0]);
    Test_FrameBuild(IMUFrameGyro, gyro_x, 0, 0, &frames[IMU_FRAME_LEN]);
    TEST_CHECK(HostPlatformMock_UartRxInject(
        uart, frames, (uint16_t)sizeof(frames)) == sizeof(frames));
}

static void Test_ContextAndStreamIsolation(void)
{
    ProjectJy901bResources resources0;
    ProjectJy901bResources resources1;
    IMUStreamDiagnostics diagnostics0;
    IMUStreamDiagnostics diagnostics1;
    IMUConfig config0;
    IMUConfig config1;
    const IMUData *data0;
    const IMUData *data1;
    uint8_t bad_frame[IMU_FRAME_LEN];

    HostPlatformMock_Reset();
    HostPlatformMock_TimeSetUs(100000ULL);
    TEST_CHECK(ProjectJy901bResources_Get(0U, &resources0) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(ProjectJy901bResources_Get(1U, &resources1) ==
               SYSTEM_DEVICE_OK);
    TEST_CHECK(resources0.uart != resources1.uart);
    TEST_CHECK(IMU_LocalGravitySet(0U, SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_LocalGravitySet(1U, SYSTEM_LOCAL_GRAVITY_MPS2) == IMU_OK);
    TEST_CHECK(IMU_Init(0U) == IMU_OK);
    TEST_CHECK(IMU_Init(1U) == IMU_OK);

    Test_PairInject(resources0.uart, 2048, 111);
    Test_PairInject(resources1.uart, -1024, -222);
    IMU_Poll(0U);
    IMU_Poll(1U);
    data0 = IMU_GetData(0U);
    data1 = IMU_GetData(1U);
    TEST_CHECK(data0 != data1);
    TEST_CHECK(data0->AccRaw[2] == 2048);
    TEST_CHECK(data1->AccRaw[2] == -1024);
    TEST_CHECK(data0->GyroRaw[0] == 111);
    TEST_CHECK(data1->GyroRaw[0] == -222);
    TEST_CHECK(data0->FrameCount == 2U);
    TEST_CHECK(data1->FrameCount == 2U);

    Test_FrameBuild(IMUFrameAcc, 1, 2, 3, bad_frame);
    bad_frame[10] ^= 0x01U;
    TEST_CHECK(HostPlatformMock_UartRxInject(
        resources0.uart, bad_frame, sizeof(bad_frame)) == sizeof(bad_frame));
    IMU_Poll(0U);
    IMU_StreamDiagnosticsGet(0U, &diagnostics0);
    IMU_StreamDiagnosticsGet(1U, &diagnostics1);
    TEST_CHECK(diagnostics0.checksum_error_count == 1U);
    TEST_CHECK(diagnostics1.checksum_error_count == 0U);
    TEST_CHECK(diagnostics0.valid_frame_count == 2U);
    TEST_CHECK(diagnostics1.valid_frame_count == 2U);

    HostPlatformMock_Jy901bEnable(resources1.uart, 1U, 0U);
    TEST_CHECK(IMU_ApplyDefaultConfig(
        1U, OutputRate_100Hz, Algorithm_9Axis) == IMU_OK);
    TEST_CHECK(IMU_GetData(1U)->FrameCount == 0U);
    Test_PairInject(resources1.uart, -1024, -222);
    IMU_Poll(1U);
    IMU_ConfigCacheGet(1U, &config1);
    IMU_Reset(0U);
    IMU_ConfigCacheGet(0U, &config0);
    TEST_CHECK(config0.ValidMask == 0U);
    {
        IMUConfig config1_after;

        IMU_ConfigCacheGet(1U, &config1_after);
        TEST_CHECK(memcmp(&config1, &config1_after, sizeof(config1)) == 0);
        TEST_CHECK(IMU_GetData(1U)->AccRaw[2] == -1024);
    }
}

int main(void)
{
    _Static_assert(PROJECT_JY901B_INSTANCE_COUNT == 2U,
        "multi-instance JY901B Host fixture must expose two contexts");
    Test_ContextAndStreamIsolation();
    return Test_Finish("jy901b_multi_instance");
}
