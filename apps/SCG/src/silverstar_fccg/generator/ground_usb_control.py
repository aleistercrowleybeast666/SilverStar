"""Private ordinary integration (independent safety review has no passed outcome).

Provenance: b66f142. Original wording: Audited single-FS-CDC EP0 derivatives; imported silicon and user files stay intact."""
import difflib
import hashlib
import json
import re

from silverstar_fccg.generator.ground_c071_usb import _Function_Replace

LIB = 'HardwareGenerated/STM32CubeMX/Middlewares/ST/STM32_USB_Device_Library/'
REVIEWED = 'HardwareGenerated/ReviewedUsbControl/'
PROFILES = {
    'classic-f103-single-v1': {
        'Class/CDC/Src/usbd_cdc.c': '9bf6b6c49a7faab7bdc465dae5df52bcc878720bd354c8596b51e16d6e210ecb',
        'Core/Src/usbd_core.c': '9696a4d61c9e05cd7989936792b15b88f9b7be567d2a927b4feeb0685f1a73a2',
        'Core/Src/usbd_ioreq.c': 'a89f4e80bb59bcd369fe412b12915ab4392bb110bb54f0b93dd521c43669dbc1',
        'Core/Inc/usbd_def.h': '1fb60258c3705a07f04c32d5b6229a8b8125f90fd72ee06959c098d94485dd05',
        'Core/Inc/usbd_core.h': '5df2712273bfd522fd5164385acc22d6c2fb899b4dc6ed09823a3698e0963c5e',
        'Core/Inc/usbd_ioreq.h': 'b3c4df07bf76dd3371def96c9de53bb2db991f6cecc4601da890641f24376175',
        'Class/CDC/Inc/usbd_cdc.h': '2bc428e2226229a206723d0441d37003a390ceea9acb7825b02dacf3afc05a1e'},
    'classic-f407-indexed-v1': {
        'Class/CDC/Src/usbd_cdc.c': '794a6d0df08fc2b777678b99013f61d0a9c93f5fbeacfaa3466c0feeaa9ada39',
        'Core/Src/usbd_core.c': '21647e3c0537a8d56cd67cc67951206f7a84501acd74d0c8a827c13e192183c5',
        'Core/Src/usbd_ioreq.c': '7df0e6888230c6e0e4af31278853ae1accdf5728288ab2d1a1190a5692157038',
        'Core/Inc/usbd_def.h': '1588736a66291a09de7aa69a5945574566413fefb84c0a7896dc088d174086a9',
        'Core/Inc/usbd_core.h': 'a6c2dfc99fabefe4db7c4c145b4ab87d6b992e3fbd15cc65ecc1c7f9d2086f78',
        'Core/Inc/usbd_ioreq.h': '8a2d44f0cc1c34c21eb75e01cec568b45b901678fba9ca2dc3b0c9a9f0364e7c',
        'Class/CDC/Inc/usbd_cdc.h': '3ea35b19e264217c3bd1d433c75f4e093930ea83cdf63aa88aee77748a9fc7dc'}
}

HEADER = '''#ifndef PC_USB_CONTROL_H
#define PC_USB_CONTROL_H
#include "usbd_def.h"
int8_t PcUsbControl_Control(uint8_t command, uint8_t *data, uint16_t length);
void PcUsbControl_Cancel(USBD_HandleTypeDef *device);
USBD_StatusTypeDef PcUsbControl_Dispatch(USBD_HandleTypeDef *device);
USBD_StatusTypeDef PcUsbControl_Setup(USBD_HandleTypeDef *device, USBD_SetupReqTypedef *request);
USBD_StatusTypeDef PcUsbControl_RxReady(USBD_HandleTypeDef *device);
#endif
'''

