#include <stdint.h>
#include <string.h>

#include "project_resources.h"
#include "neo_m9n_config.h"
#include "neo_m9n_device.h"
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
static uint8_t s_wrong_model;

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
        if ((key == 0x30210001UL) && (request_payload[1] < 3U))
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
    payload_length = Test_ReadU16Le(&data[4]);
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
        Test_ValgetRespond(&data[6], payload_length);
    }
    else if ((data[2] == TEST_NAV_CLASS) &&
             (data[3] == TEST_NAV_SAT_ID))
    {
        Test_NavSatRespond();
    }
    else if ((data[2] == TEST_MON_CLASS) && (data[3] == 4U))
    {
        uint8_t version[100] = {0U};
        uint8_t frame[108];
        uint16_t frame_length;
        (void)memcpy(&version[40], (s_wrong_model != 0U) ? "MOD=NEO-M8N" : "MOD=NEO-M9N", 11U);
        (void)memcpy(&version[70], "PROTVER=27.12", 12U);
        frame_length = Test_FrameBuild(TEST_MON_CLASS, 4U, version, 100U, frame);
        Test_FrameInject(frame, frame_length, 0U);
    }
    else if ((data[2] == TEST_CFG_CLASS) && (data[3] == 0x8AU))
    {
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
    s_uart_baudrate = baudrate;
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

int main(void)
{
    (void)memset(&s_uart_diagnostics, 0, sizeof(s_uart_diagnostics));
    s_uart_baudrate = GNSS_DEFAULT_BAUDRATE;
    TEST_CHECK(GnssNeoM9n_Init() == GnssNeoM9n_InitOk);
    Test_ConfigReadResponses();
    Test_ValgetVersionsAndKeySizes();
    Test_DiagnosticParsers();
    Test_AsyncRuntimeTransactions();
    Test_DiscontinuityCompletesTransactions();
    Test_ConfigDiffReadbackPersistence();
    return Test_Finish("neo_m9n_device");
}
