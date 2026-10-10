#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#define USBD_DEBUG_LEVEL 0U
#define USE_HAL_PCD_REGISTER_CALLBACKS 0U
#define USBD_STATE_DEFAULT 1U
#define PCD_SPEED_FULL 2U
#define DISABLE 0U
#define PCD_SNG_BUF 0U
#define USB ((void *)1)
typedef enum { HAL_OK,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT } HAL_StatusTypeDef;
typedef enum { USBD_OK,USBD_BUSY,USBD_FAIL } USBD_StatusTypeDef;
typedef struct { uint8_t unused; } USBD_DescriptorsTypeDef;
typedef struct { void *pClass,*pData;USBD_DescriptorsTypeDef *pDesc;uint8_t dev_state,id; } USBD_HandleTypeDef;
typedef struct { void *pData,*Instance;struct { uint32_t dev_endpoints,speed,low_power_enable,lpm_enable,battery_charging_enable; } Init; } PCD_HandleTypeDef;
static PCD_HandleTypeDef hpcd_USB_FS;
static uint8_t fail_pcd,fail_pma;
static unsigned errors,pmas;
static USBD_StatusTypeDef init_result=USBD_OK,start_result=USBD_OK;
static HAL_StatusTypeDef transfer_result=HAL_OK;
USBD_StatusTypeDef USBD_Init(USBD_HandleTypeDef *,USBD_DescriptorsTypeDef *,uint8_t);
USBD_StatusTypeDef USBD_Start(USBD_HandleTypeDef *);
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *);
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *,uint8_t,uint8_t *,uint16_t);
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *,uint8_t,uint8_t *,uint16_t);
USBD_StatusTypeDef USBD_Get_USB_Status(HAL_StatusTypeDef);
static void Error_Handler(void) { errors++; }
static HAL_StatusTypeDef HAL_PCD_Init(PCD_HandleTypeDef *p) { assert(p==&hpcd_USB_FS);return fail_pcd!=0U ? HAL_ERROR : HAL_OK; }
static HAL_StatusTypeDef HAL_PCDEx_PMAConfig(PCD_HandleTypeDef *p,uint16_t ep,uint16_t mode,uint32_t offset)
{ assert(p==&hpcd_USB_FS && ep<=0x82U && mode==0U && offset<512U);pmas++;return pmas==fail_pma ? HAL_ERROR : HAL_OK; }
static HAL_StatusTypeDef HAL_PCD_EP_Transmit(void *p,uint8_t ep,uint8_t *buf,uint16_t size)
{ assert(p==&hpcd_USB_FS && ep==0x81U && buf!=NULL && size==3U);return transfer_result; }
static HAL_StatusTypeDef HAL_PCD_EP_Receive(void *p,uint8_t ep,uint8_t *buf,uint16_t size)
{ assert(p==&hpcd_USB_FS && ep==1U && buf!=NULL && size==64U);return transfer_result; }
static USBD_StatusTypeDef CoreInit(USBD_HandleTypeDef *pdev) { assert(pdev!=NULL);return init_result; }
static USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *pdev) { assert(pdev!=NULL);return start_result; }

USBD_StatusTypeDef USBD_Init(USBD_HandleTypeDef *pdev,
                             USBD_DescriptorsTypeDef *pdesc, uint8_t id)
{
  /* Check whether the USB Host handle is valid */
  if (pdev == NULL)
  {
#if (USBD_DEBUG_LEVEL > 1U)
    USBD_ErrLog("Invalid Device handle");
#endif
    return USBD_FAIL;
  }

  /* Unlink previous class*/
  if (pdev->pClass != NULL)
  {
    pdev->pClass = NULL;
  }

  /* Assign USBD Descriptors */
  if (pdesc != NULL)
  {
    pdev->pDesc = pdesc;
  }

  /* Set Device initial State */
  pdev->dev_state = USBD_STATE_DEFAULT;
  pdev->id = id;
  /* Initialize low level driver */
  return CoreInit(pdev);
}
USBD_StatusTypeDef  USBD_Start(USBD_HandleTypeDef *pdev)
{
  /* Start the low level driver  */
  if (pdev == NULL) { return USBD_FAIL; }
  return USBD_LL_Start(pdev);
}
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
  if (pdev == NULL) { return USBD_FAIL; }

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
    return USBD_FAIL;
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
  if (HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x00 , PCD_SNG_BUF, 0x18) != HAL_OK) { return USBD_FAIL; }
  if (HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x80 , PCD_SNG_BUF, 0x58) != HAL_OK) { return USBD_FAIL; }
  /* USER CODE END EndPoint_Configuration */
  /* USER CODE BEGIN EndPoint_Configuration_CDC */
  if (HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x81 , PCD_SNG_BUF, 0xC0) != HAL_OK) { return USBD_FAIL; }
  if (HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x01 , PCD_SNG_BUF, 0x110) != HAL_OK) { return USBD_FAIL; }
  if (HAL_PCDEx_PMAConfig((PCD_HandleTypeDef*)pdev->pData , 0x82 , PCD_SNG_BUF, 0x100) != HAL_OK) { return USBD_FAIL; }
  /* USER CODE END EndPoint_Configuration_CDC */
  return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *pdev, uint8_t ep_addr, uint8_t *pbuf, uint16_t size)
{
  HAL_StatusTypeDef hal_status = HAL_OK;
  USBD_StatusTypeDef usb_status = USBD_OK;

  hal_status = HAL_PCD_EP_Transmit(pdev->pData, ep_addr, pbuf, size);

  usb_status =  USBD_Get_USB_Status(hal_status);

  return usb_status;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *pdev, uint8_t ep_addr, uint8_t *pbuf, uint16_t size)
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
  assert(argc==2);USBD_HandleTypeDef dev={0};USBD_DescriptorsTypeDef descriptor={0};uint8_t data[64]={0};
  if (strcmp(argv[1],"core-init")==0) { init_result=USBD_FAIL; }
  if (strcmp(argv[1],"core-start")==0) { start_result=USBD_BUSY; }
  assert(USBD_Init(&dev,&descriptor,0U)==init_result);
  assert(USBD_Start(&dev)==start_result);
  if (strcmp(argv[1],"pcd-init")==0) { fail_pcd=1U; }
  if (strcmp(argv[1],"pma")==0) { fail_pma=3U; }
  USBD_StatusTypeDef initialized=USBD_LL_Init(&dev);
  if (fail_pcd!=0U || fail_pma!=0U)
  { assert(initialized!=USBD_OK && errors==0U);return 0; }
  assert(initialized==USBD_OK && pmas==5U && errors==0U);
  if (strcmp(argv[1],"tx")==0 || strcmp(argv[1],"rearm")==0)
  {
    const HAL_StatusTypeDef hal[]={HAL_OK,HAL_ERROR,HAL_BUSY,HAL_TIMEOUT};
    const USBD_StatusTypeDef usb[]={USBD_OK,USBD_FAIL,USBD_BUSY,USBD_FAIL};
    for (unsigned i=0U;i<4U;i++)
    { transfer_result=hal[i];assert(USBD_LL_Transmit(&dev,0x81U,data,3U)==usb[i]);
      assert(USBD_LL_PrepareReceive(&dev,1U,data,64U)==usb[i]); }
  }
  return 0;
}
