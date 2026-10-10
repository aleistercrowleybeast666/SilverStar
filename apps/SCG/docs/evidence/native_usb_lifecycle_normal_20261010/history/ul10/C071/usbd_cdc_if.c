/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           USB_Device/CDC_Standalone/USB_Device/App/usbd_cdc_if.c
  * @author         MCD Application Team
  * @brief          This file implements the USB device descriptors.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2024 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* SilverStar adaptation: bounded byte stream and LL failure recovery. */
#include "usbd_cdc_if.h"
#include "pc_byte_stream.h"
#include "pc_c071_usb.h"
#include "pc_c071_control.h"
#include "main.h"
#include "usbd_ioreq.h"
#include <string.h>
extern USBD_HandleTypeDef hUsbDeviceFS;
static uint8_t s_rx[64];
static uint8_t s_idle_tx[1];
static uint8_t s_line[7] = {0x00,0xc2,0x01,0x00,0,0,8};
/* Native HAL copies the actual EP0 packet count, not the requested seven bytes. */
static uint8_t s_control_rx[64];
static volatile uint8_t s_rearm_pending;
static volatile uint8_t s_tx_failed;
static volatile uint8_t s_tx_reset_pending;
void PcC071Usb_RxArmResult(uint8_t success)
{
    s_rearm_pending = (uint8_t)((success == 1U) ? 0U : 1U);
}
void PcC071Usb_TxStartResult(uint8_t success)
{
    if (success != 1U) { s_tx_failed = 1U; s_tx_reset_pending = 1U; }
}

