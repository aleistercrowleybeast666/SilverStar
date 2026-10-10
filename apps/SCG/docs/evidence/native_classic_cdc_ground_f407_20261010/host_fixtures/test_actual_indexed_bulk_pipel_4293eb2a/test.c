#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#define USBD_OK 0U
#define USBD_BUSY 1U
#define USBD_FAIL 2U
#define USBD_SPEED_HIGH 0U
#define USBD_SPEED_FULL 1U
#define USBD_STATE_DEFAULT 1U
#define USBD_STATE_CONFIGURED 3U
#define USBD_EP_TYPE_BULK 2U
#define USBD_EP_TYPE_INTR 3U
#define CDC_IN_EP 0x81U
#define CDC_OUT_EP 0x01U
#define CDC_CMD_EP 0x82U
#define CDC_CMD_PACKET_SIZE 8U
#define CDC_DATA_HS_IN_PACKET_SIZE 512U
#define CDC_DATA_HS_OUT_PACKET_SIZE 512U
#define CDC_DATA_FS_IN_PACKET_SIZE 64U
#define CDC_DATA_FS_OUT_PACKET_SIZE 64U
typedef uint8_t USBD_StatusTypeDef;
typedef struct { uint32_t total_length;uint8_t is_used,bInterval; } Endpoint;
typedef struct { void *pClassData,*pData;void *pClassDataCmsit[1],*pUserData[1];uint8_t classId;uint8_t dev_speed,dev_state;Endpoint ep_in[16],ep_out[16]; } USBD_HandleTypeDef;
typedef struct { uint32_t TxState,RxState,TxLength,RxLength;uint8_t *TxBuffer,*RxBuffer; } USBD_CDC_HandleTypeDef;
typedef struct { int8_t (*Init)(void);int8_t (*DeInit)(void);int8_t (*Receive)(uint8_t *,uint32_t *);int8_t (*TransmitCplt)(uint8_t *,uint32_t *,uint8_t); } USBD_CDC_ItfTypeDef;
typedef struct { struct { uint32_t maxpacket; } IN_ep[16]; } PCD_HandleTypeDef;
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DataIn(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DataOut(USBD_HandleTypeDef *,uint8_t);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *,uint8_t *,uint32_t);
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *,uint8_t *);
static USBD_CDC_HandleTypeDef storage;
static USBD_HandleTypeDef dev;
static uint8_t rx[64],tx[70],fail_open,fail_init,fail_prepare,fail_tx,fail_receive,fail_close;
static unsigned opened,closed,prepared,transmitted,received,resets;
static void *TestAlloc(size_t size) { assert(size==sizeof(storage));memset(&storage,0,sizeof(storage));return &storage; }
static void TestFree(void *data) { assert(data==&storage); }
#define USBD_malloc TestAlloc
#define USBD_free TestFree
static void PcByteStream_OnUsbReset(void) { resets++; }
static USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *p,uint8_t ep,uint8_t type,uint16_t size)
{ assert(p==&dev && (ep==0x81U || ep==0x01U || ep==0x82U) && type>=2U && size<=64U);opened++;
  return opened==fail_open ? USBD_FAIL : USBD_OK; }
static USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *p,uint8_t ep)
{ assert(p==&dev && (ep==0x81U || ep==0x01U || ep==0x82U));closed++;return fail_close!=0U ? USBD_FAIL : USBD_OK; }
static USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&dev && ep==0x01U && data==rx && size==64U);prepared++;return fail_prepare!=0U ? USBD_FAIL : USBD_OK; }
static USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&dev && (ep==0x81U || ep==1U) && (data==tx || data==NULL) && size<=70U);transmitted++;return fail_tx; }
static uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *p,uint8_t ep)
{ assert(p==&dev && ep==1U);return 64U; }
static int8_t AppInit(void)
{ assert(USBD_CDC_SetRxBuffer(&dev,rx)==USBD_OK);assert(USBD_CDC_SetTxBuffer(&dev,tx,0U)==USBD_OK);return (int8_t)fail_init; }
static int8_t AppDeInit(void) { return USBD_OK; }
static int8_t AppReceive(uint8_t *p,uint32_t *length)
{ assert(p==rx && *length==64U);received++;return (int8_t)fail_receive; }

#define CDC_FS_BINTERVAL 16U
static unsigned transport_faults;
static void NativeRuntime_TransportFaultRecord(void) { transport_faults++; }

