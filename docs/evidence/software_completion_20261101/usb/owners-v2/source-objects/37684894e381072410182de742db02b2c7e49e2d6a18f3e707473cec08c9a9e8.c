#include "usb_cdc_transport.h"
#include "usb_cdc_port.h"
#include "silverstar_assert.h"
#include <stddef.h>

static uint8_t s_rx[USB_CDC_RX_CAPACITY];
static uint8_t s_tx[USB_CDC_TX_CAPACITY];
static uint16_t s_head;
static uint16_t s_tail;
static uint16_t s_count;
static uint16_t s_tx_length;
static uint32_t s_session = 1U;
static uint8_t s_online;
static uint8_t s_exhausted;
static uint8_t s_submitted;
static uint8_t s_armed;
static uint8_t s_retired = 1U;

static void UsbCdc_Check(void)
{
    SILVERSTAR_ASSERT((s_head < USB_CDC_RX_CAPACITY) &&
        (s_tail < USB_CDC_RX_CAPACITY) && (s_count <= USB_CDC_RX_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_BUFFER_CAPACITY);
    SILVERSTAR_ASSERT((s_tx_length <= USB_CDC_TX_CAPACITY) &&
        (s_submitted <= 1U) && ((s_submitted == 0U) || (s_tx_length != 0U)),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT(((s_head + USB_CDC_RX_CAPACITY - s_tail) %
        USB_CDC_RX_CAPACITY) == (s_count % USB_CDC_RX_CAPACITY),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_SEQUENCE_INVARIANT);
    SILVERSTAR_ASSERT((s_online <= 1U) && (s_armed <= 1U) &&
        (s_retired <= 1U) && (s_exhausted <= 1U) &&
        ((s_retired == 0U) || ((s_online == 0U) && (s_tx_length == 0U))),
        SILVERSTAR_ASSERT_MODULE_GENERATED,
        SILVERSTAR_ASSERT_REASON_STATE_INVARIANT);
}

static void UsbCdc_Invalidate(void)
{
    s_online = 0U;
    s_armed = 0U;
    s_head = 0U;
    s_tail = 0U;
    s_count = 0U;
    if (s_session == UINT32_MAX) { s_exhausted = 1U; }
    else { s_session++; }
    /* Submitted bytes remain owned until explicit successful cancellation. */
}

void UsbCdc_LinkDown(void)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    UsbCdc_Invalidate();
    UsbCdcPort_Unlock(token);
}

UsbCdcResult UsbCdc_Quiesced(void)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if (s_online != 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    /* Caller has proved successful hardware retirement, not just timeout. */
    s_tx_length = 0U;
    s_submitted = 0U;
    s_retired = 1U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Configure(void)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if ((s_online != 0U) || (s_retired == 0U))
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    if (s_exhausted != 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    s_online = 1U;
    s_retired = 0U;
    /* The native class performs the first receive arm during Init. */
    s_armed = 1U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Receive(const uint8_t *data, uint16_t length)
{
    uint16_t index;
    uint32_t token;
    if ((data == NULL) || (length > USB_CDC_PACKET_SIZE))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if (s_online == 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    if ((s_armed == 0U) || (length > (USB_CDC_RX_CAPACITY - s_count)))
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    s_armed = 0U;
    for (index = 0U; index < USB_CDC_PACKET_SIZE; index++)
    {
        if (index >= length) { break; }
        s_rx[s_head] = data[index];
        s_head = (uint16_t)((s_head + 1U) % USB_CDC_RX_CAPACITY);
    }
    s_count = (uint16_t)(s_count + length);
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Read(uint8_t *data, uint16_t capacity,
    uint16_t *length, uint32_t *session)
{
    uint16_t count;
    uint32_t token;
    if ((data == NULL) || (length == NULL) || (session == NULL) ||
        (capacity == 0U)) { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    UsbCdc_Check();
    *length = 0U;
    *session = s_session;
    if (s_online == 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    for (count = 0U; count < USB_CDC_RX_CAPACITY; count++)
    {
        if ((count >= capacity) || (count >= s_count)) { break; }
        data[count] = s_rx[s_tail];
        s_tail = (uint16_t)((s_tail + 1U) % USB_CDC_RX_CAPACITY);
    }
    s_count = (uint16_t)(s_count - count);
    *length = count;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

UsbCdcResult UsbCdc_Write(const uint8_t *data, uint16_t length,
    uint32_t session)
{
    uint16_t index;
    uint32_t token;
    if ((data == NULL) || (length == 0U) || (length > USB_CDC_TX_CAPACITY))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if ((s_online == 0U) || (session != s_session))
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    if (s_tx_length != 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_BUSY; }
    for (index = 0U; index < USB_CDC_TX_CAPACITY; index++)
    {
        if (index >= length) { break; }
        s_tx[index] = data[index];
    }
    s_tx_length = length;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}

static UsbCdcResult UsbCdc_TxService(void)
{
    UsbCdcResult result;
    if (s_tx_length == 0U) { return USB_CDC_OK; }
    result = UsbCdcPort_TxState();
    if (result != USB_CDC_OK) { return result; }
    if (s_submitted != 0U)
    {
        s_tx_length = 0U;
        s_submitted = 0U;
        return USB_CDC_OK;
    }
    result = UsbCdcPort_Submit(s_tx, s_tx_length);
    if (result == USB_CDC_OK) { s_submitted = 1U; }
    return result;
}

UsbCdcResult UsbCdc_Service(void)
{
    UsbCdcResult result;
    uint32_t token = UsbCdcPort_Lock();
    UsbCdc_Check();
    if (s_online == 0U)
    { UsbCdcPort_Unlock(token); return USB_CDC_OFFLINE; }
    result = UsbCdc_TxService();
    if ((result != USB_CDC_OK) && (result != USB_CDC_BUSY))
    {
        UsbCdc_Invalidate();
        UsbCdcPort_Unlock(token);
        return result;
    }
    if ((s_armed == 0U) &&
        ((USB_CDC_RX_CAPACITY - s_count) >= USB_CDC_PACKET_SIZE))
    {
        UsbCdcResult receive = UsbCdcPort_Rearm();
        if (receive == USB_CDC_OK) { s_armed = 1U; }
        else if (receive != USB_CDC_BUSY)
        { UsbCdc_Invalidate(); result = receive; }
        else { result = USB_CDC_BUSY; }
    }
    UsbCdcPort_Unlock(token);
    return result;
}

uint32_t UsbCdc_SessionGet(void)
{
    uint32_t token = UsbCdcPort_Lock();
    uint32_t session = s_session;
    UsbCdcPort_Unlock(token);
    return session;
}
