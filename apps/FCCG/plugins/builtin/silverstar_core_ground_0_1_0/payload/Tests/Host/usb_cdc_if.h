#ifndef __USBD_CDC_IF_H
#define __USBD_CDC_IF_H
#include <stdint.h>
#define USBD_OK 0U
#define USBD_BUSY 1U
#define USBD_FAIL 2U
uint8_t CDC_Transmit_FS(uint8_t *, uint16_t);
#endif
