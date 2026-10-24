from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QDialog
import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.i18n import Translator
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.configuration import SelectionAvailability
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfileUnsupportedError
from silverstar_fccg.generator.render import _FlightConfigHeader_Render, _LogMetadataDeclarations_Get
from silverstar_fccg.ui.main_window import MainWindow
from silverstar_fccg.ui.mission_capsules import MissionCapsuleBoard, MissionRuleDialog

APP = Path(__file__).resolve().parents[1]
OWNER_ID = 'silverstar.flight_logic.deployment.multi_trigger'


def _Events_Flush(qapp):
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def owner():
    service = FccgService(APP)
    return next(row for row in service.ComponentViews_Get('en_US') if row.component_id == OWNER_ID)


def test_add_duplicate_remove_and_unavailable_capsules(owner, qapp):
    availability = {option: SelectionAvailability(option != 'Tilt') for option in owner.selection_options}
    board = MissionCapsuleBoard(Translator('en_US'), owner, [], {}, availability, lambda item: 'unavailable' if not item.available else '')
    changes = QSignalSpy(board.optionsChanged)
    try:
        assert board.empty_label.isVisibleTo(board)
        assert not board.add_actions['Tilt'].isEnabled()
        board.Option_Add('Tilt'); assert changes.count() == 0
        board.Option_Add('Delay'); assert changes.count() == 1
        assert changes.at(0)[0] == ['Delay']
        board.Option_Add('Delay'); assert changes.count() == 1
        board.Option_Remove('Delay'); assert changes.at(1)[0] == []
    finally:
        board.close()


def test_dialog_cancel_unchanged_precision_and_invalid_draft(owner, qapp):
    value = 12.3456789
    dialog = MissionRuleDialog(Translator('en_US'), owner, 'Delay', {'delay': value}, True, '')
    try:
        dialog.accept()
        assert dialog.Values_Get()['delay'] == value
    finally:
        dialog.close()
    dialog = MissionRuleDialog(Translator('zh_CN'), owner, 'Delay', {'delay': 12.3456789}, True, '')
    try:
        editor = dialog.editors['delay']
        editor.setValue(99)
        dialog.reject()
        assert dialog.Values_Get() == {}
    finally:
        dialog.close()
    dialog = MissionRuleDialog(Translator('en_US'), owner, 'Delay', {'delay': 12.3456789}, True, '')
    try:
        dialog.editors['delay'].lineEdit().setText('invalid')
        dialog.accept()
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert dialog.error_label.text()
    finally:
        dialog.close()


def test_single_choice_required_declaration_is_respected(owner, qapp):
    single = replace(owner, allow_none=False, allow_multiple=False)
    availability = {option: SelectionAvailability(True) for option in owner.selection_options}
    board = MissionCapsuleBoard(Translator('en_US'), single, ['Tilt'], {}, availability, lambda item: '')
    changes = QSignalSpy(board.optionsChanged)
    try:
        board.Option_Remove('Tilt')
        assert changes.count() == 0
        board.add_actions['Delay'].trigger()
        assert changes.at(0)[0] == ['Delay']
        board.Option_Remove('Delay')
        assert changes.count() == 1
    finally:
        board.close()


def test_schema_additional_parameters_stay_in_dialog_and_resize_wraps(owner, qapp):
    custom = deepcopy(owner.options)
    custom['selection_parameters']['Delay'] = [*custom['selection_parameters']['Delay'], {
        'id': 'synthetic_second', 'type': 'integer', 'minimum': 1, 'maximum': 20,
        'default': 4, 'unit': '1', 'display_name': 'Synthetic plugin parameter'}]
    extended = replace(owner, options=custom)
    availability = {option: SelectionAvailability(True) for option in owner.selection_options}
    board = MissionCapsuleBoard(Translator('en_US'), extended, list(owner.selection_options), {}, availability, lambda item: '')
    try:
        assert ('Delay', 'synthetic_second') not in board.parameter_editors
        dialog = MissionRuleDialog(Translator('en_US'), extended, 'Delay', {}, True, '')
        assert 'synthetic_second' in dialog.editors
        dialog.editors['synthetic_second'].setValue(8); dialog.accept()
        assert dialog.Values_Get()['synthetic_second'] == 8
        dialog.close()
        for width, columns in ((380, 1), (800, 2), (1200, 3)):
            board.resize(width, 240); board._Cards_Layout()
            assert board._columns == columns
            assert len(board.cards) == 3
    finally:
        board.close()


