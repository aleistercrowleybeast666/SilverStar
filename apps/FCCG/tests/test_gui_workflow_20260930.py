"""Project workflow and display-name regressions from native desktop QA."""
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.folder_contract import ProjectRoot_Save
from silverstar_fccg.project.logging import LogAvailability_Get, ProtocolLogDefinitions_Get
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import StandardCheckBox


def test_new_project_defaults_are_ready_for_log_and_deployment_selection(workspace_root):
    service = FccgService(workspace_root)
    model = service.ProjectDraft_Create("Defaults")
    assert model.strategies["estimator"] == "silverstar.algorithm.estimator.kf6"
    assert model.strategies["ins"] == "silverstar.algorithm.ins.coning2_sculling2"
    assert model.modes["deployment"] == ["ApogeeVerticalVelocity", "Tilt"]
    definition = next(d for d in ProtocolLogDefinitions_Get(model, service.catalog)
                      if d.record == "FLIGHT_LOG_RECORD_ALIGNMENT_RESULT")
    assert LogAvailability_Get(definition, model, service.catalog).available
    assert next(s for s in model.logging_streams if s.record == definition.record).enabled


@pytest.mark.parametrize("language", ["zh_CN", "en_US"])
def test_device_titles_use_display_names_and_fallback_for_extensions(qapp, tmp_path, language):
    window = MainWindow(SettingsStore(tmp_path / "names.ini"), language=language)
    try:
        labels = [label.text() for label in window.devices_page.findChildren(QLabel)]
        assert not any("device.instance." in text or "capability." in text for text in labels)
        component = next(c for c in window._component_views if c.component_class == "barometer")
        extension = replace(component, component_class="private_extension_class",
                            name="Extension Pressure Sensor")
        assert window.devices_page._DeviceClassTitle_Get(extension) == extension.name
        title = window.devices_page._DeviceInstanceTitle_Get(extension, 2)
        assert title == "Extension Pressure Sensor 2"
        assert "private_extension_class" not in title
    finally:
        window.close()
        qapp.processEvents()


def test_ground_pc_settings_are_on_configuration_and_hardware_actions_remain(qapp, tmp_path):
    window = MainWindow(SettingsStore(tmp_path / "ground.ini"))
    try:
        config = window.ground_configuration_page
        ground = window.ground_target_page
        assert config.isAncestorOf(ground.pc_interface)
        assert config.isAncestorOf(ground.pc_resource)
        assert config.isAncestorOf(ground.enabled)
        assert ground.isAncestorOf(ground.board)
        assert ground.isAncestorOf(ground.import_ioc)
        assert ground.isAncestorOf(ground.save_instance)
        assert ground.isAncestorOf(ground.generate_button)
        assert not window.board_hardware_page.custom_widget.isHidden()
        row = next(i for i, s in enumerate(window.flight_configuration_page._streams)
                   if s.stream_id == "FLIGHT_LOG_RECORD_ALIGNMENT_RESULT")
        table = window.flight_configuration_page.logging_table
        check = table.cellWidget(row, 0).findChild(StandardCheckBox)
        assert check.isChecked()
        assert "自动" in table.item(row, 6).text()
    finally:
        window.close()
        qapp.processEvents()


def test_create_root_preserves_same_named_input_and_existing_descriptor(builtin_catalog, tmp_path):
    from silverstar_fccg.project.reference import ReferenceProject_Create
    model = ReferenceProject_Create("Preserve", catalog=builtin_catalog)
    root = tmp_path / "preserve"
    root.mkdir()
    input_file = root / "Ground_Station"
    input_file.write_bytes(b"user input")
    with pytest.raises(FileExistsError):
        ProjectRoot_Save(model, root, create_new=True)
    assert input_file.read_bytes() == b"user input"
    assert not (root / "Flight_Controller").exists()
    assert not (root / "SilverStar.ssproject").exists()
    input_file.rename(root / "preserved_input")
    ProjectRoot_Save(model, root, create_new=True)
    descriptor = root / "SilverStar.ssproject"
    previous = descriptor.read_bytes()
    model.strategies["estimator"] = None
    with pytest.raises(FileExistsError):
        ProjectRoot_Save(model, root, create_new=True)
    assert descriptor.read_bytes() == previous
