"""GUI regressions from the 93fd895 native popup and radio QA report."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.air_link import AirLinkIssues_Get
from silverstar_fccg.project.model import (
    GroundTargetConfiguration, HardwareConfiguration, HardwareResource,
)
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.resources import (
    BoardHardwareInventory_Get, BoardResourceProvisions_Get,
)
from silverstar_fccg.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]
RADIO = "silverstar.device.telemetry.sx1281"


def _Window_Create(tmp_path: Path) -> MainWindow:
    return MainWindow(SettingsStore(tmp_path / "settings.ini"),
                      service=FccgService(ROOT))


def _GroundF103Model_Get(catalog):
    model = ReferenceProject_Create("GuiGroundQA", catalog=catalog)
    board = catalog.Component_Get("silverstar.board.ground_station_0_5")
    inventory = BoardHardwareInventory_Get(board)
    resources = tuple(HardwareResource(item.resource_id, item.kind, item.metadata)
                      for item in BoardResourceProvisions_Get(board))
    model.ground_target = GroundTargetConfiguration(
        enabled=True, mcu="silverstar.mcu.stm32f103c8t6", board=board.component_id,
        hardware=HardwareConfiguration(
            mode="board_plugin", source_kind=board.board.source_kind,
            mcu=inventory.mcu_part, inventory=inventory.Dictionary_Get(),
            resources=resources,
        ),
        radio_plugin=RADIO, module_variant="e28_2g4m12sx",
        resource_assignments={
            "radio0:radio_bus": "PLATFORM_SPI_1",
            "radio0:radio_nss": "PLATFORM_GPIO_0",
            "radio0:radio_reset": "PLATFORM_GPIO_1",
            "radio0:radio_busy": "PLATFORM_GPIO_2",
            "radio0:radio_dio1": "PLATFORM_GPIO_3",
            "radio0:time": "PLATFORM_TIME_1",
        },
        pc_interface="uart", pc_resource="PLATFORM_UART_1",
    )
    return model


@pytest.mark.parametrize(
    "qt_platform", ["offscreen", "windows"] if sys.platform == "win32" else ["offscreen"],
)
def test_alignment_native_popup_round_trips_in_separate_qt_process(
    tmp_path: Path, qt_platform: str,
) -> None:
    # A Qt SIGSEGV must fail only this child, never the parent pytest process.
    script = """
import faulthandler
import sys
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
faulthandler.enable()
app = QApplication([])
root, settings = Path(sys.argv[1]), Path(sys.argv[2])
window = MainWindow(SettingsStore(settings), service=FccgService(root))
window.show()
app.processEvents()
window.navigation_list.setCurrentRow(2)
app.processEvents()
for cycle in range(5):
    for key, suffix in ((Qt.Key_Home, "external_attitude_source"),
                        (Qt.Key_End, "vector_constraints")):
        combo = window.flight_configuration_page.strategy_combos["alignment"]
        combo.setFocus()
        combo.showPopup()
        QTest.keyClick(combo.view(), key)
        QTest.keyClick(combo.view(), Qt.Key_Return)
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
        assert str(combo.currentData()).endswith(suffix), (cycle, suffix, combo.currentData())
        assert window.algorithm_parameters_page.alignment_editor.DraftStrategy_Get().endswith(suffix)
        print(f"POPUP_OK {cycle} {suffix}", flush=True)
