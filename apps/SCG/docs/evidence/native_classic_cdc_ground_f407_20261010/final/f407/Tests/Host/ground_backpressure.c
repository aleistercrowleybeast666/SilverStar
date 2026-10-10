#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "ground_bridge.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"
#include "pc_byte_stream.h"

static uint8_t connected, pending, fail_write;
static uint8_t tx_copy[70];
static const uint8_t *retained;
static uint16_t tx_length;
static unsigned forwarded, acknowledgements, status_frames, radio_frames;
static unsigned cancelled_acknowledgements;
static unsigned radio_pending, radio_calls, write_calls, read_calls, read_bytes;
static uint32_t tick;

static void TxAccept(uint8_t *data, uint16_t length)
{
    assert(!pending && length <= sizeof(tx_copy));
    memcpy(tx_copy, data, length); retained = data; tx_length = length; pending = 1U;
}

#if defined(GROUND_TEST_USB)
#include "usbd_cdc_if.h"
uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
static USBD_CDC_HandleTypeDef usb_class;
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{
    assert(usb_test_mask == 1U); write_calls++;
    if (fail_write) { if (fail_write == 2U) { PcByteStream_OnUsbReset(); } return USBD_FAIL; }
    TxAccept(data, length); usb_class.TxState = 1U; return USBD_OK;
}
static void Feed(const uint8_t *data, uint16_t length) { PcByteStream_OnUsbReceive(data, length); }
static void Connect(uint8_t value)
{
    connected = value; pending = 0U; usb_class.TxState = 0U;
    cancelled_acknowledgements = forwarded - acknowledgements;
    hUsbDeviceFS.dev_state = value ? USBD_STATE_CONFIGURED : 0U;
    hUsbDeviceFS.pClassData = value ? &usb_class : NULL; hUsbDeviceFS.pClassDataCmsit[0] = value ? &usb_class : NULL;
    PcByteStream_OnUsbReset();
}
#else
static uint8_t rx[512], tx_owned[70];
static uint16_t rx_head, rx_tail;
static uint32_t session;
static void Feed(const uint8_t *data, uint16_t length)
{
    assert((unsigned)(rx_head - rx_tail) + length <= sizeof(rx));
    for (uint16_t i = 0U; i < length; i++) { rx[rx_head++ % 512U] = data[i]; }
}
static void Connect(uint8_t value)
{ connected = value; pending = 0U; rx_head = 0U; rx_tail = 0U; session++;
  cancelled_acknowledgements = forwarded - acknowledgements; }
PcByteStreamInitResult PcByteStream_Init(void) { return PC_BYTE_STREAM_INIT_OK; }
uint32_t PcByteStream_Session_Get(void) { return session; }
uint8_t PcByteStream_Session_Check(uint32_t value) { return (value == session) ? 1U : 0U; }
uint8_t PcByteStream_Session_Enter(uint32_t value, uint32_t *token)
{ *token = 0U; return PcByteStream_Session_Check(value); }
void PcByteStream_Session_Exit(uint32_t token) { (void)token; }
uint32_t PcByteStream_OverflowCount_Get(void) { return 0U; }
uint16_t PcByteStream_ReadSession(uint8_t *data, uint16_t capacity, uint32_t *value)
{
    uint16_t n = 0U; read_calls++; *value = session;
    for (; n < capacity && rx_tail != rx_head; n++) { data[n] = rx[rx_tail++ % 512U]; }
    read_bytes += n; return n;
}
PcByteStreamWriteResult PcByteStream_WriteSession(const uint8_t *data, uint16_t length, uint32_t value)
{
    write_calls++;
    if (!connected || pending || value != session) { return PC_BYTE_STREAM_WRITE_BUSY; }
    if (fail_write) { if (fail_write == 2U) { session++; } return PC_BYTE_STREAM_WRITE_ERROR; }
    assert(length <= sizeof(tx_owned)); memcpy(tx_owned, data, length);
    TxAccept(tx_owned, length); return PC_BYTE_STREAM_WRITE_OK;
}
#endif

