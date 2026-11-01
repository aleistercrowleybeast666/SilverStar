#include <stdint.h>
#include "usb_cdc_transport.h"
#define USBD_OK 0U
#define USBD_FAIL 2U
typedef struct { uint8_t state; } USBD_HandleTypeDef;
static USBD_HandleTypeDef hUsbDeviceFS;
static uint8_t UserRxBufferFS[64], UserTxBufferFS[1];
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *dev,uint8_t *data,uint32_t length)
{ (void)dev;(void)data;(void)length;return USBD_OK; }
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *dev,uint8_t *data)
{ (void)dev;(void)data;return USBD_OK; }
static int8_t CDC_Init_FS(void)
{
  _Static_assert(sizeof(UserRxBufferFS) >= USB_CDC_PACKET_SIZE,
      "native CDC RX buffer must fit the armed packet");
  if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0U) != USBD_OK)
  { return (int8_t)USBD_FAIL; }
  if (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS) != USBD_OK)
  { return (int8_t)USBD_FAIL; }
  return (int8_t)USBD_OK;
}
int main(void) { return CDC_Init_FS(); }
