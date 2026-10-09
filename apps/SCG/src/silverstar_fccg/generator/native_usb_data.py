"""Independent native CDC bulk derivative; EP0 functions remain byte-identical."""
import hashlib
import re
import difflib
import json
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX


_HELPERS = '''static uint8_t NativeCdc_Fault(USBD_HandleTypeDef *pdev)
{
  pdev->dev_state = USBD_STATE_DEFAULT;
  PcByteStream_OnUsbReset();
  return USBD_FAIL;
}

static uint8_t NativeCdc_InitAbort(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  uint8_t cleanup = USBD_CDC_DeInit(pdev, cfgidx);
  uint8_t failure = NativeCdc_Fault(pdev);
  /* Never turn successful cleanup into successful initialization. */
  return (cleanup == USBD_BUSY) ? USBD_BUSY : failure;
}

static uint8_t NativeCdc_Open(USBD_HandleTypeDef *pdev, uint8_t ep,
                            uint8_t type, uint16_t size)
{
  USBD_StatusTypeDef result = USBD_LL_OpenEP(pdev, ep, type, size);
  if (result != USBD_OK) { return (result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL; }
  if ((ep & 0x80U) != 0U) { pdev->ep_in[ep & 0x0FU].is_used = 1U; }
  else { pdev->ep_out[ep & 0x0FU].is_used = 1U; }
  return USBD_OK;
}
'''

