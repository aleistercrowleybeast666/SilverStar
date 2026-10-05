#include <stdint.h>

#include "adc_power_config.h"
#include "host_platform_mock.h"
#include "system_power_if.h"
#include "test_common.h"

static void Test_PlatformSampleMapsToCommonInterface(void)
{
    const uint32_t raw_count = 2048U;
    const float pin_voltage =
        ((float)raw_count * ((float)ADC_POWER_NOMINAL_VREF_MV / 1000.0f)) /
        (float)ADC_POWER_FULL_SCALE_COUNT;
    SystemPowerSample sample;
    SystemDeviceHealth health;

    HostPlatformMock_Reset();
    HostPlatformMock_AdcSet(PLATFORM_OK, raw_count);
    TEST_CHECK(SystemPower_Init() == SYSTEM_DEVICE_OK);
    TEST_CHECK(SystemPower_Start() == SYSTEM_DEVICE_OK);
    HostPlatformMock_TimeSetUs(ADC_POWER_SAMPLE_PERIOD_US);
    SystemPower_Process();
    TEST_CHECK(SystemPower_LatestSampleGet(&sample) == SYSTEM_DEVICE_OK);
    TEST_CHECK(sample.sample_timestamp_us == ADC_POWER_SAMPLE_PERIOD_US);
    TEST_CHECK(sample.receive_timestamp_us == sample.sample_timestamp_us);
    TEST_CHECK(sample.sequence == 1U);
    TEST_CHECK_NEAR(sample.voltage_v,
                    (pin_voltage * ADC_POWER_DEFAULT_SCALE) +
                    ADC_POWER_DEFAULT_OFFSET_V,
                    1.0e-5f);
    TEST_CHECK(sample.valid_mask == SYSTEM_POWER_VALID_VOLTAGE);
    TEST_CHECK(SystemPower_HealthGet(&health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(health.sample_count == 1U);
    TEST_CHECK(health.online != 0U && health.healthy != 0U);
}

static void Test_PlatformFailureMapsToHealth(void)
{
    SystemDeviceHealth health;

    HostPlatformMock_AdcSet(PLATFORM_TIMEOUT, 0U);
    HostPlatformMock_TimeAdvanceUs(ADC_POWER_SAMPLE_PERIOD_US);
    SystemPower_Process();
    TEST_CHECK(SystemPower_HealthGet(&health) == SYSTEM_DEVICE_OK);
    TEST_CHECK(health.error_count == 1U);
    TEST_CHECK(health.timeout_count == 1U);
    TEST_CHECK(health.online == 0U && health.healthy == 0U);
}

int main(void)
{
    Test_PlatformSampleMapsToCommonInterface();
    Test_PlatformFailureMapsToHealth();
    return Test_Finish("board_power_service");
}