uint8_t GroundRadio_MetricsSupportedGet(void) { return 1U; }
GroundRadioResult GroundRadio_Init(void) { return GROUND_RADIO_OK; }
void GroundRadio_Process(void) { }
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length)
{ assert(data != NULL && length == 1U && data[0] == 0x42U); forwarded++; return GROUND_RADIO_OK; }
GroundRadioResult GroundRadio_RxDequeue(uint8_t *data, uint8_t *length, int8_t *rssi, int8_t *snr)
{
    radio_calls++;
    if (radio_pending == 0U) { return GROUND_RADIO_EMPTY; }
    radio_pending--; data[0] = 0x55U; *length = 1U; *rssi = -20; *snr = 1;
    return GROUND_RADIO_OK;
}
void GroundRadio_StatsGet(GroundRadioStats *stats) { memset(stats, 0, sizeof(*stats)); }

static void Complete(void)
{
    GspMinParser parser; GspMinFrame frame; unsigned frames = 0U;
    if (!pending) { return; }
    assert(memcmp(retained, tx_copy, tx_length) == 0);
    GspMinParser_Init(&parser);
    for (uint16_t i = 0U; i < tx_length; i++)
    {
        if (GspMinParser_InputByte(&parser, retained[i], &frame) == GSP_PARSER_FRAME_READY)
        {
            frames++;
            if (frame.type == GSP_TYPE_ACK)
            { assert(frame.payload[0] == GSP_TYPE_AIR_TX && frame.payload[1] == GSP_ACK_OK); acknowledgements++; }
            else if (frame.type == GSP_TYPE_GS_STATUS) { status_frames++; }
            else { assert(frame.type == GSP_TYPE_AIR_RX); radio_frames++; }
        }
    }
    assert(frames == 1U); pending = 0U;
#if defined(GROUND_TEST_USB)
    usb_class.TxState = 0U;
#endif
}

static GroundBridgeResult Step(uint32_t advance)
{
    GroundBridgeDiagnostics diag; GroundBridgeResult result;
    tick += advance; radio_calls = 0U; write_calls = 0U; read_calls = 0U; read_bytes = 0U;
    result = GroundBridge_Process(tick);
    assert(radio_calls <= 4U && write_calls <= 8U && read_calls <= 64U && read_bytes <= 64U);
    assert(GroundBridge_DiagnosticsGet(&diag) == GROUND_BRIDGE_OK && diag.pc_queued_frames <= 4U);
    if (!fail_write) { assert(diag.pc_write_error_count == 0U); }
    if (pending) { assert(memcmp(retained, tx_copy, tx_length) == 0); }
    return result;
}

static void Commands(unsigned count)
{
    uint8_t frame[70], payload[] = {1U, 0x42U};
    uint16_t length = GspMin_BuildFrame(GSP_TYPE_AIR_TX, payload, 2U, frame, sizeof(frame));
    assert(length == 8U);
    for (unsigned i = 0U; i < count; i++) { Feed(frame, length); }
}

static void Drain(void)
{
    for (unsigned i = 0U; i < 160U; i++) { Complete(); assert(Step(0U) == GROUND_BRIDGE_OK); }
    Complete(); assert(acknowledgements + cancelled_acknowledgements == forwarded);
}