window.algorithm_parameters_page.alignment_editor.cancel_button.click()
assert not window.algorithm_parameters_page.alignment_editor.draft_dirty
window.close()
app.processEvents()
"""
    environment = dict(os.environ, QT_QPA_PLATFORM=qt_platform,
                       PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", script,
         str(ROOT), str(tmp_path / "popup.ini")],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("POPUP_OK") == 10


def test_radio_invalid_selection_remains_visible_and_backend_rejects(qapp, tmp_path: Path) -> None:
    window = _Window_Create(tmp_path)
    try:
        model = ReferenceProject_Create("RadioQA", catalog=window._service.catalog)
        model.ground_target = replace(model.ground_target, enabled=True,
                                      radio_plugin=RADIO,
                                      module_variant="e28_2g4m12sx")
        model.air_link = replace(model.air_link, spreading_factor=7)
        window._model = model
        window._Project_Refresh()
        combo = window.ground_target_page.radio
        index = combo.findData(RADIO)
        assert index >= 0 and combo.currentIndex() == index
        assert not combo.model().item(index).isEnabled()
        assert "AIR_LINK_PHY_INCOMPATIBLE" in combo.model().item(index).toolTip()
        flight = window.devices_page.device_combos[model.air_link.flight_radio_instance]
        assert flight.currentData() == RADIO
        assert not flight.model().item(flight.currentIndex()).isEnabled()
        assert "AIR" in flight.model().item(flight.currentIndex()).toolTip()
        assert any(issue.code == "AIR_LINK_PHY_INCOMPATIBLE"
                   for issue in AirLinkIssues_Get(model, window._service.catalog))
        model.air_link = replace(model.air_link, spreading_factor=10)
        window._Project_Refresh()
        assert combo.currentData() == RADIO
        assert combo.model().item(combo.currentIndex()).isEnabled()
        flight = window.devices_page.device_combos[model.air_link.flight_radio_instance]
        assert flight.currentData() == RADIO
        assert flight.model().item(flight.currentIndex()).isEnabled()
        model.air_link = replace(model.air_link, radio_technology="packet")
        window._Project_Refresh()
        technology = window.air_link_page.fields["radio_technology"]
        assert technology.currentData() == "packet"
        assert not technology.model().item(technology.currentIndex()).isEnabled()
        assert combo.currentData() == RADIO
    finally:
        window.close()
        qapp.processEvents()


def test_busy_generation_is_idempotent_and_estimator_order_is_stable(
    qapp, tmp_path: Path, monkeypatch,
) -> None:
    window = _Window_Create(tmp_path)
    errors: list[object] = []
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    try:
        estimator = window.flight_configuration_page.strategy_combos["estimator"]
        assert [estimator.itemData(index) for index in range(estimator.count())] == [
            None, "silverstar.algorithm.estimator.kf6",
            "silverstar.algorithm.estimator.eskf15",
            "silverstar.algorithm.estimator.sf6",
        ]
        assert [estimator.itemText(index) for index in range(estimator.count())] == [
            "纯惯导", "KF6算法", "ESKF15算法", "SF6算法",
        ]
        window._active_worker = object()
        for _ in range(5):
            window._Targets_Generate("generate_flight")
            window._Targets_Generate("generate_ground")
        assert not errors
    finally:
        window._active_worker = None
        window.close()
        qapp.processEvents()


def test_close_waits_for_worker_and_does_not_dispatch_cancelled_result(
    qapp, tmp_path: Path, monkeypatch,
) -> None:
    window = _Window_Create(tmp_path)
    callbacks: list[object] = []
    release = threading.Event()
    monkeypatch.setattr(window, "_MessageBox_Exec", lambda *_args, **_kwargs:
                        QMessageBox.StandardButton.Yes)
    try:
        window.show()

        def slow_task(_context):
            release.wait(2)
            return "late result"

        assert window.Task_Run(slow_task, callbacks.append)
        window.close()
        assert window.isVisible()
        assert window._close_after_worker
        release.set()
        deadline = time.monotonic() + 5
        while window.isVisible() and time.monotonic() < deadline:
            qapp.processEvents()
            QTest.qWait(10)
        assert not window.isVisible()
        assert callbacks == []
        qapp.processEvents()
        assert window._active_worker is None
    finally:
        release.set()
        if window.isVisible():
            window.close()
        qapp.processEvents()


def test_visible_generate_double_click_while_busy_is_ignored(
    qapp, tmp_path: Path, monkeypatch,
) -> None:
    window = _Window_Create(tmp_path)
    errors: list[object] = []
    release = threading.Event()
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    try:
        window.navigation_list.setCurrentRow(window.PAGE_CODES.index("page.board_hardware"))
        window.show()
        qapp.processEvents()

        def slow_task(_context):
            release.wait(2)
            return None

        assert window.Task_Run(slow_task, lambda _result: None)
        button = window.board_hardware_page.generate_button
        assert button.isVisible() and not button.isEnabled()
        QTest.mouseDClick(button, Qt.MouseButton.LeftButton)
        qapp.processEvents()
        assert window._active_worker is not None
        assert errors == []
    finally:
        release.set()
        deadline = time.monotonic() + 5
        while window._active_worker is not None and time.monotonic() < deadline:
            qapp.processEvents()
            QTest.qWait(10)
        window.close()
        qapp.processEvents()


def test_alignment_confirm_is_atomic_and_save_reopen_uses_committed_snapshot(
    qapp, tmp_path: Path, monkeypatch,
) -> None:
    window = _Window_Create(tmp_path)
    errors: list[object] = []
    monkeypatch.setattr(window, "_Error_Show", errors.append)
    try:
        window._model = ReferenceProject_Create("DraftQA", catalog=window._service.catalog)
        window._Project_Refresh()
        original = window._model.alignment
        editor = window.algorithm_parameters_page.alignment_editor
        weight = editor._rows[0]["weight"]
        weight.selectAll()
        QTest.keyClicks(weight, "3.25")
        assert editor.draft_dirty
        assert window._model.alignment == original
        window._Targets_Generate("generate_flight")
        assert errors and "初始对准" in str(errors[-1])
        assert window._active_worker is None
        editor.confirm_button.click()
        assert window._model.alignment.constraints[0].weight == 3.25
        assert not editor.draft_dirty
        assert not errors[1:]
        window._project_root = tmp_path / "project"
        window._Project_Save()
        saved = window._service.Project_Open(window._project_root)
        assert saved.alignment.constraints[0].weight == 3.25
        weight = editor._rows[0]["weight"]
        weight.selectAll()
        QTest.keyClicks(weight, "4.5")
        window._Project_Save()
        assert "上次已确认配置" in window.status_label.text()
        assert window._service.Project_Open(window._project_root).alignment.constraints[0].weight == 3.25
        editor.cancel_button.click()
        assert window._model.alignment.constraints[0].weight == 3.25
        window._Project_Open(window._project_root)
        assert window._model.alignment.constraints[0].weight == 3.25
        assert not editor.draft_dirty
    finally:
        window.close()
        qapp.processEvents()


def test_windows_first_show_has_final_page_and_style_state(qapp, tmp_path: Path) -> None:
    class ShowProbe(QObject):
        def __init__(self) -> None:
            super().__init__()
            self.snapshots: list[tuple[int, bool, str]] = []

        def eventFilter(self, watched, event) -> bool:
            if event.type() == QEvent.Type.Show:
                self.snapshots.append((watched.pages.count(),
                                       bool(QApplication.instance().styleSheet()),
                                       watched.current_project_value.text()))
            return False

    window = _Window_Create(tmp_path)
    probe = ShowProbe()
    try:
        window.installEventFilter(probe)
        assert not window.isVisible()
        window.show()
        qapp.processEvents()
        assert probe.snapshots == [(len(window.PAGE_CODES), True, "SilverStar")]
    finally:
        window.close()
        qapp.processEvents()


@pytest.mark.skipif(sys.platform != "win32", reason="requires a visible Windows Qt platform")
def test_native_windows_first_paint_and_non_alignment_popup(tmp_path: Path) -> None:
    script = """
