
#include <assert.h>
#include <stdint.h>
#include "pc_byte_stream.h"
#include "usbd_cdc_if.h"

static uint8_t s_transmit_result = USBD_BUSY;
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{ assert(data != 0 && length == 3U); return s_transmit_result; }

int main(void)
{
    uint8_t input[700];
    uint8_t output[700];
    uint16_t index;
    assert(PcByteStream_Init() == PC_BYTE_STREAM_INIT_OK);
    for (index = 0U; index < 700U; index++)
    { input[index] = (uint8_t)index; }
    PcByteStream_OnUsbReceive(input, 700U);
    assert(PcByteStream_OverflowCount_Get() == 189U);
    assert(PcByteStream_Read(output, 700U) == 511U);
    for (index = 0U; index < 511U; index++)
    { assert(output[index] == input[index]); }
    assert(PcByteStream_Read(output, 700U) == 0U);
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    s_transmit_result = USBD_OK;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_OK);
    s_transmit_result = USBD_FAIL;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_ERROR);
    return 0;
}
