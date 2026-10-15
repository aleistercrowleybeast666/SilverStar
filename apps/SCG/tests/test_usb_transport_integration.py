"""Execute generated classic callback chains with injected HAL outcomes.

The functions are extracted unchanged from the delivered sources. Registers and
HAL are host models; this does not establish physical endpoint cancellation.
"""
from pathlib import Path
import os
import subprocess
import pytest

from silverstar_fccg.app.usb_transport import _Project_Read, UsbTransport_Plan, UsbTransport_Export
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.generator.usb_cdc_integration import UsbCdcIntegration_Render, UsbIntegrationProfile_Get
from silverstar_fccg.generator.usb_cdc_transport import UsbCdcTransport_Render


def _Function_Get(source, name):
    start, _opening, end = NativeC_FunctionSpanGet(source, name)
    return source[start:end]


@pytest.fixture(scope="module", params=["f103", "f407"])
def integrated(request):
    reference = os.environ.get("SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT")
    if not reference:
        pytest.skip("complete native CubeMX references not configured")
    root = Path(reference) / ("cube-" + request.param + "-usb")
    native = _Project_Read(root)
    plan = UsbTransport_Plan(root)
    assert not plan.reasons, plan.reasons
    return request.param, root, native, plan, UsbCdcIntegration_Render(native, plan.owners)


def test_edited_hook_never_receives_automatic_patches(integrated):
    _part, _root, native, plan, _rendered = integrated
    changed = dict(native)
    owner = plan.owners["usbd_cdc_if.c"]
    source = changed[owner].decode('utf-8-sig')
    _start, opening, _end = NativeC_FunctionSpanGet(source, 'CDC_Receive_FS')
    changed[owner] = (source[:opening+1] + '\n/* user owned callback logic */\n' + source[opening+1:]).encode()
    with pytest.raises(ValueError, match="UNREVIEWED_LIFECYCLE_SOURCE"):
        UsbIntegrationProfile_Get(changed)


def test_component_profile_preserves_unrelated_project_and_clock_text(integrated):
    _part, _root, native, plan, _rendered = integrated
    changed = dict(native)
    owner = plan.owners['main.c']
    changed[owner] = b'/* independent user project note */\n' + changed[owner]
    profile = UsbIntegrationProfile_Get(changed)
    assert profile['binding'] == 'REVIEWED_COMPONENTS_AND_HOOK_REGIONS'
    rendered = UsbCdcIntegration_Render(changed, plan.owners)
    assert rendered['Native/' + owner].startswith(b'/* independent user project note */')
    conf = plan.owners['usbd_conf.c']
    assert _Function_Get(rendered['Native/' + conf].decode(), 'USBD_LL_Init') == _Function_Get(
        native[conf].decode('utf-8-sig'), 'USBD_LL_Init')
    assert _Function_Get(rendered['Native/' + owner].decode(), 'SystemClock_Config') == _Function_Get(
        native[owner].decode('utf-8-sig'), 'SystemClock_Config')


def test_integrated_export_preserves_every_inspected_input(integrated, tmp_path):
    _part, root, native, _plan, _rendered = integrated
    UsbTransport_Export(root, tmp_path / "kit", integrate=True)
    assert _Project_Read(root) == native
    assert (tmp_path / "kit/lifecycle-integration.json").is_file()


