#include <stdint.h>
#include <string.h>

#include "project_resources.h"
#include "neo_m9n_config.h"
#include "neo_m9n_config_keys.h"
#include "neo_m9n_device.h"
#include "neo_m9n_startup.h"
#include "platform_critical.h"
#include "platform_time.h"
#include "platform_uart.h"
#include "test_common.h"

#define TEST_UBX_SYNC1 0xB5U
#define TEST_UBX_SYNC2 0x62U
#define TEST_CFG_CLASS 0x06U
#define TEST_VALGET_ID 0x8BU
#define TEST_ACK_CLASS 0x05U
#define TEST_ACK_NAK_ID 0x00U
#define TEST_NAV_CLASS 0x01U
#define TEST_NAV_SAT_ID 0x35U
#define TEST_MON_CLASS 0x0AU
#define TEST_MON_RF_ID 0x38U
#define TEST_FAILURE_KEY 0x30210002UL
#define TEST_FRAME_CAPACITY 128U
#define TEST_RX_CAPACITY 8192U
#ifndef PROJECT_RESOURCE_GNSS_UART
#define PROJECT_RESOURCE_GNSS_UART PLATFORM_UART_2
#endif

/* Exercise instance zero in the legacy single-receiver scenarios. */
#define GnssNeoM9n_Init() GnssNeoM9n_Init(0U)
#define GnssNeoM9n_Process(now_ms) GnssNeoM9n_Process(0U, (now_ms))
#define GnssNeoM9n_ReadHardwareConfig(out, elapsed, diagnostics) \
    GnssNeoM9n_ReadHardwareConfig(0U, (out), (elapsed), (diagnostics))
#define GnssNeoM9n_ValgetRead(keys, count, diagnostics) \
    GnssNeoM9n_ValgetRead(0U, (keys), (count), (diagnostics))
#define GnssNeoM9n_ReadSatelliteDiagnostics(diagnostics) \
    GnssNeoM9n_ReadSatelliteDiagnostics(0U, (diagnostics))
#define GnssNeoM9n_ReadRfDiagnostics(diagnostics) \
    GnssNeoM9n_ReadRfDiagnostics(0U, (diagnostics))
#define GnssNeoM9n_ConfigReadAsyncStart() \
    GnssNeoM9n_ConfigReadAsyncStart(0U)
#define GnssNeoM9n_ConfigReadAsyncPoll(out, elapsed, diagnostics, result) \
    GnssNeoM9n_ConfigReadAsyncPoll(0U, (out), (elapsed), (diagnostics), (result))
#define GnssNeoM9n_SatelliteDiagnosticsAsyncStart() \
    GnssNeoM9n_SatelliteDiagnosticsAsyncStart(0U)
#define GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(diagnostics) \
    GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(0U, (diagnostics))
#define GnssNeoM9n_RfDiagnosticsAsyncStart() \
    GnssNeoM9n_RfDiagnosticsAsyncStart(0U)
#define GnssNeoM9n_RfDiagnosticsAsyncPoll(diagnostics) \
    GnssNeoM9n_RfDiagnosticsAsyncPoll(0U, (diagnostics))

typedef enum
{
    TEST_RESPONSE_OK = 0,
    TEST_RESPONSE_GROUP_NAK,
    TEST_RESPONSE_NAK,
    TEST_RESPONSE_TX_ERROR,
    TEST_RESPONSE_CHECKSUM_ERROR,
    TEST_RESPONSE_MALFORMED,
    TEST_RESPONSE_BAD_LAYER,
    TEST_RESPONSE_BAD_POSITION,
    TEST_RESPONSE_BAD_LENGTH,
    TEST_RESPONSE_BAD_VALUE_LENGTH,
    TEST_RESPONSE_KEY_MISMATCH,
    TEST_RESPONSE_NAV_ZERO,
    TEST_RESPONSE_NAV_BAD_VERSION,
    TEST_RESPONSE_NAV_BAD_LENGTH,
    TEST_RESPONSE_NAV_COUNT_OVERFLOW,
    TEST_RESPONSE_UNRELATED_PVT,
    TEST_RESPONSE_DISCONTINUITY,
    TEST_RESPONSE_TIMEOUT
} TestResponseMode;

static uint8_t s_rx_buffer[TEST_RX_CAPACITY];
static uint16_t s_rx_head;
static uint16_t s_rx_tail;
static uint16_t s_rx_count;
static uint32_t s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
static PlatformUartDiagnostics s_uart_diagnostics;
static uint32_t s_tick_ms = 100U;
static TestResponseMode s_mode;
static uint8_t s_request_version_valid;
static uint16_t s_layer_measurement_ms[3] = {40U, 40U, 40U};
static uint32_t s_layer_writes[3];
static uint8_t s_ignore_config_write;
static uint8_t s_drop_config_ack;
static const uint8_t s_captured_monver[168] = {
    0xB5U, 0x62U, 0x0AU, 0x04U, 0xA0U, 0x00U, 0x52U, 0x4FU, 0x4DU, 0x20U, 0x43U, 0x4FU,
    0x52U, 0x45U, 0x20U, 0x34U, 0x2EU, 0x30U, 0x34U, 0x20U, 0x28U, 0x64U, 0x39U, 0x36U,
    0x34U, 0x66U, 0x34U, 0x29U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U,
    0x30U, 0x30U, 0x31U, 0x39U, 0x30U, 0x30U, 0x30U, 0x30U, 0x00U, 0x00U, 0x46U, 0x57U,
    0x56U, 0x45U, 0x52U, 0x3DU, 0x53U, 0x50U, 0x47U, 0x20U, 0x34U, 0x2EU, 0x30U, 0x34U,
    0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U,
    0x00U, 0x00U, 0x00U, 0x00U, 0x50U, 0x52U, 0x4FU, 0x54U, 0x56U, 0x45U, 0x52U, 0x3DU,
    0x33U, 0x32U, 0x2EU, 0x30U, 0x31U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U,
    0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x47U, 0x50U,
    0x53U, 0x3BU, 0x47U, 0x4CU, 0x4FU, 0x3BU, 0x47U, 0x41U, 0x4CU, 0x3BU, 0x42U, 0x44U,
    0x53U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U,
    0x00U, 0x00U, 0x00U, 0x00U, 0x53U, 0x42U, 0x41U, 0x53U, 0x3BU, 0x51U, 0x5AU, 0x53U,
    0x53U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U,
    0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x00U, 0x40U, 0x41U,
};
static uint8_t s_use_captured;
static uint32_t s_capability_reject_key;
static uint8_t s_wrong_model;
static const char *s_test_protocol = "PROTVER=27.12";
static uint8_t s_monver_silent;
static uint32_t s_signal_reset_until;
static uint8_t s_async_busy_once;
static uint8_t s_startup_item_mode;
static uint32_t s_startup_physical_baud;
static uint32_t s_startup_last_write_key;
static uint8_t s_startup_write_count;
static GnssNeoM9nConfigItem s_startup_items[32];
static uint8_t s_startup_item_count;
static uint8_t s_startup_nmea_only;
static uint8_t s_startup_nmea_bad_checksum;
static uint8_t s_startup_ubx_enabled;
static uint8_t s_startup_pubx_count;
static uint8_t s_startup_pubx_fail;
static uint8_t s_startup_nmea_count;
static uint32_t s_startup_next_nmea_ms;
static uint8_t s_recovery_test_active;
static uint8_t s_recovery_baud_fail;
static uint32_t s_recovery_mon_requests;
static uint32_t s_recovery_baud_changes;

static uint16_t Test_ReadU16Le(const uint8_t *data)
{
    return (uint16_t)((uint16_t)data[0] | ((uint16_t)data[1] << 8U));
}

static uint32_t Test_ReadU32Le(const uint8_t *data)
{
    return (uint32_t)data[0] |
        ((uint32_t)data[1] << 8U) |
        ((uint32_t)data[2] << 16U) |
        ((uint32_t)data[3] << 24U);
}

static void Test_WriteU16Le(uint8_t *data, uint16_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
}

static void Test_WriteU32Le(uint8_t *data, uint32_t value)
{
    data[0] = (uint8_t)value;
    data[1] = (uint8_t)(value >> 8U);
    data[2] = (uint8_t)(value >> 16U);
    data[3] = (uint8_t)(value >> 24U);
}

static void Test_WriteU64Le(uint8_t *data, uint64_t value)
{
    Test_WriteU32Le(data, (uint32_t)value);
    Test_WriteU32Le(&data[4], (uint32_t)(value >> 32U));
}

static uint16_t Test_FrameBuild(uint8_t message_class,
                                uint8_t message_id,
                                const uint8_t *payload,
                                uint16_t payload_length,
                                uint8_t *frame)
{
    uint8_t ck_a = 0U;
    uint8_t ck_b = 0U;
    uint16_t index;

    frame[0] = TEST_UBX_SYNC1;
    frame[1] = TEST_UBX_SYNC2;
    frame[2] = message_class;
    frame[3] = message_id;
    Test_WriteU16Le(&frame[4], payload_length);
    if (payload_length != 0U)
    {
        (void)memcpy(&frame[6], payload, payload_length);
    }
    for (index = 2U; index < (uint16_t)(6U + payload_length); index++)
    {
        ck_a = (uint8_t)(ck_a + frame[index]);
        ck_b = (uint8_t)(ck_b + ck_a);
    }
    frame[6U + payload_length] = ck_a;
    frame[7U + payload_length] = ck_b;
    return (uint16_t)(payload_length + 8U);
}

static void Test_FrameInject(uint8_t *frame, uint16_t length,
                             uint8_t corrupt_checksum)
{
    uint16_t offset;

    TEST_CHECK(length <= (uint16_t)(TEST_RX_CAPACITY - s_rx_count));
    if (corrupt_checksum != 0U) { frame[length - 1U] ^= 0x01U; }
    for (offset = 0U; offset < length; offset++)
    {
        s_rx_buffer[s_rx_head] = frame[offset];
        s_rx_head = (uint16_t)((s_rx_head + 1U) % TEST_RX_CAPACITY);
        s_rx_count++;
    }
    s_uart_diagnostics.rx_bytes += length;
    s_uart_diagnostics.rx_event_count++;
    s_uart_diagnostics.rx_active = 1U;
}