static uint8_t NativeCdc_Fault(USBD_HandleTypeDef *pdev)
{
  pdev->dev_state = USBD_STATE_DEFAULT;
  PcByteStream_OnUsbReset();
  return USBD_FAIL;
}
static uint8_t NativeCdc_InitAbort(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  uint8_t cleanup = USBD_CDC_DeInit(pdev, cfgidx);
  uint8_t failure = NativeCdc_Fault(pdev);
  /* Never turn successful cleanup into successful initialization. */
  return (cleanup == USBD_BUSY) ? USBD_BUSY : failure;
}
static uint8_t NativeCdc_Open(USBD_HandleTypeDef *pdev, uint8_t ep,
                            uint8_t type, uint16_t size)
{
  USBD_StatusTypeDef result = USBD_LL_OpenEP(pdev, ep, type, size);
  if (result != USBD_OK) { return (result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL; }
  if ((ep & 0x80U) != 0U) { pdev->ep_in[ep & 0x0FU].is_used = 1U; }
  else { pdev->ep_out[ep & 0x0FU].is_used = 1U; }
  return USBD_OK;
}
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  USBD_CDC_ItfTypeDef *itf;
  if ((pdev == NULL) || (pdev->dev_speed != USBD_SPEED_FULL) ||
      (pdev->pUserData[0] == NULL) || (pdev->pClassDataCmsit[0] != NULL)) { return USBD_FAIL; }
  itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData[0];
  if ((itf->Init == NULL) || (itf->DeInit == NULL) || (itf->Receive == NULL) ||
      (pdev->ep_in[CDC_IN_EP & 0x0FU].is_used != 0U) ||
      (pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used != 0U) ||
      (pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used != 0U)) { return USBD_FAIL; }
  pdev->ep_in[CDC_CMD_EP & 0x0FU].bInterval = CDC_FS_BINTERVAL;
  /* The recognized native configuration maps this to one static class block. */
  pdev->pClassDataCmsit[0] = USBD_malloc(sizeof(USBD_CDC_HandleTypeDef));
  pdev->pClassData = pdev->pClassDataCmsit[0];
  if (pdev->pClassDataCmsit[0] == NULL) { return NativeCdc_Fault(pdev); }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  memset(hcdc, 0, sizeof(*hcdc));
  if ((NativeCdc_Open(pdev, CDC_IN_EP, USBD_EP_TYPE_BULK, CDC_DATA_FS_IN_PACKET_SIZE) != USBD_OK) ||
      (NativeCdc_Open(pdev, CDC_OUT_EP, USBD_EP_TYPE_BULK, CDC_DATA_FS_OUT_PACKET_SIZE) != USBD_OK) ||
      (NativeCdc_Open(pdev, CDC_CMD_EP, USBD_EP_TYPE_INTR, CDC_CMD_PACKET_SIZE) != USBD_OK))
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  if ((itf->Init() != (int8_t)USBD_OK) || (hcdc->RxBuffer == NULL) || (hcdc->TxBuffer == NULL))
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  if (USBD_LL_PrepareReceive(pdev, CDC_OUT_EP, hcdc->RxBuffer, CDC_DATA_FS_OUT_PACKET_SIZE) != USBD_OK)
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  return USBD_OK;
}
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  uint8_t result = USBD_OK;
  USBD_CDC_ItfTypeDef *itf;
  /* There is one FS configuration; cleanup does not depend on its old index. */
  (void)cfgidx;
  if (pdev == NULL) { return USBD_FAIL; }
  if (pdev->ep_in[CDC_IN_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_IN_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_in[CDC_IN_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_OUT_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_CMD_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->pClassDataCmsit[0] != NULL)
  {
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
    hcdc->TxState = 1U; /* Retain buffer ownership until closure is confirmed. */
    itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData[0];
    if ((itf == NULL) || (itf->DeInit == NULL) || (itf->DeInit() != (int8_t)USBD_OK))
    { result = USBD_FAIL; }
    if (result == USBD_OK) { USBD_free(pdev->pClassDataCmsit[0]); pdev->pClassDataCmsit[0] = NULL; pdev->pClassData = NULL; }
  }
  if (result != USBD_OK) { return NativeCdc_Fault(pdev); }
  return result;
}
static uint8_t USBD_CDC_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  PCD_HandleTypeDef *hpcd;
  if ((pdev == NULL) || (epnum != (CDC_IN_EP & 0x7FU)) || (pdev->pClassDataCmsit[0] == NULL) ||
      (pdev->pData == NULL) || (pdev->dev_state != USBD_STATE_CONFIGURED)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  hpcd = (PCD_HandleTypeDef *)pdev->pData;
  if (hpcd->IN_ep[epnum].maxpacket != CDC_DATA_FS_IN_PACKET_SIZE)
  { return NativeCdc_Fault(pdev); }
  if ((pdev->ep_in[epnum].total_length > 0U) &&
      ((pdev->ep_in[epnum].total_length % CDC_DATA_FS_IN_PACKET_SIZE) == 0U))
  {
    USBD_StatusTypeDef result;
    pdev->ep_in[epnum].total_length = 0U;
    result = USBD_LL_Transmit(pdev, epnum, NULL, 0U);
    if (result != USBD_OK)
    {
      uint8_t failure = NativeCdc_Fault(pdev);
      return (result == USBD_BUSY) ? USBD_BUSY : failure;
    }
  }
  else
  {
    USBD_CDC_ItfTypeDef *itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData[0];
    if ((itf == NULL) || ((itf->TransmitCplt != NULL) &&
        (itf->TransmitCplt(hcdc->TxBuffer, &hcdc->TxLength, epnum) != (int8_t)USBD_OK)))
    { return NativeCdc_Fault(pdev); }
    hcdc->TxState = 0U;
  }
  return USBD_OK;
}
static uint8_t USBD_CDC_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  USBD_CDC_ItfTypeDef *itf;
  int8_t result;
  if ((pdev == NULL) || (epnum != (CDC_OUT_EP & 0x7FU)) || (pdev->pClassDataCmsit[0] == NULL) ||
      (pdev->pUserData[0] == NULL) || (pdev->dev_state != USBD_STATE_CONFIGURED)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData[0];
  if ((hcdc->RxBuffer == NULL) || (itf->Receive == NULL)) { return NativeCdc_Fault(pdev); }
  hcdc->RxLength = USBD_LL_GetRxDataSize(pdev, epnum);
  if (hcdc->RxLength > CDC_DATA_FS_OUT_PACKET_SIZE) { return NativeCdc_Fault(pdev); }
  result = itf->Receive(hcdc->RxBuffer, &hcdc->RxLength);
  if (result != (int8_t)USBD_OK)
  {
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == (int8_t)USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *pdev)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->pClassDataCmsit[0] == NULL) ||
      (pdev->dev_state != USBD_STATE_CONFIGURED) || (pdev->dev_speed != USBD_SPEED_FULL))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  if (hcdc->TxState != 0U) { return USBD_BUSY; }
  if ((hcdc->TxBuffer == NULL) || (hcdc->TxLength == 0U) || (hcdc->TxLength > 70U))
  { return USBD_FAIL; }
  hcdc->TxState = 1U;
  pdev->ep_in[CDC_IN_EP & 0x0FU].total_length = hcdc->TxLength;
  result = USBD_LL_Transmit(pdev, CDC_IN_EP, hcdc->TxBuffer, (uint16_t)hcdc->TxLength);
  if (result != USBD_OK)
  {
    /* A failed LL call cannot prove absence of partial DMA ownership. Keep
     * TxState and bytes owned until successful endpoint closure or reset. */
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *pdev)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->pClassDataCmsit[0] == NULL) || (pdev->dev_speed != USBD_SPEED_FULL))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  if (hcdc->RxBuffer == NULL) { return USBD_FAIL; }
  result = USBD_LL_PrepareReceive(pdev, CDC_OUT_EP, hcdc->RxBuffer, CDC_DATA_FS_OUT_PACKET_SIZE);
  if (result != USBD_OK)
  {
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *pdev, uint8_t *pbuff, uint32_t length)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  /* This private owner accepts the SCG-owned maximum 70-byte GSP frame. */
  if ((pdev == NULL) || (pdev->pClassDataCmsit[0] == NULL) || (pbuff == NULL) || (length > 70U))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  if (hcdc->TxState != 0U) { return USBD_BUSY; }
  hcdc->TxBuffer = pbuff; hcdc->TxLength = length;
  return USBD_OK;
}
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *pdev, uint8_t *pbuff)
{
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }

  USBD_CDC_HandleTypeDef *hcdc;
  if ((pdev == NULL) || (pdev->pClassDataCmsit[0] == NULL) || (pbuff == NULL)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassDataCmsit[0];
  hcdc->RxBuffer = pbuff;
  return USBD_OK;
}
int main(int argc,char **argv)
{
    assert(argc==2);USBD_CDC_ItfTypeDef itf={AppInit,AppDeInit,AppReceive,NULL};PCD_HandleTypeDef pcd={0};
    pcd.IN_ep[1].maxpacket=64U;dev.pData=&pcd;dev.pUserData[0]=&itf;dev.dev_speed=USBD_SPEED_FULL;
    if (strcmp(argv[1],"open1")==0) { fail_open=1U; }
    if (strcmp(argv[1],"open2")==0) { fail_open=2U; }
    if (strcmp(argv[1],"open3")==0) { fail_open=3U; }
    if (strcmp(argv[1],"app-init")==0) { fail_init=USBD_FAIL; }
    if (strcmp(argv[1],"prepare-init")==0) { fail_prepare=1U; }
    uint8_t result=USBD_CDC_Init(&dev,1U);
    if (fail_open!=0U || fail_init!=0U || fail_prepare!=0U)
    {
        assert(result!=USBD_OK && dev.dev_state!=USBD_STATE_CONFIGURED && dev.pClassData==NULL);
        assert(resets!=0U && dev.ep_in[1].is_used==0U && dev.ep_out[1].is_used==0U && dev.ep_in[2].is_used==0U);return 0;
    }
    assert(result==USBD_OK && storage.TxState==0U && prepared==1U);dev.dev_state=USBD_STATE_CONFIGURED;
    if (strcmp(argv[1],"bad-class")==0) { dev.classId=7U;assert(USBD_CDC_TransmitPacket(&dev)!=USBD_OK && transport_faults==1U && resets!=0U);return 0; }
    if (strcmp(argv[1],"mirror")==0) { dev.pClassData=NULL;assert(USBD_CDC_ReceivePacket(&dev)!=USBD_OK && transport_faults==1U);return 0; }
    if (strcmp(argv[1],"tx-fail")==0 || strcmp(argv[1],"tx-busy")==0)
    {
        fail_tx=strcmp(argv[1],"tx-busy")==0 ? USBD_BUSY : USBD_FAIL;
        assert(USBD_CDC_SetTxBuffer(&dev,tx,70U)==USBD_OK);
        assert(USBD_CDC_TransmitPacket(&dev)==fail_tx && transmitted==1U);
        assert(dev.dev_state!=USBD_STATE_CONFIGURED && storage.TxState!=0U && resets!=0U);return 0;
    }
    if (strcmp(argv[1],"rearm")==0)
    { fail_prepare=1U;assert(USBD_CDC_ReceivePacket(&dev)!=USBD_OK && resets!=0U);return 0; }
    if (strcmp(argv[1],"receive")==0)
    { fail_receive=USBD_FAIL;assert(USBD_CDC_DataOut(&dev,1U)!=USBD_OK && received==1U && resets!=0U);return 0; }
    if (strcmp(argv[1],"zlp")==0)
    { storage.TxState=1U;dev.ep_in[1].total_length=64U;fail_tx=USBD_FAIL;
      assert(USBD_CDC_DataIn(&dev,1U)!=USBD_OK && storage.TxState==1U && resets!=0U);return 0; }
    if (strcmp(argv[1],"close")==0)
    { fail_close=1U;assert(USBD_CDC_DeInit(&dev,1U)!=USBD_OK && dev.pClassData==&storage && storage.TxState!=0U);return 0; }
    if (strcmp(argv[1],"null-rx")==0)
    { assert(USBD_CDC_SetRxBuffer(&dev,NULL)!=USBD_OK && storage.RxBuffer==rx);return 0; }
    if (strcmp(argv[1],"null-out")==0)
    { dev.pClassData=NULL;assert(USBD_CDC_DataOut(&dev,1U)!=USBD_OK && received==0U);return 0; }
    if (strcmp(argv[1],"oversize")==0)
    { assert(USBD_CDC_SetTxBuffer(&dev,tx,71U)!=USBD_OK && storage.TxLength==0U);return 0; }
    if (strcmp(argv[1],"bad-ep")==0)
    { assert(USBD_CDC_DataOut(&dev,255U)!=USBD_OK && USBD_CDC_DataIn(&dev,255U)!=USBD_OK && received==0U);return 0; }
    assert(USBD_CDC_SetTxBuffer(&dev,tx,70U)==USBD_OK);
    assert(USBD_CDC_TransmitPacket(&dev)==USBD_OK && storage.TxState==1U);
    assert(USBD_CDC_TransmitPacket(&dev)==USBD_BUSY && transmitted==1U);
    assert(USBD_CDC_DataIn(&dev,1U)==USBD_OK && storage.TxState==0U);
    assert(USBD_CDC_DataOut(&dev,1U)==USBD_OK && received==1U);
    assert(USBD_CDC_ReceivePacket(&dev)==USBD_OK && prepared==2U);
    assert(USBD_CDC_DeInit(&dev,1U)==USBD_OK && dev.pClassData==NULL && closed==3U);return 0;
}
