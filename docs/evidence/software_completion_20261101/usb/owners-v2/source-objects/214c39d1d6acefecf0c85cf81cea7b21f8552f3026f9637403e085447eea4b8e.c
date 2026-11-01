
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "usb_cdc_transport.h"
#define USBD_OK 0U
#define USBD_FAIL 2U
#define USBD_STATE_DEFAULT 1U
#define HAL_OK 0U
#define DEVICE_FS 0U
#define PCD_SPEED_FULL 1U
#define PCD_PHY_EMBEDDED 0U
#define DISABLE 0U
#define PCD_SNG_BUF 0U
#define USE_HAL_PCD_REGISTER_CALLBACKS 0U
#define USB_OTG_FS_TOTAL_FIFO_SIZE 1280U
typedef uint8_t USBD_StatusTypeDef;
typedef struct { void *pData;uint8_t id,dev_state; } USBD_HandleTypeDef;
typedef struct { uint32_t GRXFSIZ,DIEPTXF0_HNPTXFSIZ,DIEPTXF[4],BTABLE; } Regs;
typedef struct { uint32_t dev_endpoints,speed,dma_enable,phy_itface,Sof_enable,low_power_enable,
 lpm_enable,vbus_sensing_enable,use_dedicated_ep1,battery_charging_enable; } PcdInit;
typedef struct { uint16_t pmaadress;uint8_t doublebuffer; } Ep;
typedef struct { void *pData;Regs *Instance;PcdInit Init;Ep IN_ep[16],OUT_ep[16]; } PCD_HandleTypeDef;
static USBD_HandleTypeDef hUsbDeviceFS;
static PCD_HandleTypeDef hpcd_USB_FS;
static Regs regs;
#define USB (&regs)
#define USB_OTG_FS (&regs)
static unsigned calls,fail_call,fail_init,fail_deinit,bad_readback,link_down;
void UsbCdc_LinkDown(void) { link_down++; }
uint32_t UsbCdcPort_Lock(void) { return 0U; }
void UsbCdcPort_Unlock(uint32_t token) { assert(token==0U); }
/* Host-only terminal interception: CubeMX's actual Error_Handler never returns. */
void Error_Handler(void) { assert(fail_init);exit(0); }
uint8_t HAL_PCD_Init(PCD_HandleTypeDef *p) { assert(p==&hpcd_USB_FS);return (uint8_t)fail_init; }
uint8_t HAL_PCD_DeInit(PCD_HandleTypeDef *p) { assert(p==&hpcd_USB_FS);return (uint8_t)fail_deinit; }

uint8_t HAL_PCDEx_PMAConfig(PCD_HandleTypeDef *p,uint16_t address,uint16_t kind,uint32_t location)
{ assert(p==&hpcd_USB_FS && kind==PCD_SNG_BUF);calls++;if(calls==fail_call) { return 1U; }
  Ep *ep=(address&0x80U)?&p->IN_ep[address&0x7FU]:&p->OUT_ep[address];
  ep->pmaadress=(uint16_t)(bad_readback?0U:location);ep->doublebuffer=0U;return 0U; }

USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
  /* Init USB Ip. */
  /* Link the driver to the stack. */
  hpcd_USB_FS.pData = pdev;
  pdev->pData = &hpcd_USB_FS;

  hpcd_USB_FS.Instance = USB;
  hpcd_USB_FS.Init.dev_endpoints = 8;
  hpcd_USB_FS.Init.speed = PCD_SPEED_FULL;
  hpcd_USB_FS.Init.low_power_enable = DISABLE;
  hpcd_USB_FS.Init.lpm_enable = DISABLE;
  hpcd_USB_FS.Init.battery_charging_enable = DISABLE;
  if (HAL_PCD_Init(&hpcd_USB_FS) != HAL_OK)
  {
    Error_Handler( );
  }

#if (USE_HAL_PCD_REGISTER_CALLBACKS == 1U)
  /* Register USB PCD CallBacks */
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_SOF_CB_ID, PCD_SOFCallback);
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_SETUPSTAGE_CB_ID, PCD_SetupStageCallback);
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_RESET_CB_ID, PCD_ResetCallback);
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_SUSPEND_CB_ID, PCD_SuspendCallback);
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_RESUME_CB_ID, PCD_ResumeCallback);
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_CONNECT_CB_ID, PCD_ConnectCallback);
  HAL_PCD_RegisterCallback(&hpcd_USB_FS, HAL_PCD_DISCONNECT_CB_ID, PCD_DisconnectCallback);

  HAL_PCD_RegisterDataOutStageCallback(&hpcd_USB_FS, PCD_DataOutStageCallback);
  HAL_PCD_RegisterDataInStageCallback(&hpcd_USB_FS, PCD_DataInStageCallback);
  HAL_PCD_RegisterIsoOutIncpltCallback(&hpcd_USB_FS, PCD_ISOOUTIncompleteCallback);
  HAL_PCD_RegisterIsoInIncpltCallback(&hpcd_USB_FS, PCD_ISOINIncompleteCallback);
