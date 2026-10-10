/* SilverStar: bounded single-interface FS CDC control metadata. */
#include "pc_usb_control.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include "usbd_core.h"
#include "usbd_ioreq.h"
#include <string.h>
extern USBD_HandleTypeDef hUsbDeviceFS;
static uint8_t s_line[7] = {0x00,0xC2,0x01,0x00,0U,0U,8U};
/* Native controllers may copy a full actual EP0 packet, despite a 7-byte arm. */
static uint8_t s_control_rx[64];
_Static_assert(USB_MAX_EP0_SIZE == 64U, "reviewed full-speed EP0 capacity");
_Static_assert(sizeof(((USBD_CDC_HandleTypeDef *)0)->data) >= 7U, "CDC response capacity");
static USBD_CDC_HandleTypeDef *ClassData_Get(USBD_HandleTypeDef *device)
{
    if ((device != &hUsbDeviceFS) ||
        (device->dev_state != USBD_STATE_CONFIGURED) || 
        (device->pUserData != &USBD_Interface_fops_FS)) { return NULL; }
    return (USBD_CDC_HandleTypeDef *)device->pClassData;
}
int8_t PcUsbControl_Control(uint8_t command, uint8_t *data, uint16_t length)
{
    if ((command == CDC_SET_LINE_CODING) || (command == CDC_GET_LINE_CODING))
    {
        if ((data == NULL) || (length != sizeof(s_line))) { return USBD_FAIL; }
        if (command == CDC_SET_LINE_CODING)
        {
            if ((data[4] > 2U) || (data[5] > 4U) ||
                !(((data[6] >= 5U) && (data[6] <= 8U)) || (data[6] == 16U)))
            { return USBD_FAIL; }
            memcpy(s_line, data, sizeof(s_line));
        }
        else { memcpy(data, s_line, sizeof(s_line)); }
    }
    else if ((command != CDC_SET_CONTROL_LINE_STATE) || (length != 0U))
    { return USBD_FAIL; }
    return USBD_OK;
}
void PcUsbControl_Cancel(USBD_HandleTypeDef *device)
{
    USBD_CDC_HandleTypeDef *cdc = ClassData_Get(device);
    if (cdc != NULL) { cdc->CmdOpCode = 0xFFU; cdc->CmdLength = 0U; }
}
USBD_StatusTypeDef PcUsbControl_Dispatch(USBD_HandleTypeDef *device)
{
    USBD_StatusTypeDef result = USBD_FAIL;
    if ((ClassData_Get(device) != NULL) && ((device->pClass) == &USBD_CDC))
    {
        result = (USBD_StatusTypeDef)(device->pClass)->Setup(device, &device->request);
    }
    if ((result == USBD_OK) && (device->request.wLength == 0U))
    { result = USBD_CtlSendStatus(device); }
    if (result != USBD_OK) { USBD_CtlError(device, &device->request); }
    return result;
}
USBD_StatusTypeDef PcUsbControl_Setup(USBD_HandleTypeDef *device, USBD_SetupReqTypedef *request)
{
    USBD_CDC_HandleTypeDef *cdc = ClassData_Get(device);
    USBD_CDC_ItfTypeDef *interface;
    uint16_t length;
    USBD_StatusTypeDef result;
    if ((cdc == NULL) || (request == NULL)) { return USBD_FAIL; }
    interface = (USBD_CDC_ItfTypeDef *)device->pUserData;
    PcUsbControl_Cancel(device);
    if ((interface->Control == NULL) || (request->wIndex != 0U)) { return USBD_FAIL; }
    if (request->bRequest == CDC_GET_LINE_CODING)
    {
        if ((request->bmRequest != 0xA1U) || (request->wValue != 0U)) { return USBD_FAIL; }
        if (interface->Control(CDC_GET_LINE_CODING, (uint8_t *)cdc->data, 7U) != USBD_OK)
        { return USBD_FAIL; }
        length = (request->wLength < 7U) ? request->wLength : 7U;
        return (length == 0U) ? USBD_OK : USBD_CtlSendData(device, (uint8_t *)cdc->data, length);
    }
    if (request->bmRequest != 0x21U) { return USBD_FAIL; }
    if (request->bRequest == CDC_SET_LINE_CODING)
    {
        if ((request->wValue != 0U) || (request->wLength != 7U)) { return USBD_FAIL; }
        cdc->CmdOpCode = CDC_SET_LINE_CODING;
        cdc->CmdLength = 7U;
        result = USBD_CtlPrepareRx(device, s_control_rx, 7U);
        if (result != USBD_OK) { PcUsbControl_Cancel(device); }
        return result;
    }
    if ((request->bRequest != CDC_SET_CONTROL_LINE_STATE) ||
        (request->wLength != 0U) || (request->wValue > 3U)) { return USBD_FAIL; }
    return (USBD_StatusTypeDef)interface->Control(CDC_SET_CONTROL_LINE_STATE, (uint8_t *)request, 0U);
}
USBD_StatusTypeDef PcUsbControl_RxReady(USBD_HandleTypeDef *device)
{
    USBD_CDC_HandleTypeDef *cdc = ClassData_Get(device);
    USBD_CDC_ItfTypeDef *interface;
    uint8_t command, length;
    if (cdc == NULL) { return USBD_FAIL; }
    interface = (USBD_CDC_ItfTypeDef *)device->pUserData;
    command = cdc->CmdOpCode; length = cdc->CmdLength;
    PcUsbControl_Cancel(device);
    if ((command != CDC_SET_LINE_CODING) || (length != 7U) ||
        (device->request.bmRequest != 0x21U) ||
        (device->request.bRequest != CDC_SET_LINE_CODING) ||
        (device->request.wValue != 0U) || (device->request.wIndex != 0U) ||
        (device->request.wLength != 7U) || (interface->Control == NULL) ||
        (USBD_LL_GetRxDataSize(device, 0U) != 7U)) { return USBD_FAIL; }
    return (USBD_StatusTypeDef)interface->Control(command, s_control_rx, length);
}