import sys
from pathlib import Path
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.ui.main_window import MainWindow
class FirstPaint(QObject):
    def __init__(self):
        super().__init__()
        self.events = []
    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Paint):
            self.events.append((event.type(), watched.pages.count(),
                bool(QApplication.instance().styleSheet()),
                watched.geometry().width(), watched.geometry().height()))
        return False
app = QApplication([])
root, settings = Path(sys.argv[1]), Path(sys.argv[2])
window = MainWindow(SettingsStore(settings), service=FccgService(root))
probe = FirstPaint()
window.installEventFilter(probe)
assert not window.isVisible()
window.show()
QTest.qWait(120)
app.processEvents()
assert probe.events and probe.events[0][0] == QEvent.Type.Show, probe.events
assert any(item[0] == QEvent.Type.Paint for item in probe.events), probe.events
assert all(item[1] == len(MainWindow.PAGE_CODES) and item[2] and item[3] > 0 and item[4] > 0
           for item in probe.events), probe.events
print('FIRST_PAINT_OK', probe.events[0], flush=True)
combo = window.flight_configuration_page.strategy_combos['estimator']
combo.setFocus()
combo.showPopup()
QTest.keyClick(combo.view(), Qt.Key_End)
QTest.keyClick(combo.view(), Qt.Key_Return)
QTest.qWait(50)
app.processEvents()
assert window._active_worker is None
print('ESTIMATOR_POPUP_OK', flush=True)
window.close()
app.processEvents()
"""
    environment = dict(os.environ, QT_QPA_PLATFORM="windows",
                       PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", script,
         str(ROOT), str(tmp_path / "first-paint.ini")],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FIRST_PAINT_OK" in result.stdout
    assert "ESTIMATOR_POPUP_OK" in result.stdout


@pytest.mark.skipif(sys.platform != "win32", reason="requires a visible Windows Qt platform")
def test_root_launcher_windows_first_paint(tmp_path: Path) -> None:
    script = """
