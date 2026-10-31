"""Exercise the three-workspace contract using real editors and native persistence."""
from copy import deepcopy
import json
from pathlib import Path
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer, QObject
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLabel, QPushButton, QTabWidget, QWidget

from silverstar_fccg.app.service import FccgService
from silverstar_fccg.core.settings import SettingsStore
from silverstar_fccg.core.workspace import WorkspacePolicy
from silverstar_fccg.generator.render import _FlightConfigHeader_Render
from silverstar_fccg.project.mission_functions import (
    Functions_Derive, Functions_Issues, ParameterProfile_Build, ParameterProfile_Write)
from silverstar_fccg.project.mission_process import MissionProcess_FirmwareDefault
from silverstar_fccg.ui.main_window import MainWindow

APP = Path(__file__).resolve().parents[1]


def _Events_Flush(qapp):
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def _Capsule_Click(window, identity, interact):
    """Use the ordinary button and nested modal event loop, including cancellation."""
    from silverstar_fccg.ui.mission_stage_transaction import MissionStageTransactionDialog
    outcomes = []
    def DuringDialog():
        dialog = QApplication.activeModalWidget()
        try:
            assert isinstance(dialog, MissionStageTransactionDialog)
            interact(dialog)
            outcomes.append(None)
        except BaseException as error:
            outcomes.append(error)
            if dialog is not None:
                dialog.reject()
    QTimer.singleShot(0, DuringDialog)
    button = window.workflow_page.stage_panel.cards[identity].findChild(QPushButton, 'phaseSelect')
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert outcomes, 'A normal capsule must open its real modal dialog'
    if outcomes[0] is not None:
        raise outcomes[0]


def _Snapshot(model):
    return json.loads(json.dumps(model.Dictionary_Get()))


def _Function_Click(window, identity, interact):
    outcomes = []
    def DuringDialog():
        dialog = QApplication.activeModalWidget()
        try:
            assert dialog._function_id == identity
            interact(dialog)
            outcomes.append(None)
        except BaseException as error:
            outcomes.append(error)
            if dialog is not None:
                dialog.reject()
    window.workflow_page.coverage.Function_Select(identity)
    QTimer.singleShot(0, DuringDialog)
    QTest.mouseClick(window.workflow_page.function_buttons['parameters'], Qt.MouseButton.LeftButton)
    assert outcomes
    if outcomes[0] is not None:
        raise outcomes[0]


@pytest.fixture
def workspace_window(tmp_path, qapp):
    from PySide6.QtWidgets import QMessageBox
    for name in ('msyh.ttc', 'segoeui.ttf'):
        font = Path('C:/Windows/Fonts') / name
        if font.is_file(): QFontDatabase.addApplicationFont(str(font))
    service = FccgService(APP)
    service.policy = WorkspacePolicy(APP.parents[1])
    window = MainWindow(SettingsStore(tmp_path / 'settings.ini'), service=service)
    window._toolchain_checked = True  # Tool detection has its own independent contract.
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    errors = []
    window._Error_Show = lambda *args: errors.append(args)
    yield window, errors
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
    window._project_dirty = False
    window.close()
    _Events_Flush(qapp)


def test_three_workspaces_browse_legacy_without_injecting_execution(workspace_window, tmp_path, qapp):
    window, errors = workspace_window
    model = window._service.ReferenceProject_Create('ThreeWorkspacesLegacy')
    model.mission_process = None  # An imported fixed-runtime project, before explicit migration.
    before = _Snapshot(model)
    root = window._service.ProjectRoot_Save(model, tmp_path / 'legacy')
    window._Project_Open(root)
    assert window.pages.count() == window.navigation_list.count() == 3
    assert not window.workflow_page.findChildren(QTabWidget)
    assert set(window.workflow_page.stage_panel.cards) == {
        'ready', 'mission_start', 'ascent', 'coast', 'deploy', 'descent', 'landed'}
    assert 'enabled' not in before['ground_target']
    assert not hasattr(window.ground_target_page, 'enabled')
    for language in ('zh_CN', 'en_US'):
        window.Language_Apply(language)
        for theme in ('light', 'dark'):
            window.Theme_Apply(theme)
            for index in range(3):
                window.navigation_list.setCurrentRow(index)
                window.resize(1000, 750)
                window.show()
                _Events_Flush(qapp)
                window.workflow_page.stage_panel.Stage_Select('coast')
                assert _Snapshot(window._model) == before
    assert window._model.mission_process is None
    assert window._model.mission_functions is None
    assert not errors


