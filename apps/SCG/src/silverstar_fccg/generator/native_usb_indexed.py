"""Private recognized single-slot CDC data profile; EP0 remains unchanged."""
import hashlib,re
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet

CLASS_SHA='794a6d0df08fc2b777678b99013f61d0a9c93f5fbeacfaa3466c0feeaa9ada39'
CORE_SHA='21647e3c0537a8d56cd67cc67951206f7a84501acd74d0c8a827c13e192183c5'
LL_SHA='29c45cc956aa40eab3417c6a9a39fd2b196dde7c4cef8f3699a1c500d5825fe1'


def _Replace(source,name,function):
    a,_o,b=NativeC_FunctionSpanGet(source,name)
    return source[:a]+function+source[b:]


def NativeUsbIndexedData_Derive(original):
    if hashlib.sha256(original).hexdigest()!=CLASS_SHA:
        raise ValueError('Native indexed CDC class source requires review')
    from silverstar_fccg.generator.native_usb_data import _FUNCTIONS,_HELPERS
    source=original.decode('utf-8-sig')
    # Only these two bulk function signatures have two conditional opening
    # braces. Select their non-composite declarations before replacing bodies.
    # Control/EP0 functions and their conditional text remain byte-identical.
    for name in ('USBD_CDC_SetTxBuffer','USBD_CDC_TransmitPacket'):
        pattern=(r'#ifdef USE_USBD_COMPOSITE\r?\nuint8_t '+name+r'\(.*?#else\r?\n'
            r'(uint8_t '+name+r'\(.*?\r?\n\{\r?\n[^\r\n]+\r?\n)#endif[^\r\n]*')
        source,count=re.subn(pattern,r'\1',source,count=1,flags=re.S)
        if count!=1:raise ValueError('Native indexed bulk signature owner changed: '+name)
    source=source.replace('#include "usbd_cdc.h"','#include "usbd_cdc.h"\n#include "pc_byte_stream.h"\n'
        '#include "native_runtime.h"\n#include <string.h>\n'
        '#ifdef USE_USBD_COMPOSITE\n#error "Private indexed CDC profile requires a single non-composite class"\n#endif\n'
        '_Static_assert(USBD_MAX_SUPPORTED_CLASS == 1U, "Private indexed CDC requires one class slot");',1)
    for name,body in _FUNCTIONS.items():
        body=body.replace('pdev->pClassData','pdev->pClassDataCmsit[0]').replace('pdev->pUserData','pdev->pUserData[0]')
        brace=body.index('{')+1
        body=body[:brace]+'''
  if (pdev == NULL) { return USBD_FAIL; }
  if ((pdev->classId != 0U) || (pdev->pClassData != pdev->pClassDataCmsit[0]))
  { NativeRuntime_TransportFaultRecord(); return NativeCdc_Fault(pdev); }
'''+body[brace:]
        if name=='USBD_CDC_Init':
            body=body.replace('  if (pdev->pClassDataCmsit[0] == NULL)',
                '  pdev->pClassData = pdev->pClassDataCmsit[0];\n  if (pdev->pClassDataCmsit[0] == NULL)',1)
            body=body.replace('  /* The recognized native configuration',
                '  pdev->ep_in[CDC_CMD_EP & 0x0FU].bInterval = CDC_FS_BINTERVAL;\n  /* The recognized native configuration',1)
        elif name=='USBD_CDC_DeInit':
            body=body.replace('pdev->pClassDataCmsit[0] = NULL;',
                'pdev->pClassDataCmsit[0] = NULL; pdev->pClassData = NULL;')
        elif name=='USBD_CDC_SetTxBuffer':
            body=body.replace('uint16_t length','uint32_t length')
        elif name=='USBD_CDC_DataIn':
            body=body.replace('  else { hcdc->TxState = 0U; }','''  else
  {
    USBD_CDC_ItfTypeDef *itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData[0];
    if ((itf == NULL) || ((itf->TransmitCplt != NULL) &&
        (itf->TransmitCplt(hcdc->TxBuffer, &hcdc->TxLength, epnum) != (int8_t)USBD_OK)))
    { return NativeCdc_Fault(pdev); }
    hcdc->TxState = 0U;
  }''')
        source=_Replace(source,name,body)
    a,_o,_b=NativeC_FunctionSpanGet(source,'USBD_CDC_Init')
    source=source[:a]+_HELPERS+'\n'+source[a:]
    # Bulk endpoints are now the fixed, checked single-profile constants. The
    # three mutable aliases belonged to removed composite/data implementations.
    for name,value in (('CDCInEpAdd','CDC_IN_EP'),('CDCOutEpAdd','CDC_OUT_EP'),('CDCCmdEpAdd','CDC_CMD_EP')):
        source,count=re.subn(r'(?m)^static uint8_t '+name+r'\s*=\s*'+value+r';\r?\n','',source)
        if count!=1:raise ValueError('Native indexed endpoint alias owner changed: '+name)
    return source.encode()