static void Test_NmeaInject(uint8_t corrupt_checksum)
{
    static const char body[] = "GPGGA,1";
    static const char hex[] = "0123456789ABCDEF";
    uint8_t frame[16U];
    uint8_t checksum = 0U;
    uint16_t index;
    uint16_t length = 0U;

    frame[length++] = (uint8_t)'$';
    for (index = 0U; index < sizeof(body) - 1U; index++)
    {
        checksum ^= (uint8_t)body[index];
        frame[length++] = (uint8_t)body[index];
    }
    if (corrupt_checksum != 0U) { checksum ^= 1U; }
    frame[length++] = (uint8_t)'*';
    frame[length++] = (uint8_t)hex[checksum >> 4U];
    frame[length++] = (uint8_t)hex[checksum & 0x0FU];
    frame[length++] = (uint8_t)'\r';
    frame[length++] = (uint8_t)'\n';
    Test_FrameInject(frame, length, 0U);
}

static uint8_t Test_KeyValueLength(uint32_t key)
{
    uint8_t type = (uint8_t)(key >> 28U);

    if (type == 5U) { return 8U; }
    if (type == 4U) { return 4U; }
    if (type == 3U) { return 2U; }
    return 1U;
}

static uint64_t Test_KeyValue(uint32_t key)
{
    uint8_t index;

    if (s_startup_item_mode != 0U)
    {
        if (key == 0x40520001UL)
        { return s_startup_physical_baud; }
        for (index = 0U; index < s_startup_item_count; index++)
        {
            if (s_startup_items[index].key == key)
            { return s_startup_items[index].value; }
        }
    }
    if (key == 0x40520001UL) { return GNSS_DEFAULT_BAUDRATE; }
    if (key == 0x30210001UL) { return 40U; }
    if (key == 0x20110021UL) { return GNSS_DYNMODEL_AIRBORNE_4G; }
    if (key == 0x10740002UL) { return 0U; }
    return 1U;
}

static uint8_t Test_RequestContainsKey(const uint8_t *payload,
                                       uint16_t payload_length,
                                       uint32_t key)
{
    uint16_t offset;

    for (offset = 4U; (uint16_t)(offset + 4U) <= payload_length;
         offset = (uint16_t)(offset + 4U))
    {
        if (Test_ReadU32Le(&payload[offset]) == key) { return 1U; }
    }
    return 0U;
}

static void Test_ValgetRespond(const uint8_t *request_payload,
                               uint16_t request_length)
{
    uint8_t payload[TEST_FRAME_CAPACITY];
    uint8_t frame[TEST_FRAME_CAPACITY];
    uint16_t response_length = 4U;
    uint16_t offset;
    uint16_t frame_length;
    uint32_t key;
    uint64_t value;
    uint8_t value_length;
    uint8_t contains_failure = Test_RequestContainsKey(
        request_payload, request_length, TEST_FAILURE_KEY);
    uint8_t key_count = (uint8_t)((request_length - 4U) / 4U);

    if ((s_mode == TEST_RESPONSE_TIMEOUT) && (contains_failure != 0U))
    {
        return;
    }
    if ((s_mode == TEST_RESPONSE_UNRELATED_PVT) &&
        (contains_failure != 0U))
    {
        uint8_t pvt_payload[92];

        (void)memset(pvt_payload, 0, sizeof(pvt_payload));
        frame_length = Test_FrameBuild(TEST_NAV_CLASS, 0x07U,
                                       pvt_payload,
                                       sizeof(pvt_payload), frame);
        Test_FrameInject(frame, frame_length, 0U);
        return;
    }
    if ((s_mode == TEST_RESPONSE_NAK) && (contains_failure != 0U))
    {
        const uint8_t nak_payload[2] = {TEST_CFG_CLASS, TEST_VALGET_ID};
        frame_length = Test_FrameBuild(TEST_ACK_CLASS, TEST_ACK_NAK_ID,
                                       nak_payload, 2U, frame);
        Test_FrameInject(frame, frame_length, 0U);
        return;
    }
    if ((s_mode == TEST_RESPONSE_GROUP_NAK) && (key_count > 1U))
    {
        const uint8_t nak_payload[2] = {TEST_CFG_CLASS, TEST_VALGET_ID};
        frame_length = Test_FrameBuild(TEST_ACK_CLASS, TEST_ACK_NAK_ID,
                                       nak_payload, 2U, frame);
        Test_FrameInject(frame, frame_length, 0U);
        return;
    }
    if ((s_mode == TEST_RESPONSE_MALFORMED) &&
        (contains_failure != 0U))
    {
        (void)memset(payload, 0, 4U);
        frame_length = Test_FrameBuild(TEST_CFG_CLASS, TEST_VALGET_ID,
                                       payload, 4U, frame);
        Test_FrameInject(frame, frame_length, 0U);
        return;
    }

    if ((s_mode == TEST_RESPONSE_BAD_LENGTH) &&
        (contains_failure != 0U))
    {
        (void)memset(payload, 0, sizeof(payload));
        payload[0] = 0x01U;
        frame_length = Test_FrameBuild(TEST_CFG_CLASS, TEST_VALGET_ID,
                                       payload, 4U, frame);
        Test_FrameInject(frame, frame_length, 0U);
        return;
    }
    if ((s_mode == TEST_RESPONSE_BAD_VALUE_LENGTH) &&
        (contains_failure != 0U))
    {
        (void)memset(payload, 0, sizeof(payload));
        payload[0] = 0x01U;
        Test_WriteU32Le(&payload[4], TEST_FAILURE_KEY);
        payload[8] = 0x01U;
        frame_length = Test_FrameBuild(TEST_CFG_CLASS, TEST_VALGET_ID,
                                       payload, 9U, frame);
        Test_FrameInject(frame, frame_length, 0U);
        return;
    }

    (void)memset(payload, 0, sizeof(payload));
    payload[0] = 0x01U;
    payload[1] = (uint8_t)(((s_mode == TEST_RESPONSE_BAD_LAYER) &&
                            (contains_failure != 0U)) ? 0x03U : request_payload[1]);
    payload[2] = (uint8_t)(((s_mode == TEST_RESPONSE_BAD_POSITION) &&
                            (contains_failure != 0U)) ? 0x01U : 0x00U);
    payload[3] = 0x00U;
    for (offset = 4U; (uint16_t)(offset + 4U) <= request_length;
         offset = (uint16_t)(offset + 4U))
    {
        key = Test_ReadU32Le(&request_payload[offset]);
        if ((s_mode == TEST_RESPONSE_KEY_MISMATCH) &&
            (contains_failure != 0U) &&
            (key == TEST_FAILURE_KEY))
        {
            key ^= 0x00000001UL;
        }
        value = Test_KeyValue(key);
        if ((s_startup_item_mode == 0U) &&
            (key == 0x30210001UL) && (request_payload[1] < 3U))
        { value = s_layer_measurement_ms[request_payload[1]]; }
        value_length = Test_KeyValueLength(key);
        Test_WriteU32Le(&payload[response_length], key);
        response_length = (uint16_t)(response_length + 4U);
        if (value_length == 8U)
        {
            Test_WriteU64Le(&payload[response_length], value);
        }
        else if (value_length == 4U)
        {
            Test_WriteU32Le(&payload[response_length], (uint32_t)value);
        }
        else if (value_length == 2U)
        {
            Test_WriteU16Le(&payload[response_length], (uint16_t)value);
        }
        else
        {
            payload[response_length] = (uint8_t)value;
        }
        response_length = (uint16_t)(response_length + value_length);
    }
    frame_length = Test_FrameBuild(TEST_CFG_CLASS, TEST_VALGET_ID,
                                   payload, response_length, frame);
    Test_FrameInject(frame, frame_length,
        (uint8_t)((s_mode == TEST_RESPONSE_CHECKSUM_ERROR) &&
                  (contains_failure != 0U)));
}

static void Test_NavSatRespond(void)
{
    uint8_t payload[32];
    uint8_t frame[48];
    uint16_t frame_length;

    (void)memset(payload, 0, sizeof(payload));
    payload[4] = (s_mode == TEST_RESPONSE_NAV_BAD_VERSION) ? 0U : 1U;
    payload[5] = (s_mode == TEST_RESPONSE_NAV_ZERO) ? 0U :
        (s_mode == TEST_RESPONSE_NAV_COUNT_OVERFLOW) ? 0xFFU : 2U;
    payload[10] = 30U;
    Test_WriteU32Le(&payload[16], 0x0CU);
    payload[22] = 40U;
    Test_WriteU32Le(&payload[28], 0x05U);
    frame_length = Test_FrameBuild(
        TEST_NAV_CLASS, TEST_NAV_SAT_ID, payload,
        (s_mode == TEST_RESPONSE_NAV_ZERO) ? 8U :
        (s_mode == TEST_RESPONSE_NAV_BAD_LENGTH) ? 8U :
                                                   (uint16_t)sizeof(payload),
        frame);
    Test_FrameInject(frame, frame_length,
        (uint8_t)(s_mode == TEST_RESPONSE_CHECKSUM_ERROR));
}

static void Test_MonRfRespond(void)
{
    uint8_t payload[28];
    uint8_t frame[40];
    uint16_t frame_length;

    (void)memset(payload, 0, sizeof(payload));
    payload[1] = 1U;
    payload[5] = 0x02U;
    payload[6] = 2U;
    payload[7] = 1U;
    Test_WriteU16Le(&payload[16], 100U);
    Test_WriteU16Le(&payload[18], 200U);
    payload[20] = 7U;
    frame_length = Test_FrameBuild(TEST_MON_CLASS, TEST_MON_RF_ID,
                                   payload, sizeof(payload), frame);
    Test_FrameInject(frame, frame_length, 0U);
}

