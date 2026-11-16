"""Frequency-first selection, real empty states and safe startup inventories."""
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget
from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.project.model import ProjectModel_Parse
from silverstar_fccg.project.radio_transaction import (
    RadioTransaction_BandSet,
    RadioTransaction_Commit,
    RadioTransaction_EndpointSet,
)
from silverstar_fccg.ui.hardware_transaction import HardwareTransactionDialog
from silverstar_fccg.ui.radio_transaction import RadioTransactionDialog
from silverstar_fccg.ui.window_geometry import CenteredMessageBox


def test_band_change_clears_both_radios_but_keeps_other_resources_and_cancel(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('band selection')
    model = RadioTransaction_EndpointSet(model, service.catalog, 'ground',
        'silverstar.device.telemetry.sx1281', 'e28_2g4m12sx', 12)
    model.ground_target = replace(model.ground_target,
        resource_assignments={'radio0:radio_bus': 'SPI1', 'user:reserved': 'GPIO1'})
    before = deepcopy(model.Dictionary_Get())
    draft, removed = RadioTransaction_BandSet(model, service.catalog, 'sx127x')
    assert len(removed) == 2
    assert draft.DeviceInstance_Get(draft.air_link.flight_radio_instance) is None
    assert not draft.ground_target.radio_plugin
    assert draft.ground_target.resource_assignments == {'user:reserved': 'GPIO1'}
    assert draft.hardware == model.hardware
    assert model.Dictionary_Get() == before
    result = RadioTransaction_Commit(draft, service.catalog)
    assert not service.TargetReadiness_Get(result, 'flight').ready
    assert not service.TargetReadiness_Get(result, 'ground').ready
    restored = ProjectModel_Parse(result.Dictionary_Get())
    assert restored.Dictionary_Get() == result.Dictionary_Get()
    schema = json.loads((workspace_root/'schemas/project.schema.json').read_text(encoding='utf8'))
    Draft202012Validator(schema).validate(result.Dictionary_Get())
    dialog = RadioTransactionDialog(Translator('zh_CN'), model, service.catalog)
    dialog.preset.setCurrentIndex(dialog.preset.findData('sx127x'))
    assert all(combo.currentData() is None for combo, _ in dialog.endpoints.values())
    dialog.reject()
    assert dialog.Configuration_Get() is None and model.Dictionary_Get() == before


def test_explicit_empty_radio_can_apply_and_reopen(qapp, workspace_root):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('clear radio')
    dialog = RadioTransactionDialog(Translator('en_US'), model, service.catalog)
    combo = dialog.endpoints['flight'][0]
    assert combo.model().item(0).isEnabled()
    combo.setCurrentIndex(0)
    dialog.accept()
    result = dialog.Configuration_Get()
    assert result is not None and result.DeviceInstance_Get(result.air_link.flight_radio_instance) is None
    assert not service.TargetReadiness_Get(result, 'flight').ready
    reopened = RadioTransactionDialog(Translator('en_US'), result, service.catalog)
    assert reopened.endpoints['flight'][0].currentData() is None
    reopened.reject()


@pytest.mark.parametrize('target', ['flight', 'ground'])
def test_import_only_for_custom_and_board_change_discards_pending_import(qapp, workspace_root, monkeypatch, target):
    service = FccgService(workspace_root)
    model = service.ProjectDraft_Create('hardware source')
    dialog = HardwareTransactionDialog(Translator('zh_CN'), model, service, target)
    dialog.show(); qapp.processEvents()
    combo = dialog.owner.board_combo
    combo.setCurrentIndex(combo.findData(''))
    assert combo.currentData() == ''
    assert not dialog.owner.import_directory_button.isVisible()
    combo.setCurrentIndex(combo.findData('__custom__'))
    assert dialog.owner.import_directory_button.isVisible()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *_args: 'C:/not-imported')
    dialog._Import_Select(True)
    assert dialog.ImportPath_Get() == 'C:/not-imported'
    board = service.ReferenceProject_Create('board').board if target == 'flight' else 'silverstar.board.ground_station_0_5'
    combo.setCurrentIndex(combo.findData(board))
    assert dialog.ImportPath_Get() is None
    assert not dialog.owner.import_directory_button.isVisible()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *_args: pytest.fail('board opened importer'))
    dialog._Import_Select(True)
    combo.setCurrentIndex(0)
    hardware = dialog.controller._model.hardware if target == 'flight' else dialog.controller._model.ground_target.hardware
    assert hardware.mode == 'unselected'
    dialog.reject()


