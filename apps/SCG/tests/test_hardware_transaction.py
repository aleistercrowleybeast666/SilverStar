"""Ordinary startup and private hardware options; no reference-model substitution."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMainWindow

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.project.model import HardwareConfiguration
from silverstar_fccg.project.target_readiness import TargetReadiness_Get
from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
from silverstar_fccg.ui.main_window import MainWindow


def test_readiness_reuses_domain_validation_and_is_read_only(workspace_root):
    from test_round2_targets import _GroundBoardProject_Get
    service = FccgService(workspace_root)
    draft = service.ProjectDraft_Create('ordinary')
    before = deepcopy(draft.Dictionary_Get())
    assert not service.TargetReadiness_Get(draft, 'flight').ready
    assert not service.TargetReadiness_Get(draft, 'ground').ready
    assert draft.Dictionary_Get() == before
    flight = service.ReferenceProject_Create('one flight')
    assert service.TargetReadiness_Get(flight, 'flight').ready
    assert not service.TargetReadiness_Get(flight, 'ground').ready
    ground = _GroundBoardProject_Get(service.catalog)
    ground.hardware = HardwareConfiguration()
    ground.board = ''
    assert TargetReadiness_Get(ground, service.catalog, 'ground').ready
    assert not TargetReadiness_Get(ground, service.catalog, 'flight').ready
    flight.ground_target = replace(flight.ground_target,
        radio_plugin='silverstar.device.telemetry.sx1278', module_variant='e32_400m20s', tx_power_dbm=17)
    assert not service.TargetReadiness_Get(flight, 'flight').ready


def test_ordinary_window_admission_and_request_do_not_create_project(qapp, workspace_root, tmp_path, monkeypatch):
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=FccgService(workspace_root))
    window._toolchain_checked = True
    window.show(); qapp.processEvents()
    before = deepcopy(window._model.Dictionary_Get())
    calls = []
    window._Error_Show = lambda *args: calls.append(args)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *_args: pytest.fail('unready request opened output chooser'))
    for target, page in (('flight', window.board_hardware_page), ('ground', window.ground_target_page)):
        assert not page.generate_button.isEnabled()
        window._Targets_Generate('generate_' + target)
    assert len(calls) == 2
    assert window._project_root is None
    assert window._model.Dictionary_Get() == before
    window._Actions_SetEnabled(False); window._Actions_SetEnabled(True)
    assert window._active_worker is None
    # Reproduce the completion order: restored controls, then the asynchronous
    # tool-result presenter. Tool presence must not erase configuration reasons.
    from types import SimpleNamespace
    window._Toolchains_Show(tuple(SimpleNamespace(tool_id=tool, command=tool,
        path='test/'+tool, version='test', available=True, compatible=True, target='test')
        for tool in ('compiler', 'make', 'host_gcc')))
    assert not window.board_hardware_page.generate_button.isEnabled()
    assert not window.ground_target_page.generate_button.isEnabled()
    assert all(label.text() == window._translator.Text_Get('target.generation.blocked')
               for label in window.build_page.target_status_labels.values())
    workspace = window.hardware_workspace
    assert workspace.root_layout.indexOf(workspace.link_group) > workspace.root_layout.indexOf(workspace.target_grid)
    assert workspace.root_layout.indexOf(workspace.device_group) > workspace.root_layout.indexOf(workspace.link_group)
    assert not window.flight_configuration_page.telemetry_protocol_group.isVisible()
    window.close()


def test_real_qapplication_exits_after_both_target_drafts(tmp_path):
    import json
    import os
    import subprocess
    import sys
    fixture = Path(__file__).parent/'fixtures/hardware_dialog_lifecycle.py'
    process = subprocess.run([sys.executable, str(fixture), str(tmp_path/'lifecycle')],
        env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), capture_output=True, text=True,
        encoding='utf8', errors='replace', timeout=45)
    assert process.returncode == 0, process.stdout + '\n' + process.stderr
    result = json.loads((tmp_path/'lifecycle/result.json').read_text(encoding='utf8'))
    assert result['last_window_closed'] and result['about_to_quit']
    assert not result['timed_out'] and not result['unexpected_windows']


@pytest.mark.parametrize('target', ('flight', 'ground'))
@pytest.mark.parametrize('cancel', ('cancel', 'escape', 'close'))
def test_private_hardware_edits_cancel_without_model_settings_or_cache_write(qapp, workspace_root, tmp_path, monkeypatch, target, cancel):
    service = FccgService(workspace_root)
    model = service.ProjectDraft_Create('private')
    before = deepcopy(model.Dictionary_Get())
    settings = tmp_path/'settings.ini'; settings.write_bytes(b'[existing]\nkeep=true\n')
    cache = tmp_path/'cache'; cache.mkdir(); (cache/'keep.bin').write_bytes(b'original')
    files = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    monkeypatch.setattr(service, 'CubeMxProject_Import', lambda *_args, **_kwargs: pytest.fail('import before Apply'))
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *_args: str(tmp_path/'not-imported'))
    dialog = HardwareTransactionDialog(Translator('zh_CN'), model, service, target)
    assert not dialog.findChildren(QMainWindow)
    dialog.show(); qapp.processEvents()
    dialog._Import_Select(True)
    if target == 'flight':
        dialog.controller._BoardSelection_Change(service.ReferenceProject_Create('board').board)
    else:
        dialog.controller._GroundBoard_Change('silverstar.board.ground_station_0_5')
    assert dialog.controller._model.Dictionary_Get() != before
    assert model.Dictionary_Get() == before
    if cancel == 'escape': QTest.keyClick(dialog, Qt.Key.Key_Escape)
    elif cancel == 'close': dialog.close()
    else: dialog.reject()
    qapp.processEvents()
    assert dialog.Configuration_Get() is None
    assert model.Dictionary_Get() == before
    assert {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == files


def test_apply_is_private_until_outer_transaction_and_returns_one_candidate(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ProjectDraft_Create('apply')
    before = deepcopy(model.Dictionary_Get())
    dialog = HardwareTransactionDialog(Translator('en_US'), model, service, 'ground')
    dialog.controller._GroundBoard_Change('silverstar.board.ground_station_0_5')
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.Configuration_Get().ground_target.board == 'silverstar.board.ground_station_0_5'
    assert model.Dictionary_Get() == before
    # Queued UI edits cannot publish after either terminal decision.
    candidate = dialog.Configuration_Get().Dictionary_Get()
    dialog.controller._GroundAssignment_Change('radio_bus', 'bad')
    assert dialog.Configuration_Get().Dictionary_Get() == candidate


@pytest.mark.parametrize('decision', ('cancel', 'apply', 'import_failure', 'stale'))
def test_main_window_modal_publication_and_failed_import_are_atomic(qapp, workspace_root, tmp_path, monkeypatch, decision):
    from PySide6.QtWidgets import QMessageBox
    service = FccgService(workspace_root)
    window = MainWindow(SettingsStore(tmp_path/'settings.ini'), service=service)
    window._toolchain_checked = True
    window._MessageBox_Exec = lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
    window.show(); qapp.processEvents()
    window._settings._settings.sync()
    before = deepcopy(window._model.Dictionary_Get())
    settings_before = (tmp_path/'settings.ini').read_bytes()
    errors = []
    window._Error_Show = lambda *args: errors.append(args)
    if decision == 'import_failure':
        def task(operation, complete, *_args, **_kwargs):
            try: result = operation(None)
            except ValueError as error: errors.append(str(error))
            else: complete(result)
        window.Task_Run = task
        monkeypatch.setattr(service, 'CubeMxProject_Import', lambda *_args, **_kwargs:
                            (_ for _ in ()).throw(ValueError('bad source rejected')))
    observations = []
    def edit():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, HardwareTransactionDialog)
            dialog.controller._GroundBoard_Change('silverstar.board.ground_station_0_5')
            assert window._model.Dictionary_Get() == before
            if decision == 'cancel':
                QTest.keyClick(dialog, Qt.Key.Key_Escape)
            else:
                if decision == 'import_failure': dialog._import_path = str(tmp_path/'bad-cubemx')
                if decision == 'stale': window._model.identity = replace(window._model.identity, name='changed outside dialog')
                dialog.accept()
        except BaseException as error:
            observations.append(error)
            dialog.reject()
    QTimer.singleShot(0, edit)
    window._HardwareTransaction_Open('ground')
    assert not observations
    qapp.processEvents()
    if decision == 'apply':
        assert window._model.ground_target.board == 'silverstar.board.ground_station_0_5'
        assert window._model.Dictionary_Get()['hardware'] == before['hardware']
        assert not errors
    else:
        if decision == 'stale':
            assert window._model.identity.name == 'changed outside dialog'
            assert window._model.Dictionary_Get()['ground_target'] == before['ground_target']
        else:
            assert window._model.Dictionary_Get() == before
        assert bool(errors) == (decision in ('import_failure', 'stale'))
    window._settings._settings.sync()
    assert (tmp_path/'settings.ini').read_bytes() == settings_before
    assert not (tmp_path/'bad-cubemx').exists()
    window.close()