_FUNCTIONS = {
'USBD_CDC_Init': '''static uint8_t USBD_CDC_Init(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_CDC_ItfTypeDef *itf;
  if ((pdev == NULL) || (pdev->dev_speed != USBD_SPEED_FULL) ||
      (pdev->pUserData == NULL) || (pdev->pClassData != NULL)) { return USBD_FAIL; }
  itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData;
  if ((itf->Init == NULL) || (itf->DeInit == NULL) || (itf->Receive == NULL) ||
      (pdev->ep_in[CDC_IN_EP & 0x0FU].is_used != 0U) ||
      (pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used != 0U) ||
      (pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used != 0U)) { return USBD_FAIL; }
  /* The recognized native configuration maps this to one static class block. */
  pdev->pClassData = USBD_malloc(sizeof(USBD_CDC_HandleTypeDef));
  if (pdev->pClassData == NULL) { return NativeCdc_Fault(pdev); }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  memset(hcdc, 0, sizeof(*hcdc));
  if ((NativeCdc_Open(pdev, CDC_IN_EP, USBD_EP_TYPE_BULK, CDC_DATA_FS_IN_PACKET_SIZE) != USBD_OK) ||
      (NativeCdc_Open(pdev, CDC_OUT_EP, USBD_EP_TYPE_BULK, CDC_DATA_FS_OUT_PACKET_SIZE) != USBD_OK) ||
      (NativeCdc_Open(pdev, CDC_CMD_EP, USBD_EP_TYPE_INTR, CDC_CMD_PACKET_SIZE) != USBD_OK))
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  if ((itf->Init() != (int8_t)USBD_OK) || (hcdc->RxBuffer == NULL) || (hcdc->TxBuffer == NULL))
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  if (USBD_LL_PrepareReceive(pdev, CDC_OUT_EP, hcdc->RxBuffer, CDC_DATA_FS_OUT_PACKET_SIZE) != USBD_OK)
  { return NativeCdc_InitAbort(pdev, cfgidx); }
  return USBD_OK;
}''',
'USBD_CDC_DeInit': '''static uint8_t USBD_CDC_DeInit(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  uint8_t result = USBD_OK;
  USBD_CDC_ItfTypeDef *itf;
  /* There is one FS configuration; cleanup does not depend on its old index. */
  (void)cfgidx;
  if (pdev == NULL) { return USBD_FAIL; }
  if (pdev->ep_in[CDC_IN_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_IN_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_in[CDC_IN_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_OUT_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_out[CDC_OUT_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used != 0U)
  {
    if (USBD_LL_CloseEP(pdev, CDC_CMD_EP) != USBD_OK) { result = USBD_FAIL; }
    else { pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used = 0U; }
  }
  if (pdev->pClassData != NULL)
  {
    USBD_CDC_HandleTypeDef *hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
    hcdc->TxState = 1U; /* Retain buffer ownership until closure is confirmed. */
    itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData;
    if ((itf == NULL) || (itf->DeInit == NULL) || (itf->DeInit() != (int8_t)USBD_OK))
    { result = USBD_FAIL; }
    if (result == USBD_OK) { USBD_free(pdev->pClassData); pdev->pClassData = NULL; }
  }
  if (result != USBD_OK) { return NativeCdc_Fault(pdev); }
  return result;
}''',
'USBD_CDC_SetTxBuffer': '''uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *pdev, uint8_t *pbuff, uint16_t length)
{
  USBD_CDC_HandleTypeDef *hcdc;
  /* This private owner accepts the SCG-owned maximum 70-byte GSP frame. */
  if ((pdev == NULL) || (pdev->pClassData == NULL) || (pbuff == NULL) || (length > 70U))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  if (hcdc->TxState != 0U) { return USBD_BUSY; }
  hcdc->TxBuffer = pbuff; hcdc->TxLength = length;
  return USBD_OK;
}''',
'USBD_CDC_SetRxBuffer': '''uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *pdev, uint8_t *pbuff)
{
  USBD_CDC_HandleTypeDef *hcdc;
  if ((pdev == NULL) || (pdev->pClassData == NULL) || (pbuff == NULL)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  hcdc->RxBuffer = pbuff;
  return USBD_OK;
}''',
'USBD_CDC_TransmitPacket': '''uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *pdev)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->pClassData == NULL) ||
      (pdev->dev_state != USBD_STATE_CONFIGURED) || (pdev->dev_speed != USBD_SPEED_FULL))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  if (hcdc->TxState != 0U) { return USBD_BUSY; }
  if ((hcdc->TxBuffer == NULL) || (hcdc->TxLength == 0U) || (hcdc->TxLength > 70U))
  { return USBD_FAIL; }
  hcdc->TxState = 1U;
  pdev->ep_in[CDC_IN_EP & 0x0FU].total_length = hcdc->TxLength;
  result = USBD_LL_Transmit(pdev, CDC_IN_EP, hcdc->TxBuffer, (uint16_t)hcdc->TxLength);
  if (result != USBD_OK)
  {
    /* A failed LL call cannot prove absence of partial DMA ownership. Keep
     * TxState and bytes owned until successful endpoint closure or reset. */
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}''',
'USBD_CDC_ReceivePacket': '''uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *pdev)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->pClassData == NULL) || (pdev->dev_speed != USBD_SPEED_FULL))
  { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  if (hcdc->RxBuffer == NULL) { return USBD_FAIL; }
  result = USBD_LL_PrepareReceive(pdev, CDC_OUT_EP, hcdc->RxBuffer, CDC_DATA_FS_OUT_PACKET_SIZE);
  if (result != USBD_OK)
  {
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}''',
'USBD_CDC_DataOut': '''static uint8_t USBD_CDC_DataOut(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  USBD_CDC_HandleTypeDef *hcdc;
  USBD_CDC_ItfTypeDef *itf;
  int8_t result;
  if ((pdev == NULL) || (epnum != (CDC_OUT_EP & 0x7FU)) || (pdev->pClassData == NULL) ||
      (pdev->pUserData == NULL) || (pdev->dev_state != USBD_STATE_CONFIGURED)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  itf = (USBD_CDC_ItfTypeDef *)pdev->pUserData;
  if ((hcdc->RxBuffer == NULL) || (itf->Receive == NULL)) { return NativeCdc_Fault(pdev); }
  hcdc->RxLength = USBD_LL_GetRxDataSize(pdev, epnum);
  if (hcdc->RxLength > CDC_DATA_FS_OUT_PACKET_SIZE) { return NativeCdc_Fault(pdev); }
  result = itf->Receive(hcdc->RxBuffer, &hcdc->RxLength);
  if (result != (int8_t)USBD_OK)
  {
    uint8_t failure = NativeCdc_Fault(pdev);
    return (result == (int8_t)USBD_BUSY) ? USBD_BUSY : failure;
  }
  return USBD_OK;
}''',
'USBD_CDC_DataIn': '''static uint8_t USBD_CDC_DataIn(USBD_HandleTypeDef *pdev, uint8_t epnum)
{
  USBD_CDC_HandleTypeDef *hcdc;
  PCD_HandleTypeDef *hpcd;
  if ((pdev == NULL) || (epnum != (CDC_IN_EP & 0x7FU)) || (pdev->pClassData == NULL) ||
      (pdev->pData == NULL) || (pdev->dev_state != USBD_STATE_CONFIGURED)) { return USBD_FAIL; }
  hcdc = (USBD_CDC_HandleTypeDef *)pdev->pClassData;
  hpcd = (PCD_HandleTypeDef *)pdev->pData;
  if (hpcd->IN_ep[epnum].maxpacket != CDC_DATA_FS_IN_PACKET_SIZE)
  { return NativeCdc_Fault(pdev); }
  if ((pdev->ep_in[epnum].total_length > 0U) &&
      ((pdev->ep_in[epnum].total_length % CDC_DATA_FS_IN_PACKET_SIZE) == 0U))
  {
    USBD_StatusTypeDef result;
    pdev->ep_in[epnum].total_length = 0U;
    result = USBD_LL_Transmit(pdev, epnum, NULL, 0U);
    if (result != USBD_OK)
    {
      uint8_t failure = NativeCdc_Fault(pdev);
      return (result == USBD_BUSY) ? USBD_BUSY : failure;
    }
  }
  else { hcdc->TxState = 0U; }
  return USBD_OK;
}''',
}


