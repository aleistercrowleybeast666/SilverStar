"""Ground GUI routing through the actual importer; tiny non-firmware inputs."""
from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QFileDialog

from test_ground_cubemx_base import _Cube_Get
from test_scg_ui_metadata_hotfix import window
from test_task_progress_busy import _Wait
from test_f103_ground_reference import _GroundF103Model_Get
from silverstar_fccg.build.runner import BuildRunner
import silverstar_fccg.ui.main_window as main_window_module


def test_ground_gui_import_uses_authoritative_complete_project_policy(qapp, window, tmp_path, monkeypatch):
    cube = _Cube_Get(tmp_path / "cube")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(cube))
    errors = []
    monkeypatch.setattr(window, "_Error_Show", lambda *args: errors.append(args))
    window._GroundCubeMxImport_Request(True)
    _Wait(qapp, lambda: window._active_worker is None)
    assert not errors
    ground = window._model.ground_target
    assert ground.mcu == "silverstar.mcu.stm32f103c8t6"
    assert ground.hardware.hal_cmsis_source_policy == "imported_tree_authoritative"
    assert ground.hardware.snapshot_id
    assert ground.board == "" and not ground.resource_assignments
    assert window._project_root is None


@pytest.mark.parametrize("linker", ["HardwareGenerated/STM32CubeMX/STM32F103XX_FLASH.ld", "../outside.ld", "/outside.ld", None])
def test_imported_ground_audit_uses_source_graph_linker_with_target_path_guard(qapp, window, tmp_path, monkeypatch, linker):
    window._model = _GroundF103Model_Get(window._service.catalog)
    ground = window._model.ground_target
    window._model.ground_target = replace(ground, hardware=replace(ground.hardware,
        hal_cmsis_source_policy="imported_tree_authoritative"))
    window._project_root = tmp_path / "project"
    target = window._project_root / "Ground_Station"
    (target / "Generated").mkdir(parents=True)
    (target / "Makefile").write_text("all:\n", encoding="utf8")
    (target / "Generated/ground_source_graph.json").write_text(json.dumps({"linker_script": linker}), encoding="utf8")
    audits, errors = [], []
    monkeypatch.setattr(BuildRunner, "_Process_Run", staticmethod(lambda *args, **kwargs: (0, [])))
    def audit(elf, map_file, selected_linker, *args, **kwargs):
        audits.append(selected_linker)
        return SimpleNamespace(errors=(), regions=())
    monkeypatch.setattr(main_window_module, "BuildAudit_Run", audit)
    monkeypatch.setattr(window, "_Error_Show", lambda *args: errors.append(args))
    window._TargetAction_Request("ground_build")
    _Wait(qapp, lambda: window._active_worker is None)
    if linker and linker.startswith("HardwareGenerated/"):
        assert not errors and audits == [target / linker]
        assert window.progress_bar.property("taskState") == "success"
    else:
        assert errors and not audits
        assert window.progress_bar.property("taskState") == "error"
        assert window.progress_bar.value() < 1000


@pytest.mark.parametrize("directory", [True, False])
def test_ground_gui_rejects_ioc_only_without_changing_model(qapp, window, tmp_path, monkeypatch, directory):
    cube = _Cube_Get(tmp_path / "cube")
    only = tmp_path / "ioc_only"
    only.mkdir()
    ioc = only / "test.ioc"
    ioc.write_bytes((cube / "test.ioc").read_bytes())
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(only))
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(ioc), ""))
    errors = []
    monkeypatch.setattr(window, "_Error_Show", lambda *args: errors.append(args))
    previous = asdict(window._model.ground_target)
    window._GroundCubeMxImport_Request(directory)
    _Wait(qapp, lambda: window._active_worker is None)
    assert errors
    assert asdict(window._model.ground_target) == previous
    assert window._project_root is None
