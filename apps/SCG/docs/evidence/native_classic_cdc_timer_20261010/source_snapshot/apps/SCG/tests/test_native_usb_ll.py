import os
from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.generator.native_usb_data import NativeUsbCore_Derive, NativeUsbLl_Derive


@pytest.mark.parametrize('scenario',['normal','core-init','core-start','pcd-init','pma','tx','rearm'])
def test_native_initialization_and_ll_errors_propagate(tmp_path,scenario):
    origin=os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT');compiler=shutil.which('gcc')
    if not origin or compiler is None:pytest.skip('Native fixture or Host GCC unavailable')
    root=Path(origin)/'cube-f103-usb'
    core=NativeUsbCore_Derive((root/'Middlewares/ST/STM32_USB_Device_Library/Core/Src/usbd_core.c').read_bytes()).decode()
    ll=NativeUsbLl_Derive((root/'USB_DEVICE/Target/usbd_conf.c').read_bytes()).decode()
    selected=[]
    for source,names in ((core,['USBD_Init','USBD_Start']),
        (ll,['USBD_LL_Init','USBD_LL_Transmit','USBD_LL_PrepareReceive','USBD_Get_USB_Status'])):
        for name in names:
            a,_o,b=NativeC_FunctionSpanGet(source,name);selected.append(source[a:b])
    header='''#include <stdint.h>
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
'''
    # Test the actual core entry function against a fallible LL interface, then
    # test actual LL_Init independently; no MCU/EP0 execution or review here.
    selected[0]=selected[0].replace('USBD_LL_Init(pdev)','CoreInit(pdev)')
    harness='''int main(int argc,char **argv)
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
'''
    (tmp_path/'test.c').write_text(header+'\n'+'\n'.join(selected)+'\n'+harness)
    result=subprocess.run([compiler,'-std=c11','-O2','-Wall','-Werror=implicit-function-declaration',
        str(tmp_path/'test.c'),'-o',str(tmp_path/'test.exe')],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run([str(tmp_path/'test.exe'),scenario],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
