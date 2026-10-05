from dataclasses import replace
from PySide6.QtWidgets import QFormLayout, QLabel, QWidget

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.view_models import CapabilityUsageView
from silverstar_fccg.ui.pages.components import FlightConfigurationPage
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.project.ground_activity import GroundActivityLedIssues_Get
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.model import (GroundRadioConfiguration,
    HardwareResource, ProjectModel_Parse)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import BoardResourceProvisions_Get
from silverstar_fccg.ui.pages.build import BuildPage
from silverstar_fccg.generator.multi_target import TargetGeneration_Apply, TargetScope
from silverstar_fccg.ui.pages.targets import GroundIssues_PresentationGet
from silverstar_fccg.project.air_link import AirLinkIssue


def test_capability_source_editor_is_removed_on_reorder_and_language(qapp):
    page = FlightConfigurationPage(Translator("en_US"))
    emitted = []
    page.capabilitySourceChanged.connect(lambda *args: emitted.append(args))
    baro = CapabilityUsageView("barometer.altitude", consumers=("navigation",),
        providers=(("imu0", "JY901B"), ("baro0", "BMP280")), source_instance_id="baro0")
    gnss = CapabilityUsageView("gnss.velocity", consumers=("navigation",),
        providers=(("gnss0", "NEO-M9N"),), source_name="NEO-M9N")
    page.Capabilities_Set((baro, gnss))
    old_editor = page.capability_table.cellWidget(0, 3)
    assert old_editor is not None and old_editor.count() == 2
    page.Capabilities_Set((gnss, baro))
    assert page.capability_table.cellWidget(0, 3) is None
    assert old_editor.isHidden()
    assert page.capability_table.item(0, 3).text() == "NEO-M9N"
    removed_row_editor = page.capability_table.cellWidget(1, 3)
    assert removed_row_editor.count() == 2
    old_editor.setCurrentIndex(0)
    assert emitted == []
    page.Language_Apply(Translator("zh_CN"))
    assert page.capability_table.cellWidget(0, 3) is None
    assert page.capability_table.item(0, 3).text() == "NEO-M9N"
    page.Capabilities_Set((gnss,))
    assert page.capability_table.rowCount() == 1
    assert page.capability_table.cellWidget(0, 3) is None
    assert removed_row_editor.isHidden()
    removed_row_editor.setCurrentIndex(0)
    assert emitted == []


def test_ground_uart_baud_tracks_bound_resource_and_legacy_project(builtin_catalog):
    model = ReferenceProject_Create("BaudSync", catalog=builtin_catalog)
    model.ground_target = replace(model.ground_target, enabled=True,
        board="silverstar.board.ground_station_0_5", pc_interface="uart",
        baudrate=9600, hardware=replace(model.ground_target.hardware, mode="board_plugin"))
    reopened = ProjectModel_Parse(model.Dictionary_Get())
    resolved = ProjectConfiguration_Reconcile(reopened, builtin_catalog).model
    uart = next(resource for resource in resolved.ground_target.hardware.resources
                if resource.resource_id == resolved.ground_target.pc_resource)
    assert resolved.ground_target.baudrate == uart.metadata["baud_rate"]
    replacement = HardwareResource("OTHER_UART", "uart",
        {**uart.metadata, "baud_rate": 115200})
    ground = resolved.ground_target
    resolved.ground_target = replace(ground, board="", pc_resource="OTHER_UART",
        hardware=replace(ground.hardware, mode="custom",
            resources=(*ground.hardware.resources, replacement)), baudrate=230400)
    switched = ProjectConfiguration_Reconcile(resolved, builtin_catalog).model
    assert switched.ground_target.baudrate == 115200


def test_ground_pc_page_omits_baud_row_while_model_keeps_it(qapp, tmp_path,
                                                              workspace_root):
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"),
                        service=FccgService(workspace_root))
    window._GroundBoard_Change("silverstar.board.ground_station_0_5")
    window._GroundTarget_Change("enabled", True)
    window._GroundTarget_Change("pc_interface", "uart")
    page = window.ground_target_page
    for language in ("zh_CN", "en_US"):
        window.Language_Apply(language)
        qapp.processEvents()
        labels = {label.text() for label in page.pc_group.findChildren(QLabel)}
        assert "波特率" not in labels and "Baud rate" not in labels
        assert page.pc_form.rowCount() == 4
    ground = window._model.ground_target
    selected = next(item for item in ground.hardware.resources
                    if item.resource_id == ground.pc_resource)
    assert ground.baudrate == selected.metadata["baud_rate"]
    assert ProjectModel_Parse(window._model.Dictionary_Get()).ground_target.baudrate == ground.baudrate
    window.close()


