#include "usb_cdc_retire.h"
#include "usb_cdc_port.h"
#include "usb_device.h"
#include "main.h"
#include "usbd_cdc.h"
#include <stddef.h>
extern PCD_HandleTypeDef hpcd_USB_FS;
extern USBD_HandleTypeDef hUsbDeviceFS;
_Static_assert((CDC_IN_EP == 0x81U) && (CDC_OUT_EP == 0x01U) && (CDC_CMD_EP == 0x82U),
    "Reviewed controller retirement requires the declared single CDC endpoints");

static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[5] = {hpcd_USB_FS.OUT_ep[0].pmaadress, hpcd_USB_FS.IN_ep[0].pmaadress,
        hpcd_USB_FS.IN_ep[1].pmaadress, hpcd_USB_FS.OUT_ep[1].pmaadress, hpcd_USB_FS.IN_ep[2].pmaadress};
    const uint32_t size[5] = {64U, 64U, 64U, 64U, 8U};
    uint32_t i;
    uint32_t j;
    if ((hpcd_USB_FS.Instance->BTABLE != 0U) ||
        (hpcd_USB_FS.OUT_ep[0].doublebuffer != 0U) || (hpcd_USB_FS.IN_ep[0].doublebuffer != 0U) ||
        (hpcd_USB_FS.IN_ep[1].doublebuffer != 0U) || (hpcd_USB_FS.OUT_ep[1].doublebuffer != 0U) ||
        (hpcd_USB_FS.IN_ep[2].doublebuffer != 0U)) { return USB_CDC_FAULT; }
    /* Reviewed F1 single-buffer PMA: 512 bytes, three 8-byte table entries.
     * Offsets are read from CubeMX's effective configuration, not rewritten. */
    for (i = 0U; i < 5U; i++)
    {
        if ((start[i] < 24U) || ((start[i] % 2U) != 0U) || (start[i] > 512U) ||
            (size[i] > (512U - start[i]))) { return USB_CDC_FAULT; }
        for (j = 0U; j < 5U; j++)
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
    if ((device == &hUsbDeviceFS) && (device->pData == &hpcd_USB_FS) &&
        (hpcd_USB_FS.Instance == USB))
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
    if ((address & 0x80U) != 0U)
    {
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EPTX_STAT) != 0U)
        { return USB_CDC_FAULT; }
        PCD_CLEAR_TX_EP_CTR(hpcd_USB_FS.Instance, number);
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EP_CTR_TX) != 0U)
        { return USB_CDC_FAULT; }
    }
    else
    {
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EPRX_STAT) != 0U)
        { return USB_CDC_FAULT; }
        PCD_CLEAR_RX_EP_CTR(hpcd_USB_FS.Instance, number);
        if ((PCD_GET_ENDPOINT(hpcd_USB_FS.Instance, number) & USB_EP_CTR_RX) != 0U)
        { return USB_CDC_FAULT; }
    }
    return USB_CDC_OK;
}

UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device, uint8_t address)
{
    PCD_EPTypeDef *ep;
    uint32_t token;
    uint8_t number = address & 0x7FU;
    if ((device != &hUsbDeviceFS) || (device->pData != &hpcd_USB_FS) ||
        ((address != 0x81U) && (address != 0x01U) && (address != 0x82U)))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    ep = ((address & 0x80U) != 0U) ? &hpcd_USB_FS.IN_ep[number] : &hpcd_USB_FS.OUT_ep[number];
    if ((HAL_PCD_EP_Abort(&hpcd_USB_FS, address) != HAL_OK) ||
        (HAL_PCD_EP_Close(&hpcd_USB_FS, address) != HAL_OK))
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
