"""Background file operations and their explicit destructive confirmation."""
from __future__ import annotations

import logging
import hashlib
import json
import queue
import re
import time
from pathlib import Path
from threading import Event, Lock

from config import APP_VERSION
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog
from services.device_export import DeviceExport, ExportCancelled
from services.transfer_progress import TransferProgress, ProgressThrottle
from services.file_service_client import (
    FileServiceClient,
    FileServiceError,
    FileServiceResult,
    validate_download_directory,
)
from services.magnetometer_maintenance import MagMaintenanceDecoder
from services.file_service_jobs import LogExportJob
from services.maintenance_commands import ConsoleCommand, ConsoleCommand_Validate
from ui.diagnostic_labels import Text, MaintenanceError_Format
from transport.file_service_backend import FileServiceSerialTransport
from transport.serial_options import SerialBaud_Parse
from ui.device_export_dialog import DeviceExportDestination_Choose
from services.legacy_firmware_status import LegacyFirmwareStatusClient
from services.legacy_firmware_status import LegacyFirmwareSnapshot
from services.runtime_diagnostics import RuntimeDiagnosticsClient, LegacyDiagnostics_FromSnapshot

_logger = logging.getLogger(__name__)


class _ConsoleTrace:
    """Bounded protocol transcript, without any filesystem/export interface."""
    def __init__(self, transport):
        self.transport=transport;self.lines=[];self.bytes=0;self.deadline=time.monotonic()+60.0

    def exchange(self, command, timeout, cancel):
        if len(self.lines)>=256 or time.monotonic()>=self.deadline:
            raise TimeoutError('Console transaction bound reached; cancel and reconnect')
        line=self.transport.exchange(command,min(timeout,max(.1,self.deadline-time.monotonic())),cancel)
        self.bytes+=len(line)
        if self.bytes>65536:raise OSError('Console transcript exceeded its bound')
        self.lines.append(line)
        return line


def _Console_Execute(transport, command, cancel):
    command=ConsoleCommand_Validate(command,allow_raw=True)
    trace=_ConsoleTrace(transport)
    parts=command.split(' ',2)
    client=None
    try:
        if len(parts)>=2 and parts[0]=='LOGFILE' and parts[1] in {'CAPS','STATUS','ENTER','CANCEL','LIST','META','READ'}:
            client=FileServiceClient(trace,cancel=cancel)
            client.Console_Execute(parts[1],parts[2] if len(parts)>2 else '')
        else:
            trace.exchange(command,2.0,cancel)
        return '\n'.join(trace.lines),''
    except (FileServiceError,ExportCancelled,TimeoutError,ValueError,OSError) as exc:
        if client is not None and isinstance(exc,(ExportCancelled,TimeoutError)):
            FileServiceClient(transport).cancel_remote()
        return '\n'.join(trace.lines),str(exc)


