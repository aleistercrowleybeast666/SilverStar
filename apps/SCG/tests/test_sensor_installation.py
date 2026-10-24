"""Measured position contract, legacy isolation, generation and real Qt entry."""

import json
import shutil
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QScrollArea

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.assembler import ProjectAssembler
from silverstar_fccg.generator.render import GeneratedFiles_Render
from silverstar_fccg.generator.source_graph import SourceGraph_Resolve
from silverstar_fccg.project.algorithm_parameters import (
    AlgorithmParameters_Reconcile, AlgorithmParametersHeader_Render,
)
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.generation_state import ProjectGenerationFingerprint_Get
from silverstar_fccg.project.model import DeviceInstance, ProjectModel_Load, ProjectModel_Parse, ProjectModelError
from silverstar_fccg.project.native_usb import NativeUsbReference
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.sensor_installation import (
    SENSOR_INSTALLATION_SCHEMA, SENSOR_POSITION_LIMIT_M,
    SensorInstallationConfiguration, SensorInstallationSnapshot_Get,
    SensorPosition, SensorPosition_Parse,
)
from silverstar_fccg.project.validation import (
    Project_EditValidate, Project_Validate, SensorInstallationIssues_Get,
)
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.sensor_installation_editor import SensorPositionEditor

ESKF = "silverstar.algorithm.estimator.eskf15"
ORIGIN = "CAD datum O: aft ring centre; +X connector mark; +Y right-handed; +Z nose"


def _Model_Get(catalog, estimator="kf6"):
    model = ReferenceProject_Create("Installation013", catalog=catalog)
    model.strategies["estimator"] = (
        "silverstar.algorithm.estimator." + estimator if estimator is not None else None)
    AlgorithmParameters_Reconcile(model, catalog)
    return model


def _Positions_Set(model):
    model.sensor_installation = SensorInstallationConfiguration(ORIGIN)
    model.device_instances = [
        replace(item, position_body_m=SensorPosition(0.0123456789, -0.03, 0.25))
        if item.instance_id == "imu0" else
        replace(item, position_body_m=SensorPosition(-0.04, 0.05, 1.2))
        if item.instance_id == "gnss0" else item for item in model.device_instances
    ]


def test_legacy_arm_has_no_implicit_origin_or_instance_migration(builtin_catalog):
    model = _Model_Get(builtin_catalog, "eskf15")
    model.algorithm_parameters[ESKF].update({
        "lever_arm_body_x_m": 0.3, "lever_arm_body_y_m": -0.2, "lever_arm_body_z_m": 1.5})
    before = model.Dictionary_Get()
    header = AlgorithmParametersHeader_Render(model, builtin_catalog)
    restored = ProjectModel_Parse(json.loads(json.dumps(before)))
    assert restored.Dictionary_Get() == before
    assert restored.sensor_installation is None
    assert all(item.position_body_m is None for item in restored.device_instances)
    assert before["format_version"] == 14 and "sensor_installation" not in before
    _Positions_Set(restored)
    assert AlgorithmParametersHeader_Render(restored, builtin_catalog) == header
    assert restored.algorithm_parameters == model.algorithm_parameters
    snapshot = SensorInstallationSnapshot_Get(restored, builtin_catalog)
    assert snapshot["legacy_eskf15"]["input_values"]["lever_arm_body_z_m"] == 1.5
    assert snapshot["legacy_eskf15"]["active_global_values_m"]["lever_arm_body_z_m"] == 1.5
    assert snapshot["runtime_applied"] is False


def test_instances_origin_unknown_and_measured_zero_roundtrip(tmp_path, builtin_catalog):
    model = _Model_Get(builtin_catalog)
    _Positions_Set(model)
    model.device_instances.extend([
        DeviceInstance("imu2", "silverstar.device.imu.jy901b", position_body_m=SensorPosition(0, 0, 0)),
        DeviceInstance("gnss2", "silverstar.device.gnss.neo_m9n"),
    ])
    original = model.Dictionary_Get()
    assert original["format_version"] == 20
    ProjectRoot_Save(model, tmp_path / "saved")
    reopened = ProjectModel_Load(tmp_path / "saved/SilverStar.ssproject")
    assert reopened.Dictionary_Get() == original
    assert reopened.DeviceInstance_Get("imu2").position_body_m == SensorPosition(0, 0, 0)
    assert reopened.DeviceInstance_Get("gnss2").position_body_m is None
    reopened.capability_source_overrides["imu.acceleration"] = "imu2"
    reopened.capability_source_overrides["imu.angular_rate"] = "imu2"
    assert reopened.sensor_installation.origin_description == ORIGIN
    assert reopened.DeviceInstance_Get("imu0").position_body_m == model.DeviceInstance_Get("imu0").position_body_m
    reopened.device_instances = [item for item in reopened.device_instances if item.instance_id != "imu0"]
    assert reopened.DeviceInstance_Get("imu2").position_body_m == SensorPosition(0, 0, 0)


