#include "ground_bridge.h"

#include <string.h>
#include <stddef.h>

#include "ground_radio.h"
#include "gsp_min_protocol.h"
#include "pc_byte_stream.h"
#include "silverstar_assert.h"

#define GROUND_PC_CHUNK_SIZE 64U
#define GROUND_STATUS_PERIOD_MS 1000U
#define GROUND_AIR_MAX_LEN (GSP_MIN_MAX_PAYLOAD_LEN - 3U)
#define GROUND_RADIO_BUFFER_LEN 64U
#define GROUND_PC_QUEUE_DEPTH 4U
#define GROUND_RADIO_RX_MAX_PER_PROCESS 4U

static GspMinParser s_gsp_parser;
static uint32_t s_last_status_ms;
static uint32_t s_bridge_crc_error_count;
static uint32_t s_pc_write_error_count;
static uint32_t s_pc_write_busy_count;
static uint8_t s_initialized;
static uint8_t s_pc_frames[GROUND_PC_QUEUE_DEPTH][GSP_MIN_MAX_FRAME_LEN];
static uint16_t s_pc_frame_lengths[GROUND_PC_QUEUE_DEPTH];
static uint8_t s_pc_frame_head;
static uint8_t s_pc_frame_tail;
static uint8_t s_pc_frame_count;

static GroundBridgeResult GroundBridge_FrameWrite(const uint8_t *frame, uint16_t length)
{
    if ((frame == NULL) || (length == 0U) || (length > GSP_MIN_MAX_FRAME_LEN)
        || (s_pc_frame_count >= GROUND_PC_QUEUE_DEPTH))
    {
        s_pc_write_error_count++;
        return GROUND_BRIDGE_PC_ERROR;
    }
    memcpy(s_pc_frames[s_pc_frame_tail], frame, length);
    s_pc_frame_lengths[s_pc_frame_tail] = length;
    s_pc_frame_tail = (uint8_t)((s_pc_frame_tail + 1U) % GROUND_PC_QUEUE_DEPTH);
    s_pc_frame_count++;
    return GROUND_BRIDGE_OK;
}

