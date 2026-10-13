"""Background file operations and their explicit destructive confirmation."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import time
from pathlib import Path
from threading import Event
from uuid import uuid4

from config import APP_VERSION
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
from services.device_export import DeviceExport, ExportCancelled
from services.file_service_client import (
    FileServiceClient,
    FileServiceError,
    validate_download_directory,
)
from transport.file_service_backend import FileServiceSerialTransport
from transport.serial_options import SerialBaud_Parse
from services.legacy_firmware_status import LegacyFirmwareStatusClient
from services.legacy_firmware_status import LegacyFirmwareSnapshot
from services.runtime_diagnostics import RuntimeDiagnosticsClient, LegacyDiagnostics_FromSnapshot

_logger = logging.getLogger(__name__)


class DownloadWorker(QThread):
    destination_validated = Signal(str)
    progress = Signal(object, object, str)
    confirm_delete = Signal(object)
    completed = Signal(str)
    failed = Signal(str)
    catalog = Signal(object)

    def __init__(self, port: str, baud: int, destination: Path | None, *, delete_id: int | None = None,
                 transport_factory=FileServiceSerialTransport, close_transport=True, list_only=False, parent=None) -> None:
        super().__init__(parent)
        self.port, self.baud, self.destination = port, baud, destination
        self.delete_id = delete_id
        self.transport_factory = transport_factory
        self.close_transport = close_transport
        self.list_only = list_only
        self.operation_error = None
        self.cancel = Event()
        self.decision = Event()
        self.approved_token = ""

    def request_cancel(self) -> None:
        self.cancel.set()
        self.decision.set()

    def confirm(self, token: str) -> None:
        self.approved_token = token
        self.decision.set()

    def run(self) -> None:
        transport = None
        client = None
        result = None
        error = None
        output = None
        try:
            if self.cancel.is_set():
                raise ExportCancelled("Cancelled before opening maintenance transport")
            if not self.list_only and self.delete_id is None:
                if self.destination is None:
                    raise ValueError("Select a destination")
                self.destination = validate_download_directory(self.destination)
                self.destination_validated.emit(str(self.destination))
            transport = self.transport_factory(self.port, self.baud)
            client = FileServiceClient(transport, cancel=self.cancel)
            client.negotiate()
            if self.delete_id is not None:
                log = client.prepare_delete(self.delete_id)
                self.confirm_delete.emit(log)
                while not self.decision.wait(0.1):
                    client._check()
                client._check()
                if self.approved_token:
                    client.delete(log, confirmed_token=self.approved_token)
                    result = f"Deleted mission {log.file_id}"
                else:
                    result = "Deletion declined; source retained"
                return
            client.enter_maintenance()
            ids = client.list_closed()
            self.catalog.emit(ids)
            if self.list_only:
                result = f"Listed {len(ids)} closed logs"
                return
            if not ids:
                result = "No closed device logs available"
                return
            if self.destination is None:
                raise ValueError("Select a destination")
            output = self.destination / ("SilverStar_download_" + time.strftime("%Y%m%d_%H%M%S_") + uuid4().hex[:12])
            output.mkdir(exist_ok=False)
            files = []
            for file_id in ids:
                path = client.download(file_id, output, progress=self.progress.emit)
                digest = hashlib.sha256()
                with path.open("rb") as fp:
                    while data := fp.read(1024 * 1024):
                        client._check()
                        digest.update(data)
                files.append({"path": path.name, "role": "flight_log", "format": "SSLOG", "format_version": "0.0",
                              "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()})
            manifest = {"schema_version": 1, "format": "silverstar.session-export", "session_id": output.name,
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "source_app": {"name": "GSHC", "version": APP_VERSION},
                        "protocols": {"log_file_service": 1, "sslog": "0.0"}, "files": files}
            encoded = json.dumps(manifest, indent=2).encode("utf-8")
            manifest_path = output / "manifest.json"
            with manifest_path.open("xb") as fp:
                fp.write(encoded)
                fp.flush()
                os.fsync(fp.fileno())
            if manifest_path.read_bytes() != encoded:
                raise OSError("Manifest readback mismatch")
            client._check()
            result = str(output)
        except Exception as exc:
            _logger.exception("Maintenance file operation failed")
            error = str(exc)
            self.operation_error = exc
        finally:
            if client is not None:
                client.cancel_remote()
            if transport is not None and self.close_transport:
                try:
                    transport.close()
                except Exception as exc:
                    _logger.exception("Maintenance transport close failed")
                    error = f"{error + '; ' if error else ''}Maintenance close failed: {exc}"
                    self.operation_error = exc
            if error is not None:
                if output is not None or self.destination is not None:
                    error += f"\nOutput: {output or self.destination}"
                self.failed.emit(error)
            elif result is not None:
                self.completed.emit(result)


def normalize_port(port: str) -> str:
    text = port.strip().upper()
    text = text.removeprefix("\\\\.\\")
    if re.fullmatch(r"COM[0-9]+", text):
        return "COM" + str(int(text[3:]))
    return text


class MaintenanceOwner(QThread):
    destination_validated = Signal(str)
    connection_changed = Signal(bool, str)
    progress = Signal(object, object, str)
    catalog = Signal(object)
    completed = Signal(str)
    failed = Signal(str)
    job_finished = Signal()
    service_status = Signal(bool, str)
    firmware_status = Signal(object, str)
    diagnostic_status = Signal(object, str)

    def __init__(self, port, baud, *, transport_factory=FileServiceSerialTransport, parent=None):
        super().__init__(parent)
        self.port, self.baud = port, baud
        self.transport_factory = transport_factory
        self.stop = Event()
        self.connected = Event()
        self.job_cancel = Event()
        self.jobs = queue.Queue(maxsize=1)
        self.operation = None

    def submit(self, destination=None, *, list_only=False):
        if not self.connected.is_set() or self.stop.is_set() or self.operation is not None:
            return False
        try:
            self.job_cancel.clear()
            self.jobs.put_nowait((destination, list_only))
            return True
        except queue.Full:
            return False

    def request_cancel(self):
        self.job_cancel.set()
        operation = self.operation
        if operation is not None:
            operation.request_cancel()

    def request_stop(self):
        self.stop.set()
        self.request_cancel()

    def run(self):
        transport = None
        status_client = None
        detail = "Disconnected"
        try:
            transport = self.transport_factory(self.port, self.baud)
            if self.stop.is_set():
                return
            self.connected.set()
            self.connection_changed.emit(True, f"Port open: {self.port}@{self.baud}")
            try:
                status_client = FileServiceClient(transport, cancel=self.stop)
                caps = status_client.negotiate()
                safe_files = caps.get("maintenance_required") == "1" and caps.get("status_version") == "1"
                self.service_status.emit(safe_files, f"{self.port}@{self.baud} · LOGFILE v1 · explicit maintenance {'supported' if safe_files else 'unsupported'} · device/boot identity unknown")
            except FileServiceError as exc:
                self.service_status.emit(False, f"{self.port}@{self.baud} · LOGFILE unsupported: {exc}")
                status_client = LegacyFirmwareStatusClient(transport, cancel=self.stop)
            except TimeoutError:
                self.service_status.emit(False, f"{self.port}@{self.baud} · LOGFILE unavailable: negotiation response timeout; serial port remains open")
                status_client = LegacyFirmwareStatusClient(transport, cancel=self.stop)
            if isinstance(status_client, FileServiceClient) and caps.get("status_version") != "1":
                status_client = LegacyFirmwareStatusClient(transport, cancel=self.stop)
            next_status = 0.0
            diagnostic_client = RuntimeDiagnosticsClient(transport, self.stop)
            while not self.stop.is_set():
                try:
                    destination, list_only = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    if time.monotonic() >= next_status:
                        next_status = time.monotonic() + 1.0
                        try:
                            if status_client is None:
                                status_client = FileServiceClient(transport, cancel=self.stop)
                            snapshot = status_client.status()
                            self.firmware_status.emit(snapshot, "")
                            if isinstance(snapshot, LegacyFirmwareSnapshot) and diagnostic_client is None:
                                self.diagnostic_status.emit(LegacyDiagnostics_FromSnapshot(snapshot), "Legacy 0.0 fields; completion instrumentation unavailable")
                        except (FileServiceError, TimeoutError) as exc:
                            self.firmware_status.emit(None, str(exc))
                    if diagnostic_client is not None:
                        try:
                            entries = diagnostic_client.step()
                            if entries is not None:
                                self.diagnostic_status.emit(entries, "Maintenance 0.1; independent RAM observations")
                        except (FileServiceError, TimeoutError) as exc:
                            diagnostic_client = None
                            self.diagnostic_status.emit(None, str(exc))
                    transport.check_alive()
                    continue
                if self.stop.is_set():
                    break
                transport.prepare_job()
                if diagnostic_client is not None:
                    diagnostic_client.entries, diagnostic_client.cursor = [], 0
                    diagnostic_client.next_cycle = time.monotonic() + 1.0
                self.diagnostic_status.emit(None, "Polling paused during file transfer; no real-time claim")
                operation = DownloadWorker(self.port, self.baud, destination,
                    transport_factory=lambda *_: transport, close_transport=False, list_only=list_only)
                self.operation = operation
                operation.progress.connect(self.progress, Qt.DirectConnection)
                operation.destination_validated.connect(self.destination_validated, Qt.DirectConnection)
                operation.catalog.connect(self.catalog, Qt.DirectConnection)
                operation.completed.connect(self.completed, Qt.DirectConnection)
                operation.failed.connect(self.failed, Qt.DirectConnection)
                if self.stop.is_set() or self.job_cancel.is_set():
                    operation.request_cancel()
                operation.run()
                self.operation = None
                self.jobs.task_done()
                self.job_finished.emit()
                if isinstance(operation.operation_error, OSError):
                    detail = str(operation.operation_error)
                    break
        except ExportCancelled:
            # A disconnect can arrive between the idle-loop stop check and
            # STATUS exchange. It is expected cancellation, not a modal error.
            detail = "Disconnected / status invalidated"
        except Exception as exc:
            _logger.exception("Maintenance owner failed")
            detail = str(exc)
            self.failed.emit(detail)
        finally:
            self.connected.clear()
            self.operation = None
            if transport is not None:
                try:
                    transport.close()
                except Exception as exc:
                    _logger.exception("Maintenance owner close failed")
                    detail = f"Close failed: {exc}"
                    self.failed.emit(detail)
            self.connection_changed.emit(False, detail)


class ExportWorker(QThread):
    progress = Signal(object, object, str)
    confirm_cut = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, exporter: DeviceExport, cut: bool, parent=None) -> None:
        super().__init__(parent)
        self.exporter = exporter
        self.cut = cut
        self.decision = Event()
        self.approved = False

    def request_cancel(self) -> None:
        self.exporter.cancel.set()
        self.decision.set()

    def confirm(self, approved: bool) -> None:
        self.approved = approved
        self.decision.set()

    def run(self) -> None:
        try:
            output = self.exporter.copy(cut=self.cut, progress=self.progress.emit)
            if self.cut:
                self.confirm_cut.emit(str(output))
                # Cancellation and shutdown wake this wait, without a GUI join.
                while not self.decision.wait(0.1):
                    self.exporter._check()
                self.exporter._check()
                self.exporter.delete_verified_sources(confirmed=self.approved)
            self.completed.emit(str(output))
        except ExportCancelled:
            self.failed.emit("Cancelled; any completed destination files remain. Source files retained unless a confirmed cut had already begun.")
        except Exception as exc:
            _logger.exception("Device export failed")
            self.failed.emit(str(exc))


class FileTransferManager(QObject):
    def __init__(self, controller) -> None:
        super().__init__(controller)
        self.controller = controller
        self.worker: QThread | None = None
        self.dialog: QProgressDialog | None = None
        self.stopping = False
        self.owner: MaintenanceOwner | None = None
        self.job_busy = False
        self.transport_factory = FileServiceSerialTransport
        controller.window.maintenance_page.cancel.clicked.connect(self.cancel)

    @property
    def busy(self) -> bool:
        return self.worker is not None or self.job_busy

    def _tr(self, key: str, **params) -> str:
        return self.controller._tr(key, **params)

    def _available(self, *, maintenance=False) -> bool:
        c = self.controller
        return not (self.busy or c.state.mission_started or c.state.start_transaction_pending() or (not maintenance and (c.logger.session_active
                    or c.worker is not None or c.protocol_worker is not None))
                    or c.processing_thread is not None or c.simulation_thread is not None
                    or c.data_migration_thread is not None)

    def connect_debug(self):
        c = self.controller
        if self.owner is not None:
            return
        port = c.window.debug_port_combo.currentText().strip()
        baud = SerialBaud_Parse(c.window.debug_baud_combo.currentText())
        if not port:
            self._failed(self._tr("maintenance.invalid_port"))
            return
        if baud == 0:
            self._failed(self._tr("message.invalid_baudrate"))
            return
        if c.worker is not None and normalize_port(c.worker._config.port) == normalize_port(port):
            self._failed(self._tr("maintenance.same_port"))
            return
        owner = MaintenanceOwner(port, baud, transport_factory=self.transport_factory, parent=self)
        self.owner = owner
        owner.connection_changed.connect(self._connection_changed, Qt.QueuedConnection)
        owner.service_status.connect(self._service_status, Qt.QueuedConnection)
        owner.firmware_status.connect(self._firmware_status, Qt.QueuedConnection)
        owner.diagnostic_status.connect(self._diagnostic_status, Qt.QueuedConnection)
        owner.destination_validated.connect(self._destination_validated, Qt.QueuedConnection)
        owner.progress.connect(self._progress, Qt.QueuedConnection)
        owner.catalog.connect(c.window.maintenance_page.show_catalog, Qt.QueuedConnection)
        owner.completed.connect(self._completed, Qt.QueuedConnection)
        owner.failed.connect(self._failed, Qt.QueuedConnection)
        owner.job_finished.connect(self._job_finished, Qt.QueuedConnection)
        owner.finished.connect(self._owner_finished)
        c.window.debug_status.setText(self._tr("maintenance.connecting"))
        c.window.debug_port_combo.setEnabled(False)
        c.window.debug_baud_combo.setEnabled(False)
        c.window.btn_debug_connect.setEnabled(False)
        owner.start()

    def disconnect_debug(self):
        if self.owner is not None:
            self.controller.window.maintenance_page.set_firmware_status(None, "Disconnected / invalidated")
            self.controller.window.maintenance_page.set_diagnostics(None, "Disconnected / invalidated")
            self.controller.window.debug_status.setText(self._tr("maintenance.stopping"))
            self.owner.request_stop()

    def _connection_changed(self, connected, detail):
        window = self.controller.window
        window._debug_connected = bool(connected)
        window.debug_status.setText(detail)
        window.debug_status.setToolTip(detail)
        if not connected:
            window._debug_service_supported = False
            window.maintenance_page.catalog.clear()
            window.maintenance_page.service_status.setText("LOGFILE: disconnected / negotiation invalidated")
            window.maintenance_page.set_firmware_status(None, "Disconnected / invalidated")
            window.maintenance_page.set_diagnostics(None, "Disconnected / invalidated")
        window._render_data_tool_buttons()

    def _service_status(self, supported, detail):
        window = self.controller.window
        window._debug_service_supported = bool(supported)
        window.maintenance_page.service_status.setText(detail)
        window._render_data_tool_buttons()

    def _firmware_status(self, snapshot, detail):
        if self.owner is not None and not self.owner.stop.is_set():
            self.controller.window.maintenance_page.set_firmware_status(snapshot, detail)

    def _diagnostic_status(self, entries, detail):
        if self.owner is not None and not self.owner.stop.is_set():
            self.controller.window.maintenance_page.set_diagnostics(entries, detail)

    def _destination_validated(self, destination):
        page = self.controller.window.maintenance_page
        settings = self.controller.window.i18n.settings
        settings.setValue(page.TF_DIRECTORY_KEY, destination)
        settings.sync()
        page.set_destination(destination)

    def _owner_finished(self):
        self._job_finished()
        if self.owner is not None:
            self.owner.deleteLater()
            self.owner = None
        window = self.controller.window
        window.debug_port_combo.setEnabled(True)
        window.debug_baud_combo.setEnabled(True)
        window.btn_debug_connect.setEnabled(True)

    def _job_finished(self):
        self.job_busy = False
        self.controller.window.set_data_tools_busy(self.worker is not None)
        self.controller.window.maintenance_page.cancel.setEnabled(self.worker is not None)

    def cancel(self):
        if self.worker is not None:
            self.worker.request_cancel()
        if self.owner is not None:
            self.owner.request_cancel()

    def choose_export(self, cut: bool) -> None:
        c = self.controller
        if not self._available():
            QMessageBox.information(c.window, self._tr("transfer.title"), self._tr("transfer.busy"))
            return
        sources, _ = QFileDialog.getOpenFileNames(c.window, self._tr("transfer.sources"), str(c.log_dir), "Logs (*.jsonl *.sslog);;All files (*)")
        if not sources:
            return
        destination = QFileDialog.getExistingDirectory(c.window, self._tr("transfer.destination"))
        if not destination:
            return
        if not self._available():
            self._failed(self._tr("transfer.busy"))
            return
        exporter = DeviceExport([Path(p) for p in sources], Path(destination), managed_root=c.log_dir,
                                is_active=lambda p: c.logger.session_active and c.logger.path == p,
                                app_version=APP_VERSION)
        worker = ExportWorker(exporter, cut, self)
        worker.confirm_cut.connect(self._confirm_cut, Qt.QueuedConnection)
        self._start(worker)

    def choose_download(self, delete: bool = False) -> None:
        c = self.controller
        if delete:
            self._failed(self._tr("transfer.download_delete"))
            return
        if not self._available(maintenance=True) or self.owner is None or not self.owner.connected.is_set():
            QMessageBox.information(c.window, self._tr("transfer.title"), self._tr("transfer.busy"))
            return
        page = c.window.maintenance_page
        selected = QFileDialog.getExistingDirectory(c.window, self._tr("maintenance.destination"), page.destination_path.text())
        if not selected:
            return
        self._submit_download(Path(selected))

    def refresh_device_logs(self):
        if not self._available(maintenance=True):
            return
        self._submit_download(None, list_only=True)

    def _submit_download(self, destination, *, list_only=False):
        if not self._available(maintenance=True):
            self._failed(self._tr("transfer.busy"))
            return
        if not self.controller.window._debug_service_supported or self.owner is None or not self.owner.submit(destination, list_only=list_only):
            self._failed(self._tr("maintenance.connect_first"))
            return
        self.job_busy = True
        self.controller.window.set_data_tools_busy(True)
        self.controller.window.maintenance_page.cancel.setEnabled(True)
        self.controller.window.maintenance_page.status.setText(self._tr("transfer.working"))

    def _start(self, worker: QThread) -> None:
        self.worker = worker
        self.controller.window.maintenance_page.cancel.setEnabled(True)
        self.controller.window.set_data_tools_busy(True)
        self.dialog = QProgressDialog(self._tr("transfer.working"), self._tr("transfer.cancel"), 0, 0, self.controller.window)
        self.dialog.setWindowTitle(self._tr("transfer.title"))
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(worker.request_cancel)
        worker.progress.connect(self._progress, Qt.QueuedConnection)
        worker.completed.connect(self._completed, Qt.QueuedConnection)
        worker.failed.connect(self._failed, Qt.QueuedConnection)
        worker.finished.connect(self._finished)
        self.dialog.show()
        worker.start()

    def _progress(self, done: int, total: int, detail: str) -> None:
        self.controller.window.maintenance_page.progress.setValue(min(1000, max(0, int(done * 1000 // max(1, total)))))
        self.controller.window.maintenance_page.status.setText(detail)
        if self.dialog is not None and not self.stopping:
            self.dialog.setRange(0, 1000)
            self.dialog.setValue(min(1000, max(0, int(done * 1000 // max(1, total)))))
            self.dialog.setLabelText(detail)

    def _confirm_cut(self, output: str) -> None:
        worker = self.worker
        if not isinstance(worker, ExportWorker):
            return
        approved = False
        if not self.stopping and not worker.exporter.cancel.is_set():
            approved = QMessageBox.question(self.controller.window, self._tr("transfer.title"),
                self._tr("transfer.confirm_cut", output=output),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        worker.confirm(approved)

    def _completed(self, output: str) -> None:
        self.controller.window.maintenance_page.status.setText(self._tr("transfer.completed", output=output))
        self.controller.window.maintenance_page.progress.setValue(1000)
        if not self.stopping and self.worker is not None:
            QMessageBox.information(self.controller.window, self._tr("transfer.title"), self._tr("transfer.completed", output=output))

    def _failed(self, error: str) -> None:
        self.controller.window.maintenance_page.status.setText(error)
        if not self.stopping:
            QMessageBox.warning(self.controller.window, self._tr("transfer.title"), error)

    def _finished(self) -> None:
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self.worker is not None:
            self.worker.deleteLater()
            self.worker = None
        self.controller.window.set_data_tools_busy(False)
        self.controller.window.maintenance_page.cancel.setEnabled(False)

    def shutdown(self) -> bool:
        self.stopping = True
        self.disconnect_debug()
        worker = self.worker
        if worker is not None:
            worker.request_cancel()
        # Retain the QThread and its parent if an OS I/O call does not return.
        return (worker is None or worker.wait(5000)) and (self.owner is None or self.owner.wait(5000))

    def request_window_close(self) -> bool:
        self.disconnect_debug()
        if (self.worker is None or not self.worker.isRunning()) and (self.owner is None or not self.owner.isRunning()):
            return True
        self.cancel()
        if self.dialog is not None:
            self.dialog.setLabelText(self._tr("transfer.stopping"))
        return False


__all__ = ["DownloadWorker", "ExportWorker", "FileTransferManager"]
