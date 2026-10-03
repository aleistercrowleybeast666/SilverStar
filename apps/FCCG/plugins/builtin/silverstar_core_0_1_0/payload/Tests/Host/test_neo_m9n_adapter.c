#include <stdint.h>
#include <string.h>

#include "debug_log.h"
#include "host_platform_mock.h"
#include "neo_m9n_instance.h"
#include "neo_m9n_device.h"
#include "neo_m9n_startup.h"
#include "neo_m9n_config.h"
#include "project_resources.h"
#include "system_gnss_if.h"
#include "test_common.h"

void DebugLog_Print(const char *fmt, ...)
{
    (void)fmt;
}

#define TEST_NAV_PVT_PAYLOAD_SIZE 92U
#define TEST_NAV_PVT_FRAME_SIZE   (TEST_NAV_PVT_PAYLOAD_SIZE + 8U)

#ifndef PROJECT_RESOURCE_GNSS_UART
#define PROJECT_RESOURCE_GNSS_UART PLATFORM_UART_2
#endif
#define SystemGnss_Init() NeoM9nGnssInstance_Init(0U)
#define SystemGnss_Start() NeoM9nGnssInstance_Start(0U)
#define SystemGnss_Stop() NeoM9nGnssInstance_Stop(0U)
#define SystemGnss_Process() ((void)NeoM9nGnssInstance_Process(0U))
#define SystemGnss_LatestSampleGet(sample) \
    NeoM9nGnssInstance_LatestSampleGet(0U, (sample))

static void Test_U16Put(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
}

static void Test_U32Put(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
    data[2] = (uint8_t)(value >> 16U);
    data[3] = (uint8_t)(value >> 24U);
}

static void Test_NavPvtFrameBuild(uint8_t frame[TEST_NAV_PVT_FRAME_SIZE])
{
    uint8_t *payload = &frame[6];
    uint8_t checksum_a = 0U;
    uint8_t checksum_b = 0U;
    uint16_t index;

    (void)memset(frame, 0, TEST_NAV_PVT_FRAME_SIZE);
    frame[0] = 0xB5U;
    frame[1] = 0x62U;
    frame[2] = 0x01U;
    frame[3] = 0x07U;
    Test_U16Put(&frame[4], TEST_NAV_PVT_PAYLOAD_SIZE);
    payload[20] = 3U;
    payload[21] = 1U;
    payload[23] = 12U;
    Test_U32Put(&payload[24], (uint32_t)1131234567L);
    Test_U32Put(&payload[28], (uint32_t)231234567L);
    Test_U32Put(&payload[32], (uint32_t)123450L);
    Test_U32Put(&payload[36], (uint32_t)120000L);
    Test_U32Put(&payload[40], 1000U);
    Test_U32Put(&payload[44], 1500U);
    Test_U32Put(&payload[48], (uint32_t)2000L);
    Test_U32Put(&payload[52], (uint32_t)(int32_t)-3000L);
    Test_U32Put(&payload[56], (uint32_t)400L);
    Test_U32Put(&payload[68], 100U);
    for (index = 2U; index < (TEST_NAV_PVT_FRAME_SIZE - 2U); index++)
    {
        checksum_a = (uint8_t)(checksum_a + frame[index]);
        checksum_b = (uint8_t)(checksum_b + checksum_a);
    }
    frame[TEST_NAV_PVT_FRAME_SIZE - 2U] = checksum_a;
    frame[TEST_NAV_PVT_FRAME_SIZE - 1U] = checksum_b;
}

static void Test_DeviceSampleConvertsToSystemInterface(void)
{
    uint8_t frame[TEST_NAV_PVT_FRAME_SIZE];
    SystemGnssSample sample;

    HostPlatformMock_Reset();
    HostPlatformMock_TimeSetUs(1000000ULL);
    TEST_CHECK(SystemGnss_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemGnss_Start() == SYSTEM_DEVICE_OK);
    Test_NavPvtFrameBuild(frame);
    TEST_CHECK(HostPlatformMock_UartRxInject(
        PROJECT_RESOURCE_GNSS_UART, frame, sizeof(frame)) == sizeof(frame));
    SystemGnss_Process();
    TEST_CHECK(SystemGnss_LatestSampleGet(&sample) == SYSTEM_DEVICE_OK);
    TEST_CHECK(sample.latitude_e7 == 231234567L);
    TEST_CHECK(sample.longitude_e7 == 1131234567L);
    TEST_CHECK(sample.ellipsoid_height_mm == 123450L);
    TEST_CHECK_NEAR(sample.velocity_enu_mps[0], -3.0f, 1.0e-6f);
    TEST_CHECK_NEAR(sample.velocity_enu_mps[1], 2.0f, 1.0e-6f);
    TEST_CHECK_NEAR(sample.velocity_enu_mps[2], -0.4f, 1.0e-6f);
    TEST_CHECK_NEAR(sample.horizontal_accuracy_m, 1.0f, 1.0e-6f);
    TEST_CHECK_NEAR(sample.vertical_accuracy_m, 1.5f, 1.0e-6f);
    TEST_CHECK(sample.position_usable != 0U);
    TEST_CHECK(sample.velocity_valid_mask == 0x07U);
    TEST_CHECK(SystemGnss_Stop() == SYSTEM_DEVICE_OK);
}