PlatformResult PlatformUart_Init(PlatformUartId id)
{
    if (id != PROJECT_RESOURCE_GNSS_UART)
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    s_uart_diagnostics.rx_active = 1U;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_Write(PlatformUartId id,
                                  const uint8_t *data,
                                  uint16_t length,
                                  uint32_t timeout_ms)
{
    uint16_t payload_length;
    uint8_t contains_failure;

    (void)timeout_ms;
    if (id != PROJECT_RESOURCE_GNSS_UART)
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    TEST_CHECK(data != NULL && length >= 8U);
    if (data[0] == (uint8_t)'$')
    {
        uint8_t checksum = 0U;
        uint16_t index;
        TEST_CHECK(length < 64U);
        TEST_CHECK(memcmp(data, "$PUBX,41,1,0007,0003,", 21U) == 0);
        TEST_CHECK(data[length - 5U] == (uint8_t)'*');
        TEST_CHECK(data[length - 2U] == (uint8_t)'\r');
        TEST_CHECK(data[length - 1U] == (uint8_t)'\n');
        for (index = 1U; index < length - 5U; index++)
        { checksum ^= data[index]; }
        TEST_CHECK(data[length - 4U] == (uint8_t)"0123456789ABCDEF"[checksum >> 4U]);
        TEST_CHECK(data[length - 3U] == (uint8_t)"0123456789ABCDEF"[checksum & 0x0FU]);
        s_startup_pubx_count++;
        if (s_startup_pubx_fail != 0U) { return PLATFORM_IO_ERROR; }
        s_startup_ubx_enabled = 1U;
        return PLATFORM_OK;
    }
    if ((s_recovery_test_active != 0U) &&
        (data[2] == TEST_MON_CLASS) && (data[3] == 4U))
    { s_recovery_mon_requests++; }
    if (s_startup_item_mode != 0U) { TEST_CHECK(s_tick_ms >= s_signal_reset_until); }
    payload_length = Test_ReadU16Le(&data[4]);
    if ((s_startup_item_mode != 0U) &&
        (s_uart_baudrate != s_startup_physical_baud))
    { return PLATFORM_OK; }
    if (s_mode == TEST_RESPONSE_DISCONTINUITY)
    {
        s_uart_diagnostics.rx_discontinuity_count++;
        s_uart_diagnostics.uart_overrun_error_count++;
        return PLATFORM_OK;
    }
    if ((data[2] == TEST_CFG_CLASS) && (data[3] == TEST_VALGET_ID))
    {
        s_request_version_valid = (uint8_t)((data[6] == 0x00U) &&
            (data[7] == 0x00U) && (data[8] == 0x00U) &&
            (data[9] == 0x00U));
        contains_failure = Test_RequestContainsKey(
            &data[6], payload_length, TEST_FAILURE_KEY);
        if ((s_mode == TEST_RESPONSE_TX_ERROR) &&
            (contains_failure != 0U))
        {
            return PLATFORM_IO_ERROR;
        }
        if ((s_capability_reject_key != 0U) &&
            Test_RequestContainsKey(&data[6], payload_length, s_capability_reject_key))
        {
            uint8_t payload[2] = {TEST_CFG_CLASS, TEST_VALGET_ID};
            uint8_t frame[10];
            (void)Test_FrameBuild(TEST_ACK_CLASS, TEST_ACK_NAK_ID, payload, sizeof(payload), frame);
            Test_FrameInject(frame, sizeof(frame), 0U);
            return PLATFORM_OK;
        }
        Test_ValgetRespond(&data[6], payload_length);
    }
    else if ((data[2] == TEST_NAV_CLASS) &&
             (data[3] == TEST_NAV_SAT_ID))
    {
        Test_NavSatRespond();
    }
    else if ((data[2] == TEST_MON_CLASS) && (data[3] == 4U))
    {
        uint8_t version[130] = {0U};
        uint8_t frame[138];
        uint16_t frame_length;
        if (s_monver_silent != 0U) { return PLATFORM_OK; }
        if ((s_startup_nmea_only != 0U) && (s_startup_ubx_enabled == 0U))
        { return PLATFORM_OK; }
        if (s_use_captured != 0U)
        {
            uint8_t captured[168];
            (void)memcpy(captured, s_captured_monver, sizeof(captured));
            Test_FrameInject(captured, sizeof(captured), 0U);
            return PLATFORM_OK;
        }
        (void)memcpy(&version[40], (s_wrong_model != 0U) ? "MOD=NEO-M8N" : "MOD=NEO-M9N", 11U);
        (void)memcpy(&version[70], s_test_protocol, 13U);
        if (strcmp(s_test_protocol, "PROTVER=32.01") == 0)
        { (void)memcpy(&version[100], "FWVER=SPG 4.04", sizeof("FWVER=SPG 4.04") - 1U); }
        frame_length = Test_FrameBuild(TEST_MON_CLASS, 4U, version, sizeof(version), frame);
        Test_FrameInject(frame, frame_length, 0U);
    }
    else if ((data[2] == TEST_CFG_CLASS) && (data[3] == 0x8AU))
    {
        if (s_startup_item_mode != 0U)
        {
            uint32_t key = Test_ReadU32Le(&data[10]);
            if (s_use_captured != 0U)
            {
                GnssNeoM9nIdentityDiagnostics identity;
                TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &identity) == GnssNeoM9nIdentityOk);
                TEST_CHECK(identity.capability_read_mask == 0x007FFFFFUL);
            }
            uint8_t value_len = Test_KeyValueLength(key);
            uint64_t value = 0U;
            uint8_t index;
            TEST_CHECK(payload_length == (uint16_t)(8U + value_len));
            for (index = 0U; index < value_len; index++)
            { value |= (uint64_t)data[14U + index] << (8U * index); }
            if (((key & 0x0FFF0000UL) == 0x00310000UL) &&
                (strcmp(s_test_protocol, "PROTVER=32.01") == 0))
            { s_signal_reset_until = s_tick_ms + 500U; }
            s_startup_last_write_key = key;
            s_startup_write_count++;
            if (key == 0x40520001UL)
            {
                s_startup_physical_baud = (uint32_t)value;
                return PLATFORM_OK;
            }
            for (index = 0U; index < s_startup_item_count; index++)
            {
                if (s_startup_items[index].key == key) { break; }
            }
            TEST_CHECK(index < 32U);
            if (index == s_startup_item_count)
            { s_startup_item_count++; }
            s_startup_items[index].key = key;
            s_startup_items[index].value = value;
            s_startup_items[index].value_len = value_len;
            {
                uint8_t ack[2] = {TEST_CFG_CLASS, 0x8AU};
                uint8_t frame[16];
                uint16_t frame_length = Test_FrameBuild(
                    TEST_ACK_CLASS, 1U, ack, 2U, frame);
                Test_FrameInject(frame, frame_length, 0U);
            }
            return PLATFORM_OK;
        }
        uint8_t layer;
        uint8_t ack[2] = {TEST_CFG_CLASS, 0x8AU};
        uint8_t frame[16];
        uint16_t frame_length;
        TEST_CHECK(payload_length == 10U);
        TEST_CHECK(Test_ReadU32Le(&data[10]) == 0x30210001UL);
        for (layer = 0U; layer < 3U; layer++)
        {
            if ((data[7] & (uint8_t)(1U << layer)) == 0U) { continue; }
            s_layer_writes[layer]++;
            if (s_ignore_config_write == 0U)
            { s_layer_measurement_ms[layer] = Test_ReadU16Le(&data[14]); }
        }
        if (s_drop_config_ack == 0U)
        {
            frame_length = Test_FrameBuild(TEST_ACK_CLASS, 1U, ack, 2U, frame);
            Test_FrameInject(frame, frame_length, 0U);
        }
    }
    else if ((data[2] == TEST_MON_CLASS) &&
             (data[3] == TEST_MON_RF_ID))
    {
        Test_MonRfRespond();
    }
    s_uart_diagnostics.tx_bytes += length;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_WriteFrameAsync(PlatformUartId id,
    const uint8_t *data, uint16_t length, PlatformUartTxPriority priority)
{
    (void)priority;
    if (s_async_busy_once != 0U)
    {
        s_async_busy_once = 0U;
        return PLATFORM_BUSY;
    }
    return PlatformUart_Write(id, data, length, 0U);
}