class DownloadWorker(QThread):
    byte_progress = Signal(object)
    destination_validated = Signal(str)
    progress = Signal(object, object, str)
    confirm_delete = Signal(object)
    completed = Signal(str)
    failed = Signal(str)
    catalog = Signal(object)
    catalog_details = Signal(object)
    export_results = Signal(object)

    def __init__(self, port: str, baud: int, destination: Path | None, *, delete_id: int | None = None,
                 transport_factory=FileServiceSerialTransport, close_transport=True, list_only=False, file_ids=None, timeout=300, parent=None) -> None:
        super().__init__(parent)
        self.port, self.baud, self.destination = port, baud, destination
        self.delete_id = delete_id
        self.transport_factory = transport_factory
        self.close_transport = close_transport
        self.list_only = list_only
        self.file_ids, self.timeout = file_ids, timeout
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
        last_progress = None
        trace_progress_at = 0.0
        first_data = False
        def report_progress(value):
            nonlocal last_progress, trace_progress_at, first_data
            trace = getattr(transport,'trace',None)
            if trace is not None and (last_progress is None or value.stage!=last_progress.stage
                    or time.monotonic()-trace_progress_at>=1 or value.received>0 and not first_data):
                trace.event('progress',stage=value.stage,received=value.received,total=value.total,
                            first_file_byte=value.received>0 and not first_data)
                trace_progress_at=time.monotonic()
                first_data = first_data or value.received>0
            last_progress = value
            self.byte_progress.emit(value)
        relay = ProgressThrottle(report_progress)
        try:
            relay(TransferProgress(0,None,'synchronizing'))
            if self.cancel.is_set():
                raise ExportCancelled("Cancelled before opening maintenance transport")
            if self.delete_id is not None:
                raise FileServiceError(FileServiceResult.UNSUPPORTED,'TF file service is read-only; remote deletion is disabled')
            if not self.list_only and self.delete_id is None:
                if self.destination is None:
                    raise ValueError("Select a destination")
                self.destination = validate_download_directory(self.destination)
                self.destination_validated.emit(str(self.destination))
            transport = self.transport_factory(self.port, self.baud)
            client = FileServiceClient(transport, cancel=self.cancel)
            client.negotiate()
            job = LogExportJob(self.destination,file_ids=self.file_ids,list_only=self.list_only,
                maintenance_authorized=True,timeout=self.timeout)
            try:
                def catalog_ready(ids):
                    self.catalog.emit(ids)
                    sizes = getattr(client,'catalog_sizes',{})
                    self.catalog_details.emit([{'id':identifier,'size':sizes.get(identifier)} for identifier in ids])
                report = job.run(client,progress=self.progress.emit,catalog=catalog_ready,
                    byte_progress=relay)
            finally:
                output = job.output
                self.export_results.emit(list(job.files))
            result = (report.output or (f"Listed {len(report.ids)} closed logs" if self.list_only else
                                       "No closed device logs available"))
        except Exception as exc:
            _logger.exception("Maintenance file operation failed")
            error = str(exc)
            pending_progress = relay.pending or last_progress
            if pending_progress is not None:
                error += f'\nLast phase: {pending_progress.stage}; received={pending_progress.received} B; total={pending_progress.total}'
            relay.flush('cancelled' if isinstance(exc,ExportCancelled) else 'failed')
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
                trace = getattr(transport,'trace',None)
                if trace is not None:
                    trace.event('job_failed',error=error[:2048])
                    error += f'\nDiagnostics: {trace.path or trace.error}'
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
    byte_progress = Signal(object)
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
    catalog_details = Signal(object)
    export_results = Signal(object)
    command_result = Signal(str,str,str)
    protocol_capabilities = Signal(object)

    def __init__(self, port, baud, *, transport_factory=FileServiceSerialTransport, parent=None,
                 installation_capture_enabled=False, expected_uart=None):
        super().__init__(parent)
        self.port, self.baud = port, baud
        self.expected_uart = expected_uart
        self.transport_factory = transport_factory
        self.stop = Event()
        self.connected = Event()
        self.job_cancel = Event()
        self.jobs = queue.Queue(maxsize=1)
        self.operation = None
        self.command_active = False
        self._claim_lock = Lock()
        self._claimed = False
        self._idle_active = False
        self._installation_capture_enabled = installation_capture_enabled is True
        self._installation_session = None
        self._installation_poisoned = False
        self._maintenance_initialized = False
        self.unreleased_transport = None
        self.trace_factory = None
        self.trace = None
        self.mag_subscribed = Event()
        self.mag_stream_instance = None
        self.mag_dropped = 0
        self._mag_samples = queue.Queue(maxsize=256)
        self._mag_decoder = MagMaintenanceDecoder()

    def mag_subscribe(self, enabled):
        if enabled:
            for _ in range(256):
                try: self._mag_samples.get_nowait()
                except queue.Empty: break
            self.mag_subscribed.set()
        else:
            self.mag_subscribed.clear()

    def mag_take(self):
        samples = []
        for _ in range(256):
            try: samples.append(self._mag_samples.get_nowait())
            except queue.Empty: break
        return tuple(samples), self.mag_dropped

    def _mag_capture(self, chunk):
        for sample in self._mag_decoder.feed(chunk):
            if self.mag_subscribed.is_set():
                try: self._mag_samples.put_nowait(sample)
                except queue.Full: self.mag_dropped += 1

    def submit(self, destination=None, *, list_only=False, file_ids=None):
        return self._Submit((destination,list_only,file_ids))

    def submit_command(self, text):
        return self._Submit(ConsoleCommand(ConsoleCommand_Validate(text,allow_raw=True)))

    def _Submit(self, request):
        with self._claim_lock:
            if self._installation_poisoned:
                return False
            if not isinstance(request, ConsoleCommand) and self.mag_stream_instance is not None:
                return False
            if not self.connected.is_set() or self.stop.is_set() or self._claimed or self.operation is not None or self.command_active:
                return False
            try:
                self.job_cancel.clear()
                self.jobs.put_nowait(request)
                self._claimed=True
                return True
            except queue.Full:return False

    def _Claim_Release(self):
        with self._claim_lock:self._claimed=False

    def AcquireInstallationSession(self):
        from transport.installation_owner import InstallationOwnerLease
        with self._claim_lock:
            if (not self._installation_capture_enabled or not self.connected.is_set() or not self._maintenance_initialized or self.stop.is_set()
                    or self._claimed or self._idle_active or self.operation is not None or self.command_active
                    or self.mag_stream_instance is not None or self.unreleased_transport is not None
                    or self._installation_poisoned):
                return None
            lease=InstallationOwnerLease()
            try:self.jobs.put_nowait(lease)
            except queue.Full:return None
            self._installation_session=lease;self._claimed=True
            return lease

    def request_cancel(self):
        self.job_cancel.set()
        operation = self.operation
        if operation is not None:
            operation.request_cancel()

    def request_stop(self):
        self.stop.set()
        self.request_cancel()

    def run(self):
        # A failed OS close retains ownership. A later start retries only that
        # release on this thread; it must not open a second transport.
        if self.unreleased_transport is not None:
            detail='Disconnected / transport released'
            try:
                self.unreleased_transport.close()
                self.unreleased_transport=None
            except Exception as exc:
                detail=f'Close failed: {exc}'
                self.failed.emit(detail)
            self.connection_changed.emit(False,detail)
            return
        transport = None
        status_client = None
        detail = "Disconnected"
        runtime_caps={}
        trace = None
        try:
            if self.trace_factory is not None:
                trace = self.trace_factory()
                self.trace = trace
            transport = self.transport_factory(self.port, self.baud)
            transport.expected_uart = self.expected_uart
            transport.baudrate = self.baud
            if trace is not None and hasattr(transport,'trace'):
                transport.trace = trace
            if hasattr(transport, 'receive_observer'):
                transport.receive_observer = self._mag_capture
            if self.stop.is_set():
                return
            self.connected.set()
            self.connection_changed.emit(True, f"Port open: {self.port}@{self.baud}")
            try:
                status_client = FileServiceClient(transport, cancel=self.stop)
                caps = status_client.negotiate()
                runtime_caps=dict(caps)
                self.protocol_capabilities.emit(dict(runtime_caps))
                safe_files = caps.get("maintenance_required") == "1" and caps.get("status_version") == "1"
                synchronization = getattr(transport, "startup_diagnostics", {})
                link_note = (f" · startup probe quarantined ({synchronization['quarantined_bytes']} B); fresh CAPS accepted"
                             if synchronization.get("performed") else "")
                self.service_status.emit(safe_files, f"{self.port}@{self.baud} · LOGFILE v1 · explicit maintenance {'supported' if safe_files else 'unsupported'} · device/boot identity unknown{link_note}")
            except FileServiceError as exc:
                unsupported = exc.result == FileServiceResult.UNSUPPORTED
                availability = "unsupported" if unsupported else "unavailable"
                self.service_status.emit(False, f"{self.port}@{self.baud} · LOGFILE {availability}: {exc}")
                status_client = (LegacyFirmwareStatusClient(transport, cancel=self.stop)
                                 if unsupported else None)
            except TimeoutError as exc:
                if getattr(transport,'requires_reconnect',False):
                    raise OSError(f'{exc}; reconnect required') from exc
                self.service_status.emit(False, f"{self.port}@{self.baud} · LOGFILE unavailable: negotiation response timeout; serial port remains open")
                status_client = LegacyFirmwareStatusClient(transport, cancel=self.stop)
            if isinstance(status_client, FileServiceClient) and caps.get("status_version") != "1":
                status_client = LegacyFirmwareStatusClient(transport, cancel=self.stop)
            next_status = 0.0
            diagnostic_client = RuntimeDiagnosticsClient(transport, self.stop)
            with self._claim_lock:self._maintenance_initialized=True
            while not self.stop.is_set():
                if trace is not None:trace.Pending_Flush()
                try:
                    request = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    with self._claim_lock:
                        if self._installation_session is not None:
                            continue
                        self._idle_active=True
                    try:
                        if time.monotonic() >= next_status:
                            next_status = time.monotonic() + 1.0
                            try:
                                if status_client is None:
                                    status_client = FileServiceClient(transport, cancel=self.stop)
                                snapshot = status_client.status()
                                self.firmware_status.emit(snapshot, "")
                                if isinstance(snapshot,LegacyFirmwareSnapshot):
                                    runtime_caps['legacy_response']=True
                                    self.protocol_capabilities.emit(dict(runtime_caps))
                                if isinstance(snapshot, LegacyFirmwareSnapshot) and diagnostic_client is None:
                                    self.diagnostic_status.emit(LegacyDiagnostics_FromSnapshot(snapshot), "Legacy 0.0 fields; completion instrumentation unavailable")
                            except (FileServiceError, TimeoutError) as exc:
                                self.firmware_status.emit(None, str(exc))
                        if getattr(transport,'requires_reconnect',False):
                            raise OSError('Maintenance status response incomplete; reconnect required')
                        if diagnostic_client is not None:
                            try:
                                entries = diagnostic_client.step()
                                declared=getattr(diagnostic_client,'caps',None)
                                if declared and declared.get('maintenance')!=runtime_caps.get('maintenance'):
                                    runtime_caps.update(maintenance=declared['maintenance'],compatible=declared.get('compatible',''))
                                    self.protocol_capabilities.emit(dict(runtime_caps))
                                if entries is not None:
                                    self.diagnostic_status.emit(entries, "Maintenance 0.1; independent RAM observations")
                            except (FileServiceError, TimeoutError) as exc:
                                diagnostic_client = None
                                self.diagnostic_status.emit(None, str(exc))
                        if getattr(transport,'requires_reconnect',False):
                            raise OSError('Maintenance diagnostic response incomplete; reconnect required')
                        transport.check_alive()
                    finally:
                        with self._claim_lock:self._idle_active=False
                    continue
                if self.stop.is_set():
                    break
                from transport.installation_owner import InstallationOwnerLease
                if isinstance(request,InstallationOwnerLease):
                    try:
                        request.Service(transport,self.stop)
                    finally:
                        with self._claim_lock:
                            self._installation_poisoned=bool(request.service_error or getattr(transport,'requires_reconnect',False))
                            self._installation_session=request if self._installation_poisoned else None
                            self._claimed=False
                        self.jobs.task_done()
                        if not self._installation_poisoned:
                            request.OwnerDetached()
                    if self._installation_poisoned:
                        detail='Installation exchange unconfirmed; reconnect required'
                        break
                    continue
                if isinstance(request,ConsoleCommand):
                    self.command_active=True
                    try:
                        # A live 20Hz stream cannot satisfy the startup quiet probe.
                        # Keep this already synchronized, correlated connection.
                        if self.mag_stream_instance is None:
                            transport.prepare_job()
                        start = re.fullmatch(r'MAG ([0-9]{1,3}) STREAM START', request.text)
                        if start:
                            self.mag_stream_instance = int(start[1])
                        response,error=_Console_Execute(transport,request.text,self.job_cancel)
                        if (request.text.endswith(' STREAM STOP') and not error
                                and 'state=STOPPED' in response.split()):
                            self.mag_stream_instance = None
                        self.command_result.emit(request.text,response,error)
                    except (ExportCancelled,TimeoutError,ValueError,OSError) as exc:
                        self.command_result.emit(request.text,'',str(exc))
                    finally:
                        self.command_active=False
                        self.jobs.task_done()
                        self._Claim_Release()
                        self.job_finished.emit()
                        if diagnostic_client is not None:
                            diagnostic_client.entries,diagnostic_client.cursor=[],0
                    if getattr(transport,'requires_reconnect',False):
                        detail='Incomplete maintenance exchange; reconnect required'
                        break
                    continue
                destination,list_only,file_ids=request
                transport.prepare_job()
                if diagnostic_client is not None:
                    diagnostic_client.entries, diagnostic_client.cursor = [], 0
                    diagnostic_client.next_cycle = time.monotonic() + 1.0
                self.diagnostic_status.emit(None, "Polling paused during file transfer; no real-time claim")
                operation = DownloadWorker(self.port, self.baud, destination,
                    transport_factory=lambda *_: transport, close_transport=False, list_only=list_only, file_ids=file_ids)
                self.operation = operation
                operation.progress.connect(self.progress, Qt.DirectConnection)
                operation.byte_progress.connect(self.byte_progress, Qt.DirectConnection)
                operation.destination_validated.connect(self.destination_validated, Qt.DirectConnection)
                operation.catalog.connect(self.catalog, Qt.DirectConnection)
                operation.catalog_details.connect(self.catalog_details, Qt.DirectConnection)
                operation.export_results.connect(self.export_results, Qt.DirectConnection)
                operation.completed.connect(self.completed, Qt.DirectConnection)
                operation.failed.connect(self.failed, Qt.DirectConnection)
                if self.stop.is_set() or self.job_cancel.is_set():
                    operation.request_cancel()
                operation.run()
                self.operation = None
                self.jobs.task_done()
                self._Claim_Release()
                self.job_finished.emit()
                if isinstance(operation.operation_error, OSError) or getattr(transport,'requires_reconnect',False):
                    detail = str(operation.operation_error or 'Incomplete maintenance exchange; reconnect required')
                    break
        except ExportCancelled:
            # A disconnect can arrive between the idle-loop stop check and
            # STATUS exchange. It is expected cancellation, not a modal error.
            detail = "Disconnected / status invalidated"
        except Exception as exc:
            _logger.exception("Maintenance owner failed")
            detail = str(exc)
            if trace is not None:
                trace.event('owner_failed',error=str(exc)[:2048])
                detail += f'\nDiagnostics: {trace.path or trace.error}'
            self.failed.emit(detail)
        finally:
            self.connected.clear()
            with self._claim_lock:self._maintenance_initialized=False
            self._Claim_Release()
            self.operation = None
            self.mag_subscribed.clear()
            if transport is not None:
                if self.mag_stream_instance is not None:
                    try:
                        reply = transport.exchange(f'MAG {self.mag_stream_instance} STREAM STOP', .5, Event())
                        if 'state=STOPPED' not in reply.split():
                            detail += '; magnetic stream STOP unconfirmed'
                    except Exception as exc:
                        detail += f'; magnetic stream STOP unconfirmed: {exc}'
                try:
                    transport.close()
                except Exception as exc:
                    _logger.exception("Maintenance owner close failed")
                    detail = f"Close failed: {exc}"
                    if trace is not None:trace.event('owner_failed',error=detail[:2048])
                    self.unreleased_transport=transport
                    self.failed.emit(detail)
            self.connection_changed.emit(False, detail)
            if self._installation_session is not None:
                self._installation_session.service_error=OSError(detail)
                self._installation_session.OwnerDetached()
                self._installation_session=None
            if trace is not None:
                trace.close(detail+'; transport_released='+str(self.unreleased_transport is None))


