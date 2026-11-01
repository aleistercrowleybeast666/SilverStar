#include "usbd_core.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include "usbd_desc.h"
#include "usb_cdc_transport.h"
#ifdef HOST_C071
#include "pc_c071_usb.h"
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
USBD_HandleTypeDef hUsbDeviceFS;
uint32_t host_mask;
uint32_t host_uid[3]={0x12345678U,0x3456789AU,0x56789ABCU};
static PCD_HandleTypeDef pcd;
static uint8_t *rx_ptr[8],*tx_ptr[8];
static uint32_t rx_count[8],tx_size[8];
static unsigned closes,allocated,frees;
static unsigned fail_close_once;
static unsigned fail_open_once,fail_prepare_once;
static unsigned fail_tx_once;
static unsigned fail_ep0_tx_once,fail_ep0_rx_once,ep0_ll_calls;
static unsigned allow_control_error;
static uint32_t class_storage[(sizeof(USBD_CDC_HandleTypeDef)/4U)+1U];
void *USBD_static_malloc(uint32_t size)
{ assert(size==sizeof(USBD_CDC_HandleTypeDef));assert(allocated==0U);allocated=1U;return class_storage; }
void USBD_static_free(void *p)
{ assert(p==class_storage && allocated==1U);assert(rx_ptr[1]==NULL && tx_ptr[1]==NULL);allocated=0U;frees++; }
uint8_t NativeRuntime_ReadyGet(void) { return 1U; }
void NativeRuntime_TransportFaultRecord(void) { }
uint8_t NativeClock_ContextAllowedGet(void) { return host_mask==0U; }
int NativeClock_DelayUs(uint32_t v) { assert(v==1U && host_mask==0U);return 0; }
USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *d)
{ assert(d==&hUsbDeviceFS);d->pData=&pcd;return USBD_OK; }
USBD_StatusTypeDef USBD_LL_DeInit(USBD_HandleTypeDef *d)
{ assert(d==&hUsbDeviceFS);assert(allocated==0U);return USBD_OK; }
USBD_StatusTypeDef USBD_LL_Start(USBD_HandleTypeDef *d) { assert(d==&hUsbDeviceFS);return USBD_OK; }
USBD_StatusTypeDef USBD_LL_Stop(USBD_HandleTypeDef *d)
{ assert(d==&hUsbDeviceFS);memset(rx_ptr,0,sizeof(rx_ptr));memset(tx_ptr,0,sizeof(tx_ptr));return USBD_OK; }
USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *d,uint8_t ep,uint8_t type,uint16_t size)
{ assert(d==&hUsbDeviceFS);(void)type;if(ep==0x01U && fail_open_once!=0U){fail_open_once=0U;return USBD_FAIL;}if((ep&0x80U)!=0U){pcd.IN_ep[ep&0x7FU].maxpacket=size;}return USBD_OK; }
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *d,uint8_t ep)
{ assert(d==&hUsbDeviceFS);if(ep==0x81U && fail_close_once!=0U){fail_close_once=0U;return USBD_FAIL;}if((ep&0x80U)!=0U){tx_ptr[ep&0x7FU]=NULL;}else{rx_ptr[ep]=NULL;}closes++;return USBD_OK; }
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;(void)ep;return USBD_OK; }
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *d,uint8_t ep)
{ /* ST F1 normally stalls OUT after its completed status phase. */
  assert(d==&hUsbDeviceFS && (ep==0x80U || (ep==0U && (d->ep0_state==USBD_EP0_IDLE || allow_control_error!=0U))));return USBD_OK; }