PlatformResult PlatformUart_Read(PlatformUartId id,
                                 uint8_t *data,
                                 uint16_t capacity,
                                 uint16_t *read_length)
{
    uint16_t count = 0U;

    if ((id != PROJECT_RESOURCE_GNSS_UART) || (data == NULL) ||
        (read_length == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    if ((s_startup_nmea_only != 0U) &&
        (s_startup_nmea_count == 1U) &&
        (s_uart_baudrate == s_startup_physical_baud) &&
        (s_tick_ms >= s_startup_next_nmea_ms))
    {
        Test_NmeaInject(s_startup_nmea_bad_checksum);
        s_startup_nmea_count = 2U;
    }
    while ((count < capacity) && (s_rx_count != 0U))
    {
        data[count] = s_rx_buffer[s_rx_tail];
        s_rx_tail = (uint16_t)((s_rx_tail + 1U) % TEST_RX_CAPACITY);
        s_rx_count--;
        count++;
    }
    *read_length = count;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_BaudSet(PlatformUartId id, uint32_t baudrate)
{
    if ((id != PROJECT_RESOURCE_GNSS_UART) || (baudrate == 0U))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    if (s_recovery_test_active != 0U)
    {
        s_recovery_baud_changes++;
        if ((s_recovery_baud_fail != 0U) &&
            (baudrate == s_startup_physical_baud) &&
            (s_uart_baudrate != baudrate) && (s_recovery_mon_requests != 0U))
        { return PLATFORM_IO_ERROR; }
    }
    s_uart_baudrate = baudrate;
    if ((s_startup_nmea_only != 0U) &&
        (s_startup_nmea_count == 0U) &&
        (baudrate == s_startup_physical_baud))
    {
        Test_NmeaInject(s_startup_nmea_bad_checksum);
        s_startup_nmea_count = 1U;
        s_startup_next_nmea_ms = s_tick_ms + 1000U;
    }
    return PLATFORM_OK;
}

PlatformResult PlatformUart_BaudGet(PlatformUartId id, uint32_t *baudrate)
{
    if ((id != PROJECT_RESOURCE_GNSS_UART) || (baudrate == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *baudrate = s_uart_baudrate;
    return PLATFORM_OK;
}

PlatformResult PlatformUart_DiagnosticsGet(
    PlatformUartId id, PlatformUartDiagnostics *diagnostics)
{
    if ((id != PROJECT_RESOURCE_GNSS_UART) || (diagnostics == NULL))
    {
        return PLATFORM_INVALID_ARGUMENT;
    }
    *diagnostics = s_uart_diagnostics;
    return PLATFORM_OK;
}

uint32_t PlatformTime_Ms(void)
{
    return s_tick_ms;
}

uint64_t PlatformTime_Us(void)
{
    return (uint64_t)s_tick_ms * 1000ULL;
}

void PlatformTime_DelayMs(uint32_t delay_ms)
{
    s_tick_ms += delay_ms;
}

PlatformCriticalState PlatformCritical_Enter(void)
{
    return 0U;
}

void PlatformCritical_Exit(PlatformCriticalState state)
{
    (void)state;
}

static void Test_ConfigReadMode(TestResponseMode mode,
                                GnssNeoM9nConfigReadResult expected)
{
    GnssNeoM9nConfigSnapshot snapshot;
    GnssNeoM9nConfigReadDiagnostics diagnostics;
    uint32_t elapsed_ms;

    s_mode = mode;
    TEST_CHECK(GnssNeoM9n_ReadHardwareConfig(
        &snapshot, &elapsed_ms, &diagnostics) == expected);
    if (expected == GnssNeoM9nConfigReadResponseOk)
    {
        TEST_CHECK(snapshot.valid_mask == GNSS_CONFIG_VALID_ALL);
        TEST_CHECK(diagnostics.failed_group ==
                   GnssNeoM9nConfigReadGroupNone);
        TEST_CHECK(diagnostics.response_length != 0U);
    }
    else
    {
        TEST_CHECK(diagnostics.result == expected);
        TEST_CHECK(diagnostics.failed_group ==
                   GnssNeoM9nConfigReadGroupRate);
        TEST_CHECK(diagnostics.failed_key == TEST_FAILURE_KEY);
        TEST_CHECK(snapshot.valid_mask != 0U);
        TEST_CHECK((snapshot.valid_mask & GNSS_CONFIG_VALID_RATE) == 0U);
        if (expected == GnssNeoM9nConfigReadNak)
        {
            TEST_CHECK(diagnostics.nak_class == TEST_CFG_CLASS);
            TEST_CHECK(diagnostics.nak_id == TEST_VALGET_ID);
            TEST_CHECK(diagnostics.response_length == 2U);
        }
    }
}

static void Test_ConfigReadResponses(void)
{
    Test_ConfigReadMode(TEST_RESPONSE_OK,
                        GnssNeoM9nConfigReadResponseOk);
    Test_ConfigReadMode(TEST_RESPONSE_GROUP_NAK,
                        GnssNeoM9nConfigReadResponseOk);
    Test_ConfigReadMode(TEST_RESPONSE_NAK, GnssNeoM9nConfigReadNak);
    Test_ConfigReadMode(TEST_RESPONSE_TX_ERROR,
                        GnssNeoM9nConfigReadTxError);
    Test_ConfigReadMode(TEST_RESPONSE_CHECKSUM_ERROR,
                        GnssNeoM9nConfigReadChecksumError);
    Test_ConfigReadMode(TEST_RESPONSE_MALFORMED,
                        GnssNeoM9nConfigReadMalformedResponse);
    Test_ConfigReadMode(TEST_RESPONSE_BAD_LENGTH,
                        GnssNeoM9nConfigReadMalformedResponse);
    Test_ConfigReadMode(TEST_RESPONSE_BAD_VALUE_LENGTH,
                        GnssNeoM9nConfigReadMalformedResponse);
    Test_ConfigReadMode(TEST_RESPONSE_KEY_MISMATCH,
                        GnssNeoM9nConfigReadMalformedResponse);
    Test_ConfigReadMode(TEST_RESPONSE_TIMEOUT,
                        GnssNeoM9nConfigReadTimeout);
    Test_ConfigReadMode(TEST_RESPONSE_UNRELATED_PVT,
                        GnssNeoM9nConfigReadTimeout);
}

static void Test_ValgetVersionsAndKeySizes(void)
{
    static const uint32_t keys[] =
    {
        0x10000001UL,
        0x20000001UL,
        TEST_FAILURE_KEY,
        0x40000001UL,
        0x50000001UL
    };
    GnssNeoM9nConfigReadDiagnostics diagnostics;

    s_mode = TEST_RESPONSE_OK;
    s_request_version_valid = 0U;
    TEST_CHECK(GnssNeoM9n_ValgetRead(
        keys, (uint8_t)(sizeof(keys) / sizeof(keys[0])),
        &diagnostics) == GnssNeoM9nConfigReadResponseOk);
    TEST_CHECK(s_request_version_valid != 0U);
    TEST_CHECK(diagnostics.response_version == 0x01U);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailResponseOk);

    s_mode = TEST_RESPONSE_MALFORMED;
    TEST_CHECK(GnssNeoM9n_ValgetRead(keys, 5U, &diagnostics) ==
               GnssNeoM9nConfigReadMalformedResponse);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailBadVersion);

    s_mode = TEST_RESPONSE_BAD_LAYER;
    TEST_CHECK(GnssNeoM9n_ValgetRead(keys, 5U, &diagnostics) ==
               GnssNeoM9nConfigReadMalformedResponse);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailBadLayer);

    s_mode = TEST_RESPONSE_BAD_POSITION;
    TEST_CHECK(GnssNeoM9n_ValgetRead(keys, 5U, &diagnostics) ==
               GnssNeoM9nConfigReadMalformedResponse);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailBadPosition);

    s_mode = TEST_RESPONSE_BAD_LENGTH;
    TEST_CHECK(GnssNeoM9n_ValgetRead(keys, 5U, &diagnostics) ==
               GnssNeoM9nConfigReadMalformedResponse);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailBadLength);

    s_mode = TEST_RESPONSE_KEY_MISMATCH;
    TEST_CHECK(GnssNeoM9n_ValgetRead(keys, 5U, &diagnostics) ==
               GnssNeoM9nConfigReadMalformedResponse);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailKeyMismatch);

    s_mode = TEST_RESPONSE_BAD_VALUE_LENGTH;
    TEST_CHECK(GnssNeoM9n_ValgetRead(keys, 5U, &diagnostics) ==
               GnssNeoM9nConfigReadMalformedResponse);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailValueLengthMismatch);

    {
        uint8_t payload[10] = {0x01U, 0U, 0U, 0U};
        uint8_t frame[18];
        uint16_t frame_length;

        Test_WriteU32Le(&payload[4], TEST_FAILURE_KEY);
        Test_WriteU16Le(&payload[8], 0x1234U);
        frame_length = Test_FrameBuild(TEST_CFG_CLASS, TEST_VALGET_ID,
                                       payload, sizeof(payload), frame);
        Test_FrameInject(frame, frame_length, 0U);
        s_mode = TEST_RESPONSE_TIMEOUT;
        TEST_CHECK(GnssNeoM9n_ValgetRead(
            &keys[2], 1U, &diagnostics) ==
            GnssNeoM9nConfigReadTimeout);
        TEST_CHECK(diagnostics.detailed_result ==
                   GnssNeoM9nTransactionDetailTimeout);
    }
}

static void Test_DiagnosticParsers(void)
{
    GnssNeoM9nSatelliteDiagnostics satellite;
    GnssNeoM9nRfDiagnostics rf;

    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == 0);
    TEST_CHECK(satellite.satellite_count == 2U);
    TEST_CHECK(satellite.used_count == 1U);
    TEST_CHECK(satellite.average_cno_dbhz == 35U);
    TEST_CHECK(satellite.maximum_cno_dbhz == 40U);
    TEST_CHECK(satellite.average_quality == 4U);

    s_mode = TEST_RESPONSE_NAV_ZERO;
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == 0);
    TEST_CHECK(satellite.satellite_count == 0U && satellite.valid != 0U);

    s_mode = TEST_RESPONSE_NAV_BAD_VERSION;
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == -5);
    TEST_CHECK(satellite.detailed_result ==
               GnssNeoM9nTransactionDetailBadVersion);

    s_mode = TEST_RESPONSE_NAV_BAD_LENGTH;
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == -5);
    TEST_CHECK(satellite.detailed_result ==
               GnssNeoM9nTransactionDetailBadLength);

    s_mode = TEST_RESPONSE_NAV_COUNT_OVERFLOW;
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == -5);
    TEST_CHECK(satellite.detailed_result ==
               GnssNeoM9nTransactionDetailCountOverflow);

    s_mode = TEST_RESPONSE_CHECKSUM_ERROR;
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == -5);
    TEST_CHECK(satellite.detailed_result ==
               GnssNeoM9nTransactionDetailChecksumError);
    TEST_CHECK(satellite.expected_class == TEST_NAV_CLASS);
    TEST_CHECK(satellite.expected_id == TEST_NAV_SAT_ID);
    TEST_CHECK(satellite.received_class == TEST_NAV_CLASS);
    TEST_CHECK(satellite.received_id == TEST_NAV_SAT_ID);
    TEST_CHECK((satellite.expected_ck_a != satellite.received_ck_a) ||
               (satellite.expected_ck_b != satellite.received_ck_b));

    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_ReadRfDiagnostics(&rf) == 0);
    TEST_CHECK(rf.rf_block_count == 1U);
    TEST_CHECK(rf.antenna_status == 2U && rf.antenna_power == 1U);
    TEST_CHECK(rf.noise_per_ms == 100U && rf.agc_count == 200U);
    TEST_CHECK(rf.jamming_indicator == 7U);
    TEST_CHECK(rf.jamming_state == 2U);
    TEST_CHECK(rf.cw_suppression == 7U);
}

