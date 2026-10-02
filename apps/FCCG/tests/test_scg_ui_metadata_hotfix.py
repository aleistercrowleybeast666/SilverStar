from dataclasses import replace
import time
import json
import hashlib
import yaml

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.model import HardwareResource
from silverstar_fccg.ui.main_window import MainWindow
from test_f103_ground_reference import _GroundF103Model_Get


@pytest.fixture
def window(qapp, workspace_root, tmp_path):
    current = MainWindow(SettingsStore(tmp_path / "scg.ini"), service=FccgService(workspace_root))
    current._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    yield current
    current.close()
    qapp.processEvents()


@pytest.fixture(scope="module")
def generated_pair(workspace_root, tmp_path_factory):
    root = tmp_path_factory.mktemp("scg_generated_pair")
    service = FccgService(workspace_root)
    model = _GroundF103Model_Get(service.catalog)
    TargetGeneration_Apply(model, service.catalog, service.policy, root, TargetScope.ALL)
    return root


def test_ground_native_workspace_matches_existing_make_graph(window, generated_pair):
    workspace = generated_pair / "Ground_Station/Ground_Station.code-workspace"
    document = yaml.safe_load((workspace.parent / ".eide/eide.yml").read_text(encoding="utf8"))
    graph = json.loads((workspace.parent / "Generated/ground_source_graph.json").read_text(encoding="utf8"))
    actual = [item["path"] for item in document["virtualFolder"]["files"]]
    assert set(actual) == set(graph["sources"]) | set(graph["asm_sources"])
    assert len(actual) == len(set(actual))
    assert not document["srcDirs"]
    for target in document["targets"].values():
        gcc = target["toolchainConfigMap"]["GCC"]
        assert gcc["cpuType"] == "Cortex-M3"
        assert gcc["floatingPointHardware"] == "none"
        assert gcc["scatterFilePath"] == graph["linker_script"] == "STM32F103XX_FLASH.ld"
        assert gcc["options"]["global"]["misc-control"] == "-mcpu=cortex-m3 -mthumb -mfloat-abi=soft"
        assert set(target["cppPreprocessAttrs"]["defineList"]) == set(graph["defines"])
        assert set(target["cppPreprocessAttrs"]["incList"]) == set(graph["include_dirs"])
        assert target["uploadConfigMap"]["OpenOCD"]["target"] == "stm32f1x"
        assert gcc["options"]["global"]["toolPrefix"] == "arm-none-eabi-"
        assert gcc["options"]["linker"]["$outputTaskExcludes"] == []
    assert window._VsCodeWorkspace_Validate(workspace) == ""
    flight = generated_pair / "Flight_Controller/Flight_Controller.code-workspace"
    assert window._VsCodeWorkspace_Validate(flight) == ""


