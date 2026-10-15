import hashlib
import json
import os
import threading
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from silverstar_fccg.app import native_usb
from silverstar_fccg.core.task import TaskCancelledError, TaskContext
from silverstar_fccg.generator.native_usb_graph import NativeUsbGraph_Resolve
from silverstar_fccg.project.model import ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.native_usb import (
    NativeUsbReference,
    NativeUsbReference_Parse,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.ui.pages.native_usb import NativeUsbPanel

pytest_plugins = ("test_scg_ui_metadata_hotfix",)


@pytest.mark.skipif(os.name != "nt", reason="Windows compiler process-tree regression")
def test_cancelled_compiler_stops_owned_child_process(tmp_path):
    import ctypes
    import sys

    from silverstar_fccg.build.native_usb import _Command_Run

    child_id = tmp_path / "child.txt"
    helper = tmp_path / "compiler.py"
    helper.write_text("import pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid))\n"
        "child.wait()\n", encoding="utf8")
    context = TaskContext()
    def cancel():
        deadline = time.monotonic() + 5
        while not child_id.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        context.Cancel_Request()
    worker = threading.Thread(target=cancel)
    worker.start()
    try:
        with pytest.raises(TaskCancelledError):
            _Command_Run([sys.executable, str(helper), str(child_id)], tmp_path, context, [])
    finally:
        worker.join(6)
    assert child_id.is_file()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x100000, False, int(child_id.read_text()))
    if handle:
        try:
            assert kernel.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel.CloseHandle(handle)


def test_project_roundtrip_preserves_legacy_and_binds_only_optional_usb(builtin_catalog):
    model = ReferenceProject_Create(catalog=builtin_catalog)
    original = model.Dictionary_Get()
    assert "native_usb" not in original
    assert ProjectModel_Parse(original).Dictionary_Get() == original
    model.native_usb = NativeUsbReference("D:/native", "a" * 64)
    document = model.Dictionary_Get()
    assert document["format_version"] == 19
    restored = ProjectModel_Parse(document)
    assert restored.native_usb == model.native_usb
    assert restored.ground_target == model.ground_target
    assert restored.hardware == model.hardware
    assert restored.Dictionary_Get() == document
    document["format_version"] = 18
    with pytest.raises(ProjectModelError, match="requires project format_version 19"):
        ProjectModel_Parse(document)


@pytest.mark.parametrize("patch", [
    {"version": True}, {"version": 2}, {"native_root": "relative"}, {"native_root": ""},
    {"source_sha256": "x" * 64}, {"source_sha256": ""}, {"native_root": "D:/bad\npath"},
    {"output_root": "D:/output"}, {"kit_sha256": "a" * 64}, {"receipt_file": "../secret"},
    {"receipt_sha256": "a" * 64}, {"accepted": True},
])
def test_saved_reference_cannot_smuggle_status_or_incomplete_evidence(patch):
    document = NativeUsbReference("D:/native", "a" * 64).Dictionary_Get() | patch
    with pytest.raises(ValueError):
        NativeUsbReference_Parse(document)


@pytest.fixture
def prepared(tmp_path):
    root = os.environ.get("SILVERSTAR_NATIVE_CDC_REFERENCE_ROOT")
    if not root:
        pytest.skip("complete native CubeMX reference not configured")
    inspected = native_usb.NativeUsb_Inspect(Path(root) / "cube-f103-usb", TaskContext())
    assert inspected.result == native_usb.NativeUsbWorkflowResult.Experimental
    result = native_usb.NativeUsb_Prepare(inspected.reference, tmp_path / "derived", TaskContext())
    yield result


def test_source_graph_replaces_every_owner_once_and_native_is_preserved(prepared):
    ref = prepared.reference
    graph = native_usb._Output_Verify(ref, prepared.plan)
    actual = [entry["compiled"] for entry in graph["sources"]]
    assert len(set(actual)) == len(actual)
    for original, derived in graph["replacements"].items():
        if original.endswith(".c"):
            assert actual.count(derived) == 1
            assert str(Path(ref.native_root) / original) not in actual
    assert sum(Path(p).name == "silverstar_assert.c" for p in actual) == 1
    assert native_usb.NativeUsb_Refresh(ref, TaskContext()).plan == prepared.plan
    assert graph["critical_contracts"] == "NOT_PROVEN"


def test_changed_native_input_invalidates_previous_graph_before_tool_execution(prepared, monkeypatch):
    changed = replace(prepared.plan, files_sha256={**prepared.plan.files_sha256, "changed.h": "0" * 64})
    monkeypatch.setattr(native_usb, "UsbTransport_Plan", lambda _: changed)
    with pytest.raises(ValueError, match="input changed"):
        native_usb.NativeUsb_Build(prepared.reference, "unavailable", TaskContext())