static void Test_AsyncRuntimeTransactions(void)
{
    GnssNeoM9nConfigSnapshot snapshot;
    GnssNeoM9nConfigReadDiagnostics diagnostics;
    GnssNeoM9nConfigReadResult result;
    GnssNeoM9nSatelliteDiagnostics satellite;
    GnssNeoM9nRfDiagnostics rf;
    GnssNeoM9nAsyncPollResult poll_result;
    uint32_t elapsed_ms;
    uint32_t cycle;

    s_mode = TEST_RESPONSE_GROUP_NAK;
    TEST_CHECK(GnssNeoM9n_ConfigReadAsyncStart() ==
               GnssNeoM9nAsyncStartOk);
    TEST_CHECK(GnssNeoM9n_SatelliteDiagnosticsAsyncStart() ==
               GnssNeoM9nAsyncStartBusy);
    poll_result = GnssNeoM9nAsyncPollPending;
    for (cycle = 0U; (cycle < 5000U) &&
         (poll_result == GnssNeoM9nAsyncPollPending); cycle++)
    {
        (void)GnssNeoM9n_Process(s_tick_ms);
        poll_result = GnssNeoM9n_ConfigReadAsyncPoll(
            &snapshot, &elapsed_ms, &diagnostics, &result);
        s_tick_ms++;
    }
    TEST_CHECK(poll_result == GnssNeoM9nAsyncPollComplete);
    TEST_CHECK(result == GnssNeoM9nConfigReadResponseOk);
    TEST_CHECK(snapshot.valid_mask == GNSS_CONFIG_VALID_ALL);

    s_mode = TEST_RESPONSE_NAK;
    TEST_CHECK(GnssNeoM9n_ConfigReadAsyncStart() ==
               GnssNeoM9nAsyncStartOk);
    poll_result = GnssNeoM9nAsyncPollPending;
    for (cycle = 0U; (cycle < 5000U) &&
         (poll_result == GnssNeoM9nAsyncPollPending); cycle++)
    {
        (void)GnssNeoM9n_Process(s_tick_ms);
        poll_result = GnssNeoM9n_ConfigReadAsyncPoll(
            &snapshot, &elapsed_ms, &diagnostics, &result);
        s_tick_ms++;
    }
    TEST_CHECK(result == GnssNeoM9nConfigReadNak);
    TEST_CHECK(diagnostics.failed_group ==
               GnssNeoM9nConfigReadGroupRate);
    TEST_CHECK(diagnostics.failed_key == TEST_FAILURE_KEY);

    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_SatelliteDiagnosticsAsyncStart() ==
               GnssNeoM9nAsyncStartOk);
    TEST_CHECK(GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(&satellite) ==
               GnssNeoM9nAsyncPollPending);
    (void)GnssNeoM9n_Process(s_tick_ms++);
    TEST_CHECK(GnssNeoM9n_SatelliteDiagnosticsAsyncPoll(&satellite) ==
               GnssNeoM9nAsyncPollComplete);
    TEST_CHECK(satellite.read_result == GnssNeoM9nConfigReadResponseOk);

    TEST_CHECK(GnssNeoM9n_RfDiagnosticsAsyncStart() ==
               GnssNeoM9nAsyncStartOk);
    TEST_CHECK(GnssNeoM9n_RfDiagnosticsAsyncPoll(&rf) ==
               GnssNeoM9nAsyncPollPending);
    (void)GnssNeoM9n_Process(s_tick_ms++);
    TEST_CHECK(GnssNeoM9n_RfDiagnosticsAsyncPoll(&rf) ==
               GnssNeoM9nAsyncPollComplete);
    TEST_CHECK(rf.read_result == GnssNeoM9nConfigReadResponseOk);

    s_mode = TEST_RESPONSE_DISCONTINUITY;
    TEST_CHECK(GnssNeoM9n_ConfigReadAsyncStart() ==
               GnssNeoM9nAsyncStartOk);
    (void)GnssNeoM9n_ConfigReadAsyncPoll(
        &snapshot, &elapsed_ms, &diagnostics, &result);
    (void)GnssNeoM9n_Process(s_tick_ms++);
    poll_result = GnssNeoM9n_ConfigReadAsyncPoll(
        &snapshot, &elapsed_ms, &diagnostics, &result);
    TEST_CHECK(poll_result == GnssNeoM9nAsyncPollPending);
    poll_result = GnssNeoM9n_ConfigReadAsyncPoll(
        &snapshot, &elapsed_ms, &diagnostics, &result);
    TEST_CHECK(poll_result == GnssNeoM9nAsyncPollComplete);
    TEST_CHECK(result == GnssNeoM9nConfigReadIoError);
    TEST_CHECK(diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailRxDiscontinuity);
}

static void Test_DiscontinuityCompletesTransactions(void)
{
    const uint32_t key = TEST_FAILURE_KEY;
    GnssNeoM9nConfigReadDiagnostics read_diagnostics;
    GnssNeoM9nSatelliteDiagnostics satellite;

    s_mode = TEST_RESPONSE_DISCONTINUITY;
    TEST_CHECK(GnssNeoM9n_ValgetRead(&key, 1U, &read_diagnostics) ==
               GnssNeoM9nConfigReadIoError);
    TEST_CHECK(read_diagnostics.detailed_result ==
               GnssNeoM9nTransactionDetailRxDiscontinuity);
    TEST_CHECK(GnssNeoM9n_ReadSatelliteDiagnostics(&satellite) == -6);
    TEST_CHECK(satellite.read_result == GnssNeoM9nConfigReadIoError);
    TEST_CHECK(satellite.detailed_result ==
               GnssNeoM9nTransactionDetailRxDiscontinuity);
}

static void Test_ConfigDiffReadbackPersistence(void)
{
    uint8_t saved_count = 0U;
    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    s_layer_measurement_ms[0] = 1000U;
    s_layer_measurement_ms[1] = 1000U;
    s_layer_measurement_ms[2] = 1000U;
    TEST_CHECK(GnssNeoM9n_ConfigNavRate(0U, GNSS_CFG_LAYER_RAM, 25U) == 0);
    TEST_CHECK(s_layer_writes[0] == 1U && s_layer_writes[1] == 0U && s_layer_writes[2] == 0U);
    TEST_CHECK(GnssNeoM9n_ConfigNavRate(0U, GNSS_CFG_LAYER_RAM, 25U) == 0);
    TEST_CHECK(s_layer_writes[0] == 1U);
    TEST_CHECK(GnssNeoM9n_SaveConfig(0U, GNSS_CFG_LAYER_BBR | GNSS_CFG_LAYER_FLASH, &saved_count) == 0);
    TEST_CHECK(s_layer_writes[1] == 1U && s_layer_writes[2] == 1U);
    TEST_CHECK(GnssNeoM9n_SaveConfig(0U, GNSS_CFG_LAYER_BBR | GNSS_CFG_LAYER_FLASH, &saved_count) == 0);
    TEST_CHECK(s_layer_writes[1] == 1U && s_layer_writes[2] == 1U);
    s_ignore_config_write = 1U;
    TEST_CHECK(GnssNeoM9n_ConfigNavRate(0U, GNSS_CFG_LAYER_RAM, 10U) == -4);
    TEST_CHECK(s_layer_measurement_ms[0] == 40U);
    s_ignore_config_write = 0U;
    s_drop_config_ack = 1U;
    TEST_CHECK(GnssNeoM9n_ConfigNavRate(0U, GNSS_CFG_LAYER_BBR, 10U) == -2);
    TEST_CHECK(s_layer_writes[1] == 2U);
    s_drop_config_ack = 0U;
    TEST_CHECK(GnssNeoM9n_ConfigNavRate(0U, GNSS_CFG_LAYER_BBR, 10U) == 0);
    TEST_CHECK(s_layer_writes[1] == 2U);
    s_wrong_model = 1U;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(GnssNeoM9n_Identify(0U) == GnssNeoM9nIdentifyWrongModel);
    TEST_CHECK(GnssNeoM9n_ConfigNavRate(0U, GNSS_CFG_LAYER_RAM, 25U) == -4);
    TEST_CHECK(s_layer_writes[1] == 2U);
    s_wrong_model = 0U;
}

static void Test_NonblockingProbe(void)
{
    s_wrong_model = 0U;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(GnssNeoM9n_ProbeStart(0U, GNSS_DEFAULT_BAUDRATE) ==
        GnssNeoM9nProbeStartResult_Ok);
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) ==
        GnssNeoM9nProbePollResult_Pending);
    s_tick_ms += 200U;
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) ==
        GnssNeoM9nProbePollResult_Pending);
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) ==
        GnssNeoM9nProbePollResult_Identified);
    s_wrong_model = 1U;
    TEST_CHECK(GnssNeoM9n_ProbeStart(0U, 38400U) ==
        GnssNeoM9nProbeStartResult_Ok);
    s_tick_ms += 200U;
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) ==
        GnssNeoM9nProbePollResult_Pending);
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) ==
        GnssNeoM9nProbePollResult_WrongModel);
    s_wrong_model = 0U;
}

static void Test_AsyncConfigReadBackpressure(void)
{
    GnssNeoM9nConfigSnapshot snapshot;
    GnssNeoM9nConfigReadDiagnostics diagnostics;
    GnssNeoM9nConfigReadResult result;
    GnssNeoM9nAsyncPollResult poll_result = GnssNeoM9nAsyncPollPending;
    uint32_t cycle;
    uint32_t tx_before;

    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(GnssNeoM9n_ConfigReadAsyncStart() ==
        GnssNeoM9nAsyncStartOk);
    tx_before = s_uart_diagnostics.tx_bytes;
    s_async_busy_once = 1U;
    TEST_CHECK(GnssNeoM9n_ConfigReadAsyncPoll(
        &snapshot, NULL, &diagnostics, &result) ==
        GnssNeoM9nAsyncPollPending);
    TEST_CHECK(s_uart_diagnostics.tx_bytes == tx_before);
    for (cycle = 0U; (cycle < 5000U) &&
         (poll_result == GnssNeoM9nAsyncPollPending); cycle++)
    {
        (void)GnssNeoM9n_Process(s_tick_ms);
        poll_result = GnssNeoM9n_ConfigReadAsyncPoll(
            &snapshot, NULL, &diagnostics, &result);
        s_tick_ms++;
    }
    TEST_CHECK(poll_result == GnssNeoM9nAsyncPollComplete);
    TEST_CHECK(result == GnssNeoM9nConfigReadResponseOk);
    TEST_CHECK(s_uart_diagnostics.tx_bytes > tx_before);
}

static void Test_AsyncItemReadWrite(void)
{
    GnssNeoM9nConfigItem item = {0U};
    const GnssNeoM9nConfigItem target =
        {0x30210001UL, 40U, 2U};
    uint32_t writes_before;
    uint32_t bbr_writes_before;
    uint32_t flash_writes_before;

    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    s_layer_measurement_ms[0] = 1000U;
    writes_before = s_layer_writes[0];
    bbr_writes_before = s_layer_writes[1];
    flash_writes_before = s_layer_writes[2];
    s_async_busy_once = 1U;
    TEST_CHECK(GnssNeoM9n_ItemReadStart(0U, target.key) ==
        GnssNeoM9nItemStartResult_Busy);
    TEST_CHECK(GnssNeoM9n_ItemReadStart(0U, target.key) ==
        GnssNeoM9nItemStartResult_Ok);
    TEST_CHECK(GnssNeoM9n_ItemReadPoll(0U, &item) ==
        GnssNeoM9nItemPollResult_Complete);
    TEST_CHECK(item.key == target.key);
    TEST_CHECK(item.value == 1000U);
    TEST_CHECK(item.value_len == target.value_len);
    TEST_CHECK(s_layer_writes[0] == writes_before);

    s_async_busy_once = 1U;
    TEST_CHECK(GnssNeoM9n_ItemWriteStart(0U, &target) ==
        GnssNeoM9nItemStartResult_Busy);
    TEST_CHECK(GnssNeoM9n_ItemWriteStart(0U, &target) ==
        GnssNeoM9nItemStartResult_Ok);
    TEST_CHECK(GnssNeoM9n_ItemWritePoll(0U) ==
        GnssNeoM9nItemPollResult_Complete);
    TEST_CHECK(s_layer_writes[0] == writes_before + 1U);
    TEST_CHECK(s_layer_writes[1] == bbr_writes_before);
    TEST_CHECK(s_layer_writes[2] == flash_writes_before);
    TEST_CHECK(GnssNeoM9n_ItemReadStart(0U, target.key) ==
        GnssNeoM9nItemStartResult_Ok);
    TEST_CHECK(GnssNeoM9n_ItemReadPoll(0U, &item) ==
        GnssNeoM9nItemPollResult_Complete);
    TEST_CHECK(item.value == target.value);
}