HEADER = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "usb_cdc_transport.h"
#include "silverstar_assert.h"
#define USBD_OK 0U
#define USBD_BUSY 1U
#define USBD_FAIL 2U
#define USBD_SPEED_FULL 1U
#define USBD_STATE_DEFAULT 1U
#define USBD_STATE_CONFIGURED 3U
#define USBD_STATE_SUSPENDED 4U
#define USBD_EP0_IDLE 0U
#define USBD_EP_TYPE_CTRL 0U
#define USBD_EP_TYPE_BULK 2U
#define USBD_EP_TYPE_INTR 3U
#define USB_MAX_EP0_SIZE 64U
#define CDC_IN_EP 0x81U
#define CDC_OUT_EP 1U
#define CDC_CMD_EP 0x82U
#define CDC_CMD_PACKET_SIZE 8U
#define CDC_DATA_FS_MAX_PACKET_SIZE 64U
#define CDC_DATA_FS_IN_PACKET_SIZE 64U
#define CDC_DATA_FS_OUT_PACKET_SIZE 64U
#define CDC_FS_BINTERVAL 16U
#define HAL_OK 0U
typedef uint8_t USBD_StatusTypeDef;
typedef struct USBD_Handle USBD_HandleTypeDef;
typedef struct { uint32_t total_length,maxpacket; uint8_t is_used,bInterval; } Endpoint;
typedef struct { uint8_t (*Init)(USBD_HandleTypeDef *,uint8_t); uint8_t (*DeInit)(USBD_HandleTypeDef *,uint8_t); } Class;
struct USBD_Handle {
 void *pData,*pClassData; @STORAGE@
 uint8_t dev_state,dev_old_state,dev_speed,dev_config,dev_remote_wakeup,dev_test_mode,ep0_state,classId;
 Endpoint ep_in[16],ep_out[16];
};
typedef struct { uint32_t TxState,RxState,TxLength,RxLength; uint8_t *TxBuffer,*RxBuffer; } USBD_CDC_HandleTypeDef;
typedef struct { int8_t (*Init)(void);int8_t (*DeInit)(void);int8_t (*Receive)(uint8_t *,uint32_t *);int8_t (*TransmitCplt)(uint8_t *,uint32_t *,uint8_t); } USBD_CDC_ItfTypeDef;
typedef struct { uint8_t *xfer_buff; uint32_t xfer_len,xfer_count,maxpacket; uint16_t pmaadress;uint8_t doublebuffer; } PCD_EPTypeDef;
typedef struct { uint32_t GINTSTS,GRXFSIZ,DIEPTXF0_HNPTXFSIZ,DIEPTXF[4],BTABLE; } GlobalRegs;
static GlobalRegs global_regs;
typedef struct { void *pData; GlobalRegs *Instance; struct { uint32_t dma_enable; } Init; PCD_EPTypeDef IN_ep[16],OUT_ep[16]; } PCD_HandleTypeDef;
#define USB (&global_regs)
#define USB_OTG_FS (&global_regs)
#define USB_OTG_FS_TOTAL_FIFO_SIZE 1280U
static USBD_HandleTypeDef hUsbDeviceFS;
static PCD_HandleTypeDef @PCD@;
static USBD_CDC_HandleTypeDef storage;
static uint8_t UserRxBufferFS[64],UserTxBufferFS[256];
static unsigned prepared,transmitted,closed,aborted,cleared,flushed,mask;
static uint8_t fail_open,fail_prepare,fail_tx,fail_abort,fail_close,fail_flush,fail_readback;
static uint8_t stage_result;
static unsigned staged;
static uint32_t rx_length=64U;
static struct { uint32_t DIEPINT,DIEPCTL; } in_regs[16];
static struct { uint32_t DOEPINT,DOEPCTL; } out_regs[16];
static struct { uint32_t DIEPEMPMSK,DAINTMSK; } device_regs;
static uint16_t ep_regs[16];
#define USB_OTG_DIEPCTL_EPENA 1U
#define USB_OTG_DIEPCTL_USBAEP 2U
#define USB_OTG_DOEPCTL_EPENA 1U
#define USB_OTG_DOEPCTL_USBAEP 2U
#define USB_OTG_GINTSTS_RXFLVL 16U
#define USB_EPTX_STAT 0x30U
#define USB_EPRX_STAT 0x3000U
#define USB_EP_CTR_TX 0x80U
#define USB_EP_CTR_RX 0x8000U
#define PCD_GET_ENDPOINT(p,n) ((void)(p),ep_regs[n])
#define USBx_DEVICE ((void)USBx_BASE, &device_regs)
#define USBx_INEP(n) ((void)USBx_BASE, &in_regs[n])
#define USBx_OUTEP(n) ((void)USBx_BASE, &out_regs[n])
#define PCD_CLEAR_TX_EP_CTR(p,n) ((void)(p),(void)(n),cleared++)
#define PCD_CLEAR_RX_EP_CTR(p,n) ((void)(p),(void)(n),cleared++)
uint32_t UsbCdcPort_Lock(void) { unsigned old=mask;mask=1U;return old; }
void UsbCdcPort_Unlock(uint32_t old) { mask=old; }
void SilverStarAssert_Check(uint8_t ok,SilverStarAssertModuleId m,const char *f,uint32_t l,SilverStarAssertReasonId r)
{ (void)m;(void)f;(void)l;(void)r;assert(ok); }
static void *TestAlloc(size_t size) { assert(size==sizeof(storage));return &storage; }
static void TestFree(void *data) { assert(data==&storage); }
#define USBD_malloc TestAlloc
#define USBD_free TestFree
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *,uint8_t);
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *,uint8_t *,@LENGTH@);
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *,uint8_t *);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *);
uint8_t CDC_Transmit_FS(uint8_t *,uint16_t);
static uint8_t HAL_PCD_EP_Abort(PCD_HandleTypeDef *p,uint8_t address)
{ assert(p==&@PCD@ && mask==1U);(void)address;aborted++;return fail_abort; }
static uint8_t HAL_PCD_EP_Close(PCD_HandleTypeDef *p,uint8_t address)
{ assert(p==&@PCD@ && mask==1U);unsigned n=address&0x7FU;closed++;
  if(!fail_readback) { in_regs[n].DIEPCTL=0U;out_regs[n].DOEPCTL=0U;ep_regs[n]=0U; }
  return fail_close; }
