#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "pc_byte_stream.h"
#include "usbd_cdc_if.h"

uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
static USBD_CDC_HandleTypeDef s_class;
static uint8_t s_transmit_result = USBD_BUSY;
static uint8_t *s_retained;
static uint16_t s_length;
static unsigned s_calls;

uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{
    assert(usb_test_mask == 1U);
    assert(data != 0 && length <= 70U);
    s_calls++;
    if (s_transmit_result == USBD_OK)
    {
        s_retained = data;
        s_length = length;
        s_class.TxState = 1U;
    }
    return s_transmit_result;
}

int main(void)
{
    uint8_t input[700];
    uint8_t output[700];
    uint16_t index;
    unsigned calls;
    assert(PcByteStream_Init() == PC_BYTE_STREAM_INIT_OK);
    assert(PcByteStream_ResetPending_Get() == 1U);
    assert(PcByteStream_ResetPending_Get() == 0U);
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    assert(s_calls == 0U && usb_test_mask == 0U);
    hUsbDeviceFS.dev_state = USBD_STATE_CONFIGURED;
    hUsbDeviceFS.pClassData = &s_class;
    for (index = 0U; index < 700U; index++) { input[index] = (uint8_t)index; }
    PcByteStream_OnUsbReceive(input, 700U);
    assert(PcByteStream_OverflowCount_Get() == 189U);
    assert(PcByteStream_Read(output, 700U) == 511U);
    for (index = 0U; index < 511U; index++) { assert(output[index] == input[index]); }
    assert(PcByteStream_Read(output, 700U) == 0U);
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    s_transmit_result = USBD_OK;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_OK);
    assert(s_retained != input && s_length == 3U);
    input[0] = 99U;
    assert(s_retained[0] == 0U && s_retained[1] == 1U && s_retained[2] == 2U);
    calls = s_calls;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    assert(s_calls == calls && s_retained[0] == 0U);
    s_class.TxState = 0U;
    assert(PcByteStream_Write(input, 64U) == PC_BYTE_STREAM_WRITE_OK);
    /* A full packet may still own the buffer while its ZLP completes. */
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    s_class.TxState = 0U;
    s_transmit_result = USBD_FAIL;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_ERROR);
    assert(PcByteStream_Write(input, 71U) == PC_BYTE_STREAM_WRITE_ERROR);
    assert(PcByteStream_Write(0, 3U) == PC_BYTE_STREAM_WRITE_ERROR);
    PcByteStream_OnUsbReceive(input, 500U);
    assert(PcByteStream_Read(output, 490U) == 490U);
    PcByteStream_OnUsbReceive(input, 500U);
    assert(PcByteStream_Read(output, 700U) == 510U);
    assert(memcmp(output, input + 490, 10U) == 0);
    assert(memcmp(output + 10, input, 500U) == 0);
    PcByteStream_OnUsbReceive(input, 3U);
    hUsbDeviceFS.dev_state = 0U;
    hUsbDeviceFS.pClassData = 0;
    PcByteStream_OnUsbReset();
    assert(PcByteStream_Read(output, 700U) == 0U);
    assert(PcByteStream_ResetPending_Get() == 1U);
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    hUsbDeviceFS.pClassData = &s_class;
    hUsbDeviceFS.dev_state = USBD_STATE_CONFIGURED;
    s_class.TxState = 0U;
    s_transmit_result = USBD_OK;
    {
        uint32_t old_session = PcByteStream_Session_Get();
        PcByteStream_OnUsbReset();
        assert(PcByteStream_Session_Check(old_session) == 0U);
        assert(PcByteStream_WriteSession(input, 3U, old_session) == PC_BYTE_STREAM_WRITE_BUSY);
    }
    calls = s_calls;
    usb_test_mask = 1U;
    assert(PcByteStream_Write(input, 3U) == PC_BYTE_STREAM_WRITE_BUSY);
    assert(s_calls == calls);
    assert(usb_test_mask == 1U);
    usb_test_mask = 0U;
    return 0;
}