def test_old_disabled_ground_opens_as_configurable_target(qapp, tmp_path,
                                                           workspace_root):
    service = FccgService(workspace_root)
    old = service.ProjectDraft_Create("OldGround")
    old.ground_target = replace(old.ground_target, enabled=False)
    root = tmp_path / "old_ground"
    service.ProjectRoot_Save(old, root, create_new=True)
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"), service=service)
    window._Project_Open(root)
    assert window._model.ground_target.enabled
    assert not service.Project_Open(root).ground_target.enabled
    window._GroundBoard_Change("silverstar.board.ground_station_0_5")
    assert window.ground_target_page.generate_button.isEnabled()
    result = TargetGeneration_Apply(window._model, service.catalog, service.policy,
                                    root, TargetScope.GROUND)
    assert result.targets == ("Ground_Station",)
    assert (root / "Ground_Station/Makefile").is_file()
    assert service.Project_Open(root).ground_target.enabled
    window.close()


def test_ground_errors_are_localized_and_block_only_ground_generation(
    qapp, tmp_path, workspace_root,
):
    issues = (
        AirLinkIssue("GROUND_HARDWARE_UNBOUND", "Ground hardware is not selected"),
        AirLinkIssue("GROUND_UART_UNBOUND", "Ground UART resource is unavailable"),
        AirLinkIssue("GROUND_RADIO_RESOURCE_UNBOUND", "Ground radio0 spi needs a spi resource"),
        AirLinkIssue("GROUND_RADIO_RESOURCE_UNBOUND", "Ground radio0 reset needs a gpio resource"),
        AirLinkIssue("GROUND_LED_OUTPUT_UNBOUND", "TX LED needs a writable GPIO output"),
    )
    summary, details = GroundIssues_PresentationGet(issues, Translator("zh_CN"))
    assert "地面站" in summary and "5" in summary
    assert "UART" in details and "SPI" in details and "GPIO" in details
    assert "GROUND_" not in summary + details and "Ground radio0" not in details
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"),
                        service=FccgService(workspace_root))
    window._project_root = tmp_path / "not_generated"
    shown = []
    window._Error_Show = lambda message, detail="": shown.append((message, detail))
    window._Targets_Generate("generate_ground")
    assert len(shown) == 1 and "地面站" in shown[0][0]
    assert "GROUND_" not in shown[0][0] + shown[0][1]
    assert not window._project_root.exists()
    window.close()


def test_reference_ground_led_contract_uses_pc13_off_level(builtin_catalog):
    board = builtin_catalog.Component_Get("silverstar.board.ground_station_0_5")
    led = next(item for item in BoardResourceProvisions_Get(board)
               if item.resource_id == "PLATFORM_GPIO_6")
    assert led.metadata["physical_pin"].startswith("PC13")
    assert led.metadata["initial_level"] == "high"
    assert led.metadata["activity_led_shared"] is True
    assert led.metadata["activity_led_active_high"] is False