static uint8_t USB_FlushTxFifo(void *p,uint8_t number)
{ (void)p;(void)number;flushed++;return fail_flush; }
static USBD_StatusTypeDef USBD_LL_OpenEP(USBD_HandleTypeDef *p,uint8_t ep,uint8_t type,uint16_t size)
{ assert(p==&hUsbDeviceFS);(void)ep;(void)type;(void)size;return fail_open; }
static USBD_StatusTypeDef USBD_LL_PrepareReceive(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&hUsbDeviceFS && ep==1U && data==UserRxBufferFS && size==64U);prepared++;
  @PCD@.OUT_ep[1].xfer_buff=data;@PCD@.OUT_ep[1].xfer_len=size;@PCD@.OUT_ep[1].xfer_count=0U;return fail_prepare; }
static USBD_StatusTypeDef USBD_LL_Transmit(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data,uint16_t size)
{ assert(p==&hUsbDeviceFS && (ep==1U || ep==0x81U) && size<=256U);@PCD@.IN_ep[1].xfer_buff=data;transmitted++;return fail_tx; }
static uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *p,uint8_t ep)
{ assert(p==&hUsbDeviceFS && ep==1U);return rx_length; }
'''

HARNESS = r'''
int main(int argc,char **argv)
{
 assert(argc==2);const char *scenario=argv[1];
 Class cls={USBD_CDC_Init,USBD_CDC_DeInit};
 USBD_CDC_ItfTypeDef itf={CDC_Init_FS,CDC_DeInit_FS,CDC_Receive_FS,NULL};
 hUsbDeviceFS.@CLASS@=&cls;hUsbDeviceFS.@USER@=&itf;
 hUsbDeviceFS.pData=&@PCD@;hUsbDeviceFS.dev_speed=USBD_SPEED_FULL;@PCD@.IN_ep[1].maxpacket=64U;
 @PCD@.Instance=&global_regs;@PCD@.pData=&hUsbDeviceFS;@PCD@.OUT_ep[1].xfer_buff=UserRxBufferFS;
 device_regs.DIEPEMPMSK=2U;
 @PCD@.OUT_ep[0].pmaadress=0x18U;@PCD@.IN_ep[0].pmaadress=0x58U;
 @PCD@.IN_ep[1].pmaadress=0xC0U;@PCD@.OUT_ep[1].pmaadress=0x110U;@PCD@.IN_ep[2].pmaadress=0x100U;
 global_regs.GRXFSIZ=128U;global_regs.DIEPTXF0_HNPTXFSIZ=(64U<<16)|128U;
 global_regs.DIEPTXF[0]=(64U<<16)|192U;global_regs.DIEPTXF[1]=(16U<<16)|256U;
 if(strcmp(scenario,"init-arm-fail")==0) { fail_prepare=1U; }
 if(strcmp(scenario,"init-open-fail")==0) { fail_open=1U; }
 uint8_t configured=USBD_SetClassConfig(&hUsbDeviceFS,1U);
 uint8_t out[512],data[256];memset(data,0x39,sizeof(data));memset(UserRxBufferFS,0x72,sizeof(UserRxBufferFS));
 uint32_t session;uint16_t length;
 if(fail_prepare || fail_open)
 { assert(configured!=USBD_OK);assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 assert(configured==USBD_OK && prepared==1U);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
 session=UsbCdc_SessionGet();
 if(strcmp(scenario,"bad-class-contract")==0)
 { cls.DeInit=NULL;assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);
   assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(strncmp(scenario,"callback-",9)==0)
 { if(strcmp(scenario,"callback-index")==0) { HAL_PCD_DataOutStageCallback(&@PCD@,255U);assert(staged==0U); }
   if(strcmp(scenario,"callback-owner")==0) { PCD_HandleTypeDef wrong={0};HAL_PCD_DataInStageCallback(&wrong,1U);assert(staged==0U); }
   if(strcmp(scenario,"callback-error")==0) { stage_result=USBD_FAIL;HAL_PCD_DataOutStageCallback(&@PCD@,1U);assert(staged==1U); }
   assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(strcmp(scenario,"rx-length")==0)
 { uint32_t huge=65536U;assert(CDC_Receive_FS(UserRxBufferFS,&huge)!=USBD_OK);assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OFFLINE);return 0; }
 if(strcmp(scenario,"rearm-failure")==0)
 { assert(USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK);fail_prepare=USBD_FAIL;
   assert(UsbCdc_Service()==USB_CDC_FAULT);assert(UsbCdc_Configure()==USB_CDC_BUSY);return 0; }
 for(unsigned i=0U;i<8U;i++)
 { assert(USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK);assert(UsbCdc_Service()==USB_CDC_OK); }
 assert(prepared==8U);assert(UsbCdc_Read(out,sizeof(out),&length,&session)==USB_CDC_OK && length==512U);
 for(unsigned i=0U;i<512U;i++) { assert(out[i]==0x72U); }
 assert(UsbCdc_Service()==USB_CDC_OK && prepared==9U);
 assert(UsbCdc_Write(data,256U,session)==USB_CDC_OK);
 if(strcmp(scenario,"tx-fail")==0) { fail_tx=USBD_FAIL; }
 UsbCdcResult submitted=UsbCdc_Service();
 if(fail_tx)
 { assert(submitted==USB_CDC_FAULT);assert(UsbCdc_Configure()==USB_CDC_BUSY);assert(@PCD@.IN_ep[1].xfer_buff[0]==0x39U);return 0; }
 assert(submitted==USB_CDC_OK && storage.TxState==1U);
 uint8_t *owned=@PCD@.IN_ep[1].xfer_buff;data[0]=0x18U;assert(owned[0]==0x39U);
 if(strcmp(scenario,"zlp-failure")==0)
 { fail_tx=USBD_FAIL;assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)!=USBD_OK);
   assert(storage.TxState==1U && UsbCdc_Configure()==USB_CDC_BUSY && owned[0]==0x39U);return 0; }
 if(strcmp(scenario,"abort-fail")==0) { fail_abort=1U; }
 if(strcmp(scenario,"close-fail")==0) { fail_close=1U; }
 if(strcmp(scenario,"flush-fail")==0) { fail_flush=1U; }
 if(strcmp(scenario,"retire-in-active")==0)
 { fail_readback=1U;in_regs[1].DIEPCTL=USB_OTG_DIEPCTL_EPENA;ep_regs[1]=USB_EPTX_STAT; }
 if(strcmp(scenario,"retire-out-active")==0)
 { fail_readback=1U;out_regs[1].DOEPCTL=USB_OTG_DOEPCTL_EPENA;ep_regs[1]=USB_EPRX_STAT; }
 if(strncmp(scenario,"retire-out-pending",18)==0) { global_regs.GINTSTS=USB_OTG_GINTSTS_RXFLVL; }
 if(fail_abort || fail_close || fail_flush || fail_readback || global_regs.GINTSTS)
 { assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);assert(hUsbDeviceFS.pClassData==&storage);
   assert(UsbCdc_Configure()==USB_CDC_BUSY && owned[0]==0x39U);assert(USBD_SetClassConfig(&hUsbDeviceFS,1U)!=USBD_OK);
   if(global_regs.GINTSTS) { assert(@PCD@.OUT_ep[1].xfer_buff==UserRxBufferFS); }
   if(strcmp(scenario,"retire-out-pending-retry")==0)
   { global_regs.GINTSTS=0U;assert(USBD_ClrClassConfig(&hUsbDeviceFS,1U)==USBD_OK);
     assert(USBD_SetClassConfig(&hUsbDeviceFS,1U)==USBD_OK);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
     assert(UsbCdc_Write(data,1U,session)==USB_CDC_OFFLINE);
     assert(USBD_CDC_DataOut(&hUsbDeviceFS,1U)==USBD_OK); }
   return 0; }
 if(strcmp(scenario,"suspend")==0)
 { assert(USBD_LL_Suspend(&hUsbDeviceFS)==USBD_OK);assert(USBD_LL_Resume(&hUsbDeviceFS)==USBD_OK);
   assert(UsbCdc_Write(data,1U,session)==USB_CDC_OFFLINE); }
 else
 { assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)==USBD_OK && storage.TxState==1U);assert(UsbCdc_Service()==USB_CDC_BUSY);
   assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)==USBD_OK && storage.TxState==0U);assert(UsbCdc_Service()==USB_CDC_OK); }
 if(strcmp(scenario,"disconnect")==0) { assert(USBD_LL_DevDisconnected(&hUsbDeviceFS)==USBD_OK); }
 else { assert(USBD_LL_Reset(&hUsbDeviceFS)==USBD_OK); }
 assert(hUsbDeviceFS.pClassData==NULL && @PCD@.IN_ep[1].xfer_buff==NULL && aborted==3U && closed==3U);
 assert(USBD_CDC_DataIn(&hUsbDeviceFS,1U)!=USBD_OK && USBD_CDC_DataOut(&hUsbDeviceFS,1U)!=USBD_OK);
 assert(USBD_SetClassConfig(&hUsbDeviceFS,1U)==USBD_OK);hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
 assert(UsbCdc_Write(data,1U,session)==USB_CDC_OFFLINE);session=UsbCdc_SessionGet();
 assert(UsbCdc_Write(data,1U,session)==USB_CDC_OK);return 0;
}
'''


@pytest.fixture(scope="module")
def host_program(integrated, tmp_path_factory):
    part, _root, _native, _plan, rendered = integrated
    indexed = part == "f407"
    path = tmp_path_factory.mktemp("usb-lifecycle-" + part)
    kit = UsbCdcTransport_Render(indexed=indexed)
    for name in ("usb_cdc_transport.h", "usb_cdc_port.h"):
        (path / name).write_bytes(kit['Inc/' + name])
    functions = []
    for suffix, names in (
        ('usbd_cdc.c', ('NativeCdc_Fault','NativeCdc_InitAbort','NativeCdc_Open','USBD_CDC_Init','USBD_CDC_DeInit',
            'USBD_CDC_DataIn','USBD_CDC_DataOut','USBD_CDC_TransmitPacket','USBD_CDC_ReceivePacket','USBD_CDC_SetTxBuffer','USBD_CDC_SetRxBuffer')),
        ('usbd_core.c', ('USBD_SetClassConfig','USBD_ClrClassConfig','USBD_LL_Reset','USBD_LL_DevDisconnected','USBD_LL_Suspend','USBD_LL_Resume')),
        ('usbd_cdc_if.c', ('CDC_Init_FS','CDC_DeInit_FS','CDC_Receive_FS','CDC_Transmit_FS')),
    ):
        source = next(body.decode() for name, body in rendered.items() if name.endswith('/' + suffix))
        functions.extend(_Function_Get(source, name) for name in names)
    retire_source = rendered['Src/usb_cdc_retire.c'].decode()
    retire = _Function_Get(retire_source, 'UsbCdcRetire_Endpoint')
    if 'UsbCdcRetire_HardwareFinish' in retire_source:
        retire = _Function_Get(retire_source, 'UsbCdcRetire_HardwareFinish') + '\n' + retire
    if 'UsbCdcRetire_ConfigurationCheck' in retire_source:
        retire = _Function_Get(retire_source, 'UsbCdcRetire_MemoryCheck') + '\n' + _Function_Get(
            retire_source, 'UsbCdcRetire_ConfigurationCheck') + '\n' + retire
    close_source = next(body.decode() for name, body in rendered.items() if name.endswith('/usbd_conf.c'))
    close = _Function_Get(close_source, 'USBD_LL_CloseEP')
    # Callback declarations have a fixed/registered preprocessor alternative;
    # the target compile separately proves the fixed branch is selected.
    callbacks = close_source.replace('#endif /* USE_HAL_PCD_REGISTER_CALLBACKS */', '')
    callback_functions = '''
