
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "ground_bridge.h"
#include "ground_radio.h"
#include "gsp_min_protocol.h"
#include "pc_byte_stream.h"
#include "usbd_cdc_if.h"
uint32_t usb_test_mask;
USBD_HandleTypeDef hUsbDeviceFS;
static USBD_CDC_HandleTypeDef cls;
static uint8_t frame[70];
static uint16_t frame_len;
static int inject, forwarded;
static int inject_read_reset;
static int delivery_reset;
void usb_guard_before_mask_hook(void) {
 if(delivery_reset==2) {delivery_reset=0; hUsbDeviceFS.dev_state=0; PcByteStream_OnUsbReset();}
}
void usb_irq_after_restore_hook(void) {
 if(delivery_reset==1) {delivery_reset=2;}
 if(inject_read_reset) {inject_read_reset=0;hUsbDeviceFS.dev_state=0;PcByteStream_OnUsbReset();}
}
uint8_t CDC_Transmit_FS(uint8_t *p,uint16_t n) {(void)p;(void)n;return USBD_OK;}
uint8_t GroundRadio_MetricsSupportedGet(void){return 1;}
GroundRadioResult GroundRadio_Init(void){return GROUND_RADIO_OK;}
void GroundRadio_Process(void){
 if(inject){inject=0; PcByteStream_OnUsbReset();
  /* New configured session delivers only the tail, without a frame header. */
  PcByteStream_OnUsbReceive(frame+5,(uint16_t)(frame_len-5));}
}
GroundRadioResult GroundRadio_TxEnqueue(const uint8_t *p,uint8_t n){
 assert(usb_test_mask == 1U); assert(n==2 && p[0]==0x42 && p[1]==0x43);forwarded++;return GROUND_RADIO_OK;}
GroundRadioResult GroundRadio_RxDequeue(uint8_t*p,uint8_t*n,int8_t*r,int8_t*s){
 (void)p;(void)n;(void)r;(void)s;return GROUND_RADIO_EMPTY;}
void GroundRadio_StatsGet(GroundRadioStats*s){memset(s,0,sizeof(*s));}
int main(int argc,char **argv){
 uint8_t payload[]={2,0x42,0x43};(void)argv;
 hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;hUsbDeviceFS.pClassData=&cls;
 assert(GroundBridge_Init()==GROUND_BRIDGE_OK);
 if(PcByteStream_ResetPending_Get())GroundBridge_PcReset();
 frame_len=GspMin_BuildFrame(GSP_TYPE_AIR_TX,payload,3,frame,sizeof(frame));
 if(argc>1 && strcmp(argv[1],"normal")==0) { PcByteStream_OnUsbReceive(frame,frame_len); assert(GroundBridge_Process(1)==GROUND_BRIDGE_OK); assert(forwarded==1); return 0; }
 if(argc>1 && (strcmp(argv[1],"read-reset")==0 || strcmp(argv[1],"delivery-reset")==0)){
  PcByteStream_OnUsbReceive(frame,frame_len);
  if(PcByteStream_ResetPending_Get())GroundBridge_PcReset();
  /* An actual reset IRQ immediately after Read copies the bytes and unmasks IRQs. */
  if(strcmp(argv[1],"delivery-reset")==0) {delivery_reset=1;} else {inject_read_reset=1;}
  assert(GroundBridge_Process(2)==GROUND_BRIDGE_OK);
  printf("forwarded_after_reset=%d expected=0 dev_state=%u reset_pending=%u\n",forwarded,hUsbDeviceFS.dev_state,PcByteStream_ResetPending_Get());
  return forwarded?25:0;
 }
 PcByteStream_OnUsbReceive(frame,5);
 assert(GroundBridge_Process(1)==GROUND_BRIDGE_OK);
 assert(forwarded==0);
 if(argc>1){PcByteStream_OnUsbReset();PcByteStream_OnUsbReceive(frame+5,(uint16_t)(frame_len-5));}
 /* Exact generated main-loop ordering. */
 if(PcByteStream_ResetPending_Get())GroundBridge_PcReset();
 if(argc==1)inject=1;
 assert(GroundBridge_Process(2)==GROUND_BRIDGE_OK);
 printf("forwarded_cross_session_frames=%d expected=0 reset_pending=%u\n",forwarded,PcByteStream_ResetPending_Get());
 return forwarded?24:0;
}
