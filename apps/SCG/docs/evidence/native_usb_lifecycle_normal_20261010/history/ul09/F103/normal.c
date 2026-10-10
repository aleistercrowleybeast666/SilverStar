#include "usbd_core.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include "usbd_desc.h"
#include "pc_byte_stream.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
USBD_HandleTypeDef hUsbDeviceFS;
uint32_t host_mask;
static PCD_HandleTypeDef pcd;
static uint8_t *rx_ptr[8],*tx_ptr[8];
static uint32_t rx_count[8],tx_size[8];
static unsigned closes,allocated,frees;
static unsigned fail_close_once;
static uint32_t class_storage[(sizeof(USBD_CDC_HandleTypeDef)/4U)+1U];
void *USBD_static_malloc(uint32_t size)
{ assert(size==sizeof(USBD_CDC_HandleTypeDef));assert(allocated==0U);allocated=1U;return class_storage; }
void USBD_static_free(void *p)
{ assert(p==class_storage && allocated==1U);assert(rx_ptr[1]==NULL && tx_ptr[1]==NULL);allocated=0U;frees++; }
uint8_t NativeRuntime_ReadyGet(void) { return 1U; }
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
{ assert(d==&hUsbDeviceFS);(void)type;if((ep&0x80U)!=0U){pcd.IN_ep[ep&0x7FU].maxpacket=size;}return USBD_OK; }
USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *d,uint8_t ep)
{ assert(d==&hUsbDeviceFS);if(ep==0x81U && fail_close_once!=0U){fail_close_once=0U;return USBD_FAIL;}if((ep&0x80U)!=0U){tx_ptr[ep&0x7FU]=NULL;}else{rx_ptr[ep]=NULL;}closes++;return USBD_OK; }
USBD_StatusTypeDef USBD_LL_FlushEP(USBD_HandleTypeDef *d,uint8_t ep) { (void)d;(void)ep;return USBD_OK; }
USBD_StatusTypeDef USBD_LL_StallEP(USBD_HandleTypeDef *d,uint8_t ep)
{ /* ST F1 normally stalls OUT after its completed status phase. */
  assert(d==&hUsbDeviceFS && (ep==0x80U || (ep==0U && d->ep0_state==USBD_EP0_IDLE)));return USBD_OK; }
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
{ assert(d==&hUsbDeviceFS);tx_ptr[ep&0x7FU]=p;tx_size[ep&0x7FU]=n;return USBD_OK; }
USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *d,uint8_t ep,uint8_t *p,HostTransferLength n)
{ assert(d==&hUsbDeviceFS);rx_ptr[ep&0x7FU]=p;(void)n;return USBD_OK; }
uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *d,uint8_t ep)
{ assert(d==&hUsbDeviceFS);return rx_count[ep&0x7FU]; }
void USBD_LL_Delay(uint32_t n) { (void)n; }
static void Setup(uint8_t bm,uint8_t req,uint16_t value,uint16_t index,uint16_t length)
{
 uint8_t bytes[8]={bm,req,(uint8_t)value,(uint8_t)(value>>8),(uint8_t)index,(uint8_t)(index>>8),(uint8_t)length,(uint8_t)(length>>8)};
 assert(USBD_LL_SetupStage(&hUsbDeviceFS,bytes)==USBD_OK);
}
static void InDone(uint8_t ep)
{ assert(USBD_LL_DataInStage(&hUsbDeviceFS,ep,tx_ptr[ep])==USBD_OK); }
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
 assert(tx_size[0]==9U && tx_ptr[0][1]==USB_DESC_TYPE_CONFIGURATION);InDone(0U);
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,0U,rx_ptr[0])==USBD_OK);
 Setup(0x00U,USB_REQ_SET_CONFIGURATION,1U,0U,0U);InDone(0U);
 assert(hUsbDeviceFS.dev_state==USBD_STATE_CONFIGURED && allocated==1U);
 assert(rx_ptr[1]!=NULL && hUsbDeviceFS.pClassData!=NULL);
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
static uint32_t PendingData(void)
{
 uint8_t input[64],output[64],read[64];uint32_t session;
 for(unsigned i=0;i<64U;i++){input[i]=(uint8_t)i;output[i]=(uint8_t)(i+1U);}
 memcpy(rx_ptr[1],input,64U);rx_count[1]=64U;
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,1U,rx_ptr[1])==USBD_OK);
 assert(PcByteStream_ReadSession(read,64U,&session)==64U && memcmp(read,input,64U)==0);
 assert(PcByteStream_WriteSession(output,64U,session)==PC_BYTE_STREAM_WRITE_OK);
 assert(tx_ptr[1]!=output && tx_size[1]==64U && memcmp(tx_ptr[1],output,64U)==0);
 memset(output,0,64U);assert(tx_ptr[1][0]==1U && tx_ptr[1][63]==64U);
 assert(PcByteStream_WriteSession(input,64U,session)==PC_BYTE_STREAM_WRITE_BUSY);
 assert(tx_ptr[1][0]==1U && tx_ptr[1][63]==64U);
 return session;
}
int main(int argc,char **argv)
{
 uint8_t read[8],fresh[7]={1U,2U,3U,4U,5U,6U,7U};uint32_t session,now;unsigned oldfree;
 assert(argc==2);assert(PcByteStream_Init()==PC_BYTE_STREAM_INIT_OK);
 assert(USBD_Init(&hUsbDeviceFS,&FS_Desc,0U)==USBD_OK);
 assert(USBD_RegisterClass(&hUsbDeviceFS,&USBD_CDC)==USBD_OK);
 assert(USBD_CDC_RegisterInterface(&hUsbDeviceFS,&USBD_Interface_fops_FS)==USBD_OK);
 assert(USBD_Start(&hUsbDeviceFS)==USBD_OK);EnumConfigure();ControlNormal();
 session=PendingData();oldfree=frees;
 if(strcmp(argv[1],"deinit-close-retry")==0)
 {
  void *storage=hUsbDeviceFS.pClassData;fail_close_once=1U;
  assert(USBD_DeInit(&hUsbDeviceFS)!=USBD_OK);
  assert(allocated==1U && frees==oldfree && hUsbDeviceFS.pClassData==storage);
  assert(USBD_Init(&hUsbDeviceFS,&FS_Desc,0U)!=USBD_OK);
  assert(hUsbDeviceFS.pClassData==storage);
  assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK && allocated==0U && frees==oldfree+1U);
  return 0;
 }
 if(strcmp(argv[1],"close-retry")==0)
 {
  uint8_t *pending=tx_ptr[1];fail_close_once=1U;
  assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);
  assert(allocated==1U && frees==oldfree && tx_ptr[1]==pending);
  assert(pending[0]==1U && pending[63]==64U);
  assert(PcByteStream_WriteSession(fresh,7U,session)==PC_BYTE_STREAM_WRITE_BUSY);
  assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)==USBD_OK);
  assert(allocated==0U && frees==oldfree+1U);
  EnumConfigure();now=PcByteStream_Session_Get();
  assert(PcByteStream_WriteSession(fresh,7U,now)==PC_BYTE_STREAM_WRITE_OK);InDone(1U);
  assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);return 0;
 }
 if(strcmp(argv[1],"complete-zlp")==0)
 {
  InDone(1U);assert(tx_size[1]==0U);
  assert(PcByteStream_WriteSession(fresh,7U,session)==PC_BYTE_STREAM_WRITE_BUSY);
  InDone(1U);assert(PcByteStream_WriteSession(fresh,7U,session)==PC_BYTE_STREAM_WRITE_OK);
  InDone(1U);assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);return 0;
 }
 /* Queue normal unread RX and arm a valid SET before cancellation. */
 memcpy(rx_ptr[1],fresh,7U);rx_count[1]=7U;
 assert(USBD_LL_DataOutStage(&hUsbDeviceFS,1U,rx_ptr[1])==USBD_OK);
 Setup(0x21U,CDC_SET_LINE_CODING,0U,0U,7U);
 if(strcmp(argv[1],"unconfigure")==0){Setup(0U,USB_REQ_SET_CONFIGURATION,0U,0U,0U);InDone(0U);}
 else if(strcmp(argv[1],"reset")==0){assert(USBD_LL_Reset(&hUsbDeviceFS)==USBD_OK);}
 else if(strcmp(argv[1],"disconnect")==0){assert(USBD_LL_DevDisconnected(&hUsbDeviceFS)==USBD_OK);}
 else if(strcmp(argv[1],"stop")==0){assert(USBD_Stop(&hUsbDeviceFS)==USBD_OK);}
 else {assert(strcmp(argv[1],"deinit")==0);assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);}
 assert(allocated==0U && frees==oldfree+1U && hUsbDeviceFS.pClassData==NULL);
 assert(rx_ptr[1]==NULL && tx_ptr[1]==NULL && closes>=3U);
 assert(PcByteStream_Session_Check(session)==0U && PcByteStream_ReadSession(read,8U,&now)==0U);
 assert(PcByteStream_WriteSession(fresh,7U,session)==PC_BYTE_STREAM_WRITE_BUSY);
 if(strcmp(argv[1],"deinit")==0)
 {
  assert(USBD_Init(&hUsbDeviceFS,&FS_Desc,0U)==USBD_OK);
  assert(USBD_RegisterClass(&hUsbDeviceFS,&USBD_CDC)==USBD_OK);
  assert(USBD_CDC_RegisterInterface(&hUsbDeviceFS,&USBD_Interface_fops_FS)==USBD_OK);
 }
 assert(USBD_Start(&hUsbDeviceFS)==USBD_OK);EnumConfigure();
 now=PcByteStream_Session_Get();assert(now!=session);
 assert(PcByteStream_WriteSession(fresh,7U,session)==PC_BYTE_STREAM_WRITE_BUSY);
 assert(PcByteStream_WriteSession(fresh,7U,now)==PC_BYTE_STREAM_WRITE_OK);InDone(1U);
 ControlNormal();assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);
 printf("normal lifecycle %s passed\n",argv[1]);return 0;
}
