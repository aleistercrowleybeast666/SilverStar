#ifndef PC_USB_CONTROL_H
#define PC_USB_CONTROL_H
#include "usbd_def.h"
enum { PC_USB_CONFIGURATION_DESC_CAPACITY = 67U };
uint16_t PcUsbControl_DescriptorCapacityGet(const uint8_t *descriptor);
int8_t PcUsbControl_Control(uint8_t command, uint8_t *data, uint16_t length);
void PcUsbControl_Cancel(USBD_HandleTypeDef *device);
void PcUsbControl_Abort(USBD_HandleTypeDef *device);
USBD_StatusTypeDef PcUsbControl_Dispatch(USBD_HandleTypeDef *device);
USBD_StatusTypeDef PcUsbControl_Setup(USBD_HandleTypeDef *device, USBD_SetupReqTypedef *request);
USBD_StatusTypeDef PcUsbControl_RxReady(USBD_HandleTypeDef *device);
#endif