def test_telemetry_cards_share_details_and_remove_geometry(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"),
                        service=FccgService(workspace_root))
    window.resize(1280, 800)
    window.show()
    window._GroundBoard_Change("silverstar.board.ground_station_0_5")
    window._GroundTarget_Change("enabled", True)
    window._GroundTarget_Change("radio_plugin", "silverstar.device.telemetry.sx1281")
    window._GroundTarget_Change("module_variant", "e28_2g4m12sx")
    window.pages.setCurrentWidget(window.air_link_page)
    qapp.processEvents()
    flight = window.devices_page.remove_buttons["telemetry0"]
    ground_editor = window.ground_target_page.radio_instances_editor
    ground = ground_editor.rows["radio0"]["remove"]
    for width in (1024, 1280):
        window.resize(width, 800)
        qapp.processEvents()
        for remove, add in ((flight, window.devices_page.add_buttons["telemetry"]),
                            (ground, ground_editor.add_button)):
            assert remove.width() == add.width()
            assert remove.mapTo(window, remove.rect().topLeft()).x() == (
                add.mapTo(window, add.rect().topLeft()).x())
            assert remove.mapTo(window, remove.rect().topRight()).x() == (
                add.mapTo(window, add.rect().topRight()).x())
    assert window.devices_page.telemetry_form.rowCount() >= 4
    ground_form = ground_editor.rows_layout.itemAt(0).widget().layout()
    assert ground_form.rowCount() == 3
    for form in (window.devices_page.telemetry_form, ground_form):
        labels = []
        for row in range(form.rowCount()):
            label = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
            if label is not None and field is not None and label.widget() is not None:
                labels.append((label.widget().text(), field.widget().text()
                               if hasattr(field.widget(), "text") else ""))
        assert ("射频芯片", "SX1281") in labels
        assert not {"厂商", "型号"}.intersection(name for name, _value in labels)
    assert not [widget for widget in window.devices_page.telemetry_group.findChildren(QWidget)
                if widget.objectName() == "deviceCapabilitySummary_telemetry0"
                and widget.isVisible()]
    assert len([widget for widget in window.findChildren(QWidget)
                if widget.objectName() == "protocolProfile_telemetry" and widget.isVisible()]) == 1
    window._DeviceInstance_Add("telemetry")
    primary = window._model.ground_target
    radios = (GroundRadioConfiguration("radio0", primary.radio_plugin,
              primary.module_variant, primary.tx_power_dbm),
              GroundRadioConfiguration("radio1", primary.radio_plugin,
              primary.module_variant, primary.tx_power_dbm))
    window._GroundRadios_Change(radios, "radio0")
    qapp.processEvents()
    assert "telemetry1" in window.devices_page.remove_buttons
    assert "radio1" in ground_editor.rows
    for width in (1024, 1280):
        window.resize(width, 800)
        qapp.processEvents()
        for remove in (window.devices_page.remove_buttons["telemetry0"],
                       window.devices_page.remove_buttons["telemetry1"]):
            assert remove.width() == window.devices_page.add_buttons["telemetry"].width()
        for remove in (ground_editor.rows["radio0"]["remove"],
                       ground_editor.rows["radio1"]["remove"]):
            add = ground_editor.add_button
            assert remove.width() == add.width()
            assert remove.mapTo(window, remove.rect().topLeft()).x() == (
                add.mapTo(window, add.rect().topLeft()).x())
    window._GroundTarget_Change("pc_interface", "uart")
    qapp.processEvents()
    visible_rows = [row for row in ground_editor.findChildren(QWidget)
                    if row.objectName() == "groundRadioRow_radio0" and row.isVisible()]
    assert len(visible_rows) == 1
    assert len([widget for widget in window.findChildren(QWidget)
                if widget.objectName() == "protocolProfile_telemetry" and widget.isVisible()]) == 1
    window.close()


def test_memory_layout_legacy_is_read_only_only_for_older_projects(qapp, builtin_catalog):
    page = BuildPage(Translator("zh_CN"))
    combo = page.memory_layout_combo
    assert [combo.itemData(index) for index in range(combo.count())] == [
        "auto", "eskf_window_sram"]
    model = ReferenceProject_Create("OldLayout", catalog=builtin_catalog)
    model.build = replace(model.build, memory_layout="legacy")
    reopened = ProjectModel_Parse(model.Dictionary_Get())
    assert reopened.build.memory_layout == "legacy"
    page.MemoryLayout_Set(reopened.build.memory_layout)
    assert combo.currentData() == "legacy"
    assert combo.currentText() == "旧工程布局（只读）"
    assert not combo.model().item(combo.findData("legacy")).isEnabled()
    page.Language_Apply(Translator("en_US"))
    assert combo.currentText() == "Legacy project layout (read-only)"
    page.MemoryLayout_Set("auto")
    assert combo.findData("legacy") == -1 and combo.currentData() == "auto"


def test_ground_led_intent_without_board_reports_missing_resource(builtin_catalog):
    model = ReferenceProject_Create("LedIntent", catalog=builtin_catalog)
    ground = replace(model.ground_target, enabled=True, activity_led_enabled=True)
    assert "GROUND_LED_OUTPUT_UNBOUND" in {
        issue.code for issue in GroundActivityLedIssues_Get(ground)}


def test_ground_led_checkbox_stores_intent_without_board(qapp, tmp_path, workspace_root):
    window = MainWindow(SettingsStore(tmp_path / "settings.ini"),
                        service=FccgService(workspace_root))
    ground = window._model.ground_target
    window._model.ground_target = replace(ground, enabled=True, board="")
    window._Project_Refresh()
    checkbox = window.ground_target_page.activity_led_enabled
    assert checkbox.isEnabled() and not checkbox.isChecked()
    checkbox.click()
    assert window._model.ground_target.activity_led_enabled is True
    assert not window._model.ground_target.tx_led_resource
    assert "GROUND_LED_OUTPUT_UNBOUND" in {
        issue.code for issue in GroundActivityLedIssues_Get(window._model.ground_target)}
    window.close()