def test_real_project_capsule_edits_dialog_apply_cancel_remove_restore(tmp_path, qapp, monkeypatch):
    service = FccgService(APP)
    service.policy = WorkspacePolicy(APP.parents[1])
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
    window._model = ReferenceProject_Create(catalog=service.catalog)
    window._Project_Refresh()
    window.pages.setCurrentWidget(window.flight_configuration_page)
    errors = []; monkeypatch.setattr(window, '_Error_Show', errors.append)
    try:
        board = window.flight_configuration_page.mode_capsule_boards['deployment']
        assert board.add_actions['Delay'].isEnabled()
        board.add_actions['Delay'].trigger(); _Events_Flush(qapp)
        board = window.flight_configuration_page.mode_capsule_boards['deployment']
        assert 'Delay' in board.cards
        editor = board.parameter_editors[('Delay', 'delay')]
        editor.lineEdit().setText('12.5 s')
        QTest.keyClick(editor, Qt.Key.Key_Return); _Events_Flush(qapp)
        assert window._model.mode_parameters['deployment']['Delay']['delay'] == 12.5
        def Dialog_Cancel():
            dialog = qapp.activeModalWidget()
            assert isinstance(dialog, MissionRuleDialog)
            dialog.editors['delay'].setValue(90); dialog.reject()
        QTimer.singleShot(0, Dialog_Cancel)
        window.flight_configuration_page.mode_capsule_boards['deployment'].Dialog_Open('Delay')
        _Events_Flush(qapp)
        assert window._model.mode_parameters['deployment']['Delay']['delay'] == 12.5
        def Dialog_Apply():
            dialog = qapp.activeModalWidget()
            dialog.editors['delay'].setValue(22.5); dialog.accept()
        QTimer.singleShot(0, Dialog_Apply)
        window.flight_configuration_page.mode_capsule_boards['deployment'].Dialog_Open('Delay')
        _Events_Flush(qapp)
        assert window._model.mode_parameters['deployment']['Delay']['delay'] == 22.5
        assert '22500U' in _FlightConfigHeader_Render(window._model, service.catalog)
        board = window.flight_configuration_page.mode_capsule_boards['deployment']
        board.Option_Remove('Delay'); _Events_Flush(qapp)
        assert 'Delay' not in window._model.modes['deployment']
        assert window._model.mode_parameters['deployment']['Delay']['delay'] == 22.5
        window.flight_configuration_page.mode_capsule_boards['deployment'].Option_Add('Delay')
        _Events_Flush(qapp)
        restored = window.flight_configuration_page.mode_capsule_boards['deployment']
        assert restored.parameter_editors[('Delay', 'delay')].value() == 22.5
        profile = MissionProfile_Build(window._model, service.catalog)
        service.ProjectRoot_Save(window._model, tmp_path / 'saved_project')
        reopened = service.Project_Open(tmp_path / 'saved_project')
        assert MissionProfile_Build(reopened, service.catalog) == profile
        window._model = reopened
        window._Project_Refresh()
        window.show()
        for language in ('zh_CN', 'en_US'):
            window.Language_Apply(language)
            for theme in ('light', 'dark'):
                window.Theme_Apply(theme)
                for width in (960, 1440):
                    window.resize(width, 900); _Events_Flush(qapp)
                    restored = window.flight_configuration_page.mode_capsule_boards['deployment']
                    assert restored.parameter_editors[('Delay', 'delay')].value() == 22.5
                    assert 'capsule.' not in restored.add_button.text()
                    assert set(restored.cards) == set(reopened.modes['deployment'])
        assert MissionProfile_Build(window._model, service.catalog) == profile
        assert not errors
    finally:
        window.close(); _Events_Flush(qapp)


def test_unknown_rule_owner_does_not_block_legacy_generation(builtin_catalog):
    class NewRuleCatalog:
        def __getattr__(self, name):
            return getattr(builtin_catalog, name)
        def ProjectView_Get(self, model):
            return self
        def Component_Get(self, component_id):
            manifest = builtin_catalog.Component_Get(component_id)
            return replace(manifest, version='99.0.0') if component_id == OWNER_ID else manifest
    catalog = NewRuleCatalog()
    model = ReferenceProject_Create(catalog=builtin_catalog)
    with pytest.raises(MissionProfileUnsupportedError):
        MissionProfile_Build(model, catalog)
    metadata = _LogMetadataDeclarations_Get(model, catalog, {})
    assert 'mission_profile' not in metadata
    assert 'mission_profile_rule_unsupported' in metadata['mission_profile_unavailable']['reason']