def test_format_20_preserves_existing_native_usb_reference_and_nested_presets(builtin_catalog):
    model = _Model_Get(builtin_catalog)
    model.native_usb = NativeUsbReference("D:/native-reference", "a" * 64)
    original = ProjectModel_Parse(model.Dictionary_Get())
    assert original.Dictionary_Get()["format_version"] == 19
    _Positions_Set(model)
    preset = model.Dictionary_Get()
    model.feature_tier_presets["full"] = preset
    serialized = model.Dictionary_Get()
    restored = ProjectModel_Parse(serialized)
    assert serialized["format_version"] == 20
    assert restored.native_usb == original.native_usb
    assert restored.feature_tier_presets["full"] == preset
    assert restored.Dictionary_Get() == serialized


@pytest.mark.parametrize("bad", [
    {"x": True, "y": 0, "z": 0}, {"x": "1", "y": 0, "z": 0},
    {"x": float("nan"), "y": 0, "z": 0}, {"x": float("inf"), "y": 0, "z": 0},
    {"x": 1000001, "y": 0, "z": 0}, {"x": 10**400, "y": 0, "z": 0},
    {"x": 0, "y": 0}, {"x": 0, "y": 0, "z": 0, "w": 1}, None,
])
def test_position_rejects_invalid_external_values(bad):
    with pytest.raises(ValueError, match="position_body_m"):
        SensorPosition_Parse(bad)


def test_version_unit_and_origin_corruption_are_not_silently_reinterpreted(builtin_catalog):
    model = _Model_Get(builtin_catalog)
    _Positions_Set(model)
    data = model.Dictionary_Get()
    for version in (14, 17, 18, 19):
        with pytest.raises(ProjectModelError, match="requires project format_version 20"):
            ProjectModel_Parse({**data, "format_version": version})
    for key, value in (("unit", "mm"), ("frame", "ENU"), ("origin_kind", "primary_imu"),
                       ("origin_description", "bad\norigin")):
        bad = deepcopy(data)
        bad["sensor_installation"][key] = value
        with pytest.raises(ProjectModelError):
            ProjectModel_Parse(bad)
    data.pop("sensor_installation")
    with pytest.raises(ProjectModelError, match="requires sensor_installation"):
        ProjectModel_Parse(data)


@pytest.mark.parametrize("estimator", ["kf6", "sf6", "eskf15", None])
def test_every_backend_reports_unapplied_coordinates(builtin_catalog, estimator):
    model = _Model_Get(builtin_catalog, estimator)
    _Positions_Set(model)
    for result in (Project_EditValidate(model, builtin_catalog), Project_Validate(model, builtin_catalog)):
        issue = next(item for item in result.issues if item.code == "INSTALLATION_CONFIGURATION_ONLY")
        assert issue.level == "warning"
        assert "not applied" in issue.message and "Static calibration does not solve XYZ" in issue.message
        nonzero = next(item for item in result.issues if item.code == "INSTALLATION_NONZERO_UNCOMPENSATED")
        assert nonzero.level == "warning" and "NOT compensated" in nonzero.message
        assert "imu0" in nonzero.message and "gnss0" in nonzero.message
    if estimator == "eskf15":
        assert any(item.code == "INSTALLATION_LEGACY_GLOBAL_ARM"
                   for item in SensorInstallationIssues_Get(model, builtin_catalog))


def test_origin_required_for_generation_and_other_devices_cannot_claim_position(tmp_path, builtin_catalog):
    model = _Model_Get(builtin_catalog)
    model.sensor_installation = SensorInstallationConfiguration()
    editing = SensorInstallationIssues_Get(model, builtin_catalog, editing=True)
    assert next(item for item in editing if item.code == "INSTALLATION_ORIGIN_UNDEFINED").level == "warning"
    assembler = ProjectAssembler(WorkspacePolicy(tmp_path), builtin_catalog)
    plan = assembler.Plan(model, tmp_path / "undefined")
    assert not plan.valid and not plan.operations
    assert any(item.code == "INSTALLATION_ORIGIN_UNDEFINED" for item in plan.validation.issues)
    assert not (tmp_path / "undefined").exists()
    model.sensor_installation = SensorInstallationConfiguration(ORIGIN)
    model.device_instances.append(DeviceInstance("radio2", "silverstar.device.telemetry.sx1281",
                                                position_body_m=SensorPosition(1, 2, 3)))
    assert any(item.code == "INSTALLATION_DEVICE_UNSUPPORTED"
               for item in SensorInstallationIssues_Get(model, builtin_catalog))


