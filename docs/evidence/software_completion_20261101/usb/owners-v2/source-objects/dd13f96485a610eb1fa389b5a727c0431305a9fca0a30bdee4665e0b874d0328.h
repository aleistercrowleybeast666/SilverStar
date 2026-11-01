#ifndef __USB_CDC_RETIRE_H
#define __USB_CDC_RETIRE_H
#include "usb_cdc_transport.h"
#include "usbd_def.h"
UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device);
UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device, uint8_t address);
#endif
