from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QComboBox, QGroupBox, QMessageBox
import pytest

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.project.reference import ReferenceProject_Create
from silverstar_fccg.project.mission_profile import MissionProfile_Build, MissionProfileUnsupportedError
from silverstar_fccg.generator.render import _LogMetadataDeclarations_Get
from silverstar_fccg.ui.main_window import MainWindow

APP = Path(__file__).resolve().parents[1]
OWNER_ID = 'silverstar.flight_logic.deployment.multi_trigger'


def _Events_Flush(qapp):
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_start_merge_does_not_discard_customized_phase(qapp):
    from silverstar_fccg.ui.mission_process_panel import MissionProcessPanel
    from silverstar_fccg.project.mission_process import MissionProcess_Default
    from silverstar_fccg.core.i18n import Translator
    panel=MissionProcessPanel(Translator('en_US'))
    panel.Configuration_Set(MissionProcess_Default())
    changes=QSignalSpy(panel.processChanged)
    try:
        panel.Stage_Rename('mission_start','Custom start annotation')
        assert changes.count()==1
        panel.start_policy.setCurrentIndex(panel.start_policy.findData('start_is_launch'))
        assert changes.count()==1 and panel.error.text()
        assert panel.start_policy.currentData()=='separate'
        assert panel._process['stages'][1]['name']=='Custom start annotation'
    finally:
        panel.close()


def _Modal_Click(button, dialog_type, interact):
    from PySide6.QtWidgets import QApplication
    outcomes = []
    def DuringDialog():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, dialog_type)
            interact(dialog)
            outcomes.append(None)
        except BaseException as error:
            outcomes.append(error)
            if dialog is not None: dialog.reject()
    QTimer.singleShot(0, DuringDialog)
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert outcomes, 'The normal action must open a modal editor'
    if outcomes[0] is not None: raise outcomes[0]


def test_real_project_phase_capsules_insert_dialog_start_policy_and_reopen(tmp_path, qapp, monkeypatch):
    from copy import deepcopy
    from PySide6.QtWidgets import QDialog
    from silverstar_fccg.ui.mission_template import MissionTemplateDialog
    from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
    from test_three_workspace_workflow import _Capsule_Click
    service = FccgService(APP)
    service.policy = WorkspacePolicy(APP.parents[1])
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
    window._model = ReferenceProject_Create(catalog=service.catalog)
    window._Project_Refresh()
    errors = []; monkeypatch.setattr(window, '_Error_Show', errors.append)
    try:
        panel = window.workflow_page.stage_panel
        assert list(panel.cards) == ['ready', 'ascent']
        original = deepcopy(window._model.Dictionary_Get())
        _Modal_Click(panel.create_button, MissionTemplateDialog, lambda dialog: dialog.reject())
        assert window._model.Dictionary_Get() == original
        def Template(dialog):
            assert dialog.launch_threshold.value() == dialog.burnout_threshold.value() == 2.0
            assert not dialog.recovery.isChecked()
            dialog.preset.setCurrentIndex(dialog.preset.findData('acceleration'))
            dialog.accept()
        _Modal_Click(panel.create_button, MissionTemplateDialog, Template)
        _Events_Flush(qapp)
        rows = window._model.mission_process['stages']
        assert [row['stage_id'] for row in rows] == ['ready', 'mission_start', 'ascent', 'coast']
        assert [row['condition']['value'] for row in rows[2:]] == [2.0, 2.0]
        panel.insert_before.setCurrentIndex(panel.insert_before.findData('coast'))
        before_add = deepcopy(window._model.Dictionary_Get())
        _Modal_Click(panel.add_button, MissionStageTransactionDialog, lambda dialog: dialog.reject())
        assert window._model.Dictionary_Get() == before_add
        def Add(dialog):
            dialog.stage_editor.name_edit.setText('User observation')
            dialog.stage_editor.number.setValue(1.25)
            dialog.accept()
            assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
        _Modal_Click(panel.add_button, MissionStageTransactionDialog, Add)
        _Events_Flush(qapp)
        rows = window._model.mission_process['stages']
        assert len(rows) == 5 and rows[4]['stage_id'] == 'coast'
        identity = rows[3]['stage_id']
        assert rows[3]['name'] == 'User observation'
        assert rows[3]['condition']['value'] == 1.25
        def Cancel(dialog):
            dialog.stage_editor.name_edit.setText('discarded')
            dialog.reject()
        _Capsule_Click(window, identity, Cancel); _Events_Flush(qapp)
        assert window._model.mission_process['stages'][3]['name'] == 'User observation'
        def Apply(dialog):
            dialog.stage_editor.name_edit.setText('Observation confirmation')
            dialog.stage_editor.number.setValue(2.5)
            dialog.accept()
            assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
        _Capsule_Click(window, identity, Apply); _Events_Flush(qapp)
        assert window._model.mission_process['stages'][3]['condition']['value'] == 2.5
        assert window._model.mission_process['stages'][3]['stage_id'] == identity
        profile = MissionProfile_Build(window._model, service.catalog)
        assert profile['schema_version'] == 2
        service.ProjectRoot_Save(window._model, tmp_path / 'saved_project')
        reopened = service.Project_Open(tmp_path / 'saved_project')
        assert MissionProfile_Build(reopened, service.catalog) == profile
        window._model = reopened; window._Project_Refresh(); window.show()
        for language in ('zh_CN', 'en_US'):
            window.Language_Apply(language)
            _Events_Flush(qapp)
            ins_id = window._model.strategies['ins']
            heading = window.algorithm_parameters_page._content.findChild(QGroupBox, 'algorithmParameters_' + ins_id)
            assert heading.title() == ('惯导算法' if language == 'zh_CN' else 'Inertial navigation algorithm')
            for theme in ('light', 'dark'):
                window.Theme_Apply(theme)
                for width in (960, 1440):
                    window.resize(width, 900); _Events_Flush(qapp)
                    assert identity in window.workflow_page.stage_panel.cards
                    assert 'process.' not in panel.add_button.text()
        assert MissionProfile_Build(window._model, service.catalog) == profile
        assert not errors
    finally:
        window._project_dirty = False
        window.close(); _Events_Flush(qapp)


