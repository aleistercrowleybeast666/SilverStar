#include "pc_byte_stream.h"
#include "native_runtime.h"
#include "native_clock.h"
#include "gsp_min_protocol.h"
#include "silverstar_assert.h"
#include "main.h"
#include "usbd_conf.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
#include <stddef.h>

#define PC_USB_RX_CAPACITY 512U

extern USBD_HandleTypeDef hUsbDeviceFS;

static uint8_t s_rx_buffer[PC_USB_RX_CAPACITY];
static uint8_t s_tx_buffer[GSP_MIN_MAX_FRAME_LEN];
static volatile uint16_t s_rx_head;
static volatile uint16_t s_rx_tail;
static volatile uint32_t s_rx_overflow_count;
static volatile uint8_t s_reset_pending;
static volatile uint32_t s_session;
static volatile uint8_t s_session_exhausted;

PcByteStreamInitResult PcByteStream_Init(void)
{
    PcByteStream_OnUsbReset();
    return PC_BYTE_STREAM_INIT_OK;
}

void PcByteStream_OnUsbReset(void)
{
    uint32_t saved_mask = __get_PRIMASK();
    __disable_irq();
    s_rx_head = 0U;
    s_rx_tail = 0U;
    s_reset_pending = 1U;
    if (s_session == UINT32_MAX) { s_session_exhausted = 1U; }
    else { s_session++; }
    __set_PRIMASK(saved_mask);
}

uint8_t PcByteStream_ResetPending_Get(void)
{
    uint32_t saved_mask = __get_PRIMASK();
    uint8_t pending;
    __disable_irq();
    pending = s_reset_pending;
    s_reset_pending = 0U;
    __set_PRIMASK(saved_mask);
    return pending;
}

