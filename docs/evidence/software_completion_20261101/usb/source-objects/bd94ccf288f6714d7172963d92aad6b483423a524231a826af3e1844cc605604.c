#include "usb_cdc_retire.h"
#include "usb_cdc_port.h"
#include "usb_device.h"
#include "main.h"
#include "usbd_cdc.h"
#include <stddef.h>
extern PCD_HandleTypeDef hpcd_USB_OTG_FS;
extern USBD_HandleTypeDef hUsbDeviceFS;
_Static_assert((CDC_IN_EP == 0x81U) && (CDC_OUT_EP == 0x01U) && (CDC_CMD_EP == 0x82U),
    "Reviewed controller retirement requires the declared single CDC endpoints");

static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[4] = {0U, hpcd_USB_OTG_FS.Instance->DIEPTXF0_HNPTXFSIZ & 0xFFFFU,
        hpcd_USB_OTG_FS.Instance->DIEPTXF[0] & 0xFFFFU, hpcd_USB_OTG_FS.Instance->DIEPTXF[1] & 0xFFFFU};
    uint32_t size[4] = {hpcd_USB_OTG_FS.Instance->GRXFSIZ,
        hpcd_USB_OTG_FS.Instance->DIEPTXF0_HNPTXFSIZ >> 16,
        hpcd_USB_OTG_FS.Instance->DIEPTXF[0] >> 16, hpcd_USB_OTG_FS.Instance->DIEPTXF[1] >> 16};
    uint32_t i;
    uint32_t j;
    if ((hpcd_USB_OTG_FS.Init.dma_enable != 0U) || (size[0] < 64U)) { return USB_CDC_FAULT; }
    for (i = 0U; i < 4U; i++)
    {
        if ((size[i] < 16U) || (start[i] > (USB_OTG_FS_TOTAL_FIFO_SIZE / 4U)) ||
            (size[i] > ((USB_OTG_FS_TOTAL_FIFO_SIZE / 4U) - start[i])))
        { return USB_CDC_FAULT; }
        for (j = 0U; j < 4U; j++)
        {
            if ((j < i) && (start[i] < (start[j] + size[j])) &&
                (start[j] < (start[i] + size[i]))) { return USB_CDC_FAULT; }
        }
    }
    return USB_CDC_OK;
}

UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdcResult result = USB_CDC_INVALID;
    if ((device == &hUsbDeviceFS) && (device->pData == &hpcd_USB_OTG_FS) &&
        (hpcd_USB_OTG_FS.Instance == USB_OTG_FS))
    { result = UsbCdcRetire_MemoryCheck(); }
    if (result != USB_CDC_OK) { UsbCdc_LinkDown(); }
    UsbCdcPort_Unlock(token);
    return result;
}

/* Separate the controller postcondition from the shared ownership transition.
 * Called with interrupts masked, after checked HAL abort and close. */
static UsbCdcResult UsbCdcRetire_HardwareFinish(uint8_t address)
{
    uint8_t number = address & 0x7FU;
    uintptr_t USBx_BASE = (uintptr_t)hpcd_USB_OTG_FS.Instance;
    if ((address & 0x80U) != 0U)
    {
        if (((USBx_INEP(number)->DIEPCTL &
              (USB_OTG_DIEPCTL_EPENA | USB_OTG_DIEPCTL_USBAEP)) != 0U) ||
            ((USBx_DEVICE->DAINTMSK & (1UL << number)) != 0U))
        { return USB_CDC_FAULT; }
        USBx_DEVICE->DIEPEMPMSK &= ~(1UL << number);
        if (USB_FlushTxFifo(hpcd_USB_OTG_FS.Instance, number) != HAL_OK)
        { return USB_CDC_FAULT; }
        USBx_INEP(number)->DIEPINT = 0xFB7FU;
    }
    else
    {
        if (((USBx_OUTEP(number)->DOEPCTL &
              (USB_OTG_DOEPCTL_EPENA | USB_OTG_DOEPCTL_USBAEP)) != 0U) ||
            ((USBx_DEVICE->DAINTMSK & (1UL << (number + 16U))) != 0U) ||
            ((hpcd_USB_OTG_FS.Instance->GINTSTS & USB_OTG_GINTSTS_RXFLVL) != 0U))
        { return USB_CDC_FAULT; }
        /* RX FIFO is global, including EP0. Never flush away control traffic.
         * A pending entry blocks retirement; the old pointer remains owned. */
        USBx_OUTEP(number)->DOEPINT = 0xFB7FU;
    }
    return USB_CDC_OK;
}

UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device, uint8_t address)
{
    PCD_EPTypeDef *ep;
    uint32_t token;
    uint8_t number = address & 0x7FU;
    if ((device != &hUsbDeviceFS) || (device->pData != &hpcd_USB_OTG_FS) ||
        ((address != 0x81U) && (address != 0x01U) && (address != 0x82U)))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    ep = ((address & 0x80U) != 0U) ? &hpcd_USB_OTG_FS.IN_ep[number] : &hpcd_USB_OTG_FS.OUT_ep[number];
    if ((HAL_PCD_EP_Abort(&hpcd_USB_OTG_FS, address) != HAL_OK) ||
        (HAL_PCD_EP_Close(&hpcd_USB_OTG_FS, address) != HAL_OK))
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    if (UsbCdcRetire_HardwareFinish(address) != USB_CDC_OK)
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    /* No DMA in these exact profiles. Disabled endpoints cannot consume more
     * CPU source bytes; clear pending completion and stale software pointers. */
    ep->xfer_buff = NULL;
    ep->xfer_len = 0U;
    ep->xfer_count = 0U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}