USBD_StatusTypeDef USBD_LL_DataInStage(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data)
{ assert(p==&hUsbDeviceFS);(void)ep;(void)data;staged++;return stage_result; }
USBD_StatusTypeDef USBD_LL_DataOutStage(USBD_HandleTypeDef *p,uint8_t ep,uint8_t *data)
{ assert(p==&hUsbDeviceFS);(void)ep;(void)data;staged++;return stage_result; }
''' + '\n'.join(_Function_Get(callbacks, name) for name in (
        'HAL_PCD_DataInStageCallback', 'HAL_PCD_DataOutStageCallback'))
    port = kit['Src/usb_cdc_port.c'].decode()
    port = '\n'.join(_Function_Get(port, name) for name in ('UsbCdcPort_TxState','UsbCdcPort_Submit','UsbCdcPort_Rearm'))
    header = HEADER
    if not indexed:
        header = header.replace('static uint8_t USB_FlushTxFifo(void *p,uint8_t number)\n{ (void)p;(void)number;flushed++;return fail_flush; }', '')
        header = header.replace(',flushed,mask', ',mask')
    else:
        header = header.replace(',cleared,flushed', ',flushed')
    source = header + '\n' + kit['Src/usb_cdc_transport.c'].decode() + '\n' + retire + '\n' + close + '\n' + '\n'.join(functions) + '\n' + port + '\n' + callback_functions + '\n' + HARNESS
    for old, new in {'@STORAGE@': 'void *pClassDataCmsit[1],*pUserData[1];Class *pClass[1];' if indexed else 'void *pUserData;Class *pClass;',
        '@PCD@': 'hpcd_USB_OTG_FS' if indexed else 'hpcd_USB_FS', '@LENGTH@': 'uint32_t' if indexed else 'uint16_t',
        '@CLASS@': 'pClass[0]' if indexed else 'pClass', '@USER@': 'pUserData[0]' if indexed else 'pUserData'}.items():
        source = source.replace(old, new)
    (path / 'test.c').write_text(source, encoding='utf8')
    common = Path(__file__).resolve().parents[1] / 'plugins/builtin/silverstar_core_0_1_0/payload/Common/Inc'
    command = ['gcc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion',
        '-Wshadow','-fanalyzer','-I'+str(path),'-I'+str(common),str(path/'test.c'),'-o',str(path/'test.exe')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (path/'compile.log').write_text(result.stdout+result.stderr, encoding='utf8')
    assert result.returncode == 0, result.stdout+result.stderr
    return indexed, path


@pytest.mark.parametrize('scenario', ['normal','init-arm-fail','init-open-fail','rx-length','tx-fail',
    'abort-fail','close-fail','flush-fail','suspend','disconnect',
    'retire-in-active','retire-out-active','retire-out-pending','bad-class-contract',
    'callback-index','callback-owner','callback-error','rearm-failure','zlp-failure','retire-out-pending-retry'])
def test_generated_callbacks_and_transport_lifecycle(host_program, scenario):
    indexed, path = host_program
    if scenario == 'flush-fail' and not indexed:
        pytest.skip('PMA profile has no FIFO flush operation; its abort/close paths are tested separately')
    if scenario.startswith('retire-out-pending') and not indexed:
        pytest.skip('PMA has no global RX FIFO; endpoint disable and CTR checks are covered separately')
    result = subprocess.run([str(path/'test.exe'),scenario], capture_output=True, text=True, timeout=15)
    (path/(scenario+'.log')).write_text(result.stdout+result.stderr, encoding='utf8')
    assert result.returncode == 0, result.stdout+result.stderr


INIT_HEADER = r'''
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
static PCD_HandleTypeDef @PCD@;
static Regs regs;
#define USB (&regs)
#define USB_OTG_FS (&regs)
static unsigned calls,fail_call,fail_init,fail_deinit,bad_readback,link_down;
void UsbCdc_LinkDown(void) { link_down++; }
uint32_t UsbCdcPort_Lock(void) { return 0U; }
void UsbCdcPort_Unlock(uint32_t token) { assert(token==0U); }
/* Host-only terminal interception: CubeMX's actual Error_Handler never returns. */
void Error_Handler(void) { assert(fail_init);exit(0); }
uint8_t HAL_PCD_Init(PCD_HandleTypeDef *p) { assert(p==&@PCD@);return (uint8_t)fail_init; }
uint8_t HAL_PCD_DeInit(PCD_HandleTypeDef *p) { assert(p==&@PCD@);return (uint8_t)fail_deinit; }
@SETTERS@
'''


@pytest.fixture(scope='module')
def native_init_program(integrated, tmp_path_factory):
    part, _root, _native, _plan, rendered = integrated
    indexed = part == 'f407'
    path = tmp_path_factory.mktemp('usb-native-init-' + part)
    (path / 'usb_cdc_transport.h').write_bytes(UsbCdcTransport_Render()['Inc/usb_cdc_transport.h'])
    source = next(body.decode() for name, body in rendered.items() if name.endswith('/usbd_conf.c'))
    body = _Function_Get(source, 'USBD_LL_Init')
    if 'UsbCdcNative_MemoryInit' in source:
        body = _Function_Get(source, 'UsbCdcNative_MemoryInit') + '\n' + body
    retire_source = rendered['Src/usb_cdc_retire.c'].decode()
    body += '\n' + _Function_Get(retire_source, 'UsbCdcRetire_MemoryCheck') + '\n' + _Function_Get(
        retire_source, 'UsbCdcRetire_ConfigurationCheck')
    if indexed:
        setters = r'''
