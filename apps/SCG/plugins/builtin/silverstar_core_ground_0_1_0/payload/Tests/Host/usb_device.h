#ifndef __USB_DEVICE_H
#define __USB_DEVICE_H
#include <stdint.h>
#define USBD_STATE_CONFIGURED 3U
typedef struct { uint8_t dev_state; void *pClassData; } USBD_HandleTypeDef;
typedef struct { volatile uint32_t TxState; } USBD_CDC_HandleTypeDef;
extern USBD_HandleTypeDef hUsbDeviceFS;
#endif
