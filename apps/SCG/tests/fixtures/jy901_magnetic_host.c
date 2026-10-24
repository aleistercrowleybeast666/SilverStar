#include <limits.h>
#include <stdint.h>
#include <string.h>

#include "debug_log.h"
#include "host_platform_mock.h"
#include "jy901b_config.h"
#include "jy901b_instance.h"
#include "jy901b_startup.h"
#include "platform_time.h"
#include "system_magnetometer_if.h"
#include "test_common.h"

void DebugLog_Print(const char *fmt, ...) { (void)fmt; }

static void Test_FrameInject(uint8_t instance, uint8_t type, int16_t x,
    int16_t y, int16_t z, uint16_t tail, uint8_t bad_checksum)
{
    uint8_t frame[IMU_FRAME_LEN] = {IMU_FRAME_HEADER, 0U};
    uint16_t words[4] = {(uint16_t)x, (uint16_t)y, (uint16_t)z, tail};
    ProjectJy901bResources resources;
    uint8_t index;

    TEST_CHECK(ProjectJy901bResources_Get(instance, &resources) == SYSTEM_DEVICE_OK);
    frame[1] = type;
    for (index = 0U; index < 4U; index++)
    {
        frame[2U + 2U * index] = (uint8_t)words[index];
        frame[3U + 2U * index] = (uint8_t)(words[index] >> 8U);
    }
    for (index = 0U; index < 10U; index++)
    { frame[10] = (uint8_t)(frame[10] + frame[index]); }
    frame[10] ^= bad_checksum;
    TEST_CHECK(HostPlatformMock_UartRxInject(resources.uart, frame,
        sizeof(frame)) == sizeof(frame));
    TEST_CHECK(Jy901bImuInstance_Process(instance) == SYSTEM_DEVICE_OK);
}

static void Test_Setup(void)
{
    uint8_t instance;
    HostPlatformMock_Reset();
    HostPlatformMock_TimeSetUs(250000ULL);
    for (instance = 0U; instance < PROJECT_JY901B_INSTANCE_COUNT; instance++)
    {
        TEST_CHECK(Jy901bImuInstance_Init(instance) == SYSTEM_DEVICE_OK);
        TEST_CHECK(Jy901bImuInstance_Start(instance) == SYSTEM_DEVICE_OK);
    }
}

static void Test_Masks(void)
{
    uint8_t instance;
    for (instance = 0U; instance < PROJECT_JY901B_INSTANCE_COUNT; instance++)
    {
        uint8_t reg;
        uint16_t mask;
        ProjectJy901bResources resources;
        TEST_CHECK(ProjectJy901bResources_Get(instance, &resources) == SYSTEM_DEVICE_OK);
        TEST_CHECK(IMU_StartupRegisterGet(instance, 9U, OutputRate_200Hz,
            Algorithm_6Axis, &reg, &mask) == Jy901bStartupRegisterResult_Ok);
        TEST_CHECK(reg == 0x02U);
        TEST_CHECK(mask == (uint16_t)((resources.module_variant == 1U ?
            0x0206U : 0x0246U) | (JY901B_MAGNETOMETER_ADAPTER_ENABLE ? 0x10U : 0U)));
        TEST_CHECK((mask & 0x0008U) == 0U); /* User intentionally disabled Euler. */
        TEST_CHECK((mask & 0x0206U) == 0x0206U);
    }
}

static void Test_MagneticSample(void)
{
    uint8_t instance;
    for (instance = 0U; instance < PROJECT_JY901B_INSTANCE_COUNT; instance++)
    {
        SystemMagnetometerSample sample;
        ProjectJy901bResources resources;
        float scale;
        TEST_CHECK(ProjectJy901bResources_Get(instance, &resources) == SYSTEM_DEVICE_OK);
        scale = resources.module_variant == 1U ? 0.008333f : 0.00667f;
        TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(instance, &sample) ==
            SYSTEM_DEVICE_NOT_READY);
        Test_FrameInject(instance, 0x51U, 0, 0, 2048, 2500U, 0U);
        Test_FrameInject(instance, 0x52U, 0, 0, 0, 2500U, 0U);
        TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(instance, &sample) ==
            SYSTEM_DEVICE_NOT_READY);
        Test_FrameInject(instance, 0x54U, INT16_MIN, 1234, INT16_MAX, 0x7FFFU, 0U);
        TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(instance, &sample) ==
            SYSTEM_DEVICE_OK);
        TEST_CHECK(sample.sequence == 1U);
        TEST_CHECK(sample.raw[0] == INT16_MIN && sample.raw[1] == 1234 &&
            sample.raw[2] == INT16_MAX);
        TEST_CHECK_NEAR(sample.magnetic_field_b_uT[1], 1234.0f * scale, 0.00001f);
        TEST_CHECK(sample.sample_timestamp_us == 250000ULL);
        TEST_CHECK(sample.receive_timestamp_us == sample.sample_timestamp_us);
        TEST_CHECK(sample.calibration_valid == 0U);
        TEST_CHECK((sample.valid_mask & SYSTEM_MAG_VALID_CALIBRATED) == 0U);
        Test_FrameInject(instance, 0x54U, 1, 2, 3, 0U, 1U);
        TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(instance, &sample) ==
            SYSTEM_DEVICE_OK);
        TEST_CHECK(sample.sequence == 1U && sample.raw[0] == INT16_MIN);
    }
}

