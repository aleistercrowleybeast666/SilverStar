import os
from pathlib import Path
import shutil
import subprocess
import pytest
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.generator.native_usb_data import NativeUsbData_Derive


@pytest.mark.parametrize('scenario', ['normal','open1','open2','open3','app-init','prepare-init',
    'tx-fail','tx-busy','rearm','receive','zlp','close','null-rx','null-out','oversize','bad-ep'])
def test_real_native_bulk_functions_propagate_failure(tmp_path, scenario):
    _ExerciseNativeBulk(tmp_path,scenario)


def _ExerciseNativeBulk(tmp_path, scenario, *, indexed=False):
    origin = os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT')
    compiler = shutil.which('gcc')
    if not origin or compiler is None:
        pytest.skip('Native source fixture or Host GCC unavailable')
    original = (Path(origin)/('cube-f407-usb' if indexed else 'cube-f103-usb')/'Middlewares/ST/STM32_USB_Device_Library/Class/CDC/Src/usbd_cdc.c').read_bytes()
    if indexed:
        from silverstar_fccg.generator.native_usb_indexed import NativeUsbIndexedData_Derive
        derived=NativeUsbIndexedData_Derive(original).decode('utf-8-sig')
    else:derived = NativeUsbData_Derive(original).decode('utf-8-sig')
    names = ['USBD_CDC_Init','USBD_CDC_DeInit','USBD_CDC_DataIn','USBD_CDC_DataOut',
        'USBD_CDC_TransmitPacket','USBD_CDC_ReceivePacket','USBD_CDC_SetTxBuffer','USBD_CDC_SetRxBuffer']
    if 'NativeCdc_Fault' in derived:
        names = ['NativeCdc_Fault','NativeCdc_InitAbort','NativeCdc_Open']+names
    functions = []
    for name in names:
        start, _opening, end = NativeC_FunctionSpanGet(derived, name)
        functions.append(derived[start:end])
    header = '''#include <stdint.h>
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
typedef struct { uint32_t total_length;uint8_t is_used; } Endpoint;
typedef struct { void *pClassData,*pUserData,*pData;uint8_t dev_speed,dev_state;Endpoint ep_in[16],ep_out[16]; } USBD_HandleTypeDef;
typedef struct { uint32_t TxState,RxState,TxLength,RxLength;uint8_t *TxBuffer,*RxBuffer; } USBD_CDC_HandleTypeDef;
typedef struct { int8_t (*Init)(void);int8_t (*DeInit)(void);int8_t (*Receive)(uint8_t *,uint32_t *); } USBD_CDC_ItfTypeDef;
typedef struct { struct { uint32_t maxpacket; } IN_ep[16]; } PCD_HandleTypeDef;
static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DataIn(USBD_HandleTypeDef *,uint8_t);
static uint8_t USBD_CDC_DataOut(USBD_HandleTypeDef *,uint8_t);
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *);
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *,uint8_t *,uint16_t);
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
'''
    harness = '''int main(int argc,char **argv)
{
    assert(argc==2);USBD_CDC_ItfTypeDef itf={AppInit,AppDeInit,AppReceive};PCD_HandleTypeDef pcd={0};
    pcd.IN_ep[1].maxpacket=64U;dev.pData=&pcd;dev.pUserData=&itf;dev.dev_speed=USBD_SPEED_FULL;
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
'''
    if indexed:
        header=header.replace('uint8_t is_used;','uint8_t is_used,bInterval;')
        header=header.replace('void *pClassData,*pUserData,*pData;',
            'void *pClassData,*pData;void *pClassDataCmsit[1],*pUserData[1];uint8_t classId;')
        header=header.replace('int8_t (*Receive)(uint8_t *,uint32_t *);',
            'int8_t (*Receive)(uint8_t *,uint32_t *);int8_t (*TransmitCplt)(uint8_t *,uint32_t *,uint8_t);')
        header=header.replace('uint8_t *,uint16_t);','uint8_t *,uint32_t);',1)
        header+='\n#define CDC_FS_BINTERVAL 16U\nstatic unsigned transport_faults;\nstatic void NativeRuntime_TransportFaultRecord(void) { transport_faults++; }\n'
        harness=harness.replace('itf={AppInit,AppDeInit,AppReceive}',
            'itf={AppInit,AppDeInit,AppReceive,NULL}').replace('dev.pUserData=&itf','dev.pUserData[0]=&itf')
        harness=harness.replace('    if (strcmp(argv[1],"tx-fail")',
            '    if (strcmp(argv[1],"bad-class")==0) { dev.classId=7U;assert(USBD_CDC_TransmitPacket(&dev)!=USBD_OK && transport_faults==1U && resets!=0U);return 0; }\n'
            '    if (strcmp(argv[1],"mirror")==0) { dev.pClassData=NULL;assert(USBD_CDC_ReceivePacket(&dev)!=USBD_OK && transport_faults==1U);return 0; }\n'
            '    if (strcmp(argv[1],"tx-fail")',1)
    (tmp_path/'test.c').write_text(header+'\n'+'\n'.join(functions)+'\n'+harness)
    flags = ['-std=c11','-O2','-Wall','-Werror=implicit-function-declaration','-Werror=incompatible-pointer-types']
    if derived.encode() != original:
        flags += ['-Wextra','-Werror','-Wpedantic','-Wconversion','-Wsign-conversion','-Wshadow','-fanalyzer']
    result = subprocess.run([compiler,*flags,str(tmp_path/'test.c'),'-o',str(tmp_path/'test.exe')],capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    result = subprocess.run([str(tmp_path/'test.exe'),scenario],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
