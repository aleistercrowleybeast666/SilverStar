from __future__ import annotations

import json
import os
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.generator.log_decoder_profile import LogDecoderPackage_Verify
from silverstar_fccg.generator.render import LogDecoderProfile_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.validation import Project_Validate
from silverstar_fccg.ui.main_window import MainWindow

SF6 = "silverstar.algorithm.estimator.sf6"
GAINS = ("gain_ve", "gain_vn", "gain_vu", "gain_pe", "gain_pn", "gain_pu")


def _Model(catalog):
    model = ReferenceProject_Create(catalog=catalog)
    model.strategies["estimator"] = SF6
    return ProjectConfiguration_Reconcile(model, catalog).model


def test_sf6_six_gains_source_ownership_roundtrip_and_exact_decoder(builtin_catalog):
    model = _Model(builtin_catalog)
    values = model.algorithm_parameters[SF6]
    assert {key for key in values if key.startswith("gain_")} == set(GAINS)
    assert all(values[key] == 0.2 for key in GAINS)
    assert values["gnss_velocity_measurement_delay_ms"] == 270
    assert ProjectModel_Parse(model.Dictionary_Get()).Dictionary_Get() == model.Dictionary_Get()
    assert Project_Validate(model, builtin_catalog).valid
    graph = SourceGraph_Resolve(model, builtin_catalog)
    assert "SYSTEM_BUILD_FUSION_ALGORITHM=SYSTEM_FUSION_SF6" in graph.defines
    assert "SYSTEM_BUILD_ESTIMATOR_ENABLED=0U" in graph.defines
    assert len([name for name in graph.sources if "Estimator/SF6/" in name]) == 2
    assert not any("Estimator/KF6/" in name or "Estimator/ESKF15/" in name for name in graph.sources)
    package = LogDecoderProfile_Render(model, builtin_catalog)
    assert LogDecoderPackage_Verify(package.content)
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        semantics = json.loads(archive.read("project_semantics.json"))
        catalog = json.loads(archive.read("record_catalog.json"))
    parameters = next(group for group in semantics["firmware_algorithm_parameters"] if group["component"] == SF6)
    assert {p["id"] for p in parameters["parameters"] if p["id"].startswith("gain_")} == set(GAINS)
    records = {record["name"]: record for record in catalog["records"]}
    assert records["SF6_STATE"]["payload_size"] == 72
    assert records["SF6_MEASUREMENT"]["payload_size"] == 56
    assert not any("covariance" in f["name"] or f["name"].startswith("p_diagonal") for f in records["SF6_STATE"]["fields"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01, True])
def test_sf6_gain_bounds_block_generation(builtin_catalog, value):
    model = _Model(builtin_catalog)
    model.algorithm_parameters[SF6]["gain_vu"] = value
    assert not Project_Validate(model, builtin_catalog).valid


def test_sf6_legacy_project_preserves_old_algorithm_values(builtin_catalog):
    old = ReferenceProject_Create(catalog=builtin_catalog)
    before = json.loads(json.dumps(old.Dictionary_Get()))
    reopened = ProjectConfiguration_Reconcile(ProjectModel_Parse(before), builtin_catalog).model
    assert SF6 not in reopened.algorithm_parameters
    assert reopened.algorithm_parameters == old.algorithm_parameters
    assert reopened.strategies["estimator"] == "silverstar.algorithm.estimator.kf6"


def test_sf6_gui_order_gains_edit_save_reopen(tmp_path, workspace_root, qapp, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    # MainWindow persists path preferences under its application policy. Keep
    # this fixture inside that policy even when pytest runs at monorepo root.
    fixture_parent = workspace_root / ".work"
    fixture_parent.mkdir(exist_ok=True)
    fixture_root = Path(tempfile.mkdtemp(prefix="SF6GuiRoundtrip-", dir=fixture_parent))
    window = MainWindow(SettingsStore(fixture_root / "sf6.ini"))
    monkeypatch.setattr(window, "_Error_Show", lambda *args: pytest.fail(str(args)))
    try:
        # The GUI starts with an intentionally unbound draft. Use the declared
        # board reference before testing a buildable save, keeping its gates.
        window._model = window._service.ReferenceProject_Create("SF6GuiRoundtrip")
        window._Project_Refresh()
        combo = window.flight_configuration_page.strategy_combos["estimator"]
        assert [combo.itemData(i) for i in range(combo.count())][:4] == [
            None, "silverstar.algorithm.estimator.kf6", "silverstar.algorithm.estimator.eskf15", SF6]
        combo.setCurrentIndex(combo.findData(SF6))
        qapp.processEvents()
        qapp.processEvents()
        assert window._model.strategies["estimator"] == SF6
        assert len([key for key in window.algorithm_parameters_page.editors if key[0] == SF6 and key[1] in GAINS]) == 6
        editor = window.algorithm_parameters_page.editors[(SF6, "gain_pe")]
        editor.setValue(0.35)
        QTest.keyClick(editor, Qt.Key.Key_Return)
        qapp.processEvents()
        assert window._model.algorithm_parameters[SF6]["gain_pe"] == 0.35
        service = FccgService(workspace_root)
        project = fixture_root / "SF6GuiRoundtrip"
        service.Project_Save(window._model, project, confirm_dangerous=True)
        reopened = service.Project_Open(project)
        assert reopened.algorithm_parameters[SF6]["gain_pe"] == 0.35
    finally:
        window._project_state = type(window._project_state).DRAFT
        window.close()


def test_sf6_actual_core_numeric_and_terminal_faults(tmp_path, workspace_root):
    compiler = Path(r"D:\msys64\ucrt64\bin\gcc.exe")
    if not compiler.is_file():
        pytest.skip("Host GCC unavailable")
    if os.name == "nt":
        import ctypes
        # Inherited by these test children; prevent WER dialogs on deliberate
        # terminal-trap cases without changing any other application.
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    builtin = workspace_root / "plugins/builtin"
    core = builtin / "silverstar_core_0_1_0/payload"
    sf6 = builtin / "silverstar_algorithm_estimator_sf6/payload"
    executable = tmp_path / "sf6.exe"
    command = [str(compiler), "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wsign-conversion", "-pedantic", "-O2",
               "-I" + str(core / "Common/Inc"), "-I" + str(core / "Tests/Host"),
               "-I" + str(sf6 / "Algorithm/Estimator/SF6/Inc"),
               str(core / "Common/Src/silverstar_assert.c"),
               str(sf6 / "Algorithm/Estimator/SF6/Src/navigation_sf6.c"),
               str(sf6 / "Tests/Host/test_navigation_sf6.c"), "-lm", "-o", str(executable)]
    environment = dict(os.environ, TEMP=str(tmp_path), TMP=str(tmp_path))
    built = subprocess.run(command, capture_output=True, text=True, env=environment)
    assert built.returncode == 0, built.stderr
    normal = subprocess.run([str(executable)], capture_output=True, text=True)
    assert normal.returncode == 0, normal.stdout + normal.stderr
    assert "0 failures" in normal.stdout
    cases = []
    for case in ("capacity", "state", "gain", "history"):
        result = subprocess.run([str(executable), case], capture_output=True, text=True, timeout=10)
        assert result.returncode in (-1073741795, 3221225501, -4), (case, result.returncode)
        cases.append(dict(case=case, exit_code=result.returncode))
    (tmp_path / "sf6-results.json").write_text(json.dumps(dict(command=command, normal=normal.stdout, terminal_faults=cases), indent=2), encoding="utf-8")