def test_workspace_validation_keeps_flight_and_folder_guards(window, tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    flight = root / "Flight_Controller.code-workspace"
    flight.write_text('{"folders":[{"path":"."}]}', encoding="utf8")
    (root / "Makefile").write_text("all:\n", encoding="utf8")
    assert window._VsCodeWorkspace_Validate(flight)
    ground = root / "Ground_Station.code-workspace"
    ground.write_text('{"folders":[{"path":".."}]}', encoding="utf8")
    assert window._VsCodeWorkspace_Validate(ground) == window._translator.Text_Get("error.vscode_workspace_folder")
    ground.write_text('{"folders":[{"path":"."}]}', encoding="utf8")
    assert window._VsCodeWorkspace_Validate(ground)


def test_real_ground_generation_reports_intermediate_progress(qapp, window, tmp_path, monkeypatch):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._project_root = tmp_path / "real_gui_ground"
    window._Project_Refresh()
    errors = []
    values = []
    original = window._Task_Progress
    def observe(progress, code):
        values.append(progress)
        original(progress, code)
    monkeypatch.setattr(window, "_Error_Show", lambda *args: errors.append(args))
    monkeypatch.setattr(window, "_Task_Progress", observe)
    # Planning already reports progress in the baseline. Verify the actual
    # apply phase separately so planning alone cannot satisfy this regression.
    import silverstar_fccg.ui.main_window as main_window_module
    apply_events = []
    original_apply = main_window_module.TargetGeneration_Apply
    def observe_apply(*args, **kwargs):
        callback = kwargs.get("progress_callback")
        if callback is not None:
            def apply_progress(current, total, subject, done):
                apply_events.append((current, total, subject, done))
                callback(current, total, subject, done)
            kwargs["progress_callback"] = apply_progress
        return original_apply(*args, **kwargs)
    monkeypatch.setattr(main_window_module, "TargetGeneration_Apply", observe_apply)
    window._Targets_Generate("generate_ground")
    assert window.progress_bar.value() == 0
    deadline = time.monotonic() + 120
    while window._active_worker is not None and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
        QTest.qWait(5)
    assert window._active_worker is None
    assert not errors
    assert window.progress_bar.value() == 1000
    assert any(0 < current < total for current, total, subject, done in apply_events)
    assert apply_events[-1][2:] == ("project_descriptor", True)
    assert values == sorted(values)
    assert any(0 < value < 1 for value in values), values
    assert (window._project_root / "Ground_Station/Makefile").is_file()


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_fixed_ground_uart_row_hidden_with_source_and_binding_preserved(window, language):
    window.Language_Apply(language)
    window._model = _GroundF103Model_Get(window._service.catalog)
    before = window._model.ground_target
    window._Project_Refresh()
    page = window.ground_target_page
    assert page.pc_resource.isHidden()
    assert page.pc_resource.currentData() == "PLATFORM_UART_1"
    assert "USART1" in page.pc_resource_source.text()
    assert "PLATFORM_UART_1" in page.pc_resource_source.text()
    assert window._model.ground_target == before
    # A real choice and a stale binding must remain recoverable in the UI.
    second = HardwareResource("OTHER_UART", "uart", {"physical_resource": "USART2"})
    window._model.ground_target = replace(before, hardware=replace(before.hardware, resources=(*before.hardware.resources, second)))
    window._Project_Refresh()
    assert not page.pc_resource.isHidden()
    window._model.ground_target = replace(before, pc_resource="MISSING_UART")
    window._Project_Refresh()
    assert not page.pc_resource.isHidden()
    assert page.pc_resource.currentData() == "MISSING_UART"
    assert page.pc_resource_notice.text()


@pytest.mark.parametrize("plugin", ["bmp280", "bmp390", "ms5611"])
def test_existing_barometer_gui_adds_up_to_four_without_runtime_changes(window, plugin):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    identity = "silverstar.device.barometer." + plugin
    page = window.devices_page
    combo = page.device_combos["barometer0"]
    combo.setCurrentIndex(combo.findData(identity))
    for count in range(1, 4):
        barometers = [item for item in window._model.device_instances if item.plugin == identity]
        assert len(barometers) == count
        page.add_buttons["barometer"].click()
    barometers = [item for item in window._model.device_instances if item.plugin == identity]
    assert len(barometers) == 4
    assert len({item.instance_id for item in barometers}) == 4
    assert "barometer" not in page.add_buttons
    manifest = window._service.Plugin_Get(identity)
    assert manifest.instance_policy.multi_instance_ready
    assert manifest.instance_policy.class_max == 4


def test_ground_regeneration_preserves_uploader_and_rejects_modified_build_fields(workspace_root, tmp_path):
    service = FccgService(workspace_root)
    model = _GroundF103Model_Get(service.catalog)
    root = tmp_path / "owned_ground"
    TargetGeneration_Apply(model, service.catalog, service.policy, root, TargetScope.GROUND)
    ground = root / "Ground_Station"
    eide = ground / ".eide/eide.yml"
    document = yaml.safe_load(eide.read_text(encoding="utf8"))
    for target in document["targets"].values():
        target["uploader"] = "STLink"
        target["uploadConfigMap"]["STLink"]["speed"] = 500
        target["settings"]["debugger"] = "user-debugger"
    eide.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf8")
    before = eide.read_bytes()
    TargetGeneration_Apply(model, service.catalog, service.policy, root, TargetScope.GROUND)
    assert eide.read_bytes() == before
    ownership = json.loads((ground / ".silverstar-ground-ownership.json").read_text(encoding="utf8"))
    assert ".eide/eide.yml" in ownership["files"]
    assert ownership["eide"]["owned_fields"]["targets"]["Release"]["toolchain_configuration"]["cpuType"] == "Cortex-M3"
    document["targets"]["Release"]["toolchainConfigMap"]["GCC"]["cpuType"] = "Cortex-M4"
    eide.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf8")
    before_reject = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="build-owned fields have local changes"):
        TargetGeneration_Apply(model, service.catalog, service.policy, root, TargetScope.GROUND)
    after_reject = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    assert before_reject == after_reject


@pytest.mark.parametrize("scope", [TargetScope.FLIGHT, TargetScope.GROUND, TargetScope.ALL])
def test_real_generation_progress_is_monotonic_and_finishes_only_after_descriptor(workspace_root, tmp_path, scope):
    service = FccgService(workspace_root)
    model = _GroundF103Model_Get(service.catalog)
    root = tmp_path / scope.value
    events = []
    def progress(current, total, subject, done):
        events.append(((current if done else current - 1) / total, subject))
        if done and current == total:
            assert (root / "SilverStar.ssproject").is_file()
    TargetGeneration_Apply(model, service.catalog, service.policy, root, scope, progress_callback=progress)
    values = [value for value, _subject in events]
    assert values[0] == 0
    assert values[-1] == 1
    assert values == sorted(values)
    assert any(0 < value < 1 for value in values)


