import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import zlib
from threading import Event
from unittest.mock import patch

import numpy as np
import pytest
from PySide6.QtCore import QSettings, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app import Controller
from services.i18n import I18n, Language
from services.magnetometer_calibration import MagCalibrationFitStatus
from test_file_service_client import MockTransport
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
from ui.main_window import MainWindow


def wait_for(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


class MagWire(MockTransport):
    """Accelerated sample source, genuine ASCII grammar, no hardware handles."""
    def __init__(self, *, mode="ok", hemisphere=False):
        super().__init__()
        self.receive_observer = None
        self.mode, self.hemisphere = mode, hemisphere
        self.stream = False
        self.generation = 0
        self.applied = self.saved = self.save_pending = self.save_failed = False
        self.save_reads = 0
        self.cursor = 0
        self.io_threads = []
        self.start_gate = None
        self.start_entered = Event()
        self.last_packet = None

    def prepare_job(self):
        assert not self.stream, "A live stream cannot pass a quiet startup resynchronization"

    def exchange(self, command, timeout, cancel):
        self.io_threads.append(QThread.currentThread())
        if command == "SYSTEM DIAG":
            self.commands.append(command)
            return "ERR SYSTEM DIAG code=UNSUPPORTED"
        if command == "SYSTEM INFO":
            self.commands.append(command)
            return "OK SYSTEM INFO version=0.1.3 build_tag=SIMULATED"
        if not command.startswith("MAG "):
            return super().exchange(command, timeout, cancel)
        self.commands.append(command)
        if command == "MAG LIST":
            return "OK MAG LIST count=1 DATA instance=3 descriptor_id=9 physical_device_id=42 shared=0 device=external model=LIS3MDL"
        parts = command.split()
        assert parts[:2] == ["MAG", "3"]
        if parts[2:] == ["STREAM", "START"]:
            self.start_entered.set()
            if self.start_gate is not None:
                self.start_gate.wait(.4)
            self.stream = True
            self.cursor = 0
            if self.mode == "start_timeout":
                raise TimeoutError("Simulated lost START acknowledgement")
            return "OK MAG 3 STREAM state=STARTED rate_hz=20"
        if parts[2:] == ["STREAM", "STOP"]:
            if self.mode == "stop_fail":
                return "ERR MAG 3 STREAM code=FAILED reason=SIMULATED"
            self.stream = False
            return "OK MAG 3 STREAM state=STOPPED"
        if parts[2:4] == ["CAL", "APPLY"]:
            self.last_packet = bytes.fromhex(parts[4])
            assert len(self.last_packet) == 84
            assert zlib.crc32(self.last_packet[:80]) == int.from_bytes(self.last_packet[80:], "little")
            assert self.last_packet[2:6] == bytes((42, 0, 3, 0))
            if self.mode != "apply_no_effect":
                self.generation += 1
                self.applied, self.saved, self.save_pending = True, False, False
            return "OK MAG 3 CAL action=APPLY accepted=1"
        if parts[2:] == ["CAL", "SAVE"]:
            self.save_pending = True
            self.save_reads = 0
            return "OK MAG 3 CAL action=SAVE accepted=1"
        if parts[2:] == ["CAL", "READ"]:
            if self.mode == "unsupported":
                return "ERR MAG 3 CAL code=BAD_COMMAND reason=UNSUPPORTED"
            if self.save_pending:
                self.save_reads += 1
                if self.save_reads >= 2 and self.mode != "timeout":
                    self.save_pending = False
                    self.save_failed = self.mode == "save_fail"
                    self.saved = not self.save_failed
            generation = self.generation + int(self.mode == "changed" and self.save_reads > 0)
            physical = 42 if self.applied else 0
            instance = 3 if self.applied else 0
            return (f"OK MAG 3 CAL state={'APPLIED' if self.applied else 'EMPTY'} generation={generation} "
                    f"physical_device_id={physical} instance={instance} saved={int(self.saved)} "
                    f"pending={int(self.save_pending)} failed={int(self.save_failed)} "
                    f"load_error={'STORAGE_ERROR' if self.save_failed else 'OK'}")
        raise AssertionError(command)

    def check_alive(self):
        self.io_threads.append(QThread.currentThread())
        if not self.stream or self.receive_observer is None:
            return
        for _ in range(32):
            if self.cursor >= 256:
                break
            i = self.cursor
            z = 1 - 2 * (i + .5) / 256
            if self.hemisphere:
                z = (z + 1) / 2
            radius = np.sqrt(1 - z * z)
            a = i * np.pi * (3 - np.sqrt(5))
            x, y, z = 50 * radius * np.cos(a) + 12, 50 * radius * np.sin(a) - 8, 50 * z + 3
            line = (f"EVENT MAG SAMPLE instance=3 physical_device_id=42 seq={i} sample_us={(i+1)*50000} "
                    f"x_uT={x:.6f} y_uT={y:.6f} z_uT={z:.6f}\r\n").encode()
            for start in range(0, len(line), 64):
                self.receive_observer(line[start:start+64])
            self.cursor += 1


@pytest.fixture
def gui(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat)
    window = MainWindow(I18n(settings))
    monkeypatch.setattr("app.USER_DATA_ROOT", tmp_path)
    monkeypatch.setattr("app.list_serial_port_names", lambda: [])
    monkeypatch.setattr(QMessageBox, "warning", lambda *_: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *_: QMessageBox.Ok)
    controller = Controller(window, probe_enumerator=lambda _: ProbeInventory(ProbeInventoryResult.Empty))
    wire = MagWire()
    controller.file_transfer.transport_factory = lambda *_: wire
    window.resize(1024, 768)
    window.show()
    QTest.qWait(20)
    yield application, window, controller, wire
    controller.file_transfer.mag_dialog.request_close()
    QTest.qWait(100)
    controller.shutdown()
    QTest.qWait(50)
    window.close()
    window.deleteLater()
    QTest.qWait(30)


def connected_dialog(gui):
    _, window, controller, _ = gui
    window.debug_port_combo.setCurrentText("FAKE_MAG")
    controller.file_transfer.connect_debug()
    wait_for(lambda: window._debug_connected and window._debug_service_supported)
    window.btn_mag_calibration.click()
    dialog = controller.file_transfer.mag_dialog
    wait_for(lambda: dialog.capable and not dialog.pending)
    return dialog


def fitted_dialog(gui):
    dialog = connected_dialog(gui)
    dialog.start.click()
    wait_for(lambda: dialog.collecting and len(dialog.collection.points) == 256)
    dialog.stop_fit.click()
    wait_for(lambda: dialog.fit_result is not None and dialog.fit_worker is None)
    return dialog


def applied_dialog(gui):
    dialog = fitted_dialog(gui)
    assert dialog.fit_result.status is MagCalibrationFitStatus.READY
    dialog.apply_ram.click()
    wait_for(lambda: dialog.applied_generation is not None and not dialog.pending)
    return dialog


def test_preflight_button_opens_small_dialog_without_air_or_new_page(gui):
    _, window, controller, wire = gui
    pages = window.pages.count()
    window.btn_mag_calibration.click()
    dialog = controller.file_transfer.mag_dialog
    assert dialog.isVisible() and window.pages.count() == pages
    assert not dialog.start.isEnabled() and wire.commands == []
    assert "安装方向尚未验证" in dialog.note.text()
    dialog.i18n.set_language(Language.EN_US)
    window.retranslate_ui()
    assert dialog.start.text() == "Start collection"
    assert "body-frame" in dialog.note.text()
    assert dialog.width() <= 700


def test_full_workflow_requires_explicit_apply_save_and_read_confirmation_and_preserves_console_tf(gui, monkeypatch):
    application, _, controller, wire = gui
    import ui.magnetometer_dialog as module
    original_fit = module.MagCalibration_Fit
    fit_threads = []
    def observed_fit(*args):
        fit_threads.append(QThread.currentThread())
        return original_fit(*args)
    monkeypatch.setattr(module, "MagCalibration_Fit", observed_fit)
    dialog = fitted_dialog(gui)
    assert dialog.fit_result.status is MagCalibrationFitStatus.READY
    assert not any(" CAL APPLY " in c or c.endswith(" CAL SAVE") for c in wire.commands)
    assert not controller.file_transfer.owner.mag_subscribed.is_set()
    assert controller.file_transfer.send_command("SYSTEM INFO")
    wait_for(lambda: not controller.file_transfer.job_busy)
    before = list(wire.commands)
    controller.file_transfer._submit_download(None, list_only=True)
    assert not any(c == "LOGFILE ENTER" for c in wire.commands[len(before):])
    dialog.apply_ram.click()
    wait_for(lambda: dialog.applied_generation == 1 and not dialog.pending)
    assert not dialog.saved and "RAM" in dialog.status.text()
    assert "尚未保存" in dialog.device_state.text()
    dialog.save_device.click()
    wait_for(lambda: wire.save_reads == 1)
    assert not dialog.saved
    wait_for(lambda: dialog.saved)
    assert "已保存" in dialog.device_state.text()
    assert wire.last_packet is not None and len(wire.last_packet) == 84
    assert all(thread is not application.thread() for thread in wire.io_threads)
    assert fit_threads and all(thread is not application.thread() for thread in fit_threads)
    assert not any(c.startswith("CAL ") or "CAL_START" in c for c in wire.commands)
    dialog.request_close()
    wait_for(lambda: not dialog.isVisible() and not controller.file_transfer.mag_active)
    assert controller.file_transfer.owner.connected.is_set()
    controller.file_transfer._submit_download(None, list_only=True)
    wait_for(lambda: not controller.file_transfer.job_busy)
    assert "LOGFILE ENTER" in wire.commands


def test_save_failure_does_not_claim_persistence_and_retains_only_ram_confirmation(gui):
    gui[3].mode = "save_fail"
    dialog = applied_dialog(gui)
    dialog.save_device.click()
    wait_for(lambda: gui[3].save_failed and not dialog.pending)
    assert not dialog.saved and dialog.applied_generation == 1
    assert "RAM" in dialog.status.text() and "保存失败" in dialog.status.text()
    assert "保存失败" in dialog.device_state.text()


def test_save_retry_waits_for_new_pending_completion_despite_previous_failure_flag(gui):
    wire = gui[3]
    wire.mode = "save_fail"
    dialog = applied_dialog(gui)
    dialog.save_device.click()
    wait_for(lambda: wire.save_failed and not dialog.pending)
    assert not dialog.saved
    # The firmware SaveRequest retains historical failure fields while pending.
    wire.mode = "ok"
    dialog.save_device.click()
    wait_for(lambda: wire.save_reads == 1 and not dialog.pending)
    assert wire.save_pending and wire.save_failed and not dialog.saved
    wait_for(lambda: dialog.saved)
    assert not wire.save_pending and not wire.save_failed
    assert wire.commands.count("MAG 3 CAL SAVE") == 2


def test_changed_generation_during_save_invalidates_ram_identity(gui):
    gui[3].mode = "changed"
    dialog = applied_dialog(gui)
    dialog.save_device.click()
    wait_for(lambda: dialog.applied_generation is None and not dialog.pending)
    assert not dialog.saved
    assert "未知" in dialog.status.text() or "改变" in dialog.status.text()


def test_save_timeout_is_bounded_and_not_success(gui):
    gui[3].mode = "timeout"
    dialog = applied_dialog(gui)
    dialog.save_device.click()
    wait_for(lambda: gui[3].save_reads >= 1 and dialog.save_poll.isActive())
    dialog._save_deadline = time.monotonic() - 1
    wait_for(lambda: not dialog.save_poll.isActive() and not dialog.pending)
    assert not dialog.saved and "超时" in dialog.status.text() and "RAM" in dialog.status.text()


def test_hemisphere_collection_cannot_enable_apply(gui):
    gui[3].hemisphere = True
    dialog = fitted_dialog(gui)
    assert dialog.fit_result.status is MagCalibrationFitStatus.INSUFFICIENT_COVERAGE
    assert not dialog.apply_ram.isEnabled()
    assert not any(" CAL APPLY " in c for c in gui[3].commands)


def test_cancel_collection_stops_unsubscribes_and_leaves_shared_serial_connected(gui):
    dialog = connected_dialog(gui)
    dialog.start.click()
    wait_for(lambda: dialog.collecting)
    owner = gui[2].file_transfer.owner
    dialog.request_close()
    wait_for(lambda: not dialog.isVisible() and not gui[2].file_transfer.mag_active)
    assert "MAG 3 STREAM STOP" in gui[3].commands and not gui[3].stream
    assert not owner.mag_subscribed.is_set() and owner.connected.is_set()
    assert not any(" CAL APPLY " in c or c.endswith(" CAL SAVE") for c in gui[3].commands)


def test_cancel_queued_or_active_start_cannot_leave_stream_running(gui):
    dialog = connected_dialog(gui)
    gui[3].start_gate = Event()
    dialog.start.click()
    wait_for(lambda: gui[3].start_entered.is_set())
    dialog.request_close()
    gui[3].start_gate.set()
    wait_for(lambda: not dialog.isVisible() and not gui[2].file_transfer.mag_active)
    assert not gui[3].stream and "MAG 3 STREAM STOP" in gui[3].commands


def test_disconnect_stops_stream_and_invalidates_dialog(gui):
    dialog = connected_dialog(gui)
    dialog.start.click()
    wait_for(lambda: dialog.collecting)
    gui[2].file_transfer.disconnect_debug()
    wait_for(lambda: gui[2].file_transfer.owner is None)
    assert gui[3].closed and not gui[3].stream
    assert not dialog.collecting and not dialog.capable and not dialog.start.isEnabled()
    assert not dialog.transport.session_active and not gui[2].file_transfer.mag_active


def test_unsupported_firmware_cannot_start_collection(gui):
    gui[3].mode = "unsupported"
    _, window, controller, wire = gui
    window.debug_port_combo.setCurrentText("FAKE_MAG")
    controller.file_transfer.connect_debug()
    wait_for(lambda: window._debug_connected)
    window.btn_mag_calibration.click()
    dialog = controller.file_transfer.mag_dialog
    wait_for(lambda: any(c == "MAG 3 CAL READ" for c in wire.commands) and not dialog.pending)
    assert not dialog.capable and not dialog.start.isEnabled()
    assert "STREAM START" not in " ".join(wire.commands)


def test_other_console_query_during_collection_is_serialized_but_file_and_manual_mag_are_blocked(gui):
    dialog = connected_dialog(gui)
    dialog.start.click()
    manager = gui[2].file_transfer
    wait_for(lambda: dialog.collecting and not manager.job_busy)
    assert gui[1].maintenance_page.console.send.isEnabled()
    assert manager.send_command("SYSTEM INFO")
    wait_for(lambda: not manager.job_busy)
    assert dialog.collecting and gui[3].stream
    assert not manager.send_command("LOGFILE ENTER")
    assert not manager.send_command("MAG 3 STREAM STOP")
    manager._submit_download(None, list_only=True)
    assert "LOGFILE ENTER" not in gui[3].commands


def test_apply_acknowledgement_without_new_ram_generation_cannot_enable_save(gui):
    gui[3].mode = "apply_no_effect"
    dialog = fitted_dialog(gui)
    dialog.apply_ram.click()
    wait_for(lambda: not dialog.pending)
    assert dialog.applied_generation is None and not dialog.save_device.isEnabled()
    assert "RAM 已生效" not in dialog.status.text()
    assert not any(c.endswith(" CAL SAVE") for c in gui[3].commands)


def test_lost_start_acknowledgement_requires_cleanup_without_collecting_or_applying(gui):
    gui[3].mode = "start_timeout"
    dialog = connected_dialog(gui)
    dialog.start.click()
    wait_for(lambda: gui[3].start_entered.is_set() and not dialog.pending)
    assert not dialog.collecting and not dialog.apply_ram.isEnabled()
    dialog.request_close()
    wait_for(lambda: not dialog.isVisible())
    assert not gui[3].stream and "MAG 3 STREAM STOP" in gui[3].commands


def test_failed_stop_retains_lease_and_reports_uncertainty_until_disconnect(gui):
    gui[3].mode = "stop_fail"
    dialog = connected_dialog(gui)
    dialog.start.click()
    wait_for(lambda: dialog.collecting)
    dialog.request_close()
    wait_for(lambda: not dialog.closing)
    assert dialog.isVisible() and gui[2].file_transfer.mag_active
    assert not gui[2].file_transfer.owner.mag_subscribed.is_set()
    assert "停止未确认" in dialog.status.text()
    gui[2].file_transfer.disconnect_debug()
    wait_for(lambda: gui[2].file_transfer.owner is None)
    assert not gui[2].file_transfer.mag_active and not dialog.capable
