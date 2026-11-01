"""The integrated build owns real no-heap code and usable reference FIFOs."""

import json
from pathlib import Path
import subprocess
import pytest

from test_usb_transport_integration import integrated, native_init_program
from silverstar_fccg.app.usb_transport import UsbTransport_Export
from silverstar_fccg.generator.native_usb_graph import NativeUsbGraph_Resolve


def test_integrated_heap_source_is_replaced_in_actual_build_graph(integrated, tmp_path):
    _part, root, native, plan, _rendered = integrated
    output = tmp_path / "kit"
    UsbTransport_Export(root, output, integrate=True)
    graph = NativeUsbGraph_Resolve(plan, root, output)
    heap = next(path for path in native if Path(path).name == "sysmem.c")
    rows = [row for row in graph["sources"] if row["input"] == heap]
    assert len(rows) == 1
    assert Path(rows[0]["compiled"]).name == "native_no_heap.c"
    assert rows[0]["policy"] == "first_party"
    assert "_sbrk" in graph["required_link_symbols"]
    manifest = json.loads((output / "lifecycle-integration.json").read_text())
    assert manifest["heap_policy"]["original"] == heap
    assert manifest["heap_policy"]["allocation"] == "REJECT_ALL_REQUESTS"
    assert (root / heap).read_bytes() == native[heap]


def test_unknown_heap_owner_is_not_silently_replaced(integrated):
    from silverstar_fccg.generator.usb_cdc_integration import UsbCdcIntegration_Render
    _part, _root, native, plan, _rendered = integrated
    changed = dict(native)
    heap = next(path for path in native if Path(path).name == 'sysmem.c')
    changed[heap] += b'\n/* changed allocator owner */\n'
    before = dict(changed)
    with pytest.raises(ValueError, match='reviewed sysmem source identity'):
        UsbCdcIntegration_Render(changed, plan.owners)
    assert changed == before


def test_configuration_report_keeps_original_and_explicit_derivation(integrated):
    part, _root, native, plan, rendered = integrated
    manifest = json.loads(rendered['lifecycle-integration.json'])
    configuration = manifest['configuration_derivation']
    assert configuration['hardware_acceptance'] == 'NOT_PROVEN'
    assert (b'PcUsbControl_DescriptorCapacityGet' in rendered['Inc/pc_usb_control.h']) == (part == 'f407')
    if part == 'f407':
        assert configuration['status'] == 'REVIEWED_EXACT_F407_FIFO'
        assert configuration['native']['findings']
        assert not configuration['derived']['findings']
        assert configuration['derived']['declared_fifo_words'] == 272
    else:
        assert configuration['status'] == 'NATIVE_INITIALIZATION_UNCHANGED'
    assert configuration['native'] == plan.capabilities['native_configuration']
    assert native[plan.owners['usbd_conf.c']]


def test_reference_initialization_really_provides_notification_capacity(native_init_program):
    _indexed, path, _calls = native_init_program
    result = subprocess.run([str(path / "test.exe"), "require-valid-layout"],
                            capture_output=True, text=True, timeout=15)
    (path / "require-valid-layout.log").write_text(result.stdout + result.stderr, encoding="utf8")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('mutation', ('symbol-string', 'symbol-duplicate', 'symbol-comma',
    'symbol-other', 'symbol-missing', 'heap-vendor-policy', 'other-first-party', 'heap-contract-missing'))
def test_new_graph_metadata_cannot_change_link_or_compile_ownership(integrated, tmp_path, mutation):
    _part, root, _native, plan, _rendered = integrated
    output = tmp_path / 'kit'
    UsbTransport_Export(root, output, integrate=True)
    path = output / 'lifecycle-integration.json'
    manifest = json.loads(path.read_text())
    if mutation.startswith('symbol-'):
        manifest['heap_policy']['required_link_symbols'] = {
            'symbol-string': '_sbrk', 'symbol-duplicate': ['_sbrk', '_sbrk'],
            'symbol-comma': ['_sbrk,--defsym,unexpected=1'], 'symbol-other': ['main'],
            'symbol-missing': [],
        }[mutation]
    elif mutation == 'heap-vendor-policy':
        next(row for row in manifest['replacements'] if row['original'].endswith('/sysmem.c'))['policy'] = 'vendor'
    elif mutation == 'other-first-party':
        next(row for row in manifest['replacements'] if row['original'].endswith('/main.c'))['policy'] = 'first_party'
    else:
        del manifest['heap_policy']
    path.write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError, match='heap|policy|symbol'):
        NativeUsbGraph_Resolve(plan, root, output)
