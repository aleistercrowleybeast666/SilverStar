import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app import Controller
from PySide6.QtCore import QSettings, QThread, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from services.device_export import DeviceExport, ExportCancelled
from services.i18n import I18n, Language
from test_file_service_client import MockTransport
from ui.file_transfer import DownloadWorker, ExportWorker, normalize_port
from ui.main_window import MainWindow
from ui.maintenance_page import MaintenancePage


class TransferUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        # The offscreen platform has no system font database on some Windows
        # hosts. Load the installed font explicitly so screenshots remain useful.
        font_path = Path("C:/Windows/Fonts/msyh.ttc")
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
            cls.application.setFont(QFont("Microsoft YaHei", 10))

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)
        self.window = MainWindow(I18n(self.settings))
        with patch("app.USER_DATA_ROOT", self.root), patch("app.list_serial_port_names", return_value=[]):
            self.controller = Controller(self.window)
        self.source = self.controller.log_dir / "fc_session_ui.jsonl"
        self.source.write_bytes(b'{"raw_hex":"00ff"}\n')
        self.target = self.root / "下载 日志"
        self.target.mkdir()
        self.window.pages.setCurrentIndex(3)
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        if self.controller.file_transfer.worker is not None:
            self.controller.file_transfer.worker.request_cancel()
            self.controller.file_transfer.worker.wait(3000)
            QTest.qWait(30)
        self.controller.shutdown()
        self.window.close()
        self.window.deleteLater()
        QTest.qWait(30)
        self.temp.cleanup()

    def wait_finished(self):
        deadline = time.monotonic() + 5
        while self.controller.file_transfer.busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.controller.file_transfer.busy)

    def test_copy_menu_runs_real_worker_and_keeps_source(self):
        with patch("ui.file_transfer.QFileDialog.getOpenFileNames", return_value=([str(self.source)], "")), \
             patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=str(self.target)), \
             patch("ui.file_transfer.QMessageBox.information"), patch("ui.file_transfer.QMessageBox.warning") as warning:
            self.window.action_export_copy.trigger()
            self.assertTrue(self.controller.file_transfer.busy)
            self.assertFalse(self.window.btn_process_data.isEnabled())
            self.wait_finished()
        warning.assert_not_called()
        self.assertTrue(self.source.exists())
        self.assertEqual(len(list(self.target.glob("*/manifest.json"))), 1)
        self.assertTrue(self.window.btn_process_data.isEnabled())

    def test_cut_requires_gui_confirmation_of_completed_copy(self):
        confirmations = []
        timer = QTimer()
        timer.setInterval(20)
        def approve():
            dialog = self.application.activeModalWidget()
            if not isinstance(dialog, QMessageBox):
                return
            self.assertTrue(self.source.exists())
            self.assertEqual(len(list(self.target.glob("*/manifest.json"))), 1)
            confirmations.append(dialog.text())
            evidence = os.environ.get("GSHC_TRANSFER_QA_DIR")
            if evidence:
                Path(evidence).mkdir(parents=True, exist_ok=True)
                dialog.grab().save(str(Path(evidence) / "windows_cut_confirmation.png"))
            dialog.button(QMessageBox.StandardButton.Yes).click()
            timer.stop()
        timer.timeout.connect(approve)
        with patch("ui.file_transfer.QFileDialog.getOpenFileNames", return_value=([str(self.source)], "")), \
             patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=str(self.target)), \
             patch("ui.file_transfer.QMessageBox.information"), patch("ui.file_transfer.QMessageBox.warning") as warning:
            timer.start()
            self.window.action_export_cut.trigger()
            self.wait_finished()
        warning.assert_not_called()
        self.assertEqual(len(confirmations), 1)
        self.assertFalse(self.source.exists())

    def test_declined_cut_leaves_source(self):
        with patch("ui.file_transfer.QFileDialog.getOpenFileNames", return_value=([str(self.source)], "")), \
             patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=str(self.target)), \
             patch("ui.file_transfer.QMessageBox.question", return_value=QMessageBox.StandardButton.No), \
             patch("ui.file_transfer.QMessageBox.information"):
            self.window.action_export_cut.trigger()
            self.wait_finished()
        self.assertTrue(self.source.exists())

    def test_close_cancels_and_retains_running_thread_until_finished(self):
        class SlowExport(DeviceExport):
            def copy(self, **_):
                self.cancel.wait(2)
                raise ExportCancelled()
        exporter = SlowExport([self.source], self.target, managed_root=self.controller.log_dir, is_active=lambda _: False)
        worker = ExportWorker(exporter, False, self.controller.file_transfer)
        with patch("ui.file_transfer.QMessageBox.warning"):
            self.controller.file_transfer._start(worker)
            QTest.qWait(30)
            self.window.close()
            self.assertTrue(self.window.isVisible())
            self.wait_finished()
        self.assertTrue(self.source.exists())
        self.window.close()
        self.assertFalse(self.window.isVisible())

    def test_download_menu_uses_mock_transport_off_gui_and_keeps_remote(self):
        wire = MockTransport()
        threads = []
        def factory(port, baud):
            threads.append(QThread.currentThread())
            return wire
        self.controller.file_transfer.transport_factory = factory
        self.window.debug_port_combo.setCurrentText("COM7")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        self.assertFalse(wire.closed)
        # A separate live Ground route is allowed while the maintenance owner
        # remains exclusive to COM7. The transport itself is entirely mocked.
        self.controller.worker = SimpleNamespace(_config=SimpleNamespace(port="COM8"))
        self.controller.state.connected = True
        active = self.controller.logger.open_session("test_ground")
        with patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=str(self.target)), \
             patch("ui.file_transfer.QMessageBox.information"), patch("ui.file_transfer.QMessageBox.warning") as warning:
            self.window.action_download_copy.trigger()
            self.wait_finished()
        warning.assert_not_called()
        self.assertFalse(wire.closed)
        self.assertTrue(self.controller.logger.session_active)
        self.assertTrue(active.exists())
        self.assertTrue(threads and all(thread != self.application.thread() for thread in threads))
        self.assertEqual(len(list(self.target.glob("*/manifest.json"))), 1)
        self.assertFalse(any("DELETE" in command for command in wire.commands))
        self.assertEqual(self.window.maintenance_page.catalog.count(), 1)
        page = self.window.maintenance_page
        self.assertEqual(self.settings.value(page.TF_DIRECTORY_KEY), str(self.target.resolve()))
        self.assertEqual(page.destination_path.text(), str(self.target.resolve()))
        restored = MaintenancePage(I18n(QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)))
        self.assertEqual(restored.destination_path.text(), str(self.target.resolve()))
        restored.deleteLater()
        before = list(wire.commands)
        with patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value="") as chooser:
            self.window.action_download_copy.trigger()
        self.assertEqual(chooser.call_args.args[2], str(self.target.resolve()))
        self.assertEqual(wire.commands, before)
        self.window.btn_debug_disconnect.click()
        self.wait_disconnected()
        self.assertTrue(wire.closed)

    def wait_connected(self):
        deadline = time.monotonic() + 3
        while not self.window._debug_service_supported and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(self.window._debug_connected)
        self.assertTrue(self.window._debug_service_supported)

    def test_directory_selection_cancel_sends_no_file_request_or_settings_write(self):
        wire = MockTransport()
        self.controller.file_transfer.transport_factory = lambda *_: wire
        self.window.debug_port_combo.setCurrentText("COM7")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        before = list(wire.commands)
        with patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=""):
            self.window.action_download_copy.trigger()
        QTest.qWait(30)
        self.assertEqual(wire.commands, before)
        self.assertFalse(self.controller.file_transfer.busy)
        self.assertIsNone(self.settings.value(self.window.maintenance_page.TF_DIRECTORY_KEY))

    def test_unwritable_directory_is_not_remembered_or_transferred(self):
        wire = MockTransport()
        self.controller.file_transfer.transport_factory = lambda *_: wire
        self.window.debug_port_combo.setCurrentText("COM7")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        before = list(wire.commands)
        with patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=str(self.target)), \
             patch("ui.file_transfer.validate_download_directory", side_effect=PermissionError("mock revoked permission")), \
             patch("ui.file_transfer.QMessageBox.warning"):
            self.window.action_download_copy.trigger()
            self.wait_finished()
            self.wait_disconnected()
        self.assertEqual(wire.commands, before)
        self.assertIsNone(self.settings.value(self.window.maintenance_page.TF_DIRECTORY_KEY))
        self.assertEqual(list(self.target.iterdir()), [])

    def wait_disconnected(self):
        deadline = time.monotonic() + 3
        while self.controller.file_transfer.owner is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNone(self.controller.file_transfer.owner)
        self.assertFalse(self.window._debug_connected)

    def test_dual_port_alias_collision_and_unplug_do_not_autoreconnect(self):
        self.assertEqual(normalize_port("\\\\.\\com007"), "COM7")
        self.controller.worker = SimpleNamespace(_config=SimpleNamespace(port="COM7"))
        self.window.debug_port_combo.setCurrentText("\\\\.\\com007")
        with patch("ui.file_transfer.QMessageBox.warning") as warning:
            self.window.btn_debug_connect.click()
        warning.assert_called_once()
        self.assertIsNone(self.controller.file_transfer.owner)
        self.controller.worker = None
        wire = MockTransport()
        self.controller.file_transfer.transport_factory = lambda *_: wire
        self.window.debug_port_combo.setCurrentText("COM7")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        self.window.set_ports(["COM7"])
        with patch("app.QMessageBox.warning") as warning, patch.object(self.controller.link, "open") as serial_open:
            self.controller.connect()
        warning.assert_called_once()
        serial_open.assert_not_called()
        def unplug():
            raise OSError("mock unplug")
        wire.check_alive = unplug
        with patch("ui.file_transfer.QMessageBox.warning"):
            self.wait_disconnected()
        commands = list(wire.commands)
        QTest.qWait(100)
        self.assertEqual(wire.commands, commands)

    def test_fourth_page_single_entry_and_unavailable_diagnostics(self):
        self.assertEqual(self.window.pages.count(), 4)
        self.assertEqual(self.window.btn_export_device.parent(), self.window.maintenance_page)
        page = self.window.maintenance_page
        page.render(self.controller.state)
        self.assertIn(self.window.i18n.tr("maintenance.unavailable"), page.labels["system"][1].text())
        page.btn_details.click()
        self.assertTrue(page.details.isVisible())
        self.assertEqual(page.tree.topLevelItemCount(), 5)
        self.controller.state.handshake.last_preflight_status_rx_monotonic_ns = time.monotonic_ns() - 10_000_000_000
        self.controller.state.receive_health.last_rx_monotonic_ns = time.monotonic_ns()
        self.controller.state.connected = True
        page.render(self.controller.state)
        self.assertIn(self.window.i18n.tr("maintenance.stale"), page.labels["system"][1].text())
        self.assertIn(self.window.i18n.tr("maintenance.source"), page.source.text())
        self.assertEqual(page.detail_source.text(), page.source.text())
        self.controller.state.sensor.host_rx_monotonic_ns = time.monotonic_ns()
        page.render(self.controller.state)
        sensors = page.tree.topLevelItem(1)
        self.assertEqual(sensors.child(2).text(2), self.window.i18n.tr("maintenance.time_unknown"))
        page.details.close()

    def test_unsupported_or_timed_out_caps_keeps_port_open_and_disables_files(self):
        for timeout in (False, True):
            class UnsupportedTransport(MockTransport):
                def exchange(self, command, response_timeout, cancel, negotiation_timeout=timeout):
                    if command == "LOGFILE CAPS":
                        if negotiation_timeout:
                            raise TimeoutError("mock negotiation timeout")
                        return "ERR UNKNOWN_MODULE LOGFILE"
                    return super().exchange(command, response_timeout, cancel)
            wire = UnsupportedTransport()
            self.controller.file_transfer.transport_factory = lambda *_, transport=wire: transport
            self.window.debug_port_combo.setCurrentText("COM9")
            self.window.btn_debug_connect.click()
            deadline = time.monotonic() + 3
            while "COM9@" not in self.window.maintenance_page.service_status.text() and time.monotonic() < deadline:
                QTest.qWait(10)
            self.assertTrue(self.window._debug_connected)
            self.assertFalse(self.window._debug_service_supported)
            self.assertFalse(self.window.btn_download_device.isEnabled())
            self.assertFalse(self.window.btn_refresh_device_logs.isEnabled())
            self.assertFalse(wire.closed)
            self.assertIn("timeout" if timeout else "unsupported", self.window.maintenance_page.service_status.text())
            self.window.btn_debug_disconnect.click()
            self.wait_disconnected()
            self.assertTrue(wire.closed)

    def test_close_cancels_persistent_owner_and_retains_thread_until_close(self):
        class SlowList(MockTransport):
            def exchange(self, command, timeout, cancel):
                if command.startswith("LOGFILE POLL") and self.pending[1] == "LIST":
                    return f"PENDING LOGFILE LIST request_id={self.request_id}"
                return super().exchange(command, timeout, cancel)
        wire = SlowList()
        self.controller.file_transfer.transport_factory = lambda *_: wire
        self.window.debug_port_combo.setCurrentText("COM9")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        self.window.btn_refresh_device_logs.click()
        QTest.qWait(50)
        self.assertTrue(self.controller.file_transfer.job_busy)
        with patch("ui.file_transfer.QMessageBox.warning"):
            self.window.close()
            self.assertTrue(self.window.isVisible())
            self.wait_disconnected()
        self.assertTrue(wire.closed)
        self.assertFalse(self.controller.file_transfer.busy)
        self.window.close()
        self.assertFalse(self.window.isVisible())

    def test_real_widgets_screenshots_and_translations(self):
        evidence = os.environ.get("GSHC_TRANSFER_QA_DIR")
        self.window.i18n.set_language(Language.ZH_CN)
        self.window.retranslate_ui()
        self.assertIn("导出", self.window.btn_export_device.text())
        self.assertIn("复制", self.window.action_export_copy.text())
        self.window.resize(1200, 800)
        QTest.qWait(60)
        if evidence:
            folder = Path(evidence)
            folder.mkdir(parents=True, exist_ok=True)
            self.assertTrue(self.window.grab().save(str(folder / "windows_transfer_zh.png")))
            menu = self.window.btn_export_device.menu()
            menu.popup(self.window.btn_export_device.mapToGlobal(self.window.btn_export_device.rect().bottomLeft()))
            QTest.qWait(30)
            self.assertTrue(menu.grab().save(str(folder / "windows_export_menu.png")))
            menu.close()
        self.window.i18n.set_language(Language.EN_US)
        self.window.retranslate_ui()
        self.assertIn("Export", self.window.btn_export_device.text())
        QTest.qWait(40)
        if evidence:
            self.assertTrue(self.window.grab().save(str(folder / "windows_transfer_en.png")))
            menu = self.window.btn_download_device.menu()
            menu.popup(self.window.btn_download_device.mapToGlobal(self.window.btn_download_device.rect().bottomLeft()))
            QTest.qWait(30)
            self.assertTrue(menu.grab().save(str(folder / "windows_download_menu.png")))
            menu.close()

    def test_large_progress_and_transport_close_failure_are_reported(self):
        wire = MockTransport()
        def fail_close():
            raise OSError("mock close failure")
        wire.close = fail_close
        worker = DownloadWorker("MOCK", 115200, self.target, transport_factory=lambda *_: wire)
        completed, failed = [], []
        worker.completed.connect(completed.append)
        worker.failed.connect(failed.append)
        worker.run()
        self.assertFalse(completed)
        self.assertEqual(len(failed), 1)
        self.assertIn("close failed", failed[0])
        self.assertIn(str(self.target), failed[0])
        # Qt's signed int progress range is never given a uint32 file size.
        with patch("ui.file_transfer.QMessageBox.warning"):
            exporter = DeviceExport([self.source], self.target, managed_root=self.controller.log_dir, is_active=lambda _: False)
            job = ExportWorker(exporter, False, self.controller.file_transfer)
            emitted = []
            job.progress.connect(lambda done, total, detail: emitted.append((done, total, detail)))
            job.progress.emit(0x80000000, 0xFFFFFFFF, "large signal")
            self.assertEqual(emitted, [(0x80000000, 0xFFFFFFFF, "large signal")])
            self.controller.file_transfer._start(job)
            self.controller.file_transfer._progress(0x80000000, 0xFFFFFFFF, "large file")
            self.assertEqual(self.controller.file_transfer.dialog.maximum(), 1000)
            job.request_cancel()
            self.wait_finished()

    def test_failed_download_reports_partial_output_location(self):
        wire = MockTransport()
        wire.mutate = lambda text: text.replace("crc32=CBF43926 data=", "crc32=00000000 data=")
        worker = DownloadWorker("MOCK", 115200, self.target, transport_factory=lambda *_: wire)
        failures = []
        worker.failed.connect(failures.append)
        worker.run()
        partial = next(self.target.glob("*/*.partial"))
        self.assertEqual(len(failures), 1)
        self.assertIn(str(partial.parent), failures[0])
        self.assertTrue(partial.with_name(partial.name + ".json").exists())
        self.assertEqual(wire.data, b"123456789")

    def test_pending_start_submits_no_logfile_job_or_destination_write(self):
        wire = MockTransport()
        self.controller.file_transfer.transport_factory = lambda *_: wire
        self.window.debug_port_combo.setCurrentText("COM7")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        before = list(wire.commands)
        self.controller.state.pending_command_name = "START_MISSION"
        with patch("ui.file_transfer.QFileDialog.getExistingDirectory", return_value=str(self.target)), \
             patch("ui.file_transfer.QMessageBox.information"):
            self.controller.file_transfer.choose_download()
            self.wait_finished()
        self.assertEqual(wire.commands, before)
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertFalse(self.controller.file_transfer._available())
        self.assertFalse(self.controller.file_transfer._available(maintenance=True))
        self.window.render_state()
        self.assertFalse(self.window.btn_export_device.isEnabled())
        self.assertFalse(self.window.btn_download_device.isEnabled())
        self.assertFalse(self.window.btn_refresh_device_logs.isEnabled())
        self.assertTrue(self.window.btn_generate_sim.isEnabled())

    def test_new_pending_start_cancels_existing_maintenance_job(self):
        class SlowList(MockTransport):
            def exchange(self, command, timeout, cancel):
                if command.startswith("LOGFILE POLL") and self.pending[1] == "LIST":
                    return f"PENDING LOGFILE LIST request_id={self.request_id}"
                return super().exchange(command, timeout, cancel)
        wire = SlowList()
        self.controller.file_transfer.transport_factory = lambda *_: wire
        self.window.debug_port_combo.setCurrentText("COM7")
        self.window.btn_debug_connect.click()
        self.wait_connected()
        self.window.btn_refresh_device_logs.click()
        QTest.qWait(30)
        self.assertTrue(self.controller.file_transfer.job_busy)
        self.controller.state.pending_command_name = "START_MISSION"
        with patch("ui.file_transfer.QMessageBox.warning"):
            self.window.render_state()
            self.wait_finished()
        self.assertTrue(self.controller.file_transfer.owner.job_cancel.is_set())
        self.assertFalse(any(" READ " in command for command in wire.commands))
        self.assertEqual(list(self.target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