#endif /* USE_HAL_PCD_REGISTER_CALLBACKS */
  /* USER CODE BEGIN EndPoint_Configuration */
  HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x00 , PCD_SNG_BUF, 0x18);
  HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x80 , PCD_SNG_BUF, 0x58);
  /* USER CODE END EndPoint_Configuration */
  /* USER CODE BEGIN EndPoint_Configuration_CDC */
  HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x81 , PCD_SNG_BUF, 0xC0);
  HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x01 , PCD_SNG_BUF, 0x110);
  HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x82 , PCD_SNG_BUF, 0x100);
  /* USER CODE END EndPoint_Configuration_CDC */
  return USBD_OK;
}
static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[5] = {hpcd_USB_FS.OUT_ep[0].pmaadress, hpcd_USB_FS.IN_ep[0].pmaadress,
        hpcd_USB_FS.IN_ep[1].pmaadress, hpcd_USB_FS.OUT_ep[1].pmaadress, hpcd_USB_FS.IN_ep[2].pmaadress};
    const uint32_t size[5] = {64U, 64U, 64U, 64U, 8U};
    uint32_t i;
    uint32_t j;
    if ((hpcd_USB_FS.Instance->BTABLE != 0U) ||
        (hpcd_USB_FS.OUT_ep[0].doublebuffer != 0U) || (hpcd_USB_FS.IN_ep[0].doublebuffer != 0U) ||
        (hpcd_USB_FS.IN_ep[1].doublebuffer != 0U) || (hpcd_USB_FS.OUT_ep[1].doublebuffer != 0U) ||
        (hpcd_USB_FS.IN_ep[2].doublebuffer != 0U)) { return USB_CDC_FAULT; }
    /* Reviewed F1 single-buffer PMA: 512 bytes, three 8-byte table entries.
     * Offsets are read from CubeMX's effective configuration, not rewritten. */
    for (i = 0U; i < 5U; i++)
    {
        if ((start[i] < 24U) || ((start[i] % 2U) != 0U) || (start[i] > 512U) ||
            (size[i] > (512U - start[i]))) { return USB_CDC_FAULT; }
        for (j = 0U; j < 5U; j++)
        {
            if ((j < i) && (start[i] < (start[j] + size[j])) &&
                (start[j] < (start[i] + size[i]))) { return USB_CDC_FAULT; }
        }
    }
    return USB_CDC_OK;
}
UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdcResult result = USB_CDC_INVALID;
    if ((device == &hUsbDeviceFS) && (device->pData == &hpcd_USB_FS) &&
        (hpcd_USB_FS.Instance == USB))
    { result = UsbCdcRetire_MemoryCheck(); }
    if (result != USB_CDC_OK) { UsbCdc_LinkDown(); }
    UsbCdcPort_Unlock(token);
    return result;
}
int main(int argc,char **argv)
{
 assert(argc==2);
 if(strcmp(argv[1],"pcd-failure")==0) { fail_init=1U; }
 if(strcmp(argv[1],"readback")==0) { bad_readback=1U; }
 if(strncmp(argv[1],"call-",5)==0) { fail_call=(unsigned)strtoul(argv[1]+5,NULL,10); }
 uint8_t result=USBD_LL_Init(&hUsbDeviceFS);
 if(result!=USBD_OK) { assert((fail_init && calls==0U) || (fail_call && calls==fail_call));return 0; }
 assert(result==USBD_OK);
 if(strcmp(argv[1],"require-valid-layout")==0) { assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)==USB_CDC_OK);return 0; }
 if(strcmp(argv[1],"valid-layout")==0) {  assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)==USB_CDC_OK);return 0; }
 if(strcmp(argv[1],"overlap")==0) {  hpcd_USB_FS.IN_ep[2].pmaadress=0xC0U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK);return 0; }
 if(strcmp(argv[1],"table-base")==0) { regs.BTABLE=64U;assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U);return 0; }
 if(strcmp(argv[1],"missing-notify")==0) { hpcd_USB_FS.IN_ep[2].pmaadress=0U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U);return 0; }
 if(strcmp(argv[1],"capacity")==0) { hpcd_USB_FS.IN_ep[2].pmaadress=512U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U);return 0; }
 if(fail_call||bad_readback) { assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U); }
 else { assert(result==USBD_OK);assert(calls==5U && hpcd_USB_FS.IN_ep[2].pmaadress==0x100U && hpcd_USB_FS.OUT_ep[1].pmaadress==0x110U); }
 return 0;
}
