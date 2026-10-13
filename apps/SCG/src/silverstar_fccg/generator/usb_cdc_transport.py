"""Protocol-independent, opt-in CDC integration kit; no native source rewriting."""

HEADER = '''#ifndef __USB_CDC_TRANSPORT_H
#define __USB_CDC_TRANSPORT_H
#include <stdint.h>
#define USB_CDC_RX_CAPACITY 512U
#define USB_CDC_TX_CAPACITY 256U
#define USB_CDC_PACKET_SIZE 64U
typedef enum
{
    USB_CDC_OK = 0, USB_CDC_BUSY, USB_CDC_OFFLINE,
    USB_CDC_INVALID, USB_CDC_FAULT
} UsbCdcResult;
/* OK from Write means queued; never a peer receipt/delivery acknowledgement. */
UsbCdcResult UsbCdc_Configure(void);
void UsbCdc_LinkDown(void);
UsbCdcResult UsbCdc_Quiesced(void);
UsbCdcResult UsbCdc_Receive(const uint8_t *data, uint16_t length);
UsbCdcResult UsbCdc_Read(uint8_t *data, uint16_t capacity,
    uint16_t *length, uint32_t *session);
UsbCdcResult UsbCdc_Write(const uint8_t *data, uint16_t length,
    uint32_t session);
UsbCdcResult UsbCdc_Service(void);
uint32_t UsbCdc_SessionGet(void);
#endif
'''

PORT_HEADER = '''#ifndef __USB_CDC_PORT_H
#define __USB_CDC_PORT_H
#include "usb_cdc_transport.h"
/* Fixed port functions; called with interrupts masked except Lock/Unlock.
 * No timeout may release TX ownership. Quiesced is a separate explicit hook. */
uint32_t UsbCdcPort_Lock(void);
void UsbCdcPort_Unlock(uint32_t token);
UsbCdcResult UsbCdcPort_TxState(void);
UsbCdcResult UsbCdcPort_Submit(uint8_t *data, uint16_t length);
UsbCdcResult UsbCdcPort_Rearm(void);
#endif
'''

SOURCE = '''#include "usb_cdc_transport.h"
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
'''

CLASSIC_PORT = '''#include "usb_cdc_port.h"
#include "main.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
#include <stddef.h>

extern USBD_HandleTypeDef hUsbDeviceFS;
_Static_assert(CDC_DATA_FS_MAX_PACKET_SIZE == USB_CDC_PACKET_SIZE,
    "Transport requires a 64-byte native FS endpoint");

uint32_t UsbCdcPort_Lock(void)
{
    uint32_t token = __get_PRIMASK();
    __disable_irq();
    __DMB();
    return token;
}

void UsbCdcPort_Unlock(uint32_t token)
{
    __DMB();
    __set_PRIMASK(token);
}

UsbCdcResult UsbCdcPort_TxState(void)
{
    USBD_CDC_HandleTypeDef *cdc;
@CLASS_GUARD@
    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (@CLASS_DATA@ == NULL)) { return USB_CDC_OFFLINE; }
    cdc = (USBD_CDC_HandleTypeDef *)@CLASS_DATA@;
    return (cdc->TxState == 0U) ? USB_CDC_OK : USB_CDC_BUSY;
}

UsbCdcResult UsbCdcPort_Submit(uint8_t *data, uint16_t length)
{
    uint8_t result;
    UsbCdcResult state = UsbCdcPort_TxState();
    if (state != USB_CDC_OK) { return state; }
    if ((data == NULL) || (length == 0U) || (length > USB_CDC_TX_CAPACITY))
    { return USB_CDC_INVALID; }
    result = CDC_Transmit_FS(data, length);
    /* Once called, even BUSY may hide a partial LL start. Require retirement. */
    return (result == USBD_OK) ? USB_CDC_OK : USB_CDC_FAULT;
}

UsbCdcResult UsbCdcPort_Rearm(void)
{
    uint8_t result;
@CLASS_GUARD@
    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (@CLASS_DATA@ == NULL)) { return USB_CDC_OFFLINE; }
    result = USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    /* Native rearm failure cannot prove absence of endpoint ownership. */
    return (result == USBD_OK) ? USB_CDC_OK : USB_CDC_FAULT;
}
'''


def UsbCdcTransport_Render(*, indexed: bool = False) -> dict[str, bytes]:
    class_data = "hUsbDeviceFS.pClassDataCmsit[0]" if indexed else "hUsbDeviceFS.pClassData"
    class_guard = ("    if ((hUsbDeviceFS.classId != 0U) ||\n"
                   "        (hUsbDeviceFS.pClassData != hUsbDeviceFS.pClassDataCmsit[0]))\n"
                   "    { return USB_CDC_FAULT; }") if indexed else ""
    return {
        "Inc/usb_cdc_transport.h": HEADER.encode(),
        "Inc/usb_cdc_port.h": PORT_HEADER.encode(),
        "Src/usb_cdc_transport.c": SOURCE.encode(),
        "Src/usb_cdc_port.c": CLASSIC_PORT.replace("@CLASS_DATA@", class_data).replace(
            "@CLASS_GUARD@", class_guard).encode(),
        "usb_cdc_transport.cmake": b'''# Call after defining the native target; CubeMX owns all native sources.
# Select exactly one assertion owner; never link duplicate implementations.
function(UsbCdc_Attach target assertion_owner)
  if(NOT TARGET ${target})
    message(FATAL_ERROR "UsbCdc_Attach needs an existing native target")
  endif()
  if("${assertion_owner}" STREQUAL "BUNDLED")
    target_sources(${target} PRIVATE
      "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/Common/Src/silverstar_assert.c")
  elseif(NOT "${assertion_owner}" STREQUAL "EXISTING")
    message(FATAL_ERROR "Choose BUNDLED or EXISTING assertion ownership")
  endif()
  target_sources(${target} PRIVATE
    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/Src/usb_cdc_transport.c"
    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/Src/usb_cdc_port.c")
  target_include_directories(${target} PRIVATE
    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/Inc"
    "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/Common/Inc")
endfunction()
''',
    }