import runpy
import sys
from pathlib import Path
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication
from silverstar_fccg.ui.main_window import MainWindow
import silverstar_fccg.app.application as application_module
from silverstar_fccg.core.settings import SettingsStore
class FirstPaint(QObject):
    def __init__(self):
        super().__init__()
        self.events = []
    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Paint):
            self.events.append((event.type(), watched.pages.count(),
                bool(QApplication.instance().styleSheet()),
                watched.geometry().width(), watched.geometry().height()))
        return False
repo = Path(sys.argv[1])
isolated_root = Path(sys.argv[2])
application_module.SettingsStore = lambda _path: SettingsStore(isolated_root / 'settings.ini')
application_module._Logging_Configure = lambda _root: isolated_root / 'launcher.log'
probe = FirstPaint()
original_show = MainWindow.show
def observed_show(window):
    assert not window.isVisible()
    window.installEventFilter(probe)
    original_show(window)
    QTimer.singleShot(150, QApplication.instance().quit)
MainWindow.show = observed_show
sys.argv = [str(repo / 'FCCG.py'), '--lang', 'zh_CN', '--theme', 'light']
try:
    runpy.run_path(str(repo / 'FCCG.py'), run_name='__main__')
except SystemExit as result:
    assert result.code == 0, result.code
assert probe.events and probe.events[0][0] == QEvent.Type.Show, probe.events
assert any(item[0] == QEvent.Type.Paint for item in probe.events), probe.events
assert all(item[1] == len(MainWindow.PAGE_CODES) and item[2] and item[3] > 0 and item[4] > 0
           for item in probe.events), probe.events
print('ROOT_FIRST_PAINT_OK', probe.events[0], flush=True)
"""
    environment = dict(os.environ, QT_QPA_PLATFORM="windows",
                       PYTHONDONTWRITEBYTECODE="1",
                       PYTHONPATH=str(ROOT / "src"))
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", script,
          str(ROOT.parents[1]), str(tmp_path)],
        cwd=ROOT.parents[1], env=environment,
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ROOT_FIRST_PAINT_OK" in result.stdout


def test_gui_generates_f407_and_f103(
    qapp, tmp_path: Path, monkeypatch,
) -> None:
    window = _Window_Create(tmp_path)
    errors: list[object] = []
    monkeypatch.setattr(window, "_Error_Show", lambda *details: errors.append(details))
    monkeypatch.setattr(window, "_DangerousPlan_Confirm", lambda _plan: True)
    monkeypatch.setattr(window, "_MessageBox_Exec", lambda *_args, **_kwargs:
                        QMessageBox.StandardButton.Yes)
    root = tmp_path / "gui-project"

    def wait_for(path: Path) -> None:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            qapp.processEvents()
            if path.is_file() and window._active_worker is None:
                return
            if errors and window._active_worker is None:
                raise AssertionError(f"GUI generation failed: {errors}")
            # QTest.qWait can retain the GIL on Windows/PySide; explicitly
            # yield while the Python generation worker scans and hashes files.
            time.sleep(0.01)
        raise AssertionError(f"GUI generation did not finish: {path}; {errors}")

    try:
        window._model = _GroundF103Model_Get(window._service.catalog)
        window._project_root = root
        window._Project_Refresh()
        window.board_hardware_page.generate_button.click()
        flight_makefile = root / "Flight_Controller" / "Makefile"
        wait_for(flight_makefile)
        user_payload = root / "Flight_Controller" / "user-notes.txt"
        user_payload.write_bytes(b"user-owned notes\n")
        window.ground_target_page.generate_button.click()
        ground_makefile = root / "Ground_Station" / "Makefile"
        wait_for(ground_makefile)
        assert user_payload.read_bytes() == b"user-owned notes\n"
        assert not errors
        assert (root / "Flight_Controller/Flight_Controller.code-workspace").is_file()
        assert (root / "Ground_Station/Ground_Station.code-workspace").is_file()
        assert not errors
    finally:
        if window._active_worker is not None:
            window._active_worker.Worker_Cancel()
        window.close()
        qapp.processEvents()

