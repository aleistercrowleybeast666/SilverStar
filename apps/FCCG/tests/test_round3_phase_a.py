from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy, QTest

from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow


def test_eight_pages_own_existing_editors_without_duplicate_radio(tmp_path: Path, qapp) -> None:
    window = MainWindow(SettingsStore(tmp_path / "round3.ini"))
    try:
        assert window.navigation_list.count() == window.pages.count() == 8
        assert tuple(window.navigation_list.item(i).text() for i in range(8)) == (
            "飞控设备", "飞行配置", "导航配置", "遥测配置",
            "地面站配置", "飞控硬件", "地面站硬件", "构建与检测",
        )
        for editor in (window.ground_target_page.pc_interface,
                       window.ground_target_page.pc_resource):
            assert window.ground_configuration_page.isAncestorOf(editor)
            assert not window.ground_target_page.isAncestorOf(editor)
        assert window.devices_page.telemetry_group.parent() is not window.devices_page
        assert window.air_link_page.isAncestorOf(window.devices_page.telemetry_group)
        assert window.air_link_page.isAncestorOf(
            window.flight_configuration_page.telemetry_protocol_group
        )
        assert window.air_link_page.isAncestorOf(
            window.ground_target_page.radio_selection_group
        )
        assert window.algorithm_parameters_page.isAncestorOf(
            window.flight_configuration_page.strategy_group
        )
        assert window.algorithm_parameters_page.isAncestorOf(
            window.flight_configuration_page.mode_group
        )
        assert window.build_page.root_layout.indexOf(
            window.build_page.tool_status_group
        ) == 1
        assert "generate_flight" not in window.build_page.action_buttons
        assert "ground_build" in window.build_page.action_buttons
        assert not window.build_page.action_buttons["ground_build"].isEnabled()
    finally:
        window.close()


def test_frequency_and_endpoint_power_commit_only_on_enter(tmp_path: Path, qapp) -> None:
    window = MainWindow(SettingsStore(tmp_path / "round3-numeric.ini"))
    window.show()
    qapp.processEvents()
    try:
        window.navigation_list.setCurrentRow(3)
        qapp.processEvents()
        frequency = window.air_link_page.fields["frequency_hz"]
        assert frequency.minimum() == 2473.0
        assert frequency.maximum() == 2473.0
        frequency.setFocus()
        frequency.lineEdit().setText("2400.000")
        qapp.processEvents()
        assert window._model.air_link.frequency_hz == 2473000000
        QTest.keyClick(frequency, Qt.Key.Key_Return)
        assert window._model.air_link.frequency_hz == 2473000000
        assert "AIR_LINK_FREQUENCY_OUT_OF_RANGE" in window.air_link_page.status.text()

        power = window.air_link_page.flight_tx_power
        assert (power.minimum(), power.maximum()) == (12, 12)
        commits = QSignalSpy(power.committed)
        power.setFocus()
        power.lineEdit().setText("11 dBm")
        assert window._model.flight_tx_power_dbm == 12
        assert not power.lineEdit().hasAcceptableInput(), power.lineEdit().text()
        QTest.keyClick(power, Qt.Key.Key_Return)
        assert commits.count() == 0, (power.value(), power.lineEdit().text())
        assert window._model.flight_tx_power_dbm == 12
        assert "AIR_LINK_TX_POWER_UNSUPPORTED" in window.air_link_page.status.text()
    finally:
        window.close()