static void Test_AsyncStartup(void)
{
    SystemGnssConfig target = {0U};
    uint8_t pvt_payload[92] = {0U};
    uint8_t pvt_frame[100];
    uint16_t pvt_length;
    uint32_t cycle;

    s_mode = TEST_RESPONSE_OK;
    s_rx_count = 0U;
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    s_startup_physical_baud = GNSS_FACTORY_BAUDRATE;
    s_startup_item_mode = 1U;
    s_startup_item_count = 1U;
    s_startup_items[0].key = 0x30210001UL;
    s_startup_items[0].value = 1000U;
    s_startup_items[0].value_len = 2U;
    s_startup_write_count = 0U;
    s_startup_last_write_key = 0U;
    target.navigation_rate_hz = 25U;
    target.constellation_mask = SYSTEM_GNSS_CONSTELLATION_GPS |
        SYSTEM_GNSS_CONSTELLATION_BDS |
        SYSTEM_GNSS_CONSTELLATION_GALILEO;
    target.dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G;
    target.output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    target.enabled_message_mask = SYSTEM_GNSS_MESSAGE_NAV_PVT;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(NeoM9nStartup_Init(0U, &target) == NeoM9nStartupResult_Ok);
    pvt_length = Test_FrameBuild(TEST_NAV_CLASS, 0x07U,
        pvt_payload, sizeof(pvt_payload), pvt_frame);
    for (cycle = 0U; cycle < 2000U; cycle++)
    {
        SystemDeviceStartupState state = NeoM9nStartup_StateGet(0U);
        if (state == SystemDeviceStartupState_WaitingSample)
        { Test_FrameInject(pvt_frame, pvt_length, 0U); }
        NeoM9nStartup_Tick(0U, s_tick_ms);
        state = NeoM9nStartup_StateGet(0U);
        if ((state == SystemDeviceStartupState_Ready) ||
            (state == SystemDeviceStartupState_Failed))
        { break; }
        s_tick_ms += 10U;
    }
    TEST_CHECK(NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Ready);
    TEST_CHECK(s_startup_physical_baud == GNSS_DEFAULT_BAUDRATE);
    TEST_CHECK(s_startup_write_count > 0U);
    TEST_CHECK(s_startup_write_count < 23U);
    TEST_CHECK(s_startup_last_write_key == 0x40520001UL);
    TEST_CHECK(Test_KeyValue(0x30210001UL) == 40U);

    s_rx_count = 0U;
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    s_startup_physical_baud = 0U;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(NeoM9nStartup_Init(0U, &target) == NeoM9nStartupResult_Ok);
    for (cycle = 0U; cycle < 3500U; cycle++)
    {
        NeoM9nStartup_Tick(0U, s_tick_ms);
        if (NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Failed)
        { break; }
        s_tick_ms += 10U;
    }
    TEST_CHECK(NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Failed);
    TEST_CHECK(NeoM9nStartup_FailureGet(0U) ==
        SystemDeviceStartupFailure_NotPresent);
    s_startup_item_mode = 0U;
}

static void Test_NmeaRescue(uint8_t bad_checksum, uint8_t wrong_model,
    uint8_t pubx_fail, uint8_t expect_ready)
{
    SystemGnssConfig target = {0U};
    uint8_t pvt_payload[92] = {0U};
    uint8_t pvt_frame[100];
    uint16_t pvt_length;
    uint32_t cycle;

    s_mode = TEST_RESPONSE_OK;
    s_rx_count = 0U;
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    s_startup_physical_baud = GNSS_UART_BAUD_576000;
    s_startup_item_mode = 1U;
    s_startup_nmea_only = 1U;
    s_startup_nmea_bad_checksum = bad_checksum;
    s_startup_ubx_enabled = 0U;
    s_startup_pubx_count = 0U;
    s_startup_pubx_fail = pubx_fail;
    s_startup_nmea_count = 0U;
    s_wrong_model = wrong_model;
    s_startup_item_count = 0U;
    target.navigation_rate_hz = 25U;
    target.constellation_mask = SYSTEM_GNSS_CONSTELLATION_GPS |
        SYSTEM_GNSS_CONSTELLATION_BDS |
        SYSTEM_GNSS_CONSTELLATION_GALILEO;
    target.dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G;
    target.output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    target.enabled_message_mask = SYSTEM_GNSS_MESSAGE_NAV_PVT;
    pvt_length = Test_FrameBuild(TEST_NAV_CLASS, 0x07U,
        pvt_payload, sizeof(pvt_payload), pvt_frame);
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(NeoM9nStartup_Init(0U, &target) == NeoM9nStartupResult_Ok);
    for (cycle = 0U; cycle < 4500U; cycle++)
    {
        SystemDeviceStartupState state = NeoM9nStartup_StateGet(0U);
        if (state == SystemDeviceStartupState_WaitingSample)
        { Test_FrameInject(pvt_frame, pvt_length, 0U); }
        NeoM9nStartup_Tick(0U, s_tick_ms);
        state = NeoM9nStartup_StateGet(0U);
        if ((state == SystemDeviceStartupState_Ready) ||
            (state == SystemDeviceStartupState_Failed))
        { break; }
        s_tick_ms += 10U;
    }
    TEST_CHECK((NeoM9nStartup_StateGet(0U) ==
        SystemDeviceStartupState_Ready) == (expect_ready != 0U));
    TEST_CHECK((s_startup_pubx_count != 0U) ==
        ((bad_checksum == 0U) && (expect_ready != 0U ||
        wrong_model != 0U || pubx_fail != 0U)));
    if (expect_ready != 0U)
    { TEST_CHECK(s_startup_physical_baud == GNSS_DEFAULT_BAUDRATE); }
    s_startup_nmea_only = 0U;
    s_startup_nmea_bad_checksum = 0U;
    s_startup_ubx_enabled = 0U;
    s_startup_pubx_fail = 0U;
    s_wrong_model = 0U;
    s_startup_item_mode = 0U;
}


static void Test_IdentityFrame(const char *model, const char *protocol,
    const char *firmware, const char *extra, uint8_t mode,
    GnssNeoM9nIdentityResult expected)
{
    uint8_t payload[160] = {0U};
    uint8_t frame[168];
    uint16_t length;
    GnssNeoM9nIdentityDiagnostics diagnostics;
    s_monver_silent = 1U;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(GnssNeoM9n_ProbeStart(0U, GNSS_DEFAULT_BAUDRATE) ==
        GnssNeoM9nProbeStartResult_Ok);
    /* Deliberately reorder firmware/protocol/model, with zero-filled slots. */
    if (firmware != NULL) { (void)memcpy(&payload[40], firmware, strlen(firmware)); }
    if (protocol != NULL) { (void)memcpy(&payload[70], protocol, strlen(protocol)); }
    if (model != NULL) { (void)memcpy(&payload[100], model, strlen(model)); }
    if (extra != NULL) { (void)memcpy(&payload[130], extra, strlen(extra)); }
    if (mode == 1U) { (void)memset(&payload[130], 'X', 30U); }
    if (mode == 4U) { (void)memcpy(&payload[30], "00080000", 8U); }
    if ((mode >= 5U) && (mode <= 11U))
    {
        static const char *software[] = {"ROM CORE 3.01 (107888)",
            "EXT CORE 3.51 (19dc23)", "ROM SPG 5.10 (10ca7e)",
            "EXT SPG 5.20 (000000)", "EXT CORE 1.00 (unknown)",
            "UNKNOWN BUILD", "ROM CORE 4.04 (d964f4)"};
        (void)memcpy(payload, software[mode - 5U], strlen(software[mode - 5U]));
        (void)memcpy(&payload[30], "00190000", 8U);
    }
    length = Test_FrameBuild(TEST_MON_CLASS, 4U, payload,
        (mode == 2U) ? 159U : (uint16_t)sizeof(payload), frame);
    Test_FrameInject(frame, length, (uint8_t)(mode == 3U));
    TEST_CHECK((GnssNeoM9n_ProbePoll(0U) == GnssNeoM9nProbePollResult_Identified)
        == (expected == GnssNeoM9nIdentityOk));
    TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &diagnostics) == expected);
    TEST_CHECK(diagnostics.identity_result ==
        ((mode == 3U) ? GnssNeoM9nIdentityNone : expected));
    if (expected != GnssNeoM9nIdentityOk)
    { TEST_CHECK(diagnostics.last_rejection == expected); }
    if (expected == GnssNeoM9nIdentityOk)
    { TEST_CHECK(diagnostics.profile ==
        ((diagnostics.protocol_major == 27U) ? 1U : 2U)); }
    s_monver_silent = 0U;
}