static int8_t CDC_Init_FS(void)
{
    s_rearm_pending = 0U;
    s_tx_failed = 0U;
    s_tx_reset_pending = 0U;
    PcByteStream_OnUsbReset();
    if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, s_idle_tx, 0) != USBD_OK) { return USBD_FAIL; }
    return (int8_t)USBD_CDC_SetRxBuffer(&hUsbDeviceFS, s_rx);
}
static int8_t CDC_DeInit_FS(void)
{
    s_rearm_pending = 0U;
    s_tx_failed = 0U;
    s_tx_reset_pending = 0U;
    PcByteStream_OnUsbReset();
    return USBD_OK;
}
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *data, uint16_t length)
{
    if ((cmd == CDC_SET_LINE_CODING) || (cmd == CDC_GET_LINE_CODING))
    {
        if ((data == NULL) || (length != sizeof(s_line))) { return USBD_FAIL; }
        if (cmd == CDC_SET_LINE_CODING)
        {
            if ((data[4] > 2U) || (data[5] > 4U) ||
                !(((data[6] >= 5U) && (data[6] <= 8U)) || (data[6] == 16U)))
            { return USBD_FAIL; }
            memcpy(s_line, data, sizeof(s_line));
        }
        else { memcpy(data, s_line, sizeof(s_line)); }
    }
    else if ((cmd != CDC_SET_CONTROL_LINE_STATE) || (length != 0U))
    { return USBD_FAIL; }
    return USBD_OK;
}
USBD_StatusTypeDef PcC071Usb_ControlSetup(USBD_HandleTypeDef *device,
    USBD_SetupReqTypedef *request)
{
    USBD_CDC_HandleTypeDef *cdc;
    uint16_t length;
    USBD_StatusTypeDef status;
    if ((device != &hUsbDeviceFS) || (request == NULL) ||
        (device->classId != 0U) || (device->dev_state != USBD_STATE_CONFIGURED) ||
        (device->pUserData[0] != &USBD_Interface_fops_FS)) { return USBD_FAIL; }
    cdc = (USBD_CDC_HandleTypeDef *)device->pClassDataCmsit[0];
    if (cdc == NULL) { return USBD_FAIL; }
    cdc->CmdOpCode = 0xFFU; /* A new setup cancels any previous OUT command. */
    cdc->CmdLength = 0U;
    if (request->wIndex != 0U) { return USBD_FAIL; }
    if (request->bRequest == CDC_GET_LINE_CODING)
    {
        if ((request->bmRequest != 0xA1U) || (request->wValue != 0U))
        { return USBD_FAIL; }
        /* USB 2.0 9.3.5: IN wLength is a maximum, not the callback capacity. */
        if (CDC_Control_FS(CDC_GET_LINE_CODING, (uint8_t *)cdc->data,
                (uint16_t)sizeof(s_line)) != USBD_OK) { return USBD_FAIL; }
        length = (request->wLength < sizeof(s_line)) ? request->wLength :
            (uint16_t)sizeof(s_line);
        return (length == 0U) ? USBD_OK :
            USBD_CtlSendData(device, (uint8_t *)cdc->data, length);
    }
    if (request->bmRequest != 0x21U) { return USBD_FAIL; }
    if (request->bRequest == CDC_SET_LINE_CODING)
    {
        if ((request->wValue != 0U) || (request->wLength != sizeof(s_line)))
        { return USBD_FAIL; }
        cdc->CmdOpCode = CDC_SET_LINE_CODING;
        cdc->CmdLength = (uint8_t)sizeof(s_line);
        status = USBD_CtlPrepareRx(device, s_control_rx, sizeof(s_line));
        if (status != USBD_OK) { cdc->CmdOpCode = 0xFFU; cdc->CmdLength = 0U; }
        return status;
    }
    if ((request->bRequest != CDC_SET_CONTROL_LINE_STATE) ||
        (request->wLength != 0U) || (request->wValue > 3U)) { return USBD_FAIL; }
    return (USBD_StatusTypeDef)CDC_Control_FS(CDC_SET_CONTROL_LINE_STATE,
        (uint8_t *)request, 0U);
}
USBD_StatusTypeDef PcC071Usb_ControlRxReady(USBD_HandleTypeDef *device)
{
    USBD_CDC_HandleTypeDef *cdc;
    uint8_t command, length;
    if ((device != &hUsbDeviceFS) || (device->classId != 0U) ||
        (device->dev_state != USBD_STATE_CONFIGURED) ||
        (device->pUserData[0] != &USBD_Interface_fops_FS)) { return USBD_FAIL; }
    cdc = (USBD_CDC_HandleTypeDef *)device->pClassDataCmsit[0];
    if (cdc == NULL) { return USBD_FAIL; }
    command = cdc->CmdOpCode;
    length = cdc->CmdLength;
    cdc->CmdOpCode = 0xFFU;
    cdc->CmdLength = 0U;
    if ((command != CDC_SET_LINE_CODING) || (length != sizeof(s_line)) ||
        (device->request.bmRequest != 0x21U) ||
        (device->request.bRequest != CDC_SET_LINE_CODING) ||
        (device->request.wValue != 0U) || (device->request.wIndex != 0U) ||
        (device->request.wLength != sizeof(s_line)) ||
        (USBD_LL_GetRxDataSize(device, 0U) != sizeof(s_line))) { return USBD_FAIL; }
    return (USBD_StatusTypeDef)CDC_Control_FS(command, s_control_rx, length);
}
static uint8_t Rx_Rearm(void)
{
    uint8_t status;
    if (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, s_rx) != USBD_OK) { return USBD_FAIL; }
    status = USBD_CDC_ReceivePacket(&hUsbDeviceFS);
    /* The pinned class discards LL status. Our LL hook records the actual
     * controller result, including failures during initial class setup. */
    return ((status == USBD_OK) && (s_rearm_pending == 0U)) ? USBD_OK : USBD_FAIL;
}
static int8_t CDC_Receive_FS(uint8_t *data, uint32_t *length)
{
    uint8_t status;
    if ((data == NULL) || (length == NULL) || (*length > sizeof(s_rx)))
    { s_rearm_pending = 1U; return USBD_FAIL; }
    PcByteStream_OnUsbReceive(data, (uint16_t)*length);
    status = Rx_Rearm();
    s_rearm_pending = (uint8_t)((status != USBD_OK) ? 1U : 0U);
    return (int8_t)status;
}
void PcC071Usb_Service(void)
{
    uint32_t mask = __get_PRIMASK();
    __disable_irq();
    if (s_tx_reset_pending != 0U)
    {
        s_tx_reset_pending = 0U;
        PcByteStream_OnUsbReset(); /* Invalidate session; never clear TxState. */
    }
    if ((s_rearm_pending != 0U) && (hUsbDeviceFS.dev_state == USBD_STATE_CONFIGURED) &&
        (hUsbDeviceFS.pClassData != NULL))
    {
        if (Rx_Rearm() == USBD_OK) { s_rearm_pending = 0U; }
    }
    __set_PRIMASK(mask);
}
static int8_t CDC_TransmitCplt_FS(uint8_t *data, uint32_t *length, uint8_t ep)
{
    (void)data; (void)length; (void)ep; /* Class owns TX completion and ZLP. */
    return USBD_OK;
}
USBD_CDC_ItfTypeDef USBD_Interface_fops_FS = {
    CDC_Init_FS,CDC_DeInit_FS,CDC_Control_FS,CDC_Receive_FS,CDC_TransmitCplt_FS};
uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{
    uint8_t status;
    if ((data == NULL) || (length == 0U)) { return USBD_FAIL; }
    if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, data, length) != USBD_OK) { return USBD_FAIL; }
    s_tx_failed = 0U;
    status = USBD_CDC_TransmitPacket(&hUsbDeviceFS);
    return (s_tx_failed == 0U) ? status : USBD_FAIL;
}