def NativeUsbIndexedCore_Derive(original):
    if hashlib.sha256(original).hexdigest()!=CORE_SHA:
        raise ValueError('Native indexed CDC core source requires review')
    source=original.decode('utf-8-sig')
    source=source.replace('#include "usbd_core.h"','#include "usbd_core.h"\n#include "native_runtime.h"',1)
    source=_Replace(source,'USBD_ClrClassConfig','''USBD_StatusTypeDef USBD_ClrClassConfig(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  if ((pdev == NULL) || (pdev->classId != 0U) || (pdev->pClass[0] == NULL) ||
      (pdev->pClass[0]->DeInit == NULL)) { return USBD_FAIL; }
  return (pdev->pClass[0]->DeInit(pdev, cfgidx) == USBD_OK) ? USBD_OK : USBD_FAIL;
}''')
    source=_Replace(source,'USBD_Stop','''USBD_StatusTypeDef USBD_Stop(USBD_HandleTypeDef *pdev)
{
  USBD_StatusTypeDef result;
  uint8_t class_result = USBD_OK;
  if ((pdev == NULL) || (pdev->classId != 0U)) { return USBD_FAIL; }
  pdev->dev_state = USBD_STATE_DEFAULT;
  if (pdev->pClass[0] != NULL)
  {
    if (pdev->pClass[0]->DeInit == NULL) { class_result = USBD_FAIL; }
    else { class_result = pdev->pClass[0]->DeInit(pdev, (uint8_t)pdev->dev_config); }
  }
  result = USBD_LL_Stop(pdev);
  return ((class_result == USBD_OK) && (result == USBD_OK)) ? USBD_OK : USBD_FAIL;
}''')
    # Core already propagates LL Init/Start and class data return values. Keep
    # its entire EP0 branch untouched; guard only the nonzero endpoint branch.
    for stage in ('DataIn','DataOut'):
        name='USBD_LL_'+stage+'Stage';a,_o,b=NativeC_FunctionSpanGet(source,name)
        body=source[a:b]
        anchor='    /* Get the class index relative to this interface */'
        if body.count(anchor)!=1:raise ValueError('Native indexed core data route changed')
        body=body.replace(anchor,'''    if ((pdev == NULL) || (epnum != 1U)) { return USBD_FAIL; }
    if ((pdev->classId != 0U) || (pdev->pClass[0] == NULL) || (pdev->pClass[0]->'''+stage+''' == NULL))
    { if (pdev->dev_state == USBD_STATE_CONFIGURED) { NativeRuntime_TransportFaultRecord(); } return USBD_FAIL; }
'''+anchor,1)
        source=source[:a]+body+source[b:]
    a,_o,b=NativeC_FunctionSpanGet(source,'USBD_Init');body=source[a:b]
    anchor='  pdev->pConfDesc = NULL;'
    if body.count(anchor)!=1:raise ValueError('Native indexed initialization owner changed')
    body=body.replace(anchor,'''  if ((pdev->pClassData != NULL) || (pdev->pClassDataCmsit[0] != NULL)) { return USBD_FAIL; }
  pdev->classId = 0U;
  pdev->NumClasses = 0U;
'''+anchor,1)
    source=source[:a]+body+source[b:]
    return source.encode()