POLICY = '''/* SilverStar: bounded single-interface FS CDC control metadata. */
#include "pc_usb_control.h"
#include "usbd_cdc.h"
#include "usbd_cdc_if.h"
#include "usbd_core.h"
#include "usbd_ioreq.h"
#include <string.h>
extern USBD_HandleTypeDef hUsbDeviceFS;
static uint8_t s_line[7] = {0x00,0xC2,0x01,0x00,0U,0U,8U};
/* Native controllers may copy a full actual EP0 packet, despite a 7-byte arm. */
static uint8_t s_control_rx[64];
_Static_assert(USB_MAX_EP0_SIZE == 64U, "reviewed full-speed EP0 capacity");
_Static_assert(sizeof(((USBD_CDC_HandleTypeDef *)0)->data) >= 7U, "CDC response capacity");
static USBD_CDC_HandleTypeDef *ClassData_Get(USBD_HandleTypeDef *device)
{
    if ((device != &hUsbDeviceFS) ||
        (device->dev_state != USBD_STATE_CONFIGURED) || @GUARD@
        (@USER@ != &USBD_Interface_fops_FS)) { return NULL; }
    return (USBD_CDC_HandleTypeDef *)@DATA@;
}
int8_t PcUsbControl_Control(uint8_t command, uint8_t *data, uint16_t length)
{
    if ((command == CDC_SET_LINE_CODING) || (command == CDC_GET_LINE_CODING))
    {
        if ((data == NULL) || (length != sizeof(s_line))) { return USBD_FAIL; }
        if (command == CDC_SET_LINE_CODING)
        {
            if ((data[4] > 2U) || (data[5] > 4U) ||
                !(((data[6] >= 5U) && (data[6] <= 8U)) || (data[6] == 16U)))
            { return USBD_FAIL; }
            memcpy(s_line, data, sizeof(s_line));
        }
        else { memcpy(data, s_line, sizeof(s_line)); }
    }
    else if ((command != CDC_SET_CONTROL_LINE_STATE) || (length != 0U))
    { return USBD_FAIL; }
    return USBD_OK;
}
void PcUsbControl_Cancel(USBD_HandleTypeDef *device)
{
    USBD_CDC_HandleTypeDef *cdc = ClassData_Get(device);
    if (cdc != NULL) { cdc->CmdOpCode = 0xFFU; cdc->CmdLength = 0U; }
}
USBD_StatusTypeDef PcUsbControl_Dispatch(USBD_HandleTypeDef *device)
{
    USBD_StatusTypeDef result = USBD_FAIL;
    if ((ClassData_Get(device) != NULL) && (@CLASS@ == &USBD_CDC))
    {
        result = (USBD_StatusTypeDef)@CLASS@->Setup(device, &device->request);
    }
    if ((result == USBD_OK) && (device->request.wLength == 0U))
    { result = USBD_CtlSendStatus(device); }
    if (result != USBD_OK) { USBD_CtlError(device, &device->request); }
    return result;
}
USBD_StatusTypeDef PcUsbControl_Setup(USBD_HandleTypeDef *device, USBD_SetupReqTypedef *request)
{
    USBD_CDC_HandleTypeDef *cdc = ClassData_Get(device);
    USBD_CDC_ItfTypeDef *interface;
    uint16_t length;
    USBD_StatusTypeDef result;
    if ((cdc == NULL) || (request == NULL)) { return USBD_FAIL; }
    interface = (USBD_CDC_ItfTypeDef *)@USER@;
    PcUsbControl_Cancel(device);
    if ((interface->Control == NULL) || (request->wIndex != 0U)) { return USBD_FAIL; }
    if (request->bRequest == CDC_GET_LINE_CODING)
    {
        if ((request->bmRequest != 0xA1U) || (request->wValue != 0U)) { return USBD_FAIL; }
        if (interface->Control(CDC_GET_LINE_CODING, (uint8_t *)cdc->data, 7U) != USBD_OK)
        { return USBD_FAIL; }
        length = (request->wLength < 7U) ? request->wLength : 7U;
        return (length == 0U) ? USBD_OK : USBD_CtlSendData(device, (uint8_t *)cdc->data, length);
    }
    if (request->bmRequest != 0x21U) { return USBD_FAIL; }
    if (request->bRequest == CDC_SET_LINE_CODING)
    {
        if ((request->wValue != 0U) || (request->wLength != 7U)) { return USBD_FAIL; }
        cdc->CmdOpCode = CDC_SET_LINE_CODING;
        cdc->CmdLength = 7U;
        result = USBD_CtlPrepareRx(device, s_control_rx, 7U);
        if (result != USBD_OK) { PcUsbControl_Cancel(device); }
        return result;
    }
    if ((request->bRequest != CDC_SET_CONTROL_LINE_STATE) ||
        (request->wLength != 0U) || (request->wValue > 3U)) { return USBD_FAIL; }
    return (USBD_StatusTypeDef)interface->Control(CDC_SET_CONTROL_LINE_STATE, (uint8_t *)request, 0U);
}
USBD_StatusTypeDef PcUsbControl_RxReady(USBD_HandleTypeDef *device)
{
    USBD_CDC_HandleTypeDef *cdc = ClassData_Get(device);
    USBD_CDC_ItfTypeDef *interface;
    uint8_t command, length;
    if (cdc == NULL) { return USBD_FAIL; }
    interface = (USBD_CDC_ItfTypeDef *)@USER@;
    command = cdc->CmdOpCode; length = cdc->CmdLength;
    PcUsbControl_Cancel(device);
    if ((command != CDC_SET_LINE_CODING) || (length != 7U) ||
        (device->request.bmRequest != 0x21U) ||
        (device->request.bRequest != CDC_SET_LINE_CODING) ||
        (device->request.wValue != 0U) || (device->request.wIndex != 0U) ||
        (device->request.wLength != 7U) || (interface->Control == NULL) ||
        (USBD_LL_GetRxDataSize(device, 0U) != 7U)) { return USBD_FAIL; }
    return (USBD_StatusTypeDef)interface->Control(command, s_control_rx, length);
}
'''