void PcByteStream_OnUsbReceive(const uint8_t *data, uint16_t length)
{
    uint16_t index;
    uint32_t skipped;
    if (data == NULL) { return; }
    SILVERSTAR_ASSERT((s_rx_head < PC_USB_RX_CAPACITY) &&
        (s_rx_tail < PC_USB_RX_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (index = 0U; (index < length) && (index < PC_USB_RX_CAPACITY);
         index++)
    {
        uint16_t next = (uint16_t)((s_rx_head + 1U) % PC_USB_RX_CAPACITY);
        if (next == s_rx_tail) { break; }
        s_rx_buffer[s_rx_head] = data[index];
        __DMB();
        s_rx_head = next;
    }
    skipped = (uint32_t)(length - index);
    if (skipped > (UINT32_MAX - s_rx_overflow_count))
    { s_rx_overflow_count = UINT32_MAX; }
    else { s_rx_overflow_count += skipped; }
}

uint16_t PcByteStream_Read(uint8_t *buffer, uint16_t capacity)
{
    uint32_t session;
    return PcByteStream_ReadSession(buffer, capacity, &session);
}

uint16_t PcByteStream_ReadSession(uint8_t *buffer, uint16_t capacity,
    uint32_t *session)
{
    uint32_t saved_mask;
    uint16_t count;
    if ((buffer == NULL) || (capacity == 0U) || (session == NULL)) { return 0U; }
    saved_mask = __get_PRIMASK();
    __disable_irq();
    *session = s_session;
    if (s_session_exhausted != 0U) { __set_PRIMASK(saved_mask); return 0U; }
    SILVERSTAR_ASSERT((s_rx_head < PC_USB_RX_CAPACITY) &&
        (s_rx_tail < PC_USB_RX_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    for (count = 0U; (count < capacity) &&
         (count < PC_USB_RX_CAPACITY); count++)
    {
        if (s_rx_tail == s_rx_head) { break; }
        buffer[count] = s_rx_buffer[s_rx_tail];
        s_rx_tail = (uint16_t)((s_rx_tail + 1U) % PC_USB_RX_CAPACITY);
    }
    __set_PRIMASK(saved_mask);
    return count;
}

PcByteStreamWriteResult PcByteStream_Write(const uint8_t *data,
                                          uint16_t length)
{
    return PcByteStream_WriteSession(data, length, PcByteStream_Session_Get());
}

PcByteStreamWriteResult PcByteStream_WriteSession(const uint8_t *data,
    uint16_t length, uint32_t session)
{
    uint32_t saved_mask;
    uint8_t result;
    uint16_t index;
    USBD_CDC_HandleTypeDef *cdc;
    if ((data == NULL) || (length == 0U) ||
        (length > GSP_MIN_MAX_FRAME_LEN))
    { return PC_BYTE_STREAM_WRITE_ERROR; }
    /* The native tick must advance before publication. Probe with interrupts
     * enabled; recheck READY/session below after taking the publication lock. */
    if ((NativeRuntime_ReadyGet() == 0U) || (NativeClock_ContextAllowedGet() == 0U))
    { return PC_BYTE_STREAM_WRITE_BUSY; }
    if (NativeClock_DelayUs(1U) != NativeClockResult_Ok)
    { return PC_BYTE_STREAM_WRITE_ERROR; }
    saved_mask = __get_PRIMASK();
    __disable_irq();
    if ((session != s_session) || (s_session_exhausted != 0U))
    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_WRITE_BUSY; }
    if (NativeRuntime_ReadyGet() == 0U)
    { __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_WRITE_BUSY; }
    if ((hUsbDeviceFS.dev_state == USBD_STATE_CONFIGURED) &&
        ((hUsbDeviceFS.classId != 0U) || (hUsbDeviceFS.pClassDataCmsit[0] == NULL) ||
         (hUsbDeviceFS.pClassData != hUsbDeviceFS.pClassDataCmsit[0])))
    { NativeRuntime_TransportFaultRecord(); __set_PRIMASK(saved_mask); return PC_BYTE_STREAM_WRITE_ERROR; }
    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (hUsbDeviceFS.pClassDataCmsit[0] == NULL))
    {
        __set_PRIMASK(saved_mask);
        return PC_BYTE_STREAM_WRITE_BUSY;
    }
    cdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassDataCmsit[0];
    if (cdc->TxState != 0U)
    {
        __set_PRIMASK(saved_mask);
        return PC_BYTE_STREAM_WRITE_BUSY;
    }
    for (index = 0U; (index < length) &&
         (index < GSP_MIN_MAX_FRAME_LEN); index++)
    { s_tx_buffer[index] = data[index]; }
    /* Own the bytes until the stack retires TxState, including a trailing ZLP.
       OK means accepted, not delivered. Reset/deinit aborts the old transfer.
       USB callbacks cannot run between the state check and publication. */
    result = CDC_Transmit_FS(s_tx_buffer, length);
    __set_PRIMASK(saved_mask);
    if (result == USBD_BUSY) { return PC_BYTE_STREAM_WRITE_BUSY; }
    return (result == USBD_OK) ? PC_BYTE_STREAM_WRITE_OK :
        PC_BYTE_STREAM_WRITE_ERROR;
}

uint32_t PcByteStream_OverflowCount_Get(void)
{
    return s_rx_overflow_count;
}

uint32_t PcByteStream_Session_Get(void) { return s_session; }

uint8_t PcByteStream_Session_Check(uint32_t session)
{
    return ((session == s_session) && (s_session_exhausted == 0U)) ? 1U : 0U;
}

uint8_t PcByteStream_Session_Enter(uint32_t session, uint32_t *token)
{
    uint32_t saved_mask;
    if (token == NULL) { return 0U; }
    saved_mask = __get_PRIMASK();
    __disable_irq();
    if (PcByteStream_Session_Check(session) == 0U)
    { __set_PRIMASK(saved_mask); return 0U; }
    *token = saved_mask;
    return 1U;
}

void PcByteStream_Session_Exit(uint32_t token) { __set_PRIMASK(token); }