def test_message_box_centers_on_actual_owner(qapp):
    owner = QWidget(); owner.setGeometry(80, 50, 600, 430); owner.show()
    box = CenteredMessageBox(owner)
    box.setText('Save the modified project before closing?')
    box.setStandardButtons(QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel)
    box.show(); qapp.processEvents()
    assert (box.frameGeometry().center() - owner.frameGeometry().center()).manhattanLength() <= 2
    assert owner.screen().availableGeometry().contains(box.frameGeometry())
    box.reject(); owner.close()


@pytest.mark.parametrize('target,board,mcu', [
    ('flight', 'silverstar.board.ssfc_1_0', 'silverstar.mcu.stm32h743zit6'),
    ('ground', 'silverstar.board.ssgs_1_0', 'silverstar.mcu.stm32c071fbp6'),
])
def test_existing_candidate_board_can_be_selected_without_import_or_erasing_peers(qapp, workspace_root, target, board, mcu):
    service = FccgService(workspace_root)
    model = service.ReferenceProject_Create('candidate selection')
    before = deepcopy(model)
    dialog = HardwareTransactionDialog(Translator('zh_CN'), model, service, target)
    dialog.show(); qapp.processEvents()
    combo = dialog.owner.board_combo
    index = combo.findData(board)
    assert index >= 0 and combo.model().item(index).isEnabled()
    combo.setCurrentIndex(index); qapp.processEvents()
    draft = dialog.controller._model
    selected = draft if target == 'flight' else draft.ground_target
    assert selected.board == board and selected.mcu == mcu
    assert selected.hardware.mode == 'board_plugin'
    assert not dialog.owner.import_directory_button.isVisible()
    if target == 'flight':
        assert draft.ground_target == before.ground_target
    else:
        assert draft.board == before.board and draft.device_instances == before.device_instances
    dialog.reject()
    assert model == before


def test_payload_scan_is_fresh_and_sorted(builtin_catalog, tmp_path):
    manifest = replace(builtin_catalog.Component_Get('silverstar.core.0_1_0'),
        manifest_path=tmp_path/'plugin.json', payload_roots=('Core', 'Core/sub'))
    root = tmp_path/'payload/Core'; (root/'sub').mkdir(parents=True)
    (root/'z.c').write_text('first'); (root/'sub/a.c').write_text('second')
    assert [p.name for p in manifest.PayloadFiles_Get()] == ['a.c', 'z.c']
    (root/'new.c').write_text('new'); (root/'z.c').unlink()
    assert [p.name for p in manifest.PayloadFiles_Get()] == ['new.c', 'a.c']


def test_payload_scan_still_rejects_links(builtin_catalog, tmp_path):
    from silverstar_fccg.plugins.manifest import PluginManifestError
    manifest = replace(builtin_catalog.Component_Get('silverstar.core.0_1_0'),
        manifest_path=tmp_path/'plugin.json', payload_roots=('Core',))
    root = tmp_path/'payload/Core'; root.mkdir(parents=True)
    (root/'new.c').write_text('source')
    try:
        (root/'link.c').symlink_to(root/'new.c')
    except OSError as error:
        pytest.skip('OS does not permit fixture symlinks: ' + str(error))
    with pytest.raises(PluginManifestError, match='symlink'):
        manifest.PayloadFiles_Get()
