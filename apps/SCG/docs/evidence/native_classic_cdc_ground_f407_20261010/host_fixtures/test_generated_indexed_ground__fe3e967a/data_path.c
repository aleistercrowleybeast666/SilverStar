#include "usb_device.h"
#include "native_runtime.h"
#include "native_clock.h"
#include "ground_bridge.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"
#include "pc_byte_stream.h"
#include <assert.h>
#include <string.h>
#include <stdio.h>
uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
static uint8_t UserRxBufferFS[64],UserTxBufferFS[70];
static USBD_CDC_HandleTypeDef storage;
static uint32_t rx_length;
static unsigned prepared,transmitted,forwarded,acks,air_rx,statuses;
static uint8_t inject_radio_rx;
static const uint8_t *retained;
static uint8_t retained_copy[70];
static uint32_t retained_length;
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DataIn(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DataOut(USBD_HandleTypeDef *,uint8_t);
static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Receive_FS(uint8_t *,uint32_t *);
static int8_t CDC_TransmitCplt_FS(uint8_t *,uint32_t *,uint8_t);
uint8_t NativeRuntime_ReadyGet(void) { return 1U; }
void NativeRuntime_TransportFaultRecord(void) { assert(0 && "No stored ownership fault in normal path"); }
uint8_t NativeClock_ContextAllowedGet(void) { return usb_test_mask==0U ? 1U : 0U; }
NativeClockResult NativeClock_DelayUs(uint32_t delay) { assert(delay==1U && usb_test_mask==0U);return NativeClockResult_Ok; }
static void *TestAlloc(size_t size) { assert(size==sizeof(storage));return &storage; }
static void TestFree(void *data) { assert(data==&storage); }
#define USBD_malloc TestAlloc
#define USBD_free TestFree
static USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *p,uint8_t ep,uint8_t type,uint16_t size)
{ assert(p==&hUsbDeviceFS && (ep==0x81U || ep==1U || ep==0x82U) && type>=2U && size<=64U);return USBD_OK; }
static USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *p,uint8_t ep)
{ assert(p==&hUsbDeviceFS && (ep==0x81U || ep==1U || ep==0x82U));return USBD_OK; }
static USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&hUsbDeviceFS && ep==1U && data==UserRxBufferFS && size==64U);prepared++;return USBD_OK; }
static uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *p,uint8_t ep)
{ assert(p==&hUsbDeviceFS && ep==1U);return rx_length; }
static USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{
  assert(p==&hUsbDeviceFS && ep==0x81U && data!=NULL && size<=70U && usb_test_mask==1U);
  GspMinParser parser;GspMinFrame frame;GspParserResult result=GSP_PARSER_NO_FRAME;
  GspMinParser_Init(&parser);
  for (uint16_t i=0U;i<size;i++) { result=GspMinParser_InputByte(&parser,data[i],&frame); }
  assert(result==GSP_PARSER_FRAME_READY);
  if (frame.type==GSP_TYPE_ACK) { assert(frame.payload[1]==GSP_ACK_OK);acks++; }
  else if (frame.type==GSP_TYPE_AIR_RX)
  { assert(frame.payload_len==5U && frame.payload[3]==0x91U && frame.payload[4]==0x92U);air_rx++; }
  else { assert(frame.type==GSP_TYPE_GS_STATUS);statuses++; }
  retained=data;retained_length=size;memcpy(retained_copy,data,size);transmitted++;
  return USBD_OK;
}
uint8_t GroundRadio_MetricsSupportedGet(void) { return 1U; }
GroundRadioResult GroundRadio_Init(void) { return GROUND_RADIO_OK; }
void GroundRadio_Process(void) { }
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *data,uint8_t length)
{ assert(usb_test_mask==1U && length==2U && data[0]==0x42U && data[1]==0x43U);forwarded++;return GROUND_RADIO_OK; }
GroundRadioResult GroundRadio_RxDequeue(uint8_t *data,uint8_t *length,int8_t *rssi,int8_t *snr)
{ if (inject_radio_rx==0U) { return GROUND_RADIO_EMPTY; }inject_radio_rx=0U;
  data[0]=0x91U;data[1]=0x92U;*length=2U;*rssi=-70;*snr=3;return GROUND_RADIO_OK; }
