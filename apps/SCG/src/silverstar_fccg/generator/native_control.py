"""F103 ordinary control integration composed with existing native bulk fixes.

No independent USB security acceptance is asserted. Original ST inputs remain
unchanged; combined derivatives and original-to-final patches are recorded.
"""
import hashlib, json, difflib
from silverstar_fccg.generator.ground_usb_control import NativeControl_Integrate,NativeControl_Definitions_Validate
from silverstar_fccg.generator.native_usb_data import _FUNCTIONS,_HELPERS
from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.hardware.native_classic_cdc import NATIVE_PREFIX

def _Replace(source,name,replacement):
    start,_opening,end=NativeC_FunctionSpanGet(source,name)
    return source[:start]+replacement+source[end:]

def NativeF103Control_Integrate(files,native,proof,replacements,callback_owned,bulk):
    callback=proof['cdc']['owners']['usbd_cdc_if.c']
    temporary={NATIVE_PREFIX+p:b for p,b in native.items()}
    temporary[NATIVE_PREFIX+callback]=files[callback_owned]
    changed=NativeControl_Integrate(temporary,NATIVE_PREFIX+callback,native[callback],
        library_prefix=NATIVE_PREFIX+'Middlewares/ST/STM32_USB_Device_Library/',
        reviewed_prefix='HardwareGenerated/ReviewedNativeControl/')
    NativeControl_Definitions_Validate(proof['build']['defines'])
    manifest=json.loads(temporary['Generated/usb_control_manifest.json'])
    for name in ('usbd_cdc.c','usbd_core.c'):
        original=proof['cdc']['owners'][name]
        path=changed[NATIVE_PREFIX+original]
        text=temporary[path].decode()
        bulk_text=files[replacements[NATIVE_PREFIX+original]].decode()
        if name=='usbd_cdc.c':
            text=text.replace('#include "usbd_cdc.h"','#include "usbd_cdc.h"\n#include "pc_byte_stream.h"\n#include <string.h>',1)
            for function,replacement in _FUNCTIONS.items():
                if function=='USBD_CDC_Init':
                    replacement=replacement.replace('  memset(hcdc, 0, sizeof(*hcdc));','  memset(hcdc, 0, sizeof(*hcdc));\n  hcdc->CmdOpCode = 0xFFU;')
                text=_Replace(text,function,replacement)
            start,_opening,_end=NativeC_FunctionSpanGet(text,'USBD_CDC_Init')
            text=text[:start]+_HELPERS+'\n'+text[start:]
        else:
            for function in ('USBD_Init','USBD_Start','USBD_ClrClassConfig','USBD_Stop'):
                start,_opening,end=NativeC_FunctionSpanGet(bulk_text,function)
                text=_Replace(text,function,bulk_text[start:end])
            text=_Replace(text,'USBD_DeInit',"""USBD_StatusTypeDef USBD_DeInit(USBD_HandleTypeDef *pdev)
{
  USBD_StatusTypeDef result;
  if (pdev == NULL) { return USBD_FAIL; }
  result = USBD_Stop(pdev);
  if (result != USBD_OK) { return result; }
  return USBD_LL_DeInit(pdev);
}""")
            start,opening,end=NativeC_FunctionSpanGet(text,'USBD_Init')
            text=text[:opening+1]+"\n  if ((pdev == NULL) || (pdev->pClassData != NULL)) { return USBD_FAIL; }\n"+text[opening+1:]
            for function in ('USBD_LL_Reset', 'USBD_LL_DevDisconnected'):
                start, _opening, end = NativeC_FunctionSpanGet(text, function)
                body = text[start:end]
                old = 'pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config);'
                if body.count(old) != 1:
                    raise ValueError('F103 ordinary cleanup return owner differs')
                body = body.replace(old,
                    'uint8_t result = pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config);\n'
                    '    return (result == USBD_OK) ? USBD_OK :\n'
                    '        ((result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL);', 1)
                text = text[:start] + body + text[end:]
            for stage in ('DataIn','DataOut'):
                old='    pdev->pClass->'+stage+'(pdev, epnum);'
                new=('    uint8_t result = pdev->pClass->'+stage+'(pdev, epnum);\n'
                     '    return (result == USBD_OK) ? USBD_OK :\n'
                     '        ((result == USBD_BUSY) ? USBD_BUSY : USBD_FAIL);')
                if text.count(old)!=1:raise ValueError('F103 bulk/control composition owner differs')
                text=text.replace(old,new,1)
        temporary[path]=text.encode()
        entry=next(e for e in manifest['vendor_patches'] if e['derived_path']==path)
        patch=''.join(difflib.unified_diff(native[original].decode().replace('\r\n','\n').splitlines(True),
            text.splitlines(True),fromfile=entry['original_path'],tofile=path)).encode()
        temporary[entry['patch_path']]=patch
        entry['derived_sha256']=hashlib.sha256(temporary[path]).hexdigest()
        entry['patch_sha256']=hashlib.sha256(patch).hexdigest()
        bulk_entry=next(e for e in bulk['entries'] if e['original']==NATIVE_PREFIX+original)
        bulk_entry.update(derived=path,derived_sha256=entry['derived_sha256'],
            patch=entry['patch_path'],patch_sha256=entry['patch_sha256'])
    manifest.update(independent_review='NO_PASSED_OUTCOME',formal_release=False,
        bulk_composition='Existing native bulk init/deinit/LL failure and session ownership retained')
    temporary['Generated/usb_control_manifest.json']=json.dumps(manifest,indent=2).encode()
    files.update({p:b for p,b in temporary.items() if p.startswith(('Generated/','HardwareGenerated/ReviewedNativeControl/'))})
    replacements.update(changed)
    bulk['ep0']='Shared F103 control ordinary code integrated; independent safety review has NO PASSED OUTCOME; complete EP0/async lifecycle NOT PROVEN'
    files['HardwareGenerated/ReviewedNativeBulk/manifest.json']=json.dumps(bulk,indent=2).encode()
    return manifest
