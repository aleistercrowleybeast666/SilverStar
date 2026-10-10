#ifndef __PC_C071_CONTROL_H
#define __PC_C071_CONTROL_H
#include "usbd_def.h"
USBD_StatusTypeDef PcC071Usb_ControlSetup(USBD_HandleTypeDef *device,
    USBD_SetupReqTypedef *request);
USBD_StatusTypeDef PcC071Usb_ControlRxReady(USBD_HandleTypeDef *device);
#endif
