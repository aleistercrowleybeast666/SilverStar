#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#define DEVICE_FS 0U
#define USB_OTG_FS ((void *)1)
#define PCD_SPEED_FULL 1U
#define PCD_PHY_EMBEDDED 2U
#define DISABLE 0U
#define USBD_STATE_DEFAULT 1U
typedef enum { HAL_OK,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { USBD_OK,USBD_BUSY,USBD_FAIL } USBD_StatusTypeDef;
typedef struct { void *pData;uint8_t id,dev_state; } USBD_HandleTypeDef;
typedef struct { void *pData,*Instance;struct { uint32_t dev_endpoints,speed,dma_enable,phy_itface,Sof_enable,low_power_enable,lpm_enable,vbus_sensing_enable,use_dedicated_ep1; } Init; } PCD_HandleTypeDef;
static PCD_HandleTypeDef hpcd_USB_OTG_FS;
static unsigned fifo_calls,resets,retired,faults,hal_calls;
static unsigned fail_fifo,fail_pcd,fail_cleanup;
static HAL_StatusTypeDef transfer_result=HAL_OK;
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *);
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *);
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *);
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *,uint8_t,uint8_t *,uint32_t);
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *,uint8_t,uint8_t *,uint32_t);
USBD_StatusTypeDef USBD_Get_USB_Status(HAL_StatusTypeDef);
static void PcByteStream_OnUsbReset(void) { resets++; }
static void NativeRuntime_TransportFaultRecord(void) { faults++; }
static HAL_StatusTypeDef HAL_PCD_Init(PCD_HandleTypeDef *p)
{ assert(p==&hpcd_USB_OTG_FS);assert(p->Init.dev_endpoints==4U && p->Init.dma_enable==0U);return fail_pcd!=0U ? HAL_ERROR : HAL_OK; }
static HAL_StatusTypeDef HAL_PCD_DeInit(PCD_HandleTypeDef *p)
{ assert(p==&hpcd_USB_OTG_FS);retired++;return fail_cleanup!=0U ? HAL_ERROR : HAL_OK; }
static HAL_StatusTypeDef HAL_PCDEx_SetRxFiFo(PCD_HandleTypeDef *p,uint16_t size)
{ assert(p==&hpcd_USB_OTG_FS && size==128U);fifo_calls++;return fail_fifo==fifo_calls ? HAL_ERROR : HAL_OK; }
static HAL_StatusTypeDef HAL_PCDEx_SetTxFiFo(PCD_HandleTypeDef *p,uint8_t ep,uint16_t size)
{ assert(p==&hpcd_USB_OTG_FS && ep<3U && size==(ep==2U ? 16U : 64U));fifo_calls++;return fail_fifo==fifo_calls ? HAL_ERROR : HAL_OK; }
static HAL_StatusTypeDef HAL_PCD_Start(void *p) { assert(p==&hpcd_USB_OTG_FS);hal_calls++;return transfer_result; }
static HAL_StatusTypeDef HAL_PCD_Stop(void *p) { assert(p==&hpcd_USB_OTG_FS);hal_calls++;return transfer_result; }
static HAL_StatusTypeDef HAL_PCD_EP_Transmit(void *p,uint8_t ep,uint8_t *buf,uint32_t size)
{ assert(p==&hpcd_USB_OTG_FS && ep==0x81U && buf!=NULL && size==70U);hal_calls++;return transfer_result; }
static HAL_StatusTypeDef HAL_PCD_EP_Receive(void *p,uint8_t ep,uint8_t *buf,uint32_t size)
{ assert(p==&hpcd_USB_OTG_FS && ep==1U && buf!=NULL && size==64U);hal_calls++;return transfer_result; }
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
    PcByteStream_OnUsbReset();
    if (HAL_PCD_DeInit(&hpcd_USB_OTG_FS) != HAL_OK) { NativeRuntime_TransportFaultRecord(); }
    return USBD_FAIL;
  }
  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *pdev)
{
  HAL_StatusTypeDef hal_status = HAL_OK;
  USBD_StatusTypeDef usb_status = USBD_OK;

  hal_status = HAL_PCD_Start(pdev->pData);

  usb_status =  USBD_Get_USB_Status(hal_status);

  return usb_status;
}
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *pdev)
{
  HAL_StatusTypeDef hal_status = HAL_OK;
  USBD_StatusTypeDef usb_status = USBD_OK;

  hal_status = HAL_PCD_Stop(pdev->pData);

  usb_status =  USBD_Get_USB_Status(hal_status);

  return usb_status;
}
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *pdev, uint8_t ep_addr, uint8_t *pbuf, uint32_t size)
{
  HAL_StatusTypeDef hal_status = HAL_OK;
  USBD_StatusTypeDef usb_status = USBD_OK;

  hal_status = HAL_PCD_EP_Transmit(pdev->pData, ep_addr, pbuf, size);

  usb_status =  USBD_Get_USB_Status(hal_status);

  return usb_status;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *pdev, uint8_t ep_addr, uint8_t *pbuf, uint32_t size)
{
  HAL_StatusTypeDef hal_status = HAL_OK;
  USBD_StatusTypeDef usb_status = USBD_OK;

  hal_status = HAL_PCD_EP_Receive(pdev->pData, ep_addr, pbuf, size);

  usb_status =  USBD_Get_USB_Status(hal_status);

  return usb_status;
}
USBD_StatusTypeDef USBD_Get_USB_Status(HAL_StatusTypeDef hal_status)
{
  USBD_StatusTypeDef usb_status = USBD_OK;

  switch (hal_status)
  {
    case HAL_OK :
      usb_status = USBD_OK;
    break;
    case HAL_ERROR :
      usb_status = USBD_FAIL;
    break;
    case HAL_BUSY :
      usb_status = USBD_BUSY;
    break;
    case HAL_TIMEOUT :
      usb_status = USBD_FAIL;
    break;
    default :
      usb_status = USBD_FAIL;
    break;
  }
  return usb_status;
}
int main(int argc,char **argv)
{
  assert(argc==2);USBD_HandleTypeDef dev={.id=DEVICE_FS,.dev_state=3U};uint8_t data[70]={0};
  if (strcmp(argv[1],"pcd-init")==0) { fail_pcd=1U; }
  if (strncmp(argv[1],"fifo",4U)==0 && argv[1][4]>='1' && argv[1][4]<='4') { fail_fifo=(unsigned)(argv[1][4]-'0'); }
  if (strcmp(argv[1],"fifo-cleanup")==0) { fail_fifo=4U;fail_cleanup=1U; }
  USBD_StatusTypeDef initialized=USBD_LL_Init(&dev);
  if (fail_pcd!=0U) { assert(initialized==USBD_FAIL && fifo_calls==0U);return 0; }
  if (fail_fifo!=0U)
  { assert(initialized==USBD_FAIL && fifo_calls==fail_fifo && retired==1U && resets==1U);
    assert(dev.dev_state==USBD_STATE_DEFAULT && faults==(fail_cleanup!=0U ? 1U : 0U));return 0; }
  assert(initialized==USBD_OK && fifo_calls==4U && hpcd_USB_OTG_FS.pData==&dev && dev.pData==&hpcd_USB_OTG_FS);
  if (strcmp(argv[1],"busy")==0) { transfer_result=HAL_BUSY; }
  else if (strcmp(argv[1],"timeout")==0) { transfer_result=HAL_TIMEOUT; }
  else if (strcmp(argv[1],"normal")!=0) { transfer_result=HAL_ERROR; }
  USBD_StatusTypeDef expected=transfer_result==HAL_OK ? USBD_OK : (transfer_result==HAL_BUSY ? USBD_BUSY : USBD_FAIL);
  assert(USBD_LL_Start(&dev)==expected && USBD_LL_Stop(&dev)==expected);
  assert(USBD_LL_Transmit(&dev,0x81U,data,70U)==expected);
  assert(USBD_LL_PrepareReceive(&dev,1U,data,64U)==expected && hal_calls==4U);
  return 0;
}
