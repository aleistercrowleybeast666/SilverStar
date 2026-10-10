"""Exact private C071 ordinary class retirement; EP0 source stays unchanged."""
import difflib,hashlib,json,re
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.generator.native_usb_data import _FUNCTIONS,_HELPERS

def _Replace(text,name,body):
    start,_opening,end=NativeC_FunctionSpanGet(text,name)
    return text[:start]+body+text[end:]

def C071Lifecycle_Integrate(files,graph):
    entries=[]
    for name in ('usbd_cdc.c','usbd_core.c'):
        original=next(p for p in graph['sources'] if p.endswith('/'+name))
        base=files[original];text=base.decode('utf8')
        if name=='usbd_cdc.c':
            text=text.replace('#include "usbd_cdc.h"','#include "usbd_cdc.h"\n#include "pc_byte_stream.h"',1)
            init=_FUNCTIONS['USBD_CDC_Init'].replace('pdev->pClassData','pdev->pClassDataCmsit[0]').replace('pdev->pUserData','pdev->pUserData[0]')
            init=init.replace('(pdev == NULL)', '((pdev == NULL) || (pdev->classId != 0U))',1)
            init=init.replace('  if (pdev->pClassDataCmsit[0] == NULL)',
                '  pdev->pClassData = pdev->pClassDataCmsit[0];\n  if (pdev->pClassDataCmsit[0] == NULL)',1)
            init=init.replace('  memset(hcdc, 0, sizeof(*hcdc));',
                '  memset(hcdc, 0, sizeof(*hcdc));\n  hcdc->CmdOpCode = 0xFFU;\n  pdev->ep_in[CDC_CMD_EP & 0x0FU].bInterval = CDC_FS_BINTERVAL;')
            text=_Replace(text,'USBD_CDC_Init',init)
            start,_opening,_end=NativeC_FunctionSpanGet(text,'USBD_CDC_Init')
            text=text[:start]+_HELPERS+'\n'+text[start:]
            body=_FUNCTIONS['USBD_CDC_DeInit'].replace('pdev->pClassData','pdev->pClassDataCmsit[0]').replace('pdev->pUserData','pdev->pUserData[0]')
            body=body.replace('if (pdev == NULL)', 'if ((pdev == NULL) || (pdev->classId != 0U))')
            body=body.replace('pdev->pClassDataCmsit[0] = NULL;', 'pdev->pClassDataCmsit[0] = NULL; pdev->pClassData = NULL;')
            body=body.replace('return NativeCdc_Fault(pdev);','pdev->dev_state = USBD_STATE_DEFAULT; PcByteStream_OnUsbReset(); return USBD_FAIL;')
            # Fixed single FS notification endpoint interval is retired only
            # after its actual closure, with the existing is_used flag.
            body=body.replace('pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used = 0U;',
                'pdev->ep_in[CDC_CMD_EP & 0x0FU].is_used = 0U; pdev->ep_in[CDC_CMD_EP & 0x0FU].bInterval = 0U;')
            text=_Replace(text,'USBD_CDC_DeInit',body)
            text,count=re.subn(r'(?m)^static uint8_t CDCCmdEpAdd\s*=\s*CDC_CMD_EP;\r?\n','',text)
            if count!=1:raise ValueError('C071 fixed notification endpoint declaration differs')
        else:
            start,opening,end=NativeC_FunctionSpanGet(text,'USBD_Init')
            text=text[:opening+1]+'''
  if ((pdev == NULL) || (pdev->pClassData != NULL) ||
      (pdev->pClassDataCmsit[0] != NULL)) { return USBD_FAIL; }
'''+text[opening+1:]
            text=_Replace(text,'USBD_Stop','''USBD_StatusTypeDef USBD_Stop(USBD_HandleTypeDef *pdev)
{
  uint8_t class_result = USBD_OK;
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->classId != 0U)) { return USBD_FAIL; }
  pdev->dev_state = USBD_STATE_DEFAULT;
  if (pdev->pClass[0] != NULL)
  { class_result = pdev->pClass[0]->DeInit(pdev, (uint8_t)pdev->dev_config); }
  result = USBD_LL_Stop(pdev);
  return ((class_result == USBD_OK) && (result == USBD_OK)) ? USBD_OK : USBD_FAIL;
}''')
            text=_Replace(text,'USBD_DeInit','''USBD_StatusTypeDef USBD_DeInit(USBD_HandleTypeDef *pdev)
{
  USBD_StatusTypeDef result;
  if ((pdev == NULL) || (pdev->classId != 0U)) { return USBD_FAIL; }
  result = USBD_Stop(pdev);
  /* Keep interface, descriptor and controller binding available for cleanup
   * retry until endpoint/class retirement has actually succeeded. */
  if (result != USBD_OK) { return result; }
  result = USBD_LL_DeInit(pdev);
  if (result != USBD_OK) { return result; }
  pdev->pUserData[0] = NULL;
  pdev->pDesc = NULL;
  pdev->pConfDesc = NULL;
  return USBD_OK;
}''')
        derived='HardwareGenerated/ReviewedC071Lifecycle/'+name
        files[derived]=text.encode()
        patch=derived+'.patch'
        files[patch]=''.join(difflib.unified_diff(base.decode().splitlines(True),text.splitlines(True),fromfile=original,tofile=derived)).encode()
        graph['sources']=[derived if p==original else p for p in graph['sources']]
        entries.append({'original':original,'original_sha256':hashlib.sha256(base).hexdigest(),'derived':derived,'derived_sha256':hashlib.sha256(files[derived]).hexdigest(),'patch':patch,'patch_sha256':hashlib.sha256(files[patch]).hexdigest()})
    files['Generated/c071_lifecycle_manifest.json']=json.dumps({'scope':'Private ordinary Init/DeInit; OpenEP and PrepareReceive errors abort configuration; pending bytes retained on CloseEP failure; cleanup retry, Stop/DeInit result propagation and retained-class reinit refusal','independent_review':'NO_PASSED_OUTCOME','formal_release':False,'entries':entries},indent=2).encode()
    graph['ordinary_lifecycle_derivatives']=entries
    mapping={entry['original']:entry['derived'] for entry in entries}
    graph['vendor_patch_sources']=[mapping.get(p,p) for p in graph['vendor_patch_sources']]
    return entries
