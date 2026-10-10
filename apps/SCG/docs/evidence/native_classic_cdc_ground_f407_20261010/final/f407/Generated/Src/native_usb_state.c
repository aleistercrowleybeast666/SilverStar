#include "native_usb_state.h"
#include "usb_device.h"
#include "usbd_core.h"

extern USBD_HandleTypeDef hUsbDeviceFS;
NativeUsbResult NativeUsb_Stop(void)
{
    USBD_StatusTypeDef result = USBD_LL_Stop(&hUsbDeviceFS);
    /* Gate publication even if the lower controller cannot confirm stopping.
     * The runtime records retirement failure and enters its terminal path. */
    hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT;
    return (result == USBD_OK) ? NativeUsbResult_Ok : NativeUsbResult_Failure;
}
