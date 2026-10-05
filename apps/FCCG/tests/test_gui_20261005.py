from dataclasses import replace
from PySide6.QtWidgets import QWidget

from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.view_models import CapabilityUsageView
from silverstar_fccg.ui.pages.components import FlightConfigurationPage
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.project.ground_activity import GroundActivityLedIssues_Get
from silverstar_fccg.project.configuration import ProjectConfiguration_Reconcile
from silverstar_fccg.project.model import HardwareResource, ProjectModel_Parse
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import BoardResourceProvisions_Get


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
    assert flight.width() == ground.width() == 120
    assert flight.mapTo(window, flight.rect().topRight()).x() == (
        ground.mapTo(window, ground.rect().topRight()).x())
    assert window.devices_page.telemetry_form.rowCount() >= 5
    assert ground_editor.rows_layout.itemAt(0).widget().layout().rowCount() >= 5
    assert not [widget for widget in window.devices_page.telemetry_group.findChildren(QWidget)
                if widget.objectName() == "deviceCapabilitySummary_telemetry0"
                and widget.isVisible()]
    assert len([widget for widget in window.findChildren(QWidget)
                if widget.objectName() == "protocolProfile_telemetry" and widget.isVisible()]) == 1
    window._GroundTarget_Change("pc_interface", "uart")
    qapp.processEvents()
    visible_rows = [row for row in ground_editor.findChildren(QWidget)
                    if row.objectName() == "groundRadioRow_radio0" and row.isVisible()]
    assert len(visible_rows) == 1
    assert len([widget for widget in window.findChildren(QWidget)
                if widget.objectName() == "protocolProfile_telemetry" and widget.isVisible()]) == 1
    window.close()


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
