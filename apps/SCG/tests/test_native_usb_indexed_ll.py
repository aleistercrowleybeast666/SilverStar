"""Recognized F407 normal LL initialization and HAL return paths only."""
from pathlib import Path
import os,shutil,subprocess,json,hashlib
import pytest
from silverstar_fccg.generator.native_usb_indexed import NativeUsbIndexedLl_Derive
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet


@pytest.mark.parametrize('scenario',['normal','pcd-init','fifo1','fifo2','fifo3','fifo4',
    'fifo-cleanup','tx','rearm','start','stop','busy','timeout'])
def test_actual_indexed_ll_fifo_and_ordinary_hal_returns(tmp_path,scenario):
    origin=os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT');gcc=shutil.which('gcc')
    if not origin or not gcc:pytest.skip('Native source or Host GCC unavailable')
    original=(Path(origin)/'cube-f407-usb/USB_DEVICE/Target/usbd_conf.c').read_bytes()
    derived=NativeUsbIndexedLl_Derive(original)
    text=derived.decode()
    names=['USBD_LL_Init','USBD_LL_Start','USBD_LL_Stop','USBD_LL_Transmit','USBD_LL_PrepareReceive','USBD_Get_USB_Status']
    functions=[]
    for name in names:
        a,_o,b=NativeC_FunctionSpanGet(text,name);functions.append(text[a:b])
    header=r"""#include <stdint.h>
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
"""
    harness=r"""int main(int argc,char **argv)
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
"""
    source=tmp_path/'test.c';source.write_text(header+'\n'.join(functions)+'\n'+harness)
    exe=tmp_path/'test.exe'
    command=[gcc,'-std=c11','-O2','-Wall','-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion','-Wundef','-fanalyzer',str(source),'-o',str(exe)]
    compiled=subprocess.run(command,capture_output=True,text=True,timeout=60)
    assert compiled.returncode==0,compiled.stdout+compiled.stderr
    run=subprocess.run([str(exe),scenario],capture_output=True,text=True,timeout=15)
    (tmp_path/'evidence.json').write_text(json.dumps({'compile':command,'compile_exit':compiled.returncode,'compile_stdout':compiled.stdout,'compile_stderr':compiled.stderr,
        'run':[str(exe),scenario],'run_exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr,
        'native_sha256':hashlib.sha256(original).hexdigest(),'derived_sha256':hashlib.sha256(derived).hexdigest(),
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'executable_sha256':hashlib.sha256(exe.read_bytes()).hexdigest()},indent=2))
    assert run.returncode==0,run.stdout+run.stderr
