#include <stdint.h>
#include <string.h>

#include "hw.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "sx1280-hal.h"
#include "test_common.h"

#define TEST_INSTANCE_COUNT 2U

static uint8_t s_write_reentry_pending;
static uint8_t s_read_reentry_pending;
static uint32_t s_spi_write_count[TEST_INSTANCE_COUNT];
static uint32_t s_spi_read_count[TEST_INSTANCE_COUNT];

PlatformGpioId Sx1281Bus_NssGet(uint8_t instance)
{
    return (PlatformGpioId)(instance + 1U);
}

PlatformGpioId Sx1281Bus_ResetGet(uint8_t instance)
{
    return (PlatformGpioId)(instance + 3U);
}

PlatformGpioId Sx1281Bus_BusyGet(uint8_t instance)
{
    return (PlatformGpioId)(instance + 5U);
}

PlatformGpioId Sx1281Bus_Dio1Get(uint8_t instance)
{
    return (PlatformGpioId)(instance + 7U);
}

void GpioWrite(uint8_t instance, PlatformGpioId id, uint32_t value)
{
    (void)instance;
    (void)id;
    (void)value;
}

uint8_t GpioRead(uint8_t instance, PlatformGpioId id)
{
    (void)instance;
    (void)id;
    return 0U;
}

uint8_t GpioWaitLow(
    uint8_t instance, PlatformGpioId id, uint32_t timeout_ms)
{
    (void)instance;
    (void)id;
    (void)timeout_ms;
    return 1U;
}

void SpiIn(uint8_t instance, const uint8_t *tx_buffer, uint16_t size)
{
    static uint8_t nested_payload[] = {0xB1U, 0xB2U, 0xB3U};

    if (instance >= TEST_INSTANCE_COUNT)
    {
        TEST_CHECK(0);
        return;
    }
    s_spi_write_count[instance]++;
    if ((instance == 0U) && (s_write_reentry_pending != 0U))
    {
        s_write_reentry_pending = 0U;
        SX1280HalWriteCommand(
            1U, RADIO_SET_RFFREQUENCY,
            nested_payload, (uint16_t)sizeof(nested_payload));
        TEST_CHECK(size == 3U);
        TEST_CHECK(tx_buffer[0] == (uint8_t)RADIO_SET_PACKETTYPE);
        TEST_CHECK(tx_buffer[1] == 0xA1U);
        TEST_CHECK(tx_buffer[2] == 0xA2U);
    }
    else if (instance == 1U)
    {
        TEST_CHECK(size == 4U);
        TEST_CHECK(tx_buffer[0] == (uint8_t)RADIO_SET_RFFREQUENCY);
        TEST_CHECK(memcmp(&tx_buffer[1], nested_payload,
                          sizeof(nested_payload)) == 0);
    }
}

void SpiInOut(
    uint8_t instance, const uint8_t *tx_buffer,
    uint8_t *rx_buffer, uint16_t size)
{
    uint8_t nested_result[2] = {0U, 0U};

    if (instance >= TEST_INSTANCE_COUNT)
    {
        TEST_CHECK(0);
        return;
    }
    TEST_CHECK(size == 4U);
    s_spi_read_count[instance]++;
    if ((instance == 0U) && (s_read_reentry_pending != 0U))
    {
        TEST_CHECK(tx_buffer[0] == (uint8_t)RADIO_GET_PACKETTYPE);
        rx_buffer[2] = 0xC1U;
        rx_buffer[3] = 0xC2U;
        s_read_reentry_pending = 0U;
        SX1280HalReadCommand(
            1U, RADIO_GET_RSSIINST,
            nested_result, (uint16_t)sizeof(nested_result));
        TEST_CHECK(nested_result[0] == 0xD1U);
        TEST_CHECK(nested_result[1] == 0xD2U);
    }
    else if (instance == 1U)
    {
        TEST_CHECK(tx_buffer[0] == (uint8_t)RADIO_GET_RSSIINST);
        rx_buffer[2] = 0xD1U;
        rx_buffer[3] = 0xD2U;
    }
}

PlatformCriticalState PlatformCritical_Enter(void)
{
    return 0U;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    (void)state;
}

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    (void)delay_ms;
}

static void Test_HalWorkspaceIsolation(void)
{
    uint8_t write_payload[] = {0xA1U, 0xA2U};
    uint8_t read_result[2] = {0U, 0U};

    (void)memset(s_spi_write_count, 0, sizeof(s_spi_write_count));
    (void)memset(s_spi_read_count, 0, sizeof(s_spi_read_count));
    s_write_reentry_pending = 1U;
    SX1280HalWriteCommand(
        0U, RADIO_SET_PACKETTYPE,
        write_payload, (uint16_t)sizeof(write_payload));
    TEST_CHECK(s_write_reentry_pending == 0U);
    TEST_CHECK(s_spi_write_count[0] == 1U);
    TEST_CHECK(s_spi_write_count[1] == 1U);

    s_read_reentry_pending = 1U;
    SX1280HalReadCommand(
        0U, RADIO_GET_PACKETTYPE,
        read_result, (uint16_t)sizeof(read_result));
    TEST_CHECK(s_read_reentry_pending == 0U);
    TEST_CHECK(s_spi_read_count[0] == 1U);
    TEST_CHECK(s_spi_read_count[1] == 1U);
    TEST_CHECK(read_result[0] == 0xC1U);
    TEST_CHECK(read_result[1] == 0xC2U);
}

int main(void)
{
    _Static_assert(PROJECT_SX1281_INSTANCE_COUNT == TEST_INSTANCE_COUNT,
        "multi-instance SX1280 HAL fixture must expose two contexts");
    Test_HalWorkspaceIsolation();
    return Test_Finish("sx1280_hal_multi_instance");
}
