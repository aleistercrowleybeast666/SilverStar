#ifndef __PC_C071_USB_H
#define __PC_C071_USB_H
#include <stdint.h>
/* Main-context, one bounded endpoint rearm attempt per scheduler iteration. */
void PcC071Usb_Service(void);
void PcC071Usb_RxArmResult(uint8_t success);
void PcC071Usb_TxStartResult(uint8_t success);
#endif