def NativeUsbData_Derive(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != '9bf6b6c49a7faab7bdc465dae5df52bcc878720bd354c8596b51e16d6e210ecb':
        raise ValueError('Native CDC bulk source profile is unreviewed')
    source = original.decode('utf-8-sig')
    source = source.replace('#include "usbd_cdc.h"',
        '#include "usbd_cdc.h"\n#include "pc_byte_stream.h"\n#include <string.h>', 1)
    for name, function in _FUNCTIONS.items():
        start, _opening, end = NativeC_FunctionSpanGet(source, name)
        source = source[:start]+function+source[end:]
    start, _opening, _end = NativeC_FunctionSpanGet(source, 'USBD_CDC_Init')
    source = source[:start]+_HELPERS+'\n'+source[start:]
    return source.encode('utf-8')


def NativeUsbCore_Derive(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != '9696a4d61c9e05cd7989936792b15b88f9b7be567d2a927b4feeb0685f1a73a2':
        raise ValueError('Native CDC core source profile is unreviewed')
    source = original.decode('utf-8-sig')
    for name, old, new in (
        ('USBD_Init','  USBD_LL_Init(pdev);\n\n  return USBD_OK;', '  return USBD_LL_Init(pdev);'),
        ('USBD_Start','  USBD_LL_Start(pdev);\n\n  return USBD_OK;',
         '  if (pdev == NULL) { return USBD_FAIL; }\n  return USBD_LL_Start(pdev);'),
        ('USBD_ClrClassConfig','  pdev->pClass->DeInit(pdev, cfgidx);\n\n  return USBD_OK;',
         '  if ((pdev == NULL) || (pdev->pClass == NULL)) { return USBD_FAIL; }\n'
         '  return (pdev->pClass->DeInit(pdev, cfgidx) == USBD_OK) ? USBD_OK : USBD_FAIL;')):
        start, _opening, end = NativeC_FunctionSpanGet(source, name)
        function = source[start:end].replace('\r\n','\n')
        if function.count(old) != 1:
            raise ValueError('Native core result owner changed: '+name)
        source = source[:start]+function.replace(old,new,1)+source[end:]
    for stage in ('DataIn','DataOut'):
        name = 'USBD_LL_'+stage+'Stage'
        start, _opening, end = NativeC_FunctionSpanGet(source,name)
        function = source[start:end]
        old = '    pdev->pClass->'+stage+'(pdev, epnum);'
        new = ('    uint8_t result = pdev->pClass->'+stage+'(pdev, epnum);\n'
               '    return (result == USBD_OK) ? USBD_OK :\n'
               '        ((result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL);')
        if function.count(old) != 1:
            raise ValueError('Native bulk core callback owner changed: '+stage)
        source = source[:start]+function.replace(old,new,1)+source[end:]
    start, _opening, end = NativeC_FunctionSpanGet(source,'USBD_Stop')
    source = source[:start]+'''USBD_StatusTypeDef USBD_Stop(USBD_HandleTypeDef *pdev)
{
  uint8_t class_result = USBD_OK;
  USBD_StatusTypeDef result;
  if (pdev == NULL) { return USBD_FAIL; }
  pdev->dev_state = USBD_STATE_DEFAULT;
  if (pdev->pClass != NULL)
  { class_result = pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config); }
  result = USBD_LL_Stop(pdev);
  return ((class_result == USBD_OK) && (result == USBD_OK)) ? USBD_OK : USBD_FAIL;
}'''+source[end:]
    return source.encode('utf-8')


def NativeUsbLl_Derive(original: bytes) -> bytes:
    if hashlib.sha256(original).hexdigest() != 'effe29562b9d655026d6127a87a988af13d05744d5d6d70356faefe5004d0f87':
        raise ValueError('Native CDC LL source profile is unreviewed')
    source = original.decode('utf-8-sig')
    start, opening, end = NativeC_FunctionSpanGet(source,'USBD_LL_Init')
    function = source[start:end]
    local = opening-start+1
    function = function[:local]+'\n  if (pdev == NULL) { return USBD_FAIL; }\n'+function[local:]
    if function.count('Error_Handler( );') != 1:
        raise ValueError('Native PCD initialization failure owner changed')
    function = function.replace('Error_Handler( );','return USBD_FAIL;',1)
    function, count = re.subn(r'(HAL_PCDEx_PMAConfig\([^;]+\));',
        r'if (\1 != HAL_OK) { return USBD_FAIL; }',function)
    if count != 5:
        raise ValueError('Native PMA initialization owner changed')
    source = source[:start]+function+source[end:]
    # This candidate uses fixed vendor callbacks, never a runtime registry.
    include = '#include "usbd_cdc.h"'
    if source.count(include) != 1:
        raise ValueError('Native USB LL include owner changed')
    source = source.replace(include,include+'\n#include "pc_byte_stream.h"\n#if (USE_HAL_PCD_REGISTER_CALLBACKS != 0U)\n'
        '#error "Private native bulk port requires fixed PCD callback owners"\n#endif',1)
    for stage, direction in (('DataOut','OUT'),('DataIn','IN')):
        old = ('  USBD_LL_'+stage+'Stage((USBD_HandleTypeDef*)hpcd->pData, epnum, '
            'hpcd->'+direction+'_ep[epnum].xfer_buff);')
        new = ('''  USBD_HandleTypeDef *pdev;
  if ((hpcd == NULL) || (hpcd->pData == NULL)) { return; }
  pdev = (USBD_HandleTypeDef *)hpcd->pData;
  if (epnum >= 8U) { pdev->dev_state = USBD_STATE_DEFAULT; PcByteStream_OnUsbReset(); return; }
  if (USBD_LL_'''+stage+'''Stage(pdev, epnum, hpcd->'''+direction+'''_ep[epnum].xfer_buff) != USBD_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; PcByteStream_OnUsbReset(); }''')
        if source.count(old) != 1:
            raise ValueError('Native USB LL bulk stage owner changed: '+stage)
        source = source.replace(old,new,1)
    for event in ('Reset','DevDisconnected','Suspend'):
        pattern = r'(?m)^([ \t]*)(USBD_LL_'+event+r'\([^\r\n]+\);)[ \t]*\r?$'
        source, count = re.subn(pattern,r'\1PcByteStream_OnUsbReset();\n\1\2',source)
        if count != 1:
            raise ValueError('Native USB lifecycle owner changed: '+event)
    return source.encode('utf-8')


def NativeUsbBulk_FilesRender(files: dict[str, bytes], owners: dict[str, str]
                              ) -> tuple[dict[str, bytes], dict[str, str], dict]:
    rendered = {}; replacements = {}; entries = []
    indexed=hashlib.sha256(files[owners['usbd_cdc.c']]).hexdigest()=='794a6d0df08fc2b777678b99013f61d0a9c93f5fbeacfaa3466c0feeaa9ada39'
    if indexed:
        from silverstar_fccg.generator.native_usb_indexed import NativeUsbIndexedData_Derive,NativeUsbIndexedCore_Derive,NativeUsbIndexedLl_Derive
        derivatives=(('usbd_cdc.c',NativeUsbIndexedData_Derive),('usbd_core.c',NativeUsbIndexedCore_Derive),('usbd_conf.c',NativeUsbIndexedLl_Derive))
    else:
        derivatives=(('usbd_cdc.c',NativeUsbData_Derive),('usbd_core.c',NativeUsbCore_Derive),('usbd_conf.c',NativeUsbLl_Derive))
    for name, derive in derivatives:
        path = owners[name]; original = files[path]; derived = derive(original)
        target = 'HardwareGenerated/ReviewedNativeBulk/'+path
        rendered[target] = derived
        replacements[NATIVE_PREFIX+path] = target
        patch = target+'.patch'
        rendered[patch] = ''.join(difflib.unified_diff(original.decode('utf-8-sig').splitlines(keepends=True),
            derived.decode().splitlines(keepends=True),fromfile=NATIVE_PREFIX+path,tofile=NATIVE_PREFIX+path)).encode()
        entries.append({'original':NATIVE_PREFIX+path,'original_sha256':hashlib.sha256(original).hexdigest(),
            'derived':target,'derived_sha256':hashlib.sha256(derived).hexdigest(),
            'patch':patch,'patch_sha256':hashlib.sha256(rendered[patch]).hexdigest()})
    manifest = {'format_version':1,'entries':entries,
        'scope':('Private indexed F407 vendor source profile' if indexed else 'Private F1 vendor source profile')+
            ', FS single CDC, 70-byte SCG TX and 64-byte RX; not an MCU admission list',
        'ownership':'Keep TX ownership on ambiguous LL failure; failed endpoint closure retains class block and blocks reinitialization',
        'ep0':'No shared EP0 owner patch integrated; EP0 and full async lifecycle acceptance remain NOT PROVEN',
        'exceptions':'Vendor fixed callbacks and one static class allocation retained; no heap/runtime registry introduced'}
    rendered['HardwareGenerated/ReviewedNativeBulk/manifest.json'] = json.dumps(manifest,indent=2).encode()
    return rendered,replacements,manifest