static GroundBridgeResult GroundBridge_PcFlush(void)
{
    uint8_t flushed;
    SILVERSTAR_ASSERT(s_pc_frame_count <= GROUND_PC_QUEUE_DEPTH,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_pc_frame_head < GROUND_PC_QUEUE_DEPTH,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (flushed = 0U; flushed < GROUND_PC_QUEUE_DEPTH; flushed++)
    {
        if (s_pc_frame_count == 0U) { break; }
        uint16_t expected = s_pc_frame_lengths[s_pc_frame_head];
        PcByteStreamWriteResult write_result = PcByteStream_Write(
            s_pc_frames[s_pc_frame_head], expected);
        if (write_result == PC_BYTE_STREAM_WRITE_BUSY)
        {
            if (s_pc_write_busy_count < UINT32_MAX) { s_pc_write_busy_count++; }
            return GROUND_BRIDGE_OK;
        }
        if (write_result != PC_BYTE_STREAM_WRITE_OK)
        {
            if (s_pc_write_error_count < UINT32_MAX) { s_pc_write_error_count++; }
            return GROUND_BRIDGE_PC_ERROR;
        }
        s_pc_frame_head = (uint8_t)((s_pc_frame_head + 1U) % GROUND_PC_QUEUE_DEPTH);
        s_pc_frame_count--;
    }
    return GROUND_BRIDGE_OK;
}

static GroundBridgeResult GroundBridge_AckSend(uint8_t type, uint8_t result, uint8_t detail)
{
    uint8_t frame[GSP_MIN_MAX_FRAME_LEN];
    uint16_t length = GspMin_BuildAckFrame(type, result, detail, frame, sizeof(frame));
    return GroundBridge_FrameWrite(frame, length);
}

static GroundBridgeResult GroundBridge_PcFrameHandle(const GspMinFrame *frame)
{
    uint8_t air_length;
    if (frame == NULL)
    {
        return GROUND_BRIDGE_PC_ERROR;
    }
    SILVERSTAR_ASSERT_OBJECT(frame, GspMinFrame,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    SILVERSTAR_ASSERT(frame->payload_len <= GSP_MIN_MAX_PAYLOAD_LEN,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    if (frame->type != GSP_TYPE_AIR_TX)
    {
        return GroundBridge_AckSend(frame->type, GSP_ACK_BAD_TYPE, frame->type);
    }
    if (frame->payload_len < 1U)
    {
        return GroundBridge_AckSend(frame->type, GSP_ACK_BAD_PARAM, 0U);
    }
    air_length = frame->payload[0];
    if ((air_length == 0U) || ((uint16_t)air_length + 1U != frame->payload_len))
    {
        return GroundBridge_AckSend(frame->type, GSP_ACK_BAD_LEN, air_length);
    }
    if (air_length > GROUND_AIR_MAX_LEN)
    {
        return GroundBridge_AckSend(frame->type, GSP_ACK_BAD_PARAM, air_length);
    }
    /* The AIR bytes are opaque. The Flight Controller and GSHC own semantics. */
    if (GroundRadio_TxEnqueue(&frame->payload[1], air_length) != GROUND_RADIO_OK)
    {
        return GroundBridge_AckSend(frame->type, GSP_ACK_BUSY, 0U);
    }
    return GroundBridge_AckSend(frame->type, GSP_ACK_OK, 0U);
}

static uint16_t GroundBridge_CrcCountGet(const GroundRadioStats *radio)
{
    uint32_t parser_errors = GspMinParser_GetCrcErrorCount(&s_gsp_parser);
    uint32_t total;
    SILVERSTAR_ASSERT_OBJECT(radio, GroundRadioStats,
        SILVERSTAR_ASSERT_MODULE_SYSTEM);
    if ((radio->rx_crc_error >= UINT16_MAX) ||
        (parser_errors >= UINT16_MAX) ||
        (s_bridge_crc_error_count >= UINT16_MAX))
    { return UINT16_MAX; }
    total = radio->rx_crc_error + parser_errors + s_bridge_crc_error_count;
    return (uint16_t)((total >= UINT16_MAX) ? UINT16_MAX : total);
}

static GroundBridgeResult GroundBridge_StatusSend(void)
{
    GroundRadioStats radio;
    GspGsStatusPayload status;
    uint8_t frame[GSP_MIN_MAX_FRAME_LEN];
    uint16_t length;

    memset(&radio, 0, sizeof(radio));
    memset(&status, 0, sizeof(status));
    GroundRadio_StatsGet(&radio);
    SILVERSTAR_ASSERT(radio.radio_state <= GSP_RADIO_STATE_BUSY,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_ENUM_RANGE);
    status.radio_state = radio.radio_state;
    status.gs_state = (radio.radio_state == GSP_RADIO_STATE_NOT_INIT) ?
        GSP_GS_STATE_IDLE : GSP_GS_STATE_INIT_OK;
    if (radio.radio_state == GSP_RADIO_STATE_RX)
    {
        status.gs_state = GSP_GS_STATE_RX_MODE;
    }
    else if (radio.radio_state == GSP_RADIO_STATE_TX)
    {
        status.gs_state = GSP_GS_STATE_TX_MODE;
    }
    status.tx_cnt = radio.tx_ok;
    status.rx_cnt = radio.rx_ok;
    status.crc_err_cnt = GroundBridge_CrcCountGet(&radio);
    length = GspMin_BuildGsStatusFrame(&status, frame, sizeof(frame));
    SILVERSTAR_ASSERT(length != 0U, SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_LENGTH_RANGE);
    return GroundBridge_FrameWrite(frame, length);
}

static void GroundBridge_StateReset(void)
{
    GspMinParser_Init(&s_gsp_parser);
    s_last_status_ms = 0U;
    s_bridge_crc_error_count = 0U;
    s_pc_write_error_count = 0U;
    s_pc_write_busy_count = 0U;
    s_pc_frame_head = 0U;
    s_pc_frame_tail = 0U;
    s_pc_frame_count = 0U;
    s_initialized = 0U;
}

GroundBridgeResult GroundBridge_Init(void)
{
    GroundBridge_StateReset();
    if (PcByteStream_Init() != PC_BYTE_STREAM_INIT_OK)
    {
        return GROUND_BRIDGE_PC_ERROR;
    }
    if (GroundRadio_Init() != GROUND_RADIO_OK)
    {
        return GROUND_BRIDGE_RADIO_ERROR;
    }
    s_initialized = 1U;
    if (GroundBridge_StatusSend() != GROUND_BRIDGE_OK)
    {
        return GROUND_BRIDGE_PC_ERROR;
    }
    return GroundBridge_PcFlush();
}

static GroundBridgeResult GroundBridge_PcInputProcess(void)
{
    uint8_t pc_bytes[GROUND_PC_CHUNK_SIZE];
    GspMinFrame parsed;
    uint16_t count;
    uint16_t index;
    GroundBridgeResult bridge_result = GROUND_BRIDGE_OK;
    count = PcByteStream_Read(pc_bytes, sizeof(pc_bytes));
    if (count > sizeof(pc_bytes)) { return GROUND_BRIDGE_PC_ERROR; }
    SILVERSTAR_ASSERT(count <= GROUND_PC_CHUNK_SIZE,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (index = 0U; index < count; index++)
    {
        if (GspMinParser_InputByte(&s_gsp_parser, pc_bytes[index], &parsed)
            == GSP_PARSER_FRAME_READY)
        {
            if (GroundBridge_PcFrameHandle(&parsed) != GROUND_BRIDGE_OK)
            {
                bridge_result = GROUND_BRIDGE_PC_ERROR;
            }
        }
    }
    SILVERSTAR_ASSERT(s_gsp_parser.payload_len <= GSP_MIN_MAX_PAYLOAD_LEN,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    return bridge_result;
}

static GroundBridgeResult GroundBridge_RadioInputProcess(void)
{
    uint8_t air_bytes[GROUND_RADIO_BUFFER_LEN];
    uint8_t air_length;
    int8_t rssi_dbm;
    int8_t snr_db;
    uint8_t output[GSP_MIN_MAX_FRAME_LEN];
    uint16_t output_length;
    uint8_t radio_processed;
    GroundBridgeResult bridge_result = GROUND_BRIDGE_OK;
    SILVERSTAR_ASSERT(s_pc_frame_count <= GROUND_PC_QUEUE_DEPTH,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    for (radio_processed = 0U;
         radio_processed < GROUND_RADIO_RX_MAX_PER_PROCESS;
         radio_processed++)
    {
        if (s_pc_frame_count >= GROUND_PC_QUEUE_DEPTH) { break; }
        if (GroundRadio_RxDequeue(air_bytes, &air_length, &rssi_dbm, &snr_db)
            != GROUND_RADIO_OK) { break; }
        if (air_length > sizeof(air_bytes))
        { return GROUND_BRIDGE_RADIO_ERROR; }
        SILVERSTAR_ASSERT(air_length <= GROUND_RADIO_BUFFER_LEN,
            SILVERSTAR_ASSERT_MODULE_SYSTEM,
            SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
        if ((air_length == 0U) || (air_length > GROUND_AIR_MAX_LEN))
        {
            if (s_bridge_crc_error_count < UINT32_MAX)
            { s_bridge_crc_error_count++; }
            continue;
        }
        output_length = GspMin_BuildAirRxFrame(
            rssi_dbm, (int8_t)(snr_db * 4), air_bytes, air_length,
            output, sizeof(output));
        if (GroundBridge_FrameWrite(output, output_length) != GROUND_BRIDGE_OK)
        {
            bridge_result = GROUND_BRIDGE_PC_ERROR;
        }
    }
    return bridge_result;
}

GroundBridgeResult GroundBridge_Process(uint32_t now_ms)
{
    GroundBridgeResult bridge_result = GROUND_BRIDGE_OK;
    GroundBridgeResult radio_result;
    if (s_initialized == 0U) { return GROUND_BRIDGE_RADIO_ERROR; }
    SILVERSTAR_ASSERT(s_initialized == 1U,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
    SILVERSTAR_ASSERT(s_pc_frame_count <= GROUND_PC_QUEUE_DEPTH,
        SILVERSTAR_ASSERT_MODULE_SYSTEM,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    GroundRadio_Process();
    if (GroundBridge_PcFlush() != GROUND_BRIDGE_OK)
    { bridge_result = GROUND_BRIDGE_PC_ERROR; }
    if (GroundBridge_PcInputProcess() != GROUND_BRIDGE_OK)
    { bridge_result = GROUND_BRIDGE_PC_ERROR; }
    radio_result = GroundBridge_RadioInputProcess();
    if (radio_result != GROUND_BRIDGE_OK)
    { bridge_result = radio_result; }
    if ((now_ms - s_last_status_ms) >= GROUND_STATUS_PERIOD_MS)
    {
        s_last_status_ms = now_ms;
        if (GroundBridge_StatusSend() != GROUND_BRIDGE_OK)
        {
            bridge_result = GROUND_BRIDGE_PC_ERROR;
        }
    }
    if (GroundBridge_PcFlush() != GROUND_BRIDGE_OK)
    {
        bridge_result = GROUND_BRIDGE_PC_ERROR;
    }
    return bridge_result;
}

GroundBridgeResult GroundBridge_DiagnosticsGet(
    GroundBridgeDiagnostics *diagnostics)
{
    if (diagnostics == NULL) { return GROUND_BRIDGE_PC_ERROR; }
    diagnostics->pc_write_busy_count = s_pc_write_busy_count;
    diagnostics->pc_write_error_count = s_pc_write_error_count;
    diagnostics->pc_rx_overflow_count = PcByteStream_OverflowCount_Get();
    diagnostics->pc_queued_frames = s_pc_frame_count;
    return GROUND_BRIDGE_OK;
}