@pytest.mark.parametrize("target", ["Src/usb_cdc_transport.c", "native-usb-source-graph.json", "kit-sha256.json"])
def test_changed_output_blocks_compile_before_compiler_resolution(prepared, target):
    path = Path(prepared.reference.output_root) / target
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        native_usb.NativeUsb_Build(prepared.reference, "unavailable", TaskContext())


def test_unlisted_header_cannot_shadow_native_configuration(prepared):
    path = Path(prepared.reference.output_root) / "Inc/main.h"
    path.write_text("/* unlisted shadow input */\n", encoding="utf8")
    with pytest.raises(ValueError, match="unlisted input"):
        native_usb.NativeUsb_Build(prepared.reference, "unavailable", TaskContext())


def test_duplicate_replacements_and_compiler_options_are_rejected(prepared):
    ref = prepared.reference
    output = Path(ref.output_root)
    path = output / "lifecycle-integration.json"
    manifest = json.loads(path.read_text())
    manifest["replacements"].append(manifest["replacements"][0])
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="duplicate ownership"):
        NativeUsbGraph_Resolve(prepared.plan, Path(ref.native_root), output)
    capabilities = deepcopy(prepared.plan.capabilities)
    capabilities["build"]["defines"].append("-fplugin=untrusted.dll")
    with pytest.raises(ValueError, match="literal -D"):
        NativeUsbGraph_Resolve(replace(prepared.plan, capabilities=capabilities), Path(ref.native_root), output)


def test_cancelled_operation_does_not_export_or_resolve_input(tmp_path):
    context = TaskContext()
    context.Cancel_Request()
    with pytest.raises(TaskCancelledError):
        native_usb.NativeUsb_Inspect(tmp_path / "not-present", context)


def test_panel_saved_reference_does_not_claim_compile_or_acceptance(qapp):
    panel = NativeUsbPanel("en_US")
    panel.Reference_Set(NativeUsbReference("D:/native", "a" * 64))
    assert "not rechecked" in panel.details.toPlainText()
    assert not panel.buttons["compile"].isEnabled()
    actions = []
    panel.actionRequested.connect(actions.append)
    panel.buttons["refresh"].click()
    assert actions == ["refresh"]
    panel.Language_Set("zh_CN")
    assert panel.buttons["inspect"].text() == "选择并检查"
    panel.Failure_Set(ValueError("changed"))
    assert not panel.buttons["prepare"].isEnabled()


def test_prepare_never_overwrites_existing_output(prepared):
    root = Path(prepared.reference.output_root)
    before = hashlib.sha256((root / "kit-sha256.json").read_bytes()).hexdigest()
    with pytest.raises(Exception, match="exist"):
        native_usb.NativeUsb_Prepare(prepared.reference, root, TaskContext())
    assert hashlib.sha256((root / "kit-sha256.json").read_bytes()).hexdigest() == before


@pytest.mark.parametrize("stale", [False, True])
def test_main_window_inspection_is_background_and_stale_results_do_not_replace_model(window, qapp, monkeypatch, stale):
    from PySide6.QtWidgets import QFileDialog
    from silverstar_fccg.app.usb_transport import (
        UsbTransportPlan,
        UsbTransportPlanResult,
    )

    main_thread = threading.get_ident()
    observed = []
    finish = threading.Event()
    reference = NativeUsbReference("D:/native", "a" * 64)
    plan = UsbTransportPlan(UsbTransportPlanResult.Experimental, "ST_USB_DEVICE_CDC", "UI_FIXTURE", False,
        (), {}, {}, (), (), {"automatic_integration": {"status": "SOURCE_SHAPE_AVAILABLE"}})
    result = native_usb.NativeUsbWorkflow(native_usb.NativeUsbWorkflowResult.Experimental, plan, reference)
    def inspect(path, context):
        observed.append(threading.get_ident())
        assert finish.wait(5)
        return result
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_args: "D:/native")
    monkeypatch.setattr(window._service, "NativeUsb_Inspect", inspect)
    before = window._model.native_usb
    window._NativeUsb_Request("inspect")
    try:
        assert window._active_worker is not None
        assert not window.build_page.native_usb.buttons["inspect"].isEnabled()
        if stale:
            window._project_root = Path("D:/different-project")
        finish.set()
        deadline = time.monotonic() + 10
        while window._active_worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
        assert window._active_worker is None
        assert observed and observed[0] != main_thread
        assert window._model.native_usb == (before if stale else reference)
    finally:
        finish.set()
