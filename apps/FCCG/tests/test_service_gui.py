from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.dialogs import NewProjectWizard
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import StandardCheckBox


def test_gui_service_loads_catalog_opens_project_and_previews(
    tmp_path: Path, workspace_root: Path, qapp
) -> None:
    service = FccgService(workspace_root)
    window = MainWindow(
        SettingsStore(tmp_path / "service-settings.ini"),
        service=service,
        language="en_US",
    )
    wizard = NewProjectWizard(window._translator, window)
    project_root = tmp_path / "GeneratedReference"
    model = service.ReferenceProject_Create("GeneratedReference")
    initial_plan = service.GenerationPlan_Create(model, project_root)
    assert initial_plan.validation.valid
    service.GenerationPlan_Apply(model, initial_plan)
    project_file = project_root / "SilverStar.ssproject"
    try:
        assert window.plugin_manager_dialog.panel.plugin_table.rowCount() == len(
            service.catalog.All_Get()
        )
        assert window.plugin_manager_dialog.panel.plugin_table.columnCount() == 9
        assert {"imu0", "gnss0"}.issubset(
            window.devices_page.device_combos
        )
        wizard_values = wizard.WizardData_Get()
        assert set(wizard_values) == {"name", "output_directory"}
        window._Project_Open(project_file)
        assert window.current_project_value.text() == "GeneratedReference"
        logging_table = window.flight_configuration_page.logging_table
        assert logging_table.rowCount() == len(window._model.logging_streams)
        periodic_row = next(
            row
            for row in range(logging_table.rowCount())
            if logging_table.cellWidget(row, 0)
            .findChild(StandardCheckBox)
            .property("streamId")
            == "FLIGHT_LOG_RECORD_TELEMETRY_DIAG"
        )
        period_editor = logging_table.cellWidget(periodic_row, 5)
        assert period_editor.unit_combo.currentData() == "s"
        period_editor.unit_combo.setCurrentIndex(period_editor.unit_combo.findData("ms"))
        period_editor.value_spin.setValue(250)
        QTest.keyClick(period_editor.value_spin, Qt.Key.Key_Return)
        window._ProjectModel_Sync()
        assert next(
            stream
            for stream in window._model.logging_streams
            if stream.record == "FLIGHT_LOG_RECORD_TELEMETRY_DIAG"
        ).period_us == 250_000
        normal_plan = service.GenerationPlan_Create(window._model, project_root)
        assert normal_plan.validation.valid
        assert not normal_plan.dangerous
        assert any(
            operation.target == "SilverStar.ssproject"
            for operation in normal_plan.operations
        )
        device_id = "silverstar.device.imu.jy901b"
        window._DeviceInstance_Change("imu0", "")
        assert device_id not in window._model.DevicePluginIds_Get()
        window._DeviceInstance_Change("imu0", device_id)
        assert device_id in window._model.DevicePluginIds_Get()
        assert service.Resources_AutoAssign(window._model).valid
        resource_key = "launch_ignition0:output"
        resource_row = next(
            row
            for row in range(window.board_hardware_page.resource_table.rowCount())
            if "launch_ignition0:output"
            in window.board_hardware_page.resource_table.item(row, 0).toolTip()
        )
        resource_editor = window.board_hardware_page.resource_table.cellWidget(
            resource_row, 3
        )
        assert resource_editor.property("fixedResource") is True
        assert resource_key in window._model.resource_assignments
        window._Resources_AutoAssign()
        assert resource_key in window._model.resource_assignments
        documentation = service.PluginDocumentationRoot_Get(
            "silverstar.protocol.telemetry.air_m0"
        )
        assert (documentation / "AIR_PROTOCOL.md").is_file()
        assert (project_root / "Flight_Controller.code-workspace").is_file()
        assert (project_root / ".vscode" / "tasks.json").is_file()
        assert (project_root / ".eide" / "eide.yml").is_file()
    finally:
        wizard.close()
        window.close()
        qapp.processEvents()
