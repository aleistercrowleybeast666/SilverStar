from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QComboBox, QGroupBox
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


def test_real_project_phase_capsules_insert_dialog_start_policy_and_reopen(tmp_path, qapp, monkeypatch):
    from silverstar_fccg.ui.mission_process_panel import MissionStageDialog
    service = FccgService(APP)
    service.policy = WorkspacePolicy(APP.parents[1])
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
    window._model = ReferenceProject_Create(catalog=service.catalog)
    window._Project_Refresh()
    errors = []; monkeypatch.setattr(window, '_Error_Show', errors.append)
    try:
        panel = window.flight_configuration_page.mission_process_panel
        panel.create_button.click(); _Events_Flush(qapp)
        assert len(window._model.mission_process['stages']) == 7
        panel.insert_before.setCurrentIndex(panel.insert_before.findData('deploy'))
        panel.add_button.click(); _Events_Flush(qapp)
        rows = window._model.mission_process['stages']
        assert len(rows) == 8 and rows[5]['stage_id'] == 'deploy'
        identity = rows[4]['stage_id']
        numeric = panel.value_editors[identity]
        numeric.lineEdit().setText('1.25 s')
        QTest.keyClick(numeric, Qt.Key.Key_Return); _Events_Flush(qapp)
        assert window._model.mission_process['stages'][4]['condition']['value'] == 1.25
        def Dialog_Cancel():
            dialog = qapp.activeModalWidget()
            assert isinstance(dialog, MissionStageDialog)
            dialog.name_edit.setText('discarded'); dialog.reject()
        QTimer.singleShot(0, Dialog_Cancel)
        panel.Dialog_Open(identity); _Events_Flush(qapp)
        assert window._model.mission_process['stages'][4]['name'] != 'discarded'
        def Dialog_Apply():
            dialog = qapp.activeModalWidget()
            dialog.name_edit.setText('Pre-deployment confirmation')
            dialog.number.setValue(2.5); dialog.accept()
        QTimer.singleShot(0, Dialog_Apply)
        panel.Dialog_Open(identity); _Events_Flush(qapp)
        assert window._model.mission_process['stages'][4]['condition']['value'] == 2.5
        assert window._model.mission_process['stages'][4]['stage_id'] == identity
        panel.start_policy.setCurrentIndex(panel.start_policy.findData('start_is_launch')); _Events_Flush(qapp)
        rows = window._model.mission_process['stages']
        assert not any(row['stage_id'] == 'mission_start' for row in rows)
        assert next(row for row in rows if row['stage_id'] == 'ascent')['condition']['value'] == 'start_accepted'
        panel.start_policy.setCurrentIndex(panel.start_policy.findData('separate')); _Events_Flush(qapp)
        assert any(row['stage_id'] == 'mission_start' for row in window._model.mission_process['stages'])
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
            heading = window.algorithm_parameters_page.findChild(QGroupBox, 'algorithmParameters_' + ins_id)
            assert heading.title() == ('惯导算法' if language == 'zh_CN' else 'Inertial navigation algorithm')
            for theme in ('light', 'dark'):
                window.Theme_Apply(theme)
                for width in (960, 1440):
                    window.resize(width, 900); _Events_Flush(qapp)
                    assert identity in window.flight_configuration_page.mission_process_panel.cards
                    assert 'process.' not in window.flight_configuration_page.mission_process_panel.add_button.text()
        assert MissionProfile_Build(window._model, service.catalog) == profile
        assert not errors
    finally:
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
