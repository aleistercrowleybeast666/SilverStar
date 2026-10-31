"""Normal GUI entry and honest capability admission over the existing owner."""
from dataclasses import replace
from threading import Event
import time

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from services.installation_calibration_backend import (InstallationBackend, InstallationCapabilities_Parse,
    InstallationResult)
from services.installation_calibration_worker import InstallationWorker
from test_installation_calibration_backend import MockInstallationOwner, response, run_job
from test_gui_maintenance_workflow import gui, connect, wait_for
from test_file_service_client import MockTransport
from ui.installation_dialog import InstallationDialog


def caps(**extra):
    return response('OK','CAPS',maintenance='0.1',supported=1,install_contract=1,face_auto=1,
        check_only=1,sample_format=1,max_request=191,max_line=511,train_pairs=3,
        holdout_pairs=3,pair_capacity=4096,offline=0,**extra)


def test_production_capabilities_never_infer_capture_from_contract_support():
    old = InstallationCapabilities_Parse(caps())
    assert old.contract_supported and not old.capture_available
    assert old.outcome.result is InstallationResult.Unsupported
    declared = InstallationCapabilities_Parse(caps(contract_supported=1,capture_available=0,
        apply_supported=0,save_supported=0,reason='SOURCE_QUALIFICATION'))
    assert declared.contract_supported and not declared.capture_available
    assert declared.blocking_reason == 'SOURCE_QUALIFICATION'
    assert not declared.apply_supported and not declared.save_supported
    incomplete = InstallationCapabilities_Parse(caps(capture_available=1))
    assert incomplete.outcome.result is InstallationResult.Unknown


def test_probe_releases_owner_and_does_not_begin_capture():
    owner = MockInstallationOwner()
    backend = InstallationBackend(owner, allow_simulated=True)
    worker = InstallationWorker(backend)
    try:
        result = run_job(worker, 'probe')
        assert result.result is InstallationResult.Ok
        assert result.detail.contract_supported and result.detail.capture_available
        assert not result.detail.apply_supported and not owner.busy
        assert [item.operation for item in owner.commands] == ['CAPS']
    finally: assert worker.Close().result is InstallationResult.Ok


def test_normal_maintenance_button_registers_owner_and_cleanup_is_nonblocking(gui):
    window, controller, root = gui
    connect(window, controller, MockTransport())
    manager = controller.file_transfer
    assert manager.owner._installation_capture_enabled
    window.btn_installation_calibration.click()
    dialog = manager.installation_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog.backend.provider.owner is manager.owner
    assert manager.busy and not dialog.begin.isEnabled()
    assert not manager.mag_acquire()
    assert not manager.send_command('SYSTEM INFO')
    dialog.reject()
    wait_for(lambda: manager.installation_dialog is None)
    assert not manager.busy


def test_six_face_dialog_submits_same_backend_and_displays_unapplied_state(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    owner = MockInstallationOwner()
    backend = InstallationBackend(owner, allow_simulated=True)
    dialog = InstallationDialog(None, tmp_path, backend=backend)
    dialog.show()
    dialog.probe.click()
    wait_for(lambda: dialog._pending is None)
    assert dialog.begin.isEnabled() and '目标应用：不可用' in dialog.capabilities.text()
    monkeypatch.setattr('ui.installation_dialog.QFileDialog.getSaveFileName',
        lambda *_: (str(tmp_path/'capture.jsonl'), ''))
    dialog.begin.click()
    wait_for(lambda: dialog._pending is None)
    assert dialog._session and all(button.isEnabled() for button in dialog.faces.values())
    dialog.faces['XP'].click()
    wait_for(lambda: dialog._pending is None)
    assert '已采集' in dialog.faces['XP'].text()
    assert len(backend.dataset.FittingRecords()) == 5
    assert len(backend.dataset.FreshHoldout()) == 5
    assert '未应用到 RAM' in dialog.active_status.text()
    before = time.monotonic(); dialog.reject()
    assert time.monotonic() - before < .2
    wait_for(lambda: dialog._closed)
    assert not owner.busy and backend.cleanup_confirmed
    dialog.deleteLater()