def test_modal_condition_and_shared_interval_survive_reopen(workspace_window, tmp_path, qapp):
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('Ordinary stage edit')
    window._model.mission_process = MissionProcess_FirmwareDefault(acceleration_detection=True)
    window._Project_Refresh()
    window.navigation_list.setCurrentRow(1)
    before = _Snapshot(window._model)
    changes = []
    window.workflow_page.configurationChanged.connect(changes.append)
    def Cancel(dialog):
        dialog.stage_editor.name_edit.setText('Discard this edit')
        dialog.reject()
    _Capsule_Click(window, 'coast', Cancel)
    _Events_Flush(qapp)
    assert _Snapshot(window._model) == before and not changes
    assert window.workflow_page.stage_panel.condition_editor is None
    def Apply(dialog):
        from test_workflow_connections import _InFunction
        dialog.stage_editor.name_edit.setText('Stable coast identity')
        dialog.stage_editor.signal_combo.setCurrentIndex(dialog.stage_editor.signal_combo.findData('stage_elapsed_s'))
        dialog.stage_editor.number.setValue(1.123456)
        def Function(child):
            section = child.bindings[0]._sections['telemetry.range']
            form = section.body.layout()
            start = form.itemAt(0, form.ItemRole.FieldRole).widget()
            stop = form.itemAt(1, form.ItemRole.FieldRole).widget()
            start.setCurrentIndex(start.findData(('stage_enter', 'ascent')))
            stop.setCurrentIndex(stop.findData(('stage_exit', 'coast')))
        _InFunction(dialog, 'telemetry', Function)
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    _Capsule_Click(window, 'coast', Apply)
    _Events_Flush(qapp)
    assert len(changes) == 1
    coast = next(row for row in window._model.mission_process['stages'] if row['stage_id'] == 'coast')
    assert coast['name'] == 'Stable coast identity' and coast['condition']['value'] == 1.123456
    function = next(row for row in window._model.mission_functions['functions'] if row['instance_id'] == 'telemetry')
    assert function['start']['stage_id'] == 'ascent' and function['stop']['stage_id'] == 'coast'
    assert function['stop']['kind'] == 'stage_exit' and window._model.mission_functions['schema_version'] == 2
    for identity in ('ready', 'ascent', 'coast'):
        window.workflow_page.stage_panel.Stage_Select(identity)
        _Events_Flush(qapp)
        assert len([row for row in Functions_Derive(window._model, window._service.catalog)['functions']
                    if row['instance_id'] == 'telemetry']) == 1
    saved = _Snapshot(window._model)
    root = window._service.ProjectRoot_Save(window._model, tmp_path / 'custom')
    restored = window._service.Project_Open(root)
    assert _Snapshot(restored) == saved
    # Until an adapter proves a runtime consumer, export remains fail-closed.
    if any(issue.code == 'FUNCTION_REFERENCE_ONLY' for issue in Functions_Issues(restored, window._service.catalog)):
        with pytest.raises(ValueError, match='FUNCTION_REFERENCE_ONLY'):
            _FlightConfigHeader_Render(restored, window._service.catalog)
    assert not errors