def NativeUsbIndexedLl_Derive(original):
    if hashlib.sha256(original).hexdigest()!=LL_SHA:
        raise ValueError('Native indexed CDC LL source requires review')
    source=original.decode('utf-8-sig')
    source=_Replace(source,'USBD_LL_Init','''USBD_StatusTypeDef USBD_LL_Init(USBD_HandleTypeDef *pdev)
{
  if ((pdev == NULL) || (pdev->id != DEVICE_FS)) { return USBD_FAIL; }
  hpcd_USB_OTG_FS.pData = pdev;
  pdev->pData = &hpcd_USB_OTG_FS;
  hpcd_USB_OTG_FS.Instance = USB_OTG_FS;
  hpcd_USB_OTG_FS.Init.dev_endpoints = 4U;
  hpcd_USB_OTG_FS.Init.speed = PCD_SPEED_FULL;
  hpcd_USB_OTG_FS.Init.dma_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.phy_itface = PCD_PHY_EMBEDDED;
  hpcd_USB_OTG_FS.Init.Sof_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.low_power_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.lpm_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.vbus_sensing_enable = DISABLE;
  hpcd_USB_OTG_FS.Init.use_dedicated_ep1 = DISABLE;
  if (HAL_PCD_Init(&hpcd_USB_OTG_FS) != HAL_OK) { return USBD_FAIL; }
  /* Fixed FS layout: RX=128, EP0=64, EP1=64, EP2=16 words, total 272/320.
   * EP2 retains its CDC notification endpoint; no alias into EP1's FIFO. */
  if ((HAL_PCDEx_SetRxFiFo(&hpcd_USB_OTG_FS, 128U) != HAL_OK) ||
      (HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 0U, 64U) != HAL_OK) ||
      (HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 1U, 64U) != HAL_OK) ||
      (HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 2U, 16U) != HAL_OK))
  {
    pdev->dev_state = USBD_STATE_DEFAULT;
    PcByteStream_OnUsbReset();
    if (HAL_PCD_DeInit(&hpcd_USB_OTG_FS) != HAL_OK) { NativeRuntime_TransportFaultRecord(); }
    return USBD_FAIL;
  }
  return USBD_OK;
}''')
    include='#include "usbd_cdc.h"'
    source=source.replace(include,include+'\n#include "pc_byte_stream.h"\n#include "native_runtime.h"\n'
        '_Static_assert(USE_HAL_PCD_REGISTER_CALLBACKS == 0U, "Private native port requires fixed PCD callbacks");',1)
    for stage,direction in (('DataOut','OUT'),('DataIn','IN')):
        old='  USBD_LL_'+stage+'Stage((USBD_HandleTypeDef*)hpcd->pData, epnum, hpcd->'+direction+'_ep[epnum].xfer_buff);'
        new='''  USBD_HandleTypeDef *pdev;
  if ((hpcd == NULL) || (hpcd->pData == NULL)) { return; }
  pdev = (USBD_HandleTypeDef *)hpcd->pData;
  if (epnum >= 4U) { pdev->dev_state = USBD_STATE_DEFAULT; PcByteStream_OnUsbReset(); return; }
  if (USBD_LL_'''+stage+'Stage(pdev, epnum, hpcd->'+direction+'''_ep[epnum].xfer_buff) != USBD_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; PcByteStream_OnUsbReset(); }'''
        if source.count(old)!=1:raise ValueError('Native indexed PCD bulk callback owner changed')
        source=source.replace(old,new,1)
    for event in ('Reset','DevDisconnected','Suspend'):
        pattern=r'(?m)^([ \t]*)(USBD_LL_'+event+r'\([^\r\n]+\);)[ \t]*\r?$'
        source,count=re.subn(pattern,r'\1PcByteStream_OnUsbReset();\n\1\2',source)
        if count!=1:raise ValueError('Native indexed USB lifecycle owner changed: '+event)
    return source.encode()
