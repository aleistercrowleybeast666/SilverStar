"""Normal valid CDC metadata flow only; no malformed USB or owner research."""
import shutil,subprocess
from test_native_ground_backend import bound
from test_native_classic_cdc import native
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet

HEADER=r'''#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#define USB_MAX_EP0_SIZE 64U
#define USBD_OK 0U
#define USBD_FAIL 2U
#define USBD_STATE_CONFIGURED 3U
#define CDC_SET_LINE_CODING 0x20U
#define CDC_GET_LINE_CODING 0x21U
#define CDC_SET_CONTROL_LINE_STATE 0x22U
typedef uint8_t USBD_StatusTypeDef;
typedef struct {uint8_t bmRequest,bRequest;uint16_t wValue,wIndex,wLength;} USBD_SetupReqTypedef;
typedef struct {uint32_t data[16];uint8_t CmdOpCode,CmdLength;} USBD_CDC_HandleTypeDef;
typedef struct Device USBD_HandleTypeDef;
typedef struct {uint8_t (*Setup)(USBD_HandleTypeDef *,USBD_SetupReqTypedef *);} USBD_ClassTypeDef;
typedef struct {int8_t (*Control)(uint8_t,uint8_t *,uint16_t);} USBD_CDC_ItfTypeDef;
struct Device {uint8_t dev_state;void *pUserData,*pClassData;USBD_ClassTypeDef *pClass;USBD_SetupReqTypedef request;};
int8_t PcUsbControl_Control(uint8_t,uint8_t *,uint16_t);
void PcUsbControl_Cancel(USBD_HandleTypeDef *);
USBD_StatusTypeDef PcUsbControl_Dispatch(USBD_HandleTypeDef *);
USBD_StatusTypeDef PcUsbControl_Setup(USBD_HandleTypeDef *,USBD_SetupReqTypedef *);
USBD_StatusTypeDef PcUsbControl_RxReady(USBD_HandleTypeDef *);
USBD_HandleTypeDef hUsbDeviceFS;
USBD_ClassTypeDef USBD_CDC={PcUsbControl_Setup};
USBD_CDC_ItfTypeDef USBD_Interface_fops_FS={PcUsbControl_Control};
static uint8_t *armed;static unsigned sent,statuses;
static USBD_StatusTypeDef USBD_CtlSendData(USBD_HandleTypeDef *d,uint8_t *p,uint16_t n)
{assert(d==&hUsbDeviceFS && n==7U && p!=NULL);sent++;return USBD_OK;}
static USBD_StatusTypeDef USBD_CtlPrepareRx(USBD_HandleTypeDef *d,uint8_t *p,uint16_t n)
{assert(d==&hUsbDeviceFS && n==7U);armed=p;return USBD_OK;}
static USBD_StatusTypeDef USBD_CtlSendStatus(USBD_HandleTypeDef *d)
{assert(d==&hUsbDeviceFS);statuses++;return USBD_OK;}
static void USBD_CtlError(USBD_HandleTypeDef *d,USBD_SetupReqTypedef *r)
{(void)d;(void)r;assert(0);}
static uint32_t USBD_LL_GetRxDataSize(USBD_HandleTypeDef *d,uint8_t ep)
{assert(d==&hUsbDeviceFS && ep==0U);return 7U;}
'''
HARNESS=r'''int main(void)
{
  USBD_CDC_HandleTypeDef cdc={0};
  uint8_t expected[7]={0x00U,0xC2U,0x01U,0U,0U,0U,8U};
  uint8_t changed[7]={0x80U,0x25U,0U,0U,0U,0U,8U};
  hUsbDeviceFS.dev_state=USBD_STATE_CONFIGURED;
  hUsbDeviceFS.pClassData=&cdc;hUsbDeviceFS.pUserData=&USBD_Interface_fops_FS;hUsbDeviceFS.pClass=&USBD_CDC;
  hUsbDeviceFS.request=(USBD_SetupReqTypedef){0xA1U,CDC_GET_LINE_CODING,0U,0U,7U};
  assert(PcUsbControl_Dispatch(&hUsbDeviceFS)==USBD_OK);
  assert(sent==1U && memcmp(cdc.data,expected,7U)==0);
  hUsbDeviceFS.request=(USBD_SetupReqTypedef){0x21U,CDC_SET_LINE_CODING,0U,0U,7U};
  assert(PcUsbControl_Dispatch(&hUsbDeviceFS)==USBD_OK);
  assert(armed!=NULL && cdc.CmdOpCode==CDC_SET_LINE_CODING && cdc.CmdLength==7U);
  memcpy(armed,changed,7U);
  assert(PcUsbControl_RxReady(&hUsbDeviceFS)==USBD_OK);
  assert(cdc.CmdOpCode==0xFFU && cdc.CmdLength==0U);
  hUsbDeviceFS.request=(USBD_SetupReqTypedef){0xA1U,CDC_GET_LINE_CODING,0U,0U,7U};
  assert(PcUsbControl_Dispatch(&hUsbDeviceFS)==USBD_OK);
  assert(sent==2U && memcmp(cdc.data,changed,7U)==0);
  hUsbDeviceFS.request=(USBD_SetupReqTypedef){0x21U,CDC_SET_CONTROL_LINE_STATE,3U,0U,0U};
  assert(PcUsbControl_Dispatch(&hUsbDeviceFS)==USBD_OK && statuses==1U);
  PcUsbControl_Cancel(&hUsbDeviceFS);assert(cdc.CmdOpCode==0xFFU && cdc.CmdLength==0U);
  return 0;
}
'''

def test_valid_f103_control_flow_and_preserved_bulk(bound,tmp_path):
    service,imported,args,_source=bound
    plan=service.NativeClassicCdcGroundCandidate_Plan(imported.model,device_facts=args['device_facts'])
    if args['device_facts'].part=='STM32F407VET6':
        assert plan.contract['usb_control'] is None
        return
    manifest=plan.contract['usb_control']
    assert manifest['independent_review']=='NO_PASSED_OUTCOME' and manifest['formal_release'] is False
    entry=next(e for e in manifest['vendor_patches'] if e['derived_path'].endswith('/usbd_cdc.c'))
    text=plan.files[entry['derived_path']].decode()
    start,_opening,end=NativeC_FunctionSpanGet(text,'USBD_CDC_Init')
    assert 'memset(hcdc, 0, sizeof(*hcdc))' in text[start:end]
    assert 'hcdc->CmdOpCode = 0xFFU;' in text[start:end]
    assert 'NativeCdc_InitAbort' in text[start:end]
    source=plan.files['Generated/Src/pc_usb_control.c'].decode()
    source='\n'.join(line for line in source.splitlines() if not line.startswith('#include'))
    compiler=shutil.which('gcc');assert compiler
    path=tmp_path/'control_normal.c';exe=tmp_path/'control_normal.exe'
    path.write_text(HEADER+source+HARNESS,encoding='utf8')
    result=subprocess.run([compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wvla',str(path),'-o',str(exe)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