uint8_t HAL_PCDEx_SetRxFiFo(PCD_HandleTypeDef *p,uint16_t size)
{ assert(p==&@PCD@);calls++;if(calls==fail_call) { return 1U; }regs.GRXFSIZ=size;return 0U; }
uint8_t HAL_PCDEx_SetTxFiFo(PCD_HandleTypeDef *p,uint8_t n,uint16_t size)
{ assert(p==&@PCD@ && n<=2U);calls++;if(calls==fail_call) { return 1U; }
  uint32_t offset=regs.GRXFSIZ;
  if(n==0U) { regs.DIEPTXF0_HNPTXFSIZ=((uint32_t)size<<16)|offset; }
  else { offset+=regs.DIEPTXF0_HNPTXFSIZ>>16;if(n==2U) { offset+=regs.DIEPTXF[0]>>16; }
    regs.DIEPTXF[n-1U]=((uint32_t)size<<16)|offset;if(bad_readback) { regs.DIEPTXF[n-1U]=0U; } }
  return 0U; }
'''
        check = 'assert(calls==3U && UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK);'
        valid = 'regs.DIEPTXF[0]=(64U<<16)|192U;regs.DIEPTXF[1]=(16U<<16)|256U;'
    else:
        setters = r'''
uint8_t HAL_PCDEx_PMAConfig(PCD_HandleTypeDef *p,uint16_t address,uint16_t kind,uint32_t location)
{ assert(p==&@PCD@ && kind==PCD_SNG_BUF);calls++;if(calls==fail_call) { return 1U; }
  Ep *ep=(address&0x80U)?&p->IN_ep[address&0x7FU]:&p->OUT_ep[address];
  ep->pmaadress=(uint16_t)(bad_readback?0U:location);ep->doublebuffer=0U;return 0U; }