int main(int argc, char **argv)
{
    GroundBridgeDiagnostics diag;
    assert(argc == 2); Connect((uint8_t)((strcmp(argv[1], "idle") == 0) ? 0U : 1U));
    assert(GroundBridge_Init() == GROUND_BRIDGE_OK); Complete();
    if (strcmp(argv[1], "idle") == 0)
    {
        for (unsigned i = 0U; i < 60000U; i++) { assert(Step(1000U) == GROUND_BRIDGE_OK); }
        assert(GroundBridge_DiagnosticsGet(&diag) == GROUND_BRIDGE_OK && diag.pc_status_deferred_count > 0U);
        Connect(1U); Drain(); Commands(1U); Drain(); assert(forwarded == 1U);
    }
    else if (strcmp(argv[1], "burst") == 0)
    {
        Commands(5U); assert(Step(1U) == GROUND_BRIDGE_OK); assert(forwarded == 4U);
        assert(GroundBridge_DiagnosticsGet(&diag) == GROUND_BRIDGE_OK && diag.pc_input_backpressure_count > 0U);
        Drain(); assert(forwarded == 5U && acknowledgements == 5U);
    }
    else if (strcmp(argv[1], "radio") == 0)
    {
        radio_pending = 4U; assert(Step(1000U) == GROUND_BRIDGE_OK); Drain();
        assert(radio_frames == 4U && status_frames >= 2U);
    }
    else if (strcmp(argv[1], "slow") == 0)
    {
        Commands(12U); assert(Step(1U) == GROUND_BRIDGE_OK);
        for (unsigned i = 0U; i < 10000U; i++) { assert(Step(1U) == GROUND_BRIDGE_OK); }
        assert(forwarded == 5U && acknowledgements == 0U);
        assert(GroundBridge_DiagnosticsGet(&diag) == GROUND_BRIDGE_OK && diag.pc_status_deferred_count > 0U);
        Drain(); assert(forwarded == 12U && acknowledgements == 12U);
    }
    else if (strcmp(argv[1], "mixed") == 0)
    {
        for (unsigned round = 0U; round < 200U; round++)
        {
            Commands(5U); radio_pending += 4U;
            for (unsigned i = 0U; i < 40U; i++)
            { if (i % 4U == 0U) { Complete(); } assert(Step(25U) == GROUND_BRIDGE_OK); }
            Drain();
        }
        assert(forwarded == 1000U && acknowledgements == 1000U && radio_frames == 800U);
    }
    else if (strcmp(argv[1], "sessions") == 0)
    {
        for (unsigned round = 0U; round < 100U; round++)
        {
            uint8_t frame[70], payload[] = {1U, 0x42U}; unsigned before = forwarded;
            uint16_t length = GspMin_BuildFrame(GSP_TYPE_AIR_TX, payload, 2U, frame, sizeof(frame));
            Feed(frame, 5U); assert(Step(1U) == GROUND_BRIDGE_OK);
            Connect(0U); assert(Step(10000U) == GROUND_BRIDGE_OK); Connect(1U);
            Feed(frame + 5U, (uint16_t)(length - 5U)); assert(Step(1U) == GROUND_BRIDGE_OK);
            assert(forwarded == before); Commands(1U); Drain(); assert(forwarded == before + 1U);
        }
    }
    else if (strcmp(argv[1], "queued-reset") == 0)
    {
        Commands(12U); assert(Step(1U) == GROUND_BRIDGE_OK); assert(forwarded == 4U);
        Connect(0U); assert(Step(10000U) == GROUND_BRIDGE_OK); Connect(1U); Drain();
        assert(forwarded == 4U && acknowledgements == 0U && cancelled_acknowledgements == 4U);
        Commands(1U); Drain(); assert(forwarded == 5U && acknowledgements == 1U);
    }
    else if (strcmp(argv[1], "budget") == 0)
    {
        uint8_t noise[128] = {0U}; Feed(noise, sizeof(noise));
        assert(Step(1U) == GROUND_BRIDGE_OK);
#if !defined(GROUND_TEST_USB)
        assert(read_bytes == 64U && (unsigned)(rx_head - rx_tail) == 64U);
#endif
        assert(Step(1U) == GROUND_BRIDGE_OK); Commands(1U); Drain(); assert(forwarded == 1U);
    }
    else
    {
        assert(strcmp(argv[1], "error") == 0 || strcmp(argv[1], "error-reset") == 0);
        fail_write = (uint8_t)((strcmp(argv[1], "error-reset") == 0) ? 2U : 1U);
        assert(Step(1000U) == GROUND_BRIDGE_PC_ERROR);
        assert(GroundBridge_DiagnosticsGet(&diag) == GROUND_BRIDGE_OK && diag.pc_write_error_count != 0U);
    }
    printf("PASS %s forwarded=%u ACK=%u radio=%u status=%u\n", argv[1], forwarded, acknowledgements, radio_frames, status_frames);
    return 0;
}
