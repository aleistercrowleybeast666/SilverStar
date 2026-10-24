"""Opt-in source-bound classic CDC integration; never edits the native input.

Bulk derivatives reuse the existing checked vendor transformations, then bind
the independent transport. Complete EP0 behavior remains NOT PROVEN.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import PurePosixPath
import re

from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
from silverstar_fccg.hardware.usb_transport_profiles import PROFILES, COMPONENT_PROFILES


def _Replace(source: str, name: str, body: str) -> str:
    start, _opening, end = NativeC_FunctionSpanGet(source, name)
    return source[:start] + body + source[end:]


def _Insert(source: str, name: str, insertion: str) -> str:
    _start, opening, _end = NativeC_FunctionSpanGet(source, name)
    return source[:opening + 1] + "\n" + insertion + source[opening + 1:]


def UsbIntegrationProfile_Get(files: dict[str, bytes]) -> dict:
    hashes = {p: hashlib.sha256(b).hexdigest() for p, b in sorted(files.items())}
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if fingerprint in PROFILES:
        return {**PROFILES[fingerprint], "fingerprint": fingerprint, "binding": "EXACT_REFERENCE"}
    def owner(name):
        matches = [p for p in files if PurePosixPath(p).name == name]
        if len(matches) != 1:
            raise ValueError("UNREVIEWED_LIFECYCLE_SOURCE: ambiguous component " + name)
        return matches[0]
    for profile in COMPONENT_PROFILES:
        if any(hashlib.sha256(files[owner(name)]).hexdigest() != expected
               for name, expected in profile['files'].items() if any(PurePosixPath(p).name == name for p in files)):
            continue
        if any(not any(PurePosixPath(p).name == name for p in files) for name in profile['files']):
            continue
        try:
            for key, expected in profile['regions'].items():
                filename, function = key.split(':')
                source = files[owner(filename)].decode('utf-8-sig').replace('\r\n', '\n').replace(
                    '#endif /* USE_HAL_PCD_REGISTER_CALLBACKS */', '')
                start, _opening, end = NativeC_FunctionSpanGet(source, function)
                if hashlib.sha256(source[start:end].encode()).hexdigest() != expected:
                    raise ValueError('edited hook ' + key)
            conf = files[owner('usbd_conf.c')].decode('utf-8-sig')
            if len(re.findall(r'\b' + profile['pcd'] + r'\.Instance\s*=\s*' + profile['instance'] + r'\s*;', conf)) != 1:
                raise ValueError('controller/PCD binding')
            main = files[owner('main.c')].decode('utf-8-sig')
            region = re.findall(r'/\* USER CODE BEGIN 3 \*/(.*?)/\* USER CODE END 3 \*/', main, re.S)
            if (len(region) != 1 or not re.fullmatch(r'\s*}\s*', region[0]) or
                    main.count('/* USER CODE BEGIN Includes */') != 1):
                raise ValueError('main service region already user-owned')
            from silverstar_fccg.hardware.usb_transport_capabilities import UsbBuild_Inspect, UsbCode_Read
            build, reasons = UsbBuild_Inspect(files)
            if reasons:
                raise ValueError('unresolved build inventory')
            for path in build['sources']:
                if PurePosixPath(path).name != 'usbd_cdc_if.c' and not any(
                        p.casefold() in {'drivers', 'middlewares'} for p in PurePosixPath(path).parts):
                    if re.search(r'\bCDC_Transmit_FS\s*\(', UsbCode_Read(files[path])):
                        raise ValueError('existing application TX writer ' + path)
        except (ValueError, UnicodeError) as error:
            raise ValueError('UNREVIEWED_LIFECYCLE_SOURCE: ' + str(error)) from error
        return {key: profile[key] for key in ('name', 'indexed', 'pcd', 'controller_contract')} | {
            'fingerprint': fingerprint, 'binding': 'REVIEWED_COMPONENTS_AND_HOOK_REGIONS',
            'configuration_authority': 'CUBEMX_USER_INPUT', 'compiled_and_hardware_acceptance': 'NOT_PROVEN'}
    raise ValueError("UNREVIEWED_LIFECYCLE_SOURCE: unknown middleware/HAL component; generic kit and adaptation audit remain available")


def _Bulk_Derive(original: bytes, indexed: bool) -> str:
    if indexed:
        from silverstar_fccg.generator.native_usb_indexed import NativeUsbIndexedData_Derive
        source = NativeUsbIndexedData_Derive(original).decode()
        # The borrowed guard is redundant with capability admission, the
        # retained one-slot static assertion and the pinned header's incompatible
        # composite API. Keep those real constraints and the native conditionals.
        guard = ('#ifdef USE_USBD_COMPOSITE\n'
            '#error "Private indexed CDC profile requires a single non-composite class"\n#endif\n')
        if source.count(guard) != 1:
            raise ValueError('Unreviewed indexed compile-time guard owner')
        source = source.replace(guard, '', 1)
    else:
        from silverstar_fccg.generator.native_usb_data import NativeUsbData_Derive
        source = NativeUsbData_Derive(original).decode()
    source = source.replace('#include "pc_byte_stream.h"', '#include "usb_cdc_transport.h"')
    source = source.replace('#include "native_runtime.h"\n', '')
    source = source.replace('NativeRuntime_TransportFaultRecord(); ', '')
    source = source.replace('PcByteStream_OnUsbReset()', 'UsbCdc_LinkDown()')
    source = source.replace('length > 70U', 'length > USB_CDC_TX_CAPACITY')
    source = source.replace('hcdc->TxLength > 70U', 'hcdc->TxLength > USB_CDC_TX_CAPACITY')
    source = source.replace('maximum 70-byte GSP frame', 'bounded transport chunk')
    source = _Insert(source, 'USBD_CDC_DeInit', '  UsbCdc_LinkDown();\n')
    start, _opening, end = NativeC_FunctionSpanGet(source, 'USBD_CDC_DeInit')
    body = source[start:end]
    anchor = '  return result;'
    if body.count(anchor) != 1:
        raise ValueError('Unreviewed class retirement shape')
    body = body.replace(anchor, '  if (UsbCdc_Quiesced() != USB_CDC_OK) { return USBD_FAIL; }\n' + anchor)
    return source[:start] + body + source[end:]


def _Core_Derive(original: bytes, indexed: bool) -> str:
    if indexed:
        from silverstar_fccg.generator.native_usb_indexed import NativeUsbIndexedCore_Derive
        source = NativeUsbIndexedCore_Derive(original).decode()
    else:
        from silverstar_fccg.generator.native_usb_data import NativeUsbCore_Derive
        source = NativeUsbCore_Derive(original).decode()
    source = source.replace('#include "native_runtime.h"', '#include "usb_cdc_transport.h"')
    if '#include "usb_cdc_transport.h"' not in source:
        source = source.replace('#include "usbd_core.h"', '#include "usbd_core.h"\n#include "usb_cdc_transport.h"')
    source = source.replace('NativeRuntime_TransportFaultRecord()', 'UsbCdc_LinkDown()')
    source = source.replace('#include "usb_cdc_transport.h"', '#include "usb_cdc_transport.h"\n#include "usb_device.h"\nextern USBD_HandleTypeDef hUsbDeviceFS;', 1)
    source = source.replace('#include "usb_cdc_transport.h"', '#include "usb_cdc_transport.h"\n#include "usb_cdc_retire.h"', 1)
    class_data = 'pdev->pClass[0]' if indexed else 'pdev->pClass'
    guard = '(pdev->classId != 0U) || ' if indexed else ''
    source = _Replace(source, 'USBD_SetClassConfig', '''USBD_StatusTypeDef USBD_SetClassConfig(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  if ((pdev != &hUsbDeviceFS) || @GUARD@(@CLASS@ == NULL) ||
      (@CLASS@->Init == NULL))
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return USBD_FAIL; }
  if (UsbCdcRetire_ConfigurationCheck(pdev) != USB_CDC_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; return USBD_FAIL; }
  if (@CLASS@->Init(pdev, cfgidx) != USBD_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return USBD_FAIL; }
  /* Init has opened the endpoints and checked the initial receive arm. */
  if (UsbCdc_Configure() != USB_CDC_OK)
  { pdev->dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return USBD_FAIL; }
  return USBD_OK;
}'''.replace('@GUARD@', guard).replace('@CLASS@', class_data))
    source = _Replace(source, 'USBD_ClrClassConfig', '''USBD_StatusTypeDef USBD_ClrClassConfig(USBD_HandleTypeDef *pdev, uint8_t cfgidx)
{
  UsbCdc_LinkDown();
  if ((pdev != &hUsbDeviceFS) || @GUARD@(@CLASS@ == NULL) ||
      (@CLASS@->DeInit == NULL)) { return USBD_FAIL; }
  return (@CLASS@->DeInit(pdev, cfgidx) == USBD_OK) ? USBD_OK : USBD_FAIL;
}'''.replace('@GUARD@', guard).replace('@CLASS@', class_data))
    for name in ('USBD_Stop', 'USBD_LL_Reset', 'USBD_LL_DevDisconnected', 'USBD_LL_Suspend'):
        source = _Insert(source, name, '  if (pdev != &hUsbDeviceFS) { return USBD_FAIL; }\n  UsbCdc_LinkDown();\n')
    for name in ('USBD_Stop', 'USBD_LL_Reset', 'USBD_LL_DevDisconnected'):
        contract = ('  if ((pdev != &hUsbDeviceFS) || ' + guard + '(' + class_data + ' == NULL) ||\n'
            '      (' + class_data + '->DeInit == NULL))\n'
            '  { UsbCdc_LinkDown(); return USBD_FAIL; }\n')
        source = _Insert(source, name, contract)
    if not indexed:
        for name in ('USBD_LL_Reset', 'USBD_LL_DevDisconnected'):
            start, _opening, end = NativeC_FunctionSpanGet(source, name)
            body = source[start:end]
            old = 'pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config);'
            if body.count(old) != 1:
                raise ValueError('Unreviewed core class cleanup shape')
            body = body.replace(old, 'if (pdev->pClass->DeInit(pdev, (uint8_t)pdev->dev_config) != USBD_OK)\n    { return USBD_FAIL; }')
            source = source[:start] + body + source[end:]
    source = _Replace(source, 'USBD_DeInit', '''USBD_StatusTypeDef USBD_DeInit(USBD_HandleTypeDef *pdev)
{
  if (pdev != &hUsbDeviceFS) { return USBD_FAIL; }
  if (USBD_Stop(pdev) != USBD_OK) { return USBD_FAIL; }
  return USBD_LL_DeInit(pdev);
}''')
    # Resume keeps the transport offline; only a fresh reset/configuration may
    # retire the old transfer and create a new session. No timeout-based release.
    return source


def _Interface_Derive(original: bytes) -> str:
    source = original.decode('utf-8-sig')
    source = source.replace('#include "usbd_cdc_if.h"', '#include "usbd_cdc_if.h"\n#include "usb_cdc_transport.h"\n#include <stddef.h>')
    source = _Replace(source, 'CDC_Init_FS', '''static int8_t CDC_Init_FS(void)
{
  _Static_assert(sizeof(UserRxBufferFS) >= USB_CDC_PACKET_SIZE,
      "native CDC RX buffer must fit the armed packet");
  if (USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0U) != USBD_OK)
  { return (int8_t)USBD_FAIL; }
  if (USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS) != USBD_OK)
  { return (int8_t)USBD_FAIL; }
  return (int8_t)USBD_OK;
}''')
    source = _Replace(source, 'CDC_DeInit_FS', '''static int8_t CDC_DeInit_FS(void)
{
  UsbCdc_LinkDown();
  /* Class DeInit owns checked endpoint closure and transport retirement. */
  return (int8_t)USBD_OK;
}''')
    source = _Replace(source, 'CDC_Receive_FS', '''static int8_t CDC_Receive_FS(uint8_t *data, uint32_t *length)
{
  if ((length == NULL) || (*length > USB_CDC_PACKET_SIZE) ||
      (UsbCdc_Receive(data, (uint16_t)*length) != USB_CDC_OK))
  { UsbCdc_LinkDown(); return (int8_t)USBD_FAIL; }
  /* Service alone rearms when a whole packet fits. */
  return (int8_t)USBD_OK;
}''')
    source = _Replace(source, 'CDC_Transmit_FS', '''uint8_t CDC_Transmit_FS(uint8_t *data, uint16_t length)
{
  uint8_t result = USBD_CDC_SetTxBuffer(&hUsbDeviceFS, data, length);
  if (result != USBD_OK) { return result; }
  return USBD_CDC_TransmitPacket(&hUsbDeviceFS);
}''')
    return source


def _Ll_Derive(original: bytes, indexed: bool, pcd: str) -> str:
    # Keep native clock/PMA/FIFO setup; do not import the older private F407
    # derivative's changed FIFO layout into a generic transport kit.
    source = original.decode('utf-8-sig')
    class_guard = ('(hUsbDeviceFS.classId != 0U) || (hUsbDeviceFS.pClass[0] == NULL)'
        if indexed else 'hUsbDeviceFS.pClass == NULL')
    source = source.replace('#include "usbd_cdc.h"', '#include "usbd_cdc.h"\n#include "usb_cdc_transport.h"\n#include "usb_cdc_retire.h"')
    source = _Replace(source, 'USBD_LL_CloseEP', '''USBD_StatusTypeDef USBD_LL_CloseEP(USBD_HandleTypeDef *pdev, uint8_t ep_addr)
{
  return (UsbCdcRetire_Endpoint(pdev, ep_addr) == USB_CDC_OK) ? USBD_OK : USBD_FAIL;
}''')
    for direction, array, maximum in (('DataIn', 'IN', 2), ('DataOut', 'OUT', 1)):
        old = ('  USBD_LL_' + direction + 'Stage((USBD_HandleTypeDef*)hpcd->pData, epnum, '
            'hpcd->' + array + '_ep[epnum].xfer_buff);')
        if source.count(old) != 1:
            raise ValueError('Unreviewed native data callback: ' + direction)
        new = ('''  if ((hpcd != &@PCD@) || (hpcd->pData != &hUsbDeviceFS) || (epnum > @MAX@U))
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return; }
  if (@CLASS_GUARD@)
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); return; }
  if (USBD_LL_@DIR@Stage(&hUsbDeviceFS, epnum, hpcd->@ARRAY@_ep[epnum].xfer_buff) != USBD_OK)
  { hUsbDeviceFS.dev_state = USBD_STATE_DEFAULT; UsbCdc_LinkDown(); }'''.replace('@PCD@', pcd)
            .replace('@MAX@', str(maximum)).replace('@DIR@', direction).replace('@ARRAY@', array)
            .replace('@CLASS_GUARD@', class_guard))
        source = source.replace(old, new, 1)
    source = source.replace('#include "usb_cdc_retire.h"', '#include "usb_cdc_retire.h"\n'
        'extern USBD_HandleTypeDef hUsbDeviceFS;\n'
        '_Static_assert(USE_HAL_PCD_REGISTER_CALLBACKS == 0U, "USB integration requires fixed callbacks");', 1)
    # Existing CubeMX wrappers propagate HAL returns. Preserve their signatures.
    # LL init remains vendor-owned; faults in PMA/FIFO/init are not certified.
    return source


RETIRE_HEADER = '''#ifndef __USB_CDC_RETIRE_H
#define __USB_CDC_RETIRE_H
#include "usb_cdc_transport.h"
#include "usbd_def.h"
UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device);
UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device, uint8_t address);
#endif
'''

RETIRE_SOURCE = '''#include "usb_cdc_retire.h"
#include "usb_cdc_port.h"
#include "usb_device.h"
#include "main.h"
#include "usbd_cdc.h"
#include <stddef.h>
extern PCD_HandleTypeDef @PCD@;
extern USBD_HandleTypeDef hUsbDeviceFS;
_Static_assert((CDC_IN_EP == 0x81U) && (CDC_OUT_EP == 0x01U) && (CDC_CMD_EP == 0x82U),
    "Reviewed controller retirement requires the declared single CDC endpoints");

@CONFIG@

UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device)
{
    uint32_t token = UsbCdcPort_Lock();
    UsbCdcResult result = USB_CDC_INVALID;
    if ((device == &hUsbDeviceFS) && (device->pData == &@PCD@) &&
        (@PCD@.Instance == @INSTANCE@))
    { result = UsbCdcRetire_MemoryCheck(); }
    if (result != USB_CDC_OK) { UsbCdc_LinkDown(); }
    UsbCdcPort_Unlock(token);
    return result;
}

/* Separate the controller postcondition from the shared ownership transition.
 * Called with interrupts masked, after checked HAL abort and close. */
static UsbCdcResult UsbCdcRetire_HardwareFinish(uint8_t address)
{
    uint8_t number = address & 0x7FU;
@CLEAR@
    return USB_CDC_OK;
}

UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device, uint8_t address)
{
    PCD_EPTypeDef *ep;
    uint32_t token;
    uint8_t number = address & 0x7FU;
    if ((device != &hUsbDeviceFS) || (device->pData != &@PCD@) ||
        ((address != 0x81U) && (address != 0x01U) && (address != 0x82U)))
    { return USB_CDC_INVALID; }
    token = UsbCdcPort_Lock();
    ep = ((address & 0x80U) != 0U) ? &@PCD@.IN_ep[number] : &@PCD@.OUT_ep[number];
    if ((HAL_PCD_EP_Abort(&@PCD@, address) != HAL_OK) ||
        (HAL_PCD_EP_Close(&@PCD@, address) != HAL_OK))
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    if (UsbCdcRetire_HardwareFinish(address) != USB_CDC_OK)
    { UsbCdcPort_Unlock(token); return USB_CDC_FAULT; }
    /* No DMA in these exact profiles. Disabled endpoints cannot consume more
     * CPU source bytes; clear pending completion and stale software pointers. */
    ep->xfer_buff = NULL;
    ep->xfer_len = 0U;
    ep->xfer_count = 0U;
    UsbCdcPort_Unlock(token);
    return USB_CDC_OK;
}
'''


def UsbCdcIntegration_Render(files: dict[str, bytes], owners: dict[str, str]) -> dict[str, bytes]:
    profile = UsbIntegrationProfile_Get(files)
    indexed = profile['indexed']
    expected_controller = 'otg-fs-f4-cpu-v1' if indexed else 'pma-f1-single-v1'
    if profile.get('controller_contract') != expected_controller:
        raise ValueError('UNREVIEWED_CONTROLLER_ADAPTER: memory and cancellation implementation required')
    pcd = profile['pcd']
    derived = {
        'usbd_cdc.c': _Bulk_Derive(files[owners['usbd_cdc.c']], indexed),
        'usbd_core.c': _Core_Derive(files[owners['usbd_core.c']], indexed),
        'usbd_cdc_if.c': _Interface_Derive(files[owners['usbd_cdc_if.c']]),
        'usbd_conf.c': _Ll_Derive(files[owners['usbd_conf.c']], indexed, pcd),
    }
    main = files[owners['main.c']].decode('utf-8-sig')
    anchor = '/* USER CODE BEGIN Includes */'
    main = main.replace(anchor, anchor + '\n#include "usb_cdc_transport.h"', 1)
    anchor = '/* USER CODE BEGIN 3 */'
    main = main.replace(anchor, anchor + '''
    UsbCdcResult usb_result = UsbCdc_Service();
    if ((usb_result != USB_CDC_OK) && (usb_result != USB_CDC_BUSY) &&
        (usb_result != USB_CDC_OFFLINE)) { UsbCdc_LinkDown(); }
''', 1)
    derived['main.c'] = main
    if indexed:
        # The reviewed Cube header omits two middleware feature macros. Make
        # their already-disabled choice explicit under -Wundef, as the private
        # indexed backend does; no runtime registry or BOS feature is enabled.
        header = files[owners['usbd_conf.h']].decode('utf-8-sig')
        anchor = '#define USBD_LPM_ENABLED     0U'
        if header.count(anchor) != 1:
            raise ValueError('Unreviewed native USB option owner')
        derived['usbd_conf.h'] = header.replace(anchor, anchor + '\n#define USBD_CLASS_BOS_ENABLED 0U\n#define USBD_USER_REGISTER_CALLBACK 0U', 1)
    if indexed:
        memory = '''static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[4] = {0U, @PCD@.Instance->DIEPTXF0_HNPTXFSIZ & 0xFFFFU,
        @PCD@.Instance->DIEPTXF[0] & 0xFFFFU, @PCD@.Instance->DIEPTXF[1] & 0xFFFFU};
    uint32_t size[4] = {@PCD@.Instance->GRXFSIZ,
        @PCD@.Instance->DIEPTXF0_HNPTXFSIZ >> 16,
        @PCD@.Instance->DIEPTXF[0] >> 16, @PCD@.Instance->DIEPTXF[1] >> 16};
    uint32_t i;
    uint32_t j;
    if ((@PCD@.Init.dma_enable != 0U) || (size[0] < 64U)) { return USB_CDC_FAULT; }
    for (i = 0U; i < 4U; i++)
    {
        if ((size[i] < 16U) || (start[i] > (USB_OTG_FS_TOTAL_FIFO_SIZE / 4U)) ||
            (size[i] > ((USB_OTG_FS_TOTAL_FIFO_SIZE / 4U) - start[i])))
        { return USB_CDC_FAULT; }
        for (j = 0U; j < 4U; j++)
        {
            if ((j < i) && (start[i] < (start[j] + size[j])) &&
                (start[j] < (start[i] + size[i]))) { return USB_CDC_FAULT; }
        }
    }
    return USB_CDC_OK;
}'''
        clear = '''    uintptr_t USBx_BASE = (uintptr_t)@PCD@.Instance;
    if ((address & 0x80U) != 0U)
    {
        if (((USBx_INEP(number)->DIEPCTL &
              (USB_OTG_DIEPCTL_EPENA | USB_OTG_DIEPCTL_USBAEP)) != 0U) ||
            ((USBx_DEVICE->DAINTMSK & (1UL << number)) != 0U))
        { return USB_CDC_FAULT; }
        USBx_DEVICE->DIEPEMPMSK &= ~(1UL << number);
        if (USB_FlushTxFifo(@PCD@.Instance, number) != HAL_OK)
        { return USB_CDC_FAULT; }
        USBx_INEP(number)->DIEPINT = 0xFB7FU;
    }
    else
    {
        if (((USBx_OUTEP(number)->DOEPCTL &
              (USB_OTG_DOEPCTL_EPENA | USB_OTG_DOEPCTL_USBAEP)) != 0U) ||
            ((USBx_DEVICE->DAINTMSK & (1UL << (number + 16U))) != 0U) ||
            ((@PCD@.Instance->GINTSTS & USB_OTG_GINTSTS_RXFLVL) != 0U))
        { return USB_CDC_FAULT; }
        /* RX FIFO is global, including EP0. Never flush away control traffic.
         * A pending entry blocks retirement; the old pointer remains owned. */
        USBx_OUTEP(number)->DOEPINT = 0xFB7FU;
    }'''
    else:
        memory = '''static UsbCdcResult UsbCdcRetire_MemoryCheck(void)
{
    uint32_t start[5] = {@PCD@.OUT_ep[0].pmaadress, @PCD@.IN_ep[0].pmaadress,
        @PCD@.IN_ep[1].pmaadress, @PCD@.OUT_ep[1].pmaadress, @PCD@.IN_ep[2].pmaadress};
    const uint32_t size[5] = {64U, 64U, 64U, 64U, 8U};
    uint32_t i;
    uint32_t j;
    if ((@PCD@.Instance->BTABLE != 0U) ||
        (@PCD@.OUT_ep[0].doublebuffer != 0U) || (@PCD@.IN_ep[0].doublebuffer != 0U) ||
        (@PCD@.IN_ep[1].doublebuffer != 0U) || (@PCD@.OUT_ep[1].doublebuffer != 0U) ||
        (@PCD@.IN_ep[2].doublebuffer != 0U)) { return USB_CDC_FAULT; }
    /* Reviewed F1 single-buffer PMA: 512 bytes, three 8-byte table entries.
     * Offsets are read from CubeMX's effective configuration, not rewritten. */
    for (i = 0U; i < 5U; i++)
    {
        if ((start[i] < 24U) || ((start[i] % 2U) != 0U) || (start[i] > 512U) ||
            (size[i] > (512U - start[i]))) { return USB_CDC_FAULT; }
        for (j = 0U; j < 5U; j++)
        {
            if ((j < i) && (start[i] < (start[j] + size[j])) &&
                (start[j] < (start[i] + size[i]))) { return USB_CDC_FAULT; }
        }
    }
    return USB_CDC_OK;
}'''
        clear = '''    if ((address & 0x80U) != 0U)
    {
        if ((PCD_GET_ENDPOINT(@PCD@.Instance, number) & USB_EPTX_STAT) != 0U)
        { return USB_CDC_FAULT; }
        PCD_CLEAR_TX_EP_CTR(@PCD@.Instance, number);
        if ((PCD_GET_ENDPOINT(@PCD@.Instance, number) & USB_EP_CTR_TX) != 0U)
        { return USB_CDC_FAULT; }
    }
    else
    {
        if ((PCD_GET_ENDPOINT(@PCD@.Instance, number) & USB_EPRX_STAT) != 0U)
        { return USB_CDC_FAULT; }
        PCD_CLEAR_RX_EP_CTR(@PCD@.Instance, number);
        if ((PCD_GET_ENDPOINT(@PCD@.Instance, number) & USB_EP_CTR_RX) != 0U)
        { return USB_CDC_FAULT; }
    }'''
    rendered = {'Inc/usb_cdc_retire.h': RETIRE_HEADER.encode(),
        'Src/usb_cdc_retire.c': RETIRE_SOURCE.replace('@CLEAR@', clear).replace('@CONFIG@', memory).replace(
            '@INSTANCE@', 'USB_OTG_FS' if indexed else 'USB').replace('@PCD@', pcd).encode()}
    entries = []
    for name, text in derived.items():
        original = owners[name]
        destination = 'Native/' + original
        rendered[destination] = text.encode()
        patch = ''.join(difflib.unified_diff(files[original].decode('utf-8-sig').splitlines(True),
            text.splitlines(True), fromfile=original, tofile=destination)).encode()
        rendered[destination + '.patch'] = patch
        entries.append({'original': original, 'derived': destination,
            'original_sha256': hashlib.sha256(files[original]).hexdigest(),
            'derived_sha256': hashlib.sha256(rendered[destination]).hexdigest()})
    rendered['lifecycle-integration.json'] = json.dumps({'profile': profile,
        'scope': 'CLASSIC_CALLBACKS_CONNECTED_HARDWARE_NOT_PROVEN', 'replacements': entries,
        'additional_sources': ['Src/usb_cdc_transport.c', 'Src/usb_cdc_port.c', 'Src/usb_cdc_retire.c'],
        'limits': ['Suspend invalidates session; resume stays offline until bus reset/reconfiguration.',
            'EP0 policy, HAL LL error propagation, complete critical contracts and physical cancellation NOT PROVEN.',
            'Native clock/PMA/FIFO/startup unchanged. No MCU-family admission.']}, indent=2).encode()
    return rendered