/* A fresh, checksum-valid position stream restores transport only. Configured
 * adapters must withhold navigation samples until identity/readback succeeds. */
static void Test_UnidentifiedRecoveryCannotSupplyNavigation(void)
{
    uint8_t frame[TEST_NAV_PVT_FRAME_SIZE];
    SystemGnssConfig target = {0U};
    SystemGnssSample sample;
    SystemDeviceHealth health;
    SystemDeviceConfigReport report;
    SystemGnssHardwareConfig hardware;
    GnssNeoM9nData raw;
    NeoM9nStartupRecoveryDiagnostics recovery;
    uint32_t baudrate = 0U;
    uint32_t cycle;
    uint32_t first_error_count = 0U;
    uint8_t owner_active = 0U;

    TEST_CHECK(SystemGnss_Start() == SYSTEM_DEVICE_OK);
    target.requested_mask = SYSTEM_GNSS_CFG_NAVIGATION_RATE |
        SYSTEM_GNSS_CFG_CONSTELLATIONS | SYSTEM_GNSS_CFG_DYNAMIC_MODEL |
        SYSTEM_GNSS_CFG_OUTPUT_PROTOCOL | SYSTEM_GNSS_CFG_ENABLED_MESSAGES;
    target.navigation_rate_hz = 25U;
    target.constellation_mask = SYSTEM_GNSS_CONSTELLATION_GPS;
    target.dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G;
    target.output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    target.enabled_message_mask = SYSTEM_GNSS_MESSAGE_NAV_PVT;
    TEST_CHECK(NeoM9nGnssInstance_ConfigApply(0U, &target, &report) ==
        SYSTEM_DEVICE_CONFIG_DELEGATED);
    Test_NavPvtFrameBuild(frame);
    for (cycle = 0U; cycle < 4500U; cycle++)
    {
        HostPlatformMock_TimeAdvanceUs(10000ULL);
        TEST_CHECK(PlatformUart_BaudGet(PROJECT_RESOURCE_GNSS_UART,
            &baudrate) == PLATFORM_OK);
        if (baudrate == GNSS_DEFAULT_BAUDRATE)
        {
            TEST_CHECK(HostPlatformMock_UartRxInject(PROJECT_RESOURCE_GNSS_UART,
                frame, sizeof(frame)) == sizeof(frame));
        }
        SystemGnss_Process();
        TEST_CHECK(NeoM9nStartup_RecoveryDiagnosticsGet(0U, &recovery) ==
            NeoM9nStartupResult_Ok);
        if ((owner_active == 0U) &&
            (recovery.state == NeoM9nStartupRecoveryState_Backoff))
        {
            TEST_CHECK(NeoM9nGnssInstance_RuntimeOwnerActivate(0U) == SYSTEM_DEVICE_OK);
            TEST_CHECK(NeoM9nGnssInstance_HardwareConfigRead(0U, &hardware) == SYSTEM_DEVICE_BUSY);
            TEST_CHECK(NeoM9nGnssInstance_HealthGet(0U, &health) == SYSTEM_DEVICE_OK);
            first_error_count = health.error_count;
            owner_active = 1U;
        }
        if (owner_active != 0U)
        { TEST_CHECK(SystemGnss_LatestSampleGet(&sample) == SYSTEM_DEVICE_NOT_READY); }
        if (recovery.state == NeoM9nStartupRecoveryState_Exhausted) { break; }
    }
    TEST_CHECK(owner_active == 1U);
    TEST_CHECK(recovery.state == NeoM9nStartupRecoveryState_Exhausted);
    TEST_CHECK(recovery.attempt_count == 2U);
    TEST_CHECK(PlatformUart_BaudGet(PROJECT_RESOURCE_GNSS_UART,
        &baudrate) == PLATFORM_OK);
    TEST_CHECK(baudrate == GNSS_DEFAULT_BAUDRATE);
    TEST_CHECK(HostPlatformMock_UartRxInject(PROJECT_RESOURCE_GNSS_UART,
        frame, sizeof(frame)) == sizeof(frame));
    SystemGnss_Process();
    TEST_CHECK(NeoM9nGnssInstance_HealthGet(0U, &health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(GnssNeoM9n_GetData(0U, &raw) != 0U);
    TEST_CHECK(raw.online == 1U && raw.pvtSequence > 0U);
    TEST_CHECK(health.online == 0U && health.healthy == 0U);
    TEST_CHECK(health.error_count == first_error_count);
    TEST_CHECK(SystemGnss_LatestSampleGet(&sample) == SYSTEM_DEVICE_NOT_READY);
    TEST_CHECK(SystemGnss_Stop() == SYSTEM_DEVICE_OK);
}

int main(void)
{
    Test_DeviceSampleConvertsToSystemInterface();
    Test_UnidentifiedRecoveryCannotSupplyNavigation();
    return Test_Finish("neo_m9n_adapter");
}
