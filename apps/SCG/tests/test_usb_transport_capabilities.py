"""Negative capability probes against real CubeMX input bytes, without writes."""
from pathlib import Path
import os
import json
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


@pytest.mark.parametrize('case', ['escape', 'expression', 'missing_source', 'conflicting_owner', 'unknown_field'])
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
    files['scg-usb-build.json'] = json.dumps(manifest).encode()
    monkeypatch.setattr(backend, '_Project_Read', lambda root: files)
    assert backend.UsbTransport_Plan(root).result == backend.UsbTransportPlanResult.Rejected
