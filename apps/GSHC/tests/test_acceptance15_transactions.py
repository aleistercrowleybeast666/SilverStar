"""Transaction/UI regressions from the actual maintenance acceptance session."""
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QSettings, QObject, Signal
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app import Controller
from services.i18n import I18n, Language
from services.transfer_progress import TransferProgress
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
from ui.main_window import MainWindow


@pytest.fixture
def screen(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr('app.USER_DATA_ROOT', tmp_path)
    monkeypatch.setattr('app.list_serial_port_names', lambda: [])
    window = MainWindow(I18n(QSettings(str(tmp_path/'ui.ini'), QSettings.IniFormat)))
    controller = Controller(window, probe_enumerator=lambda _: ProbeInventory(ProbeInventoryResult.Empty))
    yield application, window, controller.file_transfer
    controller.shutdown()
    window.close()
    window.deleteLater()
    QTest.qWait(20)


def test_completed_catalog_stops_both_indeterminate_bars_and_clock(screen):
    _, window, manager = screen
    manager.job_busy = True
    manager.export_dialog.set_busy(True, 'list')
    manager._byte_progress(TransferProgress(0, None, 'listing'))
    manager._catalog_details([{'id': i, 'size': 64} for i in range(1, 76)])
    assert manager.export_dialog.progress.maximum() == 0
    manager._completed('Listed 75 closed logs')
    manager._job_finished()
    assert manager.export_dialog.progress.maximum() > 0
    assert window.maintenance_page.progress.maximum() > 0
    assert not manager._progress_timer.isActive()
    assert manager._byte_last is None
    assert '75' in manager.export_dialog.status.text()
    assert '尚未导出' in manager.export_dialog.status.text()


def test_nested_confirmation_cannot_submit_same_download_twice(screen, tmp_path):
    dialog = screen[2].export_dialog
    dialog.set_connection(True, True)
    dialog.set_catalog([{'id': 62, 'size': 9519499}], selected=(62,))
    dialog.path.setText(str(tmp_path))
    submissions = []
    dialog.download_requested.disconnect()
    dialog.download_requested.connect(lambda path, ids: (submissions.append((path, ids)), dialog.set_busy(True, 'download')))
    questions = []
    def reentrant(*_):
        questions.append(1)
        if len(questions) == 1:
            dialog._start()  # A second activation delivered by the modal event loop.
        return QMessageBox.Yes
    with patch('ui.log_export_dialog.QMessageBox.question', side_effect=reentrant):
        dialog._start()
    assert len(questions) == 1
    assert submissions == [(str(tmp_path), (62,))]


def test_firmware_lock_is_a_blocked_phase_without_enabling_magnetic_actions(screen):
    dialog = screen[2].mag_dialog
    dialog.pending = 'read'
    dialog._result('read', None, 'ERR SYSTEM CAL code=LOCKED reason=FLIGHT')
    assert '固件锁定' in dialog.stage.text() and 'FLIGHT' in dialog.stage.text()
    assert 'ERR SYSTEM CAL code=LOCKED reason=FLIGHT' in dialog.status.text()
    assert not dialog.capable
    assert all(not button.isEnabled() for button in (dialog.start, dialog.apply_ram, dialog.save_device))
    dialog.i18n.set_language(Language.EN_US)
    dialog.retranslate()
    assert 'Firmware locked' in dialog.stage.text()


def test_error_notice_is_single_nonblocking_localized_and_retains_raw_diagnostic(screen):
    _, _, manager = screen
    manager._failed('LOGFILE CAPS response incomplete; reconnect required')
    first = manager._error_notice
    assert first is not None and first.isVisible()
    assert first.button(QMessageBox.Ok).text() == '确定'
    assert 'LOGFILE CAPS response incomplete; reconnect required' in first.text()
    manager._failed('Close failed: simulated driver error')
    assert manager._error_notice is first
    assert 'simulated driver error' in first.text()
    assert 'LOGFILE CAPS response incomplete; reconnect required' in first.text()
    first.button(QMessageBox.Ok).click()
    assert not first.isVisible()


def test_late_owner_progress_cannot_restart_finished_job(screen):
    manager = screen[2]
    class Emitter(QObject):
        progress = Signal(object)
        failed = Signal(str)
    old = Emitter()
    old.progress.connect(manager._byte_progress)
    old.failed.connect(manager._failed)
    manager.owner = old
    manager.job_busy = False
    old.progress.emit(TransferProgress(0, None, 'metadata'))
    assert manager._byte_last is None and not manager._progress_timer.isActive()
    manager.owner = None
    old.failed.emit('stale previous owner error')
    assert manager._error_notice is None


def test_capabilities_failure_is_never_presented_as_metadata_or_received_file_bytes(tmp_path):
    from services.file_service_client import FileServiceClient
    class Wire:
        def exchange(self, command, timeout, cancel):
            assert command == 'LOGFILE CAPS'
            raise TimeoutError('CAPS response incomplete')
    phases = []
    with pytest.raises(TimeoutError):
        FileServiceClient(Wire()).download(62,tmp_path,byte_progress=lambda *row:phases.append(row))
    assert phases == [(0,None,'capabilities')]
    assert list(tmp_path.iterdir()) == []


def test_bounded_trace_retains_terminal_counters_tail_and_existing_evidence(tmp_path):
    from services.maintenance_trace import MaintenanceTrace
    trace = MaintenanceTrace(tmp_path,'SIMULATED',230400,limit=32768)
    for i in range(300):
        trace.raw('rx',b'x'*128)
        trace.raw('tx',b'LOGFILE POLL 233\r\n')
        trace.exchange('LOGFILE POLL 233','PENDING LOGFILE META request_id=233',.005)
    trace.event('job_failed',error='Metadata operation deadline exceeded')
    trace.close('transport_released=True')
    content = trace.path.read_bytes()
    assert len(content) <= 32768
    rows = [json.loads(line) for line in content.splitlines()]
    assert rows[-1]['kind'] == 'closed' and rows[-1]['truncated']
    assert rows[-1]['rx_bytes'] == 38400 and rows[-1]['exchanges'] == 300
    assert len(rows[-1]['raw_tail']) == 8
    assert rows[-1]['last_exchanges'][-1]['response']=='PENDING LOGFILE META request_id=233'
    another = MaintenanceTrace(tmp_path,'SIMULATED',230400)
    another.close()
    assert trace.path.read_bytes() == content and another.path != trace.path


def test_trace_quota_disables_new_recording_without_removing_evidence(tmp_path):
    from services.maintenance_trace import MaintenanceTrace
    evidence = tmp_path/'maintenance_existing.jsonl'
    with evidence.open('wb') as stream:
        stream.truncate(8*1024*1024)
    trace = MaintenanceTrace(tmp_path,'SIMULATED',230400)
    assert trace.path is None and 'quota' in trace.error.lower()
    trace.raw('rx',b'OK\r\n')
    trace.close()
    assert trace.rx_bytes == 4 and evidence.stat().st_size == 8*1024*1024
    assert list(tmp_path.iterdir()) == [evidence]


def test_trace_preserves_validated_transport_and_receive_observer_without_extra_commands(tmp_path, monkeypatch):
    from test_file_service_probe_boundary import create, INFO, CAP
    from services.file_service_client import FileServiceClient
    from services.maintenance_trace import MaintenanceTrace
    _, wire, transport = create(monkeypatch)
    trace = MaintenanceTrace(tmp_path,'SIMULATED',230400)
    transport.trace = trace
    received = []
    transport.receive_observer = received.append
    FileServiceClient(transport).negotiate()
    transport.close()
    trace.close('transport_released=True')
    assert wire.tx == [b'SYSTEM INFO\r\n',b'LOGFILE CAPS\r\n'] and wire.closed
    assert b''.join(received) == INFO+CAP
    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
    assert rows[-1]['rx_bytes'] == len(INFO+CAP)
    assert rows[-1]['tx_bytes'] == sum(map(len,wire.tx))
    assert rows[-1]['last_exchanges'][-1]['response'] == CAP.decode().strip()


def test_trace_unavailable_keeps_validated_transport_working(tmp_path, monkeypatch):
    from test_file_service_probe_boundary import create
    from services.file_service_client import FileServiceClient
    from services.maintenance_trace import MaintenanceTrace
    blocked = tmp_path/'file_not_directory'
    blocked.write_bytes(b'evidence')
    trace = MaintenanceTrace(blocked,'SIMULATED',230400)
    _, wire, transport = create(monkeypatch)
    transport.trace = trace
    assert FileServiceClient(transport).negotiate()['supported'] == '1'
    transport.close()
    trace.close()
    assert trace.path is None and trace.error and wire.closed
    assert blocked.read_bytes() == b'evidence'


def test_disconnection_while_confirming_cannot_submit_after_yes(screen, tmp_path):
    dialog = screen[2].export_dialog
    dialog.set_connection(True,True)
    dialog.set_catalog([{'id':62,'size':9519499}],selected=(62,))
    dialog.path.setText(str(tmp_path))
    emitted = []
    dialog.download_requested.disconnect()
    dialog.download_requested.connect(lambda *row:emitted.append(row))
    def disconnect(*_):
        dialog.set_connection(False,False)
        return QMessageBox.Yes
    with patch('ui.log_export_dialog.QMessageBox.question',side_effect=disconnect):
        dialog._start()
    assert emitted == [] and not dialog.start.isEnabled()
