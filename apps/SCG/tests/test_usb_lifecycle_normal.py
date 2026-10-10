"""Ordinary valid first-batch lifecycle only, actual generated stack/adapter.

All setups are standard valid requests. Controller LL and Cortex intrinsics are
Host substitutes; no malformed inputs, alternate owners or security probing.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,re,shutil,subprocess
import pytest
import test_native_classic_cdc as nf
import test_native_ground_backend as nb
import test_usb_ground_backend as cb
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet

SHIM=r'''#ifndef __HOST_USB_SHIM_H
#define __HOST_USB_SHIM_H
#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#define __ALIGN_BEGIN
#define __ALIGN_END __attribute__((aligned(4)))
#define __PACKED __attribute__((packed))
#define __IO volatile
#define __STATIC_INLINE static inline
#define UNUSED(x) ((void)(x))
extern uint32_t host_uid[3];
#define UID_BASE ((uintptr_t)host_uid)
#define __DMB() ((void)0)
extern uint32_t host_mask;
static inline uint32_t __get_PRIMASK(void) { return host_mask; }
static inline void __disable_irq(void) { host_mask=1U; }
static inline void __set_PRIMASK(uint32_t v) { host_mask=v; }
typedef struct {struct {uint32_t maxpacket;} IN_ep[8];} PCD_HandleTypeDef;
static inline void HAL_Delay(uint32_t v) { (void)v; }
#endif
'''
HARNESS=r'''#include "usbd_core.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include "usbd_desc.h"
#include "pc_byte_stream.h"
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
static unsigned allow_control_error;
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
 assert(d==&hUsbDeviceFS);tx_ptr[ep&0x7FU]=p;tx_size[ep&0x7FU]=n;
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
 if(strcmp(argv[1],"tx-failure")==0)
 {
  session=PcByteStream_Session_Get();fail_tx_once=1U;
  assert(PcByteStream_WriteSession(fresh,7U,session)==PC_BYTE_STREAM_WRITE_ERROR);
  uint8_t *pending=tx_ptr[1];assert(pending!=NULL && memcmp(pending,fresh,7U)==0);
#ifdef HOST_C071
  PcC071Usb_Service();
#endif
  assert(PcByteStream_Session_Check(session)==0U);
  assert(PcByteStream_WriteSession(read,7U,PcByteStream_Session_Get())==PC_BYTE_STREAM_WRITE_BUSY);
  assert(memcmp(pending,fresh,7U)==0);
  assert(USBD_Stop(&hUsbDeviceFS)==USBD_OK && allocated==0U);
  EnumConfigure();assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);return 0;
 }
 if(strcmp(argv[1],"rx-rearm")==0)
 {
  session=PcByteStream_Session_Get();memcpy(rx_ptr[1],fresh,7U);rx_count[1]=7U;fail_prepare_once=1U;
  USBD_StatusTypeDef status=USBD_LL_DataOutStage(&hUsbDeviceFS,1U,rx_ptr[1]);
#ifdef HOST_C071
  assert(status==USBD_OK);PcC071Usb_Service();
  assert(PcByteStream_ReadSession(read,8U,&now)==7U && now==session && memcmp(read,fresh,7U)==0);
#else
  assert(status==USBD_FAIL && PcByteStream_Session_Check(session)==0U);
  assert(PcByteStream_ReadSession(read,8U,&now)==0U);
#endif
  assert(USBD_Stop(&hUsbDeviceFS)==USBD_OK);EnumConfigure();
  assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);return 0;
 }
 if(strcmp(argv[1],"init-open")==0 || strcmp(argv[1],"init-prepare")==0)
 {
  Setup(0U,USB_REQ_SET_CONFIGURATION,0U,0U,0U);InDone(0U);
  if(strcmp(argv[1],"init-open")==0){fail_open_once=1U;}else{fail_prepare_once=1U;}
  allow_control_error=1U;
  Setup(0U,USB_REQ_SET_CONFIGURATION,1U,0U,0U);
  assert(hUsbDeviceFS.dev_state!=USBD_STATE_CONFIGURED && allocated==0U);
  assert(hUsbDeviceFS.pClassData==NULL && tx_ptr[1]==NULL && rx_ptr[1]==NULL);
  allow_control_error=0U;
  EnumConfigure();assert(USBD_DeInit(&hUsbDeviceFS)==USBD_OK);return 0;
 }
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
'''

@pytest.fixture(params=['F103','C071'])
def first_batch(request,tmp_path,tmp_path_factory,builtin_catalog):
    if request.param=='F103':
        native=nf.native.__wrapped__(SimpleNamespace(param='f103-usb'),tmp_path)
        service,imported,args,_=nb.bound.__wrapped__(native,tmp_path_factory,builtin_catalog)
        plan=service.NativeClassicCdcGroundCandidate_Plan(imported.model,device_facts=args['device_facts'])
    else:
        service,imported,header,companion,_=cb.c071.__wrapped__(tmp_path_factory,builtin_catalog)
        plan=service.UsbGroundCandidate_Plan(imported.model,independent_irq_header=header,companion_root=companion).native_plan
    return request.param,plan

def test_normal_stack_lifecycle_and_buffer_sessions(first_batch,tmp_path):
    part,plan=first_batch
    files=plan.files;graph=json.loads(files['Generated/ground_source_graph.json'])
    make=files['Makefile'].decode().replace('\\\n',' ')
    assert re.search(r'^C_SOURCES := (.*)$',make,re.M)[1].split()==graph['sources']
    names=('usbd_core.c','usbd_ctlreq.c','usbd_ioreq.c','usbd_cdc.c','usbd_cdc_if.c','usbd_desc.c','pc_byte_stream.c')
    selected={name:next(p for p in graph['sources'] if p.endswith('/'+name)) for name in names}
    if part=='F103':selected['pc_usb_control.c']='Generated/Src/pc_usb_control.c'
    used={}
    for name,path in selected.items():
        (tmp_path/name).write_bytes(files[path]);used[path]=hashlib.sha256(files[path]).hexdigest()
    headers=('usbd_def.h','usbd_core.h','usbd_ctlreq.h','usbd_ioreq.h','usbd_cdc.h','usbd_cdc_if.h','usbd_desc.h','pc_byte_stream.h','gsp_min_protocol.h','pc_c071_usb.h','pc_c071_control.h','pc_usb_control.h','native_runtime.h','native_clock.h','platform_types.h')
    for name in headers:
        matches=[prefix+'/'+name for prefix in graph['include_dirs'] if prefix+'/'+name in files]
        if matches:
            path=matches[0];(tmp_path/name).write_bytes(files[path]);used[path]=hashlib.sha256(files[path]).hexdigest()
    conf=next(files[p+'/usbd_conf.h'] for p in graph['include_dirs'] if p+'/usbd_conf.h' in files).decode('utf8')
    conf=re.sub(r'#include "(?:main|stm32\w+)\.h"','#include "host_shim.h"',conf)
    (tmp_path/'usbd_conf.h').write_text(conf,encoding='utf8')
    (tmp_path/'host_shim.h').write_text(SHIM,encoding='utf8')
    (tmp_path/'main.h').write_text('#include "host_shim.h"\n',encoding='utf8')
    (tmp_path/'usb_device.h').write_text('#include "usbd_core.h"\nextern USBD_HandleTypeDef hUsbDeviceFS;\n',encoding='utf8')
    (tmp_path/'silverstar_assert.h').write_text('#include <assert.h>\n#define SILVERSTAR_ASSERT(c,m,r) assert(c)\n',encoding='utf8')
    desc_name=re.search(r'USBD_DescriptorsTypeDef\s+(\w+)\s*=',files[selected['usbd_desc.c']].decode())[1]
    (tmp_path/'normal.c').write_text(HARNESS.replace('FS_Desc',desc_name),encoding='utf8')
    compiler=shutil.which('gcc');assert compiler
    command=[compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror=implicit-function-declaration','-Werror=incompatible-pointer-types','-DUSBD_CLASS_BOS_ENABLED=0','-DUSBD_MAX_SUPPORTED_CLASS=1','-I'+str(tmp_path),*[str(tmp_path/n) for n in selected],str(tmp_path/'normal.c'),'-o',str(tmp_path/'normal.exe')]
    if part=='F103':command.insert(1,'-DHOST_F103=1')
    else:command.insert(1,'-DHOST_C071=1')
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    (tmp_path/'compile.log').write_text(result.stdout+result.stderr,encoding='utf8')
    assert result.returncode==0,result.stdout+result.stderr
    runs=[]
    for scenario in ('complete-zlp','unconfigure','reset','disconnect','stop','deinit','close-retry','deinit-close-retry','init-open','init-prepare','tx-failure','rx-rearm'):
        result=subprocess.run([str(tmp_path/'normal.exe'),scenario],capture_output=True,text=True,timeout=15)
        runs.append({'scenario':scenario,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    (tmp_path/'lifecycle-receipt.json').write_text(json.dumps({'part':part,'model_sha256':plan.model_sha256,'compiled_generated_sources_sha256':used,'command':command,'compile_exit':0,'runs':runs,'controller':'Host LL mock; native HAL/PMA/IRQ hardware is not executed'},indent=2),encoding='utf8')
    assert all(r['exit']==0 for r in runs),runs