def test_parameter_preview_cancel_and_apply_touch_only_actual_owner(workspace_window, tmp_path, qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('ParameterImportWorkspace')
    window._Project_Refresh()
    owner = window._model.strategies['ins']
    profile = ParameterProfile_Build(window._model, window._service.catalog, owner)
    parameter = next(row for row in profile['parameters'] if row['id'] == 'mechanization_aggregation')
    parameter['value'] = 1
    path = tmp_path / 'mechanization.ssparams'
    ParameterProfile_Write(path, profile)
    before = _Snapshot(window._model)
    monkeypatch.setattr('silverstar_fccg.ui.main_window.QFileDialog.getOpenFileName',
                        lambda *args, **kwargs: (str(path), ''))
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Cancel
    window._ParameterProfile_Import(owner)
    assert _Snapshot(window._model) == before
    window._MessageBox_Exec = lambda *args, **kwargs: QMessageBox.StandardButton.Apply
    window._ParameterProfile_Import(owner)
    _Events_Flush(qapp)
    after = _Snapshot(window._model)
    assert after['algorithm_parameters'][owner]['mechanization_aggregation'] == 1
    expected = deepcopy(before)
    expected['algorithm_parameters'][owner]['mechanization_aggregation'] = 1
    assert after == expected
    assert not errors


def test_issue_list_reveals_reference_stage_and_exact_shared_function(workspace_window, qapp):
    from silverstar_fccg.project.validation import Project_Validate
    window, errors = workspace_window
    model = window._service.Project_Open(APP / 'examples/Uncontrolled_Desktop_Reference.ssproject')
    model.mission_functions = Functions_Derive(model, window._service.catalog)
    function = next(row for row in model.mission_functions['functions'] if row['instance_id'] == 'estimator')
    function['start'] = {'kind': 'stage_enter', 'stage_id': 'removed_boundary'}
    window._model = model
    window._Project_Refresh()
    window.show()
    issues = Project_Validate(model, window._service.catalog).issues
    reference = next(issue for issue in issues if issue.code == 'MISSION_PROCESS_REFERENCE_ONLY')
    window.navigation_list.setCurrentRow(2)
    window.build_page.issueActivated.emit(reference)
    _Events_Flush(qapp)
    assert window.navigation_list.currentRow() == 1
    assert window._validation_focus_widget is window.workflow_page.stage_panel
    issue = next(issue for issue in issues if issue.code.startswith('FUNCTION_') and issue.message.startswith('estimator:'))
    window.navigation_list.setCurrentRow(2)
    window.build_page.issueActivated.emit(issue)
    _Events_Flush(qapp)
    assert window.navigation_list.currentRow() == 1
    assert window._validation_focus_widget is window.workflow_page.coverage
    assert window.workflow_page.coverage._functions[window.workflow_page.coverage.currentRow()] == 'estimator'
    assert not errors


@pytest.mark.parametrize('width', [900, 1024])
def test_english_small_workflow_and_dialog_keep_fields_in_view(workspace_window, qapp, width):
    from PySide6.QtWidgets import QScrollArea, QBoxLayout
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('Narrow workflow')
    window._Project_Refresh()
    window.Language_Apply('en_US')
    window.Theme_Apply('dark')
    window.resize(width, 800)
    window.show()
    window.navigation_list.setCurrentRow(1)
    workflow = window.workflow_page
    panel = workflow.stage_panel
    _Events_Flush(qapp)
    QTest.qWait(40)
    scroll = workflow._scroll
    assert scroll.widget().width() <= scroll.viewport().width()
    assert panel.toolbar.direction() == QBoxLayout.Direction.TopToBottom
    for control in (panel.create_button, panel.insert_before, panel.add_button):
        position = control.mapTo(scroll.viewport(), control.rect().topLeft())
        assert 0 <= position.x() and position.x() + control.width() <= scroll.viewport().width()
    def Inspect(dialog):
        dialog.resize(740, 620)
        qapp.processEvents()
        for control in (dialog.stage_editor.name_edit, dialog.stage_editor.event_combo):
            viewport = dialog.scroll.viewport()
            position = control.mapTo(viewport, control.rect().topLeft())
            assert 0 <= position.x() and position.x() + control.width() <= viewport.width()
        dialog.reject()
    _Capsule_Click(window, 'ascent', Inspect)
    assert not errors


@pytest.mark.parametrize('close_kind', ['cancel', 'escape', 'close'])
def test_normal_capsule_cancel_discards_parameters_and_ranges(workspace_window, qapp, close_kind):
    window, errors = workspace_window
    window._model = window._service.ReferenceProject_Create('Cancel transaction')
    window._Project_Refresh()
    before = _Snapshot(window._model)
    def Discard(dialog):
        from test_workflow_connections import _InFunction
        dialog.stage_editor.name_edit.setText('Keyboard coast draft')
        def Parameters(child):
            owner = child._draft.strategies['ins']
            child._Parameters_Reveal(owner)
            editor = child.parameters.editors[(owner, 'mechanization_aggregation')]
            editor.CommittedValue_Set(1)
            child._Parameter_Set(owner, 'mechanization_aggregation', 1)
        _InFunction(dialog, 'ins', Parameters)
        if close_kind == 'escape':
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
        elif close_kind == 'close':
            dialog.close()
        else:
            dialog.reject()
    _Capsule_Click(window, 'ascent', Discard)
    _Events_Flush(qapp)
    assert _Snapshot(window._model) == before
    window.workflow_page.stage_panel.Stage_Select('ready')
    assert _Snapshot(window._model) == before and not errors


def test_invalid_range_keeps_draft_and_referenced_stage_cannot_be_removed(workspace_window, qapp):
    window, errors = workspace_window
    model = window._service.ReferenceProject_Create('Invalid native range')
    model.mission_process = MissionProcess_FirmwareDefault(acceleration_detection=True)
    model.mission_functions = Functions_Derive(model, window._service.catalog)
    function = next(row for row in model.mission_functions['functions'] if row['instance_id'] == 'recording')
    function.update(start={'kind':'stage_enter','stage_id':'ascent'}, stop={'kind':'stage_exit','stage_id':'coast'})
    model.mission_functions['schema_version'] = 2
    window._model = model
    window._Project_Refresh()
    before = _Snapshot(window._model)
    panel = window.workflow_page.stage_panel
    panel.Stage_Remove('ascent')
    assert panel.error.text() and _Snapshot(window._model) == before
    def Invalid(dialog):
        from test_workflow_connections import _InFunction
        dialog.stage_editor.name_edit.setText('Keep this draft')
        def Range(child):
            form = child.bindings[0]._sections['recording.range'].body.layout()
            start = form.itemAt(0, form.ItemRole.FieldRole).widget()
            stop = form.itemAt(1, form.ItemRole.FieldRole).widget()
            start.setCurrentIndex(start.findData(('stage_enter', 'coast')))
            stop.setCurrentIndex(stop.findData(('stage_exit', 'ascent')))
            child.accept()
            assert child.result() != QDialog.DialogCode.Accepted
            assert child.error.text()
            assert tuple(start.currentData()) == ('stage_enter', 'coast')
            child.reject()
        _InFunction(dialog, 'recording', Range, apply=False)
        assert dialog.stage_editor.name_edit.text() == 'Keep this draft'
        dialog.reject()
    _Capsule_Click(window, 'coast', Invalid)
    _Events_Flush(qapp)
    assert _Snapshot(window._model) == before and not errors


def test_background_cancel_freezes_editors_and_never_reports_success(workspace_window, qapp):
    window, errors = workspace_window
    before = _Snapshot(window._model)
    results = []
    def Waiting(context):
        context.Progress_Report(0.25, 'status.task_running')
        for _index in range(500):
            context.Cancel_RaiseIfRequested()
            time.sleep(0.01)
        return 'unexpected completion'
    assert window.Task_Run(Waiting, results.append, indeterminate=False)
    deadline = time.monotonic() + 3
    while window.progress_bar.value() < 250 and time.monotonic() < deadline:
        qapp.processEvents(); time.sleep(0.005)
    assert not window.hardware_workspace.isEnabled()
    assert not window.workflow_page.isEnabled()
    assert window.navigation_list.isEnabled() and window.cancel_button.isEnabled()
    window.cancel_button.click()
    deadline = time.monotonic() + 3
    while window._active_worker is not None and time.monotonic() < deadline:
        qapp.processEvents(); time.sleep(0.005)
    _Events_Flush(qapp)
    assert window._active_worker is None and not results
    assert window.progress_bar.property('taskState') == 'cancelled'
    assert window.progress_bar.value() < window.progress_bar.maximum()
    assert window.hardware_workspace.isEnabled() and window.workflow_page.isEnabled()
    assert _Snapshot(window._model) == before and not errors


def test_recording_and_telemetry_ranges_are_read_only_and_restore_real_lifecycle(workspace_window, qapp):
    window, errors = workspace_window
    model = window._service.Project_Open(APP / 'examples/Uncontrolled_Desktop_Reference.ssproject')
    model.mission_functions = Functions_Derive(model, window._service.catalog)
    recording = next(row for row in model.mission_functions['functions'] if row['instance_id']=='recording')
    recording['start'] = {'kind':'stage_enter', 'stage_id':'ascent'}
    window._model = model
    window._Project_Refresh()
    for identity in ('recording', 'telemetry'):
        def Inspect(dialog):
            section = dialog.bindings[0]._sections[identity + '.range']
            form = section.body.layout()
            assert not form.itemAt(0, form.ItemRole.FieldRole).widget().isEnabled()
            assert not form.itemAt(1, form.ItemRole.FieldRole).widget().isEnabled()
            reason = window._translator.Text_Get('workflow.lifecycle_only')
            assert any(reason == label.text() for label in section.body.findChildren(QLabel))
            dialog.reject()
        _Function_Click(window, identity, Inspect)
    assert any(issue.function_id=='recording' and issue.code=='FUNCTION_REFERENCE_ONLY'
               for issue in Functions_Issues(window._model, window._service.catalog))
    def Restore(dialog):
        section = dialog.bindings[0]._sections['recording.range']
        restore = next(button for button in section.body.findChildren(QPushButton)
                       if button.text()==window._translator.Text_Get('workflow.restore_lifecycle'))
        restore.click()
        dialog.accept()
        assert dialog.result() == QDialog.DialogCode.Accepted, dialog.error.text()
    _Function_Click(window, 'recording', Restore)
    _Events_Flush(qapp)
    recording = next(row for row in window._model.mission_functions['functions'] if row['instance_id']=='recording')
    assert recording['start']=={'kind':'system_prepare','stage_id':''}
    assert recording['stop']=={'kind':'lifecycle_end','stage_id':''}
    assert not any(issue.function_id=='recording' for issue in Functions_Issues(window._model, window._service.catalog))
    assert not errors


@pytest.mark.parametrize('legacy_page,expected', [
    ('page.navigation_configuration', 1), ('page.telemetry_configuration', 0), (6, 2), (99, 0)])
def test_old_navigation_preferences_migrate_by_meaning(workspace_window, tmp_path, qapp, legacy_page, expected):
    window, errors = workspace_window
    window._settings.Value_Set('page_index', legacy_page)
    model = window._service.ReferenceProject_Create('PreferenceMigration')
    before = _Snapshot(model)
    root = window._service.ProjectRoot_Save(model, tmp_path / 'preferences')
    window._Project_Open(root)
    _Events_Flush(qapp)
    assert window.navigation_list.currentRow() == expected
    assert _Snapshot(window._model) == before
    assert not errors