def test_generated_contract_graph_and_legacy_parameters_remain_independent(builtin_catalog, workspace_root):
    model = _Model_Get(builtin_catalog, "eskf15")
    legacy_header = AlgorithmParametersHeader_Render(model, builtin_catalog)
    graph = SourceGraph_Resolve(model, builtin_catalog)
    initial_fingerprint = ProjectGenerationFingerprint_Get(model)
    _Positions_Set(model)
    assert SourceGraph_Resolve(model, builtin_catalog) == graph
    assert ProjectGenerationFingerprint_Get(model) != initial_fingerprint
    generated = GeneratedFiles_Render(model, builtin_catalog, graph)
    snapshot = json.loads(generated["Generated/project_sensor_installation.json"])
    assert snapshot["origin_description"] == ORIGIN
    assert {item["instance_id"]: item["position_body_m"] for item in snapshot["devices"]} == {
        "imu0": {"x": 0.0123456789, "y": -0.03, "z": 0.25},
        "gnss0": {"x": -0.04, "y": 0.05, "z": 1.2},
    }
    assert generated["Generated/Inc/project_algorithm_parameters.h"].decode() == legacy_header
    header = generated["Generated/Inc/project_sensor_installation.h"].decode()
    assert "PROJECT_SENSOR_INSTALLATION_RUNTIME_APPLIED 0U" in header
    assert "PROJECT_SENSOR_INSTALLATION_IMU0_BODY_X_M (0.0123456789)" in header
    # Check the shared contract's critical identity/range declarations without a new dependency.
    schema = json.loads((workspace_root.parents[1] / "contracts/sensor_installation_v1.schema.json").read_text(encoding="utf-8"))
    assert snapshot["schema"] == schema["properties"]["schema"]["const"] == SENSOR_INSTALLATION_SCHEMA
    assert schema["$defs"]["coordinate"]["maximum"] == SENSOR_POSITION_LIMIT_M
    assert schema["properties"]["runtime_applied"]["const"] is False


def test_numeric_editor_enter_commit_keeps_other_axis_import_precision(qapp):
    original = (0.123456789123, -0.234567891234, 1.234567891234)
    editor = SensorPositionEditor(Translator("en_US"), "imu0", original)
    changes = []
    editor.positionChanged.connect(changes.append)
    editor.show()
    spin = editor.coordinates["y"]
    spin.setFocus()
    spin.lineEdit().selectAll()
    QTest.keyClicks(spin.lineEdit(), "-0.75")
    assert not changes
    QTest.keyClick(spin, Qt.Key.Key_Return)
    assert changes == [(original[0], -0.75, original[2])]
    editor.recorded.setChecked(False)
    assert changes[-1] is None
    editor.close()


def test_real_gui_entry_instance_switch_language_and_save_reopen(tmp_path, workspace_root, qapp):
    # Qt's Windows offscreen plugin has no system fonts. Load a read-only local
    # font for meaningful screenshot/layout QA without changing application code.
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if not QFontDatabase.families() and font.is_file():
        assert QFontDatabase.addApplicationFont(str(font)) >= 0
    window = MainWindow(SettingsStore(tmp_path / "settings/scg.ini"), service=FccgService(workspace_root))
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    window._model = window._service.ReferenceProject_Create("InstallationGui013")
    # The existing GUI open workflow enables the Ground target. Start with the
    # same editing state so the whole-model assertion tests an actual roundtrip.
    window._model.ground_target = replace(window._model.ground_target, enabled=True)
    window._Project_Refresh()
    window.resize(1280, 900)
    window.show()
    window.pages.setCurrentWidget(window.devices_page)
    qapp.processEvents()
    try:
        page = window.devices_page
        assert not page.position_editors["imu0"].recorded.isChecked()
        assert not page.position_editors["imu0"].coordinates["x"].isEnabled()
        page.installation_origin.setText(ORIGIN)
        QTest.keyClick(page.installation_origin, Qt.Key.Key_Return)
        page.position_editors["imu0"].recorded.click()
        spin = page.position_editors["imu0"].coordinates["z"]
        spin.setFocus()
        spin.lineEdit().selectAll()
        QTest.keyClicks(spin.lineEdit(), "-0.125")
        assert window._model.DeviceInstance_Get("imu0").position_body_m.z == 0
        QTest.keyClick(spin, Qt.Key.Key_Return)
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("imu0").position_body_m == SensorPosition(0, 0, -0.125)
        assert window._model.DeviceInstance_Get("gnss0").position_body_m is None
        page.position_editors["gnss0"].recorded.click()
        gnss_spin = page.position_editors["gnss0"].coordinates["z"]
        gnss_spin.setFocus()
        gnss_spin.lineEdit().selectAll()
        QTest.keyClicks(gnss_spin.lineEdit(), "1.25")
        QTest.keyClick(gnss_spin, Qt.Key.Key_Return)
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("gnss0").position_body_m == SensorPosition(0, 0, 1.25)
        assert window._model.DeviceInstance_Get("imu0").position_body_m.z == -0.125
        window._DeviceInstance_Add("imu")
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("imu1").position_body_m is None
        before = window._model.sensor_installation
        window._CapabilitySource_Change("imu.acceleration", "imu1")
        window._CapabilitySource_Change("imu.angular_rate", "imu1")
        qapp.processEvents()
        assert window._model.capability_source_overrides["imu.acceleration"] == "imu1"
        assert window._model.sensor_installation == before
        window._DeviceVariant_Change("imu0", "uart", "jy901s")
        assert window._model.DeviceInstance_Get("imu0").profile == "jy901s"
        assert window._model.DeviceInstance_Get("imu0").position_body_m == SensorPosition(0, 0, -0.125)
        saved = window._model.Dictionary_Get()
        for language in ("en_US", "zh_CN"):
            window.Language_Apply(language)
            assert window._model.Dictionary_Get() == saved
        ProjectRoot_Save(window._model, tmp_path / "gui-project")
        window._Project_Open(tmp_path / "gui-project")
        qapp.processEvents()
        assert window._model.Dictionary_Get() == saved
        assert page.position_editors["imu0"].coordinates["z"].value() == -0.125
        assert page.installation_origin.text() == ORIGIN
        assert not list((tmp_path / "gui-project").rglob("*.bin"))
        assert not list((tmp_path / "gui-project").rglob("*.ssdecoder"))
        scroll = page.findChild(QScrollArea)
        for language in ("en_US", "zh_CN"):
            window.Language_Apply(language)
            qapp.processEvents()
            scroll.verticalScrollBar().setValue(0)
            QTest.qWait(100)
            assert page.position_editors["imu0"].coordinates["z"].isVisible()
            assert window.grab().save(str(tmp_path / ("installation-gui-" + language + ".png")))
        scroll.ensureWidgetVisible(page.position_editors["gnss0"])
        QTest.qWait(100)
        assert window.grab().save(str(tmp_path / "installation-gnss-zh_CN.png"))
    finally:
        window.close()
        qapp.processEvents()


