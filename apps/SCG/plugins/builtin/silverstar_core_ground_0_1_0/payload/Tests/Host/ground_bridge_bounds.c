
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "ground_bridge.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"
#include "pc_byte_stream.h"

static uint32_t s_rx_dequeue_calls;
static uint32_t s_pc_write_calls;
static uint8_t s_invalid_packets = 1U;
static PcByteStreamWriteResult s_write_result = PC_BYTE_STREAM_WRITE_OK;

GroundRadioResult GroundRadio_Init(void) { return GROUND_RADIO_OK; }
void GroundRadio_Process(void) { }
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data, uint8_t length)
{ (void)data; (void)length; return GROUND_RADIO_OK; }
GroundRadioResult GroundRadio_RxDequeue(uint8_t *data, uint8_t *length,
    int8_t *rssi, int8_t *snr)
{
    s_rx_dequeue_calls++;
    data[0] = 0xAAU;
    *length = s_invalid_packets ? 0U : 1U;
    *rssi = -70;
    *snr = 4;
    return GROUND_RADIO_OK;
}
void GroundRadio_StatsGet(GroundRadioStats *stats)
{ (void)memset(stats, 0, sizeof(*stats)); }
PcByteStreamInitResult PcByteStream_Init(void)
{ return PC_BYTE_STREAM_INIT_OK; }
uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity)
{ (void)buffer; (void)capacity; return 0U; }
PcByteStreamWriteResult PcByteStream_Write(const uint8_t *data, uint16_t length)
{ assert(data != 0 && length != 0U); s_pc_write_calls++; return s_write_result; }
uint32_t PcByteStream_OverflowCount_Get(void) { return 0U; }

int main(void)
{
    uint8_t oversized_air[UINT8_MAX] = {0U};
    uint8_t gsp_output[GSP_MIN_MAX_FRAME_LEN];
    assert(GspMin_BuildAirRxFrame(-70, 4, oversized_air,
        UINT8_MAX, gsp_output, sizeof(gsp_output)) == 0U);
    assert(GroundBridge_Init() == GROUND_BRIDGE_OK);
    assert(s_pc_write_calls == 1U);
    assert(GroundBridge_Process(1U) == GROUND_BRIDGE_OK);
    assert(s_rx_dequeue_calls == 4U);
    assert(GroundBridge_Process(2U) == GROUND_BRIDGE_OK);
    assert(s_rx_dequeue_calls == 8U);
    s_invalid_packets = 0U;
    assert(GroundBridge_Process(3U) == GROUND_BRIDGE_OK);
    assert(s_rx_dequeue_calls == 12U);
    assert(s_pc_write_calls == 5U);
    s_write_result = PC_BYTE_STREAM_WRITE_BUSY;
    assert(GroundBridge_Process(4U) == GROUND_BRIDGE_OK);
    {
        GroundBridgeDiagnostics diagnostics;
        assert(GroundBridge_DiagnosticsGet(&diagnostics) == GROUND_BRIDGE_OK);
        assert(diagnostics.pc_queued_frames != 0U);
        assert(diagnostics.pc_write_busy_count != 0U);
        assert(diagnostics.pc_write_error_count == 0U);
    }
    s_write_result = PC_BYTE_STREAM_WRITE_ERROR;
    assert(GroundBridge_Process(5U) == GROUND_BRIDGE_PC_ERROR);
    {
        GroundBridgeDiagnostics diagnostics;
        assert(GroundBridge_DiagnosticsGet(&diagnostics) == GROUND_BRIDGE_OK);
        assert(diagnostics.pc_write_error_count != 0U);
    }
    return 0;
}
