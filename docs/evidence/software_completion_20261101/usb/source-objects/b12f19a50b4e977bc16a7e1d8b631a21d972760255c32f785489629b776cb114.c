#include "usb_cdc_port.h"
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

    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (hUsbDeviceFS.pClassData == NULL)) { return USB_CDC_OFFLINE; }
    cdc = (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
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

    if ((hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
        (hUsbDeviceFS.pClassData == NULL)) { return USB_CDC_OFFLINE; }
    result = USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    /* Native rearm failure cannot prove absence of endpoint ownership. */
    return (result == USBD_OK) ? USB_CDC_OK : USB_CDC_FAULT;
}