USBD_StatusTypeDef USBD_LL_ClearStallEP(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;(void)ep;return USBD_OK; }
uint8_t USBD_LL_IsStallEP(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;(void)ep;return 0U; }
USBD_StatusTypeDef USBD_LL_SetUSBAddress(USBD_HandleTypeDef *d,uint8_t address)
{ assert(d==&hUsbDeviceFS && address==5U);return USBD_OK; }
#ifdef HOST_F103
typedef uint16_t HostTransferLength;
#else
typedef uint32_t HostTransferLength;
#endif
USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *d,uint8_t ep,uint8_t *p,HostTransferLength n)
{
 assert(d==&hUsbDeviceFS);if((ep&0x7FU)==0U){ep0_ll_calls++;if(fail_ep0_tx_once){fail_ep0_tx_once=0U;return USBD_FAIL;}}tx_ptr[ep&0x7FU]=p;tx_size[ep&0x7FU]=n;
 if((ep&0x7FU)==1U && fail_tx_once!=0U)
 {
  fail_tx_once=0U;
#ifdef HOST_C071
  PcC071Usb_TxStartResult(0U);
#endif
  return USBD_FAIL;
 }
#ifdef HOST_C071
 if((ep&0x7FU)==1U){PcC071Usb_TxStartResult(1U);}
#endif
 return USBD_OK;
}
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *d,uint8_t ep,uint8_t *p,HostTransferLength n)
{
 assert(d==&hUsbDeviceFS);
 if(ep==0U){ep0_ll_calls++;if(fail_ep0_rx_once){fail_ep0_rx_once=0U;return USBD_FAIL;}}
 if(ep==0x01U && fail_prepare_once!=0U)
 {
  fail_prepare_once=0U;
#ifdef HOST_C071
  PcC071Usb_RxArmResult(0U);
#endif
  return USBD_FAIL;
 }
 rx_ptr[ep&0x7FU]=p;(void)n;
#ifdef HOST_C071
 if(ep==0x01U){PcC071Usb_RxArmResult(1U);}
#endif
 return USBD_OK;
}
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *d,uint8_t ep)
{ assert(d==&hUsbDeviceFS);return rx_count[ep&0x7FU]; }
void USBD_LL_Delay(uint32_t n) { (void)n; }
static void Setup(uint8_t bm,uint8_t req,uint16_t value,uint16_t index,uint16_t length)
{
 uint8_t bytes[8]={bm,req,(uint8_t)value,(uint8_t)(value>>8),(uint8_t)index,(uint8_t)(index>>8),(uint8_t)length,(uint8_t)(length>>8)};
 USBD_StatusTypeDef status=USBD_LL_SetupStage(&hUsbDeviceFS,bytes);
 assert(status==USBD_OK || (allow_control_error!=0U && status==USBD_FAIL));
}
static void InDone(uint8_t ep)
{ uint8_t *next=tx_ptr[ep];if(ep==0U && tx_size[ep]>pcd.IN_ep[ep].maxpacket){next+=pcd.IN_ep[ep].maxpacket;}assert(USBD_LL_DataInStage(&hUsbDeviceFS,ep,next)==USBD_OK); }
static void ControlInDone(void)
{
 for(unsigned packet=0U;packet<4U && hUsbDeviceFS.ep0_state==USBD_EP0_DATA_IN;packet++){InDone(0U);}
 assert(hUsbDeviceFS.ep0_state==USBD_EP0_STATUS_OUT);
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])==USBD_OK);
}
static void EnumConfigure(void)
{
 assert(USBD_LL_DevConnected(&hUsbDeviceFS)==USBD_OK);
 assert(USBD_LL_SetSpeed(&hUsbDeviceFS,USBD_SPEED_FULL)==USBD_OK);
 assert(USBD_LL_Reset(&hUsbDeviceFS)==USBD_OK);
 assert(hUsbDeviceFS.dev_state==USBD_STATE_DEFAULT && allocated==0U);
 Setup(0x80U,USB_REQ_GET_DESCRIPTOR,0x0100U,0U,18U);
 assert(tx_size[0]==18U && tx_ptr[0][0]==18U && tx_ptr[0][1]==USB_DESC_TYPE_DEVICE);InDone(0U);
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])==USBD_OK);
 Setup(0x00U,USB_REQ_SET_ADDRESS,5U,0U,0U);InDone(0U);
 assert(hUsbDeviceFS.dev_state==USBD_STATE_ADDRESSED);
 Setup(0x80U,USB_REQ_GET_DESCRIPTOR,0x0200U,0U,9U);
 assert(tx_size[0]==9U && tx_ptr[0][1]==USB_DESC_TYPE_CONFIGURATION);
 uint16_t conf_length=(uint16_t)(tx_ptr[0][2]|((uint16_t)tx_ptr[0][3]<<8U));ControlInDone();
 Setup(0x80U,USB_REQ_GET_DESCRIPTOR,0x0200U,0U,conf_length);
 assert(tx_size[0]==conf_length && conf_length>64U);ControlInDone();
 for(uint16_t string=0U;string<4U;string++)
 {
  Setup(0x80U,USB_REQ_GET_DESCRIPTOR,(uint16_t)(0x0300U|string),(string==0U)?0U:0x0409U,255U);
  assert(tx_size[0]>=4U && tx_ptr[0][1]==USB_DESC_TYPE_STRING);ControlInDone();
 }
 Setup(0x00U,USB_REQ_SET_CONFIGURATION,1U,0U,0U);InDone(0U);
 assert(hUsbDeviceFS.dev_state==USBD_STATE_CONFIGURED && allocated==1U);
 assert(rx_ptr[1]!=NULL && hUsbDeviceFS.pClassData!=NULL);
 Setup(0x80U,USB_REQ_GET_CONFIGURATION,0U,0U,1U);
 assert(tx_size[0]==1U && tx_ptr[0][0]==1U);ControlInDone();
 for(uint16_t interface=0U;interface<2U;interface++)
 {
  Setup(0x81U,USB_REQ_GET_INTERFACE,0U,interface,1U);
  assert(tx_size[0]==1U && tx_ptr[0][0]==0U);ControlInDone();
 }
}
static void ControlNormal(void)
{
 uint8_t line[7]={0x80U,0x25U,0U,0U,0U,0U,8U};
 Setup(0x21U,CDC_SET_LINE_CODING,0U,0U,7U);
 assert(rx_ptr[0]!=NULL);memcpy(rx_ptr[0],line,7U);rx_count[0]=7U;
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])==USBD_OK);InDone(0U);
 Setup(0xA1U,CDC_GET_LINE_CODING,0U,0U,7U);
 assert(tx_size[0]==7U && memcmp(tx_ptr[0],line,7U)==0);InDone(0U);
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])==USBD_OK);
 Setup(0x21U,CDC_SET_CONTROL_LINE_STATE,3U,0U,0U);InDone(0U);
}
static void ControlBoundaries(void)
{
 static const uint16_t lengths[]={0U,1U,6U,7U,8U,64U,255U,65535U};
 for(unsigned i=0U;i<sizeof(lengths)/sizeof(lengths[0]);i++)
 {
  uint16_t n=lengths[i];uint8_t get[8]={0xA1U,CDC_GET_LINE_CODING,0U,0U,0U,0U,(uint8_t)n,(uint8_t)(n>>8U)};
  assert(USBD_LL_SetupStage(&hUsbDeviceFS,get)==USBD_OK);
  assert(tx_size[0]==(n<7U?n:7U));
 }
 allow_control_error=1U;
 for(unsigned i=0U;i<sizeof(lengths)/sizeof(lengths[0]);i++)
 {
  uint16_t n=lengths[i];uint8_t set[8]={0x21U,CDC_SET_LINE_CODING,0U,0U,0U,0U,(uint8_t)n,(uint8_t)(n>>8U)};
  if(n!=7U){assert(USBD_LL_SetupStage(&hUsbDeviceFS,set)!=USBD_OK);}
 }
 Setup(0x21U,CDC_SET_LINE_CODING,0U,0U,7U);
 memset(rx_ptr[0],0,64U);rx_count[0]=64U;
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])!=USBD_OK);
 Setup(0x21U,CDC_SET_LINE_CODING,0U,0U,7U);
 rx_count[0]=6U;assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])!=USBD_OK);
 allow_control_error=0U;
 ControlNormal();
}

