from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
)

import silverstar_fccg.ui.main_window as main_window_module
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.app.version import PRODUCT_NAME, __version__
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.generator.assembler import ApplyResult, GenerationPlan
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.project.protocols import ProtocolResolution_Resolve
from silverstar_fccg.project.validation import ProjectValidationResult
from silverstar_fccg.ui.dialogs import NewProjectWizard
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.widgets import LockedCheckBox, StandardCheckBox


def _Window_Create(tmp_path: Path, qapp) -> MainWindow:
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"))
    window.show()
    qapp.processEvents()
    return window


def test_build_log_and_internal_build_actions_are_advanced_only(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        advanced = window.build_page.advanced_section
        assert not advanced.Expanded_Is()
        assert advanced.body.isAncestorOf(window.build_page.build_log)
        assert advanced.body.isHidden()
        assert "flight_build" in window.build_page.action_buttons
        assert "ground_build" in window.build_page.action_buttons
        assert "generate_flight" not in window.build_page.action_buttons
        assert "build_release" not in window.build_page.action_buttons
        assert "flash" not in window.build_page.action_buttons
    finally:
        window.close()
        qapp.processEvents()


def test_actuators_are_optional_and_parachute_removal_clears_modes(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        launch_id = "silverstar.device.actuator.launch_ignition"
        parachute_id = "silverstar.device.actuator.parachute_pyro"
        launch = window.devices_page.device_checks[launch_id]
        parachute = window.devices_page.device_checks[parachute_id]
        assert isinstance(launch, StandardCheckBox)
        assert not isinstance(launch, LockedCheckBox)
        assert isinstance(parachute, StandardCheckBox)
        assert not isinstance(parachute, LockedCheckBox)
        assert window.devices_page.device_checks[launch_id].text() == (
            "起飞点火功率输出"
        )
        assert window.devices_page.device_checks[parachute_id].text() == (
            "火工开伞功率输出"
        )
        actuator_texts = [
            window.devices_page.actuator_checks_layout.itemAt(index).widget().text()
            for index in range(
                window.devices_page.actuator_checks_layout.count()
            )
        ]
        assert actuator_texts[:2] == ["起飞点火功率输出", "火工开伞功率输出"]
        assert not window.devices_page.install_button.isVisible()

        launch.click()
        qapp.processEvents()
        assert launch_id not in window._model.DevicePluginIds_Get()
        assert "launch_ignition0:output" not in window._model.resource_assignments
        assert window._model.modes["deployment"]

        parachute = window.devices_page.device_checks[parachute_id]
        parachute.click()
        qapp.processEvents()
        assert parachute_id not in window._model.DevicePluginIds_Get()
        assert "parachute_pyro0:output" not in window._model.resource_assignments
        assert window._model.modes["deployment"] == []

        window._OtherDevice_Toggle(parachute_id, True)
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("parachute_pyro0") is not None
        assert window._model.modes["deployment"] == [
            "ApogeeVerticalVelocity",
            "Tilt",
        ]
    finally:
        window.close()
        qapp.processEvents()


def test_vscode_workspace_launcher_prefers_code_cmd_and_opens_new_window(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = _Window_Create(tmp_path, qapp)
    install_root = tmp_path / "Microsoft VS Code"
    launcher = install_root / "bin" / "code.cmd"
    workspace = tmp_path / "LaunchTest.code-workspace"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("@echo off\n", encoding="utf-8")
    workspace.write_text('{"folders": [{"path": "."}]}\n', encoding="utf-8")
    (tmp_path / ".eide").mkdir()
    (tmp_path / ".eide" / "eide.yml").write_text(
        "version: 4.1\n", encoding="utf-8"
    )
    calls: list[tuple[str | list[str], dict[str, object]]] = []

    class ProcessFixture:
        stderr = None

        @staticmethod
        def wait(*, timeout: float) -> None:
            raise main_window_module.subprocess.TimeoutExpired(
                "code.cmd", timeout
            )

    def launch(
        command: str | list[str], **kwargs: object
    ) -> ProcessFixture:
        calls.append((command, kwargs))
        return ProcessFixture()

    monkeypatch.setattr(
        main_window_module.shutil,
        "which",
        lambda command: str(launcher) if command == "code.cmd" else None,
    )
    monkeypatch.setattr(main_window_module.subprocess, "Popen", launch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "missing-local"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "missing-program-files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "missing-program-files-x86"))
    try:
        result = window._VsCodeWorkspace_Launch(workspace)
        assert result.succeeded
        command, arguments = calls[0]
        command_text = command if isinstance(command, str) else " ".join(command)
        assert str(launcher.resolve()) in command_text
        assert "--new-window" in command_text
        assert str(workspace.resolve()) in command_text
        assert " /d /s /c \"\"" in command_text
        assert command_text.endswith('"')
        assert arguments["cwd"] == str(tmp_path.resolve())
        assert arguments["creationflags"] == getattr(
            main_window_module.subprocess, "CREATE_NO_WINDOW", 0
        )
    finally:
        window.close()
        qapp.processEvents()


def test_vscode_workspace_open_failure_shows_exact_reason(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = _Window_Create(tmp_path, qapp)
    target_root = tmp_path / "Flight_Controller"
    target_root.mkdir()
    workspace = target_root / "Flight_Controller.code-workspace"
    workspace.write_text('{"folders": [{"path": "."}]}\n', encoding="utf-8")
    (tmp_path / ".eide").mkdir()
    (tmp_path / ".eide" / "eide.yml").write_text(
        "version: 4.1\n", encoding="utf-8"
    )
    window._project_root = tmp_path
    dialogs: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        window,
        "_VsCodeWorkspace_Launch",
        lambda _workspace: main_window_module._WorkspaceLaunchResult(
            False, "fixture launcher failure"
        ),
    )
    monkeypatch.setattr(
        window,
        "_MessageBox_Exec",
        lambda *arguments: dialogs.append(arguments),
    )
    try:
        window._GeneratedProject_Open("open_vscode")
        assert len(dialogs) == 1
        assert str(workspace.resolve()) in str(dialogs[0][2])
        assert "fixture launcher failure" not in str(dialogs[0][2])
    finally:
        window.close()
        qapp.processEvents()


def test_vscode_workspace_launcher_reports_missing_installation_and_association(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    window = _Window_Create(tmp_path, qapp)
    workspace = tmp_path / "MissingLauncher.code-workspace"
    workspace.write_text('{"folders": [{"path": "."}]}\n', encoding="utf-8")
    (tmp_path / ".eide").mkdir()
    (tmp_path / ".eide" / "eide.yml").write_text(
        "version: 4.1\n", encoding="utf-8"
    )

    class DesktopServicesFixture:
        @staticmethod
        def openUrl(_url) -> bool:
            return False

    monkeypatch.setattr(main_window_module.shutil, "which", lambda _command: None)
    monkeypatch.setattr(
        main_window_module, "QDesktopServices", DesktopServicesFixture
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "missing-local"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "missing-program-files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "missing-program-files-x86"))
    try:
        result = window._VsCodeWorkspace_Launch(workspace)
        assert not result.succeeded
        assert "Code.exe" in result.reason
        assert ".code-workspace" in result.reason
    finally:
        window.close()
        qapp.processEvents()


def test_main_window_shell_navigation_theme_and_language(tmp_path: Path, qapp) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        assert window.windowTitle() == PRODUCT_NAME
        assert window.version_label.text() == f"v{__version__}"
        assert window.pages.count() == 7
        assert window.navigation_list.count() == 7
        assert not hasattr(window, "project_page")
        assert not hasattr(window, "plugins_page")
        assert [
            window.navigation_list.item(index).text()
            for index in range(window.navigation_list.count())
        ] == ["飞控设备", "飞行配置", "导航配置", "遥测配置", "飞控硬件", "地面站硬件", "构建与检测"]
        assert not hasattr(window.build_page, "configuration_combo")
        assert set(window.build_page.action_buttons) == {
            "flight_build", "flight_clean", "flight_open_vscode",
            "flight_open_folder", "flight_artifact_check",
            "ground_build", "ground_clean", "ground_open_vscode",
            "ground_open_folder", "ground_artifact_check",
            "open_firmware_output",
            "host_tests",
            "architecture_check",
            "power10_check",
            "static_analysis",
            "artifact_check",
            "tool_install_guide",
        }
        assert not window.build_page.action_buttons["flight_open_vscode"].isEnabled()
        assert not window.build_page.action_buttons["ground_open_folder"].isEnabled()
        assert not window.build_page.action_buttons[
            "open_firmware_output"
        ].isEnabled()
        assert "build_release" not in window.build_page.action_buttons
        assert "flash" not in window.build_page.action_buttons
        assert window.save_as_action.shortcut().toString() == "Ctrl+Shift+S"
        assert window.plugin_manager_dialog.panel.plugin_table.rowCount() == len(window._component_views)
        for index in range(window.pages.count()):
            window.navigation_list.setCurrentRow(index)
            assert window.pages.currentIndex() == index

        window.Language_Apply("en_US")
        # The 0.1.1 header is deliberately compact in both languages; the full
        # product expansion remains in About, without widening the header.
        assert window.title_label.text() == "SilverStar SCG"
        assert [
            window.navigation_list.item(index).text()
            for index in range(window.navigation_list.count())
        ] == [
                "Flight Devices",
                "Flight Configuration",
                "Navigation Configuration",
                "Telemetry Configuration",
                "Flight Hardware",
                "Ground Station Hardware",
                "Build & Validation",
            ]
        assert window.build_page.action_buttons["flight_build"].text() == "Build Firmware"
        assert all(
            "Build Release" not in button.text()
            for button in window.build_page.action_buttons.values()
        )
        window.Theme_Apply("dark")
        assert window._theme == "dark"
        assert "#0B2447" in qapp.styleSheet()
        window.Theme_Apply("light")
        assert "#123A78" in qapp.styleSheet()
    finally:
        window.close()


def test_ground_page_excludes_flight_board_and_owns_uart_binding(tmp_path: Path, qapp) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        page = window.ground_target_page
        page.enabled.setChecked(True)
        assert page.board.findData("silverstar.board.silverstar_0_5") == -1
        assert page.board.currentData() is None  # Shared hardware page's unselected state.
        page.radio.setCurrentIndex(
            page.radio.findData("silverstar.device.telemetry.sx1281")
        )
        page.module.setCurrentIndex(page.module.findData("e28_2g4m12sx"))
        page.pc_interface.setCurrentIndex(page.pc_interface.findData("uart"))
        assert "GROUND_UART_UNBOUND" in page.status.text()
        frequency = window.air_link_page.fields["frequency_hz"]
        frequency.CommittedValue_Set(2473.0)
        frequency.lineEdit().setText("2400.000")
        QTest.keyClick(frequency, Qt.Key.Key_Return)
        assert "AIR_LINK_FREQUENCY_OUT_OF_RANGE" in window.air_link_page.status.text()
    finally:
        window.close()


def test_new_project_wizard_is_one_step_and_requires_identity(tmp_path: Path, qapp) -> None:
    window = _Window_Create(tmp_path, qapp)
    wizard = NewProjectWizard(window._translator, window)
    try:
        wizard.show()
        qapp.processEvents()
        assert isinstance(wizard, QDialog)
        assert wizard.height() <= 220
        assert wizard.windowTitle() == "新建 SilverStar 飞控工程"
        assert not wizard.identity_page.isComplete()
        assert not wizard.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).isEnabled()
        page = wizard.identity_page
        assert page.name_label.alignment() == (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        assert page.output_label.alignment() == (
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        def center_y(widget) -> float:
            top_left = widget.mapTo(wizard, QPoint(0, 0))
            return top_left.y() + widget.height() / 2

        assert abs(center_y(page.name_label) - center_y(page.name_edit)) <= 2
        assert abs(center_y(page.output_label) - center_y(page.output_edit)) <= 2
        assert page.name_edit.mapTo(wizard, QPoint(0, 0)).x() == (
            page.output_edit.mapTo(wizard, QPoint(0, 0)).x()
        )
        assert page.name_edit.height() == page.output_edit.height()
        wizard.identity_page.name_edit.setText("Reference")
        wizard.identity_page.output_edit.setText(str(tmp_path / "generated"))
        assert wizard.identity_page.isComplete()
        assert wizard.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).isEnabled()
        values = wizard.WizardData_Get()
        assert values["name"] == "Reference"
        assert set(values) == {"name", "output_directory"}
        window.Theme_Apply("dark")
        wizard.Language_Apply(window._translator)
        qapp.processEvents()
        window.Language_Apply("en_US")
        wizard.Language_Apply(window._translator)
        assert page.name_label.text() == "Project Name"
        assert page.output_label.text() == "Output Directory"
        window.Theme_Apply("light")
        for language in ("zh_CN", "en_US"):
            window.Language_Apply(language)
            wizard.Language_Apply(window._translator)
            for theme in ("light", "dark"):
                window.Theme_Apply(theme)
                qapp.processEvents()
                screenshot = tmp_path / f"new-project-{language}-{theme}.png"
                assert wizard.grab().save(str(screenshot))
                assert screenshot.stat().st_size > 0
                assert wizard.height() <= 220
    finally:
        wizard.close()
        window.close()


def test_devices_page_is_physical_and_capabilities_are_on_flight_page(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        qapp.processEvents()
        assert set(window.devices_page.device_combos) == {
            "imu0",
            "gnss0",
            "barometer0",
            "telemetry0",
        }
        telemetry_label = window.devices_page.telemetry_form.labelForField(
            window.devices_page.device_combos["telemetry0"]
        )
        assert isinstance(telemetry_label, QLabel)
        assert telemetry_label.text() == "遥测"
        assert "silverstar.device.console.uart" not in (
            window.devices_page.device_checks
        )
        assert not hasattr(window.devices_page, "mcu_combo")
        assert set(window.board_hardware_page.platform_values) == {
            "source",
            "part",
            "family",
            "package",
            "core",
            "cubemx",
            "firmware_package",
            "source_policy",
            "timebase",
            "storage",
            "i2c",
            "pwm",
            "can",
            "plugin",
            "reason",
            "verification",
            "provenance",
        }
        assert not hasattr(window.devices_page, "capability_table")
        assert not hasattr(window.devices_page, "capability_source_combos")
        assert window._model.hardware.mode == "custom"
        assert window._model.hardware.provider == (
            "silverstar.hardware_provider.stm32_cubemx"
        )
        assert window.board_hardware_page.board_combo.currentIndex() == 0
        assert window.board_hardware_page.board_combo.currentData() == "__custom__"
        assert window.board_hardware_page.board_combo.findData("__unselected__") == -1
        board_labels = {
            window.board_hardware_page.board_combo.itemText(index)
            for index in range(window.board_hardware_page.board_combo.count())
        }
        assert "SS0.5（已验证）" in board_labels
        assert all("SilverStar 0.5" not in label for label in board_labels)
        assert not window.board_hardware_page.preparation_widget.isVisible()
        assert not window.board_hardware_page.prepare_button.isVisible()
        assert window.devices_page.other_group.isVisible()
        assert not window.devices_page.other_empty_label.isVisible()
        assert window.devices_page.device_checks[
            "silverstar.device.sensor.input_voltage"
        ].isChecked()
        assert window.devices_page.actuator_group.isVisible()
        for actuator_id in (
            "silverstar.device.actuator.launch_ignition",
            "silverstar.device.actuator.parachute_pyro",
        ):
            actuator = window.devices_page.device_checks[actuator_id]
            assert isinstance(actuator, StandardCheckBox)
            assert not isinstance(actuator, LockedCheckBox)
        assert not hasattr(window.devices_page, "requirement_table")
        assert set(window.devices_page.add_buttons) == {
            "imu",
            "gnss",
            "telemetry",
        }
        assert all(
            button.isEnabled()
            for button in window.devices_page.add_buttons.values()
        )
        assert "maintenance0" in {
            instance.instance_id for instance in window._model.device_instances
        }
        assert any(
            resource.key.startswith("maintenance0:")
            for resource in window.board_hardware_page._resources
        )
        assert set(window.flight_configuration_page.protocol_combos) == {
            "telemetry",
            "maintenance",
            "logging",
        }
        assert window.flight_configuration_page.protocol_combos[
            "maintenance"
        ].currentText() == "串口维护协议 0.0"
        assert all(
            combo.count() == 2
            for combo in window.flight_configuration_page.protocol_combos.values()
        )
        source = (Path(__file__).resolve().parents[1] /
                  "src/silverstar_fccg/ui/pages/components.py").read_text(encoding="utf-8")
        assert "JY901B" not in source
        assert "BMI088" not in source
        jy901b_summary = window.devices_page.findChild(
            QLabel, "deviceCapabilitySummary_imu0"
        )
        assert jy901b_summary is not None
        assert "加速度" in jy901b_summary.text()
        assert "不具备用途资格" in jy901b_summary.text()
        assert "磁场" not in jy901b_summary.text()

        capability_table = window.flight_configuration_page.capability_table
        assert capability_table.rowCount() > 0
        assert all(
            capability_table.cellWidget(row, 3) is None
            for row in range(capability_table.rowCount())
        )
        statuses = {
            capability_table.item(row, 0).toolTip(): capability_table.item(row, 2).text()
            for row in range(capability_table.rowCount())
        }
        kinds = {
            capability_table.item(row, 0).toolTip(): capability_table.item(row, 1).text()
            for row in range(capability_table.rowCount())
        }
        assert statuses["imu.acceleration"] == "使用"
        assert not any(key.startswith("magnetometer.") for key in statuses)
        assert statuses["attitude.external"] == "未使用"
        assert kinds["imu.acceleration"] == "原始数据"
        assert kinds["imu.software_alignment_qualified"] == "合格能力"

        alignment_combo = window.flight_configuration_page.strategy_combos[
            "alignment"
        ]
        for required_slot in ("alignment", "ins", "landing"):
            required_combo = window.flight_configuration_page.strategy_combos[
                required_slot
            ]
            assert required_combo.findData(None) == -1
            assert all(
                "请选择策略" not in required_combo.itemText(index)
                for index in range(required_combo.count())
            )
        assert (
            window.flight_configuration_page.strategy_combos["estimator"].findData(
                None
            )
            >= 0
        )
        assert {
            alignment_combo.itemData(index)
            for index in range(alignment_combo.count())
        } == {
            "silverstar.algorithm.alignment.vector_constraints",
            "silverstar.algorithm.alignment.external_attitude_source",
        }
        assert qapp.palette().color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
        ) == QColor("#64748B")
        assert qapp.palette().color(
            QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base
        ) == QColor("#E2E8F0")
        assert "background: #E2E8F0;" in qapp.styleSheet()
        landing_combo = window.flight_configuration_page.strategy_combos["landing"]
        impact_item = landing_combo.model().item(
            landing_combo.findData(
                "silverstar.flight_logic.landing.impact_then_stillness"
            )
        )
        assert impact_item is not None and not impact_item.isEnabled()
        assert "不具备着陆冲击检测资格" in impact_item.toolTip()
        assert landing_combo.model().item(
            landing_combo.findData("silverstar.flight_logic.landing.stillness")
        ).isEnabled()

        logging_table = window.flight_configuration_page.logging_table
        assert logging_table.horizontalHeaderItem(1).text() == "日志记录 / 日志流"
        assert logging_table.item(0, 1).text() == "飞行事件"
        assert abs(logging_table.columnWidth(1) - logging_table.columnWidth(6)) <= 2
        assert any(
            isinstance(
                logging_table.cellWidget(row, 0).findChild(LockedCheckBox),
                LockedCheckBox,
            )
            for row in range(logging_table.rowCount())
        )

        delay_spin = window.flight_configuration_page.mode_parameter_spins[
            ("deployment", "Delay", "delay")
        ]
        assert delay_spin.buttonSymbols() == (
            QAbstractSpinBox.ButtonSymbols.PlusMinus
        )
        assert "spin_plus_light.svg" in qapp.styleSheet()
        assert "spin_minus_light.svg" in qapp.styleSheet()

        tables = window.findChildren(QTableWidget)
        assert tables
        assert all(
            table.horizontalScrollMode()
            == QAbstractItemView.ScrollMode.ScrollPerPixel
            and table.verticalScrollMode()
            == QAbstractItemView.ScrollMode.ScrollPerPixel
            for table in tables
        )

        hardware_page = window.board_hardware_page
        assert hardware_page.advanced_section.body.isAncestorOf(
            hardware_page.auto_button
        )
        assert hardware_page.advanced_section.body.isAncestorOf(
            hardware_page.manual_validation_button
        )
        assert hardware_page.auto_button.objectName() == "primaryButton"
        assert hardware_page.manual_validation_button.objectName() == (
            "primaryButton"
        )
        assert hardware_page.auto_button.isEnabled()
        assert hardware_page.manual_validation_button.isEnabled()

        existing_board_index = next(
            index
            for index in range(hardware_page.board_combo.count())
            if hardware_page.board_combo.itemData(index) != "__custom__"
            and hardware_page.board_combo.model().item(index).isEnabled()
        )
        hardware_page.board_combo.setCurrentIndex(existing_board_index)
        qapp.processEvents()
        assert window._model.hardware.mode == "board_plugin"
        assert not hardware_page.auto_button.isEnabled()
        assert not hardware_page.manual_validation_button.isEnabled()
    finally:
        window.close()


def test_device_interface_profile_selector_updates_one_chip_instance(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        window._DeviceInstance_Change("imu0", "silverstar.device.imu.bmi088")
        qapp.processEvents()
        combo = window.devices_page.variant_combos["imu0"]
        assert combo.count() == 4
        selected = combo.findData(("spi", "bosch_sync_400_hz"))
        assert selected >= 0
        combo.setCurrentIndex(selected)
        qapp.processEvents()
        instance = window._model.DeviceInstance_Get("imu0")
        assert instance is not None
        assert instance.plugin == "silverstar.device.imu.bmi088"
        assert (instance.interface, instance.profile) == (
            "spi", "bosch_sync_400_hz"
        )
    finally:
        window.close()


def test_official_repeated_device_rows_add_to_limit_and_remove_atomically(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    try:
        for component_class, prefix in (
            ("imu", "imu"),
            ("gnss", "gnss"),
            ("telemetry", "telemetry"),
        ):
            window.devices_page.add_buttons[component_class].click()
            qapp.processEvents()
            instances = [
                item
                for item in window._model.device_instances
                if item.instance_id.startswith(prefix)
            ]
            assert [item.instance_id for item in instances] == [
                f"{prefix}0",
                f"{prefix}1",
            ]
            assert instances[0].plugin == instances[1].plugin

        for expected_index in (2, 3):
            window.devices_page.add_buttons["imu"].click()
            qapp.processEvents()
            assert f"imu{expected_index}" in window.devices_page.device_combos
        assert "imu" not in window.devices_page.add_buttons

        window.devices_page.remove_buttons["imu0"].click()
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("imu0") is None
        assert window._model.DeviceInstance_Get("imu1") is not None
        assert all(
            not key.startswith("imu0:")
            for key in window._model.resource_assignments
        )
        assert "imu0" not in window._model.capability_source_overrides.values()
        assert "imu" in window.devices_page.add_buttons

        window.devices_page.remove_buttons["telemetry0"].click()
        qapp.processEvents()
        telemetry_binding = next(
            binding
            for binding in ProtocolResolution_Resolve(
                window._model, window._service.catalog
            ).bindings
            if binding.category == "telemetry"
        )
        assert telemetry_binding.candidate_instances == ("telemetry1",)
        assert all(
            not key.startswith("telemetry0:")
            for key in window._model.resource_assignments
        )
    finally:
        window.close()


def test_pending_custom_hardware_keeps_sd_tf_storage_selectable(
    tmp_path: Path, qapp
) -> None:
    window = _Window_Create(tmp_path, qapp)
    storage_id = "silverstar.device.storage.sd_sdio_fatfs"
    try:
        selected = window.devices_page.device_checks[storage_id]
        assert selected.isChecked()
        assert selected.isEnabled()

        window._model.device_instances = [
            instance
            for instance in window._model.device_instances
            if instance.plugin != storage_id
        ]
        window._model = window._service.ProjectConfiguration_Reconcile(
            window._model
        ).model
        window._Project_Refresh()
        qapp.processEvents()

        selectable = window.devices_page.device_checks[storage_id]
        assert isinstance(selectable, StandardCheckBox)
        assert not isinstance(selectable, LockedCheckBox)
        assert selectable.isEnabled()
        assert not selectable.isChecked()

        selectable.click()
        qapp.processEvents()
        assert window._model.DeviceInstance_Get("storage0") is not None
    finally:
        window.close()


def test_background_worker_updates_shared_progress(tmp_path: Path, qapp) -> None:
    window = _Window_Create(tmp_path, qapp)
    results: list[int] = []

    def task(context) -> int:
        context.Progress_Report(0.25, "status.ready")
        context.Progress_Report(1.0, "status.ready")
        return 42

    try:
        assert window.Task_Run(task, results.append)
        deadline = time.monotonic() + 3.0
        while window._active_worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
            QTest.qWait(5)
        assert window._active_worker is None
        assert results == [42]
        QTest.qWait(400)
        qapp.processEvents()
        assert window._retired_workers == []
        assert not window.progress_bar.isVisible()
    finally:
        window.close()


def test_target_build_controls_and_quality_actions_use_shared_worker(
    tmp_path: Path, workspace_root: Path, qapp, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    project_root = tmp_path / "ProgressActions"
    model = service.ReferenceProject_Create("ProgressActions")
    TargetGeneration_Apply(
        model, service.catalog, service.policy, project_root, TargetScope.FLIGHT
    )
    window = MainWindow(
        SettingsStore(tmp_path / "progress-actions.ini"),
        service=service,
    )
    invocations: list[tuple[str, bool]] = []

    def task_run(
        function,
        _result_callback,
        _error_callback=None,
        *,
        indeterminate=False,
        line_callback=None,
    ):
        invocations.append((function.__name__, indeterminate))
        return True

    try:
        window._Project_Open(project_root)
        monkeypatch.setattr(window, "Task_Run", task_run)
        plan_calls: list[tuple[object, Path]] = []
        original_plan_create = service.GenerationPlan_Create

        def plan_create(model, root):
            plan_calls.append((model, root))
            return original_plan_create(model, root)

        monkeypatch.setattr(service, "GenerationPlan_Create", plan_create)
        window._HardwarePrepare_Request()
        assert plan_calls == []
        assert window.build_page.action_buttons["flight_open_vscode"].isEnabled()
        assert not window.build_page.action_buttons["ground_open_folder"].isEnabled()
        assert window.build_page.root_layout.indexOf(window.build_page.tool_status_group) == 1
        descriptor_before_validation = window._model.Dictionary_Get()
        window._Build_Request("architecture_check")
        assert window._model.Dictionary_Get() == descriptor_before_validation
        assert window.build_page.action_buttons["flight_clean"].text() == "清理"
    finally:
        window.close()

    assert invocations == [("prepare_plan", False), ("build", False)]


def test_hardware_prepare_plans_off_ui_thread_and_completes_safely(
    tmp_path: Path, workspace_root: Path, qapp, monkeypatch
) -> None:
    service = FccgService(workspace_root)
    window = MainWindow(
        SettingsStore(tmp_path / "hardware-async.ini"),
        service=service,
    )
    project_root = tmp_path / "HardwareAsync"
    window._model = service.ReferenceProject_Create("HardwareAsync")
    window._project_root = project_root
    window._Project_Refresh()
    plan_entered = threading.Event()
    plan_release = threading.Event()
    plan_threads: list[int] = []
    prepare_threads: list[int] = []
    errors: list[object] = []

    def plan_create(model, root):
        plan_threads.append(threading.get_ident())
        plan_entered.set()
        assert plan_release.wait(5.0)
        return GenerationPlan(
            project_root=Path(root).resolve(strict=False),
            operations=(),
            validation=ProjectValidationResult(()),
            new_project=True,
        )

    def hardware_prepare(
        model,
        root,
        *,
        confirm_dangerous=False,
        progress_callback=None,
    ):
        prepare_threads.append(threading.get_ident())
        return ApplyResult(
            project_root=Path(root),
            files_added=1,
            files_modified=0,
            component_files_preserved=0,
        )

    monkeypatch.setattr(service, "GenerationPlan_Create", plan_create)
    monkeypatch.setattr(service, "Project_HardwarePrepare", hardware_prepare)
    monkeypatch.setattr(
        window, "_Error_Show", lambda error, *_args: errors.append(error)
    )
    main_thread = threading.get_ident()
    try:
        window._HardwarePrepare_Request()
        assert window._active_worker is not None
        assert plan_entered.wait(2.0)
        assert plan_threads[0] != main_thread
        assert not (project_root / "SilverStar.ssproject").exists()
        plan_release.set()

        deadline = time.monotonic() + 10.0
        while window._active_worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
            QTest.qWait(10)
        qapp.processEvents()
        QTest.qWait(10)

        assert errors == []
        assert window._active_worker is None
        assert prepare_threads and prepare_threads[0] != main_thread
        assert window._model.hardware.mode == "board_plugin"
        assert window._retired_workers == []
    finally:
        plan_release.set()
        window.close()