static void Test_IdentityBoundary(void)
{
    static const char *versions[] = {"PROTVER=27.00", "PROTVER=27.99",
        "PROTVER=32.01", "PROTVER=32.00", "PROTVER=32.02", "PROTVER=31.01",
        "PROTVER=26.99", "PROTVER=33.01", "PROTVER=27.1", "PROTVER=27.xx",
        "PROTVER=32.01X"};
    uint8_t index;
    for (index = 0U; index < sizeof(versions) / sizeof(versions[0]); index++)
    {
        Test_IdentityFrame("MOD=NEO-M9N", versions[index],
            index < 2U ? NULL : "FWVER=SPG 4.04",
            NULL, 0U, index < 3U ? GnssNeoM9nIdentityOk :
            GnssNeoM9nIdentityUnsupportedProtocol);
    }
    /* Explicit software-family conflicts only affect the new 32.01 profile.
     * Unknown/empty software and legacy 27.xx are not a new whitelist. */
    for (index = 5U; index <= 11U; index++)
    {
        Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
            NULL, index, index <= 8U ? GnssNeoM9nIdentityWrongFirmware :
            GnssNeoM9nIdentityOk);
        Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=27.12", NULL,
            NULL, index, GnssNeoM9nIdentityOk);
    }
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=27.12", "FWVER=SPG 4.04",
        NULL, 0U, GnssNeoM9nIdentityWrongFirmware);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=27.12", NULL,
        NULL, 4U, GnssNeoM9nIdentityUnsupportedHardware);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 4U, GnssNeoM9nIdentityUnsupportedHardware);
    Test_IdentityFrame(NULL, "PROTVER=32.01", "FWVER=SPG 4.04", NULL, 0U,
        GnssNeoM9nIdentityUnsupportedHardware);
    Test_IdentityFrame("MOD=NEO-M9N", NULL, "FWVER=SPG 4.04", NULL, 0U,
        GnssNeoM9nIdentityMissingProtocol);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", NULL, NULL, 0U,
        GnssNeoM9nIdentityMissingFirmware);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=27.12", NULL, NULL, 0U,
        GnssNeoM9nIdentityOk);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.03",
        NULL, 0U, GnssNeoM9nIdentityWrongFirmware);
    Test_IdentityFrame("MOD=NEO-M8N", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 0U, GnssNeoM9nIdentityWrongModel);
    Test_IdentityFrame("MOD=NEO-F9P", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 0U, GnssNeoM9nIdentityWrongModel);
    Test_IdentityFrame("MOD=NEO-M10", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 0U, GnssNeoM9nIdentityWrongModel);
    Test_IdentityFrame("MOD=NEO-M9N-00B", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 0U, GnssNeoM9nIdentityWrongModel);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        "PROTVER=32.01", 0U, GnssNeoM9nIdentityOk);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        "PROTVER=27.12", 0U, GnssNeoM9nIdentityDuplicateConflict);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        "MOD=NEO-M8N", 0U, GnssNeoM9nIdentityDuplicateConflict);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        "FWVER=SPG 4.03", 0U, GnssNeoM9nIdentityDuplicateConflict);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 1U, GnssNeoM9nIdentityUnterminatedField);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 2U, GnssNeoM9nIdentityBadLength);
    Test_IdentityFrame("MOD=NEO-M9N", "PROTVER=32.01", "FWVER=SPG 4.04",
        NULL, 3U, GnssNeoM9nIdentityChecksumError);
}


static void Test_CapturedIdentity(void)
{
    static const uint32_t keys[23] = {
    GNSS_CFG_UART1_BAUDRATE, /* Apply communication changes last. */
    GNSS_CFG_UART1INPROT_UBX, GNSS_CFG_UART1INPROT_NMEA,
    GNSS_CFG_UART1INPROT_RTCM3X, GNSS_CFG_UART1OUTPROT_UBX,
    GNSS_CFG_UART1OUTPROT_NMEA, GNSS_CFG_MSGOUT_NAV_PVT_UART1,
    GNSS_CFG_RATE_MEAS, GNSS_CFG_RATE_NAV, GNSS_CFG_RATE_TIMEREF,
    GNSS_CFG_NAVSPG_DYNMODEL,
    GNSS_CFG_SIGNAL_GPS_ENA, GNSS_CFG_SIGNAL_GPS_L1CA_ENA,
    GNSS_CFG_SIGNAL_SBAS_ENA, GNSS_CFG_SIGNAL_SBAS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GAL_ENA, GNSS_CFG_SIGNAL_GAL_E1_ENA,
    GNSS_CFG_SIGNAL_BDS_ENA, GNSS_CFG_SIGNAL_BDS_B1_ENA,
    GNSS_CFG_SIGNAL_QZSS_ENA, GNSS_CFG_SIGNAL_QZSS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GLO_ENA, GNSS_CFG_SIGNAL_GLO_L1_ENA
};
    GnssNeoM9nIdentityDiagnostics diagnostics;
    GnssNeoM9nConfigItem item = {GNSS_CFG_RATE_NAV, 1U, 2U};
    uint8_t index;
    uint8_t frame[168];
    uint8_t payload[160];
    s_use_captured = 1U;
    s_test_protocol = "PROTVER=32.01";
    s_mode = TEST_RESPONSE_OK;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(GnssNeoM9n_ProbeStart(0U, GNSS_DEFAULT_BAUDRATE) == GnssNeoM9nProbeStartResult_Ok);
    s_tick_ms += 200U;
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) == GnssNeoM9nProbePollResult_Pending);
    TEST_CHECK(GnssNeoM9n_ProbePoll(0U) == GnssNeoM9nProbePollResult_Identified);
    TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &diagnostics) == GnssNeoM9nIdentityCapabilitiesPending);
    TEST_CHECK(diagnostics.profile == 3U && diagnostics.capability_read_mask == 0U);
    TEST_CHECK(GnssNeoM9n_ItemWriteStart(0U, &item) == GnssNeoM9nItemStartResult_NotReady);
    for (index = 0U; index < 23U; index++)
    {
        TEST_CHECK(GnssNeoM9n_ItemReadStart(0U, keys[index]) == GnssNeoM9nItemStartResult_Ok);
        TEST_CHECK(GnssNeoM9n_ItemReadPoll(0U, &item) == GnssNeoM9nItemPollResult_Complete);
        TEST_CHECK(item.key == keys[index] && item.value_len == Test_KeyValueLength(keys[index]));
        if (index < 22U)
        { TEST_CHECK(GnssNeoM9n_ItemWriteStart(0U, &item) == GnssNeoM9nItemStartResult_NotReady); }
    }
    TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &diagnostics) == GnssNeoM9nIdentityOk);
    TEST_CHECK(diagnostics.capability_read_mask == 0x007FFFFFUL);
    /* Wrong base SW/HW/FW/protocol are checksummed input, still refused. */
    s_monver_silent = 1U;
    for (index = 0U; index < 4U; index++)
    {
        static const uint8_t offsets[4] = {9U, 31U, 50U, 82U};
        TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
        TEST_CHECK(GnssNeoM9n_ProbeStart(0U, GNSS_DEFAULT_BAUDRATE) == GnssNeoM9nProbeStartResult_Ok);
        (void)memcpy(payload, &s_captured_monver[6], sizeof(payload));
        payload[offsets[index]] ^= 1U;
        (void)Test_FrameBuild(TEST_MON_CLASS, 4U, payload, sizeof(payload), frame);
        Test_FrameInject(frame, sizeof(frame), 0U);
        TEST_CHECK(GnssNeoM9n_ProbePoll(0U) == GnssNeoM9nProbePollResult_WrongModel);
        TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &diagnostics) != GnssNeoM9nIdentityOk);
        TEST_CHECK(diagnostics.capability_read_mask == 0U);
        TEST_CHECK(GnssNeoM9n_ItemWriteStart(0U, &item) != GnssNeoM9nItemStartResult_Ok);
    }
    s_monver_silent = 0U;
    s_use_captured = 0U;
    s_test_protocol = "PROTVER=27.12";
}


static void Test_CapturedCapabilityFailures(void)
{
    static const uint32_t keys[23] = {
    GNSS_CFG_UART1_BAUDRATE, /* Apply communication changes last. */
    GNSS_CFG_UART1INPROT_UBX, GNSS_CFG_UART1INPROT_NMEA,
    GNSS_CFG_UART1INPROT_RTCM3X, GNSS_CFG_UART1OUTPROT_UBX,
    GNSS_CFG_UART1OUTPROT_NMEA, GNSS_CFG_MSGOUT_NAV_PVT_UART1,
    GNSS_CFG_RATE_MEAS, GNSS_CFG_RATE_NAV, GNSS_CFG_RATE_TIMEREF,
    GNSS_CFG_NAVSPG_DYNMODEL,
    GNSS_CFG_SIGNAL_GPS_ENA, GNSS_CFG_SIGNAL_GPS_L1CA_ENA,
    GNSS_CFG_SIGNAL_SBAS_ENA, GNSS_CFG_SIGNAL_SBAS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GAL_ENA, GNSS_CFG_SIGNAL_GAL_E1_ENA,
    GNSS_CFG_SIGNAL_BDS_ENA, GNSS_CFG_SIGNAL_BDS_B1_ENA,
    GNSS_CFG_SIGNAL_QZSS_ENA, GNSS_CFG_SIGNAL_QZSS_L1CA_ENA,
    GNSS_CFG_SIGNAL_GLO_ENA, GNSS_CFG_SIGNAL_GLO_L1_ENA
};
    GnssNeoM9nIdentityDiagnostics identity;
    GnssNeoM9nConfigItem item = {GNSS_CFG_RATE_NAV, 1U, 2U};
    uint8_t failure;
    uint8_t index;
    s_use_captured = 1U;
    s_mode = TEST_RESPONSE_OK;
    for (failure = 0U; failure < 23U; failure++)
    {
        TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
        TEST_CHECK(GnssNeoM9n_ProbeStart(0U, GNSS_DEFAULT_BAUDRATE) == GnssNeoM9nProbeStartResult_Ok);
        s_tick_ms += 200U;
        TEST_CHECK(GnssNeoM9n_ProbePoll(0U) == GnssNeoM9nProbePollResult_Pending);
        TEST_CHECK(GnssNeoM9n_ProbePoll(0U) == GnssNeoM9nProbePollResult_Identified);
        s_capability_reject_key = keys[failure];
        for (index = 0U; index < 23U; index++)
        {
            TEST_CHECK(GnssNeoM9n_ItemReadStart(0U, keys[index]) == GnssNeoM9nItemStartResult_Ok);
            TEST_CHECK(GnssNeoM9n_ItemReadPoll(0U, &item) ==
                (index == failure ? GnssNeoM9nItemPollResult_Nak : GnssNeoM9nItemPollResult_Complete));
        }
        TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &identity) == GnssNeoM9nIdentityCapabilitiesPending);
        TEST_CHECK(identity.capability_read_mask != 0x007FFFFFUL);
        TEST_CHECK(GnssNeoM9n_ItemWriteStart(0U, &item) == GnssNeoM9nItemStartResult_NotReady);
        TEST_CHECK(GnssNeoM9n_SendUbx(0U, TEST_CFG_CLASS, 0x8AU, NULL, 0U) != 0);
    }
    s_capability_reject_key = 0U;
    s_use_captured = 0U;
}


/* Field failure: a valid stream is not an identity, but losing one MON-VER
 * response must not strand the MCU at the final wrong scan baud. */