def _Sha(content):
    return hashlib.sha256(content).hexdigest()


def _Function_Get(source, name):
    marker = '\n/* REVIEWED FUNCTION */\n'
    replaced = _Function_Replace(source, name, marker)
    before, after = replaced.split(marker)
    return source[len(before):len(source)-len(after)]


OWNER_BINDINGS = ('USBD_CDC_ItfTypeDef', 'USBD_Interface_fops_FS', 'hUsbDeviceFS',
    'CDC_Init_FS', 'CDC_DeInit_FS', 'CDC_Control_FS', 'CDC_Receive_FS', 'CDC_TransmitCplt_FS')


def _OwnerTokens_Get(source):
    # C phase-2 splicing precedes comments; quoted literals cannot create fake
    # declarations or conceal real directives using comment-looking content.
    source = source.replace('\\\r\n','').replace('\\\n','')
    token = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|/\*.*?\*/|//[^\n]*'''
    def mask(match):
        value = match[0]
        return (' ' if value.startswith('/') else '__C_LITERAL__') + '\n'*value.count('\n')
    return re.sub(token,mask,source,flags=re.S)


def _CallbackOwner_Validate(source, indexed):
    clean = _OwnerTokens_Get(source)
    aliases = r'(?m)^\s*#\s*(?:define|undef)\s+(?:' + '|'.join(OWNER_BINDINGS) + r')\b'
    if re.search(aliases, clean):
        raise ValueError('USB EP0 repair refuses interface/function owner macro aliases')
    owners = re.findall(r'(?m)^\s*USBD_CDC_ItfTypeDef\s+USBD_Interface_fops_FS\s*=\s*\{([^{}]*)\}\s*;',clean,re.S)
    fields = ['CDC_Init_FS','CDC_DeInit_FS','CDC_Control_FS','CDC_Receive_FS']
    if indexed: fields.append('CDC_TransmitCplt_FS')
    exact = r'\s*' + r'\s*,\s*'.join(fields) + r'\s*,?\s*'
    if len(owners) != 1 or re.fullmatch(exact, owners[0]) is None:
        raise ValueError('USB EP0 repair requires exact interface initializer fields; expressions, aliases and unknown owners refused')
    if re.search(r'(?m)^\s*extern\s+USBD_HandleTypeDef\s+hUsbDeviceFS\s*;',clean) is None:
        raise ValueError('USB EP0 repair requires exact FS device declaration')