'''
        check = 'assert(calls==5U && @PCD@.IN_ep[2].pmaadress==0x100U && @PCD@.OUT_ep[1].pmaadress==0x110U);'
        valid = ''
    harness = r'''
int main(int argc,char **argv)
{
 assert(argc==2);
 if(strcmp(argv[1],"pcd-failure")==0) { fail_init=1U; }
 if(strcmp(argv[1],"readback")==0) { bad_readback=1U; }
 if(strncmp(argv[1],"call-",5)==0) { fail_call=(unsigned)strtoul(argv[1]+5,NULL,10); }
 uint8_t result=USBD_LL_Init(&hUsbDeviceFS);
 assert(result==USBD_OK);
 if(strcmp(argv[1],"valid-layout")==0) { @VALID@ assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)==USB_CDC_OK);return 0; }
 if(strcmp(argv[1],"overlap")==0) { @VALID@ @OVERLAP@ assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK);return 0; }
 if(fail_call||bad_readback) { assert(UsbCdcRetire_ConfigurationCheck(&hUsbDeviceFS)!=USB_CDC_OK && link_down>0U); }
 else { assert(result==USBD_OK);@CHECK@ }
 return 0;
}
'''
    harness = harness.replace('@VALID@', valid).replace('@OVERLAP@',
        'regs.DIEPTXF[1]=(16U<<16)|192U;' if indexed else '@PCD@.IN_ep[2].pmaadress=0xC0U;')
    program = (INIT_HEADER.replace('@SETTERS@', setters) + body + harness.replace('@CHECK@', check)).replace(
        '@PCD@', 'hpcd_USB_OTG_FS' if indexed else 'hpcd_USB_FS')
    (path / 'test.c').write_text(program, encoding='utf8')
    command = ['gcc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion',
               '-Wsign-conversion','-Wshadow','-fanalyzer','-I'+str(path),str(path/'test.c'),'-o',str(path/'test.exe')]
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    (path/'compile.log').write_text(result.stdout+result.stderr, encoding='utf8')
    assert result.returncode == 0, result.stdout+result.stderr
    return indexed, path


@pytest.mark.parametrize('scenario', ['normal','valid-layout','overlap','pcd-failure','readback','call-1','call-2','call-3','call-4','call-5'])
def test_native_initialization_configuration_failures(native_init_program, scenario):
    indexed, path = native_init_program
    if indexed and scenario in {'call-4','call-5'}:
        pytest.skip('Original CubeMX OTG FS layout has three calls; missing TX2 is rejected at configuration boundary')
    result = subprocess.run([str(path/'test.exe'),scenario], capture_output=True, text=True, timeout=15)
    (path/(scenario+'.log')).write_text(result.stdout+result.stderr, encoding='utf8')
    assert result.returncode == 0, result.stdout+result.stderr