class ExportWorker(QThread):
    byte_progress = Signal(object)
    progress = Signal(object, object, str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, exporter: DeviceExport, cut: bool, parent=None) -> None:
        super().__init__(parent)
        self.exporter = exporter
        self.cut = cut

    def request_cancel(self) -> None:
        self.exporter.cancel.set()

    def run(self) -> None:
        relay = ProgressThrottle(self.byte_progress.emit)
        try:
            output = self.exporter.copy(cut=self.cut, progress=self.progress.emit,
                byte_progress=relay)
            self.completed.emit(str(output))
        except ExportCancelled:
            relay.flush('cancelled')
            self.failed.emit("Cancelled; any completed destination files remain. Source files retained.")
        except Exception as exc:
            relay.flush('failed')
            _logger.exception("Device export failed")
            self.failed.emit(str(exc))


class MtpExportWorker(QThread):
    byte_progress = Signal(object)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, sources, managed_root, staging_root, is_active, title, parent=None, *, backend=None):
        super().__init__(parent)
        from services.windows_mtp import WindowsMtp
        self.backend = backend or WindowsMtp()
        self.sources, self.managed_root, self.staging_root = sources, managed_root, staging_root
        self.is_active, self.title = is_active, title
        self.cancel = Event()

    def request_cancel(self):
        self.cancel.set()

    def run(self):
        from services.windows_mtp import MtpOperationResult
        relay = ProgressThrottle(self.byte_progress.emit)
        try:
            reply = self.backend.choose(self.title, self.cancel)
            if reply.result is not MtpOperationResult.Selected:
                raise ExportCancelled(reply.detail) if reply.result is MtpOperationResult.Cancelled else OSError(reply.detail)
            self.staging_root.mkdir(parents=True, exist_ok=True)
            exporter = DeviceExport(self.sources, self.staging_root, managed_root=self.managed_root,
                                    is_active=self.is_active, app_version=APP_VERSION, cancel=self.cancel)
            package = exporter.copy(cut=False, byte_progress=relay)
            relay(TransferProgress(0, None, 'verifying', detail='MTP copy / SHA-256 readback'))
            reply = self.backend.copy(package, reply.destination, self.cancel)
            if reply.result is not MtpOperationResult.Verified:
                raise OSError(reply.detail)
            total = sum(f.size for f in exporter.files)
            relay(TransferProgress(total, total, 'complete'))
            self.completed.emit(reply.destination + '\n' + reply.detail)
        except ExportCancelled as exc:
            self.cancel.set()
            relay(TransferProgress(0, None, 'cancelled'))
            self.failed.emit(str(exc) or 'Cancelled; source files retained')
        except Exception as exc:
            relay.flush('failed')
            self.failed.emit(str(exc))


