#ifndef __USB_CDC_PORT_H
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
