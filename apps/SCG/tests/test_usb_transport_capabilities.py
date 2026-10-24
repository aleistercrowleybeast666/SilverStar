"""Negative capability probes against real CubeMX input bytes, without writes."""
from pathlib import Path
import os
import json
import re
import subprocess
import pytest

import silverstar_fccg.app.usb_transport as backend


@pytest.fixture(scope="module")
def real_files():
    reference = os.environ.get("SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT")
    if not reference:
        pytest.skip("complete native CubeMX reference not configured")
    root = Path(reference) / "cube-f407-usb"
    return root, backend._Project_Read(root)


def test_real_complete_input_remains_experimental(real_files, monkeypatch):
    root, files = real_files
    monkeypatch.setattr(backend, "_Project_Read", lambda root: files)
    plan = backend.UsbTransport_Plan(root)
    assert plan.result == backend.UsbTransportPlanResult.Experimental, plan.reasons
    assert plan.capabilities["build"]["sources"]


@pytest.mark.parametrize("case", ["dma_parentheses", "dma_macro", "empty_core", "empty_class",
    "empty_make", "composite_define", "heap_allocator", "rtos_source", "uncompiled_class"])
def test_incomplete_or_unsupported_effective_capability_is_rejected(real_files, monkeypatch, case):
    root, original = real_files
    files = dict(original)
    owner = lambda name: next(p for p in files if Path(p).name == name)
    conf = owner("usbd_conf.c")
    if case.startswith("dma_"):
        value = b"(1U)" if case == "dma_parentheses" else b"MY_USB_DMA"
        assert b"dma_enable = DISABLE" in files[conf]
        files[conf] = b"#define MY_USB_DMA 1U\n" + files[conf].replace(b"dma_enable = DISABLE", b"dma_enable = " + value)
    elif case == "empty_core":
        files[owner("usbd_core.c")] = b""
    elif case == "empty_class":
        files[owner("usbd_cdc.c")] = b""
    elif case == "empty_make":
        files["Makefile"] = b""
    elif case == "composite_define":
        files[owner("usbd_conf.h")] += b"\n#define USE_USBD_COMPOSITE 1\n"
    elif case == "heap_allocator":
        files[conf] = files[conf].replace(b"USBD_static_malloc", b"malloc")
    elif case == "rtos_source":
        files[owner("main.c")] += b"\nvoid RunTask(void) { vTaskStartScheduler(); }\n"
    elif case == "uncompiled_class":
        files["Makefile"] = files["Makefile"].replace(owner("usbd_cdc.c").encode(), b"Core/Src/other.c")
        files["Core/Src/other.c"] = b"void Other(void) {}"
    monkeypatch.setattr(backend, "_Project_Read", lambda root: files)
    assert backend.UsbTransport_Plan(root).result == backend.UsbTransportPlanResult.Rejected


def _Manifest_FromMake(files):
    from silverstar_fccg.hardware.usb_transport_capabilities import UsbBuild_Inspect
    build, reasons = UsbBuild_Inspect(files)
    assert not reasons
    return {'format': 'silverstar.usb.native-build', 'version': 1,
        'sources': build['sources'], 'asm_sources': build['asm_sources'],
        'include_dirs': [v[2:] for v in build['include_dirs']],
        'defines': [v[2:] for v in build['defines']], 'cpu': build['cpu'][0].split('=', 1)[1],
        'linker_script': build['linker_script'][0]}


