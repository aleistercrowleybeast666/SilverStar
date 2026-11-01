#ifndef __USB_CDC_TRANSPORT_H
#define __USB_CDC_TRANSPORT_H
#include <stdint.h>
#define USB_CDC_RX_CAPACITY 512U
#define USB_CDC_TX_CAPACITY 256U
#define USB_CDC_PACKET_SIZE 64U
typedef enum
{
    USB_CDC_OK = 0, USB_CDC_BUSY, USB_CDC_OFFLINE,
    USB_CDC_INVALID, USB_CDC_FAULT
} UsbCdcResult;
/* OK from Write means queued; never a peer receipt/delivery acknowledgement. */
UsbCdcResult UsbCdc_Configure(void);
void UsbCdc_LinkDown(void);
UsbCdcResult UsbCdc_Quiesced(void);
UsbCdcResult UsbCdc_Receive(const uint8_t *data, uint16_t length);
UsbCdcResult UsbCdc_Read(uint8_t *data, uint16_t capacity,
    uint16_t *length, uint32_t *session);
UsbCdcResult UsbCdc_Write(const uint8_t *data, uint16_t length,
    uint32_t session);
UsbCdcResult UsbCdc_Service(void);
uint32_t UsbCdc_SessionGet(void);
#endif