def test_fresh_generation_and_regeneration_preserve_owned_payload(tmp_path, builtin_catalog):
    model = _Model_Get(builtin_catalog)
    _Positions_Set(model)
    root = tmp_path / "generated"
    assembler = ProjectAssembler(WorkspacePolicy(tmp_path), builtin_catalog)
    plan = assembler.Plan(model, root)
    assert plan.valid, plan.validation.issues
    assembler.Apply(model, plan)
    payload = root / "Devices/IMU/JY901B/Src/jy901b_device.c"
    original = payload.read_bytes() + b"\n/* project-owned sentinel */\n"
    payload.write_bytes(original)
    reopened = ProjectModel_Load(root / "SilverStar.ssproject")
    reopened.device_instances = [replace(item, position_body_m=SensorPosition(0.2, 0.3, 0.4))
                                 if item.instance_id == "imu0" else item for item in reopened.device_instances]
    plan = assembler.Plan(reopened, root)
    assert plan.valid, plan.validation.issues
    assert next(op for op in plan.operations if op.target.endswith("JY901B/Src/jy901b_device.c")).operation == "PRESERVE"
    assembler.Apply(reopened, plan)
    assert payload.read_bytes() == original
    assert json.loads((root / "Generated/project_sensor_installation.json").read_text(encoding="utf-8"))["devices"][0]["position_body_m"] == {"x": 0.2, "y": 0.3, "z": 0.4}
    # Compile the emitted data header with actual Host and ARM compilers. This
    # verifies the config surface, not a firmware link or runtime compensation.
    source = tmp_path / "installation_header.c"
    source.write_text('#include "project_sensor_installation.h"\n'
                      'int Installation_ConfigCheck(void) { return PROJECT_SENSOR_INSTALLATION_RUNTIME_APPLIED == 0U && '
                      'PROJECT_SENSOR_INSTALLATION_IMU0_BODY_X_M == 0.2; }\n', encoding="utf-8")
    for compiler in ("gcc", "arm-none-eabi-gcc"):
        executable = shutil.which(compiler)
        if executable is None:
            pytest.skip(f"{compiler} unavailable; config-header compilation not executed")
        command = [executable, "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", str(source),
                   "-I", str(root / "Generated/Inc"), "-o", str(tmp_path / (compiler + ".o"))]
        result = subprocess.run(command, capture_output=True, text=True)
        (tmp_path / (compiler + "-command.json")).write_text(json.dumps({
            "command": command, "exit_code": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr,
            "scope": "generated configuration header compile only; no firmware link",
        }, indent=2) + "\n", encoding="utf-8")
        assert result.returncode == 0, result.stdout + result.stderr