def test_declarative_inventory_supports_non_make_project_audit(real_files, monkeypatch, tmp_path):
    root, original = real_files
    files = dict(original)
    manifest = _Manifest_FromMake(files)
    files.pop('Makefile')
    files['scg-usb-build.json'] = json.dumps(manifest).encode()
    monkeypatch.setattr(backend, '_Project_Read', lambda root: files)
    plan = backend.UsbTransport_Export(root, tmp_path / 'kit')
    assert plan.result == backend.UsbTransportPlanResult.Experimental
    description = json.loads((tmp_path / 'kit/usb-adaptation.json').read_text())
    assert description['native_build_inventory']['inventory_owner'] == 'scg-usb-build.json'
    assert description['automatic_integration']['profile']['binding'] == 'REVIEWED_COMPONENTS_AND_HOOK_REGIONS'
    assert description['acceptance'] == 'NOT_PROVEN'
    assert description['lifecycle_hooks']['single_main_service'] == 'UNBOUND_REQUIRES_REVIEW'
    assert description['configuration_findings']  # Reference F407 has no explicit EP2 FIFO.


@pytest.mark.parametrize('case', ['escape', 'expression', 'missing_source', 'conflicting_owner', 'unknown_field', 'boolean_version'])
def test_declarative_inventory_never_executes_or_accepts_ambiguous_inputs(real_files, monkeypatch, case):
    root, original = real_files
    files = dict(original)
    manifest = _Manifest_FromMake(files)
    if case != 'conflicting_owner':
        files.pop('Makefile')
    if case == 'escape':
        manifest['sources'].append('../outside.c')
    elif case == 'expression':
        manifest['defines'].append('EVIL=$(touch anything)')
    elif case == 'missing_source':
        manifest['sources'].append('Core/Src/missing.c')
    elif case == 'unknown_field':
        manifest['command'] = 'do not execute this'
    elif case == 'boolean_version':
        manifest['version'] = True
    files['scg-usb-build.json'] = json.dumps(manifest).encode()
    monkeypatch.setattr(backend, '_Project_Read', lambda root: files)
    assert backend.UsbTransport_Plan(root).result == backend.UsbTransportPlanResult.Rejected


@pytest.mark.parametrize('feature,layer', [('USBX','buffer_owner'), ('HS','link'),
    ('DMA','buffer_owner'), ('CACHE','buffer_owner'), ('RTOS','scheduler')])
def test_blocked_capabilities_do_not_advertise_classic_support(real_files, monkeypatch, feature, layer):
    root, original = real_files
    files = dict(original)
    ioc = next(name for name in files if name.endswith('.ioc'))
    if feature in {'USBX', 'HS', 'RTOS'}:
        files[ioc] += {'USBX': b'\nUSB_DEVICE.Test=USBX\n',
            'HS': b'\nUSB_DEVICE.Peripheral=USB_OTG_HS\n',
            'RTOS': b'\nTest.Scheduler=FREERTOS\n'}[feature]
    elif feature == 'DMA':
        conf = next(name for name in files if name.endswith('/usbd_conf.c'))
        files[conf] = files[conf].replace(b'dma_enable = DISABLE', b'dma_enable = ENABLE')
    else:
        main = next(name for name in files if name.endswith('/main.c'))
        files[main] += b'\nvoid CacheStart(void) { SCB_EnableDCache(); }\n'
    monkeypatch.setattr(backend, '_Project_Read', lambda root: files)
    plan = backend.UsbTransport_Plan(root)
    description = backend.UsbAdaptation_Describe(plan)
    assert plan.result == backend.UsbTransportPlanResult.Rejected
    assert description['readiness'] == 'BLOCKED'
    assert description['capability_layers'][layer] == 'UNSUPPORTED_OR_UNRESOLVED'
    assert description['capability_layers']['adapter_eligibility'] == 'BLOCKED'
    if feature == 'USBX':
        assert description['bindings']['class_data'] is None
        assert description['bindings']['status'] == 'UNBOUND_UNSUPPORTED_STACK'