#include "usb_cdc_retire.h"
UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device)
{ assert(device==&hUsbDeviceFS); return USB_CDC_OK; }
UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device,uint8_t address)
{ return USBD_LL_CloseEP(device,address)==USBD_OK ? USB_CDC_OK : USB_CDC_FAULT; }
#include "pc_usb_control.h"
#include "usbd_ioreq.h"

static USBD_StatusTypeDef Request(uint8_t bm,uint8_t req,uint16_t value,uint16_t length)
{
 uint8_t bytes[8]={bm,req,(uint8_t)value,(uint8_t)(value>>8),0U,0U,(uint8_t)length,(uint8_t)(length>>8)};
 return USBD_LL_SetupStage(&hUsbDeviceFS,bytes);
}
static void FailureCheck(void)
{
 assert(hUsbDeviceFS.ep0_state==USBD_EP0_STALL);
 USBD_CDC_HandleTypeDef *cdc=(USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;
 assert(cdc!=NULL && cdc->CmdOpCode==0xFFU && cdc->CmdLength==0U);
 unsigned before=ep0_ll_calls;
 assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,NULL)==USBD_OK);
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,NULL)==USBD_OK);
 assert(ep0_ll_calls==before && hUsbDeviceFS.ep0_state==USBD_EP0_STALL);
 assert(Request(0xA1U,CDC_GET_LINE_CODING,0U,7U)==USBD_OK);
 ControlInDone();
}
static int ControlFault(const char *scenario)
{
 allow_control_error=1U;
 if(!strcmp(scenario,"null_owner"))
 {
  unsigned before=ep0_ll_calls;
  assert(PcUsbControl_Dispatch(NULL)==USBD_FAIL);
  assert(ep0_ll_calls==before);return 1;
 }
 if(!strcmp(scenario,"foreign_owner"))
 {
  USBD_HandleTypeDef foreign=hUsbDeviceFS,original=foreign;
  unsigned before=ep0_ll_calls;
  assert(PcUsbControl_Dispatch(&foreign)==USBD_FAIL);
  assert(ep0_ll_calls==before && !memcmp(&foreign,&original,sizeof(foreign)));return 1;
 }
 if(!strcmp(scenario,"get_initial_failure"))
 {
  fail_ep0_tx_once=1U;
  assert(Request(0xA1U,CDC_GET_LINE_CODING,0U,7U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"set_initial_failure"))
 {
  fail_ep0_rx_once=1U;
  assert(Request(0x21U,CDC_SET_LINE_CODING,0U,7U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"status_tx_failure"))
 {
  fail_ep0_tx_once=1U;
  assert(Request(0x21U,CDC_SET_CONTROL_LINE_STATE,3U,0U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"status_rx_failure"))
 {
  assert(Request(0xA1U,CDC_GET_LINE_CODING,0U,7U)==USBD_OK);
  fail_ep0_rx_once=1U;
  assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,tx_ptr[0])==USBD_FAIL);
 }
 else if(!strcmp(scenario,"descriptor_continuation_failure"))
 {
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,0x0200U,255U)==USBD_OK);
  assert(tx_size[0]>64U);
  fail_ep0_tx_once=1U;
  assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,tx_ptr[0]+64U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"descriptor_initial_failure"))
 {
  fail_ep0_tx_once=1U;
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,0x0100U,18U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"descriptor_premature_rx_failure"))
 {
  assert(Request(0x80U,USB_REQ_GET_DESCRIPTOR,0x0200U,255U)==USBD_OK);
  assert(tx_size[0]>64U);
  fail_ep0_rx_once=1U;
  assert(USBD_LL_DataInStage(&hUsbDeviceFS,0U,tx_ptr[0]+64U)==USBD_FAIL);
 }
 else if(!strcmp(scenario,"receive_continuation_helper_failure"))
 {
  uint8_t data[7]={0};
  fail_ep0_rx_once=1U;
  assert(USBD_CtlContinueRx(&hUsbDeviceFS,data,sizeof(data))==USBD_FAIL);
  return 1; /* Direct helper contract; current seven-byte SET has no multi-packet OUT path. */
 }
 else {return 0;}
 FailureCheck();return 1;
}

int main(int argc,char **argv)
{
 assert(argc==2);
 assert(USBD_Init(&hUsbDeviceFS,&FS_Desc,0U)==USBD_OK);
 assert(USBD_RegisterClass(&hUsbDeviceFS,&USBD_CDC)==USBD_OK);
 assert(USBD_CDC_RegisterInterface(&hUsbDeviceFS,&USBD_Interface_fops_FS)==USBD_OK);
 assert(USBD_Start(&hUsbDeviceFS)==USBD_OK);EnumConfigure();
 if(strcmp(argv[1],"normal")==0){ControlNormal();return 0;}
 if(strcmp(argv[1],"boundaries")==0){ControlBoundaries();return 0;}
 if(ControlFault(argv[1])){return 0;}
 return 2;
}