class FileTransferManager(QObject):
    def __init__(self, controller) -> None:
        super().__init__(controller)
        self.controller = controller
        self.worker: QThread | None = None
        self.dialog: QProgressDialog | None = None
        self.stopping = False
        self.owner: MaintenanceOwner | None = None
        controller.window.maintenance_owner_status = lambda: self.owner is not None
        self.job_busy = False
        self.transport_factory = FileServiceSerialTransport
        self.mag_active = False
        from transport.magnetometer_transport import MaintenanceMagTransport
        from ui.magnetometer_dialog import MagCalibrationDialog
        self.mag_transport = MaintenanceMagTransport(self)
        self.mag_dialog = MagCalibrationDialog(self.mag_transport, controller.window.i18n, controller.window)
        controller.window.on_mag_calibration = self.open_magnetometer_calibration
        controller.window.on_mag_retranslate = self.mag_dialog.retranslate
        from ui.log_export_dialog import LogExportDialog
        self.export_dialog=LogExportDialog(controller.window.i18n,controller.window)
        self.catalog_records=[]
        self._pending_destination=None
        self._verified_files=[]
        self._byte_last = None
        self._error_notice = None
        self._local_rejection_text = ''
        self._byte_phase_at = time.monotonic()
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._byte_refresh)
        controller.window.maintenance_page.export_dialog=self.export_dialog
        self.export_dialog.refresh_requested.connect(lambda:self._submit_download(None,list_only=True))
        self.export_dialog.download_requested.connect(lambda destination,ids:self._submit_download(Path(destination),file_ids=ids))
        self.export_dialog.cancel_requested.connect(self.cancel)
        controller.window.maintenance_page.console.send_requested.connect(self.send_command)
        controller.window.maintenance_page.console.declaration_changed.connect(self._Declaration_Refresh)
        controller.window.maintenance_page.cancel.clicked.connect(self.cancel)
        controller.window.maintenance_page.btn_selected_download.clicked.connect(self.SelectedDownload_Choose)
        controller.window.maintenance_page.btn_destination.clicked.connect(self.choose_default_directory)
        from services.windows_mtp import WindowsMtp
        self.mtp_backend_factory = WindowsMtp

    @property
    def busy(self) -> bool:
        return self.worker is not None or self.job_busy or self.mag_active

    def _tr(self, key: str, **params) -> str:
        return self.controller._tr(key, **params)

    def _available(self, *, maintenance=False, magnetic=False) -> bool:
        c = self.controller
        occupied = self.worker is not None or self.job_busy or (self.mag_active and not magnetic)
        return not (occupied or c.state.mission_started or c.state.start_transaction_pending() or (not maintenance and (c.logger.session_active
                    or c.worker is not None or c.protocol_worker is not None))
                    or c.processing_thread is not None or c.simulation_thread is not None
                    or c.data_migration_thread is not None)

    def open_magnetometer_calibration(self):
        self.mag_dialog.open_session()
        self.mag_dialog.raise_()

    def mag_acquire(self):
        if self.mag_active or not self._available(maintenance=True):
            return False
        if self.owner is None or not self.owner.connected.is_set() or self.owner.stop.is_set():
            return False
        self.mag_active = True
        self.controller.window.set_data_tools_busy(True)
        self.controller.window.maintenance_page.console.set_connection(True, False)
        self.export_dialog.set_busy(True, 'calibration')
        return True

    def mag_release(self):
        self.mag_active = False
        self.controller.window.set_data_tools_busy(self.busy)
        self.controller.window.maintenance_page.console.set_connection(
            self.controller.window._debug_connected, self.worker is not None or self.job_busy)
        self.export_dialog.set_busy(self.worker is not None or self.job_busy)

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
        expected_uart = c.window.maintenance_page.console.expected_uart
        if expected_uart is not None and (not isinstance(expected_uart, dict) or baud != expected_uart.get('baudrate')):
            self._failed(Text(c.window.i18n, '所选波特率与已导入描述不一致，请核对维护 UART 参数。',
                              'Selected baud differs from imported descriptor; check maintenance UART parameters.'))
            return
        owner = MaintenanceOwner(port, baud, transport_factory=self.transport_factory, parent=self, expected_uart=expected_uart)
        from services.maintenance_trace import MaintenanceTrace
        owner.trace_factory = lambda: MaintenanceTrace(c.log_dir.parent/'diagnostics',port,baud)
        self.owner = owner
        self._Declaration_Refresh()
        owner.connection_changed.connect(self._connection_changed, Qt.QueuedConnection)
        owner.service_status.connect(self._service_status, Qt.QueuedConnection)
        owner.protocol_capabilities.connect(self._protocol_capabilities,Qt.QueuedConnection)
        owner.firmware_status.connect(self._firmware_status, Qt.QueuedConnection)
        owner.diagnostic_status.connect(self._diagnostic_status, Qt.QueuedConnection)
        owner.destination_validated.connect(self._destination_validated, Qt.QueuedConnection)
        if hasattr(owner,'byte_progress'):owner.byte_progress.connect(self._byte_progress,Qt.QueuedConnection)
        else:owner.progress.connect(self._progress, Qt.QueuedConnection)
        owner.catalog.connect(c.window.maintenance_page.show_catalog, Qt.QueuedConnection)
        owner.catalog_details.connect(self._catalog_details,Qt.QueuedConnection)
        owner.export_results.connect(self._export_results,Qt.QueuedConnection)
        owner.command_result.connect(self._command_result,Qt.QueuedConnection)
        owner.completed.connect(self._completed, Qt.QueuedConnection)
        owner.failed.connect(self._failed, Qt.QueuedConnection)
        owner.job_finished.connect(self._job_finished, Qt.QueuedConnection)
        owner.finished.connect(self._owner_finished)
        c.window.set_debug_status("maintenance.connecting")
        c.window.debug_port_combo.setEnabled(False)
        c.window.debug_baud_combo.setEnabled(False)
        c.window.btn_debug_connect.setEnabled(False)
        owner.start()

    def disconnect_debug(self):
        if self.owner is not None:
            self.controller.window.maintenance_page.set_firmware_status(None, "Disconnected / invalidated")
            self.controller.window.maintenance_page.set_diagnostics(None, "Disconnected / invalidated")
            self.controller.window.set_debug_status("maintenance.stopping")
            self.owner.request_stop()
            if self.owner.unreleased_transport is not None and not self.owner.isRunning():
                self.owner.start()

    def _connection_changed(self, connected, detail):
        if not self._CurrentOwnerSignal():return
        window = self.controller.window
        window._debug_connected = bool(connected)
        if self.mag_transport.session_active or self.mag_dialog.isVisible():
            self.mag_transport.link_changed(connected, detail)
        window.maintenance_page.console.set_connection(connected,self.busy)
        self.export_dialog.set_connection(connected,window._debug_service_supported)
        self._Declaration_Refresh()
        window.set_debug_status("maintenance.serial_open" if connected else "maintenance.disconnected", detail)
        if not connected:
            window._debug_service_supported = False
            window.maintenance_page.catalog.clear()
            self.catalog_records=[]
            window.maintenance_page.service_status.setText("LOGFILE: disconnected / negotiation invalidated")
            window.maintenance_page.set_firmware_status(None, "Disconnected / invalidated")
            window.maintenance_page.set_diagnostics(None, "Disconnected / invalidated")
        window._render_data_tool_buttons()

    def _service_status(self, supported, detail):
        if not self._CurrentOwnerSignal():return
        window = self.controller.window
        window._debug_service_supported = bool(supported)
        self.export_dialog.set_connection(window._debug_connected,supported)
        window.maintenance_page.service_status.setText(detail)
        window._render_data_tool_buttons()

    def _firmware_status(self, snapshot, detail):
        if not self._CurrentOwnerSignal():return
        if self.owner is not None and not self.owner.stop.is_set():
            self.controller.window.maintenance_page.set_firmware_status(snapshot, detail)
            if self.controller.window._debug_connected:
                self.controller.window.set_debug_status(
                    "maintenance.firmware_reply" if snapshot is not None else "maintenance.status_unavailable",
                    f"{self.owner.port}@{self.owner.baud}\n{detail}")

    def _diagnostic_status(self, entries, detail):
        if not self._CurrentOwnerSignal():return
        if self.owner is not None and not self.owner.stop.is_set():
            self.controller.window.maintenance_page.set_diagnostics(entries, detail)

    def _destination_validated(self, destination):
        self._pending_destination=destination

    def _Directory_Remember(self,destination):
        page=self.controller.window.maintenance_page
        settings = self.controller.window.i18n.settings
        settings.setValue(page.TF_DIRECTORY_KEY, destination)
        settings.sync()
        page.set_destination(destination)

    def choose_default_directory(self):
        if self.busy:return
        page=self.controller.window.maintenance_page
        selected=QFileDialog.getExistingDirectory(self.controller.window,
            Text(self.controller.window.i18n,'默认TF导出目录','Default TF export directory'),page.destination_path.text())
        if not selected:return
        try:destination=validate_download_directory(Path(selected))
        except (ValueError,OSError) as exc:
            self._failed(str(exc));return
        self._Directory_Remember(str(destination))
        self.export_dialog.path.setText(str(destination))

    def _CurrentOwnerSignal(self):
        sender=self.sender()
        return sender is None or sender is self.owner

    def _protocol_capabilities(self,caps):
        if self._CurrentOwnerSignal() and self.owner is not None and not self.owner.stop.is_set():
            self.controller.window.maintenance_page.console.set_runtime_capabilities(caps)

    def _export_results(self,files):
        if not self._CurrentOwnerSignal():return
        self._verified_files=list(files)
        self.export_dialog.show_results(files)

    def _owner_finished(self):
        if not self._CurrentOwnerSignal():return
        self._job_finished()
        if self.owner is not None and self.owner.unreleased_transport is not None:
            self.controller.window._DebugStatus_Render()
            return
        if self.owner is not None:
            self.owner.deleteLater()
            self.owner = None
        self._Declaration_Refresh()
        window = self.controller.window
        window.debug_port_combo.setEnabled(True)
        window.debug_baud_combo.setEnabled(True)
        window.btn_debug_connect.setEnabled(True)
        window._DebugStatus_Render()

    def _job_finished(self):
        if not self._CurrentOwnerSignal():return
        self._progress_timer.stop()
        self.job_busy = False
        self._pending_destination=None
        self._verified_files=[]
        self.controller.window.set_data_tools_busy(self.worker is not None or self.mag_active)
        self.controller.window.maintenance_page.cancel.setEnabled(self.worker is not None)
        self.export_dialog.set_busy(self.mag_active)
        self.controller.window.maintenance_page.console.set_connection(self.controller.window._debug_connected,False)
        self.mag_transport.pump()

    def _catalog_details(self,records):
        if not self._CurrentOwnerSignal():return
        self.catalog_records=list(records)
        self.export_dialog.set_catalog(self.catalog_records)

    def send_command(self,text, *, magnetic=False):
        if magnetic and not self.mag_active:
            return False
        if not magnetic and self.mag_active:
            from services.maintenance_commands import ConsoleCommand_IsKnown
            words = text.upper().split()
            if not words: return False
            safe_file = words[:2] in (['LOGFILE', 'CAPS'], ['LOGFILE', 'STATUS'])
            if not ConsoleCommand_IsKnown(text) or words[0] == 'MAG' or words[0] == 'LOGFILE' and not safe_file:
                self.controller.window.maintenance_page.console.show_response(text, '',
                    Text(self.controller.window.i18n, '磁校准期间仅允许其他维护查询。', 'Only other maintenance queries are allowed during magnetic calibration.'))
                return False
        if not self._available(maintenance=True, magnetic=self.mag_active) or self.owner is None:
            message=Text(self.controller.window.i18n,'未发送：维护串口未连接或当前任务/传输繁忙。','Not sent: maintenance port disconnected or current task/transfer busy.')
            self.controller.window.maintenance_page.console.show_response(text,'',message)
            return False
        try:
            accepted=self.owner.submit_command(text)
        except ValueError as exc:
            self.controller.window.maintenance_page.console.show_response(text,'',str(exc))
            return False
        if accepted:
            self.job_busy=True
            self.controller.window.set_data_tools_busy(True)
            self.controller.window.maintenance_page.console.set_connection(True,True)
            self.controller.window.maintenance_page.cancel.setEnabled(True)
        else:
            self.controller.window.maintenance_page.console.show_response(text,'',Text(self.controller.window.i18n,'未发送：串口忙或已断开。','Not sent: serial owner busy or disconnected.'))
        return accepted

    def _command_result(self,command,response,error):
        if not self._CurrentOwnerSignal():return
        self.controller.window.maintenance_page.console.show_response(command,response,error)
        self.mag_transport.accept_result(command,response,error)

    def cancel(self):
        if self._byte_last is not None:
            from dataclasses import replace
            self._byte_progress(replace(self._byte_last,stage='cancelling'))
        if self.worker is not None:
            self.worker.request_cancel()
        if self.owner is not None:
            self.owner.request_cancel()

    def choose_export(self, cut: bool) -> None:
        c = self.controller
        if cut:
            self._failed(self._tr('transfer.copy_only'))
            return
        if not self._available():
            QMessageBox.information(c.window, self._tr("transfer.title"), self._tr("transfer.busy"))
            return
        sources, _ = QFileDialog.getOpenFileNames(c.window,
            self._tr("transfer.sources"), str(c.log_dir),
            "Logs (*.jsonl *.sslog);;All files (*)")
        if not sources:
            return
        selection = DeviceExportDestination_Choose(c.window.i18n, sources, c.window)
        if selection is None:
            return
        if not self._available():
            self._failed(self._tr("transfer.busy"))
            return
        kind, destination = selection
        if kind == "mtp":
            self._start_mtp_export(sources)
            return
        if kind != "directory" or not destination:
            return
        exporter = DeviceExport([Path(p) for p in sources], Path(destination), managed_root=c.log_dir,
                                is_active=lambda p: c.logger.session_active and c.logger.path == p,
                                app_version=APP_VERSION)
        worker = ExportWorker(exporter, cut, self)
        self._start(worker)

    def _start_mtp_export(self, sources):
        c = self.controller
        if not sources or not self._available():
            return
        worker = MtpExportWorker([Path(p) for p in sources], c.log_dir,
            c.log_dir.parent / 'exports' / 'mtp',
            lambda p: c.logger.session_active and c.logger.path == p,
            self._tr('transfer.mtp_destination'), self, backend=self.mtp_backend_factory())
        self._start(worker)

    def SelectedDownload_Choose(self):
        item=self.controller.window.maintenance_page.catalog.currentItem()
        identifier=item.data(Qt.UserRole) if item is not None else None
        if type(identifier) is not int:
            return
        self.choose_download(file_ids=(identifier,))

    def choose_download(self, delete: bool = False, *, file_ids=None) -> None:
        c = self.controller
        if delete:
            self._failed(self._tr("transfer.download_delete"))
            return
        if not self._available(maintenance=True) or self.owner is None or not self.owner.connected.is_set():
            QMessageBox.information(c.window, self._tr("transfer.title"), self._tr("transfer.busy"))
            return
        page = c.window.maintenance_page
        self._Declaration_Refresh()
        if self.export_dialog.isVisible():
            if file_ids is not None:
                self.export_dialog.set_catalog(self.catalog_records,selected=file_ids)
            self.export_dialog.raise_()
            self.export_dialog.activateWindow()
            return
        self.export_dialog.retranslate()
        self.export_dialog.set_connection(c.window._debug_connected,c.window._debug_service_supported)
        self.export_dialog.path.setText(page.destination_path.text())
        if self.export_dialog.files.topLevelItemCount()==0 or file_ids is not None:
            self.export_dialog.set_catalog(self.catalog_records,selected=file_ids)
        self.export_dialog.show()
        self.export_dialog.raise_()

    def refresh_device_logs(self):
        self.choose_download()

    def _Declaration_GetReason(self):
        console=self.controller.window.maintenance_page.console
        if console.declaration_loading:return 'declaration_loading'
        if self.owner is not None and console.expected_uart != getattr(self.owner,'expected_uart',None):
            return 'declaration_changed'
        return ''

    def _Declaration_Refresh(self):
        previous=self.export_dialog.verification_state
        reason=self._Declaration_GetReason()
        i18n=self.controller.window.i18n
        if reason=='declaration_loading':
            note=Text(i18n,'描述重载中，等待核验','Descriptor reloading; verification pending')
            detail=Text(i18n,'描述重载中：等待导入完成后再读取目录。当前不会发送目录或下载请求。',
                        'Descriptor reloading: wait for import to finish. Catalog/download requests will not be sent.')
        elif reason:
            note=Text(i18n,'维护描述已改变，需要重新连接核验','Maintenance declaration changed; reconnect to verify')
            detail=Text(i18n,'待重新核验：维护描述已改变。请手动断开维护串口并重新连接，再读取目录；当前不会发送目录或下载请求。',
                        'Verification required: maintenance declaration changed. Manually disconnect/reconnect the maintenance port, then reread the catalog. Catalog/download requests will not be sent.')
        else:note=detail=''
        self.export_dialog.Verification_SetState(reason,detail)
        self.controller.window.maintenance_page.console.Verification_SetNote(note)
        if previous != reason and self._local_rejection_text and not self.busy:
            replacement=detail or Text(i18n,'维护描述状态已更新，可重新读取目录。','Maintenance declaration updated; retry reading the catalog.')
            if self.owner is None:
                replacement=Text(i18n,'维护串口未连接，请连接后再读取目录。','Maintenance port disconnected; connect before reading the catalog.')
            for label in (self.export_dialog.status,self.controller.window.maintenance_page.status):
                if label.text()==self._local_rejection_text:label.setText(replacement)
            self._local_rejection_text=replacement
        return reason,detail

    def _Request_RejectLocally(self,reason,error,operation):
        trace=getattr(self.owner,'trace',None)
        def identity(value):
            return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')).hexdigest()
        recorded=bool(trace is not None and trace.Event_Post('local_rejected',reason=reason,operation=operation,
            request_sent=False,expected_uart_sha256=identity(getattr(self.owner,'expected_uart',None)),
            current_uart_sha256=identity(self.controller.window.maintenance_page.console.expected_uart),error=error[:1024]))
        detail=Text(self.controller.window.i18n,'请求尚未发送：','Request not sent: ')+error
        if not recorded:
            detail+=Text(self.controller.window.i18n,'\n本次拒绝未能写入连接诊断。','\nThis refusal could not be queued in the connection diagnostics.')
        # A refused new request must not mark an earlier/active transfer failed.
        if not self.busy:self._progress_timer.stop()
        self._local_rejection_text=detail
        self.export_dialog.status.setText(detail)
        self.controller.window.maintenance_page.status.setText(detail)
        if not self.stopping:self._ErrorNotice_Show(detail)

    def _submit_download(self, destination, *, list_only=False, file_ids=None):
        operation='list' if list_only else 'download'
        reason,detail=self._Declaration_Refresh()
        if reason:
            self._Request_RejectLocally(reason,detail,operation)
            return
        if not self._available(maintenance=True):
            self._Request_RejectLocally('busy',self._tr("transfer.busy"),operation)
            return
        options={'list_only':list_only}
        if file_ids is not None:options['file_ids']=file_ids
        if not self.controller.window._debug_service_supported or self.owner is None or not self.owner.submit(destination, **options):
            self._Request_RejectLocally('connection_unavailable',self._tr("maintenance.connect_first"),operation)
            return
        self.job_busy = True
        self._local_rejection_text=''
        self._pending_destination=None
        self._verified_files=[]
        self.controller.window.set_data_tools_busy(True)
        self.controller.window.maintenance_page.cancel.setEnabled(True)
        self.controller.window.maintenance_page.status.setText(self._tr("transfer.working"))
        self.export_dialog.set_busy(True,'list' if list_only else 'download')
        self.export_dialog.status.setText(self._tr('transfer.working'))
        self._byte_last = None
        self.controller.window.maintenance_page.console.set_connection(True,True)

    def _start(self, worker: QThread) -> None:
        self._byte_last = None
        self.worker = worker
        self.controller.window.maintenance_page.cancel.setEnabled(True)
        self.controller.window.set_data_tools_busy(True)
        self.dialog = QProgressDialog(self._tr("transfer.working"), self._tr("transfer.cancel"), 0, 0, self.controller.window)
        self.dialog.setWindowTitle(self._tr("transfer.title"))
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.canceled.connect(worker.request_cancel)
        if hasattr(worker,'byte_progress'):worker.byte_progress.connect(self._byte_progress,Qt.QueuedConnection)
        else:worker.progress.connect(self._progress, Qt.QueuedConnection)
        worker.completed.connect(self._completed, Qt.QueuedConnection)
        worker.failed.connect(self._failed, Qt.QueuedConnection)
        worker.finished.connect(self._finished)
        self.dialog.show()
        worker.start()

    def _byte_progress(self, snapshot):
        sender = self.sender()
        if sender is not None and (sender not in (self.owner,self.worker)
                or sender is self.owner and not self.job_busy):return
        if self._byte_last is None or (snapshot.stage,snapshot.index)!=(self._byte_last.stage,self._byte_last.index):
            self._byte_phase_at = time.monotonic()
        self._byte_last = snapshot
        if snapshot.stage in {'complete','failed','cancelled'}:self._progress_timer.stop()
        else:self._progress_timer.start()
        self._byte_refresh()

    def _byte_refresh(self):
        from ui.log_export_dialog import TransferProgress_Render
        snapshot = self._byte_last
        if snapshot is None:return
        self.export_dialog.show_byte_progress(snapshot)
        page = self.controller.window.maintenance_page
        detail = TransferProgress_Render(page.progress,snapshot,self.controller.window.i18n)
        if snapshot.stage not in {'complete','failed','cancelled'}:
            elapsed = max(0,time.monotonic()-self._byte_phase_at)
            detail += Text(self.controller.window.i18n,f' · 本阶段 {elapsed:.1f}s',f' · stage elapsed {elapsed:.1f}s')
        self.export_dialog.status.setText(detail)
        page.status.setText(detail)
        if self.dialog is not None and not self.stopping:
            self.dialog.setRange(page.progress.minimum(),page.progress.maximum())
            self.dialog.setValue(page.progress.value())
            self.dialog.setLabelText(detail)

    def _progress(self, done: int, total: int, detail: str) -> None:
        self.export_dialog.show_progress(done,total,detail)
        self.controller.window.maintenance_page.progress.setValue(min(1000, max(0, int(done * 1000 // max(1, total)))))
        self.controller.window.maintenance_page.status.setText(detail)
        if self.dialog is not None and not self.stopping:
            self.dialog.setRange(0, 1000)
            self.dialog.setValue(min(1000, max(0, int(done * 1000 // max(1, total)))))
            self.dialog.setLabelText(detail)

    def _completed(self, output: str) -> None:
        if self.sender() is not None and self.sender() not in (self.owner,self.worker):return
        self._progress_timer.stop()
        if self.export_dialog.busy and self.export_dialog.operation=='list':
            self._byte_last = None
            detail=Text(self.controller.window.i18n,f'目录读取完成，共{len(self.catalog_records)}项；尚未导出文件。',f'Catalog read: {len(self.catalog_records)} entries; no files exported.')
            self.export_dialog.status.setText(detail)
            self.controller.window.maintenance_page.status.setText(detail)
            for bar in (self.export_dialog.progress,self.controller.window.maintenance_page.progress):
                bar.setRange(0,1000);bar.setValue(0);bar.setFormat('%p%')
            return
        if self._pending_destination and self._verified_files and self.export_dialog.operation=='download':
            self._Directory_Remember(self._pending_destination)
        if self._byte_last is not None:
            from dataclasses import replace
            self._byte_progress(replace(self._byte_last,stage='complete'))
        self.export_dialog.status.setText(self._tr("transfer.completed", output=output))
        self.controller.window.maintenance_page.status.setText(self._tr("transfer.completed", output=output))
        self.controller.window.maintenance_page.progress.setValue(1000)
        if not self.stopping and self.worker is not None:
            QMessageBox.information(self.controller.window, self._tr("transfer.title"), self._tr("transfer.completed", output=output))

    def _failed(self, error: str) -> None:
        if self.sender() is not None and self.sender() not in (self.owner,self.worker):return
        self._progress_timer.stop()
        error = MaintenanceError_Format(error,self.controller.window.i18n)
        if isinstance(self.worker, MtpExportWorker):
            error = self._tr('transfer.mtp_failed', detail=error)
        if self._byte_last is not None:
            from dataclasses import replace
            cancelled = bool(self._byte_last.stage=='cancelled' or self.owner and self.owner.job_cancel.is_set())
            self._byte_progress(replace(self._byte_last,stage='cancelled' if cancelled else 'failed'))
        self.export_dialog.status.setText(error)
        self.controller.window.maintenance_page.status.setText(error)
        expected_cancel=bool(self.owner and self.owner.job_cancel.is_set() or
                             isinstance(self.worker, MtpExportWorker) and self.worker.cancel.is_set())
        if not self.stopping and not self.export_dialog.isVisible() and not expected_cancel:
            self._ErrorNotice_Show(error)

    def _ErrorNotice_Show(self, error):
        # One nonblocking notice avoids nested modal loops and stacked failures.
        notice = self._error_notice
        if notice is None:
            notice = QMessageBox(QMessageBox.Warning,self._tr('transfer.title'),'',QMessageBox.Ok,self.controller.window)
            notice.setTextFormat(Qt.PlainText)
            notice.setWindowModality(Qt.WindowModal)
            self._error_notice = notice
        text = notice.text()+'\n\n'+error if notice.isVisible() and error not in notice.text() else error
        if len(text)>8192:
            text = text[:2048]+'\n…\n'+text[-6144:]
        notice.setText(text)
        notice.button(QMessageBox.Ok).setText(Text(self.controller.window.i18n,'确定','OK'))
        notice.open()

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
        self.mag_dialog.request_close()
        self.disconnect_debug()
        worker = self.worker
        if worker is not None:
            worker.request_cancel()
        # Retain the QThread and its parent if an OS I/O call does not return.
        return (worker is None or worker.wait(5000)) and (self.owner is None or
            self.owner.wait(5000) and self.owner.unreleased_transport is None) and self.mag_dialog.shutdown()

    def request_window_close(self) -> bool:
        self.export_dialog.close()
        mag_done = self.mag_dialog.request_close()
        self.disconnect_debug()
        if (self.worker is None or not self.worker.isRunning()) and (self.owner is None or
                not self.owner.isRunning() and self.owner.unreleased_transport is None) and mag_done:
            return True
        self.cancel()
        if self.dialog is not None:
            self.dialog.setLabelText(self._tr("transfer.stopping"))
        return False


__all__ = ["DownloadWorker", "ExportWorker", "FileTransferManager"]
