#ifndef TEST_NATIVE_USB_H
#define TEST_NATIVE_USB_H
#include <stdint.h>
#include <stddef.h>
#define USBD_OK 0U
#define USBD_BUSY 1U
#define USBD_FAIL 2U
#define USBD_SPEED_FULL 1U
#define USBD_STATE_DEFAULT 1U
#define USBD_STATE_CONFIGURED 3U
#define USBD_EP_TYPE_BULK 2U
#define USBD_EP_TYPE_INTR 3U
#define CDC_IN_EP 0x81U
#define CDC_OUT_EP 0x01U
#define CDC_CMD_EP 0x82U
#define CDC_CMD_PACKET_SIZE 8U
#define CDC_DATA_FS_IN_PACKET_SIZE 64U
#define CDC_DATA_FS_OUT_PACKET_SIZE 64U
#define CDC_FS_BINTERVAL 16U
#define UNUSED(v) ((void)(v))
typedef uint8_t USBD_StatusTypeDef;
typedef struct { uint32_t total_length;uint8_t is_used,bInterval; } Endpoint;
typedef struct { void *pClassData,*pData;void *pClassDataCmsit[1],*pUserData[1];uint8_t classId,dev_speed,dev_state;Endpoint ep_in[4],ep_out[4]; } USBD_HandleTypeDef;
typedef struct { uint32_t TxState,RxState,TxLength,RxLength;uint8_t *TxBuffer,*RxBuffer; } USBD_CDC_HandleTypeDef;
typedef struct { int8_t (*Init)(void);int8_t (*DeInit)(void);int8_t (*Control)(uint8_t,uint8_t *,uint16_t);int8_t (*Receive)(uint8_t *,uint32_t *);int8_t (*TransmitCplt)(uint8_t *,uint32_t *,uint8_t); } USBD_CDC_ItfTypeDef;
typedef struct { struct { uint32_t maxpacket; } IN_ep[4]; } PCD_HandleTypeDef;
uint8_t CDC_Transmit_FS(uint8_t *,uint16_t);
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *,uint8_t *,uint32_t);
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *,uint8_t *);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *);
extern USBD_HandleTypeDef hUsbDeviceFS;
#endif
