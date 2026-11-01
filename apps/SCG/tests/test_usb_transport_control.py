"""Execute the generic kit's complete class/core/EP0/I/O, with Host LL ports.

The retirement hardware port is a model here; its actual implementation has a
separate register/failure suite in test_usb_transport_integration.py.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

import test_usb_lifecycle_normal as normal
from test_native_control_faults import FAULTS, _Replace_Once
from silverstar_fccg.app.usb_transport import UsbTransport_Export, _Project_Read


RETIRE_PORT = r'''
#include "usb_cdc_retire.h"
UsbCdcResult UsbCdcRetire_ConfigurationCheck(USBD_HandleTypeDef *device)
{ assert(device==&hUsbDeviceFS); return USB_CDC_OK; }
UsbCdcResult UsbCdcRetire_Endpoint(USBD_HandleTypeDef *device,uint8_t address)
{ return USBD_LL_CloseEP(device,address)==USBD_OK ? USB_CDC_OK : USB_CDC_FAULT; }
'''


@pytest.mark.parametrize('part', ('f103', 'f407'))
def test_generic_actual_ep0_boundaries_and_faults(part, tmp_path):
    reference = os.environ.get('SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT')
    if not reference:
        pytest.skip('complete native CubeMX references not configured')
    root = Path(reference) / ('cube-' + part + '-usb')
    native = _Project_Read(root)
    kit = tmp_path / 'kit'
    plan = UsbTransport_Export(root, kit, integrate=True)
    assert _Project_Read(root) == native
    manifest = json.loads((kit / 'lifecycle-integration.json').read_text(encoding='utf8'))
    replacements = {row['original']: row['derived'] for row in manifest['replacements']}
    compiled = {}
    for source in plan.capabilities['build']['sources']:
        if Path(source).name in {'usbd_core.c', 'usbd_ctlreq.c', 'usbd_ioreq.c',
                                'usbd_cdc.c', 'usbd_cdc_if.c', 'usbd_desc.c'}:
            compiled[Path(source).name] = (kit / replacements[source]).read_bytes() if source in replacements else native[source]
    for source in manifest['additional_sources']:
        if Path(source).name != 'usb_cdc_retire.c':
            compiled[Path(source).name] = (kit / source).read_bytes()
    used = {name: hashlib.sha256(body).hexdigest() for name, body in compiled.items()}
    for name, body in compiled.items():
        (tmp_path / name).write_bytes(body)
    headers = {'usbd_def.h', 'usbd_core.h', 'usbd_ctlreq.h', 'usbd_ioreq.h',
               'usbd_cdc.h', 'usbd_cdc_if.h', 'usbd_desc.h'}
    for name in headers:
        owner = next(path for path in native if Path(path).name == name)
        body = native[owner]
        (tmp_path / name).write_bytes(body)
        used[name] = hashlib.sha256(body).hexdigest()
    for header in (kit / 'Inc').glob('*.h'):
        (tmp_path / header.name).write_bytes(header.read_bytes())
        used[header.name] = hashlib.sha256(header.read_bytes()).hexdigest()
    owner = plan.owners['usbd_conf.h']
    conf = (kit / replacements[owner]).read_text(encoding='utf8') if owner in replacements else native[owner].decode('utf-8-sig')
    conf = re.sub(r'#include "(?:main|stm32\w+)\.h"', '#include "host_shim.h"', conf)
    (tmp_path / 'usbd_conf.h').write_text(conf, encoding='utf8')
    (tmp_path / 'host_shim.h').write_text(normal.SHIM, encoding='utf8')
    (tmp_path / 'main.h').write_text('#include "host_shim.h"\n', encoding='utf8')
    (tmp_path / 'usb_device.h').write_text('#include "usbd_core.h"\nextern USBD_HandleTypeDef hUsbDeviceFS;\n', encoding='utf8')
    (tmp_path / 'silverstar_assert.h').write_text('#include <assert.h>\n#define SILVERSTAR_ASSERT(c,m,r) assert(c)\n', encoding='utf8')
    source = normal.HARNESS[:normal.HARNESS.index('static uint32_t PendingData')]
    source = source.replace('#include "pc_byte_stream.h"', '#include "usb_cdc_transport.h"')
    source = _Replace_Once(source, 'static unsigned fail_tx_once;',
        'static unsigned fail_tx_once;\nstatic unsigned fail_ep0_tx_once,fail_ep0_rx_once,ep0_ll_calls;')
    source = _Replace_Once(source, 'assert(d==&hUsbDeviceFS);tx_ptr',
        'assert(d==&hUsbDeviceFS);if((ep&0x7FU)==0U){ep0_ll_calls++;if(fail_ep0_tx_once){fail_ep0_tx_once=0U;return USBD_FAIL;}}tx_ptr')
    source = _Replace_Once(source, 'if(ep==0x01U && fail_prepare_once!=0U)',
        'if(ep==0U){ep0_ll_calls++;if(fail_ep0_rx_once){fail_ep0_rx_once=0U;return USBD_FAIL;}}\n if(ep==0x01U && fail_prepare_once!=0U)')
    policy = 'pc_usb_control.c' in compiled
    fault_source = '#include "pc_usb_control.h"\n#include "usbd_ioreq.h"\n' + FAULTS if policy else ''
    source += RETIRE_PORT + fault_source + r'''
int main(int argc,char **argv)
{
 assert(argc==2);
 assert(USBD_Init(&hUsbDeviceFS,&FS_Desc,0U)==USBD_OK);
 assert(USBD_RegisterClass(&hUsbDeviceFS,&USBD_CDC)==USBD_OK);
 assert(USBD_CDC_RegisterInterface(&hUsbDeviceFS,&USBD_Interface_fops_FS)==USBD_OK);
 assert(USBD_Start(&hUsbDeviceFS)==USBD_OK);EnumConfigure();
 if(strcmp(argv[1],"normal")==0){ControlNormal();return 0;}
 if(strcmp(argv[1],"boundaries")==0){ControlBoundaries();return 0;}
 @FAULT_CALL@
 return 2;
}
'''.replace('@FAULT_CALL@', 'if(ControlFault(argv[1])){return 0;}' if policy else '/* Pre-fix kit has no bounded EP0 policy. */')
    descriptor = re.search(r'USBD_DescriptorsTypeDef\s+(\w+)\s*=', compiled['usbd_desc.c'].decode())[1]
    source = source.replace('FS_Desc', descriptor)
    (tmp_path / 'control.c').write_text(source, encoding='utf8')
    command = [shutil.which('gcc'), '-std=c11', '-O2', '-Wall', '-Wextra', '-fanalyzer',
               '-Werror=implicit-function-declaration', '-Werror=incompatible-pointer-types',
               '-DUSBD_MAX_SUPPORTED_CLASS=1', '-I' + str(tmp_path),
               *(str(tmp_path / name) for name in compiled), str(tmp_path / 'control.c'),
               '-o', str(tmp_path / 'control.exe')]
    if part == 'f103':
        command.insert(1, '-DHOST_F103=1')
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    (tmp_path / 'compile.log').write_text(result.stdout + result.stderr, encoding='utf8')
    assert result.returncode == 0, result.stdout + result.stderr
    runs = []
    for case in ('normal', 'boundaries', 'null_owner', 'foreign_owner', 'get_initial_failure',
                 'set_initial_failure', 'status_tx_failure', 'status_rx_failure',
                 'descriptor_continuation_failure', 'descriptor_initial_failure',
                 'descriptor_premature_rx_failure', 'receive_continuation_helper_failure'):
        invocation = [str(tmp_path / 'control.exe'), case]
        result = subprocess.run(invocation, capture_output=True, text=True, timeout=20)
        runs.append({'case': case, 'command': invocation, 'exit': result.returncode,
                     'stdout': result.stdout, 'stderr': result.stderr})
    receipt = {'part': part, 'policy_present': policy, 'source_sha256': used,
               'command': command, 'compile_exit': 0, 'runs': runs,
               'harness_sha256': hashlib.sha256(source.encode()).hexdigest(),
               'scope': 'Actual exported class/core/I/O/EP0/transport/port; Host LL and retirement hardware port. No hardware acceptance.'}
    (tmp_path / 'control-receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf8')
    assert all(row['exit'] == 0 for row in runs), runs
