
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
static PCD_HandleTypeDef hpcd_USB_OTG_FS;
static Regs regs;
#define USB (&regs)
#define USB_OTG_FS (&regs)
static unsigned calls,fail_call,fail_init,fail_deinit,bad_readback,link_down;
void UsbCdc_LinkDown(void) { link_down++; }
uint32_t UsbCdcPort_Lock(void) { return 0U; }
void UsbCdcPort_Unlock(uint32_t token) { assert(token==0U); }
/* Host-only terminal interception: CubeMX's actual Error_Handler never returns. */
void Error_Handler(void) { assert(fail_init);exit(0); }
uint8_t HAL_PCD_Init(PCD_HandleTypeDef *p) { assert(p==&hpcd_USB_OTG_FS);return (uint8_t)fail_init; }
uint8_t HAL_PCD_DeInit(PCD_HandleTypeDef *p) { assert(p==&hpcd_USB_OTG_FS);return (uint8_t)fail_deinit; }

uint8_t HAL_PCDEx_SetRxFiFo(PCD_HandleTypeDef *p,uint16_t size)
{ assert(p==&hpcd_USB_OTG_FS);calls++;if(calls==fail_call) { return 1U; }regs.GRXFSIZ=size;return 0U; }
uint8_t HAL_PCDEx_SetTxFiFo(PCD_HandleTypeDef *p,uint8_t n,uint16_t size)
{ assert(p==&hpcd_USB_OTG_FS && n<=2U);calls++;if(calls==fail_call) { return 1U; }
  uint32_t offset=regs.GRXFSIZ;
  if(n==0U) { regs.DIEPTXF0_HNPTXFSIZ=((uint32_t)size<<16)|offset; }
  else { offset+=regs.DIEPTXF0_HNPTXFSIZ>>16;if(n==2U) { offset+=regs.DIEPTXF[0]>>16; }
    regs.DIEPTXF[n-1U]=((uint32_t)size<<16)|offset;if(bad_readback) { regs.DIEPTXF[n-1U]=0U; } }
  return 0U; }

USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
  if ((pdev == NULL) || (pdev->id != DEVICE_FS)) { return USBD_FAIL; }
  hpcd_USB_OTG_FS.pData = pdev;
  pdev->pData = &hpcd_USB_OTG_FS;
  hpcd_USB_OTG_FS.Instance = USB_OTG_FS;
  hpcd_USB_OTG_FS.Init.dev_endpoints = 4U;
  hpcd_USB_OTG_FS.Init.speed = PCD_SPEED_FULL;
  hpcd_USB_OTG_FS.Init.dma_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.phy_itface = PCD_PHY_EMBEDDED;
  hpcd_USB_OTG_FS.Init.Sof_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.low_power_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.lpm_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.vbus_sensing_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.use_dedicated_ep1 = DISABLE;
  if (HAL_PCD_Init(&hpcd_USB_OTG_FS) != HAL_OK) { return USBD_FAIL; }
  /* Fixed FS layout: RX=128, EP0=64, EP1=64, EP2=16 words, total 272/320.
   * EP2 retains its CDC notification endpoint; no alias into EP1's FIFO. */
  if ((HAL_PCDEx_SetRxFiFo(&hpcd_USB_OTG_FS, 128U) != HAL_OK) ||
      (HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 0U, 64U) != HAL_OK) ||
      (HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 1U, 64U) != HAL_OK) ||
      (HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 2U, 16U) != HAL_OK))
  {
    pdev->dev_state = USBD_STATE_DEFAULT;
    UsbCdc_LinkDown();
    if (HAL_PCD_DeInit(&hpcd_USB_OTG_FS) != HAL_OK) { UsbCdc_LinkDown(); }
    return USBD_FAIL;
  }
  return USBD_OK;
}
static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[4] = {0U, hpcd_USB_OTG_FS.Instance->DIEPTXF0_HNPTXFSIZ & 0xFFFFU,
        hpcd_USB_OTG_FS.Instance->DIEPTXF[0] & 0xFFFFU, hpcd_USB_OTG_FS.Instance->DIEPTXF[1] & 0xFFFFU};
    uint32_t size[4] = {hpcd_USB_OTG_FS.Instance->GRXFSIZ,
        hpcd_USB_OTG_FS.Instance->DIEPTXF0_HNPTXFSIZ >> 16,
        hpcd_USB_OTG_FS.Instance->DIEPTXF[0] >> 16, hpcd_USB_OTG_FS.Instance->DIEPTXF[1] >> 16};
    uint32_t i;
    uint32_t j;
    if ((hpcd_USB_OTG_FS.Init.dma_enable != 0U) || (size[0] < 64U)) { return USB_CDC_FAULT; }
    for (i = 0U; i < 4U; i++)
    {
        if ((size[i] < 16U) || (start[i] > (USB_OTG_FS_TOTAL_FIFO_SIZE / 4U)) ||
            (size[i] > ((USB_OTG_FS_TOTAL_FIFO_SIZE / 4U) - start[i])))
        { return USB_CDC_FAULT; }
        for (j = 0U; j < 4U; j++)
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
    if ((device == &hUsbDeviceFS) && (device->pData == &hpcd_USB_OTG_FS) &&
        (hpcd_USB_OTG_FS.Instance == USB_OTG_FS))
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
 if(strcmp(argv[1],"valid-layout")==0) { regs.DIEPTXF[0]=(64U<<16)|192U;regs.DIEPTXF[1]=(16U<<16)|256U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)==USB_CDC_OK);return 0; }
 if(strcmp(argv[1],"overlap")==0) { regs.DIEPTXF[0]=(64U<<16)|192U;regs.DIEPTXF[1]=(16U<<16)|256U; regs.DIEPTXF[1]=(16U<<16)|192U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK);return 0; }
 if(strcmp(argv[1],"table-base")==0) { regs.BTABLE=64U;assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U);return 0; }
 if(strcmp(argv[1],"missing-notify")==0) { regs.DIEPTXF[1]=0U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U);return 0; }
 if(strcmp(argv[1],"capacity")==0) { regs.DIEPTXF[1]=(32U<<16)|319U; assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U);return 0; }
 if(fail_call||bad_readback) { assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U); }
 else { assert(result==USBD_OK);assert(calls==4U && UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)==USB_CDC_OK); }
 return 0;
}