@pytest.mark.parametrize('case', ['complete', 'macro', 'duplicate', 'too_small'])
def test_native_fifo_description_never_claims_effective_register_proof(real_files, case):
    from silverstar_fccg.hardware.usb_transport_capabilities import UsbNativeConfiguration_Describe
    _root, original = real_files
    files = dict(original)
    conf = next(name for name in files if name.endswith('/usbd_conf.c'))
    files[conf] = files[conf].replace(b'HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 1, 0x80);',
        b'HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 1, 0x40);\n'
        b'  HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 0x02U, 0x20);')
    if case == 'macro':
        files[conf] = files[conf].replace(b', 0x20);', b', NOT_EVALUATED);')
    elif case == 'duplicate':
        files[conf] += b'\nvoid Other(void) { HAL_PCDEx_SetTxFiFo(&hpcd_USB_OTG_FS, 2, 32); }\n'
    elif case == 'too_small':
        files[conf] = files[conf].replace(b', 0x20);', b', 8U);')
    description = UsbNativeConfiguration_Describe(files, {'usbd_conf.c': conf})
    assert description['memory_mechanism'] == 'OTG_FIFO'
    assert description['effective_geometry'] == 'NOT_PROVEN_REQUIRES_RUNTIME_GUARD'
    if case == 'complete':
        assert not description['findings'] and description['declared_fifo_words'] == 288
    else:
        assert description['findings']


def test_drd_pma_observation_is_not_automatic_adapter_admission():
    from silverstar_fccg.hardware.usb_transport_capabilities import UsbNativeConfiguration_Describe
    description = UsbNativeConfiguration_Describe({'usbd_conf.c': b'''
        hpcd_USB_DRD_FS.Instance = USB_DRD_FS;
        HAL_PCDEx_PMAConfig(&hpcd_USB_DRD_FS, 0x81U, PCD_SNG_BUF, 256U);
    '''}, {'usbd_conf.c': 'usbd_conf.c'})
    assert description['memory_mechanism'] == 'PMA'
    assert description['pcd_instances'] == [{'pcd': 'hpcd_USB_DRD_FS', 'instance': 'USB_DRD_FS'}]
    assert description['scope'] == 'SOURCE_DECLARATIONS_ONLY'
    assert description['effective_geometry'].startswith('NOT_PROVEN')


@pytest.mark.parametrize('composite', [False, True])
def test_reviewed_indexed_sdk_abi_rejects_composite_without_a_runtime_registry(real_files, tmp_path, composite):
    from silverstar_fccg.generator.usb_cdc_integration import UsbCdcIntegration_Render
    from silverstar_fccg.generator.native_hal import NativeC_FunctionSpanGet
    root, files = real_files
    plan = backend.UsbTransport_Plan(root)
    rendered = UsbCdcIntegration_Render(files, plan.owners)
    header = files[plan.owners['usbd_cdc.h']].decode('utf-8-sig')
    declarations = re.search(r'#ifdef USE_USBD_COMPOSITE\r?\nuint8_t USBD_CDC_SetTxBuffer.*?#endif[^\n]*',
        header, re.S).group(0)
    source = rendered['Native/' + plan.owners['usbd_cdc.c']].decode()
    signatures = []
    for name in ['USBD_CDC_SetTxBuffer', 'USBD_CDC_TransmitPacket']:
        start, opening, _end = NativeC_FunctionSpanGet(source, name)
        signatures.append(source[start:opening].strip() + ';')
    program = '#include <stdint.h>\ntypedef struct Device USBD_HandleTypeDef;\n' + declarations
    program += '\n' + '\n'.join(signatures) + '\nint main(void) { return 0; }\n'
    path = tmp_path / 'abi.c'
    path.write_text(program, encoding='utf8')
    command = ['gcc','-std=c11','-Wall','-Wextra','-Werror','-pedantic',
        *(['-DUSE_USBD_COMPOSITE=1'] if composite else []), '-c', str(path), '-o', str(path.with_suffix('.o'))]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (tmp_path / 'compile.log').write_text(result.stdout + result.stderr, encoding='utf8')
    if composite:
        assert result.returncode != 0
        assert 'conflicting types' in result.stderr and 'USBD_CDC_SetTxBuffer' in result.stderr
    else:
        assert result.returncode == 0, result.stderr