void GroundRadio_StatsGet(GroundRadioStats *stats) { memset(stats,0,sizeof(*stats));stats->radio_state=GSP_RADIO_STATE_RX; }
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
static int8_t CDC_Init_FS(void)
{
  PcByteStream_OnUsbReset();
  if ((USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0U) != USBD_OK) ||
      (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS) != USBD_OK)) { return USBD_FAIL; }
  return USBD_OK;
}
static int8_t CDC_DeInit_FS(void)
{ PcByteStream_OnUsbReset(); return USBD_OK; }
static int8_t CDC_Receive_FS(uint8_t *Buf, uint32_t *Len)
{
  uint8_t result;
  if ((Buf == NULL) || (Len == NULL) || (*Len > 64U)) { return USBD_FAIL; }
  PcByteStream_OnUsbReceive(Buf, (uint16_t)*Len);
  result = USBD_CDC_SetRxBuffer(&hUsbDeviceFS, Buf);
  if (result == USBD_OK) { result = USBD_CDC_ReceivePacket(&hUsbDeviceFS); }
  if (result != USBD_OK) { PcByteStream_OnUsbReset(); }
  return (int8_t)result;
}
static int8_t CDC_TransmitCplt_FS(uint8_t *Buf, uint32_t *Len, uint8_t epnum)
{
  (void)Buf; (void)Len; (void)epnum;
  return (int8_t)USBD_OK;
}
uint8_t CDC_Transmit_FS(uint8_t *Buf, uint16_t Len)
{
  uint8_t result;
  if ((Buf == NULL) || (Len == 0U) || (Len > 70U) ||
      (hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) ||
      (hUsbDeviceFS.pClassDataCmsit[0] == NULL)) { return USBD_FAIL; }
  if ((hUsbDeviceFS.classId != 0U) ||
      (hUsbDeviceFS.pClassData != hUsbDeviceFS.pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return USBD_FAIL; }
  result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, Buf, Len);
  if (result != USBD_OK) { return (result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL; }
  result = USBD_CDC_TransmitPacket(&hUsbDeviceFS);
  return (result == USBD_OK) ? USBD_OK : ((result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL);
}
static void Complete(void)
{
  if (storage.TxState!=0U)
  { assert(retained!=NULL && memcmp(retained,retained_copy,retained_length)==0);
    assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)==USBD_OK && storage.TxState==0U); }
}
static void Input(void)
{
  const uint8_t payload[3]={2U,0x42U,0x43U};
  rx_length=GspMin_BuildFrame(GSP_TYPE_AIR_TX,payload,3U,UserRxBufferFS,64U);
  assert(rx_length!=0U && USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK);
}
int main(void)
{
  PCD_HandleTypeDef pcd={0};pcd.IN_ep[1].maxpacket=64U;
  USBD_CDC_ItfTypeDef itf={CDC_Init_FS,CDC_DeInit_FS,NULL,CDC_Receive_FS,CDC_TransmitCplt_FS};
  hUsbDeviceFS.dev_speed=USBD_SPEED_FULL;hUsbDeviceFS.pData=&pcd;hUsbDeviceFS.pUserData[0]=&itf;
  assert(USBD_CDC_Init(&hUsbDeviceFS,1U)==USBD_OK);
  hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
  assert(GroundBridge_Init()==GROUND_BRIDGE_OK);Complete();
  uint32_t session=PcByteStream_Session_Get();
  Input();inject_radio_rx=1U;
  for (uint32_t now=1U;now<10U;now++) { assert(GroundBridge_Process(now)==GROUND_BRIDGE_OK);Complete(); }
  assert(forwarded==1U && acks==1U && air_rx==1U && statuses>=1U && prepared==2U);
  assert(USBD_CDC_DeInit(&hUsbDeviceFS,1U)==USBD_OK);
  GroundBridge_PcReset();
  assert(USBD_CDC_Init(&hUsbDeviceFS,1U)==USBD_OK);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
  assert(PcByteStream_WriteSession(UserTxBufferFS,3U,session)==PC_BYTE_STREAM_WRITE_BUSY);
  GroundBridge_PcReset();Input();
  for (uint32_t now=10U;now<20U;now++) { assert(GroundBridge_Process(now)==GROUND_BRIDGE_OK);Complete(); }
  assert(forwarded==2U && acks==2U && prepared==4U && usb_test_mask==0U);
  assert(USBD_CDC_DeInit(&hUsbDeviceFS,1U)==USBD_OK);
  printf("PASS actual indexed CDC/callback/PC/GSP/Ground bidirectional flow; tx=%u radio_tx=%u ack=%u air_rx=%u rearm=%u; reconnect rejects stale session\n",transmitted,forwarded,acks,air_rx,prepared);
  return 0;
}