static void Test_StartupLostIdentityRestore(void)
{
    SystemGnssConfig target = {0U};
    GnssNeoM9nData data;
    GnssNeoM9nIdentityDiagnostics identity;
    uint8_t payload[92] = {0U};
    uint8_t frame[100];
    uint16_t length;
    uint32_t cycle;

    s_tick_ms = 100U;
    s_mode = TEST_RESPONSE_OK;
    s_rx_count = 0U;
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    s_startup_physical_baud = GNSS_DEFAULT_BAUDRATE;
    s_startup_item_mode = 1U;
    s_startup_item_count = 0U;
    s_startup_write_count = 0U;
    s_monver_silent = 1U;
    target.navigation_rate_hz = 25U;
    target.constellation_mask = SYSTEM_GNSS_CONSTELLATION_GPS;
    target.dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G;
    target.output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    target.enabled_message_mask = SYSTEM_GNSS_MESSAGE_NAV_PVT;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(NeoM9nStartup_Init(0U, &target) == NeoM9nStartupResult_Ok);
    length = Test_FrameBuild(TEST_NAV_CLASS, 0x07U,
        payload, sizeof(payload), frame);
    for (cycle = 0U; cycle < 3500U; cycle++)
    {
        if ((s_uart_baudrate == s_startup_physical_baud) &&
            ((cycle % 4U) == 0U))
        { Test_FrameInject(frame, length, 0U); }
        NeoM9nStartup_Tick(0U, s_tick_ms);
        if (NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Failed)
        { break; }
        s_tick_ms += 10U;
    }
    (void)GnssNeoM9n_GetData(0U, &data);
    (void)GnssNeoM9n_IdentityDiagnosticsGet(0U, &identity);
    TEST_CHECK(NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Failed);
    TEST_CHECK(NeoM9nStartup_FailureGet(0U) == SystemDeviceStartupFailure_NotPresent);
    TEST_CHECK(data.pvtSequence > 0U);
    TEST_CHECK(identity.sequence == 0U);
    TEST_CHECK(s_startup_write_count == 0U);
    printf("FIELD_REPRO pvt=%lu identity=%lu baud=%lu failed_ms=%lu\n",
        (unsigned long)data.pvtSequence, (unsigned long)identity.sequence,
        (unsigned long)s_uart_baudrate, (unsigned long)s_tick_ms);
    TEST_CHECK(s_uart_baudrate == s_startup_physical_baud);
    s_monver_silent = 0U;
    s_startup_item_mode = 0U;
}


/* 0/5: MON-VER becomes available after failure, including tick wrap.
 * 1: permanent response loss; 2/6: explicit wrong model/version;
 * 3: corrupt PVT only; 4: failed UART restore. */
static void Test_StartupRecoveryFault(uint8_t scenario)
{
    SystemGnssConfig target = {0U};
    NeoM9nStartupRecoveryDiagnostics recovery = {0U};
    GnssNeoM9nIdentityDiagnostics identity;
    uint8_t payload[92] = {0U};
    uint8_t frame[100];
    uint16_t length;
    uint32_t cycle;
    uint32_t failure_ms = 0U;
    uint32_t quiet_requests;
    uint32_t quiet_bauds;
    uint8_t first_failure_seen = 0U;
    uint8_t expect_ready = (uint8_t)((scenario == 0U) || (scenario == 5U));

    s_tick_ms = (scenario == 5U) ? UINT32_MAX - 24500U : 100U;
    s_mode = TEST_RESPONSE_OK;
    s_rx_count = 0U;
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    s_startup_physical_baud = GNSS_DEFAULT_BAUDRATE;
    s_startup_item_mode = 1U;
    s_startup_item_count = 0U;
    s_startup_write_count = 0U;
    s_startup_nmea_only = 0U;
    s_recovery_test_active = 1U;
    s_recovery_baud_fail = (uint8_t)(scenario == 4U);
    s_recovery_mon_requests = 0U;
    s_recovery_baud_changes = 0U;
    s_signal_reset_until = 0U;
    s_monver_silent = (uint8_t)((scenario != 2U) && (scenario != 6U));
    s_wrong_model = (uint8_t)(scenario == 2U);
    s_test_protocol = (scenario == 6U) ? "PROTVER=99.99" : "PROTVER=32.01";
    target.navigation_rate_hz = 25U;
    target.constellation_mask = SYSTEM_GNSS_CONSTELLATION_GPS;
    target.dynamic_model = SYSTEM_GNSS_DYNAMIC_MODEL_AIRBORNE_4G;
    target.output_protocol = SYSTEM_GNSS_OUTPUT_PROTOCOL_UBX;
    target.enabled_message_mask = SYSTEM_GNSS_MESSAGE_NAV_PVT;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    TEST_CHECK(NeoM9nStartup_Init(0U, &target) == NeoM9nStartupResult_Ok);
    length = Test_FrameBuild(TEST_NAV_CLASS, 0x07U, payload, sizeof(payload), frame);
    for (cycle = 0U; cycle < 5000U; cycle++)
    {
        if ((s_uart_baudrate == s_startup_physical_baud) && ((cycle % 4U) == 0U))
        {
            Test_FrameInject(frame, length, (uint8_t)(scenario == 3U));
            if (scenario == 3U) { frame[length - 1U] ^= 0x01U; }
        }
        NeoM9nStartup_Tick(0U, s_tick_ms);
        TEST_CHECK(NeoM9nStartup_RecoveryDiagnosticsGet(0U, &recovery) == NeoM9nStartupResult_Ok);
        if ((first_failure_seen == 0U) &&
            (NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Failed))
        {
            first_failure_seen = 1U;
            failure_ms = s_tick_ms;
            TEST_CHECK(s_startup_write_count == 0U);
            TEST_CHECK(recovery.attempt_count == 0U);
        }
        if ((first_failure_seen != 0U) && (expect_ready != 0U) &&
            ((uint32_t)(s_tick_ms - failure_ms) >= 500U))
        { s_monver_silent = 0U; }
        if ((first_failure_seen != 0U) &&
            ((uint32_t)(s_tick_ms - failure_ms) < 1000U))
        { TEST_CHECK(recovery.attempt_count == 0U); }
        if ((NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Ready) ||
            ((first_failure_seen != 0U) && (NeoM9nStartup_RecoveryPending(0U) == 0U)))
        { break; }
        s_tick_ms += 10U;
    }
    TEST_CHECK(first_failure_seen != 0U);
    TEST_CHECK(cycle < 5000U);
    TEST_CHECK((NeoM9nStartup_StateGet(0U) == SystemDeviceStartupState_Ready) == (expect_ready != 0U));
    if (expect_ready != 0U)
    {
        TEST_CHECK(recovery.state == NeoM9nStartupRecoveryState_Ready);
        TEST_CHECK(recovery.attempt_count == 1U);
        TEST_CHECK(GnssNeoM9n_IdentityDiagnosticsGet(0U, &identity) == GnssNeoM9nIdentityOk);
        TEST_CHECK(identity.protocol_major == 32U && identity.protocol_minor == 1U);
        TEST_CHECK(s_startup_write_count != 0U);
        TEST_CHECK(Test_KeyValue(GNSS_CFG_UART1_BAUDRATE) == GNSS_DEFAULT_BAUDRATE);
        TEST_CHECK(s_uart_baudrate == GNSS_DEFAULT_BAUDRATE);
    }
    else
    {
        TEST_CHECK(s_startup_write_count == 0U);
        TEST_CHECK(recovery.attempt_count == ((scenario == 1U) ? 2U : 0U));
        TEST_CHECK(recovery.state == ((scenario == 1U) ? NeoM9nStartupRecoveryState_Exhausted :
            (scenario == 3U) ? NeoM9nStartupRecoveryState_NoStream :
            (scenario == 4U) ? NeoM9nStartupRecoveryState_RestoreFailed : NeoM9nStartupRecoveryState_Rejected));
        if (scenario != 3U && scenario != 4U)
        { TEST_CHECK(s_uart_baudrate == s_startup_physical_baud); }
    }
    if (scenario == 1U) { TEST_CHECK(s_recovery_mon_requests == 12U); }
    quiet_requests = s_recovery_mon_requests;
    quiet_bauds = s_recovery_baud_changes;
    for (cycle = 0U; cycle < 1000U; cycle++)
    { s_tick_ms += 100U; NeoM9nStartup_Tick(0U, s_tick_ms); }
    TEST_CHECK(s_recovery_mon_requests == quiet_requests);
    TEST_CHECK(s_recovery_baud_changes == quiet_bauds);
    TEST_CHECK(s_recovery_baud_changes <= 16U);
    TEST_CHECK(NeoM9nStartup_RecoveryDiagnosticsGet(0U, NULL) == NeoM9nStartupResult_InvalidArgument);
    TEST_CHECK(GnssNeoM9n_LastValidBaudGet(UINT8_MAX) == 0U);
    s_recovery_test_active = 0U;
    s_signal_reset_until = 0U;
    s_recovery_baud_fail = 0U;
    s_monver_silent = 0U;
    s_wrong_model = 0U;
    s_test_protocol = "PROTVER=27.12";
    s_startup_item_mode = 0U;
    s_tick_ms = 100U;
}

int main(void)
{
    (void)memset(&s_uart_diagnostics, 0, sizeof(s_uart_diagnostics));
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    Test_StartupLostIdentityRestore();
    for (uint8_t scenario = 0U; scenario < 7U; scenario++)
    { Test_StartupRecoveryFault(scenario); }
    Test_CapturedCapabilityFailures();
    Test_CapturedIdentity();
    Test_IdentityBoundary();
    Test_ConfigReadResponses();
    Test_ValgetVersionsAndKeySizes();
    Test_DiagnosticParsers();
    Test_AsyncRuntimeTransactions();
    Test_DiscontinuityCompletesTransactions();
    Test_ConfigDiffReadbackPersistence();
    Test_NonblockingProbe();
    s_test_protocol = "PROTVER=32.01";
    Test_NonblockingProbe();
    s_test_protocol = "PROTVER=27.12";
    Test_AsyncConfigReadBackpressure();
    Test_AsyncItemReadWrite();
    Test_AsyncStartup();
    s_test_protocol = "PROTVER=32.01";
    Test_AsyncStartup();
    Test_NmeaRescue(0U, 0U, 0U, 1U);
    Test_NmeaRescue(0U, 1U, 0U, 0U);
    s_use_captured = 1U;
    Test_AsyncStartup();
    Test_NmeaRescue(0U, 0U, 0U, 1U);
    s_use_captured = 0U;
    s_test_protocol = "PROTVER=27.12";
    Test_NmeaRescue(0U, 0U, 0U, 1U);
    Test_NmeaRescue(1U, 0U, 0U, 0U);
    Test_NmeaRescue(0U, 1U, 0U, 0U);
    Test_NmeaRescue(0U, 0U, 1U, 0U);
    return Test_Finish("neo_m9n_device");
}