@pytest.mark.parametrize("prefix", ["", "custom-arm-"])
def test_ground_eide_tool_prefix_matches_make_override(workspace_root, prefix):
    from silverstar_fccg.generator.multi_target import GroundFiles_Render
    service = FccgService(workspace_root)
    model = _GroundF103Model_Get(service.catalog)
    model.ground_target = replace(model.ground_target,
        build=replace(model.ground_target.build, toolchain_prefix=prefix))
    files = GroundFiles_Render(model, service.catalog, service.policy)
    expected = prefix or "arm-none-eabi-"
    assert "CC := " + expected + "gcc\n" in files["Makefile"].decode("utf8")
    document = yaml.safe_load(files[".eide/eide.yml"].decode("utf8"))
    for target in document["targets"].values():
        assert target["toolchainConfigMap"]["GCC"]["options"]["global"]["toolPrefix"] == expected


def test_algorithm_parameter_region_collapses_without_changing_values(window):
    window._model = _GroundF103Model_Get(window._service.catalog)
    window._Project_Refresh()
    page = window.algorithm_parameters_page
    section = page.parameters_section
    before = json.dumps(window._model.Dictionary_Get(), sort_keys=True)
    assert not section.Expanded_Is()
    assert section.body.isHidden()
    section.toggle_button.click()
    assert section.Expanded_Is()
    assert not section.body.isHidden()
    window.Language_Apply("en_US")
    assert section.Expanded_Is()
    assert section.toggle_button.text() == window._translator.Text_Get("navigation.parameters")
    assert section.toggle_button.objectName() == "collapsibleHeader"
    section.toggle_button.click()
    assert section.body.isHidden()
    assert json.dumps(window._model.Dictionary_Get(), sort_keys=True) == before


def test_new_draft_enables_ground_without_changing_reference_or_existing_projects(workspace_root):
    from silverstar_fccg.project.model import ProjectModel_Parse
    service = FccgService(workspace_root)
    draft = service.ProjectDraft_Create("NewGroundDefault")
    assert draft.ground_target.enabled
    assert not draft.ground_target.board and not draft.ground_target.mcu
    assert not service.ReferenceProject_Create("Reference").ground_target.enabled
    old = draft.Dictionary_Get()
    old["ground_target"]["enabled"] = False
    assert not ProjectModel_Parse(old).ground_target.enabled


def test_flight_export_with_empty_enabled_ground_matches_disabled_ground(workspace_root, tmp_path):
    from silverstar_fccg.project.model import GroundTargetConfiguration
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create("FlightOnly")
    model.ground_target = GroundTargetConfiguration(enabled=True)
    enabled_root = tmp_path / "enabled_ground"
    disabled_root = tmp_path / "disabled_ground"
    TargetGeneration_Apply(model, service.catalog, service.policy, enabled_root, TargetScope.FLIGHT)
    assert model.ground_target.enabled
    assert not (enabled_root / "Ground_Station/Makefile").exists()
    model.ground_target = replace(model.ground_target, enabled=False)
    TargetGeneration_Apply(model, service.catalog, service.policy, disabled_root, TargetScope.FLIGHT)
    def firmware_files(root):
        return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and
                (p.suffix.lower() in (".c", ".h", ".s", ".ld") or p.name == "Makefile")}
    assert firmware_files(enabled_root) == firmware_files(disabled_root)


def test_qt_flight_button_exports_with_enabled_unconfigured_ground(qapp, window, tmp_path, monkeypatch):
    from PySide6.QtCore import Qt
    from silverstar_fccg.project.model import GroundTargetConfiguration
    from silverstar_fccg.project.air_link import GroundTargetIssues_Get
    window._model = window._service.ReferenceProject_Create("QtFlightOnly")
    window._model.ground_target = GroundTargetConfiguration(enabled=True)
    window._project_root = tmp_path / "qt_flight_only"
    window._Project_Refresh()
    ground = window._model.ground_target
    assert ground.enabled and not ground.mcu and not ground.radio_instances
    assert GroundTargetIssues_Get(window._model, window._service.catalog)
    errors, plans = [], []
    monkeypatch.setattr(window, "_Error_Show", lambda *args: errors.append(args))
    original_plan = window._GenerationPlan_ApplyAllowed
    def observe_plan(plan):
        plans.append(plan)
        return original_plan(plan)
    monkeypatch.setattr(window, "_GenerationPlan_ApplyAllowed", observe_plan)
    window.pages.setCurrentWidget(window.board_hardware_page)
    window.show()
    qapp.processEvents()
    button = window.board_hardware_page.generate_button
    assert button.isEnabled() and button.isVisible()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert window._active_worker is not None
    deadline = time.monotonic() + 120
    while (window._active_worker is not None) and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
        QTest.qWait(5)
    assert window._active_worker is None
    assert not errors, errors
    assert len(plans) == 1 and plans[0].valid
    assert window.progress_bar.value() == 1000
    assert window._model.ground_target == ground
    root = window._project_root
    assert (root / "Flight_Controller/Makefile").is_file()
    # Saving the root creates the established empty target directories.
    # Flight-only generation must not materialize any Ground payload.
    assert not any(path.is_file() for path in (root / "Ground_Station").rglob("*"))
    descriptor = json.loads((root / "SilverStar.ssproject").read_text(encoding="utf8"))
    assert descriptor["ground_target"]["enabled"] is True