def test_stage_dropdowns_open_below_and_scroll_only_over_ten(qapp):
    from silverstar_fccg.core.i18n import Translator
    from silverstar_fccg.project.mission_process import MissionProcess_Default
    from silverstar_fccg.ui.mission_process_panel import MissionStageDialog, MissionProcessPanel
    from silverstar_fccg.ui.widgets import StandardComboBox
    process = MissionProcess_Default()
    targets = [f'pyro{index}' for index in range(12)]
    dialog = MissionStageDialog(Translator('zh_CN'), process, 4, targets)
    panel = MissionProcessPanel(Translator('zh_CN'))
    panel.Configuration_Set(process)
    try:
        assert all(isinstance(combo, StandardComboBox) for combo in dialog.findChildren(QComboBox))
        assert all(isinstance(combo, StandardComboBox) for combo in panel.findChildren(QComboBox))
        dialog.move(10,10); dialog.show(); _Events_Flush(qapp)
        combo = dialog.event_combo
        combo.showPopup(); _Events_Flush(qapp)
        assert combo.view().window().geometry().top() >= combo.mapToGlobal(combo.rect().bottomLeft()).y()
        assert combo.view().verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        combo.hidePopup()
        dialog.action.setCurrentIndex(dialog.action.findData('request_recovery'))
        dialog.target.showPopup(); _Events_Flush(qapp)
        assert dialog.target.maxVisibleItems() == 10
        assert dialog.target.view().verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        assert dialog.target.view().verticalScrollBar().maximum() > 0
        QTest.keyClick(dialog.target.view(), Qt.Key.Key_End)
        QTest.keyClick(dialog.target.view(), Qt.Key.Key_Return)
        assert dialog.target.currentData() == 'pyro11'
        dialog.accept()
        assert dialog.Process_Get()['stages'][4]['action'] == {'kind':'request_recovery','target':'pyro11'}
    finally:
        dialog.close(); panel.close(); _Events_Flush(qapp)


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