def NativeControl_Definitions_Validate(defines):
    if any(value.split('=',1)[0].split('(',1)[0].strip() in (*OWNER_BINDINGS,'USE_USBD_COMPOSITE') for value in defines):
        raise ValueError('USB EP0 repair refuses composite or interface/function owner build aliases')


def NativeControl_Integrate(files, callback_path, original_callback, *, library_prefix=LIB, reviewed_prefix=REVIEWED):
    LIB=library_prefix
    REVIEWED=reviewed_prefix
    hashes = {path: _Sha(files.get(LIB + path, b'')) for path in next(iter(PROFILES.values()))}
    matches = [name for name, expected in PROFILES.items() if hashes == expected]
    if len(matches) != 1:
        raise ValueError('USB EP0 repair refuses unreviewed class/core/I/O byte identity; native files retained')
    profile = matches[0]
    indexed = profile == 'classic-f407-indexed-v1'
    if any(re.search(rb'(?m)^\s*#\s*define\s+USE_USBD_COMPOSITE\b', data)
           for path, data in files.items() if path.endswith('.h')):
        raise ValueError('USB EP0 repair supports one classic FS CDC, not composite ownership')
    source = files[callback_path].decode('utf-8-sig').replace('\r\n', '\n')
    control = _Function_Get(source, 'CDC_Control_FS')
    body = control[control.index('{')+1:control.rindex('}')]
    body = _OwnerTokens_Get(body)
    empty = '''switch(cmd){case CDC_SEND_ENCAPSULATED_COMMAND:break;case CDC_GET_ENCAPSULATED_RESPONSE:break;
case CDC_SET_COMM_FEATURE:break;case CDC_GET_COMM_FEATURE:break;case CDC_CLEAR_COMM_FEATURE:break;
case CDC_SET_LINE_CODING:break;case CDC_GET_LINE_CODING:break;case CDC_SET_CONTROL_LINE_STATE:break;
case CDC_SEND_BREAK:break;default:break;}return(USBD_OK);'''
    if re.sub(r'\s+', '', body) != re.sub(r'\s+', '', empty):
        raise ValueError('USB EP0 repair refuses nonempty or unfamiliar user CDC_Control_FS; preserve user policy')
    _CallbackOwner_Validate(source, indexed)
    aliases = r'(?m)^\s*#\s*(?:define|undef)\s+(?:' + '|'.join(OWNER_BINDINGS) + r')\b'
    for path, content in files.items():
        if path.endswith('.h'):
            clean = _OwnerTokens_Get(content.decode('utf-8-sig'))
            if re.search(aliases, clean):
                raise ValueError('USB EP0 repair refuses owner aliases in header: ' + path)
    replacements = {}
    records = []
    for relative in hashes:
        if not relative.endswith('.c'): continue
        path = LIB + relative
        original = files[path]
        text = original.decode().replace('\r\n', '\n')
        text = text.replace('#include "usbd_cdc.h"', '#include "usbd_cdc.h"\n#include "pc_usb_control.h"', 1) if relative.startswith('Class/') else text.replace('#include "usbd_core.h"', '#include "usbd_core.h"\n#include "pc_usb_control.h"', 1)
        if relative.endswith('usbd_cdc.c'):
            if not indexed:
                # Old F1 Init leaves command fields in reused class memory.
                # Reset them before its actual interface Init/reconfiguration.
                marker = '    hcdc = (USBD_CDC_HandleTypeDef *) pdev->pClassData;'
                if text.count(marker) != 1: raise ValueError('unreviewed F1 class initialization')
                text = text.replace(marker,marker+'\n    hcdc->CmdOpCode = 0xFFU;\n    hcdc->CmdLength = 0U;',1)
            setup = _Function_Get(text, 'USBD_CDC_Setup')
            setup, count = re.subn(r'case USB_REQ_TYPE_CLASS\s*:\n.*?\n\s*break;',
                'case USB_REQ_TYPE_CLASS:\n      return (uint8_t)PcUsbControl_Setup(pdev, req);', setup, count=1, flags=re.S)
            if count != 1: raise ValueError('unreviewed CDC Setup class branch')
            setup = setup.replace('  uint16_t len;\n', '')
            if not indexed: setup = setup.replace('  USBD_CDC_HandleTypeDef   *hcdc = (USBD_CDC_HandleTypeDef *) pdev->pClassData;\n', '')
            text = _Function_Replace(text, 'USBD_CDC_Setup', setup)
            text = _Function_Replace(text, 'USBD_CDC_EP0_RxReady', 'static uint8_t USBD_CDC_EP0_RxReady(USBD_HandleTypeDef *pdev)\n{\n  return (uint8_t)PcUsbControl_RxReady(pdev);\n}')
        elif relative.endswith('usbd_core.c'):
            marker = '  pdev->ep0_data_len = pdev->request.wLength;'
            text = text.replace(marker, marker + '''
  PcUsbControl_Cancel(pdev);
  if ((pdev->request.bmRequest & USB_REQ_TYPE_MASK) == USB_REQ_TYPE_CLASS)
  { return PcUsbControl_Dispatch(pdev); }''', 1)
            if indexed:
                start = text.index('        if (idx < USBD_MAX_SUPPORTED_CLASS)', text.index('USBD_StatusTypeDef USBD_LL_DataOutStage'))
                end = text.index('        (void)USBD_CtlSendStatus(pdev);', start) + len('        (void)USBD_CtlSendStatus(pdev);')
                replacement = '''        ret = USBD_FAIL;
        if ((idx < USBD_MAX_SUPPORTED_CLASS) && (pdev->dev_state == USBD_STATE_CONFIGURED) &&
            (pdev->pClass[idx] != NULL) && (pdev->pClass[idx]->EP0_RxReady != NULL))
        { pdev->classId = idx; ret = (USBD_StatusTypeDef)pdev->pClass[idx]->EP0_RxReady(pdev); }
        if (ret != USBD_OK) { USBD_CtlError(pdev, &pdev->request); return ret; }
        ret = USBD_CtlSendStatus(pdev);
        if (ret != USBD_OK) { USBD_CtlError(pdev, &pdev->request); return ret; }'''
            else:
                start = text.index('        if ((pdev->pClass->EP0_RxReady != NULL)', text.index('USBD_StatusTypeDef USBD_LL_DataOutStage'))
                end = text.index('        USBD_CtlSendStatus(pdev);', start) + len('        USBD_CtlSendStatus(pdev);')
                replacement = '''        if ((pdev->dev_state != USBD_STATE_CONFIGURED) || (pdev->pClass == NULL) ||
            (pdev->pClass->EP0_RxReady == NULL) || (pdev->pClass->EP0_RxReady(pdev) != USBD_OK))
        { USBD_CtlError(pdev, &pdev->request); return USBD_FAIL; }
        USBD_StatusTypeDef status = USBD_CtlSendStatus(pdev);
        if (status != USBD_OK) { USBD_CtlError(pdev, &pdev->request); }
        return status;'''
            text = text[:start] + replacement + text[end:]
            text, count = re.subn(r'(?:\(void\))?USBD_CtlReceiveStatus\(pdev\);',
                'if (USBD_CtlReceiveStatus(pdev) != USBD_OK)\n          { USBD_CtlError(pdev, &pdev->request); return USBD_FAIL; }', text)
            if count != 1: raise ValueError('unreviewed EP0 status receive call')
        else:
            for name, ll in [('USBD_CtlSendData', 'USBD_LL_Transmit'), ('USBD_CtlPrepareRx', 'USBD_LL_PrepareReceive'), ('USBD_CtlSendStatus', 'USBD_LL_Transmit'), ('USBD_CtlReceiveStatus', 'USBD_LL_PrepareReceive')]:
                function = _Function_Get(text, name)
                function, count = re.subn(r'(?:\(void\))?'+ll+r'\(([^;]+)\);\s*return USBD_OK;', r'return '+ll+r'(\1);', function)
                if count != 1: raise ValueError('unreviewed EP0 LL result: '+name)
                text = _Function_Replace(text, name, function)
        derived = REVIEWED + relative
        patch_path = REVIEWED + 'Patches/' + relative.rsplit('/', 1)[1] + '.patch'
        payload = text.encode()
        patch = ''.join(difflib.unified_diff(original.decode().replace('\r\n', '\n').splitlines(True), text.splitlines(True), fromfile=path, tofile=derived)).encode()
        files[derived] = payload; files[patch_path] = patch
        records.append({'original_path':path,'original_sha256':_Sha(original), 'derived_path':derived,
                        'derived_sha256':_Sha(payload), 'patch_path':patch_path,'patch_sha256':_Sha(patch)})
        replacements[path] = derived
    source = source.replace('#include "usbd_cdc_if.h"', '#include "usbd_cdc_if.h"\n#include "pc_usb_control.h"', 1)
    source = _Function_Replace(source, 'CDC_Control_FS', '''static int8_t CDC_Control_FS(uint8_t cmd, uint8_t *pbuf, uint16_t length)
{
  return PcUsbControl_Control(cmd, pbuf, length);
}''')
    # Native ST/user callback remains a tracked derivative. Only its empty
    # Control trampoline is replaced; all policy compiles from Generated with
    # unchanged first-party strict/analyzer/Power10 coverage.
    callback_owned = REVIEWED + 'App/usbd_cdc_if.c'
    files[callback_path] = original_callback
    files[callback_owned] = source.encode()
    callback_patch = REVIEWED + 'Patches/usbd_cdc_if.c.patch'
    files[callback_patch] = ''.join(difflib.unified_diff(original_callback.decode('utf-8-sig').replace('\r\n', '\n').splitlines(True), source.splitlines(True), fromfile=callback_path, tofile=callback_owned)).encode()
    replacements[callback_path] = callback_owned
    policy = POLICY.replace('@GUARD@', '(device->classId != 0U) ||' if indexed else '').replace('@USER@', 'device->pUserData[0]' if indexed else 'device->pUserData').replace('@DATA@', 'device->pClassDataCmsit[0]' if indexed else 'device->pClassData').replace('@CLASS@', '(device->pClass[0])' if indexed else '(device->pClass)')
    files['Generated/Inc/pc_usb_control.h'] = HEADER.encode()
    files['Generated/Src/pc_usb_control.c'] = policy.encode()
    manifest = {'profile':profile,'scope':'single classic FS CDC interface 0; experimental software repair',
        'owner':'SilverStar Ground EP0 integration', 'reason':'fresh bounded GET; validate SET actual count; propagate callback/LL failure',
        'native_bottom_layer_ownership':'unchanged imported HAL/PCD/CMSIS/startup/linker; one stack',
        'vendor_patches':records, 'callback_original_path':callback_path,
        'reviewed_native_inventory_sha256':{LIB+path:digest for path,digest in hashes.items()},
        'callback_original_sha256':_Sha(original_callback), 'callback_derived_path':callback_owned,
        'callback_derived_sha256':_Sha(files[callback_owned]),
        'callback_patch_path':callback_patch, 'callback_patch_sha256':_Sha(files[callback_patch]),
        'owned_files_sha256':{path:_Sha(files[path]) for path in ['Generated/Inc/pc_usb_control.h','Generated/Src/pc_usb_control.c']}}
    files['Generated/usb_control_manifest.json'] = (json.dumps(manifest,indent=2)+'\n').encode()
    return replacements