static void Test_ReservedTail(void)
{
    SystemMagnetometerSample sample;
    uint32_t capabilities;
    Test_FrameInject(0U, 0x51U, 0, 0, 2048, 2500U, 0U);
    Test_FrameInject(0U, 0x54U, 100, -200, 300, 0x7FFFU, 0U);
    TEST_CHECK_NEAR(IMU_GetData(0U)->TemperatureC, 25.0f, 0.00001f);
    TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(0U, &sample) == SYSTEM_DEVICE_OK);
    TEST_CHECK((sample.valid_mask & SYSTEM_MAG_VALID_TEMPERATURE) == 0U);
    TEST_CHECK(Jy901bMagnetometerInstance_CapabilitiesGet(0U, &capabilities) == SYSTEM_DEVICE_OK);
    TEST_CHECK((capabilities & SYSTEM_MAG_CAP_TEMPERATURE) == 0U);
}

static void Test_StaleMagneticFrame(void)
{
    SystemMagnetometerSample sample;
    Test_FrameInject(0U, 0x54U, 100, -200, 300, 0U, 0U);
    HostPlatformMock_TimeAdvanceUs(100000ULL);
    TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(0U, &sample) == SYSTEM_DEVICE_OK);
    HostPlatformMock_TimeAdvanceUs(1ULL);
    Test_FrameInject(0U, 0x51U, 0, 0, 2048, 2500U, 0U);
    TEST_CHECK(IMU_IsOnline(0U) != 0U);
    TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(0U, &sample) == SYSTEM_DEVICE_TIMEOUT);
    HostPlatformMock_TimeSetUs(249999ULL);
    TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(0U, &sample) == SYSTEM_DEVICE_TIMEOUT);
}

static void Test_Disabled(void)
{
    SystemMagnetometerSample sample;
    const IMUData *state;
    Test_FrameInject(0U, 0x54U, 100, -200, 300, 0U, 0U);
    TEST_CHECK(Jy901bMagnetometerInstance_LatestSampleGet(0U, &sample) == SYSTEM_DEVICE_UNSUPPORTED);
    state = IMU_GetData(0U);
    TEST_CHECK(state != NULL);
    TEST_CHECK(state->MagFrameCount == 0U && state->MagTimestampUs == 0U);
    TEST_CHECK((state->ValidMask & (1U << 3U)) == 0U);
    TEST_CHECK(state->MagRaw[0] == 0 && state->MagRaw[1] == 0 && state->MagRaw[2] == 0);
}

static void Test_StartupMagneticReadback(uint8_t ignore_writes)
{
    ProjectJy901bResources resources;
    uint8_t index;
    uint32_t tick;
    uint8_t tx[2048];
    uint16_t length;
    uint16_t offset;
    TEST_CHECK(ProjectJy901bResources_Get(0U, &resources) == SYSTEM_DEVICE_OK);
    HostPlatformMock_Jy901bEnable(resources.uart, 1U, ignore_writes);
    for (index = 0U; index < JY901B_STARTUP_REGISTER_COUNT; index++)
    {
        uint8_t reg;
        uint16_t expected;
        TEST_CHECK(IMU_StartupRegisterGet(0U, index, OutputRate_200Hz,
            Algorithm_6Axis, &reg, &expected) == Jy901bStartupRegisterResult_Ok);
        if (reg == IMU_REG_RSW) { expected &= (uint16_t)~0x0010U; }
        HostPlatformMock_Jy901bRegisterSet(resources.uart, reg, expected);
    }
    TEST_CHECK(Jy901bStartup_Init(0U, OutputRate_200Hz, Algorithm_6Axis) ==
        Jy901bStartupResult_Ok);
    for (tick = 0U; tick < 1000U; tick++)
    {
        SystemDeviceStartupState state;
        Test_FrameInject(0U, 0x51U, 0, 0, 2048, 2500U, 0U);
        Test_FrameInject(0U, 0x52U, 0, 0, 0, 0U, 0U);
        Jy901bStartup_Tick(0U, PlatformTime_Ms());
        state = Jy901bStartup_StateGet(0U);
        if (state == SystemDeviceStartupState_Ready || state == SystemDeviceStartupState_Failed)
        { break; }
        HostPlatformMock_TimeAdvanceUs(10000ULL);
    }
    TEST_CHECK(Jy901bStartup_StateGet(0U) == (ignore_writes ?
        SystemDeviceStartupState_Failed : SystemDeviceStartupState_Ready));
    TEST_CHECK((HostPlatformMock_Jy901bRegisterGet(resources.uart, IMU_REG_RSW) & 0x0010U)
        == (ignore_writes ? 0U : 0x0010U));
    length = HostPlatformMock_UartTxTake(resources.uart, tx, sizeof(tx));
    for (offset = 0U; offset + IMU_CFG_FRAME_LEN <= length; offset += IMU_CFG_FRAME_LEN)
    { TEST_CHECK(tx[offset + 2U] != IMU_REG_SAVE); }
}

int main(int argc, char **argv)
{
    TEST_CHECK(argc == 2);
    Test_Setup();
    if (strcmp(argv[1], "mask") == 0) { Test_Masks(); }
    else if (strcmp(argv[1], "sample") == 0) { Test_MagneticSample(); }
    else if (strcmp(argv[1], "reserved_tail") == 0) { Test_ReservedTail(); }
    else if (strcmp(argv[1], "stale") == 0) { Test_StaleMagneticFrame(); }
    else if (strcmp(argv[1], "disabled") == 0) { Test_Disabled(); }
    else if (strcmp(argv[1], "startup") == 0) { Test_StartupMagneticReadback(0U); }
    else if (strcmp(argv[1], "readback_rejected") == 0) { Test_StartupMagneticReadback(1U); }
    else { TEST_CHECK(0); }
    return Test_Finish("jy901_magnetic");
}
