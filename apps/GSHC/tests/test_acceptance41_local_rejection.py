"""Offline real-button regressions for descriptor changes during TF selection."""
from unittest.mock import patch
import json

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app import Controller
from services.i18n import I18n
from services.maintenance_trace import MaintenanceTrace
from transport.probe_inventory import ProbeInventory, ProbeInventoryResult
from ui.file_transfer import MaintenanceOwner
from ui.main_window import MainWindow


UART = {'baudrate': 921600, 'format': '8N1'}


@pytest.fixture
def screen(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr('app.USER_DATA_ROOT', tmp_path)
    monkeypatch.setattr('app.list_serial_port_names', lambda: [])
    window = MainWindow(I18n(QSettings(str(tmp_path/'ui.ini'), QSettings.IniFormat)))
    controller = Controller(window, probe_enumerator=lambda _: ProbeInventory(ProbeInventoryResult.Empty))
    manager = controller.file_transfer
    # No owner thread is started; any accidental transport creation fails.
    def forbidden(*_):
        pytest.fail('A UI rejection test must not open a transport')
    owner = MaintenanceOwner('SYNTHETIC', 921600, transport_factory=forbidden)
    owner.connected.set()
    owner._maintenance_initialized = True
    owner.trace = MaintenanceTrace(tmp_path/'diagnostics', 'SYNTHETIC', 921600)
    manager.owner = owner
    owner.failed.connect(manager._failed, Qt.QueuedConnection)
    window._debug_connected = window._debug_service_supported = True
    manager.export_dialog.set_connection(True, True)
    manager.export_dialog.progress.setValue(0)
    yield application, window, manager, owner
    if manager._error_notice is not None:
        manager._error_notice.close()
    manager.owner = None
    manager.job_busy = False
    owner.trace.close('synthetic test only')
    controller.shutdown()
    window.close()
    window.deleteLater()
    owner.deleteLater()
    QTest.qWait(20)


def read_button(manager):
    with patch('ui.log_export_dialog.QMessageBox.question', return_value=QMessageBox.Yes):
        manager.export_dialog.refresh.click()


def test_changed_descriptor_real_button_has_notice_and_sends_nothing(screen):
    _, window, manager, owner = screen
    window.maintenance_page.console.set_protocol_declaration({'maintenance': {'uart': UART}})
    manager.export_dialog.show()
    read_button(manager)
    assert owner.jobs.empty()
    assert not manager.job_busy and not manager.export_dialog.busy
    assert manager.export_dialog.progress.value() == 0
    assert manager.export_dialog.refresh.isEnabled()
    assert not manager.export_dialog._confirming
    assert manager._error_notice is not None and manager._error_notice.isVisible()
    assert '尚未发送' in manager._error_notice.text()
    assert '重新连接' in manager.export_dialog.status.text()
    assert manager.export_dialog.verification_state == 'declaration_changed'
    assert manager.export_dialog.verification.isVisible()
    owner.trace.Pending_Flush()
    records = [json.loads(line) for line in owner.trace.path.read_text(encoding='utf-8').splitlines()]
    reject = next(row for row in records if row['kind'] == 'local_rejected')
    assert reject['reason'] == 'declaration_changed' and reject['request_sent'] is False
    assert reject['expected_uart_sha256'] != reject['current_uart_sha256']


def test_same_descriptor_reload_restores_eligible_state_and_real_button(screen):
    _, window, manager, owner = screen
    owner.expected_uart = dict(UART)
    console = window.maintenance_page.console
    console.set_protocol_declaration(None, loading=True)
    assert manager.export_dialog.verification_state == 'declaration_loading'
    console.set_protocol_declaration({'maintenance': {'uart': dict(UART)}})
    manager.export_dialog.show()
    assert manager.export_dialog.verification_state == ''
    assert not manager.export_dialog.verification.isVisible()
    read_button(manager)
    assert owner.jobs.qsize() == 1 and manager.job_busy
    assert manager._error_notice is None


def test_reload_blocks_real_button_even_when_both_uart_snapshots_are_none(screen):
    _, window, manager, owner = screen
    window.maintenance_page.console.set_protocol_declaration(None, loading=True)
    manager.export_dialog.show()
    read_button(manager)
    assert owner.jobs.empty() and not manager.job_busy
    assert '重载中' in manager._error_notice.text()
    assert '重载中' in window.maintenance_page.console.protocol_status.text()
    assert manager.export_dialog.refresh.isEnabled()


def test_hidden_dialog_local_refusal_is_visible_and_recorded(screen):
    _, window, manager, owner = screen
    window.maintenance_page.console.set_protocol_declaration({'maintenance': {'uart': UART}})
    manager.export_dialog.hide()
    read_button(manager)
    assert owner.jobs.empty()
    assert manager._error_notice.isVisible() and '尚未发送' in manager._error_notice.text()
    owner.trace.Pending_Flush()
    assert 'local_rejected' in owner.trace.path.read_text(encoding='utf-8')


def test_reload_completion_clears_old_local_refusal_and_next_click_queues(screen):
    _, window, manager, owner = screen
    owner.expected_uart = dict(UART)
    console=window.maintenance_page.console
    console.set_protocol_declaration(None,loading=True)
    manager.export_dialog.show()
    read_button(manager)
    assert '重载中' in manager.export_dialog.status.text()
    manager._error_notice.close()
    console.set_protocol_declaration({'maintenance':{'uart':dict(UART)}})
    assert '可重新读取目录' in manager.export_dialog.status.text()
    assert manager.export_dialog.verification_state == ''
    read_button(manager)
    assert owner.jobs.qsize() == 1 and manager.job_busy
    assert '尚未发送' not in manager.export_dialog.status.text()


def test_refused_new_request_preserves_active_progress(screen):
    from services.transfer_progress import TransferProgress
    _, window, manager, owner = screen
    snapshot=TransferProgress(12,100,'receiving')
    manager.job_busy=True
    manager._byte_last=snapshot
    manager._progress_timer.start()
    window.maintenance_page.console.set_protocol_declaration({'maintenance':{'uart':UART}})
    manager.export_dialog.show()
    read_button(manager)
    assert owner.jobs.empty() and manager.job_busy
    assert manager._byte_last is snapshot and manager._progress_timer.isActive()


def test_old_owner_error_cannot_replace_local_rejection(screen):
    _, window, manager, owner = screen
    window.maintenance_page.console.set_protocol_declaration({'maintenance': {'uart': UART}})
    manager.export_dialog.show()
    read_button(manager)
    notice = manager._error_notice
    text = notice.text()
    old = MaintenanceOwner('OLD_SYNTHETIC', 921600)
    old.failed.connect(manager._failed, Qt.QueuedConnection)
    old.failed.emit('obsolete owner error')
    QTest.qWait(20)
    assert notice.text() == text and 'obsolete' not in manager.export_dialog.status.text()
    assert owner.jobs.empty()
    old.deleteLater()


def test_declared_mismatch_repeated_click_reuses_one_notice(screen):
    _, window, manager, owner = screen
    window.maintenance_page.console.set_protocol_declaration({'maintenance': {'uart': UART}})
    manager.export_dialog.show()
    read_button(manager)
    notice = manager._error_notice
    notice.button(QMessageBox.Ok).click()
    read_button(manager)
    assert manager._error_notice is notice and notice.isVisible()
    assert owner.jobs.empty() and not manager.job_busy


def test_local_refusal_does_not_write_trace_on_gui_thread(screen):
    _, window, manager, owner = screen
    window.maintenance_page.console.set_protocol_declaration({'maintenance': {'uart': UART}})
    manager.export_dialog.show()
    before = owner.trace.path.read_bytes()
    with patch.object(owner.trace, 'event', side_effect=AssertionError('GUI attempted diagnostic file I/O')):
        read_button(manager)
    assert owner.trace.path.read_bytes() == before
    owner.trace.Pending_Flush()
    assert 'local_rejected' in owner.trace.path.read_text(encoding='utf-8')
